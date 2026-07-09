# 8. Plant-Insect — 病毒-媒介-宿主关系数据库

> 整合实验验证的 VH(病毒×媒介种×宿主)三元组 + WUR 全渠道传播记录,三维 facet 检索

**Live**: http://39.106.101.94/vector/

## 数据源

| 源 | 文件 | 说明 |
|---|---|---|
| **VIP-DB (VH)** | `virus_vector_host.tsv` | 实验验证的 447 病毒 × 100 媒介种 × 380 宿主,15 列(含 TaxID/传毒机制/DOI/谱系) |
| **WUR** | `wur_virus_full.tsv` | 瓦赫宁根大学 1654 病毒全渠道传播(媒介类别/传播途径/参考文献) |
| **映射** | `../docs/data/name_mapping.tsv` | ICTV/NCBI 名称映射(45176 条),用于 WUR↔VH 匹配 |
| **合并输出** | `virus_vector_merged.json` | 预合并结果(1806 病毒),供 Web 服务读取 |

## 文件结构

```
8.plant-insect/
├── api_server.py              # Flask Web 服务(:5005, /vector/)
├── vector_page.html           # 前端(3 标签页 + Plotly 图表)
├── build_vector_db.py         # 合并管线(VH + WUR → virus_vector_merged.json)
├── scrape_wur.py              # WUR 网页爬虫(结构化提取)
├── virus_vector_host.tsv      # VH 数据(15 列,实验验证)
├── wur_virus_full.tsv         # WUR 数据(含结构化 refs JSON,gitignore)
├── wur_virus_data.tsv         # WUR 中间数据
└── virus_vector_merged.json   # 合并产物(gitignore,由 build_vector_db.py 生成)
```

## 核心功能

**合并管线(`build_vector_db.py`)**
- VH 三元组按病毒名聚合去重
- WUR 通过 name_mapping 三级匹配(精确→ICTV→模糊 review)
- 输出三正交维度:传播途径(sap/seed/soil/water/vegetative) + 媒介类别(Aphid/Whitefly/Nematode…) + 昆虫传毒机制(Persistent/Non-Persistent…)
- 衍生 `Vector or means of transmission` → 媒介拉丁名 + 传播方式 拆分

**Web 服务(:5005)**
- **Vector-Host 标签页**:VH 原始表 + 8 层 Sankey(病毒科→属→种→媒介科→属→种→机制→宿主) + Top 媒介种 + 传毒机制环图 + 媒介科×机制热力图
- **WUR Database 标签页**:媒介类别/传播途径/Vector/Means 独立列 + WUR 来源链接 + 图表面板
- **Integrated Cards**:VH+WUR 合并卡片,三维 facet 过滤器(带计数)实时联动 + 来源环图/媒介类别/传播途径/热力图
- 三页统一紧凑分页

## 使用

```bash
# 爬取 WUR 数据
python scrape_wur.py

# 重建合并
python build_vector_db.py

# 启动 Web 服务
python api_server.py           # :5005
```

## 数据库引用

- `virus_vector_host.tsv`: 来自 `10.virome_discovery_pipeline` 的 VIP-DB 提取结果
- `wur_virus_full.tsv`: `scrape_wur.py` 爬取 library.wur.nl/WebQuery/virus
- `name_mapping.tsv`: 同 `config.py` → `NAME_MAPPING`
- Web 服务读取 `virus_vector_merged.json`(由 build_vector_db.py 生成)

## 部署

- systemd: `vector-host.service`
- nginx: `/vector/` → :5005
- 合并 JSON 由 `build_vector_db.py` 在服务器上运行生成
