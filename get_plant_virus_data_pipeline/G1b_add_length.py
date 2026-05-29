#!/usr/bin/env python3
"""
并行计算基因组序列长度，并添加到seqid2taxid.map文件作为第三列。
支持两种输入方式：
  - 目录模式：每个序列一个单独的FASTA文件（-g/--genome-dir）
  - 单文件模式：一个大的FASTA文件包含所有序列（-f/--genome-file）
手动指定序列类型（核酸/蛋白），若为蛋白则长度乘以3。
使用多进程加速（仅目录模式有效）。

用法：
    # 目录模式
    python add_length_parallel.py -i seqid2taxid.map -g genome_dir -o output.map --type nucleotide|protein [-p 16] [--missing-as-zero]

    # 单文件模式
    python add_length_parallel.py -i seqid2taxid.map -f all_sequences.fasta -o output.map --type nucleotide|protein [--missing-as-zero]
"""

import os
import sys
import argparse
from multiprocessing import Pool, cpu_count
from functools import partial

def calculate_fasta_length(fasta_path):
    """计算单个fasta文件的序列总长度（忽略标题行和空白行）"""
    total_length = 0
    try:
        with open(fasta_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('>'):
                    continue
                total_length += len(line)
    except Exception:
        return -1
    return total_length

def parse_multi_fasta(fasta_file, multiply_factor):
    """
    解析一个包含多条序列的FASTA文件，返回字典 {seqid: 调整后长度}
    长度已乘以multiply_factor。
    若解析过程中出错，返回空字典并输出错误信息。
    """
    seqid_to_len = {}
    current_id = None
    current_len = 0
    try:
        with open(fasta_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('>'):
                    # 保存上一条序列
                    if current_id is not None:
                        seqid_to_len[current_id] = current_len * multiply_factor
                    # 开始新序列
                    current_id = line[1:].split()[0]  # 取第一个空格前的部分作为ID
                    current_len = 0
                else:
                    current_len += len(line)
            # 保存最后一条序列
            if current_id is not None:
                seqid_to_len[current_id] = current_len * multiply_factor
    except Exception as e:
        print(f"错误：解析多序列FASTA文件失败 - {e}", file=sys.stderr)
        return {}
    return seqid_to_len

def process_seqid_dir(seqid, genome_dir, missing_as_zero, multiply_factor):
    """目录模式下处理单个seqid"""
    fasta_path = os.path.join(genome_dir, seqid + ".fasta")
    if os.path.isfile(fasta_path):
        length = calculate_fasta_length(fasta_path)
        if length < 0:
            length = 0 if missing_as_zero else -1
        else:
            length *= multiply_factor
    else:
        length = 0 if missing_as_zero else -1
    return (seqid, length)

def main():
    parser = argparse.ArgumentParser(description='计算序列长度并添加至map文件，手动指定类型（核酸/蛋白），蛋白长度×3。支持目录或单文件输入。')
    parser.add_argument('-i', '--input', required=True,
                        help='输入map文件，两列：seqid taxid')
    parser.add_argument('-o', '--output', required=True,
                        help='输出文件，三列：seqid taxid length')

    # 互斥的输入模式：目录 或 单文件
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-g', '--genome-dir',
                       help='包含FASTA文件的目录，文件名格式为 seqid.fasta（目录模式）')
    group.add_argument('-f', '--genome-file',
                       help='包含所有序列的单个FASTA文件（单文件模式）')

    parser.add_argument('-p', '--processes', type=int, default=cpu_count(),
                        help=f'并行进程数，仅目录模式有效，默认使用所有CPU核心数 ({cpu_count()})')
    parser.add_argument('--missing-as-zero', action='store_true',
                        help='若FASTA文件/序列缺失或读取失败，长度设为0（默认跳过该行）')
    parser.add_argument('--type', required=True, choices=['nucleotide', 'protein'],
                        help='序列类型：nucleotide（长度不变）或 protein（长度×3）')
    args = parser.parse_args()

    multiply_factor = 3 if args.type == 'protein' else 1

    # 读取map文件，保持顺序
    seqid_list = []      # 按顺序保存seqid
    taxid_dict = {}      # seqid -> taxid
    try:
        with open(args.input, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    seqid, taxid = parts[0], parts[1]
                    seqid_list.append(seqid)
                    taxid_dict[seqid] = taxid
                else:
                    print(f"警告：跳过无效行 {line_num}: {line}", file=sys.stderr)
    except FileNotFoundError:
        print(f"错误：输入文件 {args.input} 不存在", file=sys.stderr)
        sys.exit(1)

    if not seqid_list:
        print("错误：输入文件为空或无有效数据", file=sys.stderr)
        sys.exit(1)

    # 根据模式处理
    results = []
    if args.genome_dir:  # 目录模式
        if not os.path.isdir(args.genome_dir):
            print(f"错误：目录 {args.genome_dir} 不存在", file=sys.stderr)
            sys.exit(1)

        # 准备并行处理函数
        worker = partial(process_seqid_dir,
                         genome_dir=args.genome_dir,
                         missing_as_zero=args.missing_as_zero,
                         multiply_factor=multiply_factor)

        print(f"目录模式：开始并行计算，使用 {args.processes} 个进程...", file=sys.stderr)
        total = len(seqid_list)
        with Pool(processes=args.processes) as pool:
            for idx, (seqid, length) in enumerate(pool.imap(worker, seqid_list, chunksize=1000)):
                results.append((seqid, length))
                if (idx + 1) % 10000 == 0:
                    print(f"已处理 {idx+1}/{total} 条序列...", file=sys.stderr)

    else:  # 单文件模式
        if not os.path.isfile(args.genome_file):
            print(f"错误：文件 {args.genome_file} 不存在", file=sys.stderr)
            sys.exit(1)

        print("单文件模式：正在解析多序列FASTA文件...", file=sys.stderr)
        seqid_to_len = parse_multi_fasta(args.genome_file, multiply_factor)
        if not seqid_to_len:
            print("错误：解析FASTA文件失败或文件为空", file=sys.stderr)
            sys.exit(1)

        print(f"解析完成，共 {len(seqid_to_len)} 条序列。正在匹配map文件...", file=sys.stderr)
        for seqid in seqid_list:
            length = seqid_to_len.get(seqid, -1)
            if length < 0:
                length = 0 if args.missing_as_zero else -1
            results.append((seqid, length))

    # 写入输出文件，保持原顺序
    print("正在写入输出文件...", file=sys.stderr)
    with open(args.output, 'w') as out_f:
        written = 0
        for seqid, length in results:
            if length >= 0:
                out_f.write(f"{seqid}\t{taxid_dict[seqid]}\t{length}\n")
                written += 1
    print(f"完成！共处理 {written} 条记录，结果已写入 {args.output}", file=sys.stderr)

if __name__ == "__main__":
    main()
