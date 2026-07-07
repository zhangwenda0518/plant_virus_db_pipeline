<!-- omit in toc -->
# 植物病毒基因组数据库构建流程

> **Plant Virus Genome Database Construction Pipeline**
>
> 从 NCBI、KEGG、ICTV 三大数据源出发，经过元数据整合 → 宿主分类 → 序列提取 → 去冗余 → 聚类评估，最终构建高质量非冗余植物病毒参考基因组数据库。

---

<!-- toc -->
- [引言](#引言)
- [构建结果摘要](#构建结果摘要)
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

本数据库的构建涉及两条逻辑主线: **(一) 植物病毒宿主信息的整理**——从多源宿主标注数据中整合、校验、补全病毒-宿主关联关系；**(二) 植物病毒序列数据的整理**——基于宿主信息从公共序列库中提取、分类、去冗余植物病毒基因组序列。先宿主后序列，以下依次介绍。

### 一、植物病毒宿主信息源

准确界定病毒的植物宿主范围是构建数据库的核心前提。本研究整合以下四类宿主信息源，以最大化宿主覆盖度与可信度。

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

### 二、植物病毒参考序列数据库

基于上述宿主信息确定目标 Accession 后，从公共序列数据库中提取对应的核酸序列。我们对当前国际主流的植物病毒参考序列数据库进行了系统调研。

**NCBI Virus (NCBI 病毒门户).** NCBI Virus 门户 [https://www.ncbi.nlm.nih.gov/labs/virus/vssi/] 通过宿主谱系筛选可获得约 6,234 个植物相关病毒物种、162,836 条核酸序列。NCBI 同时通过 FTP 提供全量病毒核酸数据 (AllNucleotide.fa.gz, ~277 Gb) 和元数据 (AllNuclMetadata.csv)。该数据库数据体量最大、更新持续，是本流程的主要序列来源。

**VirusDetect 植物病毒数据库.** VirusDetect [http://virusdetect.feilab.net/] 由康奈尔大学 Fei 实验室维护，最新版本 V267 (2025-08-06)。通过 100%/97%/95% 三级序列一致性去冗余，为每个宿主界生成独特病毒序列库。以 vrl_Plants_267_U97 为例，经 Viridiplantae 谱系校验后，46,894 条序列中 29,979 条 (63.9%) 确认为植物宿主，表明基于序列相似性分类存在宿主边界溢出。

**PlantVirusBase (植物病毒基准数据库).** PlantVirusBase [http://47.90.94.155/PlantVirusBase] (2025-05-08) 收录 3,353 种植物病毒和 9,010 个病毒-植物宿主关联。Yang 等 (2025, *Plant Disease*) 分析表明双链 DNA 病毒宿主范围更广，但包膜类型、基因组大小或传播方式与宿主范围之间仅存弱关联 [https://apsjournals.apsnet.org/doi/epdf/10.1094/PDIS-07-25-1393-SR]。

**PVirDB.** PVirDB [https://zenodo.org/records/6609576] (2022-06-03) 收录 4,463 个植物病毒物种、50,611 条核酸序列，以 FASTA 格式分发 (头部格式: ">accession|taxid|description")。

**Virtool.** Virtool [https://github.com/virtool/ref-plant-viruses] v1.5.0 收录 2,084 种植物病毒、4,783 个组装，以 JSON 格式分发。

**ViralZone Virosaurus.** ViralZone [https://viralzone.expasy.org/8676] 植物病毒子集 (2020-03-30) 收录 1,230 种、6,038 条代表性序列。

**DPVweb.** DPVweb [https://www.dpvweb.net/] 收录植物病毒/类病毒/卫星序列 37,076 条。

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

### 现有数据库的局限性

尽管上述数据库在一定程度上满足了植物病毒研究的参考需求，但均存在若干共性问题: (1) 多数数据库未提供完整的层次化分类学谱系 (Realm → Species)，限制了系统发育下游分析；(2) 去冗余策略多为单一阈值 (97%/98%)，缺乏多维度的层级瀑布流 (waterfall) 去重机制；(3) 节段病毒 (segmented viruses) 的各节段在去冗余时易被误合并，导致节段信息丢失；(4) 宿主信息与病毒元数据未进行系统性交叉验证；(5) 数据库更新频率不一致，部分数据库 (如 ViralZone 2020、PVirDB 2022) 已长期未更新。

### 本研究的构建策略

基于上述调研，本研究以 NCBI 全量病毒序列 (AllNucleotide.fa.gz) 和病毒-宿主关联元数据 (VHostMetadata + AllNuclMetadata) 为基础数据源，辅以 KEGG Virus-Host DB 的宿主信息增强和 ICTV VMR (MSL41) 的权威分类校准，采用七阶段 (A-G) 流程化处理策略: (1) 多源元数据整合与宿主信息补全，(2) ICTV 宿主分类与暗物质抢救，(3) 宿主谱系交叉填补与全量分类，(4) 植物病毒序列定向提取与缺失补全，(5) 多维元数据完善 (拓扑结构/分子类型/NCBI 命名)，(6) 层级化分类与双引擎去冗余 (元数据瀑布流 + seqkit/mmseqs 序列聚类)，以及 (7) 泛基因组 ANI 聚类与基因覆盖度评估。最终产出为非冗余、可追溯、附完整谱系注释的植物病毒参考基因组数据集。

---

### 4.1 元数据整合与宿主分类

本研究以 NCBI GenBank 全量病毒核酸序列 (AllNucleotide.fa.gz, ~277 Gb) 及其元数据 (AllNuclMetadata.csv, ~2 Gb) 为基础数据源。原始宿主信息来源于 NCBI VHostMetadata.tsv (~500 Mb) 和 KEGG virushostdb.tsv (~1.5 Gb) 两份病毒-宿主关联表。合并策略采用 KEGG Virus-Host DB (VHDB) 优先原则：对有重叠的 Accession 记录，采纳 VHDB 的人工文献整理宿主信息并继承 NCBI 的权威版本号；对仅存在于 VHDB 的序列，自动追加 ".1" 版本号以确保命名一致性。合并后共获得非冗余序列 **13,818,894** 条，涵盖 **233,229** 个病毒 TaxID 和 **12,240** 个宿主 TaxID（表 4-1）。

以上数据进行宿主信息补全 (vhost_imputer)，对 Host 和 Host_Taxid 字段为空的记录，依次基于相同 TaxID 和相同 Virus_Name 采用 Polars 窗口函数进行分组补全，补全后保持 13,818,894 条。进一步使用 taxonkit（并行流程 60 线程）添加病毒和宿主的 9 级完整分类学谱系 (Virus: Realm–Species；Host: Superkingdom–Species)。

ICTV 官方 VMR (MSL41, 2026-03-20) 经 Excel 格式转换后，对 'Host source' 字段进行正则匹配实现宿主互斥分类。原生 ICTV 明确标注宿主的记录直接分类；对于标注为 'Unknown' 或 'Environmental' 的记录，通过 NCBI Host_lineage 进行拉丁文学名文本分类器抢救（暗物质抢救）。最终获得 **19,581** 条 VMR 宿主分类记录，其中包括 Plant (3,113)、Animal (5,766)、Bacteria (7,490)、Fungi (812)、Protist (198)、Archaea (198) 等宿主类别，抢救失败记录 1,756 条已单独归档。

宿主信息整合通过三层策略实现病毒-宿主关系的最大化覆盖：(i) Accession 跨表交叉填补——AllNuclMetadata 和 VHost 相互补全缺失 Host；(ii) TaxID 本地数据库匹配——通过 nucl_gb.accession2taxid (约 50 Gb) 剥离版本号后精准匹配；(iii) NCBI E-utilities API 联网兜底——对上述两步仍无法获取的 Accession 进行在线批量查询。最终生成病毒-宿主完整映射表 **14,760,225** 条，涵盖 **210,324** 个病毒 TaxID 和 **12,802** 个宿主 TaxID。最终无法确定宿主信息的记录共 93,367 条 (AllNucl) + 88,851 条 (VHost)，已单独归档供人工复核。

基于 Host_lineage 谱系的拉丁文学名正则分类器将全部记录精密划分为 10 个宿主类别。全量分类结果为：Human (12,907,780)、Animal (1,542,235)、**Plant (218,108)**、Bacteria (69,420)、Fungi (10,098)、Protist (1,648)、Oomycetes (1,141)、Unknown (1,138)、Environmental_NCBI (794)、Archaea (403)，共计 **14,752,765** 条。其中植物病毒 (Plant) 共 218,108 条 Accession 作为后续序列提取的输入目标。

> **表 4-1　元数据整合与宿主分类关键指标**
>
> | 指标 | 数值 |
> |:-----|:-----|
> | 合并后非冗余序列 (A2) | 13,818,894 |
> | 合并后病毒 TaxID | 233,229 |
> | 合并后宿主 TaxID | 12,240 |
> | VMR 宿主分类总数 (B2) | 19,581 |
> | VMR 植物病毒记录 | 3,113 |
> | 病毒-宿主完整映射 (C1) | 14,760,225 |
> | 无法确定宿主记录 | 182,218 |
> | 全量宿主分类总数 (C2) | 14,752,765 |
> | 植物病毒 Accession (Plant.tsv) | 218,108 |

### 4.2 植物病毒序列提取与元数据完善

将植物病毒 Accession 列表 (Plant.tsv, 218,108 条) 与本地 AllNucleotide FASTA 数据库 (~277 Gb) 进行 Polars Hash Join 比对。本地命中后通过 seqkit grep 高速提取，缺失序列通过 NCBI efetch API (db=nuccore, rettype=fasta) 进行全量下载（支持断点续传），合并本地提取与在线下载后共获得植物病毒序列 **218,048** 条。

从 AllNuclMetadata 本地提取 Species、Segment、Molecule_type、Length 等核心元数据字段，对本地缺失记录 (545 条) 通过 NCBI eSummary API 在线补全 (成功获取 544 条)。最终 Plant_Virus_Info.tsv 收录 **218,048** 条记录，涵盖 **7,187** 个 TaxID。序列长度范围为 6–813,435 bp (均值 2,260 bp，中位数 823 bp)。序列完整性分布为：complete (**65,060** 条, 29.8%)、partial (152,837 条, 70.1%)。在 TaxID 级别，**4,658** 个物种拥有至少一条完整基因组序列 (占比 64.8%)。标题中包含 CDS 标注的序列共 117,034 条 (53.7%)。

进一步通过 NCBI Entrez efetch (rettype=gb) 批量获取 217,722 条序列的拓扑结构 (Topology) 与分子类型 (Molecule_Type)。分子类型以单链正义 RNA (ssRNA(+)) 为主，共 116,391 条 (53.4%)，其次为单链 DNA (ssDNA(±)) 30,176 条 (13.8%)，双链 RNA (dsRNA) 6,028 条 (2.8%) 等。同时利用本地 names.dmp 与在线 NCBI Taxonomy 数据库查漏补全 NCBI 科学命名 (Scientific Name)。

> **表 4-2　植物病毒序列特征统计**
>
> | 指标 | 数值 |
> |:-----|:-----|
> | 序列总数 (Accessions) | 218,048 |
> | 唯一 TaxID | 7,187 |
> | 序列长度范围 | 6 – 813,435 bp |
> | 完整基因组序列 (complete) | 65,060 (29.8%) |
> | TaxID 级完整基因组 | 4,658 (64.8%) |
> | ssRNA(+) 分子类型 | 116,391 (53.4%) |

### 4.3 节段/非节段双层智能分类

基于 ICTV VMR 的 Genome coverage 和 GenBank Title 正则文本扫描，对 218,048 条序列进行节段病毒 (Segmented) 与非节段病毒 (Non-segmented) 双层分类。非节段病毒计 **84,301** 条 (38.7%)，节段病毒计 **133,747** 条 (61.3%)。细分类别中，NonSegmented_Complete 为 27,975 条 (12.8%)，Segmented_Complete 为 24,110 条 (11.1%)；基于 CDS 片段标注的序列占比最高 (NonSegmented_CDS_Fragment: 45,885 条；Segmented_CDS_Fragment: 18,097 条)。对于同 TaxID 下既存在节段又存在非节段序列的情形，触发同源兜底机制：经 ICTV VMR 确认的节段病毒物种 (702–703 个 TaxID) 旗下的非节段序列 (**88,299** 条) 被重新编入 Segmented_unknown 阵营，以防止节段信息在去冗余中丢失（表 4-3）。

> **表 4-3　节段/非节段分类统计**
>
> | 分类 | 序列数 | TaxID | 占比 |
> |:-----|:------:|:-----|:-----|
> | Segmented_Complete | 24,110 | 1,673 | 11.1% |
> | Segmented_CDS_Fragment | 18,097 | 524 | 8.3% |
> | Segmented_unknown (同源兜底) | 88,299 | 703 | 40.5% |
> | NonSegmented_Complete | 27,975 | 3,188 | 12.8% |
> | NonSegmented_CDS_Fragment | 45,885 | 1,006 | 21.0% |
> | NonSegmented_Partial_taxid | 4,810 | 1,962 | 2.2% |
> | 其他类别 | 8,872 | 640 | 4.1% |
> | **合计** | **218,048** | **7,187** | **100%** |

### 4.4 多层去冗余策略

去冗余分为元数据级与序列级两个层次（表 4-4）。

**元数据级去重 (TaxID 瀑布流)**：非节段病毒实施 TaxID 瀑布流拦截策略——高优先级存在的 TaxID，低优先级直接剔除，Complete 层级内同 TaxID 优先保留 RefSeq；节段病毒实施 Segment 级别智能补全——高优先级缺失的节段从低优先级中抽取补充。元数据去重后保留 **17,998** 条序列 (覆盖全部 7,187 个 TaxID)，序列消减幅度为 91.7%，但物种 (TaxID) 多样性 100% 保留。

**序列级去冗余 (双引擎聚类)**：采用 seqkit rmdup (--by-seq) 去除 100% 完全相同的序列；随后 MMseqs2 easy-cluster (--cluster-mode 2, --cov-mode 1, --min-seq-id 0.98) 进行序列相似度聚类。在每个聚类簇内按 (TaxID, Species_ICTV[, Segment]) 特征分组挽救，防止不同物种或不同节段被误合并。最终非节段代表序列 **7,635** 条 (涵盖 5,150 个 TaxID)，节段代表序列 **5,395** 条 (涵盖 2,042 个 TaxID)。合并后去冗余序列共计 **13,030** 条，相对原始 218,048 条植物病毒序列消减 **94.0%**，TaxID 保留率 100%。

> **表 4-4　去冗余各阶段序列与 TaxID 保留率**
>
> | 阶段 | 序列数 | 序列保留率 | TaxID | TaxID保留率 |
> |:-----|:------:|:----------|:-----:|:-----------|
> | Plant_Virus_Full.fasta (原始) | 218,048 | 100.0% | 7,187 | 100.0% |
> | 元数据去重后 (F3) | 17,998 | 8.3% | 7,187 | 100.0% |
> | plant.final.rmdup.fasta (F4) | 13,030 | 6.0% | 7,187 | 100.0% |
> | Plant_Virus_Ref.fasta (G2) | 11,956 | 5.5% | 6,597 | 91.8% |

### 4.5 泛基因组 ANI 聚类与 LCA 诊断

对去冗余后的 13,030 个 Accession 通过高性能并行映射引擎 (G1_seqid_to_taxid) 获取标准 TaxID，建立了 seqid2taxid.map 映射表 (共映射 13,030 条)，并追加序列长度信息 (seqid2taxid_len.map)。采用 **vclust** (algorithm=cd-hit, metric=ANI, --ani 0.98, --qcov 0.95) 进行泛基因组 ANI 聚类与 LCA (Lowest Common Ancestor) 诊断 (Roux et al., 2015; Zayed et al., 2022)。在聚类簇内执行 RefSeq 优先机制——带 '_' 前缀的 NCBI RefSeq 序列自动替换软件盲选的普通代表序列，同时检测 Category/Segment 命名冲突并触发节段挽救。

最终获得 **11,956** 条代表性参考基因组序列，覆盖 **6,597** 个 TaxID。相较原始 218,048 条植物病毒序列，序列数量总体消减 **94.5%**，TaxID 保留率为 91.8%（6,597 / 7,187）。

LCA 诊断发现跨 TaxID 混合聚类簇 **787** 个，占总聚类簇数的比例反映了序列水平相似性超过物种分类界限的程度。LCA 等级分布以 species (317)、genus (280)、family (88)、realm (20)、acellular root (28) 等级别为主（图 4-1），说明绝大多数跨 TaxID 聚类发生在属及以下分类层级。发生 RefSeq 优先替换事件 483 次，检测到 Segment 命名冲突 446 个。

> **表 4-5　LCA 混合聚类等级分布**
>
> | LCA 等级 | 混合簇数量 | LCA 等级 | 混合簇数量 |
> |:---------|:---------:|:---------|:---------:|
> | Species | 317 | Family | 88 |
> | Genus | 280 | Realm | 20 |
> | Acellular root | 28 | Subfamily | 23 |
> | No rank | 10 | Order | 8 |
> | Kingdom | 5 | Phylum | 4 |
> | Class | 3 | Suborder | 1 |

### 4.6 基因预测与覆盖度评估

利用 **pyrodigal-rv** (Larralde, 2022) 对最终 11,956 条参考基因组序列进行病毒基因预测。成功预测到 CDS 的序列 **11,847** 条 (91.1%，共 71,979 个 CDS)，未预测到基因的序列 1,183 条 (8.9%，可能为短序列片段、类病毒或非编码区域)。基因覆盖度分析表明：每基因组平均 CDS 数量为 5–6 个，平均基因覆盖度（单个基因平均长度 / 基因组长度）为 **53.3%**，平均总覆盖度（所有基因总长度 / 基因组长度）为 **84.6%**。该结果表明，未预测到基因的序列以类病毒（~300–400 bp）和短片段为主。

> **表 4-6　基因预测与覆盖度统计**
>
> | 指标 | 数值 |
> |:-----|:-----|
> | 成功预测 CDS 的序列 | 11,847 (91.1%) |
> | 未预测到 CDS 的序列 | 1,183 (8.9%) |
> | 总 CDS 数量 | 71,979 |
> | 平均基因覆盖度 | 53.3% |
> | 平均总覆盖度 | 84.6% |

### 4.7 讨论

本研究构建的去冗余植物病毒参考基因组数据库在以下方面具有显著优势：(i) 采用元数据级瀑布流 + 序列级双引擎聚类的多层级去冗余策略，在序列消减 94.5% 的同时将 TaxID 损失控制在 8.2% (7,187 → 6,597)；(ii) 节段病毒独立处理通道，通过 TaxID 同源兜底机制 (成功挽救 88,299 条节段病毒的关联序列) 和 Segment 级别补全策略防止节段信息丢失；(iii) 整合 NCBI + KEGG + ICTV 三大权威宿主信息源并进行系统性交叉验证；(iv) 附加 9 级完整病毒分类学谱系 (Realm–Species)，为系统发育下游分析提供了层次化分类基础；(v) 全流程采用模块化脚本设计，共计 21 个 Python 模块 + 1 个一体化 Shell 执行脚本 (run_all.sh)，支持断点续跑和环境变量参数化配置，仅需更新输入数据即可重建数据库。

本研究也存在若干局限性。植物病毒的定义依赖于 NCBI Host_lineage 中 Viridiplantae 谱系信息的完整性与准确性，部分跨宿主界的病毒物种可能被遗漏或误分类；去冗余阈值 (98% ANI) 为经验性参数，对于特定快速进化的 RNA 病毒（如部分正链 RNA 病毒）可能需要适当调整阈值以兼顾多样性与冗余度；基因预测依赖于 pyrodigal-rv 对病毒基因组的适应性，对未编码蛋白的类病毒 (Viroids) 仅依赖于序列聚类，其基因覆盖度指标不具生物学意义。

### 4.8 数据可用性

本研究所构建的植物病毒参考基因组数据集及其完整元数据可通过 GitHub 开源获取：https://github.com/zhangwenda0518/plant_virus_db_pipeline。最终输出产物位于 `3.final-ref-virus.db/` 目录，包括：(1) `Plant_Virus_Ref.fasta`——非冗余参考基因组序列 (11,956 条)；(2) `Plant_Virus_Ref.Info.tsv`——完整元数据表，含宿主分类、节段信息、分类学谱系等核心字段；(3) `virus_genes_cov.tsv`——基因覆盖度统计；(4) `Dereplication_Global_Summary.tsv`——各阶段去冗余效果评估。全套 21 个 Python 处理脚本、一键执行脚本 (run_all.sh)、依赖安装指南及详细使用说明均已随仓库开源。中间产物与阶段级运行日志 (4.logs/) 一并保留，确保全过程可追溯。

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
| `--raw-dir` | `-r` | `<work_dir>/0.raw_data` | 原始下载数据目录 |
| `--db-dir` | `-d` | `$HOME/database` | 本地数据库根目录 |
| `--taxonomy-dir` | `-t` | `<db_dir>/taxonomy` | NCBI Taxonomy 数据目录 |
| `--api-key` | `-k` | — | NCBI API Key (提升请求频率) |
| `--ncpu` | `-p` | 60 | 通用并行线程数 |
| `--mmseqs-threads` | `-m` | 32 | MMseqs2 聚类线程数 |
| `--taxonkit` | — | `taxonkit` | taxonkit 可执行文件路径 |

## 工作目录结构

运行 `run_all.sh` 后，产出按三大阶段组织:

```
plant_virus_db/
├── 0.raw_data/                       ← 原始输入数据
│   ├── AllNucleotide.fa.gz           # 全量病毒核酸序列
│   ├── AllNuclMetadata.csv           # 病毒元数据
│   ├── VHostMetadata.tsv             # NCBI 宿主关联表
│   ├── virushostdb.tsv               # KEGG 宿主数据
│   └── VMR_MSL41.*.xlsx              # ICTV VMR 表格
│
├── 1.virus-host_db/                  ← ★ 病毒-宿主数据库
│   ├── A-merge/                      # 阶段 A: 元数据整合
│   ├── B-ictv/                       # 阶段 B: ICTV VMR 拆分
│   └── C-host_classify/              # 阶段 C: 宿主分类
│       └── VHostMetadata/Plant.tsv   # 植物病毒 Accession 列表
│
├── 2.plant-virus.db/                 ← ★ 植物病毒参考基因组
│   ├── D-sequences/                  # 阶段 D: 序列获取
│   │   ├── Plant_Virus_Full.fasta         # 植物病毒合并序列
│   │   └── plant.virus.id            # Accession ID 列表
│   ├── E-metadata/                   # 阶段 E: 元数据完善
│   ├── F-dedup/                      # 阶段 F: 分类去冗余
│   └── G-cluster/                    # ★★★ 阶段 G: 最终产物
│       ├── Plant_Virus_Ref.fasta   # 最终参考基因组序列
│       ├── Plant_Virus_Ref.Info.tsv # 最终元数据
│       ├── virus_genes_cov.tsv       # 基因覆盖度
│       ├── clusters_with_LCA.tsv     # LCA 诊断报告
│       └── derep.summary.tsv         # 去冗余评估
│
├── 3.final-ref-virus.db/              ← ★★★ 最终参考数据库(软链接)
│   ├── Plant_Virus_Ref.fasta        → G-cluster/ 最终序列
│   ├── Plant_Virus_Ref.Info.tsv     → G-cluster/ 最终元数据
│   ├── Plant_Virus_Full.Info.tsv      → E-metadata/ 全量元数据
│   └── Plant_Virus_Full.fasta              → D-sequences/ 原始序列
│
└── 4.logs/                           ← ★ 全部运行日志
    ├── pipeline.log                  # 总时间线
    └── A1-数据质检.log ~ G4b-...log  # 各步骤详细日志
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
  [D] Plant_Virus_Full.fasta + plant.virus.id
    │
    ▼
  [E] Plant_Virus_Info.tsv (含 topo + name)
    │
    ▼
  [F] split_results/ → virus.dedup/ → Final_DB_Build/
    │
    ▼
  [G] Plant_Virus_Ref.fasta + virus_genes_cov.tsv
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
| G2 | `G2_vclust_cluster.py` | FASTA + Info + Map | `Plant_Virus_Ref.fasta` | vclust ANI 聚类 + LCA 诊断 + RefSeq 优先 |
| G3 | `G3_derep_evaluate.py` | 各级 FASTA + Info | 多维度评估报告 | 去冗余前后序列/物种保留率比较 |
| G4 | `G4_gene_coverage.py` | GFF3 + seqid2taxid | `virus_genes_cov.tsv` | 基因长度与覆盖度统计 |

---

## 原始数据下载

### raw_data 目录结构

下载完成后 `raw_data/` 应包含以下文件:

```
raw_data/
├── AllNucleotide.fa.gz              NCBI 全量病毒核酸序列          (~277G)
├── AllNuclMetadata.csv              NCBI 病毒元数据                (~2G)
├── VHostMetadata.tsv                NCBI 病毒-宿主关联表           (~500M)
├── virushostdb.tsv                  KEGG Virus-Host DB            (~1.5G)
└── VMR_MSL41.v1.20260320.xlsx       ICTV 官方 VMR 电子表格        (~4M)
```

> 另外 `~/database/taxonomy/` 下需放置 `names.dmp`、`nodes.dmp` 和 `nucl_gb.accession2taxid`。

### 下载命令

```bash
# === 创建工作目录 ===
mkdir -p ~/database/taxonomy
mkdir -p ~/plant_virus_db/raw_data
cd ~/plant_virus_db/raw_data

# === 宿主信息 ===
wget https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllDataTmp/VHostMetadata.tsv
wget https://www.genome.jp/ftp/db/virushostdb/virushostdb.tsv
wget https://ictv.global/sites/default/files/VMR/VMR_MSL41.v1.20260320.xlsx

# === 序列数据 ===
wget https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllNucleotide/AllNucleotide.fa.gz
wget https://ftp.ncbi.nlm.nih.gov/genomes/Viruses/AllNuclMetadata/AllNuclMetadata.csv.gz
gunzip AllNuclMetadata.csv.gz

# === NCBI Taxonomy ===
wget https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz -O ~/database/taxonomy/taxdump.tar.gz
tar -xzf ~/database/taxonomy/taxdump.tar.gz -C ~/database/taxonomy/
wget https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/accession2taxid/nucl_gb.accession2taxid.gz
gunzip nucl_gb.accession2taxid.gz -d ~/database/taxonomy/
```

| 文件 | 来源 | 大小 | 类型 | 用途 |
|:-----|:-----|:-----|:-----|:-----|
| `VHostMetadata.tsv` | NCBI FTP | ~500M | 宿主信息 | NCBI 病毒-宿主关联 (自动标注) |
| `virushostdb.tsv` | KEGG | ~1.5G | 宿主信息 | VHDB 病毒-宿主数据库 (文献溯源) |
| `VMR_MSL41.v1.xlsx` | ICTV | ~4M | 宿主信息 | ICTV 官方分类与宿主源 |
| `AllNucleotide.fa.gz` | NCBI FTP | ~277G | 序列数据 | 全量病毒 FASTA |
| `AllNuclMetadata.csv` | NCBI FTP | ~2G | 序列数据 | 病毒元数据 (物种/长度等) |
| `taxdump.tar.gz` | NCBI Taxonomy | ~71M | 分类数据库 | names.dmp / nodes.dmp |
| `nucl_gb.accession2taxid` | NCBI Taxonomy | ~50G | 分类数据库 | Accession → TaxID 映射 |

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
