"""Repository pattern for plant virus DB tables."""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from neblab_rag.rag.chunker import Chunk as ChunkText
from plant_virus_rag.db.models import (
    PvAbstract,
    PvChunk,
    PvDocument,
    PvFullText,
    PvIndexStatus,
    PvRecord,
    SourceType,
)


class PvRecordRepository:
    """CRUD for pv_records (structured data from ICTV / ViralZone / NCBI)."""

    def __init__(self, session: Session):
        self._session = session

    def upsert(
        self,
        *,
        source_type: SourceType,
        source_id: str | None,
        virus_name: str,
        virus_abbreviation: str | None,
        taxonomy: dict | None,
        host_species: list[str] | None,
        host_family: str | None,
        vector: str | None,
        symptoms: list[str] | None,
        transmission: str | None,
        genome_type: str | None,
        genome_size_kb: float | None,
        description: str | None,
        references: list[str] | None,
    ) -> PvRecord:
        existing: PvRecord | None = None
        if source_id:
            stmt = select(PvRecord).where(
                PvRecord.source_type == source_type, PvRecord.source_id == source_id
            )
            existing = self._session.execute(stmt).scalar_one_or_none()
        if existing is None:
            stmt = select(PvRecord).where(
                PvRecord.source_type == source_type, PvRecord.virus_name == virus_name
            )
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            record = PvRecord(
                source_type=source_type,
                source_id=source_id,
                virus_name=virus_name,
                virus_abbreviation=virus_abbreviation,
                taxonomy=taxonomy,
                host_species=host_species,
                host_family=host_family,
                vector=vector,
                symptoms=symptoms,
                transmission=transmission,
                genome_type=genome_type,
                genome_size_kb=genome_size_kb,
                description=description,
                references=references,
            )
            self._session.add(record)
            self._session.flush()
            return record

        existing.virus_abbreviation = virus_abbreviation or existing.virus_abbreviation
        existing.taxonomy = taxonomy or existing.taxonomy
        existing.host_species = host_species or existing.host_species
        existing.host_family = host_family or existing.host_family
        existing.vector = vector or existing.vector
        existing.symptoms = symptoms or existing.symptoms
        existing.transmission = transmission or existing.transmission
        existing.genome_type = genome_type or existing.genome_type
        existing.genome_size_kb = genome_size_kb or existing.genome_size_kb
        existing.description = description or existing.description
        existing.references = references or existing.references
        return existing

    def list_with_status(
        self, status: PvIndexStatus, *, limit: int | None = None
    ) -> Sequence[PvRecord]:
        stmt = select(PvRecord).where(PvRecord.status == status)
        if limit:
            stmt = stmt.limit(limit)
        return self._session.execute(stmt).scalars().all()


