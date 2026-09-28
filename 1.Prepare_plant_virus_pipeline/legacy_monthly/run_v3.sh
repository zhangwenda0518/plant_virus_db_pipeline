#!/bin/bash
# Simple monthly runner - writes output directly to log
DIR=/opt/plant_virus_db/plant_virus_db_pipeline/1.Prepare_plant_virus_pipeline
STATUS=/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/incremental_status.json
LOG=/var/log/incremental_update.log
DT=$(date -Iseconds)

cat > $STATUS <<END
{"started_at":"$DT","status":"running","total_months":7,"completed_months":0,"months":[],"summary":{"total_new_plant":0,"total_scanned":0}}
END

TOTAL_P=0; TOTAL_S=0; DONE=0

run_month() {
  local SINCE=$1 UNTIL=$2 LABEL=$3
  echo "==== $(date) $LABEL ($SINCE -> $UNTIL) ====" | tee -a $LOG
  cd $DIR
  TMP=$(mktemp)
  python3.8 U1_incremental_update.py --since $SINCE --until $UNTIL --skip-taxonomy --chunk-months 1 > $TMP 2>&1
  cat $TMP >> $LOG
  NP=$(grep "植物病毒命中:" $TMP | grep -oP "[0-9,]+" | head -1 | tr -d ,)
  NS=$(grep "去重后:" $TMP | grep -oP "[0-9,]+" | head -1 | tr -d ,)
  rm $TMP
  NP=${NP:-0}; NS=${NS:-0}
  TOTAL_P=$((TOTAL_P + NP)); TOTAL_S=$((TOTAL_S + NS)); DONE=$((DONE + 1))
  python3.8 -c "
import json
s=json.load(open('$STATUS'))
s['months'].append({'label':'$LABEL','since':'$SINCE','until':'$UNTIL','scanned':$NS,'new_plant':$NP,'status':'done'})
s['completed_months']=$DONE
s['summary']={'total_new_plant':$TOTAL_P,'total_scanned':$TOTAL_S}
if $DONE == 7: s['status']='complete'
s['updated_at']='$(date -Iseconds)'
json.dump(s,open('$STATUS','w'),ensure_ascii=False,indent=2)
"
  echo "$(date) $LABEL done: $NP plant / $NS scanned (total: $TOTAL_P)" | tee -a $LOG
}

run_month 2026-01-01 2026-01-31 "Jan"
run_month 2026-02-01 2026-02-28 "Feb"
run_month 2026-03-01 2026-03-31 "Mar"
run_month 2026-04-01 2026-04-30 "Apr"
run_month 2026-05-01 2026-05-31 "May"
run_month 2026-06-01 2026-06-30 "Jun"
run_month 2026-07-01 2026-07-29 "Jul"

echo "==== $(date) ALL DONE: $TOTAL_P plant / $TOTAL_S scanned ====" | tee -a $LOG
