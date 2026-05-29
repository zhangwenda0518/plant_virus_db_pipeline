# -*- coding: utf-8 -*-
"""
C4: Clean all host-category TSVs using multi-layer rule-based filtering.
L1-L6: remove data errors (wrong host, genus collision, phage, pathogen, placeholder).
L7: MANDATORY — Plant species that appear in other categories are removed from
    Plant_clean but saved to cross_species/ for C8 analysis.
    These are NOT errors — they're legitimate plant viruses detected in vectors,
    diet transit, etc. They're separated for cross-kingdom analysis.

Usage:
  python C4_clean_all_tsvs.py -i classified/ -o classified_clean/ -v VMR_MSL41.tsv
  -v/--vmr: (optional) ICTV VMR for genus-level cross-kingdom validation
"""
import polars as pl
import os, argparse, sys
from collections import defaultdict

# =====================================================================
# ICTV VMR Integration: Genus-level host range lookup
# =====================================================================

# ICTV Host source → C4 category
_VMR_HOST_MAP = {
    'plants': 'Plant', 'fungi': 'Fungi', 'bacteria': 'Bacteria',
    'archaea': 'Archaea', 'invertebrates': 'Invertebrate',
    'vertebrates': 'Vertebrate', 'protists': 'Protist',
    'algae': 'Plant', 'oomycetes': 'Oomycetes',
}
_VMR_ENV_SOURCES = {'soil', 'unknown', 'freshwater', 'marine',
                     'sewage', 'air', 'phytobiome'}


def _parse_vmr_host(host_str):
    """Parse ICTV Host source → (categories_list, has_S_flag)."""
    h = host_str.strip().lower()
    if not h:
        return [], False
    has_S = '(s)' in h
    h = h.replace('(s)', '').strip()
    cats = []
    for part in h.split(','):
        p = part.strip()
        if not p or p in _VMR_ENV_SOURCES:
            continue
        m = _VMR_HOST_MAP.get(p)
        if m:
            cats.append(m)
    return cats, has_S


def build_ictv_lookup(vmr_path):
    """
    Parse VMR_MSL41 to build ICTV genus→host lookup.
    Returns dict: genus → {'confirmed': set, 'env': set, 'family': str}
    """
    if not vmr_path or not os.path.exists(vmr_path):
        print(f"  [WARN] VMR not found: {vmr_path}, ICTV check disabled")
        return {}

    print(f"\nLoading ICTV VMR: {vmr_path}")
    vmr = pl.read_csv(vmr_path, separator='\t', ignore_errors=True,
                      truncate_ragged_lines=True, encoding='latin1')

    lookup = {}
    for r in vmr.iter_rows(named=True):
        genus = str(r.get('Genus', '')).strip()
        host = str(r.get('Host source', '')).strip()
        family = str(r.get('Family', '')).strip()
        if not genus:
            continue
        cats, has_S = _parse_vmr_host(host)
        if not cats:
            continue
        if genus not in lookup:
            lookup[genus] = {'confirmed': set(), 'env': set(), 'family': family}
        if has_S:
            lookup[genus]['env'].update(cats)
        else:
            lookup[genus]['confirmed'].update(cats)

    n_plant = sum(1 for g, v in lookup.items() if 'Plant' in v['confirmed'])
    n_cross = sum(1 for g, v in lookup.items() if len(v['confirmed']) >= 2)
    print(f"  ICTV genera: {len(lookup)} total, {n_plant} with Plant, {n_cross} cross-kingdom")
    return lookup


def ictv_has_host(lookup, genus, host_category):
    """Check if ICTV confirms this genus in the given host category."""
    if not lookup or genus not in lookup:
        return None  # Unknown — no ICTV record
    return host_category in lookup[genus]['confirmed']


def ictv_is_cross_kingdom(lookup, genus):
    """Check if ICTV confirms this genus in MULTIPLE host categories."""
    if not lookup or genus not in lookup:
        return None
    return len(lookup[genus]['confirmed']) >= 2

# =====================================================================

CATEGORY_KINGDOM = {
    "Plant": "Viridiplantae", "Fungi": "Fungi",
    "Bacteria": None, "Insecta": "Metazoa", "Arachnida": "Metazoa",
    "Mammalia": "Metazoa", "Aves": "Metazoa", "Human": "Metazoa",
    "Animal_other": "Metazoa", "Oomycetes": None, "Protist": None,
    "Archaea": None, "Environmental_NCBI": None, "Unknown": None,
}

