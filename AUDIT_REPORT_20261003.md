# 植物病毒数据库管线 · 全库体检报告（审稿人视角）

> 审计日期：2026-10-03 ｜ 范围：15 个模块约 620 个脚本 + 根级基础设施 + git 仓库卫生
> 方法：9 路并行深审（主链路逐行读 + 长尾模式扫描）+ 全局机械化检查（809 个 .py 全量语法编译、密钥模式扫描、git 追踪大文件清点）+ 关键 P0 断言二次复核与最小实验复现
> 本报告只读审计产物，未修改任何业务文件。密钥/口令值已脱敏。

---

## 总体结论

工程骨架与踩坑留痕文化是真实亮点（护栏账本、断点续跑、CHANGELOG 自我纠错记录），但当前状态**不可直接投稿、不可安全公开**。三类致命问题：

1. **凭据已泄露**：生产服务器 root 口令在公开 GitHub 仓库当前树中；NCBI API key 在公开仓库历史 blob 与当前 HEAD 中。
2. **对外发布的数据存在系统性失真**：引物库的"验证/评分/推荐级别"装配链断裂（4 处独立断点）；文档关键数字五个批次互斥（8,465/8,484/11,956/12,159/实测 9,022）；PAmiRDB 线上预测接口 100% 报错且"多工具共识"名不副实。
3. **版权材料整本入库公开再分发**：95 MB 在版权专著 PDF + 42 MB DOCX + 2,868 张无授权图片已推送公开仓库。

---

## 一、🔴 P0 — 安全（须立即处置）

### S1. 生产服务器 root 口令已在公网 GitHub（已发生泄露，非风险）
- `USER.md:19`：root 登录名 + 明文口令直接写在行内（原文已从工作区移除，字面量见 git 历史），已验证在 `origin/main` 当前树中；仓库已验证公开（GitHub 可匿名访问，README 首页还公布站点 IP 与 12 个服务端口映射）。
- 同一口令另复用于 2 个未跟踪部署脚本（`13.onekp_virus/deploy_onekp_to_prod.py:14-16`、`analysis/scripts/deploy_canonical.py:14-16`）。
- **处置（顺序不可乱）**：① 立即改密 + 换 SSH key 登录；② 排查服务器登录日志；③ `git filter-repo`/BFG 清历史后强推；④ 全盘轮换所有复用该口令的服务；⑤ 加 pre-commit 密钥扫描。

### S2. NCBI API key 已在公开历史中
- `1.Prepare_plant_virus_pipeline/U1_incremental_update.py:70`（`--api-key` 默认值）、`7.literature_tracker/pmc_fulltext.py:7`、另 ≥10 个未跟踪文件散落同一 key；`.mimosa/` 基线快照中还有 5+ 份副本（未被 .gitignore 排除）。
- 已验证：初始提交 `82df6663` 即含该 key 且**是 origin/main 的祖先** → 历史 blob 已公开；本次分支 HEAD 又重新引入（`git grep HEAD` 命中）。
- **处置**：去 NCBI 吊销重发；新 key 只走环境变量（`E1_extract_metadata.py` 已支持 `NCBI_API_KEY` env，可作统一范式）；清历史。
- 附带合规问题：`U1:69`、`9.metabuli/metabuli_api.py:1408` 用假邮箱 `plantvirusdb@example.com` 作 Entrez 联系人，违反 NCBI 政策；`9.metabuli/metabuli_api.py:386-413` 提交 BLAST 不带 `tool/email` 参数。

