#!/bin/bash
# 逐月增量更新 2026年1月-7月
set -e

PIPELINE_DIR="/opt/plant_virus_db/plant_virus_db_pipeline/1.Prepare_plant_virus_pipeline"
STATUS_FILE="/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/incremental_status.json"

MONTHS=(
  "2026-01-01 2026-01-31 2026年1月"
  "2026-02-01 2026-02-28 2026年2月"
  "2026-03-01 2026-03-31 2026年3月"
  "2026-04-01 2026-04-30 2026年4月"
  "2026-05-01 2026-05-31 2026年5月"
  "2026-06-01 2026-06-30 2026年6月"
  "2026-07-01 2026-07-29 2026年7月"
)

cat > "$STATUS_FILE" << EOF
{
  "started_at": "$(date -Iseconds)",
  "status": "running",
  "total_months": ${#MONTHS[@]},
  "completed_months": 0,
  "months": [],
  "summary": {"total_new_plant": 0, "total_scanned": 0}
}
EOF

TOTAL_PLANT=0
TOTAL_SCANNED=0
COMPLETED=0

for entry in "${MONTHS[@]}"; do
  read -r SINCE UNTIL LABEL <<< "$entry"
  echo ""
  echo "========================================"
  echo "  Processing: $LABEL ($SINCE to $UNTIL)"
  echo "========================================"

  cd "$PIPELINE_DIR"

  OUTPUT=$(python3.8 U1_incremental_update.py \
    --since "$SINCE" --until "$UNTIL" \
    --skip-taxonomy --chunk-months 1 \
    2>&1)
  RC=$?

  NEW_PLANT=$(echo "$OUTPUT" | grep "植物病毒命中:" | grep -oP '[0-9,]+' | head -1 | tr -d ',')
  NEW_TSV=$(echo "$OUTPUT" | grep "TSV +" | grep -oP '[0-9]+' | head -1)
  SCANNED=$(echo "$OUTPUT" | grep "去重后:" | grep -oP '[0-9,]+' | head -1 | tr -d ',')

  NEW_PLANT=${NEW_PLANT:-0}
  NEW_TSV=${NEW_TSV:-0}
  SCANNED=${SCANNED:-0}

  TOTAL_PLANT=$((TOTAL_PLANT + NEW_PLANT))
  TOTAL_SCANNED=$((TOTAL_SCANNED + SCANNED))
  COMPLETED=$((COMPLETED + 1))

  python3.8 -c "
import json
with open('$STATUS_FILE') as f: s=json.load(f)
s['months'].append({'label':'$LABEL','since':'$SINCE','until':'$UNTIL','scanned':$SCANNED,'new_plant':$NEW_PLANT,'new_tsv':$NEW_TSV,'status':'done','exit_code':$RC})
s['completed_months']=$COMPLETED
s['summary']={'total_new_plant':$TOTAL_PLANT,'total_scanned':$TOTAL_SCANNED}
if $COMPLETED == ${#MONTHS[@]}: s['status']='complete'
s['updated_at']='$(date -Iseconds)'
with open('$STATUS_FILE','w') as f: json.dump(s,f,ensure_ascii=False,indent=2)
"

  echo "  Done: $LABEL - $NEW_PLANT plant / $SCANNED scanned"
  echo "  Cumulative: $TOTAL_PLANT plant / $TOTAL_SCANNED scanned"
done

echo ""
echo "All done! Total: $TOTAL_PLANT plant viruses / $TOTAL_SCANNED sequences"
