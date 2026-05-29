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

    # 从 VMR 提取: Species, Family, Genus, Virus name(s) — 按物种名去重
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
    cols_to_fix = [c for c in ["VMR_Species", "VMR_Family", "VMR_Genus", "Virus name(s)"] if c in df.columns]
    null_before = df.filter(
        pl.col("VMR_Family").is_null() | (pl.col("VMR_Family") == "")
    ).height if "VMR_Family" in df.columns else df.height

    print(f"修复前 VMR_Family 缺失: {null_before} / {df.height} 条")

    # 用物种名 join VMR 查找表
    df = df.join(vmr_info, left_on=sp_col, right_on="VMR_Species", how="left", suffix="_vmr")

    # 对每个 VMR 列: 原始值为空时用 join 回填的值
    for col_name in cols_to_fix:
        vmr_col_name = col_name + "_vmr"
        if vmr_col_name in df.columns:
            df = df.with_columns(
                pl.when(pl.col(col_name).is_null() | (pl.col(col_name) == ""))
                  .then(pl.col(vmr_col_name))
                  .otherwise(pl.col(col_name))
                  .alias(col_name)
            )
            # VMR_Species 是 join key, 不会产生 _vmr 后缀列, 需要特殊处理
            # 如果原始 VMR_Species 为空, 用 sp_col (Species_ICTV) 的值填充
            if col_name == "VMR_Species" and df.filter(
                pl.col(col_name).is_null() | (pl.col(col_name) == "")
            ).height > 0:
                df = df.with_columns(
                    pl.when(pl.col(col_name).is_null() | (pl.col(col_name) == ""))
                      .then(pl.col(sp_col))
                      .otherwise(pl.col(col_name))
                      .alias(col_name)
                )
            df = df.drop(vmr_col_name)


        elif col_name == "VMR_Species":
            # VMR_Species 作为 join key 不产生 _vmr 列, 直接用 sp_col 填充空值
            df = df.with_columns(
                pl.when(pl.col(col_name).is_null() | (pl.col(col_name) == ""))
                  .then(pl.col(sp_col))
                  .otherwise(pl.col(col_name))
                  .alias(col_name)
            )

    # 统计修复后
    null_after = df.filter(
        pl.col("VMR_Family").is_null() | (pl.col("VMR_Family") == "")
    ).height if "VMR_Family" in df.columns else df.height

    print(f"修复后 VMR_Family 缺失: {null_after} / {df.height} 条")
    print(f"成功补全: {null_before - null_after} 条")

    df.write_csv(args.output, separator="\t")
    print(f"已保存: {args.output}")


if __name__ == "__main__":
    main()
