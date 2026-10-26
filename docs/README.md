# docs — 静态网站 + 数据文件

> Nginx 直接服务的静态内容：门户首页 (16 张入口卡片)、参考数据库 (5 页: 入口 + 4 子页)、植物界 EVE 全景、症状图库、基因图谱、互作网络图谱、宿主-病毒关联、病毒进化关系树、ICTV 分子进化树、分子树按科索引、植物病毒蛋白结构统一入口、PV-miRNA、文献浏览。

## 路由覆盖

| 路由 | 目标文件 | 说明 |
|:-----|:-----|:-----|
| `/` | `index.html` | 统一门户, 16 张入口卡片 |
| `/reference/` | `reference_index.html` | 参考数据库 (入口页 + 4 子页: segmented/nonsegmented/submit/download; 5 页共用同一导航条) |
| `/te/` | → 301 `/eve/` | 原 TE & EVE 转座子库, 2026-09-23 已下线归档 (TE 与植物病毒无关) |
| `/eve/` | `eve/index.html` | 植物界 EVE 全景 (8 视角交互分析, 2026-09-23 新增) |
| `/photos/` | `photos.html` | 症状图库 (Gallery/Dashboard/Table 三视图) |
| `/genes/` | `genes/index.html` | 基因图谱仪表盘 (hero + 5 张大卡)；浏览器在 `genes/gene_browser.html`（NLR/sRNA/UPS/miRNA/Antivirals/Downloads 六面板），统计在 `genes/data/` |
| `/network/` | `network/index.html` | 互作网络图谱 (病毒-宿主力导向网络 + 媒介-病毒-宿主三元组网络, 自我网络下钻) |
| `/association/` | `association/index.html` | 宿主-病毒关联桑基图 (病毒×宿主双谱系, 层层下钻) |
| `/phylo/` | `phylo/index.html` | 植物病毒进化关系**单页双视图**（2026-10-11 合并）：标签页① 分类树 (ICTV MSL41, 42 科/200 属/2,637 种)，标签② 分子树 (`?view=molecular` 直达) |
| `/phylo/molecular/` | `phylo/molecular/index.html` | → 跳转 `/phylo/?view=molecular`（带原查询参数；分子树视图已并入 `/phylo/` 单页，脚本在 `phylo/molecular_viewer.js`） |
| `/phylo/molecular/families/` | `phylo/molecular/families/index.html` | 分子树按科索引画廊 (25 张卡片, 含口径标注与数据质量标记) |
| `/structures3d/` | `alias` → `14.rvpsd_structures/webapp/` | **蛋白结构统一入口**（2026-10-08 三页整合 → 同日「单页化」后为外壳 + **两标签**）：`index.html` 为外壳，`rvpsd.html` = 原 RVPSD Molstar 查看器（RVPSD+vpSAT+AFDB 全原子, 2,603 种/20,950 蛋白）（非 `docs/` 下文件） |
| `/structures3d/atlas/` | `alias` → `15.uniprot_plant_virus_structures/webapp/` | UniProt 结构对账仪表盘（直挂模块 15 的 webapp，不复制文件；= 上页「结构总览」标签，覆盖对账 / 完整率 / 缺口分层 / 管线台账同页，页内锚点条定位） |
| `/structures3d/atlas/stats.html` | → 301 `/structures3d/atlas/` | 旧「统计面板」页（2026-10-08 单页化：与「结构总览」指标卡 8 张里 7 张相同，四节并入 `atlas/index.html`，旧 URL 301；旧深链 `#stats` 由外壳回落 atlas 并滚到「缺口与完整率」） |
| `/structures3d/structures_pdb/` `/structures3d/structures_alphafold/` `/structures3d/structures_selffold/` | `alias` → `15…/structures_*/` | Atlas 查看器按相对路径 `../structures_*` 读结构文件，故挂在 `/structures3d/` 一级（`expires 10m`） |
| `/uniprot3d/` `/uniprot3d/webapp/` | → 301 `/structures3d/` | 旧 Atlas 入口（2026-10-07 上线），三页整合后不再单独保留 |
| `/help/fold.html` | `help/fold.html` | Batch Folding Queue (fold_web) 帮助页（**独立保留**；2026-10-08 该功能已从 `/structures3d/` 统一入口摘除） |
| `/pamirdb/` | 反向代理 :8000 | PV-miRNA 预测工作台 (非静态) |
| `/literature/` | 反向代理 :5003 | 文献追踪 (非静态, Flask 提供) |
| `/download.html` `/nonsegmented.html` `/segmented.html` | `docs/*.html` | 根路径直接可达 (2026-09-22 补) |
| `/virus/` | → 301 `/explorer/` | 原独立 Virus Profile 页已归档, 功能并入 Explorer「病毒档案」Tab |
| `/miRNA/` | → 301 `/pamirdb/` | 旧路径, PV-miRNA 现为 `/pamirdb/` |

