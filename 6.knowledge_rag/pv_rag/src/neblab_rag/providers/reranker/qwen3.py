"""Qwen3 reranker via Cohere-style ``/rerank`` endpoint.

Note: unlike chat/embeddings, ``/rerank`` is not part of the OpenAI spec.
The request/response shape here matches Cohere and most Chinese vendor
clones (qwen3-reranker, BGE reranker servers). If your endpoint uses a
different schema, swap the JSON parsing accordingly.
"""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from neblab_rag.providers.reranker.base import RerankerProvider, RerankResult


class Qwen3RerankerProvider(RerankerProvider):
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url=f"{self._base_url}/rerank",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_k,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        results = [
            RerankResult(index=r["index"], score=r["relevance_score"]) for r in data["results"]
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
