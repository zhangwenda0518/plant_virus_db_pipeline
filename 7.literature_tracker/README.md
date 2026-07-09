# 7. Literature Tracker — 植物病毒文献自动追踪

> 多源植物病毒文献检索、AI 摘要生成、每日邮件报告

**Live**: http://39.106.101.94/literature/

## 架构

```
7.literature_tracker/
├── api_server.py              # Flask Web 服务(:5003, /literature/)
├── config.py                  # 本地文献模块配置
├── fetch_pubmed.py            # PubMed E-utilities 多策略检索(7 类查询)
├── fetch_preprints.py         # arXiv/bioRxiv 预印本抓取
├── fetch_linked_papers.py     # NCBI ELink 按 accession 关联文献
├── fetch_species_papers.py    # 按物种名检索
├── digest.py                  # DeepSeek AI 摘要生成(7.literature_tracker data)
├── dedup.py                   # 文献去重(PMID/DOI/标题相似度)
├── build_data.py              # 构建 papers.json(合并 + 日期跟踪)
├── download_genbank.py        # GenBank 记录下载(供病毒详情页注释构建)
├── build_annotation.py        # 本地 genome_annotations 注释构建
├── LitSearch/                 # 文献检索核心库(MeSH term / PubMed API)
├── auto-paper-collecter/      # 按日程自动检索(PubMed + Semantic Scholar)
├── literature-daily-report/   # 每日邮件报告(Markdown → HTML 邮件)
├── paper-daily/               # 每日论文简报(AI 摘要 + 关键词)
├── meta.seubiomed.com/        # meta 分析前端(仪表板 + 统计)
├── web/                       # 文献 Web 前端(Flask templates)
├── data/                      # 数据库(Journals/MeSH/Categories)
└── historical/                # 历史备份
```

## 功能

| 功能 | 脚本 | 说明 |
|---|---|---|
| PubMed 检索 | fetch_pubmed.py | 7 类查询(General/Geminiviridae/Potyviridae/…),NCBI API key 可选 |
| 预印本补充 | fetch_preprints.py | arXiv + bioRxiv 植物病毒方向 |
| AI 摘要 | digest.py | DeepSeek API 逐篇生成 200 字中文摘要 |
| 去重 | dedup.py | PMID → DOI → 标题 fuzz 三级去重 |
| 构建数据库 | build_data.py | 合并多源结果 → papers.json,记录 updated 日期 |
| 每日报告 | paper-daily/ | Markdown 简报 + 邮件发送(systemd timer) |
| 前端展示 | api_server.py + web/ | Flask + bootstrap-table,期刊分级,30 天高亮 |

## 使用

```bash
# 全量抓取 + 去重 + 摘要 + 生成 papers.json
python build_data.py

# 仅抓取
python fetch_pubmed.py --days 7 --api-key YOUR_KEY

# 启动 Web 服务
python api_server.py          # :5003, 访问 /literature/
```

## 部署

- systemd: `literature-tracker.service`
- papers.json 路径: `7.literature_tracker/papers.json`(gitignore, 由 build_data.py 生成)
- AI 摘要模型: DeepSeek (deepseek-v4-flash), API key 存 `/opt/plant_virus_db/.env`

## 数据流

```
fetch_pubmed.py ──┐
fetch_preprints.py ─┤
fetch_linked_papers.py ─┤
                    ├── dedup.py ──→ papers.json ──→ api_server.py ──→ /literature/
                    │                    │
               digest.py ────────────────┘(AI 摘要)
                    │
               paper-daily/ ──→ 每日邮件报告
```
