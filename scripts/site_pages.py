# -*- coding: utf-8 -*-
"""站点单一事实源：页面注册表 + 站点级常量。

被两个脚本共用：
  scripts/build_site_meta.py   —— 按 registry 注入/更新全站 head 规范块、
                                  生成 sitemap.xml 与 lib/site-version.js
  scripts/check_site_quality.py—— 质量门（head 完整性、内链解析、sitemap 一致性…）

改站点结构（新增页面 / 换域名 / 改描述）只改这一个文件，然后重跑
`python scripts/build_site_meta.py`，最后 `python scripts/check_site_quality.py` 验收。
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_ROOT = os.path.join(REPO_ROOT, "docs")

# 部署源（当前为服务器 IP；申请域名后只改这一行并重跑 build_site_meta.py）
SITE_BASE = "http://39.106.101.94"
SITE_NAME = "Plant Virus Database Platform"
SITE_NAME_ZH = "植物病毒数据库平台"
GITHUB_URL = "https://github.com/zhangwenda0518/plant_virus_db_pipeline"
THEME_COLOR = "#1a5276"
DATA_VERSION_FILE = os.path.join(DOCS_ROOT, "data", "DATA_VERSION")


def data_version():
    """从 docs/data/DATA_VERSION 取 VERSION= 值（如 2026-10-03），失败返回 None。"""
    try:
        with open(DATA_VERSION_FILE, encoding="utf-8") as f:
            m = re.search(r"^VERSION=(\S+)", f.read(), re.M)
            return m.group(1) if m else None
    except OSError:
        return None


# url=None 且 noindex=True 的页面（重定向存根、404）不进 sitemap、不加 canonical/og
PAGES = [
    dict(file="index.html", url="/", kind="hub", priority="1.0", changefreq="weekly",
         title_en="Plant Virus Database Platform", title_zh="植物病毒数据库平台",
         desc_en="Plant Virus Database Platform: curated plant virus reference sequences, symptom photos, "
                 "vector-host associations, primers, endogenous viral elements, protein structures and AI "
                 "knowledge services, cross-referenced with ICTV MSL41.",
         desc_zh="植物病毒数据库平台：植物病毒参考序列、症状照片、媒介-宿主关联、引物、内源性病毒位点、"
                 "蛋白结构与 AI 知识服务，对照 ICTV MSL41 校准。"),

    dict(file="reference_index.html", url="/reference/", kind="dataset", priority="0.9", changefreq="monthly",
         title_en="Plant Virus Reference Database", title_zh="植物病毒参考数据库",
         desc_en="Curated plant virus reference database: 9,165 representative sequences curated from 211,378 "
                 "GenBank records, cross-referenced with ICTV MSL41; dashboard, segmented and non-segmented "
                 "browsers, submission and download.",
         desc_zh="植物病毒参考数据库：从 211,132 条 GenBank 记录精修出 9,165 条代表序列，对照 ICTV MSL41；"
                 "含仪表盘、分节段/非分节段浏览、提交与下载。"),

    dict(file="segmented.html", url="/reference/segmented.html", kind="page", priority="0.6", changefreq="monthly",
         title_en="Segmented Plant Viruses", title_zh="分节段植物病毒",
         desc_en="Segmented plant virus reference browser: curated representative sequences browsable by "
                 "family and genome segment (L/M/S).",
         desc_zh="分节段植物病毒参考浏览：按科与基因组节段（L/M/S）浏览精修代表序列。"),

    dict(file="nonsegmented.html", url="/reference/nonsegmented.html", kind="page", priority="0.6", changefreq="monthly",
         title_en="Non-Segmented Plant Viruses", title_zh="非分节段植物病毒",
         desc_en="Non-segmented plant virus reference browser: curated representative sequences for "
                 "non-segmented virus genomes.",
         desc_zh="非分节段植物病毒参考浏览：非分节段基因组的精修代表序列。"),

    dict(file="submit.html", url="/reference/submit.html", kind="page", priority="0.5", changefreq="monthly",
         title_en="Submit Virus", title_zh="病毒提交",
         desc_en="Submit a plant virus sequence to the reference database: scope, format requirements and "
                 "submission form.",
         desc_zh="向参考数据库提交植物病毒序列：范围、格式要求与提交表单。"),

    dict(file="download.html", url="/reference/download.html", kind="page", priority="0.7", changefreq="monthly",
         title_en="Download — Plant Virus DB", title_zh="下载 — 植物病毒库",
         desc_en="Download plant virus reference datasets: clustered representative FASTA (9,165 records) and "
                 "full pre-deduplication set (211,132 records), each with complete metadata TSV.",
         desc_zh="植物病毒参考数据下载：聚类代表序列 FASTA（9,165 条）与去重前全量集（211,378 条），均附完整元数据 TSV。"),

    dict(file="photos.html", url="/photos/", kind="dataset", priority="0.8", changefreq="monthly",
         title_en="Plant Virus Symptom Photos", title_zh="植物病毒症状照片库",
         desc_en="Curated plant virus symptom photo gallery: 2,975 DOI-linked photos curated from EPPO, DPV, "
                 "books and research literature, filterable by host, symptom and photo position.",
         desc_zh="植物病毒症状照片库：从 EPPO、DPV、专著与文献精修的 2,975 张带 DOI 照片，可按寄主、症状与部位筛选。"),

    dict(file="relations/index.html", url="/relations/", kind="dataset", priority="0.8", changefreq="monthly",
         title_en="Virus-Vector-Host Relations", title_zh="病毒-媒介-宿主关系",
         desc_en="Virus-vector-host relations: literature-backed vector-host tables, Sankey and network views "
                 "built from 15,197 virus-host pairs across 211,132 GenBank accessions.",
         desc_zh="病毒-媒介-宿主关系：基于文献背书的媒介-宿主表、桑基图与网络视图，覆盖 15,197 对病毒-宿主关系。"),

    dict(file="association/index.html", url="/association/", kind="dataset", priority="0.7", changefreq="monthly",
         title_en="Host-Virus Associations", title_zh="宿主-病毒关联",
         desc_en="Host-virus association Sankey: virus-by-host double-lineage exploration with drill-down, "
                 "built from 208,477 mapped sequences.",
         desc_zh="宿主-病毒关联桑基图：病毒×宿主双谱系逐层下钻，基于 208,477 条可映射序列。"),

    dict(file="network/index.html", url="/network/", kind="dataset", priority="0.7", changefreq="monthly",
         title_en="Interaction Networks", title_zh="互作网络",
         desc_en="Interaction networks of plant viruses: virus-host force-directed networks and "
                 "vector-virus-host tripartite networks with ego-network drill-down.",
         desc_zh="植物病毒互作网络：病毒-宿主力导向网络与媒介-病毒-宿主三元网络，支持自我网络下钻。"),

    dict(file="eve/index.html", url="/eve/", kind="dataset", priority="0.8", changefreq="monthly",
         title_en="Plant EVE Landscape", title_zh="植物 EVE 全景",
         desc_en="Endogenous viral elements across 1,527 plant genomes and 284 host families: 150,136 loci "
                 "explored through eight linked interactive views.",
         desc_zh="植物内源性病毒元件全景：覆盖 1,527 个植物基因组、284 个宿主科的 150,136 个位点，八联动视角交互探索。"),

    dict(file="genes/index.html", url="/genes/", kind="dataset", priority="0.8", changefreq="monthly",
         title_en="Plant Immune Gene Atlas", title_zh="植物免疫基因图谱",
         desc_en="Plant immune gene atlas: RefPlantNLR 415 NLRs, 11,780 sRNA genes, 3,996 "
                 "ubiquitin-proteasome system genes and 83,166 miRNAs in one integrated resource.",
         desc_zh="植物免疫基因图谱：RefPlantNLR 415 个 NLR、11,780 个 sRNA 基因、3,996 个泛素-蛋白酶体基因与 83,166 个 miRNA。"),

    dict(file="genes/gene_browser.html", url="/genes/gene_browser.html", kind="page", priority="0.7", changefreq="monthly",
         title_en="Plant Immune & sRNA Gene Browser", title_zh="植物免疫与 sRNA 基因浏览器",
         desc_en="Interactive plant immune and sRNA gene browser: NLR, sRNA, ubiquitin-proteasome, miRNA and "
                 "antiviral panels with search, filters and downloads.",
         desc_zh="植物免疫与 sRNA 基因交互浏览器：NLR、sRNA、泛素-蛋白酶体、miRNA 与抗病毒基因面板，支持检索、筛选与下载。"),

    dict(file="genes/data/index.html", url="/genes/data/", kind="page", priority="0.4", changefreq="monthly",
         title_en="Plant Immune Gene Atlas — Statistics", title_zh="植物免疫基因图谱 — 统计",
         desc_en="Statistics for the plant immune gene atlas: per-panel counts, source breakdowns and build "
                 "metadata.",
         desc_zh="植物免疫基因图谱统计：各面板数量、来源构成与构建元数据。"),

    dict(file="phylo/index.html", url="/phylo/", kind="dataset", priority="0.8", changefreq="monthly",
         title_en="Virus Phylogeny", title_zh="病毒进化关系",
         desc_en="Plant virus phylogeny: ICTV MSL41 taxonomy tree (42 families, 200 genera, 2,637 species) and "
                 "official maximum-likelihood molecular trees with real branch lengths and support values.",
         desc_zh="植物病毒进化关系：ICTV MSL41 分类树（42 科/200 属/2,637 种）与官方最大似然分子树，真实枝长与支持度。"),

    dict(file="phylo/molecular/families/index.html", url="/phylo/molecular/families/", kind="dataset",
         priority="0.5", changefreq="monthly",
         title_en="ICTV Molecular Trees — Families", title_zh="ICTV 分子树 — 按科索引",
         desc_en="ICTV molecular trees by family: 25 family tree cards with coverage annotations and "
                 "data-quality flags.",
         desc_zh="ICTV 分子树按科索引：25 张科级树卡片，含覆盖口径标注与数据质量标记。"),

    # 重定向存根：noindex，不进 sitemap / canonical / og
    dict(file="phylo/molecular/index.html", url=None, kind="stub", priority=None, changefreq=None,
         noindex=True,
         title_en="Redirecting to Molecular Trees", title_zh="正在跳转至分子树",
         desc_en=None, desc_zh=None),

    dict(file="resources.html", url="/resources.html", kind="page", priority="0.6", changefreq="monthly",
         title_en="Supplementary Resources", title_zh="补充资源",
         desc_en="Curated supplementary resources for plant virology: 100+ public databases and tools covering "
                 "sequences, hosts, vectors, metagenomics, primers and transcriptomes.",
         desc_zh="植物病毒学补充资源：100+ 公共数据库与工具，覆盖序列、宿主、媒介、宏基因组、引物与转录组。"),

    dict(file="help/index.html", url="/help/", kind="help", priority="0.6", changefreq="monthly",
         title_en="Help & Documentation", title_zh="帮助与文档",
         desc_en="Help and documentation for the Plant Virus Database Platform: quick-start guides, reference "
                 "manuals and troubleshooting for every module.",
         desc_zh="植物病毒数据库平台帮助与文档：各模块快速上手、参考手册与故障排查。"),

    dict(file="help/reference.html", url="/help/reference.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Reference DB Help", title_zh="参考数据库帮助",
         desc_en="Reference database help: dashboard, segmented and non-segmented browsers, search, submission "
                 "and download workflows.",
         desc_zh="参考数据库帮助：仪表盘、分节段/非分节段浏览、检索、提交与下载流程。"),

    dict(file="help/photos.html", url="/help/photos.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Symptom Gallery Help", title_zh="症状图库帮助",
         desc_en="Symptom photo gallery help: gallery, dashboard and table views, filters and image provenance.",
         desc_zh="症状照片库帮助：画廊/仪表盘/表格三视图、筛选器与图片来源。"),

    dict(file="help/relations.html", url="/help/relations.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Relations Help", title_zh="关系库帮助",
         desc_en="Virus-vector-host relations help: table evidence columns, Sankey and network reading guide.",
         desc_zh="病毒-媒介-宿主关系帮助：证据列解读、桑基图与网络视图阅读指南。"),

    dict(file="help/eve.html", url="/help/eve.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Plant EVE Landscape Help", title_zh="植物 EVE 全景帮助",
         desc_en="Plant EVE landscape help: the eight linked views and how loci were called.",
         desc_zh="植物 EVE 全景帮助：八个联动视角与位点鉴定方法。"),

    dict(file="help/genes.html", url="/help/genes.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Immune Gene Atlas Help", title_zh="免疫基因图谱帮助",
         desc_en="Plant immune gene atlas help: NLR, sRNA, UPS, miRNA panels and data sources.",
         desc_zh="植物免疫基因图谱帮助：NLR、sRNA、泛素-蛋白酶体、miRNA 面板与数据来源。"),

    dict(file="help/explorer.html", url="/help/explorer.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Virus Explorer Help", title_zh="病毒浏览器帮助",
         desc_en="Virus Explorer help: 5D linked filtering, timeline, map, genome viewer and virus profiles.",
         desc_zh="病毒浏览器帮助：5D 联动筛选、时间轴、地图、基因组查看器与病毒档案。"),

    dict(file="help/metabuli.html", url="/help/metabuli.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Metabuli Help", title_zh="宏基因组分类帮助",
         desc_en="Metabuli help: contig upload, taxonomy assignment and validation outputs.",
         desc_zh="宏基因组分类帮助：contig 上传、物种注释与验证输出。"),

    dict(file="help/pamirdb.html", url="/help/pamirdb.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="PV-miRNA Help", title_zh="PV-miRNA 帮助",
         desc_en="PV-miRNA help: pre-computed virus miRNA target predictions and how to read the workbench.",
         desc_zh="PV-miRNA 帮助：预计算的病毒 miRNA 靶标预测与工作台读法。"),

    dict(file="help/phylo.html", url="/help/phylo.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Virus Phylogeny Help", title_zh="病毒进化帮助",
         desc_en="Virus phylogeny help: taxonomy tree vs molecular trees, layouts and parameter meanings.",
         desc_zh="病毒进化帮助：分类树与分子树的差异、布局与参数含义。"),

    dict(file="help/primers.html", url="/help/primers.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Primer Database Help", title_zh="引物数据库帮助",
         desc_en="Primer database help: search, ratings, specificity fields and REST API usage.",
         desc_zh="引物数据库帮助：检索、评级、特异性字段与 REST API 用法。"),

    dict(file="help/resources.html", url="/help/resources.html", kind="help", priority="0.3", changefreq="monthly",
         title_en="Supplementary Resources Help", title_zh="补充资源帮助",
         desc_en="Supplementary resources help: how the 100+ entries are organized and curated.",
         desc_zh="补充资源帮助：100+ 条目的组织方式与遴选标准。"),

    dict(file="help/knowledge.html", url="/help/knowledge.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Knowledge RAG Help", title_zh="知识库问答帮助",
         desc_en="Knowledge RAG help: asking questions, source attribution and answer limitations.",
         desc_zh="知识库问答帮助：提问方式、来源引用与答案边界。"),

    dict(file="help/literature.html", url="/help/literature.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Literature Tracker Help", title_zh="文献追踪帮助",
         desc_en="Literature tracker help: categories, AI summaries and weekly update mechanism.",
         desc_zh="文献追踪帮助：分类体系、AI 摘要与每周更新机制。"),

    dict(file="help/onekp.html", url="/help/onekp.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="1KP Virome Help", title_zh="1KP 病毒组帮助",
         desc_en="1KP virome help: sample browser, detection confidence tiers and analysis views.",
         desc_zh="1KP 病毒组帮助：样本浏览、检出置信分级与分析视图。"),

    dict(file="help/uniprot3d.html", url="/help/uniprot3d.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="UniProt Structure Atlas Help", title_zh="UniProt 结构图谱帮助",
         desc_en="UniProt structure atlas help: reconciliation dashboard, coverage and gap tiers.",
         desc_zh="UniProt 结构图谱帮助：对账仪表盘、覆盖与缺口分层。"),

    dict(file="help/vector.html", url="/help/vector.html", kind="help", priority="0.4", changefreq="monthly",
         title_en="Vector-Host DB Help", title_zh="媒介-宿主库帮助",
         desc_en="Vector-host database help: vector groups, evidence and host range views.",
         desc_zh="媒介-宿主数据库帮助：媒介类群、证据与宿主范围视图。"),

    dict(file="help/fold.html", url="/help/fold.html", kind="help", priority="0.3", changefreq="monthly",
         title_en="Batch Folding Queue Help", title_zh="批量折叠队列帮助",
         desc_en="Batch folding queue help: submitting jobs and reading queue states.",
         desc_zh="批量折叠队列帮助：任务提交与队列状态解读。"),

    # 404：noindex，不进 sitemap
    dict(file="404.html", url=None, kind="stub", priority=None, changefreq=None,
         noindex=True,
         title_en="404 — Page Not Found", title_zh="404 — 页面未找到",
         desc_en=None, desc_zh=None),
]

PAGES_BY_FILE = {p["file"]: p for p in PAGES}


def canonical_url(url_path):
    return SITE_BASE + url_path if url_path else None
