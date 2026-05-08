#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import polars as pl
import time
import os
import argparse
import subprocess
import tempfile
import sys
import gc  # 引入垃圾回收模块

def parse_args():
    parser = argparse.ArgumentParser(description="终极版：融合 TaxonKit 的病毒宿主全量补全与极细拆分 (含 Algae, Oomycetes)")
    parser.add_argument("-v", "--vhost", default="Final_Virus_Host_Lineage.tsv", help="VHost 文件 (支持 tsv/csv/parquet)")
    parser.add_argument("-a", "--allnucl", default="AllNuclMetadata.parquet", help="AllNuclMetadata 文件 (支持 tsv/csv/parquet)")
    parser.add_argument("-o", "--out_dir", default="VHost_Final_Classified", help="输出文件夹")
    parser.add_argument("--taxonkit", default="taxonkit", help="taxonkit 路径")
    return parser.parse_args()

def ensure_parquet(filepath: str) -> str:
    """自动检测文件后缀，如果是 tsv/csv 则转换为 parquet 加速后续处理"""
    if filepath.endswith('.parquet'):
        return filepath
        
    base_name, ext = os.path.splitext(filepath)
    pq_path = f"{base_name}.parquet"
    
    if not os.path.exists(pq_path):
        print(f"🔄 检测到文本格式 {ext}，正在将其转换为 Parquet 格式以加速处理: {pq_path}...")
        sep = ',' if ext.lower() == '.csv' else '\t'
        # infer_schema_length=0 会将所有列读取为Utf8字符串，防止类型推断导致的读取报错
        df = pl.read_csv(filepath, separator=sep, infer_schema_length=0)
        df.write_parquet(pq_path)
        print(f"   -> 转换完成！")
    else:
        print(f"🔄 检测到已存在对应的 Parquet 文件: {pq_path}，直接使用...")
        
    return pq_path

def resolve_host_names_via_taxonkit(host_names: list, taxonkit_path: str) -> pl.DataFrame:
    """将纯文本 Host 名称通过 taxonkit 转换为 TaxID 和 Lineage"""
    unique_hosts = list(set([h.strip() for h in host_names if h and h.strip()]))
    if not unique_hosts:
        return pl.DataFrame(schema={"Host_Name": pl.Utf8, "Host_Taxid": pl.Utf8, "Host_lineage_new": pl.Utf8})
        
    print(f"   -> 发现 {len(unique_hosts)} 个独特的宿主文本，正在调用 TaxonKit 解析物种谱系...")
    
    with tempfile.NamedTemporaryFile('w', delete=False) as f_names:
        f_names.write('\n'.join(unique_hosts))
        names_file = f_names.name
        
    try:
        # 1. Name -> TaxID
        cmd1 = [taxonkit_path, "name2taxid", names_file]
        res1 = subprocess.run(cmd1, capture_output=True, text=True)
        
        taxid_map = []
        valid_taxids = set()
        
        for line in res1.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                name, taxid = parts[0].strip(), parts[1].strip()
                if taxid: 
                    taxid_map.append({"Host_Name": name, "Host_Taxid": taxid})
                    valid_taxids.add(taxid)
                    
        # 2. TaxID -> Lineage
        with tempfile.NamedTemporaryFile('w', delete=False) as f_taxids:
            f_taxids.write('\n'.join(list(valid_taxids)))
            taxids_file = f_taxids.name
            
        cmd2 = [taxonkit_path, "lineage", taxids_file]
        res2 = subprocess.run(cmd2, capture_output=True, text=True)
        
        lineage_map = {}
        for line in res2.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                lineage_map[parts[0].strip()] = parts[1].strip()
                
        # 3. 组合结果
        final_mapping = []
        for item in taxid_map:
            item["Host_lineage_new"] = lineage_map.get(item["Host_Taxid"], "")
            final_mapping.append(item)
            
        print(f"   -> TaxonKit 解析成功！成功识别了 {len(final_mapping)} 个物种谱系。")
        return pl.DataFrame(final_mapping, schema={"Host_Name": pl.Utf8, "Host_Taxid": pl.Utf8, "Host_lineage_new": pl.Utf8})
        
    except Exception as e:
        print(f"   ⚠ TaxonKit 运行警告: {e}")
        print("   ⚠ 尝试回退至基础文本正则匹配模式...")
        return pl.DataFrame(schema={"Host_Name": pl.Utf8, "Host_Taxid": pl.Utf8, "Host_lineage_new": pl.Utf8})
    finally:
        if os.path.exists(names_file): os.unlink(names_file)
        if 'taxids_file' in locals() and os.path.exists(taxids_file): os.unlink(taxids_file)

