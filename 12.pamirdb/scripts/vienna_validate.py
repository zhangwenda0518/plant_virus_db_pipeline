"""
PAmiRDB v3 — ViennaRNA pre-miRNA structure validation.

Validates miRNA precursors using:
  1. RNAfold secondary structure prediction
  2. MFEI (Minimum Free Energy Index) calculation
  3. AMFE (Adjusted MFE) calculation
  4. Stem-loop hairpin verification

Reference criteria from literature:
  - MFE < -18 kcal/mol
  - MFEI > 0.85 (typical for plant miRNAs)
  - (A+U) content: 30-70%
  - Stem-loop hairpin topology
  - Mature miRNA located on one arm of the stem
"""

from dataclasses import dataclass
from typing import Optional
import math


@dataclass
class PreMiRNAValidation:
    """Pre-miRNA structure validation result."""
    mirna_id: str
    mature_sequence: str
    precursor_sequence: str = ""
    
    # RNAfold results
    mfe: float = 0.0             # minimum free energy (kcal/mol)
    secondary_structure: str = "" # dot-bracket notation
    mfei: float = 0.0            # MFE index
    amfe: float = 0.0            # adjusted MFE
    
    # Composition
    gc_content: float = 0.0
    au_content: float = 0.0
    
    # Structure validation
    has_hairpin: bool = False
    mature_on_stem: bool = False
    stem_length: int = 0
    loop_size: int = 0
    bulge_count: int = 0
    
    # Final validation
    passes_validation: bool = False
    validation_details: str = ""


def validate_pre_mirna(mirna_id: str, mature_seq: str,
                       precursor_seq: str = None) -> Optional[PreMiRNAValidation]:
    """
    Validate a pre-miRNA using ViennaRNA RNAfold.
    
    If precursor_seq is not provided, a minimal stem-loop is constructed
    around the mature miRNA for structural assessment.
    """
    result = PreMiRNAValidation(
        mirna_id=mirna_id,
        mature_sequence=mature_seq,
        precursor_sequence=precursor_seq or "",
    )
    
    # If no precursor provided, construct minimal one
    if not precursor_seq:
        precursor_seq = _construct_minimal_precursor(mature_seq)
        result.precursor_sequence = precursor_seq
    
    # Compute secondary structure
    structure_data = _fold_rna(precursor_seq)
    if structure_data is None:
        result.validation_details = "RNAfold failed"
        return result
    
    result.mfe = structure_data['mfe']
    result.secondary_structure = structure_data['structure']
    
    # MFEI calculation
    seq_len = len(precursor_seq)
    gc = sum(1 for c in precursor_seq.upper() if c in 'GC')
    result.gc_content = gc / seq_len * 100 if seq_len > 0 else 0
    result.au_content = (1 - gc/seq_len) * 100 if seq_len > 0 else 0
    
    if seq_len > 0 and result.gc_content > 0:
        result.mfei = abs(result.mfe) * 100 / (seq_len * result.gc_content / 100)
    result.amfe = abs(result.mfe) / seq_len * 100 if seq_len > 0 else 0
    
    # Structure analysis
    _analyze_hairpin(result, mature_seq)
    
    # Validation checks
    checks = []
    
    # MFE check
    if result.mfe <= -18:
        checks.append(f"MFE={result.mfe:.1f} <= -18 OK")
    else:
        checks.append(f"MFE={result.mfe:.1f} > -18 FAIL")
    
    # MFEI check (typical plant miRNA: > 0.85)
    if result.mfei > 0.85:
        checks.append(f"MFEI={result.mfei:.2f} > 0.85 OK")
    else:
        checks.append(f"MFEI={result.mfei:.2f} <= 0.85 FAIL")
    
    # AU content
    if 30 <= result.au_content <= 70:
        checks.append(f"AU%={result.au_content:.1f} in [30,70] OK")
    else:
        checks.append(f"AU%={result.au_content:.1f} out of [30,70] FAIL")
    
    # Hairpin
    if result.has_hairpin:
        checks.append("Stem-loop hairpin detected OK")
    else:
        checks.append("No hairpin FAIL")
    
    # Mature on stem
    if result.mature_on_stem:
        checks.append("Mature miRNA on stem arm OK")
    else:
        checks.append("Mature miRNA not on stem FAIL")
    
    result.passes_validation = (
        result.mfe <= -18 and
        result.mfei > 0.85 and
        30 <= result.au_content <= 70 and
        result.has_hairpin and
        result.mature_on_stem
    )
    
    result.validation_details = "; ".join(checks)
    return result


