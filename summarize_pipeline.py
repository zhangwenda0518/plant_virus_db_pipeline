#!/usr/bin/env python3
"""
Pipeline 运行总结工具 — 生成学术论文风格报告
------------------------------------------------
从各阶段中间产物中提取定量指标，格式化输出为期刊风格摘要。

用法:
    python summarize_pipeline.py --work-dir ~/plant_virus_db
    python summarize_pipeline.py --work-dir ~/plant_virus_db --short  (仅摘要)
"""

import argparse
import os
import sys
import csv
from pathlib import Path

# ============================================================
# 配置: 各阶段关键产物路径 (相对于 work_dir)
# ============================================================
ARTIFACTS = {
    "01_merge": {
        "Merged.VHostMetadata.tsv": "合并后 TSV (VHDB+NCBI)",
        "Merged.VHostMetadata.imputer.tsv": "宿主补全后 TSV",
        "Merged.VHostMetadata.lineage.tsv": "谱系添加后 TSV",
        "bad_rows_log.tsv": "坏行日志",
    },
    "02_ictv": {
        "VMR_Split_By_Host/VMR_Plant.tsv": "ICTV 植物病毒 VMR",
        "VMR_Split_By_Host/VMR_Animal.tsv": "ICTV 动物病毒 VMR",
        "VMR_Split_By_Host/VMR_Fungi.tsv": "ICTV 真菌病毒 VMR",
        "VMR_Split_By_Host/VMR_Bacteria.tsv": "ICTV 细菌病毒 VMR",
        "VMR_Split_By_Host/Rescue_Failed_Details.tsv": "ICTV 抢救失败详情",
    },
    "03_host": {
        "host_extract/Final_Virus_Host_Lineage.tsv": "最终病毒宿主谱系表",
        "VHostMetadata/Summary_Counts.tsv": "宿主分类汇总",
        "VHostMetadata/Plant.tsv": "植物病毒 TSV",
    },
    "04_sequences": {
        "plant.virus.fasta": "植物病毒合并 FASTA",
        "plant.virus.id": "植物病毒 Accession 列表",
        "Plant_virus_db/Plant_Extracted_Sequences.fasta": "本地已提取序列",
        "Plant_virus_db/Plant_missing_accessions.txt": "缺失 Accession 列表",
        "Plant_virus_db/Downloaded_Plant_Viruses.fasta": "在线下载序列",
    },
    "05_metadata": {
        "Plant_Virus_Info.tsv": "完整元数据表",
        "Plant_Virus_Info.summary": "统计报告",
    },
    "06_dedup": {
        "split_results/All_Classified_Virus_Info.tsv": "分类后总信息表",
        "virus.dedup/Final_Deduplicated_Info.tsv": "去重后信息表",
        "virus.dedup/Final_NonSegmented_Deduplicated.fasta": "非节段去重 FASTA",
        "virus.dedup/Final_Segmented_Deduplicated.fasta": "节段去重 FASTA",
        "Final_DB_Build/nonsegmented_mmseqs_0.98.fasta": "非节段 mmseqs 最终",
        "Final_DB_Build/segmented_mmseqs_0.98.fasta": "节段 mmseqs 最终",
        "plant.final.rmdup.fasta": "合并去冗余 FASTA",
        "plant.final.rmdup.id": "合并去冗余 ID 列表",
    },
    "07_cluster": {
        "final.cluster.ref.fasta": "最终参考基因组 FASTA",
        "final.cluster.ref_info.tsv": "最终参考基因组信息",
        "clusters_with_LCA.tsv": "LCA 诊断报告",
        "clusters.LCA_Distribution.png": "LCA 分布图",
        "derep.summary.tsv": "去冗余汇总",
        "virus_genes_cov.tsv": "基因覆盖度",
    },
}