GENUS_COLLISIONS = {"Coelogyne", "Mansonia", "Charybdis", "Paphia", "Epiphyllum",
                    "Acharia"}  # plant genus (Achariaceae) vs moth genus (Limacodidae)

ANIMAL_VIRUS_SPECIES = {"Galvornvirus isengard", "Hubei picorna-like virus 55"}

ALGAL_GENERA = {"Micromonas", "Tetradesmus", "Tetraselmis", "Picochlorum",
                "Dunaliella", "Chlorella", "Ulva", "Ostreococcus", "Bathycoccus"}

PROTIST_COLLISION_SPECIES = {"Orthotospovirus tomatomaculae", "Sagittaria virus A"}

# =====================================================================
# C4 Taxonomy Rule Dictionaries (Based on Deep Metagenomic Validations)
# =====================================================================

# 1. Absolute fungal/oomycete virus family blacklist
# NOTE: Fusagraviridae moved OUT of this list — it contains plant viruses
#       (Fusagravirus roku / Fusagravirus kyu = papaya meleira virus PMeV).
#       Fusagravirus is handled at genus level (L4b) with ICTV dynamic rescue.
FUNGAL_FAMILIES = {
    "Chrysoviridae", "Oomyviridae", "Hypoviridae", "Mitoviridae",
    "Mymonaviridae", "Gammaflexiviridae", "Deltaflexiviridae",
    "Spiciviridae", "Botryosphaeriviridae",
    "Fusariviridae", "Hadakaviridae", "Yadokariviridae",
    "Polymycoviridae", "Megabirnaviridae", "Quadriviridae", "Barnaviridae",
}

# 2. Absolute invertebrate/insect virus family blacklist
INSECT_FAMILIES = {
    "Dicistroviridae", "Iflaviridae", "Baculoviridae", "Polydnaviridae",
    "Nimaviridae", "Tetraviridae", "Nodaviridae", "Mesoniviridae",
    "Xinmoviridae", "Bidnaviridae", "Hytrosaviridae",
    "Parvoviridae", "Artoviridae",
}

# 3. Phage families (missed by L3 name check "phage")
PHAGE_FAMILIES = {
    "Fiersviridae", "Microviridae", "Steitzviridae", "Duinviridae",
    "Straboviridae", "Autographiviridae", "Herelleviridae",
    "Peduoviridae", "Zierdtviridae",
}

OOMYCETE_FAMILIES = {"Oomyviridae", "Discoviridae"}

# 4. Genus-level blacklist for MIXED families (family has plant AND fungal genera)
# 4. Genus-level blacklist for MIXED families (family has plant AND fungal genera)
FUNGAL_GENERA = {
    "Bocivirus", "Laulavirus", "Coguvirus", "Rubodvirus",
    "Orthodiscovirus", "Penoulivirus", "Scleroulivirus", "Botybirnavirus",
    "Magoulivirus", "Botrytimonavirus", "Fusagravirus",
    "Gammapartitivirus", "Epsilonpartitivirus",
    "Betaendornavirus", "Victorivirus", "Totivirus", "Mycoreovirus",
    "Duamitovirus", "Unuamitovirus",
    "Sclerotimonavirus", "Penicillimonavirus", "Alphachrysovirus",
    "Deltaflexivirus", "Gammaflexivirus", "Hubramonavirus",
}
# Note: Ourmiavirus intentionally NOT in FUNGAL_GENERA — it IS a true plant virus genus
# Note: Fusagravirus was moved here from FUNGAL_FAMILIES. L4b ICTV check preserves
#        plant-infecting species (Fusagravirus roku / Fusagravirus kyu = PMeV).
#        Fungal/omycete Fusagravirus species (e.g. Fusagravirus sani) ARE removed.

# Fallback without ICTV: genera that have known plant hosts and must NEVER be
# removed from Plant even when VMR is not available.
NO_VMR_PLANT_KEEP = {
    "Fusagravirus", "Laulavirus", "Penoulivirus", "Magoulivirus",
    "Orthodiscovirus", "Duamitovirus", "Totivirus",
}

# 4b. True plant genera in mixed families (for reverse contamination L4f)
TRUE_PLANT_GENERA = {
    "Ourmiavirus",          # Botourmiaviridae — true plant virus, fungal records are contamination
    "Maculavirus",          # Tymoviridae — plant-only, insect records are vector detection
}
# NOTE: Alphapartitivirus, Betapartitivirus, Alphaendornavirus intentionally NOT included.