### S3. 知识库 RAG / 文献站：DeepSeek 密钥明文散落 + 公网无鉴权 LLM 端点（已实测被盗刷通道畅通）
- 密钥落盘：`7.literature_tracker/update_cron.sh:5`、`run_summarize_batches.py:9`（并以 `--api-key` 传入子进程命令行，`ps` 可见）、`build_rag.py:11`（另一把嵌入 key）、`6.knowledge_rag/pv_rag/scripts/_diag.py:5`（未跟踪但随工作副本扩散）。均未进 git 历史，但处于活跃使用状态。
- **开放 LLM 代理（已线上实测）**：向 `http://39.106.101.94/literature/api/summarize/paper` 匿名 POST → 返回 HTTP 200 与完整 13 字段 LLM 抽取结果——服务器在用自己的 key 为匿名请求付费。`api_server.py:192-242` 无鉴权/无限流/不限输入长度。
- **SSRF（本地 test_client 实测）**：请求体可控制 `base_url`/`api_url`（`7.literature_tracker/api_server.py:202`、`4.virus_primer/step5_web_server.py:2227`、`step5_web_server_PROD.py:2439-2446`、`6.knowledge_rag/api_server.py:150-163`），服务端真实代访任意 URL 并回显错误详情；step5 在空 key 时还会把服务器 key 作为 Bearer 发往攻击者指定 URL（凭据外泄）。
- `6.knowledge_rag/api_server.py`（公网 `/knowledge/` → :5002）同样无鉴权，匿名可循环调用（单次最长 150s / max_tokens 2500）。
- **处置**：全部端点加鉴权/限流，客户端可控 URL 改为服务端固定白名单，服务端 key 只走服务账户，轮换全部 LLM key。

### S4. Explorer 路径穿越：`/virus/files/<path>` 可读任意文件（已本机复现）
- 生产版本 `analysis/explorer_edit_20260930/app.py:576-582`：`os.path.join(_GENOME_DIR, filepath)` 无消毒，Werkzeug `<path:>` 不拦 `..`——实测 `/virus/files/../secret/flag.txt` 返回 200 与文件内容。服务以 **root** 运行（`virus-explorer.service`），可读 `/etc/shadow`、`.env`（AI key 所在）。nginx 是否规范化 `../` 未经线上验证，但一行修复（`realpath` 前缀校验或 `send_from_directory`）远低于风险。同款写法在 `archive/_archived_13.virus_profile/app.py:70-75` 等 3 处复制粘贴。

### S5. 其余 Web 暴露面
- `9.metabuli/metabuli_api.py`：classify/blastn/blastx/cdd/primer_design 全部 POST 无鉴权（:1465 绑 0.0.0.0 公网可达），算力白嫖 + 以服务器名义向 NCBI 提交任务；超时任务不回收（:773-779、:710-716 不清理不弹出）→ 磁盘/内存无界增长可被利用。
- `7.literature_tracker` 前端：`web/index.html:483/666-668/727-729/868-870` 把 Crossref/OpenAlex 返回的 `doi/pmid/source` 未转义拼进 href/onclick（DOM XSS 触发面）；CDN 脚本无 SRI。
- `6.knowledge_rag/api_server.py:344`：LLM 回答经不做转义的 `mdLite()` 直接 innerHTML（存储型 XSS 面）；`web/app.js` 为死代码但仍在部署且有同类问题。
- `plant-virus.conf`：全站 HTTP 明文（AI key 透传交互过明文网），无任何安全头/HSTS；`location /photos/ { alias docs/ }` 把整个 docs 根（含 60+ 个 `.bak/.orig` 备份文件）暴露公网。
- `rdp_analysis/rdp_app.py:41`：Flask secret_key 默认值公开可猜；`dsRNAmax/webapp/app.py:264-268,525,540`：`ssh_host/remote_dir` 未校验直接拼进远端 shell（暴露即 RCE，当前仅绑 127.0.0.1）。
- Explorer「变异面板」无鉴权 CPU 耗尽 DoS：100 条 ×19 kb 全局两两比对实测单核 5.3 s/条（`app.py:1525-1555`），gunicorn 单 worker，2 个并发请求即 504 队列。

---

## 二、🔴 P0 — 数据正确性（对外发布的数字/库直接失真）

