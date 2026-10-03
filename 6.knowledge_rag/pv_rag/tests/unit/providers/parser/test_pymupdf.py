"""Smoke tests for the PyMuPDF parser.

These tests build small PDFs in-process (no network, no fixtures) so they
run anywhere the dependency installs.
"""

import pymupdf
import pytest
from pymupdf import FileDataError

from neblab_rag.providers.parser import PyMuPDFParser


def _make_pdf(pages: list[str]) -> bytes:
    """Synthesize a tiny PDF with the given text on each page."""
    doc = pymupdf.open()  # blank
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 100), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_parses_text_from_each_page() -> None:
    pdf = _make_pdf(["Page one content about desertification.", "Page two on land degradation."])
    parser = PyMuPDFParser()
    result = parser.parse(pdf)
    assert result.parser_name == "pymupdf"
    assert result.page_count == 2
    assert "desertification" in result.text
    assert "land degradation" in result.text


def test_concatenates_pages_with_separator() -> None:
    pdf = _make_pdf(["alpha", "beta"])
    result = PyMuPDFParser().parse(pdf)
    # The double-newline separator preserves page boundaries for downstream chunking
    assert "alpha" in result.text and "beta" in result.text
    assert result.text.index("alpha") < result.text.index("beta")


def test_raises_on_corrupt_pdf() -> None:
    """Caller should mark the doc as parse-failed; we don't silently emit empty text."""
    with pytest.raises(FileDataError):
        PyMuPDFParser().parse(b"this is not a pdf, just bytes")
