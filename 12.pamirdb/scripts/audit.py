"""Self-audit of PAmiRDB system."""
import sys, json
from pathlib import Path
sys.path.insert(0, 'scripts')

print("=" * 60)
print("  PAmiRDB Self-Audit")
print("=" * 60)

# 1. Algorithm health
print("\n--- 1. Algorithm Health ---")
from alignment import align_mirna_to_target
from consensus import _validate_psrna, _validate_rnahybrid
from rna22 import validate_with_rna22
from tapir import validate_with_tapir

mirna = 'CGGGGAACAGGCAGAGCAUGG'
target = 'GTCCCCTTCGTCCCTACGAGCT'
r1 = align_mirna_to_target('test', mirna, 'test', target)
ok1 = r1 and r1.passes_filters
print(f"  miRanda:          {'PASS' if ok1 else 'FAIL'}")

r2 = _validate_psrna(r1, 'test', 'test') if r1 else None
print(f"  psRNATarget:      {'PASS' if r2 and r2.passes else 'FAIL'}")

r3 = _validate_rnahybrid(r1, 'test', 'test') if r1 else None
print(f"  RNAhybrid:        {'PASS' if r3 and r3.passes else 'FAIL'}")

r4 = validate_with_rna22(r1, 'test', 'test', target) if r1 else None
print(f"  RNA22:            {'PASS' if r4 and r4.passes else 'FAIL (no seed-independent hit)'}")

r5 = validate_with_tapir(r1, 'test', 'test', target) if r1 else None
print(f"  TAPIR:            {'PASS' if r5 and r5.passes else 'FAIL'}")

# 2. Module imports
print("\n--- 2. Module Imports ---")
mods = ['alignment','psrnatarget','rnahybrid','rna22','tapir','consensus',
        'premirna_full','viral_mirna','validation_amirna','vsirna_conservation',
        'virus_genes','circos_network','pipeline_v5']
for m in mods:
    try:
        __import__(m); print(f"  OK  {m}")
    except Exception as e:
        print(f"  FAIL  {m}: {e}")

# 3. Data integrity
print("\n--- 3. Data Files ---")
files = [
    ('data/mirna/plant_mirnas.json', 'json'),
    ('data/virus_genomes/viruses.json', 'json'),
    ('data/virus_genomes/viruses.fasta', 'fasta'),
    ('data/virus_host/virus_host.csv', 'csv'),
    ('data/predictions_v5.json', 'json'),
]
for path, kind in files:
    p = Path(path)
    if not p.exists():
        print(f"  MISSING  {path}")
        continue
    if kind == 'json':
        d = json.load(open(p))
        if isinstance(d, list):
            print(f"  OK  {path}  ({len(d)} records)")
        else:
            print(f"  OK  {path}  ({len(d)} keys)")
    else:
        print(f"  OK  {path}  ({p.stat().st_size:,} bytes)")

# 4. Prediction field audit
print("\n--- 4. Prediction Fields ---")
with open('data/predictions_v5.json') as f:
    preds = json.load(f)
p = preds[0] if preds else {}
expected = ['mirna_id','consensus_level','consensus_detail','num_algorithms',
            'miranda_energy','miranda_identity','miranda_similarity',
            'psrna_score','psrna_cleavage','rnahybrid_mfe',
            'rna22_mfe','rna22_pattern_score','tapir_score','tapir_accessibility',
            'seed_perfect','target_protein','matching_status',
            'pre_mirna_valid','experimentally_validated','conserved_antiviral']
present = [e for e in expected if e in p]
missing = [e for e in expected if e not in p]
print(f"  Present: {len(present)}/{len(expected)}")
if missing:
    print(f"  Missing: {missing}")

# 5. Consensus distribution
print("\n--- 5. Consensus Distribution ---")
from collections import Counter
levels = Counter(pr['consensus_level'] for pr in preds)
for lvl in ['VERY HIGH','HIGH+','HIGH','MEDIUM','LOW']:
    cnt = levels.get(lvl, 0)
    if cnt:
        print(f"  {lvl:10s}: {cnt:3d}")

# 6. Consistency checks
print("\n--- 6. Consistency Checks ---")
issues = []
for pr in preds:
    if pr.get('num_algorithms', 0) < 2:
        issues.append(f"{pr['mirna_id']}->{pr['target_virus_id']}: only {pr['num_algorithms']} tools")
    if pr.get('seed_perfect') != True:
        issues.append(f"{pr['mirna_id']}->{pr['target_virus_id']}: seed={pr.get('seed_perfect')}")
    if pr.get('miranda_energy', 0) > -20:
        issues.append(f"{pr['mirna_id']}->{pr['target_virus_id']}: energy={pr.get('miranda_energy')}")
    if pr.get('miranda_mismatches', 0) > 4:
        issues.append(f"{pr['mirna_id']}->{pr['target_virus_id']}: mm={pr.get('miranda_mismatches')}")

if issues:
    print(f"  Found {len(issues)} issues:")
    for i in issues[:5]:
        print(f"    {i}")
else:
    print(f"  All {len(preds)} predictions pass core PAmiRDB filters")

print("\n" + "=" * 60)
print("  Audit Complete")
print("=" * 60)
