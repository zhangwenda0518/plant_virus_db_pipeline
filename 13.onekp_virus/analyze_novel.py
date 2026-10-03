#!/usr/bin/env python3
"""
Analyze 1KP virus-host associations: known vs potentially novel.

Classification logic:
  Level 1 - Known: virus found in its named/document host genus or family
  Level 2 - Extended family: virus in new host species but same family as known host
  Level 3 - Extended order: virus in new family but same order/clade as known host  
  Level 4 - Novel: virus in completely unexpected host clade
"""

import pandas as pd
import re
from collections import defaultdict

BASE = r'D:\桌面\C-host_classify\plant_virus_db_pipeline\13.onekp_virus'
ENC = 'utf-16-le'

# Load data
hc = pd.read_csv(f'{BASE}/high_conf.summary.tsv', sep='\t', encoding=ENC, low_memory=False)
all_data = pd.read_csv(f'{BASE}/all_viruses.best.summary.tsv', sep='\t', encoding=ENC, low_memory=False)
links = pd.read_csv(f'{BASE}/onekp_download_links.csv', encoding=ENC, low_memory=False)
samples = pd.read_csv(f'{BASE}/onekp_all_samples.csv', encoding=ENC, low_memory=False)

# Build host mapping
def extract_acc(url):
    if pd.isna(url): return None
    m = re.search(r'/([EDS]RR\d+)/', str(url))
    return m.group(1) if m else None
links['accession'] = links['SRA Download'].apply(extract_acc)
acc_to_code = dict(zip(links['accession'], links['Sample Code']))
code_to_info = {}
for _, r in samples.iterrows():
    code = str(r.get('Sample Code', '')).strip()
    if code:
        code_to_info[code] = {
            'species': str(r.get('Species', '')),
            'clade': str(r.get('Clade', '')),
            'family': str(r.get('Family', '')),
            'order': str(r.get('Order', '')),
        }
acc_to_host = {}
for acc, code in acc_to_code.items():
    if code in code_to_info:
        acc_to_host[acc] = code_to_info[code]

def enrich(df):
    df = df.copy()
    df['host_species'] = df['Sample'].map(lambda x: acc_to_host.get(x, {}).get('species', ''))
    df['host_clade'] = df['Sample'].map(lambda x: acc_to_host.get(x, {}).get('clade', ''))
    df['host_family'] = df['Sample'].map(lambda x: acc_to_host.get(x, {}).get('family', ''))
    df['host_order'] = df['Sample'].map(lambda x: acc_to_host.get(x, {}).get('order', ''))
    df['host_genus'] = df['host_species'].apply(lambda x: x.split()[0] if x else '')
    return df

hc_e = enrich(hc)
all_e = enrich(all_data)

