"""
Parse GenBank flat files to extract CDS/gene annotations for all viruses.
Matches to viruses_full.json by accession.

Output: data/virus_gene_annotations.json
  {accession_key: [{gene, product, start, end}, ...]}
"""

import json, re, os
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
GB_DIR = "/opt/plant_virus_db/plant_virus_db_pipeline/13.virus_profile/genbank_records"


def parse_genbank_file(filepath):
    """Parse one GenBank flat file, return (accession, genes_list)."""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return None, []

    # Extract accession
    acc_match = re.search(r'ACCESSION\s+(\S+)', content)
    if not acc_match:
        return None, []
    acc = acc_match.group(1).split('.')[0]  # strip version

    # Extract features section
    features_match = re.search(r'FEATURES\s+Location/Qualifiers(.*?)ORIGIN', content, re.DOTALL)
    if not features_match:
        return acc, []
    features_text = features_match.group(1)

    # Feature type classification
    CODING_TYPES = {'CDS', 'gene'}
    NCR_TYPES = {
        'regulatory', 'stem_loop', 'misc_RNA', 'rep_origin', 'polyA_site',
        'TATA_signal', 'promoter', 'enhancer', 'terminator', 'RBS',
        '5\'UTR', '3\'UTR', 'mRNA', 'exon', 'intron', 'repeat_region',
        'misc_feature', 'misc_difference', 'variation', 'primer_bind',
    }
    ALL_FEAT_TYPES = CODING_TYPES | NCR_TYPES | {'source', 'mat_peptide'}

    # Parse all features
    features = []
    feat_pattern = re.compile(
        r'(?:^|\n)\s{5}(' + '|'.join(ALL_FEAT_TYPES) + r')\s+(\S.*?)\n'
        r'(.*?)(?=\n\s{5}[a-z].*\s+\S|\n\s{5}ORIGIN|\Z)',
        re.DOTALL
    )

    for match in feat_pattern.finditer(features_text):
        feat_type = match.group(1)
        location = match.group(2).strip()
        qualifiers = match.group(3)

        # Parse location
        loc_clean = location.replace('join(', '').replace(')', '').replace('complement(', '')
        loc_simple = re.match(r'<?(\d+)\.\.>?(\d+)', loc_clean)
        if not loc_simple:
            continue
        start = int(loc_simple.group(1))
        end = int(loc_simple.group(2))

        # Extract qualifiers
        prod_match = re.search(r'/product="([^"]+)"', qualifiers)
        product = prod_match.group(1) if prod_match else feat_type

        gene_match = re.search(r'/gene="([^"]+)"', qualifiers)
        if not gene_match:
            gene_match = re.search(r'/locus_tag="([^"]+)"', qualifiers)
        gene = gene_match.group(1) if gene_match else feat_type

        # Extract /note for non-coding features (often contains functional info)
        note_match = re.search(r'/note="([^"]+)"', qualifiers)
        note = note_match.group(1) if note_match else ''

        # Determine category
        if feat_type in CODING_TYPES:
            category = 'CDS'
        elif feat_type in NCR_TYPES:
            category = 'NCR'
        elif feat_type == 'mat_peptide':
            category = 'CDS'  # mature peptide is coding
        else:
            category = 'OTHER'

        features.append({
            "gene": gene,
            "product": product,
            "start": start,
            "end": end,
            "type": feat_type,
            "category": category,
            "note": note,
        })

    # Deduplicate: prefer CDS over gene at same position, prefer CDS over NCR
    priority = {'CDS': 3, 'NCR': 1, 'OTHER': 0}
    seen_positions = {}
    for f in sorted(features, key=lambda x: (priority.get(x['category'], 0), x['start'])):
        pos = (f['start'], f['end'])
        if pos not in seen_positions or priority.get(f['category'], 0) > priority.get(seen_positions[pos].get('category', ''), 0):
            seen_positions[pos] = f

    return acc, list(seen_positions.values())


def build_annotation_db(limit=None):
    """Parse all GB files and build annotation database."""
    anno = defaultdict(list)
    files = sorted(os.listdir(GB_DIR))
    total = len(files)
    matched = 0
    no_cds = 0

    if limit:
        files = files[:limit]

    for i, fname in enumerate(files):
        if not fname.endswith('.gb'):
            continue
        fpath = os.path.join(GB_DIR, fname)
        acc, genes = parse_genbank_file(fpath)
        if acc:
            anno[acc] = genes
            if genes:
                matched += 1
            else:
                no_cds += 1

        if (i + 1) % 500 == 0:
            print(f"  [{i+1}/{total}] parsed, {matched} with CDS, {no_cds} no CDS")

    print(f"\n  Total parsed: {len(anno)}")
    print(f"  With CDS annotations: {matched}")
    print(f"  Without CDS: {no_cds}")
    return anno


def match_to_virus_db(annotations):
    """Match annotations to viruses_full.json."""
    virus_path = DATA_DIR / "virus_genomes" / "viruses_full.json"
    with open(virus_path) as f:
        viruses = json.load(f)

    # For each virus, find matching annotation by accession
    matched = 0
    unmatched = 0
    total_genes = 0

    for vid, vmeta in viruses.items():
        acc = vmeta.get('accession', '')
        key = acc.split('.')[0] if '.' in acc else acc
        genes = annotations.get(key, [])
        if genes:
            vmeta['genes'] = genes
            total_genes += len(genes)
            matched += 1
        else:
            unmatched += 1

    print(f"\n  Total viruses: {len(viruses)}")
    print(f"  Matched to CDS: {matched}")
    print(f"  No CDS found: {unmatched}")
    print(f"  Total gene annotations: {total_genes}")

    # Save enriched virus database
    out_path = DATA_DIR / "virus_genomes" / "viruses_full_annotated.json"
    with open(out_path, 'w') as f:
        json.dump(viruses, f, indent=2)
    print(f"  Saved: {out_path}")

    return viruses


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=None, help='Limit GB files')
    p.add_argument('--server', action='store_true', help='Running on server')
    args = p.parse_args()

    if args.server:
        GB_DIR = "/opt/plant_virus_db/plant_virus_db_pipeline/13.virus_profile/genbank_records"

    print("=" * 60)
    print("  Parsing GenBank records for CDS annotations")
    print(f"  Source: {GB_DIR}")
    print("=" * 60)

    annotations = build_annotation_db(limit=args.limit)
    viruses = match_to_virus_db(annotations)
