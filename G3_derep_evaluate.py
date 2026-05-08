#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import polars as pl
import argparse
import time
import os

def parse_args():
    parser = argparse.ArgumentParser(description="评估不同聚类阈值去重后的物种(TaxID)保留情况")
    parser.add_argument("-i", "--info", default="Plant_Virus_Info.tsv", help="包含 Accession, Taxid, Species_ICTV 的元数据总表")
    parser.add_argument("-f", "--fasta_files", nargs='+', required=True, help="需要评估的 FASTA 文件列表 (用空格分隔)")
    parser.add_argument("-o", "--out_dir", default="Dereplication_Stats", help="输出目录")
    parser.add_argument("--segment-aware", action="store_true", help="启用节段感知统计 (需要 Segment 列)")
    return parser.parse_args()

def get_base_accessions_from_fasta(fasta_file: str) -> set:
    """流式极速解析 FASTA 文件，提取基础 Accession (去版本号) 集合"""
    acc_set = set()
    if not os.path.exists(fasta_file):
        print(f"⚠ 警告: 找不到文件 {fasta_file}")
        return acc_set
        
    with open(fasta_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('>'):
                # 提取 >MT663307.1 中的 MT663307
                base_acc = line[1:].split()[0].split('.')[0].upper()
                acc_set.add(base_acc)
    return acc_set

def main():
    args = parse_args()
    start_time = time.time()
    os.makedirs(args.out_dir, exist_ok=True)
    
    print("==================================================================")
    print("🧬 启动病毒组序列去重(Dereplication)物种保留评估引擎")
    print("==================================================================")

    # ==========================================
    # 1. 极速加载并清洗元数据表 (兼容新旧列名)
    # ==========================================
    print(f"\n⏳ 1. 正在加载元数据表 ({args.info})...")
    
    df = pl.read_csv(args.info, separator="\t", ignore_errors=True)
    
    # 统一列名：确保 Taxid 和 Species_ICTV 存在
    if "Taxid" in df.columns:
        taxid_col = "Taxid"
    elif "taxid" in df.columns:
        taxid_col = "taxid"
    else:
        raise KeyError("元数据表中缺少 Taxid 或 taxid 列")
    
    if "Species_ICTV" in df.columns:
        species_col = "Species_ICTV"
    elif "Species" in df.columns:
        species_col = "Species"
    else:
        species_col = None
        print("⚠ 警告: 未找到 Species_ICTV 或 Species 列，物种名统计将跳过")
    
    # 提取基础列
    core_cols = ["Accession", taxid_col]
    if species_col:
        core_cols.append(species_col)
    if args.segment_aware and "Segment" in df.columns:
        core_cols.append("Segment")
    
    info_df = df.select(core_cols).with_columns([
        pl.col("Accession").cast(pl.Utf8),
        pl.col(taxid_col).cast(pl.Utf8).fill_null("missing")
    ])
    
    # 从 Accession 提取 Base_Accession 供 FASTA 匹配
    core_df = info_df.with_columns(
        pl.col("Accession").str.split(".").list.first().str.to_uppercase().alias("Base_Accession")
    )
    
    total_original_seqs = core_df.height
    total_original_taxids = core_df.select(taxid_col).n_unique()
    total_original_species = core_df.select(species_col).n_unique() if species_col else 0
    
    print(f"   -> 元数据库中包含有效记录: {total_original_seqs:>10,} 条")
    print(f"   -> 元数据库中包含独特 TaxID: {total_original_taxids:>10,} 个")
    if species_col:
        print(f"   -> 元数据库中包含独特物种名: {total_original_species:>10,} 个")
    if args.segment_aware and "Segment" in df.columns:
        print(f"   -> 节段感知模式已启用，将额外统计 Segment 保留情况")

    # 全局汇总容器
    summary_data = []
    
    # 物种级详细追踪表基底：记录最原始每个物种包含多少条序列
    group_cols = [taxid_col]
    if species_col:
        group_cols.append(species_col)
    taxid_tracking_df = core_df.group_by(group_cols).agg(pl.len().alias("Count_Original"))

    # ==========================================
    # 2. 遍历各级 FASTA 聚类结果
    # ==========================================
    print("\n⏳ 2. 正在解析各阈值 FASTA 文件并统计物种级保留率...")
    
    for fasta in args.fasta_files:
        # 使用文件名作为该阈值的标签 (例如: virus.rmdup_0.90_rep_seq)
        label = os.path.basename(fasta).replace(".fasta", "")
        print(f"   -> 正在评估: {label} ...")
        
        acc_set = get_base_accessions_from_fasta(fasta)
        if not acc_set:
            continue
            
        # 极速内存过滤：在元数据中找出当前 FASTA 依然保留的记录
        sub_df = core_df.filter(pl.col("Base_Accession").is_in(acc_set))
        
        seq_count = sub_df.height
        taxid_count = sub_df.select(taxid_col).n_unique()
        species_count = sub_df.select(species_col).n_unique() if species_col else 0
        
        # 计算总体保留率
        seq_retention = (seq_count / total_original_seqs) * 100 if total_original_seqs else 0
        taxid_retention = (taxid_count / total_original_taxids) * 100 if total_original_taxids else 0
        
        summary_data.append({
            "Dataset": label,
            "Sequences_Count": seq_count,
            "Seq_Retention(%)": round(seq_retention, 2),
            "TaxID_Count": taxid_count,
            "TaxID_Retention(%)": round(taxid_retention, 2),
            "Species_Count": species_count
        })
        
        # 统计在这个特定去重阈值下，每个 TaxID 剩了几条序列，并并入主追踪表
        sub_group = sub_df.group_by(taxid_col).agg(pl.len().alias(f"Count_{label}"))
        taxid_tracking_df = taxid_tracking_df.join(sub_group, on=taxid_col, how="left")
        
        # 如果启用了节段感知，额外输出节段级别统计（可选，不加入追踪表）
        if args.segment_aware and "Segment" in core_df.columns:
            seg_stats = sub_df.group_by(["Segment", taxid_col]).agg(pl.len().alias("seqs_in_segment"))
            # 这里不保存到主表，仅打印简要信息
            unique_seg = sub_df.select("Segment").n_unique()
            print(f"      - 节段多样性: {unique_seg} 个独特节段")

    # 填充聚合过程产生的空值为 0，这代表一个原本有的物种，在这个阈值下被完全“洗没”了
    taxid_tracking_df = taxid_tracking_df.fill_null(0)

    # ==========================================
    # 3. 统计结果渲染与输出
    # ==========================================
    summary_df = pl.DataFrame(summary_data)
    
    print("\n========== 📉 去重阈值全局缩水评估报告 ==========")
    with pl.Config(tbl_rows=20, tbl_cols=10, fmt_str_lengths=30):
        print(summary_df)
    print("=================================================\n")

    # 导出全局汇总表
    summary_file = os.path.join(args.out_dir, "Dereplication_Global_Summary.tsv")
    summary_df.write_csv(summary_file, separator="\t")
    
    # 导出物种追踪表 (按原始序列数量由大到小排序，清晰看出高丰度和低丰度物种的保留情况)
    taxid_tracking_df = taxid_tracking_df.sort("Count_Original", descending=True)
    tracking_file = os.path.join(args.out_dir, "TaxID_Retention_Details.tsv")
    taxid_tracking_df.write_csv(tracking_file, separator="\t")
    
    print(f"📄 整体降维宏观汇总表已保存: {summary_file}")
    print(f"📄 各物种去重降维诊断表已保存: {tracking_file}")
    
    # 风险警告与多样性守护
    if summary_data:
        last_label = summary_data[-1]["Dataset"]
        last_col = f"Count_{last_label}"
        
        # 找出在最后一个(最严格的)去重文件中，被缩减为 0 的物种
        lost_taxids = taxid_tracking_df.filter(pl.col(last_col) == 0).height
        
        if lost_taxids > 0:
            print(f"\n⚠ [风险警告] 在 {last_label} 中，有 {lost_taxids} 个独立 TaxID 被彻底合并/抹除。")
            print(f"   (请打开 {tracking_file} 筛选 '{last_col} == 0' 的行，查看哪些物种被误伤了)")
        else:
            print(f"\n🎉 [完美去重] 在最严苛阈值下 ({last_label})，所有物种的物种多样性(TaxID)均被 100% 保留！")

    print(f"\n⏱️ 脚本总耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
