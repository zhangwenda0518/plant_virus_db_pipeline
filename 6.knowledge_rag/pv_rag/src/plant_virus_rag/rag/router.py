"""Lightweight task router for plant virus RAG.

Classify the user query → dispatch to the right handler:
  - META     → canned system_info answer (no retrieval, no LLM)
  - QA       → retrieves + generates with strict evidence-bound prompt
  - PLANNING → retrieves + generates with labeled-reasoning prompt

Supports both single-turn (query: str) and multi-turn (messages: list[ConvMessage]).
"""

from __future__ import annotations

from neblab_rag.rag.generator import GeneratedAnswer
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.retriever import RetrievedChunk
from plant_virus_rag.rag.conversation import ConvMessage, latest_user_message
from plant_virus_rag.rag.generator import PvAnswerGenerator
from plant_virus_rag.rag.system_info import (
    IDENTITY_ANSWER,
    PvSystemInfoProvider,
    format_meta_answer,
    is_identity_query,
)
from plant_virus_rag.rag.task_classifier import TaskType, classify


class PvRouter:
    """Task router with multi-turn support.

    Single-turn callers pass ``query``; multi-turn callers pass ``messages``
    (the latest user message is extracted for classification + retrieval).
    """

    def __init__(
        self,
        pipeline: RAGPipeline,
        info_provider: PvSystemInfoProvider,
    ):
        self._pipeline = pipeline
        self._info = info_provider

    def classify(self, query: str) -> TaskType:
        return classify(query)

    async def answer(
        self,
        query: str | None = None,
        *,
        messages: list[ConvMessage] | None = None,
        top_k: int = 12,
    ) -> tuple[str, list[RetrievedChunk], GeneratedAnswer, TaskType]:
        """Route and answer.

        When ``messages`` is provided, the latest user message is used for
        classification and retrieval; the full history is passed to the
        generator.
        """
        # Extract the effective query
        if messages:
            effective = latest_user_message(messages)
            history = messages
        else:
            effective = query or ""
            history = None

        task = classify(effective)

        if task == TaskType.META:
            return await self._meta_answer(effective)

        # QA or PLANNING: set the generator's task_type + history, then delegate
        if isinstance(self._pipeline.generator, PvAnswerGenerator):
            self._pipeline.generator._current_task_type = task
            self._pipeline.generator._current_history = history

        # Note: the pipeline's QueryRewriter only sees the effective query.
        # For full multi-turn rewrite, use PvQueryRewriter.rewrite_with_context
        # before calling this method, or upgrade the pipeline.
        result = await self._pipeline.answer(query=effective, top_k=top_k)
        return (result.answer.content, result.chunks, result.answer, task)

    async def _meta_answer(
        self, query: str
    ) -> tuple[str, list[RetrievedChunk], GeneratedAnswer, TaskType]:
        if is_identity_query(query):
            text = IDENTITY_ANSWER
        else:
            info = self._info.get()
            text = format_meta_answer(info)
        return (
            text,
            [],
            GeneratedAnswer(content=text, citations=[]),
            TaskType.META,
        )
