# TE & EVE Database — 植物转座子与内源性病毒元件

> 基于 U-RVDB v32 PLN 分类 + NCBI 精选,Viridiplantae 限定

**Live**: http://39.106.101.94/te/

## 数据

- 10,537 LTR Retrotransposons (copia/gypsy/LINE)
- 217 Endogenous Viruses (ENRV)
- 200 Exogenous Viruses (EX)
- 20 MB 参考序列,1025 植物物种

## 页面

- Chart.js 可视化:各类别分布式条形图 + 物种分布 + 数据源饼图
- 下载:9 个 FASTA 参考序列(`data/`)

## 部署

- Nginx: `location /te/` → `alias docs/te/`
