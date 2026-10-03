from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neblab_rag.providers.embedding.qwen3 import Qwen3EmbeddingProvider


@pytest.fixture
def provider() -> Qwen3EmbeddingProvider:
    return Qwen3EmbeddingProvider(
        base_url="https://example.com/v1",
        api_key="key",
        model="qwen3-embedding:8b",
        dim=4096,
    )


@pytest.mark.asyncio
async def test_embed_returns_correct_shape(provider: Qwen3EmbeddingProvider):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [
            {"embedding": [0.1] * 4096, "index": 0},
            {"embedding": [0.2] * 4096, "index": 1},
        ],
        "model": "qwen3-embedding:8b",
    }
    fake_response.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        vectors = await provider.embed(["a", "b"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 4096


def test_dim_property(provider: Qwen3EmbeddingProvider):
    assert provider.dim == 4096
