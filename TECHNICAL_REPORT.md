# Plant Virus Database Platform — 技术详细报告

> **生成日期**: 2026-07-20
> **项目根目录**: `D:\桌面\C-host_classify\plant_virus_db_pipeline`
> **线上地址**: http://39.106.101.94
> **服务器**: 阿里云 ECS (北京), Nginx 反向代理 + systemd 服务

---

## 目录

1. [项目总览](#1-项目总览)
2. [顶层配置与基础设施](#2-顶层配置与基础设施)
3. [Module 1: 数据准备流水线 (Prepare)](#3-module-1-prepare_plant_virus_pipeline)
4. [Module 2: 下游分类器建库 (Build DB)](#4-module-2-build_plant_virus_db)
5. [Module 3: 交互式数据浏览器 (Virus Explorer)](#5-module-3-virus_explorer)
6. [Module 4: 引物设计与数据库 (Virus Primer)](#6-module-4-virus_primer)
7. [Module 5: 宿主分类分析 (Host Classify)](#7-module-5-host_classify)
8. [Module 6: AI 知识库问答 (Knowledge RAG)](#8-module-6-knowledge_rag)
9. [Module 7: 文献自动追踪 (Literature Tracker)](#9-module-7-literature_tracker)
10. [Module 8: 媒介-宿主关系库 (Plant-Insect)](#10-module-8-plant-insect)
11. [Module 9: 宏基因组分类器 (Metabuli)](#11-module-9-metabuli)
12. [Module 10: 病毒照片图库 (Virus Photos)](#12-module-10-virus_photos)
13. [Module 11: 抗病毒基因图谱 (Antiviral Genes)](#13-module-11-antiviral_genes)
14. [Module 12: 植物抗病毒 miRNA 预测 (PAmirDB)](#14-module-12-pamirdb)
15. [Module 13: 单病毒详情页 (Virus Profile) — [ARCHIVED]](#15-module-13-virus_profile-archived)
16. [静态站点 (docs/)](#16-静态站点-docs)
17. [部署架构](#17-部署架构)
18. [注意事项与已知问题](#18-注意事项与已知问题)

---

## 1. 项目总览

### 1.1 项目定位

**Plant Virus Database Platform** 是一个面向植物病毒学研究的多组学数据库平台，集成了参考序列数据库、交互式可视化、诊断引物设计、宏基因组分类、文献自动追踪、AI 知识库问答、miRNA 靶标预测等 13 个功能模块。

### 1.2 核心数据量

| 指标 | 数值 |
|:-----|:----:|
| 参考基因组 (非冗余) | 9,022 |
| 病毒物种 | 5,147 |
| 病毒-媒介-宿主三元组 | 1,375 |
| PCR/qPCR 引物对 | 83,830（去重后，RECOMMENDED 66,891） |
| 精选文献 | 6,525（master 全库 33,325） |
| 论文全文 (RAG) | 193,000+ |
| miRNA | 83,166 |
| NLR 免疫受体 | 415 |

### 1.3 数据来源

- NCBI GenBank 全量植物病毒序列
- ICTV VMR MSL41 (病毒分类学权威)
- KEGG Virus-Host DB (文献溯源的病毒-宿主关联)
- WUR Plant Virus Transmission Database
- U-RVDB v32.0 (植物转座子/内源性病毒)
- NCBI PubMed / bioRxiv / Crossref / OpenAlex
- DPV (Descriptions of Plant Viruses)
- EPPO Global Database
- RefPlantNLR / miRBase / PlantRG / PVsiRNAdb

### 1.4 技术栈总览

| 层级 | 技术 |
|:-----|:-----|
| 后端框架 | Flask (多模块), Dash (explorer) |
| 数据库 | SQLite (primers), Qdrant (RAG) |
| 前端 | Bootstrap 5, Chart.js, Plotly, Jinja2 |
| 流水线 | Python + Shell (run_all.sh) |
| 包管理 | pixi (conda-forge + PyPI) |
| 反向代理 | Nginx |
| 服务管理 | systemd |
| AI 模型 | DeepSeek V4 Pro (RAG 驱动) |
| 生物信息工具 | BLAST, Diamond, MMseqs2, Kraken2, Metabuli, MAFFT, VSEARCH 等 |

---

## 2. 顶层配置与基础设施

### 2.1 config.py

统一项目配置文件，所有模块从此处读取数据路径。

**关键功能**:
- 定义 `PROJECT_ROOT`、`DATA_DIR`、`PRIMER_DIR`、`HOST_DIR`
- 通过 `PIPELINE_OUTPUTS` 字典暴露 7 个核心数据文件路径
- 支持环境变量覆盖：`PVDB_<KEY>=<path>` (如 `PVDB_FULL_TSV=/custom/path`)
- 提供 `check_required()` 验证关键文件存在性
- 提供 `load_version()` / `get_version_string()` 读取 `DATA_VERSION`

**输出文件**:

| 键 | 文件 | 内容 |
|:---|:-----|:-----|
| `cluster_fasta` | Plant_Virus_Ref.fasta | 最终聚类参考序列 (9,022 条) |
| `cluster_info` | Plant_Virus_Ref.Info.tsv | 聚类参考元数据 |
| `full_tsv` | Plant_Virus_Full.Info.tsv | 全量元数据 (~199K 条) |
| `full_fasta` | Plant_Virus_Full.fasta | 全量序列 (~199K, 377MB) |
| `complete_fasta` | Plant_Virus.complete_ref.fasta | 完整参考序列 |
| `complete_info` | Plant_Virus.complete_ref_info.tsv | 完整参考元数据 |
| `gene_cov` | virus_genes_cov.tsv | 基因覆盖度表 |

**使用方式**:
```python
from config import DATA_DIR, PIPELINE_OUTPUTS
df = pd.read_csv(PIPELINE_OUTPUTS['full_tsv'], sep='\t')
```

### 2.2 pixi.toml

跨平台包管理配置（ `pixi` = conda + PyPI 的统一管理器），项目名 `plant_virus_primer_db` v2.0.0。

**依赖**:
- Python ≥3.10,<3.13
- Biopython, Polars, Flask, requests (conda-forge)
- primer3-py (PyPI)
- Linux 额外: gunicorn, primer3, mafft, blast, vsearch
- Windows 额外: waitress

**预定义任务**:
- `pixi run web` → 启动引物 Web 服务
- `pixi run pipeline` → 一键运行 step1→step5 (Linux)
- `pixi run web-win` → Windows 开发模式

### 2.3 deploy.sh

服务器一键部署脚本（5 阶段）:
1. 检查 pixi 安装
2. git pull / 手动同步
3. `pixi install`
4. 验证引物设计服务（测试序列）
5. 重启 Web 服务 (pkill + nohup)

### 2.4 _deploy.py / _deploy_explorer.py

Python 部署脚本，将 base64 编码的 HTML/JS/CSS 文件解码写入服务器目标路径。主要用于静态页面的批量部署。

### 2.5 .gitignore

排除大型数据目录: `pubmed_records/` (8.25GB), `rag-db/` (2GB), PDF/DOCX 源文件, archive/backup 目录。

### 2.6 plant-virus.conf

Nginx 主配置文件，定义 13 条 location 规则，将不同路由反向代理到各模块的内部端口 (5000-5006, 8050)。

---

## 3. Module 1: Prepare_plant_virus_pipeline

### 3.1 概述

植物病毒基因组数据库构建流水线，从 NCBI、KEGG、ICTV 三大数据源出发，经过七大阶段 (A-G) 的元数据整合、宿主分类、序列提取、去冗余、聚类评估，最终构建高质量非冗余植物病毒参考基因组数据库。

### 3.2 七大阶段 (A→G)

#### A 阶段: 元数据整合 (Metadata Integration)
- **A1_check_data.py**: 检测前置数据完整性 (4,970 行)
- **A2_merge_vhost_vhdb.py**: 合并 VHostMetadata 与 KEGG Virus-Host DB，Viridiplantae 关键词筛选 (10,473 行)
- **A3_vhost_imputer.py**: 宿主信息插补，基于分类谱系推导缺失宿主 (7,262 行)
- **A4_add_lineage.py**: 从 NCBI Taxonomy 添加完整世系信息 (13,021 行)
- **add_family_column.py**: 补充科级分类列 (3,792 行)

#### B 阶段: ICTV 宿主拆分 (ICTV Host Split)
- **B1_vmr_split_by_host.py**: 将 ICTV VMR (MSL41) 按 Host source 字段拆分，进行拉丁文文本抢救 (11,159 行)

#### C 阶段: 宿主信息整合与分类 (Host Info Integration)
- **C1_virus_host_info_extract.py**: 从多源提取病毒宿主关联信息 (22,684 行)
- **C2_classify_by_host.py**: 基于宿主做病毒分类标注 (14,280 行)
- **C3a_algae_split.py**: 藻类病毒拆分 (4,187 行)
- **C3b_animal_subsplit.py**: 动物病毒子拆分 (3,793 行)
- **C4_clean_all_tsvs.py**: 清洗所有 TSV 文件，统一格式，去除非植物记录 (32,451 行，最复杂的单文件)

#### D 阶段: 序列获取 (Sequence Acquisition)
- **D1_extract_and_check_fasta.py**: 从 NCBI 提取 FASTA 并检查完整性 (7,683 行)
- **D2_download_missing.py**: 下载缺失序列 (7,803 行)

#### E 阶段: 元数据完善 (Metadata Enrichment)
- **E1_extract_metadata.py**: 从 GenBank 记录提取详细元数据 (10,017 行)
- **E2_fetch_topology.py**: 获取基因组拓扑信息 (3,896 行)
- **E3_merge_topology.py**: 合并拓扑数据 (4,526 行)
- **E4_add_ncbi_names.py**: 添加 NCBI 物种名 (4,381 行)

#### F 阶段: 分类与去冗余 (Classification & Dedup)
- **F1_analyze_summary.py**: 汇总分析 (5,334 行)
- **F2_classify_segmented.py**: 分段基因组分类 (20,507 行)
- **F3_metadata_dedup.py**: 元数据去冗余 (10,628 行)
- **F4_seqkit_mmseqs_rescue.py**: seqkit + mmseqs2 联合去冗余 (13,399 行)

#### G 阶段: 最终聚类与评估 (Final Clustering)
- **G1_seqid_to_taxid.py**: 序列 ID → Taxonomy ID 映射 (17,916 行)
- **G1b_add_length.py**: 添加序列长度信息 (7,911 行)
- **G2_vclust_cluster.py**: VClust 聚类 (18,583 行)
- **G3_derep_evaluate.py**: 去冗余评估 (8,699 行)
- **G4_gene_coverage.py**: 基因覆盖度计算 (6,625 行)

### 3.3 Audit 子目录

审计与修复脚本集 (audit/):
- **audit_segment_blacklist.py**: 黑名单片段审计 (7,450 行)
- **audit_segment_lengths.py**: 片段长度分布分析 (11,653 行)
- **audit_segment_names.py**: 片段命名规范检查 (2,672 行)
- **audit_segment_sources.py**: 片段来源追溯 (5,683 行)
- **fix_vmr_species.py**: VMR 物种名修复 (4,120 行)
- **resolve_segments_by_sequence.py**: 基于序列解析分片段 (8,166 行)

### 3.4 run_all.sh

总入口脚本 (29,417 行)，自动执行 A→G 全部阶段，含错误处理、日志记录和断点续传。

### 3.5 注意事项

1. **运行顺序**: 必须按 A→B→C→D→E→F→G 顺序执行，后一阶段依赖前一阶段输出
2. **数据量**: 全量运行时处理 ~199K 条序列 (377MB FASTA)，建议至少 32GB 内存
3. **NCBI API 限速**: D 阶段需要大量 NCBI e-utilities 请求，需配置 API key (每秒 10 次无 key 时 3 次)
4. **VClust**: G2 聚类阈值 98% 序列一致性，可调整参数
5. **断点续传**: run_all.sh 支持从失败步骤恢复

---

## 4. Module 2: Build_plant_virus_db

### 4.1 概述

将 Module 1 产出的非冗余参考序列一次性构建为 17 种下游分类/比对工具的本地数据库。

### 4.2 核心脚本

**build_virus_db.py** (40,464 行): 统一的 CLI 工具，模块化架构。

### 4.3 构建流程

```
输入 FASTA (核酸 11,956 条 + 蛋白 72,691 条)
    │
    ├── 1. 环境检查 → 检测 17 个二进制工具可用性
    ├── 2. 软链接准备 → work_dir 下建立符号链接
    ├── 3. TaxID 提取 → 解析 FASTA header
    ├── 4. 并行建库 → 17 个构建器并发执行
    └── 5. 报告生成 → 统计耗时/磁盘/成功状态
```

### 4.4 支持的 17 种数据库

| 类别 | 工具 | 类型 | 耗时 | 磁盘 |
|:-----|:-----|:-----|:----:|:----:|
| k-mer | **Metabuli** | 核酸 | 390s | 909 MB |
| k-mer | **Kraken2** | 核酸 | 59s | 181 MB |
| k-mer | **KrakenUniq** | 核酸 | 163s | 10.4 GB |
| k-mer | **KMCP** | 核酸 | 23s | 538 MB |
| k-mer | **Ganon** | 核酸 | 267s | 76 MB |
| k-mer | **Sylph** | sketch | 1s | 44 MB |
| 比对 | **BLAST** | 核酸 | 188s | 22 MB |
| 比对 | **KMA** | k-mer比对 | 69s | 705 MB |
| 比对 | **MMseqs2** | 蛋白聚类 | 7s | 749 MB |
| 比对 | **Diamond** | 蛋白比对 | 1s | 44 MB |
| 定量 | **Salmon/Kallisto** | 核酸定量 | 82s | — |
| 定量 | **Bracken** | 丰度估计 | 17s | — |
| 分类 | **Centrifuger** | 快速分类 | 24s | 50 MB |
| 分类 | **Kun_Peng** | K2-based | <1s | 200 MB |
| 分类 | **LexicMap** | 快速分类 | 39s | 2.3 GB |
| 蛋白 | **Kaiju** | 蛋白分类 | 2s | 33 MB |
| 蛋白 | **Kraken2x** | 蛋白分类 | 54s | 57 MB |

**总计**: 17/17 成功, 23 分钟, 15.95 GB

### 4.5 关键参数

```bash
python build_virus_db.py \
  --nuc-fasta Plant_Virus_Ref.fasta \
  --prot-fasta virus.gene_pep.fasta \
  --db-prefix ref.virus.build \
  --work-dir ./5.virus.ref.build.db \
  --tax-dir ~/database/taxonomy \
  --databases all \          # 或 metabuli,kraken2,blast,...
  --threads 120 \
  --max-ram 500
```

### 4.6 设计决策

1. **动静分离**: 原始序列与构建产物物理隔离
2. **按需构建**: `--databases all` 或指定子集
3. **软链接优化**: 大文件共享避免重复
4. **NCBI Taxonomy 复用**: 所有分类工具共用同一 taxonomy 目录

---

## 5. Module 3: Virus Explorer

### 5.1 概述

基于 Dash + Plotly 的交互式植物病毒数据浏览器，提供时空演变、全基因组变异、媒介传播网络等分析视图。在线地址: `/explorer/` (端口 8050)

### 5.2 核心文件

- **app.py** (110,106 行): 主应用代码，包含所有回调函数和布局
- **app_server.py** (114,889 行): 生产环境服务器版本
- **deploy.sh** (4,560 行): 部署脚本

### 5.3 功能特性

1. **时间线视图**: 病毒序列发布/采集年份分布
2. **全球分布**: 按国家/地区的地理分布可视化
3. **序列比对展示**: 多序列比对交互展示
4. **分类学浏览**: Kingdom → Species 层级筛选
5. **内嵌 AI 助手**: 集成 DeepSeek API 的对话式数据查询
6. **基因组图谱**: 结合 GBDraw 的基因组可视化
7. **媒介传播网络**: Sankey 图展示病毒-媒介-宿主关系

### 5.4 Archive/Patches 子目录

包含 20 个历史补丁脚本，记录功能迭代:
- `add_circular_genome.py`: 添加环状基因组支持
- `add_ncbi_link.py`: 添加 NCBI 直链
- `add_profile_sync.py`: Profile 页同步
- `fix_alignment.py` / `fix_alignment_v2.py` / `fix_alignment_v3.py`: 比对功能三次修复
- `fix_gbdraw_*.py`: 基因组绘图修复 (3 个)
- `fix_explorer_callback.py`: 回调修复
- `fix_sync.py`: 同步修复
- `gbdraw_svg_embed.py`: SVG 嵌入
- `integrate_gbdraw.py`: GBDraw 集成
- `ncbi_fetcher.py`: NCBI 数据获取

### 5.5 使用注意

1. **数据量**: 加载 199K 条记录的 TSV，预计算 stats JSON 缓存
2. **Dash 特性**: WebSocket 长连接，Nginx 需配置 proxy_buffering off
3. **内存**: 约需 2GB 加载全量数据到 pandas DataFrame

---

## 6. Module 4: Virus Primer

### 6.1 概述

植物病毒诊断引物数据库 + Web 服务 + 在线引物设计，共 83,830 对去重引物（103,642 设计去重后）覆盖 4,789 物种 / 50 科，RECOMMENDED 66,891。在线地址: `/primers/`

### 6.2 五阶段流水线

| 步骤 | 文件 | 行数 | 功能 |
|:-----|:-----|:----:|:-----|
| Step 1 | step1_parse_db.py | 22,787 | 解析参考序列数据库 |
| Step 2 | step2_design_primers.py | 72,178 | 批量引物设计 (Primer3 + varVAMP + Olivar) |
| Step 3 | step3_validate_primers.py | 56,909 | 引物验证 (BLAST 特异性 + 二聚体 + 发夹) |
| Step 4 | step4_build_database.py | 21,020 | 构建 SQLite 数据库 |
| Step 5 | step5_web_server.py | 107,887 | Flask Web 服务 |
| Step 5 PROD | step5_web_server_PROD.py | 92,430 | 生产环境专用版本 |

### 6.3 Web 服务路由

| 路由 | 功能 |
|:-----|:-----|
| `/` | 首页: 数据库概览 + 快速搜索 |
| `/search` | 引物搜索: 按物种/类型/方法/推荐级别筛选 |
| `/species/<name>` | 物种详情: 所有引物列表 + 基因组覆盖度可视化 |
| `/primer/<id>` | 单引物详情: 序列、Tm、GC%、二聚体分析、BLAST 特异性 |
| `/browse` | 物种浏览: 500 个物种表格 |
| `/download` | 数据下载: FASTA/CSV/SQLite |
| `/api/*` | REST API: 9 个端点 |
| `/primers/design` | 在线引物设计: 上传 FASTA 或选择已知物种 |

### 6.4 引物设计服务

- **design_lamp.py** (22,520 行): LAMP 引物设计
- **primer_design_service.py** (28,065 行): 通用引物设计服务，支持 PCR/qPCR/Degenerate/Tiled 四种模式
- **design_web_routes.py** (11,376 行): Web 路由注册

### 6.5 LAMP 工具集 (lamp_tools/)

集成了 14 个 LAMP (环介导等温扩增) 相关工具的代码:

| 工具 | 说明 |
|:-----|:-----|
| **AnalysePrimer** | LAMP/PCR 引物分析 |
| **GLAPD** | GPU 加速 LAMP 引物设计 (含 bowtie) |
| **LAMP-Forge** | 完整 LAMP 面板设计平台 (Flask + RQ) |
| **LAMP-Primer-Hairpin** | 发夹结构检测 |
| **LAMP-Primers** | LAMP 引物设计核心 |
| **lamp-virus** | 病毒 LAMP 检测 R 包 |
| **LAMPrimers-iQ** | GUI 桌面应用 (Python + Tkinter) |
| **LAMProject** | Electron 桌面应用 (JS) |
| **lampshade** | 引物可视化 R 包 |
| **lava-dna** | LAMP 分析 conda 包 |
| **LAMP_primer_hairpin_detector_and_debugger** | Web 版发夹检测 (JS) |
| **Multiplexed_Coverage_Analysis_v3** | 多重覆盖度分析 |
| **primd** | TypeScript LAMP 引物设计 (biome) |
| **SimCycle** | LAMP 动力学模拟 (Python) |
| **R-LampPrimerAnalyzer** | R 语言 LAMP 引物分析全套脚本 |

### 6.6 数据库 Schema

SQLite 三表结构:
- **taxonomy**: species_name, genus, family, priority, genome_length
- **primers**: primer_id, species_name, primer_type, pair_id, fwd_sequence, rev_sequence, probe_sequence, product_size, design_method, gc_fwd, gc_rev, fwd_position, rev_position, fwd_tm, rev_tm, probe_tm
- **validation**: primer_id, overall_score, recommendation (RECOMMENDED/USABLE/CAUTION/NOT_RECOMMENDED), dimer_warning, probe_warning, blast_specificity_score, coverage_avg, coverage_total_seqs, fwd_coverage_pct, rev_coverage_pct, cross_dimer_3prime, probe_hairpin_tm, probe_self_dimer_dg

### 6.7 工具脚本 (tools/)

- **export_primers_static.py**: 导出引物数据为静态 JSON
- **patch_olivar_positions.py** (3,025 行): 修复 Olivar 位置标注
- **test_blast_batch.py** (12,074 行): BLAST 批量测试
- **varvamp_workflow.py** (16,109 行): varVAMP 工作流

### 6.8 注意事项

1. **服务器路径**: 生产环境代码在 `/opt/plant_virus_db/primer_design_server/`，非本地 `4.virus_primer/`
2. **Primer3**: Linux 需要 `primer3` 二进制, Windows 使用 `primer3-py`
3. **BLAST 验证**: step3 需要本地 BLAST+ 和 NCBI nt 数据库 (> 200GB)
4. **内存**: step2 设计阶段需 16GB+
5. **推荐级别**: `RECOMMENDED` ≥ 80 分, `USABLE` 60-79, `CAUTION` < 60 但有可用性, `NOT_RECOMMENDED` < 60

---

## 7. Module 5: Host Classify

### 7.1 概述

病毒宿主分类与跨界分析工具集，对 Module 1 C4 清洗后的数据进行下游分析。包含 9 个步骤脚本。

### 7.2 流程

| 步骤 | 脚本 | 行数 | 功能 |
|:----:|:-----|:----:|:-----|
| 1 | 1_cross_kingdom_overlap.py | 7,415 | 跨界重叠分析 (8级分类重叠表) |
| 2 | 2_plot_overlap.py | 14,360 | 可视化 (柱状图/独占率/UpSet 矩阵) |
| 3 | 3_host_probability.py | 6,299 | 宿主概率表 (Species/Genus/Family/Order 四级) |
| 4 | 4_cross_species.py | 6,139 | 跨物种分析 |
| 5 | 5_classify_contigs.py | 12,250 | Contig 级宿主分类 (四级级联) |
| 6 | 6_inspect_genus.py | 3,379 | 属级审计 |
| 7 | 7_query_shared_genera.py | 3,167 | 共享属查询 |
| 8 | 8_summary_stats.py | 7,399 | 汇总统计 |
| 9 | 9_split_by_taxon.py | 7,082 | 按分类单元拆分 |

### 7.3 置信度模型

双因子模型评估 P(host | taxon):

| 因子 | 公式 | 说明 |
|:-----|:-----|:-----|
| C_ent (专一性) | 1 - H / log(N) | 香农熵归一化 |
| C_sup (支持度) | 1 - e^(-n/5) | 记录数 ≥15 接近 1.0 |
| 综合 | C_ent × C_sup | ≥0.8 High, ≥0.4 Medium |

### 7.4 Contig 分类级联

Species → Genus → Family → Order 四级级联，含列偏移容错。

---

## 8. Module 6: Knowledge RAG

### 8.1 概述

AI 驱动的植物病毒学知识库问答系统。基于 193,000+ 论文全文 + DPV + viroidDB + ICTV 报告，使用 DeepSeek V4 Pro 驱动，Qdrant 向量数据库。

在线地址: `/knowledge/` (端口 5002)

### 8.2 目录结构

```
6.knowledge_rag/
├── api_server.py           # Flask API 服务 (含嵌入式 HTML 页面)
├── databases/
│   ├── dpv_md/             # ~260 个 DPV 病毒描述 Markdown 文件
│   ├── ictv_md/            # ~160 个 ICTV 病毒科报告 Markdown
│   └── viroiddb.json       # viroidDB 57 MB JSON
└── pv_rag/                 # 核心 RAG 包
    ├── alembic/            # 文献/摘要/全文表迁移
    ├── alembic_pv/         # 植物病毒专用表迁移
    ├── config/             # 配置文件
    ├── evals/              # 评估数据集 (RAG 质量评测)
    ├── rag-db/             # 预构建向量库
    │   ├── dpv_database/   # DPV 向量索引
    │   ├── ICTV_RAG_Database/ # ICTV 向量索引
    │   ├── kegg_rag.db/    # KEGG 知识库
    │   ├── ViralZone_Books/ # ViralZone 书籍
    │   └── viralzone_rag_db/ # ViralZone 向量库
    ├── scripts/            # 数据导入脚本
    ├── src/
    │   ├── neblab_rag/     # 基础 RAG 框架
    │   └── plant_virus_rag/ # 植物病毒特化模块
    └── tests/              # 单元/集成测试
```

### 8.3 API 端点

| 端点 | 方法 | 功能 |
|:-----|:----:|:-----|
| `/query` | POST | RAG 问答 (含 LLM 推理) |
| `/search` | GET | 语义搜索 (仅检索) |
| `/stats` | GET | 数据库统计 |
| `/` | GET | Web UI 页面 |

### 8.4 检索策略

1. BM25 关键词检索 (`kb.search()`, top_k=5)
2. 全文语义检索 (`kb.search_full_text()`, top_k=3)
3. 两种结果合并后送给 LLM 生成答案
4. 支持三种模式: RAG-only / Bare LLM / Hybrid

### 8.5 LLM 提示词

系统提示词 (`SYS_PROMPT`) 约定:
1. 每个声明必须用 `[N]` 标注来源
2. 不编造信息
3. 找不到时说 "not found in database"
4. 详尽提取事实/数字/发现
5. 先解释核心理念再给具体例子和数据

### 8.6 注意事项

1. **服务器位置**: 生产环境在 `/opt/src/plant_virus_rag/` (editable pip install)，非本地代码
2. **启动方式**: `uvicorn plant_virus_rag.api.main:create_pv_app --factory` (非 systemd)
3. **已知 Bug**: `/knowledge/query` 偶发 500 错误，`_enrich_citations` 期望 list 但 DB 返回 str
4. **API Key**: 可通过 `.env` 文件或 Web UI 设置
5. **向量库**: 预构建 193,277 条 Qdrant vectors（2026-07 索引批次构建验证值，见 pv_rag/README；早前版本误写 229,184，全库无出处）

---

## 9. Module 7: Literature Tracker

### 9.1 概述

植物病毒文献自动追踪系统，每周自动检索 9 大类目的新文献，支持 AI 中文摘要生成和趋势分析。在线地址: `/literature/` (端口 5003)

### 9.2 目录结构

```
7.literature_tracker/
├── web/index.html          # 单页面 Web UI (Flask 模板)
├── api_server.py           # Flask API
├── paper-daily/            # 每日论文追踪核心
│   ├── config/             # 检索策略配置
│   ├── scripts/            # 数据采集脚本
│   ├── tests/              # 测试
│   └── web/                # Web 界面
├── auto-paper-collecter/   # 自动论文收集器
│   ├── app/pipeline/       # 流水线模块
│   ├── app/services/       # 服务层
│   └── app/sources/        # 数据源适配器
├── pubmed_records/         # PubMed 下载记录
│   ├── browser_pdfs/       # 浏览器下载的 PDF
│   ├── multi_pdfs/         # 批量 PDF
│   ├── pmc_fulltext/       # PMC 全文
│   ├── pv_texts/           # 提取文本
│   ├── scihub_pdfs/        # Sci-Hub 源
│   ├── scihub_v2/          # Sci-Hub v2
│   ├── semantic_pdfs/      # Semantic Scholar 源
│   └── vpn_pdfs/           # VPN 下载的 PDF
├── LitSearch/              # 文献搜索工具
├── meta.seubiomed.com/     # 元网站 (文献来源聚合)
├── scripts/                # 采集/处理脚本
├── literature-daily-report/ # 每日报告
├── data/daily/             # 每日数据
├── backup/web_data_17cats/ # 17 类备份数据
├── historical/             # 历史里程碑数据
└── archive/                # 归档旧脚本
```

### 9.3 Web UI 六大标签

| 标签 | 功能 |
|:-----|:-----|
| **AI Knowledge Assistant** | RAG 知识库搜索 + 手动文献检索 (PubMed/bioRxiv/Crossref/OpenAlex 四源) |
| **Weekly Track** | 按周分组的文献卡片，含 AI Digest |
| **Weekly Digest** | 每周文献摘要，按年份浏览 |
| **Monthly Archive** | 2020-2026 月度存档，12 月网格 |
| **Historical** | 病毒发现时间线 + 里程碑 |
| **Paper List & Trends** | 论文列表、年份/类别/期刊统计图表 |

### 9.4 检索源

| 源 | 方法 | API |
|:---|:-----|:-----|
| PubMed | NCBI E-utilities (esearch + efetch) | eutils.ncbi.nlm.nih.gov |
| bioRxiv | API 关键词过滤 | api.biorxiv.org |
| Crossref | REST API | api.crossref.org |
| OpenAlex | REST API (含摘要倒排索引重建) | api.openalex.org |

### 9.5 AI 功能

1. **论文 AI 摘要**: 点击 `AI` 按钮 → 发送 title + abstract 到 DeepSeek → 结构化提取 (病毒/宿主/症状/媒介/地点/方法/结果/讨论)
2. **AI Digest**: 批量论文的周/月总结
3. **RAG 问答**: 知识库驱动的植物病毒学 Q&A

### 9.6 注意事项

1. **8.25 GB PDF 存储**: pubmed_records 目录已加入 .gitignore
2. **日/周/月数据**: 通过 cron job 自动采集
3. **导出**: 支持 Excel (XLXS 库) 和 JSON 两种格式
4. **API Key**: AI 摘要使用服务端 DeepSeek key

---

## 10. Module 8: Plant-Insect

### 10.1 概述

病毒-媒介-宿主关系数据库，整合自有 VH 数据和 WUR (Wageningen University) 植物病毒传播数据库，提供三维传播关系检索。在线地址: `/vector/` (端口 5005)

### 10.2 核心文件

- **api_server.py**: Flask API 服务
- **vector_page.html**: 单页面 Web UI (含 Plotly Sankey/Heatmap/柱状图)
- **data/**: VH + WUR 整合数据 (TSV/JSON)

### 10.3 数据规模

- 1,803 个病毒条目有媒介-宿主关系
- 1,654 条 WUR 病毒传播记录
- 1,375 对病毒-媒介-宿主三元组

### 10.4 Web UI 三大标签

| 标签 | 内容 |
|:-----|:-----|
| **Vector-Host** | VH 数据库: Sankey 图 + 媒介排行 + 机制分布 + 矩阵 |
| **WUR Database** | WUR 原始数据: 媒介类别/传播模式/途径分析 |
| **Integrated Cards** | 双源合并: 按病毒名匹配，标注来源(Both/VH only/WUR only)、匹配置信度、冲突标记 |

### 10.5 数据整合逻辑

1. 按 virus canonical name 匹配 VH ↔ WUR
2. 标注 `sources: ['VH'] | ['WUR'] | ['VH','WUR']`
3. 标注 `match_confidence: 'high' | 'low'`
4. 标注 `conflict_flags` (family 不一致时)

### 10.6 可视化

- **Sankey**: Virus Family → Genus → Species → Vector Family → Genus → Species → Mechanism → Host
- **Heatmap**: Vector Category × Insect Mechanisms
- **柱状图**: Top vectors / transmission modes

---

## 11. Module 9: Metabuli

### 11.1 概述

Metabuli 宏基因组分类器 Web 界面，支持 contig 上传/粘贴，返回 8 级分类结果 + Krona/Sankey 可视化。在线地址: `/metabuli/` (端口 5004)

### 11.2 核心文件

- **metabuli_page.html**: 全功能单页面 Web UI (~2200 行 JS)，含四个分析标签
- **api_server.py**: Flask API (处理分类请求、BLAST 提交)

### 11.3 四大分析标签

| 标签 | 功能 |
|:-----|:-----|
| **Metabuli** | k-mer 分类 (910 MB 植物病毒参考库) |
| **CDD** | Conserved Domain Database 搜索 (6-frame 翻译) |
| **BLASTN** | 核酸-核酸比对 (NCBI nt, Virus-restricted) |
| **BLASTX** | 翻译核酸-蛋白比对 (NCBI nr, Virus-restricted) |

### 11.4 工作流

1. 上传 FASTA 或粘贴序列
2. 选择分析类型
3. 快速填充示例 (TMV/PVY/CMV/PSTVd/Mix)
4. 异步提交 → 轮询状态 → 渲染结果
5. 结果包含: 分类表 (8级) / Sankey 图 / Krona 图 / 病毒 contig 表 / 下载链接

### 11.5 病毒 Contig 表特性

- 每个 contig 一行
- 8 级分类 (Realm→Species)
- 长度/属平均长度
- 近完整基因组标注 (0.8 ≤ length/genus_avg_len ≤ 1.2, 绿色高亮)
- 一键跳转 CDD/BLASTN/BLASTX 分析
- 支持列表排序

### 11.6 注意事项

1. **去缓存**: HTML 含 no-cache headers
2. **结果时效**: 2 小时后自动删除
3. **Metabuli DB**: 910 MB，需预构建
4. **BLAST 限速**: NCBI BLAST 提交后需等待，最长 5 分钟轮询

---

## 12. Module 10: Virus Photos

### 12.1 概述

植物病毒病害症状照片图库，整合 EPPO、DPV、书籍、文献 PDF、Open-i 五来源共 2,975 张照片。在线地址: `/photos/`

### 12.2 目录结构

```
10.virus_photos/
├── archive/               # 归档原始采集脚本
│   └── debug/             # 调试记录
└── extracted/             # 提取后的图片
    ├── images/            # 处理后的 web 图片
    ├── all_pdf_images/    # 从 PDF 提取的所有图片
    │   └── color/         # 彩色图片子集
    └── new_virus_all/     # 新病毒图片
```

### 12.3 Web 界面

静态 HTML/JS，四视图:
- **Dashboard**: KPI 统计 + 图表 (Top Host/Top Symptom/Tissue/Virus)
- **Gallery**: 卡片式浏览，按源/宿主/症状/部位/病毒筛选
- **Data Table**: 可搜索/排序/分页的数据表格
- **Submit Correction**: GitHub Issue 模板提交元数据修正

### 12.4 元数据结构

```json
{
  "virus": "virus name",
  "virus_latin": "Latin name",
  "hosts": ["common name"],
  "hosts_latin": ["Latin host name"],
  "symptoms": ["mosaic", "ring spot"],
  "parts": ["leaf", "fruit"],
  "source": "EPPO|DPV|Book|PDF",
  "caption": "description",
  "thumb": "thumbnail path",
  "full": "full image path"
}
```

---

## 13. Module 11: Antiviral Genes

### 13.1 概述

植物免疫与 sRNA 基因图谱，包含 NLR 免疫受体、sRNA 基因、UPS 系统、miRNA 四大类别。在线地址: `/genes/gene_browser.html`

### 13.2 数据内容

| 类别 | 数量 | 来源 |
|:-----|:----:|:-----|
| NLR 免疫受体 | 415 (73 物种) | RefPlantNLR |
| sRNA 基因 | 11,780 | 文献整合 |
| UPS 基因 | 3,996 | 文献整合 |
| miRNA | 83,166 | miRBase + PlantRG + PVsiRNAdb |
| vsiRNA | 322K | PVsiRNAdb |
| 抗病毒 NLR 效应子 | 59 | 文献验证 |

### 13.3 目录结构

```
11.antiviral_genes/
├── archive/               # 归档旧脚本
└── data/                  # 数据文件
    ├── individual_queries/ # 单独查询结果
    └── plantrg_mirna/     # PlantRG miRNA 数据
```

### 13.4 实现

静态 HTML/JS 页面，四标签切换，从 JSON 数据文件加载基因列表。

---

## 14. Module 12: PAmirDB

### 14.1 概述

植物抗病毒 miRNA 靶标预测工作台，使用自研 Smith-Waterman 比对引擎 + 本地启发式复核层预测（不调用 miRanda/psRNATarget/RNAhybrid 等外部工具，历史字段名保留仅兼容）。在线地址: `/pamirdb/`

### 14.2 目录结构

```
12.pamirdb/
├── backend/               # 后端分析脚本
│   └── archive/html_variants/ # HTML 变体归档
├── data/
│   ├── mirna/             # miRNA 序列数据
│   ├── virus_genomes/     # 病毒基因组序列
│   ├── virus_host/        # 病毒-宿主关联
│   └── web/               # Web 数据
├── figures/               # 可视化图表
└── scripts/deploy/        # 部署脚本
```

### 14.3 预测方法

三算法共识:
1. **miRanda**: 基于序列互补 + 自由能的 miRNA 靶标预测
2. **psRNATarget**: 植物 sRNA 靶标分析专用工具
3. **RNAhybrid**: RNA-RNA 杂交预测

### 14.4 数据规模

- 11,006 条预计算预测（799 植物物种 × 40 病毒科；自研 SW 引擎 + 启发式复核，非外部三工具）
- 三算法取交集作为高置信度预测

---

## 15. Module 13: Virus Profile — [ARCHIVED]

> ⚠️ **此模块已归档 (2026-07)**。独立 `/virus/` 网页不再使用，系统已停用。

### 15.1 归档原因

独立 `/virus/` 服务 (:5006) 已废弃，systemd 服务 `virus-profile.service` 已停用。

### 15.2 保留文件

目录已重命名为 `_archived_13.virus_profile/`，保留 `api_server.py`、`app.py` 等源代码作为参考。

---

## 16. 静态站点 (docs/)

### 16.1 概述

Nginx 直接服务的静态文件目录，包含统一门户首页、参考数据库、症状图库、植物界 EVE 全景、基因浏览器。

### 16.2 目录结构

```
docs/
├── index.html             # 统一门户首页 → /
├── reference_index.html   # 参考数据库首页 → /reference/ (含6子页)
├── photos.html            # 症状图库 → /photos/
├── table.js               # 通用表格 JS
├── i18n.js                # 中英双语切换 JS (PVDB_i18n)
├── data/                  # 参考序列 FASTA/TSV + 图片
│   ├── book_images/       # 书籍图片
│   ├── dpv_images/        # DPV 图片
│   └── pdf_images/        # PDF 提取图片
├── literature/            # 文献追踪静态数据 → /literature/
│   └── data/monthly/      # 月度报告
├── primers/               # 引物 JSON 数据 (7,193 物种)
│   └── species/           # 按物种的 JSON
└── eve/                   # 植物界 EVE 全景 → /eve/ (2026-09-23 新增)
    ├── index.html         # 8 视角交互页 (ECharts, 中英双语)
    └── data/              # eve_landscape / dynamics / phylo JSON + _audit TSV
```

### 16.3 参考数据库交互

- 双模式切换: Full DB (199K) ↔ Ref DB (8.5K)
- Chart.js 图表: 序列类型/长度/宿主/病毒科/年份/基因组属性
- 内嵌 AI 助手 (DeepSeek API)

### 16.4 TE & EVE 数据库 (2026-09-23 已下线)

> **已下线归档**：TE（转座子）与植物病毒没有直接关系，与 `/eve/` 也不是同一分析，
> 故整个 `/te/` 已下线 —— `/te/` 与 `/te/index.html` 均 301 → `/eve/`，
> 站点目录 `docs/te/` 移出服务目录，13 个帮助页导航、门户卡片、帮助页 `te_eve.html`
> 与 sitemap 条目同步移除。归档位置：
> `archive/_pending_delete_20260923/te_offline_20260923/`。
> 以下为下线前的原始说明，仅作历史记录。

从 U-RVDB v32.0 提取的植物转座子和内源性病毒元件:
- 6 个 FASTA 下载: `plant_ncbi_eve`, `plant_rvdb.ENRV`, `plant_rvdb.EX`, `plant_envr_clean` (95% 聚类), `plant_ex_clean`, `plant_te_clean` (10,537 LTR RT)

---

## 17. 部署架构

### 17.1 服务器拓扑

```
Internet
   │
   ▼
┌─────────────────────────────────────────────────────┐
│ Nginx :80 (plant-virus.conf)                        │
│  ├── / → docs/index.html (静态)                     │
│  ├── /reference/ → docs/ (静态)                     │
│  ├── /photos/ → docs/photos.html (静态)             │
│  ├── /eve/ → docs/eve/ (静态)                       │
│  ├── /genes/ → docs/genes/ (静态)                   │
│  ├── /pamirdb/ → docs/pamirdb/ (静态)               │
│  ├── /primers/ → :5000 (gunicorn Flask)             │
│  ├── /explorer/ → :8050 (Dash)                      │
│  ├── /vector/ → :5005 (Flask)                       │
│  ├── /metabuli/ → :5004 (Flask)                     │
│  ├── /literature/ → :5003 (Flask)                   │
│  └── /knowledge/ → :5002 (uvicorn FastAPI)          │
└─────────────────────────────────────────────────────┘
```

### 17.2 服务管理

```bash
# 有 systemd 管理的服务
systemctl restart primer-web      # :5000
systemctl restart virus-explorer  # :8050
systemctl restart vector-host     # :5005
systemctl restart metabuli-api    # :5004
systemctl restart literature-tracker # :5003

# 非 systemd 服务
# Knowledge RAG: nohup + uvicorn :5002
```

### 17.3 项目根目录

- 本地: `D:\桌面\C-host_classify\plant_virus_db_pipeline`
- 服务器: `/opt/plant_virus_db/plant_virus_db_pipeline`

### 17.4 代码-服务器路径差异

| 模块 | 本地路径 | 服务器路径 |
|:-----|:-----|:-----|
| Primers | 4.virus_primer/ | /opt/plant_virus_db/primer_design_server/ |
| Knowledge RAG | 6.knowledge_rag/ | /opt/src/plant_virus_rag/ |

---

## 18. 注意事项与已知问题

### 18.1 重要约定

1. **改动原则**: 仔细、可排查、可回滚；修改前核对本地与服务器一致性
2. **不主动 commit**: 除非明确要求
3. **时区**: Asia/Shanghai (UTC+8)
4. **大文件**: PDF、TSV、数据库文件已加入 .gitignore，需手动同步
5. **python 环境**: 优先使用 pixi 管理，`pixi run python` 而非系统 python

### 18.2 已知遗留 Bug

| Bug | 影响模块 | 状态 |
|:----|:---------|:----:|
| `/knowledge/query` 偶发 500 (DB 返回 str 而非 list) | Knowledge RAG | 待修 |
| Dash explorer 回调偶发序列化错误 | Virus Explorer | 观察中 |
| primer 设计服务 Olivar 位置偏移 | Virus Primer | 已 patch |

### 18.3 运行依赖

- **操作系统**: Linux (生产), Windows (开发)
- **Python**: 3.10-3.12
- **外部工具**: BLAST+, Diamond, MMseqs2, Kraken2, Metabuli, MAFFT, VSEARCH, Jellyfish
- **数据库**: NCBI Taxonomy, NCBI nt/nr (BLAST), 910 MB Metabuli DB
- **GPU**: 不需要
- **内存**: 建议 ≥ 64GB (RAG 向量库 + 全量序列)
- **磁盘**: ≥ 200GB (含 NCBI nt ≥ 150GB)

### 18.4 数据更新

数据版本记录在 `docs/data/DATA_VERSION`:
```
VERSION=x.x.x
SOURCE_ICTV=MSL41
RECORDS_TOTAL=198,885
```

运行 `python config.py` 可检查当前所有数据文件存在状态。

### 18.5 常用操作速查

```bash
# 检查数据文件
python config.py

# 重启所有服务
systemctl restart primer-web virus-explorer vector-host metabuli-api literature-tracker

# 重启 Knowledge RAG
fuser -k 5002/tcp
cd /opt && PATH=/opt/miniconda3/envs/pv_rag/bin:$PATH \
  nohup python -m uvicorn plant_virus_rag.api.main:create_pv_app \
  --factory --host 0.0.0.0 --port 5002 > /opt/pv_rag_api.log 2>&1 &

# 重载 Nginx
nginx -t && nginx -s reload

# 查看服务日志
journalctl -u primer-web -f
```

---

> **报告结束** — 共覆盖 13 个功能模块、17 种分类器、7 大流水线阶段、10+ 个 Web 服务端点。
