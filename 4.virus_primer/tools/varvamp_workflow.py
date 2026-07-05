#!/usr/bin/env python3
"""
varVAMP 集成工作流脚本
整合数据准备、比对、vsearch聚类和varvamp引物设计功能
支持单个文件或包含多个FASTA文件的目录作为输入
支持 -o 选项指定输出目录
"""

import os
import sys
import argparse
import subprocess
import logging
import glob
import shutil
from datetime import datetime
from pathlib import Path

class VarVAMPWorkflow:
    def __init__(self):
        self.logger = self.setup_logging()
        self.args = self.parse_arguments()
        
    def setup_logging(self):
        """设置日志记录"""
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        return logging.getLogger(__name__)
    
    def parse_arguments(self):
        """解析命令行参数"""
        parser = argparse.ArgumentParser(
            description="varVAMP 集成工作流脚本 - 整合数据准备、比对、聚类和引物设计"
        )
        
        parser.add_argument(
            "input", 
            help="输入文件或目录（支持单个FASTA文件或包含多个FASTA文件的目录）"
        )
        
        parser.add_argument(
            "-o", "--output-dir", 
            required=True,
            help="输出目录（必需）"
        )
        
        parser.add_argument(
            "-m", "--mode", 
            default="all",
            choices=["single", "tiled", "qpcr", "all"],
            help="运行模式: single, tiled, qpcr 或 all (默认: all)"
        )
        
        parser.add_argument(
            "-i", "--identity", 
            type=float, 
            default=0.83,
            help="vsearch聚类Identity阈值 (默认: 0.83)"
        )
        
        parser.add_argument(
            "-t", "--threads", 
            type=int, 
            default=4,
            help="使用的线程数 (默认: 4)"
        )
        
        parser.add_argument(
            "-db", "--database", 
            help="BLAST数据库目录或文件 (可选)"
        )
        
        parser.add_argument(
            "-n", "--name", 
            default="varVAMP_project",
            help="项目名称 (默认: varVAMP_project)"
        )
        
        parser.add_argument(
            "--no-align", 
            action="store_true",
            help="跳过比对步骤 (假设输入已是比对文件)"
        )
        
        parser.add_argument(
            "--no-cluster", 
            action="store_true",
            help="跳过聚类步骤"
        )
        
        parser.add_argument(
            "--min-length", 
            type=int, 
            default=0,
            help="过滤序列的最小长度 (默认: 不过滤)"
        )
        
        parser.add_argument(
            "--max-length", 
            type=int, 
            default=0,
            help="过滤序列的最大长度 (默认: 不过滤)"
        )
        
        return parser.parse_args()
    
    def run_command(self, cmd, check=True, capture_output=False):
        """运行外部命令并处理输出"""
        self.logger.info(f"执行命令: {cmd}")
        
        try:
            result = subprocess.run(
                cmd, 
                shell=True, 
                check=check, 
                capture_output=capture_output,
                text=True
            )
            if capture_output:
                return result.stdout.strip()
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"命令执行失败: {e}")
            if e.stderr:
                self.logger.error(f"错误输出: {e.stderr}")
            return False
    
    def check_tool(self, tool_name):
        """检查工具是否安装"""
        self.logger.info(f"检查工具: {tool_name}")
        return self.run_command(f"which {tool_name}", capture_output=True)
    
    def find_fasta_files(self, path):
        """查找指定路径中的所有FASTA文件"""
        path = Path(path)
        fasta_extensions = ['.fasta', '.fa', '.fna', '.ffn', '.faa', '.frn']
        
        if path.is_file():
            # 检查单个文件是否是FASTA文件
            if path.suffix.lower() in fasta_extensions:
                return [path]
            else:
                self.logger.warning(f"文件 {path} 不是FASTA格式（扩展名不支持）")
                return []
        
        elif path.is_dir():
            # 查找目录中的所有FASTA文件
            fasta_files = []
            for ext in fasta_extensions:
                fasta_files.extend(path.glob(f"*{ext}"))
                fasta_files.extend(path.glob(f"*{ext.upper()}"))
            
            if not fasta_files:
                self.logger.warning(f"在目录 {path} 中未找到FASTA文件")
            
            return fasta_files
        
        else:
            self.logger.error(f"路径不存在: {path}")
            return []
    
    def filter_sequences(self, input_file, output_file, min_length=0, max_length=0):
        """过滤序列长度"""
        if min_length <= 0 and max_length <= 0:
            # 不需要过滤
            return input_file
        
        self.logger.info(f"过滤序列: 最小长度={min_length}, 最大长度={max_length}")
        
        try:
            from Bio import SeqIO
            
            filtered_count = 0
            total_count = 0
            
            with open(output_file, 'w') as out_handle:
                for record in SeqIO.parse(input_file, "fasta"):
                    total_count += 1
                    seq_length = len(record.seq)
                    
                    # 检查长度条件
                    if (min_length <= 0 or seq_length >= min_length) and \
                       (max_length <= 0 or seq_length <= max_length):
                        SeqIO.write(record, out_handle, "fasta")
                    else:
                        filtered_count += 1
            
            self.logger.info(f"序列过滤完成: 总共 {total_count} 条序列，过滤掉 {filtered_count} 条")
            
            if total_count == filtered_count:
                self.logger.error("所有序列都被过滤掉了！")
                return None
            
            return output_file
        except ImportError:
            self.logger.warning("未安装Biopython，无法进行序列长度过滤")
            return input_file
    
    def prepare_input(self, input_path, output_dir, min_length=0, max_length=0):
        """准备输入数据"""
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        
        # 查找所有FASTA文件
        fasta_files = self.find_fasta_files(input_path)
        
        if not fasta_files:
            self.logger.error("未找到任何FASTA文件")
            return None
        
        # 如果只有一个文件，直接使用或过滤
        if len(fasta_files) == 1:
            input_file = fasta_files[0]
            
            # 如果需要过滤长度
            if min_length > 0 or max_length > 0:
                filtered_file = output_dir / "filtered_sequences.fasta"
                result = self.filter_sequences(input_file, filtered_file, min_length, max_length)
                return result if result else input_file
            else:
                return input_file
        
        # 多个文件，合并它们
        self.logger.info(f"合并 {len(fasta_files)} 个FASTA文件...")
        combined_file = output_dir / "combined_sequences.fasta"
        temp_combined = output_dir / "temp_combined.fasta"
        
        # 先合并所有文件
        with open(temp_combined, 'w') as outfile:
            for f in fasta_files:
                with open(f, 'r') as infile:
                    outfile.write(infile.read())
        
        # 如果需要过滤长度
        if min_length > 0 or max_length > 0:
            result = self.filter_sequences(temp_combined, combined_file, min_length, max_length)
            # 删除临时文件
            temp_combined.unlink()
            return result if result else temp_combined
        else:
            # 重命名临时文件
            temp_combined.rename(combined_file)
            self.logger.info(f"合并完成: {combined_file}")
            return combined_file
    
    def align_sequences(self, input_file, output_file):
        """使用MAFFT进行多序列比对"""
        self.logger.info("使用MAFFT进行多序列比对...")
        
        cmd = f"mafft --quiet --thread {self.args.threads} --auto {input_file} > {output_file}"
        if self.run_command(cmd):
            self.logger.info(f"比对完成，结果保存至: {output_file}")
            return True
        return False
    
    def cluster_sequences(self, input_file, output_dir, identity):
        """使用vsearch进行聚类"""
        self.logger.info(f"使用vsearch进行聚类，identity阈值: {identity}")
        
        cluster_dir = Path(output_dir) / "clusters"
        cluster_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = f"vsearch --cluster_fast {input_file} --id {identity} --clusters {cluster_dir}/cluster --threads {self.args.threads}"
        
        if self.run_command(cmd):
            self.logger.info(f"聚类完成，结果保存在: {cluster_dir}")
            return cluster_dir
        return None
    
    def create_blast_db(self, db_input, output_dir):
        """创建BLAST数据库"""
        self.logger.info("创建BLAST数据库...")
        
        blast_db_dir = Path(output_dir) / "blast_db"
        blast_db_dir.mkdir(parents=True, exist_ok=True)
        
        # 准备输入文件
        db_input = Path(db_input)
        off_targets_file = blast_db_dir / "off_targets.fasta"
        
        if db_input.is_dir():
            # 查找目录中的所有FASTA文件
            fasta_files = self.find_fasta_files(db_input)
            
            if not fasta_files:
                self.logger.error("数据库目录中未找到FASTA文件")
                return None
            
            # 合并文件
            with open(off_targets_file, 'w') as outfile:
                for f in fasta_files:
                    with open(f, 'r') as infile:
                        outfile.write(infile.read())
        
        elif db_input.is_file():
            # 检查文件类型
            if db_input.suffix.lower() in ['.fasta', '.fa', '.fna', '.ffn', '.faa', '.frn']:
                # 复制单个文件
                shutil.copy2(db_input, off_targets_file)
            else:
                self.logger.error("数据库文件不是FASTA格式")
                return None
        
        else:
            self.logger.error("数据库路径无效")
            return None
        
        # 创建BLAST数据库
        cmd = f"makeblastdb -in {off_targets_file} -out {blast_db_dir}/off_targets -dbtype nucl -hash_index"
        
        if self.run_command(cmd):
            self.logger.info(f"BLAST数据库创建完成: {blast_db_dir}/off_targets")
            return f"{blast_db_dir}/off_targets"
        return None
    
    def run_varvamp(self, mode, alignment, output_dir, db_path=None):
        """运行varvamp"""
        self.logger.info(f"运行varvamp {mode} 模式...")
        
        # 构建输出目录
        output_path = Path(output_dir) / f"{mode}_primers"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 构建命令
        db_arg = f"-db {db_path}" if db_path else ""
        
        if mode == "single":
            cmd = f"varvamp single {db_arg} -th {self.args.threads} --name {self.args.name} {alignment} {output_path}"
        elif mode == "tiled":
            cmd = f"varvamp tiled {db_arg} -th {self.args.threads} --name {self.args.name} {alignment} {output_path}"
        elif mode == "qpcr":
            cmd = f"varvamp qpcr {db_arg} -th {self.args.threads} --name {self.args.name} {alignment} {output_path}"
        else:
            self.logger.error(f"未知模式: {mode}")
            return False
        
        if self.run_command(cmd):
            self.logger.info(f"varvamp {mode} 模式完成，结果保存在: {output_path}")
            return True
        return False
    
    def run(self):
        """运行主工作流"""
        self.logger.info("开始varVAMP工作流")
        self.logger.info(f"输入: {self.args.input}")
        self.logger.info(f"输出目录: {self.args.output_dir}")
        self.logger.info(f"模式: {self.args.mode}")
        self.logger.info(f"线程数: {self.args.threads}")
        
        # 创建输出目录
        output_dir = Path(self.args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查必要工具
        tools = ["mafft", "vsearch", "varvamp"]
        if self.args.database:
            tools.extend(["makeblastdb", "blastn"])
        
        for tool in tools:
            if not self.check_tool(tool):
                self.logger.error(f"工具 {tool} 未安装或不在PATH中")
                return False
        
        # 准备输入
        input_file = self.prepare_input(
            self.args.input, 
            output_dir, 
            self.args.min_length, 
            self.args.max_length
        )
        if not input_file:
            return False
        
        # 比对序列（如果需要）
        if not self.args.no_align:
            alignment_file = output_dir / "aligned_sequences.fasta"
            if not self.align_sequences(input_file, alignment_file):
                return False
        else:
            alignment_file = input_file
            self.logger.info(f"跳过比对步骤，使用现有比对文件: {alignment_file}")
        
        # 聚类（如果需要）
        if not self.args.no_cluster:
            cluster_dir = self.cluster_sequences(alignment_file, output_dir, self.args.identity)
            if cluster_dir:
                self.logger.info(f"聚类已完成，结果保存在: {cluster_dir}")
                self.logger.info("注意: 本脚本尚未实现针对每个聚类的引物设计")
                self.logger.info("您可能需要手动对每个聚类运行varvamp")
            else:
                self.logger.warning("聚类步骤失败，继续执行后续步骤")
        else:
            self.logger.info("跳过聚类步骤")
        
        # 创建BLAST数据库（如果需要）
        blast_db = None
        if self.args.database:
            blast_db = self.create_blast_db(self.args.database, output_dir)
            if not blast_db:
                self.logger.warning("BLAST数据库创建失败，继续执行但不使用BLAST检查")
        
        # 运行varvamp
        modes = []
        if self.args.mode == "all":
            modes = ["single", "tiled", "qpcr"]
        else:
            modes = [self.args.mode]
        
        results = {}
        for mode in modes:
            results[mode] = self.run_varvamp(mode, alignment_file, output_dir, blast_db)
        
        # 汇总结果
        self.logger.info("工作流完成!")
        for mode, success in results.items():
            status = "成功" if success else "失败"
            self.logger.info(f"{mode} 模式: {status}")
        
        self.logger.info(f"结果保存在: {output_dir}")
        return all(results.values())

def main():
    """主函数"""
    workflow = VarVAMPWorkflow()
    success = workflow.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
