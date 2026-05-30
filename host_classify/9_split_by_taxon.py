# -*- coding: utf-8 -*-
"""
Split classified contigs hierarchically: Category → Family → Genus.

Output structure:
  {Category}/
    {Family}/
      {Family}.fasta                     — all contigs in this family
      {Family}_summary.txt               — family stats + sub-genera list
      {Genus}/
        {Genus}.fasta                    — per-genus sequences
        {Genus}_summary.txt              — per-genus stats + top species
      _other_genera/                     — genera < min_contigs merged
    _other_families/                     — small families merged

Usage:
  python 9_split_by_taxon.py -i host_classify/ -f contigs.fasta -o split_output/
"""
import polars as pl
import os, argparse
from collections import defaultdict


def load_fasta_dict(fasta_path):
    seqs = {}
    if not fasta_path or not os.path.exists(fasta_path):
        return seqs
    cid, cur = None, []
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
    n = 0
    with open(out_path, 'w') as f:
        for acc in sorted(acc_set):
            if acc in seqs:
                f.write(f">{acc}\n{seqs[acc]}\n")
                n += 1
    return n


def write_genus(cdf, genus, fam_dir, seqs, min_contigs, top_n=10):
    """Write per-genus FASTA + summary inside the family directory."""
    gdf = cdf.filter(pl.col("Genus") == genus)
    n = gdf.height
    gdir = os.path.join(fam_dir, genus)
    os.makedirs(gdir, exist_ok=True)

    accs = set(gdf["contig_id"].to_list())
    nw = write_fasta(seqs, accs, os.path.join(gdir, f"{genus}.fasta"))

    with open(os.path.join(gdir, f"{genus}_summary.txt"), 'w') as sf:
        sf.write(f"Genus: {genus}\nContigs: {n:,}\nFASTA: {nw:,} sequences\n")
        sf.write(f"\nTop Species:\n")
        sp = gdf.group_by("Species").len().sort("len", descending=True).head(top_n)
        for r in sp.iter_rows(named=True):
            sf.write(f"  {str(r['Species'])[:60]:62s} {r['len']:>8,d}\n")
    return n


def main():
    p = argparse.ArgumentParser(description="Hierarchical split by Family → Genus")
    p.add_argument("-i", "--input_dir", required=True)
    p.add_argument("-f", "--fasta", required=True)
    p.add_argument("-o", "--output_dir", default="split_by_taxon/")
    p.add_argument("--min_genus", type=int, default=10,
                   help="Minimum contigs per genus to get its own directory")
    p.add_argument("--min_family", type=int, default=5,
                   help="Minimum contigs per family to get its own directory")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    seqs = load_fasta_dict(args.fasta)
    print(f"Loaded {len(seqs):,} sequences")

    dfs = []
    for fname in sorted(os.listdir(args.input_dir)):
        if not fname.endswith('.classified.tsv'):
            continue
        dfs.append(pl.read_csv(os.path.join(args.input_dir, fname), separator='\t', truncate_ragged_lines=True))
    df = pl.concat(dfs, how="diagonal")
    print(f"Loaded {df.height:,} contigs\n")

    cats = sorted(df["Predicted_Host"].unique().to_list())
    index_path = os.path.join(args.output_dir, "index_summary.txt")

    with open(index_path, 'w', encoding='utf-8') as idx:
        idx.write(f"Taxon-Split Classification (Family → Genus)\n{'='*55}\n\n")

        for cat in cats:
            cdf = df.filter(pl.col("Predicted_Host") == cat)
            if cdf.height == 0:
                continue
            cat_dir = os.path.join(args.output_dir, cat)
            os.makedirs(cat_dir, exist_ok=True)

            idx.write(f"{'─'*45}\n{cat}  —  {cdf.height:,} contigs\n{'─'*45}\n")

            fam_counts = cdf.group_by("Family").len().sort("len", descending=True)

            for fr in fam_counts.iter_rows(named=True):
                fam = str(fr["Family"]).strip() if fr["Family"] else "NA"
                fn = fr["len"]
                if fam == "NA":
                    continue

                fcd = cdf.filter(pl.col("Family") == fam)

                if fn >= args.min_family:
                    fam_dir = os.path.join(cat_dir, fam)
                    os.makedirs(fam_dir, exist_ok=True)

                    # Family-level FASTA + summary
                    fam_accs = set(fcd["contig_id"].to_list())
                    nw = write_fasta(seqs, fam_accs, os.path.join(fam_dir, f"{fam}.fasta"))

                    with open(os.path.join(fam_dir, f"{fam}_summary.txt"), 'w') as sf:
                        sf.write(f"Family: {fam}\nContigs: {fn:,}\nFASTA: {nw:,} sequences\n")
                        sf.write(f"\nGenera ({fcd['Genus'].n_unique()}):\n")

                    # Sub-genera
                    gen_counts = fcd.group_by("Genus").len().sort("len", descending=True)
                    other_gen = set()
                    for gr in gen_counts.iter_rows(named=True):
                        gen = str(gr["Genus"]).strip() if gr["Genus"] else "NA"
                        gn = gr["len"]
                        if gen == "NA":
                            continue
                        if gn >= args.min_genus:
                            write_genus(fcd, gen, fam_dir, seqs, args.min_genus)
                            with open(os.path.join(fam_dir, f"{fam}_summary.txt"), 'a') as sf:
                                sf.write(f"  {gen:40s} {gn:>8,d}  → {gen}/")
                                sf.write(f"\n")
                        else:
                            other_gen |= set(fcd.filter(pl.col("Genus") == gen)["contig_id"].to_list())

                    # Small genera merged
                    if other_gen:
                        odir = os.path.join(fam_dir, "_other_genera")
                        os.makedirs(odir, exist_ok=True)
                        write_fasta(seqs, other_gen, os.path.join(odir, "other.fasta"))

                    # Family index line
                    idx.write(f"  {fam:40s} {fn:>8,d} contigs, {fcd['Genus'].n_unique()} genera\n")

                else:
                    # Small family → merge into _other_families
                    odir = os.path.join(cat_dir, "_other_families")
                    os.makedirs(odir, exist_ok=True)
                    fam_accs = set(fcd["contig_id"].to_list())
                    write_fasta(seqs, fam_accs, os.path.join(odir, "other.fasta"))
                    with open(os.path.join(odir, "other_summary.txt"), 'a') as sf:
                        sf.write(f"  {fam:40s} {fn:>8,d}\n")

            idx.write("\n")

    print(f"Done → {args.output_dir}/")


if __name__ == "__main__":
    main()
