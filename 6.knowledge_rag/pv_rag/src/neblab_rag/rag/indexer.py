"""Index document chunks into Qdrant.

Sprint-2 indexer: each document is split into N chunks (see rag.chunker),
each chunk is its own Postgres row + Qdrant point. The chunk's int PK
is used as the Qdrant point id directly.

Per-doc atomicity: chunk → persist → embed → upsert → mark indexed all
inside one document's iteration. If embedding fails halfway through the
batch, the doc that crashed stays at METADATA_ONLY and operator can
re-run; already-indexed docs aren't touched.

Source text is the abstract (Sprint-2 corpus). Sprint-1 will introduce
full-text alongside, sharing this same indexer pipeline by passing the
parsed full text instead of the abstract.
"""

from sqlalchemy.orm import Session

from neblab_rag.db.models import IndexStatus
from neblab_rag.db.repositories import ChunkRepository, DocumentRepository
from neblab_rag.logging_config import get_logger
from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.rag.chunker import chunk_text
from neblab_rag.vector import QdrantRepo, VectorPoint

log = get_logger(__name__)


class ChunkIndexer:
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
        self._docs = DocumentRepository(session)
        self._chunks = ChunkRepository(session)
        self._embedder = embedder
        self._qdrant = qdrant
        self._chunk_size = chunk_size
        self._overlap = overlap

    async def index_pending(self, *, commit_every: int | None = None) -> int:
        """Index every doc in METADATA_ONLY state. Returns docs processed.

        ``commit_every``: if set, commit the SQLAlchemy session after every N
        successfully indexed docs so that long-running reindex jobs don't lose
        all progress when a transient Qdrant SSL/timeout error rolls back the
        single enclosing transaction. None (default) preserves the original
        single-transaction behavior used by tests + API path.
        """
        self._qdrant.ensure_collection()
        pending = list(self._docs.list_documents_with_status(IndexStatus.METADATA_ONLY))

        total = 0
        for doc in pending:
            # Sprint 1: prefer fulltext over abstract when we successfully
            # fetched + parsed a PDF. Falls back to abstract, then title.
            if doc.fulltext and doc.fulltext.text.strip():
                source_text = doc.fulltext.text
            elif doc.abstract:
                source_text = doc.abstract.text
            else:
                source_text = doc.title
            chunks_text = chunk_text(
                source_text, chunk_size=self._chunk_size, overlap=self._overlap
            )
            chunk_rows = self._chunks.replace_for_document(doc.id, chunks_text)

            if not chunk_rows:
                # Doc has no usable text — mark failed so we don't keep retrying
                doc.status = IndexStatus.FAILED
                self._session.flush()
                log.warning("index_skip_empty", doc_id=doc.id)
                continue

            vectors = await self._embedder.embed([row.text for row in chunk_rows])

            points = [
                VectorPoint(
                    id=row.id,
                    vector=vec,
                    payload={
                        "chunk_id": row.id,
                        "doc_id": doc.id,
                        "chunk_index": row.chunk_index,
                        "openalex_id": doc.openalex_id,
                        "title": doc.title,
                        "text": row.text,
                        "year": doc.year,
                        "topic": doc.primary_topic,
                        "language": doc.language,
                    },
                )
                for row, vec in zip(chunk_rows, vectors, strict=True)
            ]
            self._qdrant.upsert_points(points)

            doc.status = IndexStatus.FULLTEXT_INDEXED
            self._session.flush()
            total += 1
            log.info("index_doc_done", doc_id=doc.id, chunks=len(chunk_rows))

            if commit_every is not None and total % commit_every == 0:
                self._session.commit()
                log.info("index_commit_checkpoint", docs_committed=total)

        log.info("index_pending_done", total_docs=total)
        return total
