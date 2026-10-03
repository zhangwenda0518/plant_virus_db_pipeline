import json
with open("data/predictions_v4.json") as f:
    preds = json.load(f)

# Find the specific prediction
for p in preds:
    if p["mirna_id"] == "ath-miR159a" and "Tomato yellow leaf curl" in p.get("target_virus_name", ""):
        print("=== ath-miR159a -> TYLCV-Iran ===")
        print(f"consensus:        {p['consensus_detail']} ({p['consensus_level']})")
        print(f"miRanda energy:   {p['miranda_energy']:.1f} kcal/mol")
        print(f"miRanda identity: {p['miranda_identity']:.1f}%")
        print(f"miRanda similarity: {p['miranda_similarity']:.1f}%")
        print(f"miRanda mismatches: {p['miranda_mismatches']}")
        print(f"seed perfect:     {p['seed_perfect']}")
        print(f"psRNATarget:      cleav={p.get('psrna_cleavage')} inhib={p.get('psrna_inhibition')}")
        print(f"RNAhybrid MFE:    {p.get('rnahybrid_mfe', 'N/A')}")
        print(f"TAPIR score:      {p.get('tapir_score', 'N/A')}")
        print(f"TAPIR access:     {p.get('tapir_accessibility', 'N/A')}")
        print(f"experimentally_validated: {p.get('experimentally_validated')}")
        print(f"conserved_antiviral: {p.get('conserved_antiviral')}")
        print(f"conservation_spp: {p.get('conservation_species_count')}")
        print(f"pre_miRNA valid:  {p.get('pre_mirna_valid')}")
        print(f"pre_miRNA criteria: {p.get('pre_mirna_criteria')}/7")
        print()
        # Show alignment
        print("Alignment:")
        print(p.get('alignment', 'N/A')[:400])
        break
