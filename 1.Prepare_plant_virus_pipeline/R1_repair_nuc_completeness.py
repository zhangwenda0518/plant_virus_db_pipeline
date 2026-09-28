#!/usr/bin/env python3
"""
R1_repair_nuc_completeness.py — 存量数据完整度字段修复 (2026-09-27)

背景 (见仓库 CHANGELOG 2026-09-27 条目):
  NCBI 上游元数据(AllNuclMetadata.csv)会把基因级标题("complete cds"、
  "gene for/encoding ..."、"\bgene\b" 类)的记录标成 Nuc_Completeness=complete,
  基因级 RefSeq 记录由此混入数据库并被 F2 判为 Complete、被 merge_to_ref
  优先选入参考集。经核查: 参考集 5,263 条 complete 中 344 条为基因级误标
  (256 条 NC_ + 88 条其他), 波及 80+ 个物种。

规则 (只动 Nuc_Completeness 一列, 不增删行):
  降级 partial : field=complete 且标题含 "partial"               → partial
  降级 fragment: field=complete 且标题为基因级完整(complete cds /
                 complete coding / complete gene(s))              → ""(未知)
  升级 complete: field 为空 且标题含 complete genome/sequence/segment
                 且无 partial / 基因级标记                        → complete

用法:
  python R1_repair_nuc_completeness.py           # 干跑: 只统计, 不写盘
  python R1_repair_nuc_completeness.py --apply   # 写盘: 先备份 .bak.20260927 再覆盖
"""
import argparse
import os
import re

import polars as pl

DATA_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "data")
FILES = [
    "Plant_Virus_Full.Info.tsv",
    "Plant_Virus_Ref.Info.tsv",
    "Plant_Virus.complete_ref_info.tsv",
]

GENE_LEVEL = r"(?i)complete\s+cds|complete\s+coding|complete\s+genes?\b|\bgene\b|\bgenes\b"
COMPLETE_OK = r"(?i)complete\s+genome|complete\s+sequence|complete\s+segment"


def repair_column(df: pl.DataFrame, protect_refseq: bool = True) -> pl.DataFrame:
    title = pl.col("GenBank_Title").fill_null("").str.to_lowercase()
    field = pl.col("Nuc_Completeness").fill_null("").str.to_lowercase().str.strip_chars()

    gene_level = title.str.contains(GENE_LEVEL) & ~title.str.contains(COMPLETE_OK)
    # 护栏: RefSeq(NC_) 的完整基因组/节段不因"基因级标题"被降级
    # （NCBI 对小型病毒与卫星的 RefSeq 标题本就用 "gene, complete cds" 写法；
    #   实测这类误伤约 270 条。--no-guard 可关闭）
    if protect_refseq and "Accession" in df.columns:
        gene_level = gene_level & ~pl.col("Accession").cast(pl.Utf8).str.starts_with("NC_")
    has_partial = title.str.contains(r"(?i)partial")
    title_complete = title.str.contains(COMPLETE_OK)

    new_field = (
        pl.when(field.eq("complete") & has_partial)
        .then(pl.lit("partial"))
        .when(field.eq("complete") & gene_level)
        .then(pl.lit(""))
        .when(field.eq("") & title_complete & ~has_partial & ~gene_level)
        .then(pl.lit("complete"))
        .otherwise(field)
    )
    return df.with_columns(new_field.alias("Nuc_Completeness"))


def main():
    ap = argparse.ArgumentParser(description="修复 Nuc_Completeness 误标(干跑默认, --apply 写盘)")
    ap.add_argument("--data-dir", default=DATA_DIR_DEFAULT)
    ap.add_argument("--apply", action="store_true", help="写盘(先备份)")
    ap.add_argument("--no-guard", action="store_true",
                    help="关闭 RefSeq 完整基因组护栏(默认开启)")
    args = ap.parse_args()

    for fname in FILES:
        path = os.path.join(args.data_dir, fname)
        if not os.path.exists(path):
            print(f"-- 跳过(不存在): {fname}")
            continue
        df = pl.read_csv(path, separator="\t", infer_schema_length=0)
        before = df["Nuc_Completeness"].fill_null("")
        repaired = repair_column(df, protect_refseq=not args.no_guard)
        after = repaired["Nuc_Completeness"].fill_null("")

        b = before.to_list()
        a = after.to_list()
        titles = df["GenBank_Title"].fill_null("").to_list()
        demote_partial = demote_gene = promote = 0
        ex = {"demote_partial": [], "demote_gene": [], "promote": []}
        for i, (x, y) in enumerate(zip(b, a)):
            if x == y:
                continue
            t = titles[i].lower()
            if x == "complete" and y == "partial":
                demote_partial += 1
                if len(ex["demote_partial"]) < 3: ex["demote_partial"].append(t[:80])
            elif x == "complete" and y == "":
                demote_gene += 1
                if len(ex["demote_gene"]) < 3: ex["demote_gene"].append(t[:80])
            elif x == "" and y == "complete":
                promote += 1
                if len(ex["promote"]) < 3: ex["promote"].append(t[:80])
        total = demote_partial + demote_gene + promote
        print(f"\n== {fname}  ({df.height:,} 行) ==")
        print(f"   降级 partial      : {demote_partial}")
        print(f"   降级 fragment(\"\") : {demote_gene}")
        print(f"   升级 complete     : {promote}")
        print(f"   合计改动          : {total}")
        for k, v in ex.items():
            for t in v:
                print(f"     [{k}] {t}")

        if args.apply and total:
            from datetime import datetime as _dt
            stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
            bak = f"{path}.bak.{stamp}"
            if not os.path.exists(bak):
                os.rename(path, bak)
                print(f"   备份: {bak}")
            repaired.write_csv(path, separator="\t")
            print(f"   已写盘: {path}")

    print("\n完成。" + ("" if args.apply else " (干跑模式, 未写盘; 加 --apply 生效)"))


if __name__ == "__main__":
    main()
