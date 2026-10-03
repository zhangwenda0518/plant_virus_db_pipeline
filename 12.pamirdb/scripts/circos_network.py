"""
PAmiRDB v3 — Circos-style miRNA-Virus regulatory network.

Generates a circular network diagram showing:
  - Outer ring: miRNAs grouped by plant species
  - Inner ring: Viruses grouped by family
  - Connecting ribbons: predicted miRNA-virus interactions
  - Color intensity by consensus level

References from literature that use Circos for miRNA-virus networks:
  - Cassava mes-miRNA-ICMV network (PMID: 36851701)
  - Cotton ghr-miRNA-CLCuKoV network (PMID: 40143327)
"""

import json
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, str(Path(__file__).parent))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

DATA_DIR = Path(__file__).parent.parent / "data"
OUT_DIR = Path(__file__).parent.parent / "figures"

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 7,
    'figure.dpi': 150,
    'savefig.dpi': 150,
    'savefig.bbox': 'tight',
})


def generate_circos_network(predictions_file: str = None,
                             output_file: str = None):
    """
    Generate a Circos-style regulatory network diagram.
    """
    if predictions_file is None:
        predictions_file = DATA_DIR / "predictions.json"
    if output_file is None:
        output_file = OUT_DIR / "circos_network.png"
    
    with open(predictions_file) as f:
        preds = json.load(f)
    
    # Organize data
    species_colors = {
        'ath': '#2ecc71', 'gma': '#27ae60', 'osa': '#1abc9c',
        'sbi': '#16a085', 'sly': '#e74c3c', 'vvi': '#9b59b6', 'zma': '#f39c12',
    }
    virus_colors = {
        'geminiviridae': '#3498db', 'potyviridae': '#e67e22',
    }
    
    # Build nodes
    mirna_nodes = defaultdict(list)
    for p in preds:
        sp = p.get('mirna_species', p.get('mirna_species_code', ''))
        mirna_nodes[sp].append(p['mirna_id'])
    
    virus_nodes = defaultdict(list)
    for p in preds:
        vid = p.get('target_virus_id', p.get('virus_id', ''))
        vname = p.get('target_virus_name', p.get('virus_name', ''))
        vfam = p.get('target_virus_family', p.get('virus_family', ''))
        virus_nodes[vid] = {"name": vname, "family": vfam, "targets": []}
    
    # Count targets per virus
    for p in preds:
        vid = p.get('target_virus_id', p.get('virus_id', ''))
        if vid in virus_nodes:
            virus_nodes[vid]["targets"].append(p['mirna_id'])
    
    # ── Create figure ───────────────────────────────────────────
    fig = plt.figure(figsize=(14, 12))
    
    # Panel layout
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
    
    # ── Panel A: Chord diagram (simplified Circos) ──────────────
    ax_chord = fig.add_subplot(gs[0, 0])
    _draw_chord_diagram(ax_chord, preds, species_colors, virus_colors)
    
    # ── Panel B: Species-Virus bipartite network ────────────────
    ax_bip = fig.add_subplot(gs[0, 1])
    _draw_bipartite_network(ax_bip, preds, species_colors, virus_colors)
    
    # ── Panel C: Consensus-level chord ─────────────────────────
    ax_cons = fig.add_subplot(gs[1, 0])
    _draw_consensus_chart(ax_cons, preds)
    
    # ── Panel D: Legend & summary ──────────────────────────────
    ax_leg = fig.add_subplot(gs[1, 1])
    _draw_legend_panel(ax_leg, preds, species_colors, virus_colors)
    
    fig.suptitle('PAmiRDB v3 — miRNA-Virus Regulatory Network', 
                 fontsize=14, fontweight='bold', y=1.01)
    fig.savefig(output_file, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"Circos network saved to {output_file}")


def _draw_chord_diagram(ax, preds, species_colors, virus_colors):
    """Draw a simplified chord diagram."""
    # Get species and virus counts
    sp_counts = defaultdict(int)
    v_counts = defaultdict(int)
    edges = []
    
    for p in preds:
        sp = p.get('mirna_species', p.get('mirna_species_code', ''))
        vf = p.get('target_virus_family', p.get('virus_family', ''))
        sp_counts[sp] += 1
        v_counts[vf] += 1
        edges.append((sp, vf))
    
    # Draw as a stacked bar chart (simplified chord)
    species_list = sorted(sp_counts.keys())
    families = sorted(v_counts.keys())
    
    # Create matrix
    matrix = np.zeros((len(species_list), len(families)))
    for sp, vf in edges:
        i = species_list.index(sp)
        j = families.index(vf)
        matrix[i, j] += 1
    
    # Normalize rows
    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    matrix_norm = matrix / row_sums
    
    # Draw stacked bars
    x = np.arange(len(species_list))
    bottom = np.zeros(len(species_list))
    
    for j, fam in enumerate(families):
        bars = ax.bar(x, matrix_norm[:, j], bottom=bottom,
                      color=virus_colors.get(fam, '#888'),
                      edgecolor='white', linewidth=1, label=fam.capitalize())
        # Add count labels
        for i, bar in enumerate(bars):
            if matrix[i, j] > 0:
                ax.text(bar.get_x() + bar.get_width()/2,
                        bar.get_y() + bar.get_height()/2,
                        str(int(matrix[i, j])),
                        ha='center', va='center', fontsize=6, fontweight='bold')
        bottom += matrix_norm[:, j]
    
    ax.set_xticks(x)
    ax.set_xticklabels([s.upper() for s in species_list], fontsize=7, rotation=45, ha='right')
    ax.set_ylabel('Proportion of Interactions')
    ax.set_title('A. miRNA-Virus Family Chord (Normalized)', fontweight='bold', fontsize=10)
    ax.legend(fontsize=6, loc='upper right')
    ax.set_ylim(0, 1.1)


