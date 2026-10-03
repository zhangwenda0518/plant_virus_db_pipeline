#!/usr/bin/env bash
# End-to-end smoke test for Plant Virus RAG pipeline.
#
# Prerequisites:
#   - mamba activate NEBLab
#   - Postgres 16 running (make pg-start)
#   - .env.local with valid API keys + Qdrant Cloud creds
#
# Usage: bash scripts/pv_smoke_run.sh

set -euo pipefail

echo "=== PV Smoke: Migrate ==="
alembic -c alembic_pv/alembic.ini upgrade head

echo ""
echo "=== PV Smoke: Ingest OpenAlex (EN, 20 papers) ==="
pv-ingest openalex --topic plant_virus --language en --max 20

echo ""
echo "=== PV Smoke: Index pending ==="
pv-ingest index --commit-every 5

echo ""
echo "=== PV Smoke: BM25 rebuild ==="
pv-ingest bm25-rebuild

echo ""
echo "=== PV Smoke: Health check ==="
# Start API in background on port 8001
uvicorn plant_virus_rag.api.main:create_pv_app --factory --port 8001 &
API_PID=$!
sleep 3

curl --noproxy '*' -s http://localhost:8001/health | python -m json.tool

echo ""
echo "=== PV Smoke: Query (EN) ==="
curl --noproxy '*' -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main symptoms of Tomato spotted wilt virus?", "top_k": 5}' \
  | python -m json.tool

echo ""
echo "=== PV Smoke: Query (ZH) ==="
curl --noproxy '*' -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "番茄斑萎病毒的主要症状是什么？", "top_k": 5}' \
  | python -m json.tool

echo ""
echo "=== PV Smoke: Stop API ==="
kill $API_PID 2>/dev/null || true

echo ""
echo "=== PV Smoke: Done! ==="
