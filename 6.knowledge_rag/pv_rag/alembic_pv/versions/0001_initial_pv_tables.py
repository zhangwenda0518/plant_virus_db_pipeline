"""initial: pv_records, pv_documents, pv_abstracts, pv_fulltexts, pv_chunks

Revision ID: 0001
Revises:
Create Date: 2026-05-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pv_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(20), nullable=False, index=True),
        sa.Column("source_id", sa.String(100), nullable=True),
        sa.Column("virus_name", sa.String(300), nullable=False, index=True),
        sa.Column("virus_abbreviation", sa.String(100), nullable=True),
        sa.Column("taxonomy", sa.JSON(), nullable=True),
        sa.Column("host_species", sa.JSON(), nullable=True),
        sa.Column("host_family", sa.String(100), nullable=True),
        sa.Column("vector", sa.String(200), nullable=True),
        sa.Column("symptoms", sa.JSON(), nullable=True),
        sa.Column("transmission", sa.String(300), nullable=True),
        sa.Column("genome_type", sa.String(50), nullable=True),
        sa.Column("genome_size_kb", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="metadata_only"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "pv_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="openalex", index=True),
        sa.Column("openalex_id", sa.String(50), unique=True, nullable=True),
        sa.Column("pubmed_id", sa.String(50), unique=True, nullable=True),
        sa.Column("doi", sa.String(200), unique=True, nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.JSON(), server_default="[]"),
        sa.Column("venue", sa.String(500), nullable=True),
        sa.Column("year", sa.Integer(), index=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("is_oa", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("cited_by_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("virus_names", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="metadata_only"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "pv_abstracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("pv_documents.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        sa.UniqueConstraint("document_id"),
    )

    op.create_table(
        "pv_fulltexts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("pv_documents.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parser_name", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id"),
    )

    op.create_table(
        "pv_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(20), nullable=False, index=True),
        sa.Column(
            "record_id",
            sa.Integer(),
            sa.ForeignKey("pv_records.id", ondelete="CASCADE"),
            index=True,
            nullable=True,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("pv_documents.id", ondelete="CASCADE"),
            index=True,
            nullable=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("record_id", "chunk_index", name="uq_pv_chunks_record_idx"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_pv_chunks_doc_idx"),
    )


def downgrade() -> None:
    op.drop_table("pv_chunks")
    op.drop_table("pv_fulltexts")
    op.drop_table("pv_abstracts")
    op.drop_table("pv_documents")
    op.drop_table("pv_records")
