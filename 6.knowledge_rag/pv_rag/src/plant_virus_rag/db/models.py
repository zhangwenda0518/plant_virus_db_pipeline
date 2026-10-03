"""SQLAlchemy ORM models for Plant Virus RAG.

Tables use the ``pv_`` prefix to avoid collisions with NEBLab tables
in the same Postgres database.

Two source categories converge at pv_chunks:
  - Structured data (ICTV, ViralZone, NCBI) → pv_records
  - Academic papers (OpenAlex, PubMed, CNKI) → pv_documents
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class PvBase(DeclarativeBase):
    """Independent metadata target for plant-virus alembic migrations."""

    pass


class SourceType(StrEnum):
    ICTV = "ictv"
    VIRALZONE = "viralzone"
    NCBI_HOST = "ncbi_host"
    OPENALEX = "openalex"
    PUBMED = "pubmed"
    CNKI = "cnki"
    PLANT_INSECT = "plant_insect"


class PvIndexStatus(StrEnum):
    METADATA_ONLY = "metadata_only"
    FULLTEXT_INDEXED = "fulltext_indexed"
    FAILED = "failed"


# ── TABLE 1: pv_records — structured virus data ──────────────────────

class PvRecord(PvBase):
    """One row per structured virus record (ICTV taxon, ViralZone fact, NCBI host)."""

    __tablename__ = "pv_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[SourceType] = mapped_column(
        String(20), nullable=False, index=True
    )
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    virus_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    virus_abbreviation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    taxonomy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    host_species: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    host_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vector: Mapped[str | None] = mapped_column(String(200), nullable=True)
    symptoms: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    transmission: Mapped[str | None] = mapped_column(String(300), nullable=True)
    genome_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    genome_size_kb: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    references: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[PvIndexStatus] = mapped_column(
        String(20), default=PvIndexStatus.METADATA_ONLY
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["PvChunk"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="PvChunk.chunk_index",
        foreign_keys="PvChunk.record_id",
    )


# ── TABLE 2: pv_documents — academic papers ──────────────────────────

class PvDocument(PvBase):
    """One row per academic paper relevant to plant virology."""

    __tablename__ = "pv_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[SourceType] = mapped_column(
        String(20), nullable=False, default=SourceType.OPENALEX, index=True
    )
    openalex_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    pubmed_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    venue: Mapped[str | None] = mapped_column(String(500), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_oa: Mapped[bool] = mapped_column(default=False)
    cited_by_count: Mapped[int] = mapped_column(default=0)
    virus_names: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[PvIndexStatus] = mapped_column(
        String(20), default=PvIndexStatus.METADATA_ONLY
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    abstract: Mapped["PvAbstract | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    fulltext: Mapped["PvFullText | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    chunks: Mapped[list["PvChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="PvChunk.chunk_index",
        foreign_keys="PvChunk.document_id",
    )


# ── TABLE 3: pv_abstracts ────────────────────────────────────────────

class PvAbstract(PvBase):
    """Abstract text per academic paper."""

    __tablename__ = "pv_abstracts"
    __table_args__ = (UniqueConstraint("document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("pv_documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=True)

    document: Mapped[PvDocument] = relationship(back_populates="abstract")


# ── TABLE 4: pv_fulltexts ────────────────────────────────────────────

class PvFullText(PvBase):
    """Parsed full text per academic paper."""

    __tablename__ = "pv_fulltexts"
    __table_args__ = (UniqueConstraint("document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("pv_documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parser_name: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[PvDocument] = relationship(back_populates="fulltext")


# ── TABLE 5: pv_chunks — shared by records AND documents ─────────────

class PvChunk(PvBase):
    """One row per text chunk indexed in Qdrant.

    Shared between structured records and academic papers, discriminated by
    ``source_type``. ``record_id`` and ``document_id`` are mutually exclusive
    (enforced at the application layer).

    The chunk's int PK IS the Qdrant point id (same pattern as NEBLab).
    """

    __tablename__ = "pv_chunks"
    __table_args__ = (
        UniqueConstraint("record_id", "chunk_index", name="uq_pv_chunks_record_idx"),
        UniqueConstraint("document_id", "chunk_index", name="uq_pv_chunks_doc_idx"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[SourceType] = mapped_column(
        String(20), nullable=False, index=True
    )
    record_id: Mapped[int | None] = mapped_column(
        ForeignKey("pv_records.id", ondelete="CASCADE"), index=True, nullable=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("pv_documents.id", ondelete="CASCADE"), index=True, nullable=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    record: Mapped[PvRecord | None] = relationship(
        back_populates="chunks", foreign_keys=[record_id]
    )
    document: Mapped[PvDocument | None] = relationship(
        back_populates="chunks", foreign_keys=[document_id]
    )
