from __future__ import annotations
"""
PAmiRDB v3 prediction scoring system.

HONESTY NOTE (2026-10-03): despite the historical function/field names
(_validate_psrna, _validate_rnahybrid, miranda_*, psrna_*, rnahybrid_*), this
module does NOT call miRanda, psRNATarget or RNAhybrid. It is a single custom
engine: a Smith-Waterman-style DP alignment (alignment.py, "custom SW-DP")
followed by local heuristic rechecks that borrow the *ideas* of those tools
(position-weighted complementarity, MFE-style scoring, seed checks). The
consensus_detail string reports the real layer names; the psrna_*/rnahybrid_*
JSON field names are kept for API/DB compatibility only.
"""
import sys, math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ── Seed Region Quality Scoring (from miRNA-seed-matching-counter) ───

def _wc_pair(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('A', 'U'), ('U', 'A'), ('G', 'C'), ('C', 'G')}


def _wobble_pair(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('G', 'U'), ('U', 'G')}


def compute_seed_quality(alignment_str: str) -> dict:
    """
    Analyze seed region (positions 2-8) complementarity from the alignment.

    Returns:
      seed_wc:    number of Watson-Crick pairs in seed (0-7)
      seed_wobble: number of G:U wobble pairs in seed (0-7)
      seed_mismatch: number of mismatches/gaps in seed (0-7)
      seed_score:    weighted quality (0-100), WC=15pt, wobble=5pt each
      is_seed_perfect: True if all 7 positions are WC pairs

    2026-10-03 fix: alignment.py only ever emits '|' (any positive-scoring
    pair — WC *or* G:U wobble) and '.' (mismatch); it never emits ':'. The old
    ':' branch was unreachable, so seed_wobble_count was structurally always 0
    ("100% perfect seed" was a bug artifact). Wobble is now classified from the
    actual aligned base pair.
    """
    lines = alignment_str.split('\n')
    if len(lines) < 3:
        return {"seed_wc": 0, "seed_wobble": 0, "seed_mismatch": 7,
                "seed_score": 0, "is_seed_perfect": False}

    mirna_line = lines[0].replace("miRNA  5' ", "").replace(" 3'", "").strip()
    pipe_line = lines[1].strip()
    target_line = lines[2].replace("target 3' ", "").replace(" 5'", "").strip()

    # Count miRNA positions through the alignment (skip gaps in miRNA)
    seed_wc = 0
    seed_wobble = 0
    seed_mismatch = 0
    mirna_pos = 0

    for m_char, t_char, p_char in zip(mirna_line, target_line, pipe_line):
        if m_char == '-':
            continue
        mirna_pos += 1
        if not (2 <= mirna_pos <= 8):
            continue
        if p_char == '|' and _wc_pair(m_char, t_char):
            seed_wc += 1
        elif p_char == '|' and _wobble_pair(m_char, t_char):
            seed_wobble += 1
        else:
            seed_mismatch += 1

    # Score: WC = 15pt each (max 105, capped at 100), wobble = 5pt each
    seed_score = min(100, seed_wc * 15 + seed_wobble * 5)

    return {
        "seed_wc": seed_wc,
        "seed_wobble": seed_wobble,
        "seed_mismatch": seed_mismatch + max(0, 7 - seed_wc - seed_wobble - seed_mismatch),
        "seed_score": seed_score,
        "is_seed_perfect": (seed_wc == 7),
    }

sys.path.insert(0, str(Path(__file__).parent))

from alignment import align_mirna_to_target, AlignmentResult
from psrnatarget import PsRNATargetResult, _position_weight
from rnahybrid import RNAhybridResult
from rna22 import RNA22Result, validate_with_rna22
from tapir import TAPIRResult, validate_with_tapir
from psrobot import PsRobotResult, validate_with_psrobot

# Expectation cutoff for the local position-weighted recheck layer (see _validate_psrna).
EXPECTATION_CUTOFF = 5.0

# ── Prediction layer selection (2026-10-03) ─────────────────────────
# Request tokens accepted from callers (e.g. POST /api/predict "algorithms").
_ALGO_ALIASES = {
    'miranda': 'core', 'core': 'core', 'swdp': 'core', 'sw-dp': 'core',
    'psrna': 'psrna', 'psrnatarget': 'psrna',
    'rnahybrid': 'mfe', 'mfe': 'mfe',
    'rna22': 'rna22', 'tapir': 'tapir', 'psrobot': 'psrobot',
}
# Honest layer names written into consensus_detail (they are LOCAL layers,
# not external tools; see module docstring).
_ALGO_LABELS = {
    'core':    'custom SW-DP',
    'psrna':   'local heuristic recheck',
    'mfe':     'local MFE heuristic',
    'rna22':   'local pattern heuristic',
    'tapir':   'local accessibility heuristic',
    'psrobot': 'local rule-based heuristic',
}


