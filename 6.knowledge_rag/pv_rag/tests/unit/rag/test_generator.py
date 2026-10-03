"""Tests for AnswerGenerator: prompt assembly + citation extraction."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.providers.llm.base import ChatResponse, StreamChunk
from neblab_rag.rag.generator import AnswerGenerator
from neblab_rag.rag.retriever import RetrievedChunk


@pytest.mark.asyncio
async def test_generate_builds_prompt_with_citations() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=10,
            doc_id=1,
            chunk_index=0,
            openalex_id="W1",
            title="A",
            text="content of A",
            score=0.9,
        ),
        RetrievedChunk(
            chunk_id=20,
            doc_id=2,
            chunk_index=0,
            openalex_id="W2",
            title="B",
            text="content of B",
            score=0.8,
        ),
    ]
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=ChatResponse(
            content="Per [1] and [2], sand control involves shelterbelts.",
            model="m",
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=20,
        )
    )

    gen = AnswerGenerator(llm=llm)
    answer = await gen.generate(query="What is sand control?", chunks=chunks)

    assert "[1]" in answer.content
    assert len(answer.citations) == 2
    assert answer.citations[0].number == 1
    assert answer.citations[0].title == "A"
    assert answer.citations[1].doc_id == 2
    assert answer.citations[1].openalex_id == "W2"


@pytest.mark.asyncio
async def test_generate_returns_fallback_when_no_chunks() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock()

    gen = AnswerGenerator(llm=llm)
    answer = await gen.generate(query="anything", chunks=[])

    assert "暂未找到" in answer.content
    assert answer.citations == []
    llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_generate_passes_system_and_user_messages_to_llm() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="t", text="x", score=0.9
        )
    ]
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=ChatResponse(content="Per [1].", model="m", finish_reason="stop")
    )

    gen = AnswerGenerator(llm=llm)
    await gen.generate(query="Q?", chunks=chunks)

    request = llm.chat.call_args.args[0]
    assert request.messages[0].role == "system"
    assert request.messages[1].role == "user"
    assert "[1] t" in request.messages[1].content
    assert "Q?" in request.messages[1].content


@pytest.mark.asyncio
async def test_generate_uses_temperature_zero_for_reproducibility() -> None:
    """Sprint 2.5: Sprint 4 baseline showed temperature=0.3 made eval runs
    non-reproducible. Generator must explicitly request 0.0."""
    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="t", text="x", score=0.9
        )
    ]
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=ChatResponse(content="Per [1].", model="m", finish_reason="stop")
    )

    gen = AnswerGenerator(llm=llm)
    await gen.generate(query="Q?", chunks=chunks)

    request = llm.chat.call_args.args[0]
    assert request.temperature == 0.0


@pytest.mark.asyncio
async def test_stream_yields_deltas_from_llm() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="t", text="x", score=0.9
        )
    ]

    async def fake_stream(_request: object) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(delta="Per ")
        yield StreamChunk(delta="[1].")
        yield StreamChunk(delta="", finish_reason="stop")

    llm = MagicMock()
    llm.stream = fake_stream

    gen = AnswerGenerator(llm=llm)
    pieces = [p async for p in gen.stream(query="Q?", chunks=chunks)]

    assert pieces == ["Per ", "[1]."]


@pytest.mark.asyncio
async def test_stream_returns_fallback_message_when_no_chunks() -> None:
    llm = MagicMock()

    gen = AnswerGenerator(llm=llm)
    pieces = [p async for p in gen.stream(query="Q?", chunks=[])]

    assert len(pieces) == 1
    assert "暂未找到" in pieces[0]
