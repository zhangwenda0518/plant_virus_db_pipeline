#!/usr/bin/env python3
"""
Step 0: 从 Plant_clean.tsv 提取需要设计引物的植物病毒物种列表
========================================================================
目的: 整理项目已有的植物病毒数据，生成需要设计引物的病毒物种清单。

逻辑:
  1. Plant_clean.tsv 是本项目清理过的植物病毒宿主关系数据
  2. 从中提取所有唯一的植物病毒物种名称
  3. 优先选择:
     - 有完整分类学信息 (ICTV/NCBI) 的病毒
     - 经济上重要的植物病毒 (如 烟草花叶病毒属、马铃薯Y病毒属、双生病毒科等)
  4. 输出病毒物种列表 + 优先级标注
"""

import polars as pl
from pathlib import Path
from collections import Counter

# ______________________________________________________________________
# 配置
PLANT_CLEAN = Path("D:/桌面/C-host_classify/Plant_clean.tsv")
OUT_SPECIES_LIST = Path("D:/桌面/C-host_classify/引物设计/plant_virus_species.tsv")
OUT_PRIORITY_LIST = Path("D:/桌面/C-host_classify/引物设计/plant_virus_priority.tsv")

# 经济上重要的植物病毒科/属 (用于标记优先级)
HIGH_PRIORITY_FAMILIES = {
    "Potyviridae",    # 马铃薯Y病毒科 — 最大的植物病毒科
    "Geminiviridae",  # 双生病毒科 — 全球粮食安全威胁
    "Bromoviridae",   # 雀麦花叶病毒科
    "Tombusviridae",  # 番茄丛矮病毒科
    "Virgaviridae",   # 烟草花叶病毒科
    "Closteroviridae",# 长线形病毒科
    "Luteoviridae",   # 黄症病毒科
    "Betaflexiviridae",
    "Secoviridae",    # 豇豆花叶病毒科
    "Caulimoviridae", # 花椰菜花叶病毒科
    "Tospoviridae",   # 番茄斑萎病毒科
    "Nanoviridae",    # 矮化病毒科
}

HIGH_PRIORITY_GENERA = {
    "Tobamovirus", "Potyvirus", "Begomovirus", "Cucumovirus",
    "Tospovirus", "Closterovirus", "Luteovirus", "Polerovirus",
    "Nepovirus", "Comovirus", "Carlavirus", "Potexvirus",
    "Fijivirus", "Tenuivirus", "Tobravirus", "Ilarvirus",
    "Nucleorhabdovirus", "Cytorhabdovirus", "Dichorhavirus",
}


def load_and_inspect():
    """加载 Plant_clean.tsv 并检查其结构"""
    print("=" * 70)
    print("Step 0: 加载植物病毒数据")
    print("=" * 70)

    df = pl.read_csv(
        PLANT_CLEAN,
        separator='\t',
        ignore_errors=True,
        infer_schema_length=10000
    )

    print(f"总行数: {len(df):,}")
    print(f"列名: {df.columns}")
    print()

    # 检查关键列
    key_cols = []
    for col in df.columns:
        non_null = df[col].null_count()
        if non_null < len(df):
            key_cols.append(col)
            print(f"  {col}: {len(df) - non_null:,} 非空值, 示例: {df[col].drop_nulls()[:3].to_list()}")

    return df, key_cols


def extract_virus_species(df: pl.DataFrame):
    """从数据中提取唯一植物病毒物种"""
    species_count = Counter()

    # 策略: 检查多个可能的物种列
    species_candidates = [
        "Species_ICTV", "Species_NCBI", "VirusSpecies",
        "Species", "Virus_Species", "virus_species",
        "Virus_name", "virus_name"
    ]

    species_col = None
    for col in species_candidates:
        if col in df.columns:
            species_col = col
            break

    if species_col is None:
        print("  ⚠ 未找到标准物种列，尝试从 Virus 相关列推断...")
        # 尝试使用 VirusFamily + VirusGenus 组合
        if "Genus" in df.columns:
            virus_genera = df["Genus"].drop_nulls().unique().to_list()
            print(f"  找到 {len(virus_genera)} 个病毒属")
            return None, virus_genera

    if species_col:
        viruses = df[species_col].drop_nulls()
        for v in viruses.to_list():
            species_count[str(v).strip()] += 1
        print(f"\n唯一病毒物种数: {len(species_count)}")
        print(f"Top 20 高频物种:")
        for sp, cnt in species_count.most_common(20):
            print(f"  {sp}: {cnt} 条记录")

    return species_count, species_col


