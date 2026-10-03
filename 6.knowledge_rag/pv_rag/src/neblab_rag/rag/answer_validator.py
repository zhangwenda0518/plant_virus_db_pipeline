"""LLM-powered answer validation — checks if cited claims actually appear in the fragments.

Extends the existing ``validate_citations()`` (syntax check on [N] range) with
semantic verification: for each [N] claim, ask a second LLM whether fragment N
really contains the claimed fact.  Produces a fidelity score so the API/UI can
flag low-confidence answers.

Failure semantics (2026-10-03 audit, P1 "幻觉校验失效开放"): when the check
cannot run — no ``[N]`` citations to verify, the validator LLM call errors, or
its JSON output cannot be parsed — the result is ``fidelity_score=None`` with
``is_reliable=False`` and a ``note`` explaining why.  It must NEVER be reported
as a passing (1.0 / reliable) answer: an unverifiable answer is not a verified
one.  Callers (e.g. ``api/routes/query.py``) surface ``None`` as
"validation unavailable".
"""

from pydantic import BaseModel

from neblab_rag.logging_config import get_logger
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider
from neblab_rag.rag.retriever import RetrievedChunk

log = get_logger(__name__)

VALIDATOR_SYSTEM_PROMPT = """You are a citation fidelity checker for a plant virus knowledge base.
Your task: verify whether each CLAIM in an answer is actually supported by its cited FRAGMENT.

For each claim, respond with a JSON object:
{
  "claim_number": <int>,
  "citation_number": <int>,
  "verdict": "supported" | "partial" | "unsupported",
  "explanation": "<one sentence>"
}

Rules:
- "supported": the fragment contains the exact fact, number, or finding stated in the claim
- "partial": the fragment discusses the topic but the specific detail is missing or different
- "unsupported": the fragment does not discuss this at all, or contradicts it
- Be strict about numbers and percentages — they must match exactly
- Be lenient about paraphrasing of qualitative descriptions
- Output ONLY a valid JSON array, nothing else."""


class ClaimValidation(BaseModel):
    claim_number: int
    citation_number: int
    verdict: str  # "supported" | "partial" | "unsupported"
    explanation: str


class AnswerValidation(BaseModel):
    claims: list[ClaimValidation]
    # 0.0–1.0 proportion of supported claims; None == "validation unavailable"
    # (never a pass — see module docstring).
    fidelity_score: float | None
    is_reliable: bool  # True only if fidelity_score is not None and >= 0.7
    note: str | None = None  # why validation is unavailable, when it is


def _unavailable(reason: str) -> AnswerValidation:
    """Validation could not be performed — report it as unavailable, not as a pass."""
    return AnswerValidation(
        claims=[], fidelity_score=None, is_reliable=False, note=reason
    )


async def validate_answer_content(
    answer: str,
    chunks: list[RetrievedChunk],
    llm: LLMProvider,
    *,
    fidelity_threshold: float = 0.7,
) -> AnswerValidation:
    """Extract cited claims from the answer and verify each against its fragment.

    Only runs when there are citations in the answer and chunks are available.
    When the check cannot run or fails (LLM error, unparseable JSON, no
    verdicts), returns ``fidelity_score=None`` + ``is_reliable=False`` + a
    ``note`` — never a fabricated 1.0 (2026-10-03 audit).
    """
    import json as _json
    import re as _re

    # Extract claims with their citation numbers
    # Pattern: text... [N] or [N,M] at the end of sentences/claims
    claims_raw = _re.findall(r"([^.!?\n]+?)\s*\[(\d+(?:,\d+)*)\]", answer)
    if not claims_raw:
        # 答案里没有 [N] 引用 → 无从校验。旧行为返回 1.0/"可靠"，等于把
        # "没做校验"标成"通过"；现在如实标注不可用。
        return _unavailable("answer contains no [N] citations")

    # Build fragment context for the validator
    fragment_texts = []
    for i, c in enumerate(chunks, 1):
        fragment_texts.append(f"[{i}] {c.title}\n{c.text[:800]}")

    claims_list = []
    for claim_text, cite_nums in claims_raw:
        for num in cite_nums.split(","):
            num = num.strip()
            if num.isdigit():
                claims_list.append({
                    "claim": claim_text.strip(),
                    "citation": int(num),
                })

    if not claims_list:
        return _unavailable("no numeric citation markers found")

    # Ask LLM to verify
    user_content = (
        "FRAGMENTS:\n" + "\n\n".join(fragment_texts) + "\n\n"
        "CLAIMS TO VERIFY:\n" +
        "\n".join(
            f"Claim {i+1}: \"{c['claim']}\" [citation {c['citation']}]"
            for i, c in enumerate(claims_list)
        )
    )

    try:
        resp = await llm.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=VALIDATOR_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=user_content),
                ],
                temperature=0.0,
                max_tokens=512,
            )
        )
        # Parse JSON array from response
        text = resp.content.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            text = _re.sub(r"^```(?:json)?\s*", "", text)
            text = _re.sub(r"```\s*$", "", text)
        results = _json.loads(text)
    except Exception as exc:
        log.warning("answer_validation_failed", error=str(exc))
        # 旧行为是"报错即 fidelity=1.0"（失效开放，审计 P1）。校验失败必须
        # 如实标注不可用，绝不冒充通过。
        return _unavailable(f"validator error: {type(exc).__name__}")

    validated = [
        ClaimValidation(
            claim_number=i + 1,
            citation_number=claims_list[i]["citation"],
            verdict=r.get("verdict", "unsupported"),
            explanation=r.get("explanation", ""),
        )
        for i, r in enumerate(results)
        if i < len(claims_list)
    ]

    if not validated:
        return _unavailable("validator returned no verdicts")

    supported = sum(1 for v in validated if v.verdict == "supported")
    score = supported / len(validated)

    return AnswerValidation(
        claims=validated,
        fidelity_score=score,
        is_reliable=score >= fidelity_threshold,
    )
