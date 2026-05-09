<!-- omit in toc -->
# 植物病毒基因组数据库构建流程

> **Plant Virus Genome Database Construction Pipeline**
>
> 从 NCBI、KEGG、ICTV 三大数据源出发，经过元数据整合 → 宿主分类 → 序列提取 → 去冗余 → 聚类评估，最终构建高质量非冗余植物病毒参考基因组数据库。

---

<!-- toc -->
- [引言](#引言)
- [快速开始](#快速开始)
- [工作目录结构](#工作目录结构)
- [执行概览](#执行概览)
- [数据流图](#数据流图)
- [A. 元数据整合](#a-元数据整合)
- [B. ICTV 宿主拆分](#b-ictv-宿主拆分)
- [C. 宿主信息整合](#c-宿主信息整合)
- [D. 序列获取](#d-序列获取)
- [E. 元数据完善](#e-元数据完善)
- [F. 分类与去冗余](#f-分类与去冗余)
- [G. 最终聚类与评估](#g-最终聚类与评估)
- [原始数据下载](#原始数据下载)
- [依赖软件安装](#依赖软件安装)
<!-- tocstop -->

---

## 引言

### 背景与意义

植物病毒 (Plant viruses) 是引起全球农作物减产的主要病原之一，每年造成的经济损失高达数百亿美元。随着高通量测序技术的发展，公共数据库中植物病毒序列数据呈指数级增长。然而，这些数据分散于不同来源，存在严重的冗余、命名不一致和宿主信息缺失等问题，给下游的宏病毒组分类、系统发育分析和分子检测引物设计造成了极大障碍。

构建一个高质量、非冗余、可追溯的植物病毒参考基因组数据库，对于提升植物病毒鉴定精度、促进比较基因组学研究和支撑植物检疫决策具有重要的基础性意义。

本数据库的构建涉及两条并行的信息主线: **(一) 植物病毒序列数据的整理**——从公共数据库中提取、分类、去冗余植物病毒基因组序列；**(二) 植物病毒宿主信息的整理**——从多源宿主标注数据中整合、校验、补全病毒-宿主关联关系。以下分别介绍两条主线所依赖的外部数据资源。

### 一、植物病毒参考序列数据库

高质量植物病毒的参考序列数据库是构建病毒参考基因组的基石。我们对当前国际主流的植物病毒参考序列数据库进行了系统调研。

**NCBI Virus (NCBI 病毒门户).** NCBI Virus 门户 [https://www.ncbi.nlm.nih.gov/labs/virus/vssi/] 通过宿主谱系筛选 (HostLineage_ss: Viridiplantae, taxid:33090) 可获取约 6,234 个植物相关病毒物种、162,836 条核酸序列。NCBI 同时通过 FTP 提供全量病毒核酸数据 (AllNucleotide.fa.gz, ~277 Gb) 和元数据 (AllNuclMetadata.csv)。该数据库的优势在于数据体量最大、更新持续，但宿主标注系自动化流程生成，存在一定比例的错误。

**VirusDetect 植物病毒数据库.** VirusDetect [http://virusdetect.feilab.net/] 由康奈尔大学 Fei 实验室维护，最新版本 V267 (2025-08-06)。通过 100%/97%/95% 三级序列一致性去冗余，为每个宿主界生成独特病毒序列库。以 vrl_Plants_267_U97 为例，经 Viridiplantae 谱系校验后，46,894 条序列中 29,979 条 (63.9%) 确认为植物宿主，其余为非 Viridiplantae 序列，表明基于序列相似性分类存在宿主边界溢出。

**PlantVirusBase (植物病毒基准数据库).** PlantVirusBase [http://47.90.94.155/PlantVirusBase] (2025-05-08) 收录 3,353 种植物病毒和 9,010 个病毒-植物宿主关联。Yang 等 (2025, *Plant Disease*) 的分析表明双链 DNA 病毒宿主范围更广，但包膜类型、基因组大小或传播方式与宿主范围之间仅存弱关联 [https://apsjournals.apsnet.org/doi/epdf/10.1094/PDIS-07-25-1393-SR]。

**PVirDB.** PVirDB [https://zenodo.org/records/6609576] (2022-06-03) 收录 4,463 个植物病毒物种、50,611 条核酸序列，以 FASTA 格式分发 (头部格式: ">accession|taxid|description")。

**Virtool.** Virtool [https://github.com/virtool/ref-plant-viruses] v1.5.0 收录 2,084 种植物病毒、4,783 个组装，以 JSON 格式分发。

**ViralZone Virosaurus.** ViralZone [https://viralzone.expasy.org/8676] 植物病毒子集 (2020-03-30) 收录 1,230 种、6,038 条代表性序列，头部含 Swiss-Prot 注释。

**DPVweb.** DPVweb [https://www.dpvweb.net/] 收录植物病毒/类病毒/卫星序列 37,076 条，感染真菌和原生动物病毒 438 条，动物病毒 1,620 条，噬菌体 123 条。

**PhytoPipe.** PhytoPipe [https://github.com/healthyPlant/PhytoPipe] 基于 ICTV VMR 和 VHDB 的内置参考列表收录 3,253 种植物病毒 TaxID。

#### 参考序列数据库汇总

| 数据库 | 版本/日期 | 物种数 | 序列数 | 去冗余策略 | 更新状态 | URL |
|:--------|:----------|:------:|:------:|:-----------|:---------|:-----|
| **NCBI Virus** | 持续更新 | 6,234 | 162,836 | 无 | 持续 | [ncbi.nlm.nih.gov](https://www.ncbi.nlm.nih.gov/labs/virus/vssi/) |
| **VirusDetect** | V267 (2025-08) | — | 128,956 | 100%/97%/95% | 定期 | [virusdetect.feilab.net](http://virusdetect.feilab.net/) |
| **PlantVirusBase** | 2025-05 | 3,353 | — | 未公开 | 2025-05 | [47.90.94.155](http://47.90.94.155/PlantVirusBase) |
| **PVirDB** | 2022-06 | 4,463 | 50,611 | 无 | 已停更 | [zenodo.org](https://zenodo.org/records/6609576) |
| **Virtool** | v1.5.0 | 2,084 | 4,783 | OTU 聚类 | 定期 | [github.com/virtool](https://github.com/virtool/ref-plant-viruses) |
| **ViralZone** | 2020-03 | 1,230 | 6,038 | 98% | 已停更 | [viralzone.expasy.org](https://viralzone.expasy.org/8676) |
| **DPVweb** | — | — | 37,076 | 无 | 持续 | [dpvweb.net](https://www.dpvweb.net/) |
| **PhytoPipe** | — | 3,253 | — | 无 | 随 VMR 更新 | [github.com/healthyPlant](https://github.com/healthyPlant/PhytoPipe) |
| **本研究** | MSL41 (2026) | — | — | 瀑布流+seqkit(100%)+mmseqs(98%)+vclust | — | [github.com/zhangwenda0518](https://github.com/zhangwenda0518/plant_virus_db_pipeline) |

> "—" = 未获取或未统计；物种数统计口径各数据库不一致。

### 二、植物病毒宿主信息源

病毒参考序列的准确宿主标注是数据库质量的核心。本研究整合以下四类宿主信息源，以最大化宿主覆盖度与可信度。

**NCBI VHostMetadata (自动标注).** NCBI 通过 FTP 提供病毒宿主关联元数据 [https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllDataTmp/]，约 1,824 条记录通过宿主谱系 (Host_lineage) 推导 Viridiplantae 关联。优势在于与序列数据库直接关联、持续更新，但自动化标注存在误标风险。

**KEGG Virus-Host DB (文献溯源).** KEGG Virus-Host DB [https://www.genome.jp/virushostdb/] 由京都大学维护，通过人工整理公开发表的病毒-宿主文献关联构建 [https://www.genome.jp/ftp/db/virushostdb/]。经 Viridiplantae 关键词筛选获得 2,555 条记录。相较于 NCBI 自动标注，文献溯源机制可信度更高，但收录范围受限于已发表文献。

**ICTV VMR Host Source (分类学权威).** ICTV 官方发布的 VMR [https://ictv.global/vmr] 包含 Host source 字段，具有分类学权威性，但大量记录标注为 "unknown"/"other"，需结合 NCBI Host_lineage 进行拉丁文文本抢救 (暗物质抢救)。

**EPPO Global Database (检疫认证).** 欧洲和地中海植物保护组织全球数据库 [https://gd.eppo.int/datasheets/] 收录植物有害生物 (含病毒) 的分类、分布和宿主植物信息，宿主范围经人工审核，尤其适用于检疫性植物病毒的宿主界定。

#### 宿主信息源汇总

| 宿主信息源 | 植物相关记录 | 标注方式 | 权威性 | 更新 | URL |
|:-----------|:-----------:|:---------|:------:|:----|:-----|
| **NCBI VHostMetadata** | 1,824 | 自动 NCBI 谱系推导 | 中 | 持续 | [ftp.ncbi.nlm.nih.gov](https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllDataTmp/) |
| **KEGG Virus-Host DB** | 2,555 | 人工文献整理 | 高 | 周期性 | [genome.jp/virushostdb](https://www.genome.jp/virushostdb/) |
| **ICTV VMR (MSL41)** | 字段决定 | 编审 + 自动混合 | 高 | 按发布周期 | [ictv.global/vmr](https://ictv.global/vmr) |
| **EPPO Global Database** | — | 人工审核 | 高 | 持续 | [gd.eppo.int](https://gd.eppo.int/datasheets/) |

> NCBI 1,824 = 门户 Viridiplantae 严格匹配；KEGG 2,555 = virushostdb.tsv 中 Host 字段含 Viridiplantae。均非唯一物种数，供参考宿主信息覆盖度。

### 现有数据库的局限性

尽管上述数据库在一定程度上满足了植物病毒研究的参考需求，但均存在若干共性问题: (1) 多数数据库未提供完整的层次化分类学谱系 (Realm → Species)，限制了系统发育下游分析；(2) 去冗余策略多为单一阈值 (97%/98%)，缺乏多维度的层级瀑布流 (waterfall) 去重机制；(3) 节段病毒 (segmented viruses) 的各节段在去冗余时易被误合并，导致节段信息丢失；(4) 宿主信息与病毒元数据未进行系统性交叉验证；(5) 数据库更新频率不一致，部分数据库 (如 ViralZone 2020、PVirDB 2022) 已长期未更新。

### 本研究的构建策略

基于上述调研，本研究以 NCBI 全量病毒序列 (AllNucleotide.fa.gz) 和病毒-宿主关联元数据 (VHostMetadata + AllNuclMetadata) 为基础数据源，辅以 KEGG Virus-Host DB 的宿主信息增强和 ICTV VMR (MSL41) 的权威分类校准，采用七阶段 (A-G) 流程化处理策略: (1) 多源元数据整合与宿主信息补全，(2) ICTV 宿主分类与暗物质抢救，(3) 宿主谱系交叉填补与全量分类，(4) 植物病毒序列定向提取与缺失补全，(5) 多维元数据完善 (拓扑结构/分子类型/NCBI 命名)，(6) 层级化分类与双引擎去冗余 (元数据瀑布流 + seqkit/mmseqs 序列聚类)，以及 (7) 泛基因组 ANI 聚类与基因覆盖度评估。最终产出为非冗余、可追溯、附完整谱系注释的植物病毒参考基因组数据集。

---

## 快速开始

```bash
# 1. 下载原始数据 (详见「原始数据下载」章节)

# 2. 仅检查前置条件
bash run_all.sh --check

# 3. 最小运行（仅邮箱必填）
bash run_all.sh -e your_email@example.com

# 4. 完整配置运行
bash run_all.sh \
  -w ~/plant_virus_db \
  -r ~/plant_virus_db/raw_data \
  -d ~/database \
  -e your_email@example.com \
  -k your_ncbi_api_key \
  -p 60 \
  -m 32

# 5. 中断后断点续跑
bash run_all.sh -e your_email@example.com   # 已完成步骤自动跳过

# 6. 生成学术总结报告
python summarize_pipeline.py --work-dir ~/plant_virus_db
```

| 参数 | 简写 | 默认值 | 说明 |
|:-----|:-----|:-----|:-----|
| `--email` | `-e` | — **(必填)** | NCBI E-utilities 邮箱 |
| `--work-dir` | `-w` | `$HOME/plant_virus_db` | 工作目录，所有产物输出位置 |
| `--raw-dir` | `-r` | `<work_dir>/raw_data` | 原始下载数据目录 |
| `--db-dir` | `-d` | `$HOME/database` | 本地数据库根目录 |
| `--taxonomy-dir` | `-t` | `<db_dir>/taxonomy` | NCBI Taxonomy 数据目录 |
| `--api-key` | `-k` | — | NCBI API Key (提升请求频率) |
| `--ncpu` | `-p` | 60 | 通用并行线程数 |
| `--mmseqs-threads` | `-m` | 32 | MMseqs2 聚类线程数 |
| `--taxonkit` | — | `taxonkit` | taxonkit 可执行文件路径 |

## 工作目录结构

运行 `run_all.sh` 后，输出按阶段组织：

```
plant_virus_db/
├── 00_logs/                         # ★ 所有阶段运行日志
│   ├── pipeline.log                 # 总时间线 (全部步骤概览)
│   ├── A1-数据质检.log              # 列名/空值率/唯一值统计
│   ├── A2-VHDB+NCBI合并.log         # 合并后序列数、TaxID 增量
│   ├── A3-宿主补全.log              # 补全前后缺失行数、找回率
│   ├── A4-添加谱系.log              # taxonkit 进度、缓存命中数
│   ├── B2-VMR宿主拆分.log           # VMR 暗物质抢救记录
│   ├── C1-宿主信息提取.log          # 交叉填补、Taxid 匹配、联网兜底
│   ├── C2-宿主分类.log              # 各宿主分类行数 (Human/Animal/Plant/...)
│   ├── D1-比对提取FASTA.log         # 本地命中数、缺失数
│   ├── D2-下载缺失序列.log          # 下载成功/失败数
│   ├── E1-提取元数据.log            # 本地匹配、在线补充数量
│   ├── E2-获取拓扑结构.log          # NCBI API 批次进度
│   ├── F1-基础统计.log              # 序列数/TaxID/长度/完整度/分子类型
│   ├── F2-节段分类拆分.log          # 节段/非节段分类战报、同源兜底挽救
│   ├── F3-元数据去重.log            # 各优先级保留/丢弃行数
│   ├── F4a-非节段去冗余.log         # seqkit rescue + mmseqs conflict + RefSeq swap
│   ├── F4b-节段去冗余.log           # 同上(节段模式)
│   ├── G1-SeqID→TaxID映射.log       # 查找映射数量、命中率
│   ├── G2-vclust聚类.log            # ★ 最重要: LCA 混合比例、RefSeq 替换、去冗余率
│   ├── G3-去冗余评估.log            # 各阶段序列/TaxID 保留率对比
│   ├── G4a-基因预测.log             # pyrodigal 预测进度
│   └── G4b-覆盖度计算.log           # 基因覆盖度统计
├── raw_data/                        ← 原始下载数据
├── 01_merge/                        ← 阶段 A 产物
│   ├── summary.csv                  # 数据质检报告
│   ├── Merged.VHostMetadata.tsv     # VHDB+NCBI 合并结果
│   ├── Merged.VHostMetadata.imputer.tsv  # 宿主补全后
│   ├── Merged.VHostMetadata.lineage.tsv  # 添加谱系后
│   └── bad_rows_log.tsv             # 脏行记录
├── 02_ictv/                         ← 阶段 B 产物
│   ├── VMR_MSL41.tsv                # ICTV VMR TSV 格式
│   ├── VMR_Split_By_Host/           # 按宿主拆分的 VMR
│   └── Rescue_Failed_Details.tsv    # 抢救失败诊断
├── 03_host/                         ← 阶段 C 产物
│   ├── host_extract/                # 宿主信息提取
│   │   ├── Final_Virus_Host_Lineage.tsv
│   │   ├── Unresolved_AllNucl.tsv   # 无法解决的 AllNucl 记录
│   │   └── Unresolved_VHost.tsv     # 无法解决的 VHost 记录
│   └── VHostMetadata/               # 按宿主分类的数据
│       ├── Summary_Counts.tsv
│       ├── Plant.tsv                # ★ 植物病毒列表
│       └── Human/Animal/...tsv
├── 04_sequences/                    ← 阶段 D 产物
│   ├── plant.virus.fasta            # ★ 植物病毒合并序列
│   ├── plant.virus.id               # Accession ID 列表
│   └── Plant_virus_db/              # 中间文件(含缺失列表)
├── 05_metadata/                     ← 阶段 E 产物
│   ├── Plant_Virus_Info.tsv         # ★ 完整元数据表
│   ├── Plant_Virus_Info.summary     # 统计报告
│   └── consistency_check.log        # Title/Length 一致性比对
│   └── Plant_Virus_Topology_...tsv  # 拓扑信息
├── 06_dedup/                        ← 阶段 F 产物
│   ├── split_results/               # 节段分类拆分结果
│   ├── virus.dedup/                 # 元数据去重结果
│   ├── Final_DB_Build/              # ★ seqkit+mmseqs 去冗余产物
│   └── plant.final.rmdup.fasta      # ★ 合并去冗余序列
└── 07_cluster/                      ← 阶段 G 最终产物
    ├── final.cluster.ref.fasta      # ★★★ 最终参考基因组
    ├── final.cluster.ref_info.tsv   # ★★★ 最终元数据
    ├── virus_genes_cov.tsv          # 基因覆盖度
    ├── clusters_with_LCA.tsv        # LCA 诊断报告
    ├── clusters.LCA_Distribution.png # LCA 分布图
    └── derep.summary.tsv            # 去冗余全流程评估
```

## 执行概览

```
A 元数据整合
  ├── A1 数据质检  →  A2 VHDB+NCBI合并  →  A3 宿主补全  →  A4 谱系添加
B ICTV宿主拆分
  └── B1 解析VMR + 按宿主分类 + 暗物质抢救
C 宿主信息整合
  ├── C1 交叉填补宿主  →  C2 全量宿主分类
D 序列获取
  ├── D1 比对本地FASTA  →  D2 下载缺失序列
E 元数据完善
  ├── E1 提取+补全  →  E2 拓扑结构  →  E3 合并拓扑  →  E4 NCBI物种名
F 分类与去冗余
  ├── F1 统计报告  →  F2 节段分类  →  F3 元数据去重  →  F4 双引擎聚类去冗余
G 最终聚类与评估
  └── G1 TaxID映射  →  G2 vclust聚类  →  G3 去重评估  →  G4 基因覆盖度
```

---

## 数据流图

```
NCBI FTP                  KEGG FTP                ICTV
    │                         │                      │
    ▼                         ▼                      ▼
AllNucleotide.fa.gz    virushostdb.tsv     VMR_MSL41.xlsx
AllNuclMetadata.csv                              │
VHostMetadata.tsv                                ▼
    │                                    xlsx2csv → VMR.tsv
    ▼                                         │
  [A] 元数据整合 ◄─────────────────────────────┘
    │
    ▼
  [B] Merged.VHostMetadata.lineage.tsv ──→ VMR_Split_By_Host/
    │
    ▼
  [C] Final_Virus_Host_Lineage.tsv ──→ Human/Animal/Plant/...tsv
    │
    ▼
  [D] plant.virus.fasta + plant.virus.id
    │
    ▼
  [E] Plant_Virus_Info.tsv (含 topo + name)
    │
    ▼
  [F] split_results/ → virus.dedup/ → Final_DB_Build/
    │
    ▼
  [G] final.cluster.ref.fasta + virus_genes_cov.tsv
```

---

## A. 元数据整合

| 序号 | 脚本 | 输入 | 输出 | 功能 |
|:-----|:-----|:-----|:-----|:-----|
| A1 | `A1_check_data.py` | `VHostMetadata.tsv` | `summary.csv` | 列名/唯一值/空值率检查 |
| A2 | `A2_merge_vhost_vhdb.py` | `virushostdb.tsv` + `VHostMetadata.tsv` | `Merged.VHostMetadata.tsv` | VHDB 优先合并，继承 NCBI 版本号 |
| A3 | `A3_vhost_imputer.py` | `Merged.VHostMetadata.tsv` | `Merged.VHostMetadata.imputer.tsv` | 基于 Taxid/Virus_Name 补全缺失宿主 |
| A4 | `A4_add_lineage.py` | `Merged.VHostMetadata.imputer.tsv` | `Merged.VHostMetadata.lineage.tsv` | taxonkit 添加 9 级完整谱系 |

---

## B. ICTV 宿主拆分

| 序号 | 脚本 | 输入 | 输出 | 功能 |
|:-----|:-----|:-----|:-----|:-----|
| B1 | `xlsx2csv` + `csvformat` | `VMR_MSL41.v1.20260320.xlsx` | `VMR_MSL41.v2.tsv` | Excel → TSV 转换 |
| B2 | `B1_vmr_split_by_host.py` | `VMR_MSL41.v2.tsv` + 谱系表 | `VMR_Split_By_Host/{Plant,...}.tsv` | 按宿主分类 + NCBI 暗物质抢救 |

---

## C. 宿主信息整合

| 序号 | 脚本 | 输入 | 输出 | 功能 |
|:-----|:-----|:-----|:-----|:-----|
| C1 | `C1_virus_host_info_extract.py` | AllNuclMetadata + 谱系表 | `Final_Virus_Host_Lineage.tsv` | 交叉填补 + Taxid 匹配 + 联网兜底 |
| C2 | `C2_classify_by_host.py` | Final 表 + AllNuclMetadata | `VHostMetadata/{Human,Plant,...}.tsv` | 按宿主精细分类 |

---

## D. 序列获取

| 序号 | 脚本 | 输入 | 输出 | 功能 |
|:-----|:-----|:-----|:-----|:-----|
| D1 | `D1_extract_and_check_fasta.py` | `Plant.tsv` + `AllNucleotide.fa.gz` | 已有/缺失 序列 + 列表 | Hash Join 比对，seqkit 高速提取 |
| D2 | `D2_download_missing.py` | 缺失 Accession 列表 | `Downloaded_Plant_Viruses.fasta` | NCBI efetch 全量下载，支持断点续传 |

---

## E. 元数据完善

| 序号 | 脚本 | 输入 | 输出 | 功能 |
|:-----|:-----|:-----|:-----|:-----|
| E1 | `E1_extract_metadata.py` | `plant.virus.id` + AllNuclMetadata | `Plant_Virus_Info.tsv` | 本地提取 + 在线补全缺失记录 |
| E2 | `E2_fetch_topology.py` | `plant.virus.id` | `Plant_Virus_Topology...info.tsv` | NCBI 批量获取 Topology + Molecule_Type |
| E3 | `E3_merge_topology.py` | Topo 表 + Plant_Virus_Info | 更新后的 Info 表 | Topology 信息合并 |
| E4 | `E4_add_ncbi_names.py` | `Plant_Virus_Info.tsv` + names.dmp | 更新后的 Info 表 | 补充 NCBI 物种学名 |

---

## F. 分类与去冗余

| 序号 | 脚本 | 输入 | 输出 | 功能 |
|:-----|:-----|:-----|:-----|:-----|
| F1 | `F1_analyze_summary.py` | `Plant_Virus_Info.tsv` | 统计报告 | 序列数/TaxID/长度/完整度统计 |
| F2 | `F2_classify_segmented.py` | Info 表 + VMR + FASTA | `split_results/` | 节段/非节段双层分类 + FASTA 拆分 |
| F3 | `F3_metadata_dedup.py` | 分类后的 Info + FASTA | `virus.dedup/` | TaxID 瀑布流去重 + Segment 补全 |
| F4 | `F4_seqkit_mmseqs_rescue.py` | 去重后 FASTA + Info | `Final_DB_Build/` | seqkit 100% + mmseqs 0.98 双引擎去冗余 |

---

## G. 最终聚类与评估

| 序号 | 脚本 | 输入 | 输出 | 功能 |
|:-----|:-----|:-----|:-----|:-----|
| G1 | `G1_seqid_to_taxid.py` | `plant.final.rmdup.id` + 映射表 | `seqid2taxid.map` | 高性能 Accession → TaxID 并行映射 |
| G2 | `G2_vclust_cluster.py` | FASTA + Info + Map | `final.cluster.ref.fasta` | vclust ANI 聚类 + LCA 诊断 + RefSeq 优先 |
| G3 | `G3_derep_evaluate.py` | 各级 FASTA + Info | 多维度评估报告 | 去冗余前后序列/物种保留率比较 |
| G4 | `G4_gene_coverage.py` | GFF3 + seqid2taxid | `virus_genes_cov.tsv` | 基因长度与覆盖度统计 |

---

## 原始数据下载

```bash
# === 创建工作目录 ===
mkdir -p ~/database/taxonomy
mkdir -p ~/plant_virus_db/raw_data
cd ~/plant_virus_db/raw_data

# === NCBI 病毒序列 (约 277G) ===
wget https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllNucleotide/AllNucleotide.fa.gz

# === NCBI 病毒元数据 (约 2G) ===
wget https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllNuclMetadata/AllNuclMetadata.csv.gz
gunzip AllNuclMetadata.csv.gz

# === NCBI 病毒宿主关联表 (约 500M) ===
wget https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllDataTmp/VHostMetadata.tsv

# === KEGG Virus-Host DB (约 1.5G) ===
wget https://www.genome.jp/ftp/db/virushostdb/virushostdb.tsv

# === ICTV VMR (定期更新) ===
# 当前最新: MSL41 (2026-03-20)
wget https://ictv.global/sites/default/files/VMR/VMR_MSL41.v1.20260320.xlsx

# === NCBI Taxonomy dump (约 71M) ===
wget https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz -O ~/database/taxonomy/taxdump.tar.gz
tar -xzf ~/database/taxonomy/taxdump.tar.gz -C ~/database/taxonomy/

# === NCBI Accession → TaxID 映射 (约 50G) ===
wget https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/accession2taxid/nucl_gb.accession2taxid.gz
gunzip nucl_gb.accession2taxid.gz -d ~/database/taxonomy/
```

| 文件 | 来源 | 大小 | 用途 |
|:-----|:-----|:-----|:-----|
| `AllNucleotide.fa.gz` | NCBI FTP | ~277G | 全量病毒 FASTA 序列 |
| `AllNuclMetadata.csv` | NCBI FTP | ~2G | 病毒元数据 (物种/宿主/长度等) |
| `VHostMetadata.tsv` | NCBI FTP | ~500M | NCBI 病毒-宿主关联 |
| `virushostdb.tsv` | KEGG | ~1.5G | VHDB 病毒-宿主数据库 |
| `VMR_MSL41.v1.20260320.xlsx` | ICTV | ~4M | ICTV 官方病毒分类与宿主 |
| `taxdump.tar.gz` | NCBI Taxonomy | ~71M | names.dmp / nodes.dmp 等 |
| `nucl_gb.accession2taxid` | NCBI Taxonomy | ~50G | Accession → TaxID 完整映射 |

**总下载量约 330G+**，建议在服务器端用 `screen`/`tmux` 后台执行。

---

## 依赖软件安装

### Python 库

```bash
pip install polars biopython pandas ete3 requests tqdm matplotlib seaborn
```

### taxonkit

> NCBI Taxonomy 谱系解析，用于 A4/C1/C2

```bash
wget https://github.com/shenwei356/taxonkit/releases/download/v0.15.0/taxonkit_linux_amd64.tar.gz
tar -xzf taxonkit_linux_amd64.tar.gz
mv taxonkit ~/bin/
```

### seqkit

> FASTA 去冗余与序列提取，用于 D1/F4

```bash
wget https://github.com/shenwei356/seqkit/releases/download/v2.8.0/seqkit_linux_amd64.tar.gz
tar -xzf seqkit_linux_amd64.tar.gz
mv seqkit ~/bin/
```

### MMseqs2

> 序列相似度聚类，用于 F4/G2

```bash
conda install -c conda-forge -c bioconda mmseqs2
# 或二进制安装
wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz
tar -xzf mmseqs-linux-avx2.tar.gz
mv mmseqs/bin/mmseqs ~/bin/
```

### vclust

> 泛基因组 ANI 聚类 + LCA 诊断，用于 G2

```bash
wget https://github.com/refresh-bio/vclust/releases/download/v1.0.0/vclust_linux_x86-64.tar.gz
tar -xzf vclust_linux_x86-64.tar.gz
mv vclust ~/bin/
```

### pyrodigal

> 病毒基因预测，提供 `pyrodigal-rv`，用于 G4

```bash
pip install pyrodigal
```

### csvkit

> Excel → TSV 转换 (`xlsx2csv` + `csvformat`)，用于 B1

```bash
pip install csvkit
```

### 依赖速查

| 工具 | 版本 | 安装方式 | 使用位置 |
|:-----|:-----|:-----|:-----|
| `polars` | >=0.20 | pip | A~G 全流程 |
| `biopython` | >=1.80 | pip | E2/E4 (Entrez/SeqIO) |
| `pandas` | >=2.0 | pip | G2/G3 |
| `ete3` | >=3.1 | pip | G2 (LCA 计算) |
| `requests` | >=2.28 | pip | C1 (NCBI API 兜底) |
| `tqdm` | >=4.64 | pip | G1 (进度条) |
| `matplotlib` | >=3.5 | pip | G2 (LCA 绘图) |
| `seaborn` | >=0.12 | pip | G2 (图表美化) |
| `taxonkit` | >=0.15 | binary | A4/C1/C2 |
| `seqkit` | >=2.5 | binary | D1/F4 |
| `mmseqs` | >=14 | conda/binary | F4/G2 |
| `vclust` | >=1.0 | binary | G2 |
| `pyrodigal` | >=3.0 | pip | G4 |
| `csvkit` | >=1.0 | pip | B1 |
