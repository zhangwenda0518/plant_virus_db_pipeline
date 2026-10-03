"""Multi-source search provider abstraction.

Defines a ``SearchProvider`` ABC with concrete implementations for:
  - arXiv (free API, Atom XML)
  - Semantic Scholar (free API, JSON)
  - PubMed (via existing ``PubMedClient`` wrapper)

All providers return a uniform ``PaperRecord`` DTO.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from plant_virus_rag.corpus.pubmed_client import PubMedClient


@dataclass
class PaperRecord:
    """Uniform paper metadata across all sources."""

    title: str
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    year: int | None = None
    doi: str | None = None
    abstract: str | None = None
    language: str | None = None
    is_oa: bool = False
    pdf_url: str | None = None
    cited_by_count: int = 0

    # Source identifiers for dedup
    source: str = ""  # "arxiv", "semantic_scholar", "pubmed"
    source_id: str = ""  # arxiv_id, S2 paper ID, or PMID

    # PubMed-specific (set by PubMedProvider)
    pubmed_id: str | None = None


class SearchProvider(ABC):
    """Abstract search provider — one concrete class per data source."""

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        max_results: int = 100,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperRecord]:
        """Search and return structured paper records."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name, e.g. 'arxiv'."""
        ...


# ── arXiv ──────────────────────────────────────────────────────────────

_ARXIV_API = "https://export.arxiv.org/api/query"

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivProvider(SearchProvider):
    """Search arXiv via the public API (no key required)."""

    name = "arxiv"

    def search(
        self,
        query: str,
        *,
        max_results: int = 100,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperRecord]:
        search_query = f"all:{query}"
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(max_results, 100),
            "sortBy": "relevance",
        }
        resp = httpx.get(_ARXIV_API, params=params, timeout=30)
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.text)
        papers: list[PaperRecord] = []
        for entry in root.findall("atom:entry", _NS):
            title_el = entry.find("atom:title", _NS)
            title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""

            authors: list[str] = []
            for auth in entry.findall("atom:author/atom:name", _NS):
                if auth.text:
                    authors.append(auth.text.strip())

            summary_el = entry.find("atom:summary", _NS)
            abstract = summary_el.text.strip() if summary_el is not None else None

            # Extract arxiv ID from the <id> tag
            id_el = entry.find("atom:id", _NS)
            arxiv_id = ""
            if id_el is not None and id_el.text:
                arxiv_id = id_el.text.split("/abs/")[-1]

            # DOI
            doi = None
            for link in entry.findall("atom:link", _NS):
                href = link.attrib.get("href", "")
                title_attr = link.attrib.get("title", "")
                if "doi" in title_attr.lower() or "doi.org" in href:
                    doi = href.replace("http://dx.doi.org/", "").replace("https://doi.org/", "")
                    break

            # Year from published date
            published_el = entry.find("atom:published", _NS)
            year = None
            if published_el is not None and published_el.text:
                try:
                    year = int(published_el.text[:4])
                except (ValueError, IndexError):
                    pass

            # PDF URL
            pdf_url = None
            for link in entry.findall("atom:link", _NS):
                if link.attrib.get("title") == "pdf":
                    pdf_url = link.attrib.get("href")
                    break

            papers.append(
                PaperRecord(
                    title=title,
                    authors=authors,
                    venue="arXiv",
                    year=year,
                    doi=doi,
                    abstract=abstract,
                    language="en",
                    is_oa=True,  # arXiv papers are always freely accessible
                    pdf_url=pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None),
                    source="arxiv",
                    source_id=arxiv_id,
                )
            )
        return papers


# ── Semantic Scholar ────────────────────────────────────────────────────

_S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = (
    "title,authors,venue,year,externalIds,abstract,"
    "openAccessPdf,publicationTypes,citationCount"
)


