#!/usr/bin/env python3
"""Fetch plant virus preprints from arXiv and bioRxiv."""
import json, os, sys, time, argparse, re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote
from xml.etree import ElementTree as ET

from config import PREPRINT_KEYWORDS, BIOXIV_KEYWORDS, PAPERS_JSON
from dedup import dedup_key

ARXIV_API = "https://export.arxiv.org/api/query"
BIORXIV_API = "https://api.biorxiv.org/details/biorxiv"


def search_arxiv(keywords: list, days: int = 7, max_results: int = 50) -> list:
    """Search arXiv for plant virus preprints in q-bio categories."""
    # Build keyword query (OR logic within each category group)
    terms = []
    for kw in keywords[:20]:  # Limit to avoid overly long query
        escaped = quote(f'all:"{kw}"')
        terms.append(escaped)

    # q-bio categories: Genomics, Populations & Evolution, Molecular Networks
    cat_filter = "cat:q-bio.GN OR cat:q-bio.PE OR cat:q-bio.MN OR cat:q-bio.OT"
    query = f"({' OR '.join(terms)}) AND ({cat_filter})"

    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    url = f"{ARXIV_API}?{urlencode(params)}"
    print(f"  Searching arXiv: {url[:120]}...")

    papers = []
    try:
        req = Request(url, headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"})
        with urlopen(req, timeout=30) as resp:
            tree = ET.parse(resp)
    except Exception as e:
        print(f"  arXiv API error: {e}")
        return papers

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    for entry in tree.findall("atom:entry", ns):
        try:
            arxiv_id_el = entry.find("atom:id", ns)
            arxiv_id = arxiv_id_el.text.split("/abs/")[-1] if arxiv_id_el is not None else ""
            title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
            abstract = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
            published = entry.findtext("atom:published", "", ns)[:10]

            authors = []
            for a in entry.findall("atom:author/atom:name", ns):
                if a.text:
                    authors.append(a.text)

            # Extract DOI from links
            doi = ""
            for link in entry.findall("atom:link", ns):
                href = link.get("href", "")
                if "doi.org" in href:
                    doi = href.split("doi.org/")[-1]

            # Extract categories
            cats = []
            for cat in entry.findall("atom:category", ns):
                term = cat.get("term", "")
                if term:
                    cats.append(term)

            # Match plant virus relevance
            matched_keywords = []
            text = (title + " " + abstract).lower()
            for kw in PREPRINT_KEYWORDS:
                if kw.lower() in text:
                    matched_keywords.append(kw)

            if matched_keywords:
                papers.append({
                    "arxiv_id": arxiv_id,
                    "doi": doi,
                    "title": title,
                    "abstract": abstract[:2000],
                    "authors": "; ".join(authors[:8]),
                    "first_author": authors[0] if authors else "",
                    "year": int(published[:4]) if published else 0,
                    "pub_date": published,
                    "journal": f"arXiv preprint ({', '.join(cats[:3])})",
                    "source": "arxiv",
                    "source_strategy": "preprint",
                    "categories": ["General"],
                    "keyword_hits": matched_keywords,
                    "added_date": datetime.now().strftime("%Y-%m-%d"),
                    "ai_done": False,
                })
        except Exception as e:
            continue

    return papers


def search_biorxiv(keywords: list, days: int = 7, max_results: int = 100) -> list:
    """Search bioRxiv API for plant virus preprints."""
    papers = []
    cursor = 0
    total_found = 0

    # Use date range query
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    print(f"  Searching bioRxiv: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # bioRxiv API: cursor-based pagination with date range
    while True:
        url = f"{BIORXIV_API}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}/{cursor}"
        try:
            req = Request(url, headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"  bioRxiv API error: {e}")
            break

        messages = data.get("messages", [])
        collection = data.get("collection", [])
        total_found = data.get("total", 0)

        for item in collection:
            title = item.get("title", "").strip()
            abstract = item.get("abstract", "").strip()
            text = (title + " " + abstract).lower()

            matched = []
            for kw in BIOXIV_KEYWORDS:
                for term in kw.split(" AND "):
                    if term.strip().lower() in text:
                        matched.append(term.strip().lower())

            if matched:
                doi = item.get("doi", "")
                published = item.get("date", "")
                authors = item.get("authors", "")
                if isinstance(authors, str):
                    authors_list = [a.strip() for a in authors.split(";")]
                elif isinstance(authors, list):
                    authors_list = authors
                else:
                    authors_list = []

                papers.append({
                    "biorxiv_doi": doi,
                    "doi": doi,
                    "title": title,
                    "abstract": abstract[:2000],
                    "authors": "; ".join(authors_list[:8]),
                    "first_author": authors_list[0] if authors_list else "",
                    "year": int(published[:4]) if published else 0,
                    "pub_date": published,
                    "journal": "bioRxiv preprint",
                    "source": "biorxiv",
                    "source_strategy": "preprint",
                    "categories": ["General"],
                    "keyword_hits": matched,
                    "added_date": datetime.now().strftime("%Y-%m-%d"),
                    "ai_done": False,
                })

        # Check for more pages
        count = len(collection)
        if count == 0 or cursor + count >= total_found or len(papers) >= max_results:
            break
        cursor += count
        time.sleep(0.3)

    print(f"  bioRxiv: {len(papers)} papers matched (from {total_found} total)")
    return papers


def main():
    p = argparse.ArgumentParser(description="Fetch plant virus preprints from arXiv + bioRxiv")
    p.add_argument("--days", type=int, default=7, help="Days to look back")
    p.add_argument("--max-results", type=int, default=50, help="Max results per source")
    p.add_argument("--output", default=str(Path(__file__).parent / "data" / "preprints.json"))
    p.add_argument("--source", default="both", choices=["arxiv", "biorxiv", "both"])
    args = p.parse_args()

    all_papers = []

    if args.source in ("arxiv", "both"):
        ap = search_arxiv(PREPRINT_KEYWORDS, args.days, args.max_results)
        print(f"  arXiv: {len(ap)} papers")
        all_papers.extend(ap)

    if args.source in ("biorxiv", "both"):
        bp = search_biorxiv(BIOXIV_KEYWORDS, args.days, args.max_results)
        all_papers.extend(bp)

    # Dedup
    seen = set()
    deduped = []
    for pap in all_papers:
        k = pap.get("doi") or pap.get("title", "")[:80].lower()
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        deduped.append(pap)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {len(deduped)} unique preprints → {args.output}")


if __name__ == "__main__":
    main()