# Insect-contaminant genera: plant/fungal genera whose presence in Insecta
# represents dietary transit or environmental contamination, NOT infection.
INSECT_EXCLUDED_GENERA = {
    "Alphapartitivirus",    # Partitiviridae — plant+fungal virus, mosquito records are dietary transit
}
# NOTE: Fijivirus/Phytoreovirus/Oryzavirus intentionally NOT included.
# They have legitimate insect-specific species (e.g., Fijivirus nilaparvatae
# infects Nilaparvata lugens). Including them would wrongly delete real insect
# reoviruses from Insecta.tsv. Their rare occurrence in Fungi/Animal_other
# is handled by L7 (species-level cross-check).

# 5. Non-plant genera (insect/animal/environmental viruses)
NON_PLANT_GENERA = {
    "Iteradensovirus", "Galvornvirus", "Mihkrovirus",
    "Vegetivirus", "Demetevirus", "Persevirus", "Shanivirus",
}

# 6. Reverse contamination: plant families misassigned to Fungi/Oomycetes
TRUE_PLANT_FAMILIES = {
    "Tombusviridae", "Virgaviridae", "Potyviridae", "Secoviridae",
    "Bromoviridae", "Closteroviridae",
}

# 7. Environmental CRESS-DNA (ubiquitous background, not host-specific)
ENVIRONMENTAL_FAMILIES = {
    "Circoviridae", "Genomoviridae", "Kanorauviridae",
    "Ouroboviridae", "Draupnirviridae", "Smacoviridae",
}
TRUE_PLANT_CRESS_FAMILIES = {"Geminiviridae", "Nanoviridae"}

VECTOR_GENERA_IN_PLANT = {
    # Plant virus genera whose presence in Insecta/Arachnida
    # is vector detection — kept in Plant, removed from Insect/Arachnid
}

# PATHOGEN_GENERA (virus name pattern matching — L4)
PATHOGEN_GENERA = [
    "Botrytis", "Sclerotinia", "Alternaria", "Fusarium", "Erysiphe",
    "Pyricularia", "Magnaporthe", "Leveillula", "Botryosphaeria",
    "Diaporthe", "Verticillium", "Ceratobasidium",
    "Plasmopara", "Sclerophthora", "Phytophthora", "Pythium",
    "Downy mildew", "Neomarica",
    "Erysiphales",
]

VALID_CATEGORIES = set(CATEGORY_KINGDOM.keys())


def add_parsed_cols(df):
    hp = pl.col("Host_lineage") + ";;;;;;;;"
    vp = pl.col("Virus_lineage") + ";;;;;;;;"
    return df.with_columns([
        hp.str.split(";").list.get(1).str.strip_chars().alias("_H_Kingdom"),
        hp.str.split(";").list.get(3).str.strip_chars().alias("_H_Class"),
        hp.str.split(";").list.get(6).str.strip_chars().alias("_H_Genus"),
        vp.str.split(";").list.get(5).str.strip_chars().alias("_V_Family"),
        vp.str.split(";").list.get(6).str.strip_chars().alias("_V_Genus"),
        vp.str.split(";").list.get(7).str.strip_chars().alias("_V_Species"),
    ])


