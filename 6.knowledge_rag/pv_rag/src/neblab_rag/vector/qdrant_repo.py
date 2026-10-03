# pyright: reportArgumentType=false
"""Qdrant access layer.

Wraps qdrant-client with our DTOs (VectorPoint, SearchHit) so the rest of
the codebase doesn't import qdrant types directly. Collection lifecycle
(``ensure_collection``) is idempotent so callers can run it on every boot.

Point IDs: Qdrant accepts either an unsigned integer or a UUID string.
We use the document's Postgres primary key (sequential int) directly —
``int`` here is the contract, not ``str``. Sending a stringified int like
``"3"`` is rejected at runtime ("3 is not a valid point ID"); the strict
type prevents that class of bug.
"""

import time
from typing import Any

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams


class VectorPoint(BaseModel):
    id: int
    vector: list[float]
    payload: dict[str, Any]


class SearchHit(BaseModel):
    # Qdrant returns whatever was upserted: int for our docs, but we keep
    # the union so a future caller upserting UUIDs (e.g. multi-chunk in
    # Plan 2) doesn't have to widen this contract again.
    id: int | str
    score: float
    payload: dict[str, Any]


# Sprint 1: full-text indexing produces 100s-1000s of chunks per doc;
# a single upsert of 4096-d × N vectors will time out against Qdrant Cloud.
# Empirically 100 × 4096-d still hangs at the default qdrant-client timeout;
# 50 fits comfortably even with 60s timeout. Tune via constructor arg if
# Qdrant Cloud tier changes the throughput envelope.
DEFAULT_UPSERT_BATCH_SIZE = 50


class QdrantRepo:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        dim: int,
        *,
        upsert_batch_size: int = DEFAULT_UPSERT_BATCH_SIZE,
    ):
        self._client = client
        self._collection = collection
        self._dim = dim
        self._upsert_batch_size = upsert_batch_size

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )

    def upsert_points(self, points: list[VectorPoint], *, max_retries: int = 5) -> None:
        for i in range(0, len(points), self._upsert_batch_size):
            batch = points[i : i + self._upsert_batch_size]
            point_structs = [
                PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in batch
            ]
            for attempt in range(1, max_retries + 1):
                try:
                    self._client.upsert(
                        collection_name=self._collection,
                        points=point_structs,
                    )
                    break
                except UnexpectedResponse as exc:
                    if attempt >= max_retries:
                        raise
                    wait = 2 ** attempt  # 2, 4, 8, 16, 32 seconds
                    print(
                        f"[qdrant] upsert batch failed (attempt {attempt}/{max_retries}), "
                        f"retrying in {wait}s: {exc}"
                    )
                    time.sleep(wait)

    def delete_points(self, point_ids: list[int]) -> None:
        if not point_ids:
            return
        self._client.delete(
            collection_name=self._collection,
            points_selector=point_ids,
        )

    def fetch_by_ids(self, point_ids: list[int]) -> dict[int, dict[str, object]]:
        """Batch-fetch payloads for the given point IDs.
        Returns dict mapping int id -> payload. IDs not found are omitted.
        """
        if not point_ids:
            return {}
        records = self._client.retrieve(
            collection_name=self._collection,
            ids=point_ids,
            with_payload=True,
        )
        return {int(r.id): r.payload or {} for r in records if r.id is not None}

    def search(self, query_vector: list[float], top_k: int = 10) -> list[SearchHit]:
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )
        return [SearchHit(id=h.id, score=h.score, payload=h.payload or {}) for h in response.points]
