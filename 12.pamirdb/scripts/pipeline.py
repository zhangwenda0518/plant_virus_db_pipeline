"""
PAmiRDB v2 batch prediction pipeline.
Enhanced: similarity%, position binding, protein annotation, matching status.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from alignment import align_mirna_to_target
from virus_genes import VIRUS_GENES, get_target_gene

DATA_DIR = Path(__file__).parent.parent / "data"


def load_mirnas(path=None):
    if path is None: path = DATA_DIR / "mirna" / "plant_mirnas.json"
    with open(path) as f: return json.load(f)


def load_viruses_meta(path=None):
    if path is None: path = DATA_DIR / "virus_genomes" / "viruses.json"
    with open(path) as f: return json.load(f)


def load_virus_seqs(path=None):
    if path is None: path = DATA_DIR / "virus_genomes" / "viruses.fasta"
    seqs = {}; cid = None; cseq = []
    for line in open(path):
        line = line.strip()
        if line.startswith('>'):
            if cid: seqs[cid] = ''.join(cseq)
            cid = line[1:].split('|')[0]; cseq = []
        else: cseq.append(line)
    if cid: seqs[cid] = ''.join(cseq)
    return seqs


def run_pipeline(mirnas=None, viruses_meta=None, virus_seqs=None):
    if mirnas is None: mirnas = load_mirnas()
    if viruses_meta is None: viruses_meta = load_viruses_meta()
    if virus_seqs is None: virus_seqs = load_virus_seqs()
    
    results = []
    total = len(mirnas) * len(virus_seqs); count = 0
    
    for mirna_id, info in mirnas.items():
        mirna_seq = info['sequence']
        for virus_id, virus_seq in virus_seqs.items():
            count += 1
            if count % 200 == 0:
                print(f"  Progress: {count}/{total} ({count*100//total}%)")
            
            r = align_mirna_to_target(mirna_id, mirna_seq, virus_id, virus_seq)
            if r and r.passes_filters:
                # Determine protein target and matching status
                vinfo = VIRUS_GENES.get(virus_id, {})
                protein, match_status = get_target_gene(virus_id, r.target_start, r.target_end)
                
                results.append({
                    "mirna_id": r.mirna_id,
                    "mirna_seq": r.mirna_seq,
                    "mirna_species": info.get('species_code', ''),
                    "mirna_species_name": info.get('species_name', ''),
                    "target_virus_id": r.target_id,
                    "target_virus_name": viruses_meta.get(virus_id, {}).get('name', ''),
                    "target_virus_family": viruses_meta.get(virus_id, {}).get('family', ''),
                    "target_start": r.target_start,
                    "target_end": r.target_end,
                    "score": r.score,
                    "energy": r.energy,
                    "num_mismatches": r.num_mismatches,
                    "num_gaps": r.num_gaps,
                    "seed_perfect": r.seed_perfect,
                    "query_cover": round(r.query_cover, 2),
                    "identity": round(r.identity, 2),
                    "similarity": round(r.similarity, 2),          # NEW
                    "query_start": r.query_start,                   # NEW
                    "query_end": r.query_end,                       # NEW
                    "alignment_length": r.alignment_length,         # NEW
                    "target_protein": protein,                      # NEW
                    "matching_status": match_status,                # NEW
                    "alignment": r.alignment_str,
                    "position_binding": r.position_binding,         # NEW
                })
    
    return results


def save_results(results, path=None):
    if path is None: path = DATA_DIR / "predictions.json"
    with open(path, 'w') as f: json.dump(results, f, indent=2)
    print(f"\n[OK] Saved {len(results)} predictions to {path}")


def print_summary(results):
    print(f"\n{'='*60}")
    print(f"  PAmiRDB v2 Prediction Summary")
    print(f"{'='*60}")
    print(f"  Total predictions: {len(results)}")
    
    sp = {}
    for r in results:
        n = r['mirna_species_name']; sp[n] = sp.get(n, 0) + 1
    print(f"\n  By species:")
    for n, c in sorted(sp.items(), key=lambda x: -x[1]):
        print(f"    {n}: {c}")
    
    fam = {}
    for r in results:
        f = r['target_virus_family']; fam[f] = fam.get(f, 0) + 1
    print(f"\n  By virus family:")
    for f, c in sorted(fam.items(), key=lambda x: -x[1]):
        print(f"    {f}: {c}")
    
    # NEW: protein distribution
    prots = {}
    for r in results:
        p = r.get('target_protein', 'Unknown'); prots[p] = prots.get(p, 0) + 1
    print(f"\n  Top targeted proteins:")
    for p, c in sorted(prots.items(), key=lambda x: -x[1])[:10]:
        print(f"    {p}: {c}")
    
    # NEW: matching status distribution
    ms = {}
    for r in results:
        s = r.get('matching_status', 'Unknown'); ms[s] = ms.get(s, 0) + 1
    print(f"\n  Matching status:")
    for s, c in sorted(ms.items()):
        print(f"    {s}: {c}")
    
    energies = [r['energy'] for r in results if r['energy']]
    if energies:
        print(f"\n  Energy: min={min(energies):.1f} max={max(energies):.1f} mean={sum(energies)/len(energies):.1f}")


if __name__ == '__main__':
    print("Loading data...")
    mirnas = load_mirnas()
    viruses_meta = load_viruses_meta()
    virus_seqs = load_virus_seqs()
    print(f"  miRNAs: {len(mirnas)}, Viruses: {len(virus_seqs)}, Pairs: {len(mirnas)*len(virus_seqs)}")
    
    print("\nRunning prediction pipeline...")
    results = run_pipeline(mirnas, viruses_meta, virus_seqs)
    
    print_summary(results)
    save_results(results)
