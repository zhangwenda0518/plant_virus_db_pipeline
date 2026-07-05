#!/usr/bin/env python3
"""
检查 Segment 列所有值 vs 黑名单，验证黑名单覆盖是否完整。

输出:
  1. 所有唯一 Segment 值，标注: BLACKLISTED / LEGIT / NEEDS_REVIEW
  2. 黑名单命中统计
  3. 未被黑名单覆盖的 Segment 值（可能漏网的假阳性）

Usage:
  python audit_segment_blacklist.py --tsv Plant_Virus_Info.full.tsv -o audit_seg_blacklist/
"""
import polars as pl
import os, argparse, re
from collections import defaultdict


# 与 F2_classify_segmented.py 一致的黑名单
BLACKLIST_PATTERN = re.compile(
    r"^(?:[0-9]+|CP|RdRp|HSP70|AC1|Polyprotein|TGB|Nuclear\s+shuttle|"
    r"putative|component\s+\d+|#[sS]eq|seq\d+|Pathogroup\s+\w+)$"
)

# 明确的合法节段名模式
LEGIT_PATTERNS = [
    re.compile(r, re.IGNORECASE) for r in [
        r"^RNA\s*\d+[a-z]?$",           # RNA1, RNA2, RNA 1, RNA1a
        r"^DNA[\s-]?[A-Z]\d*$",          # DNA-A, DNA B, DNA-A1
        r"^[SLM]\d*$",                    # L, L1, M, M2, S, S10
        r"^\d+\s*\(largest\)$",          # 1 (largest)
        r"^component\s+[AB]$",            # component A, component B
        r"^[AB]\s+component$",            # A component, B component
        r"^\d+[a-z]?$",                   # 1a, 2b (允许带小写字母)
        r"^alphasatellite$",              # alphasatellite
        r"^betasatellite$",               # betasatellite
        r"^satellite$",                   # satellite
        r"^R[A-Z]\d+$",                   # RA1, RB2
        r"^putative\s+RNA\s*\d*$",       # putative RNA, putative RNA2
        r"^genomic\s+RNA\d*$",           # genomic RNA, genomic RNA1
        r"^genomic\s+DNA\s*[A-Z]?$",     # genomic DNA, genomic DNA A
        r"^defective\s+RNA\d*$",         # defective RNA, defective RNA3
        r"^subgenomic\s+RNA\d*$",        # subgenomic RNA
        r"^DI\s*RNA\d*$",                # DI RNA, DI RNA3
        r"^[A-CNSR]+$",                   # A, B, C, NS, R (single/multi letter segment names)
    ]
]


