"""Tests for RAGPipeline orchestration: retrieve → generate → validate."""

from unittest.mock import AsyncMock, MagicMock

from neblab_rag.rag.generator import Citation, GeneratedAnswer
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.retriever import RetrievedChunk


async def test_answer_orchestrates_retriever_and_generator() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="t", text="x", score=0.9
        )
    ]
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=chunks)
    generator = MagicMock()
    generator.generate = AsyncMock(
        return_value=GeneratedAnswer(
            content="Per [1].",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="t")],
        )
    )

    pipeline = RAGPipeline(retriever=retriever, generator=generator)
    result = await pipeline.answer(query="x")

    assert result.query == "x"
    assert result.chunks == chunks
    assert result.answer.content == "Per [1]."
    assert result.citation_validation.is_valid is True
    retriever.retrieve.assert_awaited_once_with(query="x", top_k=7)
    generator.generate.assert_awaited_once_with(query="x", chunks=chunks)


async def test_answer_passes_top_k_through_to_retriever() -> None:
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[])
    generator = MagicMock()
    generator.generate = AsyncMock(
        return_value=GeneratedAnswer(content="文献库中暂未找到相关结论。", citations=[])
    )

    pipeline = RAGPipeline(retriever=retriever, generator=generator)
    await pipeline.answer(query="q", top_k=10)

    retriever.retrieve.assert_awaited_once_with(query="q", top_k=10)


async def test_answer_flags_invalid_citations() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="t", text="x", score=0.9
        )
    ]
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=chunks)
    generator = MagicMock()
    generator.generate = AsyncMock(
        return_value=GeneratedAnswer(
            content="Per [5] (hallucinated).",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="t")],
        )
    )

    pipeline = RAGPipeline(retriever=retriever, generator=generator)
    result = await pipeline.answer(query="x")

    assert result.citation_validation.is_valid is False
    assert 5 in result.citation_validation.invalid_numbers


async def test_rewriter_routes_translated_query_to_retriever_only() -> None:
    """Sprint 4: rewritten query goes to retriever (better corpus match);
    original query goes to generator (so the answer language matches)."""
    from neblab_rag.rag.query_rewriter import RewrittenQuery

    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="t", text="x", score=0.9
        )
    ]
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=chunks)
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=GeneratedAnswer(content="Per [1].", citations=[]))
    rewriter = MagicMock()
    rewriter.rewrite = AsyncMock(
        return_value=RewrittenQuery(
            original="沙漠化的机制？",
            rewritten="What are the mechanisms of desertification?",
            was_rewritten=True,
        )
    )

    pipeline = RAGPipeline(retriever=retriever, generator=generator, query_rewriter=rewriter)
    result = await pipeline.answer(query="沙漠化的机制？")

    retriever.retrieve.assert_awaited_once_with(
        query="What are the mechanisms of desertification?", top_k=7
    )
    generator.generate.assert_awaited_once_with(query="沙漠化的机制？", chunks=chunks)
    assert result.query == "沙漠化的机制？"
    assert result.rewritten_query == "What are the mechanisms of desertification?"


async def test_no_rewriter_means_original_query_used_throughout() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="t", text="x", score=0.9
        )
    ]
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=chunks)
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=GeneratedAnswer(content="Per [1].", citations=[]))

    pipeline = RAGPipeline(retriever=retriever, generator=generator)  # no rewriter
    result = await pipeline.answer(query="What is X?")

    retriever.retrieve.assert_awaited_once_with(query="What is X?", top_k=7)
    generator.generate.assert_awaited_once_with(query="What is X?", chunks=chunks)
    assert result.rewritten_query is None