def _normalize_algorithms(algorithms):
    """Normalize a caller-supplied algorithm list to layer keys.

    None -> default chain (behaviour unchanged). Unknown tokens are ignored.
    """
    if algorithms is None:
        return None
    if isinstance(algorithms, str):
        algorithms = [algorithms]
    out = set()
    for a in algorithms:
        key = _ALGO_ALIASES.get(str(a).strip().lower())
        if key:
            out.add(key)
    return out


def _is_wc(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('A', 'U'), ('U', 'A'), ('G', 'C'), ('C', 'G')}


def _is_wobble(a: str, b: str) -> bool:
    a, b = a.upper().replace('T', 'U'), b.upper().replace('T', 'U')
    return (a, b) in {('G', 'U'), ('U', 'G')}


def _validate_psrna(mr, mirna_id: str, target_id: str) -> Optional[PsRNATargetResult]:
    """Local position-weighted complementarity recheck of the SW-DP alignment.

    (Name kept for API compatibility — this is a self-built heuristic, NOT the
    psRNATarget program; see module docstring.)
    """
    lines = mr.alignment_str.split('\n')
    if len(lines) < 3: return None
    pipes = lines[1].strip()
    mline = lines[0].replace("miRNA  5' ", "").replace(" 3'", "").strip()
    tline = lines[2].replace("target 3' ", "").replace(" 5'", "").strip()
    
    score = 0.0; mm = 0; wb = 0; mpos = 0; seed = True; ctr = 0
    for m, t, p in zip(mline, tline, pipes):
        if m == '-' or t == '-': continue
        mpos += 1; w = _position_weight(mpos)
        if p == '|': score += 1.0*w
        elif p == ':': score += 0.5*w; wb += 1
        else: mm += 1
        if 2 <= mpos <= 8 and p != '|': seed = False
        if 9 <= mpos <= 11 and p != '|': ctr += 1
    
    # 2026-10-03 fix: the old threshold `exp(-3*score/mpos) <= 5.0` was <= 1 for
    # every score>0, i.e. it could never reject a hit. Real exponential gate on
    # the position-weighted total score (scale: 21-nt perfect match = 26.4):
    #   E = exp(4.0 - 0.2 * score); E <= 5.0  ⇔  score >= ~12
    exp = math.exp(4.0 - 0.2 * score)
    passes = seed and mm <= 4 and exp <= EXPECTATION_CUTOFF
    
    return PsRNATargetResult(
        mirna_id=mirna_id, target_id=target_id,
        target_start=mr.target_start, target_end=mr.target_end,
        alignment_score=score, expectation=exp, max_energy=mr.energy,
        num_mismatches=mm, num_wobbles=wb, seed_perfect=seed,
        cleavage_possible=(ctr == 0), inhibition_possible=(ctr >= 1),
        alignment_str=mr.alignment_str, passes=passes,
    )


def _validate_rnahybrid(mr, mirna_id: str, target_id: str) -> Optional[RNAhybridResult]:
    """Local MFE-style scoring recheck of the SW-DP alignment.

    (Name/fields kept for API compatibility — self-built heuristic, NOT the
    RNAhybrid program; see module docstring.)
    """
    lines = mr.alignment_str.split('\n')
    if len(lines) < 3: return None
    mline = lines[0].replace("miRNA  5' ", "").replace(" 3'", "").strip()
    tline = lines[2].replace("target 3' ", "").replace(" 5'", "").strip()
    
    mfe = 4.0; swc = 0; mpos = 0
    for m, t in zip(mline, tline):
        if m != '-' and t != '-':
            if _is_wc(m, t): mfe += -2.0
            elif _is_wobble(m, t): mfe += -1.0
            else: mfe += 1.5
        else: mfe += 1.0
        if m != '-':
            mpos += 1
            if 2 <= mpos <= 8 and _is_wc(m, t): swc += 1
    
    seed_ok = swc >= 6
    passes = mfe <= -20.0 and seed_ok
    
    return RNAhybridResult(
        mirna_id=mirna_id, target_id=target_id, mfe=mfe,
        target_start=mr.target_start, target_end=mr.target_end,
        seed_perfect=seed_ok, alignment_str=mr.alignment_str, passes=passes,
    )


