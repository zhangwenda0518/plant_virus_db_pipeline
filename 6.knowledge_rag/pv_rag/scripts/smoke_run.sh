#!/usr/bin/env bash
# End-to-end smoke test for the Sprint-0 RAG slice.
#
# Pre-requisites (operator-managed, this script does not provision them):
#   - mamba env "NEBLab" is active (so neblab-ingest / pytest / alembic on PATH)
#   - .env.local fully populated (DeepSeek + Qwen3 + Qdrant Cloud + OPENALEX_EMAIL)
#   - Qdrant Cloud cluster reachable from this machine
#
# Path:  fresh DB → migrate → ingest → embed+upsert → boot API → POST /query
#
# Run from repo root:  bash scripts/smoke_run.sh

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> [1/6] Ensuring Postgres@16 is running"
brew services list | grep -q "postgresql@16.*started" || brew services start postgresql@16
sleep 2

echo "==> [2/6] alembic upgrade head"
make migrate

echo "==> [3/6] Ingesting up to 50 desertification (en) docs from OpenAlex"
neblab-ingest ingest --topic desertification --language en --max 50

echo "==> [4/6] Chunking + embedding pending docs and upserting to Qdrant"
python <<'PY'
import asyncio

from neblab_rag.db.engine import get_session
from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from neblab_rag.rag.indexer import ChunkIndexer


async def main() -> None:
    with get_session() as session:
        indexer = ChunkIndexer(
            session=session,
            embedder=build_embedding_provider(),
            qdrant=build_qdrant_repo(),
        )
        n = await indexer.index_pending()
        print(f"Indexed {n} documents (each split into N chunks)")


asyncio.run(main())
PY

echo "==> [5/6] Booting API on :8000 (background)"
uvicorn neblab_rag.api.main:create_app --factory --port 8000 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

# Poll /health instead of fixed sleep so we don't race uvicorn boot
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "==> [6/6] POST /query"
curl -sf -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"What are the main mechanisms of desertification in northern China?"}' \
  | python -m json.tool

echo "==> SUCCESS"
