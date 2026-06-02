#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于分类元数据的病毒智能去冗余与节段补全工具
================================================
核心逻辑：
  - 非节段 (NonSegmented)：TaxID 级别瀑布流过滤。高优先级存在的 TaxID，低优先级直接剔除。
    * 新增：在 Complete 层级中，同 TaxID 优先保留 RefSeq，无 RefSeq 时才保留 GenBank。
  - 节段 (Segmented)：节段 (Segment) 级别瀑布流补全。高优先级缺失的节段，从低优先级中抽取补充。
"""

import polars as pl
import argparse
import time
import os
import collections

def parse_args():
    parser = argparse.ArgumentParser(description="基于元数据的病毒智能去冗余与节段补全工具")
    parser.add_argument("-i", "--info", default="All_Classified_Virus_Info.tsv", help="输入的总元数据表")
    parser.add_argument("-d", "--fasta_dir", default=".", help="包含拆分FASTA文件的目录")
    parser.add_argument("-o", "--out_dir", default="Smart_Deduplicated_Results", help="输出目录")
    return parser.parse_args()

def extract_fasta(input_fasta: str, output_handle, target_accs: set):
    """流式提取 FASTA 序列并追加到输出句柄"""
    if not os.path.exists(input_fasta):
        return 0
    
    extracted = 0
    write_flag = False
    with open(input_fasta, 'r', encoding='utf-8') as fin:
        for line in fin:
            if line.startswith(">"):
                base_acc = line[1:].split()[0].split('.')[0].upper()
                if base_acc in target_accs:
                    write_flag = True
                    output_handle.write(line)
                    extracted += 1
                else:
                    write_flag = False
            elif write_flag:
                output_handle.write(line)
    return extracted

def clean_segment_name(seg_str: str) -> str:
    """清理 Segment 字符串: 去空白/破折号/下划线, 转大写"""
    if not seg_str:
        return ""
    return seg_str.replace(" ", "").replace("-", "").replace("_", "").upper()

def main():
    args = parse_args()
    start_time = time.time()
    os.makedirs(args.out_dir, exist_ok=True)
    
    print("=" * 80)
    print("🧬 启动病毒元数据智能去冗余与节段补全引擎")
    print("=" * 80)
    
    # 1. 加载并预处理 Info 表
    df = pl.read_csv(args.info, separator="\t", ignore_errors=True)
    df = df.with_columns(
        pl.col("Segment").fill_null("").cast(pl.Utf8).alias("Raw_Segment")
    )
    
    # 优先级定义
    ns_prio = [
        "NonSegmented_Complete", "NonSegmented_Partial_Genome", 
        "NonSegmented_CDS_Fragment", "NonSegmented_Partial_taxid", "NonSegmented_Other_Partial"
    ]
    seg_prio = [
        "Segmented_Complete", "Segmented_Partial_Genome", 
        "Segmented_CDS_Fragment", "Segmented_Partial_taxid", "Segmented_Other_Partial"
    ]

    # =========================================================
    # 策略 A：非节段病毒 (TaxID 瀑布流拦截 + RefSeq 优先)
    # =========================================================
    ns_keep_accs = set()
    ns_seen_taxids = set()
    ns_stats = []

    for cat in ns_prio:
        cat_df = df.filter(pl.col("Category") == cat)
        total_in_cat = cat_df.height
        
        # 核心逻辑：剔除已经在高优先级中被收录过的 TaxID
        valid_df = cat_df.filter(~pl.col("Taxid").is_in(list(ns_seen_taxids)))
        
        # Complete 层级: 每 TaxID 只保留一条, 优先级 RefSeq/ICTV > RefSeq > GenBank/ICTV > GenBank
        if cat == "NonSegmented_Complete":
            valid_df = valid_df.with_columns(
                pl.when(pl.col("Sequence_Type").str.contains("RefSeq")).then(pl.lit(0)).otherwise(pl.lit(2)).alias("_refseq_rank"),
                pl.when(pl.col("Sequence_Type").str.contains("ICTV")).then(pl.lit(0)).otherwise(pl.lit(1)).alias("_ictv_rank"),
            ).with_columns(
                (pl.col("_refseq_rank") + pl.col("_ictv_rank")).alias("_sort_rank")
            ).sort("_sort_rank").unique(subset=["Taxid"], keep="first").drop(["_sort_rank", "_refseq_rank", "_ictv_rank"])

        kept_in_cat = valid_df.height
        
        new_accs = valid_df["Base_Accession"].to_list()
        ns_keep_accs.update(new_accs)
        
        # 将新提取的 TaxID 加入拦截名单
        new_taxids = valid_df["Taxid"].drop_nulls().unique().to_list()
        ns_seen_taxids.update(new_taxids)
        
        ns_stats.append((cat, total_in_cat, kept_in_cat, len(new_taxids)))

    # =========================================================
    # 策略 B：节段病毒 — 每 TaxID 保留最高质量等级的所有记录
    # 优先级: RefSeq/ICTV(0) > RefSeq(1) > GenBank/ICTV(2) > GenBank(3)
    # =========================================================
    def quality_rank(seq_type: str) -> int:
        has_refseq = "RefSeq" in str(seq_type)
        has_ictv = "ICTV" in str(seq_type)
        if has_refseq and has_ictv: return 0
        if has_refseq: return 1
        if has_ictv: return 2
        return 3

    # 跨层级 TaxID 拦截 + 同层级内 Segment 去重 (优先高质量)
    seg_keep_accs = set()
    seg_seen_taxids = set()
    seg_taxid_segs = collections.defaultdict(set)        # {taxid: set(segment_names)}
    seg_stats = []

    for tier_idx, cat in enumerate(seg_prio):
        cat_df = df.filter(pl.col("Category") == cat)
        total_in_cat = cat_df.height

        # 跨层级: 剔除已在更高层级见过的 TaxID
        valid_df = cat_df.filter(~pl.col("Taxid").is_in(list(seg_seen_taxids)))

        # 同层级内: 收集各 TaxID 的最佳质量记录 (RefSeq/ICTV 优先)
        taxid_best = {}  # {taxid: {seg: (acc, rank)}}
        for row in valid_df.iter_rows(named=True):
            tax = str(row["Taxid"])
            acc = row["Base_Accession"]
            norm_seg = clean_segment_name(row["Raw_Segment"])
            rank = quality_rank(row.get("Sequence_Type", ""))

            if tax not in taxid_best:
                taxid_best[tax] = {}
            current = taxid_best[tax].get(norm_seg if norm_seg else "__unlabeled__")
            if norm_seg:
                if current is None or rank < current[1]:
                    taxid_best[tax][norm_seg] = (acc, rank)
            else:
                # 无段名: 只在没有带段名记录时保留
                if not any(k != "__unlabeled__" for k in taxid_best[tax]):
                    if current is None or rank < current[1]:
                        taxid_best[tax]["__unlabeled__"] = (acc, rank)

        kept_in_cat = 0
        new_taxids_in_cat = 0
        for tax, segs in taxid_best.items():
            is_new = tax not in seg_seen_taxids
            for seg_key, (acc, rank) in segs.items():
                seg_keep_accs.add(acc)
                kept_in_cat += 1
            seg_seen_taxids.add(tax)
            seg_taxid_segs[tax].update(
                k for k in segs if k != "__unlabeled__"
            )
            if is_new:
                new_taxids_in_cat += 1

        seg_stats.append((cat, total_in_cat, kept_in_cat, new_taxids_in_cat))

    total_seg_taxids = len(seg_seen_taxids)

    # =========================================================
    # 生成报告与提取序列
    # =========================================================
    print("\n" + "="*80)
    print("📊 智能去冗余提取报告 (Metadata-Driven Deduplication)")
    print("="*80)
    
    print("\n【 第二阵营：非节段病毒 (按物种 TaxID 去重提取) 】")
    print(f"{'分类层级 (Priority Category)':<30} | {'原始序列':<8} | ➡️ {'保留提取':<8} | {'贡献新TaxID':<8}")
    for cat, total, kept, new_tax in ns_stats:
        print(f" - {cat:<27} | Seq={total:<4} | ➡️ Kept={kept:<4} | TaxID={new_tax:<4}")
    print(f" 🟢 非节段最终保留序列: {len(ns_keep_accs):,} 条 (覆盖 {len(ns_seen_taxids):,} 个独特TaxID)")

    # (total_seg_taxids defined above)
    print("\n【 第一阵营：节段病毒 (按缺失节段 Segment 补全提取) 】")
    print(f"{'分类层级 (Priority Category)':<30} | {'原始序列':<8} | ➡️ {'保留提取':<8} | {'贡献新TaxID':<8}")
    for cat, total, kept, new_tax in seg_stats:
        print(f" - {cat:<27} | Seq={total:<4} | ➡️ Kept={kept:<4} | TaxID={new_tax:<4}")
    print(f" 🟢 节段最终保留序列  : {len(seg_keep_accs):,} 条 (拼装/覆盖 {total_seg_taxids:,} 个独特TaxID)")
    print("="*80)

    # 保存新的 Info 表
    all_keep_accs = ns_keep_accs.union(seg_keep_accs)
    final_info_df = df.filter(pl.col("Base_Accession").is_in(list(all_keep_accs)))
    info_out_path = os.path.join(args.out_dir, "Final_Deduplicated_Info.tsv")
    final_info_df.drop("Raw_Segment").write_csv(info_out_path, separator="\t")
    print(f"\n📁 已保存去重后的总 Info 表至: {info_out_path}")

    # 提取 FASTA
    ns_fasta_out = os.path.join(args.out_dir, "Final_NonSegmented_Deduplicated.fasta")
    seg_fasta_out = os.path.join(args.out_dir, "Final_Segmented_Deduplicated.fasta")
    
    print("\n⏳ 正在从原始分块 FASTA 中流式提取去重后的终极序列...")
    
    # 提取非节段
    with open(ns_fasta_out, 'w', encoding='utf-8') as f_out:
        for cat in ns_prio:
            in_fasta = os.path.join(args.fasta_dir, f"{cat}.fasta")
            extract_fasta(in_fasta, f_out, ns_keep_accs)
    print(f"   ✅ 非节段终极序列已生成: {ns_fasta_out}")

    # 提取节段
    with open(seg_fasta_out, 'w', encoding='utf-8') as f_out:
        for cat in seg_prio:
            in_fasta = os.path.join(args.fasta_dir, f"{cat}.fasta")
            extract_fasta(in_fasta, f_out, seg_keep_accs)
    print(f"   ✅ 节段补全终极序列已生成: {seg_fasta_out}")
    
    print(f"\n⏱️ 智能去重耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
