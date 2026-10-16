# 16. fold_web — 植物病毒蛋白结构批量预测平台

> ColabFold 批量预测的 Web 化封装：**自动收集（UniProt）→ 批量预测 → 整理（pLDDT 校验）
> → 入库（`15.uniprot_plant_virus_structures/structures_index.tsv`）**，
> 同时支持**手动上传 FASTA 预测**和**手动上传 ColabFold 结果 ZIP 入库**。

## 架构

```
浏览器 ── Flask(app.py, 127.0.0.1:8800)
            ├─ 任务队列 SQLite (fold_jobs.db)，单 worker 串行（一张卡就够）
            ├─ collector  — UniProt REST 按 accession 拉序列（curl 重试，复用 15 模块通道）
            ├─ runner     — colabfold_batch 子进程（命令模板可配 FOLDWEB_PREDICT_CMD）
            └─ ingest     — rank_001 模型 + mean pLDDT → structures_selffold/{acc}.pdb
                            structures_index.tsv sources += SELF，实时刷新覆盖率面板
```

## 部署（GPU 服务器，Linux/WSL2）

```bash
# 1. 环境
pip install "colabfold[alphafold]" flask          # ColabFold ≥1.6.3 支持 pip 直装
# 2. 启动（先拷整个 16.fold_web/ 与 15.uniprot_plant_virus_structures/structures_index.tsv 同仓）
cd 16.fold_web
python app.py                                      # 默认 127.0.0.1:8800
# 或生产: gunicorn -w 1 --threads 4 -b 127.0.0.1:8800 app:app   （-w 必须为 1，队列在进程内）
# 3. nginx 反代（可选，参照 deploy/nginx_full.conf 追加 server 块）
```

环境变量：`FOLDWEB_MODULE_DIR`（数据模块根，默认 ../15.uniprot_plant_virus_structures）、
`FOLDWEB_PREDICT_CMD`（预测命令模板，`{input}/{output}` 占位）、`FOLDWEB_HOST/PORT`。
队列 worker 随首个请求启动；长期无人访问也可单独拉起 worker：
`python -c "import foldcore as fc; fc.Worker().start(); import time; time.sleep(1<<30)"`。

## 网页功能

| 功能 | 入口 |
|:--|:--|
| 覆盖率面板（蛋白/物种×自身结构/含 BFVD，实时刷新） | 首页顶部卡片 |
| 自动任务：粘贴 accession 列表（实时格式校验 + 去重计数） | 新建任务 |
| 一键填入全部 pending（带条数确认） | 新建任务 |
| 手动任务：上传 FASTA（拖拽 + 上传进度条 + 序列数预览） | 手动上传 ① |
| 结果入库：上传 ColabFold 输出 ZIP（拖拽 + 进度条） | 手动上传 ② |
| 任务队列：状态过滤 / 进度条 / 相对时间 / 日志跟随与复制 | 任务队列表 |
| 失败任务重试、完成任务删除 | 任务表操作列 |

## API（2026-10-04 安全加固 + 新端点）

| 端点 | 说明 |
|:--|:--|
| `GET /api/stats` | 覆盖率统计 |
| `GET /api/jobs?limit=N` | 任务列表（仅 UI 字段，不含 workdir/log_path） |
| `GET /api/job/<id>/log` | 任务日志（runner.log 尾部 20KB，含收集/入库阶段消息） |
| `POST /api/job/new` | accession 建任务（单任务上限 20,000 条） |
| `POST /api/job/upload_fasta` | 上传 FASTA（后缀白名单 .fa/.fasta/.txt） |
| `POST /api/job/upload_results` | 上传结果 ZIP（解压预检见下） |
| `POST /api/job/<id>/retry` | **新**：失败任务按原参数重新排队 |
| `DELETE /api/job/<id>` | **新**：删除完成/失败任务记录（jobs/ 文件保留） |
| `GET /api/export/foldify?max=N` | Foldify 导出（默认 1,000，上限 5,000，防同步长请求超时） |
| `GET /pending_accessions.txt` | 待预测清单 |

2026-10-04 审计加固（沙箱 25 项断言全通过，含 6 项上传安全用例）：

- 上传文件名经 `secure_filename` 净化 + 后缀白名单 + 服务端改名（不信任客户端文件名，
  杜绝 `../../evil.sh` 类路径穿越写入）；
- ZIP 解压前预检：成员数（≤20 万）、总解压量（≤50 GB）、成员路径合法性
  （拒绝绝对路径 / `..` / 盘符），防 zip 炸弹与 zip-slip；
- `structures_index.tsv` 写回改为临时文件 + `os.replace` 原子替换；
- collector 临时文件每次重试前清空（此前失败块会误读上一块残留、虚增 collected 计数）；
- 任务收集/入库阶段日志写入 runner.log（页面上能看全链路，不再只进服务端 stdout）；
- worker 启动加互斥锁（修复 threaded 模式下首个请求可能触发双 worker 的竞态）；
- 非法 JSON / 非法 accession / 超大任务均返回 400 而非 500；前端全字段 HTML 转义（防
  任务 message 回显 XSS）。

## 现状与边界（2026-10-04）

- **本机（Windows，无 GPU）已通过沙箱全链路冒烟测试**：stub 预测器验证了
  收集→预测→入库→覆盖率联动、格式校验、ZIP 入库、pending 联动，全部通过；
  真实预测需部署到 GPU 服务器（见上）。
