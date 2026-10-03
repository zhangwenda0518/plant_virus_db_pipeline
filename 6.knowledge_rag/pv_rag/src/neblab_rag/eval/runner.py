"""Async eval runner: loop questions through a RAGPipeline, collect metrics.

The runner doesn't decide WHICH pipeline — caller injects one. In CLI use,
we build the production pipeline (real DeepSeek/Qwen3/Qdrant); in tests,
we inject a MagicMock. Same code path either way.

Sequential by design: real-API runs already saturate provider rate limits,
and we want each question's latency measured without contention. Parallel
runs would speed wall clock but distort latency_p95 — wrong tradeoff for
an eval harness whose job is to produce trustworthy numbers.

Optional ``judge`` (Sprint 4 v0.2) runs LLM-as-judge on each answer's
citations after retrieval+generation. Adds ~5-15 LLM calls per case.
"""

import time
from collections.abc import Sequence

from pydantic import BaseModel

from neblab_rag.eval.data import EvalCase
from neblab_rag.eval.judge import CitationJudge
from neblab_rag.eval.metrics import AggregateMetrics, CaseResult, aggregate
from neblab_rag.logging_config import get_logger
from neblab_rag.rag.pipeline import RAGPipeline

log = get_logger(__name__)


class EvalReport(BaseModel):
    eval_set_version: str
    sprint_label: str  # e.g. "sprint-2-baseline" — written into the report filename
    timestamp_utc: str  # ISO 8601
    cases: list[CaseResult]
    metrics: AggregateMetrics


async def run_eval(
    cases: Sequence[EvalCase],
    pipeline: RAGPipeline,
    *,
    top_k: int = 12,
    judge: CitationJudge | None = None,
) -> list[CaseResult]:
    """Run each case through the pipeline. Failures are caught per-case so
    one broken question doesn't abort the whole eval."""
    results: list[CaseResult] = []
    for case in cases:
        log.info("eval_case_start", case_id=case.id)
        t0 = time.perf_counter()
        try:
            rag_result = await pipeline.answer(query=case.text, top_k=top_k)
            elapsed = time.perf_counter() - t0
            judgments_raw: list[dict[str, object]] = []
            if judge is not None:
                judgments = await judge.judge_answer(
                    case_id=case.id,
                    answer=rag_result.answer.content,
                    chunks=rag_result.chunks,
                )
                judgments_raw = [j.model_dump() for j in judgments]
            results.append(
                CaseResult(
                    case_id=case.id,
                    question=case.text,
                    answer=rag_result.answer.content,
                    citation_valid=rag_result.citation_validation.is_valid,
                    citations_count=len(rag_result.answer.citations),
                    chunks_retrieved=len(rag_result.chunks),
                    latency_seconds=elapsed,
                    expected_coverage=case.corpus_coverage_expected,
                    judgments=judgments_raw,
                )
            )
            log.info(
                "eval_case_done",
                case_id=case.id,
                latency=round(elapsed, 2),
                citation_valid=rag_result.citation_validation.is_valid,
                n_judgments=len(judgments_raw),
            )
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            results.append(
                CaseResult(
                    case_id=case.id,
                    question=case.text,
                    answer="",
                    citation_valid=False,
                    citations_count=0,
                    chunks_retrieved=0,
                    latency_seconds=elapsed,
                    expected_coverage=case.corpus_coverage_expected,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            log.warning("eval_case_error", case_id=case.id, error=str(exc))
    return results


def build_report(
    *,
    eval_set_version: str,
    sprint_label: str,
    timestamp_utc: str,
    results: list[CaseResult],
) -> EvalReport:
    return EvalReport(
        eval_set_version=eval_set_version,
        sprint_label=sprint_label,
        timestamp_utc=timestamp_utc,
        cases=results,
        metrics=aggregate(results),
    )
