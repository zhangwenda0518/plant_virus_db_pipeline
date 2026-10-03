"""
Rebuild NLR panel from RefPlantNLR Table S1 + InterPro domain descriptions.
Clean display with full metadata.

Usage:
  python build_nlr_panel.py \
      --xlsx <Table_S1_RefPlantNLR_v.20200528_415_Description.xlsx> \
      --ipr-dir <dir with 20200423_InterPro_79.0_{Pfam,InterPro,CDD}.tsv>

Both inputs are required to exist (no machine-specific absolute paths anymore);
defaults are repo-relative under data/ and can be overridden on the command line.
"""
import openpyxl, json, os, glob, argparse, sys

OUTDIR = os.path.dirname(__file__) + "/data"

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--xlsx",
                default=os.path.join(OUTDIR, "Table_S1_RefPlantNLR_v.20200528_415_Description.xlsx"),
                help="RefPlantNLR Table S1 xlsx (from Zenodo 3936022)")
ap.add_argument("--ipr-dir",
                default=os.path.join(OUTDIR, "interpro_description"),
                help="Directory containing 20200423_InterPro_79.0_{Pfam,InterPro,CDD}.tsv")
args = ap.parse_args()

# 1. Parse RefPlantNLR Table S1
fpath = args.xlsx
if not os.path.exists(fpath):
    sys.exit(f"ERROR: RefPlantNLR Table S1 xlsx not found: {fpath}\n"
             f"       Download Table_S1 from Zenodo 3936022 and pass --xlsx <path>.")
wb = openpyxl.load_workbook(fpath, read_only=True)
ws = wb.active

def safe_int(v):
    try: return int(str(v).replace('*','').replace('>','').replace('<',''))
    except: return 0

nlr_genes = []
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0: continue
    if not row[0]: continue
    rid = str(row[0]).strip()
    other_id = str(row[1] or '').strip()
    genpept = str(row[2] or '').strip()
    cds = str(row[3] or '').strip()
    locus = str(row[4] or '').strip()
    subclass = str(row[5] or '').strip()
    structure = str(row[6] or '').strip()
    exons = safe_int(row[7])
    length_aa = safe_int(row[8])
    host = str(row[9] or '').strip()

    # Domain type from subclass
    if 'TNL' in structure or 'TNLO' in structure or structure.startswith('TN'):
        dt = 'TNL'
    elif 'RNL' in structure:
        dt = 'RNL'
    elif 'CNL' in structure or 'CNLO' in structure or 'CONL' in structure or 'CNNL' in structure:
        dt = 'CNL'
    else:
        dt = 'NLR'

    nlr_genes.append({
        'gene_id': rid,
        'other_id': other_id,
        'genpept': genpept,
        'cds': cds,
        'locus': locus,
        'subclass': subclass,
        'structure': structure,
        'exons': exons,
        'length_aa': length_aa,
        'host': host,
        'domain_type': dt,
        'validated': 'V',
    })

wb.close()
print(f'RefPlantNLR: {len(nlr_genes)} genes')

# 2. Load InterPro Pfam descriptions for domain annotation
pfam_desc = {}
ipr_desc = {}
ip_dir = args.ipr_dir
_IPR_FILES = ('20200423_InterPro_79.0_Pfam.tsv',
              '20200423_InterPro_79.0_InterPro.tsv',
              '20200423_InterPro_79.0_CDD.tsv')
_missing = [f for f in _IPR_FILES if not os.path.exists(os.path.join(ip_dir, f))]
if _missing:
    sys.exit("ERROR: missing InterPro description file(s) under %s:\n  %s\n"
             "       Pass --ipr-dir <dir> (files ship with the RefPlantNLR Zenodo 3936022 package)."
             % (ip_dir, "\n  ".join(_missing)))

# Pfam
with open(os.path.join(ip_dir, '20200423_InterPro_79.0_Pfam.tsv'), encoding='utf-8') as f:
    next(f)
    for line in f:
        cols = line.strip().split('\t')
        if len(cols) >= 2:
            pfam_desc[cols[0]] = cols[1]

# InterPro
with open(os.path.join(ip_dir, '20200423_InterPro_79.0_InterPro.tsv'), encoding='utf-8') as f:
    next(f)
    for line in f:
        cols = line.strip().split('\t')
        if len(cols) >= 3:
            ipr_desc[cols[0]] = cols[2]

# CDD
cdd_desc = {}
with open(os.path.join(ip_dir, '20200423_InterPro_79.0_CDD.tsv'), encoding='utf-8') as f:
    next(f)
    for line in f:
        cols = line.strip().split('\t')
        if len(cols) >= 2:
            cdd_desc[cols[0]] = cols[1]

print(f'Pfam entries: {len(pfam_desc)}, IPR entries: {len(ipr_desc)}, CDD entries: {len(cdd_desc)}')

# 3. Build NLR domain architecture diagrams with proper names
# Key NLR domains with Pfam accessions
DOMAINS = {
    'TIR': {'pfam': 'PF01582', 'ipr': 'IPR000157', 'desc': 'TIR domain'},
    'NB-ARC': {'pfam': 'PF00931', 'ipr': 'IPR002182', 'desc': 'NB-ARC domain'},
    'LRR': {'pfam': 'PF13855', 'ipr': 'IPR032675', 'desc': 'Leucine-rich repeat'},
    'RPW8': {'pfam': 'PF05659', 'ipr': 'IPR008808', 'desc': 'RPW8 domain'},
    'CC': {'pfam': 'PF18052', 'ipr': 'IPR041118', 'desc': 'Coiled-coil domain'},
    'NBS': {'pfam': 'PF00931', 'ipr': 'IPR002182', 'desc': 'Nucleotide-binding site'},
}

# 4. Save processed data
nlr_data = {'genes': nlr_genes, 'domains': DOMAINS, 'stats': {}}

# Stats
from collections import Counter
nlr_data['stats']['total'] = len(nlr_genes)
nlr_data['stats']['species'] = len(set(g['host'] for g in nlr_genes))
nlr_data['stats']['domain_types'] = dict(Counter(g['domain_type'] for g in nlr_genes))
nlr_data['stats']['top_species'] = [{'species': sp, 'count': cnt}
    for sp, cnt in Counter(g['host'] for g in nlr_genes).most_common(15)]
nlr_data['stats']['avg_length'] = sum(g['length_aa'] for g in nlr_genes) // len(nlr_genes)

with open(os.path.join(OUTDIR, 'refplant_nlr_data.json'), 'w', encoding='utf-8') as f:
    json.dump(nlr_data, f, ensure_ascii=False, indent=2)

print(f'Saved refplant_nlr_data.json')
print(f'Stats: {nlr_data["stats"]}')