class SemanticScholarProvider(SearchProvider):
    """Search Semantic Scholar via the public API.

    Without an API key the rate limit is very low (~1 req / few sec).
    Get a free key at https://www.semanticscholar.org/product/api#api-key-form
    and set ``S2_API_KEY`` in ``.env.local`` for higher limits.
    """

    name = "semantic_scholar"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def search(
        self,
        query: str,
        *,
        max_results: int = 100,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperRecord]:
        params: dict = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": _S2_FIELDS,
        }
        if year_from:
            params["year"] = f"{year_from}-{year_to or ''}"
        elif year_to:
            params["year"] = f"-{year_to}"

        headers = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        resp = httpx.get(_S2_API, params=params, timeout=30, headers=headers)
        if resp.status_code == 429:
            import time
            time.sleep(3)  # back off and retry once
            resp = httpx.get(_S2_API, params=params, timeout=30, headers=headers)
        if resp.status_code != 200:
            return []

        data = resp.json()
        papers: list[PaperRecord] = []
        for item in data.get("data", []):
            doi = item.get("externalIds", {}).get("DOI")
            s2_id = item.get("paperId", "")
            title = item.get("title", "") or ""

            authors_raw = item.get("authors", [])
            authors = [a.get("name", "") for a in authors_raw if a.get("name")]

            venue = item.get("venue", "")
            if venue:
                venue = venue if isinstance(venue, str) else venue.get("name", "")

            year = item.get("year")

            abstract = item.get("abstract")

            oa_info = item.get("openAccessPdf") or {}
            pdf_url = oa_info.get("url")

            pubs = item.get("publicationTypes") or []
            is_oa = "OpenAccess" in str(pubs) or pdf_url is not None

            papers.append(
                PaperRecord(
                    title=title,
                    authors=authors,
                    venue=venue if venue else None,
                    year=int(year) if year else None,
                    doi=doi,
                    abstract=abstract,
                    language="en",
                    is_oa=is_oa,
                    pdf_url=pdf_url,
                    cited_by_count=item.get("citationCount", 0) or 0,
                    source="semantic_scholar",
                    source_id=s2_id,
                )
            )
        return papers


# ── PubMed (wrapper around existing client) ─────────────────────────────


class OpenAlexSearchProvider(SearchProvider):
    """Search OpenAlex via pyalex (API key recommended for higher rate limits)."""

    name = "openalex"

    def __init__(self, email: str):
        from neblab_rag.corpus.openalex_client import OpenAlexClient
        self._client = OpenAlexClient(email=email)

    def search(
        self,
        query: str,
        *,
        max_results: int = 100,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperRecord]:
        keywords = [query]  # OpenAlex's search_by_keywords takes a list
        sr = self._client.search_by_keywords(
            keywords=keywords,
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
        )
        records: list[PaperRecord] = []
        for r in sr:
            records.append(
                PaperRecord(
                    title=r.title,
                    authors=r.authors,
                    venue=r.venue,
                    year=r.year,
                    doi=r.doi,
                    abstract=r.abstract,
                    language=r.language,
                    is_oa=r.is_oa,
                    cited_by_count=r.cited_by_count,
                    source="openalex",
                    source_id=r.openalex_id,
                    pubmed_id=r.pubmed_id,
                )
            )
        return records


class PubMedSearchProvider(SearchProvider):
    """Adapter that wraps ``PubMedClient`` into the ``SearchProvider`` interface."""

    name = "pubmed"

    def __init__(self, email: str):
        self._client = PubMedClient(email=email)

    def search(
        self,
        query: str,
        *,
        max_results: int = 100,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PaperRecord]:
        from plant_virus_rag.corpus.pubmed_ingestion import PLANT_VIRUS_PUBMED_QUERY

        pmid_list = self._client.search(
            query or PLANT_VIRUS_PUBMED_QUERY,
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
        )
        if not pmid_list:
            return []

        papers = self._client.fetch_details(pmid_list)
        records: list[PaperRecord] = []
        for p in papers:
            records.append(
                PaperRecord(
                    title=p.title,
                    authors=p.authors,
                    venue=p.venue,
                    year=p.year,
                    doi=p.doi,
                    abstract=p.abstract,
                    language=p.language,
                    is_oa=p.is_oa,
                    source="pubmed",
                    source_id=p.pmid,
                    pubmed_id=p.pmid,
                )
            )
        return records
