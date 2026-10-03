"""Tests for the plant-virus ``POST /query`` route.

Covers the 2026-10-03 audit fixes:
  * ``answer_validation`` from the pipeline is surfaced in the response JSON
    (previously silently dropped), including the "validation unavailable"
    shape (``fidelity_score=None``, ``is_reliable=False``);
  * ``top_k`` is clamped to 1..20 by the ``QueryRequest`` validator.

The DB-backed citation enrichment is stubbed — no Postgres needed.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import plant_virus_rag.api.routes.query as qroutes
from neblab_rag.rag.answer_validator import AnswerValidation
from neblab_rag.rag.citation import CitationValidation
from neblab_rag.rag.generator import GeneratedAnswer
from neblab_rag.rag.pipeline import RAGResult
from neblab_rag.rag.retriever import RetrievedChunk
from plant_virus_rag.api.main import create_pv_app
from plant_virus_rag.api.routes.query import QueryRequest, get_pipeline


def _result(*, validation: AnswerValidation | None) -> RAGResult:
    return RAGResult(
        query="q",
        chunks=[
            RetrievedChunk(
                chunk_id=1, doc_id=1, chunk_index=0, openalex_id=None, title="t", text="x", score=1.0
            )
        ],
        answer=GeneratedAnswer(content="Per [1].", citations=[]),
        citation_validation=CitationValidation(
            is_valid=True, referenced_numbers={1}, invalid_numbers=set()
        ),
        answer_validation=validation,
    )


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(qroutes, "_enrich_citations", lambda chunks: [])
    return TestClient(create_pv_app())


def test_top_k_is_clamped_to_1_20() -> None:
    assert QueryRequest(query="q", top_k=999).top_k == 20
    assert QueryRequest(query="q", top_k=0).top_k == 1
    assert QueryRequest(query="q", top_k=-3).top_k == 1
    assert QueryRequest(query="q", top_k=7).top_k == 7


def test_query_surfaces_answer_validation(client: TestClient) -> None:
    validation = AnswerValidation(
        claims=[], fidelity_score=0.5, is_reliable=False, note=None
    )
    fake = MagicMock()
    fake.answer = AsyncMock(return_value=_result(validation=validation))
    app = client.app
    app.dependency_overrides[get_pipeline] = lambda: fake

    resp = client.post("/query", json={"query": "q"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["answer_validation"]["fidelity_score"] == 0.5
    assert payload["answer_validation"]["is_reliable"] is False


def test_query_surfaces_unavailable_validation_as_none_score(client: TestClient) -> None:
    validation = AnswerValidation(
        claims=[], fidelity_score=None, is_reliable=False, note="validator error: RuntimeError"
    )
    fake = MagicMock()
    fake.answer = AsyncMock(return_value=_result(validation=validation))
    client.app.dependency_overrides[get_pipeline] = lambda: fake

    payload = client.post("/query", json={"query": "q"}).json()

    assert payload["answer_validation"]["fidelity_score"] is None
    assert payload["answer_validation"]["is_reliable"] is False
    assert "validator error" in payload["answer_validation"]["note"]


def test_query_clamps_top_k_before_calling_pipeline(client: TestClient) -> None:
    fake = MagicMock()
    fake.answer = AsyncMock(return_value=_result(validation=None))
    client.app.dependency_overrides[get_pipeline] = lambda: fake

    client.post("/query", json={"query": "q", "top_k": 500})

    fake.answer.assert_awaited_once_with(query="q", top_k=20)
