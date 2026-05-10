import argparse
import os
import sys
import subprocess
from collections import defaultdict
from ete3 import NCBITaxa
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
# ====== 解决服务器无界面报错的核心 ======
import matplotlib
matplotlib.use('Agg')  
# ========================================

STANDARD_RANKS = {
    'species', 'genus', 'subfamily', 'family', 'suborder', 'order', 
    'class', 'phylum', 'kingdom', 'superkingdom', 'realm'
}

TRUE_SEGMENTED_CATEGORIES = {
    'Segmented_CDS_Fragment',
    'Segmented_Complete',
    'Segmented_Other_Partial',
    'Segmented_Partial_taxid'
}

def parse_fasta(fasta_path):
    with open(fasta_path, 'r') as f:
        header, seq = "", []
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith('>'):
                if header: yield header, "".join(seq)
                header = line[1:].split()[0]
                seq = []
            else:
                seq.append(line)
        if header: yield header, "".join(seq)

def get_lca_info(ncbi, taxids):
    lineages = []
    for tid in taxids:
        if tid.lower() == "unknown": continue
        try:
            lineage = ncbi.get_lineage(int(tid))
            if lineage: lineages.append(lineage)
        except ValueError:
            pass

    if not lineages: return "Unknown", "Unknown", "Unknown", "Unknown", "Unknown"
        
    common_lineage = lineages[0]
    for lin in lineages[1:]:
        new_common = []
        for t1, t2 in zip(common_lineage, lin):
            if t1 == t2: new_common.append(t1)
            else: break
        common_lineage = new_common
    
    if not common_lineage: return "Root", "root", "no rank", "root", "no rank"
        
    lca_taxid = common_lineage[-1]
    name_dict, rank_dict = ncbi.get_taxid_translator([lca_taxid]), ncbi.get_rank([lca_taxid])
    exact_name, exact_rank = name_dict.get(lca_taxid, "Unknown"), rank_dict.get(lca_taxid, "no rank")

    std_name, std_rank = exact_name, exact_rank
    if exact_rank not in STANDARD_RANKS:
        lineage_ranks = ncbi.get_rank(common_lineage)
        lineage_names = ncbi.get_taxid_translator(common_lineage)
        for ancestor_tid in reversed(common_lineage):
            anc_rank = lineage_ranks.get(ancestor_tid, 'no rank')
            if anc_rank in STANDARD_RANKS:
                std_name, std_rank = lineage_names.get(ancestor_tid, "Unknown"), anc_rank
                break
    return str(lca_taxid), exact_name, exact_rank, std_name, std_rank

