# LCA 混合聚类分布图（`*.LCA_Distribution.png`）留档

本目录保存历史批次与现行批次的 LCA 分布图，用于核对论文图 4-1 / 表 4-5 的数字口径。
这些图原先只存在于服务器工作目录中，仓库里没有任何副本，因此按批次归档一份。

## 绘制方式

- **脚本**：`1.Prepare_plant_virus_pipeline/G2_vclust_cluster.py` → `plot_results()`（`run_all.sh` 第 513 行以 `--out_plot` 指定输出路径）
- **输入表**：同一目录下的 `clusters_with_LCA.tsv`，每个跨 TaxID 混合聚类簇一行，列为
  `Cluster_Rep | Total_Seqs | Unique_Taxids | Exact_LCA_Name | Exact_LCA_Rank | Std_LCA_Name | Std_LCA_Rank | Taxid_Breakdown`
- **前处理**：`G1_seqid_to_taxid` 建立 Accession→TaxID 映射 → `vclust`（cd-hit / ANI 0.98 / qcov 0.95）聚类 → `get_lca_info()` 取簇内全部 TaxID 的共同谱系、映射到最近标准等级（`Std_LCA_Rank`）

**图面规格**（两面板，`figsize=(15, 6)`、`dpi=300`、`bbox_inches='tight'`，成图约 4427×1737 px）

| 面板 | 标题 | 内容 |
|---|---|---|
| 左 | Number of Mixed Clusters per Std_LCA_Rank | `sns.countplot(x='Std_LCA_Rank')`，viridis，柱顶标注数值，x 标签旋转 45° |
| 右 | Distribution of Unique Taxids per LCA Rank | `sns.boxplot(y='Unique_Taxids', color='lightgray', showfliers=False)` + `sns.stripplot(alpha=0.7, jitter=True, size=6)` |

等级顺序取 `df['Std_LCA_Rank'].value_counts().index`（频次降序）。**该次运行若无跨 TaxID 混合簇则不绘图**（日志打印"✅ 无跨物种聚类，跳过LCA绘图"）。

## 文件名沿革

2026-03 的脚本输出名为 `LCA_Distribution.png`；2026-03-22 起改为与输入表同前缀的 `clusters.LCA_Distribution.png`。
改名不影响内容，旧文件也没被删除，所以同一目录下两个名字会并存（这正是 `/home/zhangwenda/database/virus-db/virus-host/ncbi-virus2/` 里成对出现的原因）。

## 本目录文件与来源

| 本目录文件 | 服务器来源 | 日期 | 混合簇总数 | 配套输入表 |
|---|---|---|---|---|
| `2026-03-21_LCA_Distribution_2248clusters.png` | `virus-db/virus-host/ncbi-virus2/LCA_Distribution.png` | 2026-03-21 02:09 | 2,248 | `ncbi-virus2/clusters_with_LCA.tsv`（2,248 行） |
| `2026-03-22_clusters.LCA_Distribution_2248clusters.png` | `virus-db/virus-host/ncbi-virus2/clusters.LCA_Distribution.png` | 2026-03-22 14:50 | 2,248 | 同上（重跑，仅右面板点云有差异：42,314 px / 0.55%） |
| `2026-03-22_Plantdb_clusters.LCA_Distribution_1299clusters.png` | `virus-db/virus-host/ncbi-virus2/Plant_virus_db/clusters.LCA_Distribution.png` | 2026-03-22 21:12 | 1,299 | `ncbi-virus2/Plant_virus_db/clusters_with_LCA.tsv`（1,299 行） |
| `2026-04-03_ncbivirus3_clusters.LCA_Distribution_791clusters.png` | `virus-db/virus-host/ncbi-virus3/Plant_virus_db/clusters.LCA_Distribution.png` | 2026-04-03 17:12 | 791 | `ncbi-virus3/Plant_virus_db/clusters_with_LCA.tsv`（791 行） |
| `2026-06-02_Gcluster_clusters.LCA_Distribution_569clusters.png` | `plant_virus_db/2.plant-virus.db/G-cluster/clusters.LCA_Distribution.png` | 2026-06-02 14:37 | 569 | `G-cluster/clusters_with_LCA.tsv`（569 行），见 `6.logs/G2-vclust聚类.log` |

