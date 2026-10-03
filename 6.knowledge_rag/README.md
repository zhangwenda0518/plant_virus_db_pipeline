# 6. knowledge_rag — 植物病毒知识检索与 RAG 问答

> 两套独立检索系统: 轻量关键词引擎 (retriever.py) + 全栈 RAG 管线 (pv_rag/)。

**Live**: http://39.106.101.94/knowledge/

---

## 架构

### 系统一: 轻量关键词检索引擎

`retriever.py` + `api_server.py` (端口 5002)。纯内存操作, 无外部依赖。

- **数据源**: ICTV (192 个病毒科报告 MD) + DPV (363 个病毒描述 MD) + ViroidDB (57 MB JSON)
- **索引**: v5 BM25 段落级索引 — 文档按空行切分为约 1100 字符的段落, 对全篇正文 (不再只取前 3000 字符) 建立 IDF 加权的 BM25 统计
- **检索**: `search()` — BM25 段落级检索 (长度归一化), 精确物种名命中 +25 / 缩写展开命中 +10; DPV `Acronym:` 行建立缩写→物种索引, 查询里的中文术语经内置 zh→en 映射表展开后再检索; `search_full_text()` — 纯字符串 grep 全文搜索兜底
- **截断限制**: 单文档正文入库上限由环境变量 `KB_DOC_MAX_CHARS` 控制 (默认 60000 字符); 调小会系统性丢失 ICTV/DPV 长文后半部分 (症状/传播/检测段落), 旧版硬编码 12000 时实测 ICTV 正文丢失约 83%
- **结构化提取**: `_clean_text()` 正则提取 Family/Genus/Species/Acronym 字段

### 系统二: 全栈 RAG 管线

`pv_rag/` 子项目 (独立 Uvicorn 部署)。基于 NEBLab RAG 框架。

- **数据库**: PostgreSQL (Alembic 管理 schema: documents/abstracts/chunks 表)
- **向量库**: Qdrant (qdrant-client 操作, 支持本地文件/云集群双模式)
- **检索**: HybridRetriever (embedding 语义搜索 + BM25 + reranker 重排序)
- **索引管线**: `_index_abstracts.py` — 摘要分块→逐批 embedding→upsert 到 Qdrant (≤200点/批)
- **评估**: 50 题基准 + 诊断脚本 (evals/)

### 继承关系

```
pv_rag/src/
├── neblab_rag/          # 通用 RAG 基础框架 (可复用库)
└── plant_virus_rag/     # 植物病毒专用层 (import neblab_rag)
```

## 数据源

| 数据 | 内容 | 条目数 |
|------|------|--------|
| ICTV 分类报告 | 病毒科/属官方分类学描述 | 192 (实测) |
| DPV 数据库 | 植物病毒详细百科条目 | 363 (实测) |
| ViroidDB | 类病毒综合信息 | 57 MB JSON |

## API 端点 (系统一, :5002)

| 端点 | 方法 | 功能 |
|:-----|:----:|:-----|
| `/query` | POST | 关键词检索 + LLM 生成回答 |
| `/search` | GET | 纯关键词检索 (无 LLM) |
| `/stats` | GET | 文档统计 |
| `/` | GET | Web UI 页面 |

## 使用

```bash
# 系统一 (轻量)
python api_server.py        # :5002

# 系统二 (全栈, 需先构建索引)
cd pv_rag/
python scripts/_index_abstracts.py
uvicorn plant_virus_rag.api.main:create_pv_app --factory
```

## 结果

- 系统一: 纯内存倒排索引, 零外部依赖, 启动即用
- 系统二: PostgreSQL+Qdrant, HybridRetriever, 索引约 19.3 万 chunks（约 3.3 万论文）
- 评估题集与方法见 evals/（当前无 ground-truth correctness 指标）

## 部署

- **systemd**: `knowledge-rag.service` (:5002)
- **Nginx**: `/knowledge/` → proxy_pass :5002
- **向量库**: Qdrant (系统二独立部署)
