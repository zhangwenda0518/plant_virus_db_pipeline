# Plant Virus Phylogeny (`/phylo/`)

**2026-10-11 起为单页双视图**：分类学树与分子树合并为 `/phylo/` 一个页面，顶栏标签页切换
（`?view=molecular` 直达分子树视图）。旧地址 `/phylo/molecular/` 保留为**跳转页**
（带原查询参数跳到 `/phylo/?view=molecular&…`），不再是一个独立页面。

| 视图 | 路径 | 内容 |
|:---|:---|:---|
| 分类学树（默认） | `/phylo/` | 基于 **ICTV Master Species List 2025 MSL41 v1** 的分类学层级树。**默认只画植物病毒**（48 科 / 214 属 / 2,684 种 / 2,997 节点）；勾选「非植物病毒」可叠加灰色骨架 —— 域/界/门/纲/目 五级 + **73 个「与植物病毒同目」的非植物科** + 232 个混合属里的非植物种，共 3,450 节点。 |
| **分子系统发育树** | `/phylo/?view=molecular`（旧 `/phylo/molecular/` 跳转） | **ICTV 报告章节官方发布的**最大似然树。38 棵树 / 25 个科 / **3,341** 条序列，带真实枝长与支持度。 |
| **按科索引（画廊）** | `/phylo/molecular/families/` | 25 个科的卡片索引：树数 / 叶数 / 严格二分叉 / 支持度覆盖 / 最大枝长 / MSL 物种数与属数，加拓扑缩略图与数据质量标记。点卡片落到 `/phylo/?view=molecular&family=…&tree=…`。 |

两者性质不同：前者是**分类**（集合的嵌套，不描述分化过程），后者是**系统发育**（由序列推断的分化事件，二分叉、带枝长）。

