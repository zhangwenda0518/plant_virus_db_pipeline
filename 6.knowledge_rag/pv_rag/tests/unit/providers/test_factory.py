import os
from unittest.mock import patch

import pytest

from neblab_rag.providers.factory import (
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)


@pytest.fixture
def env() -> dict[str, str]:
    return {
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_API_KEY": "k",
        "LLM_DEFAULT_MODEL": "deepseek-v3.2",
        "EMBEDDING_BASE_URL": "https://example.com/v1",
        "EMBEDDING_API_KEY": "k",
        "EMBEDDING_MODEL": "qwen3-embedding:8b",
        "EMBEDDING_DIM": "4096",
        "RERANKER_BASE_URL": "https://example.com/v1",
        "RERANKER_API_KEY": "k",
        "RERANKER_MODEL": "qwen3-reranker:8b",
        "QDRANT_URL": "http://localhost:6333",
        "OPENALEX_EMAIL": "a@b.com",
    }


def test_build_llm_provider(env: dict[str, str]):
    with patch.dict(os.environ, env, clear=True):
        provider = build_llm_provider()
    from neblab_rag.providers.llm.deepseek import DeepSeekProvider

    assert isinstance(provider, DeepSeekProvider)


def test_build_embedding_provider(env: dict[str, str]):
    with patch.dict(os.environ, env, clear=True):
        provider = build_embedding_provider()
    assert provider.dim == 4096


def test_build_reranker_provider(env: dict[str, str]):
    with patch.dict(os.environ, env, clear=True):
        provider = build_reranker_provider()
    assert provider is not None


def test_build_qdrant_repo_uses_settings(env: dict[str, str]):
    with patch.dict(os.environ, env, clear=True):
        repo = build_qdrant_repo()
    assert repo is not None
