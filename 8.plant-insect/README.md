# 8. Plant-Insect — 病毒-媒介-宿主关系数据库

> 整合实验验证的 VH (病毒×媒介×宿主) 三元组 + WUR 全渠道传播记录，三维 facet 检索 + Sankey/Heatmap/Chord 可视化。

**Live**: http://39.106.101.94/vector/

---

## 架构

```mermaid
flowchart TB
    subgraph Sources["数据源"]
        VH["VIP-DB (VH)<br/>virus_vector_host.tsv<br/>447 病毒 × 100 媒介种 × 380 宿主<br/>15 列 (含 TaxID/传毒机制/DOI)"]
        WUR["WUR Database<br/>scrape_wur.py 爬虫<br/>wur_virus_full.tsv<br/>1,654 条全渠道传播记录"]
        MAP["名称映射<br/>name_mapping.tsv<br/>45,176 条 ICTV↔NCBI"]
    end

    subgraph Pipeline["合并管线"]
        BUILD["build_vector_db.py"]
        MATCH["两级自动匹配<br/>精确 → ICTV<br/>(模糊仅出人工复核清单)"]
        MERGE["合并标注<br/>来源: VH/WUR/Both<br/>置信度: high<br/>冲突标记 + family 冲突明细"]
    end

    subgraph Output["产出与 Web"]
        JSON["virus_vector_merged.json<br/>1,803 合并条目 = 447 (VH) + 1,356 (WUR-only)"]
        API["api_server.py :5005<br/>Flask REST API"]
        WEB["vector_page.html<br/>三标签页 SPA"]
    end

    Sources --> Pipeline
    Pipeline --> Output

    subgraph Views["Web 可视化"]
        V1["Vector-Host 标签<br/>8 层 Sankey<br/>Top 媒介 + 机制环图<br/>媒介科×机制热力图"]
        V2["WUR Database 标签<br/>媒介类别/传播途径<br/>Vector/Means 独立列"]
        V3["Integrated Cards<br/>VH+WUR 合并<br/>三维 facet 过滤器<br/>来源环图/热力图"]
    end

    Output --> Views

    style Sources fill:#e8eaf6
    style Pipeline fill:#fff3e0
    style Output fill:#e1f5fe
    style Views fill:#e8f5e9
```

---

## 数据量

> 2026-10-03 实测复算（`python build_vector_db.py` 输出 stats 与 README 逐项对齐）。
> 旧版"1,806 有媒介-宿主关系的病毒"把无关系、无 TaxID 的 WUR-only 条目混入同一口径，已拆分。

| 指标 | 数值 |
|:-----|:----:|
| 有媒介-宿主关系（VH 实验验证） | 447 |
| WUR 补充条目（待匹配，无 TaxID、无关系记录） | 1,356 |
| 合并条目总数（= 447 + 1,356） | 1,803 |
| WUR 病毒传播记录（原始抓取行） | 1,654 |
| 病毒-媒介-宿主三元组 | 1,375 |
| VH 病毒种 | 447 |
| VH 媒介种 | 100 |
| VH 宿主种 | 380 |

> 注：WUR 原始 1,654 行含 21 组重名（1,633 个唯一名）；重名条目全部保留并打 `duplicated=1`
> 标记列（见 `scrape_wur.py`），矛盾条目待人工复核，不自动合并。

---

## 数据源

| 源 | 文件 | 说明 |
|:---|:-----|:-----|
| **VIP-DB (VH)** | `virus_vector_host.tsv` | 实验验证的三元组, 15 列 (含 TaxID/传毒机制/DOI/谱系) |
| **WUR** | `wur_virus_full.tsv` | 瓦赫宁根大学全渠道传播记录 (媒介类别/传播途径/参考文献) |
| **映射** | `docs/data/name_mapping.tsv` | ICTV/NCBI 名称双向映射 (45,176 条) |
| **合并输出** | `virus_vector_merged.json` | 预合并结果 (1,803 条目 = 447 VH + 1,356 WUR-only), 供 Web 服务读取 |

---

## 合并管线 (`build_vector_db.py`)

