"""SQLAlchemy ORM models for documents + abstracts."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IndexStatus(StrEnum):
    METADATA_ONLY = "metadata_only"
    FULLTEXT_PENDING = "fulltext_pending"
    FULLTEXT_INDEXED = "fulltext_indexed"
    FAILED = "failed"


class Document(Base):
    """One row per unique document (paper)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    openalex_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    venue: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    primary_topic: Mapped[str] = mapped_column(String(100), index=True)
    extra_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str | None] = mapped_column(String(10))
    is_oa: Mapped[bool] = mapped_column(default=False)
    cited_by_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus), default=IndexStatus.METADATA_ONLY
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    abstract: Mapped["AbstractRecord | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    fulltext: Mapped["FullText | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Chunk.chunk_index",
    )


class AbstractRecord(Base):
    """Abstract text per document. Stored separately to keep the documents row small."""

    __tablename__ = "abstracts"
    __table_args__ = (UniqueConstraint("document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10))

    document: Mapped[Document] = relationship(back_populates="abstract")


class FullText(Base):
    """Parsed full text per document, when we successfully fetch+parse a PDF.

    Sprint-1 introduces this alongside the existing AbstractRecord. ChunkIndexer
    prefers fulltext over abstract when present (more material → better chunks).

    ``parser_name`` records WHICH parser produced this text (pymupdf / mineru /
    llamaparse / deepseek-ocr). Future re-parsing campaigns can filter by
    parser to selectively re-process docs whose text was extracted poorly.

    ``page_count`` is informational; ``source_url`` records where the PDF came
    from (typically OpenAlex's best_oa_location.pdf_url) so we can refetch
    or audit provenance.
    """

    __tablename__ = "fulltexts"
    __table_args__ = (UniqueConstraint("document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parser_name: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="fulltext")


class Chunk(Base):
    """One row per text chunk indexed in Qdrant.

    Sprint 2 introduces multi-chunk indexing: a single document is split into
    several overlapping chunks (see ``rag.chunker``) and each chunk is its own
    Qdrant point. The chunk's primary key (an int) IS the Qdrant point id —
    we don't store a separate ``qdrant_point_id`` column to avoid drift
    between two sources of truth.

    Sprint-2 source text is the abstract; Sprint-1 will introduce full-text
    chunks alongside, sharing the same table.
    """

    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_idx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")
