# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingTypeStubs=false
"""POST /query and GET /query/stream endpoints for plant virus RAG.

Sprint 5e: supports both single-turn (``query``) and multi-turn
(``messages``) request formats.
"""

import json
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse

from neblab_rag.db.engine import get_session
from neblab_rag.rag.answer_validator import AnswerValidation
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.retriever import RetrievedChunk
from plant_virus_rag.db.models import PvDocument
from plant_virus_rag.rag.conversation import ConvMessage, latest_user_message
from plant_virus_rag.rag.pipeline import build_pv_pipeline
from plant_virus_rag.rag.task_classifier import classify

router = APIRouter(tags=["rag"])


class QueryRequest(BaseModel):
    query: str = ""  # single-turn (backward-compat)
    messages: list[ConvMessage] | None = None  # multi-turn (Sprint 5e)
    top_k: int = 12

    @field_validator("top_k")
    @classmethod
    def _clamp_top_k(cls, v: int) -> int:
        """Clamp top_k into 1..20.

        2026-10-03 audit (P1): top_k was accepted unbounded — a single
        anonymous request could ask for a huge candidate pool and drive
        retrieval/rerank cost. Out-of-range values are clamped, not rejected,
        to stay backward compatible with existing callers.
        """
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 12
        return max(1, min(v, 20))

    def effective_query(self) -> str:
        if self.messages:
            return latest_user_message(self.messages)
        return self.query


class CitationOut(BaseModel):
    number: int
    doc_id: int
    title: str
    chunk_text: str = ""
    authors: list[str] | None = None
    venue: str | None = None
    year: int | None = None
    doi: str | None = None
    ama: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    citation_valid: bool
    task_type: str = "qa"
    # Semantic citation-fidelity check (LLM-judged).  ``fidelity_score`` is
    # None when the validator could not run or its output could not be parsed —
    # that means "validation unavailable", NOT a pass (see answer_validator).
    answer_validation: AnswerValidation | None = None


def _format_ama(citation: "CitationOut") -> str:
    """Build an AMA-style citation string."""
    parts: list[str] = []

    # Authors
    if citation.authors:
        formatted_authors = []
        for a in citation.authors:
            parts_names = a.split(", ")
            if len(parts_names) >= 2:
                last = parts_names[0]
                initials = "".join(
                    n[0].upper() for n in parts_names[1].split() if n
                )
                formatted_authors.append(f"{last} {initials}")
            else:
                formatted_authors.append(a)
        if len(formatted_authors) <= 6:
            parts.append(", ".join(formatted_authors))
        else:
            parts.append(", ".join(formatted_authors[:6]) + ", et al.")

    # Title
    parts.append(citation.title + ".")

    # Venue
    if citation.venue:
        parts[-1] = parts[-1][:-1]
        parts.append(f"{citation.venue}.")

    # Year
    if citation.year:
        parts[-1] = parts[-1][:-1]
        parts.append(f"{citation.year}.")

    # DOI
    if citation.doi:
        parts.append(f"https://doi.org/{citation.doi}")

    return " ".join(parts)


def _enrich_citations(
    chunks: list[RetrievedChunk],
) -> list[CitationOut]:
    """Build citations with full metadata from pv_documents table."""
    doc_ids = list({c.doc_id for c in chunks})

    # Fetch document metadata from Postgres
    docs_by_id: dict[int, PvDocument] = {}
    with get_session() as session:
        stmt = session.query(PvDocument).where(PvDocument.id.in_(doc_ids))
        for doc in session.execute(stmt).scalars().all():
            docs_by_id[doc.id] = doc

    citations: list[CitationOut] = []
    seen: set[int] = set()
    cited_number = 0
    for c in chunks:
        if c.doc_id in seen:
            continue
        seen.add(c.doc_id)
        cited_number += 1

        doc = docs_by_id.get(c.doc_id)
        cit = CitationOut(
            number=cited_number,
            doc_id=c.doc_id,
            title=c.title,
            chunk_text=c.text,
            authors=doc.authors if doc else None,
            venue=doc.venue if doc else None,
            year=doc.year if doc else None,
            doi=doc.doi if doc else None,
            ama="",
        )
        cit.ama = _format_ama(cit)
        citations.append(cit)

    return citations


@lru_cache(maxsize=1)
def _build_pipeline() -> RAGPipeline:
    return build_pv_pipeline(with_rewriter=True, with_bm25=True)


def get_pipeline() -> RAGPipeline:
    return _build_pipeline()


PipelineDep = Annotated[RAGPipeline, Depends(get_pipeline)]


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, pipeline: PipelineDep) -> QueryResponse:
    effective = req.effective_query()
    task_type = classify(effective).value

    result = await pipeline.answer(query=effective, top_k=req.top_k)
    citations = _enrich_citations(result.chunks)
    return QueryResponse(
        answer=result.answer.content,
        citations=citations,
        citation_valid=result.citation_validation.is_valid,
        task_type=task_type,
        # 透出语义校验结果（此前被丢弃）——前端可据此显示可信度；
        # fidelity_score=None / is_reliable=False 表示"校验不可用"而非"通过"。
        answer_validation=result.answer_validation,
    )


@router.get("/query/stream")
async def stream(
    # Depends 已包含在 Annotated 里（fastapi>=0.139 不再允许 Annotated+默认值双写）；
    # 无默认值的参数必须排在带默认值的参数之前。
    pipeline: PipelineDep,
    query: str = "",
    top_k: int = Query(12, ge=1, le=20),  # 与 QueryRequest 相同的 1..20 上限
) -> EventSourceResponse:
    """SSE streaming endpoint for PV RAG.

    Emits in order:
      - ``task_type`` event — "qa" / "planning" / "meta"
      - ``citations`` event with JSON citation ledger
      - ``delta`` events with answer fragments
      - ``done`` event when complete

    Supports ``?query=...`` for backward compat.
    """
    chunks = await pipeline.retriever.retrieve(query=query, top_k=top_k)
    task_type = classify(query).value

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield {"event": "task_type", "data": task_type}
        citations = _enrich_citations(chunks)
        yield {
            "event": "citations",
            "data": json.dumps([c.model_dump() for c in citations]),
        }

        async for delta in pipeline.generator.stream(query=query, chunks=chunks):
            yield {"event": "delta", "data": delta}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())
