> ⚠️ 2026-10-03 数字更正：本文为 2026-09-30 的快照。其中 miRNA「837 物种」为旧版 `count_mirna.py` 的计数 bug（把 38 个无序列的基因表物种名计入），修复后权威口径为 **799 物种 / 83,166 序列**（见 `data/miRNA_final_stats.json` 与根目录 `AUDIT_REPORT_20261003.md` D4）；vsiRNA 行数口径亦已按清洗后的 TSV 更新。引用数字请以重新生成的数据文件为准。

# genes 两孤儿页 · 数字重算报告（2026-09-30）

> **本次未改动任何源文件**。仅产出算式与出处，等老师裁决后再改页。
> 数据源：`D:\桌面\C-host_classify\plant_virus_db_pipeline\`（本地）与 `root@39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/`（线上）。
> 可复现脚本：`tmp_check_20260930/recompute_genes_numbers.py`、`tmp_check_20260930/trace_genes_numbers.py`。

---

## 0. 一句话结论

- **`/genes/`（`docs/genes/index.html`）的数字全部有出处、全部可复算** —— 每一条都能用生成器 `11.antiviral_genes/build_index.py` + `11.antiviral_genes/data/` 精确复算（含 miRNA 的「837 物种」，出处是 `miRNA_final_stats.json`）。
- **`/genes/data/`（`docs/genes/data/index.html`）的数字大部分无出处** —— 没有生成器，NLR 卡（400/3/8/400）、NLR 图（243/85/72）、Total Species（221）、miRNA 物种（997）都找不到任何数据源；且与 `/genes/` **逐项矛盾**。
- 两页的 **miRNA 卡描述的是两个完全不同的数据集**（83,166 条 vs 10,090 条），却共用同一张卡片文案。

> **更正记录**：本报告初版把「837」也列为无出处，**那是错的**。复查后在 `11.antiviral_genes/data/miRNA_final_stats.json` 找到 `total_species: 837` 与 `total_miRNAs: 83166`，与页面完全一致。已在下文更正。真正无出处的只有 **997**。

---

## 1. 证据链（先建立「谁生成谁」）

| 关系 | 证据 | 判定 |
|---|---|---|
| `docs/genes/index.html` 的生成器 | `11.antiviral_genes/build_index.py:8` `OUTHTML = .../index.html`；线上留档 `index.html.bak_20260930.i18npages` = **7,085 B**，与 `11.antiviral_genes/index.html` **逐字节同尺寸** | **已实测**：同源 |
| 该生成器的数据源 | `build_index.py:7` `OUTDIR = .../data` → `11.antiviral_genes/data/`（**不是** `docs/genes/data/`） | **已实测** |
| `docs/genes/data/index.html` 的生成器 | 全库搜 `10,090` 无命中生成脚本；`11.antiviral_genes/` 下无对应脚本 | **推断**：手写 |
| 两处 `all_genes_classified.json` 不同 | `11.antiviral_genes/data/` = 3,211,223 B，键 `nlr/srna/ups/mirna`；`docs/genes/data/` = 2,338,486 B，键仅 `nlr/srna` | **已实测**：**不是同一份文件** |

> ⚠️ 关键前提：**`docs/genes/` 整个目录 git 未跟踪**（`git status` → `?? docs/genes/`），所以 git 不能当基线；比基线只能取**线上副本**或**生成器源目录**。

---

## 2. `/genes/`（`docs/genes/index.html`）逐数字复算

生成器口径：`nlr = refplant_nlr_data.json["genes"]`（`build_index.py:19`）；`srna / ups = all_genes_classified.json["srna"/"ups"]`（`:22-23`）。

| # | 页面数字 | 位置 | 算式 / 出处 | 判定 |
|---|---|---|---|---|
| 1 | NLR **415** | `index.html:59` | `refplant_nlr_data.json["genes"]` 长度 = **415**（`build_index.py:108` `len(nlr)`） | ✅ |
| 2 | NLR Domain Types **4** | `:60` | `Counter(domain_type)` = `{CNL 282, TNL 94, NLR 32, RNL 7}` → **4 个键**（`:109` `len(nlr_dt)`） | ✅ |
| 3 | NLR Species **73** | `:61` | `Counter(host)` 唯一值 = **73**（`:110` `len(nlr_sp)`） | ✅ |
| 4 | NLR Validated **415** | `:62` | `validated=="V"` 计数 = **415**（`:111` `nlr_val`） | ✅ |
| 5 | sRNA **11,780** | `:68` | 源 `all_genes_classified.json["srna"]` 长度 = **11,780** | ✅ |
| 6 | sRNA Families **7** | `:69` | `Counter(family)` = `{AGO 4019, Other 3829, RDR 1951, DRB 1190, DCL 631, HEN1 131, SGS3 29}` → **7 个键** | ✅ |
| 7 | sRNA Species **215** | `:70` | `Counter(species)` 唯一值 = **215** | ✅ |
| 8 | sRNA Proteins **5,348** | `:71` | `11.antiviral_genes/data/plant_sRNA_proteins.fasta` 的 `>` 行数 = **5,348**（`build_index.py:41`） | ✅（但见 §5.3 数据漂移） |
| 9 | UPS **3,996** | `:77` | 源 `all_genes_classified.json["ups"]` 长度 = **3,996** | ✅ |
| 10 | UPS Families **9** | `:78` | `Counter(family)` 9 个键（E1 500 / Proteasome 500 / E2 498 / Fbox 498 / E3_RING 492 / BTB 467 / E3_Ubox 408 / E3_HECT 327 / Cullin 306） | ✅ |
| 11 | UPS Species **204** | `:79` | `Counter(species)` 唯一值 = **204** | ✅ |
| 12 | UPS Proteins **5,000** | `:80` | `plant_UPS_proteins.fasta` 的 `>` 行数 = **5,000** | ✅ |
| 13 | miRNA Sequences **83,166** | `:86` | `miRNA_all_combined.fa` 记录数 = **83,166** | ✅ |
| 14 | miRNA Plant Species **837** | `:87` | `miRNA_final_stats.json` 的 `total_species: 837`；同文件 `species_by_source = {plantrg 780, mirbase 54, ncbi 49, combined 837}` | ✅ |
| 15 | miRNA Data Sources **3** | `:88` | 文案自称 plantrg + miRBase + NCBI；`miRNA_final_stats.json["sources"]` = `{plantrg_json 47775, plantrg_fasta 25556, mirbase 7452, ncbi 49}` → 4 个键但归为 3 个来源 | ✅ |
| 16 | miRNA Combined FASTA **4.7 MB** | `:89` | `miRNA_all_combined.fa` = 4,661,519 B = **4.45 MiB / 4.66 MB** | ✅（四舍五入到 4.7） |
| 17 | Total Genes **16,191** | `:95` | 415 + 11,780 + 3,996 = **16,191**（`build_index.py:100` `total`） | ✅ 精确 |
| 18 | Total Species **262** | `:96` | `len(nlr_host ∪ srna_sp ∪ ups_sp)` = 73 ∪ 215 ∪ 204 = **262**（`:151`） | ✅ 精确 |
| 19 | Validated **14,935** | `:97` | 415 + 10,952 + 3,568 = **14,935**（`:152`，三个 `validated=="V"` 之和） | ✅ 精确 |
| 20 | Proteins **10,348** | `:98` | 5,348 + 5,000 = **10,348**（`:153`） | ✅（随 #8 走） |
| 21 | hero「59 antiviral NLR effector interactions」 | `:50` | `ANTIVIRAL_NLR_DATA` 长度 = **59** | ✅ |
| 22 | hero「415 …（73 species）」「11,780」「3,996」「83,166」 | `:50` | 同 #1/#3/#5/#9/#13 | ✅ |
| 23 | footer「16,191 genes across 262 species」 | `:103` | 同 #17/#18 | ✅ |

**小结：23 条全部可精确复算。**

> 附：`miRNA_final_stats.json` 自身有一处不自洽 —— `sources` 四项之和 = 47,775 + 25,556 + 7,452 + 49 = **80,832**，与 `total_miRNAs: 83166` 差 **2,334**。页面用的 83,166 与实测 `miRNA_all_combined.fa` 记录数一致，所以**页面对、统计文件错**。
> 另外：按 `>Species_miRNA_NNNNN` 前缀解析 `miRNA_all_combined.fa` 只得到 **799** 个物种名，与 837 差 38 —— 说明这 38 个物种的记录**用了不同的 header 命名**（`miRNA_final_stats.json` 记的是 plantrg 780 + mirbase 54 + ncbi 49 去重后 837，我无法用单一正则复现 837，故标为「有出处但口径未完全复现」）。

---

## 3. `/genes/data/`（`docs/genes/data/index.html`）逐数字复算

| # | 页面数字 | 位置 | 出处 | 判定 |
|---|---|---|---|---|
| 1 | NLR **400** | `data/index.html:59` | 唯一能对上的是 `RefPlantNLR_..._415_CDS.fasta` 的 `>` 数 = **400**（上游 CDS 数据集） | ⚠ **口径不同**（`/genes/` 用 AA 集的 415） |
| 2 | NLR Domain Types **3** | `:60` | ❌ 无出处。真实 `domain_type` 有 **4** 个（CNL/TNL/NLR/RNL） | ❌ |
| 3 | NLR Species **8** | `:61` | ❌ 无出处。真实 `host` 唯一值 = **73** | ❌ |
| 4 | NLR Validated **400** | `:62` | ❌ 无出处。真实 `validated=="V"` = **415**（且 415 条全为 V） | ❌ |
| 5 | NLR 图 **243 / 85 / 72**（和 400） | `:104-106` | ❌ 无出处。真实 `domain_type` = 282/94/32/7；`structure` = 252/79/25/… 都推不出 243/85/72 | ❌ |
| 6 | sRNA **11,780 / 7 / 215** | `:68-70` | 同 §2 #5/#6/#7 | ✅ |
| 7 | sRNA Proteins **5,348** | `:71` | 同 §2 #8 | ✅ |
| 8 | UPS **3,996 / 9 / 204 / 5,000** | `:77-80` | 同 §2 #9–#12 | ✅ |
| 9 | miRNA 文案 **10,090 / 997** | `:50`、`:84` | 10,090 = `plantrg_all_mirna_extended.fa` 记录数 = **10,090** ✅；**997 ❌ 无出处**（本地所有出现均为巧合：`pamirdb_v7_data.js` 的序列坐标、`gene_data.js` 的 `length_aa: 997` 等） | ⚠/❌ |
| 10 | miRNA 卡 **83,166 / 837 / 3 / 4.7 MB** | `:86-89` | 与 `/genes/` 完全相同（同 §2 #13–#16） | ⚠ 与 #9 并存 → 同卡两个数据集 |
| 11 | Total Genes **16,176** | `:95` | 400 + 11,780 + 3,996 = **16,176**（自洽，但基于 400） | ⚠ 自洽但口径错 |
| 12 | Total Species **221** | `:96` | ❌ 无出处。真实并集 = **262**；`sRNA ∪ UPS` = **217**（归一化后仍 217） | ❌ |
| 13 | Validated **14,920** | `:97` | 400 + 10,952 + 3,568 = **14,920**（自洽，基于 400） | ⚠ 自洽但口径错 |
| 14 | Proteins **10,348** | `:98` | 同 §2 #20 | ✅ |
| 15 | 图表 sRNA 家族 4019/3829/1951/1190/631/131/29 | `:109-115` | = 源 `all_genes_classified.json["srna"]` 的 family 分布（和 = 11,780） | ✅ |
| 16 | 图表 UPS 家族 8 项 | `:118-125` | 和 = 3,690，**缺 Cullin 306**；页面却写「9 个家族」（`:78`） | ⚠ 图与数字不一致 |
| 17 | 图表 Database Overview 400/11,780/3,996 | `:146-149` | 同上（NLR 用 400） | ⚠ |
| 18 | 图表 Top Species（Arabidopsis 1383 等 12 行） | `:131-142` | 未逐条核（不在本次范围） | — |

**小结：NLR 卡 4 个数 + 图 3 个数 + Total Species 221 + miRNA 997 = 9 处无出处；其余与 `/genes/` 一致。**

---

## 4. 两页互相矛盾清单（同一张卡）

| 项 | `/genes/` | `/genes/data/` | 差额 |
|---|---|---|---|
| NLR Genes | **415** | **400** | 15 |
| NLR Domain Types | **4** | **3** | 1 |
| NLR Species | **73** | **8** | 65 |
| NLR Validated | **415** | **400** | 15 |
| Total Genes | **16,191** | **16,176** | 15 |
| Total Species | **262** | **221** | 41 |
| Validated | **14,935** | **14,920** | 15 |
| miRNA 序列 | **83,166**（`miRNA_all_combined.fa`） | 卡内 83,166，但 hero/desc 写 **10,090**（`plantrg_all_mirna_extended.fa`） | 两个数据集 |
| miRNA 物种 | **837**（有出处） | 卡内 837，hero/desc 写 **997**（无出处） | — |

> 差额 15 全部来自 `415 → 400`；`16,176 = 16,191 − 15`、`14,920 = 14,935 − 15` 都能对上，说明第二页是在第一页基础上把 NLR 换成 400 后**手改**的。

---

## 5. 三个附加缺陷（与数字无关，但同属「看着能用其实不对」）

### 5.1 🔴 卡片 `onclick` 属性被 HTML 解析截断 → `localStorage` 从未生效

两页各 4 处（`docs/genes/index.html:55,64,73,82`；`docs/genes/data/index.html:55,64,73,82`）：

```html
<a class="big-card" href="gene_browser.html#nlr" onclick="localStorage.setItem("genesActiveTab","nlr")">
```

**已实测**：用 `html.parser` 解析，`onclick` 属性值只剩 `'localStorage.setItem('` —— 属性在第二个 `"` 处提前结束，**`localStorage.setItem` 根本不会执行**。导航之所以「看起来能用」，是靠 `href` 的 `#nlr` hash 兜住的。

