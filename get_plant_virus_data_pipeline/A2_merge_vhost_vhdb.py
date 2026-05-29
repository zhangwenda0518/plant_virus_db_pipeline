#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【VirusHostDB & NCBI VHostMetadata 混合特征合并工具】

设计说明：
此脚本用于生物信息学宏病毒组分析中，合并来自 VirusHostDB 和 NCBI 的元数据表。
采用高级的 "特征混合继承 (Feature Blending)" 策略：
  1. 权威覆盖：遇到共有序列，完全采用 VirusHostDB 提供的最新宿主和病毒分类信息。
  2. 版本继承：提取 NCBI 中该序列的版本号 (如 .1, .2) 并赋予 VirusHostDB 的记录。
  3. 智能补全：如果是一条仅存在于 VirusHostDB 的全新序列，自动为其追加 ".1" 版本号。

依赖环境：
  - Python 3.7+
  - Polars (pip install polars)
"""

import os
import sys
import time
import argparse

# ==========================================
# 依赖环境检查
# ==========================================
try:
    import polars as pl
except ImportError:
    print("❌ 缺少必要的依赖库 'polars'。")
    print("💡 请运行以下命令安装: pip install polars")
    sys.exit(1)


def process_and_merge(vhdb_file: str, ncbi_file: str, output_file: str):
    print(f"🚀 启动【VHDB优先 + 继承NCBI版本号 + 全景统计】混合合并流程")
    print(f"   👑 基础数据优先源 (VHDB): {vhdb_file}")
    print(f"   🏷️ 版本号继承源 (NCBI):   {ncbi_file}")
    print(f"   💾 目标输出文件:          {output_file}\n")
    
    start_time = time.time()
    expected_cols = ["Accession", "Virus_Name", "Taxid", "Host", "Host_Taxid"]

    # ==========================================
    # 1. 提取 NCBI (VHostMetadata)
    # ==========================================
    print(f"📥 [1/4] 正在解析基准库 {ncbi_file} ...")
    try:
        df_vhost_raw = pl.read_csv(
            ncbi_file, separator="\t", infer_schema_length=0, quote_char=None
        )
        df_vhost = df_vhost_raw.select([pl.col(c) for c in expected_cols])
        df_vhost = df_vhost.filter(
            pl.col("Accession").is_not_null() & (pl.col("Accession") != "")
        )
        
        # 剥离版本号，生成比对基准列
        df_vhost = df_vhost.with_columns(
            pl.col("Accession").str.replace(r"\.\d+$", "").alias("Acc_NoVersion"),
            pl.lit("NCBI").alias("Source")
        )
        df_vhost = df_vhost.unique(subset=["Acc_NoVersion"], maintain_order=True, keep="first")
        df_vhost = df_vhost.cast(pl.Utf8)

        # 统计独立信息
        vhost_count = df_vhost.height
        vhost_v_tax = df_vhost["Taxid"].n_unique()
        vhost_h_tax = df_vhost["Host_Taxid"].n_unique()

        print(f"   📊 [NCBI 库独立统计]:")
        print(f"      - 现有有效序列 (Accession): {vhost_count:,}")
        print(f"      - 包含唯一病毒 Taxid:       {vhost_v_tax:,}")
        print(f"      - 包含唯一宿主 Taxid:       {vhost_h_tax:,}\n")

        # 制作版本号映射字典
        df_ncbi_map = df_vhost.select([
            pl.col("Acc_NoVersion"),
            pl.col("Accession").alias("Accession_ncbi_version")
        ])

    except Exception as e:
        print(f"❌ 读取 {ncbi_file} 失败: {e}")
        sys.exit(1)


    # ==========================================
    # 2. 解析 VHDB 并动态继承版本号
    # ==========================================
    print(f"📥 [2/4] 正在解析高优库 {vhdb_file} ...")
    try:
        df_vhdb_raw = pl.read_csv(
            vhdb_file, separator="\t", infer_schema_length=0, quote_char=None
        )
        df_vhdb = df_vhdb_raw.select([
            pl.col("refseq id").alias("Accession"),
            pl.col("virus name").alias("Virus_Name"),
            pl.col("virus tax id").alias("Taxid"),
            pl.col("host name").alias("Host"),
            pl.col("host tax id").alias("Host_Taxid")
        ])

        # 拆分、爆破多序列号
        df_vhdb = (
            df_vhdb.with_columns(pl.col("Accession").str.split(","))
            .explode("Accession")
            .with_columns(pl.col("Accession").str.strip_chars())
        )
        df_vhdb = df_vhdb.filter(
            pl.col("Accession").is_not_null() & (pl.col("Accession") != "") & (pl.col("Accession") != "-")
        )
        
        # 剥离版本号作为 Acc_NoVersion
        df_vhdb = df_vhdb.with_columns(
            pl.col("Accession").str.replace(r"\.\d+$", "").alias("Acc_NoVersion"),
            pl.lit("VHDB").alias("Source")
        )
        df_vhdb = df_vhdb.unique(subset=["Acc_NoVersion"], maintain_order=True, keep="first")
        df_vhdb = df_vhdb.cast(pl.Utf8)

        # 统计独立信息
        vhdb_count = df_vhdb.height
        vhdb_v_tax = df_vhdb["Taxid"].n_unique()
        vhdb_h_tax = df_vhdb["Host_Taxid"].n_unique()

        print(f"   📊 [VirusHostDB 独立统计]:")
        print(f"      - 解析出有效序列 (Accession): {vhdb_count:,}")
        print(f"      - 包含唯一病毒 Taxid:       {vhdb_v_tax:,}")
        print(f"      - 包含唯一宿主 Taxid:       {vhdb_h_tax:,}\n")

        # 将 NCBI 的权威版本号 Left Join 贴到 VHDB 身上
        df_vhdb = df_vhdb.join(df_ncbi_map, on="Acc_NoVersion", how="left")
        
        # 判定：继承版本号 或 追加 ".1"
        df_vhdb = df_vhdb.with_columns(
            pl.when(pl.col("Accession_ncbi_version").is_not_null())
            .then(pl.col("Accession_ncbi_version"))
            .otherwise(pl.col("Acc_NoVersion") + ".1")
            .alias("Accession")
        ).drop("Accession_ncbi_version")

    except Exception as e:
        print(f"❌ 读取 {vhdb_file} 失败: {e}")
        sys.exit(1)


    # ==========================================
    # 3. 终极合并去重
    # ==========================================
    print("🔗 [3/4] 正在执行混合合并并剔除冗余...")
    
    # VHDB 在前，NCBI 在后
    df_merged = pl.concat([df_vhdb, df_vhost])
    
    # 根据无版本号 Accession 去重，保留排在前面的 VHDB 记录
    df_final = df_merged.unique(subset=["Acc_NoVersion"], maintain_order=True, keep="first")

    # 最终汇总统计
    final_count = df_final.height
    final_v_tax = df_final["Taxid"].n_unique()
    final_h_tax = df_final["Host_Taxid"].n_unique()

    # 增量与覆盖逻辑计算
    new_added = final_count - vhost_count 
    overwritten = vhdb_count - new_added

    print(f"   📈 [最终合并结果全景统计]:")
    print(f"      - 🟢 最终非冗余序列总数: {final_count:,}")
    print(f"        (其中从 VirusHostDB 成功纯新增了 {new_added:,} 条新序列，并自动追加了 .1)")
    print(f"        (另有 {overwritten:,} 条共有序列的元数据，已采用 VirusHostDB 的最新记录无缝覆盖)")
    print(f"      - 🦠 最终覆盖病毒 Taxid: {final_v_tax:,}")
    print(f"      - 🐄 最终覆盖宿主 Taxid: {final_h_tax:,}\n")


    # ==========================================
    # 4. 清理并写入输出文件
    # ==========================================
    print(f"💾 [4/4] 正在将最终矩阵写入: {output_file} ...")
    
    # 创建输出目录（如果不存在）
    out_dir = os.path.dirname(os.path.abspath(output_file))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
        print(f"   📁 自动创建了输出目录: {out_dir}")
    
    # 丢弃辅助列，恢复 5 列纯净格式
    df_final = df_final.select(expected_cols)
    df_final.write_csv(output_file, separator="\t", include_header=True, quote_style="never")
    
    print(f"✅ 处理完成！总耗时: {time.time() - start_time:.2f} 秒")
    print(f"📄 结果文件位于: {os.path.abspath(output_file)}\n")


def main():
    # 自定义帮助文档的格式，使其支持多行文本和更美观的排版
    parser = argparse.ArgumentParser(
        description="🦠【VirusHostDB & NCBI VHostMetadata 混合特征合并工具】🦠\n"
                    "----------------------------------------------------------\n"
                    "本工具用于合并两份病毒-宿主元数据表。在遇到相同序列号(无视版本号)时：\n"
                    "  [1] 优先采用 VirusHostDB 中的病毒分类与宿主信息。\n"
                    "  [2] 自动继承 NCBI 中该序列的标准版本号 (如 .1, .2)。\n"
                    "  [3] 若序列仅存在于 VirusHostDB 中，则自动为其追加 '.1'。",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="【使用示例】:\n"
               "  1. 基础合并 (同目录下文件):\n"
               "     python merge_hybrid_stats.py --vhdb virushostdb.tsv --ncbi VHostMetadata.tsv -o Merged.tsv\n\n"
               "  2. 指定完整输入输出路径 (系统会自动创建输出文件夹):\n"
               "     python merge_hybrid_stats.py --vhdb raw_data/virushostdb.tsv --ncbi raw_data/VHost.tsv -o results/Final_VHost.tsv\n"
    )
    
    # 输入参数设定
    parser.add_argument(
        "--vhdb", 
        required=True, 
        metavar="FILE",
        help="[必填] 高优先级元数据源 (通常为 virushostdb.tsv)\n该表的数据将被优先采纳。"
    )
    parser.add_argument(
        "--ncbi", 
        required=True, 
        metavar="FILE",
        help="[必填] 版本号基准补充源 (通常为 VHostMetadata.tsv)\n提供序列的版本号基准及补充数据。"
    )
    parser.add_argument(
        "-o", "--output", 
        default="VHostMetadata_Merged.tsv", 
        metavar="FILE",
        help="[可选] 合并去重后的最终输出文件路径。\n(默认: VHostMetadata_Merged.tsv)"
    )
    
    # 如果用户没有输入任何参数，直接显示帮助文档
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
        
    args = parser.parse_args()
    
    # 运行前检查输入文件是否存在
    if not os.path.exists(args.vhdb):
        print(f"❌ 错误: 找不到高优文件: {args.vhdb}")
        sys.exit(1)
    if not os.path.exists(args.ncbi):
        print(f"❌ 错误: 找不到基准文件: {args.ncbi}")
        sys.exit(1)
        
    process_and_merge(args.vhdb, args.ncbi, args.output)

if __name__ == "__main__":
    main()
