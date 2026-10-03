"""Test the PAmiRDB server API."""
import urllib.request
import json

BASE = "http://localhost:8000"

def api(path):
    r = urllib.request.urlopen(BASE + path, timeout=10)
    return json.loads(r.read())

# Stats
stats = api("/api/stats")
print(f"Stats: {stats['total_mirnas']} miRNAs, {stats['total_viruses']} viruses, {stats['total_predictions']} predictions")
print()

# Search: geminiviridae energy <= -25
d = api("/api/search?virus_family=geminiviridae&max_energy=-25")
print(f"Search (geminiviridae, energy <= -25): {d['total']} results")
for r in d['results'][:5]:
    print(f"  {r['mirna_id']:30s} -> {r['virus_name']:35s}  E={r['energy']:.1f}")
print()

# Specific miRNA
d = api("/api/search?mirna_id=ath-miR156a-5p")
print(f"ath-miR156a-5p targets: {d['total']} viruses")
for r in d['results']:
    print(f"  {r['virus_name']:35s}  E={r['energy']:.1f}  seed={r['seed_perfect']}")
print()

# Species filter
d = api("/api/search?plant_species=osa")
print(f"O. sativa predictions: {d['total']}")
print()

# Viruses
d = api("/api/viruses")
print(f"All viruses:")
for v in d['viruses']:
    print(f"  {v['virus_id']:10s} {v['name']:35s} {v['family']}")
