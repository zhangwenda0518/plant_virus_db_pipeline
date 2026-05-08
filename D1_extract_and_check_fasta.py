#!/usr/bin/env python3
"""
通用病毒数据比对与提取脚本 (优化版)
- 比对 TSV 中的 Accession 与本地 FASTA 数据库
- 提取本地已有的序列（支持 .gz 压缩，精确匹配版本号）
- 生成缺失记录的下载命令，支持环境变量读取 API Key 以保护隐私

要求：
    Python 3.8+，polars
可选（极大提升提取速度）：
    seqkit (https://bioinf.shenwei.me/seqkit/)
"""

import polars as pl
import os
import time
import argparse
import gzip
import shutil
import subprocess

def parse_args():
    parser = argparse.ArgumentParser(description="通用病毒数据比对与提取：比对 TSV 记录，提取已有序列，并生成缺失下载脚本")
    parser.add_argument("-t", "--tsv", required=True, help="输入的分类 TSV 文件路径 (例如: Human.tsv, Plant.tsv)")
    parser.add_argument("-f", "--fasta", required=True, help="本地 FASTA 数据库文件路径 (例如: RVDB_viroids.fasta)，支持 .gz 压缩")
    parser.add_argument("-o", "--out_dir", default="Database_Update", help="结果输出目录 (默认: Database_Update)")
    return parser.parse_args()

def extract_accessions_from_fasta(fasta_path: str) -> pl.DataFrame:
    """
    流式读取 FASTA 头，提取基础 Accession 用于快速比对，
    同时保留完整的 Fasta_ID 用于 seqkit 精确提取。
    """
    base_to_raw = {}
    open_func = gzip.open if fasta_path.endswith('.gz') else open
    with open_func(fasta_path, 'rt', encoding='utf-8') as f:
        for line in f:
            if line.startswith('>'):
                raw_id = line[1:].split()[0]         # 提取完整的带版本号的 ID，例如 NC_001422.1
                base_acc = raw_id.split('.')[0]      # 去掉版本号用于比对，例如 NC_001422
                base_to_raw[base_acc] = raw_id       # 建立映射
                
    return pl.DataFrame({
        "Base_Accession": list(base_to_raw.keys()),
        "Fasta_ID": list(base_to_raw.values())
    })

def extract_matching_fasta_python(input_fasta: str, output_fasta: str, target_accs: set):
    """
    纯 Python 流式提取（回退方案），现在使用精确匹配完整的 FASTA ID
    """
    matched_count = 0
    open_func = gzip.open if input_fasta.endswith('.gz') else open
    with open_func(input_fasta, 'rt', encoding='utf-8') as f_in, \
         open(output_fasta, 'w', encoding='utf-8') as f_out:

        write_flag = False
        for line in f_in:
            if line.startswith('>'):
                raw_id = line[1:].split()[0]
                if raw_id in target_accs:  # 使用完整的原始 ID 进行精确匹配
                    write_flag = True
                    matched_count += 1
                    f_out.write(line)
                else:
                    write_flag = False
            elif write_flag:
                f_out.write(line)
    return matched_count

def extract_matching_fasta_seqkit(input_fasta: str, output_fasta: str, target_accs: set):
    """
    使用 seqkit grep 快速提取（需要 seqkit 在 PATH 中）
    """
    id_file = output_fasta + ".ids"
    with open(id_file, 'w') as f:
        for acc in target_accs:
            f.write(acc + "\n")
    print(f"   🛠️ 临时ID文件已写入: {id_file}，包含 {len(target_accs)} 个精确 Accession")

    cmd = ["seqkit", "grep", "-f", id_file, input_fasta, "-o", output_fasta]
    print(f"   🏃 执行命令: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ seqkit 运行失败: {e.stderr}")
        raise
    finally:
        if os.path.exists(id_file):
            os.remove(id_file)

    if not os.path.exists(output_fasta):
        print(f"⚠️ 警告：输出文件 {output_fasta} 未生成")
        return 0

    result = subprocess.run(["grep", "-c", "^>", output_fasta],
                            capture_output=True, text=True)
    if result.returncode == 0:
        count = int(result.stdout.strip())
    elif result.returncode == 1:
        count = 0 
        print(f"⚠️ 注意：seqkit 未提取到任何序列，输出文件为空")
    else:
        print(f"⚠️ 警告：统计序列数时 grep 返回错误码 {result.returncode}")
        count = 0
    return count

