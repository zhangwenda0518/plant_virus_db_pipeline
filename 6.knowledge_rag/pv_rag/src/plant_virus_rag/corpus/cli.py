"""CLI for plant virus RAG ingestion and indexing.

Console script: ``pv-ingest``

Commands:
  pv-ingest structured --source dpv --dir rag-db/dpv_database/md
  pv-ingest structured --source ncbi --file rag-db/final.cluster.ref_info.tsv
  pv-ingest structured --source ictv --dir rag-db/ICTV_RAG_Database/docs
  pv-ingest structured --source viralzone --dir rag-db/viralzone_rag_db/md
  pv-ingest openalex --topic plant_virus --language en --max 500
  pv-ingest fulltext --max 50
  pv-ingest index --commit-every 10
"""

import click

from neblab_rag.config import get_settings
from neblab_rag.corpus.fulltext import FullTextFetcher
from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.db.engine import get_engine, get_session
from neblab_rag.providers.factory import (
    build_embedding_provider,
    build_qdrant_repo,
)
from neblab_rag.providers.parser import PyMuPDFParser
from neblab_rag.rag.bm25_index import BM25Index
from plant_virus_rag.config import get_composite_settings
from plant_virus_rag.corpus.ingestion import PvStructuredIngestionService
from plant_virus_rag.corpus.openalex_ingestion import PvOpenAlexIngestionService
from plant_virus_rag.corpus.pubmed_client import PubMedClient
from plant_virus_rag.corpus.pubmed_ingestion import PubMedIngestionService
from plant_virus_rag.corpus.search_provider import (
    OpenAlexSearchProvider,
    PubMedSearchProvider,
)
from plant_virus_rag.corpus.search_service import SearchService
from plant_virus_rag.corpus.topics import PLANT_VIRUS_TOPICS, TOPIC_BY_ID
from plant_virus_rag.db.models import PvChunk, SourceType
from plant_virus_rag.logging_config import configure_logging
from plant_virus_rag.rag.indexer import PvChunkIndexer

SOURCE_TYPE_MAP: dict[str, SourceType] = {
    "ictv": SourceType.ICTV,
    "viralzone": SourceType.VIRALZONE,
    "ncbi": SourceType.NCBI_HOST,
    "dpv": SourceType.ICTV,  # DPV uses ICTV as source_type
}


@click.group()
@click.option("--log-level", default=None, help="Override log level (DEBUG/INFO/WARNING)")
def cli(log_level: str | None):
    """Plant Virus RAG ingestion CLI."""
    if log_level:
        import os
        os.environ["LOG_LEVEL"] = log_level
    configure_logging()


@cli.command("structured")
@click.option(
    "--source", "-s", required=True,
    type=click.Choice(["dpv", "ncbi", "ictv", "viralzone"]),
    help="Data source type",
)
@click.option(
    "--file", "-f", "file_path", default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Single file to ingest (for TSV/CSV sources)",
)
@click.option(
    "--dir", "-d", "dir_path", default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Directory of .md files to ingest (for DPV/ICTV/ViralZone)",
)
@click.option("--max-files", "-n", default=None, type=int, help="Max files/records to ingest")
@click.option("--commit-every", default=100, help="Commit every N records")
def structured_cmd(
    source: str, file_path: str | None, dir_path: str | None,
    max_files: int | None, commit_every: int,
):
    """Ingest structured virus data."""
    source_type = SOURCE_TYPE_MAP[source]
    from pathlib import Path

    if not file_path and not dir_path:
        raise click.UsageError("Must specify --file or --dir")

    with get_session() as session:
        service = PvStructuredIngestionService(session)
        if source == "dpv":
            count = service.ingest_dpv(
                dir_path=Path(dir_path),
                commit_every=commit_every,
                max_files=max_files,
            )
            click.echo(f"Ingested {count} DPV records from {dir_path}")
        elif dir_path:
            count = service.ingest_dir(
                source_type=source_type,
                dir_path=Path(dir_path),
                commit_every=commit_every,
                max_files=max_files,
            )
            click.echo(f"Ingested {count} records from {source} ({dir_path})")
        else:
            count = service.ingest_file(
                source_type=source_type,
                file_path=Path(file_path),
                commit_every=commit_every,
            )
            click.echo(f"Ingested {count} records from {source} ({file_path})")