@dataclass
class ConsensusResult:
    mirna_id: str; mirna_seq: str; target_id: str
    target_name: str = ""; target_family: str = ""
    miranda: Optional[AlignmentResult] = None
    psrna: Optional[PsRNATargetResult] = None
    rnahyb: Optional[RNAhybridResult] = None
    rna22: Optional[RNA22Result] = None
    tapir: Optional[TAPIRResult] = None
    psrobot: Optional[PsRobotResult] = None
    num_algorithms: int = 0; consensus_level: str = ""
    best_energy: float = 0.0; best_identity: float = 0.0
    seed_quality_score: float = 0.0; seed_perfect_wc: int = 0; seed_wobble_count: int = 0
    consensus_detail: str = ""; passes_pamirdb_filter: bool = False


def run_consensus_prediction(mirna_id, mirna_seq, target_id, target_name, target_family, target_seq,
                              fast_mode=True, algorithms=None):
    """
    Run the local prediction layers for one miRNA-target pair.

    fast_mode=True (default): core SW-DP + the two fast heuristic rechecks
    fast_mode=False: also the slower local heuristics (pattern/accessibility/rule)

    algorithms: optional selection of layers to run, e.g. ['core','psrna','mfe'],
                or the aliases used by the web API ('miranda','psrna','rnahybrid',
                'rna22','tapir','psrobot').  None = default chain.  The slow
                layers (rna22/tapir/psrobot) still require fast_mode=False.
    """
    result = ConsensusResult(mirna_id=mirna_id, mirna_seq=mirna_seq,
                              target_id=target_id, target_name=target_name, target_family=target_family)
    algos = []
    requested = _normalize_algorithms(algorithms)

    def _want(layer):
        return requested is None or layer in requested

    r1 = align_mirna_to_target(mirna_id, mirna_seq, target_id, target_seq)
    core_ok = bool(r1 and r1.passes_filters)
    if core_ok:
        result.miranda = r1
        algos.append(_ALGO_LABELS['core'])

    r2 = r3 = None
    if core_ok:
        if _want('psrna'):
            r2 = _validate_psrna(r1, mirna_id, target_id)
            if r2 and r2.passes:
                result.psrna = r2; r2.consensus_votes = 1
                algos.append(_ALGO_LABELS['psrna'])

        if _want('mfe'):
            r3 = _validate_rnahybrid(r1, mirna_id, target_id)
            if r3 and r3.passes:
                result.rnahyb = r3; algos.append(_ALGO_LABELS['mfe'])

        # Slow local heuristics — only in full mode
        if not fast_mode:
            if _want('rna22'):
                r4 = validate_with_rna22(r1, mirna_id, target_id, target_seq)
                if r4 and r4.passes:
                    result.rna22 = r4; algos.append(_ALGO_LABELS['rna22'])

            if _want('tapir'):
                try:
                    r5 = validate_with_tapir(r1, mirna_id, target_id, target_seq)
                    if r5 and r5.passes:
                        result.tapir = r5; algos.append(_ALGO_LABELS['tapir'])
                except: pass

            if _want('psrobot'):
                try:
                    r6 = validate_with_psrobot(r1, mirna_id, target_id, target_seq)
                    if r6 and r6.passes:
                        result.psrobot = r6; algos.append(_ALGO_LABELS['psrobot'])
                except: pass


    if not algos: return None

    result.num_algorithms = len(algos)
    result.consensus_detail = '+'.join(algos)
    LEVEL_MAP = {1:'LOW', 2:'LOW+', 3:'MEDIUM', 4:'MEDIUM+', 5:'HIGH',
                 6:'HIGH+', 7:'VERY HIGH', 8:'VERY HIGH'}
    result.consensus_level = LEVEL_MAP.get(len(algos), 'LOW')
    
    es = [r1.energy] if r1 else []
    if r2: es.append(getattr(r2, 'max_energy', 0))
    if r3: es.append(getattr(r3, 'mfe', 0))
    result.best_energy = min(es) if es else 0.0
    result.best_identity = r1.identity if r1 else 0.0
    result.passes_pamirdb_filter = result.miranda is not None

    # Seed quality scoring (from miRNA-seed-matching-counter methodology)
    if r1 and r1.alignment_str:
        sq = compute_seed_quality(r1.alignment_str)
        result.seed_quality_score = sq["seed_score"]
        result.seed_perfect_wc = sq["seed_wc"]
        result.seed_wobble_count = sq["seed_wobble"]
    return result


