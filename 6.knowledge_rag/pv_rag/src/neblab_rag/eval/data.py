"""Eval data model: EvalCase + question-set loader.

A question set is a JSON file with this top-level shape::

    {
      "version": "v1",
      "description": "...",
      "cases": [{...EvalCase...}, ...]
    }

corpus_coverage_expected lets us distinguish two failure modes:
  - "literature insufficient" reply when expected="yes" → real miss (bug)
  - "literature insufficient" reply when expected="no" → correct caution

This decoupling matters because Sprint-2 corpus is small (50 desertification
docs); many questions WILL be out-of-coverage and we don't want them
counted as quality regressions.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Language = Literal["en", "zh"]
Difficulty = Literal["easy", "medium", "hard"]
Source = Literal["handwritten", "ai_generated", "reviewed"]
CorpusCoverage = Literal["yes", "partial", "no"]


class EvalCase(BaseModel):
    id: str
    text: str
    language: Language
    difficulty: Difficulty
    source: Source
    corpus_coverage_expected: CorpusCoverage
    notes: str = ""


class EvalSet(BaseModel):
    version: str
    description: str
    cases: list[EvalCase]


def load_eval_set(path: Path) -> EvalSet:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return EvalSet.model_validate(raw)
