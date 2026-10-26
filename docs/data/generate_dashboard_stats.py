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
ACCESSION_RE = re.compile(r"^[A-Z]{1,3}_?\d+(?:\.\d+)?$")


def normalize_family(value):
    """Clean raw GenBank family labels into ICTV-style family names.

    Drops empty values and accessions mistakenly stored in the Family column,
    and folds "unclassified Xviridae" into "Xviridae".
    """
    v = (value or "").strip()
    if not v or ACCESSION_RE.match(v):
        return ""
    return re.sub(r"(?i)^unclassified\s+", "", v).strip()


def load_plant_taxonomy(here):
    """Read the ICTV MSL41 plant-virus baseline used by /phylo/.

    Returns (plant_family_set, plant_genus_set, plant_genera_total, plant_species_total).
    """
    meta = {}
    p = here.parent / "phylo" / "taxonomy_tree.json"
    if p.exists():
        try:
            meta = json.loads(p.read_text(encoding="utf-8")).get("meta", {})
        except (OSError, ValueError):
            meta = {}
    families = {str(x).strip() for x in meta.get("plant_family_list", []) if str(x).strip()}
    genera = {str(x).strip() for x in meta.get("plant_genus_list", []) if str(x).strip()}
    return (families, genera,
            int(meta.get("plant_genera") or 0), int(meta.get("plant_species") or 0))


def build_genus_map(ref_rows):
    """Map species names in the reference table to their VMR genus."""
    mapping = {}
    for r in ref_rows:
        genus = (r.get("VMR_Genus") or "").strip()
        if not genus:
            continue
        for col in ("Species_ICTV", "Species_NCBI", "Species_Canonical"):
            name = (r.get(col) or "").strip()
            if name:
                mapping.setdefault(name, genus)
    return mapping



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


def compute_stats(rows, has_vmr=False, has_category=False, family_col="Family",
                  plant_families=None, plant_genera=None, genus_map=None, taxonomy_totals=None):
    """Compute all dashboard stats from a list of dict rows.

    Family and genus KPIs follow the ICTV MSL41 plant-virus taxonomy:
    the reference table uses its VMR assignment, the full table normalizes
    raw GenBank labels and maps species names to VMR genera.
    """
    n = len(rows)
    # taxids
    taxids = {r.get("Taxid", "") for r in rows if r.get("Taxid", "")}
    # distinct ICTV species names
    species = {(r.get("Species_ICTV") or "").strip() for r in rows if (r.get("Species_ICTV") or "").strip()}

    # families / genera
    fam_counter = Counter()
    genera = set()
    if has_vmr:
        for r in rows:
            fam = (r.get("VMR_Family") or "").strip()
            if fam:
                fam_counter[fam] += 1
            genus = (r.get("VMR_Genus") or "").strip()
            if genus:
                genera.add(genus)
    else:
        for r in rows:
            fam = normalize_family(r.get(family_col))
            if fam:
                fam_counter[fam] += 1
        if genus_map:
            for r in rows:
                for col in ("Species_ICTV", "Species_NCBI"):
                    name = (r.get(col) or "").strip()
                    if name in genus_map:
                        genera.add(genus_map[name])
                        break

    # Only count families recognized as plant viruses by ICTV MSL41.
    if plant_families:
        fam_counter = Counter({f: c for f, c in fam_counter.items() if f in plant_families})

    # Genera follow the same MSL41 baseline (VMR Host source strict list).
    if plant_genera:
        genera = {g for g in genera if g in plant_genera}

    # segmented / nonsegmented (ref only has Category)
    # 卡片口径（2026-10-26 用户定版）：物种数 = 去重 NCBI TaxID（不锚 ICTV 命名合并）；
    # 节段/非节段按 taxid 不重不漏二分——有任何节段记录的 taxid 记节段，其余记非节段，
    # 两者相加 = 物种总数。记录条数仍保留在 JSON 供核对。
    seg = ns = None
    seg_species = ns_species = None
    if has_category:
        seg_tax = set()
        seg = ns = 0
        for r in rows:
            cat = str(r.get("Category", ""))
            tid = (r.get("Taxid") or "").strip()
            if cat.startswith("Segmented"):
                seg += 1
                if tid:
                    seg_tax.add(tid)
            elif cat.startswith("NonSegmented"):
                ns += 1
        seg_species = len(seg_tax & taxids)
        ns_species = len(taxids) - seg_species

    # Sequence Types (strip /ICTV)
    st = Counter()
    for r in rows:
        v = (r.get("Sequence_Type", "") or "Unknown").replace("/ICTV", "")
        st[v] += 1
    # Top Hosts
    hosts = Counter(r.get("Host", "") for r in rows if r.get("Host", ""))
    # Molecule (strip parens)
    mol = Counter()
    for r in rows:
        v = (r.get("Molecule_type", "") or "Unknown").replace("(", "").replace(")", "")
        mol[v] += 1
    # Topology
    topo = Counter(r.get("Topology", "") or "Unknown" for r in rows)

    totals = taxonomy_totals or {}
    return {
        "kpis": {
            "sequences": n,
            "taxids": len(taxids),
            "species": len(species),
            "families": len(fam_counter),
            "genera": len(genera),
            "segmented": seg,
            "nonsegmented": ns,
            "segmented_species": seg_species,
            "nonsegmented_species": ns_species,
        },
        "taxonomy": {
            "families": totals.get("families"),
            "genera": totals.get("genera"),
            "species": totals.get("species"),
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

    plant_families, plant_genera_set, plant_genera_total, plant_species_total = load_plant_taxonomy(here)
    totals = {
        "families": len(plant_families) or None,
        "genera": plant_genera_total or None,
        "species": plant_species_total or None,
    }
    print(f"ICTV MSL41 plant-virus baseline: {totals}")

    genus_map = build_genus_map(ref)

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "full": compute_stats(
            full, has_vmr=False, has_category=False, family_col="Family",
            plant_families=plant_families, plant_genera=plant_genera_set,
            genus_map=genus_map, taxonomy_totals=totals,
        ),
        "ref": compute_stats(
            ref, has_vmr=True, has_category=True, family_col="VMR_Family",
            plant_families=plant_families, plant_genera=plant_genera_set, taxonomy_totals=totals,
        ),
    }
    for src in ("full", "ref"):
        k = result[src]["kpis"]
        print(f"  {src}: sequences={k['sequences']:,} species={k['species']:,} "
              f"families={k['families']}/{totals['families']} genera={k['genera']}/{totals['genera']}")

    out = Path(args.out)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    size = out.stat().st_size
    print(f"Wrote {out} ({size:,} bytes, {size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
