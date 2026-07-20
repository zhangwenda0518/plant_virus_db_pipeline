# docs — 静态网站 + 数据文件

> Nginx 直接服务的静态内容：门户首页、参考数据库、TE 数据库、症状图库、基因图谱。
> 
> ⚠️ 此目录是 **git 开发源**，与服务器生产环境 (`/opt/plant_virus_db/plant_virus_db_pipeline/docs/`) 已分叉，修改前务必确认目标。

**路由**:
- `/` → `index.html`（统一门户，12 模块入口卡片）
- `/reference/` → 参考数据库（reference_index.html + segmented/nonsegmented/submit/download/photos.html）
- `/te/` → TE & EVE 转座子数据库（te/index.html + data/）
- `/photos/` → 症状图库（photos.html 引用 data/*_gallery.json）
- `/genes/` → 基因图谱（服务器上有 genes/ 目录，本地待同步）

## 文件结构

```
docs/
├── index.html                  # 统一门户首页（/）
├── reference_index.html        # 参考数据库首页（/reference/）
├── segmented.html             # 节段病毒浏览
├── nonsegmented.html          # 非节段病毒浏览
├── submit.html                # 数据提交页
├── download.html              # 数据下载页
├── photos.html                # 症状图库（/photos/）
├── explorer.html              # （legacy）旧版 Explorer 入口
├── table.js                   # 交互表格 JS（DataTables）
├── i18n.js                    # 国际化 JS
├── README.md                  # 本文档
│
├── data/                      # ★ 核心参考数据 + 图片
│   ├── Plant_Virus_Full.fasta      # 全量序列（377 MB）
│   ├── Plant_Virus_Full.Info.tsv   # 全量元数据
│   ├── Plant_Virus_Ref.fasta       # 非冗余参考序列（31 MB）
│   ├── Plant_Virus_Ref.Info.tsv    # 参考元数据
│   ├── Plant_Virus.complete_ref.fasta       # 完整参考序列
│   ├── Plant_Virus.complete_ref_info.tsv    # 完整参考元数据
│   ├── virus_genes_cov.tsv          # 基因覆盖度表
│   ├── complete_acc.txt             # 完整序列 accession 列表
│   ├── DATA_VERSION                 # 数据版本号
│   ├── *_gallery.json               # 症状图库元数据（book/dpv/eppo/openi/unified）
│   ├── symptom_table.json           # 症状表
│   └── book_images/                 # 书籍截图（~2500 张）
│
├── literature/                 # 文献追踪数据（模块归属：7.literature_tracker/）
│   ├── index.html + app.js + styles.css   # 文献 SPA
│   ├── data/                   # 结构化文献数据
│   ├── monthly/                # 月度文献报告
│   └── weekly/                 # 周度文献报告
│
├── primers/                    # 引物 JSON 数据（模块归属：4.virus_primer/）
│   ├── index.json              # 引物索引
│   ├── stats.json              # 统计信息
│   └── *.json                  # 7,193 个物种的引物数据
│
└── te/                         # TE & EVE 转座子数据库（/te/）
    ├── index.html              # Chart.js 可视化页面
    ├── ltr_clusters.tsv        # LTR 聚类数据
    └── data/                   # 参考序列 FASTA（15 个文件，~50 MB）
```

## 数据文件（统一命名）

所有核心数据文件以 `Plant_Virus_` 为前缀，与 `config.py` 的 `PIPELINE_OUTPUTS` 一致：

| config.py 键 | 文件 | 用途 |
|---|---|---|
| `full_fasta` | `Plant_Virus_Full.fasta` | 全量植物病毒序列 |
| `full_tsv` | `Plant_Virus_Full.Info.tsv` | 全量元数据 |
| `cluster_fasta` | `Plant_Virus_Ref.fasta` | 非冗余参考序列 |
| `cluster_info` | `Plant_Virus_Ref.Info.tsv` | 参考元数据 |
| `complete_fasta` | `Plant_Virus.complete_ref.fasta` | 完整参考序列 |
| `complete_info` | `Plant_Virus.complete_ref_info.tsv` | 完整参考元数据 |
| `gene_cov` | `virus_genes_cov.tsv` | 基因覆盖度 |

## 部署

- 服务器路径：`/opt/plant_virus_db/plant_virus_db_pipeline/docs/`
- Nginx：`location /reference/` → `alias docs/`；`location /te/` → `alias docs/te/`
- `location = /` → `rewrite ^ /reference/index.html last;`
- 数据路径由 `config.py` 统一管理，可通过环境变量 `PVDB_*` 覆盖