def clean_one_file(input_path, output_path, category_name, miss_dir,
                   cross_species_dir=None, ictv_lookup=None):
    """Clean one host-category TSV. ictv_lookup is the ICTV genus→host dict."""
    print(f"\n{'='*60}")
    print(f"Cleaning: {category_name}")
    print(f"{'='*60}")

    df = pl.read_csv(input_path, separator='\t', truncate_ragged_lines=True)
    df = add_parsed_cols(df)
    total = df.height
    removed_log = []

    # L1: Kingdom
    expected = CATEGORY_KINGDOM.get(category_name)
    if expected:
        l1 = df.filter((pl.col("_H_Kingdom") != expected) | (pl.col("_H_Kingdom") == ""))
        df = df.filter((pl.col("_H_Kingdom") == expected) & (pl.col("_H_Kingdom") != ""))
        removed_log.append(("L1_kingdom", l1))
        print(f"  L1: removed {l1.height} (kingdom != '{expected}' or empty)")
    elif category_name == "Bacteria":
        l1 = df.filter(pl.col("_H_Kingdom") == "")
        df = df.filter(pl.col("_H_Kingdom") != "")
        removed_log.append(("L1_kingdom", l1))
        print(f"  L1: removed {l1.height} (empty kingdom)")
    else:
        print(f"  L1: skipped")

    # L2: Genus collisions
    l2 = df.filter(pl.col("_H_Genus").is_in(list(GENUS_COLLISIONS)))
    df = df.filter(~pl.col("_H_Genus").is_in(list(GENUS_COLLISIONS)))
    removed_log.append(("L2_collision", l2))
    if l2.height > 0:
        print(f"  L2: removed {l2.height} (genus collisions)")

    # L2b: Non-plant virus genera (insect/animal viruses in Plant)
    if category_name == "Plant":
        l2b = df.filter(
            pl.col("_V_Species").is_in(list(ANIMAL_VIRUS_SPECIES)) |
            pl.col("_V_Genus").is_in(list(NON_PLANT_GENERA))
        )
        df = df.filter(
            ~pl.col("_V_Species").is_in(list(ANIMAL_VIRUS_SPECIES)) &
            ~pl.col("_V_Genus").is_in(list(NON_PLANT_GENERA))
        )
        removed_log.append(("L2b_non_plant_taxon", l2b))
        if l2b.height > 0:
            print(f"  L2b: removed {l2b.height} (non-plant genus/species)")
            sps = l2b.group_by("_V_Genus").len().sort("len",descending=True)
            for r in sps.head(8).iter_rows():
                print(f"      - {str(r[0]):35s} count={r[1]}")

    # L2c: Algal hosts
    if category_name == "Plant":
        l2c = df.filter(pl.col("_H_Genus").is_in(list(ALGAL_GENERA)))
        df = df.filter(~pl.col("_H_Genus").is_in(list(ALGAL_GENERA)))
        removed_log.append(("L2c_algal", l2c))
        if l2c.height > 0:
            print(f"  L2c: removed {l2c.height} (algal hosts)")

    # L2d: Protist collision
    if category_name == "Plant":
        l2d = df.filter(pl.col("_V_Species").is_in(list(PROTIST_COLLISION_SPECIES)))
        df = df.filter(~pl.col("_V_Species").is_in(list(PROTIST_COLLISION_SPECIES)))
        removed_log.append(("L2d_protist", l2d))
        if l2d.height > 0:
            print(f"  L2d: removed {l2d.height} (protist collision)")

    # L3: Phage
    if category_name != "Bacteria":
        l3 = df.filter(
            pl.col("Virus_Name").str.to_lowercase().str.contains("phage") |
            pl.col("_V_Family").is_in(list(PHAGE_FAMILIES))
        )
        df = df.filter(
            ~pl.col("Virus_Name").str.to_lowercase().str.contains("phage") &
            ~pl.col("_V_Family").is_in(list(PHAGE_FAMILIES))
        )
        removed_log.append(("L3_phage", l3))
        if l3.height > 0:
            print(f"  L3: removed {l3.height} (phage by name or phage family)")
            fps = l3.group_by("_V_Family").len().sort("len",descending=True)
            for r in fps.head(6).iter_rows():
                print(f"      - {str(r[0]):35s} count={r[1]}")

    MACRO_HOSTS = {"Plant", "Insecta", "Arachnida", "Animal_other", "Aves", "Mammalia", "Human"}

    # L4a: Family-level blacklist (all macro-hosts, not just Plant)
    if category_name in MACRO_HOSTS:
        black_fams = FUNGAL_FAMILIES | OOMYCETE_FAMILIES | PHAGE_FAMILIES
        if category_name == "Plant":
            black_fams |= INSECT_FAMILIES
        l4a = df.filter(pl.col("_V_Family").is_in(list(black_fams)))
        df = df.filter(~pl.col("_V_Family").is_in(list(black_fams)))
        removed_log.append(("L4a_blacklist_family", l4a))
        if l4a.height > 0:
            print(f"  L4a: removed {l4a.height} (non-host family)")
            for r in l4a.group_by("_V_Family").len().sort("len",descending=True).head(8).iter_rows():
                print(f"      - {str(r[0]):35s} count={r[1]}")

    # L4b: Genus-level filter for mixed families (all macro-hosts)
    # Dynamic ICTV check: for each genus in FUNGAL_GENERA, if ICTV confirms it
    # in the CURRENT host category, keep it (it's a legitimate host, not contamination).
    # This handles: Plant (plant+fungi genera), Arachnida (invertebrate-associated),
    # Insecta (insect-associated Laulavirus), etc.
    if category_name in MACRO_HOSTS:
        # Map current C4 category to ICTV broad category
        if category_name == 'Plant':
            cur_ictv = 'Plant'
        elif category_name in ('Insecta', 'Arachnida'):
            cur_ictv = 'Invertebrate'
        elif category_name in ('Mammalia', 'Aves', 'Human', 'Animal_other'):
            cur_ictv = 'Vertebrate'
        else:
            cur_ictv = category_name

        if ictv_lookup:
            fg_keep = set()
            for g in FUNGAL_GENERA:
                if g in ictv_lookup and cur_ictv in ictv_lookup[g]['confirmed']:
                    fg_keep.add(g)
            fg_remove = list(FUNGAL_GENERA - fg_keep)
            if fg_keep:
                print(f"  L4b ICTV: keeping {sorted(fg_keep)} in {category_name} (ICTV-confirmed {cur_ictv} host)")
        else:
            # No VMR fallback: still protect genera with known plant hosts
            if category_name == 'Plant':
                fg_remove = [g for g in FUNGAL_GENERA if g not in NO_VMR_PLANT_KEEP]
            else:
                fg_remove = list(FUNGAL_GENERA)
        l4b = df.filter(pl.col("_V_Genus").is_in(fg_remove))
        df = df.filter(~pl.col("_V_Genus").is_in(fg_remove))
        removed_log.append(("L4b_fungal_genus", l4b))
        if l4b.height > 0:
            print(f"  L4b: removed {l4b.height} (fungal genus in mixed family)")
            for r in l4b.group_by("_V_Genus").len().sort("len",descending=True).head(8).iter_rows():
                print(f"      - {str(r[0]):35s} count={r[1]}")

    # L4c: Pathogen keyword matching (all macro-hosts)
    if category_name in MACRO_HOSTS:
        vn_l = pl.col("Virus_Name").str.to_lowercase()
        l4c = df.filter(pl.any_horizontal([vn_l.str.contains(g.lower()) for g in PATHOGEN_GENERA]))
        df = df.filter(~pl.any_horizontal([vn_l.str.contains(g.lower()) for g in PATHOGEN_GENERA]))
        removed_log.append(("L4c_pathogen_name", l4c))
        if l4c.height > 0:
            print(f"  L4c: removed {l4c.height} (pathogen keyword in Virus_Name)")

    # L4d: Insect family/genera + phage families from non-target categories
    if category_name in ("Plant", "Fungi"):
        l4d = df.filter(
            pl.col("_V_Family").is_in(list(INSECT_FAMILIES)) |
            pl.col("_V_Genus").is_in(list(NON_PLANT_GENERA))
        )
        df = df.filter(
            ~pl.col("_V_Family").is_in(list(INSECT_FAMILIES)) &
            ~pl.col("_V_Genus").is_in(list(NON_PLANT_GENERA))
        )
        removed_log.append(("L4d_insect_taxon", l4d))
        if l4d.height > 0:
            print(f"  L4d: removed {l4d.height} (insect family/genus in {category_name})")

    # L4e: Environmental CRESS-DNA isolation (all macro-hosts)
    if category_name in MACRO_HOSTS:
        l4e = df.filter(
            pl.col("_V_Family").is_in(list(ENVIRONMENTAL_FAMILIES)) &
            ~pl.col("_V_Family").is_in(list(TRUE_PLANT_CRESS_FAMILIES))
        )
        df = df.filter(
            ~pl.col("_V_Family").is_in(list(ENVIRONMENTAL_FAMILIES)) |
            pl.col("_V_Family").is_in(list(TRUE_PLANT_CRESS_FAMILIES))
        )
        removed_log.append(("L4e_env_CRESS", l4e))
        if l4e.height > 0:
            print(f"  L4e: removed {l4e.height} (environmental CRESS-DNA)")

    # L4f: Reverse contamination & dietary transit.
    # True plant viruses (family OR genus) in Fungi/Oomycetes/non-vector animals.
    # Excludes Insecta — insect vectors legitimately carry plant viruses (handled by L7).
    # ICTV check: if ICTV confirms genus ALSO in target category, keep it (e.g. plant+fungi genus in Fungi)
    if category_name in ("Fungi", "Oomycetes", "Animal_other", "Arachnida", "Aves", "Mammalia"):
        tp_fams = list(TRUE_PLANT_FAMILIES)
        tp_gens = list(TRUE_PLANT_GENERA)
        if ictv_lookup:
            # Remove genera from the filter if ICTV confirms them in this category
            cat_broad = category_name
            if cat_broad in ('Arachnida', 'Animal_other', 'Aves', 'Mammalia'):
                cat_broad = 'Vertebrate' if cat_broad not in ('Arachnida',) else 'Invertebrate'
            ictv_skip = {g for g in tp_gens if g in ictv_lookup
                         and cat_broad in ictv_lookup[g]['confirmed']}
            tp_gens = [g for g in tp_gens if g not in ictv_skip]
            if ictv_skip:
                print(f"  L4f ICTV: skipping {sorted(ictv_skip)} in {category_name} (ICTV-confirmed host)")
        l4f = df.filter(
            pl.col("_V_Family").is_in(tp_fams) |
            pl.col("_V_Genus").is_in(tp_gens)
        )
        df = df.filter(
            ~pl.col("_V_Family").is_in(tp_fams) &
            ~pl.col("_V_Genus").is_in(tp_gens)
        )
        removed_log.append(("L4f_reverse_plant", l4f))
        if l4f.height > 0:
            print(f"  L4f: removed {l4f.height} (true plant virus in {category_name})")
            for r in l4f.group_by("_V_Genus").len().sort("len",descending=True).head(5).iter_rows():
                print(f"      - {str(r[0]):35s} count={r[1]}")

    # L4g: Remove plant/fungal genera from Insecta (dietary transit / environmental contamination).
    # ICTV check: if ICTV confirms genus in Invertebrate, keep it in Insecta (legitimate insect host)
    if category_name == "Insecta":
        ig_remove = list(INSECT_EXCLUDED_GENERA)
        if ictv_lookup:
            ig_skip = {g for g in ig_remove if g in ictv_lookup
                       and 'Invertebrate' in ictv_lookup[g]['confirmed']}
            ig_remove = [g for g in ig_remove if g not in ig_skip]
            if ig_skip:
                print(f"  L4g ICTV: keeping {sorted(ig_skip)} in Insecta (ICTV-confirmed invertebrate host)")
        l4g = df.filter(pl.col("_V_Genus").is_in(ig_remove))
        df = df.filter(~pl.col("_V_Genus").is_in(ig_remove))
        removed_log.append(("L4g_insect_contaminant", l4g))
        if l4g.height > 0:
            print(f"  L4g: removed {l4g.height} (non-insect genus in Insecta)")
            for r in l4g.group_by("_V_Genus").len().sort("len",descending=True).head(5).iter_rows():
                print(f"      - {str(r[0]):35s} count={r[1]}")

    # L4h: ICTV-based host verification for non-Plant categories.
    # If ICTV knows this genus (has Plant records), but does NOT confirm the current
    # category as a host → contamination (e.g., Fijivirus in Fungi).
    # Only applies when ICTV has confirmed records (non-S) for the genus.
    if category_name != "Plant" and ictv_lookup and \
       category_name in (MACRO_HOSTS | {"Fungi"}):
        # Map C4 category to ICTV broad category
        if category_name in ('Insecta', 'Arachnida'):
            ictv_cat = 'Invertebrate'
        elif category_name in ('Aves', 'Mammalia', 'Human', 'Animal_other'):
            ictv_cat = 'Vertebrate'
        elif category_name == 'Oomycetes':
            ictv_cat = None  # VMR has no oomycetes category, skip L4h
        else:
            ictv_cat = category_name  # Fungi, Protist, Bacteria, Archaea

        # Collect genera to remove: ICTV knows them, confirms Plant, but NOT ictv_cat
        h_remove = set()
        if ictv_cat is not None:
            for g in set(df['_V_Genus'].to_list()):
                if g and g in ictv_lookup and g not in h_remove:
                    info = ictv_lookup[g]
                    if 'Plant' in info['confirmed'] and ictv_cat not in info['confirmed']:
                        h_remove.add(g)

        if h_remove:
            l4h = df.filter(pl.col("_V_Genus").is_in(list(h_remove)))
            df = df.filter(~pl.col("_V_Genus").is_in(list(h_remove)))
            removed_log.append(("L4h_ictv_verify", l4h))
            if l4h.height > 0:
                print(f"  L4h ICTV: removed {l4h.height} (genus not ICTV-confirmed in {category_name})")
                for r in l4h.group_by("_V_Genus").len().sort("len",descending=True).head(5).iter_rows():
                    ictv_hosts = ','.join(sorted(ictv_lookup.get(str(r[0]), {}).get('confirmed', set())))
                    print(f"      - {str(r[0]):35s} count={r[1]:>4d}  ICTV={ictv_hosts}")

    # L5: Placeholder species
    vs = pl.col("_V_Species")
    is_ph = (vs.str.contains(r"sp\.\s*$") | vs.str.to_lowercase().str.starts_with("uncultured") |
             vs.str.to_lowercase().str.starts_with("unidentified") | (vs == "Virus sp."))
    l5 = df.filter(is_ph)
    df = df.filter(~is_ph)
    removed_log.append(("L5_placeholder", l5))
    if l5.height > 0:
        print(f"  L5: removed {l5.height} (placeholder species)")

    # L6: Phage lineages — remove from all macro-hosts, not just Plant
    if category_name in MACRO_HOSTS:
        pls = {"Caudoviricetes", "Autographiviridae"}
        l6 = df.filter(pl.any_horizontal([pl.col("Virus_lineage").str.contains(t) for t in pls]))
        df = df.filter(~pl.any_horizontal([pl.col("Virus_lineage").str.contains(t) for t in pls]))
        removed_log.append(("L6_phage_lineage", l6))
        if l6.height > 0:
            print(f"  L6: removed {l6.height} (phage lineages: Caudoviricetes/Autographiviridae)")

    # L7: Cross-category species removal from NON-PLANT categories (upgraded).
    # Default: plant virus species in non-Plant categories → non-propagative contamination.
    # ICTV rescue: if ICTV confirms the species' genus as BOTH Plant AND current
    # category host → keep it (propagative dual-host, e.g. TSWV in Insecta).
    # Without VMR: fall back to aggressive species-level removal.
    if category_name != "Plant" and category_name in ("Insecta", "Arachnida", "Fungi",
            "Animal_other", "Aves"):
        input_dir = os.path.dirname(input_path) or '.'
        plant_path = os.path.join(input_dir, "Plant.tsv")
        if os.path.exists(plant_path) and category_name != "Plant":
            try:
                df_plant = pl.read_csv(plant_path, separator='\t', truncate_ragged_lines=True)
                vp_plant = (pl.col("Virus_lineage") + ";;;;;;;;").str.split(";").list.get(7).str.strip_chars()
                df_plant = df_plant.with_columns(vp_plant.alias("VS"))
                plant_sps = set(df_plant["VS"].to_list()) - {""}

                if ictv_lookup:
                    # Map current category to ICTV broad category
                    if category_name in ('Insecta', 'Arachnida'):
                        ictv_cat = 'Invertebrate'
                    elif category_name in ('Aves', 'Mammalia', 'Human', 'Animal_other'):
                        ictv_cat = 'Vertebrate'
                    else:
                        ictv_cat = category_name  # Fungi

                    # Rescue: keep plant species whose genus is ICTV-confirmed
                    # in BOTH Plant AND the current category (propagative dual-host)
                    keep_sps = set()
                    if ictv_cat is not None:
                        potential = df.filter(pl.col("_V_Species").is_in(list(plant_sps)))
                        for r in potential.iter_rows(named=True):
                            g = str(r.get('_V_Genus', '')).strip()
                            sp = str(r.get('_V_Species', '')).strip()
                            if g and g in ictv_lookup:
                                confirmed = ictv_lookup[g]['confirmed']
                                if 'Plant' in confirmed and ictv_cat in confirmed:
                                    keep_sps.add(sp)

                    remove_sps = [sp for sp in plant_sps if sp not in keep_sps]
                    if keep_sps:
                        print(f"  L7 ICTV: keeping {len(keep_sps)} propagative shared species in {category_name} "
                              f"(e.g., {sorted(list(keep_sps))[:4]})")
                else:
                    remove_sps = list(plant_sps)

                l7 = df.filter(pl.col("_V_Species").is_in(remove_sps))
                df = df.filter(~pl.col("_V_Species").is_in(remove_sps))
                removed_log.append(("L7_plant_cross_species", l7))
                print(f"  L7: removed {l7.height} records (plant virus species in {category_name} -> non-propagative contamination)")
                if l7.height > 0 and cross_species_dir:
                    os.makedirs(cross_species_dir, exist_ok=True)
                    orig_cols_l7 = [c for c in df.columns if not c.startswith("_")]
                    l7.select(orig_cols_l7).write_csv(
                        os.path.join(cross_species_dir, f"{category_name}_plant_cross_species.tsv"), separator='\t')
            except:
                print(f"  L7: skipped (Plant.tsv not found)")
        else:
            print(f"  L7: skipped (no Plant reference)")
    elif category_name == "Plant":
        print(f"  L7: skipped (Plant keeps all records; other categories will remove plant-shared species)")

    # Save
    orig_cols = [c for c in df.columns if not c.startswith("_")]
    df_clean = df.select(orig_cols)
    df_clean.write_csv(output_path, separator='\t')

    all_r = []
    for name, rdf in removed_log:
        if rdf.height > 0:
            rdf.select(orig_cols).write_csv(os.path.join(miss_dir, f"{category_name}_{name}.tsv"), separator='\t')
            all_r.append(rdf)
    if all_r:
        pl.concat(all_r, how="diagonal").select(orig_cols).write_csv(
            os.path.join(miss_dir, f"{category_name}_all_removed.tsv"), separator='\t')

    # (S) conflict check: flag genera with ICTV environmental-isolation records
    if ictv_lookup:
        s_conflicts = []
        for r in df.iter_rows(named=True):
            g = str(r.get('_V_Genus', '')).strip()
            if g and g in ictv_lookup and ictv_lookup[g]['env']:
                s_conflicts.append({
                    'Accession': str(r.get('Accession', '')),
                    'Virus_Name': str(r.get('Virus_Name', '')),
                    'Host_Name': str(r.get('Host_Name', '')),
                    'Virus_lineage': str(r.get('Virus_lineage', '')),
                    'Genus': g,
                    'ICTV_confirmed': ','.join(sorted(ictv_lookup[g]['confirmed'])),
                    'ICTV_env_S': ','.join(sorted(ictv_lookup[g]['env'])),
                    'Category': category_name,
                })
        if s_conflicts:
            sc_path = os.path.join(miss_dir, f"{category_name}_S_conflict.tsv")
            with open(sc_path, 'w') as f:
                f.write('\t'.join(s_conflicts[0].keys()) + '\n')
                for row in s_conflicts:
                    f.write('\t'.join(str(v) for v in row.values()) + '\n')
            print(f"  (S) conflict: {len(s_conflicts)} records with ICTV (S)-only host, saved to {os.path.basename(sc_path)}")

    final = df_clean.height
    print(f"  => {category_name}: {final:,} / {total:,} ({total-final:,} removed = {(total-final)/total*100:.1f}%)")
    return df_clean


