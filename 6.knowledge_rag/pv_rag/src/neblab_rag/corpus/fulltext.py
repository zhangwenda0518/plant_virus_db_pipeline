"""Full-text fetcher service.

Walks documents marked OA → asks OpenAlex for the PDF URL → downloads
the PDF → parses with the injected ParserProvider → stores the text.

Failure modes are isolated per-document: a 404, timeout, parse error, or
no-PDF-available all cause that ONE doc to be skipped (with a log line)
without aborting the batch. The outer loop returns counts so the operator
can see throughput.
"""

import contextlib

import httpx
from sqlalchemy.orm import Session

from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.db.models import IndexStatus
from neblab_rag.db.repositories import DocumentRepository, FullTextRepository
from neblab_rag.logging_config import get_logger
from neblab_rag.providers.parser.base import ParserProvider

log = get_logger(__name__)

# Most academic PDFs are well under this; cap protects us from runaway
# downloads (some preprint servers serve generated PDFs that can be huge).
DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024  # 50MB
DEFAULT_TIMEOUT_SECONDS = 30.0


class FullTextFetcher:
    def __init__(
        self,
        session: Session,
        openalex: OpenAlexClient,
        parser: ParserProvider,
        *,
        http_client: httpx.Client | None = None,
        max_bytes: int = DEFAULT_MAX_PDF_BYTES,
    ):
        self._session = session
        self._openalex = openalex
        self._parser = parser
        # Reuse a connection-pooled httpx.Client across the batch; tests inject a mock
        self._http = http_client or httpx.Client(
            timeout=DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "NEBLab-RAG/1.0 (academic research)"},
        )
        self._owns_http = http_client is None
        self._max_bytes = max_bytes
        self._docs = DocumentRepository(session)
        self._fulltexts = FullTextRepository(session)

    def __del__(self) -> None:
        if getattr(self, "_owns_http", False) and getattr(self, "_http", None) is not None:
            with contextlib.suppress(Exception):
                self._http.close()

    def fetch_pending(self, *, limit: int | None = None) -> dict[str, int]:
        """Return counts: ``{tried, no_url, downloaded, parsed, failed}``."""
        pending = list(self._docs.list_oa_without_fulltext(limit=limit))
        counts = {"tried": 0, "no_url": 0, "downloaded": 0, "parsed": 0, "failed": 0}

        for doc in pending:
            counts["tried"] += 1
            if not doc.openalex_id:
                counts["no_url"] += 1
                continue

            url = self._openalex.get_pdf_url(doc.openalex_id)
            if not url:
                log.info("fulltext_no_pdf_url", doc_id=doc.id, openalex_id=doc.openalex_id)
                counts["no_url"] += 1
                continue

            pdf_bytes = self._download(url, doc_id=doc.id)
            if pdf_bytes is None:
                counts["failed"] += 1
                continue
            counts["downloaded"] += 1

            try:
                result = self._parser.parse(pdf_bytes)
            except Exception as exc:
                # Bad PDF (corrupt / encrypted / not actually a PDF) shouldn't
                # abort the batch — mark this doc failed and move on.
                log.warning("fulltext_parse_failed", doc_id=doc.id, error=str(exc))
                doc.status = IndexStatus.FAILED
                self._session.flush()
                counts["failed"] += 1
                continue

            if not result.text.strip():
                # Parser returned empty (e.g. scanned PDF with no text layer)
                log.warning("fulltext_empty_text", doc_id=doc.id, page_count=result.page_count)
                counts["failed"] += 1
                continue

            self._fulltexts.upsert(
                document_id=doc.id,
                text=result.text,
                page_count=result.page_count,
                parser_name=result.parser_name,
                source_url=url,
            )
            self._session.flush()
            counts["parsed"] += 1
            log.info(
                "fulltext_parsed",
                doc_id=doc.id,
                pages=result.page_count,
                chars=len(result.text),
            )

        return counts

    def _download(self, url: str, *, doc_id: int) -> bytes | None:
        try:
            resp = self._http.get(url)
        except httpx.HTTPError as exc:
            log.warning("fulltext_download_error", doc_id=doc_id, url=url, error=str(exc))
            return None

        if resp.status_code != 200:
            log.warning("fulltext_download_status", doc_id=doc_id, url=url, status=resp.status_code)
            return None

        body = resp.content
        if len(body) > self._max_bytes:
            log.warning(
                "fulltext_download_too_large",
                doc_id=doc_id,
                bytes=len(body),
                max_bytes=self._max_bytes,
            )
            return None
        return body
