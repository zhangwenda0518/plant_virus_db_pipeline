# phylogeo_offload — MAFFT+FastTree 中转 246 计算服务器

39（公网 web，2 核 3.5G）跑不动比对/建树，246（校园网，256 核 644G）空有算力。
39 连不进校园网、246 能出站连 39，所以只有 **pull 模式**可行。

## 数据流

```
用户点 RTT 按钮
  → 39 phylogeo_app: run_rtt()
  → 39 phylo_offload.run_align_tree_remote():
       把 input.fa 写进 virus_explorer/phylo_jobs/<jid>/，等 done.json
  → 246 worker_246.py（cron 每分钟拉起 + flock 防重叠，进程内 3s 一轮）：
       ssh 39 → ls spool → mkdir claim 原子抢占 → scp input.fa 下来
       → mafft --thread 8 + fasttree -nt -gtr
       → scp 回传 aligned.fa / rtt.nwk / done.json
  → 39 拿到结果继续 RTT 回归 / DRT / LSD2（纯 Python，2 核足够）
```

所有 SSH 连接都由 246 发起（246 的 `~/.ssh/id_ed25519.pub` 已加到
39 的 `/root/.ssh/authorized_keys`），39 全程只读写自己的磁盘。

## 文件

| 文件 | 位置 | 作用 |
|---|---|---|
| `phylo_offload.py` | 39 `virus_explorer/` | 提交任务 + 等结果 + 心跳判断 |
| `worker_246.py` | 246 `~/phylogeo_worker/` | 轮询拉取、跑 mafft+fasttree、回传 |
| `rtt_module.py`（改动） | 39 `virus_explorer/` | 比对/建树段改为远程优先、本地回退 |

## 保险机制（网站永远可用）

1. **心跳**：worker 每轮 touch `phylo_jobs/heartbeat`；超过 180s 无心跳，
   39 侧判定 worker 离线 → 直接本地跑，用户无感。
2. **任务超时**：投出去 600s 没回音 → 39 本地跑（与原行为一致）。
3. **worker 报错**：worker 把 `error.json` 推回 39 → 39 立刻回退本地。
4. **僵尸抢占**：claim 超过 30 分钟自动清除，任务可被重新抢。
5. **现场清理**：任务目录超 2 小时自动删；结果被取走后当场删。

开关：39 上 `export PHYLO_OFFLOAD=0` 可整体禁用中转（默认启用）。

## 246 侧 crontab（用户级，无需 root）

```
* * * * * /usr/bin/flock -n /tmp/phylogeo_worker.lock /usr/bin/python3 /home/zhangwenda/phylogeo_worker/worker_246.py >> /home/zhangwenda/phylogeo_worker/worker.log 2>&1
```

结果字典新增 `align_engine` 键：`remote-246`（走了中转）/ `local-39`（回退）。
