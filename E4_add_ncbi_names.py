#!/usr/bin/env python3
import pandas as pd
from Bio import Entrez
import time
import os
import argparse

def load_local_taxonomy(names_dmp_path):
    """解析本地 names.dmp 文件"""
    local_tax_dict = {}
    if not os.path.exists(names_dmp_path):
        print(f"⚠️ 警告: 未找到本地文件 {names_dmp_path}，将全部依赖在线查询。")
        return local_tax_dict

    print(f"⏳ 正在解析本地库 {names_dmp_path}...")
    with open(names_dmp_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4 and parts[3] == "scientific name":
                # 使用字符串存储 taxid 以确保匹配稳定性
                local_tax_dict[str(parts[0])] = parts[1]
                
    print(f"✅ 本地库解析完成。")
    return local_tax_dict

def get_ncbi_name_online(taxid):
    """在线 API 获取缺失名"""
    try:
        handle = Entrez.efetch(db="taxonomy", id=str(taxid), retmode="xml")
        records = Entrez.read(handle)
        return records[0].get("ScientificName", pd.NA)
    except Exception as e:
        print(f"  ❌ 在线获取 Taxid {taxid} 失败: {e}")
        return pd.NA

def main():
    parser = argparse.ArgumentParser(description="生信工具：根据 Taxid 补充 NCBI 物种名")
    
    # -i 是必需的，-o 改为可选
    parser.add_argument("-i", "--input", required=True, help="输入的 TSV 文件路径")
    parser.add_argument("-o", "--output", help="输出的 TSV 文件路径 (如果不指定，将直接修改原文件)")
    parser.add_argument("-e", "--email", required=True, help="NCBI 查询邮箱")
    parser.add_argument("-n", "--names_dmp", default="names.dmp", help="本地 names.dmp 路径")
    
    args = parser.parse_args()
    Entrez.email = args.email
    
    # 确定最终保存路径
    output_path = args.output if args.output else args.input

    print("="*40)
    print(f"模式: {'覆盖原文件' if not args.output else '生成新文件'}")
    print(f"目标文件: {output_path}")
    print("="*40)

    # 1. 加载本地数据
    local_tax_dict = load_local_taxonomy(args.names_dmp)

    # 2. 读取表格
    df = pd.read_csv(args.input, sep="\t")

    # 统一列名修改
    # 将 taxid 改为 Taxid
    if 'taxid' in df.columns:
        df.rename(columns={'taxid': 'Taxid'}, inplace=True)
    
    # 将 Species 改为 Species_ICTV
    if 'Species' in df.columns:
        df.rename(columns={'Species': 'Species_ICTV'}, inplace=True)

    if 'Taxid' not in df.columns:
        print("❌ 错误：文件中未找到 'taxid' 或 'Taxid' 列。")
        return

    # 3. 匹配逻辑
    print("\n[1/3] 本地匹配...")
    # 确保 Taxid 列为字符串方便匹配字典
    df['Taxid_str'] = df['Taxid'].astype(str).str.replace(r'\.0$', '', regex=True)
    df['Species_NCBI'] = df['Taxid_str'].map(local_tax_dict)

    print("[2/3] 在线补漏...")
    missing_mask = df['Taxid'].notna() & df['Species_NCBI'].isna()
    missing_ids = df.loc[missing_mask, 'Taxid_str'].unique()

    if len(missing_ids) > 0:
        online_dict = {}
        for i, tid in enumerate(missing_ids):
            print(f"  -> 查询 {tid} ({i+1}/{len(missing_ids)})")
            online_dict[tid] = get_ncbi_name_online(tid)
            time.sleep(0.35)
        df.loc[missing_mask, 'Species_NCBI'] = df.loc[missing_mask, 'Taxid_str'].map(online_dict)

    print("[3/3] 执行填充兜底与格式调整...")
    if 'Species_ICTV' in df.columns:
        df['Species_NCBI'] = df['Species_NCBI'].fillna(df['Species_ICTV'])

    # 4. 调整列顺序：Species_NCBI 在前，Species_ICTV 在后
    cols = list(df.columns)
    # 移除辅助列和目标列
    for c in ['Species_NCBI', 'Taxid_str']:
        if c in cols: cols.remove(c)
    
    # 找到 Species_ICTV 的位置，并把 Species_NCBI 插入到它前面
    if 'Species_ICTV' in cols:
        idx = cols.index('Species_ICTV')
        cols.insert(idx, 'Species_NCBI')
    else:
        cols.append('Species_NCBI')

    df = df[cols]

    # 5. 保存
    df.to_csv(output_path, sep="\t", index=False)
    print(f"\n✨ 处理完毕！结果已保存至: {output_path}")

if __name__ == "__main__":
    main()
