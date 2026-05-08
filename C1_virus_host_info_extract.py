#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import polars as pl
import subprocess
import os
import sys
import time
import requests
import xml.etree.ElementTree as ET
import argparse

# ================= 辅助函数：命令行与系统 =================
def parse_args():
    parser = argparse.ArgumentParser(description="🚀 病毒-宿主推断 Pipeline (v5.2 高可用网络重试版)")
    parser.add_argument("--all_nucl", required=True, help="输入文件 1: AllNuclMetadata.csv")
    parser.add_argument("--vhost", required=True, help="输入文件 2: VHostMetadata.lineage.tsv")
    parser.add_argument("--taxid_db", required=True, help="本地 Taxid 数据库: nucl_gb.accession2taxid")
    parser.add_argument("--outdir", required=True, help="输出目录路径")
    parser.add_argument("--api", type=str, default="", help="NCBI API Key (加速在线查询)")
    parser.add_argument("--batch_size", type=int, default=200, help="API 批量大小")
    return parser.parse_args()

def run_cmd(cmd, description):
    print(f"    [*] 正在执行外部命令: {description}...")
    try:
        subprocess.run(cmd, shell=True, check=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"\n[!] 运行出错: {description}\n[!] 报错信息: {e.stderr.decode('utf-8')}")
        sys.exit(1)

