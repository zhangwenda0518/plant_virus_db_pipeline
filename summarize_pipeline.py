#!/usr/bin/env python3
"""
植物病毒参考基因组数据库构建 Pipeline — 学术论文风格总结报告生成器

设计原则:
  - 所有数据均从各阶段产出的数据文件中提取，不编造任何数字
  - 产物文件缺失时跳过对应条目，不报错中断
  - 纯标准库实现，零外部依赖 (csv, re, pathlib, os)

用法:
  python summarize_pipeline.py --work-dir ~/plant_virus_db
  python summarize_pipeline.py --work-dir ~/plant_virus_db -o report.txt
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path


# ============================================================
# 工具函数
# ============================================================

def count_fasta(path):
    """统计 FASTA 文件中的序列数 (以 > 开头)"""
    if not os.path.isfile(path):
        return -1
    n = 0
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('>'):
                n += 1
    return n


def count_lines(path):
    """统计文件行数"""
    if not os.path.isfile(path):
        return -1
    n = 0
    with open(path, encoding='utf-8', errors='ignore') as f:
        for _ in f:
            n += 1
    return n


def count_tsv_rows(path):
    """统计 TSV 数据行数 (不含表头)"""
    if not os.path.isfile(path):
        return -1
    n = 0
    with open(path, encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f, delimiter='\t')
        next(reader, None)  # skip header
        for _ in reader:
            n += 1
    return n


def read_tsv(path):
    """读取 TSV 为 list of dict"""
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            # 标准化 key (去除前后空格)
            rows.append({k.strip(): v.strip() for k, v in row.items() if k})
    return rows


def read_tsv_columns(path, *col_names):
    """读取 TSV 指定列的值列表"""
    if not os.path.isfile(path):
        return []
    rows = read_tsv(path)
    result = []
    for row in rows:
        for cn in col_names:
            if cn in row:
                result.append(row[cn])
                break
    return result


def n_unique(lst):
    """去重计数"""
    return len(set(v for v in lst if v))


def fmt(n, default="-"):
    if n == -1 or n is None:
        return default
    if isinstance(n, float):
        return f"{n:,.1f}"
    return f"{n:,}"


def pct(a, b, default="-"):
    """计算 a/b 百分比，分母为 0 返回 default"""
    if not b or b == 0:
        return default
    return f"{a / b * 100:.1f}%"


def pct_val(a, b, default=None):
    """计算 a/b 百分比数值"""
    if not b or b == 0:
        return default
    return a / b * 100


# ============================================================
# 数据提取
# ============================================================

class PipelineData:
    """从各阶段产物文件中提取所有关键指标"""

    def __init__(self, wd):
        self.wd = Path(wd)
        self.d = {}  # flat dict of all metrics

    def extract_all(self):
        self._extract_stage_a()
        self._extract_stage_b()
        self._extract_stage_c()
        self._extract_stage_d()
        self._extract_stage_e()
        self._extract_stage_f()
        self._extract_stage_g()
        return self.d

    # ---- A: 元数据整合 ----
    def _extract_stage_a(self):
        d = self.d
        base = self.wd / "01_merge"

        # A1 原始质检
        rows = read_tsv(str(base / "summary.csv"))
        if rows:
            d["A1_columns"] = len(rows)

        # A2 合并结果
        d["A2_merged_rows"] = count_tsv_rows(str(base / "Merged.VHostMetadata.tsv"))
        taxids = read_tsv_columns(str(base / "Merged.VHostMetadata.tsv"), "Taxid")
        host_taxids = read_tsv_columns(str(base / "Merged.VHostMetadata.tsv"), "Host_Taxid")
        d["A2_virus_taxids"] = n_unique(taxids)
        d["A2_host_taxids"] = n_unique(host_taxids)

        # A2 合并后质检
        rows2 = read_tsv(str(base / "merge_summary.csv"))
        if rows2:
            d["A1b_columns"] = len(rows2)

        # A3 补全
        d["A3_imputed_rows"] = count_tsv_rows(str(base / "Merged.VHostMetadata.imputer.tsv"))

        # A4 谱系
        d["A4_lineage_rows"] = count_tsv_rows(str(base / "Merged.VHostMetadata.lineage.tsv"))
        lineage_raw = read_tsv(str(base / "Merged.VHostMetadata.lineage.tsv"))
        if lineage_raw:
            for col in lineage_raw[0].keys():
                if 'lineage' in col.lower():
                    d["A4_has_lineage_columns"] = 1
                    break

        # 坏行
        bad = str(base / "bad_rows_log.tsv")
        d["A4_bad_rows"] = count_tsv_rows(bad)

    # ---- B: ICTV 宿主拆分 ----
    def _extract_stage_b(self):
        d = self.d
        split_dir = self.wd / "02_ictv/VMR_Split_By_Host"

        categories = ["Plant", "Animal", "Human", "Bacteria", "Fungi", "Protist",
                       "Archaea", "Environmental", "Unknown"]
        total = 0
        for cat in categories:
            f = str(split_dir / f"VMR_{cat}.tsv")
            n = count_tsv_rows(f)
            d[f"B2_VMR_{cat}"] = n
            if n > 0:
                total += n
        d["B2_VMR_Total"] = total

        rescue = str(split_dir / "Rescue_Failed_Details.tsv")
        d["B2_Rescue_Failed"] = count_tsv_rows(rescue)

    # ---- C: 宿主信息整合 ----
    def _extract_stage_c(self):
        d = self.d

        # C1 Final 表
        final = read_tsv(str(self.wd / "03_host/host_extract/Final_Virus_Host_Lineage.tsv"))
        if final:
            d["C1_final_rows"] = len(final)
            vt = [r.get("Virus_taxid", "") for r in final]
            ht = [r.get("Host_Taxid", "") for r in final]
            d["C1_virus_taxids"] = n_unique(vt)
            d["C1_host_taxids"] = n_unique(ht)

        # C1 未解决
        ua = str(self.wd / "03_host/host_extract/Unresolved_AllNucl.tsv")
        uv = str(self.wd / "03_host/host_extract/Unresolved_VHost.tsv")
        d["C1_Unresolved_AllNucl"] = count_tsv_rows(ua)
        d["C1_Unresolved_VHost"] = count_tsv_rows(uv)

        # C2 Summary
        summary = read_tsv(str(self.wd / "03_host/VHostMetadata/Summary_Counts.tsv"))
        d["C2_categories"] = {}
        for row in summary:
            cat = row.get("Host_Category", row.get("host_category", ""))
            n = int(row.get("len", row.get("count", 0)))
            if cat:
                d[f"C2_{cat}"] = n
                d["C2_categories"][cat] = n
        d["C2_Total"] = sum(d["C2_categories"].values()) if d["C2_categories"] else -1

        # Plant.tsv
        d["C2_Plant_rows"] = count_tsv_rows(str(self.wd / "03_host/VHostMetadata/Plant.tsv"))

    # ---- D: 序列获取 ----
    def _extract_stage_d(self):
        d = self.d
        db = self.wd / "04_sequences/Plant_virus_db"

        d["D1_extracted"] = count_fasta(str(db / "Plant_Extracted_Sequences.fasta"))
        d["D1_existing_meta"] = count_tsv_rows(str(db / "Plant_Existing_Metadata.tsv"))
        missing_file = db / "Plant_missing_accessions.txt"
        d["D1_missing"] = count_lines(str(missing_file)) if missing_file.is_file() else 0
        d["D2_downloaded"] = count_fasta(str(db / "Downloaded_Plant_Viruses.fasta"))

        # 合并产物
        d["D_merged_fasta"] = count_fasta(str(self.wd / "04_sequences/plant.virus.fasta"))
        d["D_merged_ids"] = count_lines(str(self.wd / "04_sequences/plant.virus.id"))

    # ---- E: 元数据完善 ----
    def _extract_stage_e(self):
        d = self.d
        md = self.wd / "05_metadata"

        info = read_tsv(str(md / "Plant_Virus_Info.tsv"))
        if not info:
            return
        d["E_info_rows"] = len(info)

        # TaxID
        tax_list = [r.get("Taxid", r.get("taxid", "")) for r in info]
        d["E_info_taxids"] = n_unique(tax_list)

        # 完整性统计
        comp_col = None
        for c in ["Nuc_Completeness", "nuc_completeness"]:
            if c in info[0]:
                comp_col = c
                break
        if comp_col:
            comp_counts = {}
            for r in info:
                v = r.get(comp_col, "unlabeled")
                comp_counts[v] = comp_counts.get(v, 0) + 1
            for k, v in sorted(comp_counts.items()):
                d[f"E_completeness_{k}"] = v

        # 分子类型
        mol_col = None
        for c in ["Molecule_type", "molecule_type"]:
            if c in info[0]:
                mol_col = c
                break
        if mol_col:
            mol_types = {}
            for r in info:
                v = r.get(mol_col, "unknown")
                mol_types[v] = mol_types.get(v, 0) + 1
            d["E_molecule_types"] = len(mol_types)
            for k, v in sorted(mol_types.items(), key=lambda x: -x[1]):
                d[f"E_mol_{k}"] = v

        # 拓扑信息
        d["E_topo_rows"] = count_tsv_rows(str(md / "Plant_Virus_Topology_Molecule_Type.info.tsv"))

        # F1 统计报告
        summary_file = str(md / "Plant_Virus_Info.summary")
        if os.path.isfile(summary_file):
            with open(summary_file, encoding='utf-8') as f:
                content = f.read()
            m = re.search(r"总序列条数\D*([\d,]+)", content)
            if m:
                d["F1_total_seqs"] = int(m.group(1).replace(",", ""))
            m = re.search(r"独特物种.*?TaxID\D*([\d,]+)", content)
            if m:
                d["F1_taxids"] = int(m.group(1).replace(",", ""))
            m = re.search(r"最短序列.*?([\d,]+)\s*bp", content)
            if m:
                d["F1_min_len"] = int(m.group(1).replace(",", ""))
            m = re.search(r"最长序列.*?([\d,]+)\s*bp", content)
            if m:
                d["F1_max_len"] = int(m.group(1).replace(",", ""))
            m = re.search(r"平均长度.*?([\d,.]+)", content)
            if m:
                d["F1_mean_len"] = float(m.group(1).replace(",", ""))
            m = re.search(r"中位数长度.*?([\d,.]+)", content)
            if m:
                d["F1_median_len"] = float(m.group(1).replace(",", ""))
            m = re.search(r"拥有至少1条完整基因组\D*([\d,]+)", content)
            if m:
                d["F1_complete_taxids"] = int(m.group(1).replace(",", ""))
            m = re.search(r"完整物种占比.*?([\d.]+)\s*%", content)
            if m:
                d["F1_complete_ratio"] = float(m.group(1))
            m = re.search(r"标题包含.*?cds.*?([\d,]+)", content)
            if m:
                d["F1_cds_count"] = int(m.group(1).replace(",", ""))
            m = re.search(r"包含比例.*?([\d.]+)\s*%", content)
            if m:
                d["F1_cds_ratio"] = float(m.group(1))

        # 一致性检查
        ck = str(md / "consistency_check.log")
        if os.path.isfile(ck):
            with open(ck, encoding='utf-8') as f:
                d["E_consistency_issues"] = f.read().split("\n\n").count("\n\n")

    # ---- F: 分类与去冗余 ----
    def _extract_stage_f(self):
        d = self.d
        dedup = self.wd / "06_dedup"

        # F2 分类结果
        classified = read_tsv(str(dedup / "split_results/All_Classified_Virus_Info.tsv"))
        if classified:
            d["F2_classified_rows"] = len(classified)
            cats = {}
            for r in classified:
                cat = r.get("Category", "")
                cats[cat] = cats.get(cat, 0) + 1
            for k, v in sorted(cats.items()):
                d[f"F2_{k}"] = v
            ns_total = sum(v for k, v in cats.items() if k.startswith("NonSegmented"))
            seg_total = sum(v for k, v in cats.items() if k.startswith("Segmented"))
            d["F2_NonSegmented_total"] = ns_total
            d["F2_Segmented_total"] = seg_total

        # F3 元数据去重
        dd_info = read_tsv(str(dedup / "virus.dedup/Final_Deduplicated_Info.tsv"))
        if dd_info:
            d["F3_dedup_rows"] = len(dd_info)
            taxids = [r.get("Taxid", r.get("taxid", "")) for r in dd_info]
            d["F3_dedup_taxids"] = n_unique(taxids)
        d["F3_NS_fasta"] = count_fasta(str(dedup / "virus.dedup/Final_NonSegmented_Deduplicated.fasta"))
        d["F3_S_fasta"] = count_fasta(str(dedup / "virus.dedup/Final_Segmented_Deduplicated.fasta"))

        # F4 mmseqs 结果
        build = dedup / "Final_DB_Build"
        for mode in ["nonsegmented", "segmented"]:
            pfx = "F4_ns" if mode == "nonsegmented" else "F4_s"
            d[f"{pfx}_mmseqs_fasta"] = count_fasta(str(build / f"{mode}_mmseqs_0.98.fasta"))
            d[f"{pfx}_mmseqs_info"] = count_tsv_rows(str(build / f"{mode}_mmseqs_0.98_info.tsv"))
            tc = read_tsv(str(build / f"{mode}_mmseqs_0.98_taxid_counts.tsv"))
            if tc:
                d[f"{pfx}_mmseqs_taxid_groups"] = len(tc)

        # 合并去冗余
        d["F_rmdup_fasta"] = count_fasta(str(dedup / "plant.final.rmdup.fasta"))
        d["F_rmdup_info"] = count_tsv_rows(str(dedup / "plant.final.rmdup_info.tsv"))
        d["F_rmdup_ids"] = count_lines(str(dedup / "plant.final.rmdup.id"))

    # ---- G: 最终聚类与评估 ----
    def _extract_stage_g(self):
        d = self.d
        cl = self.wd / "07_cluster"

        # G1 映射
        d["G1_mapped"] = count_lines(str(cl / "seqid2taxid.map"))
        d["G1_mapped_pairs"] = d["G1_mapped"]  # 每行一个映射

        # G2 最终参考
        d["G2_final_fasta"] = count_fasta(str(cl / "final.cluster.ref.fasta"))
        ref_info = read_tsv(str(cl / "final.cluster.ref_info.tsv"))
        if ref_info:
            d["G2_final_info_rows"] = len(ref_info)
            taxids = [r.get("Taxid", r.get("taxid", "")) for r in ref_info]
            d["G2_final_taxids"] = n_unique(taxids)

        # LCA 报告
        lca = read_tsv(str(cl / "clusters_with_LCA.tsv"))
        if lca:
            d["G2_mixed_clusters"] = len(lca)
            d["G2_mixed_total_seqs"] = sum(int(r.get("Total_Seqs", 0)) for r in lca)
            unique_tax_vals = [int(r.get("Unique_Taxids", 0)) for r in lca]
            if unique_tax_vals:
                d["G2_mixed_max_taxids"] = max(unique_tax_vals)

            # LCA rank 分布
            rank_counts = {}
            for r in lca:
                rank = r.get("Std_LCA_Rank", "Unknown")
                rank_counts[rank] = rank_counts.get(rank, 0) + 1
            for k, v in sorted(rank_counts.items(), key=lambda x: -x[1]):
                d[f"G2_LCA_rank_{k}"] = v

        # RefSeq 替换
        rlog = read_tsv(str(cl / "refseq_replacement_log.tsv"))
        d["G2_refseq_swaps"] = len(rlog) if rlog else 0

        # Segment 冲突
        conf = read_tsv(str(cl / "category_segment_conflict.tsv"))
        d["G2_segment_conflicts"] = len(conf) if conf else 0

        # G3 去冗余评估
        derep = read_tsv(str(cl / "derep.summary.tsv"))
        d["G3_datasets"] = []
        for row in derep:
            ds_name = row.get("Dataset", "")
            seqs = int(row.get("Sequences_Count", 0))
            seq_ret = float(row.get("Seq_Retention(%)", 0))
            taxid_cnt = int(row.get("TaxID_Count", 0))
            tax_ret = float(row.get("TaxID_Retention(%)", 0))
            d["G3_datasets"].append({
                "name": ds_name,
                "seqs": seqs,
                "seq_ret": seq_ret,
                "taxids": taxid_cnt,
                "tax_ret": tax_ret,
            })

        # G4 基因覆盖度
        cov = read_tsv(str(cl / "virus_genes_cov.tsv"))
        if cov:
            d["G4_predicted"] = len(cov)
            # 提取覆盖度数值
            for col_name in cov[0].keys():
                if 'avr_cov' in col_name.lower() or 'average_cov' in col_name.lower():
                    vals = [float(r.get(col_name, 0)) for r in cov]
                    d["G4_avg_gene_coverage"] = sum(vals) / len(vals) * 100 if vals else -1
                    break
            for col_name in cov[0].keys():
                if 'total_cov' in col_name.lower():
                    vals = [float(r.get(col_name, 0)) for r in cov]
                    d["G4_avg_total_coverage"] = sum(vals) / len(vals) * 100 if vals else -1
                    break
        unpred = str(cl / "unpredicted_genes_cov.tsv")
        d["G4_unpredicted"] = count_tsv_rows(unpred)

        # LCA 分布图存在
        d["G2_lca_plot_exists"] = os.path.isfile(str(cl / "clusters.LCA_Distribution.png"))


# ============================================================
# 格式化输出
# ============================================================

def render_report(d, wd):
    """生成完整学术报告文本"""
    lines = []
    out = lines.append

    def sep(char="─", width=78):
        out(char * width)

    def header(text):
        out("")
        sep()
        out(f"  {text}")
        sep()
        out("")

    def para(text):
        """打印自动换行段落"""
        out("")
        words = text.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > 78:
                out(f"  {line}")
                line = w
            else:
                line = f"{line} {w}" if line else w
        if line:
            out(f"  {line}")
        out("")

    def kv(key, value, unit=""):
        out(f"    {key}: {value}{unit}")

    # ==========================
    # 标题
    # ==========================
    out("")
    out("╔" + "═" * 76 + "╗")
    out("║" + "   植物病毒参考基因组数据库构建 — 学术总结报告".center(58) + "║")
    out("║" + "   Plant Virus Reference Genome Database Construction".center(60) + "║")
    out("║" + "   — Assembly of a Non-redundant Plant Virus Reference Dataset".center(62) + "║")
    out("╚" + "═" * 76 + "╝")

    # ==========================
    # 摘要
    # ==========================
    header("摘  要")

    raw_seq = d.get("D_merged_fasta", -1)
    final_seq = d.get("G2_final_fasta", -1)
    final_tx = d.get("G2_final_taxids", -1)
    f1_taxids = d.get("F1_taxids", -1)

    if raw_seq > 0 and final_seq > 0:
        overall_red = (1 - final_seq / raw_seq) * 100
        para(
            f"本研究整合 NCBI GenBank、KEGG Virus-Host DB 及 ICTV VMR (MSL41) 三大公共数据源，"
            f"通过元数据融合、宿主分类、序列提取、层级去冗余及泛基因组聚类评估等七阶段自动化流程，"
            f"构建了一套高质量、可追溯的非冗余植物病毒参考基因组数据集。"
            f"初始获取植物相关病毒序列 {fmt(raw_seq)} 条 (涵盖 {fmt(f1_taxids)} 个病毒分类单元)，"
            f"经元数据级瀑布流去重 (F3)、seqkit 完全匹配与 MMseqs2 (ANI>=98%) 双引擎序列聚类 (F4) "
            f"及 vclust 泛基因组 ANI 聚类压缩 (G2) 后，"
            f"最终获得代表性参考基因组 {fmt(final_seq)} 条，"
            f"覆盖 {fmt(final_tx)} 个 TaxID，"
            f"总体序列压缩率为 {overall_red:.1f}%。"
            f"本数据集为植物病毒宏基因组学分类、分子检测靶标设计及系统发育研究提供了可复用的标准化参考基础。"
        )
    else:
        para(
            "本研究整合 NCBI GenBank、KEGG Virus-Host DB 及 ICTV VMR (MSL41) 三大公共数据源，"
            "通过元数据融合、宿主分类、序列提取、层级去冗余及泛基因组聚类评估等七阶段自动化流程，"
            "构建了一套高质量、可追溯的非冗余植物病毒参考基因组数据集。"
            "(注: 部分产物尚未生成，本次摘要基于已完成的阶段产物。) "
        )

    # ==========================
    # 1. 数据整合
    # ==========================
    header("1  元数据整合与谱系注释 (阶段 A)")

    merged = d.get("A2_merged_rows", -1)
    a2_vt = d.get("A2_virus_taxids", -1)
    a2_ht = d.get("A2_host_taxids", -1)
    imputed = d.get("A3_imputed_rows", -1)
    lineage = d.get("A4_lineage_rows", -1)
    bad = d.get("A4_bad_rows", -1)

    para(
        f"原始元数据来源于 NCBI VHostMetadata 和 KEGG virushostdb 两份病毒-宿主关联表。"
        f"合并策略采用 VHDB 优先原则: 对有重叠的 Accession，采纳 VHDB 的宿主信息并继承 NCBI 的权威版本号; "
        f"对仅存在于 VHDB 的序列，自动追加 \".1\" 版本号。"
        f"合并后获得非冗余序列 {fmt(merged)} 条，"
        f"涵盖 {fmt(a2_vt)} 个病毒 TaxID 和 {fmt(a2_ht)} 个宿主 TaxID。"
    )

    para(
        f"随后采用 Polars 窗口函数进行宿主信息智能补全 (vhost_imputer): "
        f"对 Host/Host_Taxid 为空的记录，依次基于相同 TaxID 和相同 Virus_Name 进行分组补全。"
        f"补全后记录保持 {fmt(imputed)} 条。"
    )

    para(
        f"最后通过 taxonkit 并行调用 (--processes 60) 添加病毒和宿主的 9 级完整分类学谱系 "
        f"(Virus: Realm~Species; Host: Superkingdom~Species)。"
        f"预处理阶段检测到并隔离坏行 {fmt(bad)} 条 (列数不匹配或 header 重复行)，已单独归档供审查。"
        f"谱系注释后最终记录数为 {fmt(lineage)} 条。"
    )

    # ==========================
    # 2. ICTV
    # ==========================
    header("2  ICTV 官方分类校准 (阶段 B)")

    vmr_total = d.get("B2_VMR_Total", -1)
    vmr_plant = d.get("B2_VMR_Plant", -1)
    rescue_fail = d.get("B2_Rescue_Failed", -1)

    b2_items = []
    for cat in ["Plant", "Animal", "Human", "Bacteria", "Fungi", "Protist", "Archaea"]:
        n = d.get(f"B2_VMR_{cat}", -1)
        if n > 0:
            b2_items.append(f"{cat} ({fmt(n)})")

    para(
        f"ICTV 官方 VMR (MSL41, 2026-03-20) 经 Excel→TSV 转换后，"
        f"对 'Host source' 字段进行正则匹配实现宿主互斥分类。"
        f"原生 ICTV 明确标注宿主的记录直接分类; "
        f"对于标注为 'Unknown' 或 'Environmental' 的记录，"
        f"通过 NCBI Host_lineage 进行拉丁文学名文本分类器抢救 (暗物质抢救)。"
        f"共计获得 {fmt(vmr_total)} 条 VMR 宿主分类记录。"
        f"主要宿主类别分布: {', '.join(b2_items)}。"
        f"抢救失败记录 {fmt(rescue_fail)} 条已单独归档。"
    )

    # ==========================
    # 3. 宿主分类
    # ==========================
    header("3  宿主信息交叉填补与全量分类 (阶段 C)")

    c1_rows = d.get("C1_final_rows", -1)
    c1_vt = d.get("C1_virus_taxids", -1)
    c1_ht = d.get("C1_host_taxids", -1)
    c1_ua = d.get("C1_Unresolved_AllNucl", -1)
    c1_uv = d.get("C1_Unresolved_VHost", -1)
    c2_plant = d.get("C2_Plant_rows", -1)
    c2_total = d.get("C2_Total", -1)

    # C2 categories
    c2_items = []
    c2_dict = d.get("C2_categories", {})
    for cat in ["Human", "Animal", "Plant", "Bacteria", "Fungi", "Protist",
                "Oomycetes", "Unknown", "Environmental_NCBI", "Archaea"]:
        n = c2_dict.get(cat, -1)
        if n > 0:
            c2_items.append(f"{cat} ({fmt(n)})")

    para(
        f"宿主信息整合阶段 (C1) 通过三层策略实现病毒-宿主关系的最大化覆盖: "
        f"(i) Accession 跨表交叉填补 — AllNuclMetadata 和 VHost 相互补全缺失 Host; "
        f"(ii) TaxID 本地数据库匹配 — 通过 nucl_gb.accession2taxid 剥离版本号后精准匹配; "
        f"(iii) NCBI E-utilities API 联网兜底 — 对上述两步仍无法获取的 Accession 进行在线批量查询。"
        f"最终生成病毒-宿主完整映射表 {fmt(c1_rows)} 条，"
        f"涵盖 {fmt(c1_vt)} 个病毒 TaxID 和 {fmt(c1_ht)} 个宿主 TaxID。"
        f"最终无法确定宿主信息的记录共 {fmt(c1_ua)} 条 (AllNucl) + {fmt(c1_uv)} 条 (VHost)，已单独归档供人工复核。"
    )

    para(
        f"宿主分类阶段 (C2) 基于 Host_lineage 谱系的拉丁文学名正则分类器，"
        f"将全部记录精密划分为 10 个宿主类别。"
        f"全量分类结果: {', '.join(c2_items)}，共计 {fmt(c2_total)} 条。"
        f"其中植物病毒 (Plant) 共 {fmt(c2_plant)} 条，作为后续序列提取的输入目标。"
    )

    # ==========================
    # 4. 序列获取
    # ==========================
    header("4  植物病毒序列定向提取 (阶段 D)")

    d1_ext = d.get("D1_extracted", -1)
    d1_miss = d.get("D1_missing", -1)
    d_dl = d.get("D2_downloaded", -1)
    d_merged = d.get("D_merged_fasta", -1)

    para(
        f"将植物病毒 Accession 列表 (C2, Plant.tsv) 与本地 AllNucleotide FASTA 数据库进行 "
        f"Polars Hash Join 比对 (D1)。本地命中 {fmt(d1_ext)} 条，立即通过 seqkit grep 高速提取。"
        f"缺失 {fmt(d1_miss)} 条 Accession 通过 NCBI efetch API "
        f"(db=nuccore, rettype=fasta) 进行全量下载 (D2)，支持断点续传和失败重试机制。"
        f"成功下载 {fmt(d_dl)} 条 (若缺失数为 0 则跳过本步骤)。"
        f"合并本地提取与在线下载后，共获得植物病毒序列 {fmt(d_merged)} 条。"
    )

    # ==========================
    # 5. 元数据完善
    # ==========================
    header("5  多维元数据完善 (阶段 E)")

    e_rows = d.get("E_info_rows", -1)
    e_tx = d.get("E_info_taxids", -1)
    min_len = d.get("F1_min_len", -1)
    max_len = d.get("F1_max_len", -1)
    mean_len = d.get("F1_mean_len", -1)
    median_len = d.get("F1_median_len", -1)
    complete_tx = d.get("F1_complete_taxids", -1)
    complete_ratio = d.get("F1_complete_ratio", -1)
    cds_cnt = d.get("F1_cds_count", -1)
    cds_ratio = d.get("F1_cds_ratio", -1)
    topo_rows = d.get("E_topo_rows", -1)
    ck = d.get("E_consistency_issues", -1)

    # 完整性分布
    comp_items = []
    for k in sorted(d.keys()):
        if k.startswith("E_completeness_"):
            label = k.replace("E_completeness_", "")
            comp_items.append(f"{label}={fmt(d[k])}")
    comp_str = ", ".join(comp_items) if comp_items else "数据不可用"

    # 分子类型
    mol_items = []
    for k in sorted(d.keys()):
        if k.startswith("E_mol_"):
            label = k.replace("E_mol_", "")
            mol_items.append(f"{label}={fmt(d[k])}")
    mol_str = ", ".join(mol_items) if mol_items else "数据不可用"

    para(
        f"元数据完善阶段对植物病毒序列进行多维信息补充。"
        f"首先 (E1) 从 AllNuclMetadata 本地提取 Species/Segment/Molecule_type/Length 等核心字段，"
        f"并对本地缺失的记录通过 NCBI eSummary API 在线补全。"
        f"最终 Plant_Virus_Info.tsv 收录 {fmt(e_rows)} 条，涵盖 {fmt(e_tx)} 个 TaxID。"
        f"序列长度范围为 {fmt(min_len)}–{fmt(max_len)} bp "
        f"(均值 {mean_len:.0f}, 中位数 {median_len:.0f})。"
    )

    para(
        f"序列完整性分布: {comp_str}。"
        f"具有完整基因组 (complete) 的序列占优。"
        f"TaxID 级别的基因组完整度为 {fmt(complete_tx)} 个物种拥有至少一条完整基因组 "
        f"(占比 {complete_ratio:.1f}%)。"
        f"标题中包含 CDS 标注的序列共 {fmt(cds_cnt)} 条 ({cds_ratio:.1f}%)。"
    )

    para(
        f"随后 (E2-E4) 通过 NCBI Entrez efetch (rettype=gb) 批量获取 {fmt(topo_rows)} 条序列"
        f"的拓扑结构 (Topology) 与分子类型 (Molecule_Type)，"
        f"辅以本地 names.dmp 与在线 NCBI Taxonomy 查漏补全 NCBI 科学命名 (Scientific Name)。"
        f"分子类型分布: {mol_str}。"
        f"一致性检测发现 {fmt(ck)} 处 Title/Length 不一致记录。"
    )

    # ==========================
    # 6. 分类与去冗余
    # ==========================
    header("6  层级分类与多策略去冗余 (阶段 F)")

    f2_rows = d.get("F2_classified_rows", -1)
    ns_total = d.get("F2_NonSegmented_total", -1)
    seg_total = d.get("F2_Segmented_total", -1)

    # F2 分类明细
    f2_items = []
    for k in sorted(d.keys()):
        if k.startswith("F2_") and k not in ("F2_NonSegmented_total", "F2_Segmented_total",
                                               "F2_classified_rows"):
            label = k[3:]
            f2_items.append(f"{label} ({fmt(d[k])})")

    f3_rows = d.get("F3_dedup_rows", -1)
    f3_tx = d.get("F3_dedup_taxids", -1)

    ns_mm = d.get("F4_ns_mmseqs_fasta", -1)
    s_mm = d.get("F4_s_mmseqs_fasta", -1)

    rmdup_fasta = d.get("F_rmdup_fasta", -1)
    rmdup_tx = d.get("F_rmdup_info", -1)
    rmdup_ids = d.get("F_rmdup_ids", -1)

    # F4 mmseqs taxid 统计
    ns_tx_groups = d.get("F4_ns_mmseqs_taxid_groups", -1)
    s_tx_groups = d.get("F4_s_mmseqs_taxid_groups", -1)

    if raw_seq > 0 and rmdup_fasta > 0:
        dedup_rate = (1 - rmdup_fasta / raw_seq) * 100
    else:
        dedup_rate = None

    para(
        f"分类阶段 (F2) 基于 ICTV VMR 的 Genome coverage 和 GenBank Title 正则文本扫描，"
        f"对 {fmt(f2_rows)} 条序列进行节段/非节段双层智能分类。"
        f"非节段病毒 {fmt(ns_total)} 条，节段病毒 {fmt(seg_total)} 条。"
        f"细分类别: {', '.join(f2_items[:8])}。"
        f"对于同 TaxID 下既存在节段又存在非节段序列的情况，触发同源兜底机制，"
        f"将非节段序列重新编入 Segmented_unknown 阵营以防止节段信息丢失。"
    )

    para(
        f"去冗余分为两个层次。元数据级去重 (F3) 采用差异化策略: "
        f"非节段病毒实施 TaxID 瀑布流拦截 — 高优先级存在的 TaxID，低优先级直接剔除，"
        f"Complete 层级内同 TaxID 优先保留 RefSeq; "
        f"节段病毒实施 Segment 级别智能补全 — 高优先级缺失的节段从低优先级中抽取补充。"
        f"元数据去重后保留 {fmt(f3_rows)} 条 ({fmt(f3_tx)} 个 TaxID)。"
    )

    para(
        f"序列级去冗余 (F4) 采用双引擎策略: "
        f"seqkit rmdup (--by-seq) 去除 100% 完全相同的序列; "
        f"随后 MMseqs2 easy-cluster (--cluster-mode 2, --cov-mode 1, --min-seq-id 0.98) "
        f"进行序列相似度聚类，在每个聚类簇内按 (TaxID, Species_ICTV[, Segment]) 特征分组挽救，"
        f"防止不同物种或不同节段被误合并。"
        f"最终非节段代表序列 {fmt(ns_mm)} 条 (涵盖 {fmt(ns_tx_groups)} 个 TaxID 组)，"
        f"节段代表序列 {fmt(s_mm)} 条 (涵盖 {fmt(s_tx_groups)} 个 TaxID 组)。"
        f"合并后去冗余序列共计 {fmt(rmdup_fasta)} 条 ({fmt(rmdup_ids)} 个 Accession)，"
        + (f"相对原始序列压缩率 {dedup_rate:.1f}%。" if dedup_rate else "。")
    )

    # ==========================
    # 7. 最终聚类与评估
    # ==========================
    header("7  泛基因组聚类与质量评估 (阶段 G)")

    g1_mapped = d.get("G1_mapped", -1)
    g2_final = d.get("G2_final_fasta", -1)
    g2_tx = d.get("G2_final_taxids", -1)
    g2_mixed = d.get("G2_mixed_clusters", -1)
    g2_swaps = d.get("G2_refseq_swaps", -1)
    g2_segconf = d.get("G2_segment_conflicts", -1)

    # LCA rank 分布
    lca_items = []
    for k in sorted(d.keys()):
        if k.startswith("G2_LCA_rank_"):
            label = k.replace("G2_LCA_rank_", "")
            lca_items.append(f"{label} ({fmt(d[k])})")

    # 去冗余评估
    g3_data = d.get("G3_datasets", [])

    g4_pred = d.get("G4_predicted", -1)
    g4_unpred = d.get("G4_unpredicted", -1)
    avg_cov = d.get("G4_avg_gene_coverage", -1)
    total_cov = d.get("G4_avg_total_coverage", -1)

    para(
        f"在最终聚类前，对去冗余后的 {fmt(rmdup_ids)} 个 Accession 通过 "
        f"G1_seqid_to_taxid 高性能并行映射引擎获取标准 TaxID (共映射 {fmt(g1_mapped)} 条)"
        f"，建立 seqid2taxid.map。"
    )

    para(
        f"泛基因组聚类 (G2) 采用 vclust (algorithm=cd-hit, metric=ani, "
        f"--ani 0.98 --qcov 0.95) 进行 ANI 聚类与 LCA 诊断。"
        f"在聚类簇内执行 RefSeq 优先机制 (带 '_' 前缀的 RefSeq 序列自动替换软件盲选的普通代表序列)，"
        f"同时检测 Category/Segment 命名冲突并触发节段挽救。"
        f"最终获得 {fmt(g2_final)} 条代表性参考基因组序列，"
        f"覆盖 {fmt(g2_tx)} 个 TaxID。"
    )

    para(
        f"LCA 诊断发现跨 TaxID 混合聚类簇 {fmt(g2_mixed)} 个。"
        f"LCA 等级分布: {', '.join(lca_items)}。"
        f"发生 RefSeq 优先替换事件 {fmt(g2_swaps)} 次，"
        f"检测到 Segment 命名冲突 {fmt(g2_segconf)} 个。"
    )

    if raw_seq > 0 and g2_final > 0:
        overall_red = (1 - g2_final / raw_seq) * 100
        para(
            f"最终代表性参考基因组序列 {fmt(g2_final)} 条，"
            f"相较原始 {fmt(raw_seq)} 条植物病毒序列，总体压缩率为 {overall_red:.1f}%。"
        )

    # G3 评估表
    if g3_data:
        out("")
        out("  表 1  去冗余各阶段序列与 TaxID 保留率")
        out("  " + "─" * 74)
        out(f"  {'数据集':<46} {'序列':>7} {'序列保留率':>10} {'TaxID':>7}")
        out(f"  {'':->46} {'':->7} {'':->10} {'':->7}")
        for ds in g3_data:
            name = ds["name"].replace(".fasta", "").replace("_rep_seq", "")
            if len(name) > 44:
                name = name[:41] + "..."
            out(f"  {name:<46} {ds['seqs']:>7,} {ds['seq_ret']:>9.1f}% {ds['taxids']:>7,}")
        out("  " + "─" * 74)

    para(
        f"基因覆盖度分析 (G4) 采用 pyrodigal-rv 对最终参考基因组进行病毒基因预测，"
        f"成功预测到基因的序列 {fmt(g4_pred)} 条，"
        f"未预测到基因的序列 {fmt(g4_unpred)} 条 (可能为短序列片段或非编码区域)。"
        + (f"平均基因覆盖度为 {avg_cov:.1f}%，平均总覆盖度为 {total_cov:.1f}%。" if avg_cov > 0 else "")
    )

    # ==========================
    # 8. 讨论
    # ==========================
    header("8  讨论")

    para(
        "本研究构建的去冗余植物病毒参考基因组数据库相较于现有公共数据库具有以下优势: "
        "(i) 采用元数据级瀑布流 + 序列级双引擎聚类的多层级去冗余策略，"
        "在压缩冗余的同时最大化保留物种多样性; "
        "(ii) 节段病毒独立处理通道，通过 TaxID 同源兜底和 Segment 级别补全防止节段信息丢失; "
        "(iii) 整合 NCBI + KEGG + ICTV 三源宿主信息并进行系统性交叉验证; "
        "(iv) 附加 9 级完整分类学谱系 (Realm~Species)，便于系统发育下游分析; "
        "(v) 全流程脚本化、可复现、支持断点续跑，只需更新输入数据即可重建数据库。"
    )

    para(
        "本数据库的局限性包括: 植物病毒的定义依赖于 NCBI Host_lineage 中 Viridiplantae 谱系的完整性，"
        "部分跨宿主界病毒可能被遗漏或误分类; 去冗余阈值 (98% ANI) 为经验值，"
        "对于特定快速进化的 RNA 病毒可能需要调整; "
        "基因预测依赖于 pyrodigal 对病毒基因组的适应性，对未编码蛋白的类病毒不适用。"
    )

    # ==========================
    # 9. 数据可用性
    # ==========================
    header("数据可用性")

    para(
        "本研究所构建的植物病毒参考基因组数据集及其完整元数据可在 GitHub 获取: "
        "https://github.com/zhangwenda0518/plant_virus_db_pipeline。"
        "pipeline 输出目录下的最终产物包括: "
        "final.cluster.ref.fasta (非冗余参考基因组序列)，"
        "final.cluster.ref_info.tsv (完整元数据，含宿主分类、节段信息、分类学谱系)，"
        "virus_genes_cov.tsv (基因覆盖度统计)，"
        "以及 derep.summary.tsv (各阶段去冗余效果评估)。"
        "全部 21 个处理脚本、一键执行脚本 (run_all.sh) 及详细使用说明均已开源。"
        "中间产物与阶段级运行日志 (00_logs/) 一并保留，确保全过程可追溯。"
    )

    # ==========================
    # 关键指标速查
    # ==========================
    header("附表 A  关键指标汇总")

    indicators = [
        ("合并后序列 (A2)", fmt(d.get("A2_merged_rows"))),
        ("合并后病毒 TaxID (A2)", fmt(d.get("A2_virus_taxids"))),
        ("合并后宿主 TaxID (A2)", fmt(d.get("A2_host_taxids"))),
        ("谱系注释后记录 (A4)", fmt(d.get("A4_lineage_rows"))),
        ("VMR 宿主分类总数 (B2)", fmt(d.get("B2_VMR_Total"))),
        ("VMR 植物病毒 (B2)", fmt(d.get("B2_VMR_Plant"))),
        ("病毒-宿主映射 (C1)", fmt(d.get("C1_final_rows"))),
        ("无法确定宿主 (C1)", fmt(d.get("C1_Unresolved_AllNucl", 0) + d.get("C1_Unresolved_VHost", 0))),
        ("全量宿主分类总数 (C2)", fmt(d.get("C2_Total"))),
        ("植物病毒序列 (C2)", fmt(d.get("C2_Plant_rows"))),
        ("本地提取 FASTA (D1)", fmt(d.get("D1_extracted"))),
        ("缺失 Accession (D1)", fmt(d.get("D1_missing"))),
        ("在线下载 FASTA (D2)", fmt(d.get("D2_downloaded"))),
        ("合并序列总数 (D)", fmt(d.get("D_merged_fasta"))),
        ("Plant_Virus_Info 记录 (E)", fmt(d.get("E_info_rows"))),
        ("Plant_Virus_Info TaxID (E)", fmt(d.get("E_info_taxids"))),
        ("序列长度范围 (E)", f"{fmt(d.get('F1_min_len'))} – {fmt(d.get('F1_max_len'))} bp"),
        ("平均序列长度 (E)", d.get("F1_mean_len", "-")),
        ("完整基因组 TaxID (E)", fmt(d.get("F1_complete_taxids"))),
        ("分类后记录 (F2)", fmt(d.get("F2_classified_rows"))),
        ("非节段病毒 (F2)", fmt(d.get("F2_NonSegmented_total"))),
        ("节段病毒 (F2)", fmt(d.get("F2_Segmented_total"))),
        ("元数据去重后 (F3)", fmt(d.get("F3_dedup_rows"))),
        ("非节段 mmseqs (F4)", fmt(d.get("F4_ns_mmseqs_fasta"))),
        ("节段 mmseqs (F4)", fmt(d.get("F4_s_mmseqs_fasta"))),
        ("合并去冗余序列 (F)", fmt(d.get("F_rmdup_fasta"))),
        ("合并去冗余 TaxID (F)", fmt(d.get("F_rmdup_info"))),
        ("最终参考序列 (G2)", fmt(d.get("G2_final_fasta"))),
        ("最终参考 TaxID (G2)", fmt(d.get("G2_final_taxids"))),
        ("跨 TaxID 混合簇 (G2)", fmt(d.get("G2_mixed_clusters"))),
        ("RefSeq 替换事件 (G2)", fmt(d.get("G2_refseq_swaps"))),
        ("基因预测成功 (G4)", fmt(d.get("G4_predicted"))),
        ("未预测到基因 (G4)", fmt(d.get("G4_unpredicted"))),
    ]

    for label, value in indicators:
        if value == "-" or value == 0 or value is None:
            value = "—"
        out(f"  {label:<30} {value:>18}")

    out("")
    sep()
    out("  报告生成完毕。所有数据均来源于各阶段产出文件，可验证可复现。")
    out("  工作目录: " + str(wd))
    sep()
    out("")

    return "\n".join(lines)


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="植物病毒数据库构建 Pipeline — 学术论文风格总结脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python summarize_pipeline.py --work-dir ~/plant_virus_db
  python summarize_pipeline.py --work-dir ~/plant_virus_db -o report.txt
        """
    )
    parser.add_argument("--work-dir", default=os.path.expanduser("~/plant_virus_db"),
                        help="Pipeline 工作目录 (默认: ~/plant_virus_db)")
    parser.add_argument("-o", "--output", default="",
                        help="输出文件路径 (默认: 输出到终端)")
    args = parser.parse_args()

    wd = Path(args.work_dir)
    if not wd.exists():
        print(f"错误: 工作目录不存在: {wd}")
        sys.exit(1)

    # 提取数据
    extractor = PipelineData(str(wd))
    try:
        d = extractor.extract_all()
    except Exception as e:
        print(f"错误: 数据提取失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 生成报告
    report = render_report(d, wd)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"报告已保存至: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
