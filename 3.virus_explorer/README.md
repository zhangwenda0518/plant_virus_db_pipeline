# 3. Virus Explorer — 植物病毒数据交互式浏览器

> Dash 应用,交互式时空演变/基因组变异/媒介传播/病毒档案

**Live**: http://39.106.101.94/explorer/

## 标签页

| 标签 | 功能 |
|---|---|
| **时空演变趋势图** | 年份折线 + 国家条形 + 地理地图(病毒随时间/地域扩散) |
| **全基因组变异分析** | 多序列比对热图(全长展示,Plotly 缩放) + 变异率曲线 + Top 10 热点 |
| **高稳健序列数据库** | SeqIO 数据表(CSV 导出) |
| **引物数据库** | 引物设计结果(同步 primer_reference.tsv) |
| **宿主范围** | 病毒宿主属/种分布(条形图 + 表) |
| **媒介传播** | 病毒→媒介物种生态网络 Sankey(焦点高亮) + 关系明细表,跟随左侧筛选 |
| **病毒档案** | 基因组图谱(CDS 箭头/环状)+ 注释下载(gb/cds/protein/gff3/genome) + 蛋白表 + 文献,跟随左侧筛选实时联动 |

## 左侧筛选面板

- 宿主种类(MultiSelect,全部显示 + 计数)
- 目标国家/地区(Dynamic,MultiSelect)
- 基因组结构(分段/非分段 + 计数)
- 病毒科(Family MultiSelect + 计数)
- 序列完整性(Complete/Partial + 计数)
- 目标病毒物种(MultiSelect,跟随 Family/Category 联动 + 计数)
- 年份滑块(RangeSlider) + 数据源选择(采集/提交年)

## 数据加载

- 数据源:`Full.Info.tsv` + `Full.fasta`(config.py → PIPELINE_OUTPUTS)
- 缓加速:启动时预计算 `explorer_data.pkl` 缓存(406 MB,pickle)
- 媒介数据:`../8.plant-insect/virus_vector_merged.json`
- 病毒档案:`genome_annotations/` + `Ref.Info.tsv` + `papers.json`
- 名称映射:`docs/data/name_mapping.tsv` + NCBI→ICTV 转译(6182 条)

## 技术栈

- Dash + Mantine Components + Plotly
- Bio.Align.PairwiseAligner(全局双序列比对)
- Gunicorn --preload 1 worker + 2 threads(生产)
- 媒介 Sankey:Plotly Sankey trace(8 层),介质生态网络扩展

## 部署

- systemd: `virus-explorer.service`(Gunicorn :8050, preload)
- nginx: `/explorer/` → :8050 + `/_dash-*/`
- Python 3.6 兼容
