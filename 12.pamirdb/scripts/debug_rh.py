import json
with open('data/predictions_v5.json') as f:
    preds = json.load(f)

# Find HIGH+ with detail
hp = [p for p in preds if p['consensus_level'] == 'HIGH+']
for p in hp[:3]:
    print(p['consensus_detail'], '|', p['mirna_id'], '|', 
          'rnahybrid_mfe' in p, '|', 'rna22_mfe' in p)

# Find any with rnahybrid_mfe
with_rh = [p for p in preds if 'rnahybrid_mfe' in p]
print(f"\nTotal with rnahybrid_mfe: {len(with_rh)}")

# Check consensus.py's _validate_rnahybrid 
import sys; sys.path.insert(0,'scripts')
from consensus import _validate_rnahybrid, _validate_psrna
from alignment import align_mirna_to_target

r1 = align_mirna_to_target('test','CGGGGAACAGGCAGAGCAUGG','test','GTCCCCTTCGTCCCTACGAGCT')
if r1:
    r3 = _validate_rnahybrid(r1, 'test', 'test')
    print(f"\n_validate_rnahybrid direct test:")
    print(f"  result exists: {r3 is not None}")
    if r3:
        print(f"  mfe: {r3.mfe:.1f}, passes: {r3.passes}, seed: {r3.seed_perfect}")
    else:
        print("  None returned - energy too high or seed failed")
