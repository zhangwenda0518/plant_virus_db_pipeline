"""Tests for /query and /query/stream endpoints.

Pipeline is mocked via FastAPI dependency override — these are pure
HTTP-shape tests, no real LLM/Qdrant calls.
"""

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from neblab_rag.api.main import create_app
from neblab_rag.api.routes.query import get_pipeline
from neblab_rag.rag.citation import CitationValidation
from neblab_rag.rag.generator import Citation, GeneratedAnswer
from neblab_rag.rag.pipeline import RAGResult
from neblab_rag.rag.retriever import RetrievedChunk


def _make_result(query: str = "What is sand control?") -> RAGResult:
    return RAGResult(
        query=query,
        chunks=[
            RetrievedChunk(
                chunk_id=1,
                doc_id=1,
                chunk_index=0,
                openalex_id="W1",
                title="A",
                text="x",
                score=0.9,
            )
        ],
        answer=GeneratedAnswer(
            content="Per [1].",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="A")],
        ),
        citation_validation=CitationValidation(
            is_valid=True, referenced_numbers={1}, invalid_numbers=set()
        ),
    )


def test_query_returns_answer_and_citations() -> None:
    fake_pipeline = MagicMock()
    fake_pipeline.answer = AsyncMock(return_value=_make_result())

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    response = client.post("/query", json={"query": "What is sand control?"})

    assert response.status_code == 200
    data = response.json()
    assert "Per [1]" in data["answer"]
    assert data["citations"][0]["title"] == "A"
    assert data["citations"][0]["number"] == 1
    assert data["citation_valid"] is True


def test_query_passes_top_k_to_pipeline() -> None:
    fake_pipeline = MagicMock()
    fake_pipeline.answer = AsyncMock(return_value=_make_result())

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    client.post("/query", json={"query": "q", "top_k": 8})

    fake_pipeline.answer.assert_awaited_once_with(query="q", top_k=8)


def test_query_stream_emits_citations_then_deltas_then_done() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id="W1", title="A", text="x", score=0.9
        )
    ]

    async def fake_stream(*, query: str, chunks: list[RetrievedChunk]) -> AsyncIterator[str]:
        yield "Per "
        yield "[1]."

    fake_retriever = MagicMock()
    fake_retriever.retrieve = AsyncMock(return_value=chunks)
    fake_generator = MagicMock()
    fake_generator.stream = fake_stream

    fake_pipeline = MagicMock()
    fake_pipeline.retriever = fake_retriever
    fake_pipeline.generator = fake_generator

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    with client.stream("GET", "/query/stream", params={"query": "q"}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: citations" in body
    citations_line = next(
        line for line in body.splitlines() if line.startswith("data: ") and '"title": "A"' in line
    )
    payload = json.loads(citations_line.removeprefix("data: "))
    assert payload[0]["title"] == "A"
    assert payload[0]["number"] == 1

    assert "event: delta" in body
    assert "data: Per" in body
    assert "data: [1]." in body
    assert "event: done" in body
