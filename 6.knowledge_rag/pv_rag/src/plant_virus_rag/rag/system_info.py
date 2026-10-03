"""Plant-virus-specific system info for the META task handler.

Provides live corpus stats from the pv_* Postgres tables, a canned identity
answer, and a Markdown formatting template.  The meta path never calls the LLM;
all answers are deterministic and cost-free.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from plant_virus_rag.db.engine import get_pv_session
from plant_virus_rag.db.models import PvChunk, PvDocument, PvRecord


@dataclass(frozen=True)
class PvSystemInfo:
    # Live counts
    total_records: int
    total_documents: int
    total_chunks: int
    records_by_source: tuple[tuple[str, int], ...]
    documents_by_language: tuple[tuple[str, int], ...]

    # Baked-in config — update alongside findings docs.
    #
    # NOTE(2026-10-03 audit): the former ``sprint`` / ``citation_supported_rate``
    # (0.857) / ``answered_rate`` (1.0) / ``eval_set_size`` fields were
    # self-reported constants with no artifact behind them, and they were being
    # rendered as "Latest Evaluation" numbers in the META answer.  They are
    # removed: this struct now only carries live DB counts (computed in
    # PvPostgresSystemInfoProvider.get) plus verifiable retrieval config.
    chunk_size: int = 1500
    chunk_overlap: int = 300
    topics: tuple[str, ...] = (
        "plant virus taxonomy",
        "plant virology",
        "virus-host interactions",
        "viral diseases of crops",
        "virus transmission & vectors",
        "disease management & control",
    )
    sources: tuple[str, ...] = ("ICTV", "ViralZone", "NCBI", "DPV", "OpenAlex")


class PvSystemInfoProvider(Protocol):
    """Protocol so tests can inject a stub without touching Postgres."""

    def get(self) -> PvSystemInfo: ...


@dataclass
class PvPostgresSystemInfoProvider:
    """Reads plant virus corpus stats live from Postgres each call."""

    session_factory: object = field(default=None)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self.session_factory is None:
            with get_pv_session() as s:
                yield s
        else:
            with self.session_factory() as s:  # type: ignore[misc]
                yield s

    def get(self) -> PvSystemInfo:
        with self._session() as session:
            total_records = session.query(PvRecord).count()
            total_documents = session.query(PvDocument).count()
            total_chunks = session.query(PvChunk).count()

            src_rows = (
                session.query(
                    PvRecord.source_type, func.count(PvRecord.id)
                )
                .group_by(PvRecord.source_type)
                .all()
            )
            records_by_source = tuple(
                (st or "unknown", int(cnt)) for st, cnt in sorted(src_rows)
            )

            lang_rows = (
                session.query(
                    PvDocument.language, func.count(PvDocument.id)
                )
                .group_by(PvDocument.language)
                .all()
            )
            documents_by_language = tuple(
                (lang or "unknown", int(cnt)) for lang, cnt in sorted(lang_rows)
            )

        return PvSystemInfo(
            total_records=total_records,
            total_documents=total_documents,
            total_chunks=total_chunks,
            records_by_source=records_by_source,
            documents_by_language=documents_by_language,
        )


# Identity sub-routing patterns (same logic as neblab version)
_IDENTITY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
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


def is_identity_query(query: str) -> bool:
    """True when a META query is asking about the assistant's identity."""
    return any(p.search(query) for p in _IDENTITY_PATTERNS)


IDENTITY_ANSWER = (
    "## About Plant Virus RAG Knowledge Assistant\n\n"
    "I am the **Plant Virus RAG Knowledge Assistant**, "
    "a retrieval-augmented Q&A system for the Plant Virus Database.\n\n"
    "### Model Backend\n\n"
    "- **DeepSeek V4 Pro** serves as the foundation model for this system.\n\n"
    "### System Capabilities\n\n"
    "- Answers questions based on indexed plant virus structured data "
    "(ICTV/ViralZone/NCBI/DPV) and academic papers\n"
    "- Strict evidence-bound answers for virus facts/mechanisms (QA mode)\n"
    "- Labeled reasoning for management/strategy questions (Planning mode)\n"
    "- Direct structured responses for system metadata queries (Meta mode)\n\n"
    "### Data Sources\n\n"
    "- ICTV (International Committee on Taxonomy of Viruses)\n"
    "- ViralZone (virus knowledge portal)\n"
    "- NCBI virus-host information\n"
    "- DPV (Descriptions of Plant Viruses)\n"
    "- OpenAlex academic papers\n\n"
    "### Citation Discipline\n\n"
    "- Data-supported claims: marked with `[N]`\n"
    "- Inferred or extrapolated claims: marked with `(inferred)`\n"
    "- Insufficient data: explicitly stated with suggestions for further research\n\n"
    "---\n\n"
    '*Ask "How many virus species are in the database?" for corpus statistics.*\n'
)


def format_meta_answer(info: PvSystemInfo) -> str:
    """Render a uniform Markdown answer block from the PvSystemInfo struct."""
    src_lines = "\n".join(
        f"- **{src}**：{cnt}" for src, cnt in info.records_by_source
    )
    lang_lines = "\n".join(
        f"- **{lang}**: {cnt}" for lang, cnt in info.documents_by_language
    )
    topics = " / ".join(info.topics)
    sources = " / ".join(info.sources)
    return (
        "## Plant Virus Database Status\n\n"
        "### Corpus Size\n\n"
        f"- Structured virus records: **{info.total_records}**\n"
        f"- Academic papers: **{info.total_documents}**\n"
        f"- Indexed chunks: **{info.total_chunks}**\n\n"
        "### Records by Source\n\n"
        f"{src_lines}\n\n"
        "### Documents by Language\n\n"
        f"{lang_lines}\n\n"
        "### Topic Coverage\n\n"
        f"- {topics}\n\n"
        "### Data Sources\n\n"
        f"- {sources}\n\n"
        "### Retrieval & Generation Config\n\n"
        f"- chunk_size = {info.chunk_size} chars / overlap = {info.chunk_overlap}\n"
        f"- Default top_k = 12\n\n"
        # 评估指标不再在此输出：此前硬编码的 citation_supported_rate /
        # answered_rate 无评估工件支撑（审计 P1），如需展示请从 evals/ 的真实
        # 评估报告取数后另行注入。
        "---\n\n"
        "*System metadata queried live from Postgres, not from literature retrieval.*\n"
    )
