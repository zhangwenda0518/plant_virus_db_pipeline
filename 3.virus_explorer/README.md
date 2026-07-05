# 3.virus_explorer

植物病毒时空交互式探索器 (Dash 应用)。

## 功能

- 全球采集地分布地图
- 时间序列分析
- CP 基因变异分析
- 引物数据预览
- 病毒宿主范围分析
- AI 问答助手

## 技术栈

- Dash 4.x + Mantine Components
- Plotly 交互式图表
- Gunicorn 生产部署

## 部署

服务通过 Nginx 反向代理到 `/explorer/` 路径，Gunicorn 1 worker + 2 threads 运行。

## 访问

http://39.106.101.94/explorer/
