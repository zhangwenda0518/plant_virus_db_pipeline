"""PubMed paper ingestion with DOI-based deduplication against existing
pv_documents (which were mostly ingested from OpenAlex).

The PubMed query is generated dynamically from ``*_host_probability.tsv`` files
which contain host predictions for virus families, genera, and species at
three taxonomic levels. Only high- and medium-confidence plant-host predictions
are used as search terms.
"""

from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from plant_virus_rag.corpus.pubmed_client import PubMedClient
from plant_virus_rag.db.models import PvDocument, SourceType
from plant_virus_rag.db.repositories import PvDocumentRepository


def _find_tsv_path(filename: str) -> Path | None:
    """Look for the TSV file next to the project root (alongside .env.local)."""
    # Try cwd first, then walk up to find the project root
    cwd = Path.cwd()
    for base in [cwd, cwd.parent, cwd.parent.parent]:
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def _load_plant_virus_taxa() -> tuple[list[str], list[str]]:
    """Extract high+medium confidence plant-host genera and families from TSVs.

    Returns (genera, families).
    """
    genera: list[str] = []
    families: list[str] = []

    genus_path = _find_tsv_path("genus_host_probability.tsv")
    if genus_path and genus_path.exists():
        with open(genus_path, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                host = row.get("Predicted_Host", "")
                conf = row.get("Confidence_Level", "")
                name = row.get("Genus", "").strip()
                if host == "Plant" and ("High" in conf or "Medium" in conf) and name:
                    genera.append(name)

    family_path = _find_tsv_path("family_host_probability.tsv")
    if family_path and family_path.exists():
        with open(family_path, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                host = row.get("Predicted_Host", "")
                conf = row.get("Confidence_Level", "")
                name = row.get("Family", "").strip()
                if host == "Plant" and ("High" in conf or "Medium" in conf) and name:
                    families.append(name)

    return genera, families


def build_plant_virus_query() -> str:
    """Build a PubMed search query from probability-TSV-derived plant virus taxa.

    Uses genera and families from ``genus_host_probability.tsv`` and
    ``family_host_probability.tsv`` (high + medium confidence only) plus
    a base set of broad plant-virology terms.  Limits searches to title +
    abstract fields to keep the result set relevant.
    """
    genera, families = _load_plant_virus_taxa()

    # Base terms — always included
    taxa_terms = [
        '"plant virus"',
        '"plant viruses"',
        "phytovirus",
    ]

    # Family names (e.g. Potyviridae, Geminiviridae)
    for fam in families:
        taxa_terms.append(fam + "[tiab]")

    # Genus names (e.g. Potyvirus, Begomovirus)
    for gen in genera:
        taxa_terms.append(gen + "[tiab]")

    # Key specific viruses (common/significant, may not be genera in the TSV)
    key_viruses = [
        '"tobacco mosaic virus"',
        '"tomato spotted wilt virus"',
        '"cucumber mosaic virus"',
        '"turnip mosaic virus"',
        '"rice stripe virus"',
        '"maize lethal necrosis"',
        '"citrus tristeza virus"',
        '"tomato yellow leaf curl virus"',
    ]
    for kv in key_viruses:
        taxa_terms.append(kv + "[tiab]")

    virus_clause = " OR ".join(taxa_terms)

    scope_terms = " OR ".join(
        [
            "virology[tiab]",
            "infection[tiab]",
            "resistance[tiab]",
            "detection[tiab]",
            "transmission[tiab]",
            "host[tiab]",
        ]
    )

    query = f'(({virus_clause}) AND ({scope_terms}))'
    return query


# Cache the query at module level so TSV files are read only once.
PLANT_VIRUS_PUBMED_QUERY = build_plant_virus_query()


class PubMedIngestionService:
    """Search PubMed, deduplicate against existing pv_documents, insert new papers."""

    def __init__(self, client: PubMedClient, session: Session):
        self._client = client
        self._repo = PvDocumentRepository(session)
        self._session = session

    def search_and_ingest(
        self,
        *,
        max_results: int = 500,
        year_from: int | None = None,
        year_to: int | None = None,
        commit_every: int = 50,
    ) -> dict:
        """Search PubMed and insert new papers.

        Returns ``{new, skipped_duplicate, total_fetched}``.
        """
        pmids = self._client.search(
            PLANT_VIRUS_PUBMED_QUERY,
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
        )
        if not pmids:
            return {"new": 0, "skipped_duplicate": 0, "total_fetched": 0}

        papers = self._client.fetch_details(pmids)
        new_count = 0
        dup_count = 0

        for i, paper in enumerate(papers):
            existing = None

            # Dedup strategy: DOI is strongest signal
            if paper.doi:
                existing = (
                    self._session.query(PvDocument)
                    .filter(PvDocument.doi == paper.doi)
                    .first()
                )

            # Fallback: check by pubmed_id (may already exist from OpenAlex)
            if existing is None and paper.pmid:
                existing = (
                    self._session.query(PvDocument)
                    .filter(PvDocument.pubmed_id == paper.pmid)
                    .first()
                )

            if existing is not None:
                dup_count += 1
                # Enrich pubmed_id if missing on existing record
                if not existing.pubmed_id:
                    existing.pubmed_id = paper.pmid
                continue

            # Insert new paper from PubMed
            self._repo.upsert_metadata(
                source_type=SourceType.PUBMED,
                openalex_id=None,
                pubmed_id=paper.pmid,
                doi=paper.doi,
                title=paper.title,
                authors=paper.authors,
                venue=paper.venue,
                year=paper.year,
                language=paper.language,
                is_oa=paper.is_oa,
                cited_by_count=0,
                abstract_text=paper.abstract,
                virus_names=None,
            )
            new_count += 1

            if commit_every and (i + 1) % commit_every == 0:
                self._session.flush()

        self._session.commit()
        return {
            "new": new_count,
            "skipped_duplicate": dup_count,
            "total_fetched": len(pmids),
        }
