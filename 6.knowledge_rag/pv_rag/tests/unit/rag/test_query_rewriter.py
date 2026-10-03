"""Tests for QueryRewriter — translate non-English queries before retrieval."""

from unittest.mock import AsyncMock, MagicMock

from neblab_rag.providers.llm.base import ChatResponse
from neblab_rag.rag.query_rewriter import QueryRewriter, has_cjk


def test_has_cjk_detects_chinese() -> None:
    assert has_cjk("沙漠化") is True
    assert has_cjk("What is desertification?") is False
    assert has_cjk("Mixed query 沙漠化 and English") is True
    assert has_cjk("") is False


async def test_rewrite_english_query_skips_llm() -> None:
    """English queries are passed through unchanged — no LLM call needed."""
    llm = MagicMock()
    llm.chat = AsyncMock()

    rewriter = QueryRewriter(llm=llm)
    result = await rewriter.rewrite("What is desertification?")

    assert result.original == "What is desertification?"
    assert result.rewritten == "What is desertification?"
    assert result.was_rewritten is False
    llm.chat.assert_not_called()


async def test_rewrite_chinese_query_calls_llm() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=ChatResponse(
            content="What are the main mechanisms of desertification?",
            model="m",
            finish_reason="stop",
        )
    )

    rewriter = QueryRewriter(llm=llm)
    result = await rewriter.rewrite("沙漠化的主要机制是什么？")

    assert result.original == "沙漠化的主要机制是什么？"
    assert result.rewritten == "What are the main mechanisms of desertification?"
    assert result.was_rewritten is True
    llm.chat.assert_awaited_once()


async def test_rewrite_strips_whitespace_and_quotes_from_llm_output() -> None:
    """LLMs sometimes wrap their answer in quotes or whitespace — clean it up."""
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=ChatResponse(
            content='  "What is shrub invasion?"  \n', model="m", finish_reason="stop"
        )
    )

    rewriter = QueryRewriter(llm=llm)
    result = await rewriter.rewrite("灌木入侵是什么？")

    assert result.rewritten == "What is shrub invasion?"


async def test_rewrite_falls_back_to_original_on_llm_error() -> None:
    """A translation failure must not abort the retrieval — fall back to the
    original Chinese query and let dense retrieval do its best."""
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("provider down"))

    rewriter = QueryRewriter(llm=llm)
    result = await rewriter.rewrite("沙漠化")

    assert result.rewritten == "沙漠化"  # graceful degrade, not crash
    assert result.was_rewritten is False
