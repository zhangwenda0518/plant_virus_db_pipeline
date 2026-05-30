# -*- coding: utf-8 -*-
"""
Summarize classification results from C9 output (*.classified.tsv).

Outputs 4 tables:
  1. Per-level unique taxa + NA rate
  2. Per-level top-N dominant taxa × Predicted_Host breakdown
  3. Predicted_Host × taxonomic level cross-table
  4. Confidence distribution per level

Usage:
  python 8_summary_stats.py -i classified/ -o classification_summary_stats.txt
"""
import polars as pl
import os, argparse

LEVELS = ["Realm", "Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"]


def summarize(input_dir, output_path):
    # Load all classified TSVs
    dfs = []
    for fname in sorted(os.listdir(input_dir)):
        if not fname.endswith('.classified.tsv'):
            continue
        path = os.path.join(input_dir, fname)
        df = pl.read_csv(path, separator='\t', truncate_ragged_lines=True)
        dfs.append(df)

    if not dfs:
        print(f"No *.classified.tsv found in {input_dir}")
        return

    df = pl.concat(dfs, how="diagonal")
    total = df.height
    print(f"Loaded {total:,} contigs from {len(dfs)} files")

    with open(output_path, 'w', encoding='utf-8') as out:

        # ──────────────────────────────────────────────
        # Table 1: Per-level unique taxa + NA rate
        # ──────────────────────────────────────────────
        out.write("=" * 70 + "\n")
        out.write("TABLE 1: Taxonomic Level Summary\n")
        out.write("=" * 70 + "\n")
        out.write(f"{'Level':10s} {'Unique':>10s} {'NA_Count':>10s} {'NA_Pct':>8s}\n")
        for lvl in LEVELS:
            vals = df[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            na = vals.str.len_chars() == 0
            na_n = na.sum()
            unique = vals.filter(~na).n_unique()
            out.write(f"{lvl:10s} {unique:>10,d} {na_n:>10,d} {na_n/total*100:>7.1f}%\n")

        # ──────────────────────────────────────────────
        # Table 2: Per-level Top-20 with Predicted_Host breakdown
        # ──────────────────────────────────────────────
        for lvl in LEVELS:
            out.write(f"\n{'='*70}\n")
            out.write(f"TABLE 2.{LEVELS.index(lvl)+1}: {lvl} Top-20\n")
            out.write(f"{'='*70}\n")

            vals = df[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            df_lvl = df.with_columns(vals.alias("_val")).filter(pl.col("_val") != "")

            counts = df_lvl.group_by("_val").agg(
                pl.len().alias("Total"),
                *[pl.col("Predicted_Host").str.contains(c).sum().alias(c)
                  for c in sorted(df_lvl["Predicted_Host"].unique().to_list())]
            ).sort("Total", descending=True).head(20)

            # Header
            cats = sorted(df_lvl["Predicted_Host"].unique().to_list())
            header = f"{lvl:40s} {'Total':>8s}" + "".join(f" {c:>10s}" for c in cats)
            out.write(header + "\n" + "-" * len(header) + "\n")
            for r in counts.iter_rows(named=True):
                name = str(r["_val"])[:38]
                tot = r["Total"]
                parts = "".join(f" {r.get(c, 0):>10,d}" for c in cats)
                out.write(f"{name:40s} {tot:>8,d}{parts}\n")

        # ──────────────────────────────────────────────
        # Table 3: Predicted_Host × taxonomic level
        # ──────────────────────────────────────────────
        out.write(f"\n{'='*70}\n")
        out.write(f"TABLE 3: Predicted_Host × Taxonomic Levels\n")
        out.write(f"{'='*70}\n")

        cats = sorted(df["Predicted_Host"].unique().to_list())
        header = f"{'Category':20s} {'Contigs':>10s}" + "".join(f"   {l[:4]}_Uniq" for l in LEVELS)
        out.write(header + "\n" + "-" * len(header) + "\n")

        for cat in cats:
            cdf = df.filter(pl.col("Predicted_Host") == cat)
            uniqs = []
            for lvl in LEVELS:
                vals = cdf[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
                uniqs.append(vals.filter(vals.str.len_chars() > 0).n_unique())
            parts = "".join(f" {u:>10,d}" for u in uniqs)
            out.write(f"{cat:20s} {cdft.height:>10,d}{parts}\n")

        # ──────────────────────────────────────────────
        # Table 4: Confidence distribution per level
        # ──────────────────────────────────────────────
        out.write(f"\n{'='*70}\n")
        out.write(f"TABLE 4: Confidence Distribution Per Level\n")
        out.write(f"{'='*70}\n")

        conf_levels = ["High", "Medium", "Low (Singleton/Rare)", "Low (Shared Genus)", "Unknown"]
        header = f"{'Level':10s}" + "".join(f" {c:>12s}" for c in conf_levels)
        out.write(header + "\n" + "-" * len(header) + "\n")

        for lvl in LEVELS:
            vals = df[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            # Only count records where this level has a non-NA value
            df_lvl = df.filter(vals.str.len_chars() > 0)
            parts = []
            for cl in conf_levels:
                cnt = df_lvl.filter(pl.col("Confidence_Level") == cl).height
                parts.append(f" {cnt:>12,d}")
            out.write(f"{lvl:10s}" + "".join(parts) + "\n")

        # Total summary row
        parts = []
        for cl in conf_levels:
            cnt = df.filter(pl.col("Confidence_Level") == cl).height
            parts.append(f" {cnt:>12,d}")
        out.write(f"{'TOTAL':10s}" + "".join(parts) + "\n")

    print(f"Done -> {output_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Summarize C9 classification results")
    p.add_argument("-i", "--input_dir", default="classified/")
    p.add_argument("-o", "--output", default="classification_summary_stats.txt")
    args = p.parse_args()
    summarize(args.input_dir, args.output)
