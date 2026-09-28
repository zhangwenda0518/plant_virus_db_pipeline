#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
病毒序列双层智能分类与多维物种增量统计工具 (终极同源兜底版 + 全字段保留)
=========================================================
核心逻辑：
  1. 双层架构：【节段】与【非节段】正交拆分。
  2. 同源兜底：基于 TaxID，将节段病毒物种下未标明节段的序列自动划入 Segmented_unknown。
  3. 瀑布流增量统计：按照质量优先级，计算各分类为数据库贡献的【特有物种数】。
  4. 全字段保留：动态匹配并保留输入文件中的所有原始元数据列。
"""

import polars as pl
import os as _os
import sys as _sys

# ===== 护栏开关（只读保护，不新增删除/降级）=====
# PVDB_GUARDS=0 可完全关闭，关闭后行为与本文件 2026-09-27 版一致。
_GUARDS_ON = _os.environ.get("PVDB_GUARDS", "1") != "0"
try:
    _LIB = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "lib")
    if _LIB not in _sys.path:
        _sys.path.insert(0, _LIB)
    from pvcore import write_tsv_safe as _write_tsv_safe
except Exception:                                   # 缺库时不阻断主流程
    _write_tsv_safe = None
import argparse
import time
import os

def parse_args():
    parser = argparse.ArgumentParser(description="病毒序列双层智能分类与 FASTA 拆分工具")
    parser.add_argument("-i", "--info", required=True, help="NCBI 元数据 TSV 文件")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("-v", "--vmr", help="ICTV VMR 表（必需提供以获得最佳效果）")
    parser.add_argument("-f", "--fasta", help="本地 FASTA 文件（可选，提供则进行序列拆分）")
    parser.add_argument("--taxid-tsv", default="~/database/taxonomy/nucl_gb.accession2taxid", help="NCBI Taxonomy 映射文件")
    return parser.parse_args()

def ensure_parquet(file_path: str, sep: str) -> str:
    file_path = os.path.expanduser(file_path)
    if not os.path.exists(file_path): return None
    parquet_path = file_path + ".parquet"
    if os.path.exists(parquet_path): return parquet_path
    print(f"   ⏳ 正在对 {os.path.basename(file_path)} 进行流式极速转换...")
    pl.scan_csv(file_path, separator=sep, infer_schema_length=10000, ignore_errors=True).sink_parquet(parquet_path, compression="zstd")
    return parquet_path

def split_fasta_streaming(input_fasta: str, out_dir: str, acc_to_category: dict):
    categories = set(acc_to_category.values())
    file_handles = {cat: open(os.path.join(out_dir, f"{cat}.fasta"), 'w', encoding='utf-8') for cat in categories}

    current_handle, processed_count = None, 0
    with open(input_fasta, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            if line.startswith(">"):
                base_acc = line[1:].split()[0].split('.')[0].upper()
                cat = acc_to_category.get(base_acc)
                if cat:
                    current_handle = file_handles[cat]
                    current_handle.write(line)
                    processed_count += 1
                else:
                    current_handle = None
            elif current_handle:
                current_handle.write(line)

    for fh in file_handles.values(): fh.close()
    return processed_count

def normalize_segment_names(df: pl.DataFrame) -> pl.DataFrame:
    """段名规范化: 以 RefSeq/ICTV 的段名为 canonical, 其他段名按 core 匹配映射"""
    import collections

    def seg_core(s: str) -> str:
        if not s: return ""
        s = s.upper()
        for p in sorted(['GENOMICRNA','GENOMICDNA','SUBGENOMICRNA','DEFECTIVERNA',
                         'DSRNA','DSDNA','RNA','DNA','SEGMENT','COMPONENT'],
                        key=len, reverse=True):
            if s.startswith(p) and len(s) > len(p):
                s = s[len(p):]
                break
        return s.strip()

    # 只处理 Segmented 记录
    is_seg = pl.col("Category").str.starts_with("Segmented_")
    seg_df = df.filter(is_seg)
    non_seg_df = df.filter(~is_seg)

    if seg_df.height == 0:
        return df

    # 确定 canonical: RefSeq 或 ICTV (Sequence_Type 含 RefSeq 或 ICTV)
    is_canon = pl.col("Sequence_Type").str.contains("RefSeq|ICTV")

    # 按 TaxID 收集 canonical 段名 → core → canonical_seg
    canon_df = seg_df.filter(is_canon & (pl.col("Segment").is_not_null()) & (pl.col("Segment") != ""))
    canon_groups = canon_df.group_by("Taxid").agg(
        pl.col("Segment").alias("canon_segs"),
        pl.col("Length").alias("canon_lens")
    )

    # 构建映射表: TaxID → canonical segment details
    canon_map = {}  # {taxid: {core: (canon_seg, canon_len)}}
    for row in canon_groups.iter_rows(named=True):
        tax = str(row["Taxid"])
        segs = row["canon_segs"]
        lens = row["canon_lens"]
        canon_map[tax] = {}
        for seg, length in zip(segs, lens):
            clean = str(seg).replace(" ", "").replace("-", "").replace("_", "").upper()
            core = seg_core(clean)
            if core:
                canon_map[tax][core] = (clean, int(length) if length else 0)

    if not canon_map:
        return df.with_columns(pl.col("Segment").alias("Segment_Normalized"))

    # 对每条 Segmented 记录做段名规范化
    new_segments = []
    for row in seg_df.iter_rows(named=True):
        tax = str(row["Taxid"])
        seg = str(row.get("Segment", "")).strip()
        length = int(row.get("Length", 0)) if row.get("Length") else 0
        stype = str(row.get("Sequence_Type", ""))
        cat = str(row.get("Category", ""))

        clean = seg.replace(" ", "").replace("-", "").replace("_", "").upper() if seg else ""
        core = seg_core(clean)

        cmap = canon_map.get(tax, {})
        is_canonical = ("RefSeq" in stype or "ICTV" in stype)

        if not clean or is_canonical:
            new_segments.append(clean)
        elif core and core in cmap:
            cseg, clen = cmap[core]
            diff = abs(length - clen) if length and clen else 0
            if diff <= 100:
                new_segments.append(cseg)                # CONFIRMED
            elif "CDS_Fragment" in cat:
                new_segments.append(clean)                # CDS 片段: 保留原名
            else:
                new_segments.append(clean)                # CORE_DIFF: 保留原名
        else:
            new_segments.append(clean)                    # UNMATCHED

    seg_df = seg_df.with_columns(pl.Series("Segment_Normalized", new_segments))
    non_seg_df = non_seg_df.with_columns(pl.col("Segment").alias("Segment_Normalized"))
    return pl.concat([seg_df, non_seg_df], how="diagonal")


def gene_rule_protection_expr(columns) -> pl.Expr:
    """"基因级标题降级规则"的保护表达式：为 True 的记录不套用该规则。

    保护对象 = RefSeq(NC_) 且 Nuc_Completeness=complete —— NCBI 对小型病毒/卫星的
    RefSeq 标题本就写成 "gene, complete cds"，直接按标题降级会误伤完整参考序列
    （实测 270 条：小麦矮缩病毒、Pistacia emaravirus 各节段、多种卫星）。
    缺少 Nuc_Completeness 列时不保护（保守：不改变原有行为）。
    PVDB_GUARDS=0 时返回 False（等价于关闭护栏）。
    """
    if not _GUARDS_ON or "Nuc_Completeness" not in columns or "Accession" not in columns:
        return pl.lit(False)
    return (pl.col("Accession").cast(pl.Utf8).str.starts_with("NC_")
            & (pl.col("Nuc_Completeness").cast(pl.Utf8).str.to_lowercase() == "complete"))


def two_tier_classifier(df: pl.DataFrame, vmr_path: str, taxid_pq: str = None) -> pl.DataFrame:
    print(f"⏳ 正在解析 VMR 表格 ({vmr_path})...")
    vmr_df = pl.read_csv(vmr_path, separator="\t", ignore_errors=True)

    # 🌟 NEW: 为了防止与原始 TSV 中的 Species 列重名冲突，给 VMR 的列加上 VMR_ 前缀
    vmr_parsed = vmr_df.select([
        "Virus name(s)", 
        pl.col("Species").alias("VMR_Species"), 
        pl.col("Family").alias("VMR_Family"), 
        pl.col("Genus").alias("VMR_Genus"), 
        "Virus GENBANK accession", "Genome coverage"
    ]).with_columns(
        pl.col("Virus GENBANK accession").str.extract_all(r"[a-zA-Z_]+\d+").alias("Acc_List")
    ).filter(pl.col("Acc_List").is_not_null())

    vmr_exploded = vmr_parsed.with_columns(
        pl.col("Acc_List").list.len().alias("Num_Segments")
    ).explode("Acc_List").with_columns(
        pl.col("Acc_List").str.to_uppercase().alias("Base_Accession"),
        pl.col("Genome coverage").fill_null("").str.to_lowercase().alias("vmr_cov_lower"),
        (pl.col("Num_Segments") > 1).alias("Is_Multipartite_VMR")
    ).unique(subset=["Base_Accession"], keep="first")

    for col in ["Sequence_Type", "Segment"]:
        if col not in df.columns: df = df.with_columns(pl.lit("").alias(col))

    df = df.with_columns(
        pl.col("Accession").cast(pl.Utf8).str.split(".").list.first().str.to_uppercase().alias("Base_Accession"),
        pl.col("GenBank_Title").fill_null("").str.to_lowercase().alias("title_lower"),
        pl.col("Segment").fill_null("").cast(pl.Utf8).str.strip_chars().alias("Segment_Clean")
    )

    # 统一 Taxid 列名: 优先从小写 taxid 重命名
    if "taxid" in df.columns and "Taxid" not in df.columns:
        df = df.rename({"taxid": "Taxid"})

    if "Taxid" not in df.columns and taxid_pq:
        # Parquet 中列名可能是小写的 accession / taxid, 需要重命名后提取
        taxid_lf = pl.scan_parquet(taxid_pq)
        cols = taxid_lf.collect_schema().names()
        acc_col = next((c for c in cols if c.lower() == "accession"), cols[0])
        taxid_col = next((c for c in cols if c.lower() == "taxid"), None)
        rename_map = {acc_col: "Accession"}
        if taxid_col:
            rename_map[taxid_col] = "Taxid"
        taxid_lf = taxid_lf.rename(rename_map).select(["Accession", "Taxid"])
        acc_list = df.get_column("Accession").to_list()
        df = df.join(taxid_lf.filter(pl.col("Accession").is_in(acc_list)).collect(), on="Accession", how="left")
    
    df = df.join(vmr_exploded, on="Base_Accession", how="left")

    # 记录哪些 Accession 直接命中了 VMR（只有这些才加 /ICTV 标记）
    df = df.with_columns(
        pl.col("VMR_Species").is_not_null().alias("_vmr_acc_match")
    )

    # 二次兜底: Base_Accession 匹配失败时, 用 VMR_Species (即 ICTV 物种名) 回填
    # 同一物种的不同 Accession 应共享 VMR 分类信息
    vmr_species_info = vmr_exploded.select([
        "VMR_Species", "VMR_Family", "VMR_Genus", "Virus name(s)"
    ]).filter(pl.col("VMR_Species").is_not_null() & (pl.col("VMR_Species") != "")) \
      .unique(subset=["VMR_Species"], keep="first")

    # 对 Accession join 未命中且 Species_ICTV/ Species 非空的记录, 用物种名二次匹配
    sp_col = "Species_ICTV" if "Species_ICTV" in df.columns else "Species"
    mask = pl.col("VMR_Species").is_null() & pl.col(sp_col).is_not_null() & (pl.col(sp_col) != "")

    df = df.join(
        vmr_species_info.rename({"VMR_Species": sp_col}),
        on=sp_col, how="left", suffix="_sp"
    )

    # 合并: 优先用 Accession 匹配的结果, 缺失时用物种名回填的
    # /ICTV 由 _vmr_acc_match 控制, 物种名回填不会触发 /ICTV
    for col_name in ["VMR_Species", "VMR_Family", "VMR_Genus", "Virus name(s)"]:
        sp_col_name = col_name + "_sp"
        if sp_col_name in df.columns:
            df = df.with_columns(
                pl.coalesce([pl.col(col_name), pl.col(sp_col_name)]).alias(col_name)
            ).drop(sp_col_name)

    df = df.with_columns(
        pl.when(pl.col("_vmr_acc_match"))
        .then(
            pl.when(pl.col("Sequence_Type").is_null() | (pl.col("Sequence_Type") == ""))
            .then(pl.lit("/ICTV")).otherwise(pl.col("Sequence_Type") + "/ICTV")
        ).otherwise(pl.col("Sequence_Type")).alias("Sequence_Type")
    )

    df = df.with_columns(
        pl.when(
            pl.col("Is_Multipartite_VMR").fill_null(False) |
            (pl.col("Segment_Clean").str.len_chars() > 0) |
            pl.col("title_lower").str.contains(r"(?i)\bsegment\b")
        ).then(pl.lit(True)).otherwise(pl.lit(False)).alias("Is_Segmented")
    )

    # 护栏：RefSeq(NC_) 且 Nuc_Completeness=complete 的记录，不套用"基因级标题"降级规则。
    # 实测该规则会误伤 270 条 NC_ 完整基因组/节段（小麦矮缩病毒、Pistacia emaravirus
    # 各节段、多个卫星等）——NCBI 对小型病毒/卫星的 RefSeq 标题本就用 "gene, complete cds"
    # 的写法。受保护记录改走下面的原逻辑，并会被写入 quarantine/ 供复核。
    # 可用 PVDB_GUARDS=0 关闭（关闭后行为与 2026-09-27 版完全一致）。
    _protect = gene_rule_protection_expr(df.columns)

    df = df.with_columns(
        # 2026-09-27 修复: 基因级标题(泛 \bgene\b 信号, 含 "complete cds/gene(s)")与部分序列
        # 必须在 Nuc_Completeness 字段之前判定 —— NCBI 上游字段会把 "complete cds" 标成
        # complete, 旧逻辑把字段放第一优先导致 CDS_Fragment 检测器被短路,
        # 344 条基因级记录曾借此混入 Complete。标题同时声明 complete genome 者不在此列。
        # 2026-09-28 加固: 追加"RefSeq 完整基因组"护栏（见上），避免误伤完整参考序列。
        pl.when(
            pl.col("title_lower").str.contains(r"(?i)complete\s+cds|complete\s+coding|complete\s+genes?\b|\bgene\b|\bgenes\b")
            & ~pl.col("title_lower").str.contains(r"(?i)complete\s+genome|complete\s+sequence|complete\s+segment")
            & ~_protect
        ).then(pl.lit("CDS_Fragment"))
        .when(pl.col("title_lower").str.contains(r"(?i)partial genome")).then(pl.lit("Partial_Genome"))
        .when(
            (
                pl.col("vmr_cov_lower").str.contains("complete") |
                (pl.col("Nuc_Completeness") == "complete") |
                pl.col("title_lower").str.contains(r"(?i)complete sequence|complete segment|complete genome")
            ) & ~pl.col("title_lower").str.contains(r"(?i)partial")
        ).then(pl.lit("Complete"))
        .when(pl.col("title_lower").str.contains(r"(?i)\bcds\b|\bgene\b|protein|polyprotein|glycoprotein|polymerase|replicase|capsid")).then(pl.lit("CDS_Fragment"))
        .otherwise(pl.lit("Other_Partial"))
        .alias("Completeness_Level")
    )

    df = df.with_columns(
        pl.when(pl.col("Is_Segmented"))
        .then(pl.lit("Segmented_") + pl.col("Completeness_Level"))
        .otherwise(pl.lit("NonSegmented_") + pl.col("Completeness_Level"))
        .alias("Initial_Category")
    )

    df = df.with_columns(
        pl.when(pl.col("Completeness_Level") == "Complete").then(100)
        .when(pl.col("Completeness_Level") == "Partial_Genome").then(50)
        .when(pl.col("Completeness_Level") == "CDS_Fragment").then(30)
        .otherwise(10).alias("Cat_Weight"),
        pl.col("Taxid").cast(pl.Utf8)
    )

    max_weight_df = df.group_by("Taxid").agg(pl.col("Cat_Weight").max().alias("Max_Taxid_Weight"))
    df = df.join(max_weight_df, on="Taxid", how="left")

    df = df.with_columns(
        pl.when((pl.col("Max_Taxid_Weight") < 100) & (pl.col("Cat_Weight") == pl.col("Max_Taxid_Weight")))
        .then(
            pl.when(pl.col("Is_Segmented")).then(pl.lit("Segmented_Partial_taxid")).otherwise(pl.lit("NonSegmented_Partial_taxid"))
        ).otherwise(pl.col("Initial_Category")).alias("Category")
    )

    # =========================================================================
    # 🚀 同源物种节段兜底机制 (Group-based Imputation) - 增强统计版
    # =========================================================================
    segmented_taxids = df.filter(
        pl.col("Category").str.starts_with("Segmented_") & 
        (pl.col("Taxid") != pl.col("Base_Accession"))
    )["Taxid"].unique().to_list()

    rescue_mask = pl.col("Category").str.starts_with("NonSegmented_") & pl.col("Taxid").is_in(segmented_taxids)
    rescued_df = df.filter(rescue_mask)
    rescued_count = rescued_df.height
    
    if rescued_count > 0:
        rescued_taxids_count = rescued_df["Taxid"].n_unique()
        print("\n" + "🛡️ " * 35)
        print("  【同源节段兜底救援机制】触发战报")
        print("🛡️ " * 35)
        print(f"   => 关联物种数 (TaxIDs) : {rescued_taxids_count:>6,} 个 (户口本确认为节段病毒)")
        print(f"   => 成功挽救序列总数    : {rescued_count:>6,} 条 (已全部重新编入 Segmented_unknown 阵营)")
        print("\n   => 📈 挽救序列原分类来源明细:")
        source_counts = rescued_df.group_by("Category").agg(pl.len().alias("count")).sort("count", descending=True)
        for row in source_counts.to_dicts():
            print(f"      * {row['Category']:<30}: {row['count']:>6,} 条")
        print("🛡️ " * 35 + "\n")

    df = df.with_columns(
        pl.when(rescue_mask)
        .then(pl.lit("Segmented_unknown"))
        .otherwise(pl.col("Category"))
        .alias("Category")
    )

    # ── 段名规范化: 以 RefSeq/VMR 段名为 canonical 标准 ──
    df = normalize_segment_names(df)

    # 仅丢弃算法运行中的临时计算列
    return df.drop(["title_lower", "Cat_Weight", "Max_Taxid_Weight", "Initial_Category", "Segment_Clean", "Is_Segmented", "Completeness_Level", "_vmr_acc_match"])


def print_waterfall_stats(df: pl.DataFrame):
    """打印详尽的序列与TaxID多维统计面板，核心加入【瀑布流优先级增量去冗余】计算"""
    df = df.with_columns(pl.col("Category").str.split("_").list.first().alias("Major_Category"))
    total_seqs = df.height
    total_taxids = df["Taxid"].n_unique()
    
    print("\n" + "="*105)
    print("📊 最终分类统计看板 —— 附【优先级去冗余特有物种增量分析】")
    print("="*105)
    print(f"【总体数据汇总】")
    print(f" - 总序列数 (Sequences) : {total_seqs:>10,}")
    print(f" - 总物种数 (TaxIDs)    : {total_taxids:>10,}")
    
    groups_config = [
        ("Segmented", "第一阵营：节段病毒 (Segmented Viruses)"),
        ("NonSegmented", "第二阵营：非节段单体病毒 (Non-segmented Viruses)")
    ]
    
    priority_order = [
        "Complete", "Partial_Genome", "CDS_Fragment", 
        "Partial_taxid", "Other_Partial", "unknown"
    ]
    
    for major_key, major_name in groups_config:
        major_df = df.filter(pl.col("Major_Category") == major_key)
        m_seqs = major_df.height
        m_taxids = major_df["Taxid"].n_unique()
        
        print("\n" + "-"*105)
        if m_seqs == 0:
            print(f"【 {major_name} 】: 无数据")
            continue
            
        m_seq_pct = (m_seqs / total_seqs) * 100 if total_seqs else 0
        m_tax_pct = (m_taxids / total_taxids) * 100 if total_taxids else 0
        
        print(f"【 {major_name} 】")
        print(f" - 阵营总序列数 : {m_seqs:>8,} (占全局 {m_seq_pct:>5.1f}%)")
        print(f" - 阵营总物种数 : {m_taxids:>8,} (占全局 {m_tax_pct:>5.1f}%)")
        print("   * 细分类数据分布 (优先提取 Complete, 递减计算新增 TaxID):")
        
        seen_taxids = set()
        
        for suffix in priority_order:
            cat_name = f"{major_key}_{suffix}"
            cat_df = major_df.filter(pl.col("Category") == cat_name)
            c_seqs = cat_df.height
            if c_seqs == 0: continue
                
            cat_taxids = set(cat_df["Taxid"].drop_nulls().unique().to_list())
            c_taxids_total = len(cat_taxids)
            exclusive_taxids = cat_taxids - seen_taxids
            c_taxids_excl = len(exclusive_taxids)
            seen_taxids.update(cat_taxids)
            
            c_tax_pct_total = (c_taxids_total / m_taxids) * 100 if m_taxids else 0
            c_tax_pct_excl = (c_taxids_excl / m_taxids) * 100 if m_taxids else 0
            
            print(f"     {cat_name:<28} | Seq= {c_seqs:>7,} | 本类TaxID= {c_taxids_total:>5,} ({c_tax_pct_total:>5.1f}%) | ➡️ 优先特有增量TaxID= {c_taxids_excl:>5,} ({c_tax_pct_excl:>5.1f}%)")
            
    print("="*105 + "\n")


def main():
    args = parse_args()
    overall_start = time.time()
    print("=" * 70)
    print("🧬 病毒序列双层智能分类与多维物种增量统计工具 (全字段保留版)")
    print("=" * 70)

    info_df = pl.read_csv(args.info, separator="\t", ignore_errors=True)
    if args.vmr:
        taxid_pq = ensure_parquet(args.taxid_tsv, sep="\t") if "Taxid" not in info_df.columns and args.taxid_tsv else None
        info_df = two_tier_classifier(info_df, args.vmr, taxid_pq)
    else:
        print("⚠️ 必须使用VMR才能开启全功能分类，请检查参数。")
        return

    out_path = args.output
    os.makedirs(out_path, exist_ok=True)
    
    print_waterfall_stats(info_df)

    # =========================================================================
    # 🌟 NEW: 动态构建输出列，保证不丢失任何输入数据
    # =========================================================================
    # 1. 优先展示的核心列 (便于人类阅读的前几列)
    priority_cols = [
        "Accession", "Base_Accession", "Taxid","Species_NCBI", "Species_ICTV", "Segment", "Sequence_Type", "Category"
    ]
    
    # 2. 从 DataFrame 中找出所有其他未提及的列，包括原始保留的和从VMR拉取的（剔除临时运行列）
    # 注意剔除内部产生的多余特征以保持干净
    drop_patterns = ["vmr_cov_lower", "Is_Multipartite_VMR", "Acc_List", "Num_Segments"]
    remaining_cols = [
        c for c in info_df.columns 
        if c not in priority_cols 
        and c not in drop_patterns
        and not c.endswith("_right") # 避免重复合并带来的 _right 列
    ]
    
    # 3. 完美结合
    out_cols = priority_cols + remaining_cols
    clean_df = info_df.select([c for c in out_cols if c in info_df.columns])
    # =========================================================================

    clean_df.write_csv(os.path.join(out_path, "All_Classified_Virus_Info.tsv"), separator="\t")

    # 护栏审计：把"因护栏而未降级"的记录单独留一份（只写报告，不改动分类结果）
    if _GUARDS_ON and "Nuc_Completeness" in clean_df.columns:
        _t = pl.col("GenBank_Title").cast(pl.Utf8).fill_null("").str.to_lowercase()
        _would = (_t.str.contains(r"(?i)complete\s+cds|complete\s+coding|complete\s+genes?\b|\bgene\b|\bgenes\b")
                  & ~_t.str.contains(r"(?i)complete\s+genome|complete\s+sequence|complete\s+segment"))
        protected = clean_df.filter(
            pl.col("Accession").cast(pl.Utf8).str.starts_with("NC_")
            & (pl.col("Nuc_Completeness").cast(pl.Utf8).str.to_lowercase() == "complete")
            & _would)
        if protected.height:
            qdir = os.path.join(out_path, "quarantine")
            os.makedirs(qdir, exist_ok=True)
            cols = [c for c in ("Accession", "Taxid", "Species_ICTV", "Segment", "Length",
                                "Nuc_Completeness", "GenBank_Title") if c in protected.columns]
            sub = protected.select(cols)
            try:
                if _write_tsv_safe:
                    _write_tsv_safe(sub, os.path.join(qdir, "F2_refseq_complete_protected.tsv"))
                else:
                    sub.write_csv(os.path.join(qdir, "F2_refseq_complete_protected.tsv"), separator="\t")
            except Exception as e:
                print(f"  ⚠ 护栏报告写盘失败（不影响分类结果）: {e}")
            print(f"  ⚠ 护栏：{protected.height} 条 RefSeq 完整基因组未套用基因级降级规则 "
                  f"→ {qdir}/F2_refseq_complete_protected.tsv（复核用；PVDB_GUARDS=0 可关闭）")

    for cat in info_df["Category"].unique().to_list():
        clean_df.filter(pl.col("Category") == cat).write_csv(os.path.join(out_path, f"{cat}_Info.tsv"), separator="\t")

    if args.fasta:
        print(f"⏳ 流式拆分 FASTA: {args.fasta}")
        acc_to_cat = dict(zip(info_df["Base_Accession"].to_list(), info_df["Category"].to_list()))
        processed = split_fasta_streaming(args.fasta, out_path, acc_to_cat)
        print(f"   ⚡ FASTA 拆分完成，共将 {processed} 条序列写入对应的类别文件中。")
    
    print(f"\n⏱️ 总耗时: {time.time() - overall_start:.2f} 秒")

if __name__ == "__main__":
    main()
