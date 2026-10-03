"""Tests for the semantic answer validator (LLM-judged citation fidelity).

2026-10-03 audit P1: the validator previously fell back to
``fidelity_score=1.0 / is_reliable=True`` whenever it could not parse an
answer or the validator LLM call failed ("fail-open").  These tests pin the
new fail-closed contract: unverifiable → ``fidelity_score=None`` +
``is_reliable=False`` + a ``note``.
"""

import json

from neblab_rag.rag.answer_validator import validate_answer_content
from neblab_rag.rag.retriever import RetrievedChunk


class _FakeLLM:
    """Minimal LLMProvider stub: returns a canned string or raises."""

    def __init__(self, *, content: str = "", exc: Exception | None = None) -> None:
        self._content = content
        self._exc = exc

    async def chat(self, request):  # noqa: ANN001 - test stub
        if self._exc is not None:
            raise self._exc

        class _Resp:
            content = self._content

        return _Resp()


def _chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=1, doc_id=1, chunk_index=0, openalex_id=None, title="t", text="x", score=1.0
        )
    ]


def _verdicts(*verdicts: str) -> str:
    return json.dumps(
        [
            {
                "claim_number": i + 1,
                "citation_number": 1,
                "verdict": v,
                "explanation": "e",
            }
            for i, v in enumerate(verdicts)
        ]
    )


async def test_no_citations_marks_validation_unavailable() -> None:
    result = await validate_answer_content("Answer with no markers.", _chunks(), _FakeLLM())
    assert result.fidelity_score is None
    assert result.is_reliable is False
    assert result.note and "no [N] citations" in result.note


async def test_llm_error_marks_validation_unavailable() -> None:
    llm = _FakeLLM(exc=RuntimeError("boom"))
    result = await validate_answer_content("Claim [1].", _chunks(), llm)
    assert result.fidelity_score is None
    assert result.is_reliable is False
    assert result.note and "validator error" in result.note


async def test_unparseable_json_marks_validation_unavailable() -> None:
    result = await validate_answer_content("Claim [1].", _chunks(), _FakeLLM(content="not json"))
    assert result.fidelity_score is None
    assert result.is_reliable is False


async def test_supported_claims_score_high() -> None:
    result = await validate_answer_content(
        "Claim [1].", _chunks(), _FakeLLM(content=_verdicts("supported", "supported"))
    )
    assert result.fidelity_score == 1.0
    assert result.is_reliable is True
    assert result.note is None


async def test_unsupported_claims_score_zero() -> None:
    result = await validate_answer_content(
        "Claim [1].", _chunks(), _FakeLLM(content=_verdicts("unsupported", "partial"))
    )
    assert result.fidelity_score == 0.0
    assert result.is_reliable is False


async def test_fenced_json_is_parsed() -> None:
    fenced = "```json\n" + _verdicts("supported") + "\n```"
    result = await validate_answer_content("Claim [1].", _chunks(), _FakeLLM(content=fenced))
    assert result.fidelity_score == 1.0
    assert result.is_reliable is True
