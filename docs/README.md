# docs — 静态网站 + 数据文件

> Nginx 直接服务的静态内容：门户首页 (12 模块入口卡片)、参考数据库 (6 子页)、TE 数据库、症状图库、基因图谱、PV-miRNA、文献浏览。

## 路由覆盖

| 路由 | 目标文件 | 说明 |
|:-----|:-----|:-----|
| `/` | `index.html` | 统一门户, 12 模块入口卡片 |
| `/reference/` | `reference_index.html` | 参考数据库 (6 子页: segmented/nonsegmented/submit/download/explorer/photos) |
| `/te/` | `te/index.html` | TE & EVE 转座子数据库 |
| `/photos/` | `photos.html` | 症状图库 (Gallery/Dashboard/Table 三视图) |
| `/genes/` | `genes/index.html` | 基因图谱 (NLR/sRNA/UPS/miRNA 四标签) |
| `/pamirdb/` | 反向代理 :8000 | PV-miRNA 预测工作台 (非静态) |
| `/literature/` | 反向代理 :5003 | 文献追踪 (非静态, Flask 提供) |

## 文件结构

```
docs/
├── index.html                  # 统一门户首页 (/)
├── reference_index.html        # 参考数据库首页 (/reference/)
├── segmented.html             # 节段病毒浏览
├── nonsegmented.html          # 非节段病毒浏览
├── submit.html                # 数据提交页
├── download.html              # 数据下载页
├── photos.html                # 症状图库 (/photos/)
├── explorer.html              # (legacy) 旧版 Explorer 入口
├── table.js                   # 交互表格 JS (DataTables)
├── i18n.js                    # 国际化 JS (PVDB_i18n, 中英双语)
├── README.md                  # 本文档
│
├── data/                      # 核心参考数据 + 图片
│   ├── Plant_Virus_Full.fasta      # 全量序列 (377 MB, gitignore)
│   ├── Plant_Virus_Full.Info.tsv   # 全量元数据 (gitignore)
│   ├── Plant_Virus_Ref.fasta       # 非冗余参考序列 (31 MB, gitignore)
│   ├── Plant_Virus_Ref.Info.tsv    # 参考元数据
│   ├── Plant_Virus.complete_ref.fasta       # 完整参考序列 (gitignore)
│   ├── Plant_Virus.complete_ref_info.tsv    # 完整参考元数据
│   ├── virus_genes_cov.tsv          # 基因覆盖度表
│   ├── complete_acc.txt             # 完整序列 accession 列表
│   ├── DATA_VERSION                 # 数据版本号
│   ├── name_mapping.tsv             # ICTV/NCBI 名称映射 (45,176 条)
│   ├── *_gallery.json               # 症状图库元数据 (book/dpv/eppo/unified)
│   ├── symptom_table.json           # 症状表
│   ├── book_images/                 # 书籍截图
│   ├── dpv_images/                  # DPV 图版
│   └── pdf_images/                  # PDF 提取图片
│
├── literature/                 # 文献追踪静态数据 (模块归属: 7.literature_tracker/)
│   ├── index.html + app.js + styles.css   # 文献 SPA
│   ├── data/                   # 结构化文献数据
│   ├── monthly/                # 月度文献报告
│   └── weekly/                 # 周度文献报告
│
├── primers/                    # 引物 JSON 数据 (模块归属: 4.virus_primer/)
│   ├── index.json              # 引物索引
│   ├── stats.json              # 统计信息
│   └── species/                # 7,193 个物种的引物数据
│
└── te/                         # TE & EVE 转座子数据库 (/te/)
    ├── index.html              # Chart.js 可视化页面
    ├── archive/                # 归档
    └── data/                   # 6 个 FASTA 文件
        ├── plant_ncbi_eve.fa
        ├── plant_rvdb.ENRV.fa
        ├── plant_rvdb.EX.fa
        ├── plant_envr_clean.fa (95% 聚类)
        ├── plant_ex_clean.fa
        └── plant_te_clean.fa   (10,537 LTR RT)
```

## 数据文件 (统一命名)

所有核心数据文件以 `Plant_Virus_` 为前缀，与 `config.py` 的 `PIPELINE_OUTPUTS` 一致：

| config.py 键 | 文件 | 用途 | 大小 |
|:---|:-----|:-----|:----:|
| `full_fasta` | `Plant_Virus_Full.fasta` | 全量植物病毒序列 | 377 MB |
| `full_tsv` | `Plant_Virus_Full.Info.tsv` | 全量元数据 (~199K 条) | — |
| `cluster_fasta` | `Plant_Virus_Ref.fasta` | 非冗余参考序列 | 31 MB |
| `cluster_info` | `Plant_Virus_Ref.Info.tsv` | 参考元数据 (~8,465 条) | — |
| `complete_fasta` | `Plant_Virus.complete_ref.fasta` | 完整参考序列 | — |
| `complete_info` | `Plant_Virus.complete_ref_info.tsv` | 完整参考元数据 | — |
| `gene_cov` | `virus_genes_cov.tsv` | 基因覆盖度 | — |

## 关键 JS 文件

| 文件 | 功能 |
|:-----|:-----|
| `table.js` | 通用 DataTables 交互表格, 支持排序/搜索/分页/CSV 导出 |
| `i18n.js` | 中英双语切换 (PVDB_i18n), 版本 `?v=3` 缓存破坏 |

## 部署

- **服务器路径**: `/opt/plant_virus_db/plant_virus_db_pipeline/docs/`
- **Nginx**: 主配置 `plant-virus.conf`, 各路由见上表
- **数据路径**: 由 `config.py` 统一管理, 可通过环境变量 `PVDB_*` 覆盖
- **缓存策略**: `/reference/data/` → `expires 1h, Cache-Control: public, immutable`

## 注意

- 此目录是 git 开发源, 与服务器生产环境 (`/opt/plant_virus_db/plant_virus_db_pipeline/docs/`) 可能存在差异
- 大文件 (FASTA/TSV gz) 已加入 `.gitignore`, 需手动同步
- Nginx 静态页修改后需 `nginx -s reload`
