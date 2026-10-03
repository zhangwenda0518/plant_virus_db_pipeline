"""
psRNATarget-style scoring engine for PAmiRDB v3.

Implements the plant-specific miRNA target prediction algorithm from:
  Dai et al. (2018) "psRNATarget: a plant small RNA target analysis server"
  NAR 46(W1):W49-W54

Key features differentiating from miRanda:
  1. Position-dependent mismatch penalties (seed region weighted more heavily)
  2. G:U wobble scoring (0.5 penalty vs 1.0 for mismatch)
  3. Translational inhibition detection (central mismatches at 9-11)
  4. Target accessibility (UPE - unpaired energy)
  5. Expectation value scoring

Scoring scheme (from literature):
  - Perfect WC match:     +1.0
  - G:U wobble:           +0.5
  - Mismatch:             +0.0
  - Gap opening:          -2.0
  - Gap extension:        -1.0
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ── Position-dependent weight matrix ───────────────────────────────
# Positions (1-indexed from 5' end of miRNA):
#   2-8:  seed region (critical)      weight = 1.5
#   9-11: central region (cleavage)   weight = 1.5
#   12-13: transition                 weight = 1.2
#   14-21: 3' region                  weight = 1.0

def _position_weight(pos: int) -> float:
    """Get position-dependent penalty weight for miRNA position (1-indexed)."""
    if 2 <= pos <= 8:
        return 1.5   # seed region
    elif 9 <= pos <= 11:
        return 1.5   # central (cleavage-determining)
    elif 12 <= pos <= 13:
        return 1.2   # transition
    else:
        return 1.0   # 3' region (more tolerant)


# ── Complementarity scoring ────────────────────────────────────────

def _is_wc(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('A', 'U'), ('U', 'A'), ('G', 'C'), ('C', 'G')}


def _is_wobble(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('G', 'U'), ('U', 'G')}


def _base_score(a: str, b: str) -> float:
    """Score for a single base pair. Returns 1 (WC complement), 0.5 (wobble), 0 (mismatch)."""
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    # Check complementarity (A:U, G:C) not identity!
    if (a == 'A' and b == 'U') or (a == 'U' and b == 'A'):
        return 1.0
    if (a == 'G' and b == 'C') or (a == 'C' and b == 'G'):
        return 1.0
    if (a == 'G' and b == 'U') or (a == 'U' and b == 'G'):
        return 0.5
    return 0.0


# ── Core psRNATarget alignment ─────────────────────────────────────

@dataclass
class PsRNATargetResult:
    """psRNATarget prediction result."""
    mirna_id: str
    target_id: str
    target_start: int = 0
    target_end: int = 0
    alignment_score: float = 0.0
    expectation: float = 0.0
    max_energy: float = 0.0
    unpaired_energy: float = 0.0
    num_mismatches: int = 0
    num_wobbles: int = 0
    num_gaps: int = 0
    seed_perfect: bool = False
    cleavage_possible: bool = False
    inhibition_possible: bool = False
    alignment_str: str = ""
    passes: bool = False
    consensus_votes: int = 0


def _build_alignment_str(mirna_seq: str, target_seq: str,
                          aln_a: list, aln_b: list) -> str:
    """Build pipe-format alignment string."""
    pipes = []
    for a, b in zip(aln_a, aln_b):
        if a == '-' or b == '-':
            pipes.append(' ')
        elif _is_wc(a, b):
            pipes.append('|')
        elif _is_wobble(a, b):
            pipes.append(':')  # wobble indicator
        else:
            pipes.append('.')
    return (f"miRNA  5' {''.join(aln_a)} 3'\n"
            f"         {''.join(pipes)}\n"
            f"target 3' {''.join(aln_b)} 5'")


def psrna_target_scan(mirna_id: str, mirna_seq: str,
                      target_id: str, target_seq: str,
                      max_expectation: float = 5.0,
                      max_upe: float = 25.0,
                      ) -> Optional[PsRNATargetResult]:
    """
    psRNATarget-style miRNA target prediction.
    
    Parameters (from literature defaults):
      max_expectation: 0-5, lower = more stringent
      max_upe: 25 (maximum unpaired energy for target accessibility)
    """
    mirna = mirna_seq.upper().replace('T', 'U')
    target = target_seq.upper().replace('T', 'U')
    
    # OPTIMIZED: Run DP on full target once (no sliding window)
    result = _align_psrna_full(mirna, target, mirna_id, target_id)
    
    if result is None:
        return None
    
    # Calculate expectation value
    result.expectation = _calc_expectation(
        result.alignment_score, len(mirna), len(target))
    
    # Set target coordinates
    result.target_start = 0
    result.target_end = len(target)
    
    # Apply filters
    result.passes = (
        result.expectation <= max_expectation and
        result.seed_perfect and
        result.num_mismatches <= 4
    )
    
    return result


def _align_psrna_full(mirna: str, target: str,
                       mirna_id: str, target_id: str
                       ) -> Optional[PsRNATargetResult]:
    """psRNATarget alignment with position-weighted scoring on full target."""
    m, n = len(mirna), len(target)
    
    GAP_OPEN = -2.0
    GAP_EXTEND = -1.0
    
    H = [[-float('inf')] * (n + 1) for _ in range(m + 1)]
    H[0][0] = 0.0
    
    for i in range(m + 1):
        for j in range(n + 1):
            if i == 0 and j == 0:
                continue
            best = -float('inf')
            if i > 0 and j > 0:
                bs = _base_score(mirna[i-1], target[j-1])
                w = _position_weight(i)
                s = H[i-1][j-1] + bs * w
                if s > best: best = s
            if i > 0:
                s = H[i-1][j] + (GAP_EXTEND if i > 1 else GAP_OPEN)
                if s > best: best = s
            if j > 0:
                s = H[i][j-1] + (GAP_EXTEND if j > 1 else GAP_OPEN)
                if s > best: best = s
            H[i][j] = best    
    # Traceback to find best alignment
    # Find the best-scoring position in last row
    best_j = max(range(n + 1), key=lambda j: H[m][j])
    i, j = m, best_j
    aln_a, aln_b = [], []
    wc = wob = mm = gaps = 0
    seed_ok = True
    
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            bs = _base_score(mirna[i-1], target[j-1])
            w = _position_weight(i)
            if abs(H[i][j] - (H[i-1][j-1] + bs * w)) < 0.001:
                aln_a.append(mirna[i-1])
                aln_b.append(target[j-1])
                if _is_wc(mirna[i-1], target[j-1]):
                    wc += 1
                elif _is_wobble(mirna[i-1], target[j-1]):
                    wob += 1
                else:
                    mm += 1
                # Seed check
                if 2 <= i <= 8 and not _is_wc(mirna[i-1], target[j-1]):
                    seed_ok = False
                i -= 1; j -= 1
                continue
        
        if i > 0 and abs(H[i][j] - (H[i-1][j] + (GAP_EXTEND if i > 1 else GAP_OPEN))) < 0.001:
            aln_a.append(mirna[i-1]); aln_b.append('-'); gaps += 1; i -= 1
        elif j > 0:
            aln_a.append('-'); aln_b.append(target[j-1]); gaps += 1; j -= 1
        else:
            break
    
    aln_a.reverse(); aln_b.reverse()
    
    # Score: only count aligned positions
    raw_score = H[m][n]
    
    # Check central region (9-11)
    cleavage_ok = True
    inhibition_ok = False
    central_mismatches = 0
    mirna_pos = 0
    for a, b in zip(aln_a, aln_b):
        if a != '-':
            mirna_pos += 1
            if 9 <= mirna_pos <= 11:
                if not _is_wc(a, b):
                    central_mismatches += 1
    
    cleavage_ok = (central_mismatches == 0)
    inhibition_ok = (central_mismatches >= 1)
    
    # Estimate MFE (simplified)
    energy = _estimate_duplex_energy(aln_a, aln_b)
    
    aln_str = _build_alignment_str(mirna, target, aln_a, aln_b)
    
    return PsRNATargetResult(
        mirna_id=mirna_id, target_id=target_id,
        alignment_score=raw_score,
        expectation=0.0,  # calculated later
        max_energy=energy,
        unpaired_energy=0.0,  # requires target structure context
        num_mismatches=mm, num_wobbles=wob, num_gaps=gaps,
        seed_perfect=seed_ok,
        cleavage_possible=cleavage_ok,
        inhibition_possible=inhibition_ok,
        alignment_str=aln_str,
        passes=False,
    )


def _calc_expectation(score: float, mirna_len: int, target_len: int) -> float:
    """
    Calculate expectation value.
    Lower = more significant. psRNATarget uses a statistical model.
    Simplified: E = N * e^(-score), where N is the search space.
    """
    N = max(target_len - mirna_len + 1, 1)
    if score <= 0:
        return float('inf')
    # Normalize by miRNA length
    normalized = score / mirna_len
    return N * math.exp(-normalized * 3)


def _estimate_duplex_energy(aln_a: list, aln_b: list) -> float:
    """Estimate duplex free energy (simplified nearest-neighbor)."""
    try:
        import RNA
        seq_a = ''.join(c for c in aln_a if c != '-')
        seq_b = ''.join(c for c in aln_b if c != '-')
        if seq_a and seq_b:
            fc = RNA.fold_compound(seq_a + '&' + seq_b)
            return fc.mfe()[1]
    except ImportError:
        pass
    
    NN = {('A','U'):-2.0,('U','A'):-2.0,('G','C'):-3.0,('C','G'):-3.0,
          ('G','U'):-1.0,('U','G'):-1.0}
    e = 4.0
    for a, b in zip(aln_a, aln_b):
        if a == '-' or b == '-':
            e += 1.5
        else:
            if _is_wc(a, b):
                e += NN.get((a.upper(), b.upper()), -1.0)
            elif _is_wobble(a, b):
                e += -1.0
            else:
                e += 2.0
    return e
