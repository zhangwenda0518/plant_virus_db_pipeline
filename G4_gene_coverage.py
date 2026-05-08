#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import os

def parse_args():
    # 初始化 ArgumentParser，并添加详细的描述信息
    parser = argparse.ArgumentParser(
        description=(
            "=================================================================\n"
            "病毒基因覆盖度计算工具 (Virus Gene Coverage Calculator)\n"
            "功能: 结合 GFF3 基因预测结果和 MAP 长度文件，计算病毒基因的长度特征\n"
            "      及其在基因组中的覆盖度（平均值、最大值、总和）。\n"
            "      对于没有基因预测结果的序列，将单独提取到另一个文件中。\n"
            "================================================================="
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )

    # 输入参数
    parser.add_argument("-g", "--gff", required=True,
                        help="[必需] 输入的GFF3格式文件 (例如: virus.gene.gff3)\n"
                             "必须包含 CDS 特征及起止坐标以计算基因长度。")
    parser.add_argument("-m", "--map", required=True,
                        help="[必需] 输入的序列长度映射文件 (例如: seqid2taxid_len.map)\n"
                             "格式要求为制表符分隔的三列: seqid \\t taxid \\t genome_len")
    
    # 输出参数
    parser.add_argument("-o", "--out", required=True,
                        help="[必需] 主输出文件路径 (包含有基因预测结果的序列)。\n"
                             "输出列: seqid, taxid, genome_len, gene_avr_len, \n"
                             "gene_max_len, gene_total_len, gene_avr_cov, \n"
                             "gene_max_cov, gene_total_cov")
    parser.add_argument("-u", "--unpredicted", required=True,
                        help="[必需] 未预测到基因序列的单独输出文件路径。\n"
                             "仅包含三列: seqid, taxid, genome_len")

    return parser.parse_args()

def main():
    args = parse_args()

    # 1. 解析 GFF3 获取基因长度
    gene_lengths = {}
    print(f"正在读取并解析 GFF3 文件: {args.gff} ...")
    try:
        with open(args.gff, 'r') as f_gff:
            for line in f_gff:
                if line.startswith('#'):
                    continue
                parts = line.strip('\n').split('\t')
                
                # 确保行格式正确，且为 CDS (编码序列)
                if len(parts) < 9 or parts[2] != 'CDS':
                    continue
                
                seqid = parts[0]
                start = int(parts[3])
                end = int(parts[4])
                
                # 计算长度
                gene_len = end - start + 1
                
                if seqid not in gene_lengths:
                    gene_lengths[seqid] = []
                gene_lengths[seqid].append(gene_len)
    except FileNotFoundError:
        print(f"错误: 找不到 GFF3 文件 {args.gff}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"读取 GFF3 出现异常: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. 读取 MAP 文件，计算并分别写入两个输出文件
    print(f"正在读取 MAP 文件并计算覆盖度: {args.map} ...")
    count_predicted = 0
    count_unpredicted = 0

    try:
        with open(args.map, 'r') as f_map, \
             open(args.out, 'w') as f_out, \
             open(args.unpredicted, 'w') as f_unpred:

            # 写入主输出文件表头
            header_out = ["seqid", "taxid", "genome_len", "gene_avr_len", 
                          "gene_max_len", "gene_total_len", "gene_avr_cov", 
                          "gene_max_cov", "gene_total_cov"]
            f_out.write("\t".join(header_out) + "\n")

            # 写入未预测文件表头
            header_unpred = ["seqid", "taxid", "genome_len"]
            f_unpred.write("\t".join(header_unpred) + "\n")

            # 遍历 MAP
            for line in f_map:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) < 3:
                    continue
                
                seqid = parts[0]
                taxid = parts[1]
                genome_len = int(parts[2])

                # 避免分母为0的极端情况
                if genome_len == 0:
                    continue

                # 如果该 seqid 预测到了基因
                if seqid in gene_lengths and len(gene_lengths[seqid]) > 0:
                    lengths = gene_lengths[seqid]
                    
                    total_len = sum(lengths)
                    max_len = max(lengths)
                    avr_len = total_len / len(lengths)
                    
                    # 计算覆盖度
                    avr_cov = avr_len / genome_len
                    max_cov = max_len / genome_len
                    total_cov = total_len / genome_len
                    
                    row = [
                        seqid, taxid, str(genome_len),
                        f"{avr_len:.2f}", f"{max_len:.2f}", f"{total_len:.2f}",
                        f"{avr_cov:.4f}", f"{max_cov:.4f}", f"{total_cov:.4f}"
                    ]
                    f_out.write("\t".join(row) + "\n")
                    count_predicted += 1
                
                # 如果该 seqid 没有预测到基因
                else:
                    row_unpred = [seqid, taxid, str(genome_len)]
                    f_unpred.write("\t".join(row_unpred) + "\n")
                    count_unpredicted += 1

    except FileNotFoundError:
        print(f"错误: 找不到 MAP 文件 {args.map}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"处理数据或写入文件时出现异常: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. 打印统计信息
    print("-----------------------------------------------------------------")
    print("处理完成！")
    print(f"成功预测并计算出基因指标的序列数 : {count_predicted} 个 -> {args.out}")
    print(f"未预测到任何基因的序列数         : {count_unpredicted} 个 -> {args.unpredicted}")
    print("-----------------------------------------------------------------")

if __name__ == '__main__':
    main()
