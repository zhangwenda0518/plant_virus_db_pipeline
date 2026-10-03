# -*- coding: utf-8 -*-
"""
10. 属级宿主分析图（本地 VMR 数据版）

基于 docs/data/VMR_MSL41.txt (ICTV MSL41, 2024) 的 Host source 字段，
复现 2_plot_overlap.py 中属级宿主独占分析（服务器 cross_analysis 版的本地近似）:

  Panel A  植物病毒属: 植物独占 vs 与其他宿主界共享 (donut)
  Panel B  共享属中出现的其他宿主界 (横向条形)
  Panel C  各分类阶元 (Species→Realm) 植物相关分类单元的宿主独占率 (条形)
  Panel D  全库物种的宿主界分布, 植物高亮 (横向条形)

数据: ../docs/data/VMR_MSL41.txt
输出: figures/genus_host_analysis_VMR.png (300 dpi)

用法:
    python 10_plot_genus_host_VMR.py
"""

import csv
import sys
from collections import Counter
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- 参数集中
SCRIPT_DIR = Path(__file__).resolve().parent
VMR_PATH = SCRIPT_DIR.parent / "docs" / "data" / "VMR_MSL41.txt"
OUT_DIR = SCRIPT_DIR / "figures"
OUT_PNG = OUT_DIR / "genus_host_analysis_VMR.png"

VMR_ENCODING = "gbk"          # MSL41 导出文件为 GBK 编码
DPI = 300
FIG_W, FIG_H = 7.5, 5.8       # inch, 双栏略宽, 手动边距
CN_FONT = "Microsoft YaHei"

# 宿主标签 → 宿主界归并
KINGDOM_MAP = {
    "plants": "Plant",
    "fungi": "Fungi",
    "invertebrates": "Animal",
    "invertebrates, vertebrates": "Animal",  # 拆分后不会出现, 保险
    "vertebrates": "Animal",
    "bacteria": "Bacteria",
    "archaea": "Archaea",
    "protists": "Protist",
    "algae": "Algae",
}
# 环境来源 (S) 标记: 宏基因组样本来源, 非经典宿主界
ENVIRONMENTAL = {"soil", "marine", "freshwater", "sewage", "air", "unknown", "phytobiome"}

# Okabe-Ito 色盲安全配色
OI = {
    "blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
    "vermillion": "#D55E00", "sky": "#56B4E9", "purple": "#CC79A7",
    "yellow": "#F0E442", "grey": "#999999",
}


def parse_hosts(raw: str):
    """'invertebrates, plants (S)' -> {'invertebrates','plants'} (宿主界归并, 环境类单独标记)"""
    out = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        base = part.replace("(S)", "").strip().lower()
        if not base:
            continue
        if base in ENVIRONMENTAL:
            out.add("Environmental")
        else:
            out.add(KINGDOM_MAP.get(base, base.title()))
    return out


