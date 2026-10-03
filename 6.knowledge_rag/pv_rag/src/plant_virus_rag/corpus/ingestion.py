"""Structured data ingestion service for plant virus records.

Reads DPV / ICTV / ViralZone / NCBI host data via parsers, upserts into
pv_records, and maintains status tracking for downstream indexing.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from plant_virus_rag.corpus.structured.dpv_parser import DpvParser, PvRecordDTO
from plant_virus_rag.corpus.structured.ictv_md_parser import IctvMdParser
from plant_virus_rag.corpus.structured.ncbi_tsv_parser import NcbiTsvParser
from plant_virus_rag.corpus.structured.viralzone_md_parser import ViralZoneMdParser
from plant_virus_rag.db.models import PvIndexStatus, SourceType
from plant_virus_rag.db.repositories import PvRecordRepository
from plant_virus_rag.logging_config import get_logger

log = get_logger(__name__)

PARSER_CLASSES: dict[SourceType, type] = {
    SourceType.ICTV: IctvMdParser,
    SourceType.VIRALZONE: ViralZoneMdParser,
    SourceType.NCBI_HOST: NcbiTsvParser,
}

# DPV files don't have a SourceType enum value, we add it via the parser itself
DPV_SOURCE_TYPE = SourceType.ICTV  # reuse ICTV as "structured taxonomy data"


class PvStructuredIngestionService:
    """Upserts structured virus data into pv_records."""

    def __init__(self, session: Session):
        self._repo = PvRecordRepository(session)
        self._session = session

    def ingest_file(
        self,
        *,
        source_type: SourceType,
        file_path: Path,
        commit_every: int = 100,
    ) -> int:
        """Parse a single file and upsert all records. Returns count."""
        parser_cls = PARSER_CLASSES.get(source_type)
        if parser_cls is None:
            raise ValueError(f"Unknown source_type for file ingestion: {source_type}")

        parser = parser_cls()
        total = 0

        for dto in parser.parse(file_path):
            self._upsert_dto(source_type=source_type, dto=dto)
            total += 1
            if total % commit_every == 0:
                self._session.commit()
                log.info("structured_ingest_progress", source=source_type, count=total)

        self._session.commit()
        log.info("structured_ingest_done", source=source_type, total=total)
        return total

    def ingest_dir(
        self,
        *,
        source_type: SourceType,
        dir_path: Path,
        commit_every: int = 100,
        max_files: int | None = None,
    ) -> int:
        """Parse a directory of .md files and upsert all records. Returns count."""
        parser_cls = PARSER_CLASSES.get(source_type)
        if parser_cls is None:
            # DPV uses a separate parser
            raise ValueError(f"Unknown source_type for directory ingestion: {source_type}")

        parser = parser_cls()
        if not hasattr(parser, "parse_dir"):
            raise ValueError(f"Parser for {source_type} does not support directory ingestion")

        total = 0
        for dto in parser.parse_dir(dir_path):
            self._upsert_dto(source_type=source_type, dto=dto)
            total += 1
            if total % commit_every == 0:
                self._session.commit()
                log.info("structured_ingest_progress", source=source_type, count=total)
            if max_files and total >= max_files:
                break

        self._session.commit()
        log.info("structured_ingest_done", source=source_type, total=total)
        return total

    def ingest_dpv(
        self,
        *,
        dir_path: Path,
        commit_every: int = 100,
        max_files: int | None = None,
    ) -> int:
        """Ingest DPV Markdown files. Returns count."""
        parser = DpvParser()
        total = 0
        for dto in parser.parse_dir(dir_path):
            self._upsert_dto(source_type=DPV_SOURCE_TYPE, dto=dto)
            total += 1
            if total % commit_every == 0:
                self._session.commit()
                log.info("structured_ingest_progress", source="dpv", count=total)
            if max_files and total >= max_files:
                break

        self._session.commit()
        log.info("structured_ingest_done", source="dpv", total=total)
        return total

    def _upsert_dto(self, *, source_type: SourceType, dto: PvRecordDTO) -> None:
        self._repo.upsert(
            source_type=source_type,
            source_id=None,
            virus_name=dto.virus_name[:300],
            virus_abbreviation=(dto.virus_abbreviation or "")[:100] or None,
            taxonomy=dto.taxonomy,
            host_species=dto.host_species,
            host_family=dto.host_family,
            vector=dto.vector,
            symptoms=dto.symptoms,
            transmission=dto.transmission,
            genome_type=(dto.genome_type or "")[:50] or None,
            genome_size_kb=dto.genome_size_kb,
            description=dto.description,
            references=dto.references,
        )
