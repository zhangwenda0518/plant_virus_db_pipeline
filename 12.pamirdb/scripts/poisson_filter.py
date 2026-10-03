"""
PAmiRDB v5.1 — Poisson Statistical Significance Filter (P1).

Based on: Cross-Kingdom-miRNA-Predictor (1st-order Markov + Poisson + FDR)
Ref: Teng et al. (2018) Cell Host & Microbe

Unlike sequence alignment, this method asks:
  "Does this miRNA's seed sequence appear in the viral genome
   significantly more often than expected by chance?"

Algorithm:
  1. Build 1st-order Markov model on target genome (GC bias correction)
  2. Calculate expected occurrence probability of seed k-mer
  3. Count observed seed matches in target
  4. Poisson test: P(X >= k | lambda)
  5. Benjamini-Hochberg FDR correction across all pairs

Output: P-value and FDR Q-value for each prediction.
"""

import math
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

NEARLY_ZERO = 1e-300  # Prevent log(0) / underflow


def _build_markov_model(sequence: str) -> dict:
    """
    Build 1st-order Markov model with Laplace (+1) smoothing.
    Returns {mono_probs, trans_probs}.
    """
    seq = sequence.upper().replace('T', 'U')
    bases = ['A', 'U', 'G', 'C']
    alpha = 1.0

    # Mononucleotide frequencies
    mono_counts = {b: 0 for b in bases}
    for c in seq:
        if c in mono_counts:
            mono_counts[c] += 1
    total = sum(mono_counts.values())
    mono_probs = {b: (mono_counts[b] + alpha) / (total + 4 * alpha) for b in bases}

    # Dinucleotide transition frequencies
    di_counts = defaultdict(int)
    for i in range(len(seq) - 1):
        di = seq[i:i+2]
        if all(c in bases for c in di):
            di_counts[di] += 1

    trans_probs = {}
    for n1 in bases:
        row_total = sum(di_counts.get(n1 + n2, 0) for n2 in bases)
        for n2 in bases:
            dinuc = n1 + n2
            trans_probs[dinuc] = (di_counts.get(dinuc, 0) + alpha) / (row_total + 4 * alpha)

    return {"mono_probs": mono_probs, "trans_probs": trans_probs}


def _seed_expected_prob(seed_seq: str, model: dict) -> float:
    """Calculate expected probability of seed sequence under Markov model."""
    seed = seed_seq.upper().replace('T', 'U')
    mono = model["mono_probs"]
    trans = model["trans_probs"]

    prob = mono.get(seed[0], 0.25)
    for i in range(len(seed) - 1):
        dinuc = seed[i:i+2]
        prob *= trans.get(dinuc, 0.25)

    return max(prob, NEARLY_ZERO)


def _count_seed_in_target(seed_seq: str, target_seq: str) -> int:
    """Count occurrences of seed in target (exact match, non-overlapping)."""
    seed = seed_seq.upper().replace('T', 'U')
    target = target_seq.upper().replace('T', 'U')

    if len(seed) > len(target):
        return 0

    count = 0
    # Sliding window exact match
    for i in range(len(target) - len(seed) + 1):
        if target[i:i + len(seed)] == seed:
            count += 1
    return count


def _poisson_pvalue(observed: int, expected_lambda: float) -> float:
    """
    Calculate P(X >= observed) under Poisson(lambda).
    Uses incomplete gamma for numerical stability.
    Equivalent to: 1 - sum_{k=0}^{observed-1} (lambda^k * e^{-lambda} / k!)
    """
    if observed == 0:
        return 1.0
    if expected_lambda <= 0:
        expected_lambda = NEARLY_ZERO

    # Regularized lower incomplete gamma: P(X < observed | lambda)
    # Use series expansion for stability
    # P(X >= k) = 1 - e^{-lambda} * sum_{i=0}^{k-1} lambda^i / i!
    # For large lambda or k, use log-space computation

    # Simple iterative calculation (stable for small k)
    p_cumulative = 0.0
    term = 1.0  # lambda^0 / 0!
    p_cumulative += term

    for i in range(1, observed):
        term *= expected_lambda / i
        p_cumulative += term
        # Prevent overflow by clamping
        if term > 1e100:
            term = 1e100
        if p_cumulative > 1e100:
            p_cumulative = 1e100

    p_less_than_k = p_cumulative * math.exp(-expected_lambda)

    # Handle edge case: if lambda is very large
    if p_less_than_k > 1.0:
        p_less_than_k = 1.0

    return 1.0 - p_less_than_k


