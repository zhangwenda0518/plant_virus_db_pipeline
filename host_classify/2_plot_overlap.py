# -*- coding: utf-8 -*-
"""
C6: Deep Evolutionary Cross-kingdom visualization (Realm to Genus).

Biological Rules:
  1. All taxonomic levels INCLUDED (C4 handles cross-kingdom cleaning).
  2. HVT families EXCLUDED (Mitoviridae, Partitiviridae, etc.) to reveal true homology.

Outputs:
  1. Grouped Bar Chart (evolutionary divergence).
  2. UpSet Matrices (.csv) for R ComplexUpset.

Usage:
  python C6_plot_cross_kingdom.py -i classified_clean/ -o cross_analysis/ -s Plant
"""
import polars as pl
import os, argparse
import numpy as np
import matplotlib.pyplot as plt

TAXA_LEVELS = {
    "Realm": 0, "Kingdom": 1, "Phylum": 2, "Class": 3,
    "Order": 4, "Family": 5, "Genus": 6, "Species": 7,
}
LEVEL_ORDER = list(TAXA_LEVELS.keys())
# Upset matrices: exclude Species (vector/diet transit noise)
UPSET_LEVELS = ["Realm", "Kingdom", "Phylum", "Class", "Order", "Family", "Genus"]

EXCLUDE_FAMS = set()  # C4 has already cleaned the data; no additional filtering needed
SKIP = {"All_Processed_Records", "Summary_Counts", "Task1_", "Task2_", "Plant_Virus_"}


def load_taxa(path):
    df = pl.read_csv(path, separator='\t', truncate_ragged_lines=True)
    vp = pl.col("Virus_lineage") + ";;;;;;;;"
    fam = vp.str.split(";").list.get(5).str.strip_chars()
    df = df.with_columns(fam.alias("V_Family_Filter"))
    df = df.filter(~pl.col("V_Family_Filter").is_in(list(EXCLUDE_FAMS)))
    exprs = []
    for name, idx in TAXA_LEVELS.items():
        c = vp.str.split(";").list.get(idx).str.strip_chars()
        exprs.append(c.alias(f"V_{name}"))
    return df.with_columns(exprs)


def collect_overlap(input_dir, source):
    source_file = os.path.join(input_dir, f"{source}.tsv")
    df_src = load_taxa(source_file)
    src_taxa = {lvl: set(df_src[f"V_{lvl}"].to_list()) - {""} for lvl in LEVEL_ORDER}
    overlap_data = {}
    upset_data = {lvl: {} for lvl in UPSET_LEVELS}

    for f in sorted(os.listdir(input_dir)):
        if not f.endswith('.tsv') or any(p in f for p in SKIP):
            continue
        cat = f.replace('.tsv', '')
        if cat == source:
            continue
        df_cat = load_taxa(os.path.join(input_dir, f))
        overlap_data[cat] = {}
        for lvl in LEVEL_ORDER:
            cat_set = set(df_cat[f"V_{lvl}"].to_list()) - {""}
            shared = src_taxa[lvl] & cat_set
            overlap_data[cat][lvl] = len(shared)
            if lvl in UPSET_LEVELS and shared:
                upset_data[lvl][cat] = shared
    return overlap_data, upset_data


def plot_grouped_bar(overlap_data, output_path, source):
    """Grouped bar chart: shared taxa count drops sharply with taxonomic refinement."""
    valid_cats = [c for c in overlap_data if overlap_data[c].get("Realm", 0) > 0]
    valid_cats.sort()

    fig, ax = plt.subplots(figsize=(14, 7))
    x = np.arange(len(LEVEL_ORDER))
    total_width = 0.85
    width = total_width / max(len(valid_cats), 1)
    colors = plt.cm.tab20(np.linspace(0, 1, len(valid_cats)))

    for i, cat in enumerate(valid_cats):
        vals = [overlap_data[cat].get(l, 0) for l in LEVEL_ORDER]
        pos = x - total_width/2 + i*width + width/2
        bars = ax.bar(pos, vals, width, label=cat, color=colors[i], edgecolor='white', linewidth=0.5)
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                        str(val), ha='center', va='bottom', fontsize=7, rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(LEVEL_ORDER, fontsize=12)
    ax.set_ylabel("Shared Taxa Count", fontsize=12, fontweight='bold')
    ax.set_title(f"{source} Evolutionary Overlap (Species & HVT Excluded)", fontsize=15, fontweight='bold')
    ax.legend(title="Target", bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"  [1] Grouped bar: {output_path}")


def export_upset_matrices(upset_data, out_dir, source):
    """Export 0/1 presence-absence matrices for R ComplexUpset."""
    for lvl in UPSET_LEVELS:
        data = upset_data.get(lvl, {})
        if not data:
            continue
        cats = sorted(data.keys())
        all_taxa = sorted(set().union(*data.values()))
        out_path = os.path.join(out_dir, f"{source}_upset_matrix_{lvl}.csv")
        with open(out_path, 'w') as f:
            f.write("Taxon," + ",".join(cats) + "\n")
            for taxon in all_taxa:
                row = [taxon]
                for cat in cats:
                    row.append("1" if taxon in data[cat] else "0")
                f.write(",".join(row) + "\n")
        print(f"  [2] Upset matrix ({lvl}): {out_path}")


