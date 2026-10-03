"""Ingest OpenAlex records into the documents table.

Pulls metadata + reconstructed abstracts via OpenAlexClient, persists via
DocumentRepository.upsert (idempotent on openalex_id / doi). Caller is
responsible for the outer ``session.commit()``; we ``flush()`` every 100
records so progress is visible and FK ids are populated for any later
abstract inserts.
"""

from sqlalchemy.orm import Session

from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.corpus.topics import TopicConfig
from neblab_rag.db.repositories import DocumentRepository
from neblab_rag.logging_config import get_logger

log = get_logger(__name__)


class IngestionService:
    def __init__(self, client: OpenAlexClient, session: Session):
        self._client = client
        self._repo = DocumentRepository(session)
        self._session = session

    def ingest_topic(
        self,
        topic: TopicConfig,
        *,
        language: str,
        max_results: int,
    ) -> int:
        keywords = topic.zh_keywords if language == "zh" else topic.en_keywords
        log.info("ingest_start", topic=topic.id, language=language, max=max_results)

        count = 0
        for rec in self._client.search_by_keywords(
            keywords=keywords,
            language=language,
            max_results=max_results,
        ):
            self._repo.upsert_metadata(
                openalex_id=rec.openalex_id,
                doi=rec.doi,
                title=rec.title,
                authors=rec.authors,
                venue=rec.venue,
                year=rec.year,
                primary_topic=topic.id,
                extra_topics=[],
                language=rec.language,
                is_oa=rec.is_oa,
                cited_by_count=rec.cited_by_count,
                abstract_text=rec.abstract,
                abstract_language=rec.language,
            )
            count += 1
            if count % 100 == 0:
                self._session.flush()
                log.info("ingest_progress", topic=topic.id, count=count)

        log.info("ingest_done", topic=topic.id, language=language, count=count)
        return count
