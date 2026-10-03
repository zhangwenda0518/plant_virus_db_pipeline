"""Tests for the eval runner — pipeline is mocked."""

from unittest.mock import AsyncMock, MagicMock

from neblab_rag.eval.data import EvalCase
from neblab_rag.eval.runner import build_report, run_eval
from neblab_rag.rag.citation import CitationValidation
from neblab_rag.rag.generator import Citation, GeneratedAnswer
from neblab_rag.rag.pipeline import RAGResult
from neblab_rag.rag.retriever import RetrievedChunk


def _ok_rag_result(query: str = "Q?") -> RAGResult:
    return RAGResult(
        query=query,
        chunks=[
            RetrievedChunk(
                chunk_id=1,
                doc_id=1,
                chunk_index=0,
                openalex_id="W1",
                title="t",
                text="x",
                score=0.9,
            )
        ],
        answer=GeneratedAnswer(
            content="Per [1].",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="t")],
        ),
        citation_validation=CitationValidation(
            is_valid=True, referenced_numbers={1}, invalid_numbers=set()
        ),
    )


def _case(case_id: str = "c1", text: str = "Q?", coverage: str = "yes") -> EvalCase:
    return EvalCase(
        id=case_id,
        text=text,
        language="en",
        difficulty="easy",
        source="handwritten",
        corpus_coverage_expected=coverage,  # type: ignore[arg-type]
    )


async def test_runs_each_case_through_pipeline() -> None:
    pipeline = MagicMock()
    pipeline.answer = AsyncMock(return_value=_ok_rag_result())

    results = await run_eval([_case("a"), _case("b")], pipeline=pipeline)

    assert len(results) == 2
    assert results[0].case_id == "a"
    assert results[0].citation_valid is True
    assert results[0].citations_count == 1
    assert results[0].chunks_retrieved == 1
    assert results[0].error is None
    assert pipeline.answer.await_count == 2


async def test_per_case_failure_is_isolated() -> None:
    """One broken question must not abort the whole eval — operator wants
    a partial report, not nothing."""
    pipeline = MagicMock()
    pipeline.answer = AsyncMock(side_effect=[RuntimeError("provider down"), _ok_rag_result()])

    results = await run_eval([_case("a"), _case("b")], pipeline=pipeline)

    assert len(results) == 2
    assert results[0].error and "provider down" in results[0].error
    assert results[0].answer == ""
    assert results[1].error is None
    assert results[1].citation_valid is True


async def test_passes_top_k_to_pipeline() -> None:
    pipeline = MagicMock()
    pipeline.answer = AsyncMock(return_value=_ok_rag_result())

    await run_eval([_case()], pipeline=pipeline, top_k=8)

    pipeline.answer.assert_awaited_once_with(query="Q?", top_k=8)


async def test_records_latency_above_zero() -> None:
    """Smoke check that we actually time the call (uses perf_counter, so the
    delta is wall-clock time even though the mock is instant)."""
    pipeline = MagicMock()
    pipeline.answer = AsyncMock(return_value=_ok_rag_result())

    results = await run_eval([_case()], pipeline=pipeline)

    assert results[0].latency_seconds >= 0.0


async def test_build_report_aggregates_metrics() -> None:
    pipeline = MagicMock()
    pipeline.answer = AsyncMock(return_value=_ok_rag_result())
    results = await run_eval([_case("a"), _case("b")], pipeline=pipeline)

    report = build_report(
        eval_set_version="v1",
        sprint_label="test",
        timestamp_utc="2026-05-02T18:00:00Z",
        results=results,
    )
    assert report.metrics.n_cases == 2
    assert report.metrics.citation_validity_rate == 1.0
    assert report.metrics.avg_citations_per_answer == 1.0