class PvDocumentRepository:
    """CRUD for pv_documents (academic papers from OpenAlex / PubMed / CNKI)."""

    def __init__(self, session: Session):
        self._session = session

    def upsert_metadata(
        self,
        *,
        source_type: SourceType = SourceType.OPENALEX,
        openalex_id: str | None,
        pubmed_id: str | None = None,
        doi: str | None,
        title: str,
        authors: list[str],
        venue: str | None,
        year: int | None,
        language: str | None,
        is_oa: bool,
        cited_by_count: int,
        abstract_text: str | None,
        abstract_language: str | None = None,
        virus_names: list[str] | None = None,
    ) -> PvDocument:
        existing: PvDocument | None = None
        if openalex_id:
            stmt = select(PvDocument).where(PvDocument.openalex_id == openalex_id)
            existing = self._session.execute(stmt).scalar_one_or_none()
        if existing is None and doi:
            stmt = select(PvDocument).where(PvDocument.doi == doi)
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            doc = PvDocument(
                source_type=source_type,
                openalex_id=openalex_id,
                pubmed_id=pubmed_id,
                doi=doi,
                title=title,
                authors=authors,
                venue=venue,
                year=year,
                language=language,
                is_oa=is_oa,
                cited_by_count=cited_by_count,
                virus_names=virus_names,
            )
            self._session.add(doc)
            self._session.flush()
        else:
            existing.title = title
            existing.authors = authors
            existing.venue = venue
            existing.year = year
            existing.language = language
            existing.is_oa = is_oa
            existing.cited_by_count = cited_by_count
            existing.pubmed_id = pubmed_id or existing.pubmed_id
            existing.virus_names = virus_names or existing.virus_names
            doc = existing

        if abstract_text:
            if doc.abstract is None:
                doc.abstract = PvAbstract(
                    document_id=doc.id,
                    text=abstract_text,
                    language=abstract_language or "und",
                )
            else:
                doc.abstract.text = abstract_text
                doc.abstract.language = abstract_language or doc.abstract.language

        return doc

    def list_with_status(
        self, status: PvIndexStatus, *, limit: int | None = None
    ) -> Sequence[PvDocument]:
        stmt = select(PvDocument).where(PvDocument.status == status)
        if limit:
            stmt = stmt.limit(limit)
        return self._session.execute(stmt).scalars().all()

    def list_oa_without_fulltext(
        self, *, limit: int | None = None,
        year_from: int | None = None, year_to: int | None = None,
    ) -> Sequence[PvDocument]:
        stmt = (
            select(PvDocument)
            .outerjoin(PvFullText, PvDocument.id == PvFullText.document_id)
            .where(PvDocument.is_oa.is_(True))
            .where(PvFullText.id.is_(None))
        )
        if year_from:
            stmt = stmt.where(PvDocument.year >= year_from)
        if year_to:
            stmt = stmt.where(PvDocument.year <= year_to)
        if limit:
            stmt = stmt.limit(limit)
        return self._session.execute(stmt).scalars().all()


class PvFullTextRepository:
    """Persists parsed fulltext rows for pv_documents."""

    def __init__(self, session: Session):
        self._session = session

    def upsert(
        self,
        *,
        document_id: int,
        text: str,
        page_count: int,
        parser_name: str,
        source_url: str | None,
    ) -> PvFullText:
        existing = (
            self._session.execute(
                select(PvFullText).where(PvFullText.document_id == document_id)
            )
            .scalars()
            .one_or_none()
        )
        if existing is None:
            row = PvFullText(
                document_id=document_id,
                text=text,
                page_count=page_count,
                parser_name=parser_name,
                source_url=source_url,
            )
            self._session.add(row)
            self._session.flush()
            return row
        existing.text = text
        existing.page_count = page_count
        existing.parser_name = parser_name
        existing.source_url = source_url
        return existing


class PvChunkRepository:
    """Persists chunk rows. Replace-on-write keeps re-indexing idempotent."""

    def __init__(self, session: Session):
        self._session = session

    def replace_for_record(
        self, record_id: int, source_type: SourceType, chunks: list[ChunkText]
    ) -> list[PvChunk]:
        self._session.execute(
            delete(PvChunk).where(PvChunk.record_id == record_id)
        )
        rows = [
            PvChunk(
                source_type=source_type,
                record_id=record_id,
                chunk_index=i,
                text=c.text,
                start_offset=c.start,
                end_offset=c.end,
            )
            for i, c in enumerate(chunks)
        ]
        self._session.add_all(rows)
        self._session.flush()
        return rows

    def replace_for_document(
        self, document_id: int, source_type: SourceType, chunks: list[ChunkText]
    ) -> list[PvChunk]:
        self._session.execute(
            delete(PvChunk).where(PvChunk.document_id == document_id)
        )
        rows = [
            PvChunk(
                source_type=source_type,
                document_id=document_id,
                chunk_index=i,
                text=c.text,
                start_offset=c.start,
                end_offset=c.end,
            )
            for i, c in enumerate(chunks)
        ]
        self._session.add_all(rows)
        self._session.flush()
        return rows
