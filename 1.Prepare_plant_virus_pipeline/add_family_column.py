#!/usr/bin/env python3
"""
为 Plant_Virus_Info.full.tsv 补充 Family 列。
从 AllNuclMetadata.csv 按 Accession 匹配提取 Family，直接追加到现有 TSV。
只读取目标 Accession 的 Family，不会加载全量数据到内存。

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
    args = parser.parse_args()

    output = args.output if args.output else args.input

    # ── 1. 先读取 Plant_Virus_Info，获取目标 Accession 列表 ──
    print("读取输入文件...")
    df = pl.read_csv(args.input, separator="\t", truncate_ragged_lines=True)
    target_acc = df["Accession"].unique().to_list()
    # 去除版本号变体 (如 NC_001.1 → NC_001)，增加匹配率
    target_set = set(target_acc)
    for acc in target_acc:
        if "." in str(acc):
            target_set.add(str(acc).rsplit(".", 1)[0])
    print(f"目标 Accession: {len(target_acc):,} 个")

    # ── 2. 懒查询 meta CSV，只读 Accession + Family，过滤目标 Accession ──
    meta_path = os.path.expanduser(args.meta_csv)
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"找不到: {meta_path}")

    pq_path = meta_path + ".parquet"
    if os.path.exists(pq_path):
        print(f"使用 Parquet 缓存: {pq_path}")
        meta_lf = pl.scan_parquet(pq_path).select(["Accession", "Family"])
    else:
        print("扫描 CSV (首次运行)...")
        meta_lf = pl.scan_csv(
            meta_path, separator=",", infer_schema_length=10000, ignore_errors=True
        ).rename({"#Accession": "Accession"}).select(["Accession", "Family"])

    # 只提取目标的 Accession
    meta_df = meta_lf.filter(pl.col("Accession").is_in(list(target_set))).collect()
    print(f"匹配到 Family 映射: {meta_df.height:,} 条")

    # ── 3. 通过 left join 补充 Family ──
    # 去除版本号以增加匹配率
    df = df.with_columns(
        pl.col("Accession").str.split(".").list.first().alias("_acc_base")
    )

    # 按精确 Accession 匹配
    df = df.join(
        meta_df.select(["Accession", pl.col("Family")]),
        on="Accession", how="left"
    )

    # 没匹配上的，用 base Accession 再试一次
    df = df.join(
        meta_df.select([pl.col("Accession").alias("_acc_base"), pl.col("Family").alias("Family_2")]),
        on="_acc_base", how="left"
    )

    df = df.with_columns(
        pl.coalesce(["Family", "Family_2"]).alias("Family")
    ).drop(["_acc_base", "Family_2"])

    matched = df["Family"].is_not_null().sum()
    total = df.height
    print(f"匹配到 Family: {matched:,} / {total:,} ({matched/total*100:.1f}%)")

    # ── 4. 调整列顺序 ──
    cols = df.columns
    species_keys = ["Species_NCBI", "Species_ICTV", "Species"]
    insert_after = 0
    for c in cols:
        if c in species_keys:
            insert_after = cols.index(c)
    if "Family" in cols:
        cols.remove("Family")
    cols.insert(insert_after + 1, "Family")
    df = df.select(cols)

    # ── 5. 输出 ──
    df.write_csv(output, separator="\t")
    print(f"完成 → {output}")


if __name__ == "__main__":
    main()