def count_lines(work_dir, rel_path):
    """Count TSV/FASTA lines or rows. Returns (count, exists)."""
    fpath = Path(work_dir) / rel_path
    if not fpath.is_file():
        return None, False
    try:
        if fpath.suffix in (".txt", ".id"):
            with open(fpath) as f:
                return sum(1 for _ in f), True
        elif fpath.suffix in (".tsv", ".csv"):
            with open(fpath) as f:
                reader = csv.reader(f, delimiter="\t")
                next(reader, None)  # skip header
                n = sum(1 for _ in reader)
            return n, True
        elif fpath.suffix in (".fasta", ".fa"):
            with open(fpath) as f:
                n = sum(1 for line in f if line.startswith(">"))
            return n, True
        else:
            return fpath.stat().st_size, True
    except Exception:
        return None, True


def format_count(n):
    if n is None:
        return "N/A"
    if isinstance(n, int) and n > 10_000_000:
        return f"{n:,}"
    if isinstance(n, int):
        return f"{n:,}"
    return str(n)


def parse_summary_counts(work_dir):
    """Parse 03_host/VHostMetadata/Summary_Counts.tsv into a dict."""
    fpath = Path(work_dir) / "03_host/VHostMetadata/Summary_Counts.tsv"
    if not fpath.is_file():
        return {}
    counts = {}
    with open(fpath) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            cat = row.get("Host_Category", row.get("host_category", ""))
            n = row.get("len", row.get("count", "0"))
            if cat:
                counts[cat] = int(n)
    return counts


def parse_derep_summary(work_dir):
    """Parse 07_cluster/derep.summary.tsv."""
    fpath = Path(work_dir) / "07_cluster/derep.summary.tsv"
    if not fpath.is_file():
        return []
    rows = []
    with open(fpath) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def parse_info_summary(work_dir):
    """Parse 05_metadata/Plant_Virus_Info.summary text file."""
    fpath = Path(work_dir) / "05_metadata/Plant_Virus_Info.summary"
    if not fpath.is_file():
        return {}
    data = {}
    with open(fpath) as f:
        content = f.read()
    # Extract key numbers with simple heuristics
    import re
    m = re.search(r"总序列条数.*?([\d,]+)", content)
    if m:
        data["total_seqs"] = int(m.group(1).replace(",", ""))
    m = re.search(r"包含的独特物种.*?([\d,]+)", content)
    if m:
        data["unique_taxids"] = int(m.group(1).replace(",", ""))
    m = re.search(r"最短序列.*?([\d,]+)\s*bp", content)
    if m:
        data["min_len"] = int(m.group(1).replace(",", ""))
    m = re.search(r"最长序列.*?([\d,]+)\s*bp", content)
    if m:
        data["max_len"] = int(m.group(1).replace(",", ""))
    m = re.search(r"平均长度.*?([\d,]+)", content)
    if m:
        data["mean_len"] = float(m.group(1).replace(",", ""))
    m = re.search(r"拥有至少1条完整基因组的物种.*?([\d,]+)", content)
    if m:
        data["complete_taxids"] = int(m.group(1).replace(",", ""))
    m = re.search(r"完整物种占比.*?([\d.]+)\s*%", content)
    if m:
        data["complete_ratio"] = float(m.group(1))
    return data