def main():
    args = parse_args()
    start_time = time.time()
    os.makedirs(args.out_dir, exist_ok=True)

    prefix = os.path.splitext(os.path.basename(args.tsv))[0]

    print("=================================================================")
    print(f"🦠 启动通用极速比对与序列提取流 | 当前目标: {prefix} 病毒")
    print("=================================================================")

    # ==========================================
    # 1. 极速加载与清洗目标 TSV 数据
    # ==========================================
    print(f"\n⏳ 1. 加载目标病毒数据 ({args.tsv})...")
    target_df = pl.read_csv(args.tsv, separator="\t").with_columns(
        pl.col("Accession").cast(pl.Utf8).str.split(".").list.first().alias("Base_Accession")
    )
    print(f"   -> 共有待检查的 [{prefix}] 记录: {target_df.height} 条")

    # ==========================================
    # 2. 从 FASTA 文件提取 Accession 索引
    # ==========================================
    print(f"⏳ 2. 正在扫描本地 FASTA 数据库获取索引 ({args.fasta})...")
    fasta_start = time.time()
    fasta_df = extract_accessions_from_fasta(args.fasta)
    print(f"   -> 解析完毕 (耗时 {time.time()-fasta_start:.2f}s)。共发现独特序列: {fasta_df.height} 条")

    # ==========================================
    # 3. Hash Join 比对
    # ==========================================
    print("\n⏳ 3. 启动 Rust 底层 Hash Join 进行极速数据交叉比对...")
    join_start = time.time()

    existing_df_with_base = target_df.join(fasta_df, on="Base_Accession", how="inner")
    missing_df = target_df.join(fasta_df, on="Base_Accession", how="anti").drop("Base_Accession")

    # 重点修复：提取完整的 Fasta_ID 交给后续提取步骤，而不是被截断的 Base_Accession
    existing_fasta_ids = set(existing_df_with_base.get_column("Fasta_ID").to_list())
    existing_df = existing_df_with_base.drop(["Base_Accession", "Fasta_ID"])

    print(f"   ⚡ 比对完成！仅耗时: {time.time() - join_start:.4f} 秒")
    print(f"   ✅ 本地已存在 (即将提取): {existing_df.height} 条")
    print(f"   ❌ 本地缺失 (需要下载)  : {missing_df.height} 条")

    # ==========================================
    # 4. 提取已存在的 FASTA 序列
    # ==========================================
    existing_fasta_file = os.path.join(args.out_dir, f"{prefix}_Extracted_Sequences.fasta")
    if existing_df.height > 0:
        print("\n⏳ 4. 正在从本地数据库中提取匹配的 FASTA 序列...")
        extract_start = time.time()

        if shutil.which("seqkit") is not None:
            print("   🚀 检测到 seqkit，使用高速提取模式...")
            extracted_count = extract_matching_fasta_seqkit(
                args.fasta, existing_fasta_file, existing_fasta_ids
            )
        else:
            print("   🐍 seqkit 未安装，使用纯 Python 流式提取（较慢）...")
            extracted_count = extract_matching_fasta_python(
                args.fasta, existing_fasta_file, existing_fasta_ids
            )

        print(f"   -> 成功提取了 {extracted_count} 条 FASTA 序列！(耗时 {time.time() - extract_start:.2f}s)")
    else:
        print("\n⏳ 4. 本地没有任何匹配的序列，跳过提取步骤。")

    # ==========================================
    # 5. 输出元数据与下载指令
    # ==========================================
    print("\n⏳ 5. 正在生成输出元数据与下载指令...")

    existing_file = os.path.join(args.out_dir, f"{prefix}_Existing_Metadata.tsv")
    missing_file  = os.path.join(args.out_dir, f"{prefix}_Missing_Metadata.tsv")
    acc_list_file = os.path.join(args.out_dir, f"{prefix}_missing_accessions.txt")

    if existing_df.height > 0:
        existing_df.write_csv(existing_file, separator="\t")
        print(f"   📂 已提取序列保存至 : {existing_fasta_file}")
        print(f"   📂 已存在元数据保存 : {existing_file}")

    if missing_df.height > 0:
        missing_df.write_csv(missing_file, separator="\t")
        missing_accessions = missing_df.get_column("Accession").to_list()
        with open(acc_list_file, "w") as f:
            f.write("\n".join(missing_accessions) + "\n")

        print(f"   📂 缺失元数据保存至 : {missing_file}")
        print(f"   📄 缺失序列ID列表   : {acc_list_file}")

        zip_name = f"{prefix}_viruses.zip"
        
        # 安全修复：优先从环境变量读取 API Key，如果没有则留空提示
        api_key = os.environ.get("NCBI_API_KEY", "YOUR_API_KEY_HERE")
        
        print("\n==================================================================================================")
        print("💡 提取完毕！请复制以下两行命令，在终端中直接运行以高速下载缺失的数据：")
        print("--------------------------------------------------------------------------------------------------")
        print(f"cd {args.out_dir}")
        print(f'datasets download virus genome accession --inputfile {os.path.basename(acc_list_file)} --filename {zip_name} --include genome,cds,protein --api-key "{api_key}"')
        print("==================================================================================================\n")
    else:
        print(f"   🎉 完美！所有的 [{prefix}] 病毒序列本地数据库都已经涵盖！您所需的所有序列均已在 `{existing_fasta_file}` 中。")

    print(f"⏱️ 整体流水线耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
