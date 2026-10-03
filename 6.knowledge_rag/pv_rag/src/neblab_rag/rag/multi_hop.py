"""Multi-hop retrieval: detect gaps in the first answer and trigger a second retrieval.

Only activates for complex questions (PLANNING type or questions with >5 words).
The gap analysis uses a lightweight LLM call to decide if a second retrieval is needed.
"""

from pydantic import BaseModel

from neblab_rag.logging_config import get_logger
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider
from neblab_rag.rag.retriever import RetrievedChunk, Retriever

log = get_logger(__name__)

GAP_DETECTION_PROMPT = """You are a gap detector for a plant virus knowledge base.
Given a user question and a generated answer based on retrieved fragments,
decide whether critical information is MISSING from the answer that a second
retrieval could fill.

Respond with a JSON object:
{
  "needs_second_hop": true or false,
  "gap_topics": ["topic1", "topic2"],  // only if needs_second_hop
  "search_query": "combined search query for second retrieval"  // only if needs_second_hop
}

A second hop is needed when:
- The question asks about multiple aspects (e.g. detection AND control) but the answer only covers one
- The question is a comparison but only one side is addressed
- The answer explicitly mentions data gaps or says "not found in database" for a key aspect
- The question is about a specific virus but the fragments are about related but different viruses

A second hop is NOT needed when:
- The answer is comprehensive and addresses all parts of the question
- The question is a simple definition or fact lookup
- The fragments simply don't exist in the database (no point re-searching)
"""


class GapAnalysis(BaseModel):
    needs_second_hop: bool
    gap_topics: list[str] = []
    search_query: str = ""


class MultiHopResult(BaseModel):
    first_chunks: list[RetrievedChunk]
    second_chunks: list[RetrievedChunk] = []
    gap_analysis: GapAnalysis | None = None
    final_chunks: list[RetrievedChunk] = []  # deduplicated combined


async def detect_and_retrieve(
    query: str,
    first_answer: str,
    first_chunks: list[RetrievedChunk],
    retriever: Retriever,
    llm: LLMProvider,
    top_k: int = 12,
) -> MultiHopResult:
    """Detect gaps in first answer and optionally trigger second retrieval.

    Only activates for questions with >3 words (skip trivial lookups).
    Falls back gracefully if the LLM call fails.
    """
    import json as _json
    import re as _re

    # Skip multi-hop for very short queries
    if len(query.split()) <= 3:
        return MultiHopResult(
            first_chunks=first_chunks,
            final_chunks=first_chunks,
        )

    # Truncate answer to first 1500 chars for gap detection
    short_answer = first_answer[:1500]

    try:
        resp = await llm.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=GAP_DETECTION_PROMPT),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Question: {query}\n\n"
                            f"Answer (from first retrieval):\n{short_answer}\n\n"
                            "Are there critical gaps that a second retrieval could fill?"
                        ),
                    ),
                ],
                temperature=0.0,
                max_tokens=200,
            )
        )
        text = resp.content.strip()
        if text.startswith("```"):
            text = _re.sub(r"^```(?:json)?\s*", "", text)
            text = _re.sub(r"```\s*$", "", text)
        gap = _json.loads(text)
    except Exception as exc:
        log.warning("gap_detection_failed", error=str(exc))
        return MultiHopResult(
            first_chunks=first_chunks,
            final_chunks=first_chunks,
        )

    needs_hop = gap.get("needs_second_hop", False)
    search_query = gap.get("search_query", "")

    if not needs_hop or not search_query:
        return MultiHopResult(
            first_chunks=first_chunks,
            final_chunks=first_chunks,
        )

    # Second retrieval
    try:
        second_chunks = await retriever.retrieve(query=search_query, top_k=top_k)
    except Exception as exc:
        log.warning("second_hop_retrieval_failed", error=str(exc))
        return MultiHopResult(
            first_chunks=first_chunks,
            final_chunks=first_chunks,
        )

    # Deduplicate by doc_id
    seen_ids = {c.doc_id for c in first_chunks}
    new_chunks = [c for c in second_chunks if c.doc_id not in seen_ids]
    final = first_chunks + new_chunks

    log.info(
        "multi_hop_complete",
        first_count=len(first_chunks),
        second_count=len(second_chunks),
        new_count=len(new_chunks),
        final_count=len(final),
    )

    return MultiHopResult(
        first_chunks=first_chunks,
        second_chunks=second_chunks,
        gap_analysis=GapAnalysis(
            needs_second_hop=True,
            gap_topics=gap.get("gap_topics", []),
            search_query=search_query,
        ),
        final_chunks=final,
    )
