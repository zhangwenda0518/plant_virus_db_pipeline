"""Tests for ChunkIndexer — chunks each doc then upserts per-chunk vectors."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.db.models import Base, Chunk, Document, IndexStatus
from neblab_rag.db.repositories import DocumentRepository
from neblab_rag.rag.indexer import ChunkIndexer


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


def _seed_doc(session, *, abstract_text: str = "this is a test abstract") -> Document:
    repo = DocumentRepository(session)
    doc = repo.upsert_metadata(
        openalex_id="W1",
        doi=None,
        title="t",
        authors=[],
        venue=None,
        year=2020,
        primary_topic="desertification",
        extra_topics=[],
        language="en",
        is_oa=True,
        cited_by_count=0,
        abstract_text=abstract_text,
        abstract_language="en",
    )
    session.commit()
    return doc


async def test_index_pending_chunks_then_embeds_then_upserts(session) -> None:
    _seed_doc(session, abstract_text="x" * 1200)  # → 3 chunks at 500/100

    fake_embed = MagicMock()
    fake_embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]] * 3)
    fake_qdrant = MagicMock()

    indexer = ChunkIndexer(
        session=session, embedder=fake_embed, qdrant=fake_qdrant, chunk_size=500, overlap=100
    )
    n_docs = await indexer.index_pending()
    session.commit()

    assert n_docs == 1
    fake_embed.embed.assert_awaited_once()
    embed_arg = fake_embed.embed.call_args.args[0]
    assert len(embed_arg) == 3  # 3 chunks of the 1200-char doc
    fake_qdrant.upsert_points.assert_called_once()
    chunks_in_db = session.query(Chunk).all()
    assert len(chunks_in_db) == 3
    assert [c.chunk_index for c in chunks_in_db] == [0, 1, 2]


async def test_index_marks_doc_indexed_after_success(session) -> None:
    _seed_doc(session)
    fake_embed = MagicMock()
    fake_embed.embed = AsyncMock(return_value=[[0.0] * 4])
    fake_qdrant = MagicMock()

    indexer = ChunkIndexer(session=session, embedder=fake_embed, qdrant=fake_qdrant)
    await indexer.index_pending()
    session.commit()

    doc = session.query(Document).first()
    assert doc.status == IndexStatus.FULLTEXT_INDEXED


async def test_qdrant_payload_contains_chunk_metadata(session) -> None:
    _seed_doc(session, abstract_text="short text")  # → 1 chunk
    fake_embed = MagicMock()
    fake_embed.embed = AsyncMock(return_value=[[0.0] * 4])
    fake_qdrant = MagicMock()

    indexer = ChunkIndexer(session=session, embedder=fake_embed, qdrant=fake_qdrant)
    await indexer.index_pending()
    session.commit()

    points = fake_qdrant.upsert_points.call_args.args[0]
    assert len(points) == 1
    p = points[0]
    chunk_row = session.query(Chunk).first()
    assert p.id == chunk_row.id  # Qdrant point id == chunk PK
    assert p.payload["chunk_id"] == chunk_row.id
    assert p.payload["doc_id"] == chunk_row.document_id
    assert p.payload["chunk_index"] == 0
    assert p.payload["text"] == "short text"
    assert p.payload["title"] == "t"
    assert p.payload["openalex_id"] == "W1"


async def test_re_indexing_replaces_chunks_not_duplicates(session) -> None:
    _seed_doc(session, abstract_text="abc")
    fake_embed = MagicMock()
    fake_embed.embed = AsyncMock(return_value=[[0.0] * 4])
    fake_qdrant = MagicMock()

    indexer = ChunkIndexer(session=session, embedder=fake_embed, qdrant=fake_qdrant)
    await indexer.index_pending()
    session.commit()

    # Reset to METADATA_ONLY and re-run — should replace, not duplicate
    doc = session.query(Document).first()
    doc.status = IndexStatus.METADATA_ONLY
    session.commit()

    fake_embed.embed.reset_mock()
    fake_embed.embed = AsyncMock(return_value=[[0.0] * 4])
    await indexer.index_pending()
    session.commit()

    assert session.query(Chunk).count() == 1  # not 2
