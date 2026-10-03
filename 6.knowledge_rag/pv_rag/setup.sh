#!/usr/bin/env bash
# pv_rag 一键搭建脚本
# 用法: bash setup.sh
# 前置: 已安装 Python 3.10+, PostgreSQL 16, Qdrant 二进制
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "================================================"
echo "  Plant Virus RAG 一键搭建"
echo "================================================"
echo "项目目录: $PROJECT_DIR"
echo

# ─── Step 1: 检查依赖 ───────────────────────────────
echo "[1/8] 检查依赖..."
command -v python >/dev/null 2>&1 || { echo "ERROR: Python 未安装"; exit 1; }
command -v psql >/dev/null 2>&1 || { echo "ERROR: PostgreSQL 未安装或未加入 PATH"; exit 1; }
echo "  Python: $(python --version)"
echo "  PostgreSQL: $(psql --version)"
echo

# ─── Step 2: 创建 .env.local ───────────────────────
echo "[2/8] 配置 .env.local..."
if [ ! -f .env.local ]; then
    cp config/.env.example .env.local
    echo "  已创建 .env.local (从 config/.env.example 复制)"
    echo "  ⚠️  请编辑 .env.local 填入真实 API key:"
    echo "     - LLM_API_KEY (DeepSeek)"
    echo "     - EMBEDDING_API_KEY (SiliconFlow)"
    echo "     - RERANKER_API_KEY (SiliconFlow)"
    echo "     - OPENALEX_EMAIL"
    echo "  填完后重新运行此脚本。"
    exit 0
else
    echo "  .env.local 已存在,跳过"
fi
echo

# ─── Step 3: 安装 Python 包 ────────────────────────
echo "[3/8] 安装 Python 依赖..."
pip install -e ".[dev]" -q 2>&1 | tail -3
echo "  依赖安装完成"
echo

# ─── Step 4: 启动 Qdrant ───────────────────────────
echo "[4/8] 启动 Qdrant..."
if curl -s http://localhost:6333/healthz >/dev/null 2>&1; then
    echo "  Qdrant 已在运行"
else
    QDRANT_BIN="${QDRANT_BIN:-E:/BandZip解压/qdrant-x86_64-pc-windows-msvc/qdrant.exe}"
    if [ -f "$QDRANT_BIN" ]; then
        "$QDRANT_BIN" --disable-telemetry > qdrant.log 2>&1 &
        sleep 4
        if curl -s http://localhost:6333/healthz >/dev/null 2>&1; then
            echo "  Qdrant 启动成功 (PID=$!)"
        else
            echo "  ERROR: Qdrant 启动失败,查看 qdrant.log"
            exit 1
        fi
    else
        echo "  ⚠️  Qdrant 二进制未找到: $QDRANT_BIN"
        echo "     请设置 QDRANT_BIN 环境变量或手动启动 Qdrant"
        echo "     下载: https://github.com/qdrant/qdrant/releases"
        exit 1
    fi
fi
echo

# ─── Step 5: 创建 Postgres 数据库 ──────────────────
echo "[5/8] 创建 Postgres 数据库..."
PGUSER="${PGUSER:-neblab}"
PGPASSWORD="${PGPASSWORD:-neblab}"
if psql -U "$PGUSER" -h localhost -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw neblab; then
    echo "  数据库 neblab 已存在"
else
    createdb -U "$PGUSER" -h localhost neblab 2>/dev/null && echo "  数据库 neblab 创建成功" || {
        echo "  ⚠️  无法创建数据库,请手动执行:"
        echo "     createdb -U neblab neblab"
    }
fi
echo

# ─── Step 6: 运行数据库迁移 ────────────────────────
echo "[6/8] 运行数据库迁移..."
alembic -c alembic_pv/alembic.ini upgrade head 2>&1 | tail -3
echo "  迁移完成"
echo

# ─── Step 7: 摄入结构化数据 ────────────────────────
echo "[7/8] 摄入结构化数据 (ICTV/ViralZone/NCBI/plant_insect)..."
pv-ingest structured --source ictv --dir rag-db/ICTV_RAG_Database/docs 2>&1 | tail -1
pv-ingest structured --source viralzone --dir rag-db/viralzone_rag_db/md 2>&1 | tail -1
pv-ingest structured --source ncbi --file rag-db/final.cluster.ref_info.tsv 2>&1 | tail -1
python scripts/_ingest_plant_insect.py 2>&1 | tail -1
echo "  结构化数据摄入完成"
echo

# ─── Step 8: 索引 + BM25S ──────────────────────────
echo "[8/8] 索引 chunks + 重建 BM25S..."
echo "  (这一步耗时较长,取决于已有论文数量)"
pv-ingest index --no-documents --commit-every 100 2>&1 | tail -1
pv-ingest bm25-rebuild 2>&1 | tail -1
echo

echo "================================================"
echo "  ✅ 搭建完成!"
echo "================================================"
echo
echo "验证:"
echo "  pv-ingest stats                          # 数据库统计"
echo "  curl http://localhost:6333/collections   # Qdrant 状态"
echo "  python -m plant_virus_rag.eval --questions evals/questions.json --label test --judge --no-rewriter"
echo
echo "启动 API:"
echo "  uvicorn plant_virus_rag.api.main:create_pv_app --factory --port 8001"
echo
echo "查询演示:"
echo "  python scripts/demo_queries.py"
