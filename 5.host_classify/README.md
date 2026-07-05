# Host Classify — 病毒宿主分类与跨界分析工具集

## 目的

对 C4 清洗后的 `classified_clean/` 数据进行下游分析：

1. **量化跨界污染程度** — 植物病毒在真菌/昆虫/动物等非植物宿主中的分布
2. **构建宿主概率查找表** — 属/科/种级 `P(host | taxon)`，含双因子置信度评估
3. **Contig 级宿主分类** — 基于病毒注释结果的级联宿主预测

## 前置依赖

```
classified_clean/          # C4 输出 (14 个 .tsv 文件)
cross_analysis/            # C7 概率表输出目录
```

## 流程

```bash
# === 1. 跨界重叠分析 ===
python 1_cross_kingdom_overlap.py \
    -i classified_clean/ -o cross_analysis/ -s Plant

# 输出:
#   cross_analysis/multi_level_overlap.tsv      # 8 级分类重叠表
#   cross_analysis/cross_kingdom_all_details.tsv # 种级详细分类
#   cross_analysis/cross_details/*.tsv           # 每类详情

# === 2. 可视化 ===
python 2_plot_overlap.py -i classified_clean/ -o cross_analysis/

# 输出:
#   cross_analysis/Plant_evolutionary_bar.pdf    # 分组柱状图
#   cross_analysis/Plant_exclusive_vs_shared.pdf # 独占/共享比
#   cross_analysis/all_categories_exclusive.pdf  # 各类别独占率
#   cross_analysis/Plant_upset_matrix_*.csv      # UpSet 矩阵 (R 可用)

# === 3. 宿主概率表 (含置信度) ===
python 3_host_probability.py -i classified_clean/ -o cross_analysis/

# 输出:
#   cross_analysis/species_host_probability.tsv  # 种级 P(host|species) + 置信度
#   cross_analysis/genus_host_probability.tsv    # 属级 P(host|genus) + 置信度
#   cross_analysis/family_host_probability.tsv   # 科级 P(host|family) + 置信度
#   cross_analysis/order_host_probability.tsv    # 目级 P(host|order) + 置信度

# === 4. 跨物种分析 ===
python 4_cross_species.py -i classified_clean/cross_species/ -o cross_analysis/

# === 5. Contig 宿主分类 ===
python 5_classify_contigs.py \
    -i final_integrated_classification.tsv \
    -f contigs.fasta \
    --prob_dir cross_analysis/ \
    -o classified/ \
    --mode medium

# 输出:
#   classified/{Category}.classified.tsv         # 每类完整表格
#   classified/{Category}.classified.fasta       # 每类序列 (High+Medium)
#   classified/classification_result.tsv         # 全量分类结果
#   classified/classification_summary.tsv        # 统计汇总
#   classified/confidence_report.tsv             # 置信度分布

# === 6. 属级审计 (按需) ===
python 6_inspect_genus.py Plant Fungi Alphapartitivirus

# === 7. 共享属查询 (按需) ===
python 7_query_shared_genera.py Plant Fungi
```

## 置信度模型

概率表 (`3_host_probability.py`) 使用双因子置信度：

| 因子 | 公式 | 含义 |
|------|------|------|
| 专一性 C_ent | 1 − H/ log(N) | 香农熵归一化，独占属=1.0，均匀分布=0.0 |
| 支持度 C_sup | 1 − e^(−records/5) | 记录数≥15 时接近 1.0，singleton≈0.18 |
| 综合得分 | C_ent × C_sup | 0.0~1.0，≥0.8=High，≥0.4=Medium |

## 分类级联

`5_classify_contigs.py` 使用 Species → Genus → Family → Order 四级级联，含列偏移容错（处理上游合并引入的 Subphylum/Suborder 等额外列）。

## 预期结果

| 指标 | 期望值 | 说明 |
|------|--------|------|
| 种级跨界 | >0 (≤100) | ICTV 确认的增殖型双宿主 (TSWV 等) |
| 属级独占率 | ~90% | 植物病毒属绝大多数为单一宿主 |
| 分类率 | >98% | Contig 宿主分类成功率 |
| Unknown | <2% | 无可匹配分类单元的 contig |