def classify_segment_value(val: str) -> str:
    """判断单个 Segment 值是黑名单、合法、还是需要人工审查"""
    if not val or not val.strip():
        return "EMPTY"

    v = val.strip()

    # 1. 先检查黑名单
    if BLACKLIST_PATTERN.match(v):
        return "BLACKLISTED"

    # 2. 检查合法模式
    for pat in LEGIT_PATTERNS:
        if pat.match(v):
            return "LEGIT"

    # 3. 未命中任何模式 → 需要审查
    return "NEEDS_REVIEW"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tsv", required=True, help="Plant_Virus_Info.full.tsv 或 All_Classified_Virus_Info.tsv")
    p.add_argument("-o", "--output_dir", default="audit_seg_blacklist/")
    args = p.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"[1] 加载 TSV: {args.tsv}")
    df = pl.read_csv(args.tsv, separator='\t', truncate_ragged_lines=True)

    seg_col = next((c for c in df.columns if c.strip().lower() == 'segment'), 'Segment')

    # 提取所有 Segment 值并计数
    print("[2] 统计 Segment 列...")
    seg_stats = df.group_by(seg_col).agg(
        pl.len().alias("Count"),
        pl.col("Accession").first().alias("Example_Accession"),
    ).sort("Count", descending=True)

    # 如果 GenBank_Title 存在，也取示例标题
    title_col = next((c for c in df.columns if c.lower() == 'genbank_title'), None)
    if title_col:
        seg_stats = seg_stats.join(
            df.group_by(seg_col).agg(pl.col(title_col).first().alias("Example_Title")),
            on=seg_col, how="left"
        )

    # 分类每个 Segment 值
    print("[3] 分类 Segment 值...")
    results = []
    for row in seg_stats.iter_rows(named=True):
        val = row[seg_col] if row[seg_col] is not None else ""
        verdict = classify_segment_value(str(val))
        results.append({
            "Segment_Value": val,
            "Verdict": verdict,
            "Count": row["Count"],
            "Example_Accession": row.get("Example_Accession", ""),
            "Example_Title": row.get("Example_Title", ""),
        })

    result_df = pl.DataFrame(results)

    # 汇总
    verdict_summary = result_df.group_by("Verdict").agg(
        pl.col("Count").sum().alias("Total_Records"),
        pl.len().alias("Unique_Values"),
    ).sort("Total_Records", descending=True)

    total_records = result_df["Count"].sum()
    total_unique = result_df.height

    # ── 输出报告 ──
    out = os.path.join(args.output_dir, "segment_blacklist_audit.txt")
    with open(out, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("Segment 列黑名单审查报告\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"总记录数: {total_records:,}\n")
        f.write(f"唯一 Segment 值: {total_unique:,}\n\n")

        f.write("-" * 60 + "\n")
        f.write("汇总\n")
        f.write("-" * 60 + "\n")
        f.write(f"{'Verdict':<20} {'Records':>10} {'Unique':>8} {'Rec%':>8}\n")
        for row in verdict_summary.iter_rows(named=True):
            pct = 100 * row["Total_Records"] / total_records if total_records else 0
            f.write(f"{row['Verdict']:<20} {row['Total_Records']:>10,} {row['Unique_Values']:>8,} {pct:>7.1f}%\n")

        # 黑名单命中详情
        f.write("\n" + "-" * 60 + "\n")
        f.write("BLACKLISTED — 被黑名单排除的 Segment 值\n")
        f.write("-" * 60 + "\n")
        blacklisted = result_df.filter(pl.col("Verdict") == "BLACKLISTED").sort("Count", descending=True)
        f.write(f"{'Segment_Value':<30} {'Count':>8}  {'Example_Accession'}\n")
        for row in blacklisted.iter_rows(named=True):
            f.write(f"{str(row['Segment_Value']):30s} {row['Count']:>8,}  {str(row['Example_Accession'])[:30]}\n")

        # 漏网之鱼 → NEEDS_REVIEW
        f.write("\n" + "=" * 80 + "\n")
        f.write("NEEDS_REVIEW — 未被黑名单覆盖、也非明确合法模式的 Segment 值\n")
        f.write("           → 需人工判断应加入黑名单还是保留为合法\n")
        f.write("=" * 80 + "\n")
        needs_review = result_df.filter(pl.col("Verdict") == "NEEDS_REVIEW").sort("Count", descending=True)
        f.write(f"\n共 {needs_review.height} 个唯一值, {needs_review['Count'].sum():,} 条记录\n\n")
        f.write(f"{'Segment_Value':<35} {'Count':>8}  {'Example_Accession':<20}  {'Example_Title'}\n")
        f.write("-" * 80 + "\n")
        for row in needs_review.iter_rows(named=True):
            title = str(row.get('Example_Title', ''))[:80]
            acc = str(row.get('Example_Accession', ''))[:20]
            f.write(f"{str(row['Segment_Value']):35s} {row['Count']:>8,}  {acc:<20}  {title}\n")

        # LEGIT 统计
        f.write("\n" + "-" * 60 + "\n")
        legit = result_df.filter(pl.col("Verdict") == "LEGIT").sort("Count", descending=True)
        f.write(f"LEGIT — 合法节段名: {legit.height} 个唯一值, {legit['Count'].sum():,} 条记录\n")

    print(f"Done -> {out}")

    # 同时输出 NEEDS_REVIEW 的 TSV 方便手动标记
    review_tsv = os.path.join(args.output_dir, "needs_review.tsv")
    needs_review.write_csv(review_tsv, separator='\t')
    print(f"NEEDS_REVIEW 列表 -> {review_tsv}")


if __name__ == "__main__":
    main()
