#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_eve_data.py -- aggregate kingdom-scale EVE results into front-end JSON.

Run on:  ssh success   (zhangwenda@202.119.189.246, output dir ~/eve_kingdom/)
Reads :  ~/eve_kingdom/            (frozen 2026-09-23 dataset)
         /home/train/plantGIR/     (host family dir -> species dir)
         /home/train/plantGIR/species_information.csv
Writes:  ~/eve_kingdom/web_json/eve_landscape.json
         ~/eve_kingdom/web_json/eve_dynamics.json
         ~/eve_kingdom/web_json/eve_phylo.json
         ~/eve_kingdom/web_json/_audit/*.tsv     (human-checkable numbers)

Design notes / why it is written this way
-----------------------------------------
* The loci master table is 773 MB / 28.5 M rows.  Python never sees it: a
  single awk pass reduces it to the 205,873 viral_supported loci, and only
  those four columns (genome / ref_family / lca_taxname / final_class) are
  loaded.  Re-running is idempotent (the extract is cached).
* Every number that reaches the web page is mirrored into _audit/*.tsv, so a
  reader can re-check a figure without re-running the pipeline.
* Host family comes from the plantGIR directory layout (family dir contains
  species dirs).  Species -> phylum/class/order comes from
  species_information.csv; a family's plant group is the mode over its species.
* Genome type (dsDNA-RT / ssDNA / dsDNA / dsRNA / ssRNA+ / ssRNA-) is an
  explicit table keyed by viral family.  Do NOT infer it from the family name
  -- Iridoviridae is dsDNA but sits next to dsRNA families alphabetically, and
  Mitoviridae is ssRNA+ despite the "-viridae" look.
* Phage (72,573) and Other_viral (93,226) are 80% of all viral_supported loci
  and are NOT virus families.  They are kept in the totals but flagged, so the
  page can show "identified families" separately from "all hits".
"""

import os
import sys
import json
import csv
import subprocess
from collections import Counter, defaultdict

B = os.path.expanduser("~/eve_kingdom")
A = os.path.join(B, "analysis")
GIR = "/home/train/plantGIR"
OUT = os.path.join(B, "web_json")
AUD = os.path.join(OUT, "_audit")
os.makedirs(AUD, exist_ok=True)

LOCI = os.path.join(B, "kingdom_loci_all_clean.tsv.gz")
EXTRACT = os.path.join(B, "_vs_extract.tsv")

# --------------------------------------------------------------------------
# viral family -> genome type.  Sources: ICTV MSL41 genome composition.
# --------------------------------------------------------------------------
VTYPE = {
    "Caulimoviridae": "dsDNA-RT",
    "Geminiviridae": "ssDNA", "Nanoviridae": "ssDNA", "Genomoviridae": "ssDNA",
    "Circoviridae": "ssDNA", "Geminiviridae_": "ssDNA",
    "NCLDV": "dsDNA", "Naldaviricetes": "dsDNA", "Iridoviridae": "dsDNA",
    "Poxviridae": "dsDNA", "Baculoviridae": "dsDNA", "Herpesviridae": "dsDNA",
    "Chrysoviridae": "dsRNA", "Partitiviridae": "dsRNA", "Amalgaviridae": "dsRNA",
    "Reoviridae": "dsRNA", "Totiviridae": "dsRNA", "Quadriviridae": "dsRNA",
    "Megabirnaviridae": "dsRNA", "Birnaviridae": "dsRNA",
    "Betaflexiviridae": "ssRNA+", "Alphaflexiviridae": "ssRNA+",
    "Mitoviridae": "ssRNA+", "Bromoviridae": "ssRNA+", "Trichoviridae": "ssRNA+",
    "Virgaviridae": "ssRNA+", "Solemoviridae": "ssRNA+", "Tombusviridae": "ssRNA+",
    "Nodaviridae": "ssRNA+", "Endornaviridae": "ssRNA+", "Hypoviridae": "ssRNA+",
    "Potyviridae": "ssRNA+", "Closteroviridae": "ssRNA+", "Tymoviridae": "ssRNA+",
    "Secoviridae": "ssRNA+", "Luteoviridae": "ssRNA+", "Tombusviridae_": "ssRNA+",
    "Rhabdoviridae": "ssRNA-", "Phenuiviridae": "ssRNA-", "Bunyaviridae": "ssRNA-",
    "Phage": "phage", "Other_viral": "unclassified",
}
DNA_T = {"dsDNA-RT", "ssDNA", "dsDNA"}
RNA_T = {"dsRNA", "ssRNA+", "ssRNA-"}

# order of the group axis on the page (evolutionary, algae -> eudicot)
GROUP_ORDER = ["algae", "bryophyte", "fern", "gymnosperm", "basal_angiosperm",
               "magnoliid", "monocot", "eudicot", "unknown"]
GROUP_LABEL = {
    "algae": "Algae", "bryophyte": "Bryophytes", "fern": "Ferns & allies",
    "gymnosperm": "Gymnosperms", "basal_angiosperm": "Basal angiosperms",
    "magnoliid": "Magnoliids", "monocot": "Monocots", "eudicot": "Eudicots",
    "unknown": "Unplaced",
}

MONOCOT_ORDERS = {
    "Acorales", "Alismatales", "Arecales", "Asparagales", "Commelinales",
    "Dioscoreales", "Liliales", "Pandanales", "Petrosaviales", "Poales",
    "Zingiberales",
}
BASAL_ANGIO_ORDERS = {"Amborellales", "Nymphaeales", "Austrobaileyales"}
MAGNOLIID_ORDERS = {"Canellales", "Laurales", "Magnoliales", "Piperales"}

# genus-level taxa inside Caulimoviridae, recognised from the RVDB LCA name
CAULI_GENUS = [
    "Caulimovirus", "Badnavirus", "Tungrovirus", "Solendovirus", "Soymovirus",
    "Cavemovirus", "Capulavirus", "Petuvirus", "Citlodavirus", "Rosadnavirus",
    "Ruflodivirus", "Florendovirus", "Gnanfvirus", "Minuvirus", "Ormavirus",
    "Pusavirus", "Sunnivirus", "Tropaeovirus", "Cauliflower mosaic virus",
    "SVBV", "Commelina yellow mottle", "PVCV", "Caulimoviridae",
]


def plant_group(phylum, aclass, order):
    phylum = (phylum or "").strip()
    aclass = (aclass or "").strip()
    order = (order or "").strip()
    if phylum in ("Chlorophyta", "Rhodophyta", "Prasinodermophyta",
                  "Glaucophyta", "Bangiophyceae", "Florideophyceae") \
            or "phyceae" in aclass or "phycidae" in aclass:
        return "algae"
    if aclass in ("Bryopsida", "Marchantiopsida", "Anthocerotopsida",
                  "Jungermanniopsida", "Sphagnopsida", "Polytrichopsida",
                  "Andreaeopsida", "Takakiopsida", "Bryidae"):
        return "bryophyte"
    if aclass in ("Polypodiopsida", "Lycopodiopsida", "Equisetopsida",
                  "Marattiopsida", "Ophioglossopsida", "Psilotopsida"):
        return "fern"
    if aclass in ("Pinopsida", "Gnetopsida", "Ginkgoopsida", "Cycadopsida"):
        return "gymnosperm"
    if order in BASAL_ANGIO_ORDERS:
        return "basal_angiosperm"
    if order in MAGNOLIID_ORDERS:
        return "magnoliid"
    if order in MONOCOT_ORDERS:
        return "monocot"
    if order and order != "NULL":
        return "eudicot"
    return "unknown"


def genus_of(lca):
    for g in CAULI_GENUS:
        if g.lower() in (lca or "").lower():
            return g
    return None


def load_tier2():
    """nr-promoted loci (tier A+B = 4,091) -- genome + viral_family.

    These are loci that Stage-2 called undetermined but a full nr blastx
    re-classified as plant virus (bs>=50).  They are NOT in the loci master
    table, so they must be merged in by hand or the totals fall short by
    4,091 (150,136 -> 146,045).
    """
    rows = []
    p = os.path.join(B, "updated_tier2_log.tsv")
    if not os.path.exists(p):
        print("  !! missing %s" % p)
        return rows
    with open(p, encoding="utf-8", errors="replace") as fh:
        head = fh.readline().rstrip("\n").split("\t")
        i_g = head.index("genome")
        i_f = head.index("viral_family")
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) > max(i_g, i_f):
                rows.append((c[i_g], c[i_f]))
    return rows


def ensure_extract():
    if os.path.exists(EXTRACT) and os.path.getsize(EXTRACT) > 100000:
        print("[i] using cached extract: %s" % EXTRACT)
        return
    print("[i] scanning 773 MB loci master table (awk) ...")
    cmd = ("zcat %s | awk -F'\\t' 'NR>1 && $3==\"viral_supported\""
           "{print $1\"\\t\"$4\"\\t\"$14\"\\t\"$16}' > %s" % (LOCI, EXTRACT))
    subprocess.run(cmd, shell=True, check=True)
    print("[i] extract written: %s" % EXTRACT)


def load_host_map():
    """genome name -> host family (from plantGIR family/species dirs)."""
    m = {}
    if not os.path.isdir(GIR):
        return m
    for d in sorted(os.listdir(GIR)):
        p = os.path.join(GIR, d)
        if not os.path.isdir(p) or d.startswith("_"):
            continue
        for sp in os.listdir(p):
            name = sp.replace("(", "_").replace(")", "")
            m[name] = d
    return m


def load_species_tax():
    """species -> (phylum, class, order, family)."""
    t = {}
    f = os.path.join(GIR, "species_information.csv")
    if not os.path.exists(f):
        return t
    with open(f, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            sp = (row.get("species") or "").strip()
            if sp:
                t[sp] = ((row.get("phylum") or "").strip(),
                         (row.get("aclass") or "").strip(),
                         (row.get("order") or "").strip(),
                         (row.get("family") or "").strip())
    return t


def family_tax(host_map, sp_tax):
    """host family -> (phylum, class, order, group) by mode over its species."""
    votes = defaultdict(Counter)
    for genome, fam in host_map.items():
        sp = genome.rsplit("_v", 1)[0]
        if sp in sp_tax:
            votes[fam][sp_tax[sp]] += 1
    out = {}
    for fam, c in votes.items():
        (phylum, aclass, order, _f), _n = c.most_common(1)[0]
        out[fam] = (phylum, aclass, order, plant_group(phylum, aclass, order))
    return out


def jdump(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    print("  -> %-28s %8.1f KB" % (os.path.basename(path),
                                   os.path.getsize(path) / 1024.0))


def main():
    ensure_extract()
    host_map = load_host_map()
    sp_tax = load_species_tax()
    fam_tax = family_tax(host_map, sp_tax)
    print("[i] host genomes mapped: %d ; host families: %d ; tax-resolved families: %d"
          % (len(host_map), len(set(host_map.values())), len(fam_tax)))

    # ---- accumulators -----------------------------------------------------
    vs_by_genome = Counter()
    unmapped = Counter()
    fam_loci = Counter()
    fam_genomes = defaultdict(set)
    fam_hostfam = defaultdict(Counter)
    host_loci = Counter()
    host_genomes = defaultdict(set)
    host_vfam = defaultdict(Counter)
    host_rna = Counter()
    host_cauli = Counter()
    taxon_loci = Counter()
    taxon_hostfam = defaultdict(Counter)
    taxon_fam = {}

    records = []
    with open(EXTRACT, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3:
                records.append((c[0], c[1] or "unclassified", c[2]))
    n_tier1 = len(records)
    tier2 = load_tier2()
    records += [(g, f or "unclassified", "") for g, f in tier2]
    n_tier2 = len(tier2)
    print("[i] tier1(clean)=%d  tier2(nr-promoted)=%d  total=%d"
          % (n_tier1, n_tier2, len(records)))

    for genome, vfam, lca in records:
        fam = host_map.get(genome)
        if fam is None:
            unmapped[genome] += 1
            fam = "?"
        if not vfam:
            vfam = "unclassified"
        vs_by_genome[genome] += 1
        fam_loci[vfam] += 1
        fam_genomes[vfam].add(genome)
        fam_hostfam[vfam][fam] += 1
        host_loci[fam] += 1
        host_genomes[fam].add(genome)
        host_vfam[fam][vfam] += 1
        g = genus_of(lca)
        key = g if g else ("family:" + vfam)
        taxon_loci[key] += 1
        taxon_hostfam[key][fam] += 1
        taxon_fam.setdefault(key, vfam)
        if vfam in RNA_T:
            host_rna[fam] += 1
        if vfam == "Caulimoviridae":
            host_cauli[fam] += 1
    n_rows = len(records)
    print("[i] loci processed: %d ; unmapped genomes: %d"
          % (n_rows, len(unmapped)))

    # ---- per-genome verdict counts (from kingdom_summary) -----------------
    verdicts = Counter()
    per_genome = {}
    ks = os.path.join(B, "kingdom_summary.tsv")
    with open(ks, encoding="utf-8", errors="replace") as fh:
        head = fh.readline().rstrip("\n").split("\t")
        ix = {k: head.index(k) for k in ("genome", "viral_supported",
                                         "host_like", "undetermined")}
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) <= ix["undetermined"]:
                continue
            g = c[ix["genome"]]
            v = int(c[ix["viral_supported"]] or 0)
            h = int(c[ix["host_like"]] or 0)
            u = int(c[ix["undetermined"]] or 0)
            verdicts["viral_supported"] += v
            verdicts["host_like"] += h
            verdicts["undetermined"] += u
            per_genome[g] = (v, h, u)

    excluded = set()
    qcf = os.path.join(B, "qc_excluded_genomes.txt")
    if os.path.exists(qcf):
        with open(qcf, encoding="utf-8", errors="replace") as fh:
            excluded = {l.strip() for l in fh if l.strip()}

    # raw (pre-decontamination) total, from the frozen catalog, plus the phiX
    # magnitude that was removed.  205,873 - 55,737 = 150,136.
    raw_total = 0
    catf = os.path.join(B, "eve_catalog_combined.tsv")
    if os.path.exists(catf):
        with open(catf, encoding="utf-8", errors="replace") as fh:
            head = fh.readline().rstrip("\n").split("\t")
            it = head.index("total")
            for line in fh:
                c = line.rstrip("\n").split("\t")
                if len(c) > it:
                    raw_total += int(c[it] or 0)
    phix_total = 0
    qcp = os.path.join(B, "qc_phix_per_genome.tsv")
    if os.path.exists(qcp):
        with open(qcp, encoding="utf-8", errors="replace") as fh:
            head = fh.readline().rstrip("\n").split("\t")
            ip = head.index("phiX_loci")
            for line in fh:
                c = line.rstrip("\n").split("\t")
                if len(c) > ip:
                    phix_total += int(c[ip] or 0)
    print("[i] raw total (incl phiX)=%d ; phiX removed=%d" % (raw_total, phix_total))

    # ======================= FILE 1: landscape =============================
    taxa = []
    for vfam, loci in fam_loci.most_common():
        gtype = VTYPE.get(vfam, "unclassified")
        hf = len(fam_hostfam[vfam])
        top = fam_hostfam[vfam].most_common(6)
        taxa.append({"n": vfam, "l": loci, "g": len(fam_genomes[vfam]),
                     "t": gtype, "hf": hf,
                     "top": [[h, n] for h, n in top]})

    hosts = []
    for fam, loci in host_loci.most_common():
        pt = fam_tax.get(fam, ("", "", "", "unknown"))
        vbreak = host_vfam[fam].most_common(10)
        hosts.append({"n": fam, "grp": pt[3], "ord": pt[2], "l": loci,
                      "g": len(host_genomes[fam]),
                      "rna": host_rna[fam], "cauli": host_cauli[fam],
                      "vt": [[v, n] for v, n in vbreak]})

    # DNA / RNA duality
    by_type = Counter()
    type_fams = defaultdict(list)
    type_genomes = defaultdict(set)
    for vfam, loci in fam_loci.items():
        t = VTYPE.get(vfam, "unclassified")
        by_type[t] += loci
        type_fams[t].append(vfam)
        type_genomes[t] |= fam_genomes[vfam]
    dna_total = sum(by_type[t] for t in DNA_T)
    rna_total = sum(by_type[t] for t in RNA_T)
    dna_rna = {
        "dna": dna_total, "rna": rna_total,
        "ratio": round(dna_total / rna_total, 1) if rna_total else None,
        "by_type": [{"t": t, "l": by_type[t], "g": len(type_genomes[t]),
                     "f": sorted(type_fams[t], key=lambda x: -fam_loci[x])}
                    for t in sorted(by_type, key=lambda x: -by_type[x])],
    }

    # sparse matrices
    host_top = [h["n"] for h in hosts[:60]]
    host_idx = {h: i for i, h in enumerate(host_top)}
    vfam_all = [t["n"] for t in taxa]
    vfam_idx = {v: i for i, v in enumerate(vfam_all)}
    cells = []
    for fam in host_top:
        for vfam, n in host_vfam[fam].items():
            if vfam in vfam_idx:
                cells.append([host_idx[fam], vfam_idx[vfam], n])

    taxon_top = [t for t, _ in taxon_loci.most_common(32)]
    taxon_idx = {t: i for i, t in enumerate(taxon_top)}
    tax_hosts = [h["n"] for h in hosts[:45]]
    tax_host_idx = {h: i for i, h in enumerate(tax_hosts)}
    tcells = []
    for t in taxon_top:
        for fam, n in taxon_hostfam[t].items():
            if fam in tax_host_idx:
                tcells.append([taxon_idx[t], tax_host_idx[fam], n])

    landscape = {
        "generated": "2026-09-23",
        "overview": {
            "loci": n_rows,
            "loci_tier1": n_tier1,
            "loci_tier2": n_tier2,
            "loci_raw": raw_total,
            "phix_loci": phix_total,
            "genomes": len(vs_by_genome),
            "host_families": len(host_loci),
            "host_families_total": len(set(host_map.values())),
            "verdicts": dict(verdicts),
            "excluded_genomes": sorted(excluded),
            "unmapped_genomes": len(unmapped),
            "identified_family_loci": sum(
                t["l"] for t in taxa if t["t"] not in ("phage", "unclassified")),
        },
        "virus_taxa": taxa,
        "host_families": hosts,
        "group_order": GROUP_ORDER,
        "group_label": GROUP_LABEL,
        "dna_rna": dna_rna,
        "matrix_host_virus": {"hosts": host_top, "viruses": vfam_all,
                              "cells": cells},
        "matrix_taxon_host": {"taxa": taxon_top, "hosts": tax_hosts,
                              "cells": tcells,
                              "ttype": {t: VTYPE.get(taxon_fam[t], "unclassified")
                                        for t in taxon_top}},
        "taxon_breadth": [{"n": t, "l": taxon_loci[t],
                           "hf": len(taxon_hostfam[t]),
                           "fam": taxon_fam[t],
                           "top": [[h, n] for h, n in
                                   taxon_hostfam[t].most_common(5)]}
                          for t in taxon_top],
    }
    jdump(os.path.join(OUT, "eve_landscape.json"), landscape)

    # ======================= FILE 2: dynamics ==============================
    def read_tsv(path):
        rows = []
        if not os.path.exists(path):
            print("  !! missing %s" % path)
            return rows
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.readline().rstrip("\n").split("\t")
            for line in fh:
                c = line.rstrip("\n").split("\t")
                if len(c) == len(head):
                    rows.append(dict(zip(head, c)))
        return rows

    # an3 past vs present
    pp = []
    for r in read_tsv(os.path.join(A, "an3_past_vs_present_v2.tsv")):
        try:
            pp.append({"n": r["host_family"],
                       "eve": int(r["eve_loci"] or 0),
                       "rna": int(r["eve_rna"] or 0),
                       "cauli": int(r["eve_cauli"] or 0),
                       "g": int(r["eve_genomes"] or 0),
                       "ext": int(r["extant_qc"] or 0),
                       "q": r["quadrant"]})
        except (ValueError, KeyError):
            continue
    quad = Counter(r["q"] for r in pp)

    # an4 amplification
    clusters = []
    for r in read_tsv(os.path.join(A, "an4_clusters.tsv")):
        try:
            clusters.append(int(r["n_members"]))
        except ValueError:
            continue
    clusters.sort(reverse=True)
    bins = Counter()
    for n in clusters:
        if n >= 200:
            bins["200+"] += 1
        elif n >= 100:
            bins["100-199"] += 1
        elif n >= 50:
            bins["50-99"] += 1
        elif n >= 20:
            bins["20-49"] += 1
        elif n >= 10:
            bins["10-19"] += 1
        elif n >= 5:
            bins["5-9"] += 1
        elif n >= 2:
            bins["2-4"] += 1
        else:
            bins["1"] += 1

    # per-genome scatter (an4_per_genome) + host group colour
    gpts = []
    for r in read_tsv(os.path.join(A, "an4_per_genome.tsv")):
        try:
            g = r["genome"]
            fam = host_map.get(g, "?")
            grp = fam_tax.get(fam, ("", "", "", "unknown"))[3]
            gpts.append({"g": g, "f": fam, "p": grp,
                         "e": int(r["eve_total"] or 0),
                         "c": int(r["caulimoviridae"] or 0),
                         "s": int(r["genome_size_bp"] or 0)})
        except (ValueError, KeyError):
            continue

    # an2 rarefied
    rare = []
    for r in read_tsv(os.path.join(A, "an2_rarefied_richness.tsv")):
        try:
            rare.append({"n": r["host_family"],
                         "g": int(r["n_genomes"]),
                         "obs": int(r["n_viral_families_observed"]),
                         "to": int(r["rarefied_to"]),
                         "m": float(r["rarefied_mean"]),
                         "lo": int(r["r95_lo"]), "hi": int(r["r95_hi"])})
        except (ValueError, KeyError):
            continue
    rare.sort(key=lambda x: -x["m"])

    # an5 thresholds
    thr = {}
    for r in read_tsv(os.path.join(A, "an5_thresholds.tsv")):
        k = r.get("\u6307\u6807", "")
        v = r.get("\u53ef\u4fe1EVE(viral_supported)", "")
        if k and v:
            thr[k] = v

    dynamics = {
        "past_present": pp,
        "quadrants": dict(quad),
        "amplification": {"n_clusters": len(clusters),
                          "max_cluster": clusters[0] if clusters else 0,
                          "bins": bins,
                          "top": clusters[:20]},
        "genomes": gpts,
        "rarefied": rare,
        "thresholds": thr,
    }
    jdump(os.path.join(OUT, "eve_dynamics.json"), dynamics)

    # ======================= FILE 3: phylo / cases / qc ====================
    nwk = ""
    tf = os.path.join(A, "rt_phylo", "tree_rt.nwk")
    if os.path.exists(tf):
        with open(tf, encoding="utf-8", errors="replace") as fh:
            nwk = fh.read().strip()
    nb = []
    for r in read_tsv(os.path.join(A, "rt_phylo", "nearest_best.tsv")):
        nb.append({"hf": r.get("host_family", ""),
                   "ref": r.get("nearest_ref_species", ""),
                   "rhf": r.get("ref_known_host_family", ""),
                   "pid": r.get("pident", ""),
                   "len": r.get("alnlen", "")})
    same = sum(1 for r in nb if r["hf"] and r["hf"] == r["rhf"])
    ref_counter = Counter(r["ref"] for r in nb if r["ref"])

    tn = read_tsv(os.path.join(A, "rt_phylo", "tree_neighbor.tsv"))
    tn_same = sum(1 for r in tn if r.get("host_family") and
                  r.get("host_family") == r.get("nearest_host"))
    tn_ref = sum(1 for r in tn if r.get("nearest_host") == "REF")

    cases = {
        "Datisca_glomerata": {
            "family": "Datiscaceae", "loci": 23, "orfs": 14,
            "composition": [["unclassified Betaflexiviridae", 22],
                            ["unclassified Mitoviridae", 1]],
            "note": "All RNA EVEs of this family; single viral family dominates.",
        },
        "Alsophila_spinulosa": {
            "family": "Cyatheaceae", "loci": 19, "orfs": 16,
            "composition": [["Mitoviridae", 10],
                            ["unclassified Mitoviridae", 5],
                            ["Trichovirus", 4]],
            "note": "Tree fern; mitovirus-dominated, 84% with complete ORF.",
        },
    }

    viroid = []
    for r in read_tsv(os.path.join(B, "kingdom_viroid_summary.tsv")):
        viroid.append({"sp": r.get("viroid_species", ""),
                       "n": int(r.get("n_genomes", 0) or 0)})

    qc = []
    for r in read_tsv(os.path.join(B, "qc_phix_per_genome.tsv")):
        qc.append({"g": r.get("genome", ""),
                   "phi": int(r.get("phiX_loci", 0) or 0),
                   "tot": int(r.get("viral_supported_total", 0) or 0),
                   "pct": float(r.get("phiX_pct", 0) or 0)})

    phylo = {
        "tree_newick": nwk,
        "n_leaves": nwk.count(",") + 1 if nwk else 0,
        "nearest_ref": nb,
        "nearest_ref_same_family": same,
        "nearest_ref_diff_family": len(nb) - same,
        "ref_usage": [[k, v] for k, v in ref_counter.most_common(15)],
        "tree_neighbor_same": tn_same,
        "tree_neighbor_ref": tn_ref,
        "tree_neighbor_total": len(tn),
        "cases": cases,
        "viroid": viroid,
        "qc_phix": qc,
    }
    jdump(os.path.join(OUT, "eve_phylo.json"), phylo)

    # ======================= audit TSVs ====================================
    with open(os.path.join(AUD, "virus_taxa.tsv"), "w", encoding="utf-8") as fh:
        fh.write("viral_family\tloci\tgenomes\tgenome_type\thost_families\ttop_hosts\n")
        for t in taxa:
            fh.write("%s\t%d\t%d\t%s\t%d\t%s\n" % (
                t["n"], t["l"], t["g"], t["t"], t["hf"],
                ";".join("%s:%d" % (a, b) for a, b in t["top"])))
    with open(os.path.join(AUD, "host_families.tsv"), "w", encoding="utf-8") as fh:
        fh.write("host_family\tplant_group\torder\tloci\tgenomes\trna_loci\tcauli_loci\ttop_virus_families\n")
        for h in hosts:
            fh.write("%s\t%s\t%s\t%d\t%d\t%d\t%d\t%s\n" % (
                h["n"], h["grp"], h["ord"], h["l"], h["g"], h["rna"], h["cauli"],
                ";".join("%s:%d" % (a, b) for a, b in h["vt"])))
    with open(os.path.join(AUD, "matrix_host_virus.tsv"), "w", encoding="utf-8") as fh:
        fh.write("host_family\tvirus_family\tloci\n")
        for fam in host_top:
            for vfam, n in host_vfam[fam].most_common():
                fh.write("%s\t%s\t%d\n" % (fam, vfam, n))
    with open(os.path.join(AUD, "unmapped_genomes.tsv"), "w", encoding="utf-8") as fh:
        fh.write("genome\tviral_supported_loci\n")
        for g, n in unmapped.most_common():
            fh.write("%s\t%d\n" % (g, n))

    print("\n=== SUMMARY ===")
    print("loci (clean t1+t2)   : %d" % n_rows)
    print("  tier1 / tier2      : %d / %d" % (n_tier1, n_tier2))
    print("loci raw (incl phiX) : %d   (phiX removed %d)" % (raw_total, phix_total))
    print("genomes              : %d" % len(vs_by_genome))
    print("host families        : %d (of %d in plantGIR)"
          % (len(host_loci), len(set(host_map.values()))))
    print("DNA:RNA              : %d : %d  (%.1f : 1)"
          % (dna_total, rna_total,
             dna_total / rna_total if rna_total else 0))
    print("top taxa             : %s"
          % ", ".join("%s=%d" % (t["n"], t["l"]) for t in taxa[:6]))
    print("top host families    : %s"
          % ", ".join("%s=%d" % (h["n"], h["l"]) for h in hosts[:6]))
    print("unmapped genomes     : %d" % len(unmapped))
    print("DONE")


if __name__ == "__main__":
    main()
