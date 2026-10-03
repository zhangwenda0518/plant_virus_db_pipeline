import urllib.request, json
BASE = 'http://localhost:8000'
def api(p):
    return json.loads(urllib.request.urlopen(BASE + p, timeout=10).read())

print('=' * 60)
print('  PAmiRDB Demo - Key Examples')
print('=' * 60)

print('\n--- Top 5 Strongest Interactions ---')
d = api('/api/search?limit=5')
for i, r in enumerate(d['results'], 1):
    fam = '[Gemi]' if 'gemini' in r.get('virus_family', '') else '[Poty]'
    print(f'\n[{i}] {r["mirna_id"]} -> {r["virus_name"]} {fam}')
    print(f'    Energy={r["energy"]:.1f}  Mismatches={r["num_mismatches"]}  Seed={"OK" if r["seed_perfect"] else "FAIL"}')
    for l in r['alignment'].split('\n')[:3]:
        print(f'    {l}')

print('\n\n--- Energy Gradient ---')
for e in [-35, -30, -25, -20]:
    d = api(f'/api/search?max_energy={e}')
    bar = '#' * (d['total'] // 3)
    print(f'  E <= {e:4d} kcal/mol  ->  {d["total"]:3d} predictions  {bar}')

print('\n\n--- Species-Specific Antiviral Profiles ---')
for code, name in [('ath', 'A. thaliana'), ('osa', 'O. sativa'),
                    ('sly', 'S. lycopersicum'), ('zma', 'Z. mays')]:
    d = api(f'/api/search?plant_species={code}')
    g = sum(1 for r in d['results'] if 'gemini' in r.get('virus_family', ''))
    p = sum(1 for r in d['results'] if 'poty' in r.get('virus_family', ''))
    print(f'  {name:20s}  {d["total"]:2d} targets  [Geminiviridae: {g}  Potyviridae: {p}]')

print('\n\n--- Virus-Host Relationships ---')
d = api('/api/virus-hosts')
by_v = {}
for h in d['hosts']:
    by_v.setdefault(h['virus_id'], []).append(h['host_common_name'])
for vid, hosts in sorted(by_v.items()):
    print(f'  {vid:10s}  ->  {", ".join(hosts)}')

print('\n\n--- Database Summary ---')
d = api('/api/stats')
print(f'  miRNAs: {d["total_mirnas"]}  |  Viruses: {d["total_viruses"]}  |  Predictions: {d["total_predictions"]}')
print(f'  Species: {", ".join(sorted(d["species_distribution"].keys()))}')
print(f'  Families: {", ".join(sorted(d["virus_family_distribution"].keys()))}')

print(f'\n{"=" * 60}')
print(f'  Web UI: http://localhost:8000')
print(f'{"=" * 60}')
