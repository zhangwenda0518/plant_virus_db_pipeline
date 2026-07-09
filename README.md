# Plant Virus Database Platform

> 植物病毒多组学数据库平台 — 9 个功能模块，部署于阿里云 ECS

**Live**: http://39.106.101.94/

## 目录结构

```
plant_virus_db_pipeline/
├── 1.Prepare_plant_virus_pipeline/   # A-G 七阶段数据流水线(下载/清洗/聚类/分类)
├── 2.Build_plant_virus_db/           # Metabuli/Diamond/Kraken2 等 17 种下游分类器建库
├── 3.virus_explorer/                 # Dash 交互式数据浏览器(/explorer/)
├── 4.virus_primer/                   # 引物设计 + Web 服务(/primers/)
├── 5.host_classify/                  # 病毒宿主分类与跨物种分析
├── 6.knowledge_rag/                  # 基于 DPV/viroidDB 的 AI 知识库问答(/knowledge/)
├── 7.literature_tracker/             # PubMed 文献自动追踪 + 每日检索报告(/literature/)
├── 8.plant-insect/                   # 病毒-媒介-宿主关系库 + WUR 整合(/vector/)
├── 8.virus_profile/                  # 单病毒详情页(基因组注释、图谱)(/virus/)
├── 9.metabuli/                       # Metabuli 宏基因组分类器 Web(/metabuli/)
├── 10.virus_photos/                  # 病毒电镜照片/症状图库 + 图鉴生成
├── docs/                             # Reference DB 静态站(/reference/ + /te/ + /)
│   ├── portal.html                   #   统一门户首页
│   ├── te/                           #   TE & EVE 转座子-内源性病毒数据库
│   └── data/                         #   参考序列 FASTA/TSV（Plant_Virus_*）
├── config.py                         # 统一项目配置文件(PIPELINE_OUTPUTS)
├── run_all.sh                        # 流水线一键运行入口
└── requirements.txt                  # Python 依赖
```

## 在线服务(9 个模块)

| 路由 | 服务 | 技术栈 | 说明 |
|---|---|---|---|
| `/` | **统一门户** | 静态 HTML | 9 模块入口卡片 |
| `/reference/` | **参考数据库** | 静态 HTML/JS | 非冗余参考基因组下载/浏览/提交 |
| `/explorer/` | **数据浏览器** | Dash + Plotly | 时空演变/全基因组变异/媒介传播网络/病毒档案 |
| `/primers/` | **引物数据库** | Flask | 检测引物设计结果/BLAST/基因组可视化 |
| `/virus/` | **病毒详情** | Flask | 单病毒基因组图谱/注释下载/蛋白/文献 |
| `/vector/` | **媒介-宿主库** | Flask | VH+WUR 三维传播facet检索/8层Sankey/热力图 |
| `/te/` | **TE & EVE** | 静态 HTML | 植物转座子/内源性病毒元件(LTR/ENRV/ERV) |
| `/metabuli/` | **宏基因组分类** | Flask | contig 分类(NCBI→ICTV 8 级)/峰图/Krona/序列下载 |
| `/literature/` | **文献追踪** | Flask | PubMed 自动追踪/每日检索/AI 摘要生成 |
| `/knowledge/` | **知识库 RAG** | Flask + Qdrant | DPV + viroidDB AI 问答 |

## 数据来源

- NCBI GenBank 全量植物病毒序列
- ICTV VMR MSL41 病毒分类学
- WUR Plant Virus Transmission Database (library.wur.nl)
- U-RVDB v32.0 植物转座子/内源性病毒数据库
- NCBI PubMed 文献
- DPV (Descriptions of Plant Viruses) + ViroidDB

## 数据量

- 8,465 参考基因组(含本地 genome_annotations 注释)
- 6,182 病毒物种
- 1,806 个病毒有媒介-宿主关系
- 1,654 条 WUR 病毒传播记录
- 1,375 对病毒-媒介-宿主三元组
- 4726 个物种有本地基因组注释
- 10,537 个 LTR 反转录转座子 (TE 库)
- 910 MB Metabuli 植物病毒分类数据库

## 部署

阿里云 ECS 39.106.101.94(北京),Nginx 反向代理 + 7 个 systemd 服务,Python 3.6-3.10。详见各模块 README 和 `config.py`。
