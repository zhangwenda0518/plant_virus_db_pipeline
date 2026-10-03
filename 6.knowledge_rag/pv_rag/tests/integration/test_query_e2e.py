"""End-to-end tests requiring local Postgres + Qdrant Cloud + real API keys.

Skipped by default — CI runs with ``-m "not integration"``. Run manually
from a shell with mamba env active and ``.env.local`` populated::

    pytest tests/integration -v -m integration

Pre-condition: at least one document must already be ingested AND
indexed (run ``scripts/smoke_run.sh`` once first if the DB is empty).
"""

import os

import pytest

pytestmark = pytest.mark.integration

_REAL_KEY = os.getenv("LLM_API_KEY", "")
_real_creds = pytest.mark.skipif(
    not _REAL_KEY or _REAL_KEY == "test",
    reason="real LLM_API_KEY required (this is a placeholder dummy value)",
)


@_real_creds
def test_full_pipeline_runs() -> None:
    from fastapi.testclient import TestClient

    from neblab_rag.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/query",
            json={"query": "desertification mechanism in northern China"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert isinstance(data["citations"], list)
        assert isinstance(data["citation_valid"], bool)


@_real_creds
def test_health_endpoint_is_reachable() -> None:
    from fastapi.testclient import TestClient

    from neblab_rag.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
