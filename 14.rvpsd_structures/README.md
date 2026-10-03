# 14. RVPSD 植物病毒蛋白 3D 结构模块

> 来源：RVPSD（RNA Viral Protein Structure Database, Yang et al., iMetaOmics 2026,
> doi:10.1002/imo2.70120），AlphaFold2 预测，CC-BY 4.0。
> 获取与解码过程见 `../oneoff_scripts/rvpsd_fetch/README.md`。

## 内容

| 路径 | 说明 |
|---|---|
| `webapp/` | **自包含静态站**（nginx 可直接挂载）：演示页 + 数据 + 查看器 |
| `webapp/index.html` | **主页面 = PDBe Molstar 完整复刻版**（与 RVPSD 同款全 UI：序列条/Structure Tools/Quick Styles；全原子走 Molstar cartoon secondary-structure 配色，CA-trace 自动切 3Dmol 骨架） |
| `webapp/lite.html` | 轻量备用版：3Dmol.js（全原子 pLDDT 四色 cartoon 优先，CA-trace 兜底），低配设备/主页面异常时使用 |
| `webapp/data/structures_index.json` | 1,832 物种 / 17,918 蛋白索引（名称、科、pLDDT、宿主、文件映射） |
| `webapp/structures/` | 17,918 个 CA-trace PDB（614 MB，gitignore，不入库） |
| `webapp/structures_fullatom/` | **14,843 个全原子 PDB（3.87 GB）**，权威植物病毒清单的完整 AlphaFold2 模型 |
| `webapp/structures_fullatom/pull_manifest_fullatom.tsv` | 下载清单（`accession / file / status / ts`） |
| `webapp/structures_fullatom_vp/` | **2,909 个 vpSAT ESMFold 全原子 PDB**（含 DNA 病毒/卫星，accession 命名 + vp_meta.tsv 元数据） |
| `webapp/structures_fullatom_afdb/` | **260 个 AlphaFold DB 官方 PDB**（DeepMind 出品，UniProt accession 命名） |
| `webapp/structures_fullatom_candidates/` | **4,481 个全原子 PDB（1.60 GB）**，B/C 两类候选补量 + 57 条真空补齐（见下节） |
| `webapp/structures_fullatom_candidates/pull_manifest_fullatom.tsv` | 候选下载清单 |
| `webapp/structures_fullatom_domains/` | **3,250 个全原子 PDB（589 MB）**，结构域切片 / foldseek 衍生条目的全原子模型 |
| `webapp/structures_fullatom_domains/pull_manifest_fullatom.tsv` | 切片下载清单 |
| `webapp/vad.html` | **VAD 补充批次专用页**：本地缺失的植物病毒蛋白结构 + RVPSD 已有蛋白的 VAD 对照版（单体/同源二聚体切换、双版本 pLDDT 对比），入口已挂在 index.html 页眉 |
| `webapp/data/vad_index.json` | VAD 批次索引：328 病毒种 / 2,033 蛋白（含病毒 taxid、谱系、宿主、陆生/绿藻标签、二聚体可用性、RVPSD 对照映射） |
| `webapp/structures_vad/` | **2,033 个全原子 PDB（450 MB）**，VAD 单体模型 = VAD 植物病毒全量（1,768 缺失补充 + 265 对照版） |
| `webapp/structures_vad/pull_manifest_vad.tsv` | VAD 单体下载清单 |
| `webapp/structures_vad_dimers/` | **2,009 个全原子 PDB（790 MB）**，VAD 同源二聚体模型（A/B 两链；24 条 VAD 未提供） |
| `webapp/structures_vad_dimers/pull_manifest_vad.tsv` | VAD 二聚体下载清单 |
| `webapp/vendor/3Dmol-min.js` | 3Dmol.js 2.5.2（BSD，本地化，无外部依赖） |

本地预览：`cd webapp && python -m http.server 8777` → http://127.0.0.1:8777/

## 全原子版（structures_fullatom/）

2026-09-29 全量下载完成。基于权威清单 `oneoff_scripts/rvpsd_fetch/plant_final_list.tsv`
的 14,842 条 `cds_id_fas`：

```
hit = 14,782    skip = 60（冒烟测试已下）    miss = 0    fail = 0
耗时 3,280 s（54.7 分钟），3 worker + 0.5 s 间隔
```

校验（`verify_fullatom.py` 口径）：缺失 0、空文件 0、无 ATOM 0、无 SEQRES 0、
未以 `END` 结尾 0；总体积 3,961 MB；原子数 154 / 1,995（中位）/ 41,219。

