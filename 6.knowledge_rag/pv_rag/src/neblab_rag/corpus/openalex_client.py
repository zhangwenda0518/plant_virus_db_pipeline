# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false
"""Thin wrapper over pyalex with our DTO.

OpenAlex returns abstracts as an inverted index (``{word: [positions]}``)
rather than plain text — we reconstruct the original ordering here.

Setting ``pyalex.config.email`` is a process-global mutation; instantiating
``OpenAlexClient`` more than once with different emails will race. For v1
we always build a single client per ingestion run, so this is safe.
"""

from collections.abc import Iterator

import pyalex
from pyalex import Works
from pydantic import BaseModel


class OpenAlexRecord(BaseModel):
    openalex_id: str
    pubmed_id: str | None = None
    doi: str | None
    title: str
    authors: list[str]
    venue: str | None
    year: int | None
    language: str | None
    is_oa: bool
    cited_by_count: int
    abstract: str | None


class SearchResult:
    """Iterable search result with total count metadata."""

    def __init__(self, iterator: Iterator[OpenAlexRecord], total_count: int):
        self._iterator = iterator
        self.total_count = total_count

    def __iter__(self) -> Iterator[OpenAlexRecord]:
        return self._iterator


def _restore_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


class OpenAlexClient:
    def __init__(self, email: str):
        pyalex.config.email = email

    def get_pdf_url(self, openalex_id: str) -> str | None:
        """Look up the OA PDF URL for a single work by OpenAlex id.

        Returns None if the work isn't OA, has no resolvable PDF location,
        or the OpenAlex API doesn't know about the id. Callers should
        treat None as 'no PDF available' and skip that document.

        OpenAlex puts PDF URLs in two possible places: best_oa_location and
        primary_location. Some records have one but not the other; we
        check both.
        """
        try:
            work = Works()[openalex_id]
        except Exception:
            return None
        for key in ("best_oa_location", "primary_location"):
            loc = work.get(key) or {}
            url = loc.get("pdf_url")
            if url:
                return str(url)
        return None

    def search_by_keywords(
        self,
        *,
        keywords: list[str],
        language: str | None = None,
        max_results: int = 1000,
        per_page: int = 100,
        year_from: int | None = None,
        year_to: int | None = None,
        single_year: int | None = None,
    ) -> SearchResult:
        query = " OR ".join(f'"{k}"' for k in keywords)
        works = Works().search(query)
        if language:
            works = works.filter(language=language)
        if single_year is not None:
            # pyalex supports direct keyword=value for exact year match
            works = works.filter(publication_year=single_year)
        elif year_from and year_to:
            works = works.filter(publication_year=f">{year_from - 1}").filter(publication_year=f"<{year_to + 1}")
        elif year_from:
            works = works.filter(publication_year=f">{year_from - 1}")
        elif year_to:
            works = works.filter(publication_year=f"<{year_to + 1}")

        total_results = works.count()

        def _iter() -> Iterator[OpenAlexRecord]:
            count = 0
            for page in works.paginate(per_page=per_page, n_max=max_results):
                for w in page:
                    if count >= max_results:
                        return
                    loc = w.get("primary_location") or {}
                    src = loc.get("source") or {}
                    oa = w.get("open_access") or {}
                    authorships = w.get("authorships") or []
                    pubmed_url = (w.get("ids") or {}).get("pmid", "")
                    pubmed_id = pubmed_url.rsplit("/", 1)[-1] if pubmed_url else None
                    yield OpenAlexRecord(
                        openalex_id=w["id"].rsplit("/", 1)[-1],
                        pubmed_id=pubmed_id,
                        doi=(w.get("doi") or "").removeprefix("https://doi.org/") or None,
                        title=w.get("title") or "",
                        authors=[
                            name
                            for a in authorships
                            if (name := (a.get("author") or {}).get("display_name"))
                        ],
                        venue=src.get("display_name"),
                        year=w.get("publication_year"),
                        language=w.get("language"),
                        is_oa=bool(oa.get("is_oa") or False),
                        cited_by_count=w.get("cited_by_count") or 0,
                        abstract=_restore_abstract(w.get("abstract_inverted_index")),
                    )
                    count += 1

        return SearchResult(_iter(), total_results)
