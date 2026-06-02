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
    """提取 Segment 核心标识符，用于跨来源匹配。
    'RNA 2' → '2', 'DNA-A' → 'A', '2' → '2', 'RNA' → 'RNA'"""
    if not seg_str:
        return ""
    seg = seg_str.replace(" ", "").replace("-", "").replace("_", "").upper()
    # 去除已知前缀 (仅当后面还有内容, 避免把单独的 'RNA' 变成空串)
    for prefix in ["GENOMICRNA", "GENOMICDNA", "SUBGENOMICRNA", "DEFECTIVERNA", "DIRNA", "PUTATIVERNA", "RNA", "DNA"]:
        if seg.startswith(prefix) and len(seg) > len(prefix):
            seg = seg[len(prefix):]
            break
    return seg

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
    # 策略 B：节段病毒 (Segment 级别智能补全 + 质量替换)
    # 优先级: RefSeq/ICTV(0) > RefSeq(1) > GenBank/ICTV(2) > GenBank(3)
    # =========================================================
    def quality_rank(seq_type: str) -> int:
        has_refseq = "RefSeq" in str(seq_type)
        has_ictv = "ICTV" in str(seq_type)
        if has_refseq and has_ictv: return 0
        if has_refseq: return 1
        if has_ictv: return 2
        return 3

    seg_keep_accs = set()
    taxid_segments = collections.defaultdict(dict)   # {taxid: {norm_seg: (acc, rank)}}
    taxid_unlabeled = {}                              # {taxid: (acc, rank, tier)}
    taxid_has_refseq = set()                          # TaxID 至少有一条 RefSeq 记录
    seg_stats = []

    for tier_idx, cat in enumerate(seg_prio):
        cat_df = df.filter(pl.col("Category") == cat)
        total_in_cat = cat_df.height
        kept_in_cat = 0
        new_taxids_count = 0

        for row in cat_df.iter_rows(named=True):
            tax = str(row["Taxid"])
            acc = row["Base_Accession"]
            norm_seg = clean_segment_name(row["Raw_Segment"])
            rank = quality_rank(row.get("Sequence_Type", ""))
            if rank <= 1:
                taxid_has_refseq.add(tax)

            is_kept = False
            is_new_tax = (tax not in taxid_segments) and (tax not in taxid_unlabeled)

            if norm_seg != "":
                current = taxid_segments[tax].get(norm_seg)
                if current is None:
                    # 新节段 → 保留
                    taxid_segments[tax][norm_seg] = (acc, rank)
                    seg_keep_accs.add(acc)
                    is_kept = True
                elif rank < current[1]:
                    # 更高质量 → 替换旧的
                    seg_keep_accs.discard(current[0])
                    taxid_segments[tax][norm_seg] = (acc, rank)
                    seg_keep_accs.add(acc)
                    is_kept = True
                # 否则同质量或更低 → 丢弃
            else:
                # 如果已有带 Segment 名的记录, 不再保留无 Segment 名的散装序列
                if len(taxid_segments.get(tax, {})) > 0:
                    pass
                else:
                    current = taxid_unlabeled.get(tax)
                    if current is None:
                        taxid_unlabeled[tax] = (acc, rank, tier_idx)
                        seg_keep_accs.add(acc)
                        is_kept = True
                    elif rank < current[1]:
                        # 更高质量 → 替换
                        seg_keep_accs.discard(current[0])
                        taxid_unlabeled[tax] = (acc, rank, tier_idx)
                        seg_keep_accs.add(acc)
                        is_kept = True
                    elif tier_idx == current[2] and rank == current[1]:
                        # 同层级同质量多条 → 保留
                        seg_keep_accs.add(acc)
                        is_kept = True
                    # 更低质量或更低层级 → 丢弃

            if is_kept:
                kept_in_cat += 1
                if is_new_tax:
                    new_taxids_count += 1

        seg_stats.append((cat, total_in_cat, kept_in_cat, new_taxids_count))

    # RefSeq 兜底: 有 RefSeq 的 TaxID, 剔除非 RefSeq 记录
    n_refseq_cleanup = 0
    for tax in taxid_has_refseq:
        for norm_seg, (acc, rank) in list(taxid_segments.get(tax, {}).items()):
            if rank > 1:  # GenBank/ICTV 或 GenBank
                seg_keep_accs.discard(acc)
                del taxid_segments[tax][norm_seg]
                n_refseq_cleanup += 1
        if tax in taxid_unlabeled and taxid_unlabeled[tax][1] > 1:
            seg_keep_accs.discard(taxid_unlabeled[tax][0])
            del taxid_unlabeled[tax]
            n_refseq_cleanup += 1

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

    total_seg_taxids = len(set(taxid_segments.keys()).union(set(taxid_unlabeled_tier.keys())))
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
