"""Test v2: ThreadPool OpenAlex lookups + async downloads."""
import asyncio
import time

from sqlalchemy import select

from neblab_rag.config import get_settings
from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.providers.parser import PyMuPDFParser
from plant_virus_rag.corpus.fulltext_batch import download_batch
from plant_virus_rag.db.engine import get_pv_session
from plant_virus_rag.db.models import PvDocument, PvFullText

settings = get_settings()


async def main() -> None:
    with get_pv_session() as session:
        stmt = (
            select(PvDocument)
            .outerjoin(PvFullText, PvFullText.document_id == PvDocument.id)
            .where(
                PvDocument.is_oa.is_(True),
                PvDocument.openalex_id.isnot(None),
                PvDocument.year >= 2024,
                PvFullText.id.is_(None),  # skip already-parsed
            )
            .order_by(PvDocument.cited_by_count.desc().nulls_last())
            .limit(50)
        )
        docs = list(session.execute(stmt).scalars().all())
        print(f"Selected {len(docs)} OA papers (2024+, by citations)")

        client = OpenAlexClient(email=settings.openalex_email)
        parser = PyMuPDFParser()

        t0 = time.time()
        result = await download_batch(
            docs, client, parser, session,
            oa_lookup_workers=5,
            download_concurrency=10,
        )
        dt = time.time() - t0

        print(f"\nBatch v2 ({len(docs)} docs, {dt:.1f}s):")
        print(f"  parsed:   {result.parsed}")
        print(f"  no_url:   {result.no_pdf_url}")
        print(f"  failed:   {result.failed}")
        print(f"  avg/doc:  {dt/len(docs):.1f}s")
        if dt > 0:
            print(f"  throughput: {result.parsed/dt*60:.0f} parsed/min")


asyncio.run(main())
