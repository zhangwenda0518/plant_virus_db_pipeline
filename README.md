# Plant Virus DB Pipeline

基于 NCBI / KEGG / ICTV 三大数据源的植物病毒数据库构建与宿主分类分析系统。

## 目录构成

| 子目录 | 用途 | 入口 |
|--------|------|------|
| `get_plant_virus_data_pipeline/` | 建库流水线 (A-G 七阶段) | `bash run_all.sh -e email@example.com` |
| `host_classify/` | 宿主分类下游分析 (C5-C9) | 见子目录 README |
| `build_virus_db/` | 辅助建库工具 | — |

## 数据流

```
NCBI/KEGG/ICTV 原始数据
        │
        ▼
get_plant_virus_data_pipeline/       # run_all.sh 一键构建
  A 元数据整合 → B ICTV拆分 → C 宿主分类+清洗
  → D 序列获取 → E 元数据完善 → F 分类去冗余 → G 聚类评估
        │
        ▼
  classified_clean/                  # C4 清洗后的多类别宿主数据
        │
        ▼
host_classify/                       # 下游分析
  1 跨界重叠 → 2 可视化 → 3 概率表+置信度
  → 4 跨物种 → 5 contig分类 → 6/7 审计工具
```

## 快速开始

```bash
# 1. 建库
cd get_plant_virus_data_pipeline/
bash run_all.sh -e your@email.com

# 2. 下游分析 (需要 classified_clean/ 输出)
cd ../host_classify/
python 1_cross_kingdom_overlap.py -i ../../classified_clean/ -o cross_analysis/ -s Plant
python 2_plot_overlap.py -i ../../classified_clean/ -o cross_analysis/
python 3_host_probability.py -i ../../classified_clean/ -o cross_analysis/
python 5_classify_contigs.py -i contigs.tsv -f contigs.fasta --prob_dir cross_analysis/ -o classified/
```

## 详细文档

- 建库流程：[get_plant_virus_data_pipeline/README.md](get_plant_virus_data_pipeline/README.md)
- 宿主分析：[host_classify/README.md](host_classify/README.md)
