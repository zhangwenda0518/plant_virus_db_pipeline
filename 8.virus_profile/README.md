# 8. Virus Profile — 单病毒详情页

> 本地基因组注释图谱/下载/蛋白/文献,已融入 Explorer「病毒档案」tab

**Live**: http://39.106.101.94/virus/ (独立页) + http://39.106.101.94/explorer/「病毒档案」tab(探索器集成版)

## 文件

```
8.virus_profile/
└── api_server.py              # Flask Web 服务(:5006, /virus/, /virus/<name>, /virus/files/)
```

## 功能

| 端点 | 说明 |
|---|---|
| `/virus/` | 病毒物种搜索页(支持 NCBI/ICTV 名搜索) |
| `/virus/<name>` | 单病毒详情:基因组图谱/注释下载/蛋白表/相关文献/引物 |
| `/virus/files/<path>` | 本地 genome_annotations 文件下载(genome/cds/protein/gff3/gb) |

## 数据源

| 数据 | 路径(相对 pipeline 根) |
|---|---|
| 参考物种 | `docs/data/Plant_Virus_Ref.Info.tsv` |
| 全量物种(NCBI→ICTV 映射) | `docs/data/Plant_Virus_Full.Info.tsv` |
| 基因组注释 | `genome_annotations/` (4726 物种,含 GB/GFF/FASTA) |
| 文献 | `7.literature_tracker/papers.json` |
| 引物 | `docs/data/primers/primer_reference.tsv` |
| 名称映射 | `docs/data/name_mapping.tsv` |

## 与 Explorer 档案 tab 的关系

- 独立 `/virus/` 服务(:5006)提供文件下载 + 搜索页
- Explorer「病毒档案」tab 已集成详情展示(基因组图谱随左侧筛选联动)
- `/virus/files/` 由 nginx 代理到 :5006,两者共用

## 部署

- systemd: `virus-profile.service`
- nginx: `/virus/` → :5006
- 依赖 `genome_annotations/` 目录存在
