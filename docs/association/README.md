# Host–Virus Association Explorer (`/association/`)

病毒分类阶元（目→科→属→种）× 宿主分类阶元（目→科→属→种）的关联分析交互页。
双层桑基图支持**点击任意节点向下一层钻取**（层层递进），面包屑回退，双向视角（病毒→宿主 / 宿主→病毒），别名搜索直达，详情面板、PNG/CSV 导出，中英双语。

- 纯静态实现（ECharts 本地化于 `echarts.min.js`，无 CDN 依赖），nginx 直接托管。
- 数据：`associations.json`（~1.3 MB），由 `build_associations.py` 生成。

## 数据口径

| 项 | 值 |
|:---|:---|
| 序列 | 211,132 条 GenBank accession（Plant_Virus_Full.Info.tsv；2,655 行无合法 Taxid 不计入关联） |
| 关联对 | 15,197 个（病毒种 × 宿主叶） |
| 病毒种 | 5,134（Taxid → NCBI Taxonomy 谱系，与 ICTV MSL 同步的拉丁双名） |
| 宿主叶 | 3,702（Host 文本 → names.dmp → Taxid → 谱系；1,059 行未带宿主文本不计入） |
| 计数 | accession（序列）条数，非文献证实的宿主范围 |

默认仅显示植物宿主（Viridiplantae + 藻类）；34,285 条未标注宿主的记录默认隐藏，可用开关显示。
界（Kingdom）作为筛选器而非桑基层级，两侧列均从「目」开始下钻。

## 重建数据

```bash
cd docs/association
python build_associations.py          # 依赖 data/external/taxdump（nodes.dmp + names.dmp）
```

## 部署

```bash
scp index.html associations.json echarts.min.js \
    root@39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/docs/association/
```

nginx（`plant-virus.conf`）：

```nginx
location /association/ {
    alias /opt/plant_virus_db/plant_virus_db_pipeline/docs/association/;
    index index.html;
    try_files $uri $uri/ /association/index.html;
    expires 10m;
}
```

别名搜索运行时拉取 `/reference/data/name_mapping.tsv`（常用名/缩写 → ICTV 名），
仅在首次聚焦搜索框时加载一次。
