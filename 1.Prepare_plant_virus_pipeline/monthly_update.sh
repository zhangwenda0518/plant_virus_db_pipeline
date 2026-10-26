#!/bin/bash
# PlantVirusDB Monthly Update Runner（合并版：路径自动推导 + 完整 7 阶段）
# 用法: bash monthly_update.sh [YYYY-MM-DD]  (默认: 自动从上次同步日期开始)
# Cron: 0 3 1 * * bash /opt/plant_virus_db/plant_virus_db_pipeline/1.Prepare_plant_virus_pipeline/monthly_update.sh >> /var/log/monthly_update.log 2>&1

set -e

# 路径全部由脚本自身位置推导（不硬编码部署位置）：
#   REPO=<仓库根>；PVDB_PIPELINE_DIR / PVDB_DATA / PVDB_LOG / PVDB_BLAST_DB /
#   PVDB_MAKEBLASTDB / PVDB_METABULI_REBUILD / PVDB_PAMIRDB_DIR / PVDB_PAMIRDB_LOG 可覆盖
REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
DIR="${PVDB_PIPELINE_DIR:-$REPO/1.Prepare_plant_virus_pipeline}"
DATA="${PVDB_DATA:-$REPO/docs/data}"
LOG="${PVDB_LOG:-$DIR/archive/incremental_update.log}"
mkdir -p "$(dirname "$LOG")"

# 确定更新范围
if [ -n "$1" ]; then
    SINCE="$1"