> ⚠️ **`/reference/` 是 nginx `alias` 到整个 `docs/` 的镜像**，不是独立目录 —— 所以
> `/reference/photos.html`、`/reference/README.md` 都能 200，**但它们不是参考数据库的子页**
> （`photos.html` 是独立顶层页 `/photos/`，用的是另一套旧版全站导航条）。
> **「参考数据库子页」只按导航条口径算 = 5 页**：`reference_index.html`(Dashboard) +
> `segmented` / `nonsegmented` / `submit` / `download`。
> 2026-09-30 实测：`/reference/explorer/` 与 `/reference/explorer.html` 均 **404**
> （`/explorer/` 是 `proxy_pass` 动态应用，不在 alias 内）；`docs/explorer.html` 已于同日归档。
>
> 2026-09-22 补：新增 `location /` 前缀兜底（`root docs/` + `try_files $uri $uri/ =404`）。
> 此前**没有**该前缀块，未显式声明的路径匹配不到任何 location，会落到 nginx 编译期默认 root
> （`/usr/share/nginx/html`，其 `index.html` 是指向发行版测试页的符号链接）—— 于是 `GET /index.html`
> 返回测试页、`/download.html` 等直接 404。另：`docs/` 下散落的 `*.bak_*` 备份文件原先经 `/reference/`
> 别名可下载，现一律 404。站点路由自检脚本：`deploy/check_site_routes.py`（扫描全站引用逐个实测）。

## 文件结构

