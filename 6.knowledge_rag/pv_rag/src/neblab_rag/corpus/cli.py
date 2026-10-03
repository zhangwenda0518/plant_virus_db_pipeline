"""CLI entrypoint for corpus ingestion.

Usage::

    neblab-ingest ingest --max 200 --language en
    neblab-ingest ingest --topic desertification --language zh

Registered as console script ``neblab-ingest`` via pyproject.toml.
"""

import click

from neblab_rag.config import get_settings
from neblab_rag.corpus.fulltext import FullTextFetcher
from neblab_rag.corpus.ingestion import IngestionService
from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.corpus.topics import TOPIC_BY_ID, TOPICS
from neblab_rag.db.engine import get_session
from neblab_rag.logging_config import configure_logging, get_logger
from neblab_rag.providers.parser import PyMuPDFParser

log = get_logger(__name__)


@click.group()
def cli() -> None:
    """NEBLab corpus operations."""
    configure_logging(get_settings().log_level)


@cli.command("ingest")
@click.option("--topic", "topic_id", default=None, help="Topic id; default: all topics")
@click.option(
    "--language",
    default="en",
    type=click.Choice(["en", "zh"]),
    help="Language to ingest",
)
@click.option("--max", "max_results", default=500, type=int)
def ingest(topic_id: str | None, language: str, max_results: int) -> None:
    """Ingest OpenAlex metadata for topic(s)."""
    settings = get_settings()
    client = OpenAlexClient(email=settings.openalex_email)

    topics = [TOPIC_BY_ID[topic_id]] if topic_id else TOPICS

    total = 0
    with get_session() as session:
        service = IngestionService(client=client, session=session)
        for t in topics:
            n = service.ingest_topic(t, language=language, max_results=max_results)
            total += n
    log.info("ingest_total", count=total)
    click.echo(f"Ingested {total} documents")


@cli.command("fetch-fulltext")
@click.option(
    "--max",
    "max_docs",
    default=10,
    type=int,
    help="Max docs to attempt this run (default: 10 — start small)",
)
def fetch_fulltext(max_docs: int) -> None:
    """Sprint 1: download + parse PDFs for OA docs that have no fulltext yet.

    Idempotent: each run picks up where the last left off (skips docs that
    already have a FullText row). Failures (no PDF, 404, parse error) are
    logged and skipped without aborting the batch.
    """
    settings = get_settings()
    client = OpenAlexClient(email=settings.openalex_email)
    parser = PyMuPDFParser()

    with get_session() as session:
        fetcher = FullTextFetcher(session=session, openalex=client, parser=parser)
        counts = fetcher.fetch_pending(limit=max_docs)
        session.commit()

    click.echo(
        f"tried={counts['tried']}  no_url={counts['no_url']}  "
        f"downloaded={counts['downloaded']}  parsed={counts['parsed']}  failed={counts['failed']}"
    )


if __name__ == "__main__":
    cli()