### D1. 引物库（4.virus_primer step3→step4）：验证装配链 4 处独立断裂 —— 线上"验证/评分/推荐"大面积空壳或错位
- **复跑整体错位（已实测复现）**：`step3_validate_primers.py:1009→1248-1295` 在"续跑"时以过滤子集的下标给全表套结果 → 张冠李戴且写回 TSV 进入线上库。
- **Phase1 结果全丢弃（已实测复现）**：`:1162-1164` `val_df` 构造后无任何引用 → TSV 无一个二聚体/探针/验证字段；step4 读这些列全部落空 → DB 二聚体/探针列恒 0、警告恒空。
- **二聚体惩罚永不生效**：`:1252-1255` 键名不匹配 → `dimer` 恒 `{}`，-30 分支（`:636-643`）不执行；NOT_RECOMMENDED 的强二聚体可翻成 RECOMMENDED。
- **类型错配**：`:232` 存的是 primer3 对象 repr 字符串，`step4:317-319` 强转 int → 恒 0。
- 连带：`/api/chat` SSRF+key 回退（见 S3）、`run_all_steps.sh:32-35` 传不存在的 `--fasta` 参数一键流程必崩（`set -e` 直接终止）、42% 引物无 Tm/GC（varVAMP/Olivar 路径不产出）、简并引物 Tm 上下限互换（`step2:705-706` 已实测倒挂）、README 宣称的"行数"实为字节数、覆盖度/交叉反应验证在官方主流程中根本不执行。
- **影响**：`docs/data/primers/*.tsv`（103,642 行）与线上引物站的 Validation_Score / Recommendation / 二聚体警告字段不可信，需重跑修复后的 step3/step4。

### D2. 增量更新引擎（1.Prepare U1）：静默丢数据 + 状态机污染
- 批次失败静默跳过 + 同步日期**无条件前移**（`U1:852-864, 1214-1227, 1568-1574`）→ 一次网络抖动丢一批（≤500 条）且窗口永不重扫；历史佐证：`incremental_status.json` 记录曾混入 884 动物病毒/110,416 流感/1,747 噬菌体靠事后清理。
- `--dry-run` 有真实副作用（`:1526-1541` 空结果路径会推进同步日期）→ 预览后正式跑漏数据。
- L3 植物病毒 TaxID 表 27 个值大面积错误（`:84-117`，经 NCBI Taxonomy 实测：39733 注 Reoviridae 实为 Astroviridae（动物病毒）、39502-39506 注五大家科实为植物属种、1922214 注 Amalgaviridae 实为灭绝哺乳动物）→ 动物/昆虫病毒可拿"植物通行证"入库，五大家科兜底实际失效。
- merged/deleted taxid 处理为假功能（`:1391-1402` 拿 accession 集合与 taxid 比较，恒不命中且不更新）。
- 生产版本文件已实锤受害：`docs/data/DATA_VERSION` 当前 `RECORDS_TOTAL=-1`，站点版本徽标会显示"-1 records"（`config.py:79` 直拼）。

### D3. 关键数字五批互斥（论文级硬伤）
| 指标 | 各处声称 | 实测产物 |
|---|---|---|
| 参考基因组数 | 8,465（根 README）/ 8,484（模块 §4.5）/ 11,956（模块 §4.4、§4.8）/ 12,159（site_stats.json）| **9,022**（`grep -c "^>" Plant_Virus_Ref.fasta`，与 DATA_VERSION 一致）|
| 全量序列 | ~199K / 377MB | **211,132 条 / 410 MiB** |
| 病毒物种数 | 6,182 / 6,180 / 5,173 / 4,840 | 未定 |
- 同一份模块 README 内 §4.5=8,484 与 §4.8=11,956 打架；作者自己在 `1.Prepare/README.md:217` 标注"定稿前需统一"至今未闭环。`lib/render_numbers.py` 数字单一来源机制已建好但**从未接入 README/站点**且事实表已过期。

