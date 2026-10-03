# -*- coding: utf-8 -*-
"""
11. 属级宿主独占 vs 共享堆叠柱状图（复现服务器版原图）

复现 2_plot_overlap.py 产出的 "Virus Genus Exclusive vs Shared per Host Category"
（原图基于服务器 classified_clean/ C4 清洗数据统计; 本脚本使用原图上标注的
 精确数值 1:1 复现, 便于本地修改样式或数据更新后重绘）。

数据 (excl=独占属数, shared=共享属数, 来源: 原图标注):
    Bacteria     1657 +  1 = 1658  (100%)
    Animal_other  175 + 78 =  253  ( 69%)
    Insecta       142 + 76 =  218  ( 65%)
    Plant         183 + 10 =  193  ( 95%)
    Aves           66 + 47 =  113  ( 58%)
    Fungi          67 + 12 =   79  ( 85%)
    Arachnida      21 + 41 =   62  ( 34%)

输出: figures/genus_exclusive_vs_shared.png (300 dpi)
"""

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------- 参数集中
SCRIPT_DIR = Path(__file__).resolve().parent
OUT_PNG = SCRIPT_DIR / "figures" / "genus_exclusive_vs_shared.png"

DPI = 300
FIG_W, FIG_H = 10.0, 6.0

# 类别: (独占属数, 共享属数)  —— 按总数降序, 与原图一致
DATA = {
    "Bacteria": (1657, 1),
    "Animal_other": (175, 78),
    "Insecta": (142, 76),
    "Plant": (183, 10),
    "Aves": (66, 47),
    "Fungi": (67, 12),
    "Arachnida": (21, 41),
}

# 与原图一致的类别配色 (matplotlib tab10 原图取色顺序)
COLORS = {
    "Bacteria": "#1f77b4",
    "Animal_other": "#ff7f0e",
    "Insecta": "#d62728",
    "Plant": "#8c564b",
    "Aves": "#e377c2",
    "Fungi": "#bcbd22",
    "Arachnida": "#17becf",
}


def main():
    print("matplotlib", matplotlib.__version__)

    plt.rcParams["font.family"] = "Microsoft YaHei"
    plt.rcParams["axes.unicode_minus"] = False

    cats = list(DATA)                       # 字典序即原图的总数降序
    excl = np.array([DATA[c][0] for c in cats], dtype=float)
    shared = np.array([DATA[c][1] for c in cats], dtype=float)
    total = excl + shared
    rate = excl / total * 100

    colors = [COLORS[c] for c in cats]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f7f7")
    ax.grid(axis="y", color="white", linewidth=1.2, zorder=0)
    ax.set_axisbelow(True)

    x = np.arange(len(cats))
    # 独占段(实心) + 共享段(斜线纹理)
    ax.bar(x, excl, width=0.62, color=colors, zorder=3)
    ax.bar(x, shared, width=0.62, bottom=excl, color=colors,
           hatch="//", edgecolor="white", linewidth=1.0, zorder=3)

    # 顶部标注 "excl+shared=total"; 独占率白字标在实心段中部,
    # 实心段过矮的柱 (如 Arachnida) 标签移到柱右侧空白处, 用类别色避免被纹理/轴线切碎
    for xi, (e, s, t, r, c) in enumerate(zip(excl, shared, total, rate, cats)):
        ax.text(xi, t + total.max() * 0.015, f"{int(e)}+{int(s)}={int(t)}",
                ha="center", va="bottom", fontsize=9, fontweight="bold")
        if e > total.max() * 0.035:
            ax.text(xi, e / 2, f"{r:.0f}%", ha="center", va="center",
                    fontsize=9.5, fontweight="bold", color="white")
        else:
            side_y = max(e / 2, total.max() * 0.028)   # 抬离 x 轴线, 避免基线切字
            ax.text(xi + 0.38, side_y, f"{r:.0f}%", ha="left", va="center",
                    fontsize=8, fontweight="bold", color=COLORS[c])

    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Number of Genus", fontsize=11)
    ax.set_ylim(0, total.max() * 1.10)
    ax.tick_params(labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    ax.set_title("Virus Genus Exclusive vs Shared per Host Category",
                 fontsize=13, fontweight="bold", pad=14)

    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=COLORS[c], edgecolor="white")
               for c in cats]
    labels = [f"{c} (excl={DATA[c][0]})" for c in cats]
    ax.legend(handles, labels, fontsize=8.5, frameon=True,
              loc="upper right", framealpha=0.95)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=DPI)
    plt.close(fig)
    print("已保存:", OUT_PNG)


if __name__ == "__main__":
    raise SystemExit(main())
