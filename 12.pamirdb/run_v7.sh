#!/bin/bash
# ============================================================
# PAmiRDB v7 — 宿主过滤管线，自动运行 + 错误恢复
# ============================================================
set -e

WORKERS=60
LOG_DIR=/tmp/pamirdb_logs
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/v7_$(date +%Y%m%d_%H%M).log"
# `cmd 2>&1 | tee` in exec position does NOT work (exec cannot pipe a command);
# this bash process-substitution form redirects both stdout and stderr to tee.
exec > >(tee "$LOG") 2>&1

echo "============================================================"
echo "  PAmiRDB v7 Host-Filtered Pipeline"
echo "  Workers: $WORKERS"
echo "  Log: $LOG"
echo "  Started: $(date)"
echo "============================================================"

# ── 检查 Python ──
PYTHON=$(which python3.8 2>/dev/null || which python3 2>/dev/null || which python 2>/dev/null)
echo "Python: $PYTHON ($($PYTHON --version))"

# ── Step 0: 检查源数据文件 ──
echo ""
echo "[Step 0] Checking source data files..."

PROJ_DIR=$(dirname $(readlink -f "$0" 2>/dev/null || echo "$0"))
PROJ_DIR=$(cd "$(dirname "$0")" && pwd)
echo "Project dir: $PROJ_DIR"

check_file() {
    if [ -f "$1" ]; then
        echo "  [OK] $1"
    else
        echo "  [MISSING] $1"
        return 1
    fi
}

# 必要的源数据文件
REQUIRED_FILES=(
    "$PROJ_DIR/../11.antiviral_genes/data/plantrg_mirna_targets.json"
    "$PROJ_DIR/../11.antiviral_genes/data/plantrg_all_mirna.fa"
    "$PROJ_DIR/../11.antiviral_genes/data/miRBase_plant_mature.fa"
    "$PROJ_DIR/../11.antiviral_genes/data/miRNA_precursors.fasta"
    "$PROJ_DIR/../docs/data/Plant_Virus.complete_ref_info.tsv"
    "$PROJ_DIR/../docs/data/Plant_Virus.complete_ref.fasta"
)

ALL_OK=true
for f in "${REQUIRED_FILES[@]}"; do
    if ! check_file "$f"; then
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    echo ""
    echo "ERROR: Missing source data files. Please ensure:"
    echo "  - 11.antiviral_genes/data/ has miRNA source files"
    echo "  - docs/data/ has Plant_Virus.complete_ref.* files"
    exit 1
fi

# ── Step 1: 生成全量数据 ──
echo ""
echo "[Step 1] Generating full data files..."

DATA_MIRNA="$PROJ_DIR/data/mirna/plant_mirnas_full.json"
DATA_VIRUS_JSON="$PROJ_DIR/data/virus_genomes/viruses_full.json"
DATA_VIRUS_FASTA="$PROJ_DIR/data/virus_genomes/viruses_full.fasta"

if [ -f "$DATA_MIRNA" ] && [ -f "$DATA_VIRUS_JSON" ] && [ -f "$DATA_VIRUS_FASTA" ]; then
    echo "  Full data files already exist, skipping generation."
    echo "  miRNA: $($PYTHON -c "import json;print(len(json.load(open('$DATA_MIRNA'))))" 2>/dev/null || echo '?')"
    echo "  Virus: $($PYTHON -c "import json;print(len(json.load(open('$DATA_VIRUS_JSON'))))" 2>/dev/null || echo '?')"
else
    echo "  Generating full data files..."
    cd "$PROJ_DIR"
    $PYTHON -u scripts/generate_full_data.py || {
        echo "ERROR: Data generation failed!"
        exit 1
    }
fi

# ── Step 2: 检查 v7 管线脚本 ──
echo ""
echo "[Step 2] Verifying pipeline script..."
check_file "$PROJ_DIR/scripts/pipeline_v7_host_filtered.py" || {
    echo "ERROR: pipeline_v7_host_filtered.py not found!"
    exit 1
}

