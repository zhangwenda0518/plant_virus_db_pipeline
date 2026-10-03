#!/usr/bin/env python3
"""Deduplication engine — DOI > PMID > normalized title (first 80 chars)."""
from typing import Optional


def normalize_title(title: str) -> str:
    """Strip punctuation, lowercase, first 80 chars for matching."""
    if not title:
        return ""
    import re
    t = re.sub(r"[^a-z0-9]", "", title.lower())
    return t[:80]


def normalize_doi(doi: str) -> str:
    """Lowercase and strip whitespace from DOI."""
    if not doi:
        return ""
    return doi.strip().lower()


def dedup_key(paper: dict) -> Optional[str]:
    """Return the strongest dedup key for a paper."""
    doi = normalize_doi(paper.get("doi", ""))
    if doi:
        return f"doi:{doi}"
    pmid = paper.get("pmid", "")
    if pmid:
        return f"pmid:{pmid}"
    title = normalize_title(paper.get("title", ""))
    if title:
        return f"title:{title}"
    return None


def _is_blank(value) -> bool:
    """True for values that carry no information (None, '', 0 — e.g. unknown year)."""
    return value is None or value == "" or value == 0


def merge_paper(existing: dict, new: dict) -> dict:
    """Merge new paper into existing, keeping richer data."""
    merged = dict(new)
    # Identity/date fields: an existing non-empty value always wins. `merged` is
    # seeded from `new`, so a re-fetch that lacks year/pub_date/added_date/
    # first_author used to blank out the master record (audit D4).
    for field in ("year", "pub_date", "added_date", "first_author"):
        old_val = existing.get(field)
        if not _is_blank(old_val):
            merged[field] = old_val
    for field in ("abstract", "authors", "journal", "doi", "mesh_terms", "keywords"):
        new_val = new.get(field, "")
        old_val = existing.get(field, "")
        if old_val and (not new_val or len(str(new_val)) < len(str(old_val))):
            merged[field] = old_val
    # Merge categories
    merged["categories"] = sorted(set(
        (existing.get("categories") or []) +
        (new.get("categories") or [])
    ))
    # Merge associated species
    merged["associated_species"] = sorted(set(
        (existing.get("associated_species") or []) +
        (new.get("associated_species") or [])
    ), key=lambda x: str(x))
    # Keep AI summary if exists
    for ai_field in ("virus_name", "taxonomy", "symptoms", "host_plant",
                     "location", "sample_date", "vector", "transmission",
                     "overview", "methods", "results", "discussion", "is_review"):
        if existing.get(ai_field) and not new.get(ai_field):
            merged[ai_field] = existing[ai_field]
    if existing.get("ai_done") and not new.get("ai_done"):
        merged["ai_done"] = True
    # Keep the last summarization failure marker: it is cleared only by a later
    # successful summarize run (summarize_papers pops it), not by a re-fetch.
    if existing.get("ai_error") and not new.get("ai_error"):
        merged["ai_error"] = existing["ai_error"]
    return merged
