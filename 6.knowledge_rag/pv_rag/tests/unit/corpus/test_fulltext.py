"""Tests for FullTextFetcher — OpenAlex + httpx + parser are all mocked."""

from unittest.mock import MagicMock

import httpx
import pymupdf
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.corpus.fulltext import FullTextFetcher
from neblab_rag.db.models import Base, Document, FullText, IndexStatus
from neblab_rag.db.repositories import DocumentRepository
from neblab_rag.providers.parser import PyMuPDFParser


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


def _seed_oa_doc(session, openalex_id: str = "W1") -> Document:
    repo = DocumentRepository(session)
    doc = repo.upsert_metadata(
        openalex_id=openalex_id,
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
        abstract_text="abstract",
        abstract_language="en",
    )
    session.commit()
    return doc


def _make_pdf(text: str = "Real desertification text here.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), text)
    out = doc.tobytes()
    doc.close()
    return out


def _http_client_with(responses: dict[str, httpx.Response]) -> httpx.Client:
    """Build an httpx.Client whose transport returns the given URL→Response map."""

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.get(str(request.url), httpx.Response(404))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_pending_downloads_parses_and_stores(session) -> None:
    _seed_oa_doc(session)
    pdf = _make_pdf()
    openalex = MagicMock()
    openalex.get_pdf_url.return_value = "https://example.org/paper.pdf"
    http = _http_client_with({"https://example.org/paper.pdf": httpx.Response(200, content=pdf)})

    fetcher = FullTextFetcher(
        session=session, openalex=openalex, parser=PyMuPDFParser(), http_client=http
    )
    counts = fetcher.fetch_pending()
    session.commit()

    assert counts == {"tried": 1, "no_url": 0, "downloaded": 1, "parsed": 1, "failed": 0}
    ft = session.query(FullText).first()
    assert ft is not None
    assert "desertification" in ft.text
    assert ft.parser_name == "pymupdf"
    assert ft.source_url == "https://example.org/paper.pdf"


def test_fetch_skips_when_openalex_returns_no_pdf_url(session) -> None:
    _seed_oa_doc(session)
    openalex = MagicMock()
    openalex.get_pdf_url.return_value = None
    http = _http_client_with({})

    fetcher = FullTextFetcher(
        session=session, openalex=openalex, parser=PyMuPDFParser(), http_client=http
    )
    counts = fetcher.fetch_pending()

    assert counts["no_url"] == 1
    assert counts["parsed"] == 0
    assert session.query(FullText).count() == 0


def test_fetch_skips_on_http_error_without_aborting_batch(session) -> None:
    """Two docs; first 404s, second succeeds. Batch must not abort on the first."""
    _seed_oa_doc(session, openalex_id="W1")
    _seed_oa_doc(session, openalex_id="W2")

    openalex = MagicMock()
    openalex.get_pdf_url.side_effect = lambda oa_id: f"https://example.org/{oa_id}.pdf"
    http = _http_client_with(
        {
            "https://example.org/W1.pdf": httpx.Response(404),
            "https://example.org/W2.pdf": httpx.Response(200, content=_make_pdf()),
        }
    )

    fetcher = FullTextFetcher(
        session=session, openalex=openalex, parser=PyMuPDFParser(), http_client=http
    )
    counts = fetcher.fetch_pending()
    session.commit()

    assert counts["tried"] == 2
    assert counts["failed"] == 1
    assert counts["parsed"] == 1
    assert session.query(FullText).count() == 1


def test_fetch_marks_doc_failed_on_parse_error(session) -> None:
    _seed_oa_doc(session)
    openalex = MagicMock()
    openalex.get_pdf_url.return_value = "https://example.org/x.pdf"
    http = _http_client_with(
        {"https://example.org/x.pdf": httpx.Response(200, content=b"this is not a pdf")}
    )

    fetcher = FullTextFetcher(
        session=session, openalex=openalex, parser=PyMuPDFParser(), http_client=http
    )
    counts = fetcher.fetch_pending()
    session.commit()

    assert counts["failed"] == 1
    assert counts["parsed"] == 0
    doc = session.query(Document).first()
    assert doc.status == IndexStatus.FAILED


def test_fetch_skips_oversize_pdf(session) -> None:
    _seed_oa_doc(session)
    big_pdf = _make_pdf() + b"X" * (10 * 1024 * 1024)  # > 5MB cap below
    openalex = MagicMock()
    openalex.get_pdf_url.return_value = "https://example.org/huge.pdf"
    http = _http_client_with({"https://example.org/huge.pdf": httpx.Response(200, content=big_pdf)})

    fetcher = FullTextFetcher(
        session=session,
        openalex=openalex,
        parser=PyMuPDFParser(),
        http_client=http,
        max_bytes=5 * 1024 * 1024,
    )
    counts = fetcher.fetch_pending()

    assert counts["failed"] == 1
    assert session.query(FullText).count() == 0


def test_list_oa_without_fulltext_excludes_already_fetched(session) -> None:
    """Re-runs are idempotent — a doc with a fulltext row is filtered out."""
    doc = _seed_oa_doc(session)
    pdf = _make_pdf()
    openalex = MagicMock()
    openalex.get_pdf_url.return_value = "https://example.org/p.pdf"
    http = _http_client_with({"https://example.org/p.pdf": httpx.Response(200, content=pdf)})

    fetcher = FullTextFetcher(
        session=session, openalex=openalex, parser=PyMuPDFParser(), http_client=http
    )
    counts1 = fetcher.fetch_pending()
    session.commit()
    assert counts1["parsed"] == 1

    counts2 = fetcher.fetch_pending()  # second run
    assert counts2["tried"] == 0  # doc has fulltext now → excluded from pending list
    _ = doc
