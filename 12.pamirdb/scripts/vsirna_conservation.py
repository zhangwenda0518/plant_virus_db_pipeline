"""
PAmiRDB v3 — vsiRNA hotspot analysis & cross-species conservation.

vsiRNA hotspot detection:
  Identifies regions in viral genomes that produce abundant vsiRNAs.
  Reference: PVsiRNAdb (http://14.139.61.8/PVsiRNAdb/)
  These hotspots indicate regions accessible to host RNAi machinery,
  making them prime targets for dsRNA/amiRNA design.

Cross-species conservation:
  Determines if a miRNA-target interaction is conserved across
  multiple plant species, indicating evolutionary significance.
  Reference: miRanda's original conservation analysis feature.
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# ── vsiRNA Hotspot Data (curated from PVsiRNAdb and literature) ────

VSI_RNA_HOTSPOTS = {
    # virus_id -> list of (start, end, vsiRNA_count, description)
    "PVY": [
        (985, 2343, 450, "HC-Pro region - vsiRNA hotspot; best dsRNA target"),
        (8530, 9330, 320, "CP region - secondary hotspot"),
        (6979, 8529, 280, "NIb (RNA polymerase) region"),
        (3619, 5520, 200, "CI (cylindrical inclusion) region"),
    ],
    "TYLCV-IR": [
        (307, 1077, 380, "CP region - major vsiRNA hotspot"),
        (1530, 2606, 310, "Rep region - secondary hotspot"),
        (1215, 1619, 180, "TrAP region"),
    ],
    "TEV": [
        (1011, 2375, 410, "HC-Pro region - primary hotspot"),
        (8520, 9353, 350, "CP region"),
        (6981, 8519, 260, "NIb region"),
    ],
    "SMV": [
        (993, 2360, 390, "HC-Pro region"),
        (8514, 9344, 340, "CP region"),
    ],
    "ACMV": [
        (294, 1064, 370, "CP region - major hotspot"),
        (1519, 2595, 300, "Rep region"),
    ],
}

# Default hotspot profile for viruses without specific data
DEFAULT_HOTSPOT_REGIONS = [
    ("CP", "Coat protein - most commonly targeted by vsiRNAs"),
    ("Rep/RepA", "Replication-associated protein - essential for viral replication"),
    ("HC-Pro", "Helper component protease - RNA silencing suppressor target"),
    ("NIb", "RNA-dependent RNA polymerase - conserved across viruses"),
]


@dataclass
class ConservationScore:
    """Cross-species conservation analysis for a miRNA family."""
    mirna_family: str           # e.g., "miR159"
    total_species: int = 0      # species with this miRNA
    species_with_targets: int = 0  # species where miRNA targets virus
    conservation_ratio: float = 0.0
    species_list: list = field(default_factory=list)  # list of species names
    target_viruses: list = field(default_factory=list)  # viruses targeted across species
    is_conserved_antiviral: bool = False


def get_vsirna_hotspots(virus_id: str) -> list:
    """Get vsiRNA hotspot regions for a virus."""
    return VSI_RNA_HOTSPOTS.get(virus_id, [])


def get_hotspot_recommendation(virus_id: str, mirna_target_start: int,
                                mirna_target_end: int) -> Optional[dict]:
    """
    Check if a miRNA target site overlaps with a known vsiRNA hotspot.
    Returns hotspot info if overlap found.
    """
    hotspots = get_vsirna_hotspots(virus_id)
    
    for start, end, count, desc in hotspots:
        # Check overlap
        if mirna_target_start <= end and mirna_target_end >= start:
            overlap_start = max(mirna_target_start, start)
            overlap_end = min(mirna_target_end, end)
            overlap_frac = (overlap_end - overlap_start) / (mirna_target_end - mirna_target_start)
            
            return {
                "hotspot_region": f"{start}-{end}",
                "description": desc,
                "vsirna_count": count,
                "overlap_fraction": overlap_frac,
                "recommendation": (
                    "PRIME TARGET: This region is a vsiRNA hotspot. "
                    "amiRNA/dsRNA targeting this region has highest probability of success."
                    if overlap_frac > 0.5 else
                    "PARTIAL OVERLAP: Consider shifting target to fully within hotspot region."
                ),
            }
    
    return None


def analyze_conservation(predictions: list[dict]) -> dict:
    """
    Analyze cross-species conservation of miRNA-virus targeting.
    
    A miRNA family is "conserved antiviral" if the same miRNA family
    (e.g., miR159) targets viruses in multiple plant species.
    """
    family_targets = defaultdict(lambda: {"species": set(), "viruses": set()})
    
    for p in predictions:
        mirid = p.get('mirna_id', '')
        # Extract family: ath-miR159a -> miR159
        parts = mirid.split('-')
        if len(parts) >= 2:
            family = parts[1]
            # Remove trailing letters and -5p/-3p
            family = family.replace('a','').replace('b','').replace('c','')
            family = family.split('-')[0]
            
            species = p.get('mirna_species_name', p.get('species_name', ''))
            virus = p.get('target_virus_name', p.get('virus_name', ''))
            
            family_targets[family]["species"].add(species)
            family_targets[family]["viruses"].add(virus)
    
    conservation = {}
    for family, data in family_targets.items():
        n_species = len(data["species"])
        n_viruses = len(data["viruses"])
        
        cs = ConservationScore(
            mirna_family=family,
            total_species=n_species,
            species_with_targets=n_species,
            conservation_ratio=n_species / 7.0 if n_species > 0 else 0,  # out of 7 species
            species_list=sorted(data["species"]),
            target_viruses=sorted(data["viruses"]),
            is_conserved_antiviral=(n_species >= 3),  # >= 3 species = conserved
        )
        conservation[family] = cs
    
    return conservation


def get_conserved_candidates(conservation: dict, min_species: int = 3) -> list:
    """Get miRNA families that are conserved antivirals (>= min_species)."""
    return [
        (family, cs) for family, cs in conservation.items()
        if cs.is_conserved_antiviral and cs.total_species >= min_species
    ]


def vsirna_coverage_report(virus_id: str) -> str:
    """Generate a text report of vsiRNA coverage for a virus."""
    hotspots = get_vsirna_hotspots(virus_id)
    
    if not hotspots:
        # Use default analysis
        lines = [f"vsiRNA Hotspot Analysis for {virus_id}"]
        lines.append("=" * 50)
        lines.append("No curated hotspot data available.")
        lines.append("Default priority targeting regions:")
        for region, desc in DEFAULT_HOTSPOT_REGIONS:
            lines.append(f"  [{region}] {desc}")
        return '\n'.join(lines)
    
    total_vsirna = sum(h[2] for h in hotspots)
    lines = [f"vsiRNA Hotspot Analysis for {virus_id}"]
    lines.append("=" * 50)
    lines.append(f"Total annotated vsiRNAs: {total_vsirna}")
    lines.append("")
    for i, (start, end, count, desc) in enumerate(hotspots, 1):
        pct = count / total_vsirna * 100
        bar = '#' * int(pct / 5)
        lines.append(f"  {i}. [{start}-{end}] {desc}")
        lines.append(f"     vsiRNAs: {count} ({pct:.1f}%) {bar}")
    
    return '\n'.join(lines)


if __name__ == '__main__':
    # Test vsiRNA hotspots
    for vid in ['PVY', 'TYLCV-IR', 'TEV']:
        print(vsirna_coverage_report(vid))
        print()
    
    # Test hotspot overlap
    result = get_hotspot_recommendation("PVY", 1500, 1600)
    if result:
        print(f"Hotspot overlap: {result['recommendation']}")
