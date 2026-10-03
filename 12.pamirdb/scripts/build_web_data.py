"""
Convert predictions_v7_annotated.json into web-optimized data files.
Outputs:
  - data/web/predictions.js    (compact predictions, pre-grouped)
  - data/web/summary.js         (stats, species, families)
  - data/web/viruses.js         (virus browse data, grouped by family)
  - data/web/mirnas.js          (miRNA index, grouped by species)
"""
import json, sys
from pathlib import Path
from collections import defaultdict, Counter

DATA_DIR = Path(__file__).parent.parent / "data"
WEB_DIR = DATA_DIR / "web"


def build():
    WEB_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading predictions...")
    with open(DATA_DIR / "predictions_v7_annotated.json") as f:
        preds = json.load(f)

    with open(DATA_DIR / "virus_genomes" / "viruses_full.json") as f:
        viruses = json.load(f)

    with open(DATA_DIR / "mirna" / "plant_mirnas_full.json") as f:
        mirnas = json.load(f)

    results = preds.get("results", preds if isinstance(preds, list) else [])

    # ── Summary stats ──
    species_counts = Counter()
    family_counts = Counter()
    gene_counts = Counter()
    targeting_stats = Counter()
    miRNA_index = defaultdict(list)  # species -> [mirna_ids]
    virus_family_index = defaultdict(lambda: {"viruses": [], "count": 0})  # family -> {viruses: [(vid, name, count)], total_count}

    virus_hit_counts = Counter()  # vid -> prediction count
    for r in results:
        vid = r.get("target_virus_id", "")
        virus_hit_counts[vid] += 1

    # Fix missing species names by lookup
    mirna_species_map = {mid: info.get("species_name", "?") for mid, info in mirnas.items()}
    mirna_family_map = {}  # for later use
    virus_family_map = {vid: vmeta.get("family", "?") for vid, vmeta in viruses.items()}

    for r in results:
        mid = r.get("mirna_id", "")
        sp = r.get("mirna_species_name", "") or mirna_species_map.get(mid, "?")
        r["mirna_species_name"] = sp  # fix in-place
        species_counts[sp] += 1
        vf = r.get("target_virus_family", "") or "?"
        family_counts[vf] += 1
        targeting_stats[r.get("targeting_status", "no_annotation")] += 1
        gene = r.get("target_gene", "")
        product = r.get("target_product", "")
        if gene:
            gene_counts[f"{gene}: {product}"] += 1

    # miRNA index
    for mid, info in mirnas.items():
        sp = info.get("species_name", "?")
        miRNA_index[sp].append({"id": mid, "seq": info["sequence"], "len": info.get("length", len(info.get("sequence", "")))})

    # Virus index by family
    for vid, vmeta in viruses.items():
        fam = vmeta.get("family", "unknown")
        if not fam:
            fam = "unclassified"
        hosts = vmeta.get("hosts", [])
        hit_count = virus_hit_counts.get(vid, 0)
        entry = {
            "id": vid,
            "name": vmeta.get("name", vid),
            "accession": vmeta.get("accession", ""),
            "length": vmeta.get("genome_length", 0),
            "hosts": hosts[:5],  # top 5 hosts for display
            "n_hosts": len(hosts),
            "predictions": hit_count,
        }
        virus_family_index[fam]["viruses"].append(entry)
        virus_family_index[fam]["count"] += hit_count

    # Filter families with hits
    virus_family_index = {k: v for k, v in virus_family_index.items() if v["count"] > 0}

    # Sort viruses within families by prediction count
    for fam in virus_family_index:
        virus_family_index[fam]["viruses"].sort(key=lambda x: -x["predictions"])

    # ── Save compact JS data ──

    # Summary
    summary = {
        "total_pairs": preds.get("total_pairs", 0),
        "total_predictions": len(results),
        "runtime_minutes": preds.get("runtime_minutes", 0),
        "n_mirna_species": len(species_counts),
        "n_virus_families": len(family_counts),
        "n_matched_species": preds.get("summary", {}).get("species_matched", len(species_counts)),
        "targeting_stats": dict(targeting_stats),
    }
    with open(WEB_DIR / "summary.js", "w", encoding="utf-8") as f:
        f.write("window.PAMIRDB_SUMMARY=" + json.dumps(summary, ensure_ascii=False) + ";")

    # Species stats
    species_list = [{"name": s, "count": c} for s, c in species_counts.most_common()]
    with open(WEB_DIR / "species.js", "w", encoding="utf-8") as f:
        f.write("window.PAMIRDB_SPECIES=" + json.dumps(species_list, ensure_ascii=False) + ";")

    # Family stats
    family_list = [
        {"family": f, "count": c, "n_viruses": len(virus_family_index.get(f, {}).get("viruses", []))}
        for f, c in family_counts.most_common()
    ]
    with open(WEB_DIR / "families.js", "w", encoding="utf-8") as f:
        f.write("window.PAMIRDB_FAMILIES=" + json.dumps(family_list, ensure_ascii=False) + ";")

    # Top genes
    gene_list = [{"gene": g, "count": c} for g, c in gene_counts.most_common(50)]
    with open(WEB_DIR / "genes.js", "w", encoding="utf-8") as f:
        f.write("window.PAMIRDB_GENES=" + json.dumps(gene_list, ensure_ascii=False) + ";")

    # miRNA index
    mirna_out = {sp: sorted(ids, key=lambda x: x["id"]) for sp, ids in miRNA_index.items()}
    with open(WEB_DIR / "mirnas.js", "w", encoding="utf-8") as f:
        f.write("window.PAMIRDB_MIRNAS=" + json.dumps(mirna_out, ensure_ascii=False) + ";")

    # Predictions (compact: group by miRNA)
    pred_by_mirna = defaultdict(list)
    for r in results:
        pred_by_mirna[r["mirna_id"]].append({
            "v": r.get("target_virus_id", ""),
            "vn": r.get("target_virus_name", "")[:60],
            "vf": r.get("target_virus_family", ""),
            "ts": r.get("target_start", 0),
            "te": r.get("target_end", 0),
            "l": r.get("consensus_level", "LOW"),
            "n": r.get("num_algorithms", 0),
            "e": r.get("best_energy", 0),
            "sg": r.get("seed_quality_score", 0),
            "tg": r.get("target_gene", ""),
            "tp": r.get("target_product", ""),
            "st": r.get("targeting_status", ""),
        })
    with open(WEB_DIR / "predictions.js", "w", encoding="utf-8") as f:
        f.write("window.PAMIRDB_PREDICTIONS=" + json.dumps(dict(pred_by_mirna), ensure_ascii=False) + ";")

    # Virus index
    vf_sorted = sorted(virus_family_index.items(), key=lambda x: -x[1]["count"])
    with open(WEB_DIR / "viruses.js", "w", encoding="utf-8") as f:
        f.write("window.PAMIRDB_VIRUSES=" + json.dumps(vf_sorted, ensure_ascii=False) + ";")

    # File sizes
    for fname in ["summary.js", "species.js", "families.js", "genes.js", "mirnas.js", "predictions.js", "viruses.js"]:
        fp = WEB_DIR / fname
        print(f"  {fname}: {fp.stat().st_size / 1024:.0f} KB")

    print(f"\n  Saved to {WEB_DIR}")
    print(f"  Predictions: {len(results)}")
    print(f"  miRNA species: {len(species_counts)}")
    print(f"  Virus families: {len(family_counts)}")


if __name__ == "__main__":
    build()
