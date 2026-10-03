#!/usr/bin/env python3
"""
Full analysis: 1KP virus-host pairs vs PlantVirusDB known host ranges.
Uses Plant_Virus_Full.Info.tsv as ground truth for documented host associations.
"""

import pandas as pd
import re
import os
from collections import defaultdict

BASE = r'D:\桌面\C-host_classify\plant_virus_db_pipeline\13.onekp_virus'
FULL_INFO = r'D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data\Plant_Virus_Full.Info.tsv'
ENC = 'utf-16-le'

print('Loading 1KP data...')
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

# ── Load PlantVirusDB Full Info (host knowledge base) ──
print('Loading PlantVirusDB Full Info (47MB, this may take a minute)...')
full = pd.read_csv(FULL_INFO, sep='\t', low_memory=False,
                   usecols=['Species_NCBI', 'Species_ICTV', 'Host', 'Family'])
print(f'  Loaded: {len(full):,} records')

# Build per-species host knowledge
# Normalize species names
def norm_sp(s):
    if pd.isna(s): return ''
    return str(s).strip().lower()

full['sp_norm'] = full['Species_NCBI'].fillna('').apply(norm_sp)
full_ictv = full['Species_ICTV'].fillna('').apply(norm_sp)

# For each virus species, collect all known hosts
species_known_hosts = defaultdict(set)  # virus_species → set of host names
species_known_families = defaultdict(set)

for _, r in full.iterrows():
    sp = r['sp_norm']
    if not sp or sp == 'unknown':
        sp = norm_sp(r['Species_ICTV']) if pd.notna(r['Species_ICTV']) else ''
        if not sp or sp == 'unknown':
            continue
    host = str(r['Host']).strip() if pd.notna(r['Host']) else ''
    if host and host.lower() != 'unknown' and host.lower() != 'unidentified':
        species_known_hosts[sp].add(host.lower())
    fam = str(r['Family']).strip() if pd.notna(r['Family']) else ''
    if fam:
        species_known_families[sp].add(fam.lower())

print(f'  {len(species_known_hosts)} virus species with host data')

# ── Matching function ──
def match_virus_to_known(virus_name):
    """Try to match 1KP virus name to PlantVirusDB species."""
    v = virus_name.lower().strip()
    # Direct match
    if v in species_known_hosts:
        return v, species_known_hosts[v]
    # Try ICTV name variants
    for k in species_known_hosts:
        if v in k or k in v:
            return k, species_known_hosts[k]
    # Try without year/suffix
    base = re.sub(r'\s+\d+$', '', v)
    for k in species_known_hosts:
        if base in k:
            return k, species_known_hosts[k]
    return None, set()

# ── Classify each 1KP detection ──
print('Classifying virus-host pairs...')
results = []
unmatched_viruses = set()

for _, r in hc_e.iterrows():
    virus = r['Adjusted_Species']
    host_sp = str(r['host_species']).lower()
    host_genus = str(r['host_genus']).lower()
    host_fam = str(r['host_family']).lower()
    host_clade = str(r['host_clade'])
    
    if not host_sp:
        continue
    
    matched_name, known_hosts = match_virus_to_known(virus)
    
    if not known_hosts:
        unmatched_viruses.add(virus)
        category = 'Unknown'
        detail = 'No host data in PlantVirusDB'
        evidence_hosts = []
    else:
        # Check if this host (or genus/family) appears in known hosts
        host_matched = False
        genus_matched = False
        family_matched = False
        evidence_hosts = []
        
        for kh in known_hosts:
            if host_sp in kh or kh in host_sp:
                host_matched = True
                evidence_hosts.append(f'species:{kh}')
                break
        
        if not host_matched:
            for kh in known_hosts:
                if host_genus and host_genus in kh:
                    genus_matched = True
                    evidence_hosts.append(f'genus:{kh}')
                    break
        
        if not host_matched and not genus_matched:
            # Check if the virus family matches host plant family - but that's not host data
            # Just check known host families
            for kh in known_hosts:
                words = kh.split()
                for w in words:
                    if len(w) > 3 and w in host_fam:
                        family_matched = True
                        evidence_hosts.append(f'family_hint:{kh}')
                        break
                if family_matched:
                    break
        
        if host_matched:
            category = 'Known (host match)'
            detail = f'Host documented in PlantVirusDB. DB species: {matched_name}'
        elif genus_matched:
            category = 'Extended (same genus)'
            detail = f'New host species, same genus as known host. DB species: {matched_name}'
        elif family_matched:
            category = 'Extended (same family)'
            detail = f'New host genus in known host family. DB species: {matched_name}'
        else:
            category = 'Novel association'
            detail = f'Host not in known range. DB species: {matched_name}. Known hosts: {list(known_hosts)[:5]}'
    
    results.append({
        'virus': virus,
        'host_species': r['host_species'],
        'host_genus': r['host_genus'],
        'host_family': r['host_family'],
        'host_clade': host_clade,
        'host_order': r['host_order'],
        'category': category,
        'detail': detail,
        'db_matched_name': matched_name or '',
        'known_hosts_sample': ', '.join(evidence_hosts[:5]),
        'coverage': r['Rep_Coverage(%)'],
        'depth': r['Rep_MeanDepth'],
        'reads': r['Asm_EM_Reads'],
        'tpm': r['Asm_TPM'],
    })

