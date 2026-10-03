# explorer + virus_profile 单进程合并（2026-09-17）

把 `/virus/`（Virus Profile 详情页，原 gunicorn :5006）合并进 explorer
进程（:8050），两个 Dash 实例挂同一个 Flask，数据只加载一份。

## 效果（39 上实测）

| | 合并前 | 合并后 |
|---|---|---|
| 进程 | 8050 两进程 + 5006 两进程（--preload） | 8050 单 master + 单 worker |
| 真实内存（PSS） | ~1353MB（4 进程近乎全独占） | **625MB**（master 322 + worker 303，COW 共享） |
| 节省 | — | **~728MB** |

URL 结构完全不变：`/explorer/`、`/virus/`、`/virus/files/<...>` 下载路由
全部原样可用（explorer 里的 vp-link 按钮、关系表病毒名链接、注释文件下载
都不用改）。

## 文件与改动

| 文件 | 改动 |
|---|---|
| `shared_server.py`（新增，放 virus_explorer/） | `PVDB_MERGED=1` 时创建共享 Flask，否则 `SERVER=None` |
| `wsgi_merged.py`（新增，放 virus_explorer/） | 合并入口：按 `sys.modules` 复用机制先 exec explorer 再 exec vp；`DASH_URL_PREFIX` 在各自 exec 前分别设 `/explorer/` 与 `/virus/`（两个 app.py 共用这个变量名，不能一次设死） |
| `virus_explorer/app.py` | Dash 构造加 `server=_MERGED_SERVER`（try-import shared_server，独立部署回退 None） |
| `8.virus_profile/app.py` | 同上；explorer 加载块改为 sys.modules 感知（已加载则复用，避免合并模式下二次装数据） |
| `virus-explorer.service` | ExecStart 的 `app:server` → `wsgi_merged:server`（备份 .bak_merge_20260917） |
| `virus-profile.service` | `disable --now`（文件保留，未删） |
| nginx `location /virus/` | proxy_pass 5006 → 8050（备份 .bak_merge_20260917） |

原 app.py 备份：`app.py.bak_merge_20260917`（两处各一份）。

## 部署中踩的坑

共享 Flask 上两个 Dash 的 assets blueprint 名派生自
`routes_pathname_prefix`（dash.py:760），vp 若误用 `/explorer/` 前缀会报
`ValueError: The name '_explorer_dash_assets' is already registered`——
所以 wsgi_merged 必须**在 exec vp 之前**把环境变量切回 `/virus/`。

## 回退（回到两进程部署）

```bash
ssh root@39.106.101.94 '
  cp /etc/systemd/system/virus-explorer.service.bak_merge_20260917 /etc/systemd/system/virus-explorer.service
  cp /etc/nginx/conf.d/plant-virus.conf.bak_merge_20260917 /etc/nginx/conf.d/plant-virus.conf
  systemctl daemon-reload && systemctl enable --now virus-profile
  nginx -t && systemctl reload nginx && systemctl restart virus-explorer
'
```

## 验证清单（合并后已全部通过）

- `curl :8050/explorer/`、`:8050/virus/`、经 nginx 同路径 → 均 200
- `/explorer/_dash-layout`、`/virus/_dash-layout` → 200（回调路由注册正确）
- `/virus/files/Tobamovirus%20tabaci/DQ211985.gff3` → 200（含经 nginx）
- 外网 http://39.106.101.94/explorer/ 与 /virus/ → 200
- `ss :5006` 无监听；`virus-profile` disabled + inactive
