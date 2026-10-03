# pyright: reportUnknownArgumentType=false
"""Structural metrics computed from RAGResult — no extra LLM calls.

These are the cheap-to-compute baseline metrics. The expensive metric
(LLM-as-judge for citation accuracy) lives in eval.judge.

We deliberately don't ship a "correctness" or "fluency" metric here —
those need either ground-truth answers (we don't have any) or LLM-judge
(separate module). What's measurable for free:

  - structural validity (citation_valid)
  - "did we attempt an answer" (non-empty / non-fallback)
  - retrieval shape (chunks per question, citations per question)
  - latency

Together these catch big regressions: if a sprint drops citation_valid
or doubles latency, the structural metrics will show it without a single
LLM call.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel

from neblab_rag.rag.generator import EMPTY_CONTEXT_REPLY


class CaseResult(BaseModel):
    """Per-question outcome — what the runner records for each EvalCase."""

    case_id: str
    question: str
    answer: str
    citation_valid: bool
    citations_count: int
    chunks_retrieved: int
    latency_seconds: float
    expected_coverage: str  # echoes EvalCase.corpus_coverage_expected
    error: str | None = None
    # Optional — populated only when --judge ran. Keep on the case so the
    # JSON report shows per-claim verdicts inline with the question.
    judgments: list[dict[str, object]] = []


class AggregateMetrics(BaseModel):
    n_cases: int
    n_errors: int
    citation_validity_rate: float  # over non-error cases
    answered_rate: float  # % that did NOT fall back to "literature insufficient"
    expected_yes_answered_rate: float  # honesty: when corpus has it, did we answer?
    expected_no_refused_rate: float  # honesty: when corpus doesn't, did we refuse?
    avg_citations_per_answer: float
    avg_chunks_retrieved: float
    latency_p50: float
    latency_p95: float
    # Judge metrics: only populated when judge was run (else all 0.0)
    n_judgments: int = 0
    citation_supported_rate: float = 0.0
    citation_partial_rate: float = 0.0
    citation_not_supported_rate: float = 0.0


# The LLM phrases refusals many ways; we match the structural pattern of
# "[literature noun] [optional qualifier] [negation] [topic verb]". The
# Sprint-1 v0.1 baseline (n=41) added 2 false positives over the simpler
# "暂未找到" matcher: "文献中未提及" and "文献片段仅讨论了... 未涉及".
_CHINESE_REFUSAL_PATTERNS = [
    re.compile(r"文献[一-鿿]{0,4}中暂未找到"),
    # Match "文献…未提及/未涉及/etc" within ~25 chars (one clause). Use [^。\n]
    # so any non-sentence-ending char counts (CJK, ASCII, punct) — the
    # alternative '[一-鿿]' class missed real refusals with intervening
    # commas/spaces (Sprint 1 v0.1).
    re.compile(r"文献[^。\n]{0,25}(?:未提及|未涉及|未讨论|不包含|不涉及)"),
    # "无法回答" with possible adverb between (e.g. "无法直接回答") and longer
    # noun-phrase before "问题|您的" (Sprint-1 86q baseline added "无法回答关于
    # 使用...这一问题" where the topic phrase exceeds the 20-char window).
    re.compile(r"无法[^。\n]{0,8}回答[^。\n]{0,60}(?:问题|您的)"),
    re.compile(r"根据[^。\n]{0,30}文献[^。\n]{0,15}(?:无法|不能)"),
]


def is_fallback_answer(answer: str) -> bool:
    """Detect both English and Chinese 'no relevant findings' templates.

    Chinese uses a set of regexes (not literal substring) because the LLM
    varies the phrasing freely. We match the structural pattern of
    'literature-noun + (qualifier) + negation' rather than fixed strings,
    based on real refusal phrasings observed across Sprint-0 → Sprint-1
    eval baselines (see git log on this file).
    """
    if answer == EMPTY_CONTEXT_REPLY:
        return True
    a = answer.strip()
    if "literature insufficient" in a:
        return True
    # English refusal templates (must match the PvAnswerGenerator's refusal phrases)
    _EN_REFUSAL_MARKERS = [
        "relevant information was not found",
        "not found in the database",
        "no relevant information",
        "insufficient information",
        "cannot answer based on the provided",
        "the provided fragments do not contain",
    ]
    a_lower = a.lower()
    if any(marker in a_lower for marker in _EN_REFUSAL_MARKERS):
        return True
    return any(p.search(a) for p in _CHINESE_REFUSAL_PATTERNS)


def aggregate(results: Sequence[CaseResult]) -> AggregateMetrics:
    if not results:
        return AggregateMetrics(
            n_cases=0,
            n_errors=0,
            citation_validity_rate=0.0,
            answered_rate=0.0,
            expected_yes_answered_rate=0.0,
            expected_no_refused_rate=0.0,
            avg_citations_per_answer=0.0,
            avg_chunks_retrieved=0.0,
            latency_p50=0.0,
            latency_p95=0.0,
        )

    n_total = len(results)
    errors = [r for r in results if r.error]
    ok = [r for r in results if not r.error]
    n_ok = len(ok)

    answered = [r for r in ok if not is_fallback_answer(r.answer)]
    expected_yes = [r for r in ok if r.expected_coverage == "yes"]
    expected_yes_answered = [r for r in expected_yes if not is_fallback_answer(r.answer)]
    expected_no = [r for r in ok if r.expected_coverage == "no"]
    expected_no_refused = [r for r in expected_no if is_fallback_answer(r.answer)]

    latencies = sorted(r.latency_seconds for r in ok)

    # Judge metrics — flatten all judgments across all cases
    all_judgments = [j for r in ok for j in r.judgments]
    judged = [j for j in all_judgments if j.get("verdict") != "judge_error"]
    n_judged = len(judged)

    return AggregateMetrics(
        n_cases=n_total,
        n_errors=len(errors),
        citation_validity_rate=_rate(sum(1 for r in ok if r.citation_valid), n_ok),
        answered_rate=_rate(len(answered), n_ok),
        expected_yes_answered_rate=_rate(len(expected_yes_answered), len(expected_yes)),
        expected_no_refused_rate=_rate(len(expected_no_refused), len(expected_no)),
        avg_citations_per_answer=_avg(r.citations_count for r in answered),
        avg_chunks_retrieved=_avg(r.chunks_retrieved for r in ok),
        latency_p50=_percentile(latencies, 0.50),
        latency_p95=_percentile(latencies, 0.95),
        n_judgments=n_judged,
        citation_supported_rate=_rate(
            sum(1 for j in judged if j.get("verdict") == "supported"), n_judged
        ),
        citation_partial_rate=_rate(
            sum(1 for j in judged if j.get("verdict") == "partial"), n_judged
        ),
        citation_not_supported_rate=_rate(
            sum(1 for j in judged if j.get("verdict") == "not_supported"), n_judged
        ),
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _avg(values: object) -> float:
    items = list(values)  # type: ignore[arg-type]
    return sum(items) / len(items) if items else 0.0


def _percentile(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile. Returns 0 for empty input."""
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, round(p * (len(sorted_values) - 1))))
    return sorted_values[idx]