# ── Known host knowledge base ──
# Format: virus_name_lower → {expected_genera, expected_families, notes}
KNOWN_HOSTS = {
    # Viruses named after their host
    'cannabis partiti-like virus': {'genera': ['cannabis'], 'families': ['cannabaceae'], 'note': 'Named after host'},
    'cannabis sativa amalgavirus 1': {'genera': ['cannabis'], 'families': ['cannabaceae'], 'note': 'Named after host'},
    'agave potexvirus 1': {'genera': ['agave'], 'families': ['agavaceae', 'asparagaceae'], 'note': 'Named after host'},
    'agave vitivirus a': {'genera': ['agave'], 'families': ['agavaceae', 'asparagaceae'], 'note': 'Named after host'},
    'agave yellow streak virus jalisco 1': {'genera': ['agave'], 'families': ['agavaceae'], 'note': 'Named after host'},
    'agave yellow streak virus jalisco 2': {'genera': ['agave'], 'families': ['agavaceae'], 'note': 'Named after host'},
    'asclepias syriaca virus 1': {'genera': ['asclepias'], 'families': ['apocynaceae'], 'note': 'Named after host'},
    'asclepias syriaca virus 2': {'genera': ['asclepias'], 'families': ['apocynaceae'], 'note': 'Named after host'},
    'asclepias potyvirus a': {'genera': ['asclepias'], 'families': ['apocynaceae'], 'note': 'Named after host'},
    'passiflora latent virus': {'genera': ['passiflora'], 'families': ['passifloraceae'], 'note': 'Named after host'},
    'verbena latent virus': {'genera': ['verbena'], 'families': ['verbenaceae'], 'note': 'Named after host'},
    'lily mottle virus': {'genera': ['lilium'], 'families': ['liliaceae'], 'note': 'Named after host'},
    'schlumbergera virus x': {'genera': ['schlumbergera'], 'families': ['cactaceae'], 'note': 'Named after host'},
    'cymbidium mosaic virus': {'genera': ['cymbidium'], 'families': ['orchidaceae'], 'note': 'Orchid virus, broad'},
    'narcissus symptomless virus': {'genera': ['narcissus'], 'families': ['amaryllidaceae'], 'note': 'Named after host'},
    'potato virus s': {'genera': ['solanum'], 'families': ['solanaceae'], 'note': 'Broad solanaceous host'},
    'potato virus y': {'genera': ['solanum'], 'families': ['solanaceae'], 'note': 'Very broad host range'},
    'potato virus m': {'genera': ['solanum'], 'families': ['solanaceae'], 'note': 'Solanaceous'},
    'potato virus x': {'genera': ['solanum'], 'families': ['solanaceae'], 'note': 'Broad'},
    'alfalfa-associated picorna-like virus 2': {'genera': ['medicago'], 'families': ['fabaceae'], 'note': 'Named after alfalfa'},
    'beetleweed nepovirus': {'genera': [], 'families': [], 'note': 'Understudied'},
    'hemp virus t': {'genera': ['cannabis'], 'families': ['cannabaceae'], 'note': 'Named after host'},
    'beet cryptic virus 1': {'genera': ['beta'], 'families': ['amaranthaceae'], 'note': 'Beet-associated'},
    'beet capulavirus 1': {'genera': ['beta'], 'families': ['amaranthaceae'], 'note': 'Beet-associated'},
    'beet ringspot virus': {'genera': ['beta'], 'families': ['amaranthaceae'], 'note': 'Beet-associated'},
    'beet pseudoyellows virus': {'genera': ['beta'], 'families': ['amaranthaceae'], 'note': 'Beet-associated'},
    'beet western yellows virus': {'genera': ['beta'], 'families': ['amaranthaceae'], 'note': 'Beet-associated, broad'},
    'beet mild yellowing virus': {'genera': ['beta'], 'families': ['amaranthaceae'], 'note': 'Beet-associated'},
    
    # Broad host range viruses
    'tobacco rattle virus': {'genera': [], 'families': [], 'note': 'Extremely broad host range (>400 species, 50+ families)'},
    'impatiens necrotic spot virus': {'genera': ['impatiens'], 'families': [], 'note': 'Broad host range (orthotospovirus)'},
    'arabis mosaic virus': {'genera': ['arabis'], 'families': [], 'note': 'Broad host range, nematode-transmitted'},
    'cucumber mosaic virus': {'genera': ['cucumis'], 'families': ['cucurbitaceae'], 'note': 'Very broad (>1200 species)'},
    'tomato spotted wilt virus': {'genera': [], 'families': [], 'note': 'Extremely broad (orthotospovirus)'},
    
    # Citrus viroid
    'citrus exocortis yucatan viroid': {'genera': ['citrus'], 'families': ['rutaceae'], 'note': 'Citrus-associated viroid'},
    
    # Fabavirus
    'fabavirus betaviciae': {'genera': ['vicia'], 'families': ['fabaceae'], 'note': 'Fabaceae-associated'},
    
    # Potexvirus  
    'potexvirus alternantherae': {'genera': ['alternanthera'], 'families': ['amaranthaceae'], 'note': 'Named after host genus'},
    
    # Others with limited info
    'aphis glycines virus 1': {'genera': [], 'families': [], 'note': 'Insect virus (aphid), if found in plant = novel'},
    'iresine viroid 1': {'genera': ['iresine'], 'families': ['amaranthaceae'], 'note': 'Named after Iresine (Amaranthaceae)'},
    'varicosavirus lactucae': {'genera': ['lactuca'], 'families': ['asteraceae'], 'note': 'Named after Lactuca'},
    'grapevine asteroid mosaic associated virus': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'grapevine rupestris stem pitting-associated virus': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'grapevine leafroll-associated virus 13': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'grapevine syrah virus 1': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'grapevine virus a': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'grapevine virus l': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'grapevine geminivirus a': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'grapevine fleck virus': {'genera': ['vitis'], 'families': ['vitaceae'], 'note': 'Grapevine'},
    'cherry leaf roll virus': {'genera': ['prunus'], 'families': ['rosaceae'], 'note': 'Broad woody host range'},
    'apple stem grooving virus': {'genera': ['malus'], 'families': ['rosaceae'], 'note': 'Broad host range'},
    'sowbane mosaic virus': {'genera': ['chenopodium'], 'families': ['amaranthaceae'], 'note': 'Chenopodium-associated'},
    'opuntia virus x': {'genera': ['opuntia'], 'families': ['cactaceae'], 'note': 'Cactus virus'},
    'sugarcane mosaic virus': {'genera': ['saccharum'], 'families': ['poaceae'], 'note': 'Poaceae, broad'},
    'maize dwarf mosaic virus': {'genera': ['zea'], 'families': ['poaceae'], 'note': 'Poaceae'},
    'wheat streak mosaic virus': {'genera': ['triticum'], 'families': ['poaceae'], 'note': 'Poaceae'},
    'rice stripe virus': {'genera': ['oryza'], 'families': ['poaceae'], 'note': 'Poaceae'},
    'carnation mottle virus': {'genera': ['dianthus'], 'families': ['caryophyllaceae'], 'note': 'Named after host'},
    'carnation latent virus': {'genera': ['dianthus'], 'families': ['caryophyllaceae'], 'note': 'Named after host'},
}

