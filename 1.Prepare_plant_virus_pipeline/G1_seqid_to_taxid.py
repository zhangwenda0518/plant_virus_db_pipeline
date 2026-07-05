#!/usr/bin/env python3
"""
高性能Accession ID到Tax ID映射工具
支持进度条显示、并行处理和多种优化策略

作者: Assistant
版本: 2.1
许可证: MIT
"""

import polars as pl
import sys
import argparse
from pathlib import Path
import time
from tqdm import tqdm
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import math
import os
import gzip
from typing import Set, Dict, List, Tuple

def show_detailed_help():
    """显示详细帮助信息"""
    help_text = """
Accession ID到Tax ID映射工具

SYNOPSIS:
    python3 mapper.py --query-file QUERY_FILE --map-file MAP_FILE [OPTIONS]

DESCRIPTION:
    该工具用于将序列ID映射到对应的分类学ID(Tax ID)。支持大型文件处理，
    提供进度条显示和并行处理功能。

REQUIRED ARGUMENTS:
    --query-file QUERY_FILE    包含序列ID的文件，每行一个ID
    --map-file MAP_FILE        映射文件，格式为TSV，包含accession和taxid字段

OPTIONAL ARGUMENTS:
    -o, --output FILE         输出文件路径 (默认: stdout)
    -j, --jobs N              并行处理的进程数 (默认: CPU核心数)
    -b, --batch-size N        每批处理的行数 (默认: 50000)
    -v, --verbose             显示详细信息
    --no-progress             禁用进度条显示
    --format FORMAT           输入文件格式 (auto/csv/tsv/gz) (默认: auto)
    -h, --help                显示此帮助信息

EXAMPLES:
    # 基本用法
    python3 mapper.py --query-file queries.txt --map-file mapping.tsv
    
    # 使用2个进程并行处理
    python3 mapper.py --query-file queries.txt --map-file mapping.tsv --jobs 2
    
    # 处理压缩文件
    python3 mapper.py --query-file queries.txt --map-file mapping.tsv.gz
    
    # 指定输出文件
    python3 mapper.py --query-file queries.txt --map-file mapping.tsv --output results.txt

FILE FORMATS:
    Query file format:
        Each line contains one sequence ID
        Example:
            NP_001123.1
            NP_002345.2
    
    Map file format (TSV):
        First column: accession ID
        Third column: taxid
        Example:
            NP_001123    version1    9606    version2
            NP_002345    version1    10090   version2

PERFORMANCE TIPS:
    1. 对于大于10GB的文件，建议使用并行处理(--jobs参数)
    2. 较小的批次大小可以减少内存使用
    3. 使用SSD存储可以获得更好的I/O性能

EXIT STATUS:
    0   正常完成
    1   错误退出
    2   参数错误
    """
    print(help_text.strip())

def estimate_total_lines(file_path: str) -> int:
    """估算文件总行数"""
    try:
        sample_size = 10 * 1024 * 1024  # 10MB样本
        
        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rb') as f:
                sample = f.read(sample_size)
            decoded_sample = sample.decode('utf-8', errors='ignore')
        else:
            with open(file_path, 'rb') as f:
                sample = f.read(sample_size)
            decoded_sample = sample.decode('utf-8', errors='ignore')
        
        sample_lines = decoded_sample.count('\n')
        if sample_lines == 0:
            return 1000000  # 默认值
        
        file_size = os.path.getsize(file_path)
        bytes_per_line = len(sample) / sample_lines
        estimated_lines = int(file_size / bytes_per_line)
        
        return max(estimated_lines, sample_lines)
    except Exception:
        return 1000000  # 默认值

def validate_files(query_file: str, map_file: str) -> bool:
    """验证输入文件"""
    if query_file and not Path(query_file).exists():
        print(f"错误: 查询文件不存在 - {query_file}", file=sys.stderr)
        return False
    
    if map_file and not Path(map_file).exists():
        print(f"错误: 映射文件不存在 - {map_file}", file=sys.stderr)
        return False
    
    if query_file and os.path.getsize(query_file) == 0:
        print(f"错误: 查询文件为空 - {query_file}", file=sys.stderr)
        return False
    
    if map_file and os.path.getsize(map_file) == 0:
        print(f"错误: 映射文件为空 - {map_file}", file=sys.stderr)
        return False
    
    return True

def parse_query_ids(query_file: str) -> Tuple[List[str], Set[str]]:
    """解析查询ID并返回完整ID列表和前缀集合"""
    with open(query_file, 'r') as f:
        seqids = [line.strip() for line in f if line.strip()]
    
    # 构建查询前缀集合
    query_prefixes = set()
    for seqid in seqids:
        # 处理常见的ID格式，如NP_001123.1 -> NP_001123
        if '.' in seqid:
            prefix = seqid.split('.')[0]
        else:
            prefix = seqid
        query_prefixes.add(prefix)
    
    return seqids, query_prefixes