**完整性铁证**：与既有 CA-trace 版逐条对比，同一结构的原子数比为 **7.90 倍**
（10 例抽样落在 7.73–8.11），恰好等于蛋白质每残基平均重原子数（约 8）对
单 CA 的比值，说明拿到的是含侧链的完整原子模型。

## 全原子覆盖率：先说清口径（重要）

`webapp/structures/` 的 **17,918 个文件不是 17,918 个蛋白**，它由两类条目构成：

| 类别 | 数量 | 命名特征 |
|---|---|---|
| **全长蛋白条目** | **13,475** | 标准 `cds_id_fas`（`ACC_Virus_name_TAXID_product_len`） |
| 切片 / 衍生条目 | 4,443 | `..._CDD_<pfam>_<start>_<end>` 结构域切片 / `ACC_map<N>` foldseek 衍生 |

对某些蛋白，RVPSD **只发布切片、不发布全长**（典型：`AAA46903.1_Pepper_mottle_virus_12209_NA_3068`
在 index 与 CA 目录中均只有 8 个 `_CDD_` 切片 + 8 个 `_map`，无全长文件），
所以 17,918 不能直接当分母用。

**按全长条目算：13,475 / 13,475 = 100.00%**，一条不缺。
（自查脚本 `oneoff_scripts/rvpsd_fetch/verify_pdb_dir.py`）

之前记的「81.5%」是**口径错配**：分母用了 17,918（含 4,443 条切片/衍生），
分子用的是全长蛋白数，两者不是同一个集合。同理，早先 README 写的
「仅 CA-trace 有 3,355 条属另一套命名空间」也不准确——那批是 **index 的正式条目**，
只是片子，不是接口命名差异。

### 切片/衍生条目也已补齐（2026-09-29）

经大王决策，把 4,443 条切片/衍生中尚未获得全原子的 **3,250 条全部补下**
（2,275 个 `_CDD_` 结构域切片 + 975 个 `_map*` foldseek 衍生），输出独立目录
`webapp/structures_fullatom_domains/`（切片是不同性质的东西，不与 B/C 类候选混放）：

```
hit = 3,250    miss = 0    skip = 0    fail = 0
耗时 817 s（13.6 分钟），3 worker + 0.5 s 间隔，总体积 589.3 MB
校验：空文件 0、缺 ATOM 0、缺 CA 原子 0、缺 SEQRES 0、未以 END 结尾 0
```

**至此 CA-trace 目录的 17,918 条条目全部有全原子模型**：

| 口径 | 覆盖率 |
|---|---|
| 全长条目 13,475 | **100.00%** |
| 切片/衍生 4,443 | **100.00%** |
| 全部条目 17,918 | **100.00%** |

任何口径下都不再缺一条。

> 缺口补齐：57 条 CA-trace 全长条目曾在初批遗漏（`plant_final_list.tsv` 未收录，
> 多为新登录的植物相关病毒：`Ginkgo_biloba_dicistrovirus`、`Forsythia_suspensa_dicistrovirus`、
> `Helianthus_astrovirus_A`、`Camellia_totivirus_A`、`Citrus_blight-associated_pararetrovirus`、
> `Rice_dwarf-associated_bunya-like_virus` 等）。已实测站点对这 57 条**全部有全原子模型**
> （15/15 探针命中），于 2026-09-29 补齐，落在 `structures_fullatom_candidates/`。

## 两版关系

全长蛋白 13,475 条已 **100% 覆盖**（落在主批 + 候选批）。
主批另有 280 条按本地权威清单下载、CA-trace 目录未单列的条目（多为裸 accession 命名，
如 `AAA42587`、`AAA46289.1`）。

切片/衍生 4,443 条亦已 **100% 覆盖**（1,193 条随候选批顺带拿到，3,250 条专批补下于
`structures_fullatom_domains/`）。

下载路径与三条铁律见 `oneoff_scripts/rvpsd_fetch/README.md`。

## 候选补量（structures_fullatom_candidates/）

2026-09-29 补下。主批 14,842 条只覆盖「与本地权威植物病毒库按名匹配上」的记录；
站点收 GenBank 全量（13,051 个去重病毒名），本地库偏 RefSeq/ICTV（8,214 名），
有一批真植物病毒被落下。逐条分拣后补 4,424 条：

```
hit = 4,424    miss = 0    skip = 0    fail = 0
耗时 1,132 s（18.9 分钟），3 worker + 0.5 s 间隔，总体积 1,560.8 MB
单文件 13.9 KB ~ 2.9 MB（中位 36 万字节级）
校验：缺失 0、空文件 0、无 ATOM 0、无 SEQRES 0、未以 END 结尾 0
```

