# Plant Virus DB Pipeline

基于 NCBI GenBank 与 ICTV VMR MSL41 的植物病毒参考数据库构建、可视化与引物设计系统。

Live: https://zhangwenda0518.github.io/plant_virus_db_pipeline/

## 目录构成

| 子目录 | 用途 |
|--------|------|
| `get_plant_virus_data_pipeline/` | 建库流水线 (A-G 阶段) |
| `host_classify/` | 宿主分类下游分析 |
| `primer_design/` | 批量引物设计 (PCR + qPCR + CRISPR + 简并) |
| `virus_explorer/` | Dash 交互式可视化应用 (部署于 Render) |
| `docs/` | GitHub Pages 网站 (Dashboard + Table + Download + Submit) |

## 数据流

```
NCBI GenBank + ICTV VMR MSL41
        │
        ▼ get_plant_virus_data_pipeline/ (run_all.sh)
  A 元数据整合 → B ICTV拆分 → C 宿主分类+清洗
  → D 序列获取 → E 元数据完善 → F 分类去冗余 → G 聚类评估
        │
        ├── final.cluster.ref.fasta / final.cluster.ref_info.tsv
        │       │
        │       ├── docs/data/ → GitHub Pages 网站
        │       ├── virus_explorer/ → Render Dash 交互可视化
        │       └── primer_design/ → 批量引物设计流水线
        │
        └── classes_clean/ + All_Classified_Virus_Info.tsv
                │
                └── host_classify/ → 宿主概率表、contig 分类、交叉分析
```

## 网站功能

| 页面 | 功能 |
|------|------|
| **Dashboard** | Plant_Virus_Info.full.tsv 全量数据统计 (图表) |
| **Segmented** | 分节段病毒表 (Final Ref / Full DB 切换, 勾选导出) |
| **Non‑Segmented** | 非分节段病毒表 (同上) |
| **Explorer** | 筛选器 → Render Dash 应用 (时空分布 + CP变异分析) |
| **Submit** | 新病毒提交 (GitHub Issue) |
| **Download** | final.cluster.ref.fasta / info.tsv 下载 |

## 快速开始

```bash
# 1. 建库
cd get_plant_virus_data_pipeline/
bash run_all.sh -e your@email.com

# 2. 下游分析
cd ../host_classify/
python 3_host_probability.py -i ../../classified_clean/ -o cross_analysis/
python 5_classify_contigs.py -i contigs.tsv -f contigs.fasta --prob_dir cross_analysis/ -o classified/

# 3. 引物设计
cd ../primer_design/
python batch_primer_pipeline.py --fasta G-cluster/final.cluster.ref.fasta \
    --info G-cluster/final.cluster.ref_info.tsv -o primers/ -t 40

# 4. 网站部署
cp G-cluster/final.cluster.ref_info.tsv docs/data/
git add docs/data/ && git commit -m "Update data" && git push
# GitHub Pages auto-deploy from docs/ folder
```

## 引物设计类型

| 类型 | 工具 | 用途 |
|------|------|------|
| PCR | AutoPVPrimer | 常规检测引物 (250-1000bp) |
| qPCR | AutoPVPrimer | 荧光定量引物 (100-250bp) |
| Degenerate | varVAMP | 简并引物 (覆盖株系变异) |
| CRISPR_Cas12a | PAM扫描+RPA | 等温扩增CRISPR检测 |
| Delivery Verify | 基因组覆盖 | CRISPR递送验证引物 |

## 详细文档

- 建库流程：[get_plant_virus_data_pipeline/README.md](get_plant_virus_data_pipeline/README.md)
- 宿主分析：[host_classify/README.md](host_classify/README.md)
