#!/usr/bin/env python3
"""
为 Plant_Virus_Info.full.tsv 补充 Family 列。
从 AllNuclMetadata.csv 按 Accession 匹配提取 Family，直接追加到现有 TSV。

用法:
  python add_family_column.py -i Plant_Virus_Info.full.tsv -m AllNuclMetadata.csv
  python add_family_column.py -i Plant_Virus_Info.full.tsv -m AllNuclMetadata.csv -o output.tsv
"""

import argparse
import os
import polars as pl


def main():
    parser = argparse.ArgumentParser(description="为 Plant_Virus_Info 补充 Family 列")
    parser.add_argument("-i", "--input", required=True, help="Plant_Virus_Info.full.tsv")
    parser.add_argument("-m", "--meta_csv", required=True, help="AllNuclMetadata.csv")
    parser.add_argument("-o", "--output", default="", help="输出文件 (默认覆盖原文件)")
    parser.add_argument("--no-parquet", action="store_true", help="强制重新读取 CSV，不使用 parquet 缓存")
    args = parser.parse_args()

    output = args.output if args.output else args.input

    # ── 读取 meta CSV (缓存为 parquet 加速) ──
    meta_path = os.path.expanduser(args.meta_csv)
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"找不到: {meta_path}")

    pq_path = meta_path + ".parquet"
    if os.path.exists(pq_path) and not args.no_parquet:
        print(f"使用 Parquet 缓存: {pq_path}")
        meta_lf = pl.scan_parquet(pq_path)
    else:
        print(f"读取 CSV 并转换 Parquet...")
        meta_lf = pl.scan_csv(meta_path, separator=",", infer_schema_length=10000, ignore_errors=True)
        meta_lf = meta_lf.rename({"#Accession": "Accession"})
        if not args.no_parquet:
            meta_lf.sink_parquet(pq_path, compression="zstd")
            meta_lf = pl.scan_parquet(pq_path)

    # ── 提取 Accession → Family 映射 ──
    meta_df = meta_lf.select(["Accession", "Family"]).collect()
    family_map = {}
    for row in meta_df.iter_rows():
        acc, fam = row
        if acc and fam:
            family_map[str(acc).strip()] = str(fam).strip()

    print(f"从 AllNuclMetadata 提取到 {len(family_map):,} 条 Family 映射")

    # ── 读取 Plant_Virus_Info ──
    df = pl.read_csv(args.input, separator="\t", truncate_ragged_lines=True)

    # ── 按 Accession 匹配 Family ──
    df = df.with_columns(
        pl.col("Accession").replace_strict(family_map, default=None).alias("Family")
    )

    matched = df["Family"].is_not_null().sum()
    total = df.height
    print(f"匹配到 Family: {matched:,} / {total:,} ({matched/total*100:.1f}%)")

    # ── 调整列顺序：Family 放在 Species 相关列后面 ──
    cols = df.columns
    # 找到 Species 相关列的最后一个位置
    species_keys = ["Species_NCBI", "Species_ICTV", "Species"]
    insert_after = None
    for c in cols:
        if c in species_keys:
            insert_after = cols.index(c)
    if insert_after is not None:
        cols.remove("Family")
        cols.insert(insert_after + 1, "Family")
    df = df.select(cols)

    # ── 输出 ──
    df.write_csv(output, separator="\t")
    print(f"完成 → {output}")


if __name__ == "__main__":
    main()
