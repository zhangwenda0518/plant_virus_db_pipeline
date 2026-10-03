#!/usr/bin/env bash
# Ingest 2 priority topics × en/zh × 500 abstracts, then reindex.
# Idempotent: re-running skips already-ingested OpenAlex IDs.
set -euo pipefail
export PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH"

echo "=== ingest desertification en"
neblab-ingest ingest --topic desertification --language en --max 500
echo "=== ingest desertification zh"
neblab-ingest ingest --topic desertification --language zh --max 500
echo "=== ingest shelterbelt en"
neblab-ingest ingest --topic shelterbelt --language en --max 500
echo "=== ingest shelterbelt zh"
neblab-ingest ingest --topic shelterbelt --language zh --max 500

echo "=== reindex all METADATA_ONLY docs"
python scripts/reindex_all.py

echo "=== done"
