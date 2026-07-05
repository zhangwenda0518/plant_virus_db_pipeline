# 病毒下游数据库统一构建工具

> **Virus Database Builder** — 将非冗余参考基因组序列一次性构建为 17 种下游软件的本地数据库。

---

## 运行示例

```bash
python build_virus_db.py \
  --nuc-fasta final.cluster.ref.fasta \
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
| **合计** | **17/17** | **23 min** | **15.95 GB** | — |

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

## 支持的数据库

```bash
# 核酸数据库 (13 种)
metabuli centrifuger kraken2 bracken krakenuniq kmcp ganon sylph
kun_peng blast kma salmon_kallisto lexicmap

# 蛋白数据库 (4 种)
kaiju kraken2x diamond mmseqs
```
