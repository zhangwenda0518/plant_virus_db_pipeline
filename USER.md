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
- 阿里云 ECS: root@39.106.101.94 (密码 @ZWDasd248655)
- 线上: http://39.106.101.94
- 本地仓库: D:\桌面\C-host_classify\plant_virus_db_pipeline

### 生产服务实际位置 (注意: 部分与本地仓库目录不同!)
| 路由 | 服务 | 实际代码位置 |
|---|---|---|
| `/` `/reference/` `/te/` `/photos/` `/genes/` | nginx 静态 | /opt/plant_virus_db/plant_virus_db_pipeline/docs/* |
| `/literature/` | Flask :5003 (literature-tracker.service) | 7.literature_tracker/api_server.py + web/index.html (静态由 Flask send_static_file 提供) |
| `/primers/` | gunicorn :5000 (primer-web.service) | **/opt/plant_virus_db/primer_design_server/step5_web_server.py** (非本地 4.virus_primer/) |
| `/virus/` | [ARCHIVED] 已融入 `/explorer/`「病毒档案」Tab, systemd 已停用 | _archived_13.virus_profile/ |
| `/metabuli/` | Flask :5004 (metabuli-api.service) | 9.metabuli/metabuli_page.html (每次请求 read_text, 改完无需重启) |
| `/vector/` | Flask :5005 (vector-host.service) | 8.plant-insect/api_server.py + vector_page.html (启动时读入, 改完需重启) |
| `/knowledge/` | uvicorn pv_rag :5002 (nohup, 非 systemd) | **/opt/src/plant_virus_rag/** (editable install), UI 在 api/routes/ui.py |
| `/explorer/` | Dash :8050 (virus-explorer.service) | (无导航条, 暂未加 i18n) |

### 常用操作
- 重启服务: `systemctl restart primer-web vector-host metabuli-api literature-tracker`
- 重启 knowledge: `fuser -k 5002/tcp; cd /opt && PATH=/opt/miniconda3/envs/pv_rag/bin:$PATH nohup python -m uvicorn plant_virus_rag.api.main:create_pv_app --factory --host 0.0.0.0 --port 5002 > /opt/pv_rag_api.log 2>&1 &`
- nginx: `nginx -t && nginx -s reload`
- 备份目录: /opt/i18n_backup_20260717_034102/

### 已知遗留 bug (已修复)
- ~~`/knowledge/query` 偶发 500: query.py:_enrich_citations 的 CitationOut.authors 期望 list 但 DB 返回 str~~ → 已修复 (2026-07-24, 添加 _parse_authors 兼容 str/list)
- 重启 Knowledge RAG 必须先 `cd /opt` (否则读不到 .env.local)
