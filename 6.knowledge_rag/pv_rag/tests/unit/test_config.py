"""Test Settings configuration loading."""

import os
from unittest.mock import patch

from neblab_rag.config import Settings


def test_settings_loads_from_env_vars():
    env = {
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_API_KEY": "test-key",
        "LLM_DEFAULT_MODEL": "test-model",
        "EMBEDDING_BASE_URL": "https://example.com/v1",
        "EMBEDDING_API_KEY": "emb-key",
        "EMBEDDING_MODEL": "emb-model",
        "EMBEDDING_DIM": "1024",
        "RERANKER_BASE_URL": "https://example.com/v1",
        "RERANKER_API_KEY": "rr-key",
        "RERANKER_MODEL": "rr-model",
        "POSTGRES_DSN": "postgresql://x",
        "QDRANT_URL": "http://localhost:6333",
        "QDRANT_COLLECTION": "test",
        "OPENALEX_EMAIL": "a@b.com",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
    assert s.llm.api_key == "test-key"
    assert s.embedding.dim == 1024
    assert s.qdrant.collection == "test"
