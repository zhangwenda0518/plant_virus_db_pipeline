"""Rebuild pamirdb_v7_data.js from SQLite DB (with fixed families)."""
import json, sqlite3
from pathlib import Path
from collections import Counter

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "pamirdb.sqlite"

db = sqlite3.connect(str(DB_PATH))
sql = """SELECT mirna_id, target_virus_id, target_virus_name, target_virus_family,
         target_start, target_end, consensus_level, num_algorithms,
         best_energy, seed_quality_score, target_gene, target_product,
         targeting_status, consensus_detail, alignment
         FROM predictions_v7"""
rows_db = db.execute(sql).fetchall()

levels = ['LOW','LOW+','MEDIUM','MEDIUM+','HIGH','HIGH+','VERY HIGH']
out_rows = []
fams = Counter()
sp_set = Counter()

# Build species lookup from miRNA DB
with open(DATA_DIR / "mirna" / "plant_mirnas_full.json") as f:
    mirnas = json.load(f)
mid_to_sp = {mid: info.get("species_name", "") for mid, info in mirnas.items()}

for r in rows_db:
    mid = r[0]
    sp = mid_to_sp.get(mid, "")
    if not sp:
        # fallback: extract from ID format "Species_name-miRN..."
        if "_" in mid and "-" in mid:
            sp = mid.split("-")[0]
        else:
            sp = mid.split("_")[0] if "_" in mid else mid[:20]
    fam = r[3] or "unknown"
    fams[fam] += 1
    sp_set[sp] += 1
    lvl_idx = levels.index(r[5]) if r[5] in levels else 0
    out_rows.append([
        mid, sp, r[1] or "", (r[2] or "")[:60], fam,
        r[4] or 0, r[5] or 0, lvl_idx, r[7] or 0,
        round(r[8] or 0, 1), r[9] or 0, r[10] or "", r[11] or "",
        r[12] or "", r[13] or "", r[14] or ""
    ])

data = {
    "rows": out_rows,
    "families": sorted(fams.keys()),
    "species": sorted(sp_set.keys()),
    "levels": levels,
    "total": len(out_rows),
    "n_species": len(sp_set),
    "n_families": len(fams),
}

out_path = DATA_DIR / "web" / "pamirdb_v7_data_fixed.js"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    f.write("window.PAMIRDB_V7=" + json.dumps(data, ensure_ascii=False) + ";")

kb = out_path.stat().st_size / 1024
print(f"Generated: {out_path}")
print(f"  {len(out_rows)} rows, {len(sp_set)} species, {len(fams)} families")
print(f"  Size: {kb:.0f} KB")
print(f"  unknown: {fams.get('unknown', 0)}")