def plot_results(df, output_path):
    sns.set_theme(style="whitegrid", font_scale=1.1)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    rank_order = df['Std_LCA_Rank'].value_counts().index

    sns.countplot(data=df, x='Std_LCA_Rank', hue='Std_LCA_Rank', order=rank_order, ax=axes[0], palette='viridis', legend=False)
    axes[0].set_title('Number of Mixed Clusters per Std_LCA_Rank', fontweight='bold', pad=15)
    axes[0].set_xlabel('Standard LCA Rank', fontweight='bold')
    axes[0].set_ylabel('Count of Clusters', fontweight='bold')
    axes[0].tick_params(axis='x', rotation=45)
    for p in axes[0].patches:
        axes[0].annotate(f'{int(p.get_height())}', (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='bottom', fontsize=10, color='black', xytext=(0, 3), textcoords='offset points')

    sns.boxplot(data=df, x='Std_LCA_Rank', y='Unique_Taxids', order=rank_order, ax=axes[1], color='lightgray', showfliers=False)
    sns.stripplot(data=df, x='Std_LCA_Rank', y='Unique_Taxids', hue='Std_LCA_Rank', order=rank_order, ax=axes[1], palette='viridis', alpha=0.7, jitter=True, size=6, legend=False)
    axes[1].set_title('Distribution of Unique Taxids per LCA Rank', fontweight='bold', pad=15)
    axes[1].set_xlabel('Standard LCA Rank', fontweight='bold')
    axes[1].set_ylabel('Number of Unique Taxids', fontweight='bold')
    axes[1].tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def safe_lookup(dictionary, key, default="Unknown"):
    if key in dictionary: return dictionary[key]
    base_key = key.split('.')[0]
    if base_key in dictionary: return dictionary[base_key]
    return default

def main():
    parser = argparse.ArgumentParser(description="泛基因组去冗余：LCA诊断、Category冲突排查与自动挽救")
    parser.add_argument("-f", "--fasta", required=True)
    parser.add_argument("-m", "--map", required=True)
    parser.add_argument("-info", "--info", required=True)
    parser.add_argument("-c", "--clusters", default=None)
    
    parser.add_argument("--ani", type=float, default=0.98)
    parser.add_argument("--qcov", type=float, default=0.95)
    
    parser.add_argument("--out_tsv", default="clusters_with_LCA.tsv")
    parser.add_argument("--out_plot", default="clusters.LCA_Distribution.png")
    parser.add_argument("--out_taxid_clusters", default="clusters.taxid.tsv")
    parser.add_argument("--out_fasta", default="final.cluster.ref.fasta")
    parser.add_argument("--out_info", default="final.cluster.ref_info.tsv")
    parser.add_argument("--out_cat_seg_conflict", default="category_segment_conflict.tsv")
    parser.add_argument("--out_replacement_log", default="refseq_replacement_log.tsv")
    args = parser.parse_args()

    print("[1/10] 读取元数据映射 (map & info) 建立容错字典 ...")
    seq2tax = {}
    with open(args.map, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                acc = parts[0].strip()
                tax = parts[1].strip()
                seq2tax[acc] = tax
                seq2tax[acc.split('.')[0]] = tax

    acc2category = {}
    acc2segment = {}
    acc2seqtype = {}
    info_df = None
    if os.path.exists(args.info):
        info_df = pd.read_csv(args.info, sep='\t', dtype=str, keep_default_na=False)
        info_df.columns = info_df.columns.str.strip()
        
        if 'Accession' in info_df.columns:
            if 'Category' in info_df.columns:
                for acc, cat in zip(info_df['Accession'], info_df['Category']):
                    acc_str = str(acc).strip()
                    cat_str = str(cat).strip()
                    if not cat_str: cat_str = "Unassigned"
                    acc2category[acc_str] = cat_str
                    acc2category[acc_str.split('.')[0]] = cat_str
            
            if 'Segment' in info_df.columns:
                for acc, seg in zip(info_df['Accession'], info_df['Segment']):
                    acc_str = str(acc).strip()
                    seg_str = str(seg).strip()
                    if not seg_str: seg_str = "Unassigned"
                    acc2segment[acc_str] = seg_str
                    acc2segment[acc_str.split('.')[0]] = seg_str
            
            if 'Sequence_Type' in info_df.columns:
                for acc, st in zip(info_df['Accession'], info_df['Sequence_Type']):
                    acc_str = str(acc).strip()
                    st_str = str(st).strip()
                    if not st_str: st_str = "Unknown"
                    acc2seqtype[acc_str] = st_str
                    acc2seqtype[acc_str.split('.')[0]] = st_str

    if not args.clusters:
        print("[2/10] 执行 vclust 聚类 ...")
        args.clusters = "vclust_auto_clusters.tsv"
        try:
            subprocess.run(f"vclust prefilter -i {args.fasta} -o fltr.txt --min-ident {args.ani}", shell=True, check=True)
            subprocess.run(f"vclust align -i {args.fasta} -o ani.tsv --filter fltr.txt --out-ani {args.ani} --out-qcov {args.qcov}", shell=True, check=True)
            subprocess.run(f"vclust cluster -i ani.tsv -o {args.clusters} --ids ani.ids.tsv --algorithm cd-hit --metric ani --ani {args.ani} --qcov {args.qcov} --out-repr", shell=True, check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(f"❌ vclust 运行失败: {e}")
    else:
        print(f"[2/10] 读取已有聚类文件: {args.clusters}")

    print("[3/10] 解析聚类结构 ...")
    raw_cluster_to_objs = defaultdict(list)
    with open(args.clusters, 'r') as f:
        first_line = f.readline()
        if not any(k in first_line.lower() for k in ["object", "cluster"]): f.seek(0)
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                obj, rep = (parts[1], parts[2]) if len(parts) >= 3 else (parts[0], parts[1])
                raw_cluster_to_objs[rep].append(obj)

    print("[4/10] 智能指定 Cluster 核心 (RefSeq 多重共存策略) ...")
    cluster_records = []
    taxid_pairs = set()
    replacement_records = [] 
    
    for raw_rep, raw_objs in raw_cluster_to_objs.items():
        # 用 set 去重构建完整的序列池
        pool = list(set([raw_rep] + raw_objs))
        
        # 找出当前 cluster 池子里的所有 RefSeq
        refseq_candidates = [o for o in pool if safe_lookup(acc2seqtype, o, "Unknown") == "RefSeq"]
        
        is_replaced = False
        if len(refseq_candidates) > 0:
            # 💡 核心改动：无论发现1个还是多个 RefSeq，全部作为该 cluster 的保留代表！
            chosen_reps = refseq_candidates
            primary_rep = refseq_candidates[0] # 仅用于 LCA 诊断和聚类结构映射时作为主节点
            
            # 记录被夺权的情况 (如果原代表不是 RefSeq 的话)
            if safe_lookup(acc2seqtype, raw_rep, "Unknown") != "RefSeq":
                is_replaced = True
        else:
            chosen_reps = [raw_rep]
            primary_rep = raw_rep
        
        if is_replaced:
            replacement_records.append({
                "Original_Rep": raw_rep,
                "Original_TaxID": safe_lookup(seq2tax, raw_rep, "Unknown"),
                "New_RefSeq_Rep(s)": ",".join(chosen_reps),
                "New_TaxID(s)": ",".join([safe_lookup(seq2tax, r, "Unknown") for r in chosen_reps]),
                "Cluster_Size": len(pool)
            })

        cluster_records.append({
            "primary_rep": primary_rep,
            "chosen_reps": chosen_reps,
            "pool": pool
        })
        
        # 构建 taxid_pairs，所有的附属节点都挂载到 primary_rep 所在的分类下
        cluster_taxid = safe_lookup(seq2tax, primary_rep, "Unknown")
        for obj in pool:
            obj_taxid = safe_lookup(seq2tax, obj, "Unknown")
            taxid_pairs.add((obj_taxid, cluster_taxid))

    print("[5/10] NCBI 数据库初始化，进行跨域分析与【节段挽救】 ...")
    ncbi = NCBITaxa()
    tax_conflict_list = []
    cat_seg_conflict_list = []
    final_keep_ids = set() 
    clusters_rescued = 0
    seqs_rescued = 0

    for record in cluster_records:
        primary_rep = record["primary_rep"]
        chosen_reps = record["chosen_reps"]
        pool = record["pool"]
        
        tax_counts, cat_counts, seg_counts = defaultdict(int), defaultdict(int), defaultdict(int)
        
        for obj in pool:
            tax_counts[safe_lookup(seq2tax, obj, "Unknown")] += 1
            cat = safe_lookup(acc2category, obj, "Unassigned")
            cat_counts[cat] += 1
            
            if cat in TRUE_SEGMENTED_CATEGORIES:
                seg = safe_lookup(acc2segment, obj, "Unassigned")
                if seg.lower() not in ['unassigned', 'nan', 'none', 'unknown', '']:
                    seg_counts[seg] += 1
        
        is_tax_conflict = len(tax_counts) > 1
        if is_tax_conflict:
            lca_taxid, exact_name, exact_rank, std_name, std_rank = get_lca_info(ncbi, list(tax_counts.keys()))
            tax_breakdown = " | ".join([f"{t}({c})" for t, c in sorted(tax_counts.items(), key=lambda x: x[1], reverse=True)])
            tax_conflict_list.append({
                "Cluster_Rep": primary_rep, "Total_Seqs": len(pool), "Unique_Taxids": len(tax_counts),
                "Exact_LCA_Name": exact_name, "Exact_LCA_Rank": exact_rank, 
                "Std_LCA_Name": std_name, "Std_LCA_Rank": std_rank, "Taxid_Breakdown": tax_breakdown
            })
            
        has_segmented = any(c in TRUE_SEGMENTED_CATEGORIES for c in cat_counts.keys())
        has_nonsegmented = any(c.startswith("NonSegmented") for c in cat_counts.keys())
        
        is_category_conflict = has_segmented and has_nonsegmented
        is_segment_conflict = len(seg_counts) > 1
        
        if is_category_conflict or is_segment_conflict:
            cat_breakdown = " | ".join([f"{k}({v})" for k, v in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)])
            seg_breakdown = " | ".join([f"{k}({v})" for k, v in sorted(seg_counts.items(), key=lambda x: x[1], reverse=True)]) if seg_counts else "None"
            conflict_type = []
            if is_category_conflict: conflict_type.append("Category_Mix")
            if is_segment_conflict: conflict_type.append("Segment_Name_Mix")
            cat_seg_conflict_list.append({
                "Cluster_Rep": primary_rep, "Total_Seqs": len(pool), "Conflict_Type": " & ".join(conflict_type),
                "Category_Breakdown": cat_breakdown, "Segment_Breakdown": seg_breakdown
            })

        # 节段挽救触发
        if has_segmented and (is_tax_conflict or is_category_conflict or is_segment_conflict):
            final_keep_ids.update(pool)
            clusters_rescued += 1
            seqs_rescued += (len(pool) - len(chosen_reps))
        else:
            # 💡 核心出口：将筛选出的 1 条或多条代表序列全部加入白名单
            final_keep_ids.update(chosen_reps)

    print("[6/10] 输出 LCA 跨物种报告与分布图 ...")
    if tax_conflict_list:
        df_lca = pd.DataFrame(tax_conflict_list).sort_values("Total_Seqs", ascending=False)
        df_lca.to_csv(args.out_tsv, sep='\t', index=False)
        plot_results(df_lca, args.out_plot)
    else:
        print("      ✅ 无跨物种聚类，跳过LCA绘图。")

    print("[7/10] 输出 节段异常报告 (Category/Segment) ...")
    if cat_seg_conflict_list:
        pd.DataFrame(cat_seg_conflict_list).sort_values("Total_Seqs", ascending=False).to_csv(args.out_cat_seg_conflict, sep='\t', index=False)

    print(f"[8/10] 输出 RefSeq 替换审计日志 ...")
    if replacement_records:
        pd.DataFrame(replacement_records).to_csv(args.out_replacement_log, sep='\t', index=False)
        print(f"      ✅ 发现并记录了 {len(replacement_records)} 次 RefSeq 提权替换事件。")
    else:
        print("      ✅ 未发生 RefSeq 替换事件。")

    print(f"[9/10] 提取代表 FASTA (包含被挽救的节段序列) 及 TaxID映射表 ...")
    count = 0
    final_keep_ids_clean = {k.split('.')[0] for k in final_keep_ids}.union(final_keep_ids)
    with open(args.out_fasta, 'w') as out_f:
        for seqid, seq in parse_fasta(args.fasta):
            if seqid in final_keep_ids_clean or seqid.split('.')[0] in final_keep_ids_clean:
                out_f.write(f">{seqid}\n{seq}\n")
                count += 1
                if count >= len(final_keep_ids): break

    with open(args.out_taxid_clusters, 'w') as out_f:
        out_f.write("object_taxid\tcluster_taxid\n")
        for obj_taxid, clus_taxid in sorted(taxid_pairs, key=lambda x: (x[1], x[0])):
            out_f.write(f"{obj_taxid}\t{clus_taxid}\n")

    print(f"[10/10] 提取聚类后 info.tsv ...")
    if info_df is not None:
        base_keeps = [k.split('.')[0] for k in final_keep_ids]
        mask = info_df['Accession'].apply(lambda x: str(x).strip() in final_keep_ids or str(x).strip().split('.')[0] in base_keeps)
        info_df[mask].to_csv(args.out_info, sep='\t', index=False)

    all_raw_accs = set()
    for record in cluster_records:
        all_raw_accs.update(record["pool"])
    total_acc_before = len(all_raw_accs)
    
    taxids_before = {safe_lookup(seq2tax, obj, "Unknown") for obj in all_raw_accs}
    taxids_after = {safe_lookup(seq2tax, acc, "Unknown") for acc in final_keep_ids}
    taxids_before.discard("Unknown")
    taxids_after.discard("Unknown")

    print("\n" + "="*55)
    print("🚀 泛基因组去冗余 Pipeline 运行完毕")
    print("="*55)
    print(f"【去冗余前 (Raw Data)】")
    print(f"  📌 原始序列 (Accessions) 总数: {total_acc_before}")
    print(f"  📌 原始物种 (TaxIDs) 总数:     {len(taxids_before)}")
    
    print(f"\n【聚类与诊断 (Clustering & Diagnostics)】")
    print(f"  📊 总计 Cluster 数量:          {len(cluster_records)}")
    print(f"  👑 RefSeq 夺权事件次数:        {len(replacement_records)}")
    print(f"  ⚠️ 混合 Cluster (跨TaxID) 数量: {len(tax_conflict_list)}")
    if len(cluster_records) > 0:
        print(f"  📉 混合 Cluster 比例:          {len(tax_conflict_list) / len(cluster_records) * 100:.2f}%")
    print(f"  🚑 触发节段病毒挽救 Cluster数: {clusters_rescued}")
    print(f"  🏥 成功挽救节段基因组序列数:   {seqs_rescued}")
        
    print(f"\n【去冗余后 (Representative Data)】")
    print(f"  🎯 提取代表序列 (Accessions):  {len(final_keep_ids)}")
    print(f"  🧬 代表序列涵盖 TaxIDs:        {len(taxids_after)}")
    print("="*55 + "\n")

if __name__ == "__main__":
    main()
