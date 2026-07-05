#!/usr/bin/env python3
"""C2b: Split Algae from Plant based on Host_lineage.

Reads Plant.tsv, moves algal-host records to Algae.tsv.
Analogous to C3_animal_subsplit.py

Usage:
  python C2b_algae_split.py -i VHostMetadata/ -o VHostMetadata/
"""
import polars as pl
import os, argparse

# Algae host indicators in Host_lineage (Latin names at various taxonomic levels)
ALGAE_PATTERNS = [
    r"(?i)\bChlorophyta\b",       # green algae
    r"(?i)\bRhodophyta\b",        # red algae
    r"(?i)\bPhaeophyceae\b",      # brown algae
    r"(?i)\bBacillariophyt",      # diatoms (Bacillariophyceae/Bacillariophyta)
    r"(?i)\bChrysophyceae\b",     # golden algae
    r"(?i)\bPhaeophyta\b",        # brown algae (alt)
    r"(?i)\bEuglenophyt",         # euglenids
    r"(?i)\bDinophyceae\b",       # dinoflagellates
    r"(?i)\bXanthophyceae\b",     # yellow-green algae
    r"(?i)\bCryptophyt",          # cryptomonads
    r"(?i)\bHaptophyt",           # haptophytes
    r"(?i)\bGlaucophyt",          # glaucophytes
    r"(?i)\bCharophyceae\b",      # stoneworts (charophyte algae, NOT land plants)
    r"(?i)\bUlvophyceae\b",       # ulvophyte green algae
    r"(?i)\bTrebouxiophyceae\b",  # trebouxiophyte green algae
    r"(?i)\bPrasinophyt",         # prasinophyte green algae
    r"(?i)\bKlebsormidiophyt",    # klebsormidiophyte algae
    r"(?i)\bZygnemophyt",         # zygnematophyte algae (desmids)
    r"(?i)\bColeochaetophyt",     # coleochaetophyte algae
]

# Land plant indicators — these MUST NOT be reclassified as algae
LAND_PLANT_PATTERNS = [
    r"(?i)\bEmbryophyta\b",
    r"(?i)\bTracheophyta\b",
    r"(?i)\bSpermatophyt",
    r"(?i)\bAngiosperm",
    r"(?i)\bMagnoliophyt",
    r"(?i)\bLiliopsida\b",
    r"(?i)\bMagnoliopsida\b",
    r"(?i)\bBryophyt",            # mosses — land plants, not algae
    r"(?i)\bMarchantiophyt",      # liverworts
    r"(?i)\bAnthocerotophyt",     # hornworts
    r"(?i)\bPolypodiophyt",       # ferns
    r"(?i)\bLycopodiophyt",       # clubmosses
    r"(?i)\bPinophyt",            # conifers
    r"(?i)\bGnetophyt",           # gnetophytes
    r"(?i)\bCycadophyt",          # cycads
    r"(?i)\bGinkgophyt",          # ginkgo
]


def is_alga(hl):
    """Check if Host_lineage indicates an algal host (not land plant)."""
    import re
    hl = str(hl)
    if not hl or hl == 'None':
        return False
    for p in ALGAE_PATTERNS:
        if re.search(p, hl):
            for lp in LAND_PLANT_PATTERNS:
                if re.search(lp, hl):
                    return False
            return True
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input_dir", required=True)
    p.add_argument("-o", "--output_dir", required=True)
    args = p.parse_args()

    plant_path = os.path.join(args.input_dir, "Plant.tsv")
    if not os.path.exists(plant_path):
        print(f"Plant.tsv not found in {args.input_dir}")
        return

    df = pl.read_csv(plant_path, separator='\t', truncate_ragged_lines=True)

    algae_mask = df.with_columns(
        pl.col("Host_lineage").fill_null("").map_elements(is_alga, return_dtype=pl.Boolean).alias("_is_algae")
    )

    algae_df = algae_mask.filter(pl.col("_is_algae")).drop("_is_algae")
    plant_df = algae_mask.filter(~pl.col("_is_algae")).drop("_is_algae")

    print(f"Plant total:        {df.height:>8,d}")
    print(f"  → Algae viruses:  {algae_df.height:>8,d}  (moved to Algae.tsv)")
    print(f"  → Land plants:    {plant_df.height:>8,d}  (kept in Plant.tsv)")

    if algae_df.height > 0:
        algae_path = os.path.join(args.output_dir, "Algae.tsv")
        algae_df.write_csv(algae_path, separator='\t')
        print(f"\n  Algae → {algae_path}")
        # Summary
        for g, cnt in algae_df.group_by("Host_Name").len().sort("len", descending=True).head(10).iter_rows():
            print(f"    Host={str(g)[:40]:40s}  {cnt:>6,d}")

    plant_df.write_csv(os.path.join(args.output_dir, "Plant.tsv"), separator='\t')
    print(f"  Plant → {args.output_dir}/Plant.tsv")


if __name__ == "__main__":
    main()