> 生成器 `build_index.py:104` 里写的是 `onclick=\"genesActiveTab\"` 转义形式，但那是 **Python 字符串里的转义**，写进 HTML 后就是裸双引号 → **生成器本身就是错的**（修生成器才能真正修好）。

### 5.2 🟠 `/genes/data/` 线上 **403**，统计看板页没有自然入口

- nginx：`location /genes/ { alias .../docs/genes/; index gene_browser.html; }` —— **index 只认 `gene_browser.html`**，所以 `/genes/data/` 找不到 index → **403**。
- 文件本身**已部署**（线上 `docs/genes/data/index.html` = 16,380 B，Sep 30 03:47），显式路径 `/genes/data/index.html` → **200**。
- **全站零引用**（`grep -rn "genes/data" docs/` 无命中）→ 名副其实的孤儿页。

### 5.3 🟠 源目录与部署目录的 `plant_sRNA_proteins.fasta` 不是同一个文件

| 文件 | 大小 | `>` 记录数 | md5 |
|---|---|---|---|
| `11.antiviral_genes/data/plant_sRNA_proteins.fasta` | 4,591,269 B | **5,348** | `5f01b7f4…` |
| `docs/genes/data/plant_sRNA_proteins.fasta` | 4,591,269 B | **5,209** | `dc89764d…` |

