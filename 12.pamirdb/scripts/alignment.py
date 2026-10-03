"""
Core miRNA-target alignment engine for PAmiRDB v2.
Enhanced with: position-specific binding, similarity%, matching status.

Satish et al. (2019) Scientific Reports 9:4627
"""

from dataclasses import dataclass, field
from typing import Optional

SCORE = {('A','U'):5,('U','A'):5,('G','C'):5,('C','G'):5,('G','U'):2,('U','G'):2}
GAP_OPEN = -9
GAP_EXTEND = -4

# 2026-10-03: total gap-column cap for the tier filters. The loose tier could
# previously admit gap-riddled garbage hits (the stored top-ranked "strongest
# interaction" had 30 gaps). Over the cap -> not returned as a tier hit.
MAX_GAPS = 10


def _pair_score(a: str, b: str) -> int:
    a, b = a.upper().replace('T','U'), b.upper().replace('T','U')
    return SCORE.get((a,b), -3)


def _is_wc(a: str, b: str) -> bool:
    """Watson-Crick pair?"""
    a, b = a.upper().replace('T','U'), b.upper().replace('T','U')
    return (a,b) in {('A','U'),('U','A'),('G','C'),('C','G')}


def _is_wobble(a: str, b: str) -> bool:
    """G:U wobble pair?"""
    a, b = a.upper().replace('T','U'), b.upper().replace('T','U')
    return (a,b) in {('G','U'),('U','G')}


@dataclass
class AlignmentResult:
    mirna_id: str
    mirna_seq: str
    target_id: str
    target_start: int
    target_end: int
    score: float
    energy: float
    num_mismatches: int
    num_gaps: int
    seed_perfect: bool
    query_cover: float
    identity: float
    similarity: float = 0.0           # WC + wobble %
    alignment_str: str = ""
    passes_filters: bool = False
    tier_strict: bool = False
    tier_moderate: bool = False
    tier_loose: bool = False
    
    # New PAmiRDB v2 fields
    query_start: int = 1              # Query_S: miRNA 5' start position (1-indexed)
    query_end: int = 0                # Query_E: miRNA 5' end position
    alignment_length: int = 0
    target_protein: str = ""          # Viral protein targeted
    matching_status: str = ""         # Withinmatch / Overlapping
    position_binding: dict = field(default_factory=dict)  # {pos: 'WC'|'wobble'|'mismatch'|'gap'}


def _get_position_binding(aln_a: list, aln_b: list, pipes: list) -> dict:
    """
    Map miRNA positions (1-indexed from 5') to binding status.
    Returns {pos: 'WC'|'wobble'|'mismatch'|'gap'}
    """
    pos_map = {}
    mirna_pos = 0
    for a, b, p in zip(aln_a, aln_b, pipes):
        if a != '-':
            mirna_pos += 1
            if p == '|':
                if _is_wc(a, b):
                    pos_map[mirna_pos] = 'WC'
                elif _is_wobble(a, b):
                    pos_map[mirna_pos] = 'wobble'
                else:
                    pos_map[mirna_pos] = 'mismatch'
            elif b == '-':
                pos_map[mirna_pos] = 'gap'
            else:
                pos_map[mirna_pos] = 'mismatch'
    return pos_map


def _check_position_constraint(pos_binding: dict, required_positions: list) -> bool:
    """
    Check if all required positions have complementary binding (WC or wobble).
    required_positions: list of 1-indexed miRNA positions
    """
    for pos in required_positions:
        status = pos_binding.get(pos)
        if status not in ('WC', 'wobble'):
            return False
    return True


def _check_au_at_positions(pos_binding: dict, aln_a: list, positions: list) -> bool:
    """
    Check if specific miRNA positions are A or U.
    positions: list of 1-indexed miRNA positions
    """
    # Build mapping of miRNA position to nucleotide
    mirna_pos = 0
    nuc_at_pos = {}
    for a in aln_a:
        if a != '-':
            mirna_pos += 1
            nuc_at_pos[mirna_pos] = a.upper()
    
    for pos in positions:
        if nuc_at_pos.get(pos, '') not in ('A', 'U'):
            return False
    return True