@cli.command("openalex")
@click.option(
    "--topic", "-t", default="plant_virus",
    type=click.Choice([t.id for t in PLANT_VIRUS_TOPICS]),
    help="Topic to harvest (default: plant_virus)",
)
@click.option(
    "--language", "-l", default="en",
    type=click.Choice(["en", "zh"]),
    help="Paper language (default: en)",
)
@click.option("--max", "-n", "max_results", default=500, help="Max papers per topic")
@click.option("--year-from", type=int, default=None, help="Earliest publication year")
@click.option("--year-to", type=int, default=None, help="Latest publication year")
@click.option(
    "--resume", is_flag=True, default=False,
    help="Year-by-year download with resume support. Keeps progress in pv_openalex_progress.json.",
)
def openalex_cmd(
    topic: str, language: str, max_results: int,
    year_from: int | None, year_to: int | None, resume: bool,
):
    """Ingest academic papers from OpenAlex.

    Examples:
      pv-ingest openalex --year-from 2021 --max 200        # recent papers
      pv-ingest openalex --resume                          # download all years, resume-safe
      pv-ingest openalex --resume --year-from 2020         # resume from 2020 onwards
    """
    settings = get_settings()
    topic_config = TOPIC_BY_ID[topic]
    client = OpenAlexClient(email=settings.openalex_email)

    with get_session() as session:
        service = PvOpenAlexIngestionService(client, session)
        if resume:
            result = service.ingest_all_years(
                topic=topic_config,
                language=language,
                year_from=year_from,
                year_to=year_to,
                resume=True,
            )
            click.echo(
                f"Ingested {result['total']} papers across {result['years_completed']} years "
                f"for topic '{topic}' ({language})"
            )
        else:
            count = service.ingest_topic(
                topic=topic_config,
                language=language,
                max_results=max_results,
                year_from=year_from,
                year_to=year_to,
            )
            click.echo(f"Ingested {count} papers for topic '{topic}' ({language})")


@cli.command("pubmed")
@click.option("--max", "-n", "max_results", default=500, help="Max papers to fetch")
@click.option("--year-from", type=int, default=None, help="Earliest publication year")
@click.option("--year-to", type=int, default=None, help="Latest publication year")
@click.option("--commit-every", default=50, help="Commit every N papers")
def pubmed_cmd(
    max_results: int,
    year_from: int | None,
    year_to: int | None,
    commit_every: int,
):
    """Search PubMed for plant virus papers and ingest with DOI dedup.

    Papers already in pv_documents (via OpenAlex) are skipped by DOI match.
    Existing papers without a PubMed ID are enriched with the PubMed ID.

    Examples:
      pv-ingest pubmed --max 200                # recent papers
      pv-ingest pubmed --year-from 2020 --max 500
      pv-ingest pubmed --year-from 2024 --year-to 2025
    """
    settings = get_settings()
    client = PubMedClient(email=settings.openalex_email)

    with get_session() as session:
        service = PubMedIngestionService(client, session)
        result = service.search_and_ingest(
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
            commit_every=commit_every,
        )
        click.echo(
            f"PubMed: fetched {result['total_fetched']} PMIDs, "
            f"new {result['new']}, skipped {result['skipped_duplicate']} duplicates"
        )


@cli.command("multisearch")
@click.option(
    "--query", "-q", default="plant virus", help="Search query (default: plant virus)"
)
@click.option("--max", "-n", "max_results", default=20, help="Max results per source")
@click.option("--year-from", type=int, default=None, help="Earliest publication year")
@click.option("--year-to", type=int, default=None, help="Latest publication year")
@click.option(
    "--sources", "-s", default="openalex,pubmed",
    help="Comma-separated source list (default: openalex,pubmed)",
)
@click.option(
    "--ingest/--no-ingest", default=False,
    help="Also ingest new papers into pv_documents (with DOI dedup)",
)
def multisearch_cmd(
    query: str,
    max_results: int,
    year_from: int | None,
    year_to: int | None,
    sources: str,
    ingest: bool,
):
    """Search OpenAlex + PubMed in parallel with DOI dedup.

    Sources: openalex, pubmed.

    Examples:
      pv-ingest multisearch --query "tomato yellow leaf curl virus" --max 20
      pv-ingest multisearch --query "plant virus resistance" --max 50 --year-from 2024 --ingest
    """
    settings = get_settings()

    # Build providers
    provider_map = {
        "openalex": OpenAlexSearchProvider(email=settings.openalex_email),
        "pubmed": PubMedSearchProvider(email=settings.openalex_email),
    }
    selected = [s.strip() for s in sources.split(",") if s.strip() in provider_map]
    providers = [provider_map[s] for s in selected]

    service = SearchService(providers)
    click.echo(f"Searching '{query}' across {len(providers)} sources ({', '.join(selected)})...")
    results = service.search(query=query, max_results=max_results, year_from=year_from, year_to=year_to)

    click.echo(f"\nTotal after dedup: {len(results)} papers\n")
    for i, r in enumerate(results, 1):
        doi_str = f" [DOI: {r.doi}]" if r.doi else ""
        src_str = f"[{r.source}]"
        click.echo(f"  {i:>2}. {r.title[:80]}")
        click.echo(f"      {src_str}  year={r.year or '?'}  citations={r.cited_by_count}{doi_str}")

    if ingest and results:
        _ingest_search_results(results, settings)


