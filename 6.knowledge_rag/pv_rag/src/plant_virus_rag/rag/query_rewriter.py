"""Multi-turn query rewriter — extends neblab_rag's zh→en rewriter with
conversation-context folding (Sprint 5e).
"""

from neblab_rag.logging_config import get_logger
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest
from neblab_rag.rag.query_rewriter import QueryRewriter, RewrittenQuery
from plant_virus_rag.rag.conversation import (
    ConvMessage,
    conversation_summary,
    latest_user_message,
)

log = get_logger(__name__)

REWRITE_WITH_CONTEXT_PROMPT = """You rewrite the user's LATEST message into a self-contained English query suitable for searching an English-language academic literature corpus.

You receive the conversation transcript so far. Use prior turns ONLY to resolve references in the latest message ("expand section 3", "more details on that"). The query you produce must be understandable on its own without seeing the transcript.

Rules:
1. Output ONLY the rewritten English query — no quotes, no commentary, no markdown.
2. If the latest message is already self-contained and English, return it unchanged.
3. Preserve technical terms and domain vocabulary.
4. Keep it concise — what a researcher would type into a search box (single sentence preferred)."""


class PvQueryRewriter(QueryRewriter):
    """Extends neblab_rag QueryRewriter with multi-turn context folding."""

    async def rewrite_with_context(
        self, messages: list[ConvMessage]
    ) -> RewrittenQuery:
        """Fold conversation context into a standalone query for retrieval.

        First-turn calls delegate to the simpler ``rewrite()`` path so the
        extra LLM hop is only paid for actual follow-ups.
        """
        latest = latest_user_message(messages)
        if not latest:
            return RewrittenQuery(original="", rewritten="", was_rewritten=False)
        if len(messages) <= 1:
            return await self.rewrite(latest)

        transcript = conversation_summary(messages)
        try:
            resp = await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(
                            role="system", content=REWRITE_WITH_CONTEXT_PROMPT
                        ),
                        ChatMessage(role="user", content=transcript),
                    ],
                    temperature=0.0,
                    max_tokens=256,
                )
            )
        except Exception as exc:
            log.warning("context_rewrite_failed", error=str(exc), latest=latest)
            return await self.rewrite(latest)

        cleaned = resp.content.strip().strip('"').strip("'").strip()
        if not cleaned:
            log.warning("context_rewrite_empty", latest=latest)
            return await self.rewrite(latest)

        log.info("context_rewritten", original=latest, rewritten=cleaned)
        return RewrittenQuery(
            original=latest, rewritten=cleaned, was_rewritten=cleaned != latest
        )
