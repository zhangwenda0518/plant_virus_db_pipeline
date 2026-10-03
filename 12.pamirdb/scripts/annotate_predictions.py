"""
Post-process predictions_v7.json to add gene/protein annotations.
Uses viruses_full_annotated.json (from GenBank CDS parsing).

For each prediction, finds which viral gene is targeted based on
the target_start/target_end position overlap.

Usage:
  python scripts/annotate_predictions.py [predictions_file]

Output:
  data/predictions_v7_annotated.json (enriched with gene info)
"""

import json, sys
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"


def find_target_gene(genes, target_start, target_end):
    """
    Find which feature overlaps with the target position.
    Returns (gene, product, status, category).

    Status:
      within_cds   - target entirely within a CDS/gene
      within_ncr   - target entirely within a non-coding feature (regulatory, stem_loop, etc.)
      overlap_cds  - target partially overlaps CDS
      overlap_ncr  - target partially overlaps non-coding feature
      intergenic   - virus has annotations but target is in unannotated region
      no_annotation - virus has no GB record or no features
    """
    if not genes:
        return None, None, 'no_annotation', ''

    best_cds = None
    best_ncr = None
    best_cds_overlap = 0
    best_ncr_overlap = 0

    for g in genes:
        gs, ge = g['start'], g['end']
        overlap_start = max(gs, target_start or 0)
        overlap_end = min(ge, target_end or 0)
        overlap = max(0, overlap_end - overlap_start + 1)

        cat = g.get('category', 'CDS' if g.get('type') in ('CDS', 'gene', 'mat_peptide') else 'OTHER')

        if cat == 'CDS':
            if overlap > best_cds_overlap:
                best_cds_overlap = overlap
                best_cds = g
        elif cat == 'NCR':
            if overlap > best_ncr_overlap:
                best_ncr_overlap = overlap
                best_ncr = g

    # Determine status
    if best_cds and best_cds_overlap > 0:
        # Check if within or overlapping
        if target_start and target_end and best_cds['start'] <= target_start and best_cds['end'] >= target_end:
            status = 'within_cds'
        else:
            status = 'overlap_cds'
        return best_cds['gene'], best_cds['product'], status, 'CDS'

    if best_ncr and best_ncr_overlap > 0:
        if target_start and target_end and best_ncr['start'] <= target_start and best_ncr['end'] >= target_end:
            status = 'within_ncr'
        else:
            status = 'overlap_ncr'
        return best_ncr['gene'], best_ncr['product'], status, 'NCR'

    # Has annotations but target hits nothing
    return None, None, 'intergenic', ''


def annotate_predictions(pred_file=None, virus_file=None):
    """Annotate predictions with gene/protein info."""
    if pred_file is None:
        pred_file = DATA_DIR / "predictions_v7.json"
    if virus_file is None:
        virus_file = DATA_DIR / "virus_genomes" / "viruses_full_annotated.json"

    print(f"Loading predictions: {pred_file}")
    with open(pred_file) as f:
        preds = json.load(f)

    print(f"Loading virus annotations: {virus_file}")
    with open(virus_file) as f:
        viruses = json.load(f)

    results = preds.get('results', preds if isinstance(preds, list) else [])
    print(f"Predictions to annotate: {len(results)}")

    # Build virus gene lookup
    virus_genes = {}
    for vid, vmeta in viruses.items():
        genes = vmeta.get('genes', [])
        if genes:
            virus_genes[vid] = genes

    print(f"Viruses with gene annotations: {len(virus_genes)}")

    # Annotate each prediction
    annotated = []
    stats = defaultdict(int)
    gene_hits = defaultdict(int)

    for r in results:
        vid = r.get('target_virus_id', '')
        # Try both ways: full acc and stripped version
        genes = virus_genes.get(vid, virus_genes.get(vid.split('.')[0] if '.' in vid else '', []))

        t_start = r.get('target_start', 0)
        t_end = r.get('target_end', 0)
        gene, product, status, category = find_target_gene(genes, t_start, t_end)

        r['target_gene'] = gene or ''
        r['target_product'] = product or ''
        r['targeting_status'] = status
        r['targeting_category'] = category
        stats[status] += 1

        if gene:
            gene_hits[(status, gene, product)] += 1

        annotated.append(r)

    # Update predictions
    if isinstance(preds, dict):
        preds['results'] = annotated
        preds['gene_annotation'] = {
            'viruses_with_genes': len(virus_genes),
            'predictions_with_genes': stats.get('within', 0) + stats.get('overlap', 0),
            'targeting_stats': dict(stats),
        }
    else:
        preds = annotated

    # Save
    out_file = str(pred_file).replace('.json', '_annotated.json')
    with open(out_file, 'w') as f:
        json.dump(preds, f, indent=2)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Gene Annotation Results")
    print(f"{'=' * 60}")
    print(f"  within_cds:      {stats.get('within_cds', 0)}")
    print(f"  overlap_cds:     {stats.get('overlap_cds', 0)}")
    print(f"  within_ncr:      {stats.get('within_ncr', 0)}")
    print(f"  overlap_ncr:     {stats.get('overlap_ncr', 0)}")
    print(f"  intergenic:      {stats.get('intergenic', 0)}")
    print(f"  no_annotation:   {stats.get('no_annotation', 0)}")
    print(f"\n  Top targeted coding proteins:")
    for (status, gene, product), count in sorted(gene_hits.items(), key=lambda x: -x[1])[:15]:
        print(f"    [{status}] {gene}: {product} ({count})")
    print(f"\n  Saved: {out_file}")

    return annotated


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('pred_file', nargs='?', default=None, help='Predictions file to annotate')
    args = p.parse_args()
    annotate_predictions(args.pred_file)
