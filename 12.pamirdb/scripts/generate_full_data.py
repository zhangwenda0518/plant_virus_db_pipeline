"""
Generate plant_mirnas_full.json and viruses_full.{json,fasta}
from the project's existing data sources.

Inputs:
  miRNAs:  11.antiviral_genes/data/  (837 species, 83,166 miRNAs)
  Viruses:  docs/data/Plant_Virus.complete_ref.* (5,773 complete genomes)

Outputs:
  12.pamirdb/data/mirna/plant_mirnas_full.json
  12.pamirdb/data/virus_genomes/viruses_full.json
  12.pamirdb/data/virus_genomes/viruses_full.fasta

Usage:
  python scripts/generate_full_data.py
  python scripts/generate_full_data.py --mirna-only
  python scripts/generate_full_data.py --virus-only
"""

import json, os, re, sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
MIRNA_SRC = Path(__file__).parent.parent.parent / "11.antiviral_genes" / "data"
VIRUS_SRC = Path(__file__).parent.parent.parent / "docs" / "data"


# ============================================================
# PART 1: miRNA — generate plant_mirnas_full.json
# ============================================================

def generate_mirna_full():
    """Rebuild miRNA database using count_mirna.py logic and output as JSON."""
    sp_seqs = defaultdict(set)  # species -> set(sequences)
    id_map = defaultdict(dict)  # species -> {sequence: id}
    # 2026-10-03: the prediction query set must contain mature miRNAs, not
    # precursor transcripts.  Exclusions (counted into the stats file):
    #   - NCBI NR_* records (RefSeq precursor transcripts, not mature miRNAs)
    #   - sequences longer than MAX_MATURE_LEN (precursors / fragmented records)
    MAX_MATURE_LEN = 50
    excluded = {'excluded_precursors': 0, 'excluded_long': 0}

    def add(species, seq, source, mirna_id=None):
        if species and seq and len(seq) >= 15:
            seq_clean = seq.upper().replace('U', 'T')
            is_precursor = bool(mirna_id) and str(mirna_id).upper().startswith('NR_')
            is_long = len(seq_clean) > MAX_MATURE_LEN
            # Counters are raw record counts (the two conditions overlap on
            # NCBI NR_* records, which are also the long ones).
            if is_precursor:
                excluded['excluded_precursors'] += 1
            if is_long:
                excluded['excluded_long'] += 1
            if is_precursor or is_long:
                return
            if seq_clean not in sp_seqs[species]:
                sp_seqs[species].add(seq_clean)
                id_map[species][seq_clean] = mirna_id or f"{species}_miRNA_{len(sp_seqs[species]):05d}"

    # 1. plantrg JSON (780 species)
    print("[1/4] Loading plantrg_mirna_targets.json...")
    with open(MIRNA_SRC / "plantrg_mirna_targets.json") as f:
        plantrg = json.load(f)
    for sp, entries in plantrg.items():
        for e in entries:
            add(sp, e.get('query', ''), 'plantrg_json', mirna_id=e.get('name', ''))

    # 2. plantrg FASTA (112 species)
    print("[2/4] Loading plantrg_all_mirna.fa...")
    with open(MIRNA_SRC / "plantrg_all_mirna.fa") as f:
        name, seq, cur_sp = '', '', ''
        for line in f:
            if line.startswith('>'):
                if name and seq and cur_sp:
                    add(cur_sp, seq, 'plantrg_fasta', mirna_id=name)
                name = line[1:].strip().split()[0]
                cur_sp = name.split('-')[0] if '-' in name else ''
                seq = ''
            else:
                seq += line.strip()
        if name and seq and cur_sp:
            add(cur_sp, seq, 'plantrg_fasta', mirna_id=name)

    # 3. miRBase (55 species codes)
    print("[3/4] Loading miRBase_plant_mature.fa...")
    CODE_MAP = {
        'ath': 'Arabidopsis_thaliana', 'osa': 'Oryza_sativa',
        'sly': 'Solanum_lycopersicum', 'gma': 'Glycine_max',
        'zma': 'Zea_mays', 'vvi': 'Vitis_vinifera',
        'bdi': 'Brachypodium_distachyon', 'aly': 'Arabidopsis_lyrata',
        'csi': 'Citrus_sinensis', 'mtr': 'Medicago_truncatula',
        'ppe': 'Prunus_persica', 'sbi': 'Sorghum_bicolor',
        'hvu': 'Hordeum_vulgare', 'tae': 'Triticum_aestivum',
        'nta': 'Nicotiana_tabacum', 'stu': 'Solanum_tuberosum',
        'can': 'Capsicum_annuum', 'cpa': 'Carica_papaya',
        'bna': 'Brassica_napus', 'bra': 'Brassica_rapa',
        'rco': 'Ricinus_communis', 'mdo': 'Malus_domestica',
        'tca': 'Theobroma_cacao', 'ghr': 'Gossypium_hirsutum',
        'han': 'Helianthus_annuus', 'lja': 'Lotus_japonicus',
        'nbe': 'Nicotiana_benthamiana', 'pab': 'Picea_abies',
        'smo': 'Selaginella_moellendorffii', 'ptc': 'Populus_trichocarpa',
        'mes': 'Manihot_esculenta', 'lus': 'Linum_usitatissimum',
        'cme': 'Cucumis_melo', 'ccr': 'Citrus_clementina',
        'cre': 'Chlamydomonas_reinhardtii', 'vca': 'Volvox_carteri',
        'pta': 'Pinus_taeda', 'far': 'Fragaria_x_ananassa',
        'peu': 'Populus_euphratica', 'sof': 'Saccharum_officinarum',
        'ssp': 'Salvia_splendens', 'pic': 'Picea_glauca',
        'rgl': 'Rhododendron_glaucum', 'ssl': 'Solanum_sisymbriifolium',
        'aau': 'Arachis_duranensis', 'aof': 'Asparagus_officinalis',
        'fve': 'Fragaria_vesca', 'hbr': 'Hevea_brasiliensis',
        'dpr': 'Phoenix_dactylifera', 'csv': 'Cucumis_sativus',
        'egr': 'Eucalyptus_grandis', 'nnu': 'Nelumbo_nucifera',
        'ptr': 'Populus_trichocarpa', 'cmo': 'Cucurbita_moschata',
        'dcr': 'Daucus_carota', 'pda': 'Phoenix_dactylifera',
        'age': 'Asparagus_officinalis', 'bol': 'Brassica_oleracea',
        'bvu': 'Beta_vulgaris', 'oer': 'Ostreococcus_tauri',
        'hpa': 'Hordeum_vulgare',
    }
    with open(MIRNA_SRC / "miRBase_plant_mature.fa") as f:
        name, seq = '', ''
        for line in f:
            if line.startswith('>'):
                if name and seq:
                    code = name[:3]
                    sp = CODE_MAP.get(code, code)
                    add(sp, seq, 'mirbase', mirna_id=name)
                name = line[1:].strip().split()[0]
                seq = ''
            else:
                seq += line.strip()
        if name and seq:
            code = name[:3]
            sp = CODE_MAP.get(code, code)
            add(sp, seq, 'mirbase', mirna_id=name)

    # 4. NCBI precursors
    print("[4/4] Loading NCBI miRNA_precursors.fasta...")
    with open(MIRNA_SRC / "miRNA_precursors.fasta") as f:
        name, seq, cur_sp = '', '', ''
        for line in f:
            if line.startswith('>'):
                if name and seq and cur_sp:
                    add(cur_sp, seq, 'ncbi', mirna_id=name)
                header = line[1:].strip()
                m = re.match(r'[^ ]+ ([A-Z][a-z]+ [a-z]+(?:\s+subsp\.?\s+[a-z]+)?)', header)
                cur_sp = m.group(1).replace(' ', '_') if m else ''
                name = header.split()[0] if header else ''
                seq = ''
            else:
                seq += line.strip()
        if name and seq and cur_sp:
            add(cur_sp, seq, 'ncbi', mirna_id=name)

    # Build output
    output = {}
    species_count = defaultdict(int)
    for sp, seqs in sp_seqs.items():
        for seq in seqs:
            mirna_id = id_map[sp].get(seq, f"{sp}_miRNA_{species_count[sp]:05d}")
            # If ID doesn't have species prefix, add it
            if '_' not in mirna_id.split('-')[0]:
                # Already has species in name
                pass
            # Ensure unique IDs
            unique_id = mirna_id
            counter = 1
            while unique_id in output:
                unique_id = f"{mirna_id}_v{counter}"
                counter += 1
            output[unique_id] = {
                "sequence": seq,
                "species_code": sp.split('_')[0][:3].lower(),
                "species_name": sp,
                "length": len(seq),
            }
            species_count[sp] += 1

    # Save
    out_path = DATA_DIR / "mirna" / "plant_mirnas_full.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Exclusion stats (separate file so the miRNA dict stays schema-clean)
    stats_path = out_path.with_name("plant_mirnas_full_stats.json")
    stats = {
        "total_mirnas": len(output),
        "total_species": len(sp_seqs),
        "excluded_precursors": excluded['excluded_precursors'],  # NR_* records
        "excluded_long": excluded['excluded_long'],              # > 50 nt
        "max_mature_len": MAX_MATURE_LEN,
    }
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"\n  miRNAs: {len(output)} from {len(sp_seqs)} species")
    print(f"  Excluded from prediction set: {excluded['excluded_precursors']} NR_* precursors, "
          f"{excluded['excluded_long']} sequences > {MAX_MATURE_LEN} nt")
    print(f"  Saved: {out_path} ({out_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  Stats: {stats_path}")

    # Stats
    top = sorted(species_count.items(), key=lambda x: -x[1])[:10]
    print(f"  Top species:")
    for sp, cnt in top:
        print(f"    {sp}: {cnt}")


