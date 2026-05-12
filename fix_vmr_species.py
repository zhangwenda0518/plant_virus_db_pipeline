#!/usr/bin/env python3
"""
修复 final.cluster.ref_info.tsv 中缺失的 VMR 信息
Base_Accession 匹配失败时, 用 Species_ICTV/Species 做二次兜底

用法:
  python fix_vmr_species.py --info final.cluster.ref_info.tsv --vmr VMR_MSL41.tsv -o final.cluster.ref_info.fix.tsv
"""

import polars as pl
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="用 VMR 物种名补全缺失的 Family/Genus/Species 信息")
    parser.add_argument("--info", required=True, help="输入文件: final.cluster.ref_info.tsv")
    parser.add_argument("--vmr", required=True, help="ICTV VMR TSV 文件")
    parser.add_argument("-o", "--output", required=True, help="输出修复后的文件")
    args = parser.parse_args()

    print(f"读取 VMR: {args.vmr}")
    vmr = pl.read_csv(args.vmr, separator="\t", ignore_errors=True)

    # 从 VMR 提取: Species, Family, Genus, Virus name(s)
    vmr_info = vmr.select([
        pl.col("Species").alias("VMR_Species"),
        pl.col("Family").alias("VMR_Family"),
        pl.col("Genus").alias("VMR_Genus"),
        pl.col("Virus name(s)").alias("VMR_VirusName")
    ]).filter(pl.col("VMR_Species").is_not_null() & (pl.col("VMR_Species") != "")) \
      .unique(subset=["VMR_Species"], keep="first")

    print(f"读取 Info: {args.info}")
    df = pl.read_csv(args.info, separator="\t", ignore_errors=True)

    # 统一物种列名
    sp_col = "Species_ICTV" if "Species_ICTV" in df.columns else "Species"
    if sp_col not in df.columns:
        print(f"错误: 找不到物种列 (Species_ICTV/Species)")
        sys.exit(1)

    # 统计修复前
    null_before = df.filter(
        pl.col("VMR_Family").is_null() | (pl.col("VMR_Family") == "")
    ).height if "VMR_Family" in df.columns else df.height

    print(f"修复前 VMR 信息缺失: {null_before} / {df.height} 条")

    # 二次匹配
    df = df.join(
        vmr_info.rename({"VMR_Species": sp_col}),
        on=sp_col, how="left", suffix="_sp"
    )

    # 合并填充
    for src_col, sp_col_name in [
        ("VMR_Species", "VMR_Species_sp"),
        ("VMR_Family", "VMR_Family_sp"),
        ("VMR_Genus", "VMR_Genus_sp"),
        ("Virus name(s)", "VMR_VirusName_sp"),
    ]:
        if src_col not in df.columns:
            # 如果原始没有这列, 用回填的新列值
            if sp_col_name in df.columns:
                df = df.with_columns(
                    pl.col(sp_col_name).alias(src_col)
                )
        elif sp_col_name in df.columns:
            df = df.with_columns(
                pl.coalesce([pl.col(src_col), pl.col(sp_col_name)]).alias(src_col)
            ).drop(sp_col_name)

    # 统计修复后
    null_after = df.filter(
        pl.col("VMR_Family").is_null() | (pl.col("VMR_Family") == "")
    ).height

    print(f"修复后 VMR 信息缺失: {null_after} / {df.height} 条")
    print(f"成功补全: {null_before - null_after} 条")

    # 保持列顺序: 原始列 + 可能新增的 VMR 列
    df.write_csv(args.output, separator="\t")
    print(f"已保存: {args.output}")


if __name__ == "__main__":
    main()
