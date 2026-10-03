# 安全处置手册 — 凭据泄露修复（2026-10-03）

> 配套体检报告：`AUDIT_REPORT_20261003.md` 第一节。
> 代码侧脱敏已全部完成（见下文"已完成"）；**标注 [必须由你执行] 的步骤只有账号持有人能做**，按顺序来。

---

## 一、已完成（代码侧，2026-10-03）

| # | 措施 | 位置 |
|---|---|---|
| 1 | USER.md 移除 root 明文口令 | `USER.md:19` |
| 2 | U1 NCBI key/假邮箱 → `NCBI_API_KEY` / `NCBI_EMAIL` 环境变量 | `1.Prepare_plant_virus_pipeline/U1_incremental_update.py:69-71` |
| 3 | pmc_fulltext key → 环境变量 | `7.literature_tracker/pmc_fulltext.py:7` |
| 4 | DeepSeek/嵌入 key → 环境变量（4 个脚本） | `update_cron.sh`（改 source .env）、`run_summarize_batches.py`、`build_rag.py`、`pv_rag/scripts/_diag.py` |
| 5 | root 口令 → `ECS_ROOT_PWD` 环境变量（2 个部署脚本） | `13.onekp_virus/deploy_onekp_to_prod.py`、`analysis/scripts/deploy_canonical.py` |
| 6 | NCBI key → 环境变量（8 个 analysis 脚本） | `analysis/onekp_compare/*`、`analysis/protein_lengths/*`、`analysis/virus_host_order_matrix/*` |
| 7 | key 不再出现在子进程命令行（ps 不可见） | `run_summarize_batches.py` 改 env 传递 |
| 8 | .gitignore 补录安全边界 | `.mimosa/`（含密钥快照副本）等 8 个工具目录 + 根级大目录 |
| 9 | pre-commit 密钥扫描钩子（已启用 `core.hooksPath=.githooks`） | `.githooks/pre-commit` + `scripts/check_secrets.py`，含已泄露凭据指纹黑名单 |
| 10 | `RECORDS_TOTAL=-1` 修复 + 版本串负值守卫 | `docs/data/DATA_VERSION`、`config.py:get_version_string()` |

环境变量约定（写入本机/服务器 `~/.bashrc` 或 `.env`，**不要写入仓库**）：
```
NCBI_API_KEY=...      # 吊销后重新申请的新 key
NCBI_EMAIL=...        # 真实联系邮箱（NCBI 政策要求）
DEEPSEEK_API_KEY=...  # 文献摘要/RAG
SILICONFLOW_API_KEY=...  # 嵌入模型
ECS_ROOT_PWD=...      # 部署脚本过渡用；长期应改 SSH key 登录并禁用口令
```

## 二、[必须由你执行] 第 1 步：轮换全部已泄露凭据

凭据只要还在用，清不清历史都等于没清。顺序：

1. **改阿里云 ECS root 密码**（控制台重置即可），并检查 `lastb`/`/var/log/secure` 有无可疑登录；
   长期整改：改用 SSH 密钥登录 + `PasswordAuthentication no`。
2. **NCBI**：登录 NCBI 账号 → Settings → API Key Management → 删除旧 key → 生成新 key。
3. **DeepSeek 平台**：删除两把旧 key（`sk-a81b…`、`sk-b82f…`），生成新 key。
4. **SiliconFlow**：删除旧嵌入 key（`sk-tegn…`），生成新 key。
5. 新 key 按上表写入环境变量，**跑一遍受影响脚本确认正常**（`python 1.Prepare_plant_virus_pipeline/U1_incremental_update.py --dry-run` 等）。

## 三、[必须由你执行] 第 2 步：清除 git 历史中的凭据与版权文件

当前仓库有 14 个未推送提交、9,321 条工作区脏记录，**不宜由自动化直接改写历史**。请在提交/推送完当前工作后，找一台干净环境执行：

```bash
# 0) 备份
git clone --mirror git@github.com:zhangwenda0518/plant_virus_db_pipeline.git pvdb_purge.git
cd pvdb_purge.git

# 1) 安装 git-filter-repo:  pip install git-filter-repo

# 2) 写替换规则 passwords.txt（不要把字面量写进任何会入库的文件！）
#    提取字面量（已吊销，仅本地使用）：
#      NCBI key:   git show 82df6663:1.Prepare_plant_virus_pipeline/U1_incremental_update.py | grep -oE '"[0-9a-f]{32}"' | head -1
#      root 口令:  git show origin/main:USER.md | grep -oE '@[A-Za-z0-9]{8,}'
#      LLM keys:   git show <对应历史提交>:<文件> 中 sk- 开头的字面量
#    passwords.txt 每行一条（本地临时文件，用完删除）：
#      <旧字面量>==>***REMOVED_NCBI_KEY***
#      <旧口令>==>***REMOVED_PASSWORD***
#      <sk-旧key>==>***REMOVED_KEY***
git filter-repo --replace-text ../passwords.txt

# 3) 顺带把版权材料从全部历史中剔除（体积也大幅缩小）
git filter-repo --invert-paths --path 10.virus_photos/15587070.pdf --path 10.virus_photos/15587070.docx

# 4) 验证后强推（GitHub 需先在 Settings 解除分支保护；force push 通知所有协作者重新 clone）
git push --force --mirror

# 5) GitHub 侧收尾：Settings → Support → 请求清缓存（否则旧 blob 经 commit hash 仍可拉取）
```

> 注意：`git filter-repo` 会移除 remote 配置，push 前重新 `git remote add origin …`。
> 强推后所有 clone 失效，需通知协作者；线上服务器 `/opt` 的部署目录是独立文件树，不受影响，但应同步拉新。

## 四、[必须由你执行] 第 3 步：Web 暴露面加固（代码修复见对应模块提交，需重新部署）

| 端点 | 修复 | 部署动作 |
|---|---|---|
| `/literature/api/summarize/paper`、`/digest` | 加 Token 鉴权 + base_url 白名单 + 输入限长 | 更新 `7.literature_tracker/api_server.py` 后 `systemctl restart literature-tracker`；nginx 对 `/literature/api/` 加 `limit_req` |
| `/api/chat`（primer 两份 step5） | api_url 服务端固定、去掉服务器 key 回退 | 更新 `/opt/plant_virus_db/primer_design_server/step5_web_server.py` 后重启 primer-web |
| `/knowledge/` | 鉴权 + 限流 | 重启 5002（`USER.md` 常用操作） |
| `/virus/files/<path>` 路径穿越 | `send_from_directory` 修复 | 更新 explorer 代码后 `systemctl restart virus-explorer` |
| 全站 | HTTPS + 安全头 + `server_tokens off` | 阿里云免费证书 + nginx 配置更新 |

## 五、防再犯

- pre-commit 钩子已启用（本仓库 `git config core.hooksPath .githooks`，克隆者需自行执行一次，README 补充说明）。
- 新密钥只走环境变量；`.env` 已在 .gitignore。
- 每季度跑一次：`grep -rEn "sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}" --include="*.py" --include="*.sh" .`