df_r = pd.DataFrame(results)

# ── Report ──
print()
print('=' * 75)
print(' 1KP vs PlantVirusDB FULL INFO — Association Analysis')
print('=' * 75)
print(f' Total HC records analyzed: {len(df_r)}')
print(f' Unique virus species detected: {df_r["virus"].nunique()}')
print(f' Unique host species: {df_r["host_species"].nunique()}')
print(f' Unique virus-host pairs: {df_r.groupby(["virus","host_species"]).ngroups}')
print()

# Category breakdown
print('─' * 75)
print(' CATEGORY BREAKDOWN')
print('─' * 75)
cat_counts = df_r['category'].value_counts()
for cat, n in cat_counts.items():
    pct = n / len(df_r) * 100
    bar = '█' * int(pct)
    print(f'  {cat:35s}  {n:4d}  ({pct:5.1f}%)  {bar}')

# Known vs Novel summary
known = cat_counts.get('Known (host match)', 0)
extended = cat_counts.get('Extended (same genus)', 0) + cat_counts.get('Extended (same family)', 0)
novel = cat_counts.get('Novel association', 0)
unknown = cat_counts.get('Unknown', 0)
print(f'\n  📗 Known associations:        {known} ({known/len(df_r)*100:.1f}%)')
print(f'  📙 Extended host range:        {extended} ({extended/len(df_r)*100:.1f}%)')
print(f'  📕 Potentially novel:          {novel} ({novel/len(df_r)*100:.1f}%)')
print(f'  📓 No DB host data available:  {unknown} ({unknown/len(df_r)*100:.1f}%)')

# ── Novel associations detail ──
print()
print('─' * 75)
print(' POTENTIALLY NOVEL ASSOCIATIONS')
print('─' * 75)
novel_df = df_r[df_r['category'] == 'Novel association'].sort_values('depth', ascending=False)
if len(novel_df) == 0:
    print('  None found — all HC detections match known host ranges!')
else:
    for _, r in novel_df.iterrows():
        print(f'\n  🦠 {r["virus"]}')
        print(f'     Host: {r["host_species"]} ({r["host_family"]}, {r["host_clade"]})')
        print(f'     Evidence: cov={r["coverage"]:.1f}% | depth={r["depth"]:.1f}x | reads={r["reads"]:.0f}')
        print(f'     DB matched: {r["db_matched_name"]}')
        print(f'     Known hosts (sample): {r["known_hosts_sample"][:200]}')

# Extended associations
print()
print('─' * 75)
print(' EXTENDED HOST RANGE (new species/genus in known family)')
print('─' * 75)
ext_df = df_r[df_r['category'].str.contains('Extended')].sort_values('depth', ascending=False)
for _, r in ext_df.iterrows():
    print(f'\n  🦠 {r["virus"]}')
    print(f'     Host: {r["host_species"]} ({r["host_family"]})')
    print(f'     Category: {r["category"]}')
    print(f'     Evidence: cov={r["coverage"]:.1f}% | depth={r["depth"]:.1f}x | reads={r["reads"]:.0f}')

# Unmatched viruses
print()
print('─' * 75)
print(' VIRUSES WITH NO DB HOST DATA (Unknown category)')
print('─' * 75)
unk_df = df_r[df_r['category'] == 'Unknown']
unk_viruses = unk_df['virus'].unique()
print(f'  {len(unk_viruses)} virus species have no host data in PlantVirusDB:')
for v in sorted(unk_viruses):
    hosts = unk_df[unk_df['virus'] == v]['host_species'].unique()
    print(f'  🦠 {v}')
    for h in hosts:
        print(f'     → {h}')

# Top hosts by virus diversity
print()
print('─' * 75)
print(' SUPER-SPREADER HOSTS (most virus species detected)')
print('─' * 75)
host_div = df_r.groupby('host_species').agg(
    n_viruses=('virus', 'nunique'),
    n_categories=('category', lambda x: x.nunique()),
).sort_values('n_viruses', ascending=False).head(10)
for h, row in host_div.iterrows():
    viruses = df_r[df_r['host_species'] == h]['virus'].unique()
    cats = df_r[df_r['host_species'] == h]['category'].unique()
    print(f'  🌿 {h} — {int(row["n_viruses"])} virus species')
    for v in viruses:
        cat = df_r[(df_r['host_species'] == h) & (df_r['virus'] == v)]['category'].iloc[0]
        print(f'     🦠 {v} [{cat}]')

# Save
df_r.to_csv(f'{BASE}/virus_host_full_analysis.csv', index=False)
print(f'\nDetailed report saved to virus_host_full_analysis.csv')
