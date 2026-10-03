from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.corpus.ingestion import IngestionService
from neblab_rag.corpus.openalex_client import OpenAlexRecord
from neblab_rag.corpus.topics import TOPIC_BY_ID
from neblab_rag.db.models import Base, Document


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


def test_ingest_topic_inserts_records(session):
    fake_client = MagicMock()
    fake_client.search_by_keywords.return_value = iter(
        [
            OpenAlexRecord(
                openalex_id="W1",
                doi="10.1/x",
                title="A",
                authors=["X"],
                venue="V",
                year=2020,
                language="en",
                is_oa=True,
                cited_by_count=5,
                abstract="abs",
            ),
            OpenAlexRecord(
                openalex_id="W2",
                doi=None,
                title="B",
                authors=[],
                venue=None,
                year=2021,
                language="en",
                is_oa=False,
                cited_by_count=1,
                abstract=None,
            ),
        ]
    )

    service = IngestionService(client=fake_client, session=session)
    n = service.ingest_topic(TOPIC_BY_ID["desertification"], language="en", max_results=2)
    session.commit()

    assert n == 2
    docs = session.query(Document).all()
    assert len(docs) == 2
    assert {d.openalex_id for d in docs} == {"W1", "W2"}
    # at least one of the two has an abstract
    assert any(d.abstract is not None for d in docs)
