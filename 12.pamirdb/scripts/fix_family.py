"""Fix unknown virus families in predictions_v7 using Full TSV data."""
import sqlite3, json
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
TSV_PATH = Path("/home/zhangwenda/docs/data/Plant_Virus_Full.Info.tsv")

# Build species -> family from Full TSV
species_family = {}
with open(TSV_PATH, encoding='utf-8') as f:
    header = f.readline().rstrip('\n\r').split('\t')
    col = {n: i for i, n in enumerate(header)}
    for line in f:
        cols = line.rstrip('\n\r').split('\t')
        if len(cols) < len(header):
            continue
        sp_ictv = (cols[col.get('Species_ICTV', '')] or '').strip().lower()
        family = (cols[col.get('Family', '')] or '').strip()
        if sp_ictv and family and sp_ictv not in species_family:
            species_family[sp_ictv] = family

print(f"Species-family mappings: {len(species_family)}")

db = sqlite3.connect(str(DATA_DIR / "pamirdb.sqlite"))

# Check before
unknown_sql = "SELECT COUNT(*) FROM predictions_v7 WHERE target_virus_family='' OR target_virus_family IS NULL OR target_virus_family = 'unknown'"
unknown = db.execute(unknown_sql).fetchone()[0]
print(f"Unknown/empty families before: {unknown}")

# Get and update
rows = db.execute("SELECT id, target_virus_name FROM predictions_v7 WHERE target_virus_family='' OR target_virus_family IS NULL OR target_virus_family = 'unknown'").fetchall()
updated = 0
for pid, vname in rows:
    sp_key = vname.lower().strip() if vname else ''
    fam = species_family.get(sp_key, '')
    if fam:
        db.execute("UPDATE predictions_v7 SET target_virus_family=? WHERE id=?", (fam.lower(), pid))
        updated += 1

db.commit()
remaining = db.execute(unknown_sql).fetchone()[0]
print(f"Updated: {updated}")
print(f"Still unknown: {remaining}")

# Show new distribution
rows = db.execute("SELECT target_virus_family, COUNT(*) c FROM predictions_v7 GROUP BY target_virus_family ORDER BY c DESC").fetchall()
print(f"\nTotal families: {len(rows)}")
for r in rows[:15]:
    print(f"  {r[0] or '(empty)'}: {r[1]}")
print("Done!")
