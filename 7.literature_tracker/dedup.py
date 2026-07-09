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


def merge_paper(existing: dict, new: dict) -> dict:
    """Merge new paper into existing, keeping richer data."""
    merged = dict(new)
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
    for ai_field in ("summary_zh", "innovation", "limitation", "study_object",
                     "disease", "sample_size", "method_zh", "contributions"):
        if existing.get(ai_field) and not new.get(ai_field):
            merged[ai_field] = existing[ai_field]
    if existing.get("ai_done") and not new.get("ai_done"):
        merged["ai_done"] = True
    return merged
