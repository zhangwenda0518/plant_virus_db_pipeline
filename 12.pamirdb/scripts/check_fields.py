import json
with open('data/predictions_v5.json') as f:
    preds = json.load(f)

rh = [p for p in preds if 'rnahybrid_mfe' in p]
r22 = [p for p in preds if 'rna22_mfe' in p]
hp = [p for p in preds if p['consensus_level'] == 'HIGH+']

print("With RNAhybrid field:", len(rh))
print("With RNA22 field:", len(r22))
print("HIGH+ preds:", len(hp))

if hp:
    p = hp[0]
    print("\nHIGH+ example keys with tool prefixes:")
    for k in sorted(p.keys()):
        if any(prefix in k for prefix in ['rna','psrna','tapir','miranda_']):
            print(f"  {k}")
