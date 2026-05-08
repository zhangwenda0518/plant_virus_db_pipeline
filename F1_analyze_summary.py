#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import polars as pl
import argparse
import sys

def parse_args():
    parser = argparse.ArgumentParser(description="深度分析提取后的病毒元数据 (Plant_Virus_Info.tsv)")
    parser.add_argument("-i", "--input", default="Plant_Virus_Info.tsv", help="提取后的 TSV 文件路径")
    return parser.parse_args()

def main():
    args = parse_args()
    
    print(f"⏳ 正在加载并分析数据: {args.input} ...\n")
    try:
        # 加载数据
        df = pl.read_csv(args.input, separator="\t", ignore_errors=True)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        sys.exit(1)

    # 确保 Length 列是数值类型
    df = df.with_columns(pl.col("Length").cast(pl.Int64, strict=False))

    # ==========================================
    # 1. 基础统计：总序列数与 TaxID 物种数
    # ==========================================
    total_seqs = df.height
    valid_taxid_df = df.filter(pl.col("Taxid").is_not_null())
    unique_taxids = valid_taxid_df.select("Taxid").n_unique()

    # ==========================================
    # 2. Molecule_type 统计
    # ==========================================
    mol_stats = df.group_by("Molecule_type").len().sort("len", descending=True)

    # ==========================================
    # 3. Length 范围统计
    # ==========================================
    len_min = df["Length"].min()
    len_max = df["Length"].max()
    len_mean = df["Length"].mean()
    len_median = df["Length"].median()

    # ==========================================
    # 4. 序列级别的完整性 (Nuc_Completeness)
    # ==========================================
    comp_stats = df.group_by("Nuc_Completeness").len().sort("len", descending=True)

    # ==========================================
    # 5. TaxID 去重后的物种级别完整度
    # ==========================================
    # 逻辑：只要该 taxid 下【至少有一条】序列是 complete，我们就认为该物种拥有完整基因组
    taxid_comp_df = (
        valid_taxid_df.group_by("Taxid")
        .agg([
            # 检查是否有任意一条记录为 'complete'
            (pl.col("Nuc_Completeness") == "complete").any().alias("has_complete_genome"),
            # 统计该物种下共有多少条序列
            pl.col("Accession").count().alias("seq_count")
        ])
    )
    
    taxids_with_complete = taxid_comp_df.filter(pl.col("has_complete_genome")).height
    taxid_complete_ratio = (taxids_with_complete / unique_taxids) * 100 if unique_taxids > 0 else 0

    # ==========================================
    # 6. GenBank_Title 中的 CDS 标注情况
    # ==========================================
    # 使用正则匹配单词边界 \bcds\b，忽略大小写 (?i)，防止匹配到别的单词
    df = df.with_columns(
        pl.col("GenBank_Title").str.contains("(?i)\\bcds\\b").fill_null(False).alias("has_cds")
    )
    cds_count = df.filter(pl.col("has_cds")).height
    cds_ratio = (cds_count / total_seqs) * 100 if total_seqs > 0 else 0

    # ==========================================
    # 🖨️ 打印精美的分析报告
    # ==========================================
    print("==========================================================")
    print(" 🧬 病毒序列元数据体检报告 (Virus Metadata Analysis)")
    print("==========================================================")
    
    print("\n[1] 📦 基础规模 (Overview)")
    print(f"    - 总序列条数 (Accessions) : {total_seqs:,} 条")
    print(f"    - 包含的独特物种 (TaxIDs) : {unique_taxids:,} 个")

    print("\n[2] 🧬 分子类型分布 (Molecule Type)")
    for row in mol_stats.iter_rows(named=True):
        m_type = row['Molecule_type'] if row['Molecule_type'] else "Unknown (未标注)"
        print(f"    - {m_type:<15} : {row['len']:,} 条")

    print("\n[3] 📏 序列长度范围 (Length Range)")
    print(f"    - 最短序列 (Min)    : {len_min:,} bp")
    print(f"    - 最长序列 (Max)    : {len_max:,} bp")
    print(f"    - 中位数长度 (Med.) : {len_median:,.0f} bp")
    print(f"    - 平均长度 (Mean)   : {len_mean:,.0f} bp")

    print("\n[4] 🧩 序列级完整度 (Sequence-Level Completeness)")
    for row in comp_stats.iter_rows(named=True):
        comp = row['Nuc_Completeness'] if row['Nuc_Completeness'] else "Unknown (未标注)"
        print(f"    - {comp:<15} : {row['len']:,} 条")

    print("\n[5] 👑 物种级基因组完整度 (TaxID-Level Completeness)")
    print(f"    - 拥有至少1条完整基因组的物种 : {taxids_with_complete:,} 个")
    print(f"    - 完整物种占比 (去冗余后)     : {taxid_complete_ratio:.2f} %")

    print("\n[6] 🏷️ CDS 编码区标注 (CDS Annotation in Title)")
    print(f"    - 标题包含 'cds' 的序列数     : {cds_count:,} 条")
    print(f"    - 包含比例                    : {cds_ratio:.2f} %")
    
    print("\n==========================================================")
    print("✅ 分析完毕！")

if __name__ == "__main__":
    main()