### D4. 其余模块的数据级 P0（均经复算/实测）
- **8.plant-insect**：README"1,806 个有媒介-宿主关系的病毒"，复算 75%（1,356/1,803）是零关系、零 TaxID 的 WUR-only 条目混入同一口径；WUR 爬虫无去重（源文件 21 个重名自相矛盾）、无重试、截断不告警。
- **5.host_classify**：图题声称"已排除 HVT 家族/Species"，代码 `EXCLUDE_FAMS = set()` 一个都没排除（`2_plot_overlap.py:29,93`）；跨界统计把 Unknown/Environmental/Algae 当"其他宿主界"系统性虚高；"属级独占率"四个口径 72%/78%/90%/95% 互斥；全流程零 held-out 验证。
- **12.pamirdb**：线上 `POST /api/predict` 100% 报错（已对线上实测：`run_consensus_prediction() got an unexpected keyword argument 'algorithms'`，`backend/server.py:822-824` vs `scripts/consensus.py:160`）；"miRanda+psRNATarget+RNAhybrid 共识"实为单一自研引擎重打分（`consensus.py:172-196` 从不调用外部工具）；预测集混入 1,788 条 >100nt 的 miRNA 前体、线上排序第一的"最强互作"是 30 个 gap 的垃圾命中；wobble 字段因比对串只输出 `|/.` 两种符号而结构性恒 0（"100% 完美种子"是 bug 产物）；11/6,942 病毒序列被 15,000nt 静默截断；2,442/2,442 预测的病毒 ID 与服务端病毒表主键断链。
- **11.antiviral_genes**：`miRNA_final_stats.json`"837 物种"不可复现（复算 799，且 sources 分项和 80,832≠83,166，`count_mirna.py:189` 拿物种数冒充序列数）；对外下载的 vsiRNA TSV 含 7,553 行精确重复 + 77 行爬虫垃圾行（"No matching records found"），README/网页/文件三个数字互斥；"Validated 14,935"实际是 NCBI 收录标记 V 的语义挪用。
- **2.Build_plant_virus_db**：CAT 建库路径的 sed 命令含被转义吃掉的控制字符（`build_virus_db.py:605`，`\a`→BEL 且吃掉 'a'，表头损坏，`--databases all` 会静默包含）；蛋白 ID 格式判定过松（`YP_009508235.1` 被误判为基因预测格式→改用核酸表查蛋白 ID→空映射无告警）；kaiju TaxID 注入对带描述 header 静默失效（`:542` 已实测）；id→TaxID 映射零覆盖率校验；3 个外部辅助脚本（SearchAccessionIdToTaxId.py 等）仓库中不存在；README 结果表（2026-05-12 批次）早于脚本最后修改（07-07），不可复现。
- **7.literature_tracker**：`pipeline.py auto` 的 pending 选取逻辑错（`:225-234` 算完 pending 后仍按年份最新截断）→ 每周 cron 实际汇总 **0 篇**（实测 0/455）→ 新论文无 AI 字段 → 被 `--ai-verified` 过滤 → 站点可浏览数据近乎冻结（线上 2026-09 仅 2 篇入库 vs digest 声称 70 篇）；`digest.py:85-142` 下次 cron 会把 143 条周报索引截断为 ≤8 条；摘要失败被写成全"未提及"+`ai_done=True`（实测 8 篇永久损坏且不可自愈）；PubMed 抓取每查询上限 200 无分页（历史日志实锤累计漏 104 篇）。
- **语法错误 2 处（脚本不可运行）**：`13.onekp_virus/analyze_novel.py:211`（f-string 表达式内 `\"` 转义，Python<3.12 SyntaxError）、`oneoff_scripts/_bench_b1_20260919/stub_taxonkit.py:27`（字符串内嵌真实换行符）。另有 2 处 SyntaxWarning（`11.antiviral_genes/build_gene_browser.py:612`、`scrape_pvsirnadb.py:37`）。
- **10.virus_photos**：EPPO 爬虫导航失败被裸 except 吞掉后仍采集当前页面 DOM → 照片静默错配到别的病毒（`scrape_eppo_photos.py:52-59`）；三源提取双重 append 致产物 35% 重复（实测 1,107/3,174）；`filter_structured.py` 全文无 import（从未跑通）；README"925 张"与实际 2,975 条（6 个来源）全线过时。