def process_chunk_parallel(args):
    """并行处理的块处理函数"""
    chunk_info, query_prefixes = args
    file_path, start_pos, end_pos = chunk_info
    
    results = {}
    
    try:
        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                f.seek(start_pos)
                content = f.read(end_pos - start_pos)
        else:
            with open(file_path, 'rb') as f:
                f.seek(start_pos)
                content = f.read(end_pos - start_pos).decode('utf-8', errors='ignore')
        
        lines = content.split('\n')
        for line in lines:
            if not line.strip():
                continue
                
            parts = line.split('\t')
            if len(parts) >= 3:
                accession = parts[0].strip()
                taxid = parts[2].strip()
                
                if accession in query_prefixes:
                    results[accession] = taxid
    except Exception as e:
        print(f"警告: 块处理错误 - {e}", file=sys.stderr)
    
    return results

def parallel_process_large_file(query_file: str, map_file: str, 
                                num_processes: int, batch_size: int,
                                verbose: bool, show_progress: bool) -> Dict[str, str]:
    """并行处理大文件"""
    if verbose:
        print(f"使用 {num_processes} 个进程并行处理...")
    
    seqids, query_prefixes = parse_query_ids(query_file)
    
    # 计算文件分块
    file_size = os.path.getsize(map_file)
    chunk_size = max(file_size // num_processes, 10 * 1024 * 1024)  # 至少10MB每块
    
    chunks = []
    with open(map_file, 'rb') as f:
        start_pos = 0
        while start_pos < file_size:
            f.seek(start_pos + chunk_size)
            
            # 找到下一个换行符，确保按行分割
            while f.tell() < file_size:
                char = f.read(1)
                if char == b'\n':
                    break
            
            end_pos = f.tell()
            chunks.append((map_file, start_pos, end_pos))
            start_pos = end_pos
    
    # 并行处理
    results = {}
    found_count = 0
    
    progress_bar = None
    if show_progress:
        total_lines = estimate_total_lines(map_file)
        progress_bar = tqdm(total=len(chunks), desc="处理块", unit="chunks")
    
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        futures = [executor.submit(process_chunk_parallel, (chunk, query_prefixes)) for chunk in chunks]
        
        for i, future in enumerate(as_completed(futures)):
            chunk_result = future.result()
            results.update(chunk_result)
            
            found_count += len(chunk_result)
            if progress_bar:
                progress_bar.update(1)
            
            # 如果已经找到了所有需要的映射，提前结束
            if len(results) >= len(query_prefixes):
                if verbose:
                    print(f"提前终止: 已找到所有 {len(results)} 个映射")
                break
    
    if progress_bar:
        progress_bar.close()
    
    return results

def sequential_process_file(query_file: str, map_file: str, 
                           batch_size: int, verbose: bool, 
                           show_progress: bool) -> Dict[str, str]:
    """顺序处理文件"""
    seqids, query_prefixes = parse_query_ids(query_file)
    
    results = {}
    processed_lines = 0
    found_count = 0
    
    if map_file.endswith('.gz'):
        # 处理gzip文件
        total_lines = estimate_total_lines(map_file)
        progress_bar = tqdm(total=total_lines, desc="处理行", unit="lines") if show_progress else None
        
        with gzip.open(map_file, 'rt', encoding='utf-8', errors='ignore') as f:
            batch = []
            for line in f:
                batch.append(line.strip())
                
                if len(batch) >= batch_size:
                    # 处理批次
                    for batch_line in batch:
                        if not batch_line:
                            continue
                            
                        parts = batch_line.split('\t')
                        if len(parts) >= 3:
                            accession = parts[0].strip()
                            taxid = parts[2].strip()
                            
                            if accession in query_prefixes and accession not in results:
                                results[accession] = taxid
                                found_count += 1
                    
                    processed_lines += len(batch)
                    if progress_bar:
                        progress_bar.update(len(batch))
                    
                    batch = []
                    
                    # 提前终止检查
                    if len(results) >= len(query_prefixes):
                        if progress_bar:
                            progress_bar.n = total_lines
                            progress_bar.refresh()
                        break
            
            # 处理最后一批
            if batch:
                for batch_line in batch:
                    if not batch_line:
                        continue
                        
                    parts = batch_line.split('\t')
                    if len(parts) >= 3:
                        accession = parts[0].strip()
                        taxid = parts[2].strip()
                        
                        if accession in query_prefixes and accession not in results:
                            results[accession] = taxid
                            found_count += 1
        
        if progress_bar:
            progress_bar.close()
    else:
        # 处理普通文件
        total_lines = estimate_total_lines(map_file)
        progress_bar = tqdm(total=total_lines, desc="处理行", unit="lines") if show_progress else None
        
        with open(map_file, 'r', encoding='utf-8', errors='ignore') as f:
            batch = []
            for line in f:
                batch.append(line.strip())
                
                if len(batch) >= batch_size:
                    # 处理批次
                    for batch_line in batch:
                        if not batch_line:
                            continue
                            
                        parts = batch_line.split('\t')
                        if len(parts) >= 3:
                            accession = parts[0].strip()
                            taxid = parts[2].strip()
                            
                            if accession in query_prefixes and accession not in results:
                                results[accession] = taxid
                                found_count += 1
                    
                    processed_lines += len(batch)
                    if progress_bar:
                        progress_bar.update(len(batch))
                    
                    batch = []
                    
                    # 提前终止检查
                    if len(results) >= len(query_prefixes):
                        if progress_bar:
                            progress_bar.n = total_lines
                            progress_bar.refresh()
                        break
            
            # 处理最后一批
            if batch:
                for batch_line in batch:
                    if not batch_line:
                        continue
                        
                    parts = batch_line.split('\t')
                    if len(parts) >= 3:
                        accession = parts[0].strip()
                        taxid = parts[2].strip()
                        
                        if accession in query_prefixes and accession not in results:
                            results[accession] = taxid
                            found_count += 1
        
        if progress_bar:
            progress_bar.close()
    
    return results

def write_results(query_file: str, results: Dict[str, str], output_file: str = None):
    """写入结果"""
    seqids, _ = parse_query_ids(query_file)
    
    output_handle = sys.stdout if output_file is None else open(output_file, 'w')
    
    try:
        for seqid in seqids:
            prefix = seqid.split('.')[0] if '.' in seqid else seqid
            taxid = results.get(prefix, '1')  # 默认taxid为1
            output_handle.write(f"{seqid}\t{taxid}\n")
    finally:
        if output_file:
            output_handle.close()

def main():
    # 先检查命令行参数中是否包含 -h 或 --help
    if '-h' in sys.argv or '--help' in sys.argv:
        show_detailed_help()
        sys.exit(0)
    
    # 创建一个临时解析器来检查是否只有帮助参数
    temp_parser = argparse.ArgumentParser(add_help=False)
    temp_parser.add_argument('-h', '--help', action='store_true')
    temp_args, _ = temp_parser.parse_known_args()
    
    if temp_args.help:
        show_detailed_help()
        sys.exit(0)
    
    # 创建主解析器（不包含 -h 参数）
    parser = argparse.ArgumentParser(
        description="高性能Accession ID到Tax ID映射工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False  # 不自动添加 -h 参数
    )
    
    # 添加必需参数组
    required = parser.add_argument_group('必需参数')
    required.add_argument('--query-file', required=True,
                         help='包含序列ID的查询文件，每行一个ID')
    required.add_argument('--map-file', required=True,
                         help='映射文件，格式为TSV，包含accession和taxid字段')
    
    # 添加可选参数组
    optional = parser.add_argument_group('可选参数')
    optional.add_argument('-o', '--output', help='输出文件路径 (默认: stdout)')
    optional.add_argument('-j', '--jobs', type=int, default=mp.cpu_count(),
                         help='并行处理的进程数 (默认: CPU核心数)')
    optional.add_argument('-b', '--batch-size', type=int, default=50000,
                         help='每批处理的行数 (默认: 50000)')
    optional.add_argument('-v', '--verbose', action='store_true',
                         help='显示详细信息')
    optional.add_argument('--no-progress', action='store_true',
                         help='禁用进度条显示')
    optional.add_argument('--format', choices=['auto', 'csv', 'tsv', 'gz'], 
                         default='auto', help='输入文件格式 (默认: auto)')
    
    # 解析参数
    try:
        args = parser.parse_args()
    except SystemExit as e:
        if e.code != 0:  # 如果不是正常退出（如缺少必需参数）
            print("\n要查看帮助信息，请使用 -h 或 --help 参数")
            print("示例: python3 mapper.py --help\n")
        raise e
    
    if not validate_files(args.query_file, args.map_file):
        sys.exit(1)
    
    if args.verbose:
        print(f"查询文件: {args.query_file}")
        print(f"映射文件: {args.map_file}")
        print(f"输出文件: {args.output or 'stdout'}")
        print(f"并行进程数: {args.jobs}")
        print(f"批次大小: {args.batch_size}")
    
    # 根据文件大小决定是否使用并行处理
    map_file_size = os.path.getsize(args.map_file)
    use_parallel = map_file_size > 500 * 1024 * 1024  # 大于500MB使用并行
    
    start_time = time.time()
    
    if use_parallel and args.jobs > 1:
        if args.verbose:
            print("检测到大文件，使用并行处理模式...")
        results = parallel_process_large_file(
            args.query_file, args.map_file, 
            args.jobs, args.batch_size, 
            args.verbose, not args.no_progress
        )
    else:
        if args.verbose:
            print("使用顺序处理模式...")
        results = sequential_process_file(
            args.query_file, args.map_file, 
            args.batch_size, args.verbose, 
            not args.no_progress
        )
    
    write_results(args.query_file, results, args.output)
    
    elapsed_time = time.time() - start_time
    if args.verbose:
        print(f"\n处理完成!")
        print(f"找到映射数量: {len(results)}")
        print(f"总耗时: {elapsed_time:.2f} 秒")
        print(f"平均速度: {os.path.getsize(args.map_file) / elapsed_time / 1024 / 1024:.2f} MB/s")

if __name__ == "__main__":
    main()
