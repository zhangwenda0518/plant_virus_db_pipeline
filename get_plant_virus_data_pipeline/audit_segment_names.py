#!/usr/bin/env python3
"""
审计 Segmented 病毒的段名，找出需要归一化的变体。

对于同一 TaxID，列出所有不同的 Segment 写法，标注哪些来自 RefSeq。
"""
import polars as pl
import argparse
from collections import defaultdict

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tsv", required=True, help="All_Classified_Virus_Info.tsv")
    p.add_argument("--top", type=int, default=50, help="展示前 N 个有变体的 TaxID")
    args = p.parse_args()

    df = pl.read_csv(args.tsv, separator='\t', ignore_errors=True, truncate_ragged_lines=True)

    # 只取 Segmented 记录
    seg = df.filter(pl.col("Category").str.starts_with("Segmented_"))

    # 按 TaxID 分组，收集所有 Segment 值
    taxid_segs = defaultdict(lambda: {"canonical": set(), "other": set(), "canonical_acc": []})
    is_canonical = lambda st: ("RefSeq" in str(st) or "ICTV" in str(st)) if st else False

    for row in seg.iter_rows(named=True):
        tax = str(row["Taxid"])
        seg_val = str(row.get("Segment", "")).strip()
        st = row.get("Sequence_Type", "")
        if not seg_val:
            continue
        clean = seg_val.replace(" ", "").replace("-", "").replace("_", "").upper()
        if is_canonical(st):
            taxid_segs[tax]["canonical"].add(clean)
            taxid_segs[tax]["canonical_acc"].append(row["Accession"])
        else:
            taxid_segs[tax]["other"].add(clean)

    # 找出有变体的 TaxID: canonical 和非 canonical 段名不一致
    variants = []
    for tax, data in taxid_segs.items():
        ref = data["canonical"]
        other = data["other"]
        # 其他段名中，哪些不是 canonical 的直接匹配
        unmatched = other - ref
        if unmatched and ref:
            variants.append((tax, ref, unmatched, data["canonical_acc"][:2]))

    variants.sort(key=lambda x: len(x[2]), reverse=True)

    print(f"有段名变体的 TaxID: {len(variants)} / {len(taxid_segs)} 个有RefSeq/ICTV的TaxID\n")

    print(f"{'TaxID':<12} {'RefSeq/ICTV段名':<40} {'其他段名(变体)':<40}")
    print("-" * 90)
    for tax, ref, other, accs in variants[:args.top]:
        ref_str = ", ".join(sorted(ref)[:5])
        other_str = ", ".join(sorted(other)[:5])
        print(f"{tax:<12} {ref_str:<40} {other_str:<40}")

    # 统计变体模式
    print(f"\n\n=== 常见段名变体模式 (前 30) ===")
    pattern_count = defaultdict(int)
    for tax, ref, other, _ in variants:
        for o in other:
            # 检查这个 other 是否比 canonical 少前缀
            for r in ref:
                if o in r or r in o:
                    pattern_count[f"{r} ← {o}"] += 1
                    break
    for pat, cnt in sorted(pattern_count.items(), key=lambda x: -x[1])[:30]:
        print(f"  {cnt:>4}  {pat}")


if __name__ == "__main__":
    main()
