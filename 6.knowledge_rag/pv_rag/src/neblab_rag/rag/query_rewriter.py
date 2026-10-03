"""Translate and expand user queries before retrieval.

Why this exists: Sprint-2 baseline showed that Chinese questions retrieve
unrelated documents even when the topic exists in the corpus, because the
corpus is English and the cross-lingual embedding gap is real.

Sprint-5 update: added query expansion (synonyms + related terms) to improve
recall for short or ambiguous queries.  The expanded query goes to the
retriever; the original query goes to the generator.

Workflow when wired into the pipeline:
  - User asks any question
  - Rewriter detects CJK -> asks LLM to translate to natural English
  - Rewriter expands the query with synonyms/related terms
  - Expanded query goes to retriever (better recall)
  - Original query goes to generator (so the answer matches user language)

Failure mode: if any LLM call fails, we fall back to the original query
rather than crash. Worst case we get the same retrieval quality as before.
"""

from pydantic import BaseModel

from neblab_rag.logging_config import get_logger
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider

log = get_logger(__name__)


REWRITE_SYSTEM_PROMPT = """You translate user research questions into natural English suitable for searching an English-language academic literature corpus.

Rules:
1. Output ONLY the translated English query, nothing else. No quotes, no commentary, no markdown.
2. Preserve the user intent and any technical terms.
3. If the input is already English, return it unchanged.
4. Keep it concise -- aim to match what a researcher would type into a search box."""


QUERY_EXPAND_SYSTEM_PROMPT = """You are a search query expansion engine for a plant virus research database.
Given a user question, expand it into 2-4 keyword-rich search phrases
optimized for dense + sparse retrieval over an academic corpus.

Rules:
1. Output ONLY the expanded search phrases, one per line. No commentary.
2. Include synonyms, related method names, virus species names, and technical terms.
3. Cover multiple angles: detection, control, epidemiology, taxonomy -- as relevant.
4. Keep each phrase concise (5-15 words), like what a researcher would type.
5. If the query is already detailed, still add 1-2 variant formulations.

Example:
Input: "How to detect TYLCV?"
Output:
Tomato yellow leaf curl virus detection methods
TYLCV diagnosis PCR LAMP serological methods
begomovirus detection molecular diagnostics techniques"""


class RewrittenQuery(BaseModel):
    original: str
    rewritten: str
    was_rewritten: bool


def has_cjk(text: str) -> bool:
    """True if text contains any CJK unified ideograph (rough Chinese marker)."""
    return any(0x4E00 <= ord(c) <= 0x9FFF for c in text)


class QueryRewriter:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def expand(self, query: str) -> str:
        """Expand a query with synonyms and related terms for better retrieval."""
        try:
            resp = await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(role="system", content=QUERY_EXPAND_SYSTEM_PROMPT),
                        ChatMessage(role="user", content=query),
                    ],
                    temperature=0.1,
                    max_tokens=128,
                )
            )
        except Exception as exc:
            log.warning("query_expand_failed", error=str(exc), query=query)
            return query

        expanded = resp.content.strip()
        if not expanded:
            return query
        # Merge original query with expanded phrases
        combined = query + " " + " ".join(
            line.strip() for line in expanded.split("\n") if line.strip()
        )
        log.info("query_expanded", original=query, expanded=combined)
        return combined

    async def rewrite(self, query: str) -> RewrittenQuery:
        if not has_cjk(query):
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)

        try:
            resp = await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(role="system", content=REWRITE_SYSTEM_PROMPT),
                        ChatMessage(role="user", content=query),
                    ],
                    temperature=0.0,
                    max_tokens=256,
                )
            )
        except Exception as exc:
            log.warning("query_rewrite_failed", error=str(exc), query=query)
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)

        cleaned = resp.content.strip().strip('"').strip("'").strip()
        if not cleaned:
            log.warning("query_rewrite_empty", query=query)
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)

        log.info("query_rewritten", original=query, rewritten=cleaned)
        return RewrittenQuery(original=query, rewritten=cleaned, was_rewritten=True)
