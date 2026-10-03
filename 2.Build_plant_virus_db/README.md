# 病毒下游数据库统一构建工具

> **Virus Database Builder** — 将非冗余参考基因组序列一次性构建为 18 种下游软件的本地数据库。

> ⚠️ **输入口径争议（必读）**：本文档历史上引用的 **11,956 条核酸 / 72,691 条蛋白** 为 2026-05 批次输入口径；
> **现行参考库为 9,022 条**（见 `docs/data/DATA_VERSION` 的 `CLUSTER_COUNT`，与
> `grep -c "^>" Plant_Virus_Ref.fasta` 实测一致）。引用任何数字前先确认为哪一口径。

**历史批次输入** (2026-05-12): 11,956 条核酸 + 72,691 条蛋白
**历史批次输出** (2026-05-12): 17 种下游工具数据库 (15.95 GB, 23 分钟)

---

## 方法概述

### 设计思路
不同于逐个工具手动建库的繁琐流程，本工具通过统一的 CLI 接口和模块化架构，将 18 种下游分类/比对工具的数据库构建统一为单次调用。核心优势：

1. **动静分离** — 原始序列 (static) 与构建产物 (work) 物理隔离，避免污染源数据
2. **按需构建** — `--databases all` 构建全部，也可指定子集 (如 `--databases kraken2,blast`)
3. **软链接优化** — 大文件通过软链接共享，避免重复占用磁盘
4. **并发控制** — 自动检测 CPU/内存，`--threads` 和 `--max-ram` 限流
5. **Taxonomy 复用** — NCBI Taxonomy 目录一次性配置，所有分类工具共用

### 构建流程
```
输入 FASTA (核酸/蛋白)
    │
    ├── 1. 环境检查 → 检测 jellyfish/kraken2/blast/... 等二进制可用性
    ├── 2. 软链接准备 → work_dir 下建立指向原始文件的链接
    ├── 3. 分类信息提取 → 解析 FASTA header 中的 TaxID / accession
    ├── 4. 并行建库 ──── 18 个数据库构建器并发执行
    │       ├── k-mer 类: metabuli, kraken2, krakenuniq, kmcp, ganon, sylph, lexicmap
    │       ├── 比对类: blast, diamond, mmseqs, kma
    │       ├── 定量类: salmon_kallisto, bracken
    │       ├── 蛋白类: kaiju, kraken2x, CAT
    │       └── 特殊类: centrifuger, kun_peng
    └── 5. 报告生成 → 统计耗时、磁盘占用、成功/失败状态
```

### 关键设计决策
- **核酸库无宿主污染**: 输入 FASTA 需预先去除宿主基因组匹配，避免假阳性分类
- **蛋白库用于病毒发现**: 蛋白序列比对在远缘病毒检测中灵敏度优于核酸
- **k-mer 大小自适应**: 不同工具自动选择最优 k (kraken2=35, metabuli=31, kmcp=21)

---

## 运行示例

```bash
python build_virus_db.py \
  --nuc-fasta Plant_Virus_Ref.fasta \
  --prot-fasta virus.gene_pep.fasta \
  --db-prefix ref.virus.build \
  --work-dir ./5.virus.ref.build.db \
  --tax-dir ~/database/taxonomy \
  --databases all \
  --threads 120 \
  --jellyfish-bin ~/.pixi/envs/krakenuniq/bin/jellyfish
```

---

## 分析结果

> 🛑 **该表为 2026-05-12 批次结果，脚本其后多次改动（最近 2026-07-07），引用前请以重跑报告为准。**
> 本批次之后修复的建库缺陷（CAT 表头 `sed` 转义损坏、kaiju 带描述 header 的 TaxID 注入失效、
> 蛋白 ID 格式误判、映射覆盖率无校验）都会改变产物，**本表不可原样复现**。
> 输入口径亦有争议：表中 11,956/72,691 为历史口径，现行参考库 9,022 条（见文首说明）。

> 运行日期: 2026-05-12 | 输入: 11,956 条核酸 + 72,691 条蛋白

| 数据库 | 状态 | 耗时 | 磁盘占用 | 说明 |
|:-------|:----:|:----:|:--------|:-----|
| **metabuli** | ✅ | 390s | 909 MB | k-mer 分类 |
| **centrifuger** | ✅ | 24s | 50 MB | 快速分类 |
| **kraken2** | ✅ | 59s | 181 MB | 核酸分类 |
| **bracken** | ✅ | 17s | — | 丰度估计 |
| **krakenuniq** | ✅ | 163s | 10.4 GB | 高精度分类 |
| **kmcp** | ✅ | 23s | 538 MB | k-mer 搜索 |
| **ganon** | ✅ | 267s | 76 MB | 快速分类 |
| **sylph** | ✅ | 1s | 44 MB | sketch 分类 |
| **kun_peng** | ✅ | <1s | 200 MB | 快速分类 (基于 kraken2) |
| **blast** | ✅ | 188s | 22 MB | 序列比对 |
| **kma** | ✅ | 69s | 705 MB | k-mer 比对 |
| **salmon_kallisto** | ✅ | 82s | — | 定量分析 |
| **lexicmap** | ✅ | 39s | 2.3 GB | 快速分类 |
| **kaiju** | ✅ | 2s | 33 MB | 蛋白分类 |
| **kraken2x** | ✅ | 54s | 57 MB | 蛋白分类 |
| **diamond** | ✅ | 1s | 44 MB | 蛋白比对 |
| **mmseqs** | ✅ | 7s | 749 MB | 蛋白聚类搜索 |
| **合计** | **17/17** | **23 min** | **15.95 GB** | 该批次未含 CAT |

