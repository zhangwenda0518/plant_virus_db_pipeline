"""
PAmiRDB Demo - Comprehensive examples
"""
import urllib.request, json

BASE = "http://localhost:8000"

def api(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())

def sec(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def show_aln(r):
    fam_tag = "[Geminiviridae]" if 'gemini' in r.get('virus_family','') else "[Potyviridae]"
    print(f"\n  miRNA:  {r['mirna_id']}")
    print(f"  Target: {r['virus_name']} {fam_tag}")
    print(f"  Energy: {r['energy']:.1f} kcal/mol  |  Mismatches: {r['num_mismatches']}  |  Identity: {r['identity']:.1f}%")
    print(f"  Position: {r['target_start']}-{r['target_end']}  |  Seed region: {'PERFECT' if r['seed_perfect'] else 'FAIL'}")
    for line in r['alignment'].split('\n'):
        print(f"    {line}")


# Example 1: Top 5 strongest interactions
sec("EXAMPLE 1: Top 5 Strongest miRNA-Virus Interactions")
d = api("/api/search?limit=5")
for i, r in enumerate(d['results'], 1):
    print(f"\n  [{i}]", end="")
    show_aln(r)


# Example 2: Geminivirus targeting
sec("EXAMPLE 2: Geminivirus Targeting Profile")
d = api("/api/search?virus_family=geminiviridae&limit=20")
gemin = {}
for r in d['results']:
    vname = r['virus_name']
    gemin.setdefault(vname, []).append(r)
for vname, results in sorted(gemin.items()):
    print(f"\n  > {vname} -- {len(results)} targeting miRNAs")
    for r in results[:3]:
        print(f"      {r['mirna_id']:28s}  E={r['energy']:5.1f}  mm={r['num_mismatches']}")


# Example 3: Potyvirus targeting
sec("EXAMPLE 3: Potyvirus Targeting Profile")
d = api("/api/search?virus_family=potyviridae&limit=20")
poty = {}
for r in d['results']:
    vname = r['virus_name']
    poty.setdefault(vname, []).append(r)
for vname, results in sorted(poty.items()):
    print(f"\n  > {vname} -- {len(results)} targeting miRNAs")
    for r in results[:3]:
        print(f"      {r['mirna_id']:28s}  E={r['energy']:5.1f}  mm={r['num_mismatches']}")


# Example 4: Species-specific antiviral profiles
sec("EXAMPLE 4: Species-Specific Antiviral miRNA Profiles")
for code, name in [('ath','Arabidopsis thaliana'), ('osa','Oryza sativa'),
                    ('sly','Solanum lycopersicum'), ('zma','Zea mays')]:
    d = api(f"/api/search?plant_species={code}")
    gem = sum(1 for r in d['results'] if 'gemini' in r.get('virus_family',''))
    pot = sum(1 for r in d['results'] if 'poty' in r.get('virus_family',''))
    print(f"  {name:30s} ({code}): {d['total']:2d} targets  [Geminiviridae:{gem}  Potyviridae:{pot}]")


# Example 5: Energy gradient
sec("EXAMPLE 5: Energy Gradient -- Cumulative Filtering")
for cutoff in [-35, -30, -25, -20]:
    d = api(f"/api/search?max_energy={cutoff}")
    bar = '#' * (d['total'] // 5)
    print(f"  Energy <= {cutoff:4d} kcal/mol  ->  {d['total']:3d}  {bar}")


# Example 6: miRNA families comparison
sec("EXAMPLE 6: miR159 Family -- Cross-Species Antiviral Activity")
for species in ['ath', 'gma', 'osa', 'sbi', 'sly', 'vvi', 'zma']:
    for suffix in ['a', 'b']:
        mir_id = f"{species}-miR159{suffix}"
        d = api(f"/api/search?mirna_id={mir_id}")
        if d['total'] > 0:
            targets = [f"{r['virus_name']}(E={r['energy']:.0f})" for r in d['results']]
            print(f"  {mir_id:22s} -> {', '.join(targets)}")

sec("EXAMPLE 7: miR408 Family -- Copper-Regulated Antiviral miRNA")
for species in ['ath', 'gma', 'osa', 'sly', 'zma']:
    mir_id = f"{species}-miR408-5p"
    d = api(f"/api/search?mirna_id={mir_id}")
    if d['total'] > 0:
        targets = [f"{r['virus_name']}(E={r['energy']:.0f})" for r in d['results']]
        print(f"  {mir_id:22s} -> {', '.join(targets)}")


# Example 7: Virus-host network
sec("EXAMPLE 8: Virus-Host Network")
d = api("/api/virus-hosts")
by_virus = {}
for h in d['hosts']:
    by_virus.setdefault(h['virus_id'], []).append(h['host_common_name'])
for vid, hosts in sorted(by_virus.items()):
    print(f"  {vid:10s} -> {', '.join(hosts)}")


# Example 8: Full statistics dashboard
sec("EXAMPLE 9: Database Statistics Dashboard")
d = api("/api/stats")
print(f"\n  miRNAs:    {d['total_mirnas']}")
print(f"  Viruses:   {d['total_viruses']}")
print(f"  Predictions: {d['total_predictions']}")
print(f"\n  Species Distribution:")
for sp, cnt in sorted(d['species_distribution'].items(), key=lambda x:-x[1]):
    bar = '#' * cnt
    print(f"    {sp:25s} {bar} {cnt}")
print(f"\n  Virus Family Distribution:")
for fam, cnt in d['virus_family_distribution'].items():
    print(f"    {fam:25s} {'#' * (cnt*2)} {cnt}")

print(f"\n{'='*60}")
print(f"  Demo complete!  Web UI: http://localhost:8000")
print(f"{'='*60}")