来源两类（清单位于 `oneoff_scripts/rvpsd_fetch/c_verdict/_pending_candidates.tsv`）：

- **B 类 260 条**：宿主字段明确是植物，但名字不在权威库。剔 5 条误捞后
  **净候选 48 条**（`banana_virus_x`、`sunflower_mosaic_virus`、
  `wild_cucumber_mosaic_virus`、`grapevine_emaravirus_a`、`cacao_yellow_mosaic_virus` 等）。
- **C 类 4,164 条**：宿主字段空但名字/科属像植物病毒。经 NCBI Taxonomy
  逐条判定（宿主界 + 病毒名线索），**142 条判为植物相关**（55 个名），
  其余为非植物或不可判定。判据与数字见 `oneoff_scripts/rvpsd_fetch/README.md`。

> 5 条误捞实证了「名字正则不可靠」：`lyssavirus_rabies`（狂犬，宿主 bat）、
> `goat_rhabdovirus`、`infectious_hematopoietic_necrosis_virus`（鱼病毒）、
> `beatrice_hill_virus`（宿主 Culicoides 蠓）、`cacao_virus`（宿主 Nyssomyia 白蛉，
> 白蛉在英语里带 cacao 地名词）。

## 数据说明（2026-09-29 更新：双层级已接入前端）

- **三源合并（2026-10-01 完成）**：结构库现有三个全原子来源——① RVPSD 主批/候选/切片；
  ② **vpSAT**（Nomburg/Doudna, Cell 2024，zenodo.10291581，ESMFold，含 DNA 病毒）2,909 条；
  ③ **AlphaFold DB**（DeepMind 官方）260 条。合并后索引 **2,603 物种 / 20,950 蛋白**
  （fullatom_map 25,743 条）。实测：vpSAT 独有的双生病毒蛋白（DNA 病毒）在
  Molstar 中以 secondary-structure 配色正常渲染。
- **查看器现为双层级**：`data/fullatom_map.json`（22,574 条 fas→目录索引）
  覆盖三个全原子目录，命中即 **cartoon 全原子渲染**（B-factor = 逐残基
  pLDDT，molstar 页）或 pLDDT 四色 cartoon（lite 页）；未命中自动回退
  CA-trace（α-碳小球 + 相邻残基连线）。信息行实时标注「结构」类型。
- **index.html 为 RVPSD 完整复刻**（2026-09-29 实测通过，序列条 + 右侧
  Structure Tools 全部显示）：同一插件文件（PDBe Molstar 3.11.0）、同一
  render 选项集（alphafoldView / leftPanel / **rightPanel / landscape /
  sequencePanel / domainAnnotation** 四个面板开关缺一不可，漏掉即面板收起）、
  同一手动加载链（download → parseTrajectory → createModel → createStructure
  → cartoon + secondary-structure 洋红/黄配色）。此前空画布的原因是选项集含
  无效项（lighting/hideControls 组合），非 webview 环境问题。
  已知微小差异：序列条标题显示文件路径而非 accession（molstar 以下载 URL 为
  entry 标签），观感无碍。
- **独立审计（2026-09-29）**：主批 manifest ↔ 落盘零缺失（多出 1 个为 ABRV
  冒烟测试件）；40 份随机抽检全部通过全原子判定（原子/残基比 ≥4、侧链元素
  齐全、B-factor 有值）。**植物子集 17,918 蛋白现已 100% 覆盖全原子模型**
  （主批 14,843 + 候选 4,481 + 切片 3,250，三目录合计）。
  早先记的「14,611（81.5%）」是口径错配（分母含 4,443 条切片/衍生），已作废。
- 只覆盖 **RNA 病毒**（RVPSD 收录范围 = Riboviria）；ssDNA 植物病毒
  （Geminiviridae、Nanoviridae 等）不在内。
- 候选批中 ~142 条植物相关文件为**裸 accession 命名**（如 `AAR00224.pdb`），
  已随 `fullatom_map.json` 并入前端解析（按文件名即可命中，凡 fas 即为
  accession 的条目无需改名）。
- 邮件草稿保留于 `../oneoff_scripts/rvpsd_fetch/email_to_rvpsd_authors.md`
  （用途转为：请求正式的全量打包许可与更新通知）。

## 部署

**线上：<http://39.106.101.94/structures3d/>**（2026-09-30 上线；入口卡片在
`docs/resources.html` 的 Data Resources 页，`/reference/resources.html` 同步可见）

