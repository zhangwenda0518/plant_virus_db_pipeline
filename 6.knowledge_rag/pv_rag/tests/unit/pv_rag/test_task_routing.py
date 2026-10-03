"""Unit tests: task_classifier, system_info, PvAnswerGenerator, PvRouter.

Pure Python — no Postgres, Qdrant, or API calls needed.
"""

from unittest.mock import MagicMock

import pytest

from neblab_rag.providers.llm.base import ChatMessage
from neblab_rag.rag.retriever import RetrievedChunk
from plant_virus_rag.rag.generator import (
    PvAnswerGenerator,
    PV_PLANNING_SYSTEM_PROMPT,
    PV_PLANNING_SYSTEM_PROMPT_ZH,
    PV_QA_SYSTEM_PROMPT,
    PV_QA_SYSTEM_PROMPT_ZH,
)
from plant_virus_rag.rag.system_info import (
    PvSystemInfo,
    format_meta_answer,
    is_identity_query,
)
from plant_virus_rag.rag.task_classifier import TaskType, classify

# ── task_classifier ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query,expected",
    [
        ("What is tobacco mosaic virus?", TaskType.QA),
        ("什么是番茄黄化曲叶病毒？", TaskType.QA),
        ("why does CMV infect cucurbits?", TaskType.QA),
        ("how does a virus move through plasmodesmata?", TaskType.QA),
        ("What are symptoms of TSWV?", TaskType.QA),
    ],
)
def test_classify_qa(query: str, expected: TaskType) -> None:
    assert classify(query) == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("设计一个番茄黄化曲叶病毒的防治方案", TaskType.PLANNING),
        ("how to control citrus tristeza virus?", TaskType.PLANNING),
        ("建议水稻条纹病毒的监测策略", TaskType.PLANNING),
        ("制定植物病毒检疫措施", TaskType.PLANNING),
        ("design a disease management plan for maize lethal necrosis", TaskType.PLANNING),
    ],
)
def test_classify_planning(query: str, expected: TaskType) -> None:
    assert classify(query) == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("数据库有多少病毒记录", TaskType.META),
        ("收录了多少种植物病毒", TaskType.META),
        ("how many viruses are in the database?", TaskType.META),
        ("你是什么系统", TaskType.META),
        ("你是谁", TaskType.META),
        ("who are you", TaskType.META),
    ],
)
def test_classify_meta(query: str, expected: TaskType) -> None:
    assert classify(query) == expected


def test_classify_empty_returns_qa() -> None:
    assert classify("") == TaskType.QA


def test_classify_qa_override_wins_over_planning() -> None:
    """什么是 + 方案 → QA override wins."""
    assert classify("什么是番茄黄化曲叶病毒的防治方案") == TaskType.QA


# ── system_info ────────────────────────────────────────────────────────


def test_is_identity_query_matches() -> None:
    assert is_identity_query("你是谁") is True
    assert is_identity_query("你是什么模型") is True
    assert is_identity_query("who are you") is True
    assert is_identity_query("what model are you") is True


def test_is_identity_query_no_match() -> None:
    assert is_identity_query("数据库有多少病毒") is False
    assert is_identity_query("What is TMV?") is False


def test_format_meta_answer_contains_counts() -> None:
    info = PvSystemInfo(
        total_records=100,
        total_documents=5000,
        total_chunks=200,
        records_by_source=(("ictv", 50), ("ncbi_host", 50)),
        documents_by_language=(("en", 4000), ("zh", 1000)),
    )
    text = format_meta_answer(info)
    assert "100" in text
    assert "5000" in text
    assert "200" in text
    assert "ictv" in text
    # 2026-10-03 audit: sprint / citation_supported_rate / answered_rate were
    # unsourced self-reported numbers — the meta answer must not print them.
    assert "sprint-0" not in text
    assert "%" not in text.split("### Retrieval & Generation Config")[1]


def test_meta_answer_omits_unsourced_self_reported_metrics() -> None:
    """No hard-coded evaluation percentages in the META answer (audit P1)."""
    info = PvSystemInfo(
        total_records=1,
        total_documents=1,
        total_chunks=1,
        records_by_source=(("ictv", 1),),
        documents_by_language=(("en", 1),),
    )
    text = format_meta_answer(info)
    assert "Latest Evaluation" not in text
    assert "85.7" not in text
    assert "100.0%" not in text
    assert not hasattr(info, "citation_supported_rate")
    assert not hasattr(info, "answered_rate")


# ── PvAnswerGenerator ──────────────────────────────────────────────────


def _dummy_chunks(n: int = 1) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=i,
            doc_id=i,
            chunk_index=0,
            openalex_id=None,
            title=f"Doc {i}",
            text=f"content {i}",
            score=0.9,
        )
        for i in range(1, n + 1)
    ]


def test_generator_qa_prompt_en() -> None:
    gen = PvAnswerGenerator(llm=None)
    gen._current_task_type = TaskType.QA
    msgs = gen._build_messages("What is TMV?", _dummy_chunks())
    assert msgs[0].content == PV_QA_SYSTEM_PROMPT


def test_generator_qa_prompt_zh() -> None:
    gen = PvAnswerGenerator(llm=None)
    gen._current_task_type = TaskType.QA
    msgs = gen._build_messages("什么是TMV？", _dummy_chunks())
    assert msgs[0].content == PV_QA_SYSTEM_PROMPT_ZH


def test_generator_planning_prompt_en() -> None:
    gen = PvAnswerGenerator(llm=None)
    gen._current_task_type = TaskType.PLANNING
    msgs = gen._build_messages("How to control CMV?", _dummy_chunks())
    assert msgs[0].content == PV_PLANNING_SYSTEM_PROMPT


def test_generator_planning_prompt_zh() -> None:
    gen = PvAnswerGenerator(llm=None)
    gen._current_task_type = TaskType.PLANNING
    msgs = gen._build_messages("如何防控CMV？", _dummy_chunks())
    assert msgs[0].content == PV_PLANNING_SYSTEM_PROMPT_ZH


def test_generator_default_task_type_is_qa() -> None:
    gen = PvAnswerGenerator(llm=None)
    assert gen._current_task_type == TaskType.QA


def test_generator_includes_chunks_in_user_message() -> None:
    gen = PvAnswerGenerator(llm=None)
    gen._current_task_type = TaskType.QA
    chunks = _dummy_chunks(2)
    msgs = gen._build_messages("What is TMV?", chunks)
    user_content = msgs[1].content
    assert "Doc 1" in user_content
    assert "content 1" in user_content
    assert "Doc 2" in user_content


def test_generator_empty_chunks() -> None:
    gen = PvAnswerGenerator(llm=None)
    msgs = gen._build_messages("What is TMV?", [])
    assert msgs[0].content == PV_QA_SYSTEM_PROMPT  # EN because no CJK
    assert isinstance(msgs[1], ChatMessage)
