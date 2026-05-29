# -*- coding: utf-8 -*-
"""
C8: Analyze plant virus species removed from non-Plant categories by C4 L7.

Usage:
  python C8_analyze_cross_species.py --cross_species_dir classified_clean/cross_species/ \
      --classified_dir classified_clean/ --output_dir cross_analysis/
"""
import polars as pl
import os, argparse, csv
from collections import defaultdict

CATS = ["Insecta", "Arachnida", "Fungi", "Bacteria", "Animal_other", "Aves",
        "Mammalia", "Human", "Oomycetes", "Protist"]
CROSS_FAMS = {"Mitoviridae", "Partitiviridae", "Endornaviridae", "Botourmiaviridae", "Narnaviridae"}


def classify(sp, plant_cnt, cat_counts):
    """Classify a cross-category species based on record counts."""
    total = plant_cnt + sum(cat_counts.values())
    insecta = cat_counts.get("Insecta", 0)
    arachnida = cat_counts.get("Arachnida", 0)
    aves = cat_counts.get("Aves", 0)
    animal_other = cat_counts.get("Animal_other", 0)
    fungi = cat_counts.get("Fungi", 0)

    if fungi > 0:
        return "PLANT_FUNGI_SHARED"
    if plant_cnt >= 100 and insecta <= plant_cnt * 0.1:
        return "VECTOR_INSECT"
    if arachnida > 0:
        return "VECTOR_ARACHNID"
    if aves > 0 and plant_cnt >= aves:
        return "DIET_TRANSIT"
    if animal_other > 0 and plant_cnt >= animal_other:
        return "DIET_TRANSIT"
    if plant_cnt <= 3:
        return "RESIDUAL"
    return "OTHER"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cross_species_dir", default="classified_clean/cross_species/")
    p.add_argument("--classified_dir", default="classified_clean/")
    p.add_argument("--output_dir", "-o", default="cross_analysis/")
    args = p.parse_args()

    cs_dir = args.cross_species_dir
    l7_files = [f for f in os.listdir(cs_dir) if f.endswith('_plant_cross_species.tsv')]
    if not l7_files:
        print(f"No *_plant_cross_species.tsv files in {cs_dir}"); return

    os.makedirs(args.output_dir, exist_ok=True)

    # Load all L7 records
    df_list = []
    for l7f in l7_files:
        source_cat = l7f.replace('_plant_cross_species.tsv', '')
        df = pl.read_csv(os.path.join(cs_dir, l7f), separator='\t', truncate_ragged_lines=True)
        df = df.with_columns(pl.lit(source_cat).alias("Source_Category"))
        df_list.append(df)
    df_l7 = pl.concat(df_list)

    vp = pl.col("Virus_lineage") + ";;;;;;;;"
    df_l7 = df_l7.with_columns([
        vp.str.split(";").list.get(5).str.strip_chars().alias("V_Family"),
        vp.str.split(";").list.get(7).str.strip_chars().alias("V_Species"),
    ])
    l7_sps = set(df_l7["V_Species"].to_list()) - {""}
    sp_family = {r[0]: r[1] for r in df_l7.group_by(["V_Species","V_Family"]).len().iter_rows()}

    print(f"Cross-species files: {len(l7_files)} -> {df_l7.height} records")
    print(f"Unique species: {len(l7_sps)}")
    for r in df_l7.group_by("Source_Category").len().sort("len",descending=True).iter_rows():
        src_sp = len(set(df_l7.filter(pl.col("Source_Category")==r[0])["V_Species"].to_list()))
        print(f"  {str(r[0]):20s}: {r[1]:>8,d} records / {src_sp:>4d} species")

    # Fast count: group_by instead of per-species filter
    sp_counts = defaultdict(lambda: defaultdict(int))
    for cat in CATS:
        cat_path = os.path.join(args.classified_dir, f"{cat}.tsv")
        if not os.path.exists(cat_path): continue
        df_c = pl.read_csv(cat_path, separator='\t', truncate_ragged_lines=True)
        vp_c = (pl.col("Virus_lineage") + ";;;;;;;;").str.split(";").list.get(7).str.strip_chars()
        df_c = df_c.with_columns(vp_c.alias("VS"))
        df_c = df_c.filter(pl.col("VS").is_in(list(l7_sps)))
        if df_c.height == 0: continue
        for r in df_c.group_by("VS").len().iter_rows():
            sp_counts[r[0]][cat] = r[1]

    # Plant counts
    plant_path = os.path.join(args.classified_dir, "Plant.tsv")
    if os.path.exists(plant_path):
        df_plant = pl.read_csv(plant_path, separator='\t', truncate_ragged_lines=True)
        vp_p = (pl.col("Virus_lineage") + ";;;;;;;;").str.split(";").list.get(7).str.strip_chars()
        df_plant = df_plant.with_columns(vp_p.alias("VS"))
        df_plant = df_plant.filter(pl.col("VS").is_in(list(l7_sps)))
        for r in df_plant.group_by("VS").len().iter_rows():
            sp_counts[r[0]]["Plant"] = r[1]

    # Classify
    type_counts = defaultdict(list)
    detail_rows = []

    for sp in sorted(l7_sps):
        plant_cnt = sp_counts[sp].get("Plant", 0)
        cat_cnts = {c: sp_counts[sp].get(c, 0) for c in CATS}
        tp = classify(sp, plant_cnt, cat_cnts)
        type_counts[tp].append(sp)

        cats_present = sorted(c for c, v in cat_cnts.items() if v > 0)
        row = {"Cross_Type": tp, "Species": sp, "Family": sp_family.get(sp, ""),
               "Categories": " & ".join(cats_present), "Plant_Records": plant_cnt}
        for c in CATS:
            row[c] = cat_cnts.get(c, 0)
        detail_rows.append(row)

    # Print summary
    print(f"\n{'='*60}")
    print("CROSS-CATEGORY SPECIES CLASSIFICATION")
    print(f"{'='*60}")
    for tp in ["VECTOR_INSECT", "VECTOR_ARACHNID", "DIET_TRANSIT",
               "PLANT_FUNGI_SHARED", "RESIDUAL", "OTHER"]:
        sps = type_counts.get(tp, [])
        if sps:
            print(f"\n  {tp} ({len(sps)} species):")
            for sp in sorted(sps)[:5]:
                cnts = sp_counts[sp]
                cat_str = ", ".join(f"{c}={cnts[c]}" for c in sorted(cnts))
                print(f"    {sp[:50]:50s}  {cat_str}")
            if len(sps) > 5:
                print(f"    ... +{len(sps)-5} more")

    # Save detail
    detail_path = os.path.join(args.output_dir, "cross_species_analysis.tsv")
    fn = ["Cross_Type","Species","Family","Categories","Plant_Records"] + CATS
    with open(detail_path, 'w', newline='') as f:
        w = csv.DictWriter(f, delimiter='\t', fieldnames=fn)
        w.writeheader(); w.writerows(detail_rows)
    print(f"\nDetail: {detail_path}")


if __name__ == "__main__":
    main()
