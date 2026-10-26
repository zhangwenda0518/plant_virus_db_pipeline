# Changelog

All notable changes to the Plant Virus Database Platform.

## [2026-10-26] — 植物病毒口径收紧至"真正感染植物的病原"（48→42 科）+ VMR 引号解析 bug 修复

**最终基线**：**42 科 / 200 属 / 2,637 种**（原宽松口径 48/214/2,684）。Full 库覆盖 **42/42**、Ref 库覆盖 **42/42**——数据覆盖与名单完全吻合，KPI 满额，不再有"缺科"解释负担。

**第一轮（48→45）：分离来源不算感染**：ICTV VMR 的 `Host source` 字段中 `(S)` 后缀表示**分离来源**（从植物叶面/植物际/土壤分离到）而非被感染宿主。旧口径把 `plants (S)`、`phytobiome (S)` 也算植物，导致 3 个非植物病毒科混入：**Atkinsviridae、Solspiviridae**（Norzivirales 的 RNA 噬菌体，宿主 bacteria）、**Ambiguiviridae**（真菌相关，Erysiphe/Magnaporthe associated）。

**第二轮（45→42）：移除非病原意义的科**：逐科复核 45 科名单后确认 3 科不属于植物病原——
- **Metaviridae**（Athila/Del1/Tat4）、**Pseudoviridae**（Tnt1/Tto1/Tos17 等 22 种）：gypsy/copia 型**内源逆转录转座子**，整合在植物基因组内，无细胞外颗粒、无水平传播；ICTV 出于系统发生学纳入病毒分类，但不是感染植物的病原。
- **Pestiviridae**（仅 Koshovirus sonchi 1 种）：哺乳动物病毒科（猪瘟病毒所在科）；唯一记录 BK062903.1（Sonchus virus 1）系苦苣菜材料中检出的一条 TPA 序列，感染植物无证据。该记录**保留**在精选表中（ICTV 官方分类单元），仅不计入植物病毒科基线。
保留的灰色类群：卫星科（Tolecusatellitidae/Alphasatellitidae/Tomosaviridae/Tonesaviridae）、持久无衣壳病毒（Endornaviridae/Amalgaviridae）均属植物病原体系，ICTV 正式类群，维持收录。

**改动**：
1. `docs/phylo/build_taxonomy.py`：`PLANT_HOST_SOURCES` 收紧为 `{plants, invertebrates, plants}`；新增 `NON_PATHOGEN_PLANT_ELEMENT_FAMILIES = {Metaviridae, Pseudoviridae, Pestiviridae}` 并入科级黑名单。
2. `1.Prepare_plant_virus_pipeline/C4_clean_all_tsvs.py`：`PHAGE_FAMILIES` +Atkinsviridae/Solspiviridae，`FUNGAL_FAMILIES` +Ambiguiviridae，新增 `ENDOGENOUS_ELEMENT_FAMILIES = {Metaviridae, Pseudoviridae}` 并入 L4a（防御性；这两科本来就不会被 Viridiplantae 收录命中）。注意 **Pestiviridae 不入 C4 黑名单**——其唯一 Ref 记录有意保留。
3. **修复 build_taxonomy 隐性 bug**：`load_plant_species` 原用 `line.split('\t')` 手工切列，VMR 中含逗号的 Host source（如 `"invertebrates, plants"`）带引号存储、引号未剥除，导致该类记录**全部被静默丢弃**——Sedoreoviridae（水稻矮缩病毒所在科）、Spinareoviridae、Tospoviridae（番茄斑萎病毒所在科）曾因此漏判。改用 `csv.reader` 解析。
4. `docs/data/generate_dashboard_stats.py`：新增属级过滤（`meta.plant_genus_list`），KPI 属数与科名单同口径。
5. `U1_incremental_update.py`：新增 `NON_PLANT_FAMILY_BLACKLIST`（50 科，与 C4 联合黑名单逐科一致），`database_merge` 入库前拦截——此前增量查询按 `viruses[filter]+日期` 全量抓取、L1–L5 宿主判定无科级过滤，真菌/噬菌体/CRESS/内源元件病毒只要宿主谱系带 Viridiplantae 就会被月更误收，造成月度数据与全量重建漂移。
6. `monthly_update.sh`：新增 Phase 4.5（merge 后重跑 `generate_dashboard_stats.py`），修复月更后站点 /reference/ KPI 不刷新的缺口。
7. 站点数字统一：`docs/phylo/taxonomy_tree.json` 重跑（42 科/200 属/2,637 种），`dashboard_stats.json` 重生成（Full **42/42** 科、Ref **42/42** 科，属 198/200），`reference_index.html` kpi-note、`scripts/site_pages.py` phylo 描述、phylo 页 meta 同步为 42/200/2,637。

**Ref 46 科的由来（现已收口）**：旧宽松名单下 Ref 实际覆盖 46 科 = 48 − 缺 Metaviridae/Pseudoviridae（内源逆转录转座子科，GenBank 无独立病毒记录）；比 Full 多的 1 科是 **Pestiviridae**——唯一记录 BK062903.1（Sonchus virus 1 = *Koshovirus sonchi*），GenBank 原始记录 Family 列为空，仅精选表人工补了 VMR 归属。两轮收紧后 Full/Ref 均为 42/42。

**属级情况**：最终名单 200 属，两库覆盖 **198/200**。名单内未覆盖 2 属：**Magoulivirus**（本质为真菌病毒属，~50 种几乎全为 Botrytis/Fusarium/Magnaporthe 等真菌宿主，仅 *M. malus* 1 个植物种撑名单，其记录 MN386963 未进植物通道）与 **Betagymnorhavirus**（单种 Torreya virus 1，BK061818，ICTV 宿主标 plants 的真植物 rhabdo，TPA 记录未命中 Viridiplantae 收录通道）。**Lumovirus 已修**：精选表 MH425569 行的 VMR_Species/Family/Genus 等 6 列原为空（vmr_accession 匹配遗漏），已按 VMR 补齐（Geplanaviridae/Lumovirus），属覆盖 197→198。第一轮过滤曾剔除 11 属（3 个移除科的 8 属 + 仅凭 `plants (S)`/invertebrates 来源记录的 Epsilonourmiavirus、Rimosavirus、Somasatellite）；第二轮随名单移出 Koshovirus/Metavirus/Pseudovirus/Sirevirus 4 属。

**VMR 种级回填（同日第二轮）**：Ref 表曾 44%（3,983 条）记录 VMR_Family 为空——U1 月度增量兜底把 NCBI 组织名直接写进 Species_ICTV、未做 VMR 匹配。本轮：① 建立查找表 `docs/phylo/data/vmr_species_lookup.tsv`（17,554 种 + 别名共 35,431 键）；② 存量回填 Ref 2,966 条（256 条整段 VMR 字段 + 物种名规范化，2,710 条 taxid 继承补科）、Full 补 280 条科标签；③ **剔除 104 条非植物科记录**（Ambiguiviridae/Botourmiaviridae/Fiersviridae/Mymonaviridae/Phycodnaviridae 等黑名单科的残留）；④ U1 `database_merge` 内置 VMR 回填（入库即标注，未命中基线的非植物科直接拦截）。**发布口径变更：Ref 9,022 → 8,918 条 / 5,147 → 4,975 种 / 6,448 TaxIDs**（DATA_VERSION、NUMBERS.md、门户与 help 文案、build_global_index 注释同步）；属覆盖 198→199/200。

**KPI 口径调整（同日第三轮）**：/reference/ 卡片去掉"Sequences 条数"，改为 **Species 4,975 / Non-segmented species 3,681 / Segmented species 1,419**（按去重物种计，少数物种两类均有，故之和略大于总种数）；Data Source 切换默认 **Ref DB 在前**。`generate_dashboard_stats` 新增 segmented_species/nonsegmented_species 字段（记录数仍保留在 JSON 供核对）。

**新增对照表**：`docs/data/plant_virus_taxonomy_crosswalk.tsv` —— 42 科范围全部 3,632 种（严格基线 2,637 + 同科关联 995）的 ICTV↔NCBI 逐种对照：Family/Genus/Species_ICTV、ICTV_ID、Genome、VMR_Host_source、In_strict_baseline、NCBI_Taxids/Names、Full/Ref/Complete 记录数；NCBI 侧有记录的 2,220 种。已注册 API 网关 `taxonomy.plant-crosswalk`；`taxonomy.plant-taxa` 描述计数同步为 2,837。

**备份**：`docs/phylo/taxonomy_tree.json.bak.20261026_loose48`（原 48 科）、`*.bak.20261026_strict45`（中间 45 科）、`docs/data/dashboard_stats.json.bak.20261026*`、`docs/phylo/data/plant_taxa.tsv.bak.20261026*`。

## [2026-10-26] — 媒介库（8.plant-insect）：修 5 项数据/文档/路由缺陷 + 站点口径纠错

`/relations/#vector` 背后的媒介-宿主库做了五处修复，并顺带纠正了站点长期错标的统计口径。

**① transmission_routes 全空（数据断链）**：本地 `wur_virus_full.tsv` 还是旧 7 列格式
（无 `modes`、无 `duplicated`），`build_vector_db.py` 的 `parse_routes()` 拿不到输入，
导致 merged JSON 里**全部 1,803 个病毒的 `transmission_routes` 都是 `[]`**，前端
"TransmissionMeans" 柱图与 facet 全空；同因 `refs` 退回旧 `' | '` 字符串解析，
`authors/citation/means/doi` 四字段全空。重跑 `scrape_wur.py` → `build_vector_db.py` 后：
**1,186** 个病毒有 routes、**2,927** 条 ref 带结构化 `means`。

**② Literature 标签无数据源**：`vector_host_lit.json` 与生成脚本从未入库，`lit_edges`
恒为 0，页面上 Literature 标签永远空。新增 `8.plant-insect/build_lit_edges.py`。
关键决策：线上已存在一份 **10,187 边**的产物（生成脚本未回传），规模远超本地 33,325 篇
摘要能抽出的量级——因此**以线上产物为基线、本脚本做归并增强**，而不是用弱实现覆盖强数据；
`--from-scratch` 可强制忽略基线。结果 **9,958 边**（`transmitted_by` 1,551 +
`infects_host` 8,407），覆盖 3,527 病毒 / 4,687 文献，`matched_to_curated` 从 3,658 提到
**5,952（+63%）**。

**③ README 失真**：`8.plant-insect/README.md` 声称把 "Vector or means of transmission"
拆成"媒介拉丁名 + 传播方式"（代码无此字段）；宿主数写 380（380 是剔除 NA 后的口径，
含 NA 应为 381）。已订正并补 Literature 章节。

**④ 两个入口并存**：`docs/lib/site-nav.js` 已指向 `/relations/#vector`，但
`vector_page.html` 一直缺顶层跳转脚本，`/vector/` 直接访问会落到独立旧页面。补上后
遵守三要素：`window.top===window.self`（iframe 内不跳，否则外壳套娃）、`?full=1` 旁路、
`location.replace` 不留历史记录。

**⑤ `.gitignore` 与 tracked 文件矛盾**：7 个文件里 5 个是"声明忽略却已 tracked"
（`.gitignore` 对已 tracked 文件完全无效）。**判断变更**：原打算 `git rm --cached`，
但实测这些文件合计仅 ~1 MB、而仓库 pack 已 **1.04 GiB**，删除只新增删除提交、不减少
任何体积——改为让 `.gitignore` 与实际状态一致并逐条注明保留理由。同时补了
`*.bak_pre_*` / `*.orig_vmerg_*` / `*.bak_oldfmt_*` 规则。

**下游断链修复**：`19.api_gateway/registry.py` 的 `vectors.wur` filter 未覆盖重建后新增的
`modes`（受控词表，72% 非空）与 `duplicated` 列，已补上并校验所有 filter/search 列在
TSV 表头真实存在。

**站点口径纠错**：全站多处把 **1,803** 写成 "vector records / 媒介记录"，实际它是**合并后的
病毒条目总数**；真正带媒介关系的只有 **447** 个病毒 / 1,375 三元组。
`docs/help/vector.html` 还把数据源写成 "WUR + **EPPO Global Database**"（实为 WUR + VIP-DB）。
涉及 `docs/index.html`、`docs/relations/index.html`、`docs/help/{index,relations,vector}.html`。
统计键 `vector_host_pairs=1803` 改名拆为 `vector_virus_entries` / `vector_assoc_viruses` /
`vector_triplets` / `vector_routes_viruses` / `vector_lit_links` / `vector_lit_papers`
（`docs/data/site_stats.json`、`platform_stats.json`）；`scripts/build_global_index.py`
新增 `vector_counts()` **从合并产物现算**，防止月更后数字再次脱节。

**回归**：`/vector/?full=1` 15 项断言全绿（HTTP 200、四 tab 计数非零、无 Jinja 残留、
VH 1375 / WUR 1654 / merged 1803、`data_missing=False`、跳转三要素齐备）。

## [2026-10-24b] — knowledge_rag：参考 Agentic_RAG 升级检索链路

对照 <https://github.com/Anorlx/Agentic_RAG> 的机制做了一轮知识库改造，详细差距表与
路线图见 `6.knowledge_rag/AGENTIC_RAG_UPGRADE_20261024.md`。只取机制、不搬技术栈
（继续用 Qdrant/BM25S/DeepSeek），两条系统都动。

**修掉的真实缺陷**：`pv_records` 的 payload 只有 `record_id` 没有 `doc_id`，检索器统一
按 `payload.get("doc_id", -1)` 分组 —— 后果是全部 2.9K 条结构化记录被当成同一篇文档，
候选池最多只放行 3 个记录片段，引用富化时所有记录合并成 1 条且查不到标题。改为负数
命名空间 `doc_id = -record_id`，引用分别查 `pv_documents` / `pv_records`。

**路由真正生效**：改前 `classify()` 只写响应字段，META 问题照样检索+生成，PLANNING
prompt 永不触发。现在 `/query` 与 `/query/stream` 都走 `PvRouter`：META 零检索零 LLM，
PLANNING 使用自己的 prompt，响应回传 `route` / `rewritten_query`。

**证据评分 + 有界纠错**（Agentic_RAG 核心）：新增 `evidence_grader.py`（结构化判定
relevance/answerability/missing/next_action）与 `correction.py`（至多 1 次
Step-back/HyDE 重写，重检后复评，仍不足则返回空片段 → 结构化拒答）。默认关闭，
`PV_EVIDENCE_LOOP=1` 或评测 `--evidence-loop` 开启；grader 失败时退回旧行为，不会把
服务变成拒答机器。

**指标**：新增 `recall_at_k / mrr / ndcg_at_k / route_accuracy`，`EvalCase` 支持
`relevant_doc_ids` / `expected_task_type` 标签；未标注时报告打印 “not measured”，
不把 0.0 当成绩。

**L1/L2 父子块 + auto-merging**：新增 `chunk_hierarchy()`（父块按 markdown 标题切
2400/400，子块 1500/300）、`pv_chunk_parents` 表与 `pv_chunks.parent_id`（Alembic 0002）、
父子写入与 `PvChunkParentRepository`、检索端 `_auto_merge`（同父命中 ≥2 条用父块替换，
保留最佳片段 id/score 以便引用）。默认仍为平铺；启用需
`alembic upgrade head` → `pv-ingest reset-status --yes` → `index --hierarchical` →
`bm25-rebuild`（约 2.5h + ¥20-40）。未重建时 payload 无 `parent_id`，自动跳过。

**结构化库工具路由**：新增 `structured_router.py`，在 META 与向量检索之间识别
宿主/介体/科/属精确查询并查 `pv_records`（JSON/文本列 ILIKE），结果转成标准
`RetrievedChunk` 交给同一 generator；查空自动回退 RAG。规则要求列表意图 + 明确字段
线索，`Is TYLCV transmitted by whitefly?` 这类是非问句不会被列表劫持。顺带收窄
`task_classifier` 的 META 规则——原先 `哪些病毒…` / `which viruses…` 会被误判为语料
统计问题，既让 META 模板抢答，也挡住结构化路由。

**线上系统（:5002）**：① `数据库有多少病毒`/`你是谁` 走 META 路由，用真实统计回答
（生成模型数不了语料只会编）；② 段落按 markdown 标题强制分段并携带 `Section:`，
LLM 能区分“Bemisia tabaci 传播”出自 Host Range 还是 Ecology；③ 新增证据覆盖率闸门
（<34% 视为弱证据，注入明确拒答指令并回传 `evidence`）；④ 回答加 `[N]` 引用范围校验。
实测真实语料 10,245 docs → 60,651 passages、加载 10.1s、峰值 373MB、检索 0.23s。

顺带把 6 个长期失败的过期断言对齐到当前实现（默认 `top_k`、chunk 格式、oversample
倍率、题集路径、rewriter 的 expand 跳）。测试：`pv_rag` 245 passed / 2 skipped，
`6.knowledge_rag` 24 passed。

## [2026-10-24] — Explorer：Apply 按钮改重置；审查修复 6 个隐藏缺陷

筛选控件上一版已改为即时生效，`Apply Filters & Refresh Charts` 成为冗余按钮，改为
`Reset Filters`（一次恢复全部 9 项筛选）。围绕这个改动做了一轮全面审查，查出并修掉
几个一直存在但没人报的问题。

- **国家筛选长期失效**。旧逻辑「选了病毒就跳过国家筛选」，而 Target Virus Species
  默认预选 PSTVd —— 等于默认把国家筛选废掉，用户选国家毫无反应。改为条件可组合
  （AND）。实测 PSTVd + China 从 367 条（忽略国家）变为 110 条（正确）。
- **国家筛选默认值自相矛盾**。layout 写 Top-8，但 `parse_url_params` 首载时把它覆盖成
  空，Top-8 从未生效。统一为「不筛选 = 全部国家」，删掉死变量。
- **Primer 面板没有自己的选择器**，实际由 Genome-Wide Variation 的 MSA 选择器驱动 ——
  用户在 Primer Tab 上看不到那个控件。新增 `primers-virus-select` 并接入筛选联动
  （只列引物库里确实有记录的物种）。
- **引物查询每次全表扫描** 19MB / 10 万行（服务器约 2s）。改为启动时建字节偏移索引，
  按物种 seek 读取：**2s → 0.004s**。
- **下载按钮的 gff3/gb 用 gray**，看起来像禁用（这正是用户以为点不动的部分）。
  改为五种文件类型各一色（genome 蓝 / cds 青 / protein 绿 / gff3 紫 / gb 橙）；
  同时去掉 `<a><button>` 非法嵌套，改用带样式的 `<a>`。
- **地理图底图依赖海外 CDN**（`cdn.plot.ly/world_110m.json`，实测 3.4s，国内可能被拦）。
  自托管到 `/lib/world_110m.json`（136KB）并用 `Plotly.setPlotConfig({topojsonURL:'/lib/'})`
  指过去，线上实测无任何外部请求。

顺带：Data Browser 表格加表头排序/列过滤（纯前端，不打服务器）；重置按钮用
`variant="default"`（`light+gray` 浅到像 disabled）。

部署踩坑记录：服务端 dmc 2.8 的 `Anchor` 不接受 `title`、`dcc.Link` 不接受 `rel`
（本地 dmc 2.7 宽容，本地测不出来）。改完直接在服务器上跑了一遍全部面板构建函数，
9/9 通过后才重启。

## [2026-10-23c] — Explorer 模块导航：侧栏方案撤回，改回横排 + 缩短标签

上一版把 7 个模块名搬到左侧竖排，实际使用后判定不如原横排，撤回。

**为什么竖排更差**：横排 7 个全名合计约 1136px，而右侧主面板 1440 屏只有 1018px、
1280 屏 898px，确实放不下 —— 这是当初改竖排的理由。但竖排吃掉 217px 内容宽度，
DataTable 15 列只剩 790px，必须横向滚动才能看完一行；这个代价比标签换行更影响使用。

**改法**：保留横排，标签改短名 —— `Profile / Data / Trends / Variation / Primers /
Hosts / Vectors`，总宽降到约 700px，1280 屏也放得下。完整语义保留在各面板标题里
（Spatiotemporal & Geographic Distribution、Alignment Matrix & Mutation Rate Curve、
SeqIO Processed Dataset Archive 等），信息未丢失。窄于 1200px 时允许标签换行成两行。

**顺带修掉三个真实缺陷**（竖排期间暴露出来的）：

1. TabsPanel 默认 `min-width:auto` 被宽内容撑到 1664px（容器只有 1461px），
   右侧被裁到视口外 —— 表现为 Export 按钮和表格列消失。加 `min-width:0` 后由面板
   内部滚动。
2. 竖排时 TabsList 被 `align-items:stretch` 拉到 2054px 高，标签列下方拖出一条贯穿
   整页的空竖线（改用 `align-self:flex-start`，撤回竖排后该规则一并移除）。
3. Plotly 图表的 SVG 按渲染时的容器宽度定尺寸，之后容器变窄（窗口缩放、Tab 从隐藏
   切回、栅格重排）不会自动重算，撑出横向滚动条。`responsive=True` 只监听
   `window.resize`，覆盖不到这些情况，且 `Plots.resize()` 对静态图无效 ——
   必须用 `Plotly.relayout(p, {width: p.clientWidth})`。加了 ResizeObserver +
   MutationObserver 兜底，Tab 切换时补一次。

线上验证：1600/1440/1280/1150/1024/900 六档宽度均无横向溢出，7 个标签切换正常。

## [2026-10-23b] — Reference 首页改版：删 About 区块、并入 hero、对齐全站设计系统

`docs/reference_index.html` 重排。同时补上了这次改版缺失的部署文件。

- **删除「About This Database」整块**。它的内容只有一句说明 + 7 个流水线步骤，
  却独占一整张卡片、把首屏推到 900px 以下。说明并入 hero 正文，流水线改成 hero
  底部的 `hero-flow` 行（带分隔线），信息不丢、版位省掉一块。
- **首屏给出关键数字**：hero 下加 `hero-meta`（9,022 精选参考 / 211,132 条索引记录 /
  ICTV MSL41 依据）。原页面要滚过 About 才看得到任何数字。
- **数据源切换进「Database at a Glance」面板头**，与 KPI 同屏 —— 原来它孤立地漂在
  图表区和加载提示之间，没有容器归属。
- **KPI 用 `auto-fill` 而非 `auto-fit`**：Full DB 只有 3 个指标，`auto-fit` 会把它们
  拉成三张等宽大卡横贯整行，显得空旷；`auto-fill` 保留空轨道。
- **图表**：容器改固定高度（300px / Top-20 用 470px），修复 20 条横向条形图被裁到
  只剩 7 条的问题；`#charts` 先显示再建图 —— Chart.js 在 `display:none` 父级里量到
  0 尺寸，之后不会重绘（表现为卡片有标题、画布空白）；分子类型按规范名合并
  （`ssRNA+` / `ssRNA (+)` / `ss-RNA` 归一），环图图例从 20 项重复降到 13 项。
- **配色改用设计系统 token**：原图表的橙/蓝与全站深绿主色不协调，改为 accent 色族。

### 一并补上的部署缺口

改版把样式抽到 `/lib/pvdb-ui.css`、`pvdb-module.css`、`pvdb-chrome.css`（均未入库、
服务器上不存在），且 `site-nav.js` 新版输出的 `nav#pvdb-nav` 才能命中这些样式。
服务器上三份 CSS 全缺、`site-nav.js` 是旧版 → 新页面引用不到样式会变成裸 HTML，
导航也会白字透明底。本次把 4 个文件一并上传，线上验证通过。

## [2026-10-23] — Explorer 三项修复：加载提速 11×、模块联动、下载跳转；模块导航改侧边栏

用户报告三个问题：页面加载慢、检索后各模块不关联更新、点下载按钮会跳转。逐项定位并修复。

### 1. 加载慢 → 主回调 12.7s 降到 1.1s（线上实测）

根因是内存，不是计算。`df_global` 把 21 万条序列当 Python 字符串常驻（`Sequence` 列
占 **430MB**，整表 640MB），而服务器只有 3.5GB 内存、swap 已吃掉 2.5GB —— 每次筛选
`df.copy()` 都要换页。本地实测同样的计算只需 0.2s，线上要 12.7s，差值全是页表开销。

- **序列改为按需读取**：新增 `FastaIndex`（FASTA 字节偏移索引），只保存
  `accession → (offset, length)`，需要序列时 seek 读取。索引 1.6s 建成，取 30 条 5ms。
  缓存 470MB → 85MB，常驻内存 640MB → 84.5MB，服务器可用内存 913MB → 1763MB。
- **先截断再转 dict**：`to_dict('records')` 原本对全部 14.8 万筛选行执行（2.6s），
  之后才切到 `TABLE_MAX_ROWS=5000` 扔掉。改为先 `head()` 再转换。
- **去掉整表 copy**：主回调与 `update_virus_options` 的 `df_global.copy()` 改为掩码链式过滤；
  改 `Year` 列用 `assign()` 而非原地赋值。
- **Profile 加缓存**：`build_profile` 每次重读 73MB `papers.json`（1.4s）+ 全扫 19MB
  引物表（0.8s）+ `Ref.Info.tsv`，单物种 2.5–4.8s。改为启动时一次性建索引
  （`_PAPERS_ALL` / `_PRIMER_COUNTS` / `_REF_SEG_BY_SPECIES`），结果按物种名缓存
  （上限 64 条）。冷启 0.02s，热命中 0s。

### 2. 检索后模块不联动

- 五个展示选择器（Trends / Profile / Host / Vector）原本每次都重置成「记录数最多的物种」，
  用户在上方筛了某个病毒、下面各 Tab 却显示另一个 —— 这就是"不关联"的观感。
  改为读取左侧 `virus-filter`：选了具体物种则全模块统一显示这些物种；未选才回落到最丰富。
- 筛选控件全部接入主回调作为 `Input`（原来必须手动点「Apply Filters」才生效）。
  年份滑块加 `updatemode="mouseup"`，避免拖动过程中打出几十次全量重算。

### 3. 下载按钮点击后跳转

`Genome Annotation Downloads` 的链接指向 `/virus/files/<物种>/<文件>`，而 nginx 的
`location /virus/` 把整段前缀无差别 `rewrite ... permanent` 到 `/explorer/?profile=`，
于是每个下载都变成"跳回 Explorer 首页"。新增 `location ^~ /virus/files/` 直接转发到
8050（`^~` 优先于正则 rewrite），并关掉 gzip、加 `no-store`。线上验证：200 +
`application/octet-stream` + 真实 FASTA 内容，无重定向。

### 4. 布局：模块导航从顶部横排改为左侧竖排

`dmc.Tabs(orientation="vertical", placement="left", keepMounted=True)`。`keepMounted`
让切 Tab 不再重建面板。`TabsList` 用 `flexShrink:0` 由内容撑宽 —— 写死 `minWidth`
会让长标签溢出压到右侧内容区（首版即踩此坑，截图确认后修正）。

## [2026-10-17d] — MCP server：AI 助手直连查询全站数据

`19.api_gateway/mcp_server.py`（官方 `mcp` SDK，FastMCP）——把 /api/v1/ 包装成
Model Context Protocol 服务器，Claude Desktop / ZCode / Cursor 等 AI 助手可直接查库：

- **6 个工具**：`api_catalog`（目录入口，模型第一步）、`dataset_query`（过滤/搜索/
  分页覆盖全部 47 数据集，filters 规范列名 + 列表值 OR 语义）、`get_record`、
  `fetch_document`（stats/EVE/进化树/化合物详情等文档端点）、`global_search`、
  `resolve_virus_name`（通用名 → ICTV 规范名，写在工具描述里引导模型先解析）。
- **上下文保护**：不做 85 端点全暴露；单次返回 >60k 字符截断；MCP 侧 page_size
  上限 100；工具 docstring 即模型说明书。
- **传输**：stdio（桌面客户端接入，`PVDB_API_URL` 指向任意已部署环境，默认线上）；
  `PVDB_MCP_TRANSPORT=streamable-http` 可选服务器侧托管（:5020）。
- **验证**：`mcp_test.py` 端到端（stdio 握手 → tools/list → 8 个调用用例）8/8 通过，
  含错误路径（非法数据集 id 返回可读提示）。
- 人类文档同步：help/api.html「Machine-readable」区新增 MCP 接入块。

## [2026-10-17c] — REST API v1 上线：全站数据资产统一只读 API（/api/v1/）

新增 `19.api_gateway`（gunicorn :5010，`api-gateway.service`）——把平台全部数据资产以
程序化接口开放：**47 个可查询数据集 + 30 个 JSON 文档端点 + 10 个手写端点**，覆盖
19 个模块（reference / taxonomy / hosts / primers / gallery / compounds / stats / geo /
eve / genes / associations / network / vectors / pamir / literature / phylo / structures /
proteomes / search）。

- **架构**：nginx `/api/v1/`（最长前缀，`pvdb_api` 限流 120 r/min/IP）→ Flask 网关；
  数据集首次请求时从源文件懒构建 SQLite（`cache/ds_*.db`，mtime 失效自动重建，
  os.replace 原子替换多 worker 安全），月更数据零手动维护。
- **统一约定**：`{meta:{total,page,page_size,pages}, data:[...]}` 信封 + `X-Total-Count`；
  列精确过滤（列名规范化匹配）/ `q` 模糊搜索 / 排序 / `fields`·`exclude` 裁剪 / 分页
  ≤1000；CORS `*`；文档端点 ETag/304 + `?pretty`。
- **手写端点**：`/api/v1`（自描述目录）、`openapi.json`（OpenAPI 3，可导入 Swagger/
  Postman）、`search`（31,568 条全局索引）、`compounds`(+`/{name}`)、
  `pamir/genomes/{acc}`、`structures/rvpsd|vad/species/{key}`、
  `phylo/molecular/{family}`、`literature/years/{year}`、`health`。
- **数据以全量口径为准**：PAmiR miRNA 用 80,783 全库（非 /pamirdb/ 的 134 条演示子集）、
  文献用 33,325 全库；`docs/data` 里 `Plant_Virus_Full.Info.tsv`(211,132) 为主口径。
- **人类文档**：`docs/help/api.html`（端点目录从 /api/v1 动态渲染，含 curl/Python/R
  示例与命名规范说明），help 索引加 REST API 卡片，sitemap 收录。
- **验证**：`19.api_gateway/smoke_test.py` 全端点冒烟 85/85 通过（含大表懒构建：
  211k 序列 / 322k vsiRNA / 103k 引物 / 80k miRNA / 33k 文献）；ETag 304、CORS、
  fields/exclude、详情路由逐项实测。
- 注意：多数表物种名为 ICTV 规范种名，通用名先用 `reference/names?q=` 映射；
  accession 均带版本号（`NC_001926.1`）。

## [2026-10-17b] — 全站设计质量修复：impeccable 检测 1126 → 0（对比度/字号/层级/slop 清理）

