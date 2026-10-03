"""Lightweight rule-based classifier for plant virus RAG: QA vs planning vs meta.

Adapted from neblab_rag.rag.task_classifier with plant-virology-specific
vocabulary for META (virus DB stats, species counts) and PLANNING (disease
control/management plans).
"""

from __future__ import annotations

import re
from enum import StrEnum


class TaskType(StrEnum):
    QA = "qa"
    PLANNING = "planning"
    META = "meta"


# Patterns indicating a meta query — about the SYSTEM (corpus size, coverage,
# identity) rather than about plant virus content.  Checked first.
_META_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # corpus stats / coverage
        r"多少(个|条|篇|种)",
        r"一共.*?(个|条|篇|种)",
        r"总共.*?(个|条|篇|种)",
        r"收录.*?(多少|哪些|什么)",
        r"(数据库|知识库|系统|语料库).*?(多少|有什么|包含|覆盖|哪些|规模|状态|信息)",
        r"(覆盖|包含|涵盖).*?(多少|哪些)(主题|病毒|种类|来源)",
        r"哪些(主题|病毒|种类|来源|宿主|数据)",
        r"\bhow many (?:viruses?|species|records?|papers?|documents?)\b",
        r"\b(?:virus )?(?:database|corpus) (?:size|coverage|stats?|info)\b",
        r"\b(?:what (?:viruses?|species)|which (?:viruses?|hosts?))\b",
        r"\b(?:about|describe) (?:this|the) (?:database|system|corpus)\b",
        # identity / model base
        r"你是谁",
        r"你是(?:什么|哪个|哪一个)(?:模型|AI|大模型|系统|助手|数据库)",
        r"你(?:的)?(?:模型)?(?:底座|基座|backbone)",
        r"谁(?:开发|训练|做)(?:了)?你",
        r"你由(?:什么|哪个).*?(?:模型|公司)",
        r"\bwho are you\b",
        r"\bwhat (?:model|llm|ai) (?:are you|is this|powers?)\b",
        r"\bwhich (?:model|llm) (?:are you|do you use)\b",
        r"\bpowered by (?:what|which)\b",
    )
)

# Keywords that strongly suggest planning / disease management / strategy work.
_PLANNING_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # zh: design/plan/strategy/proposal/measures
        r"设计",
        r"方案",
        r"规划",
        r"计划",
        r"措施",
        r"策略",
        r"做法",
        r"路线",
        r"建议",
        # zh: plant-virus-specific planning
        r"防治",
        r"防控",
        r"控制",
        r"管理",
        r"治理",
        r"抗病毒",
        r"抗病",
        r"检疫",
        r"监测",
        # zh: imperative help phrases
        r"帮我",
        r"给我",
        r"如何制定",
        r"怎么安排",
        r"怎么做",
        r"怎么办",
        # en
        r"\bdesign\b",
        r"\bplan\b",
        r"\bproposal\b",
        r"\bblueprint\b",
        r"\bframework\b",
        r"\brecommend(?:ation)?s?\b",
        r"\bhow to\b",
        r"\bhelp me\b",
        # en: plant-virus-specific (compound to avoid matching scientific terms)
        r"management (?:strategy|plan|approach|of)",
        r"control (?:strategy|measure|of)",
        r"prevention (?:strategy|measure)",
        r"\bdisease management\b",
        r"\bintegrated pest\b",
        r"\bquarantine\b",
        r"\bsurveillance\b",
    )
)

# Strong QA signals — definition / mechanism / explanation queries.
_QA_OVERRIDE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^什么是",
        r"是什么",
        r"^为什么",
        r"^如何理解",
        r"^哪种",
        r"^哪些",
        r"\bwhat is\b",
        r"\bwhat are\b",
        r"\bwhy (?:does|do|is|are)\b",
        r"\bdefine\b",
        r"\bhow does\b",
        r"\bhow do\b",
    )
)


def classify(query: str) -> TaskType:
    """Route a query to the right task type.

    Order matters:
      1. META — checked first (corpus stats / identity).
      2. QA override — definition / mechanism queries stay strict.
      3. PLANNING — design / strategy / disease management.
      4. Default → QA.
    """
    if not query:
        return TaskType.QA
    for p in _META_PATTERNS:
        if p.search(query):
            return TaskType.META
    for p in _QA_OVERRIDE_PATTERNS:
        if p.search(query):
            return TaskType.QA
    for p in _PLANNING_PATTERNS:
        if p.search(query):
            return TaskType.PLANNING
    return TaskType.QA