```mermaid
flowchart LR
    VH_TSV["VH TSV<br/>三元组"] --> AGG["按病毒名<br/>聚合去重"]
    WUR_TSV["WUR TSV<br/>传播记录"] --> MATCH["两级自动匹配<br/>精确名 → ICTV 名"]
    MAP["name_mapping.tsv"] --> MATCH
    AGG --> MERGE["合并标注"]
    MATCH --> MERGE
    MATCH -. "相似度 ≥ 0.90 仅出复核建议" .-> REVIEW["vector_merge_review.tsv<br/>(人工复核, 不自动合并)"]
    MERGE --> OUT["virus_vector_merged.json"]

    style OUT fill:#c8e6c9
```

**合并策略**:
1. VH 三元组按病毒 canonical name 聚合去重
2. WUR 通过 name_mapping **两级自动匹配**（① 归一化名精确相等 → ② 双方经 name_mapping 归一到同一 ICTV 名）；模糊相似度 ≥0.90 **只生成人工复核清单** `vector_merge_review.tsv`，不自动合并
3. 标注 `sources`: `['VH']` | `['WUR']` | `['VH','WUR']`；WUR-only 条目无 TaxID、无关系记录，属"待匹配补充"
4. 标注 `match_confidence`: `high`（两级自动匹配均为高置信）| `mixed`（同名多条 WUR 合并）
5. 标注 `conflict_flags` 与 `conflict_details["family_mismatch"]` 明细（WUR family ≠ 主记录 family 时保留首次 family，不静默覆盖）
6. 衍生 `Vector or means of transmission` → 媒介拉丁名 + 传播方式拆分

---

## Web 界面 (三标签页)

### Vector-Host 标签页

| 组件 | 说明 |
|:-----|:-----|
| VH 原始表 | 15 列完整数据，排序/搜索 |
| **8 层 Sankey** | Virus Family → Genus → Species → Vector Family → Genus → Species → Mechanism → Host |
| Top 媒介种 | 柱状图排行 |
| 传毒机制环图 | Persistent/Non-Persistent/Semi-Persistent 分布 |
| 媒介科×机制热力图 | 二维交叉频率矩阵 |

### WUR Database 标签页

- 媒介类别 / 传播途径 / Vector / Means 独立列
- WUR 来源链接
- 图表面板 (类别分布 / 途径分布)

### Integrated Cards

- VH + WUR 合并卡片视图
- 三维 facet 过滤器 (带实时计数)
- 来源环图 / 媒介类别 / 传播途径 / 热力图
- 紧凑分页

---

## 文件结构

```
8.plant-insect/
├── api_server.py              # Flask Web 服务 (:5005, /vector/)
├── vector_page.html           # 前端 SPA (三标签页 + Plotly 图表)
├── build_vector_db.py         # 合并管线 (VH + WUR → virus_vector_merged.json)
├── scrape_wur.py              # WUR 网页爬虫 (结构化提取)
├── visualize_all.py           # 全量可视化脚本
├── virus_vector_host.tsv      # VH 数据 (15 列, 实验验证)
├── wur_virus_full.tsv         # WUR 数据 (gitignore)
├── wur_virus_data.tsv         # WUR 中间数据 (gitignore)
├── virus_vector_merged.json   # 合并产物 (gitignore)
├── vector-host.service        # systemd 服务配置
├── Fig1_overview.png          # 概览图
├── Fig2_heatmap.png           # 热力图
├── Fig3_transmission_family.png # 科级传播图
└── Supplementary Table 1.xlsx # 补充表 (gitignore)
```

---

## 快速开始

```bash
# 爬取 WUR 数据
python scrape_wur.py

# 重建合并
python build_vector_db.py

# 启动 Web 服务
python api_server.py           # :5005, 访问 /vector/
```

## 部署

| 项目 | 配置 |
|:-----|:-----|
| **systemd** | `vector-host.service` → :5005 |
| **Nginx** | `/vector/` → proxy_pass :5005 |
| **合并 JSON** | 由 `build_vector_db.py` 在服务器上运行生成 |
| **依赖** | Flask, Plotly (前端 CDN) |
