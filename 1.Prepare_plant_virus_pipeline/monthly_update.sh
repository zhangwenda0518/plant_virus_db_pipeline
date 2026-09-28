#!/bin/bash
# PlantVirusDB Monthly Update Runner
# 用法: bash monthly_update.sh [YYYY-MM-DD]  (默认: 自动从上次同步日期开始)
# Cron: 0 3 1 * * bash <REPO>/1.Prepare_plant_virus_pipeline/monthly_update.sh   # 路径按实际部署位置填写

set -e

# (已移除硬编码日志路径) # 路径全部由脚本自身位置推导（不再硬编码 opt 与 /var/log）：
#   REPO=<仓库根> 可覆盖；PVDB_LOG / PVDB_DATA 亦可覆盖
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

echo "==== $(date) Update complete ====" | tee -a "$LOG"
