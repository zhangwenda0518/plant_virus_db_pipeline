#!/usr/bin/env python
"""
Detailed inspection of shared genera between two categories.
Auto-saves each genus to cross_analysis/inspect_{genus}.txt

Usage:
  python inspect_genus.py Plant Fungi                     # all shared genera -> auto-save
  python inspect_genus.py Plant Fungi Fijivirus           # specific genus -> auto-save
  python inspect_genus.py Plant Fungi Fijivirus --stdout  # print to screen
"""
import polars as pl, sys, os

VP = pl.col('Virus_lineage') + ';;;;;;;;'
FAM = VP.str.split(';').list.get(5).str.strip_chars()
GEN = VP.str.split(';').list.get(6).str.strip_chars()
SP  = VP.str.split(';').list.get(7).str.strip_chars()

def load(cat):
    df = pl.read_csv(f'classified_clean/{cat}.tsv', separator='\t', truncate_ragged_lines=True)
    return df.with_columns([FAM.alias('F'), GEN.alias('G'), SP.alias('S')])

cat_a, cat_b = sys.argv[1], sys.argv[2]
da = load(cat_a); db = load(cat_b)
ga = set(da['G'].to_list()); gb = set(db['G'].to_list())

# Filter genus targets
if len(sys.argv) >= 4 and sys.argv[3] != '--stdout':
    targets = [sys.argv[3]]
else:
    targets = sorted(ga & gb)

use_stdout = '--stdout' in sys.argv

os.makedirs('cross_analysis', exist_ok=True)

for g in targets:
    if g not in ga or g not in gb:
        print(f"[{g}] not found in both categories")
        continue

    fa = da.filter(pl.col('G') == g)
    fb = db.filter(pl.col('G') == g)
    fam = fa['F'][0] or fb['F'][0] or ''

    # Build output
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"[{g}]  Family={fam}  |  {cat_a}={fa.height} records  |  {cat_b}={fb.height} records")
    lines.append(f"{'='*80}")

    lines.append(f"\n--- {cat_a}.tsv ({fa.height} records) ---")
    for r in fa.iter_rows(named=True):
        lines.append(f"  {str(r.get('Accession','')):15s} | {str(r.get('Virus_Name',''))[:55]:55s} | Host={str(r.get('Host_Name',''))[:25]:25s}")
        lines.append(f"    V_lineage: {str(r.get('Virus_lineage',''))[:100]}")
        lines.append(f"    H_lineage: {str(r.get('Host_lineage',''))[:100]}")

    lines.append(f"\n--- {cat_b}.tsv ({fb.height} records) ---")
    for r in fb.iter_rows(named=True):
        lines.append(f"  {str(r.get('Accession','')):15s} | {str(r.get('Virus_Name',''))[:55]:55s} | Host={str(r.get('Host_Name',''))[:25]:25s}")
        lines.append(f"    V_lineage: {str(r.get('Virus_lineage',''))[:100]}")
        lines.append(f"    H_lineage: {str(r.get('Host_lineage',''))[:100]}")

    sa = set(fa['S'].to_list()) - {''}
    sb = set(fb['S'].to_list()) - {''}
    lines.append(f"\n--- Species comparison ---")
    lines.append(f"  {cat_a} only: {len(sa - sb)} species")
    for s in sorted(sa - sb)[:8]:
        lines.append(f"    {s}")
    lines.append(f"  {cat_b} only: {len(sb - sa)} species")
    for s in sorted(sb - sa)[:8]:
        lines.append(f"    {s}")
    shared = sa & sb
    if shared:
        lines.append(f"  SHARED: {len(shared)} species !!!")
        for s in sorted(shared):
            lines.append(f"    {s}")
    else:
        lines.append(f"  SHARED: 0 OK")

    text = '\n'.join(lines)

    if use_stdout:
        print(text)
    else:
        fname = f'cross_analysis/inspect_{cat_a}_{cat_b}_{g}.txt'
        with open(fname, 'w') as f:
            f.write(text)
        print(f"Saved: {fname}")
