"""Parallel async OA PDF downloader for plant virus papers.

Two-phase pipeline:
  1. Phase 1: ThreadPoolExecutor parallelises OpenAlex PDF URL lookups
     (``pyalex`` is synchronous, so we use threads to unblock it).
  2. Phase 2: asyncio.Semaphore controls concurrent PDF downloads.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx
from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.logging_config import get_logger
from neblab_rag.providers.parser.base import ParserProvider
from sqlalchemy.orm import Session
from plant_virus_rag.db.models import PvDocument
from plant_virus_rag.db.repositories import PvFullTextRepository

log = get_logger(__name__)

DEFAULT_OA_LOOKUP_WORKERS = 5  # OpenAlex URL lookups (threaded)
DEFAULT_DOWNLOAD_CONCURRENCY = 10  # PDF downloads (async)
DEFAULT_TIMEOUT = 45.0
DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


@dataclass
class FulltextBatchResult:
    tried: int = 0
    no_pdf_url: int = 0
    parsed: int = 0
    failed: int = 0


async def download_batch(
    docs: list[PvDocument],
    openalex: OpenAlexClient,
    parser: ParserProvider,
    session: Session,
    *,
    oa_lookup_workers: int = DEFAULT_OA_LOOKUP_WORKERS,
    download_concurrency: int = DEFAULT_DOWNLOAD_CONCURRENCY,
    commit_every: int = 25,
) -> FulltextBatchResult:
    """Download and parse PDFs for a batch of OA documents.

    Phase 1 (threaded): resolve PDF URLs via OpenAlex in parallel.
    Phase 2 (async):   download + parse PDFs in parallel.
    """
    ft_repo = PvFullTextRepository(session)
    result = FulltextBatchResult(tried=len(docs))

    # ── Phase 1: parallel OpenAlex PDF URL lookups ──────────────────
    loop = asyncio.get_running_loop()

    def _lookup_url(doc: PvDocument) -> tuple[int, str | None]:
        """Thread-safe: pyalex is sync, run in executor."""
        if not doc.openalex_id:
            return (doc.id, None)
        url = openalex.get_pdf_url(doc.openalex_id)
        return (doc.id, url)

    doc_urls: dict[int, str | None] = {}
    with ThreadPoolExecutor(max_workers=oa_lookup_workers) as pool:
        futures = [loop.run_in_executor(pool, _lookup_url, doc) for doc in docs]
        for fut in asyncio.as_completed(futures):
            doc_id, url = await fut
            doc_urls[doc_id] = url

    # ── Phase 2: parallel download + parse ─────────────────────────
    sem = asyncio.Semaphore(download_concurrency)
    download_tasks: list[asyncio.Task[tuple[str, bool]]] = []

    async def _download_one(doc: PvDocument) -> tuple[str, bool]:
        url = doc_urls.get(doc.id)
        if url is None:
            return ("no_url", False)

        async with sem:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "NEBLab-RAG/1.0 (academic research)"},
            ) as client:
                try:
                    resp = await client.get(url)
                except httpx.HTTPError:
                    return ("failed", False)

        if resp.status_code != 200:
            return ("failed", False)

        body = resp.content
        if len(body) > DEFAULT_MAX_BYTES:
            return ("failed", False)

        try:
            parsed = parser.parse(body)
        except Exception:
            return ("failed", False)

        if not parsed.text.strip():
            return ("failed", False)

        ft_repo.upsert(
            document_id=doc.id,
            text=parsed.text,
            page_count=parsed.page_count,
            parser_name=parsed.parser_name,
            source_url=url,
        )
        return ("parsed", True)

    # Build lookup dict for fast doc→url mapping
    download_docs = [d for d in docs if doc_urls.get(d.id)]
    download_tasks = [asyncio.create_task(_download_one(d)) for d in download_docs]

    for i, task in enumerate(asyncio.as_completed(download_tasks)):
        status, _ok = await task
        if status == "parsed":
            result.parsed += 1
        else:
            result.failed += 1
        if commit_every and (i + 1) % commit_every == 0:
            session.flush()

    # no_url = total - (parsed + failed)
    result.no_pdf_url = result.tried - result.parsed - result.failed
    session.commit()
    return result