def load_taxa():
    rows = []
    with open(VMR_PATH, encoding=VMR_ENCODING, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            hosts = parse_hosts(r.get("Host source", ""))
            if not hosts:
                continue
            rows.append({
                "hosts": hosts,
                "Species": (r.get("Species") or "").strip(),
                "Genus": (r.get("Genus") or "").strip(),
                "Subfamily": (r.get("Subfamily") or "").strip(),
                "Family": (r.get("Family") or "").strip(),
                "Order": (r.get("Order") or "").strip(),
                "Class": (r.get("Class") or "").strip(),
                "Phylum": (r.get("Phylum") or "").strip(),
                "Kingdom": (r.get("Kingdom") or "").strip(),
                "Realm": (r.get("Realm") or "").strip(),
            })
    return rows


def exclusive_rate(records, key):
    """按 key 聚合后, 植物相关分类单元中 '仅植物' 的独占率"""
    agg = {}
    for rec in records:
        k = rec[key]
        if k:
            agg.setdefault(k, set()).update(rec["hosts"])
    plant = {k: v for k, v in agg.items() if "Plant" in v}
    excl = sum(1 for v in plant.values() if v == {"Plant"})
    return len(plant), excl


def main():
    print("matplotlib", matplotlib.__version__, "| pandas", pd.__version__,
          "| numpy", np.__version__)
    rows = load_taxa()
    print(f"VMR 记录: {len(rows)}")

    # ---- 属级: 植物病毒属独占 vs 共享 --------------------------------
    genus = {}
    for rec in rows:
        genus.setdefault(rec["Genus"], set()).update(rec["hosts"])
    plant_genera = {g: v for g, v in genus.items() if "Plant" in v}
    exclusive_g = {g for g, v in plant_genera.items() if v == {"Plant"}}
    shared_g = {g: v - {"Plant"} for g, v in plant_genera.items() if v != {"Plant"}}
    n_pg, n_ex, n_sh = len(plant_genera), len(exclusive_g), len(shared_g)
    print(f"植物相关属: {n_pg} | 独占: {n_ex} ({n_ex/n_pg:.1%}) | 共享: {n_sh}")

    partner = Counter()
    for others in shared_g.values():
        for k in others:
            partner[k] += 1
    print("共享属的其他宿主界:", dict(partner))

    # ---- 各阶元独占率 -------------------------------------------------
    level_keys = ["Species", "Genus", "Family", "Order", "Class", "Phylum", "Kingdom", "Realm"]
    level_stats = []
    for key in level_keys:
        n_plant, n_excl = exclusive_rate(rows, key)
        if n_plant == 0:
            continue
        level_stats.append((key, n_plant, n_excl, n_excl / n_plant * 100))
        print(f"  {key}: 植物相关 {n_plant}, 独占 {n_excl} ({n_excl/n_plant:.1%})")

    # ---- 物种级宿主界分布 ----------------------------------------------
    species = {}
    for rec in rows:
        species.setdefault(rec["Species"], set()).update(rec["hosts"])
    sp_kingdom = Counter()
    for v in species.values():
        for k in v:
            sp_kingdom[k] += 1
    n_sp = len(species)
    n_plant_sp = sp_kingdom["Plant"]
    print(f"物种: {n_sp} | 含植物宿主物种: {n_plant_sp} ({n_plant_sp/n_sp:.1%})")

    # ================================================================= 绘图
    plt.rcParams["font.family"] = CN_FONT
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(2, 2, figsize=(FIG_W, FIG_H))
    axA, axB, axC, axD = axes.ravel()

    # Panel A: donut 独占 vs 共享
    vals = [n_ex, n_sh]
    colors = [OI["green"], OI["orange"]]
    wedges, _ = axA.pie(
        vals, colors=colors, startangle=90, counterclock=False,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.5),
    )
    axA.text(0, 0.08, f"{n_ex/n_pg:.1%}", ha="center", va="center",
             fontsize=17, fontweight="bold", color=OI["green"])
    axA.text(0, -0.22, "植物独占", ha="center", va="center", fontsize=9, color="#444444")
    axA.legend(wedges, [f"植物独占 {n_ex} 属", f"与其他界共享 {n_sh} 属"],
               loc="lower center", bbox_to_anchor=(0.5, -0.16),
               fontsize=8.5, frameon=False, ncol=2, columnspacing=1.2,
               handlelength=1.0, handletextpad=0.4)
    axA.set_title(f"(a) 植物病毒属的宿主独占性 (n = {n_pg} 属)",
                  fontsize=10, fontweight="bold", loc="left")

    # Panel B: 共享属的其他宿主界
    pk = partner.most_common()
    labels = [k for k, _ in pk]
    counts = [c for _, c in pk]
    y = np.arange(len(labels))
    bar_colors = [OI["grey"] if l == "Environmental" else OI["blue"] for l in labels]
    axB.barh(y, counts, color=bar_colors, height=0.62)
    axB.set_yticks(y)
    axB.set_yticklabels([f"{l}（{'环境来源' if l == 'Environmental' else '宿主界'}）" if l == "Environmental" else l
                         for l in labels], fontsize=8.5)
    axB.invert_yaxis()
    for yi, c in zip(y, counts):
        axB.text(c + 0.4, yi, str(c), va="center", fontsize=8)
    axB.set_xlabel("属数（一个属可含多个其他宿主界）", fontsize=8.5)
    axB.set_xlim(0, max(counts) * 1.15)
    axB.spines[["top", "right"]].set_visible(False)
    axB.tick_params(labelsize=8)
    axB.set_title(f"(b) 共享属中的其他宿主界 (n={n_sh})",
                  fontsize=10, fontweight="bold", loc="left")

    # Panel C: 各阶元独占率（横向条形, 阶元自上而下 Species→Realm）
    level_order = ["Species", "Genus", "Family", "Order", "Class", "Phylum", "Kingdom", "Realm"]
    stats = {k: (n, ne, r) for k, n, ne, r in level_stats}
    yc = np.arange(len(level_order))
    rates_c = [stats[k][2] if k in stats else 0 for k in level_order]
    bar_c = [OI["orange"] if k == "Genus" else OI["sky"] for k in level_order]
    axC.barh(yc, rates_c, color=bar_c, height=0.62)
    axC.set_yticks(yc)
    axC.set_yticklabels([f"{k} (n={stats[k][0]})" if k in stats else f"{k} (n=0)"
                         for k in level_order], fontsize=7.5)
    axC.invert_yaxis()
    for yi, r in zip(yc, rates_c):
        axC.text(r + 1.5, yi, f"{r:.0f}%", va="center", fontsize=7.5)
    axC.set_xlim(0, 112)
    axC.set_xlabel("植物独占率 (%)", fontsize=8.5)
    # 旧文档 "~90%" 无口径出处 (见 README《属级独占率口径说明》), 仅作历史参考线
    axC.axvline(90, ls="--", lw=0.8, color=OI["vermillion"])
    axC.text(88, len(level_order) - 0.45, "旧口径参考 ~90%", fontsize=7,
             color=OI["vermillion"], ha="right")
    axC.spines[["top", "right"]].set_visible(False)
    axC.tick_params(labelsize=8)
    axC.set_title("(c) 各分类阶元的植物宿主独占率",
                  fontsize=10, fontweight="bold", loc="left")

    # Panel D: 物种级宿主界分布
    order = sp_kingdom.most_common()
    labels_d = [k for k, _ in order]
    counts_d = [c for _, c in order]
    colors_d = [OI["green"] if k == "Plant" else "#BBBBBB" for k in labels_d]
    yd = np.arange(len(labels_d))
    axD.barh(yd, counts_d, color=colors_d, height=0.62)
    axD.set_yticks(yd)
    axD.set_yticklabels(labels_d, fontsize=8.5)
    axD.invert_yaxis()
    axD.set_xscale("log")
    for yi, c in zip(yd, counts_d):
        axD.text(c * 1.15, yi, str(c), va="center", fontsize=7.5)
    axD.set_xlim(right=max(counts_d) * 6)
    axD.set_xlabel("物种数 (log 刻度)", fontsize=8.5)
    axD.spines[["top", "right"]].set_visible(False)
    axD.tick_params(labelsize=8)
    axD.set_title(f"(d) 物种宿主分布（植物 15.8%）",
                  fontsize=10, fontweight="bold", loc="left")

    fig.suptitle("基于属分类的宿主分析（ICTV MSL41, VMR 全量 19,271 条记录）",
                 fontsize=12, fontweight="bold", y=0.98)
    fig.subplots_adjust(left=0.17, right=0.98, top=0.875, bottom=0.09,
                        wspace=0.62, hspace=0.52)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=DPI)
    plt.close(fig)
    print("已保存:", OUT_PNG)


if __name__ == "__main__":
    sys.exit(main())
