"""
PAmiRDB data bridge — loads miRNA/virus data from 11.antiviral_genes.
Run once to convert existing data to PAmiRDB format.
"""
import json
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent.parent
DATA_SRC = BASE.parent / "11.antiviral_genes" / "data"
DATA_OUT = BASE / "data"
DOCS = BASE.parent.parent / "docs" / "data"

PRIORITY = [
    'Arabidopsis_thaliana','Oryza_sativa','Zea_mays','Glycine_max',
    'Solanum_lycopersicum','Nicotiana_tabacum','Nicotiana_benthamiana',
    'Triticum_aestivum','Hordeum_vulgare','Brassica_napus',
    'Manihot_esculenta','Gossypium_hirsutum','Vitis_vinifera',
    'Sorghum_bicolor','Capsicum_annuum',
]


def _parse_fasta(path):
    records = []; h = None; s = []
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line.startswith('>'):
            if h: records.append((h, ''.join(s)))
            h = line[1:]; s = []
        elif line: s.append(line)
    if h: records.append((h, ''.join(s)))
    return records


def load_mirnas():
    mirnas = {}
    # PlantRG: header format ">Actinidia_chinensis-miR169a-5p"
    plantrg = DATA_SRC / "plantrg_all_mirna.fa"
    if plantrg.exists():
        for header, seq in _parse_fasta(plantrg):
            # Parse: "Actinidia_chinensis-miR169a-5p" -> mirid, species
            parts = header.split('-', 1)  # split at first '-'
            if len(parts) == 2:
                species = parts[0]  # "Actinidia_chinensis"
                mirid = parts[1]   # "miR169a-5p"
                # Keep full ID unique: species-miRNA
                full_id = header.strip()
            else:
                species = 'unknown'
                mirid = full_id = header.strip()
            
            seq = seq.upper().replace('T', 'U')
            if 19 <= len(seq) <= 26:
                sp_name = species.replace('_', ' ')
                mirnas[full_id] = {
                    "sequence": seq,
                    "species_code": species[:3].lower(),
                    "species_name": sp_name,
                    "source": "PlantRG",
                }
    # miRBase_plant_mature (plant-filtered)
    mirbase = DATA_SRC / "miRBase_plant_mature.fa"
    seen_seqs = set(v['sequence'] for v in mirnas.values())
    if mirbase.exists():
        for header, seq in _parse_fasta(mirbase):
            parts = header.split()
            if not parts: continue
            mirid = parts[0]
            sp = ' '.join(parts[2:5]) if len(parts)>2 else 'unknown'
            seq = seq.upper().replace('T','U')
            if 19 <= len(seq) <= 26 and seq not in seen_seqs:
                k = f"mirbase_{mirid}"
                mirnas[k] = {"sequence":seq,
                    "species_code":mirid.split('-')[0] if '-' in mirid else '??',
                    "species_name":sp,"source":"miRBase"}
                seen_seqs.add(seq)
    
    # miRBase_mature_all (all species - filter for plant)
    mirbase_all = DATA_SRC / "miRBase_mature_all.fa"
    if mirbase_all.exists():
        for header, seq in _parse_fasta(mirbase_all):
            parts = header.split()
            if not parts: continue
            mirid = parts[0]
            sp = ' '.join(parts[2:5]) if len(parts)>2 else 'unknown'
            # Only load if from plant species (check 3-letter prefix)
            prefix = mirid.split('-')[0] if '-' in mirid else ''
            seq = seq.upper().replace('T','U')
            if 19 <= len(seq) <= 26 and seq not in seen_seqs:
                k = f"mirbase_all_{mirid}"
                mirnas[k] = {"sequence":seq,
                    "species_code":prefix,
                    "species_name":sp,"source":"miRBase_all"}
                seen_seqs.add(seq)
    print(f"miRNAs: {len(mirnas)}")
    return mirnas


def load_viruses():
    viruses = {}
    for src in [DATA_SRC/"plant_virus_genomes.fasta", DOCS/"Plant_Virus_Full.fasta", DOCS/"Plant_Virus_Ref.fasta"]:
        if not src.exists(): continue
        for header, seq in _parse_fasta(src):
            parts = header.split()
            acc = parts[0].split('.')[0] if parts else '?'
            name = ' '.join(parts[1:4]) if len(parts)>1 else header[:80]
            txt = (name+header).lower()
            fam = 'geminiviridae' if any(k in txt for k in ['gemini','begomo','curto','mastrevir']) else \
                  'potyviridae' if any(k in txt for k in ['potyvi','potyvir']) else 'other'
            k = acc[:20]
            if k not in viruses or len(seq) > len(viruses[k].get('seq','')):
                viruses[k] = {"accession":parts[0] if parts else '','name':name[:120],
                    "family":fam,"genome_length":len(seq),"seq":seq}
    print(f"Viruses: {len(viruses)}")
    return viruses


def main():
    print("PAmiRDB Data Bridge: 11 -> 12")
    mirnas = load_mirnas()
    viruses = load_viruses()
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    
    # MiRNA
    js = DATA_OUT / "plant_mirnas.json"
    with open(js,'w') as f: json.dump(mirnas, f, indent=2)
    fa = DATA_OUT / "plant_mirnas.fasta"
    with open(fa,'w') as f:
        for mid, info in sorted(mirnas.items()):
            f.write(f">{mid} [{info['species_name']}]\n{info['sequence']}\n")
    
    # Virus
    meta = {}
    vf = DATA_OUT / "viruses.fasta"
    with open(vf,'w') as f:
        for vid, info in viruses.items():
            meta[vid] = {k:v for k,v in info.items() if k != 'seq'}
            if info.get('seq'):
                f.write(f">{vid}|{info.get('accession','')}|{info.get('family','')}|{info.get('name','')[:60]}\n{info['seq']}\n")
    with open(DATA_OUT/"viruses.json",'w') as f: json.dump(meta, f, indent=2)
    
    print(f"Saved: {js} ({len(mirnas)} miRNAs)")
    print(f"Saved: {vf} ({len(meta)} viruses)")


if __name__ == '__main__':
    main()