> **口径警告（重要）**：分子树视图里的树是 **ICTV Report 章节正文的插图（Fig1–Fig6）**，
> **不是覆盖全科的物种树**。叶集合常常远小于该科物种表，叶可能是基因片段或蛋白登录号，
> 有些树还含**别的科**作为外群。详见 [M4 第 4 条](#m4-已知数据质量问题实测未修改源文件)。
> 页面在醒目位置（黄色警示条 + 页脚）标注了这一点。

- 纯静态实现（ECharts 本地化于 `echarts.min.js`，无 CDN 依赖），nginx 直接托管。
- 分类树数据：`taxonomy_tree.json`（~298 KB，3,450 节点），由 `build_taxonomy.py` 生成。
- 分子树数据：`molecular_trees.json`（~267 KB，38 棵树），由 `fetch_ictv_trees.py` + `build_molecular.py` 生成；
  视图脚本抽在 `molecular_viewer.js`（页面加载即取数，`echarts.init` 延迟到标签页首次激活）。
- 按科索引数据：`molecular/families/family_index.json`（~106 KB），由 `build_family_index.py` 生成
  （**只读** `molecular_trees.json`，不改动已验证产物）。
- 矩形 / 圆形两种布局，可折叠展开到属或种，按科着色，别名搜索，PNG 导出，中英双语。
- 「非植物病毒」开关**默认关闭**（只显示植物病毒）。打开后叠加灰色骨架 —— 详见 §5。

---

## 1. 数据来源

| 用途 | 文件 | 说明 |
|:---|:---|:---|
| 分类层级 | `data/MSL41_species.tsv` | ICTV MSL41 v1 主表导出，17,554 条 species |
| 植物病毒判定 | ICTV VMR `Host source` 列 | ICTV 官方宿主标注，isolate 级 |

`data/MSL41_species.tsv` 由 `export_msl41.py` 从 ICTV 官方 `.xlsx` 导出
（本机无 openpyxl/pandas，用标准库 `zipfile` + `ElementTree` 流式解析 14 MB 的 sheet XML）。

```bash
python export_msl41.py --xlsx "ICTV_Master_Species_List_2025_MSL41.v1.xlsx" \
                       --out data/MSL41_species.tsv
```

## 2. 判定口径

**ICTV Master Species List 只发布分类层级（Realm→…→Species），没有宿主列。**
判定「哪些科属是植物病毒」必须借助 ICTV VMR 的 `Host source` 字段。

判定规则（见 `build_taxonomy.py`）：

1. 取 VMR 中 `Host source ∈ {plants, plants (S), invertebrates, plants, phytobiome (S)}` 的 **species**；
2. 剔除科级黑名单中的科（噬菌体 / 真菌 / 昆虫 / 卵菌 / 环境 CRESS-DNA），
   黑名单与 `1.Prepare_plant_virus_pipeline/C4_clean_all_tsvs.py` 保持一致；
3. 其余**一律以 VMR 的种级标注为准，不做属级黑名单过滤**（理由见下）。

结果：**48 科 / 214 属 / 2,684 种**，且 2,684 个种 **100% 能在 MSL41 中命中**。

### 为什么不做属级黑名单

`C4_clean_all_tsvs.py` 里的 `FUNGAL_GENERA` / `INSECT_EXCLUDED_GENERA` 等属级名单，
用途是「把序列从 `Plant.tsv` 移到 `Fungi.tsv` / `Insecta.tsv`」，是**文件归类**规则，
不是「该属不是植物病毒」的判定。直接拿来过滤会误杀真实的植物病毒属：

| 属 | 科 | 被误杀的证据 |
|:---|:---|:---|
| `Fusagravirus` | Fusagraviridae | `Fusagravirus kyu` / `roku` = 番木瓜乳汁病毒 PMeV |
| `Totivirus` | Orthototiviridae | `Totivirus jyukyu` 等 4 种标 plants |
| `Magoulivirus` / `Penoulivirus` | Botourmiaviridae | `Magoulivirus malus`、`Penoulivirus malus` |
| `Ourmiavirus` | Botourmiaviridae | C4 注释亦明确其为真植物病毒属 |

加属级黑名单会让植物病毒科从 48 个掉到 45 个，因此**弃用**。

## 3. 边界情形（逐条核查过）

| 情形 | 处理 | 依据 |
|:---|:---|:---|
| `Pestiviridae`（Amarillovirales 目，整体为动物/蜱传病毒） | **保留** | 科内仅 `Koshovirus sonchi` 标 plants。已查证 `Koshovirus` 确为植物感染病毒属（文献：*Two novel flavi-like viruses shed light on the plant-infecting koshoviruses*，GKaV / carrot 相关） |
| `Rhabdoviridae`（混合科） | 保留植物属 | 257/615 种标 plants，均为 `Alphacytorhabdovirus`、`Betanucleorhabdovirus` 等植物属 |
| `Phenuiviridae` / `Partitiviridae` / `Endornaviridae` / `Spinareoviridae` / `Sedoreoviridae`（混合科） | 保留植物属 | 分别为 `Coguvirus`、`Alphapartitivirus`/`Betapartitivirus`、`Alphaendornavirus`、`Fijivirus`、`Phytoreovirus` |
| 卫星病毒 / 类病毒（`Alphasatellitidae`、`Tolecusatellitidae`、`Avsunviroidae`、`Pospiviroidae`） | 按 ICTV 原样直接挂在根下 | MSL41 中这些科未定界（Realm/Kingdom/…/Order 为空），未人为造虚拟父节点 |

## 4. 交叉验证

用两条**互相独立**的路径各算一遍植物病毒科集合：

| 路径 | 数据源 | 科数 |
|:---|:---|:---|
| A（本页采用） | ICTV VMR `Host source` 种级判定 + 科级黑名单 | 48 |
| B | `docs/data/Plant_Virus_Ref.Info.tsv` 的 `VMR_Family`（NCBI 植物病毒参考序列） | 48 |

**交集 46 科。** 差异 4 科已逐条核查：

| 科 | 路径 | VMR 宿主标注（实测） | 结论 |
|:---|:---|:---|:---|
| `Metaviridae` | 仅 A | invertebrates 21 / **plants 3** / fungi 5 / protists 1 / vertebrates 1 | 确有植物宿主 → **A 正确** |
| `Pseudoviridae` | 仅 A | **plants 22** / fungi 6 / invertebrates 3 / protists 2 | 主要宿主为植物 → **A 正确** |
| `Anicreviridae` | 仅 B | vertebrates 3 / invertebrates 5，**无 plants** | 动物病毒 → **B 误纳** |
| `Vilyaviridae` | 仅 B | vertebrates 9 / protists 18，**无 plants** | 动物/原生生物病毒 → **B 误纳** |

> **附带发现**：`docs/data/Plant_Virus_Ref.Info.tsv` 收录了 `Anicreviridae`、`Vilyaviridae`
> 两个非植物病毒科（共 36 个种）。这是路径 B 的数据噪声，建议后续单独清理，
> **本次未改动该文件**。

## 5. 剪枝策略

分两层：**构建期**（`build_taxonomy.py`，决定 JSON 里有什么）与**页面级**（`index.html`，决定画不画）。

### 5.1 构建期剪枝（`build_taxonomy.py`）

对应需求「非植物病毒灰色显示但不建树」：

- 非植物病毒分支（`pc == 0`）在**目级**停止展开 —— 仍以灰色节点显示位置，但不再往下铺属/种。
  若一路铺到科级再往下，单是灰色科就有 379 个，整棵树会被撑到 7,000px 以上。
- **科级**：保留「有植物病毒种」的科（48 个），**外加「与植物病毒同目」的非植物科（73 个）**。
  后者以**灰色叶节点**出现 —— 能看到"这个目里还有哪些非植物病毒科"，但**展不开**（本库没有它们的属/种）。
  判定口径是「父节点是含植物病毒的**目**」，不是宽松的「父节点 `pc > 0`」—— 差别很大，见下方说明。
- **属级**：只保留「有植物病毒种」的属；无植物种的属一律剪掉（所以非植物病毒的「属」一个都没有）。
- 属以下保留全部种：混合属里既可能是植物种（彩色）也可能是非植物种（灰色）。

最终 3,450 节点。正交布局按可见叶子数自适应画布高度，避免几百个科压成一条线。

> **为什么限定「父节点是目」而不是宽松的「父节点 `pc > 0`」**（实测差别很大）：
> MSL41 里有 **5,263 条记录没有 Order**，`build_tree()` 会跳过缺失层级把科直接挂到最近的已知层 ——
> 于是 `Caudoviricetes`（**纲**）下直接挂了 91 个噬菌体科、根 `Viruses` 下直接挂了 25 个古菌噬菌体科。
> 若按宽松口径保留，那 25 个会作为灰色科出现在**域那一层**（根的其他子节点全是 realm），
> 既不是「同目」，视觉上也会误导。实测：严格口径 **+73** 个科；宽松口径 **+195** 个。

### 5.2 页面级开关「非植物病毒」（**默认关闭**）

`/phylo/` 的 DISPLAY 区有一个「非植物病毒 / Non-plant viruses」复选框，**默认不勾选**。

- **关闭（默认）**：把**所有** `pc == 0` 的节点从树上摘掉，只留植物病毒 —— 2,997 节点。
- **打开**：原样放回，回到构建期剪枝后的完整骨架 —— 3,450 节点。

`pc == 0` 的节点共 **453** 个（`3,450 − 453 = 2,997`，与默认态自洽），分布如下（实测，不是估计）：

| 层级 | 域 | 界 | 门 | 纲 | 目 | 科 | 属 | 种 |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|
| `pc == 0` 个数 | 8 | 8 | 15 | 34 | 83 | **73** | 0 | 232 |
| 该层总数 | 10 | 11 | 22 | 50 | 105 | **121** | 214 | 2,916 |

> **两个容易说错的口径**（2026-09-22 实测澄清）：
> 1. **树里的非植物病毒「科」只有 73 个，且全在混合目下** —— 科级保留条件是
>    「有植物病毒种」**或**「父节点是含植物病毒的目」。后一类共 73 个（分布在 20 个混合目里，
>    最多的是 `Ghabrivirales` 17 个），它们**全是灰色叶节点**：本库没有它们的属/种，
>    所以**看得到、展不开**。**非植物病毒的「属」一个都没有** —— 属级一律要求 `pc > 0`。
>    若想说「非植物病毒的科属」，那除了这 73 个科，其余指的是**构建期被剪掉、页面里根本不存在**的。
> 2. **灰色节点全是死端，点了展不开** —— 83 个 `pc == 0` 的目 `children` 为空（构建期在目级停止展开），
>    73 个非植物科同样没有 `children`。它们只是"与植物病毒同处更高层级 / 同目"的占位。
>    开关打开后依然展不开，这是设计如此、不是 bug。

深度=「科」时可见节点数：关闭 **99** 个 / 打开 **320** 个
（`99 + 221 = 320`，差的 221 = 148 个灰色骨架 + 73 个非植物科；
232 个非植物种在属/种层，深度=科时本就不可见）；顶栏 `taxa shown` 随之显示 2,997 / 3,450。

**实现要点**：开关是**就地摘除 + `STASH` 记原位置**，不是每次渲染克隆一棵裁剪树。
原因是 ECharts 的 tree 展开/折叠**直接改数据对象**上的 `collapsed` —— 若传给它克隆树，
用户展开的状态在下一次 `render()` 时就会丢（旧版 `stripGrey` 每次 `buildOption()` 都克隆，正是这个毛病）。
放回时必须**倒序** `splice`，索引才与摘除前一致。
另外该开关会增删节点与边，属于**结构性变化**，`render()` 里必须与布局切换一样先 `CHART.clear()`。

**搜索非植物节点时会自动勾上开关** —— 否则 `expandTo()` 在树上找不到节点，用户搜了却什么都没发生。

## 6. 重建

```bash
cd docs/phylo
python export_msl41.py --xlsx "<ICTV MSL41 .xlsx 路径>" --out data/MSL41_species.tsv
python build_taxonomy.py            # 默认读 ../../oneoff_scripts/_bench_b1_20260919/vmr.tsv
```

`build_taxonomy.py` 可用 `--msl` / `--vmr` / `--out` 指定路径，并输出
`data/plant_taxa.tsv`（判定结果清单，供人工复核）。

## 7. 部署

2026-10-11 单页合并后，`index.html` 同时包含两个视图，分子树脚本抽为 `molecular_viewer.js`：

```bash
# 单页（分类树 + 分子树标签页）与全部数据
scp index.html molecular_viewer.js taxonomy_tree.json molecular_trees.json echarts.min.js \
    root@39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/docs/phylo/
scp -r data ictv_raw fetch_ictv_trees.py build_molecular.py build_genus_map.py \
    root@39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/docs/phylo/

# 旧地址跳转页 + M12 的 genus_map.json（数据文件，分子树视图仍按原路径读取）
scp molecular/index.html molecular/genus_map.json \
    root@39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/docs/phylo/molecular/

# families 画廊（链接已指向 /phylo/?view=molecular&…）
scp molecular/families/index.html \
    root@39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/docs/phylo/molecular/families/
```

> `/phylo/molecular/genus_map.json` 由现有的 `location /phylo/molecular/`（`root` +
> `try_files $uri $uri/ =404`）直接托管，**不需要新增 nginx 规则**；但这也意味着
> 文件名/路径写错时是 **404 而不是兜底**，页面对此做了降级（见 M12）。
> `molecular/index.html` 现在只是**跳转页**：JS `location.replace('/phylo/?view=molecular' + 原查询参数)`，
> 另加 `<meta http-equiv="refresh">` 兜底；nginx 配置无需任何变动。

## 8. URL 参数

可直接分享特定视图：

| 参数 | 取值 | 说明 |
|:---|:---|:---|
| `view` | `molecular` | 直达「分子树」标签页；省略则落在分类学树。切换标签页时页面用 `history.replaceState` 自动维护该参数 |
| `layout` | `orthogonal` / `radial` | 矩形 / 圆形布局 |
| `depth` | `5`–`8` | 展开至 目 / 科 / 属 / 种 |
| `gray` | `1` / `0` | `1` = 显示非植物病毒骨架；`0` = 只显示植物病毒（**默认**，不写该参数也是 0） |
| `color` | `0` | 关闭按科着色（统一蓝色） |
| `q` | 分类单元名 | 自动定位并打开详情面板 |

示例：`/phylo/?q=Geminiviridae&depth=7&layout=radial`；分子树 `/phylo/?view=molecular&family=Bromoviridae&mode=radial`（M7 的参数原样可用；两个视图的 `q` 各有含义 —— 分类树=分类单元定位，分子树=末端序列匹配）。

## 9. 口径提醒

`/phylo/` 默认的「分类树」标签页是**分类学层级树**，不是分子系统发育树 ——
**分支长度不代表进化距离**。需要真实进化距离请切到「分子树」标签页
（`/phylo/?view=molecular`；下文沿用旧路径 `/phylo/molecular/` 指代这一视图）。

---

# 分子系统发育树（`/phylo/?view=molecular`）

ICTV Report 每个科章节的 **Resources 页**挂着该科报告插图对应的**最大似然树（Newick）**
与比对文件。这些是官方发布的真实分子树 —— 二分叉、带枝长（替换/位点）与节点支持度。
2026-10-11 起该视图并入 `/phylo/` 单页（顶栏标签页切换），`/phylo/molecular/` 为带参跳转页；
本节以下内容中的 `/phylo/molecular/` 均按此理解。

## M1. 抓取

```bash
python fetch_ictv_trees.py --discover      # 抓 48 个植物病毒科的 Resources 页，写 ictv_raw/manifest.json
python fetch_ictv_trees.py --download      # 下载树文件（--with-alignments 连比对一起下）
python fetch_ictv_trees.py --summary       # 打印覆盖概况
```

章节 URL 规律：`https://ictv.global/report/chapter/<科名小写>/<科名小写>/resources`。

**页面里文件链接有三种写法，正则必须都覆盖**（踩过的坑）：

| 写法 | 例子 |
|:---|:---|
| 相对路径 | `href="/sites/default/files/report_files/xxx.treefile.txt"` |
| 绝对 URL | `href="https://ictv.global/sites/default/files/report_files/xxx.treefile.txt"` |
| **带前导空格** | `href=" /sites/default/files/report_files/ONSR.Tospo.Fig3.treefile.txt"` |

文件名里**含空格**也真实存在（`ONSR.Fimo.Fig3_.v4.RNA1 newick.txt`），下载前要 URL 转义。

## M2. 覆盖情况（实测）

| 口径 | 数量 |
|:---|:---|
| 植物病毒科总数 | 48 |
| **有 Resources 页（HTTP 200）的科** | **25** |
| **有树文件的科** | **25**（有资源页的科 100% 都有树） |
| 树文件总数 | 38 |
| 比对文件总数 | 42 |
| 末端序列总数 | **3,341**（旧记 3,904，含 563 个由解析 bug 产生的空叶；见 M4 第 0 条） |
| 严格二分叉的树 | **36 / 38**（旧记 33/38；修复后仅剩 `Closteroviridae\|Fig4` 与 `Endornaviridae\|Fig2` 有多分叉） |
| 无 Resources 页的科 | 23 |

那 23 个科要分两类看（已逐类实测章节页状态码）：

| 类别 | 数量 | 说明 |
|:---|:---|:---|
| A. 有在线章节，但**章节里没挂 Resources 页** | 11 | `Amalgaviridae` `Amesuviridae` **`Betaflexiviridae`** `Mayoviridae` `Metaxyviridae` `Orthototiviridae` `Pamosaviridae` `Sedoreoviridae` `Spinareoviridae` `Tomosaviridae` `Tonesaviridae` |
| B. ICTV **根本还没写在线章节** | 12 | `Alphasatellitidae` `Ambiguiviridae` `Atkinsviridae` `Fusagraviridae` `Geplanaviridae` `Mahapunaviridae` `Ourmiaviridae` `Pestiviridae` `Solspiviridae` `Tolecusatellitidae` **`Tombusviridae`** **`Tymoviridae`** |

> A 类实测：章节页 200、`/resources` 404、且**章节页里没有任何指向资源页的链接** ——
> 是 ICTV 出章节时就没附补充文件，不是我们探错路径。
> B 类实测：章节页本身 404。

**38 这个数字是完整的**，不是漏抓：
- `sites/default/files/report_files/` **禁止列目录**（404），无法直接枚举，只能靠资源页反查；
- 抽查 5 个资源页（Potyviridae / Geminiviridae / Virgaviridae / Rhabdoviridae / Closteroviridae），
  用宽松正则抓页面内**全部** `/sites/default/files/` 引用与已捕获集合做差，
  **未捕获 0 个**（其余全是 CSS/JS/图片）。

## M3. 解析

```bash
python build_molecular.py          # -> molecular_trees.json
```

`build_molecular.py` 内置标准库 Newick 解析器，处理的非标准情形：

| 情形 | 例子 | 处理 |
|:---|:---|:---|
| 引号标签 | `'Potato virus Y'` | 支持 `''` 转义 |
| 节点注释 | `[&R]` 前缀、`[comment]` | 跳过 |
| **类群名与支持度连写** | `)'Tymovirales'0.9980:0.43` | 连续读多个 token，再拆名字/支持度 |
| 支持度两种量纲 | `0.995` 或 `99.5` | 统一归一到 0–1 |
| 枝长缺失 | — | 前端自动退回按深度等距布局 |

## M4. 已知数据质量问题（实测）

> **本节数字已于 2026-09-22 全面重算。** 起因是发现 `build_molecular.py` 的 Newick 解析器
> 有一个 bug：遇到方括号注释会**凭空多造一个空叶**（见下面第 0 条）。三个科的树因此被污染，
> 本节原先引用的「3,904 末端」等分母全部偏大。下方数字均已按修复后的口径重算，
> 凡与旧值不同处都标了 **→**。

0. **【解析 bug，已修】方括号注释会多造一个空叶**（`build_molecular.py`）。
   ICTV 有 3 个科把支持度写在方括号里（`):0.11091[1000],`），而解析器在子节点循环里
   遇到 `[` 是 `_skip_comment(); continue` —— 等于**又解析了一个子树**，此刻光标停在 `,` 上，
   于是读出一个无名、无枝长的空叶。空叶数恰好等于该文件里 `[` 的个数：

| 科 | 文件 | `[` 数 | 旧叶数 | **正确叶数** |
|:---|---:|---:|---:|---:|
| Metaviridae | `ORTD.Meta.Fig3.v9.treefile.nwk` | 207 | 417 | **210** |
| Pseudoviridae | `ORTR.Pseudo.Fig3.treefile.nwk` | 207 | 417 | **210** |
| Phenuiviridae | `ONSR.Phenui.Fig3_.v5_treefile.txt` | 149 | 301 | **152** |

   影响面：重生成 `molecular_trees.json` 后 **只有 3/38 棵树变化，其余 35 棵结构哈希逐字节不变**；
   叶总数 **3,904 → 3,341**（差 563 = 207+149+207）。
   **`docs/phylo/molecular_trees.json` 已于 2026-09-22 重新生成并上线**（md5 `ea7908b7…` → `fe9f7367…`），
   派生数据 `molecular/families/family_index.json` 同步重生成，线上已无空叶。
   修复前后可用两套解析器全量对拍验证：38 棵 ICTV 树逐棵比
   「叶集合 + 内部节点数 + 最大度」，修复后 **38/38 一致**。

1. **两个科发布了同一个树文件**：`Metaviridae/ORTD.Meta.Fig3.v9.treefile.nwk` 与
   `Pseudoviridae/ORTR.Pseudo.Fig3.treefile.nwk` **MD5 完全相同**
   （`ed5a8d71f1dc0adeb6480185348e3e7a`，均 7,486 字节）。
   **已向 ICTV 官网复核（2026-09-22）**：两个 URL
   （`…/inline-images/ORTD.Meta.Fig3.v9.treefile.nwk` 与 `…/report_files/ORTR.Pseudo.Fig3.treefile.nwk`）
   都返回 200、都返回这同一份字节 —— **重复出在 ICTV 上游，不是本库抓取或解析的问题**，
   本库是忠实的镜像。叶名是 `Ty3-1` / `CRM` / `Cereba` / `Tse3` / `Del` / `G-Rhodo` / `Beetle1`
   这类 **Ty3/gypsy 型** 元件，属 **Metaviridae** 的特征（Ty1/copia 才是 Pseudoviridae），
   所以更可能是 **ICTV 把 Metaviridae 的图也挂到了 Pseudoviridae 章节页上**。
   引用前建议向 ICTV 确认；本页**照实呈现**，不擅自删改。
   叶数与多分叉数原写作「417 末端 / 145 多分叉」，**→ 210 末端 / 0 多分叉**：
   那 207 个空叶就是「多分叉」的来源（空叶的父节点度数为 3 以上），修复后这两个科
   与 Phenuiviridae 都变成干净的二分叉树。
2. **末端名含占位符**：3,341 个末端中有 **58 个（1.74%）** 带 ICTV 自己的「登录号查不到」标记
   （旧写作 3,904 中的 1.5%，分母已按修复后口径更正；**58 这个分子不变** ——
   空叶本来就没有名字，不参与占位符计数）。
   **这个标记有三种写法，必须一起匹配**，只按其中一种数会漏掉一半以上：

| 写法 | 数量 | 分布 |
|:---|:---|:---|
| `ACCESSION_NOT_ON_SPREADSHEET`（下划线） | 26 | `Potyviridae` 25、`Bromoviridae` 1 |
| `ACCESSION NOT ON SPREADSHEET`（空格） | 31 | `Kitaviridae` 12、`Botourmiaviridae` 10、`Secoviridae` 9 |
| `ACCESSION FORMAT NOT RECOGNISED` | 1 | `Kitaviridae` 1 |

   按科合计：`Potyviridae` 25、`Kitaviridae` 13、`Botourmiaviridae` 10、`Secoviridae` 9、`Bromoviridae` 1。

   > **更正（2026-09-22）**：本节早先写的「**32 个（0.8%）**，分布在 Kitaviridae 13 /
   > Botourmiaviridae 10 / Secoviridae 9」**是错的** —— 当时只匹配了带空格的那一种写法，
   > 把 Potyviridae 的 25 个和 Bromoviridae 的 1 个**全部漏掉**。正确数字是 **58 个（1.5%）**。
   > 复核用的正则是 `build_family_index.py` 里的 `PLACEHOLDER_RE`：
   > `ACCESSION[\s_]*(?:NOT[\s_]*ON[\s_]*SPREADSHEET|FORMAT[\s_]*NOT[\s_]*RECOGNISED)`。
3. **支持度标注：3 棵是「有但被丢了」，1 棵是真的没有**（原写作「4 棵树没有任何支持度标注」，**已更正**）。
   - `Metaviridae`（207 处）、`Pseudoviridae`（207 处）、`Phenuiviridae`（149 处）：
     支持度写在**方括号**里，如 `):0.11091[1000],`，取值 225–1000（看着是 1000 次自举的计数）。
     解析器把方括号当注释丢掉，所以 `stats.supportN` 才是 0 —— **不是数据没有**。
   - `Secoviridae`（`OPSR.Seco.Fig4.v10.treefile.txt`）：方括号 0 处，**确实没有支持度标注**。
   前端对无支持度的节点一律保留，不做合并。

   > **未决**：方括号里的值是否要当支持度用，属**判定语义**，未擅自改。
   > 若要认，需在解析器里把 `[n]` 关联到所在节点（`n>1` 时按 `n/100` 归一）。
4. **这些树是「章节插图」，不是「全科物种树」** —— 建任何按科命名的页面之前必须先知道这一点。
   文件名里的 `FigN` 就是 ICTV Report 章节正文的图号（分布：Fig3 ×15、Fig4 ×13、Fig5 ×3、
   Fig2 ×3、Fig6 ×2、Fig1 ×1、无编号 ×1）。叶集合**既不等于该科的物种表，也不限于该科**：

| 现象 | 实测 |
|:---|:---|
| 叶数远少于物种数 | `Geminiviridae` 560 物种 / 树上仅 **29** 叶；`Closteroviridae` 88 / 52 |
| 叶是**片段**而非全长基因组 | `Rhabdoviridae` 三棵树分别 688 bp / 1,612 bp / 1,207 bp |
| 叶是**基因区或蛋白** | `Alphaflexiviridae` Fig3 是 `replicase` 区；`Aspiviridae` Fig3 是蛋白登录号 |
| 叶是**别的科的病毒** | `Virgaviridae` Fig6 含 CMV（Cucumovirus）、BMV（Bromovirus）—— 二者均属 `Bromoviridae`，此处作外群 |
| 叶名与分类无关 | `Metaviridae` / `Pseudoviridae` 叶名是 `Gmr1` / `rGmr1` 这类转座子元件名 |

**跨科登录号复用（可复现的判据）**：按 `build_family_index.py` 的 `ACC_RE`
（`[A-Z]{2,3}[0-9]{5,6}`，在标签内任意位置 `findall`）统计，**3,341 个叶**中共得
**1,863 个不同登录号**，其中 **37 个同时出现在不同科的树里**。例如 `AF278535`、`AJ272328`
（Bromoviridae Fig4 ↔ Virgaviridae Fig6）、`KX272883`（Konkoviridae Fig4 ↔ Phenuiviridae Fig2）、
`DQ352194`（Kitaviridae Fig3 ↔ Virgaviridae Fig6）、`AB976029`（Benyviridae Fig4 ↔ Virgaviridae Fig1/2/6）。

> **口径更正（2026-09-22）**：分子（1,863 / 37）**没变** —— 空叶本来就没有名字，不参与计数；
> 但**分母**从 3,904 改成 3,341，所以「1,863 只占叶总数的 48%」**→ 55.8%**。
> 另外提醒：`ACC_RE` 要求字母后**直接**跟数字，**匹配不到 `NC_018616` 这类带下划线的 RefSeq 登录号**，
> 所以这个口径天然偏低，37 仍然是下界。

> **结论**：「科的标签」在这批数据里的含义是**「哪一章发表了这张图」**，不是「叶都属于这个科」。
> 因此任何按科命名/分组的展示都必须显式标注口径，否则会把跨科外群当成该科成员展示。
> 若确实需要「全科物种树」，ICTV 数据本身给不了，只能自己建（MAFFT → IQ-TREE）。

## M5. 前端实现要点

- **枝长树（phylogram）**：ECharts `lines`（`polyline: true`）+ `scatter`，在 `cartesian2d`
  里用**累积枝长**定位 x、叶序定位 y，画直角折线边 —— 不是 ECharts `tree` 那种等距拓扑图。
  `grid` 撑满画布、`xAxis/yAxis` 隐藏，使数据坐标 1:1 等于像素坐标。
- **支持度过滤**：滑块低于阈值的内部分支合并为 `[N sequences]` 单点；无支持度的节点一律保留。
- **环形视图**：ECharts `tree` + `layout: 'radial'`，可滚轮缩放。末端名长，ECharts 会给标签
  留空间把树压小，因此**只在末端 ≤ 20 时才默认显示标签**。
  （注意：`series-tree.zoom` 是绕左上角缩放的，直接调大会把树推出画面，不要用。）
- **末端标签清洗**：只清洗**显示用**短标签（去掉登录号、`replicase`、`complete genome`、
  `isolate XXX` 等套话）；tooltip 与详情面板始终给原始全名。

## M6. 重建全流程

```bash
cd docs/phylo
python fetch_ictv_trees.py --discover && python fetch_ictv_trees.py --download
python build_molecular.py
python build_family_index.py      # -> molecular/families/family_index.json
python build_genus_map.py         # -> molecular/genus_map.json（按属着色用，见 M12）
```

> `build_genus_map.py` **只读** `molecular_trees.json` 与 `data/VMR_MSL41.txt`，
> 不修改任何已验收产物；它自带口径断言（tips=3341 / mapped=2199），对不上就拒绝写出。

## M7. URL 参数

| 参数 | 取值 | 说明 |
|:---|:---|:---|
| `family` | 科名 | 预选科 |
| `tree` | 树 id（`科名\|FigN`） | 预选树 |
| `mode` | `phylo` / `radial` | 枝长树 / 环形 |
| `sup` | `0`–`100` | 支持度阈值 |
| `bl` | `0` | 关闭枝长比例（退回等距） |
| `q` | 关键词 | 高亮命中末端 |

示例：`/phylo/molecular/?family=Rhabdoviridae&sup=80`

## M8. 按科索引页（`/phylo/molecular/families/`）

### 为什么要有这一页

`/phylo/molecular/` 把 25 个科的树塞在一个下拉框里，单科没有独立入口、也没法单独分享。
索引页给每个科一张卡，卡片本身就是「单科独立展示」的入口，点进去落到查看器并带上深链参数。

### 数据构建

`build_family_index.py` **只读** `molecular_trees.json`（已交付并线上验证过的产物），
另出一份派生的 `molecular/families/family_index.json`（~106 KB）。**不要**为了这页去改
`molecular_trees.json`。

每科的字段：`nTrees` / `leaves` / `internals` / `binaryTrees` / `treesWithSupport` /
`supportCoverage` / `blMax` / `crossAcc` / `fragN` / `phN` / `mslSpecies` / `mslGenera` /
`genomes` / `leafToSpecies` / `trees[]`。

### 缩略图（sparkline）

每棵树降采样成一条 `viewBox="0 0 100 34"` 的 SVG path：

- x 用**拓扑深度**而非枝长 —— 缩略图只看形状，不按比例，这样不同树可以并排比较；
- 叶数超过 `SPARK_TIPS=48` 时，把每个小分支塌缩成一根竖笔，path 长度控制在 O(48)；
- 渲染时配 `preserveAspectRatio="none"` + `vector-effect="non-scaling-stroke"`，
  横向拉伸填充卡片但线宽保持 1px；
- 38 棵树的 path 合计约 90 KB，直接内联在 JSON 里，前端不做二次布局。

### 卡片上的数据质量标记

四个标记都是**实测**出来的，不是装饰：

| 标记 | 判据 | 命中 |
|:---|:---|:---|
| 无支持度 | `treesWithSupport === 0` | Metaviridae、Pseudoviridae、Phenuiviridae、Secoviridae |
| 占位符叶名 | `phN > 0`（三种写法都匹配，见 M4-2） | Potyviridae 25、Kitaviridae 13、Botourmiaviridae 10、Secoviridae 9、Bromoviridae 1 |
| 含跨科序列 | `crossAcc > 0` | Konkoviridae 19、Phenuiviridae 18、Virgaviridae 17、Benyviridae 13、Alphaflexiviridae 3、Kitaviridae 3、Bromoviridae 2、Fimoviridae 1 |
| 片段非全长 | 过半叶名带 `\d+_bp` | Rhabdoviridae（1,077 / 1,077） |

`leafToSpecies` 只是描述性的：`< 0.5` 标「叶数 ≪ 物种数」，`> 2` 标「叶数 ≫ 物种数」。
**它不能当覆盖率读** —— 分子那边是序列/株系/片段，分母是物种，口径不同。

### nginx

**不需要新增 location**。父级 `/phylo/molecular/` 用的是 `root` 而非 `alias`，
所以 `/phylo/molecular/families/` 天然被它匹配，`try_files $uri $uri/` 会落到子目录的
`index.html`。这也正是当初把分子树页从 `alias` 改成 `root` 的附带好处（见第 7 节）。

## M9. 自建树：可行性已实测（参数待定）

### 为什么要自建

ICTV 的树是章节插图（M4-4），覆盖不全。要「全科物种树」只能自己建 —— GPI 的
520 条 Geminiviridae 树就是这么来的（其 Links→Softwares 列着 MAFFT / RAxML-ng / IQ-TREE）。

### 工具链与资源（实测）

| 环境 | MAFFT | IQ-TREE | 其他 |
|:---|:---|:---|:---|
| 本地 Windows | **无** | **无** | 无 |
| **服务器 `39.106.101.94`** | **v7.525** | **3.1.3** | `trimal`、`seqkit` 2.13.0 |

> **建树只能在服务器上跑**（本地一个都没有）。
> 服务器规格：**2 vCPU / 3.5 GB 内存 / 磁盘余 12 GB（77% 已用）** ——
> 这是自建树的真正瓶颈，不是算法。用 `nice -n 19` 可保证网站仍正常响应
> （实测 `/` 0.69 s、`/phylo/molecular/families/` 0.19 s）。

#### 内存是硬约束：Caulimoviridae 105 条在 3.5 GB 机器上跑不过去（实测）

输入固定：`work/Caulimoviridae.fa`，105 条 × 6,450..9,872 bp，共 **812 kb**。

| # | 配置 | 结果 | 峰值 RSS | 墙钟 |
|:--|:---|:---|---:|---:|
| 1 | `--auto`（→ L-INS-i） | 内核 OOM 杀 `disttbfast`，`.aln` 留 0 字节 | 2.92 GB | ~6 min |
| 2 | `--retree 2 --maxiterate 0 --6merpair` + `ulimit -v 2200000` | MAFFT 自报 `Allocation error( 21210 int vec )` | 1.70 GB | 4:31 |
| 3 | 同上但**去掉** `ulimit` | 内核 OOM 杀 `disttbfast` | **2.93 GB** | 8:29 |
| 4 | 加 `--parttree --partsize 30` | **参数被静默忽略**，与 #3 同样被杀 | 2.93 GB | — |

第 4 条的证据：`--parttree --partsize 30` 下 `disttbfast` 的调用参数与不加时**逐字相同**
（`-q 0 -E 2 -V -1.53 -s 0.0 -W 6 -O -C 2-2 -b 62 -g 0 -f -1.53 -Q 100.0 -h 0 -F -X 0.1 -x 100`），
MAFFT 7.525 既没报错也没改变行为。

#### 真正的根因：内存由**序列长度**主导，不由条数主导

固定 N=11 条（`seqkit sample -s 42`），只改长度：

| 截取长度 | 峰值 RSS | 墙钟 |
|---:|---:|---:|
| 1,000 bp | **39 MB** | <1 s |
| 2,500 bp | **102 MB** | 4 s |
| 5,000 bp | **265 MB** | 34 s |

长度 2×（2,500→5,000）→ 内存 2.6×、时间 8.5×。而 105 条**全长**（平均 7,735 bp）要 **2.93 GB**。

> **所以内存墙不是「105 条太多」，而是「每条 7.8 kb 太长」。**
> 截到 1 kb 时 11 条只要 39 MB —— 差 75 倍。
> 换句话说：**改比对保守区（如 ~1.5 kb 的 RT/RNase H）而不是全长基因组，
> 这台服务器就能轻松跑完。**

> **2026-09-22 这条已被证实，而且原因比"省内存"更严重 —— 是「输入区域选错了」。**
> ICTV 为每棵树**同时发布了背后的比对文件**（`ictv_raw/manifest.json` 里 `kind:"align"`，
> 42 个比对 vs 38 棵树；比对条目**没有 `local` 字段**，当初漏下了）。
> 补下 `ORTD.Caulimo.Fig4.v9_align.txt` 一看：**108 条 / 1,674 列 / 每条去间隙 1,158–1,512 bp
> （中位 1,227）/ 间隙率 26.6%**，只占全长基因组的 **16–21%**，位置在 ORF3 的 RT/RNaseH 区。
> **ICTV 用的是保守区，我们用全长，所以树根本不可比。**
>
> **勘误**：这里初版写的「1,194–1,227 bp / 15–17%」是错的（把中位数当成了上界）。
> 真值见 `work/measure_ictv_aligns.py` 的可复算输出。
>
> **而且这不是个例** —— 把 manifest 里 42 条 `kind:"align"` 里的 19 条补下逐条量过之后：
> **10/19 是氨基酸（蛋白）比对**，9/19 是核苷酸；核苷酸那些只覆盖基因组的 **7–54%**。
> 文件名直接写着区域（`Replicase.aa` / `Capsid.aa` / `RdRP` / `CP`）。
> 全部结果见 **M11** 与 `work/ictv_align_survey.md`。
>
> 用长度代理实测（105 条各截到 1,200 bp，同机同参数）：
>
> | 输入 | 线程 | 峰值 RSS | 墙钟 |
> |:---|---:|---:|---:|
> | 全长 7,735 bp | 2 | 2.93 GB | 8:29（服务器 OOM） |
> | 全长 7,735 bp | 20 | 12.4 GB | 10:55 |
> | **1,200 bp** | **2** | **269 MB** | **26 s** |
> | **1,200 bp** | 20 | **965 MB** | **12.5 s** |
>
> **269 MB / 26 秒 —— 那台 2 核 3.5 GB 的服务器完全跑得动。**
> "必须换机器"是输入选错造成的假象。详细证据见 `work/REPRODUCE.md` 第 8 节。
> 唯一遗留问题：本地库**没有 CDS 坐标**（`Plant_Virus_Full.Info.tsv` 只有
> `Family`/`Segment`/`Length` 等，无起止位点），取区域要先定方法（属判定语义）。

内核日志（第 3 次）：

```
[Tue Sep 22 01:24:10 2026] Out of memory: Killed process 2933508 (disttbfast)
  total-vm:3735580kB, anon-rss:2931724kB
oom-kill:constraint=CONSTRAINT_NONE,...,global_oom
```

**三个被实测推翻的想当然**：

1. ~~`--6merpair` / FFT-NS-2 能降内存~~ —— **不降**。第 3 次 2.93 GB 与第 1 次
   L-INS-i 的 2.92 GB 几乎相同。瓶颈不在引导树距离算法上。
2. ~~`ulimit -v` 是合适的内存护栏~~ —— **不是**。它限的是**虚拟地址空间**，
   而多线程 glibc 会预留大量从未触碰的地址空间（线程栈 / malloc arena / mmap 缓冲）。
   第 2 次在 **RSS 只有 1.70 GB** 时就报 `Allocation error( 21210 int vec )`
   —— 连 85 KB 的小向量都申请不到，**是被护栏误杀，不是内存不够**。
3. ~~`systemd-run -p MemoryMax=` 可以兜底~~ —— **在这台机器上不生效**。
   实测 `MemoryMax=300M` 下成功分配了 600 MB（systemd 239 / cgroup v1，
   memory 控制器未接管）。**本机没有可用的内存硬限。**

**两点必须知道的运维事实**：

- 三次 OOM，内核**每次都挑 `disttbfast`**（oom_score 最高）当受害者，线上站点三次
  都活着（`/` 200 / 0.003 s）。**这是运气，不是设计** ——
  `constraint=CONSTRAINT_NONE` + `global_oom` 意味着受害者由 oom_score 决定，
  换个负载组合就可能轮到 gunicorn。
- 看门狗（每 5 秒采样，>2.4 GB 即杀）**没来得及触发**：MAFFT 一次 realloc 就从阈值下
  冲到 2.93 GB，采样间隔太粗。要用就得更高频，或干脆靠 cgroup。

> **所以：这台 2 vCPU / 3.5 GB 的机器不适合做「105 条 × 8 kb 级」的比对。**
> 它是 web 服务器，不是计算节点。建树应当在别处算完，再把结果作为静态数据部署。

#### 那在哪里算？本机 WSL 就够（实测）

老师这台机器（Windows）实测规格：

| 环境 | 核数 | 可用内存 | MAFFT | IQ-TREE |
|:---|---:|---:|:---|:---|
| 服务器 `39.106.101.94` | 2 | 3.5 GB | v7.525 | 3.1.3 |
| **本机 WSL `Ubuntu-24.04`** | **20** | **31 GB** | 无（需装） | 无（需装） |
| 本机 Windows（Git Bash） | 20 | 63.8 GB | 无 | 无 |

**内存 9 倍、核数 10 倍**，且 WSL 里 `/mnt/d/桌面/C-host_classify/plant_virus_db_pipeline`
直接可见。2.93 GB 的需求放进去毫无压力。

好消息是**项目自己的 `pixi.toml` 已经声明了 `mafft = ">=7.520"`（`target.linux-64.dependencies`）**，
WSL 是 linux-64，装个 pixi 就能直接 `pixi install` 复用，不需要额外找二进制。

> **注意 bioconda 的 `mafft` 不支持 win-64**（只有 `linux-64` / `osx-64` / `linux-aarch64`），
> 所以**不能在 Windows 侧 `pixi add mafft`** —— 必须走 WSL。IQ-TREE 同理。

**这一步没有做**（在老师机器上装环境属于外部动作，等您定）。




### 序列库

`docs/data/Plant_Virus.complete_ref.fasta`（26 MB，**5,773 条**）+
`Plant_Virus.complete_ref_info.tsv`（含 `VMR_Family` / `VMR_Genus` / `VMR_Species` /
`Segment` / `Nuc_Completeness` / `Length` / `Sequence_Type`）。
FASTA 头是**裸登录号**，与 info 表的 `Accession` 一一对应，可直接 join。

### 四个必须先处理的坑（`build_own_trees.py --audit` 实测）

1. **`Segment` 字段对同一件事有十几种写法**。Geminiviridae 实测：
   `DNA-A` / `DNA A` / `A` / `A component` / `component A` **都是 A 组分**；
   `DNA-B` / `DNA B` / `B` / `B component` / `component B` **都是 B 组分**。
   **不归一会把 A 和 B 混进同一个 alignment —— 而它们是不同的分子。**
   脚本用 `norm_segment()` 归一，并把**无法归类的写法打印出来**而不是静默丢弃
   （实测报出 `1` `I` `S` `M` `L` 等，均为真实存在的其他分体命名）。
2. **11 个科没有单分体序列**，必须按组分/片段拆开分别建树：
   `Fimoviridae` `Bromoviridae` `Tospoviridae` `Nanoviridae` `Phenuiviridae`
   `Kitaviridae` `Partitiviridae` `Aspiviridae` `Sedoreoviridae` `Konkoviridae` `Mayoviridae`
3. **8 个科的长度跨度 > 3×**，说明库里混着基因区与全长基因组，必须按长度筛，
   否则是把苹果和橘子放一起 align：
   `Potyviridae`(1,479..11,519) `Betaflexiviridae` `Solemoviridae` `Tospoviridae`
   `Tombusviridae` `Phenuiviridae` `Alphaflexiviridae` `Kitaviridae` …
4. **物种标注列选错了会得出完全相反的结论**（这一条是踩过坑才补上的，见下）。
   `VMR_Species` 全库只有 **14.7%（850/5773）** 有值，`Species_ICTV` 是 **100%**。
   用 `VMR_Species` 数物种，会把 `Caulimoviridae` 数成 14 个（实际 105 个）。
   所有物种计数一律走 `species_key()`。

### 物种覆盖：不是「不够」，是「标注稀疏」

**这一节我上一版写错了，更正如下。**

上一版用 `VMR_Species` 数物种，得出「Caulimoviridae 只有 14 个物种 / MSL 109」
「Geminiviridae 120 / 560」，并据此判定「本地库建不出全科物种树」。

**错在选错了列。** 实测填充率：

```
VMR_Species    非空   850 / 5773  (14.7%)   <- 上一版用的就是它
Species_ICTV   非空  5773 / 5773  (100.0%)
Species_NCBI   非空  5773 / 5773  (100.0%)
VMR_Genus      非空  4116 / 5773  (71.3%)   <- 所以有 1657 条没有科归属
```

按 `Species_ICTV` 重算，本地库的覆盖其实**相当高**：

| 科 | MSL41 物种 | 本库物种 | 覆盖 |
|:---|---:|---:|---:|
| Pospiviroidae | 40 | 39 | 98% |
| Caulimoviridae | 109 | 105 | 96% |
| Fimoviridae | 33 | 31 | 94% |
| Bromoviridae | 52 | 49 | 94% |
| Alphaflexiviridae | 73 | 67 | 92% |
| Betaflexiviridae | 159 | 144 | 91% |
| Solemoviridae | 148 | 128 | 86% |
| Tombusviridae | 102 | 85 | 83% |
| Tolecusatellitidae | 133 | 111 | 83% |
| Tospoviridae | 36 | 30 | 83% |
| Potyviridae | 264 | 207 | 78% |
| Alphasatellitidae | 93 | 72 | 77% |
| Tymoviridae | 43 | 32 | 74% |
| Closteroviridae | 88 | 56 | 64% |
| Virgaviridae | 59 | 35 | 59% |
| Geminiviridae | 560 | 197 | **35%** |
| Rhabdoviridae | 615 | 90 | **15%** |

> **结论要改**：本地库对**多数植物病毒科已接近物种完整** —— 10 个科 ≥80%，
> 17 个科 ≥50%。这些科可以直接建「近全科物种树」，不需要另取序列。

覆盖不足、需要另从 NCBI GenBank 取序列的是少数几个大科：

| 科 | MSL41 | 本库 | 缺口 |
|:---|---:|---:|---:|
| Rhabdoviridae | 615 | 90 | 525 |
| Geminiviridae | 560 | 197 | 363 |
| Atkinsviridae | 262 | 0 | 262 |
| Phenuiviridae | 223 | 23 | 200 |
| Secoviridae | 215 | 18 | 197 |
| Botourmiaviridae | 150 | 1 | 149 |

> GPI 的 520 条 Geminiviridae 正对应这里的缺口（本库只有 197）。要补齐只能另取，
> 且需先定口径（全部 GenBank / 只要 RefSeq / 按物种去冗余）—— 这一步**没有做**，
> 等老师定。

#### `species_key()` 是启发式，不是权威物种表

`VMR_Species` 与 `Species_ICTV` **不是同一个命名空间**：850 个非空 `VMR_Species`
里只有 **62.1%（528）** 与 `Species_ICTV` 相同，其余 37.9% 的 `Species_ICTV`
装的是 NCBI 常用名。实测例：

```
LC625373.1   VMR_Species='Caulimovirus tessellodahliae'  Species_ICTV='Dahlia common mosaic virus'
NC_018616.1  VMR_Species=''                              Species_ICTV='Caulimovirus tessellodahliae'
```

两条其实是**同一物种的两个分离物**（Dahlia common mosaic virus 的 ICTV 名就是
`Caulimovirus tessellodahliae`），所以按 `species_key()` 合并是**正确**的。
全库去重得 3,505 个物种键，比单用 `Species_ICTV` 的 3,521 少 16，即合并掉 16 个重复。

> 计数可以信；但**不要把它当权威物种名录对外发布**，物种数一律以 MSL41 为准。


### 建议建树清单（≥50% 覆盖且 ≥8 条：17 个科 / 1,212 条序列）

口径：`--complete-only --derep-species`，有单分体的直接建；无单分体的按组分拆、取最大组分。

| 科 | MSL41 | 建议条数 | 覆盖 | 比对规模 | 建法 |
|:---|---:|---:|---:|---:|:---|
| Pospiviroidae | 40 | 39 | 98% | 0.01 M | 单分体直接建 |
| Caulimoviridae | 109 | 104 | 95% | 0.80 M | 单分体直接建 |
| Nanoviridae | 15 | 14 | 93% | 0.01 M | 拆组分（最大 M，共 11 组分） |
| Alphaflexiviridae | 73 | 67 | 92% | 0.46 M | 单分体直接建 |
| Betaflexiviridae | 159 | 144 | 91% | 1.14 M | 单分体直接建 |
| Fimoviridae | 33 | 29 | 88% | 0.04 M | 拆组分（最大 4，共 13 组分） |
| Bromoviridae | 52 | 45 | 87% | 0.13 M | 拆组分（最大 2，共 3 组分） |
| Solemoviridae | 148 | 128 | 86% | 0.71 M | 单分体直接建 |
| Tolecusatellitidae | 133 | 111 | 83% | 0.14 M | 单分体直接建 |
| Tombusviridae | 102 | 85 | 83% | 0.36 M | 单分体直接建 |
| Potyviridae | 264 | 207 | 78% | **2.00 M** | 单分体直接建 |
| Tospoviridae | 36 | 28 | 78% | 0.09 M | 拆组分（最大 S，共 5 组分） |
| Alphasatellitidae | 93 | 72 | 77% | 0.09 M | 单分体直接建 |
| Tymoviridae | 43 | 32 | 74% | 0.20 M | 单分体直接建 |
| Closteroviridae | 88 | 56 | 64% | 0.91 M | 单分体直接建 |
| Virgaviridae | 59 | 35 | 59% | 0.22 M | 单分体直接建 |
| Endornaviridae | 31 | 16 | 52% | 0.23 M | 单分体直接建 |

**合计 1,212 条序列 / 7.6 M字符。** 注意 Potyviridae 与 Closteroviridae 长度跨度极大
（1,479..11,519 与 12,971..21,087），**必须先定长度窗口**再建，否则混着基因区与全长。

> 这个清单**只是建议，未执行**。要建哪些科、长度窗口取多少、`--retree 2` 还是 `--auto`，
> 都是判定语义的选择，等老师定。

### 用法

```bash
python build_own_trees.py --audit                       # 只报告，不改任何东西
python build_own_trees.py --family Caulimoviridae --segment mono --complete-only \
       --out work/Caulimoviridae.fa
```

输出 FASTA + `<out>.manifest.tsv`（含每一步筛选的条数与每条序列的归属，即**可复现记录**）。
本地与服务器跑出的 FASTA 与 manifest **MD5 完全一致**，说明选择过程是确定性的。

建树命令（**在大内存机器上执行**；服务器上跑不过去，见上）。
**实测可行的是三段式：比对 → 修剪 → 建树** —— 中间那步不能省（理由见下）：

```bash
# 不要加 ulimit -v —— 它限虚拟地址空间，会远早于真实内存压力就报分配失败
# ① 比对：全长基因组差异大，L-INS-i 会过度插空，先跑出来再修剪
mafft --auto --thread 20 work/Caulimoviridae.fa > work/Caulimoviridae.fa.aln

# ② 修剪：实测原始比对 26,163 列 / 70.4% 间隙（序列才 ~7.7 kb，膨胀 3.4 倍），
#    不修剪直接建树不可信。两种模式给的列集合不同，是判定语义的选择：
trimal -gappyout    -in work/Caulimoviridae.fa.aln -out work/Caulimoviridae.trim_gappyout.fa
trimal -automated1  -in work/Caulimoviridae.fa.aln -out work/Caulimoviridae.trim_automated1.fa

# ③ 建树（种子与自举次数写死，保证可复现）
iqtree -s work/Caulimoviridae.trim_automated1.fa \
       -m MFP -B 1000 --seed 42 -T 20 -pre work/Caulimoviridae.trim
```

实测数据（105 条 Caulimoviridae，WSL 20 核 / 31 GB）：

| 步骤 | 结果 |
|:---|:---|
| ① MAFFT `--auto --thread 20` | rc=0，峰值 RSS **12.4 GB**，墙钟 **10:55**，比对 2,747,115 字符 / 26,163 列 / **70.4% 间隙** |
| ② `trimal -gappyout` | 5,231 列 / 8.8% 间隙 |
| ② `trimal -automated1` | 3,955 列 / 7.6% 间隙 |
| ③ ModelFinder | 968 个模型，最佳 **GTR+F+R8**（AIC / AICc / BIC 三者一致），CPU 6h26m / 墙钟 **19:45** |

> 注意 RSS 随**线程数**也增长：同一条数据 2 线程 2.93 GB、20 线程 **12.4 GB**（线程缓冲区是复制的）。

> **参数选择纪律**：`--segment` / `--complete-only` / `--min-len` / `--derep-species`
> 这些都是**判定语义的选择**，会影响结果。默认全部不启用，由使用者显式指定，
> 并完整写进 manifest。
>
> 同理，`--retree 2 --maxiterate 0 --6merpair` 也是**质量换内存**的选择 —— 但实测它
> **并不省内存**（见上表 #1 vs #3）。换到内存足够的机器上应当回到 `--auto`（L-INS-i）。
> 这个取舍由老师定。


### 渲染（不经浏览器看图）

`render_tree_svg.py` 把 Newick 渲成独立 SVG（x = 累积枝长，y = 叶 DFS 序）：

```bash
python render_tree_svg.py --tree work/Caulimoviridae.treefile \
       --out work/Caulimoviridae.svg --manifest work/Caulimoviridae.manifest.tsv
```

加 `--manifest` 时按 `VMR_Genus` 着色并出图例。已用 ICTV 的
`Geminiviridae/OSD.Gem.Fig3.v3.treefile.txt` 做过三重校验：

| 校验 | 方法 | 结果 |
|:---|:---|:---|
| 跨解析器一致 | 与 `build_molecular.py` 的解析结果对拍 | leaves 29 / internals 27 / maxDegree 3 / blMax 0.639139 / supportN 26 —— **5/5 相同** |
| 几何自洽 | 三条独立恒等式（见下） | 叶圆点 29 = 叶数；竖枝 27 = 内部节点数；横枝 55 = 节点总数 56 − 1。零越界、零非有限坐标 |
| 语义自洽 | 只画支持度 <95 的标签 | 26 个支持度中 6 个 <95，SVG 里红色标签正好 6 个 |

> **2026-09-22 修了一个解析 bug**：`split_parts()` 原先把**纯数字的叶名**也当支持度，
> 于是 ICTV 树里 `297`、`17.6`、`1731`、`412`、`0.16690164` 这些叶名被吞掉（共 4+4+1 条）。
> 现在按 `split_parts(parts, is_leaf)` 区分：**叶的标签一律整串当名字**，只有内部节点才可能是支持度。
> 修复后与 `build_molecular.py` 在 38 棵 ICTV 树上全量对拍 **38/38 一致**。

> **2026-09-22 更正一处算术**：上面「几何自洽」原先写作
> 「竖枝 27 + 横枝 55 = 82 = 56 − 1」—— **82 ≠ 55，这个恒等式是错的**。
> 正确的三条独立恒等式是：**叶圆点数 = 叶数**、**竖枝数 = 内部节点数**、
> **横枝数 = 节点总数 − 1**（每条边一条横枝）。竖枝与横枝相加没有意义。
> 已按此重新核验，两条都成立。


## M10. 树体检（`check_tree.py`）

自建树跑完不能凭「看起来像一棵树」就交付。`check_tree.py` 是只读体检工具，退出码 0/1 便于批量跑：

```bash
python check_tree.py --tree work/Caulimoviridae.trim.treefile \
                     --manifest work/Caulimoviridae.manifest.tsv \
                     --ref ictv_raw/Caulimoviridae/ORTD.Caulimo.Fig4..v9_treefile.txt
```

三项检查：

1. **结构统计** —— 叶数 / 内部节点数 / 最大度 / 枝长范围（含**负枝长**告警）/ 支持度分布。
   叶数必须等于输入序列数，否则比对阶段就丢了序列。
2. **属的单系性（主要判据）** —— ICTV 分类假定每个属都是单系群，所以「单系率」是
   「树可不可信」的可证伪检验量。不单系的属会报告**最小包含枝**多出多少条、混进了哪些属。
3. **与 ICTV 已发表树对拍**（`--ref`，可选）—— 按登录号取交集，比较非平凡枝（clade）集合的
   Jaccard 一致率，并**显式打印交集大小**。

两道护栏（都是踩过坑加的）：

- **只在「有属名」的叶之间判单系性**。第一版直接在整棵树上判，拿只有 12/108 条有属名的
  ICTV 图去测，把本来单系的 `Badnavirus` 误报成「最小包含枝多 61 条」。
  现在先 `prune()` 剪到有属名的叶再判，并打印「参与判定的叶 N / M」。
- **映射率 <50% 时明确声明「本条不作判据」**，退出码不置 1。

自检：`--tree X --ref X` → 非平凡枝 Jaccard **100.0%**（对拍逻辑自洽）。

> **那个 60% 的线是本脚本自定的参考线，不是权威标准**，只用来把「明显是噪声」和
> 「需要人工看」分开。判定口径应由老师定，输出里也写明了这一点。

## M11. ICTV 官方比对用了多大区域（`measure_ictv_aligns.py`，19 个科实测）

### 为什么要有这一节

M9 里「ICTV 用保守区、我们用全长」这条结论，**初版证据只有 Caulimoviridae 一个科**。
一个科撑不起一条通用结论 —— 万一是这个科的特例呢。于是把 manifest 里 42 条
`kind:"align"` 中能下到的 19 条全部补下逐条量了一遍。

> **顺带说明为什么当初全漏了**：`manifest.json` 里 `tree` 条目都带 `local` 字段（38/38），
> 而 `align` 条目**一个都没有**（0/42）。按 `local` 判断"下没下过"就会把它们全部跳过。

### 用法

```bash
python work/measure_ictv_aligns.py                       # 打印表格
python work/measure_ictv_aligns.py --md work/ictv_align_survey.md   # 同时写出 md
```

### 结果

| 项 | 数值 |
|:---|:---|
| 实测 | 19 / 42 条 |
| **氨基酸（蛋白）比对** | **10 条** |
| 核苷酸比对 | 9 条 |
| 核苷酸比对覆盖基因组 | **7% – 54%** |
| 间隙率 | 0% – 53.6%，中位 **26.6%** |
| 对照：本库全长 Caulimoviridae | 26,163 列 / **70.4%** 间隙 |

**类型判据是自证的**：按 A/C/G/T/U 占非间隙字符的比例判定，结果**完全双峰** ——
核苷酸一律 **100.0%**、蛋白 **17.4%–27.3%**，**中间没有任何样本**。
所以"是蛋白还是核苷酸"不是主观判断。

> 注意：不能用"是否出现 `RYSW`"来判断核苷酸 —— 这些既是 IUPAC 简并码
> （R=A/G、Y=C/T、S=G/C、W=A/T），也是蛋白里的 Arg/Tyr/Ser/Trp。
> 只能用"**只有蛋白才有**的字母"（`E F I L P Q Z J O X`）加占比兜底。

文件名直接写着区域，不需要额外推断：

```
Alphaflexiviridae Fig3  Replicase.aa   → 复制酶（蛋白）
Alphaflexiviridae Fig4  Capsid.aa      → 衣壳蛋白
Solemoviridae    Fig3A  RdRPalignment  → RdRP
Solemoviridae    Fig3B  CPalignment    → 外壳蛋白
```

### 反例：别把结论说过头

**Potyviridae Fig3 不是"一小段保守区"，而是整个多聚蛋白**：
3,084 aa（中位）、**GDD 聚合酶催化基序 208/208 条全有**、KITC（HC-Pro）64/208，
3,084 × 3 = 9,252 nt ≈ 该科完整基因组中位 9,736 nt 的 **95%**。

所以准确表述是：

> **ICTV 比对的是「同源编码区」，而且常常以氨基酸形式 —— 不是全长的核苷酸基因组。**
> 这个区域可能很小（Caulimoviridae 的 RT/RNaseH，占基因组 16–21%），
> 也可能几乎覆盖全部编码区（Potyviridae 的多聚蛋白，占 95%）。

**因此 M9 的配方要按科分别定**，不是一律"截一小段"，而是"截到该科建树所用的那个同源编码区"；
Potyviridae 这类建议**直接在氨基酸层面**做。

### M11.2 保守区坐标怎么取（`derive_region_coords.py`）

M9 的第 ① 步曾**卡住**：本地库 `Plant_Virus_Full.Info.tsv` **只有 Family/Segment/Length，
没有 CDS 坐标**，无从知道"截哪一段"。

**实测结论：不需要注释文件。** 方法一句话：

> ICTV 比对里每条序列，本来就是从该科全长上**截下来的那一段**。
> 把比对序列去掉间隙后，在库内对应全长上做**精确子串匹配**，匹配到的区间就是坐标。

ICTV 自己就是这么截的，所以匹配**精确**，不需要比对或容错；匹配不上再试反向互补链。

```bash
python work/derive_region_coords.py --family Caulimoviridae --md work/region_coords_Caulimoviridae.md
python work/derive_region_coords.py --family Virgaviridae \
    --align ictv_raw/Virgaviridae/OPSR.Virga.Alignment.Fig3.v1.fst
```

| 科 | ICTV 比对 | 命中 | 区间中位 | 占全长 | 起点范围 |
|:--|:--|--:|--:|:--|:--|
| Caulimoviridae | Fig4（108 条） | **104 / 108** | 1,227 bp | **16.2%**（12.1–19.0%） | 2,728 – 7,050 |
| Virgaviridae | Fig3（57 条） | **54 / 57** | 466 bp | **7.3%**（6.8–31.2%） | 90 – 6,126 |
| Geminiviridae | Fig3（29 条） | 19 / 29 | 2,861 bp | **100.0%** | 1 – 1 |

**两个必须注意的点**：

1. **不能全科硬编码一个窗口。** Caulimoviridae 起点范围 2,728–7,050 ——
   都落在 ~16% 的位置，但**绝对坐标差异很大**（各属基因组结构不同）。
   必须**逐条推导**，不能写死 `subseq -r 5223:6449`。
2. **Geminiviridae 是反例**：那里 ICTV 用的是**全长组件**（区间 100%、起点全是 1）。
   再次印证 M11 的结论 —— **取哪个区域是按科定的，没有通用规则。**

**已知限制**：按登录号查找会漏掉"ICTV 用原始 GenBank 号、本库是 RefSeq"的情形
（Geminiviridae 9/29 条因此未匹配，如 `X15656` vs 库内 `NC_*`）。
补法是再加一层按物种名的模糊匹配，本次未做。

**对建树的意义**：M9 的第 ① 步**从"需要定方法"变成"方法已验证，只需定用哪个区域"**；
若决定"照抄 ICTV 的区域"，则直接用本脚本输出即可。


## M12. 按属着色（`build_genus_map.py` → `molecular/genus_map.json`）

### 为什么需要它

**ICTV 分子树的叶没有分类阶元。** 38 棵树的叶标签只有登录号、基因/片段缩写、毒株别名
（比对文件的序列头是同一套写法，**没有额外信息**）—— 所以页面上"科下面看不到属"不是渲染漏了，
而是**数据源里根本没有**。

> ICTV 也没有随树发布补充表格。某些树里出现 `ACCESSION NOT ON SPREADSHEET`，
> 指的是**章节作者自己的私有 Excel**，不是公开资源。

属要另配。全站有属的地方只有两处：`families/` 卡片的 `Genera (MSL)`，和 `/phylo/`（genus 214）。

### 映射方法

来源 = `data/VMR_MSL41.txt`（19,271 行）的两列：`Virus name abbreviation(s)`（8,653 键）
与 `Virus GENBANK accession`（23,249 键）。**这两列在 `MSL41_species.tsv` 里没有。**

对每个叶标签依次尝试三条路，**每一步都必须过「科约束」**：

1. 登录号（含版本号剥离与 `NC116488`→`NC_001410` 补零归一）
2. 通用毒名（长名优先）
3. 缩写（按词切，**不能整串子串匹配**）

```bash
python build_genus_map.py            # -> molecular/genus_map.json
```

### ⚠️ 硬规则：必须按科约束

缩写表是**全局**的。不约束科就会跨科错标 —— 实测抓到：

| 缩写 | 无约束错标 | 实际所在科 |
|:--|:--|:--|
| `SCRV` | `Orbivirus`（Reoviridae） | Rhabdoviridae 的叶 |
| `MaYMV` | `Begomovirus`（Geminiviridae） | 非 Geminiviridae 的叶 |

**判定一个属是否接受，看它的科是否等于这棵树的科。** 已复核：**3,265 个属没有一个是跨科的**，
所以这个过滤器干净、不会误杀合法映射。

| 口径 | 覆盖率 |
|:--|--:|
| 不约束科 | 70.1%（**数字好看但是错的**） |
| **按科约束（采用）** | **65.8%（2,199 / 3,341 叶）** |

约束后抽 20 条人工复核，**全部正确**。

### 页面上怎么表现

- 开关 **「末端按属着色 / Colour tips by genus」**（DISPLAY 组，默认开）。
- 调色板 24 槽，`hsl(i*15, 62%, ...)`，**按属名排序依次取色**。
  - 色相必须按 **24 等分**（`i*15`）。写成 `(i*30)%360` 每 12 步就绕回同一色相，
    24 个槽位实际只有 12 种颜色（Rhabdoviridae Fig4 有 60 个属，踩过这个坑）。
  - 属数 > 24 时图例给出「颜色循环」提示。
- **未映射的叶显式标灰 `#b9c4cf`**，并在图例里单列 `not mapped` + 主要原因。
- 悬停 tooltip 增加一行 `genus: <属名>`。
- 颜色写在**数据层** `itemStyle`（环形树是 `tree` 系列，series 级回调读不到挂在节点上的自定义字段）。
- **降级**：`genus_map.json` 取不到时（404 / 解析失败）自动关掉开关并隐藏控件，
  页面与改动前**逐像素一致**（实测 0 像素差）。

### 还没映射上的（照实呈现，未做人工补标）

| 类别 | 例子 | 原因 |
|:--|:--|:--|
| 转座子元件名 | `Gmr1` / `Osvaldo` / `Woot` / `Ulysses` / `CsRN1` | Metaviridae / Pseudoviridae 的叶是元件名（且这两科上游发布的是同一棵树） |
| 裸登录号 | Phenuiviridae 部分叶 | 该登录号不在 MSL41 的 accession 列里 |
| 蛋白登录号 | Aspiviridae | 叶用蛋白号；且含**非植物外群**（`Canine morbillivirus` 等） |
| 缩写缺失 | Konkoviridae / Benyviridae / Solemoviridae / Closteroviridae / Virgaviridae | MSL41 未给缩写 |

**口径**：这些一律**标灰、不猜**。灰叶数量与原因已写进 `genus_map.json` 的 `unmappedReasons`。