- 待预测清单来源：`pending_prediction_bfvd_only.tsv`(3,333) + `pending_prediction.tsv`(365)
  = 3,556 条；批量离线输入包另见 `15.uniprot_plant_virus_structures/colabfold_input/`。
- **304 条 >2,700 aa 多聚蛋白不在本平台直接预测范围**，需先结构域切分
  （清单：`colabfold_input/batch_polyprotein/polyprotein_list.tsv`）。
- 约 55 条 <50 aa 极小蛋白可跑但结果参考价值有限。
- 安全：默认只绑 127.0.0.1；公网部署请套 nginx + 认证（应用本身无鉴权）。
- 大批量（3,394 条）建议 MMseqs2 API 模式夜间挂机；服务器能放本地 UniRef30/PDB70
  数据库（约 2 TB）则更稳更快。

## Foldify 外部通道（2026-10-03 接入）

Foldify（https://foldify-open.cloud.e-infra.cz/ ，捷克 e-INFRA CZ，MIT 开源）：
免费无登录的在线预测平台，集成 **AlphaFold3 / AlphaFold2 / ColabFold / OmegaFold /
ESMFold**（MultiFold 可多模型对比）。限制：单序列 ≤600 aa、每用户并发 5、
**无公开 API**、结果保留 7–30 天。

集成方式（三档）：
1. **手动通道导出**：`/api/export/foldify` 或首页 ③ 链接 —— 把待预测清单中 ≤600 aa
   的序列按 100 条/块打包 ZIP（含 manifest），人工到 Foldify 逐条提交；
   跑完下载结果打包，走首页「上传结果入库」导回 structures_index（sources += SELF）。
2. 15 号模块 webapp 的蛋白详情面板已加 Foldify 直达链接（单条临时预测用）。
3. **自建 Foldify**（远期可选）：源码 MIT（github.com/CERIT-SC/foldify-open），
   Docker/K8s 部署，可给本平台增加 AF3/OmegaFold/ESMFold 后端——需要 K8s GPU 集群，
   单卡服务器不适用。

边界：批量主体（3,394 条）仍走本地 ColabFold；Foldify 仅作人工小批量补漏与多模型
交叉验证，勿对其做自动化批量提交（公平使用限制）。

## 沙箱回归测试（无 GPU 也可跑）

`python smoke_sandbox.py`：把模块目录指向临时副本、预测器换成 `test_stub_predictor.py`，
全链路冒烟 11 项——首页/stats 账目、FASTA 上传→队列→stub 预测→入库（SELF 落盘+
sources 翻转）→pending 联动、Foldify 导出 ZIP 结构（manifest/README/全部 ≤600aa）。
**不写真实 structures_index.tsv**，真实索引只读；2026-10-06 全绿，并借此抓出并修复
foldcore 缺 `import tempfile` 导致 Foldify 导出 500 的 bug。

## AF3 权重与 AlphaFast 通道（2026-10-04 就位）

**权重**：`models/af3.bin.zst`（973 MB zstd 压缩，解压后约 1.07 GB）。
DeepMind 已取消表单申请制，直链
`https://storage.googleapis.com/alphafold3/af3.bin.zst` 公开下载，下载即受
[AF3 Model Parameters Terms of Use](https://github.com/google-deepmind/alphafold3/blob/main/WEIGHTS_TERMS_OF_USE.md)
约束：**非商业、禁止临床用途、权重不得转分发**（学术植物病毒研究合规）。
GFW 环境直连需 `--ssl-no-revoke` 绕过证书吊销检查误报（CRYPT_E_REVOCATION_OFFLINE）：

```bash
curl -L --ssl-no-revoke -C - --retry 8 --retry-delay 10 --retry-all-errors \
  -o models/af3.bin.zst https://storage.googleapis.com/alphafold3/af3.bin.zst
```

校验记录（2026-10-04）：1,020,545,840 字节精确匹配；zstd 全量流解压
1,146,811,260 字节通过；解压流 sha256 前 16 位 `df8bbf2621f17dd3`。

**AlphaFast**（github.com/RomeroLab/alphafast，代码 CC-BY-NC-SA）：AF3 高吞吐封装，
用 MMseqs2-GPU 替换 Jackhmmer 同源搜索（68.5×），端到端 22.8×（单 H200；4×H200
约 8 s/输入）。三种模式：Docker 本地 / Singularity+SLURM 集群（示例 `alphafast.sl`，
数据库放 NVMe）/ Modal 无服务器（基准 $0.035/输入，长序列按时长上浮）。
输入为 AF3-dialect JSON 文件目录，输出 cif（B-factor 即 pLDDT）与本平台
入库、viewer 通道天然兼容。

**对 365 条零覆盖蛋白缺口的适配**：实际长度 286–3,471 aa（仅 1 条 <2,000；
304 条 >2,700 aa，最长 3,471 aa 在 AF3 token 预算内**可直跑**，结构域切块
精修可选非必需）。路径取舍：
① 本机 Docker 不可行（无 NVIDIA 卡）；② Modal 最贴合现状（全套约 $30–80，
仅支持信用卡、不支持支付宝，国内访问可能需代理）；③ GPU 服务器/超算走
SLURM 模式，**下单前必须确认 NVIDIA 卡型**（A800/H800 可用；昇腾等国产卡
跑不了 MMseqs2-GPU/JAX）。AF3-dialect JSON 输入包已生成：
`15.uniprot_plant_virus_structures/alphafast_input/`（365 个任务 + manifest +
README；生成脚本 `oneoff_scripts/uniprot_pdb_fetch/prepare_alphafast_input.py`）。
