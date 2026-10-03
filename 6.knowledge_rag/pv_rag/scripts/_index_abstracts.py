"""Index paper abstracts into Qdrant — chunk, embed, upsert, verify.

Usage:
  python -u scripts/_index_abstracts.py          # test: 100 papers
  python -u scripts/_index_abstracts.py --full   # full: all papers 2020+
"""

from __future__ import annotations

import asyncio
import sys
import time

from sqlalchemy import select

from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from neblab_rag.rag.chunker import chunk_text
from neblab_rag.vector import VectorPoint
from plant_virus_rag.config import get_composite_settings
from plant_virus_rag.db.engine import get_pv_session
from plant_virus_rag.db.models import PvAbstract, PvChunk, PvDocument

BATCH_SIZE = 32
CHUNK_SIZE = 1000
OVERLAP = 200
DOCS_PER_FLUSH = 100  # flush DB + commit every N docs


async def index_abstracts(year_from: int, limit: int | None = None):
    settings = get_composite_settings()
    embedder = build_embedding_provider()
    qdrant = build_qdrant_repo(collection=settings.qdrant_collection)
    qdrant.ensure_collection()

    with get_pv_session() as session:
        stmt = (
            select(
                PvDocument.id, PvDocument.title, PvDocument.openalex_id,
                PvDocument.year, PvDocument.language,
                PvAbstract.text
            )
            .join(PvAbstract, PvAbstract.document_id == PvDocument.id)
            .where(PvDocument.year >= year_from)
            .order_by(PvDocument.year.desc(), PvDocument.id)
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = list(session.execute(stmt).fetchall())
    total_docs = len(rows)
    print(f"Selected {total_docs} papers with abstracts (year>={year_from})")

    pending_texts: list[str] = []
    pending_points: list[VectorPoint] = []
    total_chunks = 0
    processed = 0
    t0 = time.time()
    embed_tokens = 0

    with get_pv_session() as s2:
        for idx, row in enumerate(rows):
            doc_id, title, oa_id, year, lang, abs_text = row
            source_text = abs_text if abs_text and abs_text.strip() else (title or "")
            chunk_objs = chunk_text(source_text, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
            texts = [c.text for c in chunk_objs]
            if not texts:
                continue

            # Delete old chunks
            old_ids = [r[0] for r in s2.execute(
                select(PvChunk.id).where(PvChunk.document_id == doc_id)
            ).fetchall()]
            if old_ids:
                qdrant.delete_points(old_ids)
            s2.query(PvChunk).filter(PvChunk.document_id == doc_id).delete()

            for ci, t in enumerate(texts):
                c = PvChunk(
                    source_type="openalex", document_id=doc_id,
                    chunk_index=ci, text=t, start_offset=0, end_offset=len(t)
                )
                s2.add(c)
                s2.flush()
                pending_texts.append(t)
                pending_points.append(VectorPoint(
                    id=c.id, vector=[],
                    payload={
                        "chunk_id": c.id, "doc_id": doc_id,
                        "openalex_id": oa_id, "title": title, "text": t,
                        "year": year, "language": lang, "source_type": "openalex",
                        "chunk_index": ci,
                    }
                ))

            total_chunks += len(texts)
            processed += 1

            if processed % DOCS_PER_FLUSH == 0:
                s2.commit()

            # Flush embedding batch
            while len(pending_texts) >= BATCH_SIZE:
                batch_t = pending_texts[:BATCH_SIZE]
                batch_p = pending_points[:BATCH_SIZE]
                vecs = await embedder.embed(batch_t)
                embed_tokens += sum(len(t) for t in batch_t)
                for pt, v in zip(batch_p, vecs):
                    pt.vector = v
                qdrant.upsert_points(batch_p)
                pending_texts = pending_texts[BATCH_SIZE:]
                pending_points = pending_points[BATCH_SIZE:]

            if processed % 500 == 0 or processed == total_docs:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total_docs - processed) / rate / 60 if rate > 0 else 0
                pct = processed / total_docs * 100
                print(f"  [{processed:>6}/{total_docs} {pct:5.1f}%] "
                      f"chunks={total_chunks} rate={rate:.1f} docs/s "
                      f"eta={eta:.0f}min  embed_kchars={embed_tokens//1000}")

        s2.commit()

    # Final flush
    if pending_texts:
        vecs = await embedder.embed(pending_texts)
        for pt, v in zip(pending_points, vecs):
            pt.vector = v
        qdrant.upsert_points(pending_points)

    elapsed = time.time() - t0
    print(f"\nDone: {processed} papers → {total_chunks} chunks in {elapsed/60:.1f}min")

    # Verify
    vecs = await embedder.embed(["plant virus resistance mechanism"])
    hits = qdrant.search(vecs[0], top_k=3)
    print("Top hits:")
    for h in hits:
        print(f"  score={h.score:.4f} doc_id={h.payload.get('doc_id')} {h.payload.get('text','')[:80]}")
    return processed, total_chunks


async def main():
    if "--full" in sys.argv:
        await index_abstracts(year_from=2020)
    else:
        print("=== TEST: 100 papers ===")
        await index_abstracts(year_from=2025, limit=100)
        print("\nReady. Use --full for all 55K papers 2020+.")


if __name__ == "__main__":
    asyncio.run(main())