nginx 片段（`/etc/nginx/conf.d/plant-virus.conf`，插在 `# ---- 7. Virus Vector Host ----` 之前）：

```nginx
location = /structures3d { return 301 /structures3d/; }
location /structures3d/ {
    alias /opt/plant_virus_db/plant_virus_db_pipeline/14.rvpsd_structures/webapp/;
    index index.html;
}
```

- `alias` 对子目录/深层路径天然有效，**不要加 `try_files`** —— `alias` + `try_files`
  会把 alias 值再拼一次完整 uri，子目录直接 404（同 `/phylo/molecular/` 的坑）。
- 裸路径 `/structures3d` 必须单独一条 `location =` 补斜杠，否则会落到 `location /` 兜底变 404。

### 只上传索引真正引用的文件（本地 6.8 GB → 线上 4.6 GB）

`webapp/` 本地 6.8 GB，但**索引只引用其中 17,918 个 PDB**，其余 5.1 GB 上传了也永远不会被请求：

| 目录 | 本地文件 | 索引引用 | 处置 |
|---|---:|---:|---|
| `structures/`（CA-trace） | 17,918（614 MB） | **0** | **不上传**。`structures_index.json` 每个 `fas` 100% 命中 `fullatom_map.json`，`initViewer()` 里的 CA-trace 回退分支永不触发 |
| `structures_fullatom/` | 14,843（3.87 GB） | 14,563 | 只传被引用的 |
| `structures_fullatom_candidates/` | 4,481（1.60 GB） | **105** | 只传被引用的 |
| `structures_fullatom_domains/` | 3,250（589 MB） | 3,250 | 全传 |
| 静态（3 html + 2 json + 3 vendor） | 8 | 8 | 全传 |

**实测线上体积**：`structures_fullatom` 3,899 MB + `_domains` 597 MB + `_candidates` 55 MB
+ 静态约 10 MB = **4,561 MB**，文件数 14,563 / 3,250 / 105，合计 **17,918**（`verify_server.py`）。

覆盖性证明（`tmp_check_20260930/check_local_coverage.py`，6 条判据全 PASS）：
索引 17,918 个 `fas` 在 `fullatom_map` 中命中率 **100%**，映射目录全部落在已上传的三个之内，
本地文件 0 缺失，tar 清单 0 缺漏、0 多余；`fas` 含 `/ \ : * ? " < > |` 者 **0**
（含这些字符会让 `encodeURIComponent` 出的 URL 与磁盘文件名对不上）。

⚠️ `tar -T` 的清单文件**必须是 LF**：CRLF 会让 `\r` 被当作文件名的一部分 → 全部
`Cannot stat`。更阴的是 `tar -cf - -T list | ssh host "tar -xf -"` 的退出码取自 **ssh**，
`set -e` 拦不住「本地 0 文件、远端 0 文件、退出码 0」的假成功 → 必须加 `set -o pipefail`。

### 数据更新

1. 重跑 `oneoff_scripts/rvpsd_fetch/`（该目录 README 有全流程）。
2. 跑 `check_local_coverage.py` 重算「索引引用集」，按同样方式增量上传。
3. 跑 `verify_server.py` 核对远端计数与抽样 md5。

### 与 Explorer 集成（**尚未实现**）

`index.html` 目前**不解析 URL 参数**（没有 `?species=&protein=` 入口），所以
`dcc.Loading` + `html.Iframe` 指过去的做法需要先给 `index.html` 加 URL 参数支持。
本轮按老师要求**未改 Explorer**。

## VAD 补充批次（structures_vad/ + structures_vad_dimers/，2026-10-01）

来源：**VAD — Viral AlphaFold Database**（Odai & Leemann et al.,
*Science Advances* 2025, doi:10.1126/sciadv.adz8560，Atkinson 实验室）。
VAD 对 RefSeq 病毒蛋白聚类后预测了 26,962 个单体 + 26,754 个同源二聚体
（AlphaFold2 全原子，pLDDT 写入 B-factor），数据开放在
`data-sharing.atkinson-lab.com/vad/`。RVPSD 只收 RNA 病毒，VAD 覆盖所有
病毒类型——本批次正是用它补齐 RVPSD 之外的植物病毒蛋白结构。

**"缺少"的口径**（脚本在 `../oneoff_scripts/vad_fetch/`，全程可复算）：