def _bh_fdr_correction(pvalues: list) -> list:
    """
    Benjamini-Hochberg FDR correction.
    Returns list of Q-values aligned with input p-values.
    """
    n = len(pvalues)
    if n == 0:
        return []

    # Sort indices by p-value
    if HAS_NUMPY:
        sorted_idx = np.argsort(pvalues)
        sorted_p = np.array(pvalues)[sorted_idx]
        ranks = np.arange(1, n + 1)
        qvalues = sorted_p * n / ranks
        # Ensure monotonicity
        for i in range(n - 2, -1, -1):
            qvalues[i] = min(qvalues[i], qvalues[i + 1])
        # Clamp to [0, 1]
        qvalues = np.clip(qvalues, 0, 1)
        # Unsort
        result = np.zeros(n)
        result[sorted_idx] = qvalues
        return result.tolist()
    else:
        sorted_pairs = sorted(enumerate(pvalues), key=lambda x: x[1])
        sorted_idx = [p[0] for p in sorted_pairs]
        sorted_p = [p[1] for p in sorted_pairs]
        qvalues = [min(sorted_p[i] * n / (i + 1), 1.0) for i in range(n)]
        for i in range(n - 2, -1, -1):
            qvalues[i] = min(qvalues[i], qvalues[i + 1])
        result = [0.0] * n
        for idx, q in zip(sorted_idx, qvalues):
            result[idx] = q
        return result


# ── Seed Extraction ──────────────────────────────────────────────────

def extract_seed_sequence(mirna_seq: str, seed_start: int = 2,
                          seed_end: int = 8) -> str:
    """Extract the seed region (default: positions 2-8, 1-indexed) from miRNA."""
    # Convert to 0-indexed
    s = seed_start - 1
    e = seed_end
    if s < 0:
        s = 0
    if e > len(mirna_seq):
        e = len(mirna_seq)
    return mirna_seq[s:e]


# ── Main Poisson Filter ───────────────────────────────────────────────

def score_prediction_poisson(mirna_id: str, mirna_seq: str,
                              virus_id: str, virus_seq: str,
                              seed_start: int = 2, seed_end: int = 8,
                              ) -> dict:
    """
    Calculate Poisson-based statistical significance for one miRNA-virus pair.

    Returns:
      seed_seq:        seed region extracted
      expected_lambda: expected occurrences under Markov null model
      observed_count:  actual occurrences in virus genome
      p_value:         Poisson P(X >= observed | lambda)
      log10_p_value:   -log10(p_value) for ranking
      is_significant:  p < 0.05
    """
    seed = extract_seed_sequence(mirna_seq, seed_start, seed_end)
    if len(seed) < 4:
        return {"seed_seq": seed, "p_value": 1.0, "log10_p_value": 0.0,
                "is_significant": False}

    # Build Markov model on virus genome
    model = _build_markov_model(virus_seq)

    # Expected probability and lambda
    p_seed = _seed_expected_prob(seed, model)
    windows = len(virus_seq) - len(seed) + 1
    if windows <= 0:
        return {"seed_seq": seed, "p_value": 1.0, "log10_p_value": 0.0,
                "is_significant": False, "expected_lambda": 0.0, "observed_count": 0}

    expected_lambda = windows * p_seed

    # Observed count
    observed = _count_seed_in_target(seed, virus_seq)

    # P-value
    p_val = _poisson_pvalue(observed, expected_lambda)

    return {
        "seed_seq": seed,
        "seed_length": len(seed),
        "windows_scanned": windows,
        "expected_lambda": round(expected_lambda, 4),
        "observed_count": observed,
        "p_value": p_val,
        "log10_p_value": -math.log10(max(p_val, 1e-300)),
        "is_significant": p_val < 0.05,
    }