引入 [impeccable](https://github.com/pbakaus/impeccable)（项目级 v4.6.0，`.claude/` 未跟踪 + 用户级 skill 升级）
作为设计质量门，与 `check_site_quality.py`（工程规范门）互补。全站 37 页扫描出 1126 条设计反模式，
四轮脚本化修复后 **复扫 0 条**。修复脚本存档于 `oneoff_scripts/fix_design_quality_{,r2_,r3_,r4_}20261017.py`。

**低对比度（WCAG AA，334 条 → 0）**
- 文字灰阶统一加深：`#8a99a8/#9aa7b4/#7a8a99/#95a5b5/#888/#999/#777` 等 → `#5d6b7a`（浅底 ≥4.5:1）；
- 主题蓝加深：链接/渐变端/按钮底 `#2e86c1`、`#4b97ca`、`#3e83b5` → `#1f6fa9`（白字/白底均 ≥4.5:1）；
- gene_browser 色板 chips/badges/segments：按 WCAG 亮度算法自动选字色（浅底保原色配深字、
  中深底配白字、不达标则逐级加深 0.93 至达标），Set3/Dark2 色板身份保留、可读性达标；
- help 页 hero 副标题 `opacity:.85` 混合色 → 实体色（检测器按混合后颜色评估）；viewtabs 未选中页签
  `opacity:.72` → 实体 `#e6eef5`；topbar 半透明白底 chip α .14→.07（混合底 ≥4.6:1）；
- 语义色文字加深：#e67e22→#b35309、#e74c3c→#c0392b、#ef6c00→#b35309；
- 彩色阴影中性化 rgba(20,60,90,*)/rgba(10,40,70,*) → rgba(0,0,0,*)（dark-glow）。

**字号（726 条 → 0）**
- 功能文字 <11px → 11px（统计带标签 10.5px、badge 9px、domain 段 8px 等）；
- 正文 <12px → 12px（gene_browser 数据表/段落）；导航 badge、页脚引用行同步提升。

**结构与其他（66 条 → 0/豁免）**
- 标题跳级：首页/help 首页分区标签 `div.sec` → `h2.sec`（样式不变）；help 子页 h3→h2；
  gene_browser h4→h3、h5→h4（35+16 处，行内样式保留外观）；
- side-tab slop：border-left 竖条与圆角并存 → 去圆角（.tip/.note/.ps-card/.notice 等）；
- cramped：`.dom-bar` 用同色 2px border 做内缩；relations `.stage` iframe 离边 8px；
  两个全出血可视化组件（domain 架构条、iframe 舞台）按工具推荐机制 scope-out（`.impeccable/config.json`）；
- broken-image：photos.html 灯箱 `<img src="">` → 1px 透明 GIF 占位；
- bounce-easing：ai-assistant.js 打字点动画 pvaiBounce → pvaiPulse（实为脉冲非弹跳）；
- em-dash-overuse：整规则忽略（中文破折号为正常标点，检测器按英文 AI 腔设计）。

**配置与卫生**
- `.impeccable/config.json`（可提交）：ignoreRules=[em-dash-overuse]、ignoreFiles=15 个 vendor 压缩库；
  `.gitignore` 增加 `.impeccable/*` + `!.impeccable/config.json`；
- 扫描范围不含 vendor 库（bootstrap/plotly/jquery 等压缩产物无法修复，永久排除）。

**验收**：`npx impeccable detect docs` → **0 findings**；Playwright 冒烟（首页/gene_browser/help/
download/relations）无 JS 错误、版式无破坏；自家 `check_site_quality.py` 37 页 PASS。

## [2026-10-17] — 全站工程化改造：注册表驱动的 head 规范 / SEO+JSON-LD / 学术页脚 / 质量门 / 部署根清淤

37 个静态页从「手改 HTML」升级为「单一事实源 + 生成器 + 质量门」的工程化管理（详见 `docs/README.md`
「站点工程化」一节）。

**新增工具链（scripts/）**
- `site_pages.py`：37 页注册表（文件 ↔ canonical 路由映射、中英标题/描述、JSON-LD 类型）+ 站点常量；
- `build_site_meta.py`：幂等注入 `<!--#[site-meta]-->` 规范 head 块（description/canonical/OG/Twitter/
  theme-color/缺失补齐 viewport+favicon），并生成 `sitemap.xml` 与 `lib/site-version.js`；`--check` 可挂 CI；
- `check_site_quality.py`：质量门 —— head 完备性、sitemap↔注册表一致、robots Sitemap 行、site-version↔
  DATA_VERSION 一致、**全站 397 条内链解析**（含 nginx alias 路由映射）、部署根卫生、JSON 可解析、
  单页体积预算。当前 37 页 PASS / 0 warning。

**SEO / 学术元数据（此前 7/37 页有 description、0 页有 OG/canonical/JSON-LD → 现全覆盖）**
- 全站 canonical + Open Graph + Twitter Card + theme-color；首页 schema.org **WebSite + DataCatalog**
  （含 9 个数据集条目），9 个数据页 schema.org **Dataset**（许可、标识符 pvdb-2026-10-03、dateModified）；
- `sitemap.xml` 落地 35 条 URL（nginx `location = /sitemap.xml` alias 之前一直 404）；
- robots.txt 的 Sitemap 行与部署源对齐。

**学术级署名与版本可见性**
- `lib/site-nav.js` v3：页面无自有页脚时自动注入学术页脚（平台名 · 数据版本 · MIT · GitHub ·
  推荐引用格式含访问日期）；修复 `data-active`/`data-badge` 在 DOMContentLoaded 分支因
  `currentScript` 为 null 而静默失效的潜在 bug；nav 增加 `aria-label`；
- 首页页脚升级为 数据版本 v{DATA_VERSION} · MIT License · GitHub（版本由 site-version.js 供给）；
- `i18n.js` 中英浮钮补 `aria-label`。

**性能**
- 首页 echarts（约 1MB）从同步加载改为**展开访客地图时按需注入**，首屏零阻塞（Playwright 实测：
  加载时序证明懒加载生效、地图渲染正常）；
- 首页检索框补 aria-label。

**缺陷修复**
- `download.html` 残缺标记修复（游离 `</div>` + 孤儿下载按钮，某次手改遗留）；
- `phylo/molecular/index.html` 重定向存根补 viewport/favicon/robots noindex（由生成器统一供给）。

**部署根清淤（web root 不再暴露备份）**
- docs/ 下 100+ 个 `.orig_*` / `.bak_*` / `_tmp_*` / `hosted_*` 文件全部移出：
  页面/JS 备份 → `archive/website_backups_20261017/`（已 gitignore）；
- docs/data/ 下 24 个数据 `.bak`（含 395MB fasta 备份）与 4 个历史批次快照目录
  （canonical_20261003 / live_20261003 / online_20260901 / deploy_20260918，共约 2.9GB、全仓零引用）
  → `data_backups/docs_data_20261017/`（已 gitignore）；docs/association/__pycache__ 删除；
- `plant-virus.conf`：`location /` 增加 `error_page 404 /404.html`（仅静态根，API 不受影响）；
  备份拦截正则补 `\.orig_`（原只拦 `.bak`/`_bak`，`.orig_*` 一直可被下载）。

**验收**：`check_site_quality.py` 37 页 PASS；Playwright 本地冒烟（首页/访客地图懒加载/下载页/help/404/
页脚注入）无 console 错误（本地 404 均为 nginx 专属路由的预期现象）。

## [2026-10-16] — 全站数字校对：卡片/统计与实际数据全面对齐（用户反馈"卡片显示和实际数量不符"）

6 路并行只读审计 + 逐项实算修复。所有数字一律以当前数据产物为准（参考库 `Plant_Virus_Ref.Info.tsv`
9,022 行 / Full 211,132 行，2026-10-03 批次；`docs/data/NUMBERS.md` 为单一事实来源）。

**事实表与数据源（先刷源头，再改页面）**
- 重跑 `docs/data/generate_dashboard_stats.py` → `dashboard_stats.json`（ref 8,465→**9,022**、
  full 199,068→**211,132**，7 月旧快照退役）；`1.Prepare.../lib/render_numbers.py` 重出 `NUMBERS.md`。
- `docs/data/site_stats.json` 重写：12,159→**9,022**、照片 2,854→**2,975**、媒介 1,806→**1,803**、
  文献 6,525→**33,325**（master 口径）、物种 4,840→**5,147**（ICTV；NUMBERS 首次生成的 5,148 系 render_numbers 把 ragged 行 null 计入，已修并复核）。
- **重建 `docs/association/associations.json`**：`build_associations.py` 先修崩点（新批次 TSV 含
  2,655 行空/非法 Taxid，原样 `int()` 必崩 → 跳过并注释），重建后 meta=15,197 对 / 5,134 病毒种 /
  3,702 宿主 / 208,477 可映射序列（旧 14,791/199,070 为 09-21 批次）；`docs/network/network.json`
  连带重建（vh 1,375/447/100/380 不变，继承 meta 更新）。

**首页 `docs/index.html`**：hero 五格全部改实数（9,022/2,975/1,803/33,325/1,341）；八张卡片文案改口径——
参考库 9,022/5,147、照片 2,975、关系 15,197 对/211,132/1,803、引物 57,075/4,798/41,000 RECOMMENDED
（原 103,642/4,789 是 6-30 静态导出，与线上库 57,075 两套批次）、结构卡改区间口径 53,000+/4,200+
（原 53,240 出自未入 git 的 merged 索引且 AF3 文件不在仓库）、PV-miRNA 402×42→11,006 预测·799 植物·
40 病毒科（402/42 全库无出处）、文献 33,325+6,525 AI-curated、RAG 229,184→**193,277** vectors
（唯一有构建验证记录的值，见 pv_rag/README；TECHNICAL_REPORT 同步改）。

**参考库各页**：reference_index 硬编码 199K/8.5K→211K/9.0K；table.js 199K→211K；download.html
四条下载件记录数/列数/体积全改（9,022·29 列·3.1MB / 211,132·21 列·410MB·51MB）；help/reference
199,499→9,022、6,182→5,147；help/index 与 help 各分页（照片/关系/媒介/基因/文献/PV-miRNA）同步。

**关系模块**：relations/association/network 三页静态文案（211,132/15,197/5,134/3,702/1,803）——
动态统计条此后直接读重建后的 JSON，自动正确。

**EVE（docs/eve/）**：回填 `eve_landscape.json` 的 `host_families[].rna`（原全 0 → 按
`eve_dynamics.past_present` 实际值，RNA 视图排序恢复，头部 Poaceae 147/Porellaceae 136/Gentianaceae
110）；页内文案 4 处改实数（PVCV 953→952、未解析物种记录 801→1,258、top-20 位点 14,512→15,292、
参考病毒 21→19）；"63.4% soft-mask" 无法从数据复现 → 改定性表述。

**/genes/（抗性基因）**：docs 三页 837→**799** 物种（miRNA_final_stats 权威值，源目录 10-13 已改、
docs 是旧拷贝）、"12 plant + 19 virus"→**20**；`docs/genes/data/` 数据件与标签对齐——pvsirnadb
TSV 换干净版（327,012→322,214 行，去掉 4,797 重复+1 垃圾行）、7 个 sRNA 家族 TSV 按
`all_genes_classified.json` 重切（4,019/631/1,951/1,190/29/131/3,829，原 served 件是另一批数据）、
`pvsirnadb_embedded.json` 重生成（total 327,010→322,214）、all_genes_classified.json 同步源版。

**结构模块**：atlas `build_data.py` 重跑（TSV 10-15 新增 142 条 SELF 后 stats.json 一直停在 10-03：
own 1,112→**1,254**/26.1%、any 4,445→**4,587**/95.4%、真零 365→**223**、P3 304→**183**、by_src 补
SELF=142）；横幅按 genome.json 改（91.6%→**92.2%**、26,604→**26,788**、2,455→**2,271**、
986→**860** 代表簇）；修 `structures_index.tsv` 142 行 `selffold_model` 文件名缺 `ACC__ACC` 前缀
（142 个 3D 查看器链接全 404 → 全部可解析），改后重跑 build_data.py 同步 proteins.json。

**文献站**：`web/index.html` metric 条拆双口径——"Papers Indexed (master) 33,325" + 新增
"AI-Curated Entries"（=index.json 动态求和 6,525），页头 33,325 与列表 6,525 不再互斥。
另把 "AI Knowledge Assistant" 标签页四格硬编码统计（7,099/2,892/20,010/229,184，均无出处）
整块换成可验证口径：33,325 master / 6,525 AI-curated / 193,277 Qdrant vectors；
`docs/help/pamirdb.html` 的 402×42 同步改为 11,006 预测·799 植物·40 病毒科。

**README**：根 README 与 4.virus_primer/README 引物数字加双口径标注（线上库 57,075/4,798 vs
静态导出 103,642/4,789）。

**遗留（本次不改，待定方向）**：① `structures_index_merged.json`（未入 git，10-11 建）已落后 142 条
SELF，且无页面消费；② 引物线上库(57,075)与静态导出(103,642)两套批次未合一（需重跑 step3/step4）；
③ PV-miRNA 首页"3-algorithm consensus"方法表述与模块自述（自研 SW-DP）矛盾，归 METHOD_STATUS
待决；④ 文献 by_category 20 个旧标签未归一到 9 个配置类；⑤ literature web/data 年分片 14 个
陈旧文件（合计 6,575 的出处）未清理。

所有被替换的数据文件均留 `.bak_20261016` 同目录备份（nginx 对 `*_bak*` 返回 404，不会外露）。
**全仓文档过时数字清理（2026-10-16 傍晚）**：审计报告类历史文档（AUDIT_REPORT_20261003 /
AI_MODULE_DB_AUDIT_20261008 / INCREMENTAL_METRIC_AUDIT_20261007 等）按其时点记录原则不改，其余文档清点修正：

- `docs/data/DATA_VERSION`：`SPECIES_COUNT` 5173→**5147**（该键无脚本写入属手维；以 Ref.Info.tsv
  `Species_ICTV` 去重实算为准，`render_numbers.py` 的 null 计数 bug 修复后 NUMBERS.md 同值）。
- 根 `README.md` 数据量表：物种 5,173→5,147、媒介-宿主病毒 1,806→**1,803**、精选文献 7,099→**6,525**
  （注明 master 33,325）、"RAG 知识库论文 60,000+/50K chunks"→**193,277 Qdrant vectors**（有构建验证值的口径）、
  照片 925→**2,975**（925 实为 EPPO 单源；五来源 EPPO 925/DPV 1,230/Book 432/PDF 360/Open-i 28）、
  目录树 (925 张)→(2,975 张)。
- `TECHNICAL_REPORT.md`：§1.2 表（8,465→9,022、6,182→5,147、引物 57,072→83,830 去重后、文献 7,099→6,525）、
  §cluster_fasta ~8,465→9,022、§primers 57,072/4,799→83,830/4,789、§photos 四来源 925→五来源 2,975、
  §pamirdb "402×42"→11,006 预测（799 植物×40 病毒科，自研引擎）、§vector 1,806→1,803；
  export_primers_static.py 的"8,925 行"（实为字节数的旧误）删除计数。
- `docs/README.md`（线上 /README.md 直接服务）：cluster_info ~8,465→9,022。
- `docs/association/README.md` + `docs/network/README.md`：199,070/14,791/4,820/3,040 →
  **211,132（208,477 可映射）/15,197/5,134/3,702**，与重建后的 associations.json meta 同源。
- `15.uniprot_plant_virus_structures/README.md`：四路皆无 365(7.6%)→**223(4.6%)**、任一来源有结构
  4,445(92.4%)→**4,587(95.4%)**、多聚蛋白 304→**183**（10-15 增 142 条 SELF 后口径，与重建 stats.json 一致）。
- `16.fold_web/README.md`：待预测缺口 3,698→**3,556**。
- `3.virus_explorer/README.md`：papers.json 7,099→**33,325**、媒介 1,806→1,803。
- `7.literature_tracker/README.md`：精选文献总计 7,099→**6,525**（master 33,325）。
- `4.virus_primer/README.md`：快照表下补当前线上库口径行（83,830 去重 / 按类型 / 验证分布）。
- `1.Prepare_plant_virus_pipeline/README.md`：批次数字"定稿前需统一"悬案结案——发布口径 = 9,022/6,534
  （DATA_VERSION + NUMBERS.md），8,465/8,464/8,484 标注为历史批次。
- 不改的：AUDIT/METHOD_STATUS/SECURITY 等时点审计报告；`6.knowledge_rag/databases/` 语料正文；
  各 `*.bak_*/.orig_*` 备份；CHANGELOG 历史条目。

**引物库合一（2026-10-16 下午，用户拍板后执行）**：生产机仅 2核/3G 且无流水线资产 → 在本地
20核/64G 跑通全链。`makeblastdb` 建病毒库（Plant_Virus_Full.fasta 211,132 序列，LMDB 需纯 ASCII 路径）；
`step3`（修复版）对 2026-06-30 设计批次 103,642 对做 dimer+GC/Tm+病毒 BLAST 全量验证（按
(物种,Fwd,Rev) 去重 → **83,830 对**；RECOMMENDED 66,891 / USABLE 15,345 / NOT_RECOMMENDED 1,594；
植物脱靶与物种内覆盖度本次未跑——本批无 split_species FASTA，见遗留）；`step4` 建库
（taxonomy 由导出 TSV 聚合生成 species_index.tsv，genome_length 从旧线上库回填 4,786 物种）。
上传生产机换库（旧库备份 `primer_database.db.bak_premerge_20261016`），`primer-web` 重启后
`/api/stats` = 83,830/4,789/50 ✓。首页/帮助页/README 引物数字全部同步为合并后口径，
"静态导出 103,642" 双口径备注废除。



## [2026-10-12] — 全站顶部导航统一为 /pamirdb/ 设计（site-nav.js 共享组件）

此前站内并存 **4 种导航**：pamirdb 渐变版（46px，`linear-gradient(135deg,#1a3a5c,#2c6e49)`）、
docs 主站深蓝版（`#1a5276`，52px）、genes 深蓝版（`#1a3a5c`，48px）、knowledge/literature 旧版
（还带已停用的 `/virus/`、`/te/` 链接）；另有 10+ 页面（首页、结构子页、pamirdb 弦图页、foldweb 等）
**完全没有导航**。统一到 /pamirdb/ 截图同款设计：

- **新增共享组件 `docs/lib/site-nav.js`**（线上经 `/lib/site-nav.js` 分发）：注入 `#pvdb-nav`
  渐变导航，条目与 pamirdb 完全一致（Reference/Photos/Vector/TE & EVE/Genes/Primers/OneKP ‖
  Explorer/Metabuli/PV-miRNA ‖ Literature/Knowledge/Resources/Help）；CSS 全部以 `#pvdb-nav`
  作用域书写，不与页面自身 `nav{}` 规则打架；自动按 URL 高亮当前栏目（`.on`/`.active` 双兼容，
  与 `i18n.js` 的 markActive 同口径）；文案自带 `data-i18n` 双语标注；页面没引 i18n.js 时自动补载
  （顺带获得全站中英浮钮）；支持 `data-badge` / `PVDB_nav.setBadge()` 右侧徽标。
- **替换旧站点级导航（10 文件）**：photos、knowledge `api_server.py`(+pv_rag ui.py)、literature
  `api_server.py`+`web/index.html`、vector_page、step5(DEV/PROD，Bootstrap 导航退役并去掉
  `body padding-top` 补偿)、metabuli（`.bar` 即旧导航，连带样式清除）、pamirdb 旧版 index.html。
- **Reference/Genes 模块页改为「全局导航 + 浅色 `nav.pvdb-subnav` 二级条」**（12 文件）：
  reference_index/segmented/nonsegmented/submit/download、genes 三页、11.antiviral_genes 生成器
  （build_index.py / build_gene_browser.py）同步改模板，重新生成不回退。
- **保留局部 topbar/header、上方插入全局导航（16 文件）**：eve/relations/network/association/
  phylo(含 molecular)、首页、structures3d 外壳+rvpsd/lite/vad、atlas index+viewer、foldweb、
  pamirdb chord_compare/network、phylo/molecular/index.html（原漏网页面）。
- **Dash 应用**：explorer（app.py + app_server.py）、onekp 的 `index_string` 在 `<body>` 后注入同一
  `<script src="/lib/site-nav.js">`。
- **附带修正**：pamirdb 基准页 `index_new.html` 的 TE & EVE 改指 `/eve/`（省一跳 301）；photos
  灯箱与 metabuli 遮罩 z-index 提到 10010（原 200/999 会被 sticky 导航盖住）。
- **[2026-10-13 追记] 去掉 topbar 双重品牌**：全局导航已含 "Plant Virus DB"，
  relations/eve/network/association/phylo×2/structures3d 外壳共 7 处 `.topbar` 里的
  品牌 div + 分隔符删除（备份 `*.orig_topbar_20261013` / 线上 `.bak_topbar_20261013`），
  局部条只留模块副标题 + 统计芯片。
- **[2026-10-13 追记] Dash 三应用删除旧内建导航头**：explorer `app.py`(+`app_server.py`)、
  onekp `onekp_app.py` 的 `dmc.AppShellHeader`（旧深蓝导航，含已停用的 /virus/、/te/ 链接）
  在全局导航上线后被顶到 sticky 导航下面不可见，但 Mantine 的 52px header 占位保留 →
  /explorer/ 顶部出现一条空白带。删除 AppShellHeader 与 `header={"height":52}` 占位，
  原头部独有的数据徽标（species/sequences/数据版本）改为正文顶部右对齐一条。
  服务器备份 `.bak_dashhdr_20261013`，virus-explorer / onekp-dashboard 已重启。
- **[2026-10-13 追记] structures3d 外壳藏子页全局导航**：外壳以 iframe 内嵌 atlas/rvpsd
  子页，子页注入的 `#pvdb-nav` 会与外壳顶栏重复成三层条 → `muteInnerChrome()` 注入
  `#pvdb-nav{display:none!important}`（子页单独打开不受影响），备份 `.bak_topnav_20261013`。
- **[2026-10-13 追记] help/×18 + resources.html 收编进共享导航**：全站目检发现这 19 页
  此前只统一了渐变**样式**、导航**条目**仍是旧集合（缺 OneKP / TE & EVE，分组竖线错位，
  Help 被 spacer 挤到最右）→ 删除各自内联导航与 `nav{}` CSS，统一改挂
  `/lib/site-nav.js`（备份 `.bak_navitems_20261013`）。此后全站导航条目只有
  `docs/lib/site-nav.js` 一个出处。
- **[2026-10-13 追记] 全站头部体检**：40 条线上路由结构扫描（HTTP 码 / 导航计数 /
  品牌重复 / 残留旧标记）+ 20 余页浏览器目检（重复导航、空白占位带、高亮错误、
  遮挡关系），除上述 help/resources 条目旧集合外无其它问题；`/species/` 裸路径 404
  为历史行为（需带物种 ID），与本次无关。
- **[2026-10-13 追记] 首页撤掉导航**：首页是 hero + 全模块卡片的落地页，顶部导航
  冗余 → 移除注入（备份 `*.orig_homenav_20261013` / 线上 `.bak_homenav_20261013`）。
  澄清 IA：`/reference/` 并非首页别名，nginx 为其配了独立 index，服务的是
  Reference Database 仪表盘（reference_index.html，带全局导航 + 模块 subnav），
  因此撤首页导航无连带影响。现状：首页=纯落地页；其余功能页=全局导航+模块条。
- **[2026-10-13 追记] Vector 并入 /relations/ 单一入口**：`/relations/#vector`（媒介与
  文献库视图，原为 iframe 内嵌 /vector/）与独立页 `/vector/` 合并为一个入口——
  ① 全站导航 Vector 改指 `/relations/#vector`（site-nav.js + pamirdb 内联导航）；
  ② `/vector/` 顶层直接访问自动 `location.replace('/relations/#vector')`，
  `?full=1` 保留独立全屏表格，iframe 内嵌不受影响；
  ③ relations 外壳 `muteInnerChrome` 增加藏内嵌页 `.hero`（消除页中页双标题与
  1,806/1,375 双计数打架）；
  ④ 外壳 `syncNav()` 跟视图同步全局导航高亮（仅 #vector 点亮 Vector，
  其它视图清掉 i18n markActive 前缀误加的 .active），页脚文案同步改写。
  备份 `*.orig_vmerg_20261013` / 线上 `.bak_vmerg_20261013`，vector-host 已重启。
- **[2026-10-13 追记] site-nav.js 不缓存 + 全站 include 带 ?v=2**：导航单一出处化后
  原 `/lib/` 的 `expires 7d` 会让存量访客最长 7 天拿不到新导航。nginx 增加精确
  `location = /lib/site-nav.js { no-cache }`（conf 备份 `.bak_sitenav_20261013`，
  本地 plant-virus.conf 镜像同步），全站 61 处 include 统一升 `?v=2`
  （此后改导航须同步升版本号）。
- **备份**：全部改动文件旁留 `*.orig_pamirdbnav`（与既往 `.orig_navall` 惯例一致）。

**验收**：本地 `_probe/nav_test_server.py`（模拟 nginx 路径）+ 浏览器实测——首页/photos/genes/eve/
structures3d-lite/reference_index 均正确渲染两层导航且当前栏目高亮；中文切换后导航翻译正常；
help/resources 旧内联渐变导航回归无损；py 模板 10 个文件 `py_compile` 通过、site-nav.js
`node --check` 通过。

## [2026-10-08] — 后续调整 ②：`/structures3d/` 外壳「Atlas 单页化」（三标签 → 两标签）

老师反馈：「Statistics panel / Coverage atlas 保留一个不就可以了嘛？…乱的很，重新设计规划」。
诊断出的重复（全部消掉）：

1. **同一排指标卡渲染两遍** —— `atlas/index.html` 8 张 vs `atlas/stats.html` 8 张，其中 **7 张逐字相同**；
2. **外壳把子应用自己的导航做了两遍** —— 模块 15 本来就有「总览｜统计面板｜预测平台 ↗」，被 `muteInnerChrome()` 藏掉，又在外面重做；
3. **外壳 chips 与子页读数逐项重复** —— `2,603 物种·20,950 模型` 与 `rvpsd.html` 自己那行一样；`4,810/92.4%/3,698` 与 Atlas 指标卡一样；
4. **「预测管线」内容其实没删掉** —— 模块 15 总览页里就有一整块「蛋白结构预测管线（缺口 3,698 条怎么补）」；
5. 外壳多一行「描述 + 本页直达锚点」，与标签副标题重复；
6. 三标签视觉语言不统一，切换时整屏风格跳变；
7. 藏 header 时丢掉了「预测平台 ↗」入口。

**改动**：

- **模块 15 `webapp/index.html` 重写为单页**：`stats.html` 的四节（完整率甜甜圈 / 缺口分层 / 来源组合明细 / 管线台账）全部并入；
  header 由深蓝横条（与外壳顶栏撞色）改为**浅色 sticky**，页签换成**页内锚点条**
  （总览 / 来源组合 / 蛋白检索 / 病毒级覆盖 / 缺口与完整率 / 管线台账），滚动时高亮当前小节。
  指标卡由两页各 8 张合并为**唯一一份 9 张**（并集，加 `reviewed`）。
- **`15…/webapp/stats.html` 退役**：本地 → `archive/_pending_delete_20261008/stats.html`（MANIFEST 登记，
  md5 `b023a14f…`）；线上 → `_backup_20261008_structures3dhub/retired/stats.html`；URL 301 回 `atlas/`。
- **外壳 `14…/webapp/index.html`**：3 标签 → **2 标签**（结构总览 / 3D 模型浏览）；`.strip` 卡片条并进
  `nav.topbar`（深色栏上的胶囊按钮），`.head` 描述行整行删除、`acts` 并进 topbar，
  4 颗 chips 删除 —— **顶栏从三条栏收成一条**。
- **`muteInnerChrome()` 不再藏子页 `body>header`**：atlas 的 header 现在是「页名 + 页内锚点条」，
  正是需要的第二层定位；只藏子页那颗浮动语言按钮。（rvpsd 的 header 本来就不藏。）
- **旧深链兼容**：`#stats` 回落 atlas 并滚到「缺口与完整率」；新增 `#atlas/<section>` 复合形式；
  `#pipeline` 仍优雅回落。
- **nginx**：`/etc/nginx/conf.d/plant-virus.conf` 就地补丁（+`location = /structures3d/atlas/stats.html { return 301 /structures3d/atlas/; }`，
  两处注释改「两标签」），备份 `plant-virus.conf.pre_singlepage`；`nginx -t` 通过后 reload。
  镜像 `deploy/nginx_full.conf` 与线上该区段 md5 **完全一致**（`47f622b2d54fe8746fce1c737c15f349`）。

**验收**：`_probe/check_structures3d_ui.py` 重写为 57 项（2 标签 / 顶栏无 chips / atlas header 不藏 /
锚点条 6 项 / 详情面板仍在舞台内 / `#stats` 回落 / stats.html 301）。本地 staging **57/57**，线上 **57/57**。
三个上传文件本地与线上 md5 逐字节一致（外壳 `ccd0584e…`、模块 15 index `d21271c4…`、common.js `da0f5be3…`）。

**文档同步**：`docs/README.md`、`docs/help/index.html`、`docs/help/uniprot3d.html`、`docs/resources.html`、
`docs/index.html`（首页卡片「four tabs」→「two tabs」—— 上一轮摘 pipeline 时漏改，本次一并修正）、
`USER.md`、两个模块 README、`SECURITY_DEPLOY_20261008.md`、`deploy/nginx_full.conf`、`deploy/_new_conf_staging.conf`。

---

## [2026-10-08] — 后续调整：从 `/structures3d/` 摘除「预测管线」标签（Batch Folding Queue）

**背景**：老师复核统一入口后判定 **Batch Folding Queue（`16.fold_web` 的 ColabFold 队列）没啥用**，
从统一入口去掉。范围按老师选定 = **只去掉入口标签**，`/foldweb/` 服务与模块 16 一律不动。

- **外壳四标签 → 三标签**（结构总览 / 统计面板 / 3D 模型浏览）：`14.rvpsd_structures/webapp/index.html`
  删掉 `VIEWS.pipeline` 与 `ORDER` 里的 `'pipeline'`，同步改 meta description、注释与页脚文案
  （"Four views, three original pages" → "Three views, two original pages"）。
  **旧深链 `#pipeline` 优雅回落**到默认视图 atlas（`VIEWS[k] ? k : DEFAULT_KEY`），不白屏。
- **`pipeline.html` 退役**：本地移入 `archive/_pending_delete_20261008/`（MANIFEST 已登记）；
  线上移入 `_backup_20261008_structures3dhub/retired/`。内容页只是 `docs/help/fold.html`
  去掉全站 `<nav>` 的副本，**原帮助页仍在，无内容损失**。
- **`/help/fold.html` 撤销 301，恢复为独立帮助页**（由 nginx `location /help/` 提供）。
  nginx 只删掉 `location = /help/fold.html { return 301 /structures3d/; }` 一条 + 改两处注释
  （行数 379→379，location 行数不变；下载线上现版 → 本地打补丁 → 出 diff → 回传 → `nginx -t` → reload）。
- **引用回改**：`docs/help/index.html` 的 Batch Folding Queue 卡改回 `href="/help/fold.html"`
  （原先指向已不存在的 `#pipeline`）；`docs/index.html` 首页卡片、`docs/resources.html`
  资源卡、`docs/help/uniprot3d.html` 正文里的「Folding pipeline 标签」表述一并去掉。
- **文档同步**：`docs/README.md`（`/structures3d/` 改「三标签」；`/help/fold.html` 由 301 行改为普通页行）、
  `USER.md`、`14.rvpsd_structures/README.md`（删 pipeline.html 行）、`deploy/nginx_full.conf` 与
  `deploy/_new_conf_staging.conf` 镜像、`SECURITY_DEPLOY_20261008.md` 的注。
- **验收**：验收脚本 `_probe/check_structures3d_ui.py` 断言改为 3 标签，并新增
  「统一入口无 pipeline 按钮」「`#pipeline` 回落 atlas」「`/help/fold.html` 仍是带全站导航条的独立页」
  三条探针。上传的 6 个文件**本地 md5 == 线上 md5**。

## [2026-10-08] — 蛋白结构三页整合为 `/structures3d/` 统一入口（外壳 + 四标签）

**背景**：`/help/fold.html`（折叠队列帮助）、`/uniprot3d/webapp/`（UniProt Structure Atlas）、
`/structures3d/`（RVPSD Molstar 查看器）本是同一主题的三个分散页面。按老师决策整合为一个入口，
**原三页逻辑零改动**（外壳 + 标签页 iframe，仿 `/relations/` 的做法）。

- **新入口 `/structures3d/`**：`14.rvpsd_structures/webapp/index.html` 改为**外壳**，四标签 =
  **结构总览**（`atlas/`）/ **统计面板**（`atlas/stats.html`）/ **3D 模型浏览**（`rvpsd.html`）/
  **预测管线**（`pipeline.html`）。原 Molstar 查看器 `index.html` **改名**为 `rvpsd.html`（内容一行未改，
  md5 `395c46b4…` 与改前逐字节相同）；`pipeline.html` = `docs/help/fold.html` 去掉全站 `<nav>`（判据：
  把 NAV 加回必须逐字节还原）。`molstar.html` / `vad.html` 的内部回链 `./index.html` → `./rvpsd.html`
  （否则子页会甩回外壳）。
- **外壳两个设计点**：① 只做壳 —— 子页一行未改，外壳仅往 iframe 注入一条样式藏掉子页自己的标题栏与
  语言按钮（`body>header`、`#pvdb-lang-btn`），免得叠成「两个导航栏」；② **高度刻意定死**（`.stage{flex:1}`），
  与 `/relations/` 的「随内容撑高」相反 —— RVPSD 查看器自身 `height:100vh`（撑高会与 iframe 视口自指成
  反馈环），Atlas 的 `#detail` 是 `position:fixed`（撑高后点表格下半部的行时面板跑到屏幕外）。
- **多 iframe 保活**：只切 `visibility` 不切 `display`（WebGL canvas 后备存储会被丢），最多保留 2 个
  （当前 + 上一个）。
- **nginx**（`conf.d/plant-virus.conf`，location 66→70，行 359→379）：新增
  `location /structures3d/atlas/`（直挂模块 15 的 webapp，**最长前缀优先**）、三个
  `location /structures3d/structures_{pdb,alphafold,selffold}/`（Atlas 查看器按 `../structures_*`
  相对路径读文件，故挂一级）、`build_data.py` 与 `colabfold_input/`、`*.db|log|tmp` 屏蔽 404。
  **旧入口全部 301**：`/uniprot3d`、`/uniprot3d/`、`/uniprot3d/*`、`/help/fold.html` → `/structures3d/`。
- **既有缺陷 A/B/C 一并补上**（老师选「全上」）：
  - **A**：Atlas 查看器缺结构文件 → 补传 `proteins.json` 真正引用的 **78 个 PDB cif + 435 个 AFDB cif（398 MB）**；
    `structures_selffold/` 被 0 条蛋白引用（`sf` 字段全空），暂不提供，fold_web 入库后自动生效。
  - **B**：RVPSD 缺 `structures_fullatom_vp`/`_afdb` → 补传 **2,909 vpSAT + 260 AFDB 全原子 PDB**；
    并补传新版 `fullatom_map.json`（**25,743 条**；旧版 22,574 条不含 vp/afdb，会让新版索引 3,032 条解析不到）。
  - **C**：VAD 批次（1.25 GB）从未部署 → 补传 `structures_vad/` + `structures_vad_dimers/`。
- **入口接线**：`docs/index.html` 把 RVPSD / Atlas / 折叠队列三张卡合成一张（首页入口卡片 18→16，
  与 README 记的 16 重新一致）；`docs/help/index.html`、`docs/help/uniprot3d.html` 引用改指
  `/structures3d/#atlas`、`/structures3d/#pipeline`。
- **验收**：本地 + 线上 Playwright 各 **42/42 通过**（判据是**基线对照**「不引入新错误」而非「零错误」）；
  线上数据抽样 `structures_fullatom`/`_domains`/`_candidates`/`_vp`/`_afdb` 各 100% 200、
  `structures_pdb` 78/78、`structures_alphafold` 435/435；VAD 单体 200/200、二聚体 195/200
  （缺的 5 条落在 24 条 VAD 未提供之内，自洽）；全站回归 24/24 = 200；旧入口 301 全部正确
  （含 `/uniprot3d/structures_index.tsv`）。备份 `/opt/plant_virus_db/_backup_20261008_structures3dhub`。
- **行尾纪律**：`14.rvpsd_structures/webapp/index.html` 与 `docs/index.html` 是 CRLF，其余 LF，
  逐文件按原行尾写回并断言。
- **顺带修正（口径）**：外壳顶部 chips、首页 `docs/index.html` 卡片、资源页 `docs/resources.html`
  的 Protein Structure 卡、以及 `docs/help/uniprot3d.html` 正文，原写「**1,832** 种 / **17,918** 蛋白」，
  是 2026-09-30 RVPSD-only 的旧数；2026-10-01 三源合并（RVPSD + vpSAT + AlphaFoldDB）后索引实为
  **2,603 种 / 20,950 蛋白**（线上 `structures_index.json` 的 `count_species`/`count_proteins`），
  而查看器自身早已按数据实时显示 2,603 —— **同一个页面上自相矛盾**。本次一并改正，并把资源页卡片
  描述从「AlphaFold2 预测」改成四标签统一入口的合述。

## [2026-10-08] — 部署 AI 模块安全加固（SSRF / 服务器 key 回退 / 匿名烧 key / 限流）

**背景**：`AI_MODULE_DB_AUDIT_20261008.md` 审查发现——修复代码都在仓库里，但**线上从未部署**
（本地=已修版、线上=未修版）。本次按老师三项决策上线。报告：`SECURITY_DEPLOY_20261008.md`。

- **`/api/chat`（primer-web）P0-5 完整部署**：`api_url` 由服务端固定为 DeepSeek 官方地址
  （忽略客户端传入 → 防 SSRF）；**取消服务器 key 回退**（无 key 返回 401，key 必须由浏览器用户自备）；
  新增 32KB 单条消息长度守卫（413）；顺带修掉前端引用**线上不存在**的 `ai-api-url` 输入框导致的 null 抛错。
  **不做整文件覆盖**——只打 6 处最小补丁，**保留线上 `/lib/` 自建静态库**（本地安全版把 bootstrap
  换成了 jsdelivr CDN，属国内不可用回归，刻意不引入）。
- **knowledge-rag**：部署 SSRF 护栏（`_llm_url_allowed`，严格比对 hostname 而非 `startswith`）、
  输入长度上限、`httponly` 会话 cookie、搜索 `limit` int 守卫、前端 XSS 转义加固。
- **literature-tracker**：部署 `require_api_token` / base_url 白名单 / body 上限 / papers.json 缓存 /
  不回显异常堆栈。按决策 **不启用 token**（`LITERATURE_API_TOKEN` 留空 → 装饰器 no-op），
  匿名烧 key 改由 nginx 限流兜底。
- **nginx 限流**：新增 `limit_req_zone zone=pvdb_llm rate=30r/m`，对 `/knowledge/query` 与
  `/literature/api/summarize/(paper|digest)` 两个**匿名可消耗服务器 key** 的端点限流
  （`burst=10 nodelay`，429）。对照 `/knowledge/search` 未限流，证明定向不误伤。
- **明文 key 移出**：`literature-tracker.service` 里的 `Environment="LLM_API_KEY=sk-a81b04…"`
  改为 `EnvironmentFile=-/opt/plant_virus_db/literature-tracker.env`（**权限 600**）。
  **⚠ 该 key 仍需老师在 DeepSeek 控制台轮换**（本报告仅移出明文，未轮换）。
- **行尾纪律**：生产 step5/knowledge 是 LF、literature 是 CRLF，部署后**逐一复核行尾未变**。
  补丁生成器初版因 `Path.write_text()` 在 Windows 做换行翻译而写出 CRLF，已改用**字节级 I/O** 修正。
- **验证**：SSRF→400、无 key→401、超长→413、限流→429（且未限流端点不受影响）；
  零回归 `/lib/bootstrap.min.css` 200、`/primers/` jsdelivr=0、knowledge/literature 均返回真实数据、
  全站 23 个入口全部 200。三个 systemd 服务 active。生产运行时为 **Python 3.8**
  （补丁已用 `ast.parse(feature_version=(3,8))` 校验）。

## [2026-10-07] — 修正 `/reference/` 月度增量口径：并列展示「序列数」与「新分类单元数」（方案 C）

**背景**：老师质疑 `/reference/` Monthly Incremental Update 的月度数字是「新增的已知病毒」还是
「新病毒」。复核发现页面展示的 `new_plant`（120/2233/1899/807/783/455/1244）**两者都不是** ——
它是实测值按 ~6.22% 等比缩放的派生值：数学上 `new_plant == floor(new_plant_raw × k)`，
k 的唯一可行区间 `(0.0622133403, 0.0622172843)`（宽 4e-6）恰含 `7544/121256 = 0.06221548`，
逐月精确复现；`round()` 无解。全仓库与线上**均无脚本产出该字段**，JSON 也不在 git 内。
复核报告：`INCREMENTAL_METRIC_AUDIT_20261007.md`。

- **数据链三方互证**（运行日志 / 逐月产物 TSV 行数 / JSON 字段完全一致）：
  `scanned` = 去重后扫描数；`new_plant_raw` = 植物病毒命中（当月新入库植物病毒**序列条数**）；
  `new_taxids` = 🆕 新发现植物病毒 TaxID（真正的「新病毒」口径）。
  逐月 TSV `incremental_updates/<ts>/incremental_plant_viruses_info.tsv` 行数 =
  1,930 / 35,902 / 30,524 / 12,984 / 12,601 / 7,319 / 19,996，逐月精确吻合。
- **按老师决策（方案 C）改展示**：卡片并列显示「新增植物病毒序列」（主数字）+「N 个新分类单元」；
  汇总改为 `121,256 new plant virus sequences · 400,917 total viruses scanned · 311 new plant virus taxa`；
  区块底加口径脚注（sequences = 窗口内新入库记录；taxa = 此前未收录的分类单元）。中英双语
  （新增运行时 `t()` 助手 + 注册 `PVDB_onLangChange` 钩子重建卡片）。
- **JSON schema 变更**（`docs/data/incremental_status.json`，基线取**线上较新副本**）：
  `new_plant_raw` → `new_plant_sequences`；删除派生字段 `new_plant` / `total_new_plant`(7544)
  与冗余 `scanned_raw`；summary 原 `new_taxids: 226` 实为 `merge_to_ref` 的 "Added" 口径
  （与逐月 🆕 不同），改名 `ref_added_taxids` 保留，另设 `total_new_taxids: 311`
  （= 逐月求和，与卡片一致）。自洽校验：Σ序列 = 121,256 ✓、Σ扫描 = 400,917 ✓、Σtaxa = 311 ✓。
- **顺带发现并记录**（未改数据）：summary 的 `total_new_plant`(7544) 与其逐月之和(7541) 本就差 3；
  `new_taxids`(226) 与逐月之和(311) 口径不同却同名 —— 本次已分开命名。
- **Verification**：`deploy/check_reference_incremental_ui.py`（Playwright，本地与线上**各跑一遍
  17/17 通过、0 JS 错误**）；双语切换实测（EN/中文标签与汇总均正确）；`/reference/` 区域 5 页全 200；
  线上 md5 与本地逐字节一致（`4f8dad9b…` / `9359c356…`）；两文件行尾保持 LF（CR=0）。
  回退源：服务器 `docs/reference_index.html.bak_20261007.incrementalmetric` +
  `docs/data/incremental_status.json.bak_20261007.incrementalmetric`
  （改动前 md5 `0368ca73…` / `0a970667…`）。

## [2026-10-07] — fold_web 有限上线 /foldweb/（Basic Auth，无 GPU 模式）+ curl 兼容修复

- **决策变更**（应用户要求，原"刻意不反代"作废）：16.fold_web 部署到 39.106.101.94，
  nginx `/foldweb/` 反代 127.0.0.1:8800 并加 Basic Auth（凭据在本地密码管理器，
  严禁入库）；ZIP 上传上限收紧 2G（服务器磁盘余量小）；systemd 服务 `foldweb.service`
  常驻。Foldify 本就是在线服务，无需部署，webapp/help 已有入口与链接。
- **无 GPU 模式**：`FOLDWEB_PREDICT_CMD` 指向 `no_gpu_predict.sh`（中文提示改走
  上传结果入库通道，实测日志可见）；上传结果入库 / Foldify 导出 / 覆盖统计可用。
  服务器入库后需重跑 `webapp/build_data.py` 刷新线上 Atlas 页面。
- **修 3 个部署期 bug**：①服务器无 `colabfold_input/` 目录致 SQLite 建库 500（补 mkdir）；
  ②`/api/job/new` 对数组 payload 500（容错为 400/收下，API 调用方常见形状）；
  ③**服务器 curl 过旧不认识 `--retry-all-errors`**（7.71.0+ 才有）致收集 5 连败且
  `-s` 吞掉报错——foldcore 去掉该参数、curl 加 `-sS -L`、rc+stderr 记入任务日志、
  空 body 也判失败重试。
- 部署校验：公网无凭据 401 / 带凭据 200；stats API 账目正确；测试任务收集→无 GPU
  提示→error 全链路实测后清理。help/fold.html 双部署说明更新。

## [2026-10-07] — 口径对齐：新建 17.genome_proteome（9,022 基因组蛋白宇宙）+ 超算批量管线跑通

**用户点破口径错位**：15 模块的 4,810 条蛋白是 UniProt 收录口径（模式毒株），与 2 号模块
9,022 条病毒基因组不是一套体系；建库输入口径实为 72,691 蛋白（2026-05 批次）。从基因组
重建蛋白宇宙（新模块 `17.genome_proteome/`）：

- **蛋白全库**：9,022 accession 经 NCBI `efetch rettype=fasta_cds_aa` 批量拉取官方注释蛋白
  **29,059 条**（覆盖 8,091 基因组；其余 ~480 条为类病毒/无注释记录，不编码蛋白——
  12 个"失败"批实为 LC/AJ/AF 等类病毒 accession，生物学正确）。
  `docs/data/Plant_Virus_proteins.faa`；脚本 `oneoff_scripts/pv_proteome/fetch_all_proteins.py`。
- **聚类去冗余**：MMseqs2 easy-cluster 50% id/cov 0.8 → **11,017 结构代表**（90% 档
  20,550 几乎不省）。产物回传 `17.genome_proteome/`。
- **五路结构对账**：RVPSD 直配 675（protein_id↔GenBank 文件名；全库实点核对 24,606 条，
  VAD 新批次对植物病毒增量为 0）；PDB/AFDB/BFVD 经 UniProt 继承（代表 vs UniProt 4,810
  序列比对 ≥90% id，仅 320 代表可映射——基因组宇宙远大于 UniProt 模式株）。**有结构代表
  969（8.8%），缺口 10,048 代表**。明细 `17.genome_proteome/coverage_report.tsv`。
- **hx 站批量管线修复跑通**：SFTP 上传的 Windows 反斜杠文件名炸弹（posixpath.basename
  对 `D:/…/json\X.json` 失效）导致 Stage2 全灭 + MSA 白算 5 小时；远端 Python 改名修复，
  worker 池 v4（领任务制+断点续跑+增量复用 MSA+triton 失败自动换 cutlass）重提，
  首条 2303aa（A0A059WRQ4）复用 MSA+推理 18.4 分钟出 cif（ranking_score 0.51，
  已回传 structures_selffold/）。提交数上限逼出 worker 架构（365 任务只占 6 名额）。
- **昆山 4090 Notebook 实测**：SSH 网关转发需容器重启才建立；mmseqs-linux-gpu（CUDA
  build）部署跑通、结果正确（166 命中），但 **CPU 格式库无 GPU 索引生成入口（createindex
  --gpu 不识别），流式搬运 IO 拖死（286aa 777s），无速度优势 → 实例关机止损**。GPU-MSA
  正路 = Modal Option A（RomeroLab 托管 1.2TB prebuilt GPU 索引，--msa-only 端点国内实测
  可达，估 $0.1-0.5/条，需国际卡）或 hx 提额。
- 10,048 缺口预算：hx 现状 1 worker ~279 天；提额 128 核（8 worker）~35 天；
  提额+Modal MSA ~15-18 天。`17.genome_proteome/README.md` 有完整预算表。
- **跨机分工架构端到端验证通过（10-07 深夜）**：4090 "GPU 慢"是共享盘 IO 假象——
  库复制本地盘后 3059aa GPU search 仅 16s；**批量模式 365 条 vs small_bfd 一次 24 分钟**
  （索引载入摊薄，vs hx CPU ~730 小时）。完整 MSA 链 `createdb→search(--gpu 1)→
  result2msa(--msa-format-mode 5=A3M, 带 AF3 过滤参数)` 在 4090 跑通（Q0PIV3：11s+6s，
  112 条 a3m）；自写组装器内嵌 `unpairedMsa` 生成 AF3 输入 JSON，回传 hx 站实测
  **data pipeline 0 次搜索、9.88 秒完成（原 135 分钟）**，推理正常出 cif。新架构确立：
  4090=MSA 工厂（批量 ~500 条/天），hx=推理工厂（1 worker ~70 条/天，提额 8 worker 后
  与 MSA 产能匹配）；4090 撤销关机建议，转正为 MSA 工厂。

## [2026-10-07] — 上线验证抓出 webapp 渲染双 bug + /uniprot3d/ 入口重构

浏览器实测（非 HTTP 200 口径）发现并修复三个问题，均已上线复核：
- **stats.html / viewer.html 数据解构 bug**：`loadJSON` 返回 Promise.all 数组，
  两页却按单对象使用（`.then(S=>` / `.then(list=>`），导致统计面板全 undefined/NaN、
  查看器永远"未知 accession"。修复为 `.then(([S])=>` / `.then(([list])=>`。
  （此前所有验证只查过端点状态码，从未真正渲染——index.html 解构正确，一直正常。）
- **nginx /uniprot3d/ 根路径服务方式重构**：原 `index webapp/index.html` 直服方式下
  浏览器地址在模块根，页面相对引用（common.js、data/*.json）解析到根路径 404，
  首页成空壳。改为入口 301 到 /uniprot3d/webapp/ + 专用 alias location；
  viewer 的 ../structures_* 相对路径由模块根 location 继续承接。
- 提醒：webapp 静态资源带 `expires 10m`，更新 HTML 后浏览器可能用缓存，
  验证需强刷或带查询参数。
- 线上复核（浏览器截图 + DOM 计数）：总览 8 卡/14 行组合条形图/检索表、统计面板
  8 卡/3 段环形图/缺口表(合计 365)/组合明细 20 行/台账 6 行，账目与索引一致。

## [2026-10-07] — /uniprot3d/ 轻量上线（39.106.101.94）

- 15 号结构站（webapp 三页 + structures_index.tsv + virus_coverage.tsv）与门户增量
  （docs/index.html 含新模块入口 + help/ 全套含 fold.html）已部署到阿里云，
  nginx conf 差量插入 uniprot3d 四个 location（模块根 alias + colabfold_input/ 与
  *.db|log|tmp 屏蔽 404）+ webapp 裸目录 301 收口到根；旧 conf 备份为
  plant-virus.conf.bak_20261007_uniprot3d。
- 线上验证：/uniprot3d/、stats.html、viewer.html、三个数据 JSON、索引 TSV 全 200；
  运行期产物 404；14 个既有模块回归全 200；门户首页出现 /uniprot3d/webapp/ 入口。
- 边界：554MB PDB + 182MB cif 结构文件未上传（用户选择轻量先上线），线上 3D 查看器
  点开具体结构会 404，补传即恢复；fold_web (16) 按设计不公网暴露（无鉴权），
  走 SSH 隧道在 GPU 服务器使用。
- deploy/nginx_full.conf（含全部 location 的配置 source of truth）与
  deploy/check_site_routes.py（docs 根相对链接线上缺口扫描器）首次入库。

## [2026-10-06] — fold_web/webapp/Foldify 全链路复验：修复 Foldify 导出 500 + 沙箱回归测试

- 沙箱端到端回归测试新增 `16.fold_web/smoke_sandbox.py`（11 项断言）：临时模块副本 +
  stub 预测器，覆盖首页/stats 账目、FASTA 上传→队列→预测→入库（SELF 落盘 + sources
  翻转）→pending 联动、Foldify 导出 ZIP 结构（manifest/README/全部 ≤600aa）；
  **不写真实 structures_index.tsv**，真实索引只读。
- 借此抓出并修复真 bug：`foldcore.py` 的 `fetch_fasta_map` 使用 `tempfile.mkstemp`
  但未 import，导致 `/api/export/foldify` 实际请求 500（此前仅文档层面"沙箱通过"）。
  修复后 11/11 全绿，导出端点实拉 UniProt 验证通过（P03562/P03567/P21935）。
- 复验确认真实数据无污染：structures_index SELF 标记 0 条（此前会话的
  P03567=BFVD,SELF 为其沙箱副本状态）；`structures_selffold/` 仅含 alphafast 管线
  真实 AF3 试跑产物（A0A059WRQ4，5 文件）。
- 15 webapp 9 端点复验 200，stats.json 账目与索引一致
  （4,810 蛋白/413 物种/own 1,112=23.1%/缺口 365/BFVD 4,366/RVPSD 910/AFDB 435/PDB 80）。

## [2026-10-04] — AF3 权重就位：免申请直链下载（973 MB → 16.fold_web/models/）+ AlphaFast 通道评估

- 核实官方仓库：DeepMind **已取消 AF3 权重的表单申请制**，改为公开直链
  `https://storage.googleapis.com/alphafold3/af3.bin.zst`，下载即受
  Model Parameters Terms of Use 约束（非商业/禁临床/权重不得转分发；学术合规）。
  AlphaFast README 的"表单申请 2–5 个工作日"说法已过时。
- 下载链路：直连需 `curl --ssl-no-revoke`（schannel 吊销检查被墙误报
  CRYPT_E_REVOCATION_OFFLINE，加参数后 206 正常取流，平均 ~620 KB/s 约 25 分钟）；
  系统代理 127.0.0.1:8081 对 https CONNECT 握手失败未采用。
- 完整性校验：1,020,545,840 字节精确匹配 + zstd 帧头 `28b52ffd` +
  Python zstandard 全量流解压 1,146,811,260 字节通过
  （sha256 前 16 位 `df8bbf2621f17dd3`）。`16.fold_web/models/` 已入 .gitignore。
- AlphaFast（RomeroLab/alphafast）评估：MMseqs2-GPU 替换 Jackhmmer（同源搜索
  68.5×、端到端 22.8×，4×H200 约 8 s/输入；Modal 基准 $0.035/输入，仅支持
  信用卡，不支持支付宝/微信）。对照缺口：365 条零覆盖蛋白实际 286–3,471 aa
  （304 条 >2,700；最长 3,471 aa 在 AF3 token 预算内可直跑，切块精修可选）；
  三路径中本机 Docker 不可行（无卡）、Modal 最贴合（全套约 $30–80）、
  超算需先确认 NVIDIA 卡型（昇腾等国产卡跑不了 MMseqs2-GPU/JAX）。
- **AF3-dialect JSON 输入包已生成**：`prepare_alphafast_input.py` 复用 FASTA
  抓取通道，产出 `alphafast_input/json/` 365 个任务（id=["A"]、seed=1、
  version=1）+ manifest.tsv + README（三种运行模式与手动回传说明），
  全量 schema/序列/长度校验通过；`json/` 目录不入库（30 秒可重生成）。

## [2026-10-02] — 15 模块宇宙收紧：去除噬藻体/绿藻病毒（6,803 → 4,810 条）

宿主口径从 Viridiplantae(33090) 收紧为**必须含陆生植物 Streptophyta(35493)**，
整体剔除 8 个绿藻病毒物种共 **1,993 条**蛋白（PBCV-NY2A 877、PBCV-1 849、
MpV-SP1 243、MpRV 11、PBCV-IL3A/PoV01/NC1A/XZ-6E 零头；与陆生组零重叠），
留档 `removed_green_alga_viruses.tsv`；同步删除其独占结构文件（39 PDB + 898 AF 模型，
约 380 MB）。重建顺序踩坑：`sifts_sweep.py` 不重建交叉引用基线，必须先跑
`uniprot_structure_fetch.py pdb` 再跑 sweep，否则 union 仍按旧清单算。

**收紧后终账（四路对账）**：4,810 条（reviewed 1,274）；PDB 实验结构 218（554 MB）、
AFDB 现役模型 435（182 MB）、RVPSD 桥接 910、BFVD 命中 4,366；**任一来源有结构
4,445（92.4%），真零 365 条**（304 条为 >2,700 aa 多聚蛋白需切分，reviewed 仅 31）；
物种级零结构 6/413。昆虫病毒经实验性植物宿主混入的个例（FHV 9 条）暂保留，
README 已注明。GCVA 补充批次（枸杞弹状病毒）不受影响。

## [2026-10-01] — 15 模块收口：SIFTS 反查 + RVPSD 对账 + BFVD 接入 + 蛋白级结构总索引 + GCVA 补充批次

`15.uniprot_plant_virus_structures` 收口为"可复算的结构可得性总账"：

- **BFVD 接入（NAR 2025, gkae1119，最大增量）**：351,242 个病毒蛋白 UniRef30 簇代表
  的 ColabFold 结构库，专补 AFDB 不含病毒。对全部 6,803 条经
  `bfvd.foldseek.com/api/{acc}` 逐条查询（`bfvd_lookup.py`），命中 **6,358（93.5%）**，
  其中 4,391 条只有 BFVD 有。四路合计 **6,437/6,803（94.6%）蛋白至少一路结构，
  真零只剩 366 条**（304 条为 >2,700 aa 多聚蛋白，需切分后折叠）；物种级零结构
  从 157 个缩到 6 个。结构文件托管 workers.dev 本机不可达（README 有说明）。
- **SIFTS 反查**：EBI SIFTS 全量映射表联表（RCSB Search API 的 UniProt 字段不开放
  批量检索，实测），3,006 条链级映射，比 UniProt 交叉引用多发现 5 个 PDB 条目
  （1FVI/21AW/8QKP/9RP8/9VJD），PDB 实验结构最终 **258/258 校验通过**（680 MB）。
- **RVPSD 对账**：经 GenBank 蛋白 ID 桥接（UniProt 公开 idmapping 对
  `to=EMBL-GenBank-DDBJ` 实测返回空，改 JSON 流直抽 ProteinId，9,122 对），
  从 14 模块 5 个 manifest 命中 910 条蛋白。
- **蛋白级总索引 `structures_index.tsv`**：6,803 条蛋白 × {PDB, AFDB, RVPSD}，
  **2,046 (30.1%) 至少一路结构**；4,757 条三路皆无，按折叠难度分层输出
  `pending_prediction.tsv`（P1 reviewed 619 / P2 unreviewed 3,779 /
  P3 多聚蛋白 304 / P4 极小 55）。
- **GCVA 补充批次**：Cytorhabdovirus sp. 'lycii'（OR489165.1，枸杞病毒）UniProt
  全无收录，模块宇宙之外单独立批 `structures_supplementary_gcva/`——本地
  AlphaFold3 的 6 个蛋白 model_0 全部并入并带 pLDDT 统计（N 80.8 / L 77.3 /
  M 37.8，符合弹状病毒生物学预期）。

## [2026-10-01] — 新增 `15.uniprot_plant_virus_structures`：UniProt 植物宿主病毒蛋白结构全量落盘

从 UniProtKB（release 2026_03）把"病毒分类 10239 ∩ 植物宿主 Viridiplantae 33090"的
6,803 条蛋白清单与其结构层全部下载落地，与 `14.rvpsd_structures`（RVPSD AF2 第三方
模型）互补——本模块是 **UniProt 官方交叉引用**指向的结构：

- **PDB 实验结构 258 个**（118 条蛋白有 PDB 交叉引用 = 253 个；另经 EBI SIFTS 全量
  联表反查补齐 UniProt 滞后漏掉的 5 个；3,006 条链级映射），mmCIF，680 MB，
  258/258 校验通过（`data_` 头 + `_atom_site.`）。
- **AFDB 现役模型 1,333 个**：对全部 6,803 条逐条探测（交叉引用仅 1,093 条，≠覆盖
  真值；漏网的 262 个靠全量探测补齐），mmCIF 解压后 334 MB，1,333/1,333 校验通过；
  其余 5,470 条确证 AFDB 无模型（多为病毒 TrEMBL，AFDB 覆盖不含）。
- **蛋白级总索引 `structures_index.tsv`**：与 14.rvpsd_structures 对账（经 GenBank
  蛋白 ID 桥接，9,122 对），三源合计 **2,046/6,803 (30.1%) 蛋白至少有一路结构**
  （PDB 122 / AFDB 1,333 / RVPSD 910），4,757 条三路皆无。
- 踩坑记录（README 第五节）：`xref:pdb` 非合法查询字段；AFDB 文件已换代到
  `model_v6.cif`（v4/.gz 全 404），且名义 `.cif` 实际回传 gzip 流；RCSB Search API
  的 UniProt 字段不可批量反查（走 SIFTS 联表）；UniProt 公开 idmapping 对
  `to=EMBL-GenBank-DDBJ` 返回空（改 JSON 流直抽 ProteinId）。
- 入库物：README、全量清单 TSV、pdb/afdb 链接表（含 SIFTS 联表、`afdb_links_all.tsv`）、
  蛋白级总索引、下载 manifest、脚本 `oneoff_scripts/uniprot_pdb_fetch/`（断点续跑）；
  结构本体约 1.0 GB 已 gitignore。

## [2026-09-30] — `/relations/` 外壳（续）：消掉 iframe 内的重复标题 + 修掉 `/vector/` 死空白

承接同日上一条「消除两个导航栏 + 四个 hash 变真子页面」。老师看过线上后反馈
**「还是出现重复」**（截图里标题出现两遍）。

### 症状与根因

**重复标题来自两层，肉眼看起来像「一条标题写了两遍」：**

| 层 | 元素 | 位置 |
|:--|:--|:--|
| 外壳 | `.strip button.vtab > span.t`（四个视图切换条） | y≈116 |
| iframe 内 | `/network/` 自带的 `body > .tabs`（vh / tvh 切换条） | y≈25 / 33 |

`/network/` 的 `.tabs` 是它**页面自身**的切换条，在外壳里与外壳的 `.strip` 功能完全重叠
→ 显示出来就是「同一个标题两遍」。实测重复数（可见 + 有高度 + `innerText` 含
"host network" 且无更深子元素也含的最内层节点）：**graph 2、tvh 2、sankey 0、vector 0**。
`/association/` 与 `/vector/` 源码里没有 `.tabs`（已核 `8.plant-insect/vector_page.html`
与线上 HTML），所以 `body>.tabs` 只命中 `/network/`。

**另一个空白来源（与上一轮那个 41px 棘轮无关）**：`.stage{min-height:min(74vh,700px)}`
在 900 高视口下是 666px，**压过**脚本设的内联 `height` —— 当 `/network/` 内容缩到 573px 时
`.stage` 仍是 666px，底部留 93px 空白。

**上一轮那个 41px 棘轮也一并修掉**：`fitFrame()` 原本量 `documentElement.scrollHeight`，
内容比 iframe 视口矮时它被钳到视口高度 → iframe 高度只涨不缩。改量 `body.scrollHeight`
（不被钳制）后，`/vector/` 底部死空白 41px → **1px**。

### 改动（`docs/relations/index.html`，23,474 B → 25,915 B，纯 LF，CRLF 保持 0）

中途 24,045 B 是「只修棘轮」那一版，已单独部署过；最终版 25,915 B。四处：

1. **藏掉 iframe 内的切换条**：注入样式再追加 `body>.tabs{display:none!important}`。
   按钮**留在 DOM 里**（`#tab-vh` 仍在）→ `/network/` 自己的脚本不被打断。
2. **`fitFrame()` 改量 `body.scrollHeight`**（棘轮修复，见上）。
3. **撤掉 `.stage` 的 min-height**：`show()` 与 `fitFrame()` 里显式
   `stage.style.minHeight = knownH ? '0' : ''`，让内联 height 真正说了算。
4. **钉住内层画布高度**：注入 `#chart{min-height:480px!important}`。藏掉 `.tabs` 后
   `/network/` 少 76px，而它的 `#chart{min-height:clamp(0,100vh-228,480)}` 在 iframe 里
   是**自指**的（`100vh` = iframe 高）→ 画布会跟着缩（实测 480→363）。这条只在外壳里生效，
   不影响独立访问 `/network/`；对 `/association/` 实测**无影响**（`#chart` 改前改后都是 816px）。

### 部署与验证

- **A/B（`ab_final.py`，同一 1440×900，静置 9s）LIVE → 候选 D**：

  | 视图 | 重复标题 | `#chart` 高 | `.stage` 空白 | `.tabs` |
  |:--|:--|:--|:--|:--|
  | sankey | 0 → 0 | 816 → 816 | 0 → 0 | absent → absent |
  | graph | **2 → 0** | 480 → 480 | 0 → 0 | flex → **none** |
  | tvh | **2 → 0** | 523 → 523 | 0 → 0 | flex → **none** |
  | vector | 0 → 0 | — | 0 → 0 | absent → absent |

  JS 错误 0 条。逐文件 scp，线上 md5 == 本地 md5 == `b491dbf9b2964ae058f8edadd5a8e9b3`。
- 备份（服务端 `docs/relations/`）：`index.html.bak_20260930c.ratchet`（`7bf17e8a…`，本轮起点）、
  `index.html.bak_20260930d.tabs`（`065cc00a…`，动 `.tabs` 之前）。
- **`docs/relations/work/check_relations_nav.py`（线上，含反向对照）：81 passed, 0 failed。**
  脚本本轮重写：`KNOWN_DEAD` 清空（41px 已不存在）；静置改 `SETTLE_MS = 7000`
  （力导向图会把外壳 400ms 轮询推迟 2–5s，3.2s 窗口曾把结论整个量反）；新增三组断言 ——
  重复标题数 == 0、`.tabs` 只剩空壳（`display:none` 且 `#tab-vh` 在）、内层 `#chart ≥ 480px`、
  `.stage` 空白 == 0。反向对照（`REL_PRE` = 原始外壳 20,692 B / `76bb5cde…`）证明改前
  nav 确实占位 43px（`/vector/` 40px）、graph/tvh 重复数确实为 2、`.tabs` 确实是 `flex`。
- **跨态判据（本轮修正过一次，如实记录）**：
  * `sankey` / `vector`：上移量 == nav 高（43 / 40），**文档高度减少也恰好等于** nav 高 —— 逐像素。
  * `graph` / `tvh`：上移量 == nav 高 + `.tabs` 的 margin-top（**55 = 43 + 12**），逐像素；
    但**文档高度差不作断言** —— `/network/` 的 `body` 是 `height:100vh` 的 flex 列，
    文档高度由 iframe 视口反推（自指），且本轮又钉了 `#chart` 高度，差值是多个信号叠加
    （实测 130，而 nav + `.tabs` 外框 = 43+76+12 = 131）。第一版我把这两个视图也写成
    「差 == nav 高」，5 条断言因此报红 —— **是判据写错，不是页面有问题**。
- **`docs/relations/work/check_subpages.py`（线上）：30 passed, 0 failed**（四个子页面
  title 互不相同、permalink 指 `#<hash>`、按钮打开 `/relations/#graph`、切语言 title 跟着变）。

### 已知未处理（如实标注）

- **页脚仍保留指向独立路由的 `<a href="/association/">` 等链接**，承载「三个源页面均未改动」
  的出处说明，未擅自删。
- **`#chart{min-height:480px!important}` 是外壳内全局规则**，不区分页面。实测对
  `/association/` 无影响（816px 未变）、`/vector/` 无 `#chart`，故未再收窄选择器；
  若日后有内层页的自然高度 < 480px，会被这条顶高。
- **上一轮列出的「`/vector/` 底部 41px 空白」已关闭**（现 1px，在 ±2 容差内）。

## [2026-09-30] — 三处导航条删除已下线的「Virus Profile」项

### 缘由

老师反馈：`/genes/gene_browser.html#nlr` 的导航条里有 `Virus Profile`，且「导航栏全都有」。
核查属实：`/virus/` 早已下线（301 → `/explorer/`，功能并入 Explorer 的「病毒档案」Tab，
见 `docs/README.md` 路由表），但该导航项仍残留在 3 个活页面的 `<nav>` 里。

枚举全站 33 个活 html（含 `<nav>` 的 32 个）后确认：站内共 **4 套导航家族**，只有 2 套含该死项。

| 文件 | 家族 | nav 项数 |
|---|---|---|
| `docs/genes/gene_browser.html` | D genes 局部 | 9 → **8** |
| `docs/photos.html` | C 全站 nav（旧版） | 15 → **14** |
| `docs/resources.html` | C 全站 nav（旧版） | 13 → **12** |

`help/*`（16 页）与参考库子站（5 页）本就是无该项的新版导航，未动。

### 改动（字节级删除，只移除那一个 `<a>`）

| 文件 | 行尾 | 删掉的字节 | 大小 |
|---|---|---|---|
| `docs/genes/gene_browser.html` | LF | `  <a href="/virus/" data-i18n="Virus Profile\|病毒档案">Virus Profile</a>\n`（整行） | 270,888 → 270,811（−77） |
| `docs/photos.html` | CRLF | 同上，含 `\r\n`（整行） | 26,372 → 26,294（−78） |
| `docs/resources.html` | LF | `<a href="/virus/" …>Virus Profile</a>`（该 nav 压成一行，只删元素） | 83,286 → 83,212（−74） |

### 验证

- **零回归判据**：`new == old.replace(REMOVED_UNIT, b"", 1)` **且** `old.count(REMOVED_UNIT) == 1`
  → 三文件全 PASS；导航项差集恰为 `{Virus Profile}`、`data-i18n` 词条各 −1、nav 内 `/virus/` 残留 **0**。
- **行尾不变式**：`gene_browser` bareLF 984 → 983（= 删掉的那一行）、`photos` CRLF 407 → 406、
  `resources` 361 → 361（删的是同行内元素，不动换行）。
- **部署前同步性证明**：三文件本地 md5 与线上**改前** md5 逐个相等
  （`aceea7ac…` / `9dfc5b26…` / `5bd786d3…`）⇒ 无既存漂移，本次推送只带来本改动。
- **线上复核**：三页 md5 = 本地改后 md5（`937b4476…` / `352c785d…` / `a4a9e0ce…`）；
  真 Chrome 无头实测导航条：8 / 14 / 12 项、**单行**、`overflowX = 0`、无空/不可见项、无 `Virus Profile`。
- 备份：本地与服务端各一份 `*.bak_20260930.navvirusprofile`（md5 均等于改动前版本，另跑 `md5sum` 核对）。

### 有意未改动 / 附带发现

1. `gene_browser.html` 第 884 行的 `href="/virus/?virus=…"`（病毒名标签，JS 模板拼的）**未动** ——
   那是内容型链接，不是导航项。**但它实际已失效**：`/virus/` 的 301 到 `/explorer/`
   **会丢掉查询串**（实测 `?virus=X` 最终落在 `http://…/explorer/`，无参数）→ 点击标签不会带出对应病毒。**待老师定**。
2. `photos.html` / `resources.html` 的 nav 属**旧版**（缺 `Relations` / `EVE` / `Phylo`），
   与 `help/*` 的新版不一致 —— 本轮只按要求删 `Virus Profile`，**导航版本对齐未做**。
3. 部署时一次 `scp` 混传了不同目录的文件，`genes/gene_browser.html` 被**拍平**落成 `docs/gene_browser.html`
   （站点根下的野文件）→ 已移入 `archive/_pending_delete_20260930/docs_misfiled_gene_browser.html`
   并登记 `MANIFEST.tsv`；线上 `/gene_browser.html` 复测 **404**。

---

## [2026-09-30] — 首页 `/relations/` 卡片介绍文字精简（可见 351 → 241 字符）

### 症状

上一轮精简 `/phylo/` 之后，Data Resources 组的 `/relations/` 卡片成了整页最长的一段介绍：
可见文字 **351 字符**、**9 行**（文字自然高度 187.2 px ÷ 行高 20.8 px），
同排 Reference DB 169 / Photos 152 / EVE 235。该行高度 **366 px**，由它决定。

### 改动（`docs/index.html`，CRLF，11,673 → 11,557 B）

只替换该卡 `<p>` 正文，标签结构与其余字段（`h3` / `.path` / `.go` / `href`）一字未动：

- **删**：`with the literature evidence behind each record`（压成 `literature-backed`）
  与末句 `&mdash; 1,375 of them carry a validated host and feed the triplet network`。
- **留**：四个视图的枚举（Sankey / 两个网络 / 表格）与三个头条数字
  （14,791 病毒–宿主对、199,070 GenBank 登录号、1,806 条媒介记录）。

改后 **6 行**、241 字符；该行高度 366 → **304 px**。

### 结果

至此 **Data Resources 与 Analysis Tools 两行的卡片高度都是 304 px**。
全站 16 张卡最长的是 `/relations/` **241** 字符（其后 `/eve/` 235、`/phylo/` 228、`/explorer/` 220），
分布已收敛到 96–241 区间，不再有单张卡把整行撑高。

### 验证

- **强形式同步性证明**：把本次替换**重放到线上原文件**（已含上一轮的 `/phylo/` 改动）上 →
  与本地改后文件**逐字节相同**（md5 `f60ddd4ef08228dbf830463e06c661d0`）⇒ 线上无既存漂移，
  并断言**上一轮的改动未被回退**。
- **行尾不变式**：CRLF 86 → 86、bare LF 0 → 0。
- 备份：服务端 `docs/index.html.bak_20260930d.relationscard`，md5 = `0f0693bb…`
  （= 本轮改动前版本，另跑 `md5sum` 核对，**不靠 `cp` 退出码**）。单文件 scp，本地/服务器/线上三方 md5 一致。
- 无头浏览器（线上）：`a.card` **16** 张、16 个卡片 `href` 全部 **200**、**0** JS 错误、**0** 个 4xx/5xx。
- 该 `<p>` 无 `data-i18n`（与全站其他卡片一致，英文单语）→ 不涉及 i18n 词条。

### 有意未改动

`docs/relations/index.html` 页面本身与 `docs/relations/work/` 下的验收脚本 —— 本轮只动门户卡片文字。

---

## [2026-09-30] — 首页 `/phylo/` 卡片介绍文字精简（可见 570 → 228 字符）

### 症状

`docs/index.html` 的 Analysis Tools 组里，指向 `/phylo/` 的卡片 `<p>` 是整页最长的一段介绍：
可见文字 **570 字符**，是同排另外三张卡（Explorer 220 / Metabuli 123 / PV-miRNA 120）的 2.6–4.8 倍，
渲染成 **15 行**（文字自然高度 312.0 px ÷ 行高 20.8 px）。CSS grid 的行高由最高的一张卡决定
→ 该行被撑到 **491 px**，另外三张卡下方各留出约 190 px 空白。

> 口径：可见字符数一律取**浏览器渲染后的 `innerText.length`**。等价的手算方式是
> 「剥掉标签 **+ 完整解实体**（`&mdash;`→`—` 各算 1 个字符）」；只替换 `&mdash;` 而漏掉
> `&ndash;` 会数偏（本条最初报的 570 恰好正确，中途一度按错误推断"更正"成 558，**已回改**）。
> 行数不要用 `Range.getClientRects()` 数 —— `<b>` 会把一个视觉行算成多段
> （实测同一个 6 行段落数出 12）；也不要用 `<p>` 的高度除以行高 ——
> `.card p{flex:1}` 会把它**拉伸填满卡片**。正确做法：临时 `el.style.flex='none'` 量文字自然高度。

### 改动（`docs/index.html`，CRLF，12,027 → 11,673 B；字符数 11,738 → 11,384，差额 289 为多字节字符）

只替换该卡 `<p>` 的正文，标签结构与其余字段（`h3` / `.path` / `.go` / `href`）一字未动：

- **删**：`grey backbone of realm/kingdom/phylum/class/order plus the 73 non-plant families…`
  以及末句 `The two use different conventions: … not the whole family.`
- **留**（口径纪律要求「分类树 ≠ 分子系统发育树」必须写明，压成两个括号）：
  `Two complementary views of plant virus evolution: the ICTV MSL41 taxonomy tree (set nesting,
  no branch lengths) and official molecular trees from ICTV Report chapters (maximum-likelihood,
  real branch lengths and support values).`

改后渲染 **6 行**，与同排其他卡一致；该行高度 491 → **304 px**。
改后长度 228 字符，在 16 张卡里排第 3（原先第 1），与中位数齐平。

### 验证

- **强形式同步性证明**：把本次替换**重放到线上原文件**上 → 与本地改后文件**逐字节相同**
  （md5 `0f0693bba3e735b38a94c6b0501c0cb6`）⇒ 线上无既存漂移，差异全部来自这一处替换。
- **行尾不变式**：CRLF 86 → 86、bare LF 0 → 0（纯行内替换，未增删行）。
- 备份：服务端 `docs/index.html.bak_20260930c.phylocard`，md5 = `36e3f326…`
  （= 改动前版本，另跑 `md5sum` 核对，**不靠 `cp` 退出码**）。单文件 scp，本地/服务器/线上三方 md5 一致。
- 无头浏览器（线上）：`a.card` **16** 张、`div.card` **0** 张（与改前一致）；16 个卡片 `href` 全部 **200**；
  **0** JS 错误、**0** 个 4xx/5xx。
- 该 `<p>` 无 `data-i18n`（与全站其他卡片一致，英文单语）→ 不涉及 i18n 词条，`docs/README.md` 无联动项。

### 有意未改动

- `docs/help/phylo.html` 里也写了「73 non-plant families」，但那是**帮助页对功能的说明**，不是这张卡的副本。
- `docs/phylo/work/patch_index_merge_phylo.py` 是 2026-09-22 建卡时的**历史补丁脚本**（内含当时的卡片原文）
  → 属快照，不动。

### 顺带实测（未改，待老师定）

按同样口径量了全部 16 张卡：`/relations/` **393** 字符仍是最长的一张（比改前的 `/phylo/` 短，但明显高于其余）。

---

## [2026-09-30] — `/relations/` 外壳：消除「两个导航栏」+ 四个 hash 变成真正的子页面

### 症状与根因

`/relations/` 是把三个独立页嵌进 iframe 的外壳。外壳自己有一条 `nav.topbar`，
而**嵌进来的每一页也各有一条导航条**（`/association/`、`/network/` 是 `nav.topbar`，
`/vector/` 是一整套带 `.top-row`/`.sub-row` 的全站导航条）→ 页面上叠出「两个导航栏」。
实测确认不是本地漂移：本地 md5 与线上一致（`76bb5cde09cc822d3a4d0c01b1bbd723`），
源码注释也写明「所有页面自身一行未改」。

同时四个视图共用同一个 `<title>`，且「来源页面 /association/」外链与「Open standalone」
按钮都把用户带离本页 —— 与「四个视图是本页的子页面」的定位不一致。

### 改动（`docs/relations/index.html`，20,692 B → 23,474 B，纯 LF，CRLF 保持 0）

1. **藏掉内嵌页的导航条与语言按钮**：`muteInnerLang` → `muteInnerChrome`，
   注入样式由 `#pvdb-lang-btn,#pvdb-i18n-btn{display:none!important}` 再追加
   `body>nav{display:none!important}`。三个源页的 `nav` 都恰好是 `body` 的直接子级
   且全页唯一（实测），故 `body>nav` 精确命中，不会碰到 `.controls`/`.detail`。
2. **四个 hash 变成子页面**：新增 `paintTitle()`，按当前视图改写 `<title>` 的
   `data-i18n` 属性**与** `document.title`（`i18n.js` 的 `apply()` 会 `textContent`
   覆盖 `<title>`，只改其一会被打回固定值）；`paintDesc()` 的「来源页面」外链改为
   **本页直达锚点** `#<view>`；`#btn-open` 由「Open standalone」改为
   「Open in new tab」，打开 `location.pathname + '#' + key` 而非独立路由。
3. **语言切换即时重绘**：把 400 ms 轮询体抽成 `repaintForLang()`，
   外壳语言按钮包装 i18n 的 DOM0 `onclick` 后**同步**调用它。

### 部署与验证

- **同步性证明（强形式）**：把上述四处编辑**重放到线上原文件**上，结果与本地改后文件
  **逐字节相同**（md5 `7bf17e8a3d842a95d375140e7756af02`）⇒ 线上无既存漂移，
  本次差异全部来自这四处编辑。
- 备份：服务端 `docs/relations/index.html.bak_20260930b.subpages`，
  其 md5 = `76bb5cde…`（= 改动前版本，另跑 md5sum 核对，不靠 `cp` 退出码）。
  逐文件 scp，线上 md5 与本地一致。
- `docs/relations/work/check_relations_nav.py`（线上，含反向对照）：**52 passed, 0 failed**。
  反向对照用改动前 HTML 证明「改之前内嵌 nav 确实可见且占位 43 px（`/vector/` 40 px）」，
  并断言文档高度/首个内容块**恰好**随 nav 高度变化。
- `docs/relations/work/check_subpages.py`（线上）：**30 passed, 0 failed**。
  四个视图 title 互不相同、permalink 指向 `#<hash>`、按钮打开 `/relations/#graph`
  且不再开 `/network/`、切语言后 title 变「病毒–宿主网络 · 病毒-媒介-宿主关系」。
- 死空白 A/B（线上，page.route 换回改动前外壳）：sankey / graph / tvh 三页 iframe 高度
  **恰好减少 43 px**、底部零空白；`/vector/` 见下。

### 已知未处理（如实标注，非本轮范围）

- **`/vector/` 视图底部留 41 px 空白（实测 4/4 稳定）**。藏掉 nav 后内容少 40 px，
  但 `fitFrame()` 量的是 `documentElement.scrollHeight` —— 内容比 iframe 视口**矮**时
  它被钳到视口高度（实测 `html.scrollHeight=1358` 而 `body.scrollHeight=1318`），
  于是 iframe 高度**只涨不缩**。反证：把 nav 强行 `display:block` 回来（navH=40），
  `docScrollH` 仍是 1358 不动 ⇒ 该值在此视图不含信息。
  这个「棘轮」是外壳**既有**性质（`/graph/` 一直有 112 px 内容被裁切，本次反而改善 43 px），
  修法是把测量换成不被钳制的值（如 `body.scrollHeight`），但会动到四个视图共用的
  高度逻辑，**未擅自改**，等老师定。
- **页脚仍保留指向独立路由的 `<a href="/association/">` 等链接**（第 167–168 行）。
  它承载的是「三个源页面均未改动」的出处说明，未擅自删。
- **外壳语言按钮的端到端切换耗时线上 1.3–3.3 s**（改动前 2.1–6.1 s，区间重叠）。
  页内分解（capture 监听 + 包装 `repaintForLang`）：点击事件真正派发到处理器后
  重绘只用 **0.2–0.5 ms** ⇒ 耗时几乎全在「浏览器派发点击事件时排在 iframe 力导向图后面」，
  外壳无法改善。第 3 条改动去掉的是「依赖 400 ms 轮询」这一层，不是主因。

## [2026-09-30] — `/eve/` Cases & QC 视图留白修复（三块 grid 统一 band）

### 症状与根因

线上 `/eve/?view=qc` 三块面板之间留白异常大。实测（1600×950，`#chart` 高 685 px，
读 ECharts `grid[i].coordinateSystem.getRect()`）：

| grid | 改前声明 | 实际 y/h | 类目数 | band = h/类目数 |
|:--|:--|:--|:--|:--|
| 0 案例 | `top: 26`(px), `h: 30%` | 26.0 / 205.5 | 2 | **102.8 px** |
| 1 phiX174 | `top: '48%'`, `h: 18%` | 328.8 / 123.3 | 8 | **15.4 px** |
| 2 类病毒 | `top: '74%'`, `h: 18%` | 506.9 / 123.3 | 2 | **61.6 px** |

块间距 **97.3 px / 54.8 px**，画布空白 **232.9 px = 34.0%**。根因是 `rQc()` 里
`grid[].top/height` 硬编码百分比**与各自类目数不匹配**（2 根柱却分到 30% 高），
且 `top` **混用 px 与 %** → 块间距随视口高度非线性变化。

对照：同页 5 个单 grid 视图空白仅 5.5–17.8%；`amp`（2 grid）同病更重 —— 缝 130.4 px、空白 38.0%（本轮未动）。

### 改动（`docs/eve/index.html` 的 `rQc()`，2 处）

```diff
     grid: [
-      { left: 150, right: 90, top: 26, height: '30%' },
-      { left: 150, right: 90, top: '48%', height: '18%' },
-      { left: 150, right: 90, top: '74%', height: '18%' }
+      { left: 150, right: 90, top: '3%', height: '14.2%' },
+      { left: 150, right: 90, top: '21.2%', height: '56.7%' },
+      { left: 150, right: 90, top: '81.9%', height: '14.2%' }
     ],
-        type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 11,
+        type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 20,
```

三块 `top/height` 全部改为百分比（band 48.6 / 48.5 / 48.6，块间距 27.3 / 27.4，空白 34.0% → **14.9%**）；
第二块 8 根柱在 48.6 px 的 band 里 `barMaxWidth` 11 → 20。改动脚本（幂等 + `count==1` 断言 + 行尾自证）：
`oneoff_scripts/apply_eve_qc_grid_a2.py`。

### 部署与验证

- 改前线上 md5 `adfcd1ee…` = 本地改前 → 无既存漂移；服务器备份 `docs/eve/index.html.bak_20260930.qcgrid`。
- 改后本地/线上 md5 均 `0ac28bc5bd6f9a3ad9d1a4febc0e8bae`（逐字节一致）；行尾 **LF 973 / CRLF 0** 不变（59,293 → 59,305 B）。
- 线上复测：1600×950 band 48.6/48.5/48.6、空白 14.9%；1000×820 band 39.8/39.7/39.8、空白 14.9%；两者**零 JS 错误、零 4xx**。
- **无回归**：同探针跑全部 8 个视图，其余 7 个视图 blank 逐项与改前完全相同。
- 诊断报告与对照图：`docs/eve/work/QC_LAYOUT_DIAGNOSIS_20260930.md`、`QC_LAYOUT_COMPARE_20260930.png`、
  `QC_LAYOUT_AFTER_20260930.png`、探针 `docs/eve/work/probe_qc_layout.py`。

### 已知未处理（如实标注，非本轮范围）

第二块（phiX174）**排序键与绘图口径不一致**：数组按 `phi`（绝对条数）降序取 top8，画的却是 `pct`（百分比）。
后果：`Leavenworthia_alabamica_v1.0`（1/1 = 100%）与 `Iberis_amara_v1.0`（1/2 = 50%）被挤出前 8，
而 `Pinus_taeda_v1.0`（1/4927 = 0.0%）被画进来。图例文字写的是 "share"（份额）。改按 `pct` 排又会把
`tot=1/2` 的噪声顶上来，**需要分母下限** → 属判定语义，待定方向。另：图例色块（`#c0392b` / `#16a085`）
与实际柱色（`#e67e22` / `#bdc3c7`）不一致；第一块 log 轴 10→100 与数据 19/23 不匹配，右侧 64% 横向空置。

## [2026-09-27] — 修复完整度误标链（基因级记录冒充完整基因组）+ 存量数据修复

### 根因（refinfo_analysis 复现分析中查出）

「属内长度一致性」复现 Yuan 2022 只得 90.28%（文献 98.28%），追查发现失败物种约半数
**不是完整基因组，而是基因级序列挂 complete 名下**。完整错误链三站：

1. **源头**：NCBI 上游元数据（AllNuclMetadata.csv）按 defline 关键词派生
   `Nuc_Completeness`，**"complete cds"（基因级完整）也被标成 complete**。
   实测参考集 5,263 条 complete 中 **344 条为基因级误标**（256 条 NC_ RefSeq 基因记录
   + 88 条其他），年份横跨 1993–2025；全量集同类误标 1,242 条。
   实例：`NC_038693.1 "Sikte waterborne virus ... coat protein gene, complete cds"`（1,194 nt）。
2. **F2 短路**：`Completeness_Level` 的 when 链把 `Nuc_Completeness=="complete"` 放在
   第一优先，自带的 CDS/gene 标题检测器（fallback 分支）永远轮不到执行 →
   基因记录固化成 `NonSegmented_Complete`。
3. **merge_to_ref 选错记录**：`rank_record` 只看完整度(×1000)+RefSeq(+100)+年份，
   一条 615 nt 基因 RefSeq（≈10,100 分）稳赢 6,116 nt 真完整基因组——
   实例：*Tymovirus belladonnae*（615 nt 基因入选，6,116 nt 全长在库未选）。

### 代码修复（3 处改动 + 1 个新脚本）

| 文件 | 修复 |
|:--|:--|
| `U1_incremental_update.py` | `_detect_nuc_completeness`：基因级标题（"complete cds" 及泛 `\bgene\b` 信号）返回 `""` 而非 `complete`；标题含 complete genome/sequence/segment 时除外 |
| `F2_classify_segmented.py` | `Completeness_Level` when 链：基因级/部分序列的**标题检测提到字段之前**，CDS_Fragment 检测器不再被误标字段短路 |
| `merge_to_ref.py` | ① `effective_completeness`：标题与字段冲突时以标题为准；② `rank_record` 加长度项（同级之内越长越优，压制 RefSeq/年份加成）；③ 节段判定改以 `Category`（F2 权威标记，Segmented_* 3,664 条）优先——旧逻辑只看 `Segment` 字段（4,858 条为空），节段物种被当单基因组处理；④ 节段病毒合并改**只增不删**，且只补「该 taxid 参考集尚缺的节段类型」中最优的一条干净 complete 记录（不收已有类型的新分离株与 defective 分子，防灌水）；⑤ 替换/新增记录的 VMR_*/Category 注释列从被替换旧行或同物种兄弟行继承（修复"替换即制造无注释裸行"）；⑥ 数据目录支持环境变量 `PVDB_DATA_DIR` 本机覆盖。**注意**：Windows 下二次运行需先移走旧 `.bak`（`os.rename` 不覆盖已有目标） |

### [2026-09-27] merge_to_ref 本机执行记录（修复后首跑，耗时约 1 分钟）

| 项 | 数值 |
|:--|:--|
| 参考集规模 | 8,465 → **8,500**（Kept 5,099 / Replaced 448 / SegmentTopUp 215 / 新 taxid 368） |
| 找回缺型节段 | **215 条**（DNA-B 24、DNA-A 15、RNA2 14、RNA1 12、RNA3 8…；Begomovirus 45、Fijivirus 35、Emaravirus 18 等，共 92 taxid；defective 已过滤） |
| 获得双节段 DNA-A+B 的物种 | +22（带 DNA-B 物种达 245） |
| 非节段物种换更优记录 | 448（含 *Tymovirus belladonnae*：615 nt 基因 → OR082757.1 6,116 nt complete） |
| 新增 taxid | 366 个（物种键 4,726 → 4,846） |
| 注释完整性 | Category 空行 0；VMR_Genus 非空 4,935（补段回填 201/215，余为新种待下次 F2） |
| complete 记录 | 5,348（R1 修复后 4,915 + 补段 215 + 新 taxid 218） |
| 一致性 | Ref FASTA 8,500 条 = Info 8,500 行 |
| `R1_repair_nuc_completeness.py`（新增） | 存量修复脚本：只改 `Nuc_Completeness` 一列，默认干跑，`--apply` 先备份 `.bak.20260927` 再写盘 |

### 存量数据修复（已执行 `--apply`，备份均为 `.bak.20260927`）

| 文件 | 降级 partial | 降级 fragment("") | 升级 complete | 复检残余误标 |
|:--|--:|--:|--:|--:|
| `Plant_Virus_Ref.Info.tsv` (8,465) | 49 | 303 | 4 | **0** |
| `Plant_Virus_Full.Info.tsv` (199,070) | 237 | 1,005 | 15 | **0** |
| `Plant_Virus.complete_ref_info.tsv` (5,773) | 0 | 303 | 4 | — |

逐行核对：改动**仅发生在 Nuc_Completeness 列**（Ref 356 行 / Full 1,257 行，非目标列零变动），
行数与列数不变。

### 验证记录

- `py_compile` 4 个文件全部通过。
- 单元测试（U1 判定 8 例、merge 打分 4 例含 *Tymovirus belladonnae* 反转案例、
  F2 分级链 8 例 polars 实跑）：**全部通过**。
- `refinfo_analysis/90_verify_claims.py` 退出码 0——该分析基于 2026-09-26 数据快照的
  派生文件（`out/`），修复不影响其自洽性；**重跑 01–52 号脚本将得到修复后的新数字**
  （属内一致性 <10% 预计 90.28% → ~94.5%，另见 refinfo 报告 §3.1 的 RNA/DNA 拆分）。

### 口径备忘（非 bug，需引用时注意）

G2 去冗余阈值为 **vclust ANI≥0.98 + qcov≥0.95**。物种级惯例口径
（pident≥95% & 覆盖≥90%）下参考集仍有 7.2% 近重复——外部引用"非冗余"时须注明阈值口径。

## [2026-09-23d] — 下线 `/te/`：TE 与植物病毒无关，旧路径 301 → `/eve/`

### 决定

老师原话：`临时目录删除干净，另外TE还有必要保留嘛，去除嘛。TE和我们的EVE没什么关系的`

给出的四个处置方案里，老师选：**整个 `/te/` 彻底下线**。

> 下线理由（老师给的判据，照录）：TE（转座子）与植物病毒**没有直接关系**，
> 与 `/eve/` 也不是同一分析 —— `/te/` 是 U-RVDB v32.0 的**转座子/LTR-RT/RNA 病毒组参考集合**，
> `/eve/` 是**植物基因组的全库 EVE 扫描结果**。两件事只是原先被合在一张卡片里。

### 影响面（全量枚举后才动手）

| 类别 | 数量 | 处置 |
|:--|--:|:--|
| `docs/te/` 目录 | 40 文件 / 62.27 MB | 移出服务目录归档 |
| 帮助页 `help/te_eve.html` + 图 | 3 文件（含 1 个 `.bak`） | 移出归档 |
| 孤立资源 `help/images/te_main.png` | 364,019 B | 移出归档 |
| 站内导航引用 | 17 处 | 逐处删除 |
| 门户卡片 | 1 张 | 删除（`/eve/` 卡片上一版已加） |
| `help/index.html` 整卡 | 1 张 | 删除 |
| `sitemap.xml` 条目 | 1 条 | `/te/` → `/eve/` |
| nginx `location /te/` | 1 块 | 改 301 |

**17 处引用**明细：13 个 help 页导航条（`explorer / genes / index / knowledge / literature /
metabuli / pamirdb / photos / primers / reference / resources / vector` + `help/index.html`）、
门户 `docs/index.html`、`docs/photos.html`、`docs/reference_index.html`、`docs/resources.html`。

### 1. 关键判据：**光删 nginx 块不够，目录必须真的移走**

`location /` 兜底是 `root docs/ + try_files $uri $uri/ =404`，
所以 `docs/te/index.html` **会被继续服务** —— 只删 location 会留下一个「文档里说下线了、
实际还能打开」的假下线。因此：**先移目录，再改 nginx**。

### 2. nginx：301 而非 404，且**必须同时声明 `=` 与 `/te/` 两条**

```nginx
location = /te   { return 301 /eve/; }   # 裸 /te —— 前缀块不匹配它
location /te/    { return 301 /eve/; }
```

**前缀 location `/te/` 不匹配裸 `/te`**：少了 `=` 那条，裸 `/te` 会落到 `location /` 兜底 → 404。
实测四条旧路径全部 301 到 `/eve/`：`/te`、`/te/`、`/te/index.html`、`/te/data/*.fasta`。

### 3. 部署前同步性证明：把「我的编辑」重放到线上原文件上

做法：`本地改后文件` 是否等于 `线上原文件 + 本次编辑`（逐字节）。相等即证明线上无既存漂移。

19 个文件里 **17 个 SAME**，2 个 DIFF —— 都是**既存漂移**，与 `/te/` 无关：
`docs/photos.html`、`docs/reference_index.html` 的 `/genes/` 导航行本地是 **4 空格缩进**、
线上是 **2 空格**（`git diff` 显示这两行是本会话之前那次导航改版留下的未提交改动）。
**处置：把本地归一为 2 空格**，使本次部署严格等于「只删 `/te/`」，线上零附带变化。

### 4. 部署与验收

- 服务端先归档：`docs/te/`（32 文件 / 65.51 MB）+ 4 个 help 资源 → `$R/archive/_pending_delete_20260923/te_offline_20260923/`（36 文件 / 66.21 MB），移出后 `docs/` 零残留
- 逐文件 scp **19 个文件**，先备份 `*.bak_20260923.teoffline`（19 个），再 **md5 逐个比对 → 19/19 一致**
- nginx：备份 `plant-virus.conf.bak_20260923.teoffline` → `nginx -t` 通过 → `reload` → `active`（305 → 307 行，LF 保持）
- 路由：`/te`、`/te/`、`/te/index.html`、`/te/data/*` 全 301 → `/eve/`；`/help/te_eve.html`、两张 te 图 全 404；其余页面全 200
- `deploy/check_site_routes.py`：**缺口数 = 0**（扫描 32 个 HTML / 67 个根相对 URL）
- 线上无头验收（Playwright，9 个页面）：**0 JS 错误 / 0 个 4xx / 0 个 `/te/` 链接**，门户卡片数 **15**
- `/eve/` 无回归：既有 `docs/eve/work/check_eve_ui.py` 线上跑 **0 checks failed**

### 5. 踩到的坑

1. **验收断言自己写太宽**：脚本末尾 `assert b"docs/te/" not in new` —— 新写的**注释里就含**
   `docs/te/ 已移出服务目录` 字样，于是改完的文件被判为「有残留」。**文件其实是对的，断言是错的**。
   改用精确判据 `grep "alias .*docs/te/"` 复核。
2. **`rm_lines` 假设 needle 在行尾**：门户卡片那行 needle 后面还有 `</div></a>`，
   `href="/te/" + 行尾` 匹配不到（count=0）。**那条 assert 正是靠这个立刻暴露问题** ——
   改用整行内容匹配。
3. **列宽估算错**：`TECHNICAL_REPORT.md` 拓扑图里把 `/te/ → docs/te/` 换成 `/eve/ → docs/eve/`
   我按「+4 列」补空格，实际是**两处各 +1 = +2 列**。靠显示宽度断言（东亚字符算 2 列）抓到。

### 6. 归档位置

- 本地：`archive/_pending_delete_20260923/te_offline_20260923/`（父级 `C-host_classify/archive/`）
- 服务端：`/opt/plant_virus_db/plant_virus_db_pipeline/archive/_pending_delete_20260923/te_offline_20260923/`
- 回退源：git（`docs/te/*` 17 个文件已跟踪）+ 上述两处副本 + 服务器 `docs/*.bak_20260923.teoffline` 与 `plant-virus.conf.bak_20260923.teoffline`
- MANIFEST：`archive/_pending_delete_20260923/MANIFEST.tsv` 已记 3 行（`tmp_eve_20260923/`、`te_offline_20260923/`、`help/images/te_main.png`）

---

## [2026-09-23c] — 新增 `/eve/` 植物界 EVE 全景页（8 视角全交互）

### 需求

老师原话：`补充我们的分析结果 到 http://39.106.101.94/te/` /
`几种视角，植物不同科属 病毒不同科 或者不同DNA RNA 类型 这样，你看看 怎么重新设计` /
`现在 http://39.106.101.94/te/全是静态的，怎么设计好好看看，希望你做的最好`。

先做了现状诊断，再让老师在两个方向里选，老师选定：

- **架构**：**「TE 和 EVE 内容分开，单独 EVE 网页」** → 新建 `/eve/`，`/te/` 结构不动，只在顶部加入口
- **深度**：**「全交互多视角」** → 8 个视角 + 全局联动筛选 + 导出

> 老师给的会话文件 `D:\桌面\hi-fever/sess_544a450b-….zcode-session` **全盘搜索不存在**，
> 改用 `hi-fever/CONCLUSION.md` + `PARALLEL_ANALYSIS_RESULTS.md` 作为口径依据（内容与需求完全对应）。

### 1. 数字口径：两个总数都对，页面上必须同时写

这是本次最容易出错的地方，**聚合脚本首轮就踩了**：

| 口径 | 数值 | 构成 |
|:--|--:|:--|
| `viral_supported` 位点，**原始** | **205,873** | tier1 201,782 + tier2 4,091（= `CONCLUSION.md` 的口径） |
| 其中 phiX174 建库内参污染 | **55,737**（27%） | 单基因组 `Abies_alba_v1.0` 占 55,725 |
| `viral_supported` 位点，**去污染后** | **150,136** | tier1 146,045 + tier2 4,091（= **页面展示的口径**） |

**根因**：`kingdom_loci_all_clean.tsv.gz` 里**不含 tier2**（nr 提升的 4,091 条），
只读主表会得到 146,045，且 DNA:RNA 变成 41.9:1、基因组数变成 1,396 —— 三个数字同时错。
`merge_tier2.log` 里写着权威算式 `tier1 201,782 + tier2 4,091 = 合并总量 205,873`，
据此新增 `load_tier2()` 读 `updated_tier2_log.tsv` 并入后才逐项对上。

修正后与 `CONCLUSION.md` 逐项核对通过：**150,136 位点 / 284 宿主科 / Caulimoviridae 36,781（693 基因组）/
Solanaceae 19,837 / Nyctaginaceae 11,214 / DNA:RNA 29.3:1**。

> 口径自洽校验：`40,074（可辨识病毒科）+ 93,226（Other_viral）+ 16,836（Phage）= 150,136` ✓

**页面页眉与页脚同时标注 205,873 与 150,136**，并写明差额是**被剔除的污染**而不是缺失数据 ——
读者不可能把两个数字搞混。

### 2. 8 个视角

| id | 视角 | 内容 |
|:--|:--|:--|
| `virus` | 病毒科 | 各病毒科位点数（按基因组类型着色），可下钻到宿主科 |
| `host` | 宿主科 | 284 个宿主科排名 + 植物类群演化轴（algae→eudicot）着色 |
| `dnarna` | DNA/RNA 二重性 | 环形图 + 条形图，DNA 38,751 : RNA 1,323 |
| `matrix` | 科×宿主矩阵 | 热图，可在「病毒科×宿主科」「病毒属×宿主科」两种子模式间切换 |
| `past` | 古感染对照 | 过去 vs 现在的四象限散点 |
| `amp` | 扩增动力学 | 拷贝数分布 + bitscore 阈值校准 |
| `tree` | RT 系统发育 | Pfam `RVT_1` → MAFFT/clipkit/IQ-TREE，269 叶（250 EVE + 19 参考病毒） |
| `qc` | 质控 | phiX 污染溯源 + 未映射基因组 |

全局联动：基因组类型复选框（8 类）、宿主类群复选框（9 组）、Top-N 选择器（10/15/20/30/50），
三者对 8 个视角**同时生效**；导出 PNG / CSV / Reset；URL 参数 `?view=&topn=&off=&offg=` 可分享状态。

### 3. 数据来源与聚合

分析数据**不在网站服务器上**，在**分析服务器 246**（`ssh success`）的 `~/eve_kingdom/`。
新增 `docs/eve/build_eve_data.py`（26 KB），在 246 上跑，产出 3 个 JSON 回传：

| 产物 | 大小 | 内容 |
|:--|--:|:--|
| `data/eve_landscape.json` | 68.9 KB | 总览 / 病毒科 / 宿主科 / DNA-RNA / 两个矩阵 |
| `data/eve_dynamics.json` | 184.6 KB | 古感染 / 扩增动力学 / 每基因组散点 / 稀释曲线 / 阈值 |
| `data/eve_phylo.json` | 353.9 KB | Newick 树 / 最近参考判定 / 案例 / 类病毒 / phiX 质控 |

外加 `data/_audit/*.tsv`（`virus_taxa` / `host_families` / `matrix_host_virus` / `unmapped_genomes`）
—— **每个头条数字都有可人工核对的 TSV 镜像**。

实现要点：773 MB / 2,850 万行的位点主表用**单次 awk** 抽成 205,873 行（python 从不加载全表），
结果缓存到 `~/eve_kingdom/_vs_extract.tsv`（可重跑、幂等）；病毒基因组类型是**显式表**，
不从科名推断；宿主科来自 `plantGIR` 目录结构。

### 4. 踩到的坑（可复用）

- **ECharts `setOption` 按索引覆盖 series**：DNA/RNA 视角第二次 `setOption({series:[bar]})`
  把 `series[0]` 的环形图顶掉了 → 必须**一次 `setOption` 带全部 series**。
- **category 轴自下而上**：矩阵按降序喂数据，`Other_viral` 会跑到最底 → 数组要 `.slice().reverse()`。
- **热图必须用对数色阶**：最大值 93,226 时线性色阶把其余全部压平 → 存 `Math.log10(n+1)`，
  `visualMap.formatter` 反算回真实值，tooltip 读原始 `p.data.n`。
- **i18n 动态文本不会自己更新**：`i18n.js` 用 `el.textContent = …`，页面里 `VLAB`/`GLAB`
  只在加载时求值一次 → 改成 `relabelV()`/`relabelG()` 函数，在 init 与语言按钮回调里重跑，
  并同时重建视角列表与筛选器。
- **语言切换测试必须先清 localStorage**：直接点按钮会把 `zh` 翻回 `en`，测出来是假通过。
- **`page.on('pageerror')` 不算完**：像素对比看不出「点了什么都不发生」，
  每个控件（PNG/CSV/Reset/复选框）都另加**功能探针**断言副作用（导出类用 `expect_download`）。

### 5. 验收（本地，0 失败）

```bash
python -m http.server 8899            # 在 docs/ 下起本地服务
C:/Python312/python.exe docs/eve/work/check_eve_ui.py   .tmp/   # 8 视角渲染 + 控件探针
C:/Python312/python.exe docs/eve/work/check_eve_i18n.py .tmp/   # 中英切换
```

两者均以 **`0 checks failed`** 结束，且 `pageerror` / `console.error` 归零。
另有 `work/snap_extra.py` 出子模式截图（DNA/RNA 仅可辨识科、矩阵属级、宿主 RNA、树顶），
**逐张人工肉眼确认**，不只信「已写出」。

### 6. 接站点

- 门户 `docs/index.html`：在 **Curated Data** 组、`/te/` 卡片之后新增 `/eve/` 独立卡片
  （CRLF 保持不变：97 → 98 行）。
- `/te/` 页顶部（hero 之后）加**入口横幅**指向 `/eve/`，并写明「本页是原始序列集合，
  新页是基因组尺度的分析结果」，避免读者把两页混为一谈。
- `docs/README.md`：路由表新增 `/eve/` 行；文件结构树新增 `eve/` 子树；
  门户卡片数按**实测**改为 **16**（原写 18，已陈旧 —— 实际 `<a class="card">` 13 + `<div class="card">` 2 = 15，新增后 16）。
- nginx `plant-virus.conf` 新增 `location /eve/`：**用 `root` 而非 `alias`**（与 `/phylo/molecular/` 同形，
  `try_files $uri $uri/ =404`）。原因是页面要从 `data/` 子目录取 JSON 与审计 TSV，
  而 `root` 形态是本服务器上已被 `/phylo/molecular/families/family_index.json` 验证过的写法。
  （顺带实测澄清：`alias` + `try_files` **并非**在子目录上全面失效 ——
  `/association/associations.json`、`/network/network.json` 经 `alias` 都正常返回 200 JSON；
  出问题的只是「子目录当页面用」那一类。此处仍选 `root`，因为它没有任何额外代价。）

---

## [2026-09-23b] — `/phylo/molecular/` 增加「按属着色 + 悬浮显示属」

### 需求
老师原话：`http://39.106.101.94/phylo/molecular/ 怎么没有属呢，科下面，物种的属在哪，怎么没`。
先做诊断并回报，老师在两个方案里选了 **「按属着色 + 悬浮显示属」**。

### 1. 诊断：不是渲染漏了，是数据源里没有

`/phylo/molecular/` 渲染的是 **ICTV 各章节的插图树**，叶标签只有登录号、基因/片段缩写、
毒株别名三类写法，**不含任何分类阶元**。逐棵查了 38 棵树、又逐个比对了 14 份 ICTV 比对文件的
序列头，写法与叶标签**完全一致** —— 上游没有多给一个字段。

> 排查中还否掉了一条"看起来很有希望"的线索：用 `\b[A-Z][a-z]{3,}\s+[a-z]{4,}\b` 在
> Geminiviridae 的比对里"找出" 28/29 个二名法，实际是**普通毒名**（`Tomato yellow leaf curl virus`
> 的 "Tomato yellow" 被当成属名）。**结论靠逐文件核对，不靠正则。**

属在全站只有两处存在：`families/` 卡片的 `Genera (MSL)`、`/phylo/`（genus 214）。

### 2. 做法：派生文件 + 只读构建脚本

新增 `docs/phylo/build_genus_map.py`（**只读** `molecular_trees.json` 与 `data/VMR_MSL41.txt`，
不触碰任何已验收产物）→ 产出 `docs/phylo/molecular/genus_map.json`。

- 来源列：`Virus name abbreviation(s)`（8,653 键）+ `Virus GENBANK accession`（23,249 键）——
  这两列**不在** `MSL41_species.tsv` 里。
- 匹配顺序：登录号（版本号剥离 + `NC116488`→`NC_001410` 补零）→ 通用毒名（长名优先）→ 缩写。
- 构建脚本自带**口径断言**（`tips=3341` / `mapped=2199`），对不上直接拒绝写出。

**⚠️ 硬规则：必须按科约束。** 缩写表是全局的，不约束就会跨科错标：

| 缩写 | 无约束错标 | 实际 |
|:--|:--|:--|
| `SCRV` | `Orbivirus`（Reoviridae） | Rhabdoviridae 的叶 |
| `MaYMV` | `Begomovirus`（Geminiviridae） | 非 Geminiviridae 的叶 |

已复核 **3,265 个属无一跨科**，所以这个过滤器不会误杀合法映射。

| 口径 | 覆盖率 |
|:--|--:|
| 不约束科 | 70.1%（数字好看但是错的） |
| **按科约束（采用）** | **65.8%（2,199 / 3,341）**，抽 20 条人工复核全对 |

### 3. 页面表现

- DISPLAY 组新增开关 **「末端按属着色 / Colour tips by genus」**（默认开）。
- 24 槽调色板 `hsl(i*15, 62%, ...)`，按属名排序取色；属数 > 24 时图例给「颜色循环」提示。
- **未映射的叶显式标灰 `#b9c4cf`**，图例单列 `not mapped` 与主要原因 —— **不猜**。
- 悬停 tooltip 增加 `genus: <属名>`；点击详情面板增加 `GENUS` 一行。
- 页脚补一行**来源声明**：属由 MSL41 映射而来，**不是 ICTV 在这棵树上的标注**。
- **降级**：`genus_map.json` 取不到时自动关开关并隐藏控件，页面与改动前逐像素一致。

### 4. 顺带修掉两个既有 bug（同一个根因）

**根因**：`boot()` 里 `state.treeId = wantTree || (best ? best.t : f0.trees[0].id)`
把**树对象**赋给了 `state.treeId`（应为 `best.t.id`）。`currentTree()` 找不到匹配 id 时
会静默回退，所以平时看不出。

**表现 1 — 属映射查表全部落空**（本次开发时撞上）：任何以 `state.treeId` 为键的查表都会 miss
（`GEN.trees[tid]` 被它打空，表现为图例空、叶全灰，而 `hasKey` 明明是 true）。
另外它让「挑一棵中等规模的树」这一意图失效。

**表现 2 — PNG 导出在默认加载下彻底失效**（既有缺陷，本次顺带修好）：
`#btnPng` 里 `a.download = state.treeId.replace(/[|]/g, '_') + '.png'`，
而 `state.treeId` 是对象 → 抛 `TypeError: state.treeId.replace is not a function`，
**点击后什么都不发生、没有任何下载**。实测触发面：

| 加载方式 | 改动前 | 改动后 |
|:--|:--|:--|
| 默认（无 `?tree=`） | ❌ 抛异常、不下载 | ✅ `Alphaflexiviridae_Fig3.png` |
| `?tree=Alphaflexiviridae\|Fig3` | ✅ 正常 | ✅ 正常 |
| `?family=Potyviridae` | ✅ 正常 | ✅ 正常 |

即**用户直接打开页面再点 PNG**（最常见路径）本来就是坏的。

已核 `best.t` 恰是 `best.f.trees[0]`，**故本修复不改变默认视图**（见 §8 的 15 状态 0 像素差）。

### 5. 验收（全部实测）

像素比对裁到画布区域（`#chart`）：

| 判据 | 结果 |
|:--|--:|
| A/A 基线 NEW vs NEW2 | **0 px** |
| 降级 NEW_NOGEN vs OLD（无 `genus_map.json`） | **0 px** |
| 生效 NEW vs OLD | 910 px（0.1032%） |
| 可逆 NEW_OFF vs OLD（关开关） | **0 px** |

补充验收 5 项全过：环形模式生效（1746 px）、Rhabdoviridae Fig4/Fig5 调色板**恰好用满 24 色**、
切语言图例刷成中文、开关反向对照 910 px、搜索高亮橙色未被属色盖掉。

线上实测（打 `http://39.106.101.94/phylo/molecular/`）：`genus_map.json` **200**、
默认视图 7 种叶色、图例非空、tooltip 含 `genus: Potexvirus`；服务端 JSON 逐树汇总自洽
（tips=3341 / mapped=2199）。

### 6. 已知未映射（照实呈现，未人工补标）

转座子元件名（Metaviridae / Pseudoviridae，`Gmr1`/`Osvaldo`/`Woot` 等）、
Phenuiviridae 的裸登录号、Aspiviridae 的蛋白登录号（且含非植物外群）、
以及 Konkoviridae / Benyviridae / Solemoviridae / Closteroviridae / Virgaviridae 缩写缺失。
一律标灰，数量与原因写进 `genus_map.json` 的 `unmappedReasons`。

### 7. 部署

`docs/phylo/molecular/index.html`（45,728→46,443 B）、`docs/phylo/molecular/genus_map.json`（新增，110,981 B）、
`docs/phylo/build_genus_map.py`（新增，8,898 B）。逐文件 scp + md5 比对一致；
原 `index.html` 备份为 `index.html.bak_20260923a.genuscolor`（md5 `e54771f5…`，即改动前版本）。
**nginx 无需改动** —— 现有 `location /phylo/molecular/`（`root` + `try_files`）直接托管 JSON。

### 8. 无回归验证：改动**没有碰坏任何原有功能**

本次改的是**已验收页面**，且动了 `render()`、环形树的 `conv()`、`bindUI()` 与 `boot()`，
所以只证明「新功能对」还不够 —— 必须证明**原有控件一个都没变**。

`docs/phylo/work/verify_molecular_no_regression.py` 对**每个已有功能状态**比对
「新页面（拦掉 `genus_map.json` → 自动降级成没有这个功能）」vs「改动前的 HTML」，
裁到画布必须 **0 像素差**，同时比对画布外的文本（统计 chip / 标题 / 支持度读数 / 节点详情面板）。

| 状态 | 像素差 | 状态 | 像素差 |
|:--|--:|:--|--:|
| 默认视图 | **0** | 搜索=potexvirus | **0** |
| 环形布局 | **0** | 搜索=无命中串 | **0** |
| 枝长比例=关 | **0** | 点 Fit width | **0** |
| 显示支持度=关 | **0** | 点 Reset | **0** |
| 显示末端标签=关 | **0** | 点环形再回枝长 | **0** |
| 支持度阈值=70 / 100 | **0** / **0** | 点一个末端（详情面板） | **0** |
| 切科=Potyviridae | **0** | | |
| 切树=Rhabdoviridae\|Fig4 | **0** | | |

**15 / 15 状态全部 0 像素差，chip/标题/支持度读数/详情面板文本也全部一致** ——
**渲染层面**本次改动是纯增量的，原有功能未被影响。

> **更正（我上一版写错了）**：这里原本写的是"本次改动是纯增量的"，不够准确。
> 补做的**功能探针**查出**一处有意的差异**（不是回归）：改动前 **PNG 导出**在**默认加载**
> （无 `?tree=` 参数）下**就是坏的** —— `a.download = state.treeId.replace(/[|]/g,'_')`，
> 而 `state.treeId` 当时被 `boot()` 赋成了**树对象**，`.replace` 不是函数 → 抛
> `TypeError: state.treeId.replace is not a function`，**点击后什么都不发生、没有任何下载**；
> 带 `?tree=` / `?family=` 时反而正常（那时 `state.treeId` 是字符串）。
> 本次 `boot()` 的修复**顺带修好了它**。所以准确说法是：
> **渲染不变（15/15 状态 0 像素差），另修复 1 个既有缺陷（PNG 导出）**。

⚠️ **方法论教训**：**像素对拍看不出「点了什么都不发生」。** PNG 导出这个缺陷画布
**一个像素都不变**，纯像素回归会**完全漏掉**。因此 `verify_molecular_no_regression.py`
除 15 个像素状态外，另加**功能探针**：断言控件**确实产生预期副作用**
（PNG 探针：默认加载下点击 → 必须触发下载；改动前失败、改动后成功，均已被脚本固化）。

> 用「拦掉派生数据」而不是「关掉开关」来造参照态：`#btnReset` 会把 `state.colorGenus`
> 重置为 `!!GEN`，在派生数据被拦掉时 `GEN` 为 `null` → 始终为 false，
> 不会被任何交互意外打开，比手动取消勾选更稳。

## [2026-09-23a] — 修移动端桑基图标签重叠 + 本轮新扫出的溢出缺陷，`/relations/` 一并验收

### 需求
老师原话：`移动端桑基图标签重叠 等全部修复吧`。
即把 `[2026-09-22l]` §5 里「留待老师决定」的那条已知问题落地，
再连带把「等全部」扫出来的其它缺陷一起处置。已部署并通过视觉验收。

### 1. 起因：390px 下桑基图四个标签列互相压字

`/association/` 原页把标签列的宽度按**桌面宽度**写死，容器窄下来后四列挤在一处。
两处改动：

- `sankeyGutter` / `nodeGap` 改为随容器宽度取值（宽屏照旧、窄屏收紧），
  保证四列标签各自有自己的水平走廊；
- 修 ECharts 的**尺寸盲区**：原来只在初始化时量一次高度，
  语言切换 / 窗口缩放后画布不跟着变，窄屏下画布高度比内容矮一截，
  标签被算进了错误的位置。现在渲染时同步高度、宽度交给 ResizeObserver。

实测（zrender display list 世界坐标，非目测）：

| 页面 | 视口 | 标签总数 | 可见 | 重叠对 | 被裁 |
|:--|--:|--:|--:|--:|--:|
| `/association/` 独立 | 390 | 32 | 32 | 0 | 0 |
| `/association/` 独立 | 768 | 32 | 32 | 0 | 0 |
| `/relations/` 内嵌桑基 | 390 / 768 / 1440 | 32 | 32 | 0 | 0 |

`/network/` 两个 tab 的 12 种状态同样是 `OVERLAP=0 clipped=0`。
视觉验收（12 张全页图）确认：原缺陷那页 `A_assoc_390.png` pass。

### 2. 语言按钮从画布上搬进顶栏

`i18n.js` 的 `injectToggle()` 把按钮做成左下角 `position:fixed` 的 44px 圆圈。
`/association/` 和 `/network/` 的画布都是**通栏满宽**，躲不开：
实测 390px 下它压住画布左上 44×38px，768px 下压 44×44px，
`/network/` 的图例第一项左上角也被啃掉一块（图例因此曾右让 70px）。

两页各加一个 IIFE，把按钮收进 `nav.topbar .stats`，和旁边的统计 chip 排在一起。
**直接重写 `style.cssText` 而不是加 class** —— 宽高/圆角/定位都是内联样式，样式表盖不过去；
`onclick` 是属性赋值，搬节点不丢。

有个坑：`/network/` 的 `fillStats()` 用 `innerHTML` 重建 chip，
**会把挂在同一个 `.stats` 下的按钮一起冲掉**，而 relocation 脚本只能搬现存节点、重建不出一个来。
解法是给 chip 单独一个 `<span id="statbar">` 并设 `display:contents`
（这层壳子在 flex 里透明，chip 仍按 `.stats` 的子元素排布），按钮挂在 `.stats` 本身上。

顺带清掉两处因为按钮存在才加的打补丁：
`.legendbar` 窄屏的 `padding-left:70px`（图例左边缘回到 17，与上面的 `chart-head` 对齐）、
两页 footer 的 76px 左边距（正文回到 20）。

实测 390 / 768 / 1440 三档：按钮 52×25、`position:static`、挂在 `.stats` 下、
**与画布零重叠**；中英切换正常；切 tab 后按钮不被冲掉；`pageerrors: none`。

### 3. 【本轮新发现】`/network/` 在 768–1150px 竖屏把脚注压在图上

视觉验收报出来的，本地量过确认是真的，而且**不是原来的问题**：
`body` 被钉成 `height:100vh`，`≤1150px` 时 `.layout` 变成一列
（控件在上、画布在下），控件一栏实测 604px（768 宽）/ 771px（390 宽），
画布 `min-height` 又要 480px，加起来超过 body 能给 `.layout` 的确定高度，
画布就溢出版心 —— 实测 768×1024 下 **footer 位于 y=870 而画布铺到 y=1184**，
灰色脚注整段压在图上，页面上像渲染坏了一样。
390px 看不出来是因为视口矮（844 < 910），`@media(max-height:910px)` 恰好兜住。

修法：`≤1150px` 时把 `body{height:100vh}` 换成 `height:auto;min-height:100vh`。
窄屏下侧栏本来就是 `position:static;max-height:none`，不靠 body 的确定高度，撤掉无副作用；
取舍和已有的 `@media(max-height:910px)` 一致 —— 放不下就整页滚动，不裁内容。

7 个视口 × 2 个 tab 全部实测通过（画布底边比 footer 顶边高 15px，相交元素 0 个）：

| 视口 | overFooter | 与画布相交元素 |
|:--|--:|--:|
| 390×844 | −15 px | 0 |
| 768×1024 | −15 px | 0 |
| 768×1366 | −15 px | 0 |
| 1024×1366 | −15 px | 0 |
| 1150×1200 | −15 px | 0 |
| 820×1180 | −15 px | 0 |
| 1440×900 | −15 px | 0 |

同时确认外壳没被带坏：`/relations/` 内嵌 graph / tvh 的 iframe 仍是 356×1816 / 734×1620，
没有出现「min-height 反激」式的高度暴涨。

### 4. 【验收报的第三处】`/vector/` 表格"被截断" —— 是误报，但补了滑动线索

视觉验收判 `C_hub_390_vector.png` fail：Virus Name 列在卡片右缘被切断
（`Cauliflower mosaic` 切在 `virus` 前、`Rice tungro baciliff…`）。
量过发现**没有内容丢失**：内嵌 iframe 里 `.table-wrap` 是 `scrollWidth=1066 / clientWidth=336`
的横滚容器，逐个 `<td>` 量 `scrollWidth - clientWidth` 最大为 **0**，
内页文档也没有横向溢出。全页截图拍不到裹层里的横滚内容，右缘看起来就是切断的。

真正的问题是**没有滑动线索**：移动端（`≤720px`）把滚动条藏了，
于是"右边还有"这件事在图上完全看不出来。
给 `.table-wrap` 加了一条右缘渐隐（`mask-image`）。
mask 挂在 `overflow` 容器自身上，坐标跟着容器边框走而不跟着内容滚动，
手指划动时这条渐隐钉在原位。

**这一处已上线**（老师随后明确「上线」）。`/vector/` 由 `8.plant-insect/api_server.py` 的 Flask 出，
模板在 import 时读进内存，所以要重启 gunicorn 才生效：`systemctl restart vector-host.service`。
上传前比对过线上副本 —— 服务端那份停在 **9-13**，**连 `.table-wrap` 裹层都还没有**，
也就是说上一轮做的移动端横滚改造一直没上线，这次连同渐隐一起补齐了。
`api_server.py` 本地与服务端逐字节一致，无需改 Python 侧。

线上实测 390px：`mask` 生效、裹层可横滚（1066 / 370）、**文档宽度等于视口（无横向溢出）**、
100 行数据正常渲染、`pageerror` 无。

### Files changed

| 文件 | 改动 |
|:--|:--|
| `docs/association/index.html` | 标签列宽随容器自适应 + ECharts 尺寸盲区 + 语言按钮搬进顶栏 + footer 左边距归位 |
| `docs/network/index.html` | 同上 + **`≤1150px` 撤掉 `body{height:100vh}`**（修画布压脚注）+ `#statbar`/`display:contents` 拆分 + 图例左缩进归位 |
| `8.plant-insect/vector_page.html` | 移动端表格右缘渐隐 + `.table-wrap` 裹层（**本轮补齐上线**，已重启 gunicorn） |
| `CHANGELOG.md` | 本条 |

### Verification

- `/association/` 390 / 768、`/network/` 两个 tab × 7 个视口：标签重叠 0、被裁 0、画布不压脚注
- 语言按钮三档视口：`position:static`、在 `.stats` 下、与画布零重叠、中英切换正常、切 tab 不丢
- 视觉验收 12 张全页图：原缺陷页与该页中文版均 pass；`/relations/` 四视图 pass
- 部署：`docs/network/index.html`、`docs/association/index.html` 逐文件 scp，
  线上 md5 与本地逐字节一致（`b7b071c47d00` / `7d0270140362`），备份 `.bak_20260923.net768`
- 本轮三个文件全部上线：`docs/network/index.html`（`b7b071c47d00`）、
  `docs/association/index.html`（`7d0270140362`）、
  `8.plant-insect/vector_page.html`（`afaab48a4832`，已 `systemctl restart vector-host.service`），
  备份分别为 `.bak_20260923.net768` 与 `.bak_20260923.vecfade`

## [2026-09-22n] — 把 `[2026-09-22m]` 的「未做」全部落地 + 修 `/genes/` 的 Windows 反斜杠文件名 bug

### 需求
老师原话：`再次检查，全部修复`。范围 = 上一轮列在「未做（等老师定）」里的四项，加上「再次检查」扫出来的新问题。

### 1. 【新发现·最严重】`/genes/` 有 62 个文件名字面含反斜杠 → 32 个下载链接 404

服务端 `docs/genes/` 里躺着 62 个名字带**字面反斜杠**的文件，如：

```
docs/genes/data\UPS_all_genes.tsv        # 目录分隔符被当成文件名的一部分
docs/genes/data\protein_sRNA_AGO.fasta
docs/genes/data\all_genes_classified.json
```

成因是**在 Windows 上跑生成脚本、用 `os.path.join('data', ...)` 拼出 `data\xxx` 再上传**。
Linux 把 `\` 当普通字符 → 这些文件**不在 `data/` 目录里**，而 `gene_browser.html` 的 44 个
`data/...` 引用中 **32 个 404**（其余 12 个命中 `data/` 里真有的文件）。

- 判据：`/genes/data/all_genes_classified.json` **HTTP 404**（而磁盘上确有该文件，只是叫 `data\...`）
- 影响：`/genes/`（"Plant Immune & sRNA Gene Atlas"）页面上 **46 个下载链接里 32 个点下去是 404**。
  首屏 KPI 数字不受影响（页面只在加载时取 `data/gene_data.js`），所以**光看页面看不出来** —— 得逐个 `fetch` 下载链接才发现。
- 修法：目标 `data/<base>` **不存在** → 重命名进 `data/`（**54 个**）；
  目标**已存在** → 保留 `data/` 现状（页面本就在用它），把反斜杠副本移到归档区（**8 个**）。
- **8 个重名的不动 `data/`**，因为方向不一致、且不能猜：
  - `gene_data.js`（反斜杠 2,338,504 B / `data/` 3,288,479 B）、`files_manifest.json`：`data/` 更新更大 → 保留 `data/`
  - **6 个 `sRNA_*_genes.tsv`**：两版**表头同为 8 列、行集几乎完全不相交（交集仅表头）**
    （如 `sRNA_DRB`：反斜杠 1,190 行 vs `data/` 5,000 行）。**同一 schema 的两套不同数据集，无法判定哪版对** →
    保留 `data/` 现状，反斜杠副本移入 `/opt/plant_virus_db/.archive/genes_backslash_dupes_20260922/`，**报给老师定**。
- 验收：修后 **46/46 下载链接 HTTP 200**（真浏览器在页面内逐个 `fetch`）；`genes/` 下反斜杠条目 **0**；`data/` 文件数 30 → 84。

### 2. `docs/literature/` 死副本 → 归档；`deploy_web.py` 去掉残留同步

上一轮只删了 `/antigenes/` 死链，留了「这份文件还留不留」给老师。本轮查清并归档：

- `docs/literature/` **被 nginx `location /literature/`（proxy_pass :5003）完全遮蔽**，
  仅经**历史别名** `/reference/literature/` 可达 —— 而该别名路径是**坏页面**：
  `GET /reference/literature/` → 200，但 `/reference/literature/data/1941.json` → **404**
  （服务端只同步了 22 个文件，不是 863 个）。
- 本地 `docs/literature/data/` 与 `7.literature_tracker/web/data/` **863 个文件中 862 个逐字节相同**
  （唯一差异是生成物 `stats.json`）；`index.html`/`app.js` 均为 `web/` 同名文件的旧版
  （60,779 vs 61,054 B；11,695 vs 22,555 B）→ **本地这份是完整重复，归档不丢任何独有数据**。
- `deploy_web.py:53-70` 仍在往该被遮蔽路径同步 `index.html`+`app.js`（**且漏了 `data/` 与 `styles.css`**，
  这正是坏页面的成因）→ **移除该段**，替换为说明为何移除的注释。脚本语法检查通过（2,828 → 2,869 B）。
- 归档：本地 866 文件 / 63.5 MB → `archive/_pending_delete_20260922/literature_stale_static_copy/`；
  服务端 41 文件 → `/opt/plant_virus_db/.archive/literature_static_20260922/`（**含两个字面反斜杠目录**
  `data\monthly`、`data\weekly`，一并带走）。
- 验收：`/literature/`（Flask）仍 200；`/reference/` 仍 200；全站路由扫描**缺口 0**。

### 3. nginx：备份文件拦截模式补上 `_bak` 结尾

上一轮记的「未做」项：`/lib/plotly.min.js.truncated_bak` **HTTP 200、3.3 MB 可公开下载**，
因为既有规则 `location ~* \.bak[_.]` **匹配不到 `_bak` 结尾**（没有 `.bak` 这个子串）。

- 先扫全站 28 个 bak 类文件确认扩展**不会误伤**：新模式 `(\.bak[_.]|_bak($|[_.]))` 全覆盖
- 就地改 conf + 幂等备份 + `nginx -t` 通过后 reload（+ 校验失败自动回滚）
- 验收：`/lib/plotly.min.js.truncated_bak` → **404**；`/lib/plotly.min.js`（本体）仍 **200**、未误伤

### 4. phylo 两页「切语言后 placeholder 不刷新」→ 修

`i18n.js` 现为 **v4.0**（按钮 `#pvdb-lang-btn`）；v3.0 时代是 `#pvdb-i18n-btn`。
**两版的 `PVDB_i18n.lang` 都是函数**（v3 `lang:function(){return lang;}` / v4 `lang:lang`）。

全站扫描 29 个有 i18n 耦合的页面后定位两处：

| 页面 | 病因 |
|:--|:--|
| `docs/phylo/index.html` | 只 `getElementById('pvdb-i18n-btn')`，v4.0 下**绑不上**，点击无反应 |
| `docs/phylo/molecular/index.html` | `fixPlaceholders()` 只在 `fetch` 回调里跑**一次**，切语言不重跑 |

`docs/phylo/molecular/families/index.html` 已是**正确范式**（文档级委托、两个 id 都认）→ 照它统一。
两页各加「文档级 capture 点击委托」，两个 id 都认、与按钮注入时机无关。

**反向对照（关键）**：用 `page.route` 把**改前版本**喂回浏览器 ——
改前版本 `html.lang` 从 `en` 变到 `zh-CN`（证明点击确实生效），**但 placeholder 不变**；
改后版本 placeholder 正常刷新且可逆。→ 证明这个检查确实能抓到原 bug，不是「两边都静止」的假通过。

验收：本地 + 线上各跑一遍，两页 placeholder `Family / genus / species…` ⇄ `科 / 属 / 种名…`、
`accession / species…` ⇄ `登录号 / 物种名…` 均正确切换；线上 2/2 md5 MATCH。

### 5. 镜像补齐 + 双向漂移按「内容判方向」逐文件处置

**先承认上一轮的判据错误**：上一轮凭 mtime 说「服务端更新」，不成立。本轮一律**按内容判方向**。

**5.1 补齐本地缺失（非备份）**：服务端独有 560 个 / 1,831 MB。
排除**纯备份与生成缓存** 400 个 / 1,573 MB（`data/backup_20260901` 486 MB、`data/backup_pre_tswv_20260918` 486 MB、
`data/incremental_updates/` 291 MB、`data/pdf_images/` 179 MB〔**0 页面引用**〕、
`taxonomy/taxdump.tar.gz` 75 MB〔NCBI dump 缓存〕、`data/backup_broken_align_*` 50 MB、各类 `*.bak*`），
**拉回 160 个 / 258.6 MB**（`genes/**`、`genes/data/**`、`data/` 9 个、`data/primers/`、
`phylo/work/` 49 个、`te/data/`、`data/host_analysis/`、根级 `robots.txt`/`sitemap.xml`/`favicon-aphid.svg`/`.nojekyll` 等）。
用 `tar` 流式（**不整目录 scp**）。验收：服务端独有 **560 → 400**，剩下的恰好全是排除项，「待拉取 0」。

**5.2 双向漂移逐文件处置**（34 个大小不同）：

| 方向 | 文件 | 处置 |
|:--|:--|:--|
| **本地新 → 部署** | `help/*.html` ×11（补中文译文；服务端仍是 `Core Features\|Core Features`，个别还写坏如 `APIAccess`） | 部署 |
| **本地新 → 部署** | `association/index.html`（`sankeyGutter()` 窄屏留白修复 + `chart.resize()`，本地 +50 行） | 部署 |
| **本地新 → 部署** | `phylo/build_taxonomy.py`（2026-09-22 老师口径：保留「与植物病毒同目」的非植物科）、`phylo/build_own_trees.py`（`species_key()` 修 `VMR_Species` 14.7% 填充率 bug）、`phylo/build_molecular.py`（Newick 方括号注释 `continue` 多造子树 bug）、`network/build_network.py`（缩写→属回退） | 部署 |
| **本地新 → 部署** | `phylo/work/Caulimoviridae.fa.aln`（服务端是 **0 B 空文件**，本地 2.8 MB 有内容） | 部署 |
| **服务端新 → 拉回** | `te/te_index_clean.html`、`te/te_head.html`、`te/te_index_full.html`（服务端已改 `/lib/chart.umd.min.js`，本地还在引 **CDN** —— 违反项目铁律） | 拉回 |

验收：部署 **17/17** + 拉取 **3/3** md5 MATCH；线上真浏览器 `/help/reference.html`（zh）渲染含「核心功能」、
`/association/` 有 `sankeyGutter`、`/te/` 从 `/lib/chart` 取库且 **CDN 请求 0 条**；全站路由扫描**缺口 0**。

**5.3 未动、报给老师（生成类数据，方向双向、需流水线语义）**：
`data/Plant_Virus_Full.fasta`（服务端 +65 MB）、`Plant_Virus_Ref.fasta`（+16 MB）、
`Plant_Virus_Full.Info.tsv`（服务端 210,168 行 vs 本地 199,071）、`Plant_Virus_Ref.Info.tsv`（12,160 vs 8,466）、
`.incremental_state.json`（4.28 MB vs 94 B）、`DATA_VERSION` —— **服务端新**；
`data/unified_gallery.json`（本地 2,975 条 vs 服务端 2,854）、`help/images/pamirdb_result.png`、
`.nojekyll` —— **本地新**。
（`dpv_gallery.json` 与 `eppo_gallery.json` 两侧**条目数完全相同**（1,287 / 925），只是本地压缩成 1 行、
服务端美化格式 —— **不是分歧**；`Plant_Virus.complete_ref_info.tsv` 两侧同为 5,774 行，同理。）

### Verification

- `/genes/`：46/46 下载链接 200；`genes/` 反斜杠条目 0；`data/` 30 → 84 文件
- `/literature/`：Flask 页仍 200；`/reference/` 仍 200；死副本已归档
- nginx：`truncated_bak` 404、`plotly.min.js` 200；`nginx -t` 通过后 reload
- phylo i18n：本地 + 线上各 2 页 placeholder 切换正确，**A/A 基线 + A/B 反向对照均通过**
- 镜像：服务端独有 560 → 400（余者全是排除项）；部署 17/17 + 拉取 3/3 MATCH
- 全站路由扫描：**缺口 0**（修前 0，本轮改动无回归）

### Files changed

| 文件 | 改前 | 改后 |
|:--|:--|:--|
| `docs/phylo/index.html` | 42,014 B | 42,305 B（文档级委托，两个按钮 id 都认） |
| `docs/phylo/molecular/index.html` | 36,146 B | 36,597 B（同上，加切语言重刷） |
| `docs/README.md` | 9,665 B | 9,792 B（`literature/` 树条目改为「已归档」） |
| `7.literature_tracker/web/deploy_web.py` | 2,828 B | 2,869 B（移除写向被遮蔽路径的残留同步） |
| 服务端 `docs/genes/**` | 62 个字面反斜杠文件 | 54 个移入 `data/`，8 个移入归档区 |
| 服务端 `/etc/nginx/conf.d/plant-virus.conf` | `\.bak[_.]` | `(\.bak[_.]\|_bak($\|[_.]))` |
| 本地 `docs/**` | — | 拉回 160 个服务端独有文件 + 3 个 te 页 |
| 归档 | — | `archive/_pending_delete_20260922/literature_stale_static_copy/`（866 文件 / 63.5 MB） |

## [2026-09-22m] — 本地镜像过期文件回拉同步（6 个顶层文件 + 配套）+ 删掉 `/antigenes/` 死链

### 需求
老师原话两条：
> `/antigenes/`：全项目仅 literature/index.html 一处导航链接，无应用、无 location、无服务、无文档 → 无目标可指 **修复**
> 本地镜像对服务端有 6 个顶层文件过期 **修复 旧版归档**

### 1. 先查方向：不是「本地落后」，而是**双向漂移**

上一轮我只凭 mtime 说「服务端更新」，**这个判据不成立**。这轮做了**四向对照**
（本地工作区 / `git HEAD` / `snapshots/server_work_20260911/` / 线上现版）：

| 文件 | 本地工作区 | git HEAD | 9-11 快照 | 线上现版 | 结论 |
|:--|:--|:--|:--|:--|:--|
| `i18n.js` | `f35fdb83`(v3.0) | =本地 | `7446b0b5` | `7446b0b5`(v4.0) | 线上新 |
| `download.html` | `aff298d5` | `019507bc` | =本地 | `5fa174cb` | 线上新（9-19 又改过） |
| `nonsegmented.html` | `c4c00bec` | `8bab58e7` | `90e7720c` | `5ae62eeb` | 三边都不同，线上最新 |
| `segmented.html` | `d97817dd` | `22f0722f` | `5a1b7f2b` | `7adf5bb2` | 同上 |
| `submit.html` | `e02a27f5` | `1ba96d3a` | `bdde09dd` | `51fc1325` | 同上 |
| `resources.html` | `cbcb3b38` | `1a3aa0f2` | `c772bd31` | `4c2c6d25` | 同上 |

**本地那 5 份是「`git HEAD` 之外的未提交改动」，且都停在 7-29**；线上是 9-11/9-14/9-19 的版本。
判「哪边对」不看 mtime，看**内容**：

- 线上版用**本地 `lib/*`**，本地版引 **CDN**（`cdn.datatables.net`）—— 本地版违反项目铁律「不要引 CDN」
- 线上版补了 `<link rel="icon" href="/favicon.svg">`，本地版没有
- **本地 `nonsegmented.html` 的 `data-i18n` 属性是坏的**：
  `data-i18n="Non-Segmented Viruses|非分段病毒"Non‑Segmented` —— **少了一个 `>`**，标签被撑破
- `i18n.js`：线上 **v4.0**（`{init, apply, setLang, lang}`、按钮 `#pvdb-lang-btn`、含 `markActive()`），
  本地 **v3.0**（`{init, toggle, swap, lang}`、按钮 `#pvdb-i18n-btn`）—— 与 `[2026-09-22l]` 记的「本地仍是 v3、
  严禁推送覆盖」完全吻合

**同时确认漂移是双向的**：`docs/help/*.html`（11 个）本地**更大且含中文译文**（线上仍是 `Core Features|Core Features`
未译），`association/index.html` 本地 +1,985 B —— 这些是**本地新、线上旧**，**本轮一律没动**（见 §5）。

### 2. 同步：只「拉」不「推」

方向 = **本地 ← 服务端**。逐个 `scp` 取回（**禁整目录 scp**，会把线上更新版回退——既有铁律）：

- 6 个点名文件：`i18n.js` `download.html` `nonsegmented.html` `segmented.html` `submit.html` `resources.html`
- 配套 **`favicon.svg`**（795 B）—— 同步后这 6 页都新引用了它，本地没有
- 配套 **`docs/lib/`（17 个文件）**—— `nonsegmented/segmented` 新引用 `lib/*` 共 8 个；
  且 `photos.html`/`reference_index.html`/`te/index.html` **早就在引用 `lib/chart.umd.min.js`**（既有悬空引用）。
  **排除**线上那个 `lib/plotly.min.js.truncated_bak`（3.3 MB 垃圾备份，见 §5）

本地旧版全部先备份到 `archive/_pending_delete_20260922/mirror_sync_20260922/local_old/`。

### 3. `/antigenes/`：删链接（不是造路由）

- 全项目仅 `docs/literature/index.html:122` 一处真链接（其余 grep 命中都是论文摘要里的英文单词）
- 线上真正在服务的 `/literature/` 是 **Flask 5003 发的 `7.literature_tracker/web/index.html`**，
  其 12 项导航**既无 `/antigenes/` 也无 `/miRNA/`**（新版用 `/pamirdb/`）
- `docs/literature/index.html` 是**从未被服务**的手工遗留副本（`deploy_web.py` 只同步到 `7.literature_tracker/web/`），
  其 8 项导航是三代前的设计
- 13 个 nginx conf 备份里**从未出现过** `/antigenes/`；`snapshots/server_work_20260911/` 里的
  `patch_nginx_antivirals.py` 是**另一个**路由（`/antivirals/` 植物源抗病毒化合物），与 AntiGenes 无关
- 故修法 = **删掉该行**（两侧各自就地改，不互相覆盖：本地 CRLF、服务端 LF）

### 4. 验收

- 本地镜像自洽：起本地 HTTP 服务逐个 GET，**6 页 + `favicon.svg` + 9 个 lib 全 200 且与磁盘逐字节一致，0 失败**
- 与线上逐字节：**7/7 MATCH**（6 文件 + `favicon.svg`）；`docs/lib/` **17/17 一致**
- 死链：本地 / 服务端 `docs/literature/index.html` 的 `antigenes` 计数 **0 / 0**；本地 `GET /antigenes/` → 404
- 线上无回归：`/literature/` 仍 200 且导航无 antigenes；全站引用扫描**缺口数 = 0**
- 换行符守恒：本地 `docs/literature/index.html` CR 901→900、仍 CRLF；服务端仍 CR=0（纯 LF）
- 悬空引用检查：0 条（`data-src="full"/"ref"` 是来源切换按钮的 data 属性，非资源引用）

### 5. 未做（等老师定）

1. **本地镜像还有更大范围的漂移**，本轮只处理点名的 6 个 + 配套：
   - **本地新、线上旧**（本地有未部署的改进）：`docs/help/*.html`（11 个，含中文译文）、
     `association/index.html`、`docs/index.html`（=线上，已同步）、`te/index.html`
   - **仅线上有**（本地缺）：`robots.txt`、`sitemap.xml`、`favicon-aphid.svg`、`help/resources.html`、
     `genes/**`（含 3.3 MB `gene_data.js`）、`lib/` 剩余 7 个（echarts/plotly/xlsx/bootstrap + `fonts/`）
2. **`/lib/plotly.min.js.truncated_bak` 可被公开下载**（HTTP 200、3.3 MB）。
   上一轮修 `.bak_*` 的模式**没覆盖 `_bak` 结尾**。属新发现，未动 nginx。
3. **`docs/phylo/index.html:871` 是既有线上小 bug**：只认 v3 的按钮 id `pvdb-i18n-btn`，
   而线上 i18n 是 v4.0（`pvdb-lang-btn`）→ 切语言时搜索框 placeholder 不刷新（有 `if (btn && ...)` 兜底，不报错）。
   该文件本地与线上**逐字节一致**（`f3f44dde`），所以这是线上既有行为，非本轮引入。未改。
4. `docs/literature/index.html` 整体是死副本（未被服务、且与线上 Flask 版内容不同）。
   本轮只删了死链，**没有**把它对齐到 Flask 版 —— 那要先定「这份文件到底还留不留」。

### Files changed

| 文件 | 改前 | 改后 |
|:--|:--|:--|
| `docs/i18n.js` | `f35fdb83` (3,801 B, v3.0) | `7446b0b5` (3,208 B, v4.0) |
| `docs/download.html` | `aff298d5` (11,320 B) | `5fa174cb` (11,437 B) |
| `docs/nonsegmented.html` | `c4c00bec` (10,772 B) | `5ae62eeb` (11,096 B) |
| `docs/segmented.html` | `d97817dd` (10,752 B) | `7adf5bb2` (11,074 B) |
| `docs/submit.html` | `e02a27f5` (16,754 B) | `51fc1325` (16,711 B) |
| `docs/resources.html` | `cbcb3b38` (42,788 B) | `4c2c6d25` (42,651 B) |
| `docs/favicon.svg` | 无 | `15390d25` (795 B) |
| `docs/lib/` | 无 | 17 个文件（与服务端一致） |
| `docs/literature/index.html` | 60,818 B | 60,779 B（删 `/antigenes/` 一行，CRLF 守恒） |
| 服务端 `docs/literature/index.html` | 59,833 B | 59,795 B（同上一行，LF 守恒；备份 `*.bak_20260922_antigenes`） |

## [2026-09-22l] — `/relations/` 汇总页：三个页面合成一张卡，本身一个字节不改

### 需求
「页面展示了太多的卡片，所以，我就有点想合并 `/vector/` `/vector//association/` `/network/`
内嵌呢，**不改变原来的**」——原话把三个页面嵌进一个入口，且**原页必须保持原样**。
老师随后定下两件事：① 用**视图切换器**（4 个视图）；② 外壳上**两个数都标**
（1,806 条记录 与 1,375 条三元组），因为四个视图口径不同、各有人关心。

### 0. 先定「不改变原来的」到底怎么落地

原页 `/association/`、`/network/`、`/vector/` **零改动**（唯一例外见 §3）。
汇总页 `/relations/` 是**新文件**（`docs/relations/index.html`，未纳入 git），
用 iframe 全屏嵌入原页：

| 视图 | 嵌入对象 | 内容 |
|:--|:--|:--|
| 关联流 | `/association/` | 桑基图（ECharts → canvas） |
| 病毒–宿主网络 | `/network/` | 力导向图（canvas，199,070 条序列） |
| 媒介–病毒–宿主网络 | `/network/#tvh` | 1,375 条文献验证三元组 |
| 媒介与文献库 | `/vector/` | Flask 服务端表格 |

**4 个视图而不是 3 个**：`/network/` 自带两个 Tab，直接嵌整页会让用户在外壳里
再点一次；拆成两个视图、用深链 `#tvh` 定位，外壳一次点到位。

### 1. 深链是拆 Tab 的前提，而 `/network/` 原先不支持

`/network/` 的 Tab 只能靠点击。为此做了**唯一的原页改动**（2 处、纯增量，不碰任何现有逻辑）：

- `switchTab()` 里锚点变化时 `history.replaceState`（try/catch）同步 `location.hash`
  —— 用 replaceState 不用 pushState：不堆历史记录，且嵌在 iframe 里**不能劫持外壳的返回键**
- 启动时读 `location.hash === '#tvh'` 选中对应 Tab，并监听 `hashchange`

效果：`/network/#tvh` 现在独立访问也是「媒介–病毒–宿主网络」Tab（上线实测
`tab-evh` 带 `on` 类、三个按钮齐全）。`replaceState` 的失败被静默吞掉 ——
`file://` 等场景下不炸，只是深层链接失效，可接受。

### 2. 外壳的四个关键实现点

**(a) 双槽 iframe 缓存**（当前 + 上一个）：切走再切回**保留下钻状态**
（网络图点开的节点不会丢），同时把内存按住 —— `/vector/` 一页就 ~8.3 MB。
暖帧保持 `visibility:hidden` 而**不是 `display:none`**：力图画在 canvas 上，
`display:none` 子树的 canvas 后备存储会被浏览器丢弃，切回来就是白的。

**(b) 高度不写死，跟内容走**（本轮修掉的最后一个视觉缺陷）：
外壳原先给舞台定高，**中文标签一高，桑基图就在折线处被拦腰截断**。
改为 iframe 内文档多高、舞台就多高 —— 整页滚，而不是在几百像素的框里套一层小滚动条。
安全性来自一次实测：三个源页的文档高度与 iframe 窗口高度**无关**
（窗口 684/900/1200/1600 四档下恒为 1058px），所以量一次就收敛，不会「越撑越高」。
400ms 轮询兜底换视图/切语言/改窗口，差不到 16px 不写盘，避免来回抖。
修后 en/zh 舞台均为 1058px、图表盒底 928px、`clipped: false`（zh 桌面版已有 visual-judge 通过记录）。

**(c) 语言跟随**：外壳轮询（400ms）+ 源页 i18n 各自独立，
i18n 是**服务端 v4.0**（`window.PVDB_i18n = {init, apply, setLang, lang}`，
按钮 id `pvdb-lang-btn`，默认 `en` 无浏览器语种探测）。本地仓库那份仍是 **v3，
严禁推送覆盖**（MEMORY.md 既有铁律，本轮再次确认线上为 v4.0）。

**(d) 外壳标注口径**：`#vdesc` 标 1,806 条记录（Vector–Virus–Host 三元组库）与
1,375 条三元组（文献验证子集），两者都标 —— 因为四个视图里只有媒介视图用到这组数。

### 3. 首页卡片 17 → 15

`/vector/`、`/network/`、`/association/` 三张卡 → **1 张**指向 `/relations/` 的汇总卡
（卡内 4 个子链直达各视图）。删除的卡片只动导航，不动被链接的页面本身。
顺带给 `.card h3 a`、`.card .path a` 补了 `color:inherit`（原页 CSS 在汇总卡里
把标题染成了默认蓝，与其它 14 张卡不一致）。

### 4. 上线与验收

- 服务器旧版备份 `*.bak_relations_20260922`；推送**逐文件 scp**（禁用整目录，
  否则回退线上较新版本 —— MEMORY.md 铁律）；推送前查 LF-only
- 线上 md5 与本地**逐字节一致**：`relations/index.html`、`index.html`、`network/index.html`
- `sitemap.xml` 就地补 1 条（18 → 19），`/relations/` 位于第 14 位，XML 良构、LF-only
- **回归 4 视图全过**：4 个 Tab + 深链 + 暖帧 ≤2 + 中文标签 + 首页 15 卡 +
  独立 `/network/#tvh` 激活正确；线上 HTTP 200 × 6（含 `/sitemap.xml`）
- **线上 fit 收敛实测**：graph 视图舞台 815px 连续 4 次采样稳定、`clipped: false`
- **zh 切换线上生效**：外壳与被嵌 association 页同时转中，`html_lang: "zh-CN"`

### 5. 留下的一处已知问题（**不是本轮引入，未修**）

移动端 390px 下桑基图标签列重叠。已查明是 `/association/` **原页自身属性**：
把 canvas 钉在同一宽度（322px），**独立访问与嵌入产生的墨迹逐字节相同**
（`ink_x0=20, ink_x1=171, blank_cols=170`），外壳是复现而非劣化。
修它必须改 `/association/`，与「不改变原来的」直接冲突 —— **留待老师决定**。

> **2026-09-23 已修**：老师随后明确「移动端桑基图标签重叠 等全部修复吧」，
> 本节这条已知问题连同外壳一起处置完毕，详见 `[2026-09-23a]`。

## [2026-09-22k] — nginx 路由修补：补 `location /` 兜底、清 5 类路由缺口、停用路由 301

### 需求
「**全部修复**」—— 处理上一轮明确留待老师决定的「两处 nginx 路由缺口」
（`GET /index.html` 返回发行版自带测试页、根级 `/README.md` 404）。

### 0. 先把「缺口」查全，而不是只修看到的两条

新增 `deploy/check_site_routes.py`：扫 `docs/` 下全部 **33 个 HTML** 里引用的**根相对 URL**（**72 个**），
逐个实测线上状态，按「本地有对应文件 / 无对应文件」分类。**结果比预期多**：

| 类别 | 数量 | 明细 |
|:--|:--|:--|
| 本地有文件、线上打不开 | **3** | `/download.html`、`/nonsegmented.html`、`/segmented.html`（均 404，都被 `te/te_index_full.html` 引用） |
| 无页面引用、但用户会手输 | 2 | `/index.html`（返回 452 B 发行版测试页）、`/README.md`（404） |
| 后端路由异常 | 2 | `/virus/` **502**（6 处导航引用）、`/antigenes/` 404（1 处） |

### 1. 根因：conf 里**只有 `location = /` 精确匹配，没有 `location /` 前缀块**

未显式声明的路径匹配不到任何 location → 落到 nginx **编译期默认 root** `/usr/share/nginx/html`，
而它的 `index.html` 是指向 `../../testpage/index.html` 的**符号链接**（发行版自带测试页）。
所以 `GET /index.html` 拿到的是**别人的页面**，`/download.html` 等则 404。

修法（服务器 conf 就地改，未用本地文件覆盖）：
```nginx
location / {
    root /opt/plant_virus_db/plant_virus_db_pipeline/docs;
    try_files $uri $uri/ =404;
}
```
`location /` 是最短前缀 → 所有既有 location 都比它更具体，**互不影响**（回归 29/29 通过）。

### 2. `/virus/` 的 502 **不是 bug，是有意停用**

本 CHANGELOG 早前已记：`13.virus_profile/` → `_archived_13.virus_profile/`，独立 `/virus/` 网页已停用、
功能并入 Virus Explorer 的「病毒档案」Tab，`virus-profile.service` 已停用。但 6 个页面
（`help/`、`photos.html`、`reference_index.html`、`te/` ×3）的导航仍指向它 → 502。
**修法不是启服务**（那属老师的方向决定），而是把死路由 301 到现役入口：
`location /virus/ { return 301 /explorer/; }`（同时加 `= /virus` 覆盖无斜杠写法）。

### 3. 另外两处

- `/miRNA/` → 301 `/pamirdb/`（依据：首页 PV-miRNA 卡片即指向 `/pamirdb/`，`literature/` 页导航用的是旧路径）
- `*.bak_*` 一律 404：`docs/` 下共 **22 个**备份文件（顶层 10 个），原先经 `/reference/` 的 alias
  **可直接下载** → 加 `location ~* \.bak[_.] { return 404; }`（已确认无任何页面引用 `.bak_`）

### Verification
- `nginx -t` 通过后 `systemctl reload nginx`；备份 `plant-virus.conf.bak_20260922_routefix`
  （**幂等**：已存在则跳过，不覆盖好备份）；conf 10,074 → 11,298 B，LF-only
- **修复项 10/10 PASS**：5 个根级静态文件 HTTP 200 且 md5 与服务端副本一致；2 个 301 目标正确；
  `.bak_` 经 `/` 与经 `/reference/` 两条路径都 404；未知路径 → **干净 404**（不再是测试页）
- **回归 29/29 PASS**：`/`、`/phylo/`、`/phylo/molecular/`、`/phylo/molecular/families/`、`/association/`、
  `/te/`、`/help/`、`/primers/`、`/explorer/`、`/literature/`、`/genes/`、`/photos/`、`/resources.html`、
  `/reference/`、`/i18n.js`、`/lib/*`、`/onekp/`、`/pamirdb/`、`/knowledge/`、`/metabuli/`、`/vector/` 等
  全部仍 200
- **全站引用扫描：缺口数 = 0**（修前 3）

### Files changed
| 文件 | 变化 |
|:--|:--|
| 服务器 `/etc/nginx/conf.d/plant-virus.conf` | 10,074 → 11,298 B；备份 `.bak_20260922_routefix` |
| `docs/README.md` | 路由表补 3 行 + 缺口成因说明；8,741 → 9,665 B |
| `deploy/check_site_routes.py` | **新增**（4,054 B），可复用的站点路由自检脚本 |

### 未做（等老师定）
1. **`/antigenes/`**：全项目仅 `literature/index.html` 一处导航链接，**无应用、无 nginx location、
   无 systemd 服务、无任何文档记载** → 无目标可指，故未擅自删链接也未擅自造路由。
2. **本地镜像对服务端有 6 个顶层文件过期**（本地 7 月版 vs 服务端 9 月版）：`download.html`、
   `i18n.js`（本地 v3.0 / 服务端 **v4.0**）、`nonsegmented.html`、`resources.html`、`segmented.html`、
   `submit.html`。**风险**：将来若从本地整目录部署，会把线上这几个页面**回退**。
   方向判断依据：服务端 mtime（9-11/14/19）与版本号都更新。**按「不顺手改」的规矩未动本地文件。**
3. **`deploy/nginx_full.conf`** 是 7 月 30 日的 5,182 B 旧快照（现役 conf 11,298 B），疑已无用途。
4. **`paper_dl_tmp/` 1.1 GB 未归档**：含真实基因组数据（`Balanophora_subcupularis.genome.fa` 1.17 GB），
   同级还有 `paper_dl/`、`paper_dl_packed/`、`paper_dl_stage/`，疑为仍在用的下载/打包工作区。
   （本日另外三个临时目录 `.tmp_nginx/`、`.deploy_tmp/`、`.tmp_wsl/` 已归档至
   `archive/_pending_delete_20260922/`，MANIFEST 45 → 48 行。）

## [2026-09-22j] — 画边交叉的真正原因 + 重生成分子树数据（去 563 空叶）+ 首页两张 phylo 卡合并

### 需求
1. 「`/phylo/molecular/` 怎么这么错乱，出现了交叉，**是不是 ICTV 有多个建树方法，但是你没区分**，
   因为有的用的全长，有的用的单个蛋白构建的。你好好检查下，到底咋回事」（附截图）
2. 首页 `/phylo/` 与 `/phylo/molecular/` 两张卡能否合并
3. 「**全都修复**」—— 一并含此前挂起的「重新生成 `molecular_trees.json`」

### 1. 交叉的原因：**画边的折点顺序写反了**（不是「混了不同建树方法」）

**先证伪那个假设**（它是半个对的，但不是本因）：
- ICTV 各章节确实按不同区域建树（`work/ictv_align_survey.md`：19 个科里 10 个是氨基酸比对，
  核苷酸的那些只覆盖基因组 7–54%；Potyviridae Fig3 是 3,084 aa 的多聚蛋白 ≈ 基因组的 95%）。**这半句对。**
- 但**本页一次只渲染一棵树**（`family` + `tree` 两个 `<select>`，`drawPhylogram(root, leafN, t)` 只收一个根），
  根本不存在「把不同区域的树画在一起」。
- 截图那棵树 `Alphaflexiviridae|Fig3`（`OPSR.Alphaflexi.Fig3.Replicase.aa.tree.nwk`）的 59 个叶
  **全部**是 `replicase`（`rdrp`/`coat`/`tgb` 只是长描述性叶名里的词）。**所以本因不是它。**

**真因**在 `docs/phylo/molecular/index.html` 的 `drawPhylogram()`：一条边是 3 点折线，
**折点的先后决定横线画在哪一层的 y 上**。

```js
// 旧（错）：横线画在**父节点**的 y 上
lineData.push({coords: [[n._x, n._y], [c._x, n._y], [c._x, c._y]]});
// 新（对）：竖线画在**父节点**的 x 上 —— 横线长度正好等于枝长
lineData.push({coords: [[n._x, n._y], [n._x, c._y], [c._x, c._y]]});
```

旧写法是**等距 cladogram**（所有枝长相等）的标准画法，那种图上横线都很短，看不出问题。
**本页 `state.useBL` 默认 `true`**（`<input id="useBL" checked>`），x 是**累积枝长** ——
一条长枝的横线会一路向右横扫，**穿过沿途所有无关枝条的竖线**。
附带第二个症状：兄弟边的横线都落在**同一个** `n._y` 上，**共线重叠成一条**。

**实测（38 棵树全量）**：

| 画法 | 交叉 | 共线重叠 | 受影响的树 |
|:---|---:|---:|---:|
| 旧（横线在父 y） | **1,397** | **3,351** | 35 / 38 |
| 新（竖线在父 x） | **0** | **0** | 0 / 38 |

截图那棵 `Alphaflexiviridae|Fig3`：59 叶 / 115 条边 → **45 处交叉 + 58 处重叠**。

- **两个互相独立的证据**（都指向 45，不是巧合）：
  ① `work/check_phylogram_crossings.py` —— 纯 Python 复刻 `setD/setY/setX` 的几何；
  ② `work/verify_phylogram_edges.py` —— **取浏览器里 ECharts 实际吃到的坐标**。
  二者在固定 `W=1200` 的复刻与真页面 1500 px 的实际几何下给出**同一个数**，
  因为「横段 × 竖段严格相交」的计数对 x、y 的**单调缩放不变**（仿射不变量）。
- **环形布局不受影响**：它走 ECharts 内置 `type:'tree', layout:'radial'`，几何由 ECharts 自己算。
- 验收脚本带**反向对照**：用 `page.route` 在网络层把折点**改回旧写法**，必须重新数出 >0 处交叉 ——
  否则这个检查可能是恒为 0 的空检查。实测 `reverted → 45`，证明它真能抓到这个 bug。

```
  [shipped ] Alphaflexiviridae|Fig3   edges=115   cross=0
  [shipped ] Rhabdoviridae|Fig4       edges=1153  cross=0
  [shipped ] Potyviridae|Fig3         edges=413   cross=0
  [shipped ] Pseudoviridae|Fig3       edges=624   cross=0
  [reverted] Alphaflexiviridae|Fig3   edges=115   cross=45
  发布版全部为 0 交叉 : PASS      反向对照确实能抓到 : PASS
```

### 2. 重生成 `molecular_trees.json`：去掉 563 个幻影空叶

解析器 bug 早已修好（见 `[2026-09-22d]`），但**产物一直没重生成**。本次按「先差分、再覆盖」执行：

- **叶总数 3,904 → 3,341**（差 563 = 207 + 149 + 207）。
- **只有 3/38 棵树变化**（Metaviridae / Pseudoviridae / Phenuiviridae），
  其余 **35 棵结构哈希逐字节不变**；树 ID 集合不变（仍 25 科 38 树）。
- 差分**按父节点分组看**（`work/diff_molecular_regen.py`），不只看总数：
  被删的叶**全部是无名空叶**（`{'': 207}` / `{'': 149}` / `{'': 207}`），
  非空叶一个没动（210/210、152/152、210/210）。
- **`internals` 完全没变**（208 / 150 / 208）—— 幻影叶是挂在**已存在**的内部节点上的，
  没有凭空多出内部节点。这同时解释了旧版「145 个多分叉」的来源：空叶把父节点度数顶到 ≥3。
- 派生数据 `molecular/families/family_index.json` 同步重生成（`build_family_index.py` 对源文件**只读**）。
  `crossAccessions` 37 / `accTotal` 1,863 / `placeholderTips` 58 / `fragmentTips` 1,077 **全部不变** ——
  幻影叶本来就不含登录号、占位符、片段标记。
- md5：`molecular_trees.json` `ea7908b792bdd6927bf67097f59a16f2`（272,915 B）
  → **`fe9f7367694dc1ed925623991ec1fb0c`（271,218 B）**；
  `family_index.json` `69a9b23afa9de817c468b39bee4d31b5` → **`8134e8f4845d9ad9d2d7e645a3b13b5a`**。
  **这两个文件都不在 git 里**，覆盖前把旧版存到 `docs/phylo/.tmp_regen/*.old.json` 作为回滚源。

### 3. 顺手查实：Metaviridae 与 Pseudoviridae 的树**是同一个文件**（上游问题）
`ORTD.Meta.Fig3.v9.treefile.nwk` 与 `ORTR.Pseudo.Fig3.treefile.nwk` md5 相同（`ed5a8d71…`，各 7,486 B）。
**本次向 ICTV 官网复核**：两个 URL（`…/inline-images/…` 与 `…/report_files/…`）**都返回 200、都是这同一份字节**
—— **重复出在 ICTV 上游，不是本库抓取或解析的问题**，本库是忠实镜像。
叶名是 `Ty3-1` / `CRM` / `Cereba` / `Tse3` / `Del` / `G-Rhodo` / `Beetle1` 这类 **Ty3/gypsy** 元件，
属 **Metaviridae** 特征（Ty1/copia 才是 Pseudoviridae），故更可能是 ICTV 把 Metaviridae 的图也挂到了
Pseudoviridae 章节页。**本页照实呈现，不擅自删改** —— 引用前建议向 ICTV 确认。

### 4. 首页两张 phylo 卡合并（方案 A）
- Analysis Tools 由 **7 张 → 6 张**（3+3 正好两行）。`/phylo/` 与 `/phylo/molecular/` 合成一张
  「Virus Phylogeny」，卡内放**两个显式子链接**（各带一个数字：`48 fam · 2,684 spp` / `38 trees · 3,341 seqs`）。
- 外层由 `<a class="card">` 改成 **`<div class="card">`** —— **HTML 不允许 `a` 套 `a`**，
  否则浏览器会把内层 `<a>` 拆出去。已确认站内**没有任何 JS 绑定 `.card`**（只有 hero 的 `site_stats.json`）。
- 新增 `.card .sub` 样式（药丸式链接 + `→` 用 CSS `::after`，不占 i18n 文本）。
  两个子链接的标签用 `data-i18n` 译成「分类学树 / ICTV 分子树」；
  **数字放在 `<em>` 里**，因为 i18n 是 `el.textContent = ...`，会**清掉子元素** ——
  所以 `data-i18n` 只能挂在**只含文本的 `<span>`** 上，不能挂在 `<a>` 上。
- 卡描述里原本重复了子链接已给出的数字，已删掉冗余。
- **CRLF 保住了**：`docs/index.html` 是纯 CRLF，改动用 Python 按 `\r\n` 切行、改完拼回，
  并断言 `CR == LF`。行数 101 → 100（删掉一行卡），CR 100 → **99**。
  md5 `bb89fa9beb8b0083aea1557b13624ae5`（11,902 B）→ **`a1dad428aea62e68f76a21f33c5c7e11`（12,524 B）**。

### 5. 文档同步
- `docs/README.md`：路由表与文件结构里的 `3,904 条序列` / `3,904 末端, ~267 KB` → **`3,341` / `~265 KB`**。
- `docs/phylo/README.md`：表头去掉「线上页面暂仍显示旧版 3,904」的过时括注；
  M4 第 0 条改为**已重新生成并上线**；M4 第 1 条把「可能是…也可能是…」升级为**已向官网复核**的结论。
- 历史条目（`[2026-09-22b]` / `[2026-09-22d]` / `[2026-09-22e]`）里「尚未重新生成」的表述**故意不动** —— 那是当时的事实快照。

### Verification
- **几何验收**（`work/verify_phylogram_edges.py`）：发布版 4 棵树全部 **0 交叉**，反向对照 **45 交叉** → PASS。
- **数据差分**（`work/diff_molecular_regen.py`）：变化的科 = {Metaviridae, Phenuiviridae, Pseudoviridae} = 预期，**PASS**；
  树集合无增减 **PASS**；35 棵结构哈希不变。
- **产物自洽**：`molecular_trees.json` 的 `leavesTotal` = `family_index.json` 的 `meta.leaves` = 逐科加总 = **3,341**，三者一致 PASS。
- **首页真浏览器验收**（`work/verify_index_merge.py`，15/15 PASS，1440×1000）：
  Analysis Tools 6 张卡 / 子链接恰好 2 个且 href 正确 / 两个子链接有非零尺寸且上下排布 /
  `/phylo/` 与 `/phylo/molecular/` 均 HTTP 200 / 中文态标题「病毒进化关系」+ 标签「分类学树」「ICTV 分子树」/
  分子页 chips `25 科 / 38 棵 / 3,341 序列` / 按科索引页 200 且 25 张卡 / **无 JS 报错、无 4xx**。
  - 唯一的 404 是 `/reference/data/site_stats.json` —— 该文件**由服务器端定时生成、本机没有**；
    已实测线上 **HTTP 200 / 185 B**（`"generated": "2026-09-22 05:30"`），故**不是本次改动引入的**，
    已在脚本里按已知项排除并注明。

### Files changed
| 文件 | 变化 |
|:---|:---|
| `docs/phylo/molecular/index.html` | 画边折点顺序（1 行）+ 说明注释 → md5 `c25d96c73dd30a777e5f7165c6463fb3` |
| `docs/phylo/molecular_trees.json` | 重生成，3,904 → 3,341 叶 → md5 `fe9f7367694dc1ed925623991ec1fb0c` |
| `docs/phylo/molecular/families/family_index.json` | 同步重生成 → md5 `8134e8f4845d9ad9d2d7e645a3b13b5a` |
| `docs/index.html` | 两卡合并为一张（7→6）+ `.card .sub` 样式 → md5 `a1dad428aea62e68f76a21f33c5c7e11` |
| `docs/README.md` | 两处计数 3,904 → 3,341 → md5 `a1acede1253f06e0bccc842841ef2936` |
| `docs/phylo/README.md` | 去掉过时括注、M4 第 0/1 条更新 → md5 `1f643a11fc7270b9d59419149c750882` |
| `docs/phylo/work/{check_phylogram_crossings,verify_phylogram_edges,diff_molecular_regen,patch_index_merge_phylo,verify_index_merge}.py` | 新增诊断/验收脚本 |

### 未做（等老师定）
- Metaviridae / Pseudoviridae 的**重复树**：本页照实呈现，**未删改**。是否要在页面上加注、
  或向 ICTV 报告，属口径决定。
- `build_family_index.py` 的 `ACC_RE` 仍匹配不到 `NC_018616` 这类带下划线的 RefSeq 登录号（未改，先报告）。
- 首页合并**只做了方案 A**；把两张页面真正合成一个（方案 C/D）未做 —— 两者渲染引擎与控制项完全不同，
  且「章节插图 vs 全科物种树」的口径风险更高。


## [2026-09-22i] — `/phylo/` 新增「非植物病毒」开关，默认只显示植物病毒

### 需求
「非植物病毒科支持切换显示和不显示，默认不显示。」
（补充说明：「…我们之前也展示了非植物病毒的科属，注意这些非病毒科是因为和植物病毒**同目或者同科**才展示的，
但是灰色节点显示不支持展开，现在我想补充一个开关，是否展示这些非植物病毒的科属，现在默认不展示。」）

### 先澄清一个口径（实测，不是推断）
**初版** `taxonomy_tree.json` 里 **没有 `pc == 0` 的科或属** —— `build_taxonomy.py` 的 `prune()`
对科、属两级要求 `pc > 0`，无植物种的科/属在**构建期**就被剪掉了。
所以当时页面上的灰色节点实际落在**域/界/门/纲/目**五级，共 **148** 个（深度=科时可见）：

| 层级 | 域 | 界 | 门 | 纲 | 目 | 科 | 属 | 种 |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|
| `pc == 0`（初版） | 8 | 8 | 15 | 34 | 83 | **0** | **0** | 232 |
| 该层总数 | 10 | 11 | 22 | 50 | 105 | 48 | 214 | 2,916 |

而且它们**全是死端**：83 个 `pc == 0` 的目 `children` 为空（构建期在目级停止展开），
这正是「灰色节点不支持展开」的原因 —— 开关打开后依然展不开，属设计如此。

### 同日后续（口径调整）：把「与植物病毒同目」的非植物科加回数据
老师选定口径：**「只加回『与植物病毒同目』的非植物科」**。
`prune()` 的科级保留条件由「有植物病毒种」放宽为「有植物病毒种 **或** 父节点是含植物病毒的**目**」。

**为什么必须限定父节点是「目」，而不是宽松的「父节点 `pc > 0`」**：MSL41 里 **5,263 条记录没有 Order**，
`build_tree()` 会跳过缺失层级把科直接挂到最近的已知层 —— `Caudoviricetes`（**纲**）下直接挂了
91 个噬菌体科、根 `Viruses` 下直接挂了 25 个古菌噬菌体科。若按宽松口径保留，那 25 个会作为灰色科
出现在**域那一层**（根的其他子节点全是 realm），既不是「同目」，视觉上也会误导。
**实测：严格口径 +73 个科；宽松口径 +195 个。**

- **净变化 +73 个节点，全部是 `family`，0 个删除**；域/界/门/纲/目/属/种 各层 ±0。
- 73 个新科分布在 **20 个混合目**：`Ghabrivirales` 17、`Mononegavirales` 10、`Picornavirales` 8、
  `Hareavirales` 7、`Elliovirales` 5、`Hepelivirales` 4、`Durnavirales` 3，其余 13 个目各 1–2 个。
- 它们**全是灰色叶节点**（`pc == 0` 且无 `children`）—— 本库没有它们的属/种，所以**看得到、展不开**。
- **植物病毒分支逐字节不变**：新旧树 `json.dumps(tree, sort_keys=True)` 相等；
  `data/plant_taxa.tsv` 也逐字节相同（md5 `504695ef8b940cb93fc53197fc173eb9`）—— 植物判定逻辑未动。
- **默认态仍恰好 2,997 个节点**（`3,450 − 453 = 2,997`）。
- `taxonomy_tree.json`：300,764 B / md5 `9861f07be032c09dd523686eea0f8ae6`
  → **304,890 B / md5 `c1c7dae44309e3ca44f44f4e8efa1b27`**。
  该文件**不在 git 里**（`git ls-files --error-unmatch` 报 untracked），
  所以覆盖前把旧版存到 `docs/phylo/.tmp_live/taxonomy_tree.old.json` 作为回滚源。

### Changed
- **`docs/phylo/index.html`**
  - DISPLAY 区的复选框由 `Non-plant backbone`（**默认勾选**）改为 `非植物病毒 / Non-plant viruses`（**默认不勾选**）。
  - 旧版 `stripGrey()` 只裁 `rank > family` 的 `pc == 0` 节点 —— 也就是**只删掉 232 个非植物种**，
    灰色骨架（域/界/门/纲/目）**根本没被删**，所以那个勾选框看上去几乎没效果。
    现改为**把所有 `pc == 0` 节点从树上摘除**：默认 2,997 节点 / 勾选后 3,450 节点。
  - 实现方式是**就地摘除 + `STASH` 记 `{parent,index,child}`**，而不是每次渲染克隆裁剪树。
    原因：ECharts 的 tree 展开/折叠**直接改数据对象上的 `collapsed`**，传克隆树会让展开状态
    在下次 `render()` 时丢失（旧版 `stripGrey` 每次 `buildOption()` 都克隆，正是这个毛病）。
    放回时**倒序 `splice`**，索引才与摘除前一致。
  - `render()` 的 clear 判据由「只看 `layout`」扩展为「`layout` 或非植物病毒可见性」——
    该开关同样增删节点与边，属结构性变化。
  - 顶栏 `taxa shown` 改为随开关动态更新（此前只算一次，隐藏后仍显示全量节点数）。
  - `btnReset` 一并置为不勾选；`applyUrlParams` 接受 `gray=1`（显示）与 `gray=0`（不显示）。
  - **搜索非植物节点时自动勾上开关** —— 否则 `expandTo()` 在树上找不到节点，用户搜了却什么都没发生。

### Added
- `docs/phylo/work/ui_regression_layout.py` 扩展为覆盖两类结构性切换：
  新增 **C5**（点开 == 一开始就勾选）、**C6**（点关 == 默认态）、**C7**（切 5 轮不累积），
  外加 **C8 反向对照**（默认 vs 打开必须有 >1% 变化），并加入**数值判据**
  （可见 99/320 节点、全树 2,997/3,450、顶栏计数）。
  数据加回 73 个科后，`EXP_SHOWN` 同步更新为 `{'vis': 320, 'all': 3450, 'chip': '3,450'}` 并**重跑通过**。
  另外补了 `patch_showgray_default()` —— 用 `page.route` 改写 HTML 造出「一开始就勾选」的参照页，
  并**断言补丁目标存在**（找不到就报错，而不是静默返回原 HTML 让对照项变成假通过）。

### Verification（真浏览器实测）
| 检查 | 结果 |
|:---|:---|
| C1 orthogonal→Circular vs 干净径向 | 0.0000% ✓ |
| C2 radial→Rectangular vs 干净正交 | 0.0000% ✓ |
| C3 切 3 轮后停在径向 vs 干净径向 | 0.0000% ✓ |
| C4 深度 Family→Species（反向对照） | 10.24% ✓ |
| C5 点开 vs 干净显示态 | **0.0000%** ✓；数值 320 / 3,450 / 3,450 ✓ |
| C6 点关 vs 默认隐藏态 | **0.0000%** ✓；数值 99 / 2,997 / 2,997 ✓ |
| C7 开关切 5 轮后回到关闭 vs 默认 | **0.0000%** ✓ |
| C8 默认 vs 打开（反向对照） | 16.88% ✓ |
| A/A 基线（同样输入两次） | 0 个差异像素 → 渲染确定性，0.0032% 不是噪声 |
| `?gray=1` / `?gray=0` / 无参数 | 3,450 / 2,997 / 2,997 ✓ |
| 搜索 `Ligamenvirales`（非植物死端目） | 自动勾选并打开详情面板 ✓ |
| Reset 按钮 | 回到不勾选 / 2,997 ✓ |
| 中文界面 label / hint | 「非植物病毒」/ 提示已替换 ✓ |
| **加回 73 个科后整套重跑** | **8/8 PASS**，C5/C6/C7 均 0.0000% ✓ |
| **部署后线上复核**（HTTP + 真浏览器） | 服务器 md5 == 本地；默认 2,997 / 打开 3,450；开关两态 0.0000% ✓ |

> **判据陷阱（已排除）**：开关是**原生 checkbox**，点过之后带悬停高亮，会让**它自己那 15×15 像素**
> 变化（坐标 35..49 × 332..346，正好等于 `getBoundingClientRect()`），而画布**逐像素一致**。
> 用 `elementFromPoint` 反查确认后，凡涉及该开关的检查项一律**裁到画布区域**再比 ——
> 裁切后差异为**精确的 0.0000%**。

### 未做
- 非植物病毒的**属**没有加回数据（属级仍一律要求 `pc > 0`）；**混合目之外**的非植物科也没有加回。
  本次只按老师选的口径加回「与植物病毒同目」的非植物科（73 个）。
- 这 73 个科**在页面上仍是展不开的灰色叶节点** —— 本库没有它们的属/种，属数据边界、不是 bug。
- `ui_regression_layout.py` 仍未接入 CI / nginx 检查，需手动跑。

## [2026-09-22g] — `/phylo/` 切「圆形」后残留矩形树：ECharts tree 是增量更新

### 现象
在 `/phylo/` 点 Circular，画布上除了圆环树，**还叠着一棵矩形树**（长横枝 + 末端短竖线）。

### 根因（真浏览器逐层验证，非推断）
不是 CSS、不是缓存、也不是"两棵树的 DOM"（全页只有 1 个 canvas、1 个 echarts 实例、1 个 series）。
真正原因是 **ECharts 的 `tree` 视图是增量更新**：只改 `layout` 再
`setOption(..., {notMerge: true})` 时，正交布局下**已存在的边不会重建**，
而是保留旧的 orthogonal 形状（`shape` 里带 `parentPoint` / `childPoints` / `forkPosition`）。

实测证据链：
1. 切到径向后的 `displayList` 里 **247 条边中有 114 条仍是 orthogonal 形状**
   （shape key 为 `childPoints,forkPosition,orient,parentPoint`）。
2. 让页面**从不渲染正交**（改 HTML 默认高亮按钮）再对比：
   切换得到的图与"干净径向"相差 **1.0042%** 像素；从不渲染正交则 0%。
3. `zr.refresh()` / `refreshImmediately()` 强制全量重绘后差异 **0.0000%**
   → 说明不是位图残留，而是图形本身被这样画出来的。

### Fixed
- **`docs/phylo/index.html`** `render()`：检测到布局变化时先 `CHART.clear()`。
  只在布局变化时清，避免影响深度/配色等其他控件的行为。
  ```js
  var lay = document.getElementById('mRadial').classList.contains('on') ? 'radial' : 'orthogonal';
  if (LAST_LAYOUT !== null && LAST_LAYOUT !== lay) CHART.clear();
  LAST_LAYOUT = lay;
  CHART.setOption(buildOption(), { notMerge: true });
  ```

### Added
- **`docs/phylo/work/ui_regression_layout.py`**：可重跑的回归测试（自带本地服务，无浏览器时 SKIP）。
  判据不靠肉眼，而是**与"该布局单独渲染"逐像素比较**：
  C1 orthogonal→Circular、C2 radial→Rectangular、C3 反复切 3 轮后停在径向 —— 三条都必须 **0.0000%**；
  另加 **C4 反向对照**：改非布局控件（深度 Family→Species）**必须**有 >1% 变化，
  否则前三条会因为"两边都是静止画面"而假通过。

### Verification（全部实测）
| 检查 | 结果 |
|:---|:---|
| C1 orthogonal→Circular vs 干净径向 | **0.0000%** ✓ |
| C2 radial→Rectangular vs 干净正交 | **0.0000%** ✓ |
| C3 切 3 轮后停在径向 vs 干净径向 | **0.0000%** ✓ |
| C4 深度 Family→Species（反向对照） | 13.68% ✓ 有变化 |
| 回归：关/开"按科着色" | 0.35% / 0.012% ✓ |
| 全页 canvas / echarts 实例 / series 数 | 1 / 1 / 1（排除"两棵树"假设） |

### 未做
- 该页未纳入 nginx 部署流程的自动检查；`ui_regression_layout.py` 需手动跑（或接进 CI）。

## [2026-09-22h] — `/network/` 视觉验收二轮：详情面板的横条、被圆啃掉的标签、被卡片切开的控件

接上一轮的 7 张截图门（`documents:visual-judge`）。本轮门 9 张图里 3 张挂在同一个缺陷上，
另有 2 个只看代码没发现的缺陷由量具量出来。

### 现象一：详情面板里每个邻居的权重横条**一模一样长**
同一节点的「邻居与共同序列数」列表里，横条粗细毫无差别 —— 那排 `.barwrap > i` 全是
`style="width:NaN%"`。CSS 解析不了 `NaN%`，当成空串丢掉，于是 `width` 落到默认 `auto`，
而容器是定宽 52px 的，每根条都被拉满。

根因（不是样式问题，是分子分母不是同一个变量）：
`rowsHtmlOf(rows, maxNb)` 里按**参数** `maxNb` 算宽度，而唯一的调用方根本不传第二个参数。
`const mx = maxNb || Math.max(1, ...rows.map(r => r[1]))` 救了场却没人用 —— `maxNb` 为
`undefined` 时 `100 * w / undefined` 得到 `NaN`。修复后按 `mx` 算（`rows` 已按权重降序，
`mx` 即该节点的全局最大权重），量到的宽度从「全 52px」变成有区分度的
100 / 85 / 28 / 8 %（Dioscoreaceae）与 100 / 2 / 1 / 0 %（Allexivirus）。

### 现象二：标签被大圆啃成半个名字
默认视图里有个宿主名被啃成 `Clayto…`（原文 Clytostomaceae 一类）。标签高 13.5px，
一个 12px 名字的圆只要盖住 12% 就能啃掉一两个字 —— 盖圆阈值 `LBL_HUB_COVER` 原为 **0.20**，
挡不住这种。

阈值扫到 **0.10**。`coverFrac` 量的是几何重叠，与「谁画在上面」无关（圆后画啃标签、标签
后画糊住圆，两种都得拦），所以这个数同时管两个方向。判据是「改完之后有没有变少」：
用 `thcut.js` 把贪心算法在冻结的几何上按 `[0.20, 0.10, 0.05, 0.02, 0]` 五档重放（只切
`el.invisible`，不动布局，一次运行拿到五个阈值的反事实），九个状态轮次的结论是
**可见标签数、value 前 25 / 50 的带标签节点数在 0.20 与 0.10 两档完全一致，一个都没少，
而啃咬上限减半**。量具 `accept.js` 改为直接读页面常量 `LBL_HUB_COVER / LBL_HUB_R`，
两边不会再各自漂移。

### 现象三：tab2 侧栏最后那个控件被卡片底边切成两半
`documents:visual-judge` 的 g4 / g5 / g7 三张图同一条：侧栏白卡的圆角底边把
「节点标签 前 70」下拉框拦腰截断，看着像渲染坏了。实测是内容真超了：
tab1 侧栏 444px、tab2 **640px**，而 1600×960 下只给 697px、1366×768 只给 505px。

四处调整（都在 `docs/network/index.html`）：
- **标签档位移到图表页头**（PNG/CSV/重置 左边）：它决定的是「画布上出现多少名字」，
  和那几个按钮同属视图开关，本来就不该躲在筛选卡里；两个标签页都因此永远可见。
- **6 个传毒机制改两列**：全名最长 49 字符，竖排吃掉 200px 以上；两列后仍显示完整名字。
- **阶元行 / 权重+TopN / 斥力+连线长度 各改同行并排**：阶元行的标题原先单独占一行。
- **`@media(max-height:910px)` 改整页滚动**：910 是实测临界点（可给高度 ≈ 视口高 − 263，
  tab2 需 640）—— 低于它再锁一屏必然切控件，改成页面滚动则所有控件靠页滚到达。
  滚动条同时改为可见（`scrollbar-width:thin` + 自定义 thumb），矮视口下侧栏真要滚时
  读起来是「可以滚」而不是「坏了」。

### 现象四：两层下钻没有证据
`shots.py` 的 g3 只做到「双击聚焦」，面包屑只有一级，看不出层层递进。补了第二步：
点一个邻居再走一层，面包屑变成两级（本地轮次 `Potyvirus › Alstroemeriaceae`，
上线后端到端复测 `Potyvirus › Caryophyllaceae`）。

### 实测否决（这四个方向都不是路，留在记录里省得再走一遍）
- **标签挪位置**：display-list 里给 `it.x = it.x - 80` **赋值是成功的**（324.88 → 244.88），
  但量出来的矩形纹丝不动 —— `el.updateTransform()` + `zr.refreshImmediately()` 之后
  `par.getComputedTransform()` 依旧原值；直接改 `it.transform[4]` 无效；去戳 tspan 的
  `style.x/y` 会让该元素直接从 `chartLabels()` 里消失（`lr.y + 6.75 ≈ 0 / lr.height == 13.5`
  的恒等式过滤器把它当空元素剔掉）。加上此前已否决的环形摆放与 `moveOverlap:'shiftY'`
  （允许挪位后 ECharts 反而不隐藏，重叠对从 9 涨到 43），标签位置这一维是**关闭的**：
  只能在「显示/隐藏」与阈值上做文章。
- **改绘制顺序让标签压过圆**：`zr.storage.getDisplayList()` 返回的是**非活数组**，
  把 tspan 挪到末尾，下一次重绘就被还原（`after1Idx` 与 `beforeOrder` 完全相同）。
- **`window.__dbg.select`**：不存在，ECharts 也不收合成的 `zr.handler.dispatch('click')`
  （派发后 `st.sel` 仍为 null）。自动化只能用真鼠标点 `sym.transform[4]/[5]`，且每次点之前
  要等够 600ms 把 `deferClick` 的 240ms 定时器放空。

### Verification
- **8 个状态量具全过**（双标签 × 中英 × 标签 前70/全显）：A 标签互撞 **0**、
  B 盖枢纽圆 >0.10 **0**、C 出画布 **0**，无 JS 报错。各状态可见标签 14–82 个。
- **侧栏裁剪探针 6/6 视口零裁剪**（1600×960 / 1440×900 / 1366×768 / 1280×800 × 双标签）：
  判据不是「滚动高度小于客户高度」（那只会把问题挪到别的视口），而是**逐个控件判有没有被
  卡片底边切成半截**。
- **功能回归**：模式筛选 6 个勾选框（360 → 180 → 27 → 0 → 恢复 360，空选出空图提示）、
  标签档位移到页头后换档仍驱动重绘、中英切换后控件原位重画且档位不丢。
- **视觉门**：`documents:visual-judge` 5/5 通过（tab2 中文 *2 / tab2 英文 / 1366×768 整页滚动态 / tab1 中文），
  页头「节点标签 [前 70] PNG CSV 重置」两个语言都在一行且不压标题。
- **部署后端到端**：`http://39.106.101.94/network/` 实载，双标签 426 / 360 节点，
  双击下钻 + 点邻居走一步得到两级面包屑，无 JS 报错、无失败请求。
  `index.html` 与 `network.json` 两端 MD5 逐字节一致（`d159d982…` / `c77251e7…`），
  服务器侧留 `*.bak_pre022h_20260922`；**服务器 `docs/i18n.js` 为 v4，未动**。
- **顺手修 `docs/sitemap.xml`**（与 `/network/` 同批上线）：原来指着两个 404 的
  `/rdp/`、`/phylogeography/`，换成实际在线的 `/network/`、`/association/`、`/phylo/`，
  全表 18 条（逐条 curl 均为 200）。服务器侧先备份再改，改完 XML 可解析、`/sitemap.xml` 200（1093B），
  三条新 loc 逐条 200、两条旧 loc 确认 404（备份 `sitemap.xml.bak_20260922`）。

## [2026-09-22f] — 把「ICTV 用保守区」从 1 个科推广到 19 个科（并纠正自己写错的数）

### Added
- **`docs/phylo/work/measure_ictv_aligns.py`**: 量 ICTV 官方比对"到底用了多大区域"的只读脚本。
  逐条读 `manifest.json` 的 `kind:"align"`（42 条），输出序列数 / 列数 / 每条去间隙长度 /
  间隙率 / 类型（核苷酸 or 蛋白）/ 占该科完整基因组的比例。产物 `work/ictv_align_survey.md`
  由脚本生成（文件头写明"请勿手改，改脚本重跑"）。
- **补下 19 个 ICTV 官方比对文件**（此前因 `kind:"align"` 条目**没有 `local` 字段**而全部漏下）：
  12 个科 / 19 条，落在 `docs/phylo/ictv_raw/<Family>/`。
- **`docs/phylo/work/derive_region_coords.py`**: 从 ICTV 自己的比对**反推保守区坐标**的只读脚本，
  解决 M9 第 ① 步"本地库没有 CDS 坐标、不知道截哪一段"的卡点。
  产物 `work/region_coords_Caulimoviridae.md`。

### 关键结果：结论从"个案"升级为"普遍做法"，而且表述被修正了一次
- **10/19 是氨基酸（蛋白）比对**，9/19 是核苷酸；核苷酸那些只覆盖基因组的 **7–54%**。
- **判据可自证**：按 A/C/G/T/U 占比分类，结果**完全双峰** ——
  核苷酸一律 **100.0%**、蛋白 **17.4–27.3%**，中间零样本。所以这不是主观判断。
- 文件名直接写着区域：`Replicase.aa`、`Capsid.aa`、`RdRP`、`CP`。
- 间隙率中位 **26.6%**，而本库全长比对是 **70.4%**。
- **反例（防止把结论说过头）**：Potyviridae Fig3 是 **3,084 aa 的多聚蛋白全长** ——
  208 条里 **GDD 聚合酶催化基序 208/208 全有**、KITC（HC-Pro）64/208，
  3,084×3 = 9,252 nt ≈ 该科完整基因组中位 9,736 nt 的 **95%**。
  所以准确表述是「ICTV 比对**同源编码区**（常以氨基酸形式），不喂全长核苷酸」，
  **而不是**「只取一小段保守区」。配方要**按科分别定**。

### 关键结果 2：保守区坐标**取得到**（原以为卡住的问题）
- 方法：ICTV 比对里每条序列本就是它从全长上**截下来的那一段** →
  去间隙后在库内对应全长上做**精确子串匹配**，区间即坐标。不需要任何注释文件。

| 科 | 命中 | 区间中位 | 占全长 | 起点范围 |
|:--|--:|--:|:--|:--|
| Caulimoviridae Fig4 | **104 / 108** | 1,227 bp | **16.2%**（12.1–19.0%） | 2,728 – 7,050 |
| Virgaviridae Fig3 | **54 / 57** | 466 bp | **7.3%**（6.8–31.2%） | 90 – 6,126 |
| Geminiviridae Fig3 | 19 / 29 | 2,861 bp | **100.0%** | 1 – 1 |

- **不能全科硬编码一个坐标窗口**：Caulimoviridae 起点范围 2,728–7,050，
  都落在 ~16% 但绝对坐标差异大 → 必须**逐条推导**。
- **Geminiviridae 是反例**：ICTV 那里用的是**全长组件**（区间 100%）。
  再次说明"取哪个区域按科定，没有通用规则"。
- 已知限制：按登录号查找漏掉"ICTV 用原始 GenBank 号、本库是 RefSeq"的情形
  （Geminiviridae 9/29 未匹配，如 `X15656` vs `NC_*`）。未补物种名模糊匹配。

### Fixed — 更正我自己上一版写错的数字，以及本次新写的两个 bug
- 上一版（`[2026-09-22e]`）记的 Caulimoviridae 比对「每条 **1,194–1,227 bp**、占基因组 **15–17%**」
  **是错的**：1,227 是**中位数**，被误当成了上界，于是区间被压成"中位数上下 3%"这种不合常理的样子。
  逐条重算（108 条全部 1,674 列；去 `-`/`.` 后 **1,158–1,512**，中位 1,227；文件内无 `?`）后
  真值为 **16–21%**。已在 4 处同步更正：本文件 `[2026-09-22e]` 节、`docs/phylo/README.md`、
  `docs/phylo/work/REPRODUCE.md` §8.1、`docs/phylo/work/lenprobe_result.md`。
- **`measure_ictv_aligns.py` 第一版的类型判据是错的**：用"是否出现 `RYSW`"判核苷酸 ——
  但这些既是 IUPAC 简并码（R=A/G、Y=C/T、S=G/C、W=A/T）又是蛋白里的 Arg/Tyr/Ser/Trp，
  Caulimoviridae / Nanoviridae / Virgaviridae Fig6 被误判成 `other(RY)` 之类。
  改为"只有蛋白才有的字母（`EFILPQZJOX`）+ A/C/G/T/U 占比 ≥0.85"两步判据。
- **`derive_region_coords.py` 的未命中分类是错的**：把"名字里没有登录号"和
  "有登录号但库内没有"合并成一类，于是 `Epiphyllum_mottle-associated_virus_(MH396440)`
  这种明显带登录号的名字被报成"抽不到登录号"。改为**四类分列**（命中 / 匹配不上 /
  库内无 / 无登录号），并加 `assert` 保证四类之和 = 总数 ——
  这个 `assert` 立刻又抓出我自己漏算的一类（104+3+0≠108）。
- 删掉 `derive_region_coords.py` 里一行死代码（`lens = [seqs[h[1]] and len(...)]`）。

### Verification
- `measure_ictv_aligns.py` 可重跑，产物 md 由脚本生成 → 数字可独立复核。
- 分类判据自证：ACGT 占比双峰、零重叠（见上）。
- Potyviridae"多聚蛋白"由**基序存在性**验证（GDD 208/208），不是靠长度猜的。
- `derive_region_coords.py` 的计数由 `assert` 保证平账；三个科实跑均通过
  （104+1+3=108；54+3=57；19+9+1=29）。
- 坐标推导用的是**精确子串匹配**（ICTV 自己就是截的），因此结果不存在比对误差。
- 全部 11 个 Python 脚本通过 `ast.parse`；CHANGELOG 标题有序完整。

### 未做（等老师定）
- 23 条比对仍未下载（Rhabdoviridae 6、Benyviridae 3、Konkoviridae 2、Botourmiaviridae 2、
  Aspiviridae 2，其余 8 个科各 1）—— 与建树计划无关，按需再下。
- `derive_region_coords.py` 未加"按物种名模糊匹配"的兜底，所以非 RefSeq 登录号的条目会漏。
- 仍**未重新生成**线上 `docs/phylo/molecular_trees.json`（解析修复已在源码里，产物仍含 563 个幽灵叶）。

## [2026-09-22e] — 自建树试点跑通：管线对了，但**输入区域选错了**

### Added
- **`docs/phylo/check_tree.py`**: 自建树体检工具（只读，退出码 0/1）—— 结构统计（含负枝长告警）+
  **属的单系性**（可证伪判据）+ 与 ICTV 已发表树对拍（按登录号取交集比非平凡枝）。
  两道护栏：只对**有属名**的叶判单系性；映射率 <50% 时明确声明"本条不作判据"。
- `docs/phylo/work/Caulimoviridae.trim.{treefile,contree,splits.nex,svg,png}` + `wsl_trim_build.log`：
  第一棵跑通的自建树及其渲染图。
- `docs/phylo/ictv_raw/Caulimoviridae/ORTD.Caulimo.Fig4.v9_align.txt`（185,517 字节）：
  ICTV 该科树的**背后比对**。当初漏下 —— `manifest.json` 里比对条目**没有 `local` 字段**。

### 实测：全链路跑通（WSL Ubuntu-24.04 / 20 核 / 31 GB）

| 步骤 | 结果 |
|:---|:---|
| MAFFT `--auto --thread 20` | rc=0，峰值 RSS **12.4 GB**，墙钟 **10:55**，比对 26,163 列 / **70.4% 间隙** |
| `trimal -gappyout` / `-automated1` | 5,231 列 / 8.8% 间隙；3,955 列 / 7.6% 间隙 |
| IQ-TREE `-m MFP -B 1000 --seed 42 -T 20` | 最佳模型 **GTR+F+R8**；总墙钟 **40m14s**，CPU 13h07m |
| 最终树 | BEST SCORE −317610.720，总枝长 50.439，105 taxa / 369 splits，支持度 102/103 有值（23 个 <95） |
| `check_tree.py` | 属单系性 **5/7 = 71.4%**，退出码 0 |

### 关键更正：ICTV 用保守区，我们用全长（**推翻上一版的"内存墙"归因**）
- ICTV Fig4 的比对：**108 条 / 1,674 列 / 每条去间隙 1,158–1,512 bp（中位 1,227）/ 间隙率 26.6%**，
  只占全长基因组 **16–21%**（定位在全长第 ~5,500–6,700 bp，与 ORF3 的 RT/RNaseH 区相符）。
  本试点用的是 6,450–9,872 bp 全长 → 26,163 列 / 70.4% 间隙。
  > **勘误（2026-09-22 当晚复核）**：本节初稿把每条长度写成「1,194–1,227 bp」、占比写成「15–17%」，
  > 是**错的** —— 1,227 是**中位数**，被误当成了上界。逐条重算后真值如上（最短 1,158、最长 1,512）。
  > 用 `work/measure_ictv_aligns.py` 可复核。
- **推广到 19 个科（同批实测）**：ICTV 的比对**根本不是全长基因组** ——
  **10/19 是氨基酸（蛋白）比对**，9/19 是核苷酸；核苷酸的那些覆盖基因组的 **7–54%**。
  文件名本身就写着区域：`Replicase.aa`、`Capsid.aa`、`RdRP`、`CP`。
  间隙率中位 **26.6%**，而本库全长比对是 **70.4%** —— 这是"硬把不同区域拼在一起"的典型症状。
  详见 `work/ictv_align_survey.md`。
- **可证伪的判据**：两棵树共有的 12 条叶里 8 条是 Badnavirus ——
  在 **ICTV Fig4 里是干净的单系枝（8 条，零混入）**，在**本树里不是单系（最小包含枝 = 全部 12 条）**。
  两棵树在同一命题上直接冲突，ICTV 那棵与分类一致。
- 根因定位到本树的根是**三叉**：`DQ822073.1_Badnavirus_etadioscoreae` 单独落在最基部
  （+ 101 叶大枝 + 3 条 `dioscoreae` 类），使 Badnavirus 成为多系。
- **换成 1.2 kb 后内存墙消失**（105 条各截到 1,200 bp 实测）：
  2 线程 **269 MB / 26 s**、20 线程 **965 MB / 12.5 s** —— 对比全长的 2.93 GB / 12.4 GB。
  **那台 2 核 3.5 GB 的服务器完全跑得动；"必须换机器"是输入选错造成的假象。**

### Fixed
- `docs/phylo/README.md` M4：按修复后的解析口径重算全部数字（详见 `[2026-09-22d]`）——
  叶总数 3,904 → **3,341**、严格二分叉 33/38 → **36/38**、占位符占比 1.5% → **1.74%**、
  「4 棵树没有支持度」更正为「3 棵有但被丢了 + Secoviridae 真的没有」、
  「1,863 占 48%」→ **55.8%**（分子不变，分母更正）。
- `docs/phylo/README.md`：`render_tree_svg.py` 的几何校验原写
  「竖枝 27 + 横枝 55 = 82 = 56 − 1」—— **82 ≠ 55，恒等式是错的**。
  正确的三条：叶圆点数 = 叶数、竖枝数 = 内部节点数、横枝数 = 节点总数 − 1。
- `docs/phylo/work/REPRODUCE.md`：补第 8 节（输入区域选错的决定性证据），
  并修订第 3 节参数、第 6 节路径、第 7 节复现命令与验收基线。

### 数据核查
- `build_family_index.py` 的 `ACC_RE = [A-Z]{2,3}[0-9]{5,6}` 要求字母后**直接**跟数字，
  **匹配不到 `NC_018616` 这类带下划线的 RefSeq 登录号** —— 该页的登录号计数天然偏低。
  （未修改，先报告。）
- 线上产物 `docs/phylo/molecular_trees.json` **仍未重新生成**，仍是含 563 个空叶的旧版。

### Verification
- `check_tree.py` 自检：`--tree X --ref X` → 非平凡枝 Jaccard **100.0%**。
- 健壮性：38 棵 ICTV 树 × {无 manifest, 有 manifest} 共 76 次调用，**全部退出码 0，零崩溃**。
- `render_tree_svg.py` 回归：改完 `split_parts` 后重跑 Geminiviridae Fig3，
  leaves 29 / internals 27 / maxDegree 3 / blMax 0.639139 / supportN 26 —— **5/5 与记录值一致**。
- 新树几何自洽：叶圆点 105 = 叶数；竖枝 103 = 内部节点数；横枝 207 = 208 − 1；
  红色支持度标签 23 = 支持度 <95 的节点数。
- 视觉确认：无头 Chrome 截图 `work/Caulimoviridae.trim.png`（238 KB），
  肉眼可见 Caulimovirus 单系成枝、支持度标签位置正确。

### 未做（等老师定）
- 建树范围（哪些科 / 长度窗口 / 修剪口径）、保守区的取法、线上 JSON 是否重新生成。



## [2026-09-22d] — Newick 解析双 bug（线上 3 个科的树被污染）

### Added
- **`docs/phylo/check_tree.py`**: 自建树体检工具（只读）。详细说明见本日 `[2026-09-22e]` 条目。

### Fixed
- **`docs/phylo/build_molecular.py` 方括号注释会凭空多造一个空叶**（**线上数据已受影响**）。
  `_subtree()` 的子节点循环里遇到 `[` 是 `_skip_comment(); continue`，而 `_read_length()`
  读到 `[` 就停，于是 `continue` 回到循环开头等于**又解析了一个子树**；此刻光标停在 `,` 上，
  `_read_label()` 读出空串 → 多出一个无名、无枝长的空叶。ICTV 有 3 个科的树把支持度写在
  方括号里（`):0.11091[1000],`），空叶数恰好等于 `[` 个数：

  | 科 | 文件 | `[` 数 | 线上叶数 | 正确叶数 |
  |:---|---:|---:|---:|---:|
  | Metaviridae | `ORTD.Meta.Fig3.v9.treefile.nwk` | 207 | 417 | **210** |
  | Pseudoviridae | `ORTR.Pseudo.Fig3.treefile.nwk` | 207 | 417 | **210** |
  | Phenuiviridae | `ONSR.Phenui.Fig3_.v5_treefile.txt` | 149 | 301 | **152** |

  最小复现：`((A:1,B:2):0.5[1000],C:3):0.2[999];` 旧代码 → 叶 `['A','B','','C']`，修后 `['A','B','C']`。
  修复：跳完注释后**重新判断分隔符**（`,` / `)`），不再造子节点。
- **`docs/phylo/render_tree_svg.py` 把纯数字的叶名当成支持度吞掉**。
  `split_parts()` 对叶也做数值判定，而 ICTV 树里存在纯数字叶名（Metaviridae/Pseudoviridae
  的 `297`、`17.6`、`1731`、`412`，Potyviridae 的 `0.16690164`，共 4+4+1 条），
  被判成支持度后 `name=None`。改为 `split_parts(parts, is_leaf)`：叶的标签一律整串当名字。
  （`build_molecular.py` 无此问题 —— 它只对内部节点调 `split_name_support`。）

### 数据核查（差分，未覆盖线上产物）
- 修复后把 `molecular_trees.json` 重新生成到临时路径做逐科差分：
  **只有 3/38 棵树变化，其余 35 棵结构哈希逐字节不变**；叶总数 **3904 → 3341**
  （差 563 = 207+149+207）；树 ID 集合不变，仍 25 科 38 树。
- **`docs/phylo/molecular_trees.json` 尚未重新生成** —— 线上仍是带缺陷的旧版。
  重新生成会改变已验收页面，按项目约定**等老师确认**。

### Verification
- **双解析器全量对拍**：`build_molecular.parse_newick` vs `render_tree_svg.parse_newick`，
  38 棵 ICTV 树逐棵比「叶集合 + 内部节点数 + 最大度」→ 修复后 **38/38 完全一致**，
  空叶名 **0**。修复前该对拍直接抛 `TypeError: '<' not supported between NoneType and str`。
- 自对拍：`check_tree.py --tree X --ref X` → 非平凡枝 Jaccard **100.0%**（对拍逻辑自洽）。
- 护栏实测：拿只有 12/108 叶有属名的 ICTV 图去测，脚本正确声明「只有 11% 的叶有属名，
  单系率不具代表性 —— 本条不作判据」，退出码 0（第一版误报 `Badnavirus 不单系`，加剪枝后修正）。



### Added
- **`docs/network/`**: 互作网络图谱交互页，两个标签页共用一套力导向图交互
  - **病毒–宿主**：全部植物病毒 ↔ 植物宿主，199,070 条 GenBank accession 聚合为 14,791 个「病毒种 × 宿主叶」关联对（4,820 病毒种 × 3,040 宿主叶），复用 `../association/associations.json`
  - **媒介–病毒–宿主**：1,375 条 VIP-DB 实验验证三元组（447 病毒 × 100 媒介 × 380 宿主、6 类传毒方式、281 个 DOI），媒介作为第二类节点入图，病毒–媒介边可展开显示传毒方式标签
  - **宏观/微观两层视角**：阶元阶梯（病毒/宿主/媒介各自 目→科→属→种）+ Top-N 合并看整体；**双击任意节点下钻到它的自我网络**，点邻居沿网络再走一步，顶部 `🦠 virusA → 🌿 hostB → …` 路径条逐级回退；聚焦态下节点大小改为「占本品类比例」
  - 权重阈值滑块、仅植物宿主开关、媒介传毒方式勾选、别名搜索（缩写 TSWV/CMV… + ICTV 学名，命中直达并高亮）、PNG（2.5×）/TSV 导出、斥力/连线长度实时调节、fit 按包围盒反算缩放并自动收尾、中英双语（复用 i18n.js）。纯静态 + 本地 ECharts，无 CDN 依赖
- **`docs/network/build_network.py`**: 数据构建脚本 — `virus_vector_host.tsv`（VIP-DB 三元组，宿主经 `data/external/taxdump` 解析谱系）+ `associations.json` 聚合，输出 `network.json`（0.64 MB）
- **`docs/network/README.md`**：数据口径（两个口径都不是宿主范围的权威判定）、交互设计、重建与部署说明
- nginx 路由 `/network/`（plant-virus.conf）；`docs/index.html` Analysis Tools 新增入口卡片（17 → 18 张）；`docs/README.md` 路由表与文件结构同步

### Fixed（上线前本地实测，5 个视口 × 20 状态）
- **整页比视口高出一条滚动条、页脚被顶出屏幕**：`body` 用 `min-height:100vh` 只给「至少这么高」，侧栏 `max-height:100%` 拿不到确定高度就不生效，侧栏 816px 的内容把 `.layout` 整行撑开。改为 `height:100vh` 的纵向弹性列 + `min-height:0` 链，画布由 flex 决定高度（实测 1680×1000 / 1600×700 / 1440×620 / 1366×640 / 1280×560 五档 `documentElement.scrollHeight == clientHeight`）
- **矮视口下画布压住页脚**：`#chart{min-height:480px}` 写死，窗口矮时画布被顶着不缩，底部 27px 盖在页脚上还顶出滚动（实测 1440×620 / 1366×640）。改为 `min-height:clamp(0px, calc(100vh - 228px), 480px)`，画布下限跟着剩余高度走
- **搜索下拉被侧栏滚动容器切掉**：下拉留在 `aside.controls`（`overflow-y:auto`）里，视口越矮切得越多——1440×620 下 24 条结果少了 38px，末条点不着。改为 `position:fixed` + 按输入框视口坐标定位，并监听 `scroll`(捕获段)/`resize` 跟随
- **标签互相压字**：密集核心区标签重叠不可读。`labelLayout.hideOverlap` 之外给节点标签加白色描边（`textBorderColor/textBorderWidth`）+ 与节点的 6px 间距。**实测否决 `moveOverlap:'shiftY'`**：允许挪位后 ECharts 就不隐藏了，只错开一点点，重叠对从 9 涨到 43
- **`Q_repulsion` 状态图被推出画布**：斥力滑到 300 时包围盒反算的 zoom 被 `scaleLimit.min=0.2` 夹断，半径又没按 zoom 换算。下限放到 0.01，闭合解改用像素半径

### Verification
- 20 个状态（双标签 × 阶元 × 聚焦 × 走一步 × 面包屑回退 × 详情面板 × 边点击 × 搜索跳转 × 筛选 × 中英切换 × 拖动滑块）全量回归：节点墨水不出画布边缘、面板无内容溢出、无 JS 报错
- 标签重叠用 zrender `tspan` 世界坐标量化：默认阶元 0 对重叠，仅「标签全显」物种级 opt-in 状态有 9 对（已由描边兜底）
- 视觉验收：7 张截图（中文默认态 / 聚焦+详情 / 三元组网络 / 媒介聚焦 / 搜索下拉展开 / 英文态 / 1440×620 矮视口下拉）送 `documents:visual-judge` 门，中文态由 `localStorage` 预置 + 落盘前断言 `PVDB_i18n.lang()==='zh'` 保证，杜绝「名字叫 zh 实际是英文」的错误标注

## [2026-09-22b] — 自建树可行性实测：内存 OOM、物种键 bug、覆盖度结论更正

### Added
- **`docs/phylo/render_tree_svg.py`**: 把 Newick 渲成独立 SVG（x = 累积枝长，y = 叶 DFS 序，画布按叶数自动加高），加 `--manifest` 时按 `VMR_Genus` 着色并出图例。用于**不经浏览器**检查自建树。已用 ICTV 的 `Geminiviridae/OSD.Gem.Fig3.v3.treefile.txt` 做三重校验（见 README M9）
- **`docs/phylo/work/REPRODUCE.md`**: 自建树试点的**可复现记录** —— 输入选择（含 MD5 基线）、工具链、固定参数（`--seed 42`）、四次失败的完整数据、长度标度实验、三条可选路径、复现命令
- **`docs/phylo/work/render_check_Geminiviridae_Fig3.{svg,png}`**: 渲染器的校验产物（PNG 由无头 Chrome 截图，用于目视核对）
- **README M9 新增「建议建树清单」**: 17 个 ≥50% 覆盖的科（合计 1,212 条 / 7.6 M字符），含建议条数、覆盖度、比对规模、建法（单分体直接建 / 拆组分）
- **README M9 新增「那在哪里算？本机 WSL 就够」**: 服务器 2 核 / 3.5 GB vs 本机 WSL 20 核 / 31 GB 的实测对照
- **`docs/phylo/work/` 下的服务器脚本**（均为试验用，非交付物）：`run_pilot{,2,3,4}.sh`、`ceiling.sh`、`control.sh`、`lenscale.sh` 及各轮日志


### Fixed
- **`build_own_trees.py` 物种键 bug（严重）**：`--derep-species` 原先用 `VMR_Species` 作去重键，而该列全库仅 **14.7%（850/5773）** 有值 —— 85% 的行键都是空串，**整科会被塌成 1 条序列**。改为 `species_key()`，按 `VMR_Species → Species_ICTV → Species_NCBI → 登录号` 回退；`--audit` 的「物种」列、manifest 的 `species` 列、导出统计一并改用该键
- **`build_own_trees.py` 打印的建树命令**：原为 `mafft --auto`（实测会被 OOM killer 杀，见下），先改为 `--retree 2 --maxiterate 0 --6merpair` + `ulimit -v 2200000`；**同轮实测又推翻了护栏这一步**（`ulimit -v` 限虚拟地址空间，在 RSS 仅 1.70 GB 时误杀），最终版已**去掉护栏**，并改为提示「在大内存机器上执行」
- **`render_tree_svg.py` 两个崩溃**：① 嵌套函数 `read_tokens()` / `sub()` 未声明 `nonlocal i` → `UnboundLocalError`；② `Node.__slots__` 缺 `d` / `y` → 布局阶段 `AttributeError`

### 数据核查（实测，未修改任何源文件）
- **更正 README M9 的覆盖度结论（上一版写错了）**：上一版用 `VMR_Species` 数物种，得出「Caulimoviridae 14 物种 / MSL 109」「Geminiviridae 120 / 560」，并据此判定「本地库建不出全科物种树」。**错在选错了列** —— `VMR_Species` 填充率仅 14.7%，而 `Species_ICTV` / `Species_NCBI` 是 100%。按后者重算：

  | 科 | MSL41 物种 | 本库 | 覆盖 |
  |:---|---:|---:|---:|
  | Pospiviroidae | 40 | 39 | 98% |
  | Caulimoviridae | 109 | 105 | 96% |
  | Fimoviridae | 33 | 31 | 94% |
  | Bromoviridae | 52 | 49 | 94% |
  | Alphaflexiviridae | 73 | 67 | 92% |
  | Betaflexiviridae | 159 | 144 | 91% |
  | Solemoviridae | 148 | 128 | 86% |
  | Tolecusatellitidae | 133 | 111 | 83% |
  | Potyviridae | 264 | 207 | 78% |
  | Geminiviridae | 560 | 197 | **35%** |
  | Rhabdoviridae | 615 | 90 | **15%** |

  **新结论**：本地库对**多数植物病毒科已接近物种完整**（10 个科 ≥80%、17 个科 ≥50%），可直接建「近全科物种树」；只有 Rhabdoviridae / Geminiviridae / Phenuiviridae / Secoviridae 等少数大科缺口大 —— GPI 的 520 条 Geminiviridae 正对应此缺口
- **`VMR_Species` 与 `Species_ICTV` 不是同一命名空间**：850 个非空 `VMR_Species` 中只有 **62.1%（528）** 与 `Species_ICTV` 相同，其余 37.9% 的 `Species_ICTV` 装的是 NCBI 常用名（如 `LC625373.1` 的 `VMR_Species='Caulimovirus tessellodahliae'`，而 `Species_ICTV='Dahlia common mosaic virus'`）。`species_key()` 全库去重得 3,505，比单用 `Species_ICTV` 的 3,521 少 16（即合并掉 16 个重复物种）—— **计数可信用，但不可当权威物种名录**
- **服务器内存是硬约束：全长基因组比对在这台机器上跑不过去（四次尝试全部失败）**
  输入固定为 `work/Caulimoviridae.fa`（105 条 × 6,450..9,872 bp，共 812 kb）：

  | # | 配置 | 结果 | 峰值 RSS | 墙钟 |
  |:--|:---|:---|---:|---:|
  | 1 | `--auto`（→ L-INS-i） | 内核 OOM 杀 `disttbfast`，`.aln` 留 0 字节 | 2.92 GB | ~6 min |
  | 2 | 配置 3 + `ulimit -v 2200000` | MAFFT 自报 `Allocation error( 21210 int vec )` | 1.70 GB | 4:31 |
  | 3 | `--retree 2 --maxiterate 0 --6merpair` | 内核 OOM 杀 `disttbfast` | **2.93 GB** | 8:29 |
  | 4 | 配置 3 + `--parttree --partsize 30` | 参数被**静默忽略**，与 #3 同样被杀 | 2.93 GB | — |

  内核日志（#3）：`Killed process 2933508 (disttbfast) total-vm:3735580kB, anon-rss:2931724kB`
  / `constraint=CONSTRAINT_NONE,...,global_oom`。第 4 条的证据是 `--parttree` 下
  `disttbfast` 的调用参数与不加时**逐字相同**。
- **三个被实测推翻的想当然**：① ~~`--6merpair`/FFT-NS-2 能降内存~~ —— **不降**（2.93 vs 2.92 GB）；
  ② ~~`ulimit -v` 是合适的内存护栏~~ —— **不是**，它限**虚拟地址空间**，多线程 glibc 预留大量
  未触碰空间，#2 在 **RSS 仅 1.70 GB** 时报错，连 85 KB 的向量都申请不到，是**被护栏误杀**；
  ③ ~~`systemd-run -p MemoryMax=` 可兜底~~ —— **本机不生效**（systemd 239 / cgroup v1，
  实测 `MemoryMax=300M` 下成功分配 600 MB）。**本机没有可用的内存硬限。**
- **根因是序列长度，不是条数**（固定 N=11，只改截取长度）：

  | 长度 | 峰值 RSS | 墙钟 |
  |---:|---:|---:|
  | 1,000 bp | **39 MB** | <1 s |
  | 2,500 bp | 102 MB | 4 s |
  | 5,000 bp | 265 MB | 34 s |
  | 7,786 bp（全长） | — | **>10 min 未完成** |

  长度 2× → 内存 2.6×、时间 8.5×。**内存墙是「每条 7.8 kb 太长」，不是「105 条太多」**
  —— 截到 1 kb 时只要 39 MB，差 75 倍。
- **本机 WSL 可以算**（实测）：WSL `Ubuntu-24.04` 有 **20 核 / 31 GB 可用内存**
  （服务器 2 核 / 3.5 GB，**内存 9×、核数 10×**），`/mnt/d/桌面/C-host_classify/plant_virus_db_pipeline`
  直接可见。项目 `pixi.toml` 的 `target.linux-64.dependencies` **已含 `mafft = ">=7.520"`**，
  WSL 内装 pixi 即可复用。**注意 bioconda 的 `mafft` 不支持 win-64**，Windows 侧无法 `pixi add`。
- **三次 OOM 的受害者都是 `disttbfast`**（oom_score 最高），线上站点三次都活着；
  自建的常驻内存看门狗（5 秒采样 / 2.4 GB 阈值）**没来得及触发**。
  **站点存活是运气不是设计** —— 全局 OOM 的受害者由 oom_score 决定。


### Verification
- `render_tree_svg.py` 三重校验：① 与 `build_molecular.py` 对拍 **5/5 指标相同**（leaves 29 / internals 27 / maxDegree 3 / blMax 0.639139 / supportN 26）；② 几何自洽 —— 竖枝 27 + 横枝 55 = **82 = 节点数 56 − 1**，零越界、零非有限坐标；③ 语义自洽 —— 26 个支持度中 6 个 <95，SVG 里红色标签**正好 6 个**
- `build_own_trees.py --audit` 物种列修复前后：Geminiviridae **43 → 197**、Betaflexiviridae 20 → **144**、Solemoviridae 68 → **128**、Tolecusatellitidae 17 → **111**、Rhabdoviridae 34 → **90**、Fimoviridae 6 → **29**
- `--derep-species` 回归：Geminiviridae 修复前塌成 **1 条**，修复后 **541 条 / 541 物种**（含全部 complete、未按组分筛）；Caulimoviridae 104、Potyviridae 213
- Caulimoviridae 的 105 条去重为 104 已逐条查清：`LC625373.1` 与 `NC_018616.1` 是**同一物种的两个分离物**（Dahlia common mosaic virus），合并正确
- 线上站点在计算期间保持可用：`/` 200 / 0.007 s
- **渲染器目视核对**：用无头 Chrome 把校验 SVG 截成 PNG（`work/render_check_Geminiviridae_Fig3.png`），肉眼确认 29 个叶、枝长按比例、红色支持度标签 6 个（54/87/39/68/90/67），与数值统计一致
- **站点在全部试验期间保持可用**；重负载后回归 5 条路由全部 200，且字节数与 09-22 验收时**逐字节一致**：`/` 11,205 B、`/phylo/` 36,523 B、`/phylo/molecular/` 35,613 B、`/phylo/molecular/families/` 20,148 B、`family_index.json` 111,152 B；nginx 3 进程、gunicorn 13 进程均存活
- 服务器上所有试验进程已清理，`pgrep -af "[m]afft|[d]isttbfast|[d]vtditr"` 无残留

## [2026-09-22] — 分子树按科索引页 + 口径标注 + 占位符计数更正

### Added
- **`docs/phylo/molecular/families/`**: 分子树的**按科索引画廊**。25 张卡片，每张含树数 / 叶数（附「叶÷物种」比值）/ 严格二分叉 / 支持度覆盖 / 最大枝长 / MSL 属数 / 基因组类型、**拓扑缩略图**、数据质量标记，点卡片带深链落到查看器。支持按叶数 / 物种数 / 叶÷物种 / 跨科数 / 科名排序，科名筛选，「只看含跨科序列」「只看无支持度」两个过滤器。中英双语，零 CDN
- **`docs/phylo/build_family_index.py`**: 由 `molecular_trees.json` 生成派生数据 `families/family_index.json`（111 KB）。**只读**已验证产物，**不改动** `molecular_trees.json`。内含每棵树降采样后的 sparkline（拓扑深度布局，path 合计 ~90 KB，叶数 >48 时把小分支塌缩成竖笔）
- **`/phylo/molecular/` 页首口径标注**：新增醒目提示条，说明这些树是章节插图（Fig1–Fig6）、叶集合不等于该科物种表、可能含跨科外群；DATASET 面板加「All families →」入口，页首提示条加「See the per-family index →」

### 数据核查（实测，未修改任何源文件）
- **更正上一版写错的占位符计数**：上一版记「**32/3,904（0.8%）**，分布在 Kitaviridae 13 / Botourmiaviridae 10 / Secoviridae 9」**是错的**。该占位符有**三种写法**，当时只匹配了带空格那一种，把 Potyviridae 的 25 个和 Bromoviridae 的 1 个**全部漏掉**。正确总数是 **58/3,904（1.5%）**：
  | 写法 | 数量 | 分布 |
  |:---|:---|:---|
  | `ACCESSION_NOT_ON_SPREADSHEET`（下划线） | 26 | Potyviridae 25、Bromoviridae 1 |
  | `ACCESSION NOT ON SPREADSHEET`（空格） | 31 | Kitaviridae 12、Botourmiaviridae 10、Secoviridae 9 |
  | `ACCESSION FORMAT NOT RECOGNISED` | 1 | Kitaviridae 1 |

  复核正则见 `build_family_index.py` 的 `PLACEHOLDER_RE`
- **这批树是「章节插图」，不是「全科物种树」**（本次新发现，之前 README 未记）：文件名 `FigN` 就是章节正文的图号（Fig3 ×15、Fig4 ×13、Fig5 ×3、Fig2 ×3、Fig6 ×2、Fig1 ×1、无编号 ×1）；叶集合既不等于该科物种表、也不限于该科。**1,863 个可识别登录号中有 37 个跨科出现**（下界，登录号命中率仅 48%）
  - `Geminiviridae` 560 物种 / 树上仅 **29** 叶；`Closteroviridae` 88/52
  - `Rhabdoviridae` 1,077 叶**全部**是 688 / 1,612 / 1,207 bp 的**片段**，非全长基因组
  - `Virgaviridae` Fig6 含 CMV（Cucumovirus）与 BMV（Bromovirus）—— 二者均属 **Bromoviridae**，此处作外群
  - `Alphaflexiviridae` Fig3 的叶是 `replicase` 基因区；`Aspiviridae` Fig3 的叶是**蛋白**登录号
  - 故「科的标签」含义是**「哪一章发表了这张图」**，不是「叶都属于这个科」
- 索引页把这四类问题做成卡片标记（均已实测）：无支持度 4 科、占位符叶名 5 科、含跨科序列 8 科、片段非全长 1 科（Rhabdoviridae）

### Verification
- 6 个上传文件 **MD5 本地/服务器逐字节一致**（`molecular/index.html`、`families/index.html`、`family_index.json`、`build_family_index.py`、`phylo/README.md`、`docs/README.md`）
- 线上路由全部 200：`/phylo/molecular/families/` 20,148 B、`.../family_index.json` 111,152 B、`/phylo/molecular/` 35,613 B、`/phylo/` 36,523 B、`/` 11,205 B
- **nginx 无需改动**：父级 `/phylo/molecular/` 用的是 `root` 而非 `alias`，子目录天然被它匹配（`try_files $uri $uri/` → 子目录 `index.html`），这正是 09-21 把分子树页从 `alias` 改成 `root` 的附带好处
- 无头 Chrome 实测线上页：渲染出 **25 张卡片、38 个 Fig 按钮、25 条缩略图 path，无重复科**
- 深链实测：`/phylo/molecular/?family=Konkoviridae&tree=Konkoviridae%7CFig4` → 图表标题为 `Konkoviridae|Fig4 · Figure 4`，参数解析正确
- 部署前备份：`docs/phylo/molecular/index.html.bak_famidx_20260922`（33,133 B，旧版）

## [2026-09-21c] — ICTV 官方分子系统发育树页（/phylo/molecular/）

### Added
- **`docs/phylo/molecular/`**: 展示 **ICTV Report 各科章节官方发布的**最大似然系统发育树交互页。**25 个植物病毒科 / 38 棵树 / 3,904 条末端序列**。枝长树（phylogram，按累积枝长定位）+ 环形双布局、支持度阈值过滤（低支持度分支合并为 `[N sequences]`）、支持度按置信度着色、末端搜索高亮、节点详情（含最小包含分支）、PNG 导出、中英双语、URL 参数分享（`?family=&tree=&mode=&sup=&q=`）。纯静态 + 本地 ECharts
- **`docs/phylo/fetch_ictv_trees.py`**: 抓取各科 `resources` 页并下载树/比对文件。`--discover` 写 `ictv_raw/manifest.json`，`--download` 下载（`--with-alignments` 连比对一起），`--summary` 打印覆盖概况
- **`docs/phylo/build_molecular.py`**: 标准库 Newick 解析器 + 统计，输出 `molecular_trees.json`（~267 KB / 38 棵树）
- **`docs/phylo/ictv_raw/`**: 38 个原始 Newick 文件 + manifest（39 文件 / 308 KB），保留来源与可复现性
- nginx 路由 `/phylo/molecular/`；`/phylo/` 顶栏与 portal 首页各新增入口

### Fixed
- **nginx `alias` + `try_files` 路径拼接坑**：`/phylo/` 用的是 `alias`，若分子树子页沿用同一块，`try_files` 会按 `alias+uri` 拼路径，导致 `/phylo/molecular/` 被兜底到 `/phylo/index.html`（分类树页）。**改为单独声明 `location /phylo/molecular/` 并用 `root`**
- **Newick 解析器支持「类群名与支持度连写」**：ICTV 有文件写成 `)'Tymovirales'0.9980:0.43`（标准 Newick 只允许一个标签），原先解析中断。改为连续读取多个 token 再拆分名字/支持度，`Virgaviridae Fig6` 由此可解析（38/38 全部成功）
- **文件链接正则覆盖三种写法**：相对路径、绝对 URL、**带前导空格**（`href=" /sites/..."`）。原正则只匹配相对路径，漏掉 Caulimoviridae/Secoviridae/Tospoviridae/Fimoviridae，树文件数 33→38
- 环形视图：末端名过长时 ECharts 会为标签留空间把树压小，改为仅在末端 ≤ 20 时默认显示标签；`series-tree.zoom` 是绕左上角缩放会推出画面，已弃用

### 数据核查（实测，未修改任何源文件）
- **两个科发布了同一个树文件**：`Metaviridae/ORTD.Meta.Fig3.v9.treefile.nwk` 与 `Pseudoviridae/ORTR.Pseudo.Fig3.treefile.nwk` **MD5 完全相同**（`ed5a8d71f1dc0adeb6480185348e3e7a`，均 7,486 B / 417 末端 / 145 多分叉）。可能是 ICTV 有意合并分析，也可能是发布失误，引用前建议确认
- **末端名含占位符**：本条原记「32/3,904（0.8%），分布在 Kitaviridae(13)、Botourmiaviridae(10)、Secoviridae(9)」，**已在 [2026-09-22] 条目中更正为 58/3,904（1.5%）** —— 当时只匹配了该占位符带空格的一种写法，漏掉 `ACCESSION_NOT_ON_SPREADSHEET`（下划线，26 个）与 `ACCESSION FORMAT NOT RECOGNISED`（1 个）
- **4 棵树无任何支持度标注**：Metaviridae、Pseudoviridae、Phenuiviridae、Secoviridae
- 12 个科（`Alphasatellitidae`/`Tombusviridae`/`Tymoviridae` 等）ICTV 尚未发布在线章节，`/resources` 返回 404 —— 属官方未覆盖，非抓取失败
- **另有 11 个科有在线章节但章节里没挂 Resources 页**（`Amalgaviridae`/`Betaflexiviridae`/`Orthototiviridae`/`Spinareoviridae` 等）：章节页 200、`/resources` 404、且章节页内无任何资源页链接。合计 23 个科无树
- **38 这个数字经过完整性核查**：`report_files/` 禁止列目录（404），抽查 5 个资源页用宽松正则比对全部 `/sites/default/files/` 引用，**未捕获 0 个**。有资源页的 25 个科 **100% 都有树**（无「有页面无树」的科）
- **38 棵树中 33 棵严格二分叉** —— 与分类学树（186/376 节点多分叉）形成对照，可用于说明「分类树 vs 系统发育树」的口径差异

### Verification
- 线上四个路由 + 门户全部 HTTP 200；`/phylo/molecular/` 返回 33,133 B 与本地分子页字节数一致，确认未被兜底到分类树页
- 4 个上传文件 MD5 本地/服务器逐字节比对一致；`nginx -t` 通过后 reload
- 本地与线上各做无头浏览器渲染实测（含 578 末端的 Rhabdoviridae 大树、环形模式、Virgaviridae/Closteroviridae 抽样）
- 部署前备份：`plant-virus.conf.bak_mol_20260921`、`docs/index.html.bak_mol_20260921`、`docs/phylo/index.html.bak_mol_20260921`

## [2026-09-21b] — 植物病毒进化关系页（/phylo/）

### Added
- **`docs/phylo/`**: 基于 ICTV MSL41 v1 的植物病毒分类学进化关系树交互页。48 科 / 214 属 / 2,684 种，叠加在全部病毒（427 科 / 17,554 种）的灰色骨架上。矩形/圆形双布局、目→科→属→种可折叠展开、按科着色（48 色黄金角分配）、别名搜索、谱系面包屑、PNG 导出、中英双语、URL 参数分享（`?layout=&depth=&gray=&q=`）。纯静态 + 本地 ECharts，无 CDN 依赖
- **`docs/phylo/export_msl41.py`**: 用标准库 `zipfile`+`ElementTree` 流式解析 ICTV 官方 .xlsx（本机无 openpyxl/pandas），导出 17,554 条 species 到 `data/MSL41_species.tsv`
- **`docs/phylo/build_taxonomy.py`**: 建树脚本。**ICTV MSL 无宿主列**，植物病毒判定改由 ICTV VMR 的 `Host source` 种级标注完成 + 科级黑名单（沿用 `C4_clean_all_tsvs.py`）。输出 `taxonomy_tree.json`（3,377 节点 / 293 KB）
- nginx 路由 `/phylo/`（plant-virus.conf）；portal 首页 Analysis Tools 新增入口卡片

### Fixed / 数据核查
- **弃用属级黑名单**：`C4_clean_all_tsvs.py` 的 `FUNGAL_GENERA` 等属级名单是「序列文件归类」规则，非「非植物病毒」判定。误用会误杀 `Fusagravirus`(PMeV)、`Totivirus`、`Magoulivirus`/`Penoulivirus`、`Ourmiavirus`，使植物病毒科 48→45
- **`Pestiviridae` 保留判定**：科内仅 `Koshovirus sonchi` 标 plants，查证 `Koshovirus` 确为植物感染病毒属（GKaV/carrot），故保留而非剔除
- **发现 `docs/data/Plant_Virus_Ref.Info.tsv` 误纳 2 个非植物病毒科**：`Anicreviridae`（vertebrates/invertebrates）与 `Vilyaviridae`（vertebrates/protists），共 36 个种，VMR 宿主标注中均无 plants。**本次未改动该文件**，留待后续单独清理

### Verification
- 两条独立路径交叉验证植物病毒科集合：VMR 宿主判定 vs RefSeq `VMR_Family`，交集 46/48，4 个差异科已逐条核查（见 `docs/phylo/README.md` §4）
- 2,684 个植物病毒种 **100% 命中 MSL41**；父子关系在 JSON 层逐一验证
- 本地无头浏览器渲染实测 + 部署后线上端到端实测；上传文件 MD5 逐字节比对一致

## [2026-09-21] — 宿主-病毒关联分析页（/association/）

### Added
- **`docs/association/`**: 病毒目科属种 × 植物(宿主)目科属种关联分析交互页，双层桑基图点击层层下钻（目→科→属→种），面包屑回退、双向视角（病毒→宿主 / 宿主→病毒）、Top-N 聚合、别名搜索（TSWV/CMV 等，懒加载 /reference/data/name_mapping.tsv）、节点/连线详情面板、PNG/CSV 导出、中英双语（复用 i18n.js）。纯静态 + 本地 ECharts，无 CDN 依赖
- **`docs/association/build_associations.py`**: 数据构建脚本 — 199,070 条 accession 的病毒 Taxid 与宿主文本经 `data/external/taxdump` (NCBI Taxonomy, ICTV 同步) 解析为双层谱系，聚合为 14,791 个种级关联对 (4,820 病毒种 × 3,040 宿主叶, 宿主解析率 99.5%)，输出 associations.json (~1.3 MB)
- nginx 路由 `/association/`（plant-virus.conf）；portal 首页 Analysis Tools 新增入口卡片

## [2026-07-24] — Knowledge RAG 500 修复 + i18n v3 全站部署

### Fixed
- **Knowledge RAG /query 500 错误**: `_enrich_citations` 中 `CitationOut.authors` 期望 `list[str]` 但 DB 返回分号分隔 `str`; 新增 `_parse_authors()` 兼容两种类型
- **Knowledge RAG 重启失败**: 未 `cd /opt` 导致 pydantic-settings 找不到 `.env.local`; USER.md 已更新重启命令
- **i18n 切换按钮无效**: 9 个页面 (reference/photos/literature/te/explorer/submit/download/segmented/nonsegmented) 有 i18n.js 但无 `data-i18n` 属性, 已补全标题翻译

### Changed
- **i18n v3 轻量版**: 旧版文本节点匹配方案替换为 `data-i18n` 属性方案, 覆盖 23 个页面的导航/标题/卡片 UI 文本
- 全站 HTML 中译英完成 (26 个文件)
- portal 首页新增 Help & Documentation 和 Supplementary Resources 入口卡片

### Added
- `docs/resources.html`: 14 分类 100+ 公共数据库与工具资源整理页
- nginx 路由: `/resources.html`, `/help/`

## [2026-07-23b] — README 全面更新 + 数据量同步

### Changed
- **根 README.md**: 修正引物总量 57,072 → 103,642; 新增服务端口映射表; 补充 Metabuli Primer/GenBank 功能描述; 统一 12 模块技术栈说明
- **7.literature_tracker README**: 新增 Mermaid 架构图 + CI 自动化流程图; 补充 7 类检索策略/AI 摘要 8 字段/文件结构全览; 从 ~30 行扩展到 ~200 行
- **8.plant-insect README**: 新增 Mermaid 架构图 + 合并管线流程图; 补充三维 facet 检索详情; Web 三标签页可视化说明; 从 ~60 行扩展到 ~150 行
- **9.metabuli README**: 更新四大→五大分析标签 (新增 Primer + GenBank 基因可视化); 补充引物设计工作流 Mermaid 图; 添加 2026-07-23 修复记录; 完善 VSC 表 Analyze 列四件套说明
- **11.antiviral_genes README**: 全中文化 + 新增 Mermaid 架构图; 补充处理管线流程图; 从 ~120 行英文化扩展到 ~220 行中文版
- **12.pamirdb README**: 新增 Mermaid 架构图 + 三算法共识分级说明; 补充预测管线/Sankey-Chord-Heatmap 可视化; 从 ~100 行扩展到 ~170 行
- **docs README**: 新增路由覆盖表; 补充 TE FASTA 文件清单/i18n 版本号; 完善缓存策略说明

### Fixed
- 根 README 引物对数量: 57,072 → 103,642 (同步 primer 模块最新统计)
- 根 README RAG 论文数: 193,000+ → 60,000+ (修正为向量化全文数)
- 根 README 在线服务表: 补充 Metabuli Primer 设计/GenBank 可视化功能
- 根 README Metabuli 分析标签数: 四 → 五 (新增 Primer 设计)

## [2026-07-23] — Metabuli 增强: Primer 设计 + GenBank 基因可视化 + 错误修复

### Added
- **Primer 设计标签页**: 对分类出的病毒 contig 一键设计 PCR/qPCR 引物 (Primer3 + varVAMP 保守区策略)
- **GenBank 基因结构可视化**: `/metabuli/genbank/<accession>` API 端点，从 NCBI 自动拉取并缓存 GenBank 注释
- 引物结果页基因组位置 SVG 叠加 CDS/gene/mat_peptide/UTR 轨道
- VSC 表 Analyze 列新增 Primer 按钮 (CDD/BLASTN/BLASTX/Primer 四件套)
- NCBI→ICTV 物种名转换: Primer 用 NCBI taxon 查物种索引, VSC 显示 ICTV 物种名
- 引物结果链接到 `/primers/` 引物数据库详情页

### Fixed
- **i18n.js 语法错误**: 删除 `'的': ''s'` 导致的 `Unexpected identifier 's'`
- **metabuli_page.html JS 语法**: `5\'\''->3\'\''` 转义断裂 → 改用 `&#39;→3&#39;` HTML entity
- **Primer Score 全零**: `round(penalty, 2)` 精度不足 → `round(penalty, 4)`
- **Primer Results 不显示**: `primer_status` 端点无 results → `renderPrimer` 自动 fetch `/primer_results`
- **服务器磁盘满 (100%)**: 清理 3.4G i18n 备份 + 240MB db tar.gz，导致 nginx POST 500
- i18n.js 引用添加 `?v=3` 缓存破坏参数

### Changed
- `9.metabuli/metabuli_page.html`: Analyze 列宽度 180→240px, i18n.js 版本号
- `9.metabuli/metabuli_api.py`: 新增 GenBank 特征解析 (`_fetch_gb`, `_extract_features`)
- `4.virus_primer/step2_design_primers.py`: Penalty 精度 2→4 位小数
- `docs/i18n.js`: 删除无效翻译条目

## [2026-07-20] — 项目审计修复 + 模块文档全面更新 + Module 13 归档

### Archived
- **`13.virus_profile/` → `_archived_13.virus_profile/`**: 独立 `/virus/` 网页已停用，功能融入 `3.virus_explorer`「病毒档案」Tab。systemd 服务 `virus-profile.service` 已停用

### Changed
- **6 个模块 README 全面更新** (新增 17 个 Mermaid 图表): `4.virus_primer` (1.2→10.5KB), `13.virus_profile` (1.5→7.4KB), `3.virus_explorer` (2.1→8.1KB), `9.metabuli` (2.2→9.5KB), `5.host_classify` (3.6→7.2KB), `10.virus_photos` (2.9→9.3KB)
- `README.md`, `TECHNICAL_REPORT.md`, `USER.md` 同步更新: 模块数 13→12, 删除 `/virus/` 路由引用, Explorer 描述含病毒档案

### Fixed
- 修复模块重复编号: `8.virus_profile` → `13.virus_profile`（与 `8.plant-insect` 冲突）
- `.gitignore` 新增: pubmed_records (8.25 GB), rag-db (2 GB), PDF/DOCX 源文件, archive/backup 目录
- 清理 `12.pamirdb/README.md` 中不存在的 index 变体引用
- 统一 nginx 配置: `3.virus_explorer/nginx.conf` 标记为 DEPRECATED，主配置为 `plant-virus.conf`

### Added
- systemd `.service` 文件: `virus-explorer`, `literature-tracker`, `vector-host`, `metabuli-api`
- `LICENSE` (MIT)
- `CHANGELOG.md`
- `SOUL.md` 项目原则定义

### Changed
- `1.Prepare_plant_virus_pipeline/` audit/fix 脚本移至 `audit/` 子目录
- 大文件加入 `.gitignore`: `8.plant-insect/*.tsv`, `8.plant-insect/*.xlsx`, `8.plant-insect/Fig*.png`

## [_v2 / _PROD 文件说明]

项目中存在以 `_v2` 或 `_PROD` 后缀命名的文件，含义如下：
- `_v2`: 第二版重写的脚本（`europepmc_v2.py`, `app_v2.bak` 等），`_v2` 为当前使用版本
- `_PROD`: 生产环境专用版本（`step5_web_server_PROD.py`），区别于开发/测试版本

## [本地/服务器路径差异]

本地仓库: `D:\桌面\C-host_classify\plant_virus_db_pipeline`
服务器: `/opt/plant_virus_db/plant_virus_db_pipeline`

个别服务代码位置不同（详见 `USER.md`），如：
- Primers 服务: 服务器 `/opt/plant_virus_db/primer_design_server/`，非本地 `4.virus_primer/`
- Knowledge RAG: 服务器 `/opt/src/plant_virus_rag/`，非本地 `6.knowledge_rag/`

### [2026-09-27·追加] 节段标签归并（refinfo common.norm_seg/resolve_segments + merge_to_ref._seg_key 同步扩展）

据 refinfo_analysis 离群物种追查，节段命名存在系统性别名/变体/重复登记：

- **别名映射**：ACOMPONENT/BCOMPONENT→DNA-A/B（Begomovirus）、RNAREP/RNATGB/RNACP→RNA1/2/3
  （Pomovirus 提交惯例）、BBTVR→DNA-R（Babuvirus）、SATELLITE*/SAT*→卫星单列；
- **变体后缀**：RNA3A/B→RNA3（Emaravirus）、DNAC1/C2→DNA-C、DNAR1-R4→DNA-R（Nanovirus；
  DNA-U1/U2/U4 为不同组分，保留）；
- **跨名重复合并**：同物种内代表序列 ≥80% k-mer Jaccard 判为同一分子重复登记
  （实例：Dichorhavirus clerodendri 的 DNA-L=RNA1=6,524 nt 同序、BBTV 的 DNA-A=DNA-R=BBTVR）；
  同物种不同组分（Nanovirus DNA-C vs DNA-U1 同长不同序）不受影响；
- **纠正**：此前"Dichorhavirus 6 个 2 段物种应补到 4 段"的判断有误——实查 8 种全部为
  RNA1+RNA2 二分基因组，clerodendri 的 4 段系同节段重复登记，归并后无需补收；
- **可疑记录复核**：*B. zetainflatheobromae*（NC_038379.1, 13.2 kb）序列真实但宿主记录为
  河北小麦，物种指定存疑（CSSToA 文献 ~7.4 kb），保留并标注；Olive virus A（21,087 nt MAG）
  经文献证实为真实大小（~21,057 nt），无需处理。

效果（refinfo_analysis ⑥ 分段·节段齐全）：81.73% → **87.47%**；节段数对齐子集 95.45%。
遗留：Babuvirus musae（BBTV 多分离株组件混收，19 段）需人工按分离株整理。

### [2026-09-27·追加2] 删除 Babuvirus musae 异隔离株组件 13 条（作者指令）

musae（BBTV）在参考集中混收了多个地理隔离株的组件（DNA-A/B/U/3-6、RNA1-6；与正典
NC_003473-79 序列同一性仅 53–92%），无分离株字段无法自动归组。已删除 13 条
（备份 `.bak.20260927_musae`），保留正典 6 组分 + 2 条卫星。参考集 8,500 → **8,487**；
musae 归位 6 段，Babuvirus 属内一致率 0% → 100%。

### [2026-09-28] 修复 Deltasatellite solani 记录替换错误（merge_to_ref 长优先规则副作用）

离群审计发现：`Deltasatellite solani` 在参考集中的记录为 AB113651.1（1,354 nt，
"Tomato leaf curl virus satellite DNA"，betasatellite 尺寸），系 merge_to_ref 的
`rank_record`「同完整度取更长」规则替换所致；而 ICTV VMR_MSL41 该物种范例为 U74627
（RefSeq NC_002743.1，682 nt，"tomato leaf curl deltasatellite"）。该属 13 个物种
正常范围 662–739 nt。

处置：`Plant_Virus_Ref.Info.tsv` 与 `Plant_Virus_Ref.fasta` 以 NC_002743.1 替换 AB113651.1
（备份 `.bak.20260928_fix`）。参考集条数不变（8,484）。

附带发现（非本次操作，需确认来源）：相对 `Plant_Virus_Ref.Info.tsv.bak.20260927_musae`
（8,500 条），另有 3 条记录在此前已被移除：
`NC_038379.1`（Badnavirus zetainflatheobromae，河北小麦存疑记录）、
`NC_040365.1`（Tentweb spider associated circular virus，蛛类关联）、
`KY487991.1`（Uncultured virus clone CG97，未培养环境克隆）。
若非人工主动清理，请核对。

## [2026-10-03] — 新增 `16.fold_web`：ColabFold 批量预测 Web 平台（收集→预测→整理→入库 + 手动上传）

承接 15 模块的 3,698 条待预测缺口，把 ColabFold 批量预测做成自服务网页：

- **自动链路**：粘贴/一键填入 pending accession → UniProt 自动拉序列 → colabfold_batch
  子进程预测 → rank_001 + mean pLDDT 校验 → 落盘 `structures_selffold/`，
  `structures_index.tsv` sources += SELF，覆盖率面板实时刷新。
- **手动链路**：上传 FASTA 直接建预测任务；上传 ColabFold 结果 ZIP 直接入库。
- **部署**：pip 装 `colabfold[alphafold]`（≥1.6.3）+ flask，GPU 服务器一条命令起服务；
  本机（无 GPU）已用 stub 预测器完成沙箱全链路冒烟（收集 2/2、入库、pending 联动、
  ZIP 路径全通过）。
- 边界：304 条 >2,700 aa 多聚蛋白需先切分（清单在 15/colabfold_input）；
  应用无鉴权，公网部署需套 nginx + 认证。

## [2026-10-03] — 15 模块新增 webapp：总览 + 统计面板 + 检索 + 3Dmol 查看器

静态自包含站（`15.uniprot_plant_virus_structures/webapp/`，模块根目录起服务）：
- `index.html` 总览 dashboard：8 指标卡、来源组合条形图、蛋白检索（accession/物种/entry，
  点行弹详情 + UniProt/RCSB/AFDB 外链 + 3D 入口）、413 毒株覆盖表；
- `stats.html` 统计面板：物种完整率环形图（100/158/155）、来源组合 14 行明细与单源命中、
  待预测缺口分层（365 真零 = 304 多聚蛋白 + 61 常规）、管线台账；
- `viewer.html` 3Dmol 查看器：PDB/AFDB/自建三类来源切换，预测模型按 pLDDT 四段着色；
- 数据层 `build_data.py` 由 structures_index/virus_coverage 幂等生成
  stats/proteins/virus_coverage 三个 JSON（0.9MB 蛋白索引，无外部 CDN 依赖，3Dmol 本地化）。

## [2026-10-03] — Foldify 外部预测通道接入（16.fold_web + 15 webapp）

- 16.fold_web 新增 `/api/export/foldify`：待预测清单中 ≤600 aa 蛋白按 100 条/块打包
  ZIP（manifest + 使用说明），供 Foldify（免费在线 AF3/AF2/ColabFold/OmegaFold/ESMFold）
  人工提交；结果经「上传结果入库」回流 structures_index。
- 15 webapp 蛋白详情面板加 Foldify 直达链接。
- 定位：人工小批量补漏与多模型交叉验证；批量主体仍为本地 ColabFold
  （Foldify 无公开 API、并发 5、≤600aa，不做自动化批量提交）。
  远期可选：MIT 源码自建 Foldify（K8s GPU 集群）补 AF3/OmegaFold/ESMFold 后端。
