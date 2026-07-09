# docs — 静态网站 + 数据文件

> Nginx 直接服务的静态内容:门户首页、参考数据库、TE 数据库、数据下载

**路由**:
- `/` → `portal.html`(统一门户)
- `/reference/` → 参考数据库首页(index.html + segmented/nonsegmented/submit/download/photos.html)
- `/te/` → TE & EVE 转座子数据库(index.html + data/)

## 文件结构

```
docs/
├── portal.html                # 统一门户首页(/)
├── index.html                 # 参考数据库首页(/reference/)
├── segmented.html             # 分段病毒浏览
├── nonsegmented.html          # 非分段病毒浏览
├── submit.html                # 数据提交页
├── photos.html                # 病毒照片图鉴
├── download.html              # 数据下载页
├── table.js                   # 交互表格 JS
├── DATA_VERSION               # 当前数据版本号
├── README.md                  # 本文档
├── explorer.html              # (legacy) 旧版 Explorer 入口
├── te/                        # TE & EVE 数据库
│   ├── index.html             # Chart.js 可视化页面
│   └── data/                  # 参考序列 FASTA(9 文件, ~49MB)
├── data/                      # 参考序列+元数据
│   ├── Plant_Virus_Full.fasta # 全量序列(377 MB)
│   ├── Plant_Virus_Full.Info.tsv # 全量元数据
│   ├── Plant_Virus_Ref.fasta  # 非冗余参考序列(31 MB)
│   ├── Plant_Virus_Ref.Info.tsv # 参考元数据
│   ├── Plant_Virus.complete_ref.fasta # 完整参考序列
│   ├── Plant_Virus.complete_ref_info.tsv
│   ├── virus_genes_cov.tsv    # 基因覆盖度表
│   ├── complete_acc.txt       # 完整序列 accession 列表
│   ├── name_mapping.tsv       # ICTV/NCBI 名称映射(45176 条)
│   └── primers/               # 引物 JSON 数据(7193 物种)
│       ├── index.json
│       ├── stats.json
│       └── *.json
└── explorer_data.pkl           # Explorer 缓存(405 MB, gitignore)
```

## 数据文件(统一命名)

所有数据文件以 `Plant_Virus_` 为前缀,与 `config.py` 的 `PIPELINE_OUTPUTS` 一致:

| config.py 键 | 文件 |
|---|---|
| `full_fasta` | `Plant_Virus_Full.fasta` |
| `full_tsv` | `Plant_Virus_Full.Info.tsv` |
| `cluster_fasta` | `Plant_Virus_Ref.fasta` |
| `cluster_info` | `Plant_Virus_Ref.Info.tsv` |

## 部署

- Nginx: `location /reference/` → `alias docs/`; `location /te/` → `alias docs/te/`
- `location = /` → `try_files /portal.html`
- 数据文件 path 由 `config.py` 统一管理
