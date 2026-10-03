"""Index plant virus records and documents into Qdrant.

Batches embedding calls across multiple documents/records for throughput.
"""

from sqlalchemy.orm import Session

from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.rag.chunker import chunk_text
from neblab_rag.vector import QdrantRepo, VectorPoint
from plant_virus_rag.db.models import PvDocument, PvIndexStatus, PvRecord
from plant_virus_rag.db.repositories import PvChunkRepository, PvDocumentRepository, PvRecordRepository
from plant_virus_rag.logging_config import get_logger

log = get_logger(__name__)

BATCH_SIZE = 32  # match Qwen3EmbeddingProvider default


class PvChunkIndexer:
    """Indexes pv_records and pv_documents into Qdrant with batched embedding."""

    def __init__(
        self,
        session: Session,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
        *,
        chunk_size: int = 1500,
        overlap: int = 300,
    ):
        self._session = session
        self._records = PvRecordRepository(session)
        self._docs = PvDocumentRepository(session)
        self._chunks = PvChunkRepository(session)
        self._embedder = embedder
        self._qdrant = qdrant
        self._chunk_size = chunk_size
        self._overlap = overlap

    # ── batched core ───────────────────────────────────────────────

    async def _index_pending(
        self,
        items: list,
        *,
        commit_every: int | None,
        label: str,  # "record" or "doc"
    ) -> int:
        """Common batch-indexing loop for records and documents.

        ``commit_every``: durable-progress checkpoint — commit the SQLAlchemy
        session after every N successfully processed items, mirroring
        ``neblab_rag.rag.indexer.ChunkIndexer.index_pending``.  The pending
        embedding batch is upserted to Qdrant *before* each checkpoint commit,
        so Qdrant points and the DB rows that back them advance in lockstep:
        a crash can no longer leave Qdrant holding vectors whose chunk rows
        were rolled back (DB ↔ Qdrant divergence), which was the previous
        behaviour when ``--commit-every`` was passed (single commit at the
        very end).
        """
        if not items:
            log.info(f"pv_index_{label}s_done", total=0)
            return 0

        self._qdrant.ensure_collection()

        from plant_virus_rag.db.models import PvChunk as PvChunkModel

        # Collect chunk texts + metadata for the current embedding batch
        pending_texts: list[str] = []
        pending_points: list[VectorPoint] = []
        processed = 0  # items with chunks written (checkpoint counter)
        total = 0      # items flipped METADATA_ONLY -> FULLTEXT_INDEXED
        checkpoint = commit_every if (commit_every and commit_every > 0) else None

        async def _flush_pending() -> None:
            """Upsert the outstanding embedding batch to Qdrant and clear it."""
            nonlocal pending_texts, pending_points
            if pending_texts:
                await self._flush_batch(pending_texts, pending_points, len(pending_texts))
                pending_texts, pending_points = [], []

        import click as _click
        label_text = f"Indexing {label}s"
        with _click.progressbar(items, label=label_text, show_pos=True) as bar:
            for item in bar:
                if label == "doc":
                    source_text = self._source_for_doc(item)
                else:
                    source_text = item.description or item.virus_name

                texts = chunk_text(source_text, chunk_size=self._chunk_size, overlap=self._overlap)
                if not texts:
                    item.status = PvIndexStatus.FAILED
                    self._session.flush()
                    log.warning("pv_index_skip_empty", **{f"{label}_id": item.id})
                    continue

                # Query old chunk IDs before replace (so we can delete stale Qdrant points)
                if label == "doc":
                    old_chunks = self._session.query(PvChunkModel.id).where(
                        PvChunkModel.document_id == item.id
                    ).all()
                    old_ids = [c[0] for c in old_chunks]
                    new_rows = self._chunks.replace_for_document(item.id, item.source_type, texts)
                else:
                    old_chunks = self._session.query(PvChunkModel.id).where(
                        PvChunkModel.record_id == item.id
                    ).all()
                    old_ids = [c[0] for c in old_chunks]
                    new_rows = self._chunks.replace_for_record(item.id, item.source_type, texts)
                # Delete stale Qdrant points
                if old_ids:
                    self._qdrant.delete_points(old_ids)

                for row in new_rows:
                    pending_texts.append(row.text)
                    payload = (
                        self._document_payload(item, row.id, row.chunk_index, row.text)
                        if label == "doc"
                        else self._record_payload(item, row.id, row.chunk_index, row.text)
                    )
                    pending_points.append(VectorPoint(id=row.id, vector=[], payload=payload))

                # Flush embedding batch when full
                while len(pending_texts) >= BATCH_SIZE:
                    await self._flush_batch(pending_texts, pending_points, BATCH_SIZE)
                    pending_texts = pending_texts[BATCH_SIZE:]
                    pending_points = pending_points[BATCH_SIZE:]

                if item.status == PvIndexStatus.METADATA_ONLY:
                    item.status = PvIndexStatus.FULLTEXT_INDEXED
                    total += 1
                processed += 1

                # Checkpoint: flush Qdrant first, then commit the DB session so
                # both stores carry the same progress.
                if checkpoint is not None and processed % checkpoint == 0:
                    await _flush_pending()
                    self._session.commit()
                    log.info("pv_index_commit_checkpoint", **{f"{label}s_committed": processed})

            # Flush remaining batch + commit final statuses
            await _flush_pending()
            self._session.flush()
            if checkpoint is not None:
                self._session.commit()
                log.info("pv_index_commit_checkpoint", **{f"{label}s_committed": processed})

        log.info(f"pv_index_{label}s_done", total=total)
        return total

    async def _flush_batch(self, texts: list[str], points: list[VectorPoint], n: int) -> None:
        batch_texts = texts[:n]
        batch_points = points[:n]
        vectors = await self._embedder.embed(batch_texts)
        for pt, vec in zip(batch_points, vectors):
            pt.vector = vec
        self._qdrant.upsert_points(batch_points)

    @staticmethod
    def _source_for_doc(doc: PvDocument) -> str:
        if doc.fulltext and doc.fulltext.text.strip():
            return doc.fulltext.text
        if doc.abstract:
            return doc.abstract.text
        return doc.title

    # ── public API ─────────────────────────────────────────────────

    async def index_pending_records(self, *, commit_every: int | None = None) -> int:
        pending = list(self._records.list_with_status(PvIndexStatus.METADATA_ONLY))
        return await self._index_pending(pending, commit_every=commit_every, label="record")

    async def index_pending_documents(self, *, commit_every: int | None = None) -> int:
        pending = list(self._docs.list_with_status(PvIndexStatus.METADATA_ONLY))
        return await self._index_pending(pending, commit_every=commit_every, label="doc")

    async def index_all(self, *, commit_every: int | None = None) -> tuple[int, int]:
        n_records = await self.index_pending_records(commit_every=commit_every)
        n_docs = await self.index_pending_documents(commit_every=commit_every)
        return n_records, n_docs

    # ── payload builders ──────────────────────────────────────────

    @staticmethod
    def _record_payload(record: PvRecord, chunk_row_id: int, chunk_index: int, text: str) -> dict:
        return {
            "chunk_id": chunk_row_id,
            "record_id": record.id,
            "chunk_index": chunk_index,
            "source_type": str(record.source_type),
            "virus_name": record.virus_name,
            "host_species": record.host_species,
            "genome_type": record.genome_type,
            "symptoms": record.symptoms,
            "taxonomy": record.taxonomy,
            "text": text,
        }

    @staticmethod
    def _document_payload(doc: PvDocument, chunk_row_id: int, chunk_index: int, text: str) -> dict:
        return {
            "chunk_id": chunk_row_id,
            "doc_id": doc.id,
            "chunk_index": chunk_index,
            "source_type": str(doc.source_type),
            "title": doc.title,
            "authors": doc.authors,
            "venue": doc.venue,
            "year": doc.year,
            "doi": doc.doi,
            "virus_names": doc.virus_names,
            "text": text,
            "language": doc.language,
        }
