# -*- coding: utf-8 -*-
"""
C7: Multi-level (Family, Genus, Species) host probability and confidence.
Features a mathematically rigorous dual-factor confidence model:
  1. Shannon Entropy for Exclusivity Confidence (penalizes sharing)
  2. Saturated Exponential curve for Support Confidence (penalizes low sample size)

Outputs: prediction, P(max), and multi-layer confidence metrics.

Usage:
  python C7_genus_host_probability.py -i classified_clean/ -o cross_analysis/
"""
import polars as pl
import os, argparse, csv, math
from collections import defaultdict

# Categories detected from input directory. Exclude Unknown/Environmental_NCBI/cross_species/miss.
_CAT_SKIP = {"Unknown", "Environmental_NCBI", "cross_species", "miss", "All_Processed_Records", "Animal"}


def detect_categories(input_dir):
    """Auto-detect host categories from *.tsv files in input_dir."""
    cats = []
    for f in sorted(os.listdir(input_dir)):
        if f.endswith('.tsv'):
            cat = f.replace('.tsv', '')
            if cat not in _CAT_SKIP:
                cats.append(cat)
    return cats


def parse_and_load_counts(input_dir, level_col, core_cats):
    """Compute record counts per taxon at a specific taxonomic level."""
    taxon_counts = {}
    all_taxa = set()

    for cat in core_cats:
        path = os.path.join(input_dir, f"{cat}.tsv")
        if not os.path.exists(path):
            continue

        df = pl.read_csv(path, separator='\t', truncate_ragged_lines=True)
        vp = pl.col("Virus_lineage") + ";;;;;;;;"
        target_col = vp.str.split(";").list.get(level_col).str.strip_chars()
        df = df.with_columns(target_col.alias("T"))
        df = df.filter(pl.col("T") != "")

        for r in df.group_by("T").len().iter_rows():
            taxon, cnt = r[0], r[1]
            if taxon not in taxon_counts:
                taxon_counts[taxon] = {}
            taxon_counts[taxon][cat] = cnt
            all_taxa.add(taxon)

    return taxon_counts, all_taxa


def calculate_and_save_probabilities(taxon_counts, all_taxa, level_label, output_dir, core_cats):
    """Calculate P(host), Shannon Entropy, and Dual-Factor Confidence."""
    prob_rows = []
    max_entropy = math.log2(len(core_cats)) if core_cats else 1.0

    for taxon in sorted(all_taxa):
        cat_record = taxon_counts[taxon]
        total_records = sum(cat_record.values())

        # Find predicted host (maximum probability)
        pred_host = "Unknown"
        max_p = 0.0
        for cat in core_cats:
            p = cat_record.get(cat, 0) / total_records
            if p > max_p:
                max_p = p
                pred_host = cat

        # 1. Compute Shannon Entropy (Uncertainty)
        entropy = 0.0
        for cat in core_cats:
            p = cat_record.get(cat, 0) / total_records
            if p > 0:
                entropy -= p * math.log2(p)

        # 2. Exclusivity Confidence (1.0 = strictly exclusive, 0.0 = evenly shared)
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        excl_conf = 1.0 - norm_entropy

        # 3. Support Confidence (saturated exponential to penalize singletons)
        # Reaches >95% confidence when Total_Records >= 15
        support_conf = 1.0 - math.exp(-total_records / 5.0)

        # 4. Combined Integrated Confidence Score (0.0 ~ 1.0)
        integrated_conf = excl_conf * support_conf

        # 5. Interpret confidence rating
        if total_records < 3:
            rating = "Low (Singleton/Rare)"
        elif integrated_conf >= 0.8:
            rating = "High"
        elif integrated_conf >= 0.4:
            rating = "Medium"
        else:
            rating = "Low (Shared Genus)"

        # Build row
        row = {
            level_label: taxon,
            "Predicted_Host": pred_host,
            "P_Max": max_p,
            "Integrated_Confidence": round(integrated_conf, 4),
            "Confidence_Level": rating,
            "Total_Records": total_records,
            "Shannon_Entropy": round(entropy, 4),
            "Exclusivity_Conf": round(excl_conf, 4),
            "Support_Conf": round(support_conf, 4),
        }

        for cat in core_cats:
            row[f"{cat}_Records"] = cat_record.get(cat, 0)
            row[f"P({cat})"] = round(cat_record.get(cat, 0) / total_records, 4)

        prob_rows.append(row)

    # Save to TSV
    out_path = os.path.join(output_dir, f"{level_label.lower()}_host_probability.tsv")
    fieldnames = [
        level_label, "Predicted_Host", "P_Max", "Integrated_Confidence",
        "Confidence_Level", "Total_Records", "Shannon_Entropy",
        "Exclusivity_Conf", "Support_Conf"
    ] + [f"{c}_Records" for c in core_cats] + [f"P({c})" for c in core_cats]

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, delimiter='\t', fieldnames=fieldnames)
        w.writeheader()
        w.writerows(prob_rows)

    n_high = sum(1 for r in prob_rows if 'High' in r['Confidence_Level'])
    n_med = sum(1 for r in prob_rows if r['Confidence_Level'] == 'Medium')
    n_low = sum(1 for r in prob_rows if 'Low' in r['Confidence_Level'])
    print(f"  {level_label}: {len(prob_rows)} taxa → High={n_high}, Medium={n_med}, Low={n_low} → {out_path}")


def main():
    p = argparse.ArgumentParser(description="C7: Multi-level host probability & confidence tables")
    p.add_argument("-i", "--input_dir", default="classified_clean/")
    p.add_argument("-o", "--output_dir", default="cross_analysis/")
    args = p.parse_args()

    core_cats = detect_categories(args.input_dir)
    print(f"Detected {len(core_cats)} categories: {core_cats}")
    os.makedirs(args.output_dir, exist_ok=True)

    levels = [("Species", 7), ("Genus", 6), ("Family", 5), ("Order", 4)]
    for level_label, col_idx in levels:
        print(f"\n=== {level_label} level ===")
        counts, taxa = parse_and_load_counts(args.input_dir, col_idx, core_cats)
        calculate_and_save_probabilities(counts, taxa, level_label, args.output_dir, core_cats)

    print("\nDone. All multi-level probability & confidence tables saved.")


if __name__ == "__main__":
    main()