---

## 三、🟠 P0 — 版权与合规（公开再分发风险）

- **在版权专著整本入库**：`10.virus_photos/15587070.pdf`（95.2 MB）+ `15587070.docx`（42.9 MB，实测为《100种常见植物病毒病害彩色图鉴》杨彩霞编著，中国农业出版社 2024 年 12 月第 1 版，ISBN 978-7-109-32854-9）**均在公开仓库 HEAD 与完整历史中**；`.gitignore:52-53` 写了排除但对已跟踪文件无效。
- **无授权图片批量再分发**：`docs/data/book_images/` 1,113 张 + `10.virus_photos/extracted/images/` 486 张 + `docs/data/dpv_images/` 1,279 张（DPV 版权属 BSA）已入库公开；`unified_gallery.json` **2,975/2,975 条无任何 license/rights 字段**，DPV 的 photographer 恒为占位串"DPV Database"。
- **许可状态自相矛盾**：LICENSE（MIT）未被 git 跟踪（公开仓库实际无授权文件）；SOUL.md"禁止未授权商用"与 MIT 允许商用直接矛盾；NCBI/ICTV/KEGG/WUR/EPPO 各数据源再分发条款全文未提。
- **处置**：立即从线上撤下书目与图片 → git 历史清理（与大文件治理同一次 filter-repo 完成）→ 逐源补 permission 或改纯外链 → 图库补 license/attribution 字段。14/15 模块（结构库）的许可台账（RVPSD CC-BY、zenodo 编号、doi 齐全）是现成的整改模板。

---

## 四、🟡 P1 — 可复现性与仓库卫生（审稿人必查项）

**构建入口与依赖**
- 根 `run_all.sh` 是 2026-07-07 过期副本（与模块版 diff 1,336 行，无规范层/体检/R1/U1），而根 README:36 与 TECHNICAL_REPORT §3.4 指向的正是它 → 按 README 复现得到旧口径数据库。
- 依赖三套互不覆盖：requirements.txt（5 行，仅 Explorer）不含管线依赖（polars/biopython/ete3/tqdm 全缺）；pixi.toml 只覆盖引物模块且 **pixi.toml/pixi.lock 均未被 git 跟踪**；taxonkit/mmseqs/vclust/seqkit/pyrodigal-rv 等外部二进制无版本记录、无声明。
- CI 必然红灯：唯一 workflow 引用不存在的 `environment.yml`；模块内已有测试（F2 护栏黄金快照、pv_rag 164 个单测）无 CI 入口。

**Git 仓库状态**
- 9,321 条脏记录：8,088 个已跟踪文件在工作树缺失（docs/primers/species 7,194 个等）；14 个提交未推送（origin/main 停在 07-27）；CHANGELOG 工作树 2,240 行 vs HEAD 100 行。
- >5MB 已跟踪文件 6 个共 273 MB；`.git` 415 MB；20+ 个未跟踪且未忽略的大目录（paper_dl 11G、.tools 1.9G、.mimosa 119M 含密钥副本）——一次 `git add -A` 即灾难。
- 5 个 gitlink 无 `.gitmodules`（clone 即空目录）；`14.rvpsd_structures`/`15.uniprot_plant_virus_structures` 两个"已交付"模块 **0 文件入库**（README 自称"脚本入库"不实）；TECHNICAL_REPORT.md、LICENSE、TE 模块（已宣布下线）状态混乱。
- Explorer 三份 app.py 互不相同（仓库版 1987 行 vs 线上生产版 2345 行，md5 互异）→ 按仓库重部署会回归已修复 bug（节段标签匹配 `app.py:636`）并丢失 `/virus/*` 路由。

