"""
PAmiRDB Result Visualizations.
Generates publication-quality charts from prediction data.
"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# Style
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 9,
    'axes.titlesize': 11,
    'axes.labelsize': 9,
    'figure.dpi': 150,
    'savefig.dpi': 150,
    'savefig.bbox': 'tight',
})

COLORS = {
    'geminiviridae': '#3498db',
    'potyviridae': '#e67e22',
    'A. thaliana': '#2ecc71', 'G. max': '#27ae60',
    'O. sativa': '#1abc9c', 'S. bicolor': '#16a085',
    'S. lycopersicum': '#e74c3c', 'V. vinifera': '#9b59b6',
    'Z. mays': '#f39c12',
}

SPECIES_ORDER = ['Arabidopsis thaliana', 'Oryza sativa', 'Glycine max',
                 'Sorghum bicolor', 'Solanum lycopersicum', 'Vitis vinifera', 'Zea mays']

with open(DATA_DIR / 'predictions.json') as f:
    preds = json.load(f)

with open(DATA_DIR / 'mirna' / 'plant_mirnas.json') as f:
    mirnas = json.load(f)

with open(DATA_DIR / 'virus_genomes' / 'viruses.json') as f:
    viruses = json.load(f)

out_dir = Path(__file__).parent.parent / "figures"
out_dir.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════
# FIGURE 1: Species × Virus Family heatmap
# ═══════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 5))

families = ['geminiviridae', 'potyviridae']
matrix = np.zeros((7, 2))
species_list = []
for i, sp in enumerate(SPECIES_ORDER):
    species_list.append(sp)
    for j, fam in enumerate(families):
        cnt = sum(1 for p in preds
                  if p.get('mirna_species_name') == sp
                  and p.get('target_virus_family') == fam)
        matrix[i, j] = cnt

im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto', vmin=0)

ax.set_xticks(range(2))
ax.set_xticklabels(['Geminiviridae', 'Potyviridae'], fontsize=9)
ax.set_yticks(range(7))
ax.set_yticklabels([s.replace(' ', '\n') for s in species_list], fontsize=8)

for i in range(7):
    for j in range(2):
        val = int(matrix[i, j])
        color = 'white' if val > max(matrix.max()*0.6, 1) else 'black'
        ax.text(j, i, str(val), ha='center', va='center', fontsize=10,
                fontweight='bold', color=color)

ax.set_title('miRNA-Virus Interactions by Species and Family', fontweight='bold')
cbar = plt.colorbar(im, ax=ax, shrink=0.85)
cbar.set_label('Predicted Interactions')

fig.tight_layout()
fig.savefig(out_dir / 'fig1_species_family_heatmap.png')
plt.close()
print("Figure 1 saved")

# ═══════════════════════════════════════════════════════════════════
# FIGURE 2: Energy distribution histogram
# ═══════════════════════════════════════════════════════════════════
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

energies = [p['energy'] for p in preds]

# Histogram
ax1.hist(energies, bins=16, color='#2c6e49', edgecolor='white', alpha=0.85)
ax1.axvline(x=-20, color='#e74c3c', linestyle='--', linewidth=1.5, label='Threshold (-20)')
ax1.axvline(x=np.mean(energies), color='#f39c12', linestyle='-', linewidth=1.5,
            label=f'Mean ({np.mean(energies):.1f})')
ax1.set_xlabel('Free Energy (kcal/mol)')
ax1.set_ylabel('Count')
ax1.set_title('Energy Distribution', fontweight='bold')
ax1.legend(fontsize=8)

# Boxplot by family
gemini_e = [p['energy'] for p in preds if p.get('target_virus_family') == 'geminiviridae']
poty_e = [p['energy'] for p in preds if p.get('target_virus_family') == 'potyviridae']
bp = ax2.boxplot([gemini_e, poty_e], patch_artist=True, widths=0.5)
ax2.set_xticklabels(['Geminiviridae', 'Potyviridae'])
bp['boxes'][0].set_facecolor(COLORS['geminiviridae'])
bp['boxes'][1].set_facecolor(COLORS['potyviridae'])
ax2.set_ylabel('Free Energy (kcal/mol)')
ax2.set_title('Energy by Virus Family', fontweight='bold')
ax2.axhline(y=-20, color='#e74c3c', linestyle='--', linewidth=1, alpha=0.5)

fig.tight_layout()
fig.savefig(out_dir / 'fig2_energy_distribution.png')
plt.close()
print("Figure 2 saved")

# ═══════════════════════════════════════════════════════════════════
# FIGURE 3: Top targeted proteins + matching status
# ═══════════════════════════════════════════════════════════════════
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

# Protein distribution
prots = Counter(p.get('target_protein', 'Unknown') for p in preds)
top_prots = prots.most_common(8)
labels_p = [p[0][:30] for p in top_prots]
values_p = [p[1] for p in top_prots]
colors_p = plt.cm.Greens(np.linspace(0.3, 0.9, len(top_prots)))
bars = ax1.barh(range(len(top_prots)), values_p, color=colors_p[::-1])
ax1.set_yticks(range(len(top_prots)))
ax1.set_yticklabels(labels_p, fontsize=8)
ax1.set_xlabel('Count')
ax1.set_title('Targeted Viral Proteins', fontweight='bold')
for bar, val in zip(bars, values_p):
    ax1.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
             str(val), va='center', fontsize=9)

# Matching status pie
ms = Counter(p.get('matching_status', 'Unknown') for p in preds)
colors_ms = {'Withinmatch': '#2ecc71', 'Outside gene': '#e74c3c', 'Overlapping': '#f39c12'}
wedges, texts, autotexts = ax2.pie(
    ms.values(), labels=ms.keys(), autopct='%1.1f%%',
    colors=[colors_ms.get(k, '#95a5a6') for k in ms.keys()],
    startangle=90,
    explode=tuple(0.05 if k == 'Withinmatch' else 0 for k in ms.keys()))
for t in autotexts:
    t.set_fontsize(9)
ax2.set_title('Matching Status', fontweight='bold')

fig.tight_layout()
fig.savefig(out_dir / 'fig3_proteins_status.png')
plt.close()
print("Figure 3 saved")

# ═══════════════════════════════════════════════════════════════════
# FIGURE 4: miRNA family targeting overview (top families)
# ═══════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 5))

# Group by miRNA family (e.g., miR156, miR159, etc.)
family_counts = Counter()
for p in preds:
    mirid = p['mirna_id']
    # Extract family: ath-miR159a -> miR159
    parts = mirid.split('-')
    if len(parts) >= 2:
        fam = parts[1].replace('a','').replace('b','').replace('c','')
        # Remove -5p/-3p suffix
        fam = fam.split('-')[0]
        family_counts[fam] += 1

top_fams = family_counts.most_common(12)
names = [f[0] for f in top_fams]
counts = [f[1] for f in top_fams]

colors_fam = plt.cm.YlOrRd(np.linspace(0.3, 0.95, len(top_fams)))
bars = ax.bar(range(len(top_fams)), counts, color=colors_fam[::-1])
ax.set_xticks(range(len(top_fams)))
ax.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
ax.set_ylabel('Number of Viral Targets')
ax.set_title('Top miRNA Families Targeting Viruses', fontweight='bold')
for bar, val in zip(bars, counts):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
            str(val), ha='center', fontsize=9, fontweight='bold')

fig.tight_layout()
fig.savefig(out_dir / 'fig4_mirna_families.png')
plt.close()
print("Figure 4 saved")

# ═══════════════════════════════════════════════════════════════════
# FIGURE 5: Dashboard-style summary (4 panels)
# ═══════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(12, 8))
gs = fig.add_gridspec(2, 3, hspace=0.4, wspace=0.35)

# Panel A: Species bar chart
ax_a = fig.add_subplot(gs[0, 0])
sp_counts = Counter(p.get('mirna_species_name', '') for p in preds)
sp_sorted = sorted(sp_counts.items(), key=lambda x: -x[1])
sp_names = [s[0].replace(' ', '\n') for s in sp_sorted]
sp_vals = [s[1] for s in sp_sorted]
ax_a.bar(range(len(sp_sorted)), sp_vals, color=[COLORS.get(s[0], '#95a5a6') for s in sp_sorted])
ax_a.set_xticks(range(len(sp_sorted)))
ax_a.set_xticklabels(sp_names, fontsize=7)
ax_a.set_ylabel('Interactions')
ax_a.set_title('A. By Plant Species', fontweight='bold', fontsize=10)

# Panel B: Energy by species (boxplot)
ax_b = fig.add_subplot(gs[0, 1])
sp_energies = defaultdict(list)
for p in preds:
    sp_energies[p.get('mirna_species_name', '')].append(p['energy'])
sp_names_b = [s for s in SPECIES_ORDER if s in sp_energies]
sp_data = [sp_energies[s] for s in sp_names_b]
bp = ax_b.boxplot(sp_data, patch_artist=True, widths=0.6)
ax_b.set_xticklabels([s.split()[0][:3]+'.' for s in sp_names_b], fontsize=7, rotation=45)
for patch, sp_name in zip(bp['boxes'], sp_names_b):
    patch.set_facecolor(COLORS.get(sp_name, '#95a5a6'))
ax_b.set_ylabel('Free Energy (kcal/mol)')
ax_b.set_title('B. Energy by Species', fontweight='bold', fontsize=10)
ax_b.tick_params(axis='x', rotation=45, labelsize=7)

# Panel C: Identity vs Similarity scatter
ax_c = fig.add_subplot(gs[0, 2])
identities = [p['identity'] for p in preds]
similarities = [p.get('similarity', p['identity']) for p in preds]
ax_c.scatter(identities, similarities, alpha=0.5, c='#2c6e49', s=20)
ax_c.plot([60, 100], [60, 100], '--', color='gray', alpha=0.5, label='Identity = Similarity')
ax_c.set_xlabel('Identity % (WC only)')
ax_c.set_ylabel('Similarity % (WC + Wobble)')
ax_c.set_title('C. Identity vs Similarity', fontweight='bold', fontsize=10)
ax_c.legend(fontsize=7)

# Panel D: Family pie
ax_d = fig.add_subplot(gs[1, 0])
fam_counts = Counter(p.get('target_virus_family', '') for p in preds)
ax_d.pie(fam_counts.values(), labels=['Geminiviridae', 'Potyviridae'],
         autopct='%1.1f%%', colors=[COLORS['geminiviridae'], COLORS['potyviridae']],
         startangle=90, explode=(0.03, 0.03))
ax_d.set_title('D. By Virus Family', fontweight='bold', fontsize=10)

# Panel E: Seed region & mismatch summary
ax_e = fig.add_subplot(gs[1, 1])
seed_ok = sum(1 for p in preds if p['seed_perfect'])
seed_fail = len(preds) - seed_ok
ax_e.bar(['Seed OK', 'Seed Fail'], [seed_ok, seed_fail],
         color=['#2ecc71', '#e74c3c'])
ax_e.set_ylabel('Count')
ax_e.set_title('E. Seed Region (2-8) Status', fontweight='bold', fontsize=10)
for i, (bar, val) in enumerate(zip(ax_e.patches, [seed_ok, seed_fail])):
    ax_e.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
              str(val), ha='center', fontweight='bold')

# Panel F: Mismatch distribution
ax_f = fig.add_subplot(gs[1, 2])
mm_counts = Counter(p['num_mismatches'] for p in preds)
mm_sorted = sorted(mm_counts.items())
ax_f.bar([m[0] for m in mm_sorted], [m[1] for m in mm_sorted],
         color=plt.cm.Reds(np.linspace(0.3, 0.9, len(mm_sorted))))
ax_f.set_xlabel('Number of Mismatches')
ax_f.set_ylabel('Count')
ax_f.set_title('F. Mismatch Distribution', fontweight='bold', fontsize=10)
ax_f.set_xticks([m[0] for m in mm_sorted])

fig.suptitle('PAmiRDB v2 — Prediction Landscape Overview', fontsize=13, fontweight='bold', y=1.01)
fig.savefig(out_dir / 'fig5_dashboard.png', bbox_inches='tight')
plt.close()
print("Figure 5 saved")

print(f"\nAll figures saved to {out_dir}/")
for f in sorted(out_dir.glob('*.png')):
    print(f"  {f.name} ({f.stat().st_size:,} bytes)")
