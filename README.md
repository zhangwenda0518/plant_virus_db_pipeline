# Plant Virus Database Platform

> 植物病毒多组学数据库平台 — 12 个功能模块 + 1 个归档模块，部署于阿里云 ECS

**Live**: http://39.106.101.94/

## 目录结构

```
plant_virus_db_pipeline/
├── 1.Prepare_plant_virus_pipeline/   # 七大阶段数据流水线 (A-G: 下载/清洗/聚类/分类)
├── 2.Build_plant_virus_db/           # 17 种下游分类器统一建库工具
├── 3.virus_explorer/                 # Dash 交互式数据浏览器 (/explorer/)
├── 4.virus_primer/                   # 引物设计五阶段流水线 + Web 服务 (/primers/)
├── 5.host_classify/                  # 病毒宿主分类与跨物种分析 (9 步分析)
├── 6.knowledge_rag/                  # AI 知识库 RAG 问答 (DeepSeek + Qdrant) (/knowledge/)
├── 7.literature_tracker/             # PubMed 文献自动追踪 + AI 摘要 + 每日报告 (/literature/)
├── 8.plant-insect/                   # 病毒-媒介-宿主关系库 (VH + WUR 整合) (/vector/)
├── 9.metabuli/                       # 宏基因组分类器 Web + 引物设计 + GenBank 可视化 (/metabuli/)
├── 10.virus_photos/                  # 五源病毒症状照片图库 (2,975 张) (/photos/)
├── 11.antiviral_genes/               # 植物免疫基因图谱 (NLR/sRNA/UPS/miRNA) (/genes/)
├── 12.pamirdb/                       # 植物抗病毒 miRNA 三算法共识预测 (/pamirdb/)
├── 13.onekp_virus/                   # 1KP 转录组病毒 Dashboard (/onekp/)
├── archive/                          # [归档] 历史一次性脚本 + 单病毒详情页 (git 忽略)
├── docs/                             # Nginx 静态站 (/ /reference/ /eve/ /photos/ /genes/ /pamirdb/)
│   ├── index.html                    #   统一门户首页 → /
│   ├── reference_index.html          #   参考数据库首页 → /reference/
│   ├── photos.html                   #   症状图库 → /photos/
│   ├── table.js / i18n.js            #   公用 JS
│   ├── data/                         #   参考序列 FASTA/TSV + 图片
│   ├── literature/                   #   文献追踪静态文件
│   ├── primers/                      #   引物 JSON 数据 (7,193 物种)
│   └── eve/                          #   植物界 EVE 全景 → /eve/
├── config.py                         # 统一项目配置 (PIPELINE_OUTPUTS / PRIMER_OUTPUTS / HOST_OUTPUTS)
├── pixi.toml                         # 跨平台包管理 (conda-forge + PyPI)
├── run_all.sh                        # [已废弃] 2026-07-07 过期副本；流水线入口请用
│                                     #   1.Prepare_plant_virus_pipeline/run_all.sh
└── requirements.txt                  # Python 依赖
```

## 在线服务 (12 个模块)

