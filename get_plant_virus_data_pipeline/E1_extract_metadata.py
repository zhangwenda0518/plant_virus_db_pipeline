#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import polars as pl
import os
import time
import argparse
import urllib.request
import urllib.parse
import json

def parse_args():
    parser = argparse.ArgumentParser(description="极速提取本地元数据，并自动联网补全缺失信息的整合引擎。")
    parser.add_argument("-i", "--input_id", required=True, help="输入的 Accession 列表文件 (如: plant.virus.id)")
    parser.add_argument("-m", "--meta_csv", default="AllNuclMetadata.csv", help="NCBI Virus 元数据文件路径")
    parser.add_argument("-t", "--taxid_tsv", default="~/database/taxonomy/nucl_gb.accession2taxid", help="NCBI Taxonomy 映射文件路径")
    parser.add_argument("-o", "--output", default="Plant_Virus_Info_Final.tsv", help="输出的最终结果 TSV 文件")
    parser.add_argument("-k", "--api_key", default="80a47d7eae0bef204ccf4a2714c96bec8809", help="NCBI API Key (用于在线补充数据)")
    return parser.parse_args()

def ensure_parquet(file_path: str, sep: str, rename_dict: dict = None) -> str:
    """自动检测与生成 Parquet 缓存"""
    file_path = os.path.expanduser(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"❌ 找不到原始数据库文件: {file_path}")

    parquet_path = file_path + ".parquet"
    if os.path.exists(parquet_path):
        print(f"   ✅ 检测到 Parquet 缓存，直接使用: {parquet_path}")
        return parquet_path
        
    print(f"   ⏳ 正在对 {os.path.basename(file_path)} 进行流式极速转换...")
    start_time = time.time()
    
    lf = pl.scan_csv(file_path, separator=sep, infer_schema_length=10000, ignore_errors=True)
    if rename_dict:
        lf = lf.rename(rename_dict)
        
    lf.sink_parquet(parquet_path, compression="zstd")
    print(f"   🎉 转换完成！耗时: {time.time() - start_time:.2f} 秒。")
    return parquet_path

def fetch_missing_from_ncbi(accessions: list, api_key: str) -> pl.DataFrame:
    """从 NCBI 在线抓取缺失的元数据并返回 Polars DataFrame"""
    total = len(accessions)
    print(f"\n🌐 启动 NCBI eSummary 实时元数据抓取引擎")
    print(f"📊 待查询缺失序列 : {total} 条")
    
    chunk_size = 300
    success_count = 0
    rescued_records = []

    for i in range(0, total, chunk_size):
        chunk = accessions[i:i+chunk_size]
        id_string = ",".join(chunk)
        
        params = {
            "db": "nuccore",
            "id": id_string,
            "retmode": "json",
            "api_key": api_key
        }
        
        data = urllib.parse.urlencode(params).encode("utf-8")
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        req = urllib.request.Request(url, data=data)
        
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_data = response.read().decode("utf-8")
                    json_data = json.loads(res_data)
                    
                    result = json_data.get("result", {})
                    uids = result.get("uids", [])
                    
                    for uid in uids:
                        record = result.get(uid, {})
                        
                        rescued_records.append({
                            "Accession": record.get("accessionversion", "Unknown"),
                            "taxid": str(record.get("taxid", "")),
                            "Species": record.get("organism", ""),
                            "Length": str(record.get("slen", "")),
                            "GenBank_Title": record.get("title", ""),
                            "Segment": record.get("segment", None), # 新增：在线抓取 Segment (使用 None 避免覆盖本地有效值)
                            "NCBI_Status": record.get("status", "live") 
                        })
                        success_count += 1
                        
                    print(f"   ✅ 进度: [ {min(i+chunk_size, total)} / {total} ] - 成功抓取批次数据。")
                    break
                    
            except Exception as e:
                print(f"      ⚠ 网络异常 (重试 {attempt}/3): {e}")
                time.sleep(3)

        time.sleep(0.3) # 遵守 NCBI 频率限制

    print(f"🎉 抓取任务完成！成功获取 : {success_count} 条元数据")
    
    if rescued_records:
        return pl.DataFrame(rescued_records)
    else:
        # 新增 Segment 列到空表的 schema 中
        return pl.DataFrame(schema={
            "Accession": pl.Utf8, "taxid": pl.Utf8, "Species": pl.Utf8, 
            "Length": pl.Utf8, "GenBank_Title": pl.Utf8, "Segment": pl.Utf8, 
            "NCBI_Status": pl.Utf8
        })