def assign_priority(species_count: Counter):
    """根据科/属信息标记引物设计优先级"""
    # 读取 Plant.tsv 获取科属信息
    plant_raw = Path("D:/桌面/C-host_classify/Plant.tsv")
    priority_map = {}

    if plant_raw.exists():
        df_plant = pl.read_csv(plant_raw, separator='\t', ignore_errors=True)

        # 尝试获取物种→科→属映射
        for row in df_plant.iter_rows(named=True):
            sp = str(row.get("Species_NCBI", row.get("Species_ICTV", ""))).strip()
            family = str(row.get("Family", "")).strip()
            genus = str(row.get("Genus", "")).strip()

            if not sp or sp not in species_count:
                continue

            level = "LOW"
            reason = ""

            if family in HIGH_PRIORITY_FAMILIES:
                level = "HIGH"
                reason = f"重要科: {family}"
            if genus in HIGH_PRIORITY_GENERA:
                level = "HIGH"
                reason = f"重要属: {genus}"

            if sp not in priority_map or level == "HIGH":
                priority_map[sp] = {
                    "Family": family,
                    "Genus": genus,
                    "Priority": level,
                    "Reason": reason,
                    "Count": species_count.get(sp, 0)
                }

    # 补充未匹配的物种
    for sp, cnt in species_count.items():
        if sp not in priority_map:
            priority_map[sp] = {
                "Family": "", "Genus": "",
                "Priority": "MEDIUM",
                "Reason": "无科属信息",
                "Count": cnt
            }

    return priority_map


def write_output(species_count: Counter, priority_map: dict):
    """写入输出文件"""
    # 物种列表
    rows = []
    for sp, cnt in species_count.most_common():
        pinfo = priority_map.get(sp, {})
        rows.append({
            "Species": sp,
            "Record_Count": cnt,
            "Priority": pinfo.get("Priority", "MEDIUM"),
            "Family": pinfo.get("Family", ""),
            "Genus": pinfo.get("Genus", ""),
            "Priority_Reason": pinfo.get("Reason", "")
        })

    df_out = pl.DataFrame(rows)
    df_out.write_csv(OUT_SPECIES_LIST, separator='\t')
    print(f"\n物种列表 → {OUT_SPECIES_LIST} ({len(df_out)} 个物种)")

    # 按优先级分组统计
    for level in ["HIGH", "MEDIUM", "LOW"]:
        subset = df_out.filter(pl.col("Priority") == level)
        print(f"  {level}: {len(subset)} 个物种")

    # 高优先级物种单独输出
    high = df_out.filter(pl.col("Priority") == "HIGH")
    high.write_csv(OUT_PRIORITY_LIST, separator='\t')
    print(f"高优先级物种 → {OUT_PRIORITY_LIST} ({len(high)} 个)")

    return df_out


def main():
    df, key_cols = load_and_inspect()
    species_count, species_col = extract_virus_species(df)

    if species_count is None:
        print("\n  ⚠ 无法提取物种信息，请检查数据格式")
        return None

    priority_map = assign_priority(species_count)
    result = write_output(species_count, priority_map)

    print("\n" + "=" * 70)
    print("Step 0 完成！下一步:")
    print("  1. step1_fetch_genomes.py -- 从 NCBI 下载病毒基因组序列")
    print("  2. batch_primer_pipeline.py -- 批量设计引物")
    print("=" * 70)

    return result


if __name__ == "__main__":
    main()
