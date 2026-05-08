#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
病毒双引擎去冗余与生物学分类多维挽救流水线 (RefSeq高优终极版)
=====================================================
核心逻辑：
  - Seqkit 引擎: 去除 100% 完全相同的序列。
  - MMseqs2 引擎: 去除指定阈值 (默认 0.98) 相似度的序列。
挽救 (Rescue) 逻辑：
  - 非节段模式 (--mode nonsegmented): 基于 (TaxID, Species_ICTV) 挽留。
  - 节段模式 (--mode segmented): 严格基于 (TaxID, Species_ICTV, Segment) 挽留，彻底杜绝误删不同节段！
新增逻辑：
  - 【RefSeq 篡位机制】: 在同一聚类/特征组内，若存在带 "_" 的高质量 NCBI RefSeq，
    无条件篡位替换掉软件盲选的普通代表序列。
"""

import polars as pl
import argparse
import time
import os
import subprocess
import shutil
from collections import defaultdict

def parse_args():
    parser = argparse.ArgumentParser(description="双引擎去冗余与生物学多维特征挽救流水线 (支持 RefSeq 优先)")
    parser.add_argument("-f", "--fasta", required=True, help="输入的 FASTA 文件")
    parser.add_argument("-i", "--info", required=True, help="对应的元数据 TSV 表 (包含 Accession, Taxid, Species_ICTV, Segment)")
    parser.add_argument("-m", "--mode", choices=["segmented", "nonsegmented"], required=True, help="【关键】指定处理模式，决定挽留策略的维度")
    parser.add_argument("-o", "--out_dir", default="Final_Deduplication_Results", help="输出目录")
    parser.add_argument("-t", "--threads", default="20", help="使用的线程数 (默认: 20)")
    parser.add_argument("-s", "--seq_id", default="0.98", help="MMseqs2 相似度阈值 (默认: 0.98)")
    return parser.parse_args()

def clean_segment_name(seg_str: str) -> str:
    """清理并标准化 Segment 字符串，便于精准对比"""
    if not seg_str or seg_str == "None":
        return "UNLABELED"
    return str(seg_str).replace(" ", "").replace("-", "").replace("_", "").upper()

def load_metadata(info_file: str):
    """加载元数据，建立包含 Segment 的深度查询字典"""
    print(f"⏳ 正在加载并解析物种分类元数据表 ({info_file})...")
    info_df = pl.read_csv(info_file, separator="\t", ignore_errors=True)
    
    # 确保 Segment 列存在
    if "Segment" not in info_df.columns:
        info_df = info_df.with_columns(pl.lit("UNLABELED").alias("Segment"))
        
    acc_to_meta = {}
    base_accs = []
    
    for row in info_df.iter_rows(named=True):
        raw_acc = str(row.get("Accession", "")).strip()
        if not raw_acc or raw_acc == "None":
            base_accs.append("")
            continue
            
        base_acc = raw_acc.split(".")[0].upper()
        base_accs.append(base_acc)
        
        acc_to_meta[base_acc] = {
            "Taxid": str(row.get("Taxid", "Unknown_TaxID")).strip(),
            "Species_ICTV": str(row.get("Species_ICTV", "Unknown_Species")).strip(),
            "Segment": clean_segment_name(row.get("Segment", ""))
        }
        
    info_df = info_df.with_columns(pl.Series("Base_Accession", base_accs))
    print(f"   -> 成功装载 {len(acc_to_meta):,} 条物种信息记录。")
    return info_df, acc_to_meta

def get_rescue_trait(acc: str, acc_to_meta: dict, mode: str):
    """【核心】生成用于判断是否冗余的生物学特征元组"""
    meta = acc_to_meta.get(acc, {})
    taxid = meta.get("Taxid", "NA")
    species = meta.get("Species_ICTV", "NA")
    
    if mode == "segmented":
        seg = meta.get("Segment", "UNLABELED")
        return (taxid, species, seg)
    else:
        return (taxid, species)

def extract_fasta(input_fasta: str, output_fasta: str, target_accs: set):
    """流式提取 FASTA 序列"""
    extracted = 0
    with open(input_fasta, 'r', encoding='utf-8') as fin, \
         open(output_fasta, 'w', encoding='utf-8') as fout:
        write_flag = False
        for line in fin:
            if line.startswith(">"):
                base_acc = line[1:].split()[0].split('.')[0].upper()
                if base_acc in target_accs:
                    write_flag = True
                    fout.write(line)
                    extracted += 1
                else:
                    write_flag = False
            elif write_flag:
                fout.write(line)
    return extracted

def generate_validation_reports(engine_name, prefix, retained_accs, info_df, out_dir):
    filtered_df = info_df.filter(pl.col("Base_Accession").is_in(retained_accs))
    dedup_info_path = os.path.join(out_dir, f"{prefix}_info.tsv")
    filtered_df.drop("Base_Accession").write_csv(dedup_info_path, separator="\t")
    
    count_df = filtered_df.group_by(["Taxid", "Species_ICTV"]).agg(
        pl.len().alias("Retained_Sequences_Count")
    ).sort("Retained_Sequences_Count", descending=True)
    count_path = os.path.join(out_dir, f"{prefix}_taxid_counts.tsv")
    count_df.write_csv(count_path, separator="\t")
    
    unique_taxids = filtered_df.select("Taxid").n_unique()
    print(f"\n   📊 [{engine_name}] 多样性验证与保留报告:")
    print(f"      - 🧬 最终保留序列总数 : {len(retained_accs):,} 条")
    print(f"      - 🦠 覆盖独特 TaxID   : {unique_taxids:,} 个")
    print(f"      - 📄 附属文件已保存至 : {out_dir}")

def run_seqkit_pipeline(fasta, mode, out_dir, threads, acc_to_meta, info_df):
    """引擎一：Seqkit 100% 精确去重与维度挽救 (集成 RefSeq 篡位)"""
    print("\n" + "="*70)
    print("🚀 引擎一：Seqkit 100% 精确去重序列 (rmdup)")
    print("="*70)
    
    prefix = f"{mode}_seqkit_rmdup"
    tmp_fasta = os.path.join(out_dir, f"{prefix}_tmp.fasta")
    cluster_list = os.path.join(out_dir, f"{prefix}.list")
    final_fasta = os.path.join(out_dir, f"{prefix}.fasta")
    
    cmd = ["seqkit", "rmdup", "-D", cluster_list, "--by-seq", "-j", str(threads), "-o", tmp_fasta, fasta]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    kept_accessions = set()
    with open(tmp_fasta, 'r') as f:
        for line in f:
            if line.startswith('>'):
                kept_accessions.add(line[1:].split()[0].split('.')[0].upper())
                
    rescue_accessions = set()
    refseq_swap_count = 0  # 记录 RefSeq 替换次数
    
    if os.path.exists(cluster_list):
        with open(cluster_list, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 2: continue
                members = [acc.strip().split('.')[0].upper() for acc in parts[1].split(',') if acc.strip()]
                kept_in_cluster = [acc for acc in members if acc in kept_accessions]
                if not kept_in_cluster: continue
                
                kept_acc = kept_in_cluster[0]
                kept_trait = get_rescue_trait(kept_acc, acc_to_meta, mode)
                
                # 【外科手术点 1】：对簇内成员按特征分组
                trait_groups = defaultdict(list)
                for acc in members:
                    trait_groups[get_rescue_trait(acc, acc_to_meta, mode)].append(acc)
                
                for trait, mem_list in trait_groups.items():
                    # 优先把带 "_" 的 RefSeq 排在前面
                    best_acc = sorted(mem_list, key=lambda x: not "_" in x)[0]
                    
                    if trait == kept_trait:
                        # 对于 Seqkit 默认选出的那组特征，如果最好的序列是 RefSeq，且原来选的不是，触发篡位！
                        if best_acc != kept_acc and "_" in best_acc and not "_" in kept_acc:
                            refseq_swap_count += 1
                            kept_accessions.remove(kept_acc) # 将瞎选的普通序列踢除
                            kept_accessions.add(best_acc)    # 换上高质量 RefSeq
                    else:
                        # 这是对其他同源异构体（不同 TaxID/Segment）的常规挽救，同样首选 RefSeq
                        rescue_accessions.add(best_acc)
                        
    print(f"   -> 分析完毕！拦截并挽救了 {len(rescue_accessions):,} 条异源同源序列。")
    print(f"   -> 👑 触发 [RefSeq 优先替换] : {refseq_swap_count:,} 次。")
    
    final_targets = kept_accessions.union(rescue_accessions)
    extract_fasta(fasta, final_fasta, final_targets)
    
    if os.path.exists(tmp_fasta): os.remove(tmp_fasta)
    if os.path.exists(cluster_list): os.remove(cluster_list)
    generate_validation_reports("Seqkit 严格去重", prefix, final_targets, info_df, out_dir)
    return final_fasta

def run_mmseqs_pipeline(fasta, mode, out_dir, threads, seq_id, acc_to_meta, info_df):
    """引擎二：MMseqs2 相似度去重与维度挽救 (集成 RefSeq 篡位)"""
    print("\n" + "="*70)
    print(f"🚀 引擎二：MMseqs2 {seq_id} 相似度聚类去重 (easy-cluster)")
    print("="*70)
    
    prefix = f"{mode}_mmseqs_{seq_id}"
    tmp_dir = os.path.join(out_dir, f"tmp_{prefix}")
    os.makedirs(tmp_dir, exist_ok=True)
    out_prefix = os.path.join(out_dir, prefix)
    final_fasta = f"{out_prefix}.fasta"
    
    cmd = [
        "mmseqs", "easy-cluster", fasta, out_prefix, tmp_dir,
        "--split-memory-limit", "32G", "--cluster-mode", "2",
        "--cov-mode", "1", "--min-seq-id", str(seq_id),
        "--threads", str(threads), "-k", "11", "-v", "0"
    ]
    subprocess.run(cmd, check=True)
    
    cluster_tsv = f"{out_prefix}_cluster.tsv"
    clusters = defaultdict(list)
    if os.path.exists(cluster_tsv):
        with open(cluster_tsv, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    clusters[parts[0].split('.')[0].upper()].append(parts[1].split('.')[0].upper())
            
    final_reps = set()
    conflict_count = 0
    refseq_swap_count = 0  # 记录 RefSeq 替换次数
    
    for rep, members in clusters.items():
        trait_groups = defaultdict(list)
        for mem in members:
            trait = get_rescue_trait(mem, acc_to_meta, mode)
            trait_groups[trait].append(mem)
            
        if len(trait_groups) > 1: conflict_count += 1
            
        # 【外科手术点 2】：优化挑选逻辑
        for trait, mem_list in trait_groups.items():
            # 同样，带 "_" 的优先
            best_acc = sorted(mem_list, key=lambda x: not "_" in x)[0]
            
            if rep in mem_list:
                # 软件原定的代表序列 (rep) 属于这一组。检查是否需要用 RefSeq 替换它
                if best_acc != rep and "_" in best_acc and not "_" in rep:
                    refseq_swap_count += 1
                    final_reps.add(best_acc)
                else:
                    final_reps.add(rep)  # 如果没有 RefSeq 优势，尊重软件的原始选择
            else:
                # 这是由于物种冲突被额外挽救出来的分支，直接推选最好的 RefSeq
                final_reps.add(best_acc)
                
    print(f"   -> 发现冲突特征簇 {conflict_count:,} 个。挽救执行完毕。")
    print(f"   -> 👑 触发 [RefSeq 优先替换] : {refseq_swap_count:,} 次。")
    
    extract_fasta(fasta, final_fasta, final_reps)
    
    shutil.rmtree(tmp_dir, ignore_errors=True)
    for ext in ["_all_seqs.fasta", "_cluster.tsv", "_rep_seq.fasta"]:
        fpath = f"{out_prefix}{ext}"
        if os.path.exists(fpath): os.remove(fpath)
            
    generate_validation_reports("MMseqs2 相似度去重", prefix, final_reps, info_df, out_dir)
    return final_fasta

def main():
    args = parse_args()
    start_time = time.time()
    os.makedirs(args.out_dir, exist_ok=True)
    
    print("======================================================================")
    print(f"🧬 双引擎序列去重流水线启动 | 运行模式: 【{args.mode.upper()}】")
    print("======================================================================")
    
    info_df, acc_to_meta = load_metadata(args.info)
    
    # 第一阶段：用原始 FASTA 跑 Seqkit
    seqkit_fasta = run_seqkit_pipeline(args.fasta, args.mode, args.out_dir, args.threads, acc_to_meta, info_df)
    
    # 第二阶段：用 Seqkit 过滤后的 FASTA 跑 MMseqs
    run_mmseqs_pipeline(seqkit_fasta, args.mode, args.out_dir, args.threads, args.seq_id, acc_to_meta, info_df)
    
    print("\n" + "="*70)
    print(f"🎉 任务圆满结束！请查看 `{args.out_dir}` 目录中带有 `mmseqs_{args.seq_id}.fasta` 后缀的文件。")
    print(f"⏱️ 耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
