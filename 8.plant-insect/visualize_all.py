"""
植物病毒-媒介-宿主 数据可视化
4张出版级图表
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

# ── 全局样式 ─────────────────────────────────
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'DejaVu Sans'],
    'font.size': 9,
    'axes.titlesize': 11,
    'axes.labelsize': 10,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 7.5,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1,
})

OUT = r'D:\桌面\C-host_classify\plant_virus_db_pipeline\8.plant-insect'

# ── 配色 ───────────────────────────────────
# Colorblind-friendly (Wong, 2011)
CB_PALETTE = ['#0072B2', '#E69F00', '#009E73', '#F0E442',
              '#D55E00', '#CC79A7', '#56B4E9', '#000000']

FAMILY_PALETTE = {
    'Geminiviridae': '#E63946',
    'Potyviridae': '#457B9D',
    'Secoviridae': '#2A9D8F',
    'Solemoviridae': '#E9C46A',
    'Tospoviridae': '#F4A261',
    'Bromoviridae': '#264653',
    'Closteroviridae': '#A8DADC',
    'Tombusviridae': '#6D6875',
    'Spinareoviridae': '#B5838D',
    'Rhabdoviridae': '#FFB4A2',
}

# ── 加载数据 ─────────────────────────────────
def load_data():
    vvh = pd.read_csv(f'{OUT}/virus_vector_host.tsv', sep='\t')
    wur = pd.read_csv(f'{OUT}/wur_virus_full.tsv', sep='\t', quoting=3)  # QUOTE_NONE
    return vvh, wur


# ═══════════════════════════════════════════
# FIG 1: 三联面板 — 宏观概览
# ═══════════════════════════════════════════
def fig1_overview(vvh):
    fig = plt.figure(figsize=(14, 5.5))
    gs = GridSpec(1, 3, figure=fig, wspace=0.35, width_ratios=[1.2, 1, 1])

    # ── A: 病毒科 TOP12 ──
    ax_a = fig.add_subplot(gs[0])
    fam_counts = vvh['Virus Family'].value_counts().head(12)
    colors_a = [FAMILY_PALETTE.get(f, '#999999') for f in fam_counts.index]
    bars = ax_a.barh(range(len(fam_counts)), fam_counts.values[::-1], height=0.7, color=colors_a[::-1])
    ax_a.set_yticks(range(len(fam_counts)))
    ax_a.set_yticklabels(fam_counts.index[::-1])
    ax_a.set_xlabel('Number of records')
    ax_a.set_title('A  Virus Family Distribution\n(virus_vector_host)', loc='left', fontweight='bold')
    ax_a.spines['top'].set_visible(False)
    ax_a.spines['right'].set_visible(False)
    for i, (bar, val) in enumerate(zip(bars, fam_counts.values[::-1])):
        ax_a.text(val + 2, bar.get_y() + bar.get_height()/2, str(val), va='center', fontsize=7)

    # ── B: 传播方式 ──
    ax_b = fig.add_subplot(gs[1])
    tm = vvh['Virus Transmission Mode'].value_counts()
    # 简化标签
    label_map = {
        'Circulative, Persistent Non-Propagative Transmission': 'Circulative,\nPersistent Non-Prop.',
        'Circulative, Persistent-Propagative Transmission': 'Circulative,\nPersistent-Propagative',
        'Non-Persistent Transmission': 'Non-Persistent',
        'Non-Circulative, Semi-Persistent Transmission': 'Non-Circulative,\nSemi-Persistent',
        'Persistent, circulative': 'Persistent,\nCirculative',
    }
    labels = [label_map.get(k, k) for k in tm.index]
    colors_b = CB_PALETTE[:len(tm)]
    wedges, texts, autotexts = ax_b.pie(tm.values, labels=None, autopct='%1.1f%%',
                                          colors=colors_b, pctdistance=0.78,
                                          wedgeprops=dict(width=0.35, edgecolor='white', linewidth=0.8))
    ax_b.set_title('B  Transmission Modes', loc='left', fontweight='bold')
    # Legend
    legend_labels = [f'{l}\n(n={v})' for l, v in zip(labels, tm.values)]
    ax_b.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(1.05, 0.5),
                fontsize=6.5, frameon=False)

    # ── C: 媒介目 + 科 ──
    ax_c = fig.add_subplot(gs[2])
    vo = vvh['Vector Order'].value_counts()
    orders_sort = ['Hemiptera', 'Thysanoptera', 'Coleoptera', 'Lepidoptera', 'Diptera', 'Hymenoptera']
    vo_sorted = pd.Series({k: vo.get(k, 0) for k in orders_sort if k in vo.index})

    # 每个 Order 下细分 Family
    bottom = np.zeros(len(vo_sorted))
    fam_in_order = {}
    for order in vo_sorted.index:
        fam_in_order[order] = vvh[vvh['Vector Order'] == order]['Vector Family'].value_counts()

    all_order_families = set()
    for fams in fam_in_order.values():
        all_order_families.update(fams.index)

    colors_c = plt.cm.Set3(np.linspace(0, 1, len(all_order_families)))
    fam_color = dict(zip(all_order_families, colors_c))

    for order_idx, order in enumerate(vo_sorted.index):
        fams = fam_in_order[order]
        cumsum = 0
        for fam, cnt in fams.items():
            ax_c.bar(order_idx, cnt, bottom=cumsum, color=fam_color[fam],
                     width=0.55, edgecolor='white', linewidth=0.4)
            if cnt > 20:
                ax_c.text(order_idx, cumsum + cnt/2, fam[:12], ha='center', va='center',
                         fontsize=5.5, rotation=0)
            cumsum += cnt

    ax_c.set_xticks(range(len(vo_sorted)))
    ax_c.set_xticklabels(vo_sorted.index, rotation=30, ha='right')
    ax_c.set_ylabel('Number of records')
    ax_c.set_title('C  Vector Order & Family Composition', loc='left', fontweight='bold')
    ax_c.spines['top'].set_visible(False)
    ax_c.spines['right'].set_visible(False)

    fig.suptitle('Plant Virus – Vector – Host Database: Macro-scale Overview',
                 fontsize=13, fontweight='bold', y=1.02)
    fig.savefig(f'{OUT}/Fig1_overview.png', dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print('Fig1 saved ✓')


# ═══════════════════════════════════════════
# FIG 2: 病毒科 × 媒介科 热图
# ═══════════════════════════════════════════
def fig2_heatmap(vvh):
    # Top virus families × top vector families
    top_vfams = vvh['Virus Family'].value_counts().head(12).index
    top_vfams_vec = vvh['Vector Family'].value_counts().head(10).index

    cross = pd.crosstab(vvh['Virus Family'], vvh['Vector Family'])
    cross = cross.loc[cross.index.isin(top_vfams), cross.columns.isin(top_vfams_vec)]
    # 去掉全0行/列
    cross = cross.loc[cross.sum(axis=1) > 0, cross.sum(axis=0) > 0]

    fig, ax = plt.subplots(figsize=(9, 6))

    # Custom colormap
    cmap = LinearSegmentedColormap.from_list('custom', ['#F7FBFF', '#2171B5', '#08306B'])

    im = ax.imshow(cross.values, aspect='auto', cmap=cmap)

    # Annotate
    for i in range(cross.shape[0]):
        for j in range(cross.shape[1]):
            val = cross.values[i, j]
            if val > 0:
                color = 'white' if val > cross.values.max() * 0.6 else 'black'
                ax.text(j, i, str(val), ha='center', va='center', fontsize=7, color=color)

    ax.set_xticks(range(cross.shape[1]))
    ax.set_xticklabels(cross.columns, rotation=45, ha='right', fontsize=8)
    ax.set_yticks(range(cross.shape[0]))
    ax.set_yticklabels(cross.index, fontsize=8)
    ax.set_xlabel('Vector Family', fontsize=10)
    ax.set_ylabel('Virus Family', fontsize=10)
    ax.set_title('Virus Family × Vector Family Association Heatmap', fontsize=12,
                 fontweight='bold', loc='left')

    cbar = plt.colorbar(im, ax=ax, shrink=0.82, pad=0.02)
    cbar.set_label('Records', fontsize=9)

    fig.tight_layout()
    fig.savefig(f'{OUT}/Fig2_heatmap.png', dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print('Fig2 saved ✓')


# ═══════════════════════════════════════════
# FIG 3: 病毒科 → 传播方式 冲积图 (用堆叠柱状图近似)
# ═══════════════════════════════════════════
def fig3_transmission_by_family(vvh):
    top_fams = vvh['Virus Family'].value_counts().head(10).index
    df = vvh[vvh['Virus Family'].isin(top_fams)]

    # 简化传播方式
    def simplify_tm(tm):
        if 'Non-Propagative' in str(tm):
            return 'Circulative\nNon-Propagative'
        elif 'Propagative' in str(tm):
            return 'Circulative\nPropagative'
        elif 'Non-Persistent' in str(tm):
            return 'Non-Persistent'
        elif 'Semi-Persistent' in str(tm):
            return 'Semi-Persistent'
        elif 'Persistent, circulative' in str(tm):
            return 'Persistent\nCirculative'
        return 'Other/NA'
    df['TM_simple'] = df['Virus Transmission Mode'].apply(simplify_tm)

    cross = pd.crosstab(df['Virus Family'], df['TM_simple'])
    # 按总量排序
    cross['total'] = cross.sum(axis=1)
    cross = cross.sort_values('total', ascending=True).drop(columns='total')

    # 统一列顺序
    desired_order = ['Circulative\nNon-Propagative', 'Circulative\nPropagative',
                     'Non-Persistent', 'Semi-Persistent', 'Persistent\nCirculative', 'Other/NA']
    for col in desired_order:
        if col not in cross.columns:
            cross[col] = 0
    cross = cross[desired_order]

    fig, ax = plt.subplots(figsize=(10, 5.5))

    tm_colors = {
        'Circulative\nNon-Propagative': '#457B9D',
        'Circulative\nPropagative': '#E63946',
        'Non-Persistent': '#2A9D8F',
        'Semi-Persistent': '#E9C46A',
        'Persistent\nCirculative': '#F4A261',
        'Other/NA': '#CCCCCC',
    }

    left = np.zeros(len(cross))
    for col in cross.columns:
        bars = ax.barh(cross.index, cross[col], left=left, color=tm_colors[col],
                       height=0.65, label=col, edgecolor='white', linewidth=0.4)
        left += cross[col].values

    ax.set_xlabel('Number of records')
    ax.set_title('Virus Family × Transmission Mode Composition', fontsize=12,
                 fontweight='bold', loc='left')
    ax.legend(loc='lower right', fontsize=7.5, frameon=True, ncol=2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    fig.tight_layout()
    fig.savefig(f'{OUT}/Fig3_transmission_family.png', dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print('Fig3 saved ✓')


# ═══════════════════════════════════════════
# FIG 4: wur_virus_full — 文献量 + 媒介类别
# ═══════════════════════════════════════════
def fig4_wur_overview(wur):
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    # ── A: Top virus families ──
    ax = axes[0]
    fams = wur['family'].value_counts().head(12)
    bars = ax.barh(range(len(fams)), fams.values[::-1], height=0.7,
                   color=plt.cm.viridis(np.linspace(0.15, 0.85, len(fams)))[::-1])
    ax.set_yticks(range(len(fams)))
    ax.set_yticklabels(fams.index[::-1])
    ax.set_xlabel('Number of viruses')
    ax.set_title('A  Virus Families\n(wur_virus_full)', loc='left', fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    for bar, val in zip(bars, fams.values[::-1]):
        ax.text(val + 1, bar.get_y() + bar.get_height()/2, str(val), va='center', fontsize=7)

    # ── B: Reference count distribution ──
    ax = axes[1]
    ref_counts = wur['ref_count'].astype(int)
    bins = np.arange(0, ref_counts.max() + 2) - 0.5
    ax.hist(ref_counts, bins=bins, color='#457B9D', edgecolor='white', linewidth=0.5,
            alpha=0.85)
    ax.axvline(ref_counts.median(), color='#E63946', linestyle='--', linewidth=1.2,
               label=f'Median = {ref_counts.median():.0f}')
    ax.axvline(ref_counts.mean(), color='#E9C46A', linestyle='--', linewidth=1.2,
               label=f'Mean = {ref_counts.mean():.1f}')
    ax.set_xlabel('Reference count per virus')
    ax.set_ylabel('Number of viruses')
    ax.set_title('B  Literature Coverage', loc='left', fontweight='bold')
    ax.legend(fontsize=7, frameon=False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # ── C: Vector organism categories ──
    ax = axes[2]
    # Clean vector_org
    def classify_vector(vo):
        vo = str(vo).strip().lower()
        if not vo or vo == 'nan':
            return 'Unknown'
        if 'aphid' in vo:
            return 'Aphid'
        if 'whitefly' in vo or 'aleyrod' in vo:
            return 'Whitefly'
        if 'leafhopper' in vo or 'cicadellid' in vo:
            return 'Leafhopper'
        if 'mite' in vo:
            return 'Mite'
        if 'thrips' in vo:
            return 'Thrips'
        if 'beetle' in vo or 'chrysomelid' in vo or 'coccinellid' in vo:
            return 'Beetle'
        if 'nematode' in vo:
            return 'Nematode'
        if 'mealybug' in vo:
            return 'Mealybug'
        if 'planthopper' in vo or 'delphacid' in vo:
            return 'Planthopper'
        if 'plasmodiophor' in vo or 'olpid' in vo:
            return 'Fungus-like'
        if 'no vector' in vo or 'none' in vo:
            return 'No vector reported'
        return 'Other'
    wur['vec_class'] = wur['vector_org'].apply(classify_vector)
    vec_counts = wur['vec_class'].value_counts()
    order = ['Aphid', 'Whitefly', 'Leafhopper', 'Mite', 'Beetle', 'Thrips',
             'Mealybug', 'Planthopper', 'Nematode', 'Fungus-like', 'No vector reported', 'Other', 'Unknown']
    vec_sorted = pd.Series({k: vec_counts.get(k, 0) for k in order if k in vec_counts.index})

    colors_v = ['#457B9D', '#E63946', '#2A9D8F', '#E9C46A', '#F4A261', '#264653',
                '#A8DADC', '#6D6875', '#B5838D', '#FFB4A2', '#CCCCCC', '#999999', '#DDDDDD']
    wedges, texts, autotexts = ax.pie(vec_sorted.values, labels=None, autopct='',
                                        colors=colors_v[:len(vec_sorted)],
                                        wedgeprops=dict(width=0.38, edgecolor='white', linewidth=0.5))
    legend_labels = [f'{l} ({v})' for l, v in zip(vec_sorted.index, vec_sorted.values)]
    ax.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(1.02, 0.5),
              fontsize=6.5, frameon=False)
    ax.set_title('C  Vector Categories\n(wur_virus_full)', loc='left', fontweight='bold')

    fig.suptitle('WUR Plant Virus Database: Diversity & Literature Coverage',
                 fontsize=13, fontweight='bold', y=1.02)
    fig.tight_layout()
    fig.savefig(f'{OUT}/Fig4_wur_overview.png', dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print('Fig4 saved ✓')


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
if __name__ == '__main__':
    print('Loading data...')
    vvh, wur = load_data()
    print(f'  virus_vector_host: {len(vvh)} rows')
    print(f'  wur_virus_full: {len(wur)} rows')

    print('\nGenerating figures...')
    fig1_overview(vvh)
    fig2_heatmap(vvh)
    fig3_transmission_by_family(vvh)
    fig4_wur_overview(wur)
    print('\nAll figures generated successfully.')
