#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import sys
import os
from Bio import Entrez, SeqIO

def main():
    # 1. 设置命令行参数解析器并编写帮助信息
    parser = argparse.ArgumentParser(
        description="批量从 NCBI 核酸数据库获取序列信息并导出为表格 (TSV 格式)。\n提取字段: Accession, Title, Length (纯数字), Topology, Molecule_Type",
        epilog="使用示例: python get_info.py -i acc_list.txt -o result.tsv -e your_email@example.com",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # 添加参数
    parser.add_argument("-i", "--input", required=True, 
                        help="[必填] 输入文件路径，包含 Accession 号，每行一个。")
    parser.add_argument("-o", "--output", default="sequence_info.tsv", 
                        help="[可选] 输出文件路径 (默认: sequence_info.tsv)。推荐使用 .tsv 或 .txt 后缀。")
    parser.add_argument("-e", "--email", required=True, 
                        help="[必填] 你的电子邮箱地址 (NCBI 官方要求，用于防止滥用)。")
    parser.add_argument("-b", "--batch", type=int, default=200, 
                        help="[可选] 每次向 NCBI 发起请求的并发数量 (默认: 200，建议在 100-500 之间)。")

    # 2. 解析参数
    args = parser.parse_args()

    # 将邮箱传递给 Entrez
    Entrez.email = args.email

    # 3. 检查输入文件是否存在
    if not os.path.exists(args.input):
        print(f"❌ 错误: 找不到输入文件 '{args.input}'，请检查路径是否正确！")
        sys.exit(1)

    # 4. 读取 Accession 列表
    with open(args.input, "r", encoding="utf-8") as f:
        acc_list = [line.strip() for line in f if line.strip()]

    if not acc_list:
        print(f"❌ 错误: 输入文件 '{args.input}' 为空或没有有效的 Accession 号！")
        sys.exit(1)

    print(f"✅ 成功读取 {len(acc_list)} 个 Accession 号，准备开始下载...\n")

    # 5. 打开输出文件并准备抓取
    with open(args.output, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.writer(out_f, delimiter="\t")
        # 写入表头
        writer.writerow(["Accession", "Title", "Length", "Topology", "Molecule_Type"])
        
        # 按设定的 batch_size 分批次抓取
        for i in range(0, len(acc_list), args.batch):
            batch = acc_list[i : i + args.batch]
            end_idx = min(i + args.batch, len(acc_list))
            print(f"⏳ 正在处理第 {i+1} 到 {end_idx} 条序列...")
            
            try:
                # 核心抓取代码：下载 GenBank 格式并解析
                handle = Entrez.efetch(db="nuccore", id=batch, rettype="gb", retmode="text")
                records = SeqIO.parse(handle, "genbank")
                
                # 遍历并提取所需的 5 个字段
                for record in records:
                    acc = record.id
                    title = record.description
                    length = len(record)  # 【修改处】直接获取纯数字，不加千位分隔符
                    topology = record.annotations.get("topology", "unknown")
                    mol_type = record.annotations.get("molecule_type", "unknown")
                    
                    writer.writerow([acc, title, length, topology, mol_type])
                
                handle.close()
            except Exception as e:
                print(f"⚠️ 抓取该批次时发生网络或解析错误: {e}")
                print("➡️ 提示：请检查网络连接或 Accession 号是否拼写正确。")

    print(f"\n🎉 全部提取完成！结果已保存至: {os.path.abspath(args.output)}")

if __name__ == "__main__":
    main()