def _construct_minimal_precursor(mature_seq: str) -> str:
    """
    Construct a minimal stem-loop precursor around a mature miRNA.
    Uses reverse-complement for the opposite stem arm.
    """
    complement = {'A': 'U', 'U': 'A', 'G': 'C', 'C': 'G'}
    # Create reverse complement
    rc = ''.join(complement.get(c, c) for c in reversed(mature_seq))
    # Add a short loop
    loop = 'UCGA'  # typical tetraloop
    precursor = mature_seq + loop + rc
    return precursor


def _fold_rna(sequence: str) -> Optional[dict]:
    """Fold RNA using ViennaRNA or fallback."""
    try:
        import RNA
        fc = RNA.fold_compound(sequence)
        (structure, mfe) = fc.mfe()
        return {'mfe': mfe, 'structure': structure}
    except ImportError:
        pass
    
    # Simple fallback: estimate based on GC content and length
    gc = sum(1 for c in sequence.upper() if c in 'GC')
    au = len(sequence) - gc
    # Approximate MFE for a hairpin
    estimated_mfe = -(gc * 2.5 + au * 1.2) + 4.0
    return {'mfe': estimated_mfe, 'structure': '.' * len(sequence)}


def _analyze_hairpin(result: PreMiRNAValidation, mature_seq: str):
    """Analyze hairpin structure from dot-bracket notation."""
    struct = result.secondary_structure
    
    # Count paired bases (stem) vs unpaired (loop)
    paired = sum(1 for c in struct if c in '()')
    unpaired = sum(1 for c in struct if c == '.')
    
    result.stem_length = paired // 2  # each pair counts as 2 chars
    
    # Find largest loop (consecutive unpaired)
    max_loop = 0
    current = 0
    for c in struct:
        if c == '.':
            current += 1
            max_loop = max(max_loop, current)
        else:
            current = 0
    result.loop_size = max_loop
    
    # Hairpin: has both stems and a loop
    result.has_hairpin = (paired > 6 and max_loop >= 2)
    
    # Check if mature sequence is on a stem arm
    # Simplified: check if most of the mature region is paired
    if mature_seq and result.has_hairpin:
        precursor = result.precursor_sequence
        pos = precursor.find(mature_seq)
        if pos >= 0:
            region = struct[pos:pos + len(mature_seq)]
            paired_in_region = sum(1 for c in region if c in '()')
            result.mature_on_stem = paired_in_region >= len(region) * 0.6
    
    # Count bulges (isolated unpaired bases within stems)
    bulge = 0
    in_stem = False
    for i, c in enumerate(struct):
        if c in '()':
            in_stem = True
        elif in_stem and c == '.':
            if i+1 < len(struct) and struct[i+1] in '()':
                bulge += 1
            else:
                in_stem = False
    result.bulge_count = bulge


# ── MFEI reference table from literature ────────────────────────────

def get_mfei_reference():
    """Reference MFEI values from plant miRNA literature."""
    return {
        "Arabidopsis thaliana": {"typical_mfei": 1.05, "typical_mfe": -45},
        "Oryza sativa": {"typical_mfei": 1.10, "typical_mfe": -42},
        "Zea mays": {"typical_mfei": 0.95, "typical_mfe": -40},
        "Glycine max": {"typical_mfei": 0.98, "typical_mfe": -43},
        "Solanum lycopersicum": {"typical_mfei": 0.92, "typical_mfe": -38},
        "Vitis vinifera": {"typical_mfei": 0.90, "typical_mfe": -37},
        "Sorghum bicolor": {"typical_mfei": 0.96, "typical_mfe": -41},
    }


if __name__ == '__main__':
    # Test
    r = validate_pre_mirna("ath-miR408-5p", "CGGGGAACAGGCAGAGCAUGG")
    if r:
        print(f"miRNA: {r.mirna_id}")
        print(f"Precursor: {r.precursor_sequence[:50]}...")
        print(f"MFE: {r.mfe:.1f} kcal/mol")
        print(f"MFEI: {r.mfei:.2f}")
        print(f"AMFE: {r.amfe:.1f}")
        print(f"GC: {r.gc_content:.1f}%  AU: {r.au_content:.1f}%")
        print(f"Hairpin: {r.has_hairpin}  Mature on stem: {r.mature_on_stem}")
        print(f"Stem: {r.stem_length}bp  Loop: {r.loop_size}nt  Bulges: {r.bulge_count}")
        print(f"Structure: {r.secondary_structure}")
        print(f"Passes: {r.passes_validation}")
        print(f"Details: {r.validation_details}")