1. 从 Dataset S1 的 `sequence_clusters_lineage`（647k 行）取宿主谱系含
   **Viridiplantae** 的簇代表，且该代表在 VAD 里有结构 → 植物病毒代表 3,942，
   其中有结构者 **2,033**（陆生植物 465 + 绿藻 1,568）；
2. 与本地双层比对：accession 直比 0 命中（本地以 GenBank 为主、VAD 纯 RefSeq），
   **序列精确比对命中 265**（都是与 RVPSD 重叠的 RNA 病毒，同序列同结构）；
3. 剩余 **1,768 = 本地缺失**（陆生植物 200 + 绿藻病毒 1,568）。
   绿藻病毒（Phycodnaviridae 等 dsDNA 大病毒，Chlorella/Ostreococcus/
   Micromonas 宿主）此前在本管线完全空白，本批次一次性补齐。

**下载**（`pull_vad_monomers.py`，静态文件直连，8 worker，可续跑）：

```
单体   ok = 1,758 + skip = 10（冒烟测试）  = 1,768/1,768   fail = 0    682 s
二聚体 ok = 1,741 + skip = 10             = 1,751/1,768   17 条 VAD 未提供
校验   verify_vad.py：空文件 0、缺 ATOM 0、缺 CA 0、未以 END 结尾 0 → PASS
体积   单体 355.2 MB + 二聚体 631.0 MB
```

### 对照版：RVPSD 已有的也补了 VAD 版（2026-10-01 二期）

应用户要求（"RVPSD 的质量不一定有 VAD 的好"），把与本地 RVPSD **序列完全一致的
265 个**蛋白的 VAD 模型也下载入库作对照——`structures_vad/` 因此成为
**VAD 植物病毒全量集（2,033 个单体）**，RVPSD 原件一律未动（只增不改）。

```
对照版下载：单体 265/265 + 二聚体 258/265（7 条 VAD 未提供），102 s，fail = 0
复检：单体 2,033/2,033 全齐（449.5 MB）+ 二聚体 2,009（789.6 MB）→ PASS
```

**pLDDT 质量对比**（264 对同序列蛋白，VAD 版 vs RVPSD 版平均分）：

```
VAD 71.16  vs  RVPSD 68.70      Δ 中位数 +2.52
VAD 更高: 163   RVPSD 更高: 83   相当(|Δ|≤0.5): 18
```

即平均而言 VAD 版略优（约 +2.5 pLDDT，~62% 蛋白更高），但**并非全面占优**
（约 1/3 蛋白 RVPSD 版更高，两版最大差 ±17~21）——两套都是 AlphaFold2 预测，
差异来自运行版本/参数，逐条比较后择优使用即可。vad.html 的信息行对对照版
蛋白自动显示两边 pLDDT 与谁更优（如大麦温和花叶病毒 RNA2：VAD 73.7 vs
RVPSD 63.9），物种列表与下拉框用「RVPSD对照」标签区分。

注意 VAD 的 PDB **没有 SEQRES/HELIX 记录**（与 RVPSD 导出格式不同），
`rvpsd_fetch/verify_pdb_dir.py` 的 SEQRES 检查对它不适用，已用
`vad_fetch/verify_vad.py` 专用校验。

**前端**：`vad.html`（与 index.html 同款 PDBe Molstar 流程）+
`data/vad_index.json`，支持单体/同源二聚体一键切换；物种列表带
「陆生植物病毒 / 绿藻病毒」标签，可按宿主搜索，对照版蛋白带
「RVPSD 已有·VAD 对照版」徽章与 pLDDT 对比。index.html 页眉加了入口链接。
部署时除索引引用文件外，还需上传 `vad.html`、`vad_index.json` 与两个结构目录。

序列级比对用的本地序列库与中间产物（`local_fulllength_seqs.json`、
`vad_plant_reps_self.tsv`、`vad_plant_missing_final.tsv`、
`vad_plant_overlap_final.tsv` 等）保留在 `../oneoff_scripts/vad_fetch/`，
后续 VAD 出新版可直接重跑差集增量更新。

## 引用

Yang Q, et al. RNA viral protein structure database. iMetaOmics 2026;3(3):e70120.
数据 CC-BY 4.0；查看器 3Dmol.js BSD。

Odai R, Leemann M, Al-Murad T, Abdullah M, Hauryliuk V, Durairaj J, Pereira J, Atkinson GC.
The Viral AlphaFold Database of monomers and homodimers reveals conserved protein folds
in viruses of bacteria, archaea, and eukaryotes. Science Advances 2025. doi:10.1126/sciadv.adz8560
数据 data-sharing.atkinson-lab.com/vad/（补充批次 structures_vad*/）。
