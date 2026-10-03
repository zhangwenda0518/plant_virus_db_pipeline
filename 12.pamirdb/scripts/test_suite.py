"""
PAmiRDB Comprehensive Test Suite.
Tests all API endpoints and verifies PAmiRDB-specific features.
"""
import urllib.request
import json
import sys

BASE = "http://localhost:8000"
passed = 0
failed = 0

def api(path):
    r = urllib.request.urlopen(BASE + path, timeout=10)
    return json.loads(r.read())

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  -- {detail}")

print("=" * 60)
print("  PAmiRDB Test Suite")
print("  Satish et al. (2019) Scientific Reports 9:4627")
print("=" * 60)

# ── Test 1: Server health ──────────────────────────────────────────
print("\n--- Test 1: Server Health ---")
try:
    r = urllib.request.urlopen(BASE + "/", timeout=5)
    test("Homepage loads", r.status == 200)
except Exception as e:
    test("Homepage loads", False, str(e))

try:
    d = api("/api/stats")
    test("Stats endpoint", "total_mirnas" in d, str(d.keys()))
except Exception as e:
    test("Stats endpoint", False, str(e))

# ── Test 2: Database contents ──────────────────────────────────────
print("\n--- Test 2: Database Contents ---")
d = api("/api/stats")
test("miRNA count > 100", d['total_mirnas'] >= 100, f"got {d['total_mirnas']}")
test("Virus count >= 10", d['total_viruses'] >= 10, f"got {d['total_viruses']}")
test("Predictions > 0", d['total_predictions'] > 0, f"got {d['total_predictions']}")
test("7 plant species", len(d['species_distribution']) == 7, 
     f"got {len(d['species_distribution'])}: {list(d['species_distribution'].keys())}")
test("2 virus families", len(d['virus_family_distribution']) == 2,
     f"got {len(d['virus_family_distribution'])}: {list(d['virus_family_distribution'].keys())}")

# ── Test 3: miRNA listing ──────────────────────────────────────────
print("\n--- Test 3: miRNA Listing ---")
d = api("/api/mirnas")
test("miRNA list returns", len(d['mirnas']) > 0)

# Test species filtering
for code in ['ath', 'osa', 'sly', 'zma']:
    d = api(f"/api/mirnas?species={code}")
    test(f"Filter by species {code}", len(d['mirnas']) > 0, f"got {len(d['mirnas'])}")

# ── Test 4: Virus listing ──────────────────────────────────────────
print("\n--- Test 4: Virus Listing ---")
d = api("/api/viruses")
test("Virus list returns", len(d['viruses']) == 10, f"got {len(d['viruses'])}")

d = api("/api/viruses?family=geminiviridae")
test("Filter geminiviridae", len(d['viruses']) == 5, f"got {len(d['viruses'])}")

d = api("/api/viruses?family=potyviridae")
test("Filter potyviridae", len(d['viruses']) == 5, f"got {len(d['viruses'])}")

# ── Test 5: Search API ─────────────────────────────────────────────
print("\n--- Test 5: Search API ---")

# Full search
d = api("/api/search")
test("Full search returns results", d['total'] == 92, f"got {d['total']}")

# Virus family filter
d = api("/api/search?virus_family=geminiviridae")
test("Family filter (geminiviridae)", d['total'] > 0, f"got {d['total']}")

d = api("/api/search?virus_family=potyviridae")
test("Family filter (potyviridae)", d['total'] > 0, f"got {d['total']}")

# Plant species filter
d = api("/api/search?plant_species=ath")
test("Species filter (A. thaliana)", d['total'] > 0, f"got {d['total']}")

d = api("/api/search?plant_species=osa")
test("Species filter (O. sativa)", d['total'] > 0, f"got {d['total']}")

# Energy threshold
d = api("/api/search?max_energy=-25")
test("Energy filter (<=-25)", d['total'] > 0, f"got {d['total']}")
for r in d['results']:
    if r['energy'] > -25:
        test("Energy filter (all <= -25)", False, f"{r['mirna_id']} energy={r['energy']}")
        break
else:
    test("Energy filter (all <= -25)", True)

d = api("/api/search?max_energy=-30")
test("Energy filter (<=-30)", d['total'] > 0, f"got {d['total']}")

# Specific miRNA
d = api("/api/search?mirna_id=ath-miR408-5p")
test("Specific miRNA (ath-miR408-5p)", d['total'] > 0, f"got {d['total']}")

# Specific virus
d = api("/api/search?virus_id=TYLCV-IR")
test("Specific virus (TYLCV-IR)", d['total'] > 0, f"got {d['total']}")

# Combined filters
d = api("/api/search?virus_family=geminiviridae&max_energy=-25&plant_species=ath")
test("Combined filters (gemini+energy+ath)", d['total'] > 0, f"got {d['total']}")

# ── Test 6: PAmiRDB-specific criteria ──────────────────────────────
print("\n--- Test 6: PAmiRDB Filter Criteria ---")
d = api("/api/search")

# All results must have seed region perfect (positions 2-8)
all_seed_ok = all(r['seed_perfect'] for r in d['results'])
test("All results: seed region perfect", all_seed_ok)

# All results must have <= 4 mismatches
all_mm_ok = all(r['num_mismatches'] <= 4 for r in d['results'])
test("All results: <= 4 mismatches", all_mm_ok)

# All results must have energy <= -20
all_energy_ok = all(r['energy'] <= -20 for r in d['results'])
test("All results: energy <= -20 kcal/mol", all_energy_ok)

# Energy range
energies = [r['energy'] for r in d['results']]
test("Energy min <= -30", min(energies) <= -30, f"min={min(energies):.1f}")

# Identity check
for r in d['results']:
    if r['identity'] < 0 or r['identity'] > 100:
        test("Identity in [0,100]", False, f"{r['mirna_id']} identity={r['identity']}")
        break
else:
    test("Identity in [0,100]", True)

# ── Test 7: Virus-host relationships ───────────────────────────────
print("\n--- Test 7: Virus-Host Data ---")
d = api("/api/virus-hosts")
test("Virus-host data returns", d['total'] == 22, f"got {d['total']}")

d = api("/api/virus-hosts?virus_id=TYLCV-IR")
test("TYLCV-IR has hosts", d['total'] >= 2, f"got {d['total']}")

d = api("/api/virus-hosts?virus_id=PVY")
test("PVY has hosts", d['total'] >= 3, f"got {d['total']}")

# ── Test 8: Alignment quality ──────────────────────────────────────
print("\n--- Test 8: Alignment Quality ---")
d = api("/api/search?max_energy=-30")
for r in d['results'][:3]:
    has_alignment = 'alignment' in r and len(r.get('alignment', '')) > 10
    test(f"Alignment present ({r['mirna_id'][:20]})", has_alignment)

# ── Summary ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
total = passed + failed
print(f"  Results: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("  ALL TESTS PASSED!")
else:
    print(f"  {failed} TEST(S) FAILED!")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
