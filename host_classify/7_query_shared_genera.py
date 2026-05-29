#!/usr/bin/env python
"""Plant-reference shared genus query.

Usage:
  python query_shared_genera.py                      # all categories, detail TSV
  python query_shared_genera.py Plant Fungi          # simple screen + detail TSV
"""
import polars as pl, sys, csv
from collections import defaultdict

VP = pl.col('Virus_lineage') + ';;;;;;;;'
FAM = VP.str.split(';').list.get(5).str.strip_chars()
GEN = VP.str.split(';').list.get(6).str.strip_chars()
SP  = VP.str.split(';').list.get(7).str.strip_chars()

def load(cat):
    df = pl.read_csv(f'classified_clean/{cat}.tsv', separator='\t', truncate_ragged_lines=True)
    return df.with_columns([FAM.alias('F'), GEN.alias('G'), SP.alias('S')]).filter(pl.col('G')!='')

def analyze_pair(cat_a, cat_b, save_detail=True):
    """Compare two categories, return shared genera info."""
    da = load(cat_a); db = load(cat_b)
    ga = set(da['G'].to_list()); gb = set(db['G'].to_list())
    shared = sorted(ga & gb)
    excl = len(ga - gb)

    a_sp_per_gen = defaultdict(lambda: defaultdict(int))
    for r in da.group_by(['G','S']).len().iter_rows():
        a_sp_per_gen[r[0]][r[1]] += r[2]
    b_sp_per_gen = defaultdict(lambda: defaultdict(int))
    for r in db.group_by(['G','S']).len().iter_rows():
        b_sp_per_gen[r[0]][r[1]] += r[2]

    print(f'\n{cat_a}: {len(ga)} genera, {cat_b}: {len(gb)} genera')
    print(f'Shared: {len(shared)}, {cat_a}-exclusive: {excl}')
    print()

    rows = []
    for g in shared:
        pc = sum(a_sp_per_gen[g].values())
        bc = sum(b_sp_per_gen[g].values())
        fam = da.filter(pl.col('G')==g)['F'][0] or db.filter(pl.col('G')==g)['F'][0] or ''
        a_sp = sorted(a_sp_per_gen[g].keys())
        b_sp = sorted(b_sp_per_gen[g].keys())

        print(f'  {g:35s}  {cat_a}={pc:>5d}  {cat_b}={bc:>4d}')

        if save_detail:
            for s in a_sp:
                rows.append({'Genus': g, 'Family': fam, f'{cat_a}_Records': pc, f'{cat_b}_Records': bc,
                             f'{cat_a}_Species': s, f'In_{cat_b}': int(s in set(b_sp))})
            for s in b_sp:
                if s not in set(a_sp):
                    rows.append({'Genus': g, 'Family': fam, f'{cat_a}_Records': pc, f'{cat_b}_Records': bc,
                                 f'{cat_a}_Species': '', f'In_{cat_b}': 1})

    if save_detail and rows:
        fn = ['Genus','Family',f'{cat_a}_Records',f'{cat_b}_Records',f'{cat_a}_Species',f'In_{cat_b}']
        path = f'cross_analysis/{cat_a}_{cat_b}_shared_genera.tsv'
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, delimiter='\t', fieldnames=fn)
            w.writeheader(); w.writerows(rows)
        print(f'\n  Detail saved: {path} ({len(rows)} rows)')

    return shared, rows


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        # Mode 1: specific pair
        analyze_pair(sys.argv[1], sys.argv[2], save_detail=True)
    else:
        # Mode 2: Plant vs all others
        for cat in ['Fungi','Insecta','Arachnida','Aves','Animal_other','Oomycetes']:
            analyze_pair('Plant', cat, save_detail=True)
