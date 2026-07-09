# 9. Metabuli — 植物病毒宏基因组分类器

> 上传 contig 比对植物病毒参考库,NCB→ICTV 8 级分类,序列下载

**Live**: http://39.106.101.94/metabuli/

## 文件

```
9.metabuli/
├── metabuli_api.py            # Flask Web 服务(:5004, /metabuli/)
├── metabuli_page.html         # 前端(Plotly Sankey/Krona iframe)
├── fetch_examples.py          # 从 NCBI efetch 生成演示示例 JSON
├── metabuli_examples.json     # TMV/PVY/CMV/PSTVd 全长基因组示例
├── build_taxid_lineage.py     # nodes.dmp/names.dmp → taxid_lineage.tsv(NCBI→ICTV 权威谱系)
└── taxid_lineage.tsv          # 预生成 taxid 映射表(gitignore,由 build_taxid_lineage.py 生成)
```

## 功能

| 功能 | 说明 |
|---|---|
| **分类** | Metabuli classify(seq-mode 3) ← 910MB plant virus DB(`ref.virus.build.metabuli_db`) |
| **分类表** | 域界门纲目科属种 8 级(权威 NCBI→ICTV 谱系,基于 nodes.dmp/names.dmp) |
| **Taxonomy Sankey** | 每属仅前 5 种开关(默认开,防拥堵) |
| **Krona 图** | 默认隐藏 unclassified(扣正父节点),可勾选还原 |
| **病毒序列分类** | 逐 contig 分类表 TSV + 病毒序列 FASTA(带 taxid/taxon/rank 表头) + 下载 |
| **示例** | TMV/PVY/CMV/PSTVd 全长基因组(RefSeq,CP→全长切换) |
| **自动清理** | Job 结果 2 小时后自动删除 |

## 使用

```bash
# 生成 taxid→ICTV 8 级谱系表(一次性)
python build_taxid_lineage.py

# 生成演示示例
python fetch_examples.py

# 启动 Web 服务
python metabuli_api.py         # :5004
```

## 数据库引用

- Metabuli DB: `/opt/plant_virus_db/ref.virus.build.metabuli_db`(由 `2.Build_plant_virus_db/build_virus_db.py` 构建)
- Taxonomy: `/opt/plant_virus_db/taxonomy/nodes.dmp` + `names.dmp`(NCBI,含 ICTV 双名法名)
- Metabuli binary: `/usr/local/bin/metabuli`

## 架构说明

`metabuli_api.py` 启动时加载 `taxid_lineage.tsv`(22,190 taxid,缓存于内存),
分类完成后通过 `_extract_virus()` 按 taxid 查询谱系,生成逐 contig 等级数据。

## 部署

- systemd: `metabuli-api.service`
- nginx: `/metabuli/` → :5004,`client_max_body_size 110m`
- taxid_lineage.tsv 由 build_taxid_lineage.py 在服务器上生成