def _draw_bipartite_network(ax, preds, species_colors, virus_colors):
    """Draw a bipartite network of miRNA species -> virus."""
    # Build adjacency
    sp_virus = defaultdict(lambda: defaultdict(int))
    for p in preds:
        sp = p.get('mirna_species_name', p.get('species_name', ''))
        vname = p.get('target_virus_name', p.get('virus_name', ''))
        key = vname[:25]
        sp_virus[sp][key] += 1
    
    species_list = sorted(sp_virus.keys())
    virus_list = sorted(set(
        v for sp_data in sp_virus.values() for v in sp_data.keys()
    ))
    
    # Matrix for heatmap
    matrix = np.zeros((len(species_list), len(virus_list)))
    for i, sp in enumerate(species_list):
        for j, v in enumerate(virus_list):
            matrix[i, j] = sp_virus[sp].get(v, 0)
    
    im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
    
    ax.set_xticks(range(len(virus_list)))
    ax.set_xticklabels(virus_list, rotation=45, ha='right', fontsize=6)
    ax.set_yticks(range(len(species_list)))
    ax.set_yticklabels([s[:25] for s in species_list], fontsize=7)
    
    # Add values in cells
    for i in range(len(species_list)):
        for j in range(len(virus_list)):
            val = int(matrix[i, j])
            if val > 0:
                color = 'white' if val >= 3 else 'black'
                ax.text(j, i, str(val), ha='center', va='center',
                        fontsize=7, fontweight='bold', color=color)
    
    ax.set_title('B. Species-Virus Interaction Matrix', fontweight='bold', fontsize=10)
    plt.colorbar(im, ax=ax, shrink=0.8).set_label('Count', fontsize=7)


def _draw_consensus_chart(ax, preds):
    """Draw consensus-level distribution."""
    # Group by consensus level
    levels = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    
    for p in preds:
        level = p.get('consensus_level', 'LOW')
        levels[level] = levels.get(level, 0) + 1
    
    # If consensus data exists, use it; otherwise estimate
    if sum(levels.values()) == 0:
        # Estimate from miRanda data (default: LOW since only 1 tool)
        levels['LOW'] = len(preds)
    
    colors_cons = {'HIGH': '#2ecc71', 'MEDIUM': '#f39c12', 'LOW': '#e74c3c'}
    labels = list(levels.keys())
    values = list(levels.values())
    colors = [colors_cons.get(l, '#888') for l in labels]
    
    wedges, texts, autotexts = ax.pie(
        values, labels=[f'{l}\n({v})' for l, v in zip(labels, values)],
        colors=colors, autopct='%1.1f%%', startangle=90,
        explode=tuple(0.05 if l == 'HIGH' else 0 for l in labels)
    )
    for t in autotexts:
        t.set_fontsize(8)
    ax.set_title('C. Consensus Level Distribution', fontweight='bold', fontsize=10)


def _draw_legend_panel(ax, preds, species_colors, virus_colors):
    """Draw legend and summary statistics."""
    ax.axis('off')
    
    # Summary stats
    total = len(preds)
    n_species = len(set(p.get('mirna_species_name', p.get('species_name', '')) for p in preds))
    n_viruses = len(set(p.get('target_virus_name', p.get('virus_name', '')) for p in preds))
    
    # Find top miRNA family
    from collections import Counter
    families = Counter()
    for p in preds:
        mirid = p.get('mirna_id', '')
        parts = mirid.split('-')
        if len(parts) >= 2:
            fam = parts[1].replace('a','').replace('b','').split('-')[0]
            families[fam] += 1
    top_fam = families.most_common(3)
    
    text = (
        f"PAmiRDB v3 Network Summary\n"
        f"{'='*35}\n\n"
        f"Total Interactions: {total}\n"
        f"Plant Species: {n_species}\n"
        f"Virus Genomes: {n_viruses}\n\n"
        f"Top Antiviral miRNA Families:\n"
    )
    for fam, cnt in top_fam:
        text += f"  {fam}: {cnt} targets\n"
    
    text += f"\nSpecies:\n"
    for code, color in species_colors.items():
        text += f"  {code.upper()}  "
    
    text += f"\n\nVirus Families:\n"
    for fam, color in virus_colors.items():
        text += f"  {fam.capitalize()}\n"
    
    text += f"\nConsensus Levels:\n"
    text += f"  *** HIGH  (3/3 tools) = Most reliable\n"
    text += f"  **  MEDIUM (2/3 tools) = Probable\n"
    text += f"  *   LOW    (1/3 tools) = Needs validation\n"
    
    ax.text(0.05, 0.95, text, transform=ax.transAxes,
            fontsize=8, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='#f8f9fa', alpha=0.8))


if __name__ == '__main__':
    generate_circos_network()