| 路由 | 服务 | 技术栈 | 说明 |
|---|---|---|---|
| `/` | **统一门户** | 静态 HTML | 12 模块入口卡片 |
| `/reference/` | **参考数据库** | 静态 HTML/JS | 非冗余参考基因组下载/浏览/提交 (6 子页) |
| `/explorer/` | **数据浏览器** | Dash + Plotly | 时空演变/全基因组变异/媒介传播网络/病毒档案/内嵌 AI 助手 |
| `/primers/` | **引物数据库** | Flask | 83,830 对去重引物 / 4,789 物种 / 50 科（103,642 设计去重后，2026-10-16 全库验证合库上线）, REST API, 在线设计, AI 问答 |
| `/vector/` | **媒介-宿主库** | Flask | VH + WUR 三维传播 facet 检索, Sankey/Heatmap/Chord 可视化 |
| `/eve/` | **植物界 EVE 全景** | 静态 HTML | 1,527 基因组 / 284 宿主科, 150,136 个去污染 EVE 位点, 8 视角交互 |
| `/metabuli/` | **宏基因组分类** | Flask | contig 分类 (8 级)/Krona/Sankey/引物设计/GenBank 基因可视化/CDD/BLAST 验证 |
| `/photos/` | **症状图库** | 静态 HTML/JS | EPPO/DPV/Book/PDF 四来源, Gallery/Dashboard/Table 三视图 |
| `/genes/` | **基因图谱** | 静态 HTML/JS | NLR (415)/sRNA (11,780)/UPS (3,996)/miRNA (83,166) 四标签 |
| `/pamirdb/` | **PV-miRNA** | Python HTTP | miRNA 靶标预测: 自研 Smith-Waterman 引擎 + 本地启发式复核层（不调用外部工具，11,006 条预计算预测） |
| `/literature/` | **文献追踪** | Flask | PubMed 自动追踪/手动 4 源检索/AI 摘要/趋势分析 |
| `/knowledge/` | **知识库 RAG** | FastAPI + Qdrant | 60K+ 论文全文 + DPV + viroidDB, DeepSeek V4 Pro 驱动 |

## 数据来源

- NCBI GenBank 全量病毒序列 (~277 GB AllNucleotide)
- ICTV VMR MSL41 病毒分类学权威
- KEGG Virus-Host DB 文献溯源的病毒-宿主关联
- WUR Plant Virus Transmission Database (library.wur.nl)
- U-RVDB v32.0 植物转座子/内源性病毒数据库 (TE 模块 2026-09-23 已下线)
- NCBI PubMed / bioRxiv / Crossref / OpenAlex 文献
- DPV (Descriptions of Plant Viruses) + viroidDB
- EPPO Global Database 病害症状照片
- RefPlantNLR 实验验证免疫受体 (415)
- miRBase + PlantRG + PVsiRNAdb

## 数据量

> 下列数字与 `docs/data/DATA_VERSION` 保持一致；如有出入，**以 `docs/data/DATA_VERSION` 为准**
>（该文件由流水线维护，是唯一的数字来源；本表改为不与其冲突的口径）。

| 类别 | 数值 | 说明 |
|:-----|:----:|:-----|
| 参考基因组 (非冗余) | 9,183 | Plant_Virus_Ref.fasta, 98% ANI 聚类 (DATA_VERSION CLUSTER_COUNT) |
| 病毒物种 | 5,171 | ICTV MSL41 覆盖 (DATA_VERSION SPECIES_COUNT; Species_ICTV 去重实算) |
| 全量序列 | 211,132 | Plant_Virus_Full.fasta (410 MB) (DATA_VERSION RECORDS_PLANT) |
| 有媒介-宿主关系的病毒 | 1,803 | VH + WUR 整合（447 VH + 1,356 WUR-only） |
| 病毒-媒介-宿主三元组 | 1,375 | 实验验证 + 文献追踪 |
| WUR 病毒传播记录 | 1,654 | 全渠道传播模式 |
| 本地基因组注释物种 | 4,726 | GenBank .gb 文件 |
| 引物对总数 | 83,830（RECOMMENDED 66,891 / USABLE 15,345 / NOT_RECOMMENDED 1,594） | 103,642 设计去重后合库，覆盖 4,789 物种 / 50 科 |
| 精选文献 | 6,525 | AI 精选（master 全库 33,325）；PubMed + bioRxiv + Crossref + OpenAlex |
| RAG 知识库向量 | 193,277 | Qdrant vectors（DPV/ICTV/ViroidDB 全文分块, 2026-07 构建验证值） |
| 病毒症状照片 | 2,975 | EPPO(925)/DPV(1,230)/Book(432)/PDF(360)/Open-i(28) 五来源 |
| TE 转座子 | 10,537 | LTR 反转录转座子 (U-RVDB v32.0)【模块 2026-09-23 已下线】 |
| EVE 位点 | 150,136 | 植物界 EVE 全库 (1,527 基因组 / 284 宿主科, phiX174 去污染后) |
| NLR 免疫受体 | 415 | RefPlantNLR, 73 物种 |
| sRNA 通路基因 | 11,780 | AGO/DCL/RDR/DRB/SGS3/HEN1 |
| UPS 泛素系统基因 | 3,996 | E1/E2/E3/F-box/BTB/Cullin/Proteasome |
| miRNA 序列 | 83,166 | miRBase + PlantRG + NCBI |
| vsiRNA 记录 | 322,214 | PVsiRNAdb, 12 种植物 |
| Metabuli 分类数据库 | 910 MB | k-mer 植物病毒参考 |
| 17 种下游工具库 | 15.95 GB | 23 分钟全量构建 |

