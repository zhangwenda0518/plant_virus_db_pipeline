# 10. Virus Photos — 植物病毒电镜照片 / 症状图库

> 病毒粒子、包涵体、寄主症状图片收集与图鉴生成

**Live**: http://39.106.101.94/photos.html

## 数据源

| 源 | 说明 |
|---|---|
| EPPO Global Database | 植物病毒标准照片(经济重要病害) |
| DPV (Descriptions of Plant Viruses) | 经典图版提取(含电子显微镜) |
| PubMed Central / Open-i | 文献附图自动抓取 |
| 专著扫描 | 植物病毒学经典教材 PDF 提取 |

## 文件

```
10.virus_photos/
├── 15587070.pdf               # 参考专著 PDF
├── 15587070.docx              # 专著提取文本
├── scrape_eppo.js             # EPPO 网站爬取(Puppeteer)
├── scrape_eppo_photos.py      # EPPO 图片 URL 提取
├── scrape_openi.py            # Open-i (PMC 附图) 搜索+下载
├── extract_dpv.py             # DPV 图版文字提取
├── extract_dpv_tags.py        # DPV 标注/关键词提取
├── extract_book.py            # 专著章节+图版提取
├── parse_book.py              # 专著文本解析
├── rebuild_book.py            # 专著内容重建(标签+图片关联)
├── build_gallery_json.py      # 生成图鉴 JSON 数据
├── eppo_virus_photos.tsv      # EPPO 图片元数据
├── normalize_taxonomy.py      # 病毒名归一化(ICTV 匹配)
├── aps_extract.js             # APS(美国植物病理学会)提取
└── extracted/                 # 提取产物(图片/文本)
```

## 工作流

```
EPPO ──→ scrape_eppo.js/ps ──→ eppo_virus_photos.tsv ──┐
DPV  ──→ extract_dpv.py ──────────────────────────────┤
PMC  ──→ scrape_openi.py ─────────────────────────────┤
专著  ──→ extract_book.py ────────────────────────────┤
                                                       ├── build_gallery_json.py → gallery.json
                                                       │
normalize_taxonomy.py ←── (ICTV 名归一)               │
                                                       │
                                                  ──→ docs/photos.html
```

## 使用

```bash
# EPPO 爬取(需要 Node.js + Puppeteer)
node scrape_eppo.js

# EPPO 图片提取
python scrape_eppo_photos.py

# Open-i 文献附图
python scrape_openi.py --virus "Tobacco mosaic virus"

# 专著提取
python extract_book.py

# 生成图鉴 JSON
python build_gallery_json.py
```

## 部署

- 静态页: `docs/photos.html`(gateway 入口)
- `deploy_photos.sh`: 一键部署脚本(上传提取产物到服务器)

## 数据库引用

- ICTV 名归一化: `../docs/data/name_mapping.tsv`
- 病毒参考数据: `../docs/data/Plant_Virus_Ref.Info.tsv`
- 输出: `docs/photos.html` + gallery JSON