各批次等级分布（左图柱值，合计 = 混合簇总数）：

| 批次 | 分布 |
|---|---|
| 2026-03（2,248） | genus 1181 / species 631 / family 146 / acellular root 103 / subfamily 61 / realm 55 / order 25 / kingdom 21 / phylum 10 / class 8 / no rank 7 |
| 2026-03 Plantdb（1,299） | genus 567 / species 446 / family 114 / subfamily 45 / acellular root 45 / realm 43 / order 14 / class 7 / no rank 6 / kingdom 6 / phylum 6 |
| 2026-04-03（791） | species 320 / genus 281 / family 89 / acellular root 28 / subfamily 23 / realm 20 / no rank 10 / order 8 / kingdom 5 / phylum 4 / class 3 |
| 2026-06-02（569） | species 271 / genus 196 / family 39 / subfamily 19 / realm 17 / acellular root 14 / order 7 / kingdom 2 / class 2 / suborder 1 / phylum 1 |

## 注意

`1.Prepare_plant_virus_pipeline/README.md` §4.5 正文与表 4-5 写的是 **787** 个混合簇（species 317 / genus 280 / family 88 …），与各批次都不完全相等，但**最接近 `ncbi-virus3`（2026-04-03）那一版**——该版同目录的 `refseq_replacement_log.tsv` 为 **483** 行，与正文"RefSeq 优先替换事件 483 次"完全一致，`final.cluster.ref.fasta` 11,936 条（正文 11,956）、独特 TaxID 6,583（正文 6,597）、`category_segment_conflict.tsv` 449 行（正文 446）。差异都在个位数，说明表 4-5 出自这一代流水线（可能是同批次的又一次运行）。
因此**图 4-1 应使用 `2026-04-03_ncbivirus3_...791clusters.png` 这一版**，而不是 3 月的 2,248/1,299 版；3 月那两张是更早期的全量输入快照，簇数是 4 月版的约 2.8 倍。

## 复现

```bash
# 重新生成（路径按实际工作目录调整）
python G2_vclust_cluster.py \
    -f  <work>/2.plant-virus.db/F-dedup/plant.final.rmdup.fasta \
    ... \
    --out_tsv  <work>/2.plant-virus.db/G-cluster/clusters_with_LCA.tsv \
    --out_plot <work>/2.plant-virus.db/G-cluster/clusters.LCA_Distribution.png
```

完整参数见 `run_all.sh` 的 G2 调用段（第 508-520 行）。

## 2026-09-28 补充：新确认三个批次 + 表 4-5 出处更正

在 success 服务器（202.119.189.246）上全盘搜索同名图，共 7 处 `clusters.LCA_Distribution.png`
（加上 ncbi-virus2 旧名 `LCA_Distribution.png` 共 8 版记录），其中 3 处此前未归档，已 scp
回本目录（md5 与服务器逐一核对一致）：

| 本目录文件 | 服务器来源 | 日期 | 混合簇总数 |
|---|---|---|---|
| `2026-05-10_testdb_gcluster_clusters.LCA_Distribution_787clusters.png` + `..._with_LCA_787rows.tsv` | `plantvirus-db/plant_virus_db/test-db/2.plant-virus.db/G-cluster` | 2026-05-10 14:12 | 787 |
| `2026-05-10_testdb_gcluster2_...`（同前缀，+tsv） | 同上 `G-cluster2` | 2026-05-10 09:49 | 787 |
| `2026-06-01_hgenes_...`（同前缀，+tsv） | `~/plant_virus_db/2.plant-virus.db/H-virus_genes/G-cluster` | 2026-06-01 16:14 | 774 |

等级分布：