def main():
    p = argparse.ArgumentParser(description="C4: Clean all host-category TSVs")
    p.add_argument("--input_dir", "-i", default="classified/")
    p.add_argument("--output_dir", "-o", default="classified_clean/")
    p.add_argument("--categories", default=None)
    p.add_argument("--vmr", "-v", default=None,
                   help="Path to ICTV VMR_MSL41.tsv for genus-level host cross-check")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    miss_dir = os.path.join(args.output_dir, "miss")
    os.makedirs(miss_dir, exist_ok=True)

    # Build ICTV genus host lookup
    ictv_lookup = build_ictv_lookup(args.vmr) if args.vmr else {}

    skipped = []
    if args.categories:
        files = [f.strip() for f in args.categories.split(",")]
    else:
        all_f = sorted(os.listdir(args.input_dir))
        files = [f for f in all_f if f.endswith('.tsv') and f.replace('.tsv','') in VALID_CATEGORIES]
        skipped = [f for f in all_f if f.endswith('.tsv') and f.replace('.tsv','') not in VALID_CATEGORIES]

    print(f"Input:  {args.input_dir}")
    print(f"Output: {args.output_dir}")
    print(f"Valid files: {len(files)}")
    if skipped:
        print(f"Skipped: {', '.join(skipped)}")

    for fname in files:
        cat = fname.replace('.tsv', '')
        in_path = os.path.join(args.input_dir, fname)
        out_path = os.path.join(args.output_dir, fname)
        if not os.path.exists(in_path):
            print(f"  SKIP: {fname} not found")
            continue
        l7_cats = {"Insecta", "Arachnida", "Fungi", "Animal_other", "Aves"}
        cross_dir = os.path.join(args.output_dir, "cross_species") if cat in l7_cats else None
        clean_one_file(in_path, out_path, cat, miss_dir, cross_species_dir=cross_dir,
                       ictv_lookup=ictv_lookup)

    print(f"\nDone. Cleaned files in {args.output_dir}/")
    print(f"Removed records in {miss_dir}/")


if __name__ == "__main__":
    main()
