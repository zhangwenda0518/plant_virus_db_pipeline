# Plant Virus Database Platform

> 植物病毒多组学数据库平台 — 12 个功能模块 + 1 个归档模块，部署于阿里云 ECS

**Live**: http://39.106.101.94/

## 目录结构

```
plant_virus_db_pipeline/
├── 1.Prepare_plant_virus_pipeline/   # A-G 七阶段数据流水线(下载/清洗/聚类/分类)
├── 2.Build_plant_virus_db/           # Metabuli/Diamond/Kraken2 等 17 种下游分类器建库
├── 3.virus_explorer/                 # Dash 交互式数据浏览器(/explorer/)
├── 4.virus_primer/                   # 引物设计 + Web 服务(/primers/)
├── 5.host_classify/                  # 病毒宿主分类与跨物种分析
├── 6.knowledge_rag/                  # AI 知识库问答(neblab_rag基础+plant_virus_rag特化,DeepSeek/Qdrant)(/knowledge/)
├── 7.literature_tracker/             # PubMed 文献自动追踪 + 每日检索报告(/literature/)
├── 8.plant-insect/                   # 病毒-媒介-宿主关系库 + WUR 整合(/vector/)
├── 9.metabuli/                       # Metabuli 宏基因组分类器 Web(/metabuli/)
├── 10.virus_photos/                  # 病毒电镜照片/症状图库 + 图鉴生成(/photos/)
├── 11.antiviral_genes/               # 植物免疫与sRNA基因图谱(/genes/)
├── 12.pamirdb/                       # 植物抗病毒miRNA预测工作台(/pamirdb/)
├── _archived_13.virus_profile/        # [已归档] 单病毒详情页(独立网页已废弃)
├── docs/                             # Nginx 静态站(/reference/ + /te/ + /photos/ + /)
│   ├── index.html                    #   统一门户首页 → /
│   ├── index.html                    #   参考数据库首页 → /reference/
│   ├── photos.html                   #   症状图库 → /photos/
│   ├── table.js / i18n.js            #   公用 JS
│   ├── data/                         #   参考序列 FASTA/TSV + 图片（Plant_Virus_*）
│   ├── literature/                   #   文献追踪静态文件 → /literature/
│   ├── primers/                      #   引物 JSON 数据（7,193 物种）
│   └── te/                           #   TE & EVE 转座子数据库 → /te/
├── config.py                         # 统一项目配置文件(PIPELINE_OUTPUTS)
├── run_all.sh                        # 流水线一键运行入口
└── requirements.txt                  # Python 依赖
```

## 在线服务 (12 个模块)

| 路由 | 服务 | 技术栈 | 说明 |
|---|---|---|---|
| `/` | **统一门户** | 静态 HTML | 13 模块入口卡片 |
| `/reference/` | **参考数据库** | 静态 HTML/JS | 非冗余参考基因组下载/浏览/提交，6子页 |
| `/explorer/` | **数据浏览器** | Dash + Plotly | 时空演变/全基因组变异/媒介传播网络/内嵌AI助手 |
| `/primers/` | **引物数据库** | Flask | 57,072对PCR/qPCR引物，REST API，搜索/浏览/下载 |
| `/vector/` | **媒介-宿主库** | Flask | VH+WUR 三维传播facet检索/三视图/桑基图/热力图 |
| `/te/` | **TE & EVE** | 静态 HTML | 植物转座子/内源性病毒元件(LTR/ENRV/ERV)，6个FASTA下载 |
| `/metabuli/` | **宏基因组分类** | Flask | contig分类(8级)/Krona/Sankey/Primer设计/GenBank基因可视化 |
| `/photos/` | **症状图库** | 静态 HTML/JS | EPPO/DPV/Book/PDF四来源，Gallery/Dashboard/Table三视图 |
| `/genes/gene_browser.html` | **基因图谱** | 静态 HTML/JS | NLR(415)/sRNA(11,780)/UPS(3,996)/miRNA(83,166)四标签 |
| `/pamirdb/` | **PAmiRDB** | 静态 HTML/JS | miRNA靶标预测: miRanda+psRNATarget+RNAhybrid三算法共识 |
| `/literature/` | **文献追踪** | Flask | PubMed自动追踪/手动4源检索/AI摘要/趋势分析 |
| `/knowledge/` | **知识库 RAG** | Flask + Qdrant | 193K论文+DPV+viroidDB，DeepSeek V4 Pro驱动 |

## 数据来源

- NCBI GenBank 全量植物病毒序列
- ICTV VMR MSL41 病毒分类学
- WUR Plant Virus Transmission Database (library.wur.nl)
- U-RVDB v32.0 植物转座子/内源性病毒数据库
- NCBI PubMed / bioRxiv / Crossref / OpenAlex 文献
- DPV (Descriptions of Plant Viruses) + viroidDB
- EPPO Global Database 病害症状照片
- RefPlantNLR 验证免疫受体 (415)
- miRBase + PlantRG + PVsiRNAdb

## 数据量

- 8,465 参考基因组(含本地 genome_annotations 注释)
- 6,182 病毒物种
- 1,806 个病毒有媒介-宿主关系
- 1,654 条 WUR 病毒传播记录
- 1,375 对病毒-媒介-宿主三元组
- 4,726 个物种有本地基因组注释
- 10,537 个 LTR 反转录转座子 (TE 库)
- 910 MB Metabuli 植物病毒分类数据库
- 57,072 对 PCR/qPCR 引物 (4,799 物种)
- 7,099 精选文献 + 2,892 结构化记录
- 193,000+ 论文全文 (RAG 知识库)
- 925 张症状照片
- 415 个 NLR 基因 (73 物种)
- 83,166 miRNAs + 322K vsiRNAs

## 部署

阿里云 ECS 39.106.101.94(北京), Nginx 反向代理 + systemd 服务, Python 3.6-3.12。详见各模块 README 和 `config.py`。
