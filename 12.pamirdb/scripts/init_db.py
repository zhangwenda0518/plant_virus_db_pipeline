"""Initialize database and run a quick test."""
import sys
sys.path.insert(0, 'scripts')
from database import Database

db = Database()
db.create_tables()
db.load_data_files()

print("Database ready!")

# Quick test queries
results = db.query(max_energy=-25)
print(f"Test 1 (energy <= -25): {len(results)} results")
for r in results[:3]:
    print(f"  {r['mirna_id']} -> {r['virus_name']}  energy={r['energy']:.1f}")

results = db.query(virus_family='geminiviridae')
print(f"\nTest 2 (geminiviridae only): {len(results)} results")

results = db.query(plant_species='ath')
print(f"Test 3 (A. thaliana only): {len(results)} results")

# Get summary stats
print("\n=== Database Summary ===")
mirnas = db.get_mirnas()
viruses = db.get_viruses()
all_preds = db.query()
print(f"miRNAs: {len(mirnas)}")
print(f"Viruses: {len(viruses)}")
print(f"Predictions: {len(all_preds)}")
print("Species:", sorted(set(m.get('species_code','') for m in mirnas)))
print("Families:", sorted(set(v.get('family','') for v in viruses)))
