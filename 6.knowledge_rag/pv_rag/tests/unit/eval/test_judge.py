"""Tests for the LLM-as-judge citation faithfulness metric."""

from unittest.mock import AsyncMock, MagicMock

from neblab_rag.eval.judge import CitationJudge, _parse_verdict, _split_claims
from neblab_rag.providers.llm.base import ChatResponse
from neblab_rag.rag.retriever import RetrievedChunk


def _chunk(n: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=n, doc_id=n, chunk_index=0, openalex_id=f"W{n}", title="t", text=text, score=0.9
    )


def test_split_claims_extracts_sentences_with_citations() -> None:
    answer = "Per [1], X is true. Y is unrelated. Per [2] and [3], Z holds."
    claims = _split_claims(answer)
    assert claims == [
        ("Per [1], X is true.", [1]),
        ("Per [2] and [3], Z holds.", [2, 3]),
    ]


def test_split_claims_handles_chinese_punctuation() -> None:
    answer = "根据 [1]，机制 A 成立。这句无引用。再看 [2]，机制 B 也成立。"
    claims = _split_claims(answer)
    assert len(claims) == 2
    assert claims[0][1] == [1]
    assert claims[1][1] == [2]


def test_split_claims_skips_sentences_without_citations() -> None:
    assert _split_claims("This has no brackets at all.") == []


def test_parse_verdict_accepts_clean_json() -> None:
    v, r = _parse_verdict('{"verdict": "supported", "rationale": "chunk states it directly"}')
    assert v == "supported"
    assert r == "chunk states it directly"


def test_parse_verdict_strips_markdown_fences() -> None:
    raw = '```json\n{"verdict": "partial", "rationale": "on topic"}\n```'
    v, r = _parse_verdict(raw)
    assert v == "partial"
    assert r == "on topic"


def test_parse_verdict_rejects_unknown_verdict() -> None:
    v, _ = _parse_verdict('{"verdict": "maybe", "rationale": "x"}')
    assert v == "judge_error"


def test_parse_verdict_rejects_non_json() -> None:
    v, _ = _parse_verdict("yes I think so")
    assert v == "judge_error"


async def test_judge_calls_llm_per_citation() -> None:
    chunks = [
        _chunk(1, "Shrubs invade grasslands and erode soil"),
        _chunk(2, "Climate change affects rainfall"),
    ]
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=ChatResponse(
            content='{"verdict": "supported", "rationale": "ok"}',
            model="m",
            finish_reason="stop",
        )
    )

    judge = CitationJudge(llm=llm)
    results = await judge.judge_answer(
        case_id="c1",
        answer="Shrub invasion erodes soil [1]. Climate matters [2].",
        chunks=chunks,
    )

    assert len(results) == 2
    assert results[0].chunk_number == 1
    assert results[0].verdict == "supported"
    assert results[1].chunk_number == 2
    assert llm.chat.await_count == 2


async def test_judge_marks_out_of_range_citation_as_error() -> None:
    """If the answer cites [5] but only 3 chunks were retrieved, that's a
    structural-validation issue we still want to record (not crash on)."""
    llm = MagicMock()
    llm.chat = AsyncMock()  # must NOT be called for out-of-range

    judge = CitationJudge(llm=llm)
    results = await judge.judge_answer(
        case_id="c1",
        answer="Per [5] hallucinated.",
        chunks=[_chunk(1, "x")],
    )

    assert len(results) == 1
    assert results[0].verdict == "judge_error"
    assert "out of range" in results[0].rationale
    llm.chat.assert_not_called()


async def test_judge_returns_empty_when_no_chunks() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock()
    judge = CitationJudge(llm=llm)

    results = await judge.judge_answer(case_id="c1", answer="anything", chunks=[])

    assert results == []
    llm.chat.assert_not_called()


async def test_judge_handles_llm_failure_gracefully() -> None:
    chunks = [_chunk(1, "x")]
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("provider down"))
    judge = CitationJudge(llm=llm)

    results = await judge.judge_answer(case_id="c1", answer="Per [1] something.", chunks=chunks)

    assert len(results) == 1
    assert results[0].verdict == "judge_error"
    assert "llm error" in results[0].rationale.lower()
