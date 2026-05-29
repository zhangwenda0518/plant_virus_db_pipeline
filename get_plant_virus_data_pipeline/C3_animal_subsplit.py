# -*- coding: utf-8 -*-
"""
C3: Split Animal category into Mammalia/Aves/Insecta/Arachnida/Animal_other.

Usage:
  python C3_animal_subsplit.py --input Animal.tsv --output_dir classified/

Based on Host_lineage Class field (index 3 after semicolon split).
"""
import polars as pl
import os
import argparse


def subsplit_animal(input_path, output_dir):
    """Split Animal.tsv by host class into sub-category TSVs."""
    os.makedirs(output_dir, exist_ok=True)

    print(f"[1] Loading {input_path} ...")
    df = pl.read_csv(input_path, separator='\t', truncate_ragged_lines=True)

    # Parse Host_lineage Class (index 3)
    hp = pl.col("Host_lineage") + ";;;;;;;;"
    df = df.with_columns([
        hp.str.split(";").list.get(1).str.strip_chars().alias("H_Kingdom"),
        hp.str.split(";").list.get(3).str.strip_chars().alias("H_Class"),
        hp.str.split(";").list.get(4).str.strip_chars().alias("H_Order"),
    ])

    total = df.height
    print(f"    Loaded {total:,} records")

    # Define sub-category rules
    splits = {
        "Mammalia.tsv":   pl.col("H_Class") == "Mammalia",
        "Aves.tsv":       pl.col("H_Class") == "Aves",
        "Insecta.tsv":    pl.col("H_Class") == "Insecta",
        "Arachnida.tsv":  pl.col("H_Class") == "Arachnida",
    }

    # Apply splits
    results = {}
    remaining = df.clone()

    for filename, condition in splits.items():
        subset = df.filter(condition)
        # Remove helper columns, keep originals
        orig_cols = [c for c in subset.columns if not c.startswith("H_")]
        subset = subset.select(orig_cols)
        outpath = os.path.join(output_dir, filename)
        subset.write_csv(outpath, separator='\t')
        results[filename] = subset.height
        print(f"    {filename:20s}: {subset.height:>10,d} records")

    # Everything else goes to Animal_other
    all_matched = df.filter(
        pl.any_horizontal([list(splits.values())[i] for i in range(len(splits))])
    )
    other = df.join(all_matched, on=df.columns, how="anti")
    orig_cols = [c for c in other.columns if not c.startswith("H_")]
    other = other.select(orig_cols)
    outpath = os.path.join(output_dir, "Animal_other.tsv")
    other.write_csv(outpath, separator='\t')
    results["Animal_other.tsv"] = other.height
    print(f"    Animal_other.tsv    : {other.height:>10,d} records")

    # Verify
    split_total = sum(results.values())
    print(f"\n    Total split: {split_total:,} / {total:,} ({split_total/total*100:.1f}%)")
    if split_total != total:
        print(f"    WARNING: {total - split_total} records unaccounted!")

    # Class distribution within Mammalia/Aves/Insecta/Arachnida
    print("\n[2] Order-level breakdown:")
    for filename in ["Insecta.tsv", "Arachnida.tsv"]:
        subpath = os.path.join(output_dir, filename)
        if os.path.exists(subpath):
            sub = pl.read_csv(subpath, separator='\t', truncate_ragged_lines=True)
            hp2 = pl.col("Host_lineage") + ";;;;;;;;"
            sub = sub.with_columns(hp2.str.split(";").list.get(4).str.strip_chars().alias("H_Order"))
            print(f"  {filename}:")
            for r in sub.group_by("H_Order").len().sort("len", descending=True).head(10).iter_rows():
                print(f"    {str(r[0]):30s} {r[1]:>10,d}")

    print(f"\nDone. Output in {output_dir}/")
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Split Animal.tsv by host class")
    p.add_argument("--input", "-i", required=True, help="Animal.tsv path")
    p.add_argument("--output_dir", "-o", default="classified/", help="Output directory")
    args = p.parse_args()
    subsplit_animal(args.input, args.output_dir)