- **2026-05-10 testdb G-cluster（787）**：species 317 / genus 280 / family 88 / acellular root 28 /
  subfamily 23 / realm 20 / no rank 10 / order 8 / kingdom 5 / phylum 4 / class 3 / suborder 1
- 2026-05-10 testdb G-cluster2（787）：与 14:12 版**逐级完全相同**
- 2026-06-01 hgenes（774）：species 351 / genus 278 / family 59 / subfamily 27 / realm 21 /
  acellular root 17 / order 9 / phylum 4 / kingdom 3 / no rank 2 / class 2 / suborder 1

**表 4-5 出处更正**：上文「注意」推断 787「最接近 ncbi-virus3（791）、可能是同批次又一次
运行」——现已确证：**2026-05-10 test-db/G-cluster 与表 4-5 的 787（species 317 / genus 280 /
family 88 …）逐级完全一致**，此即表 4-5 的直接出处。图 4-1 应改用
`2026-05-10_testdb_gcluster_clusters.LCA_Distribution_787clusters.png`。

**批次谱系（8 版）**：2,248（03-21 / 03-22，ncbi-virus2 root，**未净化全量 pull**）→ 1,299
（03-22，ncbi-virus2/Plant_virus_db 子集，预过滤参考）→ 791（04-03，ncbi-virus3）→ 787
（05-10 ×2，test-db）→ 774（06-01，H-virus_genes，F-dedup 前）→ 569（06-02，现行 G-cluster，
F-dedup 后）。聚类判据：kmer-db + lz-ani all2all，ANI ≥ 0.98 且 qcov ≥ 0.95（见 `6.logs/G2` 日志）。

**输入口径警示（2026-09-28 谱系鉴定，勿跨口径直接比较 2,248 vs 569）**：

- 3 月 root 的聚类输入（216,695 条）**不是纯植物病毒集**，是未做宿主净化的原始 pull：
  含 Phycodnaviridae（藻类 dsDNA）1,333 / Mitoviridae 216 / Genomoviridae 180 /
  Fiersviridae（RNA 噬菌体）110 / Parvoviridae 55 / Pestiviridae 43 / Coronaviridae 11 等
  非植物科约 2,100 条（~1%），另有 10,909 条（~5%）无科级归属的未分配类群。
- 6 月全量集（199,068 条）经宿主净化后上述各科全部为 0（管线 C3a 藻类拆分等步骤），
  但 Tospoviridae 记录从 9,477 降到 3,574（记录级净化，原因待查）。
- 影响量化：3 月 2,248 个混合簇中**仅 70 个（3.1%）**含非植物科 TaxID（其中
  Phycodnaviridae 占 45 个）——口径混杂存在但只解释小头；混合簇 2,248 → 569 的 4 倍
  差距主因仍是**未去冗余**（3 月 root 混合簇平均 36.1 条成员、合计 81,184 条，
  4 月以后平均 ~2.8 条、合计 ~1,500–2,300 条）。
- 鉴定方法与数据：本地 taxdump 爬科级谱系，脚本
  `D:\桌面\文章写作\_session_tmp_20260912\lca_audit\compare_composition.py`
  （输入：3 月 root `seqid2tax.map`、`clusters_with_LCA.tsv`，对照 6 月
  `Plant_Virus_Full.Info.tsv` 的 Family 列）。

**diff 结论**（对 `clusters_with_LCA.tsv` 逐行比较）：

- G-cluster vs G-cluster2（同日两次）：整表 diff 1,218 行几乎全部来自 Taxid_Breakdown 内部
  排序与代表序列选择差异，仅约 10 簇更换代表；等级分布不变。
- 791 → 787：445 / 441 行互有增减，多数亦为 breakdown 排序差异，净减 4 簇。
- 774 → 569（F-dedup 前后）：消失的 567 行 LCA 等级以 species 251、genus 203 为主——
  去冗余直接消解了"同种多 TaxID"型混合簇；说明**种级混合信号大头来自冗余序列
  （同种重复提交 / 旧物种 TaxID）**，跨属 / 跨科部分才需要逐簇人工核查。
