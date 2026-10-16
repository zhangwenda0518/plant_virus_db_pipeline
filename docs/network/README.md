# 互作网络图谱 (`/network/`)

所有植物病毒与宿主的**力导向网络图**，以及**宿主–媒介–病毒**三元组网络。两个标签页共用一套交互：
阶元阶梯（目→科→属→种）+ Top-N 合并看宏观结构，**双击任意节点下钻到它的自我网络**（ego network），
再点击邻居沿网络一步步走，顶部路径条随时回退；别名搜索直达、阶元/权重/媒介传毒方式筛选、
PNG/CSV 导出、中英双语。

- 纯静态实现（ECharts 本地化于 `echarts.min.js`，无 CDN 依赖），nginx 直接托管。
- 数据：`network.json`（~0.64 MB）+ 复用 `/association/associations.json`（~1.3 MB）。

## 两个标签页

| 标签 | 内容 | 数据源 | 计数口径 |
|:---|:---|:---|:---|
| 病毒–宿主 | 全部植物病毒 ↔ 植物宿主，按两侧阶元聚合 | `../association/associations.json` | 211,132 条 GenBank 序列（208,477 条可映射）聚合到 15,197 个「病毒种 × 宿主叶」关联对 |
| 媒介–病毒–宿主 | 文献验证的「病毒 × 媒介 × 宿主」三元组，边可展开为媒介节点 | `network.json` | 1,375 条 VIP-DB 实验验证三元组，含媒介目/科/属、传毒方式、DOI |

两个口径都**不是宿主范围的权威判定**：前者是 GenBank 上登录的宿主注释（一条序列算一次），
后者是文献里做过的传播实验（1,375 条只是极小样本）。100 个媒介、447 个病毒、380 个宿主
意味着任意两两组合远未覆盖，图上「没有连线」只代表文献没报道过。

## 数据口径

| 项 | 值 |
|:---|:---|
| 三元组 | 1,375（其中 120 条宿主未能解析到分类谱系，界记为 Unknown，随「仅植物宿主」默认隐藏） |
| 病毒 | 447 种 → 31 科 / 64 属 / 447 种（病毒侧阶元取 NCBI/ICTV 谱系） |
| 媒介 | 100 种 → 73 属（昆虫为主，另有螨、线虫、真菌） |
| 宿主 | 380 个（含界 1,375 条中可解析的全部谱系） |
| 传毒方式 | 6 类（持久循环型 / 持久循回增殖型 / 非持久型 / 半持久型 / 持久循环型 / NA） |
| 文献 | 281 个 DOI |
| 病毒–宿主侧 | 211,132 条序列 / 15,197 关联对 / 5,134 病毒种 / 3,702 宿主叶 |

默认仅显示**植物宿主**（Viridiplantae + 藻类）；界（Kingdom）作为筛选器而不是网络层级，
两侧列均从「目」开始聚合。`(no order)` / `(no family)` / `(no genus)` 是 NCBI 谱系里该位置
确实没有分类单元的 taxa，照实显示，不并入「其他」。

## 交互设计

- **宏观**：阶元阶梯（病毒/宿主/媒介各自 目→科→属→种）+ Top-N 合并。「其他（合并）」节点把
  长尾 taxon 合成一个灰节点，避免物种级上千个节点把图挤成一团。
- **微观**：双击节点 → 只保留它和直接邻居的 ego network，节点大小改为「占本品类的比例」；
  点邻居再走一步，`focus` 深度记录在顶部路径条（`🦠 virusA → 🌿 hostB → …`），点任意一级回退。
- **权重筛选**：最小连线数滑块，低于阈值的边整条隐藏（物种级尤其有用）。
- **搜索**：当前标签页内任意阶元的 taxon，支持同名缩写（TSWV、CMV…）和 ICTV 学名，
  命中后直接跳到该节点所在视图并高亮。
- **导出**：PNG（2.5× 像素比，白底）与当前视图的 TSV/CSV（含聚焦态）。
- **画布**：滚轮缩放、拖拽平移、节点可拖动；斥力/连线长度两个滑块可实时调，
  fit 会按当前节点包围盒反算缩放并自动收尾。

## 重建数据

```bash
cd docs/network
python build_network.py     # 依赖 data/external/taxdump 与 ../association/associations.json
```

## 部署

```bash
scp index.html network.json echarts.min.js \
    root@39.106.101.94:/opt/plant_virus_db/plant_virus_db_pipeline/docs/network/
```

nginx（`plant-virus.conf`）：

```nginx
location /network/ {
    alias /opt/plant_virus_db/plant_virus_db_pipeline/docs/network/;
    index index.html;
    try_files $uri $uri/ /network/index.html;
    expires 10m;
}
```

页面同时从 `/association/associations.json` 读取病毒–宿主数据，因此 `/association/` 路由必须可访问。
