#!/usr/bin/env python3
"""
审计 Segmented 病毒的段名变体，区分 RefSeq 和 VMR (GenBank/ICTV) 来源。
"""
import polars as pl
import argparse
from collections import defaultdict

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tsv", required=True, help="All_Classified_Virus_Info.tsv")
    p.add_argument("--top", type=int, default=50)
    args = p.parse_args()

    df = pl.read_csv(args.tsv, separator='\t', ignore_errors=True, truncate_ragged_lines=True)
    seg = df.filter(pl.col("Category").str.starts_with("Segmented_"))

    # 按 TaxID 分组: refseq, vmr, other 三段
    data = defaultdict(lambda: {"refseq": set(), "vmr": set(), "other": set()})
    for row in seg.iter_rows(named=True):
        tax = str(row["Taxid"])
        sv = str(row.get("Segment", "")).strip()
        if not sv: continue
        clean = sv.replace(" ", "").replace("-", "").replace("_", "").upper()
        st = str(row.get("Sequence_Type", ""))
        if "RefSeq" in st:
            data[tax]["refseq"].add(clean)
        elif "ICTV" in st:
            data[tax]["vmr"].add(clean)
        else:
            data[tax]["other"].add(clean)

    # 找变体
    variants = []
    only_ref = only_vmr = both = 0
    for tax, d in data.items():
        canon = d["refseq"] | d["vmr"]
        unmatched = d["other"] - canon
        if unmatched and canon:
            variants.append((tax, d["refseq"], d["vmr"], unmatched))
            if d["refseq"] and d["vmr"]: both += 1
            elif d["refseq"]: only_ref += 1
            else: only_vmr += 1

    variants.sort(key=lambda x: len(x[3]), reverse=True)

    print(f"有段名变体的 TaxID: {len(variants)} / {len(data)}")
    print(f"  canonical 来源: 仅RefSeq={only_ref}  仅VMR={only_vmr}  两者={both}\n")
    print(f"{'TaxID':<10} {'RefSeq段名':<35} {'VMR段名':<35} {'变体':<35}")
    print("-" * 115)
    for tax, ref, vmr, other in variants[:args.top]:
        r = ", ".join(sorted(ref)[:4])
        v = ", ".join(sorted(vmr)[:4]) if vmr else "—"
        o = ", ".join(sorted(other)[:4])
        print(f"{tax:<10} {r:<35} {v:<35} {o:<35}")

    # 模式统计
    print(f"\n=== 常见段名变体模式 (前 30) ===")
    pat = defaultdict(int)
    for tax, ref, vmr, other in variants:
        canon = ref | vmr
        for o in other:
            for r in canon:
                if o in r or r in o:
                    pat[f"{r} ← {o}"] += 1
                    break
    for k, v in sorted(pat.items(), key=lambda x: -x[1])[:30]:
        print(f"  {v:>4}  {k}")

if __name__ == "__main__":
    main()