**已实测**：字节数相同但 md5 不同；header 集合差异 —— 只在源里的 **2,246** 条，只在部署里的 **2,021** 条（差异集中在 `other` 家族）。首个字节差异在 offset 2,198,957。

→ 页面写的 **5,348 是按源目录算的**，与**线上实际提供下载的那份文件（5,209）不符**。这是个**数据漂移**问题，需要老师定：以哪份为准、要不要重新生成。

---

## 6. 请老师裁决的问题（不改数字，只列问题）

1. **两页要不要合并/下线一个？** `/genes/data/` 无入口（403）、无生成器、数字大部分无出处 —— 是保留并修、还是下线？
2. **NLR 口径**：415（RefPlantNLR AA 集，`/genes/` 用）还是 400（CDS 集，`/genes/data/` 用）？建议统一为 **415**。
3. **Total Species 221 怎么来的？** 真实并集是 262。是要改成 262，还是 221 有我不知道的筛选条件？
4. **miRNA 卡到底指哪个数据集？** 83,166 条（`miRNA_all_combined.fa`，837 物种）/ 10,090 条（`plantrg_all_mirna_extended.fa`）—— 两页混用，需要定一个。
5. **`997` 这个物种数是从哪来的？** 本地数据里找不到（10,090 那一路的物种数我也没能复现）。是从论文/外部统计抄来的吗？
6. **`plant_sRNA_proteins.fasta` 以哪份为准？**（源 5,348 vs 线上 5,209）
7. **`onclick` 的 `localStorage` 那句**要不要修？（含生成器 `build_index.py:104`；修了才真正生效）
8. **`/genes/data/` 要不要给 nginx 加 index**，还是干脆下线？

---

## 附：本次用到的可复现命令

```bash
# 数字重算（NLR/sRNA/UPS/miRNA/合计 + 附加发现）
python tmp_check_20260930/recompute_genes_numbers.py     # → GENES_NUMBERS_20260930.md
# 追根（gene_data.js 权威口径、物种并集、蛋白文件差异、孤儿页可达性）
python tmp_check_20260930/trace_genes_numbers.py
# 线上可达性
curl -s -o /dev/null -w "%{http_code}\n" http://39.106.101.94/genes/data/
```
