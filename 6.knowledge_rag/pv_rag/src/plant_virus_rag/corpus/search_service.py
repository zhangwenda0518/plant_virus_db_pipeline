"""Multi-source search orchestrator.

Fans out a query to all configured ``SearchProvider`` implementations in
parallel (via ``ThreadPoolExecutor``), deduplicates results by DOI (then
title), and returns a unified ranked result set.

Inspired by ArxivAgent's ``SearchService`` pattern.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

from plant_virus_rag.corpus.search_provider import PaperRecord, SearchProvider

# Source trust bonus: more authoritative sources get a scoring edge.
_SOURCE_BONUS: dict[str, float] = {
    "pubmed": 1.0,
    "semantic_scholar": 0.9,
    "arxiv": 0.85,
}


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy match."""
    if not title:
        return ""
    return re.sub(r"[^a-z0-9\s]", "", title.lower().strip())


def _title_similarity(a: str, b: str) -> float:
    """Simple title similarity via SequenceMatcher."""
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _paper_identity(paper: PaperRecord) -> tuple[str, str]:
    """Return a dedup identity tuple: (doi_or_empty, normalized_title)."""
    return (paper.doi or "", _normalize_title(paper.title))


class SearchService:
    """Parallel multi-source search with DOI-based deduplication."""

    def __init__(self, providers: list[SearchProvider]):
        self._providers = providers

    def search(
        self,
        query: str,
        *,
        max_results: int = 100,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperRecord]:
        """Search all providers in parallel, deduplicate, rank."""
        all_papers: list[PaperRecord] = []

        with ThreadPoolExecutor(max_workers=len(self._providers)) as pool:
            futures = {
                pool.submit(p.search, query, max_results=max_results, year_from=year_from, year_to=year_to): p
                for p in self._providers
            }
            for fut in as_completed(futures):
                try:
                    results = fut.result()
                    all_papers.extend(results)
                except Exception:
                    pass  # one source failing shouldn't abort the batch

        return self._dedupe_and_rank(all_papers)

    def _dedupe_and_rank(
        self, papers: list[PaperRecord]
    ) -> list[PaperRecord]:
        """DOI-then-title dedup, then score-sort descending."""
        seen: dict[str, PaperRecord] = {}  # DOI → best paper
        title_groups: dict[str, list[PaperRecord]] = {}  # norm_title → candidates

        for paper in papers:
            # Primary dedup key: DOI
            if paper.doi and paper.doi.strip():
                doi_key = paper.doi.strip().lower()
                if doi_key in seen:
                    # Keep the one with better metadata (e.g. more complete abstract)
                    existing = seen[doi_key]
                    if self._is_better(paper, existing):
                        seen[doi_key] = paper
                else:
                    seen[doi_key] = paper
            else:
                # No DOI — group by normalized title for fuzzy match
                nt = _normalize_title(paper.title)
                title_groups.setdefault(nt, []).append(paper)

        # For title groups, deduplicate by similarity > 0.85
        merged: list[PaperRecord] = list(seen.values())
        processed_titles: set[str] = set()

        for nt, group in title_groups.items():
            # Check if this title group is already covered by a DOI paper
            already_covered = False
            for existing in merged:
                if _title_similarity(nt, _normalize_title(existing.title)) > 0.85:
                    already_covered = True
                    break
            if already_covered:
                continue

            # Dedup within the title group
            best = max(group, key=lambda p: self._paper_score(p))
            merged.append(best)

        merged.sort(key=lambda p: self._paper_score(p), reverse=True)
        return merged

    @staticmethod
    def _is_better(a: PaperRecord, b: PaperRecord) -> bool:
        """Return True if ``a`` is a better record than ``b``."""
        score_a = (
            (1 if a.abstract else 0)
            + (1 if a.doi else 0)
            + (1 if a.authors else 0)
            + (a.cited_by_count / 1000)
        )
        score_b = (
            (1 if b.abstract else 0)
            + (1 if b.doi else 0)
            + (1 if b.authors else 0)
            + (b.cited_by_count / 1000)
        )
        return score_a > score_b

    @staticmethod
    def _paper_score(paper: PaperRecord) -> float:
        """Composite score for ranking: source trust + citation boost."""
        src = _SOURCE_BONUS.get(paper.source, 0.5)
        citation = min(paper.cited_by_count / 500, 1.0) * 0.3
        has_abstract = 0.2 if paper.abstract else 0.0
        has_doi = 0.1 if paper.doi else 0.0
        return src + citation + has_abstract + has_doi