**代码卫生共性**
- "行数"实为字节数：5.host_classify README 表格 9/9 吻合字节数、TECHNICAL_REPORT"build_virus_db.py 40,464 行"（实 739 行）、4.virus_primer README 同病 → 代码规模虚报 20-40 倍，审稿人抽一处即崩。
- 硬编码绝对路径遍布（`D:\桌面\...`、`/home/zhangwenda`、`/opt/plant_virus_db`、仓库外的 `D:/桌面/NEBLab/...`）；个人 QQ 邮箱、个人 Gmail 入码。
- 12.pamirdb `pv_rag` 整目录未入库 + "被测代码（NEBLab editable 安装）≠ 被审代码 ≠ 生产代码"三份漂移。
- `6.knowledge_rag` 检索文档级截断丢 83% ICTV 正文（`retriever.py:153` text[:12000]）；README"RAG 0.82 vs 0.47"准确率无任何评估工件支撑（题集实为 18/18/5 题，metrics.py 自认无 ground truth）；`bm25s` 未声明依赖（按文档搭建必崩）；`--commit-every` 在 PV 索引器是空操作（崩溃致 DB↔Qdrant 分叉）。
- 爬虫共性三缺：无 robots 检查（自建 robots.txt 双重标准）、无重试、无断点（跑完才落盘）；失败静默 `except: return []` 至少 15+ 处。
- 缓存永不失效（1.Prepare 五个脚本的 parquet/idx"存在即用"）；U1 增量产物与主链路两棵目录树同名不同 schema（21 列 vs 17 列、`Taxid` 大小写敏感）→ 下游 metabuli 静默拿空 map。

---

## 五、审稿人意见（按投稿审查顺序）

1. **数据可用性声明与实物对不上**：声称"全套脚本+依赖+中间产物公开可得"，实际 14/15 模块未入库、pixi.lock 不在、TECHNICAL_REPORT 不在、LICENSE 不在；同时公开仓库里挂着 root 口令与版权书目——编辑部/伦理审查会直接要求说明处置。
2. **数字必须单一来源**：建立"产物路径+时间+校验和"的事实表并重跑 `render_numbers --check` 进 CI（机制已有，未接线且过期）。当前 8,465/8,484/11,956/12,159/9,022 五值并存是desk reject 级硬伤。
3. **方法学阈值全部需要出处或敏感性分析**：宿主分类的 HVT 家族清单、碰撞属清单、`src_cnt≤2且cat_cnt>10`、双因子置信度 `1−e^(−n/5)`；引物的 -12/-6/-2/-30 权重与 BLAST 参数（blastn-short/evalue 100/alen≥12 无 identity 阈值，特异性公式对单侧脱靶不可见）；pamirdb 的全部自造系数。每条给文献引用或 ±50% 扫描表。
4. **验证缺口是最大方法学短板**：宿主分类零 held-out（建议以 VMR `Host source` 为金标准报混淆矩阵/Macro-F1）；引物零湿实验验证（建议 schema 加 `validation_source` 字段并在 UI 明示 in silico；抽 10-20 对做 PCR/qPCR 标准曲线）；pamirdb 零阳性/阴性对照（建议 AntiVIRmiR 正对照 + 种子打乱估 FDR + 与真实 miRanda/RNAhybrid 对照跑）；RAG 零 ground truth（先删掉不可核验的 0.82/0.47，再扩题集+换异源 judge+补 recall@k）。
5. **数据溯源要闭环**：330GB 原始输入只查存在性（`lib/pvcore.write_manifest` 已有但主链路未调用）；VMR 版本固定是好的但无列/行数校验；外部工具版本全链路无记录；`docs/data/DATA_VERSION` 修掉 `RECORDS_TOTAL=-1` 后是很好的溯源骨架。
6. **对外 API 与页面要版本可引用**：Explorer 无数据快照端点、无数据字典（21 列无文档）、CSV 导出静默截断 5000 行；metabuli README 宣称"Virus-restricted nt 库"与代码 `BLAST_ENTREZ=""`（无限制）直接矛盾；文献站 digest 统计口径（全量 33K）与浏览口径（ai-verified 6.5K）差 5 倍且同站展示。

---

## 六、亮点（值得保留并在论文中强调）

