# pyright: reportArgumentType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""PyMuPDF (fitz) parser — Sprint 1 v0.1 default.

Fast, in-process, no network, no LLM. Handles 90%+ of clean academic PDFs
well. Falls down on:
  - Heavily layouted papers (multi-column with floats interrupting text flow)
  - Scanned / image-based PDFs (no text layer at all)
  - Mathematical notation (LaTeX → unicode is hit-or-miss)

For those, the spec lines up MinerU / LlamaParse / deepseek-ocr — which
land later behind the same ParserProvider interface.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import pymupdf

from neblab_rag.providers.parser.base import ParseResult, ParserProvider


class PyMuPDFParser(ParserProvider):
    parser_name = "pymupdf"

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        # PyMuPDF reads from a bytes stream via filetype hint — no temp file needed
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        try:
            pages_text: list[str] = []
            for page in doc:
                pages_text.append(page.get_text("text"))
            full_text = "\n\n".join(pages_text).strip()
            return ParseResult(
                text=full_text,
                page_count=len(doc),
                parser_name=self.parser_name,
                metadata={
                    "title_from_pdf": doc.metadata.get("title", "") if doc.metadata else "",
                },
            )
        finally:
            doc.close()
