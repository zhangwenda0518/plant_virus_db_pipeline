# User Profile

> This file describes the user you serve. Update it as you learn more.

## Name

## Preferences

- 改动要仔细、可排查、可回滚；本地与服务器务必先核对一致性再动手
- 不主动 commit，除非明确要求

## Timezone

Asia/Shanghai (服务器北京时间)

## Context

### 部署环境
- 阿里云 ECS: root@39.106.101.94 （凭据在本地密码管理器，严禁写入仓库；2026-10-03 前的历史口令已泄露，必须轮换）
- 线上: http://39.106.101.94
- 本地仓库: D:\桌面\C-host_classify\plant_virus_db_pipeline

### 生产服务实际位置 (注意: 部分与本地仓库目录不同!)
| 路由 | 服务 | 实际代码位置 |
|---|---|---|
| `/` `/reference/` `/eve/` `/photos/` `/genes/` | nginx 静态 | /opt/plant_virus_db/plant_virus_db_pipeline/docs/* |
| `/literature/` | Flask :5003 (literature-tracker.service) | 7.literature_tracker/api_server.py + web/index.html (静态由 Flask send_static_file 提供) |
| `/primers/` | gunicorn :5000 (primer-web.service) | **/opt/plant_virus_db/primer_design_server/step5_web_server.py** (非本地 4.virus_primer/) |
| `/virus/` | [ARCHIVED] 已融入 `/explorer/`「病毒档案」Tab, systemd 已停用 | archive/_archived_13.virus_profile/ |
| `/metabuli/` | Flask :5004 (metabuli-api.service) | 9.metabuli/metabuli_page.html (每次请求 read_text, 改完无需重启) |
| `/onekp/` | Dash :8051 (onekp-dashboard.service) | 13.onekp_virus/onekp_app.py (2026-09 核实: md5 与本地一致) |
| `/vector/` | Flask :5005 (vector-host.service) | 8.plant-insect/api_server.py + vector_page.html (启动时读入, 改完需重启) |
| `/knowledge/` | uvicorn pv_rag :5002 (nohup, 非 systemd) | **/opt/src/plant_virus_rag/** (editable install), UI 在 api/routes/ui.py |
| `/explorer/` | Dash :8050 (virus-explorer.service) | (无导航条, 暂未加 i18n) |
| `/uniprot3d/` | nginx 静态 (conf.d/plant-virus.conf 2026-10-07 新增) | 15.uniprot_plant_virus_structures/（轻量上线：webapp+索引 TSV；554MB PDB/182MB cif 结构文件未上传，3D 查看器点开结构会 404，补传后即恢复；运行期产物 colabfold_input/ 与 *.db 已屏蔽 404） |
| fold_web (16) | 2026-10-07 有限上线：`/foldweb/`（nginx Basic Auth，凭据在本地密码管理器，严禁入库）+ GPU 服务器本地 8800（SSH 隧道） | 服务器为**无 GPU 模式**：自动预测禁用（no_gpu_predict.sh 提示改走上传通道），上传结果入库/Foldify 导出/统计可用；systemd 服务 `foldweb.service`；入库后需在服务器重跑 `webapp/build_data.py` 刷新线上页面 |

### 常用操作
- 重启服务: `systemctl restart primer-web vector-host metabuli-api literature-tracker`
- 重启 knowledge: `fuser -k 5002/tcp; cd /opt && PATH=/opt/miniconda3/envs/pv_rag/bin:$PATH nohup python -m uvicorn plant_virus_rag.api.main:create_pv_app --factory --host 0.0.0.0 --port 5002 > /opt/pv_rag_api.log 2>&1 &`
- nginx: `nginx -t && nginx -s reload`
- 备份目录: /opt/i18n_backup_20260717_034102/

### 已知遗留 bug (已修复)
- ~~`/knowledge/query` 偶发 500: query.py:_enrich_citations 的 CitationOut.authors 期望 list 但 DB 返回 str~~ → 已修复 (2026-07-24, 添加 _parse_authors 兼容 str/list)
- 重启 Knowledge RAG 必须先 `cd /opt` (否则读不到 .env.local)
