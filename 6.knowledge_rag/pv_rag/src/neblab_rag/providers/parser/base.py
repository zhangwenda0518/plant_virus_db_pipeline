"""ParserProvider abstract interface.

Sprint 1: PDF (and eventually image-PDF / scanned-PDF) parsing is a
separate concern from RAG retrieval/generation, with multiple competing
implementations (PyMuPDF, MinerU, LlamaParse, deepseek-ocr per spec §4.3).
The interface keeps business code (corpus.fulltext) decoupled from
specific libraries.

ParseResult.text is plain text — chunking + embedding happens downstream
in the RAG pipeline. Implementations may add structured metadata
(sections, tables) in payload as Sprint-1.5 / Sprint-2 grows; for v0.1
text-only is enough.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ParseResult(BaseModel):
    text: str
    page_count: int
    parser_name: str  # e.g. "pymupdf", "mineru" — recorded so retraining can re-process
    metadata: dict[str, Any] = {}


class ParserProvider(ABC):
    """Abstract PDF/document parser. One concrete impl per backend."""

    @abstractmethod
    def parse(self, pdf_bytes: bytes) -> ParseResult:
        """Parse a PDF byte stream into plain text + page count + metadata.

        Implementations should NOT raise on parse failure that produces
        partial output — return what was extracted with an empty/short
        text. Raise only on truly broken input (corrupted PDF, password-
        protected, etc.) so the caller can mark the doc as failed.
        """
        ...
