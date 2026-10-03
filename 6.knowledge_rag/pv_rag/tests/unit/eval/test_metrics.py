"""Tests for eval structural metrics."""

import pytest

from neblab_rag.eval.metrics import (
    CaseResult,
    aggregate,
    is_fallback_answer,
)


def _result(
    *,
    case_id: str = "c",
    answer: str = "Per [1].",
    citation_valid: bool = True,
    citations_count: int = 1,
    chunks_retrieved: int = 5,
    latency: float = 1.0,
    expected: str = "yes",
    error: str | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        question="?",
        answer=answer,
        citation_valid=citation_valid,
        citations_count=citations_count,
        chunks_retrieved=chunks_retrieved,
        latency_seconds=latency,
        expected_coverage=expected,
        error=error,
    )


def test_is_fallback_answer_detects_english() -> None:
    assert is_fallback_answer("Sorry, the literature insufficient to answer.") is True


def test_is_fallback_answer_detects_chinese() -> None:
    assert is_fallback_answer("根据文献片段，文献中暂未找到相关结论。") is True


def test_is_fallback_answer_detects_chinese_with_qualifier_variants() -> None:
    """Sprint 2.5 v1 baseline (n=41) caught a real refusal as 'answered'
    because the LLM said '文献片段中暂未找到' instead of plain '文献中暂未找到'."""
    assert is_fallback_answer("文献片段中暂未找到相关结论。") is True
    assert is_fallback_answer("文献库中暂未找到相关内容。") is True
    assert is_fallback_answer("根据文献片段中暂未找到具体结论") is True


def test_is_fallback_answer_detects_more_refusal_phrasings() -> None:
    """Sprint 1 v0.1 baseline (n=41 against fulltext) added these phrasings —
    the LLM gets more creative when it has a richer corpus to politely refuse."""
    assert is_fallback_answer("文献中未提及CRISPR基因编辑技术") is True
    assert is_fallback_answer("文献片段仅讨论了干旱区，未涉及海洋酸化") is True
    assert is_fallback_answer("根据所提供的文献片段，无法回答您的问题") is True


def test_is_fallback_answer_does_not_match_unrelated_chinese() -> None:
    """Tight regexes — genuine prose shouldn't match accidentally."""
    assert is_fallback_answer("这篇文献讨论了荒漠化的机制") is False
    assert is_fallback_answer("文献中讨论了多种暂时性的影响") is False
    assert is_fallback_answer("无法精确测量该现象") is False  # "无法" w/o "回答 + 文献"


def test_is_fallback_answer_skips_substantive_answer() -> None:
    assert is_fallback_answer("Per [1] desertification is driven by X.") is False


def test_aggregate_empty_returns_zeros() -> None:
    m = aggregate([])
    assert m.n_cases == 0
    assert m.citation_validity_rate == 0.0


def test_aggregate_citation_validity_only_over_non_error() -> None:
    m = aggregate(
        [
            _result(citation_valid=True),
            _result(citation_valid=False),
            _result(error="boom", citation_valid=False),
        ]
    )
    assert m.n_cases == 3
    assert m.n_errors == 1
    assert m.citation_validity_rate == pytest.approx(0.5)  # 1 of 2 non-error


def test_aggregate_honesty_rates() -> None:
    m = aggregate(
        [
            # 2 expected-yes, 1 answered, 1 fallback → 50% answered
            _result(expected="yes", answer="Per [1] X."),
            _result(expected="yes", answer="文献库中暂未找到相关结论。"),
            # 2 expected-no, 1 refused, 1 hallucinated → 50% refused
            _result(expected="no", answer="文献中暂未找到相关结论。"),
            _result(expected="no", answer="Per [1] hallucinated answer."),
        ]
    )
    assert m.expected_yes_answered_rate == pytest.approx(0.5)
    assert m.expected_no_refused_rate == pytest.approx(0.5)


def test_aggregate_avg_citations_only_counts_answered() -> None:
    """Fallback answers shouldn't pull avg_citations down — they have 0 cites
    but they're a separate kind of result, tracked by answered_rate."""
    m = aggregate(
        [
            _result(answer="Per [1][2].", citations_count=2),
            _result(answer="Per [1][2][3].", citations_count=3),
            _result(answer="文献库中暂未找到相关结论。", citations_count=0),
        ]
    )
    assert m.avg_citations_per_answer == pytest.approx(2.5)  # (2+3)/2


def test_aggregate_latency_p95() -> None:
    m = aggregate([_result(latency=float(i)) for i in range(1, 21)])
    # 20 values 1..20 → p95 nearest-rank → idx round(0.95 * 19) = 18 → value 19
    assert m.latency_p95 == 19.0
    assert m.latency_p50 == 11.0  # idx round(0.50 * 19) = 10 → value 11
