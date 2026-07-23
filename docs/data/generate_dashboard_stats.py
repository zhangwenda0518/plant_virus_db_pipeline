#!/usr/bin/env python3
"""
Pre-generate dashboard_stats.json for the Reference DB Dashboard.

Reads Plant_Virus_Full.Info.tsv and Plant_Virus_Ref.Info.tsv,
computes all chart statistics server-side, writes a single small JSON
so the browser no longer has to parse 48MB of TSV.

Output: docs/data/dashboard_stats.json
Structure:
{
  "generated_at": "2026-07-17...",
  "full": { kpis, sequenceTypes, topHosts, topFamilies, moleculeTypes,
            collectionYears, releaseYears, topology, lengthBins },
  "ref":  { ...same... }
}

Usage:
  python3 generate_dashboard_stats.py
  # or with explicit paths:
  python3 generate_dashboard_stats.py --full path/Full.Info.tsv --ref path/Ref.Info.tsv -o out.json
"""
import csv
import json
import re
import sys
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _top(counter, n=20):
    return [[k, v] for k, v in counter.most_common(n) if k]


def _year_bins(rows, col):
    c = Counter()
    for r in rows:
        m = YEAR_RE.search(str(r.get(col, "") or ""))
        if m:
            c[m.group(0)] += 1
    return [[k, c[k]] for k in sorted(c.keys())]


def _length_bins(rows, col="Length", step=1000, max_len=20000):
    bins = Counter()
    for r in rows:
        try:
            v = int(float(r.get(col, 0) or 0))
        except (ValueError, TypeError):
            continue
        if 0 < v < max_len:
            b = (v // step) * step
            bins[b] += 1
    return [[f"{b}-{b + step - 1}", bins[b]] for b in sorted(bins.keys())]


def compute_stats(rows, has_vmr=False, has_category=False, family_col="Family"):
    """Compute all dashboard stats from a list of dict rows."""
    n = len(rows)
    # taxids
    taxids = {r.get("Taxid", "") for r in rows if r.get("Taxid", "")}
    # families / genera (ref only has VMR_*)
    if has_vmr:
        fams = {r.get("VMR_Family", "") for r in rows if r.get("VMR_Family", "")}
        genera = {r.get("VMR_Genus", "") for r in rows if r.get("VMR_Genus", "")}
        fam_col = "VMR_Family"
    else:
        fams = {r.get(family_col, "") for r in rows if r.get(family_col, "")}
        genera = set()
        fam_col = family_col
    # segmented / nonsegmented (ref only has Category)
    seg = ns = None
    if has_category:
        seg = sum(1 for r in rows if str(r.get("Category", "")).startswith("Segmented"))
        ns = sum(1 for r in rows if str(r.get("Category", "")).startswith("NonSegmented"))

    # Sequence Types (strip /ICTV)
    st = Counter()
    for r in rows:
        v = (r.get("Sequence_Type", "") or "Unknown").replace("/ICTV", "")
        st[v] += 1
    # Top Hosts
    hosts = Counter(r.get("Host", "") for r in rows if r.get("Host", ""))
    # Top Families
    fam_counter = Counter(r.get(fam_col, "") for r in rows if r.get(fam_col, ""))
    # Molecule (strip parens)
    mol = Counter()
    for r in rows:
        v = (r.get("Molecule_type", "") or "Unknown").replace("(", "").replace(")", "")
        mol[v] += 1
    # Topology
    topo = Counter(r.get("Topology", "") or "Unknown" for r in rows)

    return {
        "kpis": {
            "sequences": n,
            "taxids": len(taxids),
            "families": len(fams) if fams else 0,
            "genera": len(genera),
            "segmented": seg,
            "nonsegmented": ns,
        },
        "sequenceTypes": _top(st, 20),
        "topHosts": _top(hosts, 20),
        "topFamilies": _top(fam_counter, 20),
        "moleculeTypes": [[k, v] for k, v in mol.most_common() if k],
        "collectionYears": _year_bins(rows, "Collection_Date"),
        "releaseYears": _year_bins(rows, "Release_Date"),
        "topology": [[k, v] for k, v in topo.most_common() if k],
        "lengthBins": _length_bins(rows),
    }


def read_tsv(path):
    if not Path(path).exists():
        print(f"  [warn] not found: {path}", file=sys.stderr)
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def main():
    ap = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    ap.add_argument("--full", default=str(here / "Plant_Virus_Full.Info.tsv"))
    ap.add_argument("--ref", default=str(here / "Plant_Virus_Ref.Info.tsv"))
    ap.add_argument("-o", "--out", default=str(here / "dashboard_stats.json"))
    args = ap.parse_args()

    print(f"Reading Full: {args.full}")
    full = read_tsv(args.full)
    print(f"  -> {len(full)} rows")
    print(f"Reading Ref:  {args.ref}")
    ref = read_tsv(args.ref)
    print(f"  -> {len(ref)} rows")

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "full": compute_stats(full, has_vmr=False, has_category=False, family_col="Family"),
        "ref": compute_stats(ref, has_vmr=True, has_category=True, family_col="VMR_Family"),
    }

    out = Path(args.out)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    size = out.stat().st_size
    print(f"Wrote {out} ({size:,} bytes, {size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