def check_dependencies():
    try:
        subprocess.run(["taxonkit", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except Exception:
        print("[!] 致命错误: 未检测到 taxonkit，请先安装并添加到环境变量中。")
        sys.exit(1)

# ================= 辅助函数：Parquet 加速引擎 =================
def load_data_fast(file_path, default_sep=","):
    base_path, _ = os.path.splitext(file_path)
    pq_path = f"{base_path}.parquet"
    if os.path.exists(pq_path):
        return pl.read_parquet(pq_path)
    
    print(f"    [*] ⏳ 首次加载，正在将 {os.path.basename(file_path)} 转换为 Parquet 格式以提速...")
    try:
        pl.scan_csv(file_path, separator=default_sep, infer_schema_length=0, ignore_errors=True).sink_parquet(pq_path)
        return pl.read_parquet(pq_path)
    except Exception as e:
        print(f"    [!] 转换失败 ({e})，回退到普通读取...")
        return pl.read_csv(file_path, separator=default_sep, infer_schema_length=0, ignore_errors=True)

def prepare_taxid_db_parquet(db_path):
    if db_path.endswith('.parquet'): return db_path
    pq_path = f"{db_path}.parquet"
    if os.path.exists(pq_path): return pq_path
    
    print(f"    [*] ⏳ 正在将 NCBI 数据库流式转换为 Parquet 格式 (仅需执行一次)...")
    pl.scan_csv(db_path, separator="\t", infer_schema_length=10000, ignore_errors=True).sink_parquet(pq_path)
    return pq_path

# ================= 辅助函数：API 联网兜底引擎 (引入 Session 与 重试) =================
def fetch_taxid_from_ncbi_nuccore(accession_list, api_key, batch_size):
    acc_to_taxid = {}
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    total = len(accession_list)
    
    # 【优化】使用 Session 复用 TCP 连接，大幅降低 Connection Reset 概率
    session = requests.Session()
    
    for i in range(0, total, batch_size):
        batch = accession_list[i:i+batch_size]
        params = {"db": "nuccore", "id": ",".join(batch), "retmode": "json"}
        if api_key: params["api_key"] = api_key
            
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = session.post(base_url, data=params, timeout=40)
                response.raise_for_status()
                data = response.json()
                success_count = 0
                
                if "result" in data and "uids" in data["result"]:
                    for uid in data["result"]["uids"]:
                        if uid == "uids": continue
                        record = data["result"][uid]
                        acc = record.get("accessionversion")
                        taxid = record.get("taxid")
                        if acc and taxid:
                            acc_to_taxid[acc] = str(taxid)
                            success_count += 1
                            
                print(f"      [-] 进度: {min(i+batch_size, total)}/{total} | 本批次成功获取: {success_count} 个")
                sys.stdout.flush()
                break # 成功则跳出重试循环
                
            except Exception as e:
                err_msg = str(e).split('\n')[0][:80] # 截断过长的错误信息
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5 # 指数退避: 等待 5秒, 10秒...
                    print(f"      [!] ⚠️ 批次 {batch[0]}... 遭遇网络波动: {err_msg} -> {wait_time}秒后进行重试 ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"      [!] ❌ 批次 {batch[0]}... 多次重试均失败，已跳过。错误: {err_msg}")
                    
        time.sleep(0.15 if api_key else 0.4)
            
    return acc_to_taxid

def fetch_ncbi_lineage_online(taxids, target_type, api_key, batch_size):
    if not taxids: return []
    print(f"      -> [联网兜底] 启动 API 下载 Taxonomy，补充 {len(taxids)} 个 {target_type} 的谱系...")
    sys.stdout.flush() 
    results = []
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    # 【优化】使用 Session
    session = requests.Session()
    
    for i in range(0, len(taxids), batch_size):
        chunk = [str(t) for t in taxids[i:i+batch_size]]
        params = {'db': 'taxonomy', 'id': ','.join(chunk), 'retmode': 'xml'}
        if api_key: params['api_key'] = api_key
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = session.post(base_url, data=params, timeout=40)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                
                batch_found = 0
                for taxon in root.findall('Taxon'):
                    tid = taxon.find('TaxId').text if taxon.find('TaxId') is not None else ""
                    name = taxon.find('ScientificName').text if taxon.find('ScientificName') is not None else ""
                    rank = taxon.find('Rank').text if taxon.find('Rank') is not None else ""
                    lin_dict = {'superkingdom': '', 'realm': '', 'clade': '', 'kingdom': '', 'phylum': '', 'class': '', 'order': '', 'family': '', 'genus': '', 'species': ''}
                    
                    lineage_ex = taxon.find('LineageEx')
                    if lineage_ex is not None:
                        for node in lineage_ex.findall('Taxon'):
                            r = node.find('Rank').text if node.find('Rank') is not None else ""
                            n = node.find('ScientificName').text if node.find('ScientificName') is not None else ""
                            if r in lin_dict: lin_dict[r] = n
                    if rank in lin_dict: lin_dict[rank] = name
                        
                    level_1 = (lin_dict['realm'] if lin_dict['realm'] else lin_dict['clade']) if target_type == "Virus" else lin_dict['superkingdom'] 
                    strain = name if rank in ['no rank', 'strain', 'isolate', 'forma specialis'] and lin_dict['species'] != '' else ''
                    
                    formatted_lin = f"{level_1};{lin_dict['kingdom']};{lin_dict['phylum']};{lin_dict['class']};{lin_dict['order']};{lin_dict['family']};{lin_dict['genus']};{lin_dict['species']};{strain}"
                    results.append({"taxid": tid, "name": name, "lineage": formatted_lin})
                    batch_found += 1
                    
                print(f"         [API 进度] 批次 {i+1} ~ {i+len(chunk)}: 成功找回 {batch_found} 条")
                sys.stdout.flush()
                break # 成功跳出重试循环
                
            except Exception as e:
                err_msg = str(e).split('\n')[0][:80]
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    print(f"         [!] ⚠️ 批次 {i+1} ~ {i+len(chunk)} 遭遇网络波动: {err_msg} -> {wait_time}秒后重试 ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"         [!] ❌ 批次 {i+1} ~ {i+len(chunk)} 多次请求失败跳过: {err_msg}")
                    
        time.sleep(0.15 if api_key else 0.4)
        
    return results

def process_lineage(df_clean, target_type, format_string, outdir, args):
    taxid_col, name_col, lin_col, prefix = ("Virus_taxid", "Virus_Name", "Virus_lineage", "tmp_virus") if target_type == "Virus" else ("Host_Taxid", "Host_Name_Std", "Host_lineage", "tmp_host")
    prefix_path = os.path.join(outdir, prefix)
    
    taxids = df_clean.select(taxid_col).unique().drop_nulls().filter(pl.col(taxid_col) != "")
    print(f"    [*] 提取出 {taxids.height} 个独立的 {target_type} Taxid 准备解析...")
    taxids.write_csv(f"{prefix_path}_taxids.txt", include_header=False)
    
    cmd = f'taxonkit lineage -n -i 1 "{prefix_path}_taxids.txt" | taxonkit reformat -I 1 -i 2 -f "{format_string}" -S > "{prefix_path}_lineage.tsv"'
    run_cmd(cmd, f"{target_type} Lineage 本地解析")
    
    df_lin = pl.read_csv(f"{prefix_path}_lineage.tsv", separator="\t", has_header=False, new_columns=[taxid_col, "Raw_Lin", name_col, lin_col], infer_schema_length=0)
    df_lin = df_lin.select([taxid_col, name_col, lin_col])
    
    failed_df = df_lin.filter((pl.col(lin_col).is_null() | (pl.col(lin_col) == "") | (pl.col(lin_col) == ";;;;;;;;")) & pl.col(taxid_col).is_not_null() & (pl.col(taxid_col) != ""))
    failed_taxids = [str(x) for x in failed_df[taxid_col].to_list() if x is not None and str(x).strip() != ""]
    
    if failed_taxids:
        print(f"    [*] 发现 {len(failed_taxids)} 个 {target_type} Taxid 本地解析为空，转入 API 兜底流程...")
        online_res = fetch_ncbi_lineage_online(failed_taxids, target_type, args.api, args.batch_size)
        if online_res:
            df_online = pl.DataFrame(online_res).rename({"taxid": taxid_col, "name": name_col, "lineage": lin_col})
            df_online = df_online.select([pl.col(taxid_col).cast(pl.Utf8), pl.col(name_col).cast(pl.Utf8), pl.col(lin_col).cast(pl.Utf8)])
            df_lin_success = df_lin.join(df_online, on=taxid_col, how="anti")
            df_lin = pl.concat([df_lin_success, df_online], how="diagonal")
            print(f"      -> API 在线补充最终成功找回: {df_online.height} 条谱系。")
    else:
        print(f"    [*] ✅ 本地数据库强大，所有 {target_type} Taxid 100% 解析成功！")
        
    return df_lin

# ================= 核心主流程 =================
def main():
    args = parse_args()
    check_dependencies()
    os.makedirs(args.outdir, exist_ok=True)
    
    # --- 阶段一：读取与基础清理 ---
    print("\n=========================================================")
    print(">>> 阶段 1：加载原始数据并清洗基础格式...")
    print("=========================================================")
    df_all = load_data_fast(args.all_nucl, default_sep=",")
    df_vhost = load_data_fast(args.vhost, default_sep="\t")
    
    if "#Accession" in df_all.columns: df_all = df_all.rename({"#Accession": "Accession"})
    if "Taxid" in df_vhost.columns: df_vhost = df_vhost.rename({"Taxid": "taxid"})
    
    df_all = df_all.with_columns(pl.col("Host").str.strip_chars().replace("", None))
    df_vhost = df_vhost.with_columns(pl.col("Host").str.strip_chars().replace("", None), pl.col("taxid").cast(pl.String))
    print(f"[*] AllNucl 载入 {df_all.height} 条；VHost 载入 {df_vhost.height} 条。")

    # --- 阶段二：Accession 交叉填补 ---
    print("\n=========================================================")
    print(">>> 阶段 2：基于 Accession 跨表交叉填补缺失 Host...")
    print("=========================================================")
    # 填补前统计
    all_null_pre = df_all.select(pl.col("Host").null_count()).item()
    vhost_null_pre = df_vhost.select(pl.col("Host").null_count()).item()

    known_all = df_all.filter(pl.col("Host").is_not_null()).select(["Accession", "Host"]).rename({"Host": "Host_all"})
    known_vhost = df_vhost.filter(pl.col("Host").is_not_null()).select(["Accession", "Host"]).rename({"Host": "Host_vhost"})

    df_all = df_all.join(known_vhost, on="Accession", how="left").with_columns(pl.coalesce(["Host", "Host_vhost"]).alias("Host")).drop("Host_vhost")
    df_vhost = df_vhost.join(known_all, on="Accession", how="left").with_columns(pl.coalesce(["Host", "Host_all"]).alias("Host")).drop("Host_all")

    # 填补后统计
    all_null_post = df_all.select(pl.col("Host").null_count()).item()
    vhost_null_post = df_vhost.select(pl.col("Host").null_count()).item()

    print(f"    [AllNucl 填补] 填补前缺失: {all_null_pre} | 交叉成功填补: {all_null_pre - all_null_post} | 仍缺失: {all_null_post}")
    print(f"    [VHost 填补]   填补前缺失: {vhost_null_pre} | 交叉成功填补: {vhost_null_pre - vhost_null_post} | 仍缺失: {vhost_null_post}")

    # --- 阶段三：Taxid 智能匹配 (剥离版本号 + 联网兜底) ---
    print("\n=========================================================")
    print(">>> 阶段 3：通过 nucl_gb 匹配并联网补充 Taxid...")
    print("=========================================================")
    if "taxid" not in df_all.columns: df_all = df_all.with_columns(pl.lit(None).alias("taxid").cast(pl.String))
    
    pq_db_path = prepare_taxid_db_parquet(args.taxid_db)
    missing_accs_df = pl.concat([
        df_all.filter(pl.col("taxid").is_null()).select("Accession"),
        df_vhost.filter(pl.col("taxid").is_null()).select("Accession")
    ]).unique().drop_nulls()

    if missing_accs_df.height > 0:
        lazy_db = pl.scan_parquet(pq_db_path)
        db_cols = lazy_db.collect_schema().names()
        acc_col = "accession" if "accession" in db_cols else db_cols[0]
        
        # 剥离版本号进行精准本地匹配
        missing_accs_df = missing_accs_df.with_columns(pl.col("Accession").str.split(".").list.first().alias("Accession_Base"))
        tmp_acc_path = os.path.join(args.outdir, "tmp_missing_accs.parquet")
        missing_accs_df.write_parquet(tmp_acc_path)
        
        query = lazy_db.select([acc_col, "taxid"]).join(pl.scan_parquet(tmp_acc_path), left_on=acc_col, right_on="Accession_Base", how="inner")
        
        try: df_taxdb = query.collect(engine="streaming")
        except TypeError: df_taxdb = query.collect(streaming=True)
        
        df_taxdb = df_taxdb.select(["Accession", "taxid"]).rename({"taxid": "taxid_db"}).with_columns(pl.col("taxid_db").cast(pl.String))
        
        df_all = df_all.join(df_taxdb, on="Accession", how="left").with_columns(pl.coalesce(["taxid", "taxid_db"]).alias("taxid")).drop("taxid_db")
        df_vhost = df_vhost.join(df_taxdb, on="Accession", how="left").with_columns(pl.coalesce(["taxid", "taxid_db"]).alias("taxid")).drop("taxid_db")
        print(f"    [*] 本地匹配完成。成功找回 {df_taxdb.height} 个 Taxid。")
        if os.path.exists(tmp_acc_path): os.remove(tmp_acc_path)

    still_missing_taxids = list(set(
        df_all.filter(pl.col("taxid").is_null())["Accession"].to_list() +
        df_vhost.filter(pl.col("taxid").is_null())["Accession"].to_list()
    ))
    
    if still_missing_taxids:
        print(f"    - 去重后需要联网下载的 Accession 数量: {len(still_missing_taxids)} 个")
        print(f"      [联网] 启动 API 下载，共需查询 {len(still_missing_taxids)} 个缺失 taxid 的 Accession...")
        acc2taxid_net = fetch_taxid_from_ncbi_nuccore(still_missing_taxids, args.api, args.batch_size)
        if acc2taxid_net:
            df_net = pl.DataFrame({"Accession": list(acc2taxid_net.keys()), "taxid_net": list(acc2taxid_net.values())})
            df_net = df_net.select([pl.col("Accession").cast(pl.Utf8), pl.col("taxid_net").cast(pl.Utf8)])
            df_all = df_all.join(df_net, on="Accession", how="left").with_columns(pl.coalesce(["taxid", "taxid_net"]).alias("taxid")).drop("taxid_net")
            df_vhost = df_vhost.join(df_net, on="Accession", how="left").with_columns(pl.coalesce(["taxid", "taxid_net"]).alias("taxid")).drop("taxid_net")
            print(f"    [*] 联网补充完毕。成功获取并合并 {len(acc2taxid_net)} 个记录。")

    # --- 阶段四：全局 Taxid 同源填补 (拯救大量数据的核心) ---
    print("\n=========================================================")
    print(">>> 阶段 4：基于 全局(AllNucl+VHost) 同 Taxid 的记录填补缺失 Host...")
    print("=========================================================")
    valid_vhost = df_vhost.filter(pl.col("Host").is_not_null() & pl.col("taxid").is_not_null()).select(["taxid", "Host"])
    valid_all = df_all.filter(pl.col("Host").is_not_null() & pl.col("taxid").is_not_null()).select(["taxid", "Host"])
    
    df_global_taxid_dict = pl.concat([valid_vhost, valid_all]).unique(subset=["taxid"], keep="first").rename({"Host": "Host_taxfill"})
    print(f"    [*] 从联合库中提取到全局 'Taxid -> Host' 映射规则: {df_global_taxid_dict.height} 条")

    # 记录同源填补前状态
    all_null_pre_tax = df_all.select(pl.col("Host").null_count()).item()
    vhost_null_pre_tax = df_vhost.select(pl.col("Host").null_count()).item()

    df_vhost = df_vhost.join(df_global_taxid_dict, on="taxid", how="left").with_columns(pl.coalesce(["Host", "Host_taxfill"]).alias("Host")).drop("Host_taxfill")
    df_all = df_all.join(df_global_taxid_dict, on="taxid", how="left").with_columns(pl.coalesce(["Host", "Host_taxfill"]).alias("Host")).drop("Host_taxfill")

    # 记录同源填补后状态
    all_null_post_tax = df_all.select(pl.col("Host").null_count()).item()
    vhost_null_post_tax = df_vhost.select(pl.col("Host").null_count()).item()

    print("    [VHost 同源填补]")
    print(f"      - 填补前缺失: {vhost_null_pre_tax} | 成功填补: {vhost_null_pre_tax - vhost_null_post_tax} | 仍缺失: {vhost_null_post_tax}")
    print("    [AllNucl 同源填补]")
    print(f"      - 填补前缺失: {all_null_pre_tax} | 成功填补: {all_null_pre_tax - all_null_post_tax} | 仍缺失: {all_null_post_tax}")

    # --- 阶段五：输出孤儿记录并合并 ---
    print("\n=========================================================")
    print(">>> 阶段 5：输出最终无法获得宿主信息的孤儿记录...")
    print("=========================================================")
    print(f"    - AllNucl 最终缺失 Host 记录: {all_null_post_tax} 条")
    print(f"    - VHost 最终缺失 Host 记录: {vhost_null_post_tax} 条")
    
    unresolved_all = df_all.filter(pl.col("Host").is_null())
    unresolved_vhost = df_vhost.filter(pl.col("Host").is_null())
    unresolved_all.write_csv(os.path.join(args.outdir, "Unresolved_AllNucl.tsv"), separator="\t")
    unresolved_vhost.write_csv(os.path.join(args.outdir, "Unresolved_VHost.tsv"), separator="\t")
    print(">>> 🎉 所有分析与联合填补流程执行完毕！")

    # 合并有效数据
    df_merged = pl.concat([df_all.select(["Accession", "taxid", "Host"]), df_vhost.select(["Accession", "taxid", "Host"])]).unique(subset=["Accession"], keep="first")
    df_clean = df_merged.filter(pl.col("Host").is_not_null() & pl.col("taxid").is_not_null())
    df_clean = df_clean.rename({"taxid": "Virus_taxid", "Host": "Host_Name_Raw"})
    
    # --- 阶段六：Lineage 解析 ---
    print("\n>>> 阶段 6：获取 [病毒] 的名称与 9级完整谱系 (Realm)...")
    df_v_lin = process_lineage(df_clean, "Virus", "{r};{K};{p};{c};{o};{f};{g};{s};{t}", args.outdir, args)

    print("\n>>> 阶段 7：获取 [宿主] 的 Taxid 与 9级完整谱系 (Domain)...")
    host_names_path = os.path.join(args.outdir, "tmp_host_names.txt")
    host_name2taxid_path = os.path.join(args.outdir, "tmp_host_name2taxid.tsv")
    
    df_clean.select("Host_Name_Raw").unique().drop_nulls().write_csv(host_names_path, include_header=False)
    run_cmd(f'taxonkit name2taxid -i 1 "{host_names_path}" > "{host_name2taxid_path}"', "宿主名称 -> Taxid")
    
    df_h_taxid = pl.read_csv(host_name2taxid_path, separator="\t", has_header=False, new_columns=["Host_Name_Raw", "Host_Taxid"], infer_schema_length=0)
    df_h_taxid = df_h_taxid.with_columns(pl.col("Host_Taxid").cast(pl.Utf8).str.split(",").list.first().str.strip_chars())
    
    df_clean_with_htaxid = df_clean.join(df_h_taxid, on="Host_Name_Raw", how="left")
    df_h_lin = process_lineage(df_clean_with_htaxid, "Host", "{d};{K};{p};{c};{o};{f};{g};{s};{t}", args.outdir, args)

    # --- 阶段八：整理并输出 ---
    print("\n=========================================================")
    print(">>> 阶段 8：拼合最终宽表并格式化输出...")
    print("=========================================================")
    df_final = df_clean.join(df_v_lin, on="Virus_taxid", how="left")
    df_final = df_final.join(df_h_taxid, on="Host_Name_Raw", how="left")
    df_final = df_final.join(df_h_lin, on="Host_Taxid", how="left")
    
    df_final = df_final.with_columns(pl.coalesce(["Host_Name_Std", "Host_Name_Raw"]).alias("Host_Name"))
    df_final = df_final.select(["Accession", "Virus_Name", "Virus_taxid", "Virus_lineage", "Host_Name", "Host_Taxid", "Host_lineage"]).fill_null("")
    
    final_out = os.path.join(args.outdir, "Final_Virus_Host_Lineage.tsv")
    df_final.write_csv(final_out, separator="\t")
    
    print(f"    🏆 最终有效输出数据 : {df_final.height} 条")
    print(f"    [*] 🎉 任务全部圆满完成！最终文件保存在: {final_out}\n")

    # 自动清理临时文件
    for tmp in os.listdir(args.outdir):
        if tmp.startswith("tmp_"): os.remove(os.path.join(args.outdir, tmp))

if __name__ == "__main__":
    main()