def align_mirna_to_target(
    mirna_id: str, mirna_seq: str,
    target_id: str, target_seq: str,
    required_positions: list = None,  # positions that MUST be paired
    check_au_positions: list = None,  # positions that MUST be A or U
    max_gaps: int = MAX_GAPS,         # total gap columns cap for tier filters
) -> Optional[AlignmentResult]:
    """Run miRanda-style alignment with optional position constraints."""
    mirna = mirna_seq.upper().replace('T','U')
    target = target_seq.upper().replace('T','U')
    m, n = len(mirna), len(target)

    # DP forward
    H = [[0.0]*(n+1) for _ in range(m+1)]
    best_score, best_pos = 0.0, (0,0)
    for i in range(1,m+1):
        for j in range(1,n+1):
            diag = H[i-1][j-1]+_pair_score(mirna[i-1],target[j-1])
            up = H[i-1][j]+(GAP_EXTEND if i>1 and H[i-1][j]>0 else GAP_OPEN+GAP_EXTEND)
            left = H[i][j-1]+(GAP_EXTEND if j>1 and H[i][j-1]>0 else GAP_OPEN+GAP_EXTEND)
            H[i][j]=max(0.0,diag,up,left)
            if H[i][j]>best_score:
                best_score=H[i][j]; best_pos=(i,j)

    if best_score==0:
        return None

    # Traceback
    i,j=best_pos; aln_a,aln_b,pipes=[],[],[]
    mismatches=gaps=0
    while i>0 and j>0 and H[i][j]>0:
        cur=H[i][j]
        if cur==H[i-1][j-1]+_pair_score(mirna[i-1],target[j-1]):
            s=_pair_score(mirna[i-1],target[j-1])
            aln_a.append(mirna[i-1]); aln_b.append(target[j-1])
            pipes.append('|' if s>0 else '.')
            if s<=0: mismatches+=1
            i-=1;j-=1
        elif cur==H[i-1][j]+(GAP_EXTEND if i>1 and H[i-1][j]>0 else GAP_OPEN+GAP_EXTEND):
            aln_a.append(mirna[i-1]); aln_b.append('-'); pipes.append(' '); gaps+=1; i-=1
        else:
            aln_a.append('-'); aln_b.append(target[j-1]); pipes.append(' '); gaps+=1; j-=1

    aln_a.reverse(); aln_b.reverse(); pipes.reverse()
    t_start=j; t_end=best_pos[1]

    # Position binding map
    pos_binding = _get_position_binding(aln_a, aln_b, pipes)

    # If position constraints specified, check them
    if required_positions:
        if not _check_position_constraint(pos_binding, required_positions):
            return None
    if check_au_positions:
        if not _check_au_at_positions(pos_binding, aln_a, check_au_positions):
            return None

    # Seed check (2-8)
    mirna_pos=0; seed_ok=True
    for a,b,p in zip(aln_a,aln_b,pipes):
        if a!='-':
            mirna_pos+=1
            if 2<=mirna_pos<=8 and p!='|':
                seed_ok=False; break

    # Energy
    energy=_estimate_energy(aln_a,aln_b)

    # Query_S and Query_E (first and last miRNA positions in alignment)
    query_s=1; query_e=0
    mirna_pos=0
    for a in aln_a:
        if a!='-':
            mirna_pos+=1
            if query_s is None: query_s=mirna_pos
            query_e=mirna_pos
    if query_s is None: query_s=1

    # Alignment length
    aln_len=len(aln_a)

    # Metrics
    aln_bases=len([c for c in aln_a if c!='-'])
    query_cover=aln_bases/len(mirna_seq)*100 if mirna_seq else 0

    # Identity: WC pairs / miRNA length
    wc_pairs=sum(1 for a,b in zip(aln_a,aln_b) if _is_wc(a,b))
    identity=wc_pairs/len(mirna_seq)*100 if mirna_seq else 0

    # Similarity: (WC + wobble) / miRNA length
    wobble_pairs=sum(1 for a,b in zip(aln_a,aln_b) if _is_wobble(a,b))
    similarity=(wc_pairs+wobble_pairs)/len(mirna_seq)*100 if mirna_seq else 0

    # Consecutive mismatch check
    max_cons=0; cur_cons=0
    for ch in pipes:
        if ch!='|': cur_cons+=1; max_cons=max(max_cons,cur_cons)
        else: cur_cons=0

    passes=(seed_ok and mismatches<=4 and max_cons<=2 and energy<=-20 and gaps<=max_gaps)
    
    # Score threshold from original miRanda C source (all.c)
    # Default: 50, strict (i-miRNA): 140
    SCORE_THRESHOLD = 50
    
    # Tiered filter: support progressive sensitivity
    # (2026-10-03: every tier now also enforces the total-gap cap `max_gaps`;
    #  a 30-gap garbage alignment no longer passes the loose tier.)
    gaps_ok = gaps <= max_gaps
    tier_strict  = (seed_ok and mismatches<=4 and max_cons<=2 and energy<=-20 and best_score>=SCORE_THRESHOLD and gaps_ok)
    tier_moderate = (seed_ok and mismatches<=6 and max_cons<=3 and energy<=-15 and best_score>=SCORE_THRESHOLD*0.7 and gaps_ok)
    tier_loose   = (mismatches<=10 and max_cons<=4 and energy<=-10 and best_score>=SCORE_THRESHOLD*0.4 and gaps_ok)

    aln_str=(f"miRNA  5' {''.join(aln_a)} 3'\n"
             f"         {''.join(pipes)}\n"
             f"target 3' {''.join(aln_b)} 5'")

    return AlignmentResult(
        mirna_id=mirna_id, mirna_seq=mirna_seq,
        target_id=target_id, target_start=t_start, target_end=t_end,
        score=best_score, energy=energy,
        num_mismatches=mismatches, num_gaps=gaps,
        seed_perfect=seed_ok, query_cover=query_cover,
        identity=identity, similarity=similarity,
        alignment_str=aln_str, passes_filters=tier_strict,
        tier_strict=tier_strict, tier_moderate=tier_moderate, tier_loose=tier_loose,
        query_start=query_s, query_end=query_e,
        alignment_length=aln_len,
        position_binding=pos_binding,
    )


def _estimate_energy(aln_a: list, aln_b: list) -> float:
    try:
        import RNA
        seq_a=''.join(c for c in aln_a if c!='-')
        seq_b=''.join(c for c in aln_b if c!='-')
        if seq_a and seq_b:
            fc=RNA.fold_compound(seq_a+'&'+seq_b)
            return fc.mfe()[1]
    except ImportError: pass

    NN={('A','U'):-2.0,('U','A'):-2.0,('G','C'):-3.0,('C','G'):-3.0,
        ('G','U'):-1.0,('U','G'):-1.0}
    e=4.0
    for a,b in zip(aln_a,aln_b):
        if a=='-' or b=='-': e+=1.0
        else: e+=NN.get((a.upper(),b.upper()),2.0)
    return e


# Re-export helper for pipeline
def get_position_binding(aln_a, aln_b, pipes):
    return _get_position_binding(list(aln_a), list(aln_b), list(pipes))


def check_position_constraint(pos_binding, positions):
    return _check_position_constraint(pos_binding, positions)
