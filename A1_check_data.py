#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import polars as pl
import os
import sys

def parse_args():
    parser = argparse.ArgumentParser(description="🚀 极速大数据集质量统计工具 (支持输出空值示例)")
    parser.add_argument("-i", "--input", required=True, help="[必填] 输入文件路径")
    parser.add_argument("-s", "--sep", default="\t", help="[可选] 分隔符 (默认: '\\t'。CSV请用 ',')")
    parser.add_argument("-o", "--output", default="", help="[可选] 输出统计报告的路径 (例如: summary.csv)")
    parser.add_argument("-n", "--num_samples", type=int, default=5, help="[可选] 展示每列空值的样本数量 (默认: 5行)")
    return parser.parse_args()

def main():
    args = parse_args()
    input_file = args.input
    
    if not os.path.exists(input_file):
        print(f"[!] 错误: 找不到文件 '{input_file}'")
        sys.exit(1)
        
    print("=========================================================")
    print(f">>> 🚀 正在对 {os.path.basename(input_file)} 进行极速数据质量分析...")
    print("=========================================================\n")
    
    # 1. 智能加载数据
    if input_file.endswith(".parquet"):
        print("⚡ 检测到 Parquet 格式，极速加载中...")
        df = pl.read_parquet(input_file)
    else:
        base_name, _ = os.path.splitext(input_file)
        parquet_cache = f"{base_name}.parquet"
        
        if os.path.exists(parquet_cache):
            print(f"⚡ 发现对应的 Parquet 缓存 ({os.path.basename(parquet_cache)})，极速加载中...")
            df = pl.read_parquet(parquet_cache)
        else:
            print(f"⏳ 正在读取纯文本文件 (分隔符: '{args.sep}')...")
            # 增强型读取，防止逗号截断报错
            df = pl.read_csv(
                input_file, 
                separator=args.sep, 
                infer_schema_length=0,
                truncate_ragged_lines=True,  
                quote_char='"',              
                ignore_errors=True           
            )
            
            # 清洗 NCBI 常见的 '#Accession' 表头
            if df.columns and df.columns[0].startswith("#"):
                clean_name = df.columns[0].lstrip("#")
                df = df.rename({df.columns[0]: clean_name})
            
    total_rows = df.height
    print(f"\n📊 数据集总行数 (Total Rows): {total_rows:,}\n")
    
    if total_rows == 0:
        print("[!] 警告: 数据集为空！")
        sys.exit(0)

    # 2. 计算统计指标 & 收集空值样本
    results = []
    null_samples_dict = {}  # 字典：用于存储每一列包含空值的样本 DataFrame

    for col_name in df.columns:
        # 定义空值条件：物理上的 Null 或者 空白字符串 ""
        null_condition = pl.col(col_name).is_null() | (pl.col(col_name).cast(pl.Utf8).str.strip_chars() == "")
        
        null_count = df.filter(null_condition).height
        
        # 如果发现空值，抓取前 N 行样本保存下来
        if null_count > 0:
            sample_df = df.filter(null_condition).head(args.num_samples)
            null_samples_dict[col_name] = sample_df

        unique_count = df.select(pl.col(col_name)).n_unique()
        missing_rate = (null_count / total_rows) * 100
        
        results.append({
            "列名 (Column)": col_name,
            "总数 (Total)": total_rows,
            "唯一值 (Unique)": unique_count,
            "空值 (Null/Empty)": null_count,
            "缺失率 (Missing %)": f"{missing_rate:.2f}%"
        })

    # 3. 生成并打印总体统计表格
    summary_df = pl.DataFrame(results)
    print("【第一部分：数据质量全局概览】")
    with pl.Config(tbl_rows=100, fmt_str_lengths=40):
        print(summary_df)
        
    # 4. 打印空值数据示例 (分析师大揭秘)
    if null_samples_dict:
        print("\n" + "="*57)
        print(">>> 🕵️  【第二部分：发现空值！以下是引发空值的数据示例】")
        print("="*57)
        
        for col_name, sample_df in null_samples_dict.items():
            print(f"\n🔻 列 [{col_name}] 缺失或为空的示例 (展示前 {sample_df.height} 行，带上下文):")
            # 配置 polars 打印格式，确保在终端里不换行、对齐好看
            with pl.Config(tbl_rows=args.num_samples, fmt_str_lengths=30, tbl_width_chars=150):
                print(sample_df)
    else:
        print("\n🎉 太棒了！整个数据集没有任何空值，极其完美。")

    # 5. 保存报告
    if args.output:
        summary_df.write_csv(args.output)
        print(f"\n💾 统计报告已保存至: {args.output}")
    else:
        print("\n💡 分析完成！")

if __name__ == "__main__":
    main()
