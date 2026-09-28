# 已被取代的月度增量脚本（2026-09-28 归档）

这三个脚本是同一件工作（2026 年 1–7 月月度回填）的连续三次重写，功能被
同目录上层的 `monthly_update.sh` 完全覆盖（后者是唯一带 cron、唯一调用
`merge_to_ref.py`、唯一持久化 `last_sync_date` 的版本）。

- `run_monthly_update.sh`（7 个中文月份标签 + 状态文件）
- `run_monthly_v2.sh`（结构改为函数式，逻辑同上）
- `run_v3.sh`（英文月份标签 + tee 日志）

保留原因：其中的 `--skip-taxonomy` 调用方式在 `monthly_update.sh` 里没有，若将来需要按需跳过 taxonomy 同步，可从这里取用。