def to_dict(cr: ConsensusResult) -> dict:
    d = {"mirna_id": cr.mirna_id, "mirna_seq": cr.mirna_seq,
         "target_virus_id": cr.target_id, "target_virus_name": cr.target_name,
         "target_virus_family": cr.target_family,
         "num_algorithms": cr.num_algorithms, "consensus_level": cr.consensus_level,
         "consensus_detail": cr.consensus_detail,
         "best_energy": cr.best_energy, "best_identity": cr.best_identity,
         "seed_quality_score": cr.seed_quality_score,
         "seed_perfect_wc": cr.seed_perfect_wc,
         "seed_wobble_count": cr.seed_wobble_count}
    if cr.miranda:
        r = cr.miranda
        d.update(seed_perfect=r.seed_perfect, query_cover=r.query_cover,
                 query_start=r.query_start, query_end=r.query_end,
                 alignment_length=r.alignment_length,
                 target_start=r.target_start, target_end=r.target_end,
                 miranda_score=r.score, miranda_energy=r.energy,
                 miranda_identity=r.identity, miranda_similarity=r.similarity,
                 miranda_mismatches=r.num_mismatches, miranda_gaps=r.num_gaps,
                 alignment=r.alignment_str)
    if cr.psrna:
        r = cr.psrna
        d.update(psrna_score=r.alignment_score, psrna_expectation=r.expectation,
                 psrna_energy=r.max_energy, psrna_cleavage=r.cleavage_possible,
                 psrna_inhibition=r.inhibition_possible, psrna_alignment=r.alignment_str)
    if cr.rnahyb:
        r = cr.rnahyb
        d.update(rnahybrid_mfe=r.mfe, rnahybrid_seed=r.seed_perfect,
                 rnahybrid_alignment=r.alignment_str)
    if cr.rna22:
        r = cr.rna22
        d.update(rna22_mfe=r.mfe, rna22_pattern_score=r.pattern_score,
                 rna22_seed=r.seed_perfect, rna22_alignment=r.alignment_str)
    if cr.tapir:
        r = cr.tapir
        d.update(tapir_score=r.tapir_score, tapir_accessibility=r.accessibility_score,
                 tapir_seed=r.seed_score, tapir_up_energy=r.up_energy)
    return d


# ── Union/Intersection/Individual stratified output (Paper 2) ─────

def stratified_consensus(results: list[dict]) -> dict:
    """
    Generate three-layer consensus output per paper 2 methodology:
      - Individual:  per-algorithm predictions
      - Union:       all unique miRNA-virus pairs (high sensitivity)
      - Intersection: pairs found by >=2, >=3, >=4 tools (high specificity)
    """
    # Individual
    individual = {}
    for r in results:
        detail = r.get('consensus_detail', 'miRanda')
        for tool in detail.split('+'):
            tool = tool.strip()
            individual.setdefault(tool, []).append(r['mirna_id'] + '|' + r.get('target_virus_id', r.get('virus_id', '')))

    # Union (deduplicated miRNA-virus pairs)
    union = list(set(r['mirna_id'] + '|' + r.get('target_virus_id', r.get('virus_id', ''))
                     for r in results))

    # Intersection by algorithm count
    intersection = {}
    for n in [2, 3, 4, 5]:
        pairs = [r for r in results if r.get('num_algorithms', 0) >= n]
        intersection[f'>={n}_tools'] = {
            'count': len(pairs),
            'pairs': [r['mirna_id'] + '|' + r.get('target_virus_id', r.get('virus_id', ''))
                       for r in pairs],
        }

    return {
        'individual': {tool: {'count': len(pairs)} for tool, pairs in individual.items()},
        'union': {'count': len(union)},
        'intersection': intersection,
    }


if __name__ == '__main__':
    cr = run_consensus_prediction(
        "ath-miR408-5p", "CGGGGAACAGGCAGAGCAUGG",
        "ACMV", "African cassava mosaic virus", "geminiviridae",
        "GTCCCCTTCGTCCCTACGAGCT")
    if cr:
        s = {"HIGH":"***","MEDIUM":"** ","LOW":"*  "}.get(cr.consensus_level,"?  ")
        print(f"{s} [{cr.consensus_level}] {cr.mirna_id} -> {cr.target_name}")
        print(f"   Layers: {cr.consensus_detail} ({cr.num_algorithms} layer(s) passed)")
        print(f"   Energy: {cr.best_energy:.1f}")
    else:
        print("No consensus")