def classify_pair(virus_lower, host_genus, host_family, host_clade, host_order):
    """Classify a virus-host pair."""
    virus_lower = virus_lower.lower().strip()
    host_genus = host_genus.lower().strip()
    host_family = host_family.lower().strip()
    
    kb = KNOWN_HOSTS.get(virus_lower, {})
    
    if not kb:
        # No knowledge base entry - check if virus name contains host genus
        for part in virus_lower.replace('-', ' ').split():
            if part in host_genus or host_genus in part:
                return 'Known (named)', 'Virus name matches host genus'
        return 'Unknown', 'No host range data available'
    
    note = kb.get('note', '')
    expected_genera = [g.lower() for g in kb.get('genera', [])]
    expected_families = [f.lower() for f in kb.get('families', [])]
    
    # Level 1: Same genus
    if host_genus in expected_genera:
        return 'Known (genus match)', f'Expected host genus. {note}'
    
    # Level 2: Same family
    if host_family in expected_families:
        return 'Extended (same family)', f'New host genus in known family. {note}'
    
    # Level 3: Broad host range viruses
    if 'broad' in note.lower() or 'extremely' in note.lower():
        return 'Known (broad range)', f'Virus with documented broad host range. {note}'
    
    # Level 4: Check if virus name suggests a different family
    virus_words = set(virus_lower.replace('-', ' ').split())
    if expected_genera or expected_families:
        if expected_families:
            return 'Novel (cross-family)', f'Unexpected host family. Expected: {expected_families}. {note}'
        return 'Novel (cross-genus)', f'Unexpected host genus. Expected: {expected_genera}. {note}'
    
    return 'Uncertain', f'Insufficient data. {note}'