def main():
    args = parse_args()
    start_time = time.time()
    print("==================================================================")
    print("🧬 启动极速本地关联与在线拯救(Rescue)引擎")
    print("==================================================================")

    # ==========================================
    # 1. 本地数据库缓存与查询
    # ==========================================
    print("\n[阶段 1/4] 数据库状态检查与预热...")
    meta_pq = ensure_parquet(args.meta_csv, sep=",", rename_dict={"#Accession": "Accession"})
    taxid_pq = ensure_parquet(args.taxid_tsv, sep="\t")

    print(f"\n[阶段 2/4] 读取目标 Accession 列表: {args.input_id}")
    with open(args.input_id, 'r', encoding='utf-8') as f:
        target_list = [line.strip() for line in f if line.strip()]
        
    target_ids_df = pl.DataFrame({"Accession": target_list})

    print("\n[阶段 3/4] 在本地底层进行极速跨表映射与数据提取...")
    # 新增：在 meta_cols 中加入 "Segment"
    meta_cols = [
        "Accession", "Species", "Family", "Segment", "Molecule_type", "Sequence_Type", "Length",
        "Nuc_Completeness", "GenBank_Title", "Geo_Location",
        "USA", "Host", "Isolation_Source", "Collection_Date", "Release_Date"
    ]
    meta_lf = pl.scan_parquet(meta_pq).select(meta_cols).filter(pl.col("Accession").is_in(target_list))
    
    taxid_lf = (
        pl.scan_parquet(taxid_pq)
        .rename({"accession.version": "Accession"})
        .select(["Accession", "taxid"])
        .filter(pl.col("Accession").is_in(target_list))
        .with_columns(pl.col("taxid").cast(pl.Utf8))
    )

    final_df = (
        target_ids_df.lazy()
        .join(meta_lf, on="Accession", how="left")
        .join(taxid_lf, on="Accession", how="left")
        .collect()
    )

    # ==========================================
    # 2. 识别缺失并触发在线拯救
    # ==========================================
    # 找到 Species 或 taxid 为空的 Accession
    missing_df = final_df.filter(pl.col("Species").is_null() | pl.col("taxid").is_null())
    missing_accessions = missing_df["Accession"].to_list()
    
    print(f"\n📊 本地提取结果初步统计:")
    print(f"   - 总输入序列 : {final_df.height} 条")
    print(f"   - 完全匹配   : {final_df.height - len(missing_accessions)} 条")
    print(f"   - 存在缺失   : {len(missing_accessions)} 条 (将尝试在线补充)")

    # ==========================================
    # 3. 合并联网抓取的数据
    # ==========================================
    print("\n[阶段 4/4] 联网拯救并合并数据...")
    if missing_accessions:
        rescued_df = fetch_missing_from_ncbi(missing_accessions, args.api_key)
        
        if rescued_df.height > 0:
            # 使用 left join 将抓取到的数据贴合到主表上
            final_df = final_df.join(rescued_df, on="Accession", how="left", suffix="_rescued")
            
            # 使用 coalesce 优先取 rescued 的数据，如果 rescued 没有，则取原来的数据
            final_df = final_df.with_columns([
                pl.col("Length").cast(pl.Utf8),
                pl.col("Segment").cast(pl.Utf8) # 强制转码，防止类型冲突
            ])
            
            # 新增：处理 Segment 字段的无缝修补
            final_df = final_df.with_columns([
                pl.coalesce(["taxid_rescued", "taxid"]).alias("taxid"),
                pl.coalesce(["Species_rescued", "Species"]).alias("Species"),
                pl.coalesce(["Length_rescued", "Length"]).alias("Length"),
                pl.coalesce(["GenBank_Title_rescued", "GenBank_Title"]).alias("GenBank_Title"),
                pl.coalesce(["Segment_rescued", "Segment"]).alias("Segment")
            ]).drop(["taxid_rescued", "Species_rescued", "Length_rescued", "GenBank_Title_rescued", "Segment_rescued"])
    else:
        # 如果没有缺失，强行补一个空的 NCBI_Status 保证列一致
        final_df = final_df.with_columns(pl.lit("local_only").alias("NCBI_Status"))

    # ==========================================
    # 4. 保存最终结果
    # ==========================================
    # 整理列顺序，将 Segment 放在 Species 后面
    final_cols = [
        "Accession", "taxid", "Species", "Family", "Segment", "Molecule_type", "Sequence_Type", "Length",
        "Nuc_Completeness", "GenBank_Title", "Geo_Location", "USA",
        "Host", "Isolation_Source", "Collection_Date", "Release_Date", "NCBI_Status"
    ]
    # 确保只输出存在的列（容错处理）
    out_cols = [c for c in final_cols if c in final_df.columns]
    final_df = final_df.select(out_cols)

    final_df.write_csv(args.output, separator="\t")
    print(f"\n✅ 终极数据表已保存至 : {args.output}")
    print(f"⏱️ 整体总耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
