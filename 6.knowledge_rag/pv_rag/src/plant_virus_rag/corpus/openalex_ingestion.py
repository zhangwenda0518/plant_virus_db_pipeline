"""OpenAlex paper ingestion for plant virus domain with resume support."""

import json
import time
from pathlib import Path

from sqlalchemy.orm import Session

from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.corpus.topics import TopicConfig
from neblab_rag.logging_config import get_logger
from plant_virus_rag.db.models import SourceType
from plant_virus_rag.db.repositories import PvDocumentRepository

log = get_logger(__name__)

PROGRESS_FILE = "pv_openalex_progress.json"
MAX_RETRIES = 5


class PvOpenAlexIngestionService:
    def __init__(self, client: OpenAlexClient, session: Session):
        self._client = client
        self._repo = PvDocumentRepository(session)
        self._session = session

    def ingest_topic(
        self,
        topic: TopicConfig,
        *,
        language: str,
        max_results: int,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> int:
        keywords = topic.zh_keywords if language == "zh" else topic.en_keywords
        log.info(
            "pv_ingest_start", topic=topic.id, language=language, max=max_results,
            year_from=year_from, year_to=year_to,
        )
        result = self._client.search_by_keywords(
            keywords=keywords, language=language, max_results=max_results,
            year_from=year_from, year_to=year_to,
        )
        log.info("pv_ingest_total_available", total=result.total_count)
        count = 0
        for rec in result:
            self._upsert(rec)
            count += 1
            if count % 100 == 0:
                self._session.flush()
                log.info("pv_ingest_progress", topic=topic.id, count=count)
        self._session.commit()
        log.info("pv_ingest_done", topic=topic.id, language=language, count=count)
        return count

    def ingest_all_years(
        self, topic: TopicConfig, *, language: str,
        year_from: int | None = None, year_to: int | None = None,
        resume: bool = False,
    ) -> dict:
        """Download year by year with resume and progress bar."""
        keywords = topic.zh_keywords if language == "zh" else topic.en_keywords
        if year_from is None:
            year_from = 1950
        if year_to is None:
            import datetime
            year_to = datetime.datetime.now().year

        years = list(range(year_to, year_from - 1, -1))
        progress = self._load_progress()
        completed = set(progress.get(f"{language}_completed", []))
        if resume:
            log.info("pv_ingest_resume", completed_years=len(completed))

        pending = [y for y in years if not (resume and y in completed)]
        log.info("pv_ingest_years_pending", count=len(pending), total=len(years))

        import click as _click
        total_count = 0
        years_done = 0

        with _click.progressbar(pending, label=f"Downloading {language.upper()}", show_pos=True) as bar:
            for year in bar:
                log.info("pv_ingest_year_start", year=year, language=language)
                year_count = self._ingest_year(keywords, language, year)
                if year_count >= 0:
                    total_count += year_count
                    years_done += 1
                    completed.add(year)
                    self._save_progress(language, completed)
                    log.info("pv_ingest_year_done", year=year, count=year_count,
                             total_so_far=total_count, years_done=years_done)

        log.info("pv_ingest_all_years_done", language=language,
                 total=total_count, years_completed=years_done)
        return {"total": total_count, "years_completed": years_done}

    def _ingest_year(self, keywords: list[str], language: str, year: int) -> int:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = self._client.search_by_keywords(
                    keywords=keywords, language=language,
                    max_results=10000, single_year=year,
                )
                count = 0
                for rec in result:
                    self._upsert(rec)
                    count += 1
                self._session.commit()
                return count
            except Exception as exc:
                if attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    log.warning("pv_ingest_year_retry", year=year,
                                attempt=attempt, wait=wait, error=str(exc))
                    time.sleep(wait)
                    try:
                        self._session.rollback()
                    except Exception:
                        pass
                else:
                    log.warning("pv_ingest_year_failed", year=year,
                                attempts=MAX_RETRIES, error=str(exc))
                    try:
                        self._session.rollback()
                    except Exception:
                        pass
                    return -1
        return -1

    def _upsert(self, rec) -> None:
        try:
            self._repo.upsert_metadata(
                source_type=SourceType.OPENALEX,
                openalex_id=rec.openalex_id,
                pubmed_id=rec.pubmed_id,
                doi=rec.doi,
                title=rec.title,
                authors=rec.authors,
                venue=rec.venue,
                year=rec.year,
                language=rec.language,
                is_oa=rec.is_oa,
                cited_by_count=rec.cited_by_count,
                abstract_text=rec.abstract,
                abstract_language=rec.language,
                virus_names=None,
            )
        except Exception:
            try:
                self._session.rollback()
            except Exception:
                pass

    def _load_progress(self) -> dict:
        p = Path(PROGRESS_FILE)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return {}
        return {}

    def _save_progress(self, language: str, completed: set[int]) -> None:
        progress = self._load_progress()
        progress[f"{language}_completed"] = sorted(completed, reverse=True)
        Path(PROGRESS_FILE).write_text(json.dumps(progress, indent=2))