```
docs/
├── index.html                  # 统一门户首页 (/)
├── reference_index.html        # 参考数据库首页 (/reference/)
├── segmented.html             # 节段病毒浏览
├── nonsegmented.html          # 非节段病毒浏览
├── submit.html                # 数据提交页
├── download.html              # 数据下载页
├── photos.html                # 症状图库 (/photos/)
├── resources.html             # 补充资源页 (/resources.html, 100+ 外部库与工具)
├── table.js                   # 交互表格 JS (DataTables)
├── i18n.js                    # 国际化 JS (PVDB_i18n, 中英双语)
├── sitemap.xml                # 站点地图 (35 条 canonical URL, build_site_meta.py 生成, 勿手改)
├── robots.txt                 # 爬虫规则
├── favicon.svg                # 站点图标
├── favicon-aphid.svg          # 站点图标 (蚜虫版)
├── .nojekyll                  # GitHub Pages 用 (空文件; 本地与线上均有)
├── README.md                  # 本文档
│
├── lib/                       # 本地化前端依赖 (全站无 CDN 依赖)
│   ├── jquery-3.7.1.min.js / jquery.dataTables.min.js|.css   # jQuery + DataTables 1.13.7
│   ├── buttons.* / dataTables.buttons.min.js|.css            # DataTables 导出按钮 (CSV/Excel)
│   ├── bootstrap.min.css / bootstrap.bundle.min.js / bootstrap-icons.css + fonts/  # Bootstrap 5
│   ├── echarts.min.js         # ECharts (network/association/phylo/eve 用)
│   ├── chart.umd.min.js       # Chart.js
│   ├── plotly.min.js          # Plotly
│   ├── papaparse.min.js       # CSV 解析
│   └── xlsx.full.min.js       # xlsx 读写
│
├── data/                      # 核心参考数据 + 图片 (下列为部分列举, 见本块末尾注)
│   ├── Plant_Virus_Full.fasta      # 全量序列 (377 MB, gitignore)
│   ├── Plant_Virus_Full.Info.tsv   # 全量元数据 (gitignore)
│   ├── Plant_Virus_Ref.fasta       # 非冗余参考序列 (31 MB, gitignore)
│   ├── Plant_Virus_Ref.Info.tsv    # 参考元数据
│   ├── Plant_Virus.complete_ref.fasta       # 完整参考序列 (gitignore)
│   ├── Plant_Virus.complete_ref_info.tsv    # 完整参考元数据
│   ├── virus_genes_cov.tsv          # 基因覆盖度表
│   ├── complete_acc.txt             # 完整序列 accession 列表
│   ├── DATA_VERSION                 # 数据版本号
│   ├── name_mapping.tsv             # ICTV/NCBI 名称映射 (45,176 条)
│   ├── *_gallery.json               # 症状图库元数据 (book/dpv/eppo/unified)
│   ├── symptom_table.json           # 症状表
│   ├── book_images/                 # 书籍截图
│   ├── dpv_images/                  # DPV 图版
│   └── pdf_images/                  # PDF 提取图片
│   # 注: 以上为部分列举。data/ 实际另有 VMR_MSL41.txt、chart_data.json、dashboard_stats.json、
│   #     site_stats.json【服务端定时生成, 本地必然 404】、canonical_*.tsv、segment_*.tsv、
│   #     species_canonical.tsv、antivirals.json、host_analysis/、primers/、taxonomy/ 等；
│   #     2026-10-17 起 *.bak* 备份已全部移出 web root → 仓库根 data_backups/（不再随部署暴露）。
│
├── taxonomy/                  # 宿主分类缓存 (无 index.html, 故 /taxonomy/ 为 403)
│   └── host_lineage_cache.json # 宿主谱系缓存
│
├── network/                    # 互作网络图谱 (/network/)
│   ├── index.html              # 力导向网络交互页 (双标签: 病毒-宿主 / 媒介-病毒-宿主)
│   ├── network.json            # VIP-DB 三元组数据 (~0.64 MB, 1,375 条)
│   ├── build_network.py        # 数据构建脚本 (associations.json + virus_vector_host.tsv)
│   ├── echarts.min.js          # 本地 ECharts (无 CDN 依赖)
│   └── README.md               # 数据口径 / 交互设计 / 部署
│
├── association/                # 宿主-病毒关联 (/association/)
│   ├── index.html              # 双层桑基图交互页
│   ├── associations.json       # 关联数据 (~1.3 MB)
│   ├── build_associations.py   # 数据构建脚本
│   └── echarts.min.js          # 本地 ECharts (无 CDN 依赖)
│
├── relations/                  # 病毒-媒介-宿主关系汇总 (/relations/, 2026-09-22 新增)
│   └── index.html              # 四视图入口页 (关联桑基 + 双网络 + 媒介-宿主表, 卡片跳 /association/ /network/ /vector/)
│
├── phylo/                      # 植物病毒进化关系 (/phylo/)
│   ├── index.html              # 分类学树交互页 (矩形/圆形双布局)
│   ├── taxonomy_tree.json      # 分类树数据 (3,319 节点, ~289 KB；默认只画植物病毒 2,926)
│   ├── build_taxonomy.py       # 建树脚本 (VMR 宿主判定 + 科级黑名单)
│   ├── export_msl41.py         # ICTV MSL41 xlsx → TSV (标准库流式解析)
│   ├── echarts.min.js          # 本地 ECharts
│   ├── README.md               # 判定口径 / 边界情形 / 交叉验证 / 分子树说明
│   ├── data/                   # MSL41_species.tsv + plant_taxa.tsv
│   ├── molecular/              # 分子树数据目录（视图已并入 /phylo/ 单页标签②）
│   │   ├── index.html          # 跳转页 → /phylo/?view=molecular（带原查询参数）
│   │   ├── genus_map.json      # 属映射派生数据（分子树视图仍按此路径读取）
│   │   └── families/           # 按科索引画廊 (/phylo/molecular/families/)
│   │       ├── index.html      # 25 科卡片: 指标 + 拓扑缩略图 + 数据质量标记
│   │       └── family_index.json  # 派生数据 (~106 KB, 含 sparkline path)
│   ├── molecular_trees.json    # 分子树数据 (38 棵, 3,341 末端, ~265 KB)
│   ├── fetch_ictv_trees.py     # 抓 ICTV 各科 Resources 页并下载树/比对文件
│   ├── build_molecular.py      # Newick 解析器 + 统计 → molecular_trees.json
│   ├── build_family_index.py   # 只读 molecular_trees.json → 按科索引数据
│   └── ictv_raw/               # 38 个原始 Newick + manifest.json (39 文件, 308 KB)
│
├── genes/                      # 基因图谱 (/genes/)
│   ├── index.html              # 基因图谱首页 (四标签)
│   ├── gene_browser.html       # 基因浏览器 (NLR / sRNA / UPS / miRNA)
│   ├── target_data.js          # 前端数据常量
│   └── data/                   # 基因数据 (RefPlantNLR / UPS / sRNA / miRNA 的 TSV + FASTA)
│
├── help/                       # 帮助与文档 (/help/)
│   ├── index.html              # 帮助总览
│   ├── <模块>.html             # 16 个模块各自的用户指南 (reference/photos/genes/phylo/explorer/…)
│   └── images/                 # 指南插图 (33 张)
│
├── literature/                 # 【2026-09-22 已归档】被 nginx `location /literature/` 遮蔽的
│                              #   陈旧静态副本 (data/ 与 7.literature_tracker/web/data/ 862/863
│                              #   逐字节相同)。线上 `/literature/` 由 Flask 5003 提供。
│                              #   归档位置见 archive/_pending_delete_20260922/MANIFEST.tsv
│
├── primers/                    # 引物 JSON 数据 (模块归属: 4.virus_primer/)
│   ├── index.json              # 引物索引
│   ├── stats.json              # 统计信息
│   └── species/                # 7,193 个物种的引物数据
│
└── eve/                        # 植物界 EVE 全景 (/eve/, 2026-09-23 新增)
    ├── index.html              # 8 视角交互页 (ECharts, 中英双语)
    ├── build_eve_data.py       # 聚合脚本 (在分析服务器 246 上跑)
    ├── echarts.min.js          # 本地 ECharts (无 CDN 依赖)
    ├── README.md               # 数字口径 / 视角说明 / 重建与部署
    ├── data/
    │   ├── eve_landscape.json  # 位点/科/宿主/矩阵 (~67 KB)
    │   ├── eve_dynamics.json   # 古感染 / 扩增动力学 (~180 KB)
    │   ├── eve_phylo.json      # RT 系统发育树 (~346 KB)
    │   └── _audit/             # 可复核 TSV 镜像 (病毒分类 / 宿主科 / 矩阵 / 未映射)
    └── work/                   # 无头浏览器验收脚本 (Playwright)
        ├── check_eve_ui.py     # 8 视角渲染 + 控件功能探针
        ├── check_eve_i18n.py   # 中英切换
        └── snap_extra.py       # 子模式截图
```