# ── Classify all HC pairs ──
results = []
for _, r in hc_e.iterrows():
    virus = r['Adjusted_Species']
    host_sp = r['host_species']
    host_genus = r['host_genus']
    host_fam = r['host_family']
    host_clade = r['host_clade']
    host_order = r['host_order']
    cov = r['Rep_Coverage(%)']
    depth = r['Rep_MeanDepth']
    n_reads = r['Asm_EM_Reads']
    
    if not host_sp:
        continue
    
    category, detail = classify_pair(virus, host_genus, host_fam, host_clade, host_order)
    results.append({
        'virus': virus,
        'host_species': host_sp,
        'host_genus': host_genus,
        'host_family': host_fam,
        'host_clade': host_clade,
        'host_order': host_order,
        'category': category,
        'detail': detail,
        'coverage': cov,
        'depth': depth,
        'reads': n_reads,
    })

df_r = pd.DataFrame(results)

# ── Summary ──
print('=' * 70)
print('1KP VIRUS-HOST ASSOCIATION ANALYSIS')
print('=' * 70)
print(f'Total high-confidence virus-host records: {len(df_r)}')
print(f'Unique virus-host species pairs: {df_r.groupby(["virus","host_species"]).ngroups}')
print(f'Unique viruses: {df_r["virus"].nunique()}')
print(f'Unique host species: {df_r["host_species"].nunique()}')
print()

# Category breakdown
print('─' * 70)
print('CATEGORY BREAKDOWN')
print('─' * 70)
cat_counts = df_r['category'].value_counts()
for cat, n in cat_counts.items():
    pct = n / len(df_r) * 100
    bar = '█' * int(pct / 2)
    print(f'  {cat:30s}  {n:4d}  ({pct:5.1f}%)  {bar}')

print()
print('─' * 70)
print('NOVEL / EXTENDED ASSOCIATIONS')
print('─' * 70)

novel = df_r[df_r['category'].str.contains('Novel|Extended|Uncertain')]
for _, r in novel.iterrows():
    print(f'\n  Virus: {r["virus"]}')
    print(f'  Host:  {r["host_species"]} ({r["host_family"]}, {r["host_clade"]})')
    print(f'  Category: {r["category"]}')
    print(f'  Detail:  {r["detail"]}')
    print(f'  Evidence: cov={r["coverage"]:.1f}%, depth={r["depth"]:.1f}x, reads={r["reads"]:.0f}')

print()
print('─' * 70)
print('NOTABLE FINDINGS')
print('─' * 70)

# Find cross-clade associations
print('\n1. Cross-clade / unexpected host jumps:')
cross = df_r[df_r['category'].str.contains('Novel')]
for _, r in cross.iterrows():
    print(f'   {r["virus"][:50]}')
    print(f'   → {r["host_species"][:45]} | {r["host_family"]} | {r["host_clade"]}')

print('\n2. Most promiscuous viruses (most host species in 1KP):')
promiscuous = df_r.groupby('virus')['host_species'].nunique().sort_values(ascending=False).head(10)
for v, n in promiscuous.items():
    hosts = df_r[df_r['virus'] == v]['host_species'].unique()
    print(f'   {v}: {n} host species')
    for h in hosts[:5]:
        print(f'      - {h}')

print('\n3. Host species with most virus detections:')
host_counts = df_r.groupby('host_species')['virus'].nunique().sort_values(ascending=False).head(10)
for h, n in host_counts.items():
    viruses = df_r[df_r['host_species'] == h]['virus'].unique()
    print(f'   {h}: {n} virus species')
    for v in viruses[:3]:
        print(f'      - {v}')

# Save detailed report
df_r.to_csv(f'{BASE}/virus_host_classification.csv', index=False)
print(f'\nDetailed report saved to virus_host_classification.csv')
