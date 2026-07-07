#!/usr/bin/env python3
"""
Compare segmented virus detection sources: VMR vs TSV Segment column.

Usage:
  python audit_segment_sources.py \
      --tsv Plant_Virus_Full.Info.tsv \
      --vmr VMR_MSL41.tsv \
      --f2_result All_Classified_Virus_Info.tsv \
      -o audit_segment/
"""
import polars as pl
import os, argparse
from collections import defaultdict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tsv", required=True, help="Plant_Virus_Full.Info.tsv")
    p.add_argument("--vmr", required=True, help="VMR_MSL41.tsv")
    p.add_argument("--f2_result", required=True, help="F2 All_Classified_Virus_Info.tsv")
    p.add_argument("-o", "--output_dir", default="audit_segment/")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # ── 1. VMR: extract TaxIDs where Acc_List.len > 1 (multipartite species) ──
    print("[1] Parsing VMR...")
    vmr = pl.read_csv(args.vmr, separator='\t', ignore_errors=True,
                      truncate_ragged_lines=True, encoding='latin1')
    vmr = vmr.with_columns(
        pl.col("Virus GENBANK accession").str.extract_all(r"[A-Za-z_]+\d+").alias("Acc_List"),
        pl.col("Species").alias("VMR_Species"),
        pl.col("Family").alias("VMR_Family"),
        pl.col("Genus").alias("VMR_Genus"),
    ).filter(pl.col("Acc_List").is_not_null())
    vmr = vmr.with_columns(pl.col("Acc_List").list.len().alias("Num_Acc"))

    # TaxIDs from VMR where Num_Acc > 1 (multipartite by VMR definition)
    vmr_multipartite = vmr.filter(pl.col("Num_Acc") > 1).select(
        "VMR_Species", "VMR_Family", "VMR_Genus", "Num_Acc"
    ).unique()
    vmr_species_set = set(vmr_multipartite["VMR_Species"].to_list())

    # ── 2. TSV: extract TaxIDs from Segment column ──
    print("[2] Parsing TSV...")
    tsv = pl.read_csv(args.tsv, separator='\t', truncate_ragged_lines=True)
    seg_col = [c for c in tsv.columns if c.strip() in ('Segment', 'segment')]
    seg_col = seg_col[0] if seg_col else 'Segment'
    taxid_col = 'taxid' if 'taxid' in tsv.columns else 'Taxid'

    tsv_seg = tsv.filter(pl.col(seg_col).fill_null('').cast(pl.Utf8).str.strip_chars().str.len_chars() > 0)
    tsv_seg_taxids = set(tsv_seg[taxid_col].cast(pl.Utf8).to_list()) - {''}

    # ── 3. F2 result: check category assignments ──
    print("[3] Parsing F2 result...")
    f2_cols = ['Category'] if 'Category' in pl.read_csv(args.f2_result, separator='\t', n_rows=1).columns else []
    f2 = pl.read_csv(args.f2_result, separator='\t', truncate_ragged_lines=True)

    # ── 4. Write report ──
    out = os.path.join(args.output_dir, "segment_source_audit.txt")
    with open(out, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("Segment Source Audit: VMR vs TSV Segment Column\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"VMR multipartite species (Num_Acc > 1): {len(vmr_species_set):,}\n")
        f.write(f"TSV Segment column non-empty TaxIDs:     {len(tsv_seg_taxids):,}\n\n")

        # Overlap
        both = vmr_species_set & tsv_seg_taxids
        vmr_only = vmr_species_set - tsv_seg_taxids
        seg_only = tsv_seg_taxids - vmr_species_set

        f.write(f"VMR ∩ TSV:  {len(both):,}\n")
        f.write(f"VMR only:   {len(vmr_only):,}\n")
        f.write(f"Seg only:   {len(seg_only):,}\n")
        f.write(f"Total:      {len(vmr_species_set | tsv_seg_taxids):,}\n\n")

        # Seg-only details
        f.write("-" * 60 + "\n")
        f.write("SEGMENT-ONLY TaxIDs (not VMR-confirmed) — potential false positives\n")
        f.write("-" * 60 + "\n")

        seg_only_values = defaultdict(list)
        for r in tsv_seg.filter(pl.col(taxid_col).cast(pl.Utf8).is_in(list(seg_only))).iter_rows(named=True):
            tid = str(r[taxid_col])
            seg = str(r[seg_col]).strip()
            species = str(r.get('Species_NCBI', r.get('Species', '')))
            seg_only_values[tid].append((seg, species))

        # Classify each: likely legitimate vs likely false
        import re
        legit_pattern = re.compile(
            r'^(DNA[- ]?[A-Z]+\d*|RNA[- ]?\d+[a-z]?|[SLM]\d*|[A-CNSR]\b|' +
            r'\d+(?:\s*[a-z])?$|' +
            r'component\s+[AB]|[AB]\s+component|' +
            r'DNA[- ]?[a-z]+|' +
            r'alphasatellite|betasatellite|satellite|' +
            r'R[A-Z]\d+|' +
            r'putative\s+RNA|' +
            r'\d+\s*\(largest\))$', re.IGNORECASE)
        false_pattern = re.compile(
            r'^(CP|RdRp|HSP70|AC1|Polyprotein|TGB|Nuclear\s+shuttle|' +
            r'#[sS]eq\d+|seq\d+|Pathogroup\s+\w+|' +
            r'component\s+\d+|putative)$', re.IGNORECASE)

        legit_count, false_count, unknown_count = 0, 0, 0

        for tid in sorted(seg_only):
            vals = seg_only_values[tid]
            seg_str = vals[0][0]
            species = vals[0][1]

            if legit_pattern.match(seg_str):
                tag = "  LEGIT"
                legit_count += 1
            elif false_pattern.match(seg_str):
                tag = "  FALSE"
                false_count += 1
            else:
                tag = "  UNKN"
                unknown_count += 1

            n_records = len(tsv_seg.filter(pl.col(taxid_col).cast(pl.Utf8) == tid))
            f.write(f"[{tag}] TaxID={tid:>10s}  Seg={seg_str:30s}  Records={n_records:>6,d}  Species={species[:50]}\n")

        f.write(f"\n  LEGIT: {legit_count}  FALSE: {false_count}  UNKNOWN: {unknown_count}\n")

    print(f"Done -> {out}")


if __name__ == "__main__":
    main()
