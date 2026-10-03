import urllib.request, json
d = json.loads(urllib.request.urlopen(
    "http://localhost:8000/api/search?max_energy=-30&limit=3", timeout=5).read())
for r in d["results"]:
    print("=" * 60)
    print("miRNA:", r["mirna_id"], " Virus:", r["virus_name"])
    print("Energy:", r["energy"], " Mismatches:", r["num_mismatches"], " Seed:", r["seed_perfect"])
    print()
    print(r["alignment"])
    print()
