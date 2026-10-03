"""Reindex every METADATA_ONLY doc in Postgres into Qdrant.

Long-running on a fresh corpus (1000+ docs × ~3s each). Two reliability
mechanisms:

* ``commit_every=10`` inside ChunkIndexer flushes durable progress every
  ten docs so a transient Qdrant Cloud SSL blip rolls back at most ten
  docs of work, not the entire run.
* A retry loop here re-opens a fresh session after any exception and
  resumes — the next call picks up only docs still at METADATA_ONLY,
  so already-indexed work isn't redone.
"""

import asyncio
import sys

from neblab_rag.db.engine import get_session
from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from neblab_rag.rag.indexer import ChunkIndexer

MAX_RETRIES = 30
BACKOFF_SECONDS = 30


async def _index_once() -> int:
    embedder = build_embedding_provider()
    qdrant = build_qdrant_repo()
    with get_session() as session:
        indexer = ChunkIndexer(session=session, embedder=embedder, qdrant=qdrant)
        return await indexer.index_pending(commit_every=10)


async def main() -> None:
    grand_total = 0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            n = await _index_once()
            grand_total += n
            print(f"attempt {attempt}: indexed {n} docs (running total {grand_total})")
            if n == 0:
                break
            # n>0 means we got through the entire pending list; loop again only
            # in the rare case more docs got ingested concurrently.
            break
        except Exception as exc:
            print(f"attempt {attempt} failed: {exc!r}", file=sys.stderr)
            if attempt == MAX_RETRIES:
                raise
            await asyncio.sleep(BACKOFF_SECONDS)
            print(f"retrying after {BACKOFF_SECONDS}s ...", file=sys.stderr)
    print(f"indexed_docs={grand_total}")


if __name__ == "__main__":
    asyncio.run(main())
