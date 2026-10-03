"""Repository unit tests using SQLite in-memory."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.db.models import Base, IndexStatus
from neblab_rag.db.repositories import DocumentRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


def test_upsert_inserts_new_document(session):
    repo = DocumentRepository(session)
    doc = repo.upsert_metadata(
        openalex_id="W1",
        title="hello",
        primary_topic="desertification",
        authors=["A"],
        year=2020,
        language="en",
        is_oa=True,
        cited_by_count=5,
        venue="Nature",
        extra_topics=["land-degradation"],
        doi=None,
        abstract_text="Some abstract about sand.",
        abstract_language="en",
    )
    session.commit()
    assert doc.id is not None
    assert doc.abstract is not None


def test_upsert_updates_existing_document(session):
    repo = DocumentRepository(session)
    repo.upsert_metadata(
        openalex_id="W1",
        title="v1",
        primary_topic="t",
        authors=[],
        year=None,
        language=None,
        is_oa=False,
        cited_by_count=0,
        venue=None,
        extra_topics=[],
        doi=None,
        abstract_text="a1",
        abstract_language="en",
    )
    session.commit()
    doc = repo.upsert_metadata(
        openalex_id="W1",
        title="v2",
        primary_topic="t",
        authors=[],
        year=None,
        language=None,
        is_oa=False,
        cited_by_count=0,
        venue=None,
        extra_topics=[],
        doi=None,
        abstract_text="a2",
        abstract_language="en",
    )
    session.commit()
    assert doc.title == "v2"
    assert doc.abstract is not None
    assert doc.abstract.text == "a2"


def test_list_pending_metadata_returns_only_metadata_only(session):
    repo = DocumentRepository(session)
    repo.upsert_metadata(
        openalex_id="W1",
        title="t",
        primary_topic="t",
        authors=[],
        year=None,
        language=None,
        is_oa=False,
        cited_by_count=0,
        venue=None,
        extra_topics=[],
        doi=None,
        abstract_text="a",
        abstract_language="en",
    )
    session.commit()
    docs = repo.list_documents_with_status(IndexStatus.METADATA_ONLY)
    assert len(docs) == 1
