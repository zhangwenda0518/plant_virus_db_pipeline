"""PubMed client via Biopython Bio.Entrez.

Rate-limited (3 req/s as per NCBI guidelines) with a mandatory email
for Entrez identification.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from Bio import Entrez

# NCBI: no more than 3 requests/second without an API key
_DEFAULT_RATE = 3.0  # seconds between requests


@dataclass
class PubMedPaper:
    pmid: str
    doi: str | None
    title: str
    authors: list[str]
    venue: str | None
    year: int | None
    language: str | None
    abstract: str | None
    is_oa: bool
    pub_type_list: list[str]


class PubMedClient:
    """Searches PubMed and fetches structured metadata."""

    def __init__(self, email: str, *, rate_limit: float = _DEFAULT_RATE):
        Entrez.email = email
        self._rate = rate_limit
        self._last_request = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._rate:
            time.sleep(self._rate - elapsed)
        self._last_request = time.monotonic()

    def search(
        self,
        query: str,
        *,
        max_results: int = 500,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[str]:
        """Return PubMed IDs matching the query."""
        full_query = query
        if year_from or year_to:
            if year_from and year_to:
                full_query += f" AND ({year_from}:{year_to}[dp])"
            elif year_from:
                full_query += f" AND ({year_from}:3000[dp])"
            else:
                full_query += f" AND (1800:{year_to}[dp])"

        self._wait()
        handle = Entrez.esearch(
            db="pubmed", term=full_query, retmax=max_results, sort="relevance"
        )
        result = Entrez.read(handle)
        handle.close()
        return list(result["IdList"])

    def fetch_details(self, pmids: list[str]) -> list[PubMedPaper]:
        """Fetch structured metadata for a batch of PubMed IDs."""
        if not pmids:
            return []
        self._wait()
        handle = Entrez.efetch(
            db="pubmed", id=",".join(pmids), rettype="xml", retmode="xml"
        )
        records = Entrez.read(handle)
        handle.close()

        papers: list[PubMedPaper] = []
        for article in records["PubmedArticle"]:
            paper = self._parse_article(article)
            if paper:
                papers.append(paper)
        return papers

    def _parse_article(self, article: dict) -> PubMedPaper | None:
        try:
            medline = article["MedlineCitation"]
            pmid = str(medline["PMID"])
            article_data = medline.get("Article", {})

            # Title
            title = article_data.get("ArticleTitle", "")
            if not title:
                return None

            # DOI
            doi = None
            for eid in article_data.get("ELocationID", []):
                if eid.attributes.get("EIdType") == "doi":
                    doi = str(eid)
                    break
            if not doi:
                for aid in article.get("PubmedData", {}).get("ArticleIdList", []):
                    if aid.attributes.get("IdType") == "doi":
                        doi = str(aid)
                        break

            # Authors
            authors: list[str] = []
            for author in article_data.get("AuthorList", []):
                last = author.get("LastName", "")
                fore = author.get("ForeName", "")
                if last:
                    authors.append(f"{last}, {fore}" if fore else last)

            # Journal
            journal = article_data.get("Journal", {})
            venue = journal.get("Title", None)
            if not venue:
                venue = journal.get("ISOAbbreviation", None)

            # Year
            year = None
            pub_date = journal.get("JournalIssue", {}).get("PubDate", {})
            year_str = pub_date.get("Year", "")
            if year_str:
                try:
                    year = int(year_str)
                except ValueError:
                    pass

            # Language
            language = article_data.get("Language", [None])[0]

            # Abstract
            abstract_data = article_data.get("Abstract", {}).get("AbstractText", [])
            abstract = " ".join(
                str(t) for t in abstract_data if t
            ) or None

            # Publication types
            pub_types = [
                str(pt) for pt in medline.get("PublicationTypeList", [])
            ]

            # PubMedCentral (OA)
            is_oa = False
            for pid in article.get("PubmedData", {}).get("ArticleIdList", []):
                if pid.attributes.get("IdType") == "pmc":
                    is_oa = True
                    break

            return PubMedPaper(
                pmid=pmid,
                doi=doi,
                title=title,
                authors=authors,
                venue=venue,
                year=year,
                language=language,
                abstract=abstract,
                is_oa=is_oa,
                pub_type_list=pub_types,
            )
        except Exception:
            return None
