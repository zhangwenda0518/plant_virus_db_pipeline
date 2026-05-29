#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import polars as pl
import os
import sys
import time

def parse_args():
    parser = argparse.ArgumentParser(description="🚀 VHostMetadata 智能缺失值补全与质量分析工具")
    parser.add_argument("-i", "--input", required=True, help="[必填] 输入的 TSV/CSV 文件路径")
    parser.add_argument("-o", "--output", default="VHostMetadata_imputed.tsv", help="[可选] 补全后的文件保存路径")
    parser.add_argument("-s", "--sep", default="\t", help="[可选] 分隔符 (默认: '\\t')")
    parser.add_argument("-n", "--num_samples", type=int, default=5, help="[可选] 展示空值的样本数量")
    return parser.parse_args()

def analyze_dataframe(df: pl.DataFrame, step_name: str, num_samples: int):
    """通用的数据质量分析函数"""
    print(f"\n{'='*60}")
    print(f">>> 📊 {step_name}")
    print(f"{'='*60}")
    
    total_rows = df.height
    print(f"📌 数据集总行数 (Total Rows): {total_rows:,}\n")
    
    if total_rows == 0:
        return

    results = []
    null_samples_dict = {}

    for col_name in df.columns:
        # 定义空值条件 (真正的 null 或者是只包含空白字符的字符串)
        null_condition = pl.col(col_name).is_null() | (pl.col(col_name).cast(pl.Utf8).str.strip_chars() == "")
        
        null_count = df.filter(null_condition).height
        unique_count = df.select(pl.col(col_name)).n_unique()
        missing_rate = (null_count / total_rows) * 100
        
        results.append({
            "列名 (Column)": col_name,
            "总数 (Total)": total_rows,
            "唯一值 (Unique)": unique_count,
            "空值 (Null/Empty)": null_count,
            "缺失率 (Missing %)": f"{missing_rate:.2f}%"
        })

        if null_count > 0:
            null_samples_dict[col_name] = df.filter(null_condition).head(num_samples)

    # 打印统计表格
    summary_df = pl.DataFrame(results)
    with pl.Config(tbl_rows=100, fmt_str_lengths=40):
        print(summary_df)
        
    # 打印空值示例
    if null_samples_dict:
        print("\n🕵️ 发现空值！以下是引发空值的数据示例:")
        for col_name, sample_df in null_samples_dict.items():
            print(f"\n🔻 列 [{col_name}] 缺失的示例 (前 {sample_df.height} 行):")
            with pl.Config(tbl_rows=num_samples, fmt_str_lengths=30, tbl_width_chars=120):
                print(sample_df)
    else:
        print("\n🎉 完美！当前数据集中没有任何空值。")

def impute_missing_hosts(df: pl.DataFrame) -> pl.DataFrame:
    """基于相同的 Taxid 或 Virus_Name 填补 Host 和 Host_Taxid"""
    print(f"\n{'='*60}")
    print(f">>> 🪄 正在执行智能补全算法 (基于窗口函数)...")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    # 1. 规范化空值：将空白字符串、"-"、"NA" 统一转为 null，方便后续处理
    null_markers = ["", "-", "NA", "null", "N/A"]
    df = df.with_columns([
        pl.when(pl.col(c).str.strip_chars().is_in(null_markers))
          .then(None)
          .otherwise(pl.col(c))
          .alias(c)
        for c in ["Host", "Host_Taxid"]
    ])
    
    # 2. 核心补全逻辑 A：基于 Taxid 分组补全
    # 逻辑说明：在相同 Taxid 的组内，提取第一个非空的值，利用 coalesce 合并回去
    df = df.with_columns([
        pl.coalesce([
            pl.col("Host"), 
            pl.col("Host").drop_nulls().first().over("Taxid")
        ]).alias("Host"),
        
        pl.coalesce([
            pl.col("Host_Taxid"), 
            pl.col("Host_Taxid").drop_nulls().first().over("Taxid")
        ]).alias("Host_Taxid")
    ])
    
    # 3. 核心补全逻辑 B：基于 Virus_Name 分组二次补全 (兜底防漏)
    df = df.with_columns([
        pl.coalesce([
            pl.col("Host"), 
            pl.col("Host").drop_nulls().first().over("Virus_Name")
        ]).alias("Host"),
        
        pl.coalesce([
            pl.col("Host_Taxid"), 
            pl.col("Host_Taxid").drop_nulls().first().over("Virus_Name")
        ]).alias("Host_Taxid")
    ])
    
    # 将 null 还原为空白字符串 (保持与原数据集风格一致，可选)
    df = df.fill_null("")
    
    elapsed = time.time() - start_time
    print(f"✅ 补全算法执行完毕！耗时: {elapsed:.2f} 秒")
    
    return df

def main():
    args = parse_args()
    input_file = args.input
    
    if not os.path.exists(input_file):
        print(f"[!] 错误: 找不到文件 '{input_file}'")
        sys.exit(1)
        
    print(f"⏳ 正在读取纯文本文件 (分隔符: '{args.sep}')...")
    
    # 使用现代 Polars 标准读取，取消引号截断，全部读为字符串
    df = pl.read_csv(
        input_file, 
        separator=args.sep, 
        infer_schema=False,         # 替代已废弃的 infer_schema_length=0
        quote_char=None,            # 绝对禁用引号！防止生物学名字里的单双引号引发大面积截断
        truncate_ragged_lines=False,
        ignore_errors=False
    )
    
    # 清洗 NCBI 常见的 '#Accession' 表头
    if df.columns and df.columns[0].startswith("#"):
        clean_name = df.columns[0].lstrip("#")
        df = df.rename({df.columns[0]: clean_name})

    # ==========================================
    # 第一步：补全前的数据分析
    # ==========================================
    analyze_dataframe(df, "【第一步】原始数据质量概览 (补全前)", args.num_samples)

    # ==========================================
    # 第二步：执行补全算法
    # ==========================================
    # 提取补全前 Host 的空值数量，用于计算修复了多少行
    null_before = df.filter(pl.col("Host").is_null() | (pl.col("Host").str.strip_chars() == "")).height
    
    df_imputed = impute_missing_hosts(df)
    
    # ==========================================
    # 第三步：补全后的数据分析
    # ==========================================
    analyze_dataframe(df_imputed, "【第三步】补全后的数据质量概览", args.num_samples)

    null_after = df_imputed.filter(pl.col("Host").is_null() | (pl.col("Host").str.strip_chars() == "")).height
    recovered = null_before - null_after
    
    print(f"\n📈 【补全成果报告】")
    print(f"   - 原始缺失行数: {null_before:,}")
    print(f"   - 成功找回行数: {recovered:,}  (🎉 占比: {recovered/(null_before+0.0001)*100:.2f}%)")
    print(f"   - 仍无法找回行数: {null_after:,} (这些病毒在整个库中都没有宿主记录)")

    # ==========================================
    # 第四步：保存结果
    # ==========================================
    print(f"\n💾 正在保存结果至: {args.output} ...")
    df_imputed.write_csv(
        args.output, 
        separator=args.sep, 
        quote_style="never" # 保持 TSV 纯洁性，不加引号
    )
    print("✅ 保存完成！")

if __name__ == "__main__":
    main()
