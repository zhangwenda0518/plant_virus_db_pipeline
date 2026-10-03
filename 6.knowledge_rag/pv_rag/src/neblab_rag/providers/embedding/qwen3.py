"""Qwen3 embedding provider via OpenAI-compatible /embeddings endpoint.

Provider-agnostic at the wire level; named ``Qwen3EmbeddingProvider`` because
qwen3-embedding:8b is the v1 default. Batches inputs internally so callers
can pass arbitrary list sizes.

Optional SQLite-backed cache (``cache_path``) avoids re-embedding identical
text across runs — useful when re-indexing after schema changes or when
running evals repeatedly.
"""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from neblab_rag.providers.embedding.base import EmbeddingProvider


class Qwen3EmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        timeout: float = 60.0,
        batch_size: int = 32,
        cache_path: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._timeout = timeout
        self._batch_size = batch_size
        self._cache_path = cache_path
        self._cache_lock = threading.Lock()
        if cache_path:
            self._init_cache()

    def _init_cache(self) -> None:
        Path(self._cache_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._cache_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS embeddings (
                    text_hash TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON embeddings(text_hash)"
            )

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_get(self, text: str) -> list[float] | None:
        if not self._cache_path:
            return None
        with sqlite3.connect(self._cache_path) as conn:
            row = conn.execute(
                "SELECT vector FROM embeddings WHERE text_hash = ? AND model = ?",
                (self._hash(text), self._model),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def _cache_put(self, text: str, vector: list[float]) -> None:
        if not self._cache_path:
            return
        with self._cache_lock, sqlite3.connect(self._cache_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (text_hash, text, vector, model) VALUES (?, ?, ?, ?)",
                (self._hash(text), text, json.dumps(vector), self._model),
            )

    @property
    def dim(self) -> int:
        return self._dim

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url=f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Check cache first, partition into cached vs missing
        results: list[list[float] | None] = [None] * len(texts)
        missing_idx: list[int] = []
        missing_texts: list[str] = []
        for i, t in enumerate(texts):
            cached = self._cache_get(t)
            if cached is not None:
                results[i] = cached
            else:
                missing_idx.append(i)
                missing_texts.append(t)

        # Embed only the missing ones in batches
        for j in range(0, len(missing_texts), self._batch_size):
            batch = missing_texts[j : j + self._batch_size]
            vectors = await self._embed_batch(batch)
            for text, vec in zip(batch, vectors):
                self._cache_put(text, vec)
            for k, vec in enumerate(vectors):
                results[missing_idx[j + k]] = vec

        return [r for r in results if r is not None]
