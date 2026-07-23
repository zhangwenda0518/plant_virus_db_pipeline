# 9. Metabuli — 植物病毒宏基因组分类器 Web

> 上传 contig 序列，基于 910 MB 植物病毒参考库进行 k-mer 分类。8 级 NCBI→ICTV 谱系注释 + BLASTN/BLASTX/CDD 三重验证。

**Live**: http://39.106.101.94/metabuli/

---

## 架构

```mermaid
flowchart TB
    subgraph Input["输入"]
        UPLOAD["上传 FASTA<br/>或粘贴序列<br/>≤ 100 MB"]
        EXAMPLES["快速填充示例<br/>TMV/PVY/CMV/PSTVd/Mix"]
    end

    subgraph Engine["分类引擎"]
        METABULI["Metabuli classify<br/>seq-mode 3<br/>910 MB 植物病毒 DB"]
        TAXLIN["taxid_lineage.tsv<br/>22,190 taxid<br/>NCBI→ICTV 8级谱系"]
    end

    subgraph Verify["验证工具链"]
        BLASTN["BLASTN<br/>NCBI nt 核酸比对"]
        BLASTX["BLASTX<br/>NCBI nr 6-frame 翻译"]
        CDD["CDD<br/>保守域搜索"]
    end

    subgraph Output["输出"]
        TABLE["8级分类表<br/>Realm→Species"]
        VIRUS["病毒 contig 表<br/>近完整基因组高亮"]
        SANKEY["Taxonomy Sankey<br/>前5种过滤"]
        KRONA["Krona 图<br/>可隐藏 unclassified"]
        DOWNLOAD["下载<br/>TSV + FASTA"]
    end

    Input --> Engine
    Engine --> Output
    TABLE --> Verify
    Verify --> Output

    style Input fill:#e8eaf6
    style Engine fill:#e1f5fe
    style Verify fill:#fff3e0
    style Output fill:#e8f5e9
```

---

## 文件结构

```
9.metabuli/
├── metabuli_api.py            # Flask 服务 (:5004)
│                              #   - 异步 Metabuli 分类
│                              #   - BLASTN/BLASTX/CDD 提交 + 轮询
│                              #   - taxid_lineage.tsv 内存缓存
│                              #   - Job 管理 (2h 自动清理)
├── metabuli_page.html         # 前端 SPA (~2200 行 JS)
│                              #   - 4 个分析标签页
│                              #   - Plotly Sankey + Krona iframe
│                              #   - 快速填充示例 + 上传进度
├── build_taxid_lineage.py     # 生成 taxid→ICTV 8 级谱系表
├── taxid_lineage.tsv          # 预生成映射 (22,190 taxid)
├── fetch_examples.py          # NCBI efetch 生成示例
├── metabuli_examples.json     # TMV/PVY/CMV/PSTVd 全长基因组 JSON
└── README.md
```

---

## 四大分析标签 → 五大分析标签

### 1. Metabuli — k-mer 分类

```
┌──────────────────────────────────────────────────────────┐
│  输入: FASTA contigs (≤100 MB)                           │
│                                                          │
│  Metabuli classify (seq-mode 3)                          │
│       ↓                                                  │
│  910 MB 植物病毒参考库 (ref.virus.build.metabuli_db)     │
│       ↓                                                  │
│  8 级分类: Realm → Kingdom → Phylum → Class →           │
│            Order → Family → Genus → Species              │
│       ↓                                                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 分类表 (每 contig 一行)                          │    │
│  │ Contig | Length | Realm..Species | Score | Flag │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌──────────────────────────┐ ┌──────────────────────┐  │
│  │ Sankey 图 (前5种过滤)    │ │ Krona 图 (交互式)    │  │
│  └──────────────────────────┘ └──────────────────────┘  │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 病毒 contig 表 (仅病毒命中)                      │    │
│  │ · 近完整基因组高亮 (绿色)                        │    │
│  │ · 0.8 ≤ length/genus_avg ≤ 1.2 标注            │    │
│  │ · 一键跳转 CDD/BLASTN/BLASTX/Primer                │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 2. CDD — 保守域搜索

- 对选中的 contig 进行 6-frame 翻译
- 提交 NCBI CDD (Conserved Domain Database)
- 返回: 域名称、E-value、位置、描述
- 用于: 确认病毒蛋白域架构 (如 RdRp pfam00978)

### 3. BLASTN — 核酸比对

- 对选中的 contig 提交 NCBI BLASTN
- 数据库: NCBI nt (Virus-restricted)
- Top 50 hits，含 accession/description/identity/coverage/e-value

### 4. BLASTX — 翻译蛋白比对

- 6-frame 翻译后对 NCBI nr 进行 BLASTX
- 数据库: NCBI nr (Virus-restricted)
- 远缘病毒检测: 蛋白比对灵敏度优于核酸

### 5. Primer — 引物设计

- 对分类出的病毒 contig 一键设计 PCR/qPCR 引物
- 引擎: Primer3 + varVAMP 保守区策略
- 自动关联 NCBI→ICTV 物种名，填充 species_name
- 引物对质量评分 (Penalty, 4 位小数精度)
- 基因组位置可视化: 引物结合位点 + GenBank CDS/gene 轨道
- 自动缓存 NCBI GenBank 注释文件 (gb 格式)
- 结果链接到 `/primers/` 引物数据库完整详情页

```
Genome Position (6,403 bp) with GenBank annotation
Scale:  |====|====|====|====|====|====|====|====|
F1:     [F1]██████████████████████████████████[R1]
F2:        [F2]███████████████████████████[R2]
Genes:  [████Replicase█████████████][█CP█]
        CDS ████  gene ████  mat_peptide ████