def _ingest_search_results(results: list, settings) -> None:
    """Insert search results into pv_documents with DOI dedup."""
    from plant_virus_rag.db.repositories import PvDocumentRepository
    from plant_virus_rag.db.models import SourceType as PvSourceType

    source_type_map = {
        "arxiv": PvSourceType.OPENALEX,  # arxiv not in our SourceType enum, use openalex
        "semantic_scholar": PvSourceType.OPENALEX,
        "pubmed": PvSourceType.PUBMED,
    }

    with get_session() as session:
        repo = PvDocumentRepository(session)
        new_count = 0
        dup_count = 0
        for r in results:
            existing = None
            if r.doi:
                from sqlalchemy import select
                from plant_virus_rag.db.models import PvDocument
                existing = session.execute(
                    select(PvDocument).where(PvDocument.doi == r.doi)
                ).scalar_one_or_none()

            if existing is not None:
                dup_count += 1
                continue

            st = source_type_map.get(r.source, PvSourceType.OPENALEX)
            repo.upsert_metadata(
                source_type=st,
                openalex_id=None,
                pubmed_id=r.pubmed_id,
                doi=r.doi,
                title=r.title,
                authors=r.authors,
                venue=r.venue,
                year=r.year,
                language=r.language,
                is_oa=r.is_oa,
                cited_by_count=r.cited_by_count,
                abstract_text=r.abstract,
                virus_names=None,
            )
            new_count += 1

        session.commit()
        click.echo(f"\nIngested: {new_count} new, {dup_count} duplicates skipped")