else
    SINCE=$(python3.8 -c "
import json, os
s = json.load(open('$DATA/incremental_status.json'))
print(s.get('last_sync_date', '2026-07-29'))
" 2>/dev/null || echo "2026-07-29")
fi

UNTIL=$(date +%Y-%m-%d)
LABEL="$(date +%Y年%m月)"

echo "==== $(date) Monthly Update: $SINCE -> $UNTIL ====" | tee -a "$LOG"

# Phase 1-3: 增量获取 + 宿主判定 + 数据库合并 (含QC过滤)
cd "$DIR"
python3.8 U1_incremental_update.py \
    --since "$SINCE" --until "$UNTIL" \
    --chunk-months 1 2>&1 | tee -a "$LOG"

# Phase 4: 合并到 Ref 参考集
echo "==== $(date) Merging to Ref ====" | tee -a "$LOG"
python3.8 "$DIR/merge_to_ref.py" 2>&1 | tee -a "$LOG"

# 更新状态 (保留最近7个月)
python3.8 -c "
import json
s = json.load(open('$DATA/incremental_status.json'))
s['last_sync_date'] = '$UNTIL'
s['updated_at'] = '$(date -Iseconds)'
# Keep only last 7 months
if len(s.get('months',[])) > 7:
    s['months'] = s['months'][-7:]
json.dump(s, open('$DATA/incremental_status.json', 'w'), ensure_ascii=False, indent=2)
print('Status updated, months:', len(s.get('months',[])))
"

# Phase 4.5: VMR 定向补收（基线内"ICTV 有名、NCBI 宿主谱系漏标"的种，幂等秒退）
echo "==== $(date) VMR directed collection (V1) ====" | tee -a "$LOG"
(cd "$DIR" && python3.8 V1_vmr_directed_collect.py --vmr "$DATA/VMR_MSL41.txt" >> "$LOG" 2>&1)     && echo "V1 collection done" | tee -a "$LOG"     || echo "WARNING: V1 collection failed (non-fatal)" | tee -a "$LOG"

# Phase 4.6: 重建 dashboard 统计（站点 /reference/ KPI 随月更刷新；失败不中断管线）
echo "==== $(date) Regenerating dashboard stats ====" | tee -a "$LOG"
(cd "$DATA" && python3.8 generate_dashboard_stats.py >> "$LOG" 2>&1) \
    && echo "dashboard_stats.json regenerated" | tee -a "$LOG" \
    || echo "WARNING: dashboard stats regeneration failed (non-fatal)" | tee -a "$LOG"

# Phase 5: 重建下游 BLAST 库（保持 /metabuli/ DB BLAST 与 Ref 同步）
if [ -n "${PVDB_MAKEBLASTDB:-}" ]; then
    MAKEBLASTDB="$PVDB_MAKEBLASTDB"
elif [ -x /opt/miniconda3/bin/makeblastdb ]; then
    MAKEBLASTDB=/opt/miniconda3/bin/makeblastdb
else
    MAKEBLASTDB="$(command -v makeblastdb 2>/dev/null || true)"
fi
BLAST_DB_DIR="${PVDB_BLAST_DB:-$(dirname "$REPO")/blast_db}"
if [ -n "$MAKEBLASTDB" ] && [ -x "$MAKEBLASTDB" ]; then
    echo "==== $(date) Rebuilding BLAST DB ====" | tee -a "$LOG"
    mkdir -p "$BLAST_DB_DIR"
    "$MAKEBLASTDB" \
        -in "$DATA/Plant_Virus_Ref.fasta" -dbtype nucl \
        -out "$BLAST_DB_DIR/plant_virus_ref" \
        -title "PlantVirusDB Reference (monthly)" >> "$LOG" 2>&1 \
        && echo "BLAST DB rebuilt" | tee -a "$LOG"
fi

# Phase 6: 重建 Metabuli 分类库（脚本内部：建到 .new -> 原子换库 -> 留 .prev -> 重启 API）
METABULI_REBUILD="${PVDB_METABULI_REBUILD:-$REPO/9.metabuli/rebuild_metabuli_db.sh}"
if [ -x "$METABULI_REBUILD" ]; then
    echo "==== $(date) Rebuilding Metabuli DB ====" | tee -a "$LOG"
    "$METABULI_REBUILD" >> "$LOG" 2>&1 \
        && echo "Metabuli DB rebuilt" | tee -a "$LOG"
fi

# Phase 7: PAmiRDB 基因注解随检索刷新（有新病毒才下载重建，无新病毒秒退）
#   独立兜底：刷新失败只告警，不中断月度检索管线
if [ -n "${PVDB_PAMIRDB_DIR:-}" ]; then
    PAMIRDB_DIR="$PVDB_PAMIRDB_DIR"
elif [ -d /opt/pamirdb ]; then
    PAMIRDB_DIR=/opt/pamirdb
else
    PAMIRDB_DIR="$REPO/12.pamirdb"
fi
if [ -f "$PAMIRDB_DIR/scripts/parse_genbank_cds.py" ]; then
    echo "==== $(date) Refreshing PAmiRDB gene annotations ====" | tee -a "$LOG"
    PAMIRDB_LOG="${PVDB_PAMIRDB_LOG:-$DIR/archive/pamirdb_fetch_missing.log}"
    mkdir -p "$(dirname "$PAMIRDB_LOG")"
    flock -n /var/lock/pamirdb_fetch_gb.lock \
        bash -c "cd '$PAMIRDB_DIR' && python3.8 scripts/parse_genbank_cds.py --fetch-missing --exit-if-no-missing" \
        >> "$PAMIRDB_LOG" 2>&1 \
        && echo "PAmiRDB annotations refreshed" | tee -a "$LOG" \
        || echo "WARNING: PAmiRDB annotation refresh failed (non-fatal)" | tee -a "$LOG"
fi

# Phase 8: 门户全局检索索引（/data/global_search_index.json）随数据月更重建
#   独立兜底：失败只告警，不中断月度管线（检索框继续用上一版索引）
echo "==== $(date) Rebuilding global search index ====" | tee -a "$LOG"
(cd "$REPO" && python3.8 scripts/build_global_index.py >> "$LOG" 2>&1) \
    && echo "Global search index rebuilt" | tee -a "$LOG" \
    || echo "WARNING: global search index rebuild failed (non-fatal)" | tee -a "$LOG"

echo "==== $(date) Update complete ====" | tee -a "$LOG"
