"""
PAmiRDB v4.4 — TAPIR target accessibility scoring.

TAPIR (Target Prediction for Plant miRNAs):
  Bonnet et al. (2012) "TAPIR, a web server for the prediction of
  plant microRNA targets..."

TAPIR uniquely evaluates:
  1. Seed region complementarity (like other tools)
  2. Target mRNA secondary structure ACCESSIBILITY
     — is the target site buried or exposed?
  3. miRNA:target duplex free energy

Key insight: Even if a miRNA is perfectly complementary to a target,
if the target region is locked in secondary structure, binding is
energetically unfavorable.

Our implementation:
  1. Compute target region accessibility score (0-100)
  2. Combine with complementarity score
  3. Produce integrated TAPIR score
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TAPIRResult:
    """TAPIR target prediction result."""
    mirna_id: str
    target_id: str
    seed_score: float            # seed region complementarity (0-100)
    accessibility_score: float    # target accessibility (0-100)
    energy_score: float           # duplex energy contribution
    tapir_score: float            # combined score (0-100, higher = better)
    target_region_structure: str  # dot-bracket of target region
    up_energy: float              # energy to open target site
    passes: bool
    consensus_votes: int = 0


def _is_wc(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('A', 'U'), ('U', 'A'), ('G', 'C'), ('C', 'G')}


def _is_wobble(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('G', 'U'), ('U', 'G')}


def compute_accessibility(target_seq: str, site_start: int,
                           site_end: int, flank_width: int = 70) -> dict:
    """
    Compute target site accessibility.
    
    Uses ViennaRNA to fold the target region (including flanks)
    and determine if the binding site is in a single-stranded
    (accessible) or double-stranded (inaccessible) state.
    
    Returns:
      accessibility: fraction of target site that is unpaired
      up_energy: energy required to open the target site
      structure: dot-bracket of the region
    """
    target = target_seq.upper().replace('T', 'U')
    
    # Extract region with flanks
    flank_start = max(0, site_start - flank_width)
    flank_end = min(len(target), site_end + flank_width)
    region = target[flank_start:flank_end]
    
    # Adjust site coordinates to regional
    reg_start = site_start - flank_start
    reg_end = site_end - flank_start
    
    # Fold the region
    try:
        import RNA
        fc = RNA.fold_compound(region)
        (structure, mfe) = fc.mfe()
        
        # Compute energy required to open the binding site
        # Constrain the binding site to be unpaired
        constraints = '.' * len(region)
        constraints = (constraints[:reg_start] +
                      'x' * (reg_end - reg_start) +
                      constraints[reg_end:])
        
        fc2 = RNA.fold_compound(region)
        # Soft-constrain: force site to be unpaired
        for i in range(reg_start, reg_end):
            fc2.add_constraints([(i + 1, i + 1, 0, 0)])  # force unpaired
        
        (constrained_struct, constrained_mfe) = fc2.mfe()
        up_energy = constrained_mfe - mfe
        
    except ImportError:
        # Fallback: estimate accessibility from sequence composition
        region_seq = region[reg_start:reg_end]
        gc = sum(1 for c in region_seq if c in 'GC')
        # GC-rich regions tend to be more structured (less accessible)
        accessibility = 1.0 - (gc / len(region_seq)) if region_seq else 0.5
        structure = '.' * len(region)
        up_energy = gc * 0.5  # approximate: GC pairs cost ~0.5 kcal to open
    
    else:
        # Count unpaired bases in the site
        site_struct = structure[reg_start:reg_end]
        unpaired = sum(1 for c in site_struct if c == '.')
        total = len(site_struct)
        accessibility = unpaired / total if total > 0 else 0.5
    
    return {
        "accessibility": accessibility,
        "up_energy": up_energy,
        "structure": structure,
        "region_start": flank_start,
        "region_end": flank_end,
    }


def compute_seed_score(mirna_seq: str, target_seq: str,
                        site_start: int, site_end: int) -> float:
    """
    Compute seed region complementarity score.
    TAPIR focuses on seed (2-8) and supplementary pairing.
    """
    mirna = mirna_seq.upper().replace('T', 'U')
    target = target_seq.upper().replace('T', 'U')
    
    # Extract aligned region
    t_seg = target[site_start:site_end]
    
    # Compute complementarity
    total_score = 0.0
    max_score = 0.0
    mirna_pos = 0
    
    for i in range(min(len(mirna), len(t_seg))):
        mirna_pos = i + 1  # 1-indexed
        m_char = mirna[i]
        t_char = t_seg[i]
        
        # Position weight (seed = 2x)
        if 2 <= mirna_pos <= 8:
            w = 2.0
        else:
            w = 1.0
        
        if _is_wc(m_char, t_char):
            total_score += 1.0 * w
            max_score += 1.0 * w
        elif _is_wobble(m_char, t_char):
            total_score += 0.5 * w
            max_score += 1.0 * w
    
    seed_score = (total_score / max_score * 100) if max_score > 0 else 0
    return seed_score


def tapir_predict(mirna_id: str, mirna_seq: str,
                  target_id: str, target_seq: str,
                  site_start: int, site_end: int,
                  min_score: float = 60.0,
                  ) -> Optional[TAPIRResult]:
    """
    TAPIR combined target prediction.
    
    Combines:
      1. Seed complementarity score
      2. Target accessibility
      3. Overall duplex energy
    """
    mirna = mirna_seq.upper().replace('T', 'U')
    target = target_seq.upper().replace('T', 'U')
    
    # 1. Seed score
    seed_score = compute_seed_score(mirna, target, site_start, site_end)
    
    # 2. Accessibility
    acc = compute_accessibility(target, site_start, site_end)
    acc_score = acc["accessibility"] * 100  # convert to 0-100
    
    # 3. Energy score (normalized to 0-100)
    # More accessible → lower up_energy → higher energy_score
    up_e = acc["up_energy"]
    energy_score = max(0, min(100, 100 - up_e * 10))
    
    # Combined TAPIR score (weighted)
    # Seed complementarity: 50%
    # Accessibility: 30%
    # Energy: 20%
    tapir_score = seed_score * 0.5 + acc_score * 0.3 + energy_score * 0.2
    
    passes = tapir_score >= min_score
    
    return TAPIRResult(
        mirna_id=mirna_id,
        target_id=target_id,
        seed_score=round(seed_score, 1),
        accessibility_score=round(acc_score, 1),
        energy_score=round(energy_score, 1),
        tapir_score=round(tapir_score, 1),
        target_region_structure=acc["structure"],
        up_energy=round(acc["up_energy"], 2),
        passes=passes,
    )


def validate_with_tapir(miranda_result, mirna_id: str,
                         target_id: str, target_seq: str,
                         ) -> Optional[TAPIRResult]:
    """
    Validate a miRanda alignment with TAPIR accessibility criteria.
    Used in consensus pipeline.
    """
    mirna_seq = miranda_result.mirna_seq
    t_start = miranda_result.target_start
    t_end = miranda_result.target_end
    
    return tapir_predict(
        mirna_id=mirna_id,
        mirna_seq=mirna_seq,
        target_id=target_id,
        target_seq=target_seq,
        site_start=t_start,
        site_end=t_end,
    )


if __name__ == '__main__':
    # Test
    mirna = "UUUGGAUUGAAGGGAGCUCUA"
    target = "GUGAAACCUAACUUCCCUCGAGAUUUCAACGAUU"
    site_start = 5
    site_end = 26
    
    r = tapir_predict("ath-miR159a", mirna, "test_target",
                       target, site_start, site_end)
    if r:
        print(f"TAPIR Score: {r.tapir_score:.1f}/100")
        print(f"  Seed: {r.seed_score:.1f}")
        print(f"  Accessibility: {r.accessibility_score:.1f}")
        print(f"  Energy: {r.energy_score:.1f}")
        print(f"  UP energy: {r.up_energy:.2f} kcal/mol")
        print(f"  Passes: {r.passes}")