@cli.command("fulltext")
@click.option("--max", "-n", "limit", default=50, help="Max PDFs to fetch")
@click.option("--year-from", type=int, default=None, help="Earliest publication year")
@click.option("--year-to", type=int, default=None, help="Latest publication year")
def fulltext_cmd(limit: int, year_from: int | None, year_to: int | None):
    """Download and parse OA PDFs for plant virus papers."""
    import httpx as _httpx
    parser = PyMuPDFParser()
    settings = get_settings()
    oa_client = OpenAlexClient(email=settings.openalex_email)

    with get_session() as session:
        from plant_virus_rag.db.repositories import PvDocumentRepository, PvFullTextRepository
        pv_doc_repo = PvDocumentRepository(session)
        ft_repo = PvFullTextRepository(session)

        pending = pv_doc_repo.list_oa_without_fulltext(
            limit=limit, year_from=year_from, year_to=year_to,
        )
        total = len(pending)
        parsed = 0
        failed = 0
        no_url = 0

        import click as _click
        with _click.progressbar(pending, label="Downloading PDFs", show_pos=True) as bar:
            for doc in bar:
                if not doc.openalex_id:
                    no_url += 1
                    continue
                url = oa_client.get_pdf_url(doc.openalex_id)
                if not url:
                    no_url += 1
                    continue
                try:
                    resp = _httpx.get(url, timeout=30, follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
                    if resp.status_code != 200:
                        failed += 1
                        continue
                    result = parser.parse(resp.content)
                    if not result.text.strip():
                        failed += 1
                        continue
                    ft_repo.upsert(
                        document_id=doc.id, text=result.text,
                        page_count=result.page_count,
                        parser_name=result.parser_name, source_url=url,
                    )
                    session.flush()
                    parsed += 1
                except Exception:
                    failed += 1
                    continue

        year_info = ""
        if year_from:
            year_info += f", from {year_from}"
        if year_to:
            year_info += f", to {year_to}"
        click.echo(
            f"Fulltext{year_info}: parsed {parsed}, failed {failed}, "
            f"no_url {no_url}, total pending {total}"
        )


@cli.command("index")
@click.option("--commit-every", default=None, type=int, help="Commit every N docs/records")
@click.option("--records/--no-records", default=True, help="Index structured records")
@click.option("--documents/--no-documents", default=True, help="Index academic papers")
def index_cmd(commit_every: int | None, records: bool, documents: bool):
    """Index pending records and documents into Qdrant."""
    import asyncio

    settings = get_composite_settings()
    embedder = build_embedding_provider()
    qdrant = build_qdrant_repo(collection=settings.qdrant_collection)

    async def _run():
        with get_session() as session:
            indexer = PvChunkIndexer(
                session=session,
                embedder=embedder,
                qdrant=qdrant,
            )
            n_records = 0
            n_docs = 0
            if records:
                n_records = await indexer.index_pending_records(commit_every=commit_every)
            if documents:
                n_docs = await indexer.index_pending_documents(commit_every=commit_every)
            return n_records, n_docs

    n_records, n_docs = asyncio.run(_run())
    click.echo(f"Indexed {n_records} records + {n_docs} documents")


@cli.command("bm25-rebuild")
def bm25_rebuild_cmd():
    """Rebuild the PV BM25 index and print stats. Persists to disk for fast reload."""
    with get_session() as session:
        rows = session.query(PvChunk.id, PvChunk.text, PvChunk.source_type).all()
    index = BM25Index.from_chunks([(int(r[0]), str(r[1])) for r in rows])

    from collections import Counter
    source_counts = Counter()
    for r in rows:
        source_counts[str(r[2])] += 1

    # Persist to disk so next pipeline init skips the 30s rebuild
    from plant_virus_rag.rag.pipeline import BM25S_CACHE_DIR
    try:
        index.save(BM25S_CACHE_DIR)
        click.echo(f"BM25S index saved to {BM25S_CACHE_DIR}/")
    except Exception as exc:
        click.echo(f"Warning: failed to persist BM25S cache: {exc}")

    click.echo(f"BM25 index rebuilt: {len(rows)} chunks")
    for st, cnt in sorted(source_counts.items()):
        click.echo(f"  {st}: {cnt}")


@cli.command("stats")
def stats_cmd():
    """Show database statistics: paper year distribution, OA ratio, source counts."""
    from plant_virus_rag.db.models import PvDocument, PvRecord, PvIndexStatus
    from sqlalchemy import func as sa_func

    with get_session() as session:
        # ── pv_documents (academic papers) ──
        click.echo("=" * 60)
        click.echo("  Academic Papers (pv_documents)")
        click.echo("=" * 60)

        doc_count = session.query(sa_func.count(PvDocument.id)).scalar()
        oa_count = session.query(sa_func.count(PvDocument.id)).filter(
            PvDocument.is_oa.is_(True)
        ).scalar()
        pubmed_count = session.query(sa_func.count(PvDocument.id)).filter(
            PvDocument.pubmed_id.isnot(None)
        ).scalar()

        click.echo(f"  Total papers:         {doc_count}")
        click.echo(f"  Open Access (OA):     {oa_count} ({oa_count/doc_count*100:.1f}%)" if doc_count else "  OA: 0")
        click.echo(f"  With PubMed ID:       {pubmed_count}")

        # Year distribution
        years = (
            session.query(PvDocument.year, sa_func.count(PvDocument.id))
            .filter(PvDocument.year.isnot(None))
            .group_by(PvDocument.year)
            .order_by(PvDocument.year)
            .all()
        )
        if years:
            max_cnt = max(c for _, c in years)
            click.echo(f"\n  Year distribution ({len(years)} years):")
            for year, cnt in years:
                bar = "█" * max(1, cnt * 40 // max(1, max_cnt))
                click.echo(f"    {year}: {cnt:>5}  {bar}")

        # ── pv_records (structured data) ──
        click.echo(f"\n{'=' * 60}")
        click.echo("  Structured Records (pv_records)")
        click.echo("=" * 60)

        source_counts = (
            session.query(PvRecord.source_type, sa_func.count(PvRecord.id))
            .group_by(PvRecord.source_type)
            .order_by(sa_func.count(PvRecord.id).desc())
            .all()
        )
        rec_total = session.query(sa_func.count(PvRecord.id)).scalar()
        click.echo(f"  Total records:        {rec_total}")
        for st, cnt in source_counts:
            click.echo(f"    {st}: {cnt}")

        # ── Index status ──
        click.echo(f"\n{'=' * 60}")
        click.echo("  Index Status")
        click.echo("=" * 60)
        doc_status = (
            session.query(PvDocument.status, sa_func.count(PvDocument.id))
            .group_by(PvDocument.status)
            .all()
        )
        rec_status = (
            session.query(PvRecord.status, sa_func.count(PvRecord.id))
            .group_by(PvRecord.status)
            .all()
        )
        click.echo("  pv_documents:")
        for status, cnt in doc_status:
            click.echo(f"    {status}: {cnt}")
        click.echo("  pv_records:")
        for status, cnt in rec_status:
            click.echo(f"    {status}: {cnt}")

        # ── Chunk stats ──
        click.echo(f"\n{'=' * 60}")
        click.echo("  Chunks (pv_chunks)")
        click.echo("=" * 60)
        chunk_total = session.query(sa_func.count(PvChunk.id)).scalar()
        chunks_by_source = (
            session.query(PvChunk.source_type, sa_func.count(PvChunk.id))
            .group_by(PvChunk.source_type)
            .order_by(sa_func.count(PvChunk.id).desc())
            .all()
        )
        click.echo(f"  Total chunks: {chunk_total}")
        for st, cnt in chunks_by_source:
            click.echo(f"    {st}: {cnt}")
