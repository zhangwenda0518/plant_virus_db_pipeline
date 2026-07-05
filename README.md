# Plant Virus Reference Database

> 植物病毒参考数据库、引物设计工具与交互式时空探索系统

**Live**: http://39.106.101.94/

## 目录结构

```
plant_virus_db_pipeline/
├── 1.Prepare_plant_virus_pipeline/   # A-G 七阶段数据流水线
├── 2.Build_plant_virus_db/           # 参考数据库构建
├── 3.virus_explorer/                 # Dash 交互式可视化
├── 4.virus_primer/                   # 引物设计 + Web 服务
├── 5.host_classify/                  # 病毒宿主分类分析
├── docs/                             # Reference DB 静态网站
├── config.py                         # 统一项目配置
└── run_all.sh                        # 流水线一键运行入口 (已移至 pipeline/)
```

## 三个在线数据库

| 数据库 | 地址 | 技术栈 |
|--------|------|--------|
| **Reference DB** | http://39.106.101.94/reference/ | HTML/CSS/JS 静态仪表板 |
| **Primer DB** | http://39.106.101.94/primers/ | Flask + SQLite |
| **Virus Explorer** | http://39.106.101.94/explorer/ | Dash + Plotly |

## 数据来源

- NCBI GenBank 全量植物病毒序列
- ICTV VMR MSL41 病毒分类学
- KEGG 功能注释

## 数据量

- 198,885 条病毒序列记录
- 6,176 个病毒物种
- 103,642 对引物
- 4,729 个物种有宿主数据