> **关于 CAT（第 18 个库，2026-05-12 批次之后加入，未列入上表）**：
> 构建器已随代码提供（`PROT_DBS` 第 5 项），建库前提是安装 **CAT_pack ≥ v6.0**
> （`CAT_pack prepare --db_fasta --names --nodes --acc2tax --db_dir`），且 `--acc2tax` 首行必须是
> `accession.version<TAB>taxid` 表头 —— 旧版脚本用 `sed '1i\...'` 生成该表头时被 Python 转义吃成
> `<BEL>ccession.version`，会导致 CAT 建库失败，现已改用 `printf`（见 `build_virus_db.py` 的 `build_cat`）。
> 旧 CAT_pack v5 的 `prepare` 子命令参数完全不同（`--fresh/--existing` + 下载式建库），不兼容本脚本。

---

## 参数说明

| 参数 | 必填 | 说明 |
|:-----|:----|:-----|
| `--nuc-fasta` | 核酸或蛋白必填其一 | 核酸参考基因组 FASTA |
| `--prot-fasta` | 核酸或蛋白必填其一 | 蛋白序列 FASTA (如 pyrodigal 产物) |
| `--db-prefix` | 否 | 数据库前缀 (默认: virus_db) |
| `--work-dir` | 否 | 工作目录 (默认: .) |
| `--tax-dir` | 否 | NCBI Taxonomy 目录 |
| `--databases` | 否 | 要构建的数据库列表, `all` = 全部 |
| `--threads` | 否 | 线程数 (默认: 32) |
| `--max-ram` | 否 | 最大内存 GB (默认: 500) |
| `--jellyfish-bin` | 否 | jellyfish 路径 (krakenuniq 需要) |

> 说明：`--databases all` 时核酸库与蛋白库各自按输入自动取舍；映射表生成后脚本会做
> **ID→TaxID 覆盖率对账**（<95% 打 WARNING 并把未命中清单落盘
> `<db_prefix>.<nuc|prot>.unmapped_ids.txt`），kaiju 建库另会输出
> `<db_prefix>.kaiju.unmapped_ids.txt`。

## 下游分析脚本关键参数

### `batch_class.reads.py` — 宏病毒分类批处理

| 参数 | 默认 | 说明 |
|:-----|:----|:-----|
| `-i/--input-dir` | 必填 | FASTQ 存放目录 |
| `-o/--output-dir` | 必填 | 统一输出根目录 (仅存放结果) |
| `-d/--db-dir` | 否 | 所有数据库统一存放的大目录 (浅层自动搜索) |
| `--db-<tool>` / `--kaiju-nodes/--kaiju-names` | 否 | 手动指定某库路径 / Kaiju taxonomy 文件 |
| `--tools` | `all` | 要跑的工具集合 |
| `--jobs` | 1 | 并行样本数 (内存消耗大时保持 1) |
| `--threads` | 30 | 单任务线程数 |

### `batch_virus_depth.py` — 参考基因组深度定量 (V42.4)

| 参数 | 默认 | 说明 |
|:-----|:----|:-----|
| `-r/--reference` | 必填 | 全局参考基因组 FASTA |
| `--ref_info` | 必填 | 本地参考信息 TSV (Accession/taxid/Species 列) |
| `--tool` | `bowtie2` | 比对引擎 (kallisto/salmon 为伪比对, 无 ANI/Pi) |
| `--coverage` | 10.0 | A 轨: 绝对全长覆盖度下限 (%)，**低于 10% 即使有 reads 也不报出** |
| `--ratio` | 0.3 | A 轨: 泊松分布覆盖度比值下限 (打假局部堆叠假阳性) |
| `--meandepth` | 0.5 | A 轨: 代表序列最小平均深度 (过滤单 read 噪声) |
| `--min_tpm` | 1.0 | 最低 TPM (过滤痕量污染) |
| `--min_uniq_reads` | 10 | 最少独特比对 reads 数 (过滤 1–2 条 reads 的假阳性) |
| `--sp_thresh` | 95.0 | 物种级 ANI 识别阈值 (%)，仅传统比对模式生效 |
| `--genes_cov` / `--min_gene_total_cov` / `--min_gene_avr_cov` | — / 80 / 5 | B 轨双轨制放行 (转录区覆盖挽救) |
| `--long_read` | 关闭 | 输入为长读 (ONT/PacBio); 影响 minimap2 预设 (见下) |
| `--use_coverm` 及 `--min_aln_len/--min_aln_prop/--min_pid` | 关闭 / 80 / 0.85 / 0.90 | CoverM 严格清洗 (仅传统比对) |

> minimap2 预设规则：双端 → `sr`；单端短读 (Illumina) → `sr`；
> 仅当 `--long_read` 或自动测得平均读长 > 1 kb 时才用 `map-ont`。
> **注意**：`--coverage 10` 与 `--min_tpm 1.0` 等阈值为经验值，重跑论文级结果前应在
> 目标数据上做敏感性分析，不要直接照抄默认值当结论。

## 支持的数据库

```bash
# 核酸数据库 (13 种)
metabuli centrifuger kraken2 bracken krakenuniq kmcp ganon sylph
kun_peng blast kma salmon_kallisto lexicmap

# 蛋白数据库 (5 种) — 与 build_virus_db.py 的 PROT_DBS 一致
kaiju kraken2x diamond mmseqs CAT
```

> `CAT` 为蛋白库第 5 项，需 CAT_pack ≥ v6.0（安装方式见 CAT 官方仓库）；
> `--databases all` 会包含它，未安装时该库在汇总表中显示为 ❌ 失败，不影响其余 17 库。
