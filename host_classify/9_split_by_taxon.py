# -*- coding: utf-8 -*-
"""
Split classified contigs by Family and Genus within each Predicted_Host.

Output per-category directory:
  {category}/
    by_family/{Family}.fasta         — per-family sequences
    by_family/{Family}_summary.txt   — per-family stats
    by_genus/{Genus}.fasta           — per-genus sequences
    by_genus/{Genus}_summary.txt     — per-genus stats
    index_summary.txt                — overview with per-taxon counts

Usage:
  python 9_split_by_taxon.py -i host_classify/ -f contigs.fasta -o split_output/
"""
import polars as pl
import os, argparse
from collections import defaultdict


def load_fasta_dict(fasta_path):
    """Load FASTA into {id: seq} dict."""
    if not fasta_path or not os.path.exists(fasta_path):
        return {}
    seqs = {}
    cid = None
    cur = []
    with open(fasta_path, 'r') as f:
        for line in f:
            if line.startswith('>'):
                if cid:
                    seqs[cid] = ''.join(cur)
                cid = line[1:].strip().split()[0]
                cur = []
            else:
                cur.append(line.strip().upper())
        if cid:
            seqs[cid] = ''.join(cur)
    return seqs


def write_fasta(seqs, acc_set, out_path):
    """Write FASTA for given accession set."""
    n = 0
    with open(out_path, 'w') as f:
        for acc in sorted(acc_set):
            if acc in seqs:
                f.write(f">{acc}\n{seqs[acc]}\n")
                n += 1
    return n


def main():
    p = argparse.ArgumentParser(description="Split classified contigs by Family/Genus")
    p.add_argument("-i", "--input_dir", required=True,
                   help="Directory with *.classified.tsv files (C9 output)")
    p.add_argument("-f", "--fasta", required=True,
                   help="FASTA file with contig sequences")
    p.add_argument("-o", "--output_dir", default="split_by_taxon/")
    p.add_argument("--min_contigs", type=int, default=10,
                   help="Minimum contigs per taxon to create separate FASTA (smaller grouped)")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    seqs = load_fasta_dict(args.fasta)
    print(f"Loaded {len(seqs):,} sequences from FASTA")

    # Load all classified TSVs
    dfs = []
    for fname in sorted(os.listdir(args.input_dir)):
        if not fname.endswith('.classified.tsv'):
            continue
        df = pl.read_csv(os.path.join(args.input_dir, fname), separator='\t', truncate_ragged_lines=True)
        dfs.append(df)
    df = pl.concat(dfs, how="diagonal")
    print(f"Loaded {df.height:,} classified contigs\n")

    cats = sorted(df["Predicted_Host"].unique().to_list())

    # Global index
    index_path = os.path.join(args.output_dir, "index_summary.txt")
    with open(index_path, 'w', encoding='utf-8') as idx:
        idx.write(f"Taxon-Split Classification Summary\n{'='*60}\n\n")

        for cat in cats:
            cdf = df.filter(pl.col("Predicted_Host") == cat)
            if cdf.height == 0:
                continue

            cat_dir = os.path.join(args.output_dir, cat)
            fam_dir = os.path.join(cat_dir, "by_family")
            gen_dir = os.path.join(cat_dir, "by_genus")
            os.makedirs(fam_dir, exist_ok=True)
            os.makedirs(gen_dir, exist_ok=True)

            idx.write(f"{'─'*50}\n{cat}  —  {cdf.height:,} contigs\n{'─'*50}\n")

            # ── By Family ──
            fam_counts = cdf.group_by("Family").agg(pl.len().alias("N")).sort("N", descending=True)
            other_fam_accs = set()

            fam_idx = []
            for r in fam_counts.iter_rows(named=True):
                fam = str(r["Family"]).strip() if r["Family"] else "NA"
                n = r["N"]
                if fam == "NA":
                    continue
                fam_idx.append((fam, n))
                if n >= args.min_contigs:
                    accs = set(cdf.filter(pl.col("Family") == fam)["contig_id"].to_list())
                    n_written = write_fasta(seqs, accs, os.path.join(fam_dir, f"{fam}.fasta"))
                    with open(os.path.join(fam_dir, f"{fam}_summary.txt"), 'w') as sf:
                        sf.write(f"Family: {fam}\nContigs: {n:,}\nFASTA: {n_written:,} sequences\n")
                        # Top genera in this family
                        top_gen = cdf.filter(pl.col("Family") == fam).group_by("Genus").agg(pl.len().alias("N")).sort("N", descending=True).head(10)
                        sf.write(f"\nTop Genera:\n")
                        for gr in top_gen.iter_rows(named=True):
                            sf.write(f"  {str(gr['Genus']):40s} {gr['N']:>8,d}\n")
                else:
                    other_fam_accs |= set(cdf.filter(pl.col("Family") == fam)["contig_id"].to_list())

            # Small families grouped
            if other_fam_accs:
                write_fasta(seqs, other_fam_accs, os.path.join(fam_dir, "_other_small_families.fasta"))

            # Family index
            idx.write(f"\n  Families ({len(fam_idx)}):\n")
            for fam, n in fam_idx[:20]:
                idx.write(f"    {fam:40s} {n:>8,d}\n")

            # ── By Genus ──
            gen_counts = cdf.group_by("Genus").agg(pl.len().alias("N")).sort("N", descending=True)
            other_gen_accs = set()
            gen_list = []

            for r in gen_counts.iter_rows(named=True):
                gen = str(r["Genus"]).strip() if r["Genus"] else "NA"
                n = r["N"]
                if gen == "NA":
                    continue
                gen_list.append((gen, n))
                if n >= args.min_contigs:
                    accs = set(cdf.filter(pl.col("Genus") == gen)["contig_id"].to_list())
                    n_written = write_fasta(seqs, accs, os.path.join(gen_dir, f"{gen}.fasta"))
                    with open(os.path.join(gen_dir, f"{gen}_summary.txt"), 'w') as sf:
                        sf.write(f"Genus: {gen}\nContigs: {n:,}\nFASTA: {n_written:,} sequences\n")
                        # Top species in this genus
                        top_sp = cdf.filter(pl.col("Genus") == gen).group_by("Species").agg(pl.len().alias("N")).sort("N", descending=True).head(10)
                        sf.write(f"\nTop Species:\n")
                        for sr in top_sp.iter_rows(named=True):
                            sf.write(f"  {str(sr['Species']):50s} {sr['N']:>8,d}\n")
                else:
                    other_gen_accs |= set(cdf.filter(pl.col("Genus") == gen)["contig_id"].to_list())

            if other_gen_accs:
                write_fasta(seqs, other_gen_accs, os.path.join(gen_dir, "_other_small_genera.fasta"))

            idx.write(f"\n  Genera ({len(gen_list)}):\n")
            for gen, n in gen_list[:30]:
                idx.write(f"    {gen:40s} {n:>8,d}\n")

            idx.write("\n")

    print(f"Done → {args.output_dir}/")
    print(f"  {index_path}")


if __name__ == "__main__":
    main()