def apply_poisson_filter(results):
    # type: (List[Dict]) -> List[Dict]
    """
    Apply Poisson filter to all existing predictions.
    Adds poisson_* fields and FDR Q-value to each result.

    Expects results from pipeline with mirna_seq and virus sequence info.
    If virus_seq not available in result, loads from data files.
    """
    if not results:
        return results

    data_dir = Path(__file__).parent.parent / "data"

    # Load virus sequences if needed
    virus_seqs = {}
    fasta = data_dir / "virus_genomes" / "viruses.fasta"
    if fasta.exists():
        cid = None
        cseq = []
        for line in open(fasta):
            line = line.strip()
            if line.startswith('>'):
                if cid:
                    virus_seqs[cid] = ''.join(cseq)
                cid = line[1:].split('|')[0]
                cseq = []
            else:
                cseq.append(line)
        if cid:
            virus_seqs[cid] = ''.join(cseq)

    # Score each prediction
    pvalues = []
    scored = []
    for r in results:
        mirna_id = r.get("mirna_id", "")
        mirna_seq = r.get("mirna_seq", "")
        virus_id = r.get("target_virus_id", r.get("virus_id", ""))
        virus_seq = virus_seqs.get(virus_id, "")

        if mirna_seq and virus_seq:
            ps = score_prediction_poisson(mirna_id, mirna_seq, virus_id, virus_seq)
        else:
            ps = {"p_value": 1.0, "log10_p_value": 0.0, "is_significant": False,
                  "expected_lambda": 0.0, "observed_count": 0, "seed_seq": ""}

        r["poisson_p_value"] = ps["p_value"]
        r["poisson_log10_p_value"] = round(ps["log10_p_value"], 2)
        r["poisson_expected"] = ps.get("expected_lambda", 0)
        r["poisson_observed"] = ps.get("observed_count", 0)
        r["poisson_seed"] = ps.get("seed_seq", "")
        pvalues.append(ps["p_value"])
        scored.append(r)

    # FDR correction across all pairs
    qvalues = _bh_fdr_correction(pvalues)
    for r, q in zip(scored, qvalues):
        r["poisson_fdr_q_value"] = round(q, 4)
        r["poisson_fdr_significant"] = q < 0.05

    return scored


def get_poisson_summary(results):
    # type: (List[Dict]) -> Dict
    """Generate summary stats for Poisson filtering."""
    if not results:
        return {"total": 0, "significant": 0, "fdr_significant": 0}

    sig_p = sum(1 for r in results if r.get("poisson_p_value", 1) < 0.05)
    sig_fdr = sum(1 for r in results if r.get("poisson_fdr_q_value", 1) < 0.05)

    return {
        "total": len(results),
        "significant_p_value": sig_p,
        "significant_p_pct": round(sig_p / len(results) * 100, 1),
        "significant_fdr": sig_fdr,
        "significant_fdr_pct": round(sig_fdr / len(results) * 100, 1),
    }


if __name__ == '__main__':
    # Test
    mirna = "UUUGGAUUGAAGGGAGCUCUA"
    virus = "GTCCCCTTCGTCCCTACGAGCTAAACCUAACCUCCCUCGAGAUttAACCUAACCUCCCUCGAGAUacgt"
    seed = extract_seed_sequence(mirna)
    print(f"Seed: {seed} (positions 2-8)")

    ps = score_prediction_poisson("test-miR159a", mirna, "test-virus", virus)
    for k, v in ps.items():
        print(f"  {k}: {v}")
