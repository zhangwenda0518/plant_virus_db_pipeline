"""Tests for eval data model + loader."""

import json
from pathlib import Path

import pydantic
import pytest

from neblab_rag.eval.data import EvalCase, EvalSet, load_eval_set


def test_eval_case_validates_required_fields() -> None:
    case = EvalCase(
        id="t1",
        text="What is X?",
        language="en",
        difficulty="easy",
        source="handwritten",
        corpus_coverage_expected="yes",
    )
    assert case.id == "t1"
    assert case.notes == ""  # default


def test_eval_case_rejects_invalid_enum() -> None:
    with pytest.raises(pydantic.ValidationError):
        EvalCase(
            id="t1",
            text="?",
            language="fr",  # pyright: ignore[reportArgumentType]  invalid: only en/zh
            difficulty="easy",
            source="handwritten",
            corpus_coverage_expected="yes",
        )


def test_load_eval_set_round_trip(tmp_path: Path) -> None:
    payload = {
        "version": "v1-test",
        "description": "tiny",
        "cases": [
            {
                "id": "c1",
                "text": "Q?",
                "language": "en",
                "difficulty": "easy",
                "source": "handwritten",
                "corpus_coverage_expected": "yes",
            }
        ],
    }
    p = tmp_path / "questions.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_eval_set(p)
    assert isinstance(loaded, EvalSet)
    assert loaded.version == "v1-test"
    assert len(loaded.cases) == 1
    assert loaded.cases[0].id == "c1"


def test_v1_seed_set_loads_and_has_balanced_difficulty() -> None:
    """The shipped seed set must always parse and stay roughly balanced."""
    repo_root = Path(__file__).resolve().parents[3]
    seed = load_eval_set(repo_root / "evals" / "v1" / "questions.json")
    assert seed.version.startswith("v")
    assert len(seed.cases) >= 10  # baseline floor

    # Ids must be unique (else CLI reports get confusing)
    ids = [c.id for c in seed.cases]
    assert len(ids) == len(set(ids))

    # Roughly balanced difficulty (no single tier dominates)
    by_difficulty = dict.fromkeys(("easy", "medium", "hard"), 0)
    for c in seed.cases:
        by_difficulty[c.difficulty] += 1
    for tier, n in by_difficulty.items():
        assert n >= 2, f"only {n} {tier} cases in seed — too few to be meaningful"
