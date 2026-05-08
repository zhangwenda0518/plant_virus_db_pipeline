<!-- omit in toc -->
# 植物病毒基因组数据库构建流程

> **Plant Virus Genome Database Construction Pipeline**
>
> 从 NCBI、KEGG、ICTV 三大数据源出发，经过元数据整合 → 宿主分类 → 序列提取 → 去冗余 → 聚类评估，最终构建高质量非冗余植物病毒参考基因组数据库。

---

<!-- toc -->
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

## 快速开始

```bash
# 1. 配置环境变量 (按实际情况修改)
export WORK_DIR="$HOME/plant_virus_db"
export RAW_DIR="$WORK_DIR/raw_data"
export DATABASE_DIR="$HOME/database"
export EMAIL="your_email@example.com"

# 2. 下载原始数据 (见下方「原始数据下载」章节)

# 3. 一键运行全流程
bash run_all.sh

# 支持断点续跑 — 已完成的步骤会自动跳过
```

## 工作目录结构

运行 `run_all.sh` 后，输出按阶段组织：

```
plant_virus_db/
├── 00_logs/                         # ★ 所有阶段运行日志
│   ├── pipeline.log                 # 总日志 (时间线)
│   ├── A.log ~ G.log                # 各阶段详细日志
│   └── F4a.log / F4b.log            # 子步骤独立日志
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