## 数据文件 (统一命名)

所有核心数据文件以 `Plant_Virus_` 为前缀，与 `config.py` 的 `PIPELINE_OUTPUTS` 一致：

| config.py 键 | 文件 | 用途 | 大小 |
|:---|:-----|:-----|:----:|
| `full_fasta` | `Plant_Virus_Full.fasta` | 全量植物病毒序列 | 377 MB |
| `full_tsv` | `Plant_Virus_Full.Info.tsv` | 全量元数据 (~199K 条) | — |
| `cluster_fasta` | `Plant_Virus_Ref.fasta` | 非冗余参考序列 | 31 MB |
| `cluster_info` | `Plant_Virus_Ref.Info.tsv` | 参考元数据 (9,165 条) | — |
| `complete_fasta` | `Plant_Virus.complete_ref.fasta` | 完整参考序列 | — |
| `complete_info` | `Plant_Virus.complete_ref_info.tsv` | 完整参考元数据 | — |
| `gene_cov` | `virus_genes_cov.tsv` | 基因覆盖度 | — |

## 关键 JS 文件

| 文件 | 功能 |
|:-----|:-----|
| `table.js` | 通用 DataTables 交互表格, 支持排序/搜索/分页/CSV 导出 |
| `i18n.js` | 中英双语切换 (PVDB_i18n), 版本 `?v=3` 缓存破坏 |

