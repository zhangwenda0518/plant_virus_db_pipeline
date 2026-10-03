from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neblab_rag.providers.reranker.qwen3 import Qwen3RerankerProvider


@pytest.mark.asyncio
async def test_rerank_returns_sorted_indices_with_scores():
    provider = Qwen3RerankerProvider(
        base_url="https://example.com/v1",
        api_key="key",
        model="qwen3-reranker:8b",
    )
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "results": [
            {"index": 0, "relevance_score": 0.4},
            {"index": 1, "relevance_score": 0.9},
            {"index": 2, "relevance_score": 0.7},
        ],
    }
    fake_response.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        ranked = await provider.rerank(query="x", documents=["a", "b", "c"], top_k=2)
    assert [r.index for r in ranked] == [1, 2]
    assert ranked[0].score == 0.9