# ── Step 3: 先 dry-run 确认配对数量 ──
echo ""
echo "[Step 3] Dry-run: counting host-filtered pairs..."
cd "$PROJ_DIR"
PAIR_INFO=$($PYTHON scripts/pipeline_v7_host_filtered.py --pairs-only 2>&1)
echo "$PAIR_INFO"

PAIR_COUNT=$(echo "$PAIR_INFO" | grep "Total miRNA-virus pairs" | grep -oP '[\d,]+' | tr -d ',')
if [ -z "$PAIR_COUNT" ] || [ "$PAIR_COUNT" -eq 0 ]; then
    echo "ERROR: No pairs to process! Check host matching."
    exit 1
fi
echo "  Pairs to process: $PAIR_COUNT"

# ── Step 4: 运行管线 (带重试) ──
echo ""
echo "[Step 4] Running host-filtered pipeline..."
echo "  Workers: $WORKERS"
echo "  Started at: $(date)"

MAX_RETRIES=2
RETRY=0
EXIT_CODE=0

while [ $RETRY -le $MAX_RETRIES ]; do
    if [ $RETRY -gt 0 ]; then
        echo ""
        echo "  === RETRY $RETRY/$MAX_RETRIES ==="
        sleep 5
    fi

    cd "$PROJ_DIR"
    # `if ...; then` form: `set -e` aborts the script on a bare failing command,
    # which made this entire retry/recovery block dead code. Commands in an `if`
    # condition are exempt from set -e, so errors now fall through to recovery.
    if $PYTHON -u scripts/pipeline_v7_host_filtered.py --workers $WORKERS; then
        echo ""
        echo "  Pipeline completed successfully!"
        break
    else
        EXIT_CODE=$?
        echo ""
        echo "  Pipeline exited with code $EXIT_CODE"
        RETRY=$((RETRY + 1))

        if [ $RETRY -le $MAX_RETRIES ]; then
            echo "  Checking for common issues..."

            # 检查是否是内存不足
            FREE_MEM=$(free -m 2>/dev/null | awk '/Mem:/ {print $4}' || echo "unknown")
            echo "  Free memory: ${FREE_MEM}MB"

            # 如果内存不足，降低线程数
            if [ "$FREE_MEM" != "unknown" ] && [ "$FREE_MEM" -lt 1024 ]; then
                OLD_WORKERS=$WORKERS
                WORKERS=$((WORKERS / 2))
                [ $WORKERS -lt 4 ] && WORKERS=4
                echo "  Low memory! Reducing workers: $OLD_WORKERS -> $WORKERS"
            fi

            # 清理可能损坏的中间文件 (pipeline writes atomically via *.tmp + rename,
            # so a crashed run may leave predictions_v7.json.tmp behind)
            rm -f "$PROJ_DIR/data/predictions_v7.json.tmp" 2>/dev/null
        fi
    fi
done

# ── Step 5: 结果验证 ──
echo ""
echo "[Step 5] Validating results..."

RESULT_FILE="$PROJ_DIR/data/predictions_v7.json"
if [ -f "$RESULT_FILE" ]; then
    RESULT_SIZE=$(stat -c%s "$RESULT_FILE" 2>/dev/null || stat -f%z "$RESULT_FILE" 2>/dev/null || echo 0)
    PRED_COUNT=$($PYTHON -c "import json;d=json.load(open('$RESULT_FILE'));print(d.get('total_predictions',0))" 2>/dev/null || echo 0)

    echo "  Result file: $RESULT_FILE"
    echo "  File size: $RESULT_SIZE bytes"
    echo "  Predictions: $PRED_COUNT"

    if [ "$PRED_COUNT" -gt 0 ] && [ "$RESULT_SIZE" -gt 100 ]; then
        echo "  [OK] Results valid!"
    else
        echo "  [WARN] Results seem empty or invalid"
    fi
else
    echo "  [WARN] No result file found!"
fi

# ── 完成 ──
echo ""
echo "============================================================"
echo "  Pipeline Finished"
echo "  Ended: $(date)"
echo "  Log: $LOG"
echo "  Result: $PROJ_DIR/data/predictions_v7.json"
echo "============================================================"