def main():
    parser = argparse.ArgumentParser(
        description="植物病毒数据库构建 Pipeline 总结报告"
    )
    parser.add_argument("--work-dir", default=os.path.expanduser("~/plant_virus_db"),
                        help="Pipeline 工作目录 (默认: ~/plant_virus_db)")
    parser.add_argument("--short", action="store_true",
                        help="仅输出摘要 (Abstract only)")
    args = parser.parse_args()

    wd = args.work_dir
    if not os.path.isdir(wd):
        print(f"错误: 工作目录不存在: {wd}")
        sys.exit(1)

    # ===========================================
    # Gather all data
    # ===========================================
    artifact_stats = {}
    for stage_dir, files in ARTIFACTS.items():
        for fname, desc in files.items():
            count, exists = count_lines(wd, f"{stage_dir}/{fname}")
            artifact_stats[f"{stage_dir}/{fname}"] = (count, exists, desc)

    host_counts = parse_summary_counts(wd)
    derep_data = parse_derep_summary(wd)
    info_summary = parse_info_summary(wd)

    # Derived metrics
    n_raw_seq = count_lines(wd, "04_sequences/plant.virus.fasta")[0]
    n_dedup_seq = count_lines(wd, "06_dedup/plant.final.rmdup.fasta")[0]
    n_final_seq = count_lines(wd, "07_cluster/final.cluster.ref.fasta")[0]
    n_raw_taxid = info_summary.get("unique_taxids")
    n_final_info = count_lines(wd, "07_cluster/final.cluster.ref_info.tsv")[0]

    # ===========================================
    # Output
    # ===========================================
    print()
    print("=" * 78)
    print("  植物病毒参考基因组数据库构建 Pipeline — 运行总结报告")
    print("=" * 78)

    if not args.short:
        print()
        print("─" * 78)
        print("  ABSTRACT")
        print("─" * 78)
        print()
        print(f"  We constructed a non-redundant plant virus reference genome database")
        print(f"  by integrating metadata from NCBI Virus, KEGG Virus-Host DB, and ICTV VMR.")
        print(f"  Starting from {format_count(n_raw_seq)} raw plant virus sequences")
        print(f"  (representing {format_count(n_raw_taxid)} unique viral TaxIDs), a multi-stage")
        print(f"  deduplication pipeline (metadata-driven waterfall + seqkit 100% identity")
        print(f"  removal + MMseqs2 98% ANI clustering + vclust ANI-based compression)")
        print(f"  yielded {format_count(n_final_seq)} representative genome sequences")
        print(f"  spanning {format_count(n_final_info)} TaxIDs, suitable for downstream")
        print(f"  comparative genomics and phylogenomic analyses.")

    # ===========================================
    # Results
    # ===========================================
    print()
    print("─" * 78)
    print("  RESULTS")
    print("─" * 78)

    # --- Stage A ---
    print()
    print("  1. Metadata Integration (Stage A)")
    merged_count, _, _ = artifact_stats.get(
        "01_merge/Merged.VHostMetadata.tsv", (None, False, ""))
    imputed_count, _, _ = artifact_stats.get(
        "01_merge/Merged.VHostMetadata.imputer.tsv", (None, False, ""))
    lineage_count, _, _ = artifact_stats.get(
        "01_merge/Merged.VHostMetadata.lineage.tsv", (None, False, ""))
    bad_rows, _, _ = artifact_stats.get(
        "01_merge/bad_rows_log.tsv", (None, False, ""))

    print(f"      Merged VHDB + NCBI records:  {format_count(merged_count)}")
    print(f"      After host imputation:        {format_count(imputed_count)}")
    print(f"      After lineage annotation:     {format_count(lineage_count)}")
    if bad_rows:
        print(f"      Malformed rows filtered:      {format_count(bad_rows)}")

    # --- Stage B ---
    print()
    print("  2. ICTV VMR Classification (Stage B)")
    vmr_plant, _, _ = artifact_stats.get(
        "02_ictv/VMR_Split_By_Host/VMR_Plant.tsv", (None, False, ""))
    vmr_animal, _, _ = artifact_stats.get(
        "02_ictv/VMR_Split_By_Host/VMR_Animal.tsv", (None, False, ""))
    vmr_fungi, _, _ = artifact_stats.get(
        "02_ictv/VMR_Split_By_Host/VMR_Fungi.tsv", (None, False, ""))
    vmr_bacteria, _, _ = artifact_stats.get(
        "02_ictv/VMR_Split_By_Host/VMR_Bacteria.tsv", (None, False, ""))
    rescue_fail_count, _, _ = artifact_stats.get(
        "02_ictv/VMR_Split_By_Host/Rescue_Failed_Details.tsv", (None, False, ""))

    print(f"      Plant VMR records:            {format_count(vmr_plant)}")
    print(f"      Animal VMR records:           {format_count(vmr_animal)}")
    print(f"      Fungi VMR records:            {format_count(vmr_fungi)}")
    print(f"      Bacteria VMR records:         {format_count(vmr_bacteria)}")
    if rescue_fail_count:
        print(f"      Dark-matter rescue failures:  {format_count(rescue_fail_count)}")

    # --- Stage C ---
    print()
    print("  3. Host Classification (Stage C)")
    final_lineage_count, _, _ = artifact_stats.get(
        "03_host/host_extract/Final_Virus_Host_Lineage.tsv", (None, False, ""))
    plant_tsv_count, _, _ = artifact_stats.get(
        "03_host/VHostMetadata/Plant.tsv", (None, False, ""))

    print(f"      Total classified records:     {format_count(final_lineage_count)}")
    if host_counts:
        for cat in ["Human", "Animal", "Plant", "Bacteria", "Fungi",
                     "Protist", "Oomycetes", "Unknown", "Environmental_NCBI", "Archaea"]:
            if cat in host_counts:
                print(f"        {cat:<25} {host_counts[cat]:>12,}")

    # --- Stage D ---
    print()
    print("  4. Sequence Retrieval (Stage D)")
    local_seq, _, _ = artifact_stats.get(
        "04_sequences/Plant_virus_db/Plant_Extracted_Sequences.fasta", (None, False, ""))
    missing_ids, _, _ = artifact_stats.get(
        "04_sequences/Plant_virus_db/Plant_missing_accessions.txt", (None, False, ""))
    dl_seq, _, _ = artifact_stats.get(
        "04_sequences/Plant_virus_db/Downloaded_Plant_Viruses.fasta", (None, False, ""))

    print(f"      Extracted from local DB:      {format_count(local_seq)}")
    print(f"      Missing accessions:           {format_count(missing_ids)}")
    print(f"      Downloaded via NCBI efetch:   {format_count(dl_seq)}")
    print(f"      Total assembled sequences:    {format_count(n_raw_seq)}")

    # --- Stage E ---
    print()
    print("  5. Metadata Completion (Stage E)")
    print(f"      Total records in info table:  {format_count(info_summary.get('total_seqs'))}")
    print(f"      Unique TaxIDs:                {format_count(info_summary.get('unique_taxids'))}")
    print(f"      Length range:                 {format_count(info_summary.get('min_len'))} "
          f"- {format_count(info_summary.get('max_len'))} bp")
    print(f"      Mean length:                  {info_summary.get('mean_len', 'N/A')}")
    print(f"      TaxIDs with complete genome:  {format_count(info_summary.get('complete_taxids'))}"
          f" ({info_summary.get('complete_ratio', 'N/A')}%)")

    # --- Stage F ---
    print()
    print("  6. Classification and Deduplication (Stage F)")
    classified_count, _, _ = artifact_stats.get(
        "06_dedup/split_results/All_Classified_Virus_Info.tsv", (None, False, ""))
    dedup_info, _, _ = artifact_stats.get(
        "06_dedup/virus.dedup/Final_Deduplicated_Info.tsv", (None, False, ""))
    ns_dedup_seq, _, _ = artifact_stats.get(
        "06_dedup/virus.dedup/Final_NonSegmented_Deduplicated.fasta", (None, False, ""))
    seg_dedup_seq, _, _ = artifact_stats.get(
        "06_dedup/virus.dedup/Final_Segmented_Deduplicated.fasta", (None, False, ""))
    ns_final_seq, _, _ = artifact_stats.get(
        "06_dedup/Final_DB_Build/nonsegmented_mmseqs_0.98.fasta", (None, False, ""))
    seg_final_seq, _, _ = artifact_stats.get(
        "06_dedup/Final_DB_Build/segmented_mmseqs_0.98.fasta", (None, False, ""))

    print(f"      Classified records (F2):      {format_count(classified_count)}")
    print(f"      After metadata dedup (F3):    {format_count(dedup_info)}")
    print(f"      Non-segmented (F3):           {format_count(ns_dedup_seq)}")
    print(f"      Segmented (F3):               {format_count(seg_dedup_seq)}")
    print(f"      Non-segmented after mmseqs:   {format_count(ns_final_seq)}")
    print(f"      Segmented after mmseqs:       {format_count(seg_final_seq)}")
    print(f"      Combined dedup total:         {format_count(n_dedup_seq)}")

    # --- Stage G ---
    print()
    print("  7. Clustering and Final Assessment (Stage G)")
    lca_count, _, _ = artifact_stats.get(
        "07_cluster/clusters_with_LCA.tsv", (None, False, ""))
    cov_count, _, _ = artifact_stats.get(
        "07_cluster/virus_genes_cov.tsv", (None, False, ""))

    print(f"      Final reference sequences:    {format_count(n_final_seq)}")
    print(f"      Final reference TaxIDs:       {format_count(n_final_info)}")

    # Dereplication summary table
    if derep_data:
        print(f"      LCA conflict clusters:        {format_count(lca_count)}")
        print(f"      Virus genes coverage records: {format_count(cov_count)}")
        print()
        print("      Dereplication progression:")
        header = list(derep_data[0].keys())
        # print table header
        print(f"      {'Dataset':<45} {'Seqs':>12} {'TaxID_Retention%':>16}")
        print(f"      {'-'*43}  {'-'*10}  {'-'*14}")
        for row in derep_data:
            ds = row.get("Dataset", "")
            seqs = row.get("Sequences_Count", "")
            tax_ret = row.get("TaxID_Retention(%)", row.get("TaxID_Retention(%)", ""))
            # Shorten long filenames
            if len(ds) > 43:
                ds = ds[:40] + "..."
            print(f"      {ds:<45} {seqs:>12} {tax_ret:>16}")

    # ===========================================
    # Final metrics
    # ===========================================
    print()
    print("─" * 78)
    print("  FINAL DATABASE METRICS")
    print("─" * 78)
    print()

    if n_raw_seq and n_final_seq:
        seq_reduction = (1 - n_final_seq / n_raw_seq) * 100
        print(f"  Raw sequences (plant.virus.fasta):            {format_count(n_raw_seq)}")
        print(f"  After metadata dedup + mmseqs (rmdup.fasta):  {format_count(n_dedup_seq)}")
        print(f"  Final reference (cluster.ref.fasta):           {format_count(n_final_seq)}")
        print(f"  Overall sequence reduction:                     {seq_reduction:.1f}%")

    if n_raw_taxid and n_final_info:
        taxid_retention = n_final_info / n_raw_taxid * 100
        print(f"  Raw TaxIDs:                                    {format_count(n_raw_taxid)}")
        print(f"  Final TaxIDs retained:                         {format_count(n_final_info)}")
        print(f"  TaxID retention rate:                          {taxid_retention:.1f}%")

    print()
    print("─" * 78)
    print("  DATA AVAILABILITY")
    print("─" * 78)
    print()
    print(f"  The final reference genome database (FASTA + TSV metadata) is available at:")
    print(f"    {wd}/07_cluster/final.cluster.ref.fasta")
    print(f"    {wd}/07_cluster/final.cluster.ref_info.tsv")
    print(f"  All intermediate artifacts and stage-level logs are preserved at:")
    print(f"    {wd}/00_logs/  (pipeline execution logs)")
    print(f"    {wd}/01_merge/ through 07_cluster/ (stage-specific outputs)")
    print()
    print("=" * 78)


if __name__ == "__main__":
    main()
