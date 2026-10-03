"""
Count total miRNA sequences across all sources.
Logic: intra-species dedup, cross-species kept.
"""
import json, os
from collections import defaultdict

OUTDIR = os.path.dirname(__file__) + "/data"
sp_seqs = defaultdict(set)  # species -> set of unique sequences (uppercase)
source_counts = defaultdict(lambda: defaultdict(int))  # source -> species -> count

def add(species, seq, source):
    """Add a miRNA sequence for a species. Dedup within species by sequence."""
    if species and seq and len(seq) >= 15:
        seq_clean = seq.upper().replace('U','T')  # normalize RNA -> DNA
        if seq_clean not in sp_seqs[species]:
            sp_seqs[species].add(seq_clean)
            source_counts[source][species] += 1

# ============================================================
# 1. plantrg JSON (780 species, 128,925 interactions)
#    Each entry has 'query' = miRNA sequence
# ============================================================
with open(os.path.join(OUTDIR, 'plantrg_mirna_targets.json')) as f:
    plantrg = json.load(f)
for sp, entries in plantrg.items():
    for e in entries:
        add(sp, e.get('query',''), 'plantrg_json')

# ============================================================
# 2. plantrg web FASTA (112 species, 38,416 mature miRNAs)
#    Downloaded from http://plantrg.bio2db.com/static/miRNA/mature/
# ============================================================
with open(os.path.join(OUTDIR, 'plantrg_all_mirna.fa')) as f:
    name, seq, cur_sp = '', '', ''
    for line in f:
        if line.startswith('>'):
            if name and seq and cur_sp:
                add(cur_sp, seq, 'plantrg_fasta')
            name = line[1:].strip().split()[0]
            # Species name is first part of miRNA ID (e.g., Arabidopsis_thaliana-miR156a)
            cur_sp = name.split('-')[0] if '-' in name else ''
            seq = ''
        else:
            seq += line.strip()
    if name and seq and cur_sp:
        add(cur_sp, seq, 'plantrg_fasta')

# ============================================================
# 3. miRBase mature (55 plant species, 11,618 mature miRNAs)
#    3-letter codes mapped to full species names
# ============================================================
CODE_MAP = {
    'ath':'Arabidopsis_thaliana','osa':'Oryza_sativa','sly':'Solanum_lycopersicum',
    'gma':'Glycine_max','zma':'Zea_mays','vvi':'Vitis_vinifera',
    'bdi':'Brachypodium_distachyon','aly':'Arabidopsis_lyrata','csi':'Citrus_sinensis',
    'mtr':'Medicago_truncatula','ppe':'Prunus_persica','sbi':'Sorghum_bicolor',
    'hvu':'Hordeum_vulgare','tae':'Triticum_aestivum','nta':'Nicotiana_tabacum',
    'stu':'Solanum_tuberosum','can':'Capsicum_annuum','cpa':'Carica_papaya',
    'bna':'Brassica_napus','bra':'Brassica_rapa','rco':'Ricinus_communis',
    'mdo':'Malus_domestica','tca':'Theobroma_cacao','ghr':'Gossypium_hirsutum',
    'han':'Helianthus_annuus','lja':'Lotus_japonicus','nbe':'Nicotiana_benthamiana',
    'pab':'Picea_abies','smo':'Selaginella_moellendorffii','ptc':'Populus_trichocarpa',
    'mes':'Manihot_esculenta','lus':'Linum_usitatissimum','cme':'Cucumis_melo',
    'ccr':'Citrus_clementina','cre':'Chlamydomonas_reinhardtii','vca':'Volvox_carteri',
    'pta':'Pinus_taeda','far':'Fragaria_x_ananassa','peu':'Populus_euphratica',
    'sof':'Saccharum_officinarum','ssp':'Salvia_splendens','pic':'Picea_glauca',
    'rgl':'Rhododendron_glaucum','ssl':'Solanum_sisymbriifolium',
    'aau':'Arachis_duranensis','aof':'Asparagus_officinalis','fve':'Fragaria_vesca',
    'hbr':'Hevea_brasiliensis','dpr':'Phoenix_dactylifera','csv':'Cucumis_sativus',
    'egr':'Eucalyptus_grandis','nnu':'Nelumbo_nucifera','ptr':'Populus_trichocarpa',
    'cmo':'Cucurbita_moschata','dcr':'Daucus_carota','pda':'Phoenix_dactylifera',
    'age':'Asparagus_officinalis','bol':'Brassica_oleracea','bvu':'Beta_vulgaris',
    'oer':'Ostreococcus_tauri','hpa':'Hordeum_vulgare',
}

with open(os.path.join(OUTDIR, 'miRBase_plant_mature.fa')) as f:
    name, seq = '', ''
    for line in f:
        if line.startswith('>'):
            if name and seq:
                code = name[:3]
                sp = CODE_MAP.get(code, code)
                add(sp, seq, 'mirbase')
            name = line[1:].strip().split()[0]
            seq = ''
        else:
            seq += line.strip()
    if name and seq:
        code = name[:3]
        sp = CODE_MAP.get(code, code)
        add(sp, seq, 'mirbase')