def compute_exclusive_vs_shared(input_dir, source):
    """Split Plant taxa at each level into exclusive (only Plant) vs shared (any other category)."""
    source_file = os.path.join(input_dir, f"{source}.tsv")
    df_src = load_taxa(source_file)

    # All taxa from all other categories
    other_taxa = {lvl: set() for lvl in LEVEL_ORDER}
    for f in sorted(os.listdir(input_dir)):
        cat = f.replace('.tsv', '')
        if not f.endswith('.tsv') or cat == source or any(p in f for p in SKIP):
            continue
        df_c = load_taxa(os.path.join(input_dir, f))
        for lvl in LEVEL_ORDER:
            other_taxa[lvl] |= set(df_c[f"V_{lvl}"].to_list()) - {""}

    exclusive = {}
    shared = {}
    for lvl in LEVEL_ORDER:
        src_set = set(df_src[f"V_{lvl}"].to_list()) - {""}
        exclusive[lvl] = len(src_set - other_taxa[lvl])
        shared[lvl] = len(src_set & other_taxa[lvl])
    return exclusive, shared


def plot_exclusive_shared(exclusive, shared, output_path, source):
    """Grouped bar chart: Exclusive vs Shared taxa at each level."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    levels_show = LEVEL_ORDER  # all 8 levels including Species
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    x = np.arange(len(levels_show))
    width = 0.35

    # ---- Grouped bar ----
    excl_vals = [exclusive[l] for l in levels_show]
    shar_vals = [shared[l] for l in levels_show]
    bars1 = ax1.bar(x - width/2, excl_vals, width, label='Plant-Exclusive',
                    color='#2c7bb6', edgecolor='white', linewidth=0.5)
    bars2 = ax1.bar(x + width/2, shar_vals, width, label='Cross-Kingdom Shared',
                    color='#d7191c', edgecolor='white', linewidth=0.5)
    for bar, val in zip(bars1, excl_vals):
        if val > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                     str(val), ha='center', va='bottom', fontsize=8, fontweight='bold', color='#2c7bb6')
    for bar, val in zip(bars2, shar_vals):
        if val > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                     str(val), ha='center', va='bottom', fontsize=8, fontweight='bold', color='#d7191c')
    ax1.set_xticks(x)
    ax1.set_xticklabels(levels_show, fontsize=11)
    ax1.set_ylabel("Number of Taxa", fontsize=12)
    ax1.set_title(f"{source}: Exclusive vs Shared Taxa (Grouped)", fontsize=13)
    ax1.legend(fontsize=10)
    ax1.grid(axis='y', alpha=0.3)
    ax1.spines['top'].set_visible(False); ax1.spines['right'].set_visible(False)

    # ---- Stacked percentage bar ----
    totals = [exclusive[l] + shared[l] for l in levels_show]
    excl_pct = [exclusive[l] / totals[i] * 100 if totals[i] > 0 else 0 for i, l in enumerate(levels_show)]
    shar_pct = [shared[l] / totals[i] * 100 if totals[i] > 0 else 0 for i, l in enumerate(levels_show)]
    p1 = ax2.bar(x, excl_pct, color='#2c7bb6', edgecolor='white', linewidth=0.5)
    p2 = ax2.bar(x, shar_pct, bottom=excl_pct, color='#d7191c', edgecolor='white', linewidth=0.5)
    for i in range(len(x)):
        if excl_pct[i] > 5:
            ax2.text(x[i], excl_pct[i]/2, f'{excl_pct[i]:.0f}%', ha='center', va='center',
                     fontsize=8, fontweight='bold', color='white')
        if shar_pct[i] > 5:
            ax2.text(x[i], excl_pct[i] + shar_pct[i]/2, f'{shar_pct[i]:.0f}%', ha='center',
                     va='center', fontsize=8, fontweight='bold', color='white')
    ax2.set_xticks(x)
    ax2.set_xticklabels(levels_show, fontsize=11)
    ax2.set_ylabel("Percentage", fontsize=12)
    ax2.set_title(f"{source}: Exclusive vs Shared Taxa (Stacked %)", fontsize=13)
    ax2.legend(fontsize=10)
    ax2.set_ylim(0, 105)
    ax2.spines['top'].set_visible(False); ax2.spines['right'].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"  [3] Exclusive/Shared bar: {output_path}")


def compute_all_exclusive(input_dir):
    """Compute exclusive taxa counts for ALL categories at all levels."""
    CORE_CATS = ["Plant", "Insecta", "Arachnida", "Fungi", "Bacteria",
                 "Animal_other", "Aves", "Mammalia", "Human"]
    cat_taxa = {}
    for f in sorted(os.listdir(input_dir)):
        cat = f.replace('.tsv', '')
        if not f.endswith('.tsv') or cat not in CORE_CATS:
            continue
        df = load_taxa(os.path.join(input_dir, f))
        cat_taxa[cat] = {}
        for lvl in LEVEL_ORDER:
            cat_taxa[cat][lvl] = set(df[f"V_{lvl}"].to_list()) - {""}

    all_exclusive = {}
    for cat in cat_taxa:
        all_exclusive[cat] = {}
        for lvl in LEVEL_ORDER:
            own_set = cat_taxa[cat][lvl]
            others = set()
            for other_cat, other_data in cat_taxa.items():
                if other_cat != cat:
                    others |= other_data.get(lvl, set())
            all_exclusive[cat][lvl] = len(own_set - others)
    return all_exclusive, cat_taxa


def plot_all_exclusive(all_exclusive, cat_taxa, output_path):
    """Heatmap-style grouped bar: exclusive taxa per category at each level."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    cats = sorted(all_exclusive.keys())
    levels_show = ["Realm", "Kingdom", "Phylum", "Class", "Order", "Family", "Genus"]

    fig, ax = plt.subplots(figsize=(16, 8))
    x = np.arange(len(cats))
    n_bars = len(levels_show)
    width = 0.8 / n_bars
    colors = plt.cm.viridis(np.linspace(0.1, 0.9, n_bars))

    for i, lvl in enumerate(levels_show):
        pos = x - 0.4 + i * width + width / 2
        vals = [all_exclusive[cat].get(lvl, 0) for cat in cats]
        bars = ax.bar(pos, vals, width, label=lvl, color=colors[i], edgecolor='white', linewidth=0.3)
        # Only annotate top values
        for bar, val in zip(bars, vals):
            if val > 50:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        str(val), ha='center', va='bottom', fontsize=5, rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=10)
    ax.set_ylabel("Number of Exclusive Taxa", fontsize=12, fontweight='bold')
    ax.set_title("Virus Taxa Exclusive to Each Host Category (HVT Families Excluded)", fontsize=14, fontweight='bold')
    ax.legend(title="Taxonomic Level", fontsize=7, ncol=4, loc='upper right')
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"  [4] All-category exclusive: {output_path}")

    # Print detailed table
    print(f"\n{'='*80}")
    print(f"EXCLUSIVE TAXA PER CATEGORY (HVT excluded)")
    print(f"{'='*80}")
    header = f"{'Category':16s}"
    for lvl in levels_show:
        header += f" {lvl:>8s}"
    print(header)
    print("-" * (16 + 9 * len(levels_show)))
    for cat in cats:
        row = f"{cat:16s}"
        for lvl in levels_show:
            e = all_exclusive[cat].get(lvl, 0)
            total = len(cat_taxa[cat].get(lvl, set()))
            row += f" {e:>5d}/{total:<2d}" if total > 0 else f" {'-':>8s}"
        print(row)

    # Export table
    tsv_path = output_path.replace('.pdf', '.tsv')
    with open(tsv_path, 'w') as f:
        f.write("Category\t" + "\t".join(levels_show) + "\n")
        for cat in cats:
            vals = "\t".join(str(all_exclusive[cat].get(l, 0)) for l in levels_show)
            f.write(f"{cat}\t{vals}\n")
    print(f"  Table: {tsv_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input_dir", default="classified_clean/")
    p.add_argument("-o", "--output_dir", default="cross_analysis/")
    p.add_argument("-s", "--source", default="Plant")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"Deep homology analysis: {args.source}")

    overlap_data, upset_data = collect_overlap(args.input_dir, args.source)

    plot_grouped_bar(overlap_data,
                     os.path.join(args.output_dir, f"{args.source}_evolutionary_bar.pdf"),
                     args.source)
    export_upset_matrices(upset_data, args.output_dir, args.source)

    # Exclusive vs Shared (Plant only)
    exclusive, shared = compute_exclusive_vs_shared(args.input_dir, args.source)
    plot_exclusive_shared(exclusive, shared,
                          os.path.join(args.output_dir, f"{args.source}_exclusive_vs_shared.pdf"),
                          args.source)

    # All-category exclusive analysis
    all_exclusive, cat_taxa = compute_all_exclusive(args.input_dir)
    plot_all_exclusive(all_exclusive, cat_taxa,
                       os.path.join(args.output_dir, "all_categories_exclusive.pdf"))

    # Print table
    print(f"\n{'='*60}")
    print(f"{'Level':10s} {'Exclusive':>10s} {'Shared':>10s} {'Total':>10s} {'%Exclusive':>10s}")
    print(f"{'-'*50}")
    for lvl in LEVEL_ORDER:
        e = exclusive[lvl]; s = shared[lvl]; t = e + s
        pct = e / t * 100 if t > 0 else 0
        print(f"{lvl:10s} {e:>10,d} {s:>10,d} {t:>10,d} {pct:>9.1f}%")


if __name__ == "__main__":
    main()
