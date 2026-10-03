from unittest.mock import MagicMock

import pytest

from neblab_rag.vector.qdrant_repo import QdrantRepo, VectorPoint


@pytest.fixture
def mock_client():
    return MagicMock()


def test_ensure_collection_creates_if_missing(mock_client):
    mock_client.collection_exists.return_value = False
    repo = QdrantRepo(client=mock_client, collection="test", dim=4)
    repo.ensure_collection()
    mock_client.create_collection.assert_called_once()


def test_upsert_points_passes_correct_payload(mock_client):
    repo = QdrantRepo(client=mock_client, collection="test", dim=4)
    repo.upsert_points(
        [
            VectorPoint(id=1, vector=[0.1, 0.2, 0.3, 0.4], payload={"doc_id": 1}),
        ]
    )
    mock_client.upsert.assert_called_once()
    args = mock_client.upsert.call_args.kwargs
    assert args["collection_name"] == "test"
    assert args["points"][0].id == 1  # must be int — Qdrant rejects strings like "1"


def test_upsert_points_batches_above_limit(mock_client):
    """Sprint 1: full-text indexing produces 100s+ chunks per doc; a single
    upsert above ~200 points times out against Qdrant Cloud. Repo batches
    internally with configurable size."""
    repo = QdrantRepo(client=mock_client, collection="test", dim=4, upsert_batch_size=10)
    points = [VectorPoint(id=i, vector=[0.0] * 4, payload={}) for i in range(25)]
    repo.upsert_points(points)
    # 25 points / 10 batch size → 3 calls (10 + 10 + 5)
    assert mock_client.upsert.call_count == 3
    batch_sizes = [len(call.kwargs["points"]) for call in mock_client.upsert.call_args_list]
    assert batch_sizes == [10, 10, 5]


def test_search_returns_top_hits(mock_client):
    mock_hit = MagicMock()
    mock_hit.id = "p1"
    mock_hit.score = 0.9
    mock_hit.payload = {"doc_id": 1}
    mock_client.query_points.return_value.points = [mock_hit]

    repo = QdrantRepo(client=mock_client, collection="test", dim=4)
    hits = repo.search(query_vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
    assert len(hits) == 1
    assert hits[0].score == 0.9