# ============================================================
# 4. NCBI miRNA precursor sequences (2,415 RefSeq precursors)
#    Species extracted from FASTA header
# ============================================================
import re
ncbi_sp = set()
ncbi_fpath = os.path.join(OUTDIR, 'miRNA_genes.tsv')
if os.path.exists(ncbi_fpath):
    with open(ncbi_fpath, encoding='utf-8-sig') as f:
        next(f)
        for line in f:
            cols = line.strip().split('\t')
            if len(cols) >= 4 and cols[3]:
                ncbi_sp.add(cols[3])

with open(os.path.join(OUTDIR, 'miRNA_precursors.fasta')) as f:
    name, seq, cur_sp = '', '', ''
    for line in f:
        if line.startswith('>'):
            if name and seq and cur_sp:
                add(cur_sp, seq, 'ncbi')
            # Extract species from header: >NR_120837.2 Brassica rapa microRNA...
            header = line[1:].strip()
            # Try species pattern: Genus species (two words with capital first letter)
            m = re.match(r'[^ ]+ ([A-Z][a-z]+ [a-z]+(?:\s+subsp\.?\s+[a-z]+)?)', header)
            if m:
                cur_sp = m.group(1).replace(' ','_')
            else:
                cur_sp = ''
            name = header.split()[0] if header else ''
            seq = ''
        else:
            seq += line.strip()
    if name and seq and cur_sp:
        add(cur_sp, seq, 'ncbi')
    ncbi_sp |= set(source_counts['ncbi'].keys())

# NOTE (2026-10-03 fix): gene-table species without any precursor sequence
# must NOT be registered as (empty) species here — doing so inflated
# total_species from 799 to 837 (38 TSV-only name variants such as
# 'Populus trichocarpa' vs 'Populus_trichocarpa' with zero sequences).
# Species are counted below by non-empty sequence sets only.

# ============================================================
# REPORT
# ============================================================
# Only species that actually contributed >=1 unique sequence count as species.
total_sp = sum(1 for seqs in sp_seqs.values() if seqs)
total_mir = sum(len(seqs) for seqs in sp_seqs.values())

print("=" * 60)
print("FINAL miRNA DATABASE STATISTICS")
print("=" * 60)
print(f"Total species:                     {total_sp}")
print(f"Total miRNAs (intra-species dedup): {total_mir:,}")
print()
print("Source breakdown:")
print(f"  plantrg JSON (780 species):  {sum(source_counts['plantrg_json'].values()):>8,}")
print(f"  plantrg FASTA (112 species): {sum(source_counts['plantrg_fasta'].values()):>8,}")
print(f"  miRBase (55 species codes):  {sum(source_counts['mirbase'].values()):>8,}")
print(f"  NCBI precursors ({len(source_counts['ncbi'])} species): {sum(source_counts['ncbi'].values()):>8,}")
print()

# Species per source
ptrg_sp = set(source_counts['plantrg_json'].keys()) | set(source_counts['plantrg_fasta'].keys())
mir_sp = set(source_counts['mirbase'].keys())
ncbi_seq_sp = set(source_counts['ncbi'].keys())   # species with precursor sequences (11)
print(f"Species by source:")
print(f"  plantrg: {len(ptrg_sp)}")
print(f"  miRBase: {len(mir_sp)}")
print(f"  NCBI:    {len(ncbi_seq_sp)} with sequences "
      f"(+{len(ncbi_sp - ncbi_seq_sp)} gene-table-only species, no precursor sequences)")
print(f"  Combined: {len(ptrg_sp | mir_sp | ncbi_seq_sp)}")
print()

# Verification checks
# 1. Spot check: Arabidopsis should have ~400+ miRNAs
ath_count = len(sp_seqs.get('Arabidopsis_thaliana', set()))
print(f"Spot check - Arabidopsis thaliana: {ath_count} miRNAs (expected ~400+)")

# 2. Spot check: Rice should have ~700+
osa_count = len(sp_seqs.get('Oryza_sativa', set()))
print(f"Spot check - Oryza sativa: {osa_count} miRNAs (expected ~700+)")

# 3. Check no cross-species dedup happened
ath_seqs = sp_seqs.get('Arabidopsis_thaliana', set())
osa_seqs = sp_seqs.get('Oryza_sativa', set())
overlap = ath_seqs & osa_seqs
print(f"Cross-species sequence overlap (ath vs osa): {len(overlap)} shared sequences")
if overlap:
    print(f"  Example: {list(overlap)[0][:30]}")

# Save summary
summary = {
    'total_species': total_sp,
    'total_miRNAs': total_mir,
    'sources': {
        'plantrg_json': sum(source_counts['plantrg_json'].values()),
        'plantrg_fasta': sum(source_counts['plantrg_fasta'].values()),
        'mirbase': sum(source_counts['mirbase'].values()),
        'ncbi': sum(source_counts['ncbi'].values())
    },
    'species_by_source': {
        'plantrg': len(ptrg_sp),
        'mirbase': len(mir_sp),
        'ncbi': len(ncbi_seq_sp),
        'ncbi_gene_records': len(ncbi_sp),
        'combined': len(ptrg_sp | mir_sp | ncbi_seq_sp)
    },
    'top_species': sorted(
        [(sp, len(seqs)) for sp, seqs in sp_seqs.items()],
        key=lambda x: -x[1]
    )[:30]
}

with open(os.path.join(OUTDIR, 'miRNA_final_stats.json'), 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"\nSummary saved to miRNA_final_stats.json")
