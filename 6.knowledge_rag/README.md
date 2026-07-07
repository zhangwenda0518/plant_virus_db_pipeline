# 6.knowledge_rag

植物病毒知识库 + RAG 智能问答模块。

## 数据源

| 数据 | 路径 | 内容 |
|------|------|------|
| ICTV Reports | `databases/ictv_md/` | 192 个病毒科/属分类学报告 (Markdown) |
| DPV Database | `databases/dpv_md/` | 363 种植物病毒详细描述 (Markdown) |
| ViroidDB | `databases/viroiddb.json` | 55MB 类病毒综合数据 |
| Plant Virus Info | `databases/Plant_Virus_Info.tsv` | 全量植物病毒元数据 |

## 使用方法

### 1. 同步知识库数据

```bash
# 从 NEBLab 项目复制知识库
cp -r ../../NEBLab/rag-db/ICTV_RAG_Database/docs/ databases/ictv_md/
cp -r ../../NEBLab/rag-db/dpv_database/md/         databases/dpv_md/
cp ../../NEBLab/rag-db/viroiddb.json               databases/
cp ../../NEBLab/rag-db/Plant_Virus_Info.tsv         databases/
```

### 2. 启动知识库 API

```bash
python api_server.py --port 5002
```

### 3. 问答

```bash
curl -X POST http://localhost:5002/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"TMV的传播方式是什么？"}'
```
