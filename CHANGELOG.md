# Changelog

All notable changes to the Plant Virus Database Platform.

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