# ============================================================
# PART 2: Virus — generate viruses_full.{json,fasta}
# ============================================================

def generate_virus_full():
    """Use ref sequences (high quality) + expand hosts from Full TSV."""
    print("\n[1/3] Loading ref virus metadata (complete_ref)...")

    # Step 1: Load ref viruses (5,773 high quality reference genomes)
    ref_viruses = {}
    with open(VIRUS_SRC / "Plant_Virus.complete_ref_info.tsv", encoding='utf-8') as f:
        header = f.readline().rstrip('\n\r').split('\t')
        col = {n: i for i, n in enumerate(header)}
        for line in f:
            cols = line.rstrip('\n\r').split('\t')
            if len(cols) < len(header):
                continue
            acc = cols[col['Accession']]
            key = acc.split('.')[0] if '.' in acc else acc
            sp_ictv = (cols[col.get('Species_ICTV', '')] or '').strip()
            family = (cols[col.get('VMR_Family', '')] or '').strip()
            length = int(cols[col['Length']]) if cols[col['Length']].isdigit() else 0
            if key not in ref_viruses:
                ref_viruses[key] = {
                    "accession": acc,
                    "name": sp_ictv[:100],
                    "family": family.lower() if family else 'unknown',
                    "genome_length": length,
                    "hosts": set(),
                }

    print(f"  Ref viruses: {len(ref_viruses)}")

    # Step 2: Load ALL hosts from Full TSV for each Species_ICTV
    print("[2/3] Expanding hosts from Full TSV...")
    species_hosts = {}
    with open(VIRUS_SRC / "Plant_Virus_Full.Info.tsv", encoding='utf-8') as f:
        header = f.readline().rstrip('\n\r').split('\t')
        col_f = {n: i for i, n in enumerate(header)}
        for line in f:
            cols = line.rstrip('\n\r').split('\t')
            if len(cols) < len(header):
                continue
            sp = (cols[col_f.get('Species_ICTV', '')] or '').strip().lower()
            host = (cols[col_f.get('Host', '')] or '').strip()
            if sp and host:
                if sp not in species_hosts:
                    species_hosts[sp] = set()
                species_hosts[sp].add(host.lower().replace(' ', '_'))

    # Expand ref virus hosts
    expanded = 0
    for key, v in ref_viruses.items():
        sp = v['name'].lower()
        all_hosts = species_hosts.get(sp, set())
        if all_hosts:
            v['hosts'] = all_hosts
            if len(all_hosts) > 1:
                expanded += 1

    total_host_entries = sum(len(v.get('hosts', set())) for v in ref_viruses.values())
    print(f"  Species with expanded hosts: {expanded}")
    print(f"  Total host-virus pairs: {total_host_entries}")

    # Step 2b: Add Full-only virus species (missing from ref)
    ref_species_set = {v['name'].lower() for v in ref_viruses.values() if v['name']}
    full_only_best = {}  # species_ictv_lower -> (key, priority, length, acc, family)
    with open(VIRUS_SRC / "Plant_Virus_Full.Info.tsv", encoding='utf-8') as f:
        f.readline()  # skip header
        for line in f:
            cols = line.rstrip('\n\r').split('\t')
            if len(cols) < len(header):
                continue
            sp = (cols[col_f.get('Species_ICTV', '')] or '').strip().lower()
            host = (cols[col_f.get('Host', '')] or '').strip()
            if not sp or not host or sp in ref_species_set:
                continue
            acc = (cols[col_f.get('Accession', '')] or '').strip()
            key = acc.split('.')[0] if '.' in acc else acc
            family = (cols[col_f.get('Family', '')] or '').strip()
            is_refseq = (cols[col_f.get('Sequence_Type', '')] or '').strip() == 'RefSeq'
            is_complete = (cols[col_f.get('Nuc_Completeness', '')] or '').strip() == 'complete'
            length = int(cols[col_f['Length']]) if cols[col_f['Length']].isdigit() else 0
            priority = (2 if is_refseq else 0) + (1 if is_complete else 0)
            current = full_only_best.get(sp)
            if current is None or priority > current[1] or (priority == current[1] and length > current[2]):
                full_only_best[sp] = (key, priority, length, acc, family)

    # Add Full-only species to ref_viruses
    full_only_added = 0
    for sp, (key, priority, length, acc, family) in full_only_best.items():
        if key not in ref_viruses:  # avoid collision
            all_hosts = species_hosts.get(sp, set())
            if all_hosts:
                ref_viruses[key] = {
                    "accession": acc,
                    "name": sp[:100],
                    "family": family.lower() if family else 'unknown',
                    "genome_length": length,
                    "hosts": all_hosts,
                }
                full_only_added += 1

    print(f"  Full-only species added: {full_only_added}")
    print(f"  Total viruses (ref + full-only): {len(ref_viruses)}")

    # Step 3: Load ref FASTA sequences
    print("[3/3] Loading ref FASTA and matching...")
    virus_seqs = {}
    for fa_path in [VIRUS_SRC / "Plant_Virus.complete_ref.fasta",
                    VIRUS_SRC / "Plant_Virus_Full.fasta"]:
        if fa_path.exists():
            cid, cseq = None, []
            for line in open(fa_path):
                line = line.strip()
                if line.startswith('>'):
                    if cid:
                        virus_seqs[cid] = ''.join(cseq)
                    h = line[1:].split()[0]
                    cid = h.split('.')[0]
                    cseq = []
                else:
                    cseq.append(line)
            if cid:
                virus_seqs[cid] = ''.join(cseq)

    print(f"  FASTA sequences: {len(virus_seqs)}")

    # Build output: one virus entry with hosts list
    info = {}
    matched_fasta = []
    for vid, v in ref_viruses.items():
        seq = virus_seqs.get(vid, '')
        hosts = v.get('hosts', set())
        if seq and len(seq) >= 21 and hosts:
            info[vid] = {
                "accession": v["accession"],
                "name": v["name"],
                "family": v["family"],
                "genome_length": v["genome_length"],
                "hosts": sorted(hosts),
            }
            matched_fasta.append(f">{vid}|{v['accession']}|{v['family']}|{v['name']}\n{seq}\n")

    # Save JSON
    json_path = DATA_DIR / "virus_genomes" / "viruses_full.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, 'w') as f:
        json.dump(info, f, indent=2)

    # Save FASTA
    fasta_path = DATA_DIR / "virus_genomes" / "viruses_full.fasta"
    with open(fasta_path, 'w') as f:
        f.writelines(matched_fasta)

    print(f"\n  Output viruses: {len(info)}")
    print(f"  Total host entries: {sum(len(v['hosts']) for v in info.values())}")
    print(f"  Saved: {json_path} ({json_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  Saved: {fasta_path} ({fasta_path.stat().st_size / 1024 / 1024:.1f} MB)")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Generate full data files for PAmiRDB pipeline')
    p.add_argument('--mirna-only', action='store_true')
    p.add_argument('--virus-only', action='store_true')
    args = p.parse_args()

    run_mirna = not args.virus_only
    run_virus = not args.mirna_only

    print("=" * 60)
    print("  Generate Full Data Files for PAmiRDB Pipeline")
    print("=" * 60)

    if run_mirna:
        print("\n" + "=" * 60)
        print("  PART 1: miRNA Database")
        print("=" * 60)
        generate_mirna_full()

    if run_virus:
        print("\n" + "=" * 60)
        print("  PART 2: Virus Database")
        print("=" * 60)
        generate_virus_full()

    print("\n" + "=" * 60)
    print("  Done!")
    print("=" * 60)
    if run_mirna and run_virus:
        # Quick estimate
        import json as _j
        with open(DATA_DIR / "mirna" / "plant_mirnas_full.json") as f:
            nm = len(_j.load(f))
        with open(DATA_DIR / "virus_genomes" / "viruses_full.json") as f:
            nv = len(_j.load(f))
        total_pairs = nm * nv
        print(f"  Total pairs: {nm:,} × {nv:,} = {total_pairs:,}")
        print(f"  Estimated time (serial): ~{total_pairs * 0.05 / 3600:.0f} hours")
        print(f"  Estimated time (256-core): ~{total_pairs * 0.01 / 256 / 3600:.1f} hours")
        print(f"\n  Tip: Use --virus-limit or --mirna-limit to reduce scope")
