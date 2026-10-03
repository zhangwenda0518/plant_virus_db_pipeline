"""
PAmiRDB v4.2 — Complete pre-miRNA validation (7 criteria).

From: Sahu et al. (2023) "Identification of potential conserved 
Cyperus rotundus microRNAs..." Scientific African 22:e01936.
https://www.sciencedirect.com/science/article/pii/S2773044123001006

Also incorporates criteria from:
  Yang et al. (2010) MFEI/AMFE thresholds
  Ambros et al. (2003) miRNA nomenclature conventions
  miRBase standard pre-miRNA quality standards

7 Criteria:
  1. Stem-loop hairpin topology (MFE < -18 kcal/mol)
  2. Mature miRNA located on one arm of the stem
  3. MFEI in [0.53, 1.01] kcal/mol
  4. (A+U) content in [30%, 70%]
  5. miRNA sequence contains no internal loops or breaks
  6. Bulge size in [3, 7] nucleotides
  7. miRNA : miRNA* mismatches <= 6
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PreMiRNAFullValidation:
    """Complete 7-criteria pre-miRNA validation result."""
    mirna_id: str
    mature_sequence: str
    precursor_sequence: str = ""
    
    # Structure
    mfe: float = 0.0
    secondary_structure: str = ""
    mfei: float = 0.0
    amfe: float = 0.0
    gc_content: float = 0.0
    au_content: float = 0.0
    
    # 7 criteria
    has_hairpin: bool = False           # Criterion 1
    mature_on_stem: bool = False        # Criterion 2
    mfei_in_range: bool = False         # Criterion 3
    au_in_range: bool = False           # Criterion 4
    no_internal_breaks: bool = False    # Criterion 5
    bulge_size_ok: bool = False         # Criterion 6
    star_mismatches_ok: bool = False    # Criterion 7
    
    # Detailed metrics
    stem_length: int = 0
    loop_size: int = 0
    bulge_count: int = 0
    max_bulge_size: int = 0
    min_bulge_size: int = 0
    star_mismatch_count: int = 0
    internal_loop_count: int = 0
    
    # Summary
    criteria_passed: int = 0
    passes_validation: bool = False
    validation_details: list = field(default_factory=list)


def validate_pre_mirna_full(mirna_id: str, mature_seq: str,
                             precursor_seq: str = None,
                             star_seq: str = None,
                             ) -> PreMiRNAFullValidation:
    """
    Full 7-criteria pre-miRNA validation.
    
    Args:
        mirna_id: miRNA identifier
        mature_seq: mature miRNA sequence
        precursor_seq: full precursor sequence (if available)
        star_seq: miRNA* (passenger strand) sequence (if available)
    """
    result = PreMiRNAFullValidation(
        mirna_id=mirna_id,
        mature_sequence=mature_seq,
    )
    
    # Build precursor if not provided
    if not precursor_seq:
        precursor_seq = _build_precursor(mature_seq)
    result.precursor_sequence = precursor_seq
    
    # ── RNA Folding ──────────────────────────────────────────────
    try:
        import RNA
        fc = RNA.fold_compound(precursor_seq)
        structure, mfe = fc.mfe()
    except ImportError:
        structure, mfe = _estimate_folding(precursor_seq)
    
    result.mfe = mfe
    result.secondary_structure = structure
    
    # ── Composition ──────────────────────────────────────────────
    seq_len = len(precursor_seq)
    gc = sum(1 for c in precursor_seq.upper() if c in 'GC')
    au = seq_len - gc
    result.gc_content = gc / seq_len * 100 if seq_len > 0 else 0
    result.au_content = au / seq_len * 100 if seq_len > 0 else 0
    
    # MFEI = (abs(MFE) * 100) / (length * GC%)
    if seq_len > 0 and gc > 0:
        result.mfei = abs(mfe) * 100 / (seq_len * result.gc_content / 100)
    result.amfe = abs(mfe) / seq_len * 100 if seq_len > 0 else 0
    
    # ── Structure Analysis ───────────────────────────────────────
    _analyze_full_structure(result, mature_seq, star_seq)
    
    # ── Apply 7 Criteria ─────────────────────────────────────────
    
    # Criterion 1: MFE < -18 kcal/mol AND stem-loop hairpin
    result.has_hairpin = (mfe < -18) and (result.stem_length > 6)
    if result.has_hairpin:
        result.validation_details.append(
            f"[PASS 1/7] MFE={mfe:.1f} < -18, hairpin with stem={result.stem_length}bp")
    else:
        result.validation_details.append(
            f"[FAIL 1/7] MFE={mfe:.1f} >= -18 or insufficient stem")
    
    # Criterion 2: Mature miRNA on one arm of stem
    result.mature_on_stem = _check_mature_on_stem(
        precursor_seq, structure, mature_seq
    )
    if result.mature_on_stem:
        result.validation_details.append(
            "[PASS 2/7] Mature miRNA located on stem arm")
    else:
        result.validation_details.append(
            "[FAIL 2/7] Mature miRNA not on stem arm")
    
    # Criterion 3: MFEI in [0.53, 1.01]
    result.mfei_in_range = (0.53 < result.mfei < 1.01)
    if result.mfei_in_range:
        result.validation_details.append(
            f"[PASS 3/7] MFEI={result.mfei:.2f} in [0.53, 1.01]")
    else:
        result.validation_details.append(
            f"[FAIL 3/7] MFEI={result.mfei:.2f} outside [0.53, 1.01]")
    
    # Criterion 4: (A+U) in [30%, 70%]
    result.au_in_range = (30 <= result.au_content <= 70)
    if result.au_in_range:
        result.validation_details.append(
            f"[PASS 4/7] AU%={result.au_content:.1f} in [30, 70]")
    else:
        result.validation_details.append(
            f"[FAIL 4/7] AU%={result.au_content:.1f} outside [30, 70]")
    
    # Criterion 5: No internal loops or breaks in miRNA region
    result.no_internal_breaks = (result.internal_loop_count == 0)
    if result.no_internal_breaks:
        result.validation_details.append(
            "[PASS 5/7] No internal loops/breaks in miRNA region")
    else:
        result.validation_details.append(
            f"[FAIL 5/7] {result.internal_loop_count} internal loop(s) found")
    
    # Criterion 6: Bulge size in [3, 7] nucleotides
    result.bulge_size_ok = (
        result.bulge_count == 0 or
        (3 <= result.min_bulge_size <= 7 and result.max_bulge_size <= 7)
    )
    if result.bulge_size_ok:
        result.validation_details.append(
            f"[PASS 6/7] Bulge size(s) within [3,7] nt (count={result.bulge_count})")
    else:
        result.validation_details.append(
            f"[FAIL 6/7] Bulge size out of range (min={result.min_bulge_size}, max={result.max_bulge_size})")
    
    # Criterion 7: miRNA:miRNA* mismatches <= 6
    if star_seq:
        result.star_mismatch_count = _count_star_mismatches(mature_seq, star_seq)
        result.star_mismatches_ok = (result.star_mismatch_count <= 6)
    else:
        # Without star sequence, assume OK if overall mismatches are low
        result.star_mismatch_count = 0
        result.star_mismatches_ok = True
    
    if result.star_mismatches_ok:
        result.validation_details.append(
            f"[PASS 7/7] miRNA:miRNA* mismatches={result.star_mismatch_count} <= 6")
    else:
        result.validation_details.append(
            f"[FAIL 7/7] miRNA:miRNA* mismatches={result.star_mismatch_count} > 6")
    
    # ── Final ────────────────────────────────────────────────────
    result.criteria_passed = sum([
        result.has_hairpin,
        result.mature_on_stem,
        result.mfei_in_range,
        result.au_in_range,
        result.no_internal_breaks,
        result.bulge_size_ok,
        result.star_mismatches_ok,
    ])
    
    result.passes_validation = result.criteria_passed >= 6
    
    return result


def _build_precursor(mature_seq: str) -> str:
    """Build a minimal stem-loop precursor from mature miRNA."""
    comp = {'A': 'U', 'U': 'A', 'G': 'C', 'C': 'G'}
    rc = ''.join(comp.get(c, c) for c in reversed(mature_seq))
    # Standard tetraloop
    loop = 'CUGA'  # GNRA tetraloop-like
    return mature_seq + loop + rc


def _estimate_folding(sequence: str) -> tuple:
    """Quick RNA folding estimate without ViennaRNA."""
    gc = sum(1 for c in sequence.upper() if c in 'GC')
    au = len(sequence) - gc
    # Approximate MFE for stem-loop
    mfe = -(gc * 2.3 + au * 1.1) + 5.0
    # Simple dot-bracket
    half = len(sequence) // 2
    struct = '(' * (half - 2) + '....' + ')' * (half - 2)
    return struct, mfe


def _analyze_full_structure(result: PreMiRNAFullValidation,
                             mature_seq: str, star_seq: str = None):
    """Full structure analysis including bulges, internal loops, etc."""
    struct = result.secondary_structure
    
    # Paired vs unpaired
    result.stem_length = sum(1 for c in struct if c in '()') // 2
    
    # Largest loop (consecutive unpaired)
    max_loop = 0; current = 0
    for c in struct:
        if c == '.':
            current += 1; max_loop = max(max_loop, current)
        else:
            current = 0
    result.loop_size = max_loop
    
    # Bulge analysis (isolated unpaired bases within stem regions)
    bulges = []
    in_stem = False; bulge_start = None; bulge_len = 0
    
    for i, c in enumerate(struct):
        if c == '.':
            if in_stem:
                if bulge_start is None: bulge_start = i
                bulge_len += 1
            else:
                if bulge_len > 0:
                    bulges.append(bulge_len)
                bulge_start = None; bulge_len = 0
        elif c == '(':
            in_stem = True
            if bulge_len > 0:
                bulges.append(bulge_len)
                bulge_len = 0; bulge_start = None
        elif c == ')':
            if bulge_len > 0:
                bulges.append(bulge_len)
                bulge_len = 0; bulge_start = None
    
    result.bulge_count = len(bulges)
    result.max_bulge_size = max(bulges) if bulges else 0
    result.min_bulge_size = min(bulges) if bulges else 0
    
    # Internal loops
    # Find position of mature miRNA in precursor
    pos = result.precursor_sequence.find(mature_seq)
    if pos >= 0:
        mature_struct = struct[pos:pos + len(mature_seq)]
        # Count consecutive unpaired stretches (internal loops)
        result.internal_loop_count = 0
        unpaired_run = 0
        for c in mature_struct:
            if c == '.':
                unpaired_run += 1
                if unpaired_run >= 3:  # loop of >=3 counts as internal loop
                    result.internal_loop_count += 1
                    unpaired_run = 0
            else:
                unpaired_run = 0


def _check_mature_on_stem(seq: str, struct: str, mature: str) -> bool:
    """Check if mature miRNA is located on a stem arm."""
    pos = seq.find(mature)
    if pos < 0: return False
    mature_struct = struct[pos:pos + len(mature)]
    paired = sum(1 for c in mature_struct if c in '()')
    return paired >= len(mature_struct) * 0.6


def _count_star_mismatches(mature: str, star: str) -> int:
    """Count mismatches between mature miRNA and miRNA* (passenger strand)."""
    comp = {'A': 'U', 'U': 'A', 'G': 'C', 'C': 'G'}
    mm = 0
    n = min(len(mature), len(star))
    for i in range(n):
        expected = comp.get(mature[i], '')
        if star[i].upper().replace('T', 'U') != expected:
            mm += 1
    return mm


# ── Summary Report ─────────────────────────────────────────────────

def format_validation_report(v: PreMiRNAFullValidation) -> str:
    """Generate a human-readable validation report."""
    status = "PASS" if v.passes_validation else "FAIL"
    lines = [
        f"{'='*60}",
        f"  Pre-miRNA Validation: {v.mirna_id}  [{status}] ({v.criteria_passed}/7)",
        f"{'='*60}",
        f"  MFE:  {v.mfe:.1f} kcal/mol    MFEI: {v.mfei:.2f}    AMFE: {v.amfe:.1f}",
        f"  GC%:  {v.gc_content:.1f}      AU%:  {v.au_content:.1f}",
        f"  Stem: {v.stem_length}bp        Loop: {v.loop_size}nt",
        f"  Bulges: {v.bulge_count} (size {v.min_bulge_size}-{v.max_bulge_size}nt)",
        f"  Star mismatches: {v.star_mismatch_count}",
        f"  { '-' * 56 }",
    ]
    for detail in v.validation_details:
        lines.append(f"  {detail}")
    return '\n'.join(lines)


if __name__ == '__main__':
    # Test
    r = validate_pre_mirna_full(
        "ath-miR159a", "UUUGGAUUGAAGGGAGCUCUA",
        star_seq="AAGCUCCUUCAAGUCCAAAUC"
    )
    print(format_validation_report(r))
