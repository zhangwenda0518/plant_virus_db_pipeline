"""LLM-as-judge for citation faithfulness.

Sprint 4 v0.2 deep metric. The structural ``citation_validity_rate`` checks
that every [N] in an answer maps to a real retrieved chunk, but says nothing
about whether the chunk actually supports the claim. This module closes
that gap: parse claims out of the answer, look up the cited chunks, ask
the LLM "does this chunk support this claim?".

Aggregation report (3 numbers, not 1):
  - supported_rate    — chunk clearly supports the claim
  - partial_rate      — chunk is on-topic but doesn't fully back the claim
  - not_supported_rate — chunk doesn't support the claim (would be a citation error)

We don't collapse partial into not-supported because the distinction is
useful diagnostically — it tells us whether to retrain retrieval (partial
→ better recall) vs the generator (not-supported → stricter prompt).
"""

import json
import re
from typing import Literal

from pydantic import BaseModel

from neblab_rag.logging_config import get_logger
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider
from neblab_rag.rag.retriever import RetrievedChunk

log = get_logger(__name__)


Verdict = Literal["supported", "partial", "not_supported", "judge_error"]


class JudgmentResult(BaseModel):
    case_id: str
    claim: str
    chunk_number: int  # 1-indexed [N] from the answer
    chunk_text_excerpt: str  # first ~200 chars for the report
    verdict: Verdict
    rationale: str


JUDGE_SYSTEM_PROMPT = """You evaluate whether a cited literature chunk actually supports a claim.

Given:
  - CLAIM: a sentence from a generated answer
  - CHUNK: the literature passage that was cited for this claim

Decide one of:
  - supported: the chunk clearly states or directly implies the claim
  - partial:   the chunk is on-topic and adjacent, but doesn't fully back the specific claim
  - not_supported: the chunk does not support the claim at all

Respond with ONLY a JSON object, no markdown fences, no commentary:
{"verdict": "supported" | "partial" | "not_supported", "rationale": "one sentence why"}
"""

# A "claim sentence" is a sentence that ends with a period (incl. CJK)
# AND contains at least one [N] citation marker. We split AFTER any
# sentence-ender — whitespace optional because CJK text typically has no
# space between sentences (你好。世界。 doesn't split with \s+).
_SENTENCE_SPLIT = re.compile(r"(?<=[.。!！?？])\s*")
_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def _split_claims(answer: str) -> list[tuple[str, list[int]]]:
    """Return [(sentence, [cited numbers]), ...] for sentences with citations."""
    out: list[tuple[str, list[int]]] = []
    for sentence in _SENTENCE_SPLIT.split(answer.strip()):
        s = sentence.strip()
        nums = [int(m) for m in _CITATION_PATTERN.findall(s)]
        if s and nums:
            out.append((s, nums))
    return out


class CitationJudge:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def judge_answer(
        self, *, case_id: str, answer: str, chunks: list[RetrievedChunk]
    ) -> list[JudgmentResult]:
        if not chunks:
            return []

        results: list[JudgmentResult] = []
        for claim, cited_numbers in _split_claims(answer):
            for n in cited_numbers:
                # [N] is 1-indexed against the chunks list at generation time
                if n < 1 or n > len(chunks):
                    # Structural validation already flags this; record as error
                    results.append(
                        JudgmentResult(
                            case_id=case_id,
                            claim=claim,
                            chunk_number=n,
                            chunk_text_excerpt="",
                            verdict="judge_error",
                            rationale=f"[{n}] is out of range for {len(chunks)} chunks",
                        )
                    )
                    continue
                chunk = chunks[n - 1]
                verdict, rationale = await self._judge_one(claim, chunk.text)
                results.append(
                    JudgmentResult(
                        case_id=case_id,
                        claim=claim,
                        chunk_number=n,
                        chunk_text_excerpt=chunk.text[:200],
                        verdict=verdict,
                        rationale=rationale,
                    )
                )
        return results

    async def _judge_one(self, claim: str, chunk_text: str) -> tuple[Verdict, str]:
        try:
            resp = await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(role="system", content=JUDGE_SYSTEM_PROMPT),
                        ChatMessage(
                            role="user",
                            content=f"CLAIM:\n{claim}\n\nCHUNK:\n{chunk_text}",
                        ),
                    ],
                    temperature=0.0,
                    max_tokens=200,
                )
            )
        except Exception as exc:
            log.warning("judge_llm_error", error=str(exc))
            return "judge_error", f"llm error: {exc}"

        return _parse_verdict(resp.content)


def _parse_verdict(content: str) -> tuple[Verdict, str]:
    """LLMs sometimes wrap JSON in markdown fences — be lenient."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # strip fences like ```json\n{...}\n```
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return "judge_error", f"non-JSON response: {content[:120]}"

    verdict = data.get("verdict")
    rationale = data.get("rationale", "")
    if verdict not in ("supported", "partial", "not_supported"):
        return "judge_error", f"unknown verdict: {verdict!r}"
    return verdict, str(rationale)