def apply_classification(df: pl.DataFrame, lineage_col: str) -> pl.DataFrame:
    """终极细化版：基于 NCBI 谱系文本的标准正则归类"""
    return df.with_columns(
        pl.when(pl.col(lineage_col).str.contains("(?i)Homo sapiens|Homo|Human")).then(pl.lit("Human"))
        .when(pl.col(lineage_col).str.contains("(?i)Metazoa|Animalia|Bos taurus|Sus scrofa|Macaca|vertebrate|invertebrate|Chordata|Arthropoda|Nematoda|Platyhelminthes")).then(pl.lit("Animal"))
        .when(pl.col(lineage_col).str.contains("(?i)Viridiplantae|Plant|Embryophyta|Streptophyta|Tracheophyta")).then(pl.lit("Plant"))
        .when(pl.col(lineage_col).str.contains("(?i)oomycetes|Oomycota|Peronosporomycetes|Phytophthora|Pythium|Plasmopara")).then(pl.lit("Oomycetes"))
        .when(pl.col(lineage_col).str.contains("(?i)Fungi|Ascomycota|Basidiomycota|Chytridiomycota|Mucoromycota|Zygomycota")).then(pl.lit("Fungi"))
        .when(pl.col(lineage_col).str.contains("(?i)Sar|Stramenopiles|Alveolata|Rhizaria|Amoebozoa|Excavata|protist|Ciliophora|Apicomplexa|Euglenozoa")).then(pl.lit("Protist"))
        .when(pl.col(lineage_col).str.contains("(?i)Bacteria|Escherichia|Pseudomonadota|Firmicutes|Actinomycetota|Bacteroidota|Cyanobacteria|Proteobacteria")).then(pl.lit("Bacteria"))
        .when(pl.col(lineage_col).str.contains("(?i)Archaea|Euryarchaeota|Crenarchaeota|Thermoproteota")).then(pl.lit("Archaea"))
        .when(pl.col(lineage_col).str.contains("(?i)environmental|uncultured|metagenome|soil|water|marine|sewage|sludge|wastewater")).then(pl.lit("Environmental_NCBI"))
        .otherwise(pl.lit("Unknown"))
        .alias("Host_Category")
    )

