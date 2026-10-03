# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingTypeStubs=false
"""POST /query and GET /query/stream endpoints.

The pipeline holds long-lived clients (qdrant, httpx) so we build it
once and cache it. Tests override ``get_pipeline`` via FastAPI's
``app.dependency_overrides`` to inject mocks — that's why this module
exposes ``get_pipeline`` as a module-level function instead of a closure.

``sse_starlette`` ships without stubs; pyright noise is silenced at the
file level (same pattern used in ``corpus/openalex_client.py``).
"""

import json
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from neblab_rag.providers.factory import (
    build_bm25_index,
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)
from neblab_rag.rag.generator import AnswerGenerator
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.query_rewriter import QueryRewriter
from neblab_rag.rag.retriever import HybridRetriever

router = APIRouter(tags=["rag"])


class QueryRequest(BaseModel):
    query: str
    top_k: int = 12


class CitationOut(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    citation_valid: bool


@lru_cache(maxsize=1)
def _build_pipeline() -> RAGPipeline:
    llm = build_llm_provider()
    retriever = HybridRetriever(
        embedder=build_embedding_provider(),
        qdrant=build_qdrant_repo(),
        reranker=build_reranker_provider(),
        # Sprint 2.5: BM25 hybrid. Index built once at startup from current
        # Postgres state — restart the API after re-indexing the corpus.
        bm25=build_bm25_index(),
    )
    return RAGPipeline(
        retriever=retriever,
        generator=AnswerGenerator(llm=llm),
        # Same LLM instance for rewriting — translation is a cheap chat call
        query_rewriter=QueryRewriter(llm=llm),
    )


def get_pipeline() -> RAGPipeline:
    return _build_pipeline()


PipelineDep = Annotated[RAGPipeline, Depends(get_pipeline)]


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, pipeline: PipelineDep) -> QueryResponse:
    result = await pipeline.answer(query=req.query, top_k=req.top_k)
    return QueryResponse(
        answer=result.answer.content,
        citations=[CitationOut(**c.model_dump()) for c in result.answer.citations],
        citation_valid=result.citation_validation.is_valid,
    )


@router.get("/query/stream")
async def stream(query: str, pipeline: PipelineDep, top_k: int = 12) -> EventSourceResponse:
    """SSE streaming endpoint.

    Emits in order:
      - one ``citations`` event with the JSON-encoded citation ledger
      - many ``delta`` events, each carrying a fragment of the answer
      - a single ``done`` event when streaming completes
    """
    chunks = await pipeline.retriever.retrieve(query=query, top_k=top_k)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        citations_payload = [
            {
                "number": i + 1,
                "doc_id": c.doc_id,
                "openalex_id": c.openalex_id,
                "title": c.title,
            }
            for i, c in enumerate(chunks)
        ]
        yield {"event": "citations", "data": json.dumps(citations_payload)}

        async for delta in pipeline.generator.stream(query=query, chunks=chunks):
            yield {"event": "delta", "data": delta}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())