## 技术栈

| 层级 | 技术 |
|:-----|:-----|
| 后端框架 | Flask (多模块), Dash (explorer), FastAPI (knowledge RAG) |
| 数据库 | SQLite (primers), Qdrant (RAG) |
| 前端 | Bootstrap 5, Chart.js, Plotly, Jinja2, DataTables |
| 流水线 | Python + Shell (run_all.sh) |
| 包管理 | pixi (conda-forge + PyPI) |
| 反向代理 | Nginx |
| 服务管理 | systemd |
| AI 模型 | DeepSeek V4 Pro (RAG) / DeepSeek V4 Flash (文献摘要) |
| 生物信息工具 | BLAST, Diamond, MMseqs2, Kraken2, Metabuli, MAFFT, VSEARCH, Primer3, varVAMP, Olivar 等 |

## 部署

阿里云 ECS 39.106.101.94 (北京), Nginx 反向代理 + systemd 服务, Python 3.10-3.12。

详见各模块 README、`config.py`、`TECHNICAL_REPORT.md` 和 `USER.md`。

### 服务端口映射

| 端口 | 服务 | systemd 单元 |
|:----:|:-----|:-----|
| 80 | Nginx 反向代理 | nginx.service |
| 5000 | 引物 Web | primer-web.service |
| 5002 | 知识库 RAG | nohup uvicorn (非 systemd) |
| 5003 | 文献追踪 | literature-tracker.service |
| 5004 | Metabuli 分类 | metabuli-api.service |
| 5005 | 媒介-宿主 | vector-host.service |
| 5006 | [已停用] 病毒档案 | virus-profile.service (inactive) |
| 5010 | REST API v1（全站数据开放） | api-gateway.service |
| 8000 | PAmiRDB | pamirdb.service |
| 8050 | Virus Explorer | virus-explorer.service |

## 最近更新

### 2026-07-23 — Metabuli Primer 设计 + GenBank 基因可视化

- **Primer 设计标签页**: 对分类出的病毒 contig 一键设计 PCR/qPCR 引物 (Primer3 + varVAMP 保守区策略)
- **GenBank 基因结构可视化**: `/metabuli/genbank/<accession>` API，NCBI 自动拉取 + 缓存注释
- 引物结果页基因组位置 SVG 叠加 CDS/gene/mat_peptide/UTR 轨道
- **Analyze 列四件套**: CDD / BLASTN / BLASTX / Primer 一键跳转
- NCBI→ICTV 物种名自动转换

### 2026-07-20 — 项目审计 + 模块 13 归档

- `13.virus_profile` 归档为 `_archived_13.virus_profile`，功能融入 explorer「病毒档案」Tab
- 6 个模块 README 全面更新，新增 17 个 Mermaid 图表
- 修复模块编号冲突、`.gitignore` 大文件排除、systemd service 文件补齐

详见 [`CHANGELOG.md`](CHANGELOG.md)。
