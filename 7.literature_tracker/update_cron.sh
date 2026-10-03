#!/bin/bash
# Update server cron for weekly literature tracking
crontab -l 2>/dev/null | grep -v "literature\|fetch_pubmed\|fetch_linked" > /tmp/new_cron

echo "0 6 * * 1 cd /opt/plant_virus_db/plant_virus_db_pipeline/7.literature_tracker && . /opt/plant_virus_db/.env && LLM_API_KEY="${DEEPSEEK_API_KEY:?need DEEPSEEK_API_KEY in /opt/plant_virus_db/.env}" LLM_BASE_URL=https://api.deepseek.com/v1 LLM_MODEL=deepseek-v4-flash python3 pipeline.py auto --days 7 >> /var/log/literature-weekly.log 2>&1 && python3 pipeline.py digest-weekly --weeks-back 8 --no-ai >> /var/log/literature-weekly.log 2>&1 && python3 build_data.py --ai-verified >> /var/log/literature-weekly.log 2>&1" >> /tmp/new_cron

crontab /tmp/new_cron
echo "=== New cron ==="
crontab -l | grep literature
echo "=== Done ==="
