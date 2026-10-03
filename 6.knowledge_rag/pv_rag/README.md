# Plant Virus RAG — 植物病毒检索增强生成系统

> 完整独立可运行的植物病毒知识库 RAG 系统  
> 基于 NEBLab 框架的 Sprint-5 任务路由架构  
> 构建日期: 2026-07-08 ~ 2026-07-09  

---

## 目录

1. [一键搭建](#一键搭建)
2. [系统概述](#系统概述)
3. [环境依赖](#环境依赖)
4. [数据流程](#数据流程)
5. [完整构建过程](#完整构建过程)
6. [各阶段注意事项与耗时](#各阶段注意事项与耗时)
7. [评估结果](#评估结果)
8. [API 使用](#api-使用)
9. [文件清单](#文件清单)
10. [优化记录](#优化记录)

---

## 一键搭建

### 前置条件

| 软件 | 版本 | 下载 |
|------|------|------|
| Python | 3.10+ | https://python.org |
| PostgreSQL | 16 | https://postgresql.org/download/ |
| Qdrant | 1.18+ | https://github.com/qdrant/qdrant/releases |

### 一键执行

```bash
cd 6.knowledge_rag/pv_rag
bash setup.sh
```

脚本会自动完成 8 步:
1. 检查 Python/Postgres 依赖
2. 创建 `.env.local` (首次会暂停,提示填 API key)
3. 安装 Python 依赖 (`pip install -e ".[dev]"`)
4. 启动 Qdrant server (localhost:6333)
5. 创建 Postgres `neblab` 数据库
6. 运行数据库迁移建表
7. 摄入结构化数据 (ICTV/ViralZone/NCBI/plant_insect)
8. 索引 chunks + 重建 BM25S

**首次运行**: 脚本会在 Step 2 暂停,让你编辑 `.env.local` 填入 API key。填完再跑一次。

### 手动搭建(如脚本失败)

#### Step 1: 安装依赖

```bash
cd pv_rag
pip install -e ".[dev]"
```

#### Step 2: 配置环境变量

```bash
cp config/.env.example .env.local
# 编辑 .env.local 填入:
#   LLM_API_KEY          = sk-your-deepseek-key
#   LLM_DEFAULT_MODEL    = deepseek-v4-pro
#   EMBEDDING_API_KEY    = sk-your-siliconflow-key
#   RERANKER_API_KEY     = sk-your-siliconflow-key
#   OPENALEX_EMAIL       = your-email@university.edu
#   POSTGRES_DSN         = postgresql+psycopg2://neblab:neblab@localhost:5432/neblab
#   QDRANT_URL           = http://localhost:6333
```

#### Step 3: 启动 Postgres + Qdrant

```bash
# Postgres (作为系统服务运行)
# 创建数据库:
createdb -U neblab neblab

# Qdrant (本地二进制)
E:/BandZip解压/qdrant-x86_64-pc-windows-msvc/qdrant.exe --disable-telemetry &

# 验证
curl http://localhost:6333/healthz
# 输出: healthz check passed
```

#### Step 4: 建表 + 摄取 + 索引

```bash
# 建表
alembic -c alembic_pv/alembic.ini upgrade head

# 摄入结构化数据
pv-ingest structured --source ictv --dir rag-db/ICTV_RAG_Database/docs
pv-ingest structured --source viralzone --dir rag-db/viralzone_rag_db/md
pv-ingest structured --source ncbi --file rag-db/final.cluster.ref_info.tsv
python scripts/_ingest_plant_insect.py

# 摄入论文 (OpenAlex 已预加载,如需补充 PubMed)
pv-ingest pubmed --max 500 --year-from 2024

# 索引
pv-ingest index --commit-every 200          # 全量(records + documents)
pv-ingest bm25-rebuild                      # 重建 BM25S 索引(持久化到磁盘)
```

#### Step 5: 验证

```bash
pv-ingest stats                              # 数据库统计
curl http://localhost:6333/collections       # Qdrant 状态
python scripts/demo_queries.py               # 路由演示
python -m plant_virus_rag.eval --questions evals/questions.json --label test --judge --no-rewriter
```

---

## 系统概述

### 架构

```
用户问题
    ↓
PvRouter (task_classifier)
    ├── META      → 模板化回答 (0 LLM, 0 检索)
    ├── QA        → HybridRetriever (dense + BM25S) → PvAnswerGenerator (严格引用)
    └── PLANNING  → HybridRetriever → PvAnswerGenerator (标注推理)
```

### 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| LLM | DeepSeek V4 Pro | 答案生成 + Judge |
| Embedding | Qwen3-Embedding-8B (SiliconFlow) | 4096-d 向量 |
| Reranker | Qwen3-Reranker-8B (SiliconFlow) | 检索重排序 |
| 向量库 | Qdrant 1.18.2 (本地) | localhost:6333 |
| BM25 | bm25s (scipy-based) | 稀疏检索,支持磁盘持久化 |
| 数据库 | PostgreSQL 16 | 论文元数据 + chunks |
| 框架 | FastAPI + Click CLI | API + 命令行 |

---

## 环境依赖

### Python 包

```bash
# 核心
fastapi uvicorn pydantic pydantic-settings
sqlalchemy alembic asyncpg psycopg2-binary
qdrant-client pyalex httpx
structlog python-dotenv sse-starlette tenacity
click rank-bm25 pymupdf biopython bm25s

# 开发
pytest pytest-asyncio pytest-cov pytest-mock pyright ruff
```

`pyproject.toml` 已声明,`pip install -e ".[dev]"` 一键安装。

### .env.local 配置模板

见 `config/.env.example`,关键字段:

```ini
# LLM
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-your-key
LLM_DEFAULT_MODEL=deepseek-v4-pro
LLM_LIGHT_MODEL=deepseek-v4-flash

# Embedding
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=sk-your-key
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
EMBEDDING_DIM=4096

# Reranker
RERANKER_BASE_URL=https://api.siliconflow.cn/v1
RERANKER_API_KEY=sk-your-key
RERANKER_MODEL=Qwen/Qwen3-Reranker-8B

# Postgres
POSTGRES_DSN=postgresql+psycopg2://neblab:neblab@localhost:5432/neblab

# Qdrant (本地 server)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=neblab_abstracts
PV_QDRANT_COLLECTION=pv_chunks

# OpenAlex
OPENALEX_EMAIL=your-email@university.edu
OPENALEX_API_KEY=your-key

LOG_LEVEL=INFO
```

---

## 数据流程

### 完整 pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    1. 数据摄入                                │
├─────────────────────────────────────────────────────────────┤
│  ICTV/ViralZone/NCBI/DPV  ──→  pv_records (1,071)           │
│  OpenAlex API              ──→  pv_documents (91,643)        │
│  PubMed Entrez             ──→  pv_documents (+202 new)      │
│  plant-insect TSV          ──→  pv_records (+1,821)          │
├─────────────────────────────────────────────────────────────┤
│                    2. 文本分块                                │
├─────────────────────────────────────────────────────────────┤
│  chunk_text(1000,200) → 193,277 chunks                       │
├─────────────────────────────────────────────────────────────┤
│                    3. 向量嵌入                                │
├─────────────────────────────────────────────────────────────┤
│  Qwen3-Embedding-8B → 193,277 × 4096-d vectors               │
│  (SiliconFlow API, batch_size=32, SQLite 缓存)                │
├─────────────────────────────────────────────────────────────┤
│                    4. 索引存储                                │
├─────────────────────────────────────────────────────────────┤
│  chunks    ──→  PostgreSQL pv_chunks                         │
│  vectors   ──→  Qdrant pv_chunks collection                  │
│  BM25S     ──→  内存索引 + 磁盘持久化 (bm25s_cache/)          │
├─────────────────────────────────────────────────────────────┤
│                    5. 检索 + 生成                             │
├─────────────────────────────────────────────────────────────┤
│  用户问题 → task_classifier → HybridRetriever                 │
│          → PvAnswerGenerator → 答案 + 引用                    │
└─────────────────────────────────────────────────────────────┘
```

### 数据规模

| 层级 | 来源 | 数量 | chunks |
|------|------|------|--------|
| 结构化记录 | ICTV | 539 | 2,226 |
| | NCBI Host | 462 | 462 |
| | ViralZone | 70 | 74 |
| | plant_insect | 1,821 | 1,821 |
| 学术论文 | OpenAlex | 91,643 | 188,267 |
| | PubMed | 202 | 427 |
| **合计** | | **94,737** | **193,277** |

---

## 完整构建过程

### Step 1: 数据库准备

```bash
createdb -U neblab neblab
alembic -c alembic_pv/alembic.ini upgrade head
```

**结果**: pv_records, pv_documents, pv_abstracts, pv_chunks 等表创建

### Step 2: 摄入结构化数据

```bash
pv-ingest structured --source ictv --dir rag-db/ICTV_RAG_Database/docs      # 539 records
pv-ingest structured --source viralzone --dir rag-db/viralzone_rag_db/md    # 70 records
pv-ingest structured --source ncbi --file rag-db/final.cluster.ref_info.tsv # 462 records
python scripts/_ingest_plant_insect.py                                      # 1,821 records
```

### Step 3: 摄入论文元数据

```bash
# OpenAlex (预加载 91,643 篇)
pv-ingest openalex --topic plant_virus --language en --resume

# PubMed 补充 (TSV 220 检索词驱动)
pv-ingest pubmed --max 500 --year-from 2024 --year-to 2024
pv-ingest pubmed --max 500 --year-from 2025 --year-to 2025
# 结果: +196 新论文 (auto DOI 去重)
```

### Step 4: 论文摘要索引

```bash
pv-ingest index --no-records --documents --commit-every 200  # ~2.5h, 188K chunks
pv-ingest index --no-documents --commit-every 100            # records, ~5min
pv-ingest bm25-rebuild                                        # BM25S 重建+持久化
```

### Step 5: 验证

```bash
pv-ingest stats
pv-ingest bm25-rebuild
curl http://localhost:6333/collections/pv_chunks | grep points_count
python -m plant_virus_rag.eval --questions evals/questions.json --label baseline --judge --no-rewriter
```

**最终状态:**
```
Total papers:         91,845
Structured records:   2,892
Total chunks:         193,277
Qdrant vectors:       193,277
BM25S index:          193,277 documents (持久化到 bm25s_cache/)
```

---

## 各阶段注意事项与耗时

### 总览

| 阶段 | 耗时 | 费用 | 可中断恢复 |
|------|------|------|-----------|
| 1. 环境准备 | 10-30 min | 0 | ✅ |
| 2. 数据库迁移 | <1 min | 0 | ✅ |
| 3. 结构化数据摄入 | ~5 min | 0 | ✅ |
| 4. OpenAlex 论文摄入 | 已预加载 / ~10h (全量) | 0 | ✅ |
| 5. PubMed 补充 | ~10 min/500 篇 | 0 | ✅ |
| 6. 摘要索引 | ~2.5 h (91K 篇) | ~¥20-40 | ✅ |
| 7. records 索引 | ~5 min | ~¥1 | ✅ |
| 8. BM25S 重建 | ~6 s | 0 | ✅(持久化) |
| 9. QA eval | ~8 min (20 题) | ~¥2 | — |
| 10. PLANNING eval | ~3 min (5 题) | ~¥1 | — |
| **总计** | **~3.5 h** | **~¥25-45** | |

---

### 阶段 1: 环境准备 (10-30 min)

#### 注意事项
- **Python 版本**: 必须 3.10+,推荐 3.12(`StrEnum` 需要 3.11+,3.10 用 `str` 子类)
- **Postgres**: 必须 16,不是 15 或 17(迁移脚本针对 16 测试)
- **Qdrant**: 二进制版即可,不需要 Docker
- **磁盘空间**: 至少 5 GB(代码 + rag-db + Qdrant 数据 + 缓存)
- **网络**: 需访问 `api.deepseek.com` + `api.siliconflow.cn` + `export.arxiv.org`(可选)

#### 常见问题
| 问题 | 解决 |
|------|------|
| `pip install` 失败 | 用国内镜像:`pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| Postgres 连接拒绝 | 检查服务是否启动,`pg_isready -h localhost` |
| Qdrant 端口占用 | `netstat -ano \| findstr 6333`,杀掉占用进程 |

---

### 阶段 2: 数据库迁移 (<1 min)

#### 注意事项
- 迁移前确保 `neblab` 数据库已创建
- `alembic_pv/` 是 pv 专属迁移,和主 `alembic/` 独立
- 迁移幂等,重复运行不会报错

#### 验证
```bash
psql -U neblab -d neblab -c "\dt pv_*"
# 应看到: pv_records, pv_documents, pv_abstracts, pv_chunks, pv_fulltexts, pv_alembic_version
```

---

### 阶段 3: 结构化数据摄入 (~5 min)

#### 注意事项
- **ICTV**: 192 个 md 文件,解析为 539 records
- **ViralZone**: 131 个 genus md,解析为 70 records(非全部植物病毒)
- **NCBI**: `final.cluster.ref_info.tsv` 11,936 行,只取有 `VMR_Species` 的 462 条
- **DPV**: 363 个 md,复用 ICTV source_type
- **plant_insect**: 1,376 行病毒-媒介-宿主关系,去重后 1,821 records

#### 常见问题
| 问题 | 解决 |
|------|------|
| `FileNotFoundError: rag-db/...` | 确认在 pv_rag 目录下运行,rag-db/ 是相对路径 |
| ICTV 解析警告 | 部分老格式 md 会跳过,不影响主体 |
| plant_insect 重复 | 脚本自动按 (virus_name, vector) 去重 |

#### 验证
```bash
pv-ingest stats
# Structured Records (pv_records) 应显示:
#   ictv: 539  ncbi_host: 462  viralzone: 70  plant_insect: 1821
```

---

### 阶段 4: OpenAlex 论文摄入

#### 注意事项
- **已预加载**: 91,643 篇已在数据库中(从 NEBLab 迁移)
- **全量重建**: `pv-ingest openalex --resume` 约 10 小时(2012-2026 逐年拉取)
- **断点续传**: 进度保存在 `pv_openalex_progress.json`,中断后重跑自动跳过已完成年份
- **API key**: `OPENALEX_EMAIL` 必填(OpenAlex 政策),`OPENALEX_API_KEY` 可选(提高限额)

#### 常见问题
| 问题 | 解决 |
|------|------|
| 429 Too Many Requests | 加 `OPENALEX_API_KEY`,或降低 `--max` |
| 中文论文质量差 | OpenAlex 中文覆盖弱,改用 PubMed 补充 |

---

### 阶段 5: PubMed 补充 (~10 min/500 篇)

#### 注意事项
- **检索词**: TSV 驱动 220 个植物病毒属/科(高+中置信度)
- **去重**: DOI 匹配优先,已有 OpenAlex 论文自动跳过
- **限速**: NCBI 要求 ≤3 请求/秒,脚本已内置
- **断点续传**: 无,但重复运行安全(去重逻辑保证)

#### 验证
```bash
pv-ingest pubmed --max 10 --year-from 2025
# 输出: "fetched 10 PMIDs, new X, skipped Y duplicates"
```

---

### 阶段 6: 摘要索引 (~2.5 h, 91K 篇)

#### ⚠️ 最耗时阶段

#### 注意事项
- **API 费用**: ~¥20-40(SiliconFlow Qwen3-Embedding-8B,~41M tokens)
- **batch_size**: 32 chunk/批,每批 ~1-2s
- **commit_every**: 200 篇/次 DB 提交,避免长事务死锁
- **embedding 缓存**: 已加 SQLite 缓存(`embedding_cache.sqlite`),重复运行只 embed 新文本
- **断点恢复**: 已索引的论文状态为 `fulltext_indexed`,重跑自动跳过

#### 监控进度
```bash
# 另开终端,实时查看 Qdrant 向量增长
watch -n 30 'curl -s http://localhost:6333/collections/pv_chunks | grep points_count'
```

#### 常见问题
| 问题 | 解决 |
|------|------|
| `HTTP 429` 限速 | 降低 batch_size 或加请求间隔 |
| Qdrant WAL 锁错误 | 重启 Qdrant,删 `storage/collections/pv_chunks/0/wal/` |
| Postgres 死锁 | 单进程运行,不要并发 `pv-ingest index` |
| 中途中断 | 直接重跑,已索引的会跳过 |

#### 预期产出
```
Total chunks: 193,277 (188K openalex + 427 pubmed + 2,762 records + 1,821 plant_insect)
Qdrant vectors: 193,277
```

---

### 阶段 7: records 索引 (~5 min)

#### 注意事项
- 先重置 records 状态:`UPDATE pv_records SET status='metadata_only'`
- 1,071 records → ~2,762 chunks(每条 1-3 chunk)
- 费用: ~¥1

#### 验证
```bash
pv-ingest stats
# pv_records: fulltext_indexed = 1071
```

---

### 阶段 8: BM25S 重建 (~6 s)

#### 注意事项
- **首次**: ~6s(tokenize 193K + index + save 到磁盘)
- **后续**: ~1.8s(从 `bm25s_cache/` 加载)
- **持久化**: `bm25-rebuild` CLI 自动保存
- **缓存位置**: `<pv_rag>/bm25s_cache`(基于模块定位的绝对路径,与启动时 cwd 无关;
  可用环境变量 `PV_BM25S_CACHE_DIR` 覆盖)
- **失效条件**: pv_chunks 表数据变化时需重建 —— 加载时会把缓存元数据里的
  chunk 数与 pv_chunks 当前行数比对,不一致自动判为过期并重建(无需手工删缓存)

#### 常见问题
| 问题 | 解决 |
|------|------|
| `'BM25' object has no attribute 'scores'` | 加载路径 bug(已修:用 `bm25s.BM25.load()` 类方法);若再遇到,确认 `pip install -U bm25s` 且代码未回退 |
| 加载缓存报错/疑似过期 | 删 `bm25s_cache/` 重建(正常情况会自动对账重建) |

---

### 阶段 9: QA eval (~8 min, 20 题)

#### 注意事项
- **DeepSeek V4 Pro 是推理模型**: 延迟 20-60s/题(含 reasoning_content)
- **judge 也调 LLM**: 每题额外 5-15s 判断引用有效性
- **费用**: ~¥2(20 题 × ~3K tokens)
- **--no-rewriter**: 推荐用此参数(rewriter 反而降低质量)
- **BM25S 首次查询慢**: 第一题会触发索引构建(~6s),后续正常

#### 常见问题
| 问题 | 解决 |
|------|------|
| `HTTP 401` | 检查 `.env.local` 的 `LLM_API_KEY` |
| `WinError 10061` | 网络问题,重跑(已索引的会跳过) |
| 超时 | 加 `--no-judge` 跳过 judge,或减少题目 |

---

### 阶段 10: PLANNING eval (~3 min, 5 题)

#### 注意事项
- PLANNING 答案更长(结构化输出),延迟略高于 QA
- 5 题全部应分类为 PLANNING(用 `scripts/pv_planning_questions.json` 验证)
- judge 标准不同(允许标注推理),supported 率天然偏高

---

## 评估结果

### QA 评估 (20 题, pv_v1 标准集)

| 指标 | May 基线 | 最终版 (BM25S) |
|------|---------|----------------|
| Errors | 4/20 | **0/20** |
| Citation validity | 100% | **100%** |
| Answered rate | 100% | **100%** |
| Judge supported | 75.8% | **92.3%** |
| Judge partial | 14.4% | **7.7%** |
| Judge not_supported | 9.8% | **0.0%** |
| Latency p50 | 12.9s | 37.1s |

### PLANNING 评估 (5 题)

| 指标 | 值 |
|------|-----|
| Errors | **0/5** |
| Citation validity | 100% |
| Judge supported | **100%** |
| Latency p50 | 32.9s |

### META 路由

| 查询 | 延迟 | LLM 调用 | 结果 |
|------|------|---------|------|
| "数据库有多少病毒" | 0.2s | 0 | 实时 PG 统计 |
| "你是谁" | 0.0s | 0 | 身份模板 |

### 拒答机制 (V2 18 题,优化后)

| 指标 | 修复前 | **修复后** |
|------|--------|-----------|
| Answered rate | 100% | 77.8% (正确拒答 4 题) |
| Expected-Yes Answered | 100% | 92.3% |
| **Expected-No Refused** | **0%** | **100%** |

---

## API 使用

### 启动 API

```bash
uvicorn plant_virus_rag.api.main:create_pv_app --factory --port 8001
```

### 单轮查询

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is tomato yellow leaf curl virus?", "top_k": 7}'
```

### 多轮对话

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"messages": [
    {"role": "user", "content": "What is TYLCV?"},
    {"role": "assistant", "content": "TYLCV is a begomovirus..."},
    {"role": "user", "content": "How is it transmitted?"}
  ], "top_k": 7}'
```

### 流式 SSE

```bash
curl -N "http://localhost:8001/query/stream?query=tomato+yellow+leaf+curl+virus&top_k=7"
```

### CLI 命令速查

```bash
pv-ingest stats                          # 数据库统计
pv-ingest bm25-rebuild                   # 重建 BM25S 索引
pv-ingest index --no-documents           # 索引 records
pv-ingest index --no-records --documents # 索引 documents
pv-ingest pubmed --max 500 --year-from 2024
pv-ingest multisearch --query "TYLCV" --max 20
pv-ingest multisearch --query "TMV" --max 50 --ingest

# Eval
python -m plant_virus_rag.eval --questions evals/questions.json --label test --judge --no-rewriter
```

---

## 文件清单

```
pv_rag/
├── setup.sh                     # 一键搭建脚本
├── README.md                    # 本文档
├── pyproject.toml               # 包定义
├── alembic.ini                  # DB 迁移配置
├── Makefile                     # 常用命令
├── src/
│   ├── neblab_rag/              # 基础框架(BM25S/Citation/Qdrant local)
│   └── plant_virus_rag/         # 植物病毒 RAG
│       ├── rag/                 # task_classifier/router/system_info/generator/conversation
│       ├── corpus/              # pubmed/search_provider/fulltext_batch
│       ├── api/                 # FastAPI routes
│       ├── db/                  # models/repositories
│       └── eval/                # eval harness
├── tests/                       # 28 个单元测试
├── alembic/ + alembic_pv/       # 数据库迁移
├── rag-db/                      # 原始数据(ICTV/ViralZone/NCBI/DPV)
├── config/
│   └── .env.example             # 配置模板
├── evals/                       # 11 个评估报告 + 问题集
└── scripts/                     # 23 个脚本
    ├── standalone_download.py   # 独立 PDF 下载器
    ├── distributed_download.py  # 分布式下载+merge
    ├── demo_queries.py          # 路由演示
    ├── _ingest_plant_insect.py  # plant_insect 摄入
    ├── _index_abstracts.py      # 摘要索引
    ├── shard_0~3_docs.json      # 4 分片文档列表
    └── ...
```

---

## 优化记录 (2026-07-09)

### 1. 拒答机制修复

**问题**: QA prompt 措辞过弱,deepseek-v4-pro 仍强行回答本应拒答的问题。eval `expected_no_refused: 0%`。

**修复**:
- 强化 prompt: 加 "MANDATORY REFUSAL" 强制拒答条款
- 加 few-shot 拒答示例(英文+中文各 2 例)
- 加明确拒答模板
- 修 `eval/metrics.py` 的 `is_fallback_answer()`: 加英文拒答模式识别

**结果**: `expected_no_refused` 0% → **100%**

### 2. Embedding 缓存 (SQLite)

**修复**: 在 `Qwen3EmbeddingProvider` 加 SQLite 缓存层
- key = SHA256(text + model),value = JSON 向量
- 缓存文件: `./embedding_cache.sqlite`

**结果**: 重复 embedding 快 **125x** (1.25s → 0.01s)

### 3. BM25S 索引持久化

**修复**: `BM25Index` 加 `save()/load()`
- `bm25-rebuild` 自动保存到 `./bm25s_cache/`
- `build_pv_bm25_index()` 优先从磁盘加载

**结果**: 启动加载快 **3x** (6s → 1.83s)

---

## 构建总结

| 阶段 | 耗时 | 依赖 |
|------|------|------|
| 数据库迁移 | <1min | PostgreSQL 16 |
| 结构化数据摄入 | ~5min | rag-db/ 数据 |
| 论文元数据摄入 | 已完成 (91K) | OpenAlex API |
| PubMed 补充 | ~10min/500篇 | NCBI Entrez |
| 摘要索引 | ~2.5h (91K 篇) | SiliconFlow API |
| records 索引 | ~5min | SiliconFlow API |
| BM25S 重建 | ~6s (含持久化) | 本地 CPU |
| QA eval 20题 | ~8min | DeepSeek API |
| PLANNING eval 5题 | ~3min | DeepSeek API |
| **总计** | **~3.5h** | |
