# 13. OneKP Virus — 千植物转录组病毒 Dashboard

> 1KP (OneKP) 1,341 个植物转录组样本的病毒组检测结果，独立 Dash 应用，挂载于 `/onekp/`。

**服务**: `onekp-dashboard.service`（服务器现役单元，enabled），端口 8051，`/opt/plant_virus_db/plant_virus_db_pipeline/13.onekp_virus/`

---

## ⚠️ 目录约定：数据文件与脚本同层是代码写死的设计

`onekp_app.py` 中 `RESULTS_DIR = BASE_DIR`（数据 TSV/CSV 与应用同层），**不要把数据文件移入子目录**，否则应用与部署脚本都会失效。

## 文件说明

### 应用与分析脚本
| 文件 | 说明 |
|---|---|
| `onekp_app.py` | Dash Web 应用（优先读 `.cache/` pickle，缺失时回退到同层 TSV/CSV） |
| `prep_onekp_data.py` | 数据预处理，生成 `.cache/onekp_data.pkl` |
| `enrich_onekp_data.py` | 宿主富集分析，生成 `.cache/onekp_enriched.pkl` |
| `analyze_full.py` / `analyze_novel.py` | 全量 / 新病毒分析 |
| `check_onekp_meta.py` | 样本元数据校验 |

### 应用输入数据（勿移动）
| 文件 | 说明 |
|---|---|
| `all_viruses.best.summary.tsv` | 全部病毒检测汇总（主数据） |
| `high_conf.summary.tsv` / `high_conf.summary.discarded.tsv` | 高置信结果 / 被剔除记录 |
| `onekp_all_samples.csv` / `onekp_download_links.csv` | 样本列表 / 下载链接（utf-16-le 编码） |
| `sample_resource_usage.tsv` | 样本资源占用 |
| `virus_host_full_analysis.csv` | 病毒-宿主全量分析（`analyze_full.py` 输入） |

### 产物
| 位置 | 说明 |
|---|---|
| `results/` | 无脚本引用的历史分析输出（`filter_stats.*`、`virus_host_pairs_*`），仅供参考 |
| `.cache/` | 运行时 pickle 缓存（可删，下次启动自动重建） |

### 部署
- `onekp-dashboard-prod.service` — 本地留存的 systemd 单元，内容与服务器现役单元一致（仅文件名不同；服务器 2026-09 核实：active 的是 `onekp-dashboard.service`，另有一个 disabled 的 `onekp-dashboard-prod.service`）
- `deploy_onekp_to_prod.py` — 部署脚本（2026-09-13 已修正：本地源路径指向本目录，服务器目标 `13.onekp_virus/`，单元名 `onekp-dashboard.service`，nginx conf 目标改为实际加载的 `/etc/nginx/conf.d/plant-virus.conf`）

## 历史遗留（已清理）

`3.virus_explorer/` 下曾有一份旧拷贝（`onekp_app.py`、`prep_onekp_data.py`、`enrich_onekp_data.py`、`onekp-dashboard.service`、`deploy_onekp.sh`），版本旧于本目录。2026-09-13 已上服务器核实：线上跑的就是本目录的 `onekp_app.py`（md5 一致），服务器上不存在旧拷贝，且 `3.virus_explorer/app.py` 仅以 URL 链接指向 `/onekp/`、无文件依赖——旧拷贝已于同日从本地删除。
