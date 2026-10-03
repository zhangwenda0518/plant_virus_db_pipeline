# 12. PV-miRNA — 植物抗病毒 miRNA 预测工作台

> 基于自定义 Smith-Waterman 比对引擎的植物病毒 miRNA 靶标预测。Python stdlib HTTPServer + SQLite。7 物种原型。

**Live**: http://39.106.101.94/pamirdb/

---

## 架构

```
12.pamirdb/
├── run.py                     # 管线启动器
├── run_v7.sh                  # 生产部署脚本
├── backend/
│   └── server.py              # Python stdlib HTTP 服务 (:8000)
├── scripts/
│   ├── alignment.py           # ★ 核心: 自定义 Smith-Waterman 比对引擎
│   ├── pipeline.py            # 批量预测管线
│   ├── virus_genes.py         # 病毒蛋白 CDS 坐标 + 注释
│   ├── download_data.py       # 数据获取 (miRBase + 病毒基因组)
│   └── ...
├── data/
│   ├── pamirdb.sqlite         # SQLite 数据库 (WAL 模式)
│   ├── predictions.json       # 预测结果
│   ├── mirna/                 # miRNA 序列 (plant_mirnas.json)
│   └── virus_genomes/         # 病毒基因组 (viruses.fasta + viruses.json)
└── figures/
```

## 核心预测引擎

`scripts/alignment.py` 实现了自定义的 Smith-Waterman 式动态规划比对引擎，**不调用 miRanda/psRNATarget/RNAhybrid 等外部工具**。

- **碱基对得分**: WC 配对 (A:U, G:C) = +5, wobble (G:U) = +2, 错配 = -3
- **空位罚分**: gap_open = -9, gap_extend = -4
- **Seed 区检查**: miRNA 位置 2-8 必须全部为 WC 或 wobble 配对
- **可选约束**: `required_positions` (指定位置必须配对), `check_au_positions` (指定位置必须为 A/U)
- **输出字段**: 20 字段, 含 similarity (WC+wobble 占比), target_protein (命中病毒蛋白), matching_status (Withinmatch/Overlapping), position_binding (每个位置的 WC/wobble/mismatch/gap 状态)

## 批量预测

`scripts/pipeline.py` 对所有 miRNA × 病毒基因组组合做笛卡尔积遍历, 每 200 对输出进度。通过 `align_mirna_to_target()` 调用比对引擎, 仅保留 `passes_filters=True` 的结果。按物种和病毒科输出统计摘要。

## 病毒蛋白注释

`scripts/virus_genes.py` 维护 `VIRUS_GENES` 字典, 记录每种病毒 CDS 的坐标区间和产物名称。`get_target_gene(virus_id, start, end)` 通过区间匹配判定 miRNA 靶向的是哪个病毒蛋白 (CP/RdRp/MP 等), 同时判定 matching_status。

## Web 后端

`backend/server.py` — Python 标准库 `http.server.HTTPServer` + `BaseHTTPRequestHandler` 实现的纯 stdlib HTTP 服务器。首次启动自动建 SQLite 数据库 (WAL 模式, 四表: mirnas/viruses/virus_hosts/predictions), 空库时从 JSON/CSV/FASTA 自动导入。查询支持按 miRNA ID/物种/病毒 ID/病毒科/靶标蛋白分页筛选。

## 数据量

| 指标 | 数值 |
|:-----|:----:|
| 原型植物物种 | 7 (拟南芥/大豆/水稻/高粱/番茄/葡萄/玉米) |
| miRNA 预测查询集 | 80,783 (来自 11.antiviral_genes 的 799 物种; 已剔除 2,414 条 NR_* 前体与 2,403 条 >50 nt 序列, 见 `data/mirna/plant_mirnas_full_stats.json`) |
| 预测算法 | 自定义 Smith-Waterman (非 miRanda/psRNATarget/RNAhybrid) |
| 数据库格式 | SQLite (pamirdb.sqlite) |

## 方法与诚实性说明（2026-10-03 修订）

- **引擎构成（非多工具共识）**：全部预测由单一自研引擎产生——Smith-Waterman 式 DP 比对（`scripts/alignment.py`，`consensus_detail` 中记为 `custom SW-DP`）+ 本地启发式复核层（`local heuristic recheck` / `local MFE heuristic` 等）。**不调用 miRanda / psRNATarget / RNAhybrid / RNA22 / TAPIR / psRobot**；`miranda_*` / `psrna_*` / `rnahybrid_*` 只是 API/数据库的历史字段名，前端展示文案已改为"自研比对 + 启发式复核（非外部工具）"。
- **能量字段与 ViennaRNA**：`alignment.py::_estimate_energy` 在检测到 Python `RNA` 模块（ViennaRNA）时用其 MFE，否则退回自建最近邻近似。因此 `energy` / `rnahybrid_mfe` 的绝对数值**依赖运行环境**，且当前不记录 ViennaRNA 版本（也未在任何 manifest 中固定），跨环境比较能量值前请先确认该依赖是否安装及其版本。
- **预测集过滤**：查询集排除 NCBI `NR_*` 前体记录与 >50 nt 序列；比对结果加总 gap 上限 `MAX_GAPS=10`（超出不入结果，历史数据中的 30-gap"最强互作"属于旧版漏洞产物）；病毒序列超过 `SEQ_MAX_LEN=15000` 时截断并逐条告警、汇总到 `data/truncated_viruses.tsv`（预期 91 条）。
- **验证集口径**：`validation_amirna.py` 的候选表混合了实验证据与 in-silico 预测；仅 `experimental=True` 的条目会置 `validated=True`（前端显示 "Exp. Validated"），预测类条目标注 `in-silico prediction`，无法溯源的条目（原 `*_2025` 占位 PMID）已移除假 PMID 并标注 `unverified`。
- **存量数据**：`data/predictions_v7_annotated.json` 与线上 SQLite 中的 11,006 条预测生成于上述修复之前（含前体命中、>10 gap 命中、旧 `miRanda+psRNATarget+RNAhybrid` 字样），**需重跑 v7 管线后才会采用新口径**。
- **病毒 ID 链接**：预测的 `target_virus_id` 为 GenBank accession，服务启动时会从 `viruses_full.json` 建立 accession 补充索引（annotation 表优先，accession 回落），/api/scan 与 family 字段由此修复。

## 快速开始

```bash
python run.py                    # :8000
python run.py --pipeline         # 仅运行预测管线
python run.py --all              # 管线 + 服务
bash run_v7.sh                   # v7 生产部署
```

## 部署

| 项目 | 配置 |
|:-----|:-----|
| **服务类型** | Python stdlib HTTPServer (非 FastAPI/Uvicorn) |
| **systemd** | `pamirdb.service` → :8000 |
| **Nginx** | `/pamirdb/` → proxy_pass `http://127.0.0.1:8000/` |
| **数据库** | SQLite WAL 模式, 启动时自动建表/导入 |
