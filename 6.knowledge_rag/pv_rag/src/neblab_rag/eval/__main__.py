"""CLI: ``python -m neblab_rag.eval --questions evals/v1/questions.json``.

Runs each question through the production pipeline (real DeepSeek + Qwen3
+ Qdrant), prints a summary table, and writes the full report to a JSON
file under ``evals/runs/`` so we can diff metrics across sprints.

Note: this hits paid APIs. Treat as a developer command, not CI default.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from neblab_rag.eval.data import load_eval_set
from neblab_rag.eval.judge import CitationJudge
from neblab_rag.eval.runner import EvalReport, build_report, run_eval
from neblab_rag.providers.factory import (
    build_bm25_index,
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)
from neblab_rag.rag.generator import AnswerGenerator
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.query_rewriter import QueryRewriter
from neblab_rag.rag.retriever import HierarchicalRetriever, HybridRetriever


def _build_pipeline(
    *,
    with_rewriter: bool,
    with_bm25: bool,
    with_hierarchical: bool,
    hier_top_docs: int,
    hier_chunks_per_doc: int,
) -> RAGPipeline:
    llm = build_llm_provider()
    bm25 = build_bm25_index() if with_bm25 else None
    embedder = build_embedding_provider()
    qdrant = build_qdrant_repo()
    reranker = build_reranker_provider()
    retriever: HybridRetriever | HierarchicalRetriever
    if with_hierarchical:
        retriever = HierarchicalRetriever(
            embedder=embedder,
            qdrant=qdrant,
            reranker=reranker,
            bm25=bm25,
            top_docs=hier_top_docs,
            chunks_per_doc=hier_chunks_per_doc,
        )
    else:
        retriever = HybridRetriever(embedder=embedder, qdrant=qdrant, reranker=reranker, bm25=bm25)
    return RAGPipeline(
        retriever=retriever,
        generator=AnswerGenerator(llm=llm),
        query_rewriter=QueryRewriter(llm=llm) if with_rewriter else None,
    )


def _print_summary(report_path: Path, report: EvalReport) -> None:
    m = report.metrics
    print(f"\n=== Eval summary ({report.sprint_label}) ===")
    print(f"  cases:                    {m.n_cases}")
    print(f"  errors:                   {m.n_errors}")
    print(f"  citation_validity_rate:   {m.citation_validity_rate:.1%}")
    print(f"  answered_rate:            {m.answered_rate:.1%}")
    print(f"  expected_yes_answered:    {m.expected_yes_answered_rate:.1%}")
    print(f"  expected_no_refused:      {m.expected_no_refused_rate:.1%}")
    print(f"  avg_citations_per_answer: {m.avg_citations_per_answer:.2f}")
    print(f"  avg_chunks_retrieved:     {m.avg_chunks_retrieved:.2f}")
    print(f"  latency_p50:              {m.latency_p50:.2f}s")
    print(f"  latency_p95:              {m.latency_p95:.2f}s")
    if m.n_judgments:
        print(f"\n  --- judge ({m.n_judgments} citations judged) ---")
        print(f"  citation_supported_rate:  {m.citation_supported_rate:.1%}")
        print(f"  citation_partial_rate:    {m.citation_partial_rate:.1%}")
        print(f"  citation_not_supported:   {m.citation_not_supported_rate:.1%}")
    print(f"\nFull report → {report_path}\n")


async def _run(args: argparse.Namespace) -> int:
    eval_set = load_eval_set(Path(args.questions))
    pipeline = _build_pipeline(
        with_rewriter=not args.no_rewriter,
        with_bm25=not args.no_bm25,
        with_hierarchical=args.hierarchical,
        hier_top_docs=args.hier_top_docs,
        hier_chunks_per_doc=args.hier_chunks_per_doc,
    )
    judge = CitationJudge(llm=build_llm_provider()) if args.judge else None

    print(
        f"Running {len(eval_set.cases)} cases from {eval_set.version} "
        f"(judge={'on' if judge else 'off'}, "
        f"rewriter={'off' if args.no_rewriter else 'on'}, "
        f"bm25={'off' if args.no_bm25 else 'on'}, "
        f"retriever={'hierarchical' if args.hierarchical else 'flat'}) ..."
    )
    results = await run_eval(eval_set.cases, pipeline=pipeline, top_k=args.top_k, judge=judge)

    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    report = build_report(
        eval_set_version=eval_set.version,
        sprint_label=args.label,
        timestamp_utc=timestamp,
        results=results,
    )

    out_path = Path(args.out_dir) / f"{args.label}-{timestamp.replace(':', '')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    _print_summary(out_path, report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neblab_rag.eval", description=__doc__)
    parser.add_argument(
        "--questions",
        default="evals/v1/questions.json",
        help="Path to question set JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Sprint label for the report filename, e.g. 'sprint-2-baseline'",
    )
    parser.add_argument("--out-dir", default="evals/runs", help="Where to write the JSON report")
    parser.add_argument("--top-k", type=int, default=7)
    parser.add_argument(
        "--no-rewriter",
        action="store_true",
        help="Disable query rewriter (zh→en) — for A/B comparison against rewriter-on baselines",
    )
    parser.add_argument(
        "--no-bm25",
        action="store_true",
        help="Disable BM25 sparse retrieval — for A/B comparison against hybrid baselines",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Enable LLM-as-judge for citation faithfulness (~5-15 extra LLM calls per case)",
    )
    parser.add_argument(
        "--hierarchical",
        action="store_true",
        help="Use HierarchicalRetriever (doc-then-chunk) instead of flat HybridRetriever",
    )
    parser.add_argument(
        "--hier-top-docs",
        type=int,
        default=5,
        help="When --hierarchical: number of docs to keep at stage 1 (default 5)",
    )
    parser.add_argument(
        "--hier-chunks-per-doc",
        type=int,
        default=3,
        help="When --hierarchical: chunks per kept doc at stage 2 (default 3)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
