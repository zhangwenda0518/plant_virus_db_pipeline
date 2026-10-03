"""Tests for ChunkRepository — replace-on-write idempotency."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.db.models import Base, Chunk, Document
from neblab_rag.db.repositories import ChunkRepository, DocumentRepository
from neblab_rag.rag.chunker import Chunk as ChunkText


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


def _make_doc(session) -> Document:
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
        abstract_text="some abstract",
        abstract_language="en",
    )
    session.commit()
    return doc


def test_replace_inserts_new_chunks_when_none_exist(session):
    doc = _make_doc(session)
    repo = ChunkRepository(session)

    inserted = repo.replace_for_document(
        doc.id,
        [
            ChunkText(text="part 1", start=0, end=6),
            ChunkText(text="part 2", start=6, end=12),
        ],
    )
    session.commit()

    assert len(inserted) == 2
    assert inserted[0].chunk_index == 0 and inserted[0].text == "part 1"
    assert inserted[1].chunk_index == 1 and inserted[1].start_offset == 6


def test_replace_deletes_old_chunks_first(session):
    doc = _make_doc(session)
    repo = ChunkRepository(session)

    repo.replace_for_document(doc.id, [ChunkText(text="old", start=0, end=3)])
    session.commit()

    # Re-running with new chunks must replace, not duplicate
    repo.replace_for_document(
        doc.id,
        [
            ChunkText(text="new1", start=0, end=4),
            ChunkText(text="new2", start=4, end=8),
        ],
    )
    session.commit()

    new_chunks = session.query(Chunk).filter_by(document_id=doc.id).all()
    assert len(new_chunks) == 2
    assert {c.text for c in new_chunks} == {"new1", "new2"}
    # 'old' must not survive
    assert "old" not in {c.text for c in new_chunks}


def test_replace_with_empty_list_clears_chunks(session):
    doc = _make_doc(session)
    repo = ChunkRepository(session)

    repo.replace_for_document(doc.id, [ChunkText(text="x", start=0, end=1)])
    session.commit()
    repo.replace_for_document(doc.id, [])
    session.commit()

    assert session.query(Chunk).filter_by(document_id=doc.id).count() == 0
