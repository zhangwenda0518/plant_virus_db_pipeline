# -*- coding: utf-8 -*-
"""
Summarize C9 classification results.

Output (in -o directory):
  classification_summary.txt    — overall cross-category summary (4 tables)
  {Category}_summary.txt        — per-category detailed stats

Usage:
  python 8_summary_stats.py -i classified/ -o stats/
"""
import polars as pl
import os, argparse

LEVELS = ["Realm", "Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"]


def write_overall(df, out_dir):
    """Overall summary across all categories."""
    path = os.path.join(out_dir, "classification_summary.txt")
    total = df.height
    with open(path, 'w', encoding='utf-8') as out:
        out.write(f"Total contigs: {total:,}  |  Categories: {df['Predicted_Host'].n_unique()}\n")

        # ── Table 1: Per-level unique taxa + NA ──
        out.write(f"\n{'─'*70}\nTABLE 1 ─ Taxonomic Level Summary\n{'─'*70}\n")
        out.write(f"{'Level':10s} {'Unique':>10s} {'NA_Count':>10s} {'NA_Pct':>8s}\n")
        for lvl in LEVELS:
            vals = df[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            na_n = vals.str.len_chars().eq(0).sum()
            u = vals.filter(vals.str.len_chars() > 0).n_unique()
            out.write(f"{lvl:10s} {u:>10,d} {na_n:>10,d} {na_n/total*100:>7.1f}%\n")

        # ── Table 2: Per-level Top-20 × Predicted_Host ──
        cats = sorted(df["Predicted_Host"].unique().to_list())
        for lvl in LEVELS:
            out.write(f"\n{'─'*70}\nTABLE 2.{LEVELS.index(lvl)+1} ─ Top-20 {lvl}\n{'─'*70}\n")
            vals = df[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            df_l = df.with_columns(vals.alias("_val")).filter(pl.col("_val") != "")
            counts = df_l.group_by("_val").agg(
                pl.len().alias("Total"),
                *[pl.col("Predicted_Host").eq(c).sum().alias(c) for c in cats]
            ).sort("Total", descending=True).head(20)
            header = f"{lvl:40s} {'Total':>8s}" + "".join(f" {c:>10s}" for c in cats)
            out.write(header + "\n" + "-" * len(header) + "\n")
            for r in counts.iter_rows(named=True):
                name = str(r["_val"])[:38]
                parts = "".join(f" {r.get(c, 0):>10,d}" for c in cats)
                out.write(f"{name:40s} {r['Total']:>8,d}{parts}\n")

        # ── Table 3: Predicted_Host × levels ──
        out.write(f"\n{'─'*70}\nTABLE 3 ─ Predicted_Host × Taxonomic Levels\n{'─'*70}\n")
        header = f"{'Category':20s} {'Contigs':>10s}" + "".join(f"   {l[:4]}_Uniq" for l in LEVELS)
        out.write(header + "\n" + "-" * len(header) + "\n")
        for cat in cats:
            cdf = df.filter(pl.col("Predicted_Host") == cat)
            parts = "".join(f" {_nuniq(cdf, l):>10,d}" for l in LEVELS)
            out.write(f"{cat:20s} {cdf.height:>10,d}{parts}\n")

        # ── Table 4: Confidence per level ──
        out.write(f"\n{'─'*70}\nTABLE 4 ─ Confidence Distribution Per Level\n{'─'*70}\n")
        confs = ["High", "Medium", "Low (Singleton/Rare)", "Low (Shared Genus)", "Unknown"]
        header = f"{'Level':10s}" + "".join(f" {c:>12s}" for c in confs)
        out.write(header + "\n" + "-" * len(header) + "\n")
        for lvl in LEVELS:
            vals = df[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            d = df.filter(vals.str.len_chars() > 0)
            parts = "".join(f" {d.filter(pl.col('Confidence_Level')==c).height:>12,d}" for c in confs)
            out.write(f"{lvl:10s}{parts}\n")
        parts = "".join(f" {df.filter(pl.col('Confidence_Level')==c).height:>12,d}" for c in confs)
        out.write(f"{'TOTAL':10s}{parts}\n")

    print(f"  {path}")


def write_category_detail(df, cat_name, out_dir):
    """Per-category detailed stats."""
    cdf = df.filter(pl.col("Predicted_Host") == cat_name)
    n = cdf.height
    path = os.path.join(out_dir, f"{cat_name}_summary.txt")
    with open(path, 'w', encoding='utf-8') as out:
        out.write(f"{'='*60}\n")
        out.write(f"{cat_name} ─ {n:,} contigs\n")
        out.write(f"{'='*60}\n")

        # Per-level unique + NA
        out.write(f"\n─ Taxonomic Resolution ─\n")
        out.write(f"{'Level':10s} {'Unique':>10s} {'NA':>8s} {'NA%':>6s}\n")
        for lvl in LEVELS:
            vals = cdf[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            na_n = vals.str.len_chars().eq(0).sum()
            u = vals.filter(vals.str.len_chars() > 0).n_unique()
            out.write(f"{lvl:10s} {u:>10,d} {na_n:>8,d} {na_n/n*100:>5.1f}%\n")

        # Per-level Top-15
        for lvl in LEVELS:
            vals = cdf[lvl].fill_null("").cast(pl.Utf8).str.strip_chars()
            df_l = cdf.with_columns(vals.alias("_val")).filter(pl.col("_val") != "")
            top = df_l.group_by("_val").len().sort("len", descending=True).head(15)
            if top.height == 0:
                continue
            out.write(f"\n─ Top-15 {lvl} ─\n")
            for r in top.iter_rows(named=True):
                name = str(r["_val"])[:50]
                out.write(f"  {name:52s} {r['len']:>8,d}\n")

        # Confidence levels
        out.write(f"\n─ Confidence ─\n")
        for cl in ["High", "Medium", "Low (Singleton/Rare)", "Low (Shared Genus)", "Unknown"]:
            cnt = cdf.filter(pl.col("Confidence_Level") == cl).height
            if cnt > 0:
                out.write(f"  {cl:25s} {cnt:>8,d} ({cnt/n*100:.1f}%)\n")

        # Determination method breakdown
        out.write(f"\n─ Determination Level ─\n")
        for g, sdf in cdf.group_by("Determination_Level"):
            dl = str(g[0]) if g else "Unknown"
            out.write(f"  {dl:25s} {sdf.height:>8,d}\n")

        # _pass_conf
        pas = cdf.filter(pl.col("_pass_conf").eq(True)).height
        out.write(f"\n─ Pass Confidence Filter ─\n")
        out.write(f"  Pass: {pas:,} ({pas/n*100:.1f}%)\n")
        out.write(f"  Fail: {n-pas:,}\n")

    print(f"  {path}")


def _nuniq(df, col):
    vals = df[col].fill_null("").cast(pl.Utf8).str.strip_chars()
    return vals.filter(vals.str.len_chars() > 0).n_unique()


def main():
    p = argparse.ArgumentParser(description="Summarize C9 classification results")
    p.add_argument("-i", "--input_dir", default="classified/")
    p.add_argument("-o", "--output_dir", default="stats/")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    dfs = []
    for fname in sorted(os.listdir(args.input_dir)):
        if not fname.endswith('.classified.tsv'):
            continue
        path = os.path.join(args.input_dir, fname)
        dfs.append(pl.read_csv(path, separator='\t', truncate_ragged_lines=True))

    if not dfs:
        print(f"No *.classified.tsv found in {args.input_dir}")
        return

    df = pl.concat(dfs, how="diagonal")
    print(f"Loaded {df.height:,} contigs from {len(dfs)} files\n")

    # Overall summary
    print("Overall:")
    write_overall(df, args.output_dir)

    # Per-category detail
    print("\nPer-category:")
    for cat in sorted(df["Predicted_Host"].unique().to_list()):
        write_category_detail(df, cat, args.output_dir)

    print(f"\nDone → {args.output_dir}/")


if __name__ == "__main__":
    main()