## 部署

- **服务器路径**: `/opt/plant_virus_db/plant_virus_db_pipeline/docs/`
- **Nginx**: 主配置 `plant-virus.conf`, 各路由见上表
- **数据路径**: 由 `config.py` 统一管理, 可通过环境变量 `PVDB_*` 覆盖
- **缓存策略**: `/reference/data/` → `expires 1h, Cache-Control: public, immutable`

## 站点工程化（2026-10-17 起）

全站静态页进入「注册表驱动」的工程化管理。三个脚本构成工具链：

| 脚本 | 职责 |
|:-----|:-----|
| `scripts/site_pages.py` | **单一事实源**：37 页注册表（文件 ↔ canonical URL 路由映射、中英标题/描述、JSON-LD 类型）+ 站点常量（域名、许可、主题色）。新增页面/换域名只改这里 |
| `scripts/build_site_meta.py` | 生成器：按注册表给每页 `</head>` 前注入/替换 `<!--#[site-meta]-->` 规范块（description / canonical / Open Graph / Twitter Card / theme-color / 缺失补齐的 viewport+favicon / JSON-LD）；产出 `sitemap.xml` 与 `lib/site-version.js`。幂等，`--check` 模式可挂 CI |
| `scripts/check_site_quality.py` | 质量门（退出码即结果）：head 完备性、sitemap 与注册表一致、robots Sitemap 行、site-version 与 DATA_VERSION 一致、全站内链解析（含 nginx alias 路由映射表）、部署根卫生（禁 .orig*/.bak*/__pycache__）、JSON 可解析、单页 >300KB 告警 |

**标准工作流**（改页面 / 加页面 / 月更数据后）：

```bash
python scripts/site_pages.py            # 改注册表（编辑）
python scripts/build_site_meta.py       # 重新注入 + 出 sitemap/site-version
python scripts/check_site_quality.py    # 质量门验收，必须 PASS
```

**已建立的站级约定**

- head 规范块由生成器统一供给，**不要手写** description/canonical/og（会被下次生成覆盖/去重）；
- 每页保留自己的 `<title>`（带 data-i18n 可翻译）；
- `lib/site-version.js` 是数据版本的唯一前端出口（`window.PVDB_SITE.version`），
  由 DATA_VERSION 生成；`lib/site-nav.js` v3 在页面**没有**自己的页脚时自动注入学术页脚
  （平台名 · 数据版本 · MIT · GitHub · 推荐引用含访问日期），有页脚则跳过，`data-footer="off"` 可关；
- `404.html` 为双语静态 404（nginx `location /` 内 `error_page 404 /404.html`）；
- `phylo/molecular/index.html` 为 noindex 重定向存根，不进 sitemap；
- 部署根卫生：历史备份/快照已归档至 `archive/website_backups_20261017/`（页面/JS 备份）
  与 `data_backups/docs_data_20261017/`（数据 .bak 与 4 个批次快照目录，约 2.9GB，均已 gitignore），
  **不要再把备份文件放进 docs/`**；nginx 另有 `\.orig_` 404 拦截兜底。

## 注意

- 此目录是 git 开发源, 与服务器生产环境 (`/opt/plant_virus_db/plant_virus_db_pipeline/docs/`) 可能存在差异
- 大文件 (FASTA/TSV gz) 已加入 `.gitignore`, 需手动同步
- Nginx 静态页修改后需 `nginx -s reload`
