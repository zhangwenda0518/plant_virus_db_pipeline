"""Tests for Document and AbstractRecord ORM models."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from neblab_rag.db.models import AbstractRecord, Base, Document, IndexStatus


def test_document_default_status_applies_on_insert():
    """SQLAlchemy column defaults fire at INSERT time, not at __init__."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        doc = Document(
            openalex_id="W123",
            title="Test",
            primary_topic="desertification",
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        assert doc.status == IndexStatus.METADATA_ONLY
        assert doc.is_oa is False
        assert doc.cited_by_count == 0


def test_abstract_record_required_fields():
    rec = AbstractRecord(
        document_id=1,
        text="abstract text",
        language="en",
    )
    assert rec.text == "abstract text"
    assert rec.language == "en"
