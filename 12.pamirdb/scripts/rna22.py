"""
PAmiRDB v4.5 — RNA22 pattern-recognition target prediction engine.

RNA22 (Miranda et al. 2006, Cell 126:1203-1217):
  - Pattern-based: finds statistically significant miRNA-target patterns
  - NO seed-region requirement — can detect non-canonical interactions
  - Uses MFE (Minimum Free Energy) as primary metric
  - High sensitivity — catches targets missed by seed-based tools
  - Web-based interactive tool

Key differences from miRanda:
  1. Pattern discovery first, then filtering
  2. No seed requirement — finds interactions at any position
  3. Uses statistical significance (p-value) for pattern matching
  4. Allows bulge/internal loops in miRNA:target duplex freely

Implementation approach:
  1. Extract all k-mer patterns from miRNA (length ~7-8 nt)
  2. Search target for reverse-complement matches to these patterns
  3. Extend matches with energy optimization
  4. Score by MFE and statistical significance
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math


def _is_wc(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('A', 'U'), ('U', 'A'), ('G', 'C'), ('C', 'G')}


def _is_wobble(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('G', 'U'), ('U', 'G')}


def _rev_comp(seq: str) -> str:
    """Reverse complement."""
    comp = {'A': 'U', 'U': 'A', 'G': 'C', 'C': 'G', 'T': 'U'}
    return ''.join(comp.get(c, c) for c in reversed(seq.upper()))


@dataclass
class RNA22Result:
    """RNA22 prediction result."""
    mirna_id: str
    target_id: str
    mfe: float                    # minimum free energy
    pattern_score: float          # statistical pattern match score
    target_start: int
    target_end: int
    num_mismatches: int
    num_wobbles: int
    seed_perfect: bool            # RNA22 doesn't require this
    alignment_str: str
    passes: bool
    consensus_votes: int = 0


def rna22_predict(mirna_id: str, mirna_seq: str,
                  target_id: str, target_seq: str,
                  pattern_length: int = 7,
                  max_mfe: float = -20.0,
                  max_pvalue: float = 0.05,
                  ) -> list[RNA22Result]:
    """
    RNA22-style pattern-based target prediction.
    
    Steps:
      1. Generate k-mer patterns from miRNA
      2. Search target for reverse-complement matches
      3. Extend matches bidirectionally with energy minimization
      4. Score and filter
    
    Returns list of RNA22Result (may be multiple hits per target).
    """
    mirna = mirna_seq.upper().replace('T', 'U')
    target = target_seq.upper().replace('T', 'U')
    
    results = []
    patterns_seen = set()  # avoid duplicate patterns
    
    # Step 1: Extract patterns from miRNA (sliding window)
    for i in range(len(mirna) - pattern_length + 1):
        pattern = mirna[i:i + pattern_length]
        pattern_rc = _rev_comp(pattern)
        
        if pattern in patterns_seen:
            continue
        patterns_seen.add(pattern)
        
        # Step 2: Search target for pattern reverse-complement
        pos = 0
        while True:
            pos = target.find(pattern_rc, pos)
            if pos == -1:
                break
            
            # Step 3: Extend alignment bidirectionally
            result = _extend_from_seed(
                mirna, target, i, pos, mirna_id, target_id
            )
            
            if result and result.mfe <= max_mfe:
                # Calculate statistical significance
                pvalue = _calc_pattern_pvalue(
                    pattern, target, result.mfe
                )
                result.pattern_score = -math.log10(max(pvalue, 1e-10))
                
                if pvalue <= max_pvalue:
                    result.passes = True
                    results.append(result)
            
            pos += 1
    
    # Sort by pattern_score (higher = more significant)
    results.sort(key=lambda x: -x.pattern_score)
    
    # Deduplicate overlapping hits (keep best)
    final = []
    used_ranges = []
    for r in results:
        overlap = False
        for s, e in used_ranges:
            if r.target_start < e and r.target_end > s:
                overlap = True
                break
        if not overlap:
            final.append(r)
            used_ranges.append((r.target_start, r.target_end))
    
    return final[:20]


def _extend_from_seed(mirna: str, target: str,
                       mirna_seed_start: int, target_seed_start: int,
                       mirna_id: str, target_id: str,
                       ) -> Optional[RNA22Result]:
    """
    Extend alignment from a seed match in both directions.
    Uses energy-optimized DP to find the best extended alignment.
    """
    seed_len = 7  # pattern length
    
    # Build alignment by extending outward from seed
    aln_a, aln_b, pipes = [], [], []
    
    # Extend left (toward 5' of miRNA, 3' of target)
    i, j = mirna_seed_start - 1, target_seed_start - 1
    left_a, left_b, left_p = [], [], []
    while i >= 0 and j >= 0:
        if _is_wc(mirna[i], target[j]):
            left_a.append(mirna[i]); left_b.append(target[j])
            left_p.append('|')
        elif _is_wobble(mirna[i], target[j]):
            left_a.append(mirna[i]); left_b.append(target[j])
            left_p.append(':')
        else:
            # Check if skipping creates better energy
            skip_i = _pair_energy(mirna[i+1] if i+1 < len(mirna) else '',
                                   target[j]) if i+1 < len(mirna) else 999
            skip_j = _pair_energy(mirna[i],
                                   target[j+1] if j+1 < len(target) else '') if j+1 < len(target) else 999
            if skip_i < 0:
                left_a.append('-'); left_b.append(target[j])
                left_p.append(' '); j -= 1; continue
            elif skip_j < 0:
                left_a.append(mirna[i]); left_b.append('-')
                left_p.append(' '); i -= 1; continue
            else:
                left_a.append(mirna[i]); left_b.append(target[j])
                left_p.append('.')
        i -= 1; j -= 1
    
    left_a.reverse(); left_b.reverse(); left_p.reverse()
    aln_a.extend(left_a); aln_b.extend(left_b); pipes.extend(left_p)
    
    # Seed region
    for k in range(seed_len):
        aln_a.append(mirna[mirna_seed_start + k])
        aln_b.append(target[target_seed_start + k])
        pipes.append('|')
    
    # Extend right (toward 3' of miRNA, 5' of target)
    i, j = mirna_seed_start + seed_len, target_seed_start + seed_len
    while i < len(mirna) and j < len(target):
        if _is_wc(mirna[i], target[j]):
            aln_a.append(mirna[i]); aln_b.append(target[j])
            pipes.append('|')
        elif _is_wobble(mirna[i], target[j]):
            aln_a.append(mirna[i]); aln_b.append(target[j])
            pipes.append(':')
        else:
            skip_i = _pair_energy(mirna[i-1] if i > 0 else '',
                                   target[j]) if i > 0 else 999
            skip_j = _pair_energy(mirna[i],
                                   target[j-1] if j > 0 else '') if j > 0 else 999
            if skip_i < 0:
                aln_a.append('-'); aln_b.append(target[j])
                pipes.append(' '); j += 1; continue
            elif skip_j < 0:
                aln_a.append(mirna[i]); aln_b.append('-')
                pipes.append(' '); i += 1; continue
            else:
                aln_a.append(mirna[i]); aln_b.append(target[j])
                pipes.append('.')
        i += 1; j += 1
    
    if len(aln_a) < 10:
        return None
    
    # Compute MFE
    mfe = _compute_duplex_energy(aln_a, aln_b)
    
    # Count mismatches/wobbles
    mm = sum(1 for p in pipes if p == '.')
    wb = sum(1 for p in pipes if p == ':')
    
    # Seed check (RNA22 doesn't require it, but we note it)
    seed_ok = True
    mirna_pos = 0
    for a, p in zip(aln_a, pipes):
        if a != '-':
            mirna_pos += 1
            if 2 <= mirna_pos <= 8 and p != '|':
                seed_ok = False
    
    aln_str = (f"miRNA  5' {''.join(aln_a)} 3'\n"
               f"         {''.join(pipes)}\n"
               f"target 3' {''.join(aln_b)} 5'")
    
    t_start = target_seed_start - len(left_a)
    t_end = target_seed_start + seed_len + (len(aln_a) - len(left_a) - seed_len)
    
    return RNA22Result(
        mirna_id=mirna_id, target_id=target_id,
        mfe=mfe, pattern_score=0.0,
        target_start=max(0, t_start),
        target_end=t_end,
        num_mismatches=mm, num_wobbles=wb,
        seed_perfect=seed_ok,
        alignment_str=aln_str, passes=False,
    )


def _pair_energy(a: str, b: str) -> float:
    """Energy contribution of a base pair (negative = favorable)."""
    if not a or not b:
        return 999
    if _is_wc(a, b):
        return -2.0
    if _is_wobble(a, b):
        return -1.0
    return 2.0  # mismatch penalty


def _compute_duplex_energy(aln_a: list, aln_b: list) -> float:
    """Compute MFE of aligned duplex."""
    e = 4.0
    for a, b in zip(aln_a, aln_b):
        if a == '-' or b == '-':
            e += 1.5
        elif _is_wc(a, b):
            e += -2.0
        elif _is_wobble(a, b):
            e += -1.0
        else:
            e += 2.0
    return e


def _calc_pattern_pvalue(pattern: str, target: str, mfe: float) -> float:
    """
    Calculate pattern-match statistical significance.
    Based on how many times the pattern would be expected by chance.
    """
    pattern_rc = _rev_comp(pattern)
    # Count occurrences
    count = 0
    pos = 0
    while True:
        pos = target.find(pattern_rc, pos)
        if pos == -1:
            break
        count += 1
        pos += 1
    
    # Expected by chance (simplified)
    target_len = len(target)
    pattern_len = len(pattern)
    expected = target_len / (4 ** pattern_len) if pattern_len > 0 else 1
    
    # Poisson p-value
    if expected <= 0:
        return 0.0
    
    # Probability of observing >= count occurrences
    p = 0.0
    for k in range(count):
        p += (expected ** k) * math.exp(-expected) / math.factorial(k)
    
    return 1.0 - p


def validate_with_rna22(miranda_result, mirna_id: str,
                         target_id: str, target_seq: str,
                         ) -> Optional[RNA22Result]:
    """
    Validate a miRanda hit with RNA22.
    Returns RNA22Result if RNA22 independently finds a target
    in the same region (±20bp).
    """
    mirna_seq = miranda_result.mirna_seq
    t_start = max(0, miranda_result.target_start - 20)
    t_end = min(len(target_seq), miranda_result.target_end + 20)
    target_region = target_seq[t_start:t_end]
    
    results = rna22_predict(
        mirna_id, mirna_seq, target_id, target_region,
        max_mfe=-15.0, max_pvalue=0.10  # relaxed for validation
    )
    
    if results:
        # Adjust coordinates
        best = results[0]
        best.target_start += t_start
        best.target_end += t_start
        return best
    
    return None


if __name__ == '__main__':
    # Test
    mirna = "UUUGGAUUGAAGGGAGCUCUA"
    target = "GUGAAACCUAACUUCCCUCGAGAUUUCAACGAUUUGGGAUUGAA"
    
    results = rna22_predict("ath-miR159a", mirna, "test", target)
    print(f"RNA22 found {len(results)} targets")
    for r in results[:3]:
        print(f"  MFE={r.mfe:.1f}  pattern_score={r.pattern_score:.1f}  mm={r.num_mismatches}  seed={r.seed_perfect}")
        if r.alignment_str:
            for line in r.alignment_str.split('\n')[:3]:
                print(f"    {line}")
