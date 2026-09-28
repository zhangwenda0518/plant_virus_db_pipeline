#!/bin/bash
set -e
DIR="/opt/plant_virus_db/plant_virus_db_pipeline/1.Prepare_plant_virus_pipeline"
STATUS="/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/incremental_status.json"
LOG="/var/log/incremental_update.log"

MONTHS=(
  "2026-01-01 2026-01-31 1月"
  "2026-02-01 2026-02-28 2月"
  "2026-03-01 2026-03-31 3月"
  "2026-04-01 2026-04-30 4月"
  "2026-05-01 2026-05-31 5月"
  "2026-06-01 2026-06-30 6月"
  "2026-07-01 2026-07-29 7月"
)

cat > "$STATUS" << JSON
{"started_at":"$(date -Iseconds)","status":"running","total_months":7,"completed_months":0,"months":[],"summary":{"total_new_plant":0,"total_scanned":0}}
JSON

TOTAL_PLANT=0; TOTAL_SCANNED=0; COMPLETED=0

for entry in "${MONTHS[@]}"; do
  read -r SINCE UNTIL LABEL <<< "$entry"
  echo "" >> "$LOG"
  echo "==== $(date) Processing: $LABEL ($SINCE -> $UNTIL) ====" | tee -a "$LOG"
  
  cd "$DIR"
  TMPFILE=$(mktemp)
  set +e
  python3.8 U1_incremental_update.py --since "$SINCE" --until "$UNTIL" --skip-taxonomy --chunk-months 1 > "$TMPFILE" 2>&1
  RC=$?
  set -e
  
  OUTPUT=$(cat "$TMPFILE")
  cat "$TMPFILE" >> "$LOG"
  rm "$TMPFILE"
  
  NEW_PLANT=$(echo "$OUTPUT" | grep "植物病毒命中:" | grep -oP "[0-9,]+" | head -1 | tr -d ",")
  NEW_TSV=$(echo "$OUTPUT" | grep "TSV +" | grep -oP "[0-9]+" | head -1)
  SCANNED=$(echo "$OUTPUT" | grep "去重后:" | grep -oP "[0-9,]+" | head -1 | tr -d ",")
  NEW_PLANT=${NEW_PLANT:-0}; NEW_TSV=${NEW_TSV:-0}; SCANNED=${SCANNED:-0}
  
  TOTAL_PLANT=$((TOTAL_PLANT + NEW_PLANT))
  TOTAL_SCANNED=$((TOTAL_SCANNED + SCANNED))
  COMPLETED=$((COMPLETED + 1))
  
  python3.8 -c "
import json
with open('$STATUS') as f: s=json.load(f)
s['months'].append({'label':'$LABEL','since':'$SINCE','until':'$UNTIL','scanned':$SCANNED,'new_plant':$NEW_PLANT,'new_tsv':$NEW_TSV,'status':'done'})
s['completed_months']=$COMPLETED
s['summary']={'total_new_plant':$TOTAL_PLANT,'total_scanned':$TOTAL_SCANNED}
if $COMPLETED == 7: s['status']='complete'
s['updated_at']='$(date -Iseconds)'
with open('$STATUS','w') as f: json.dump(s,f,ensure_ascii=False,indent=2)
"
  echo "$(date) $LABEL: plant=$NEW_PLANT scanned=$SCANNED total_plant=$TOTAL_PLANT" | tee -a "$LOG"
done
echo "$(date) ALL DONE. Total: $TOTAL_PLANT plant / $TOTAL_SCANNED scanned" | tee -a "$LOG"
