#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import urllib.request
import urllib.parse
import time
import sys
import os
import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        description="🚀 NCBI 极速、全量核酸序列下载器 (突破 genome 完整度限制)\n"
                    "----------------------------------------------------------\n"
                    "此工具直接调用 NCBI E-utilities 原生接口，绕过 datasets 的智能过滤，\n"
                    "确保列表中的每一个 Accession（哪怕只是短片段）都能被完整下载到本地。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "-i", "--input", 
        required=True, 
        help="[必填] 输入的 Accession 列表文件路径 (每行一个 Accession，例如: missing_accessions_list.txt)"
    )
    
    parser.add_argument(
        "-o", "--output", 
        required=True, 
        help="[必填] 最终保存的 FASTA 序列文件路径 (例如: Downloaded_Viruses.fasta)"
    )
    
    parser.add_argument(
        "-k", "--api_key", 
        default="80a47d7eae0bef204ccf4a2714c96bec8809", 
        help="[可选] NCBI API Key。提供后请求频率上限可提升至 10次/秒。\n"
             "       如果不填，将使用代码中默认的 API Key。"
    )
    
    parser.add_argument(
        "-c", "--chunk_size", 
        type=int, 
        default=400, 
        help="[可选] 每次向 NCBI 发送请求的 Accession 数量 (默认: 400)。\n"
             "       建议范围 200~500，过大可能导致 URL 过长或 NCBI 服务器超时拒绝。"
    )
    
    parser.add_argument(
        "-r", "--max_retries", 
        type=int, 
        default=5, 
        help="[可选] 遇到网络超时或 502/504 错误时的最大重试次数 (默认: 5)。"
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="[可选] 开启断点续传模式。\n"
             "       程序会自动检查 output 文件中已存在的序列，并跳过这些已下载的 Accession。"
    )

    return parser.parse_args()

def check_existing_accessions(output_file: str) -> set:
    """如果开启断点续传，扫描已下载文件中的 '>' 提取出已成功下载的基础 Accession"""
    existing_accs = set()
    if not os.path.exists(output_file):
        return existing_accs
    
    print(f"🔄 检测到开启了 --resume 断点续传，正在扫描已存在文件 [{output_file}]...")
    with open(output_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith(">"):
                # 从 ">NC_012345.1 description..." 中提取 "NC_012345"
                base_acc = line[1:].split()[0].split('.')[0]
                existing_accs.add(base_acc)
                
    print(f"   -> 发现 {len(existing_accs)} 条已成功下载的独特序列，将跳过它们。")
    return existing_accs

def download_missing_fasta():
    args = parse_args()

    # 1. 验证输入文件
    if not os.path.exists(args.input):
        print(f"❌ 错误: 找不到输入文件 '{args.input}'")
        sys.exit(1)

    # 2. 加载所有需要下载的 Accessions
    with open(args.input, 'r') as f:
        raw_accessions = [line.strip() for line in f if line.strip()]

    # 3. 处理断点续传过滤
    if args.resume:
        existing_accs = check_existing_accessions(args.output)
        # 过滤掉已经下载的序列（比较基础 Accession 即可）
        accessions = [acc for acc in raw_accessions if acc.split('.')[0] not in existing_accs]
        
        # 打开模式变为追加
        open_mode = 'a'
        if not accessions:
            print("🎉 完美！该列表中的所有序列均已存在于您的本地文件中，无需重复下载。")
            sys.exit(0)
    else:
        accessions = raw_accessions
        # 不续传则强制覆盖重写
        open_mode = 'w'

    total = len(accessions)
    print("==========================================================")
    print(f"🚀 启动 NCBI 原生高频下载引擎")
    print(f"📊 待下载序列总数 : {total} 条")
    print(f"📦 批量请求大小   : 每次 {args.chunk_size} 条")
    print(f"🔑 API Key        : {args.api_key[:8]}********")
    print("==========================================================")

    success_count = 0
    fail_count = 0

    with open(args.output, open_mode, encoding="utf-8") as out_f:
        for i in range(0, total, args.chunk_size):
            chunk = accessions[i:i+args.chunk_size]
            id_string = ",".join(chunk)
            
            # 构建 efetch API 核心请求参数 (db=nuccore 无脑下全部核酸)
            params = {
                "db": "nuccore",
                "id": id_string,
                "rettype": "fasta",
                "retmode": "text",
                "api_key": args.api_key
            }
            
            data = urllib.parse.urlencode(params).encode("utf-8")
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            req = urllib.request.Request(url, data=data)
            
            chunk_success = False
            for attempt in range(1, args.max_retries + 1):
                try:
                    with urllib.request.urlopen(req, timeout=120) as response:
                        fasta_data = response.read().decode("utf-8")
                        
                        # 如果 NCBI 被挤爆，有时会返回空字符串或 HTML 报错页
                        if fasta_data.strip().startswith(">"):
                            out_f.write(fasta_data)
                            if not fasta_data.endswith('\n'):
                                out_f.write('\n')
                                
                            chunk_success = True
                            success_count += len(chunk)
                            print(f"   ✅ 进度: [ {success_count} / {total} ] - 成功下载 {len(chunk)} 条。")
                            break
                        else:
                            # 如果返回的不是 FASTA，抛出异常以触发重试
                            err_msg = fasta_data[:100].replace('\n', ' ')
                            raise ValueError(f"NCBI 未返回标准 FASTA，内容摘要: {err_msg}")
                            
                except Exception as e:
                    print(f"      ⚠ 下载异常 (重试 {attempt}/{args.max_retries}): {str(e)}")
                    # 遇到错误时停顿久一点，防止被彻底拉黑
                    time.sleep(5)
            
            if not chunk_success:
                print(f"   ❌ [极其罕见] 该批次彻底失败 (从 {chunk[0]} 等 {len(chunk)} 条)。它们可能已被 NCBI 永久移除。")
                fail_count += len(chunk)

            # API 速率保护：有 API Key 时，NCBI 允许 10次请求/秒。
            # 为了极端稳定，我们每批次间只停顿 0.3 秒，完全不构成压力。
            time.sleep(0.3)

    print("==========================================================")
    print(f"🎉 跑批任务全部结束！")
    print(f"✅ 成功下载 : {success_count} 条")
    if fail_count > 0:
        print(f"❌ 失败记录 : {fail_count} 条 (大概率是 NCBI 端由于测序错误等原因废弃了该记录)")
    print(f"📁 结果已存 : {args.output}")
    print("==========================================================")

if __name__ == "__main__":
    download_missing_fasta()