- **护栏账本体系**（1.Prepare `lib/pvcore.py` Ledger/quarantine/guards + F2 黄金快照测试）：可关、可测、可复核，同类科研管线中少见。
- **事故留痕文化**：CHANGELOG 2,240 行踩坑记录、U1 注释里的 208 次重复追加与 1,747 噬菌体事故、step3 注释里两个历史 bug 的修法、`REPORT_20260930.md` 的 md5 上链与双方法互证——修 bug 的自省是真功夫，问题只在"修完没有闭环到文档与数据"。
- **15.uniprot 模块是全项目数据纪律标杆**：README 每个计数与落盘逐项吻合、口径变更有留档（绿藻病毒 1,993 条剔除）、下载脚本带重试/校验/manifest/断点——可直接作为其他模块整改模板。
- **metabuli 库重建脚本**专业（预开 swap、死 taxid 重映射、原子换库+`.prev` 回滚）；**谱系自证**不迷信工具输出。
- **pv_rag 检索工程**（RRF 融合、per-doc cap、层次检索、temperature=0 复现注释）、**NCBI 合规细节**（OA-only 下载带 mailto、3 req/s 自限）、**中文术语映射+缩写索引**。
- **8.plant-insect 合并策略的克制**（模糊匹配只出 review 不自动并）与 **2.Build 的工程骨架**（断点续传、污染隔离、动静日志分离）。
- 前端 XSS 防护在 Explorer 主路径（textContent/组件转义）与文献站标题/摘要（esc()）是到位的，问题集中在遗漏点。

---

## 七、修复优先级路线图

| 序 | 动作 | 为什么先做 |
|---|---|---|
| 1 | **改服务器 root 密码 + 换 SSH key + 排查登录日志**（S1）| 已发生的泄露，每天暴露 |
| 2 | **轮换全部密钥**：NCBI key、DeepSeek×2、SiliconFlow（S2/S3）| 同上 |
| 3 | **线上撤下版权书目与书图/DPV 图**（三）| 法律风险随公开时长增长 |
| 4 | **git filter-repo 清历史**（口令/key/书目一次清）+ 强推 + 加 pre-commit secret 扫描 + 提交工作区（含 14 个未推送提交先审查再推）| 防止 9,321 条脏状态与未跟踪密钥副本误入库 |
| 5 | **Web 加固**：`/virus/files` realpath 校验、三个 LLM 端点加鉴权+限流+URL 白名单、nginx 安全头 + 全站 HTTPS | S3-S5 |
| 6 | **修复引物 step3→step4 装配链并重跑全库**（D1 四断点一起修）| 线上引物数据当前不可信 |
| 7 | **修复 U1 状态机**（失败不前移日期、dry-run 零副作用、修 TaxID 表）并统一 `RECORDS_TOTAL` | 防增量继续丢数据 |
| 8 | **修复 literature pipeline pending 逻辑 + digest 索引覆盖**，恢复站点更新 | 站点已实质冻结 |
| 9 | **数字统一**：重跑 render_numbers、接入 README/站点、修 DATA_VERSION | 投稿前置 |
| 10 | PAmiRDB 线上接口修复 + "共识"改名 + 前体过滤；host_classify 图题与实现对齐；antiviral 837→799 重生成 | 对外口径诚实性 |
| 11 | 依赖/CI/子模块治理：pixi.lock 入库、environment.yml 或删 workflow、.gitmodules、14/15 模块入库、两个 run_all.sh 二选一 | 可复现性 |
| 12 | 补验证：held-out 评估、阳性/阴性对照、工具版本记录、阈值出处 | 审稿人意见闭环 |

---

*本报告由 9 路并行深度审计 + 全局机械化检查生成；所有 P0 均给出 file:line 证据，关键项经独立复核或最小实验复现（引物错位、路径穿越、SSRF、开放代理线上实测、pamirdb 线上接口实测、U1 TaxID 表 NCBI 实查、CAT sed 求值、kaiju awk 最小样例等）。标"待确认"的仅为需线上/外部工具环境的项目。*