def main():
    args = parse_args()
    start_time = time.time()
    os.makedirs(args.out_dir, exist_ok=True)
    
    print("=====================================================")
    print("🚀 启动全维度病毒宿主信息补全与精细分类流 (内存优化版)")
    print("=====================================================")

    # 自动转换为 Parquet（针对 VHost 和 AllNucl）
    vhost_pq = ensure_parquet(args.vhost)
    allnucl_pq = ensure_parquet(args.allnucl)

    # ==========================================
    # 1. 基础加载与内部分类
    # ==========================================
    print("\n⏳ 1. 加载 VHost 数据并执行基础分类...")
    vhost_df = pl.read_parquet(vhost_pq).with_columns([
        pl.col("Virus_taxid").cast(pl.Utf8),
        pl.col("Host_Taxid").cast(pl.Utf8),
        pl.col("Host_lineage").fill_null("")
    ])
    
    vhost_df = apply_classification(vhost_df, "Host_lineage")
    
    has_info_vhost = vhost_df.filter(pl.col("Host_Category") != "Unknown")
    need_rescue_vhost = vhost_df.filter(pl.col("Host_Category") == "Unknown")

    # 内部 Virus_taxid 自救
    taxid_mapping = has_info_vhost.select(["Virus_taxid", "Host_Name", "Host_Taxid", "Host_lineage", "Host_Category"]).drop_nulls("Virus_taxid").unique("Virus_taxid", keep="first")
    rescued_by_taxid = need_rescue_vhost.drop(["Host_Name", "Host_Taxid", "Host_lineage", "Host_Category"]).join(taxid_mapping, on="Virus_taxid", how="left")
    
    internal_rescued = rescued_by_taxid.filter(pl.col("Host_Category").is_not_null())
    still_need_rescue_vhost = rescued_by_taxid.filter(pl.col("Host_Category").is_null()).drop(["Host_Name", "Host_Taxid", "Host_lineage", "Host_Category"])

    base_good_df = pl.concat([has_info_vhost, internal_rescued], how="diagonal")
    print(f"   -> 已确立基础分类记录数: {base_good_df.height} 条")

    # 释放早期的 VHost 变量
    del vhost_df, has_info_vhost, need_rescue_vhost, taxid_mapping, rescued_by_taxid, internal_rescued
    gc.collect()

    # ==========================================
    # 2. 从 AllNuclMetadata 大表中捞取缺失文本与新序列
    # ==========================================
    print("\n⏳ 2. 扫描核酸大表，捞取缺失文本及全新 Accession...")
    
    try:
        # 【内存优化】: 启用 engine="streaming" 降低读取峰值，并修复了弃用警告
        allnucl_df = pl.scan_parquet(allnucl_pq).select([
            pl.col("#Accession").cast(pl.Utf8).alias("Accession"), 
            pl.col("Host").cast(pl.Utf8).alias("Host_Name"),
            pl.col("Species").cast(pl.Utf8), 
            pl.col("Family").cast(pl.Utf8), 
            pl.col("Genus").cast(pl.Utf8)
        ]).filter(pl.col("Host_Name").is_not_null() & (pl.col("Host_Name") != "")).collect(engine="streaming")

        rescued_hosts_for_vhost = still_need_rescue_vhost.join(allnucl_df.select(["Accession", "Host_Name"]), on="Accession", how="inner")

        vhost_all_accs = base_good_df.get_column("Accession").to_list() + still_need_rescue_vhost.get_column("Accession").to_list()
        brand_new_accessions = allnucl_df.filter(~pl.col("Accession").is_in(vhost_all_accs))
        
        brand_new_formatted = brand_new_accessions.with_columns([
            pl.col("Species").alias("Virus_Name"),
            pl.lit(None).cast(pl.Utf8).alias("Virus_taxid"),
            pl.concat_str([
                pl.col("Family").fill_null(""), pl.lit(";"), 
                pl.col("Genus").fill_null(""), pl.lit(";"), 
                pl.col("Species").fill_null("")
            ], separator="").alias("Virus_lineage")
        ]).select(["Accession", "Virus_Name", "Virus_taxid", "Virus_lineage", "Host_Name"])

        print(f"   -> 从大表捞回 VHost 缺失记录: {rescued_hosts_for_vhost.height} 条")
        print(f"   -> 发现 VHost 未收录的全新记录: {brand_new_formatted.height} 条")

        all_needs_taxonkit = pl.concat([rescued_hosts_for_vhost, brand_new_formatted], how="diagonal")
        
        # 释放 allnucl_df，它是千万级别的大表
        del allnucl_df, still_need_rescue_vhost, rescued_hosts_for_vhost, brand_new_accessions, brand_new_formatted
        gc.collect()
        
    except Exception as e:
        print(f"   ⚠ 无法处理大表 {allnucl_pq} (可能是测试环境下没有该文件): {e}")
        all_needs_taxonkit = pl.DataFrame()

    # ==========================================
    # 3. TaxonKit 解析：文本 -> TaxID -> 谱系
    # ==========================================
    if all_needs_taxonkit.height > 0:
        print("\n⏳ 3. 启动 TaxonKit 深度解析流程...")
        unique_host_strings = all_needs_taxonkit.get_column("Host_Name").to_list()
        taxonkit_mapping = resolve_host_names_via_taxonkit(unique_host_strings, args.taxonkit)

        resolved_df = all_needs_taxonkit.join(taxonkit_mapping, on="Host_Name", how="left")
        
        resolved_df = resolved_df.with_columns(
            pl.coalesce([pl.col("Host_lineage_new"), pl.col("Host_Name")]).alias("Classification_String")
        )
        resolved_df = apply_classification(resolved_df, "Classification_String")
        
        final_rescued_df = resolved_df.with_columns([
            pl.col("Host_lineage_new").alias("Host_lineage")
        ]).select(base_good_df.columns) # 对齐列以安全 concat
        
        del all_needs_taxonkit, resolved_df, taxonkit_mapping
        gc.collect()
    else:
        print("\n⏳ 3. 没有需要解析的缺失数据，跳过 TaxonKit...")
        final_rescued_df = pl.DataFrame(schema=base_good_df.schema)

    # ==========================================
    # 4. 汇总与 Sequence_Type 并入
    # ==========================================
    print("\n⏳ 4. 正在合并数据...")
    final_df = pl.concat([base_good_df, final_rescued_df], how="diagonal")
    
    # 【内存优化】: 核心合并完成，立刻删掉合并前的两个大表并回收内存
    del base_good_df, final_rescued_df
    gc.collect()
    
    # 如果 allnucl 包含 Sequence_Type，尝试合并
    try:
        # 【内存优化】: 再次启用 engine="streaming" 并修复警告
        seq_type_df = pl.scan_parquet(allnucl_pq).select([
            pl.col("#Accession").cast(pl.Utf8).alias("Accession"),
            pl.col("Sequence_Type").cast(pl.Utf8)
        ]).collect(engine="streaming")
        final_df = final_df.join(seq_type_df, on="Accession", how="left")
        
        del seq_type_df
        gc.collect()
    except Exception:
        pass # 若不存在此列则跳过
    
    # ==========================================
    # 5. 生成统计与拆分输出
    # ==========================================
    summary_df = final_df.group_by("Host_Category").len().sort("len", descending=True)
    
    print("\n========== 最终分类统计 ==========")
    for row in summary_df.iter_rows(named=True):
        print(f" - {row['Host_Category']:<20} : {row['len']:>10,} 条")
    print("====================================\n")

    # 写入全局总表
    final_df.write_csv(os.path.join(args.out_dir, "All_Processed_Records.tsv"), separator="\t")
    summary_df.write_csv(os.path.join(args.out_dir, "Summary_Counts.tsv"), separator="\t")

    print("⏳ 正在生成独立分类文件...")
    unique_categories = summary_df.get_column("Host_Category").to_list()
    for cat in unique_categories:
        out_path = os.path.join(args.out_dir, f"{cat}.tsv")
        
        cat_df = final_df.filter(pl.col("Host_Category") == cat)
        cat_df.write_csv(out_path, separator="\t")
        print(f"   📂 写入完成: {cat+'.tsv':<25} ({cat_df.height} 条)")

    print(f"\n✅ 完美收官！所有文件已输出至目录: {args.out_dir}/")
    print(f"⏱️ 总耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