```

---

## 分类工作流

```mermaid
sequenceDiagram
    actor User
    participant Web as metabuli_page.html
    participant API as metabuli_api.py :5004
    participant Meta as Metabuli binary
    participant DB as 910 MB DB
    participant BLAST as NCBI BLAST/CDD

    User->>Web: 上传 FASTA 或粘贴序列
    Web->>API: POST /api/classify
    API->>Meta: subprocess: metabuli classify
    Meta->>DB: k-mer 搜索 + LCA 分类
    DB-->>Meta: 分类结果 TSV
    Meta-->>API: 完成
    API->>API: 查询 taxid_lineage.tsv<br/>生成 8 级谱系
    API->>API: 提取病毒 contig<br/>计算 genus_avg_len
    API-->>Web: 分类结果 JSON
    Web-->>User: 渲染分类表 + Sankey + Krona

    Note over User,BLAST: 可选: 点击验证按钮
    User->>Web: 点击 BLASTN/BLASTX/CDD
    Web->>API: POST /api/blast
    API->>BLAST: 提交 NCBI BLAST/CDD
    BLAST-->>API: 轮询完成
    API-->>Web: 结果 JSON
    Web-->>User: 弹窗显示详细比对
```

---

## 关键参数

| 参数 | 值 | 说明 |
|:-----|:---|:-----|
| Metabuli 模式 | seq-mode 3 | 适合 assembled contig |
| 参考库 | 910 MB | 由 `2.Build_plant_virus_db/build_virus_db.py` 构建 |
| 最大输入 | 100 MB | 可配置 `MAX_SIZE` |
| 分类耗时 | 3-5 分钟 | 典型输入大小 |
| 数据库 taxid | 22,190 | 覆盖 ICTV 全部病毒分类单元 |
| Job 保留时间 | 2 小时 | 自动清理 |
| BLAST 等待 | ≤ 5 分钟 | 轮询间隔 5s |
| CDD 等待 | ≤ 5 分钟 | 轮询间隔 5s |

---

## 病毒 Contig 表特性

```
┌──────────────────────────────────────────────────────────────┐
│ 病毒 Contig 分类结果                                         │
│ ┌──────────┬────────┬─────────┬──────┬──────────┬──────────┐│
│ │ Contig   │ Length │ Species │ Score│ 属均长   │ 完整性   ││
│ ├──────────┼────────┼─────────┼──────┼──────────┼──────────┤│
│ │ NODE_12  │ 9,247  │ Novel   │ 0.72 │ 10,200   │ 🟢 0.91x ││  ← 近完整
│ │ NODE_5   │ 6,395  │ TMV     │ 0.98 │ 6,400    │ 🟢 1.00x ││  ← 参考质量
│ │ NODE_33  │ 1,200  │ PVY     │ 0.85 │ 9,700    │   0.12x  ││  ← 片段
│ └──────────┴────────┴─────────┴──────┴──────────┴──────────┘│
│  🟢 绿色高亮 = 0.8 ≤ length/genus_avg ≤ 1.2                │
│  单击 contig → 跳转 CDD/BLASTN/BLASTX 验证                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# 生成 taxid→ICTV 8 级谱系表 (一次性)
python build_taxid_lineage.py

# 生成演示示例
python fetch_examples.py

# 启动 Web 服务
python metabuli_api.py         # :5004
```

## 数据库依赖

| 文件 | 路径 | 来源 |
|:-----|:-----|:-----|
| Metabuli DB | `/opt/plant_virus_db/ref.virus.build.metabuli_db` | `2.Build_plant_virus_db/build_virus_db.py` |
| NCBI Taxonomy | `/opt/plant_virus_db/taxonomy/nodes.dmp` + `names.dmp` | NCBI FTP |
| Metabuli binary | `/usr/local/bin/metabuli` | 系统安装 |
| taxid_lineage.tsv | `9.metabuli/taxid_lineage.tsv` | `build_taxid_lineage.py` |

---

## 部署

| 项目 | 配置 |
|:-----|:-----|
| **systemd** | `metabuli-api.service` → :5004 |
| **Nginx** | `/metabuli/` → :5004, `client_max_body_size 110m` |
| **内存** | ~500 MB (分类进程 + taxlin 缓存) |
| **磁盘** | 910 MB (Metabuli DB) + ~50 MB (Job 临时文件) |
