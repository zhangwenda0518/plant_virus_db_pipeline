"""Generate draft eval questions from the live corpus.

Pulls chunk titles + abstracts from Postgres, asks the LLM to generate
diverse research questions covering the corpus, then writes a draft JSON
that follows the EvalCase schema. The output is INTENDED FOR HUMAN REVIEW
before being merged into ``evals/v1/questions.json`` — the LLM is good
at coverage and phrasing but human curation catches duplicates, ambiguous
wording, and ensures honest difficulty/coverage labels.

Usage:
    PATH="$HOME/miniforge3/envs/NEBLab/bin:$PATH" python scripts/generate_eval_questions.py \
        --target 30 --out evals/v1/draft-questions.json
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from neblab_rag.db.engine import get_session
from neblab_rag.db.models import Document
from neblab_rag.providers.factory import build_llm_provider
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest


GENERATOR_SYSTEM_PROMPT = """You are an evaluation engineer building a question set to test a RAG system over a literature corpus on desertification and land degradation.

Given the list of paper titles below, generate diverse research questions that:
- Cover different subtopics (causes, mechanisms, monitoring, restoration, policy, regional case studies, etc.)
- Vary in difficulty (easy = single concept; medium = multi-source synthesis; hard = boundary case or out-of-coverage)
- Mix English and Chinese phrasings
- Include some questions where the corpus likely CANNOT answer (out-of-coverage), to test the system's honesty

For each question return a JSON object with EXACTLY these fields:
  id: stable kebab-case identifier, lowercase, e.g. "easy.en.feedback-loop"
       use prefix "easy."/"medium."/"hard." then ".en."/".zh." then a topic slug
  text: the question itself
  language: "en" or "zh"
  difficulty: "easy" | "medium" | "hard"
  source: always "ai_generated"
  corpus_coverage_expected: "yes" | "partial" | "no"
       yes = corpus very likely contains a direct answer
       partial = corpus has adjacent material but no clean fit
       no = corpus is unlikely to address this; tests honest refusal
  notes: one sentence explaining your difficulty + coverage rationale

Output a JSON ARRAY only — no surrounding text, no markdown fences."""


async def generate_questions(target: int, sample_titles: list[str]) -> list[dict[str, object]]:
    llm = build_llm_provider()
    titles_block = "\n".join(f"- {t}" for t in sample_titles)
    user_message = f"""Generate {target} diverse questions for this corpus.

Paper titles:
{titles_block}

Aim for: ~30% easy / 50% medium / 20% hard, ~70% English / 30% Chinese,
~70% coverage=yes / 15% partial / 15% no. Return a JSON array."""

    resp = await llm.chat(
        ChatRequest(
            messages=[
                ChatMessage(role="system", content=GENERATOR_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_message),
            ],
            temperature=0.7,  # diversity matters more than determinism here
            max_tokens=8000,
        )
    )

    cleaned = resp.content.strip()
    # LLMs sometimes still wrap in ```json ... ```
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        questions = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"FAILED to parse LLM output as JSON: {e}", file=sys.stderr)
        print(f"Raw output:\n{resp.content[:500]}...", file=sys.stderr)
        return []

    if not isinstance(questions, list):
        print("LLM returned non-list", file=sys.stderr)
        return []

    return questions


def fetch_titles() -> list[str]:
    with get_session() as s:
        rows = s.query(Document.title).all()
    return [r[0] for r in rows]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=25, help="how many questions to draft")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="LLM call size; loops until target met. Smaller = safer vs read timeout on big targets.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evals/v1/draft-questions.json"),
        help="Output draft JSON path",
    )
    args = parser.parse_args()

    titles = fetch_titles()
    print(f"Pulled {len(titles)} titles from Postgres; asking LLM for {args.target} questions ...")

    questions: list[dict[str, object]] = []
    while len(questions) < args.target:
        remaining = args.target - len(questions)
        batch_n = min(args.batch_size, remaining)
        print(f"  batch: requesting {batch_n} (have {len(questions)}/{args.target})")
        batch = await generate_questions(batch_n, titles)
        if not batch:
            print("Batch returned empty — stopping.", file=sys.stderr)
            break
        questions.extend(batch)

    if not questions:
        print("No questions generated.", file=sys.stderr)
        return 1

    print(f"LLM returned {len(questions)} questions total.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

    by_difficulty: dict[str, int] = {}
    by_lang: dict[str, int] = {}
    by_coverage: dict[str, int] = {}
    for q in questions:
        by_difficulty[q.get("difficulty", "?")] = by_difficulty.get(q.get("difficulty", "?"), 0) + 1
        by_lang[q.get("language", "?")] = by_lang.get(q.get("language", "?"), 0) + 1
        by_coverage[q.get("corpus_coverage_expected", "?")] = (
            by_coverage.get(q.get("corpus_coverage_expected", "?"), 0) + 1
        )

    print(f"\nDistribution:")
    print(f"  difficulty: {by_difficulty}")
    print(f"  language:   {by_lang}")
    print(f"  coverage:   {by_coverage}")
    print(f"\nDraft written → {args.out}")
    print("Next: review/curate, then merge selected questions into evals/v1/questions.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
