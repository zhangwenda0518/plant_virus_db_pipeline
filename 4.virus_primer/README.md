# 4.virus_primer

植物病毒引物设计与 Web 服务。

## 功能

- 全自动引物设计流水线 (PCR/qPCR/Degenerate/Tiled)
- Flask Web 服务器 (搜索/浏览/下载/API)
- AI 问答助手
- 多工具集成: Primer3 + AutoPVPrimer + varVAMP + Olivar

## 流水线

```bash
bash run_all_steps.sh    # 一键运行所有步骤
# 或分步运行:
python step1_parse_db.py          # 解析参考数据库
python step2_design_primers.py    # 批量引物设计
python step3_validate_primers.py  # 引物验证
python step4_build_database.py    # 构建引物数据库
python step5_web_server.py        # 启动 Web 服务
```

## Web 部署

```bash
gunicorn -w 2 -b 127.0.0.1:5000 wsgi:app
```

## 访问

http://39.106.101.94/primers/

## 目录

| 目录 | 用途 |
|------|------|
| `tools/` | 辅助工具 (导出/补丁/BLAST 测试) |
| `archive/` | 旧版引物设计脚本归档 |
| `PrimerForgeX/` | AI 引物优化引擎 (独立模块) |
| `Olivar/` | 平铺扩增引物设计工具 |
| `varVAMP/` | 简并引物设计工具 |

## 数据量

- 103,642 对引物
- 覆盖 4,789 个病毒物种
- PCR: 18,101 | qPCR: 14,006 | Tiled: 68,920 | Degenerate: 2,615
