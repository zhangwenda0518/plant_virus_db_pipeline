#!/usr/bin/env python3
"""Plant Virus Literature Fetcher — multi-query, categorized PubMed crawler."""

import json, os, sys, time, argparse, re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

BASE = Path(os.path.dirname(os.path.abspath(__file__)))

# Single source of truth: import categories + master DB path from config.py
sys.path.insert(0, str(BASE))
from config import QUERY_CATEGORIES, PAPERS_JSON

DEFAULT_OUT = PAPERS_JSON  # aligned with config.py master DB: data/papers.json

# Retry-exhausted query/batch failures are appended here (never a silent []).
FAILURES_TSV = BASE / "data" / "fetch_failures.tsv"

# ESearch will not return more ids than this per query term (retstart+retmax cap).
HARD_MAX_RESULTS = 10000


def _clean_cell(value, limit: int = 300) -> str:
    s = str(value if value is not None else "")
    for ch in ("\t", "\n", "\r"):
        s = s.replace(ch, " ")
    return s.strip()[:limit]


def _log_fetch_failure(stage: str, query: str, reason: str):
    """Append a fetch failure to data/fetch_failures.tsv instead of losing it."""
    path = Path(FAILURES_TSV)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            if new_file:
                f.write("time\tstage\tquery\treason\n")
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\t"
                    f"{_clean_cell(stage, 40)}\t{_clean_cell(query, 300)}\t"
                    f"{_clean_cell(reason, 300)}\n")
        print(f"    [WARN] fetch failure logged to {path.name}: "
              f"{stage} — {_clean_cell(reason, 120)}")
    except Exception as e:
        print(f"    [WARN] could not write {path}: {e}")


def _date_window_clause(mindate: str, maxdate: str) -> str:
    """(pdat OR edat) window written in PubMed query syntax.

    `pdat` (publication date) alone misses records that only entered PubMed during
    the window (ahead-of-print / late-indexed items), which is exactly the
    incremental-fetch gap. `edat` is the Entrez date (when the record was added).
    """
    return f"({mindate}:{maxdate}[pdat] OR {mindate}:{maxdate}[edat])"


def esearch(query, max_results=50, days=90, api_key="", start_date=None, end_date=None,
            retstart=0):
    """POST-based ESearch. If start_date/end_date given (YYYY-MM-DD), use them; else last `days`.

    The window is applied as a (pdat OR edat) term — see `_date_window_clause`.
    NOTE: datetime.now() uses the server's LOCAL timezone, so the window depends on
    the host clock/TZ (a UTC-hosted cron can lag/lead the local day by up to 24h;
    acceptable because the weekly run re-scans 7 days).
    """
    if start_date:
        mindate = start_date.replace("-", "/")
        # Default end date = server-local today (timezone-dependent, see docstring).
        maxdate = (end_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "/")
    else:
        # Server-local "now" (timezone-dependent, see docstring).
        mindate = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
        maxdate = datetime.now().strftime("%Y/%m/%d")
    term = f"({query}) AND {_date_window_clause(mindate, maxdate)}"
    params = {"db": "pubmed", "term": term, "retmax": max_results, "retstart": retstart,
              "retmode": "xml", "sort": "date"}
    if api_key:
        params["api_key"] = api_key
    req = Request("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                  data=urlencode(params).encode(),
                  headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"})
    last_err = "unknown error"
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                tree = ET.parse(resp)
                return [e.text for e in tree.findall(".//Id")], int(tree.findtext(".//Count") or 0)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < 2:
                time.sleep(2 ** attempt)
    _log_fetch_failure("esearch", query, last_err)
    return [], 0


def esearch_paged(query, max_results=50, days=90, api_key="", start_date=None,
                  end_date=None, hard_limit=HARD_MAX_RESULTS):
    """ESearch with retstart pagination; returns (pmids, total_count).

    A single ESearch returns at most `retmax` ids; without pagination everything
    past the first page was silently dropped (historical logs: 104 papers lost).
    Fetches up to min(count, hard_limit) ids, warning on the first page when
    count > retmax.
    """
    ids, count = esearch(query, max_results=max_results, days=days, api_key=api_key,
                         start_date=start_date, end_date=end_date, retstart=0)
    if count > max_results:
        print(f"    [page] {count} hits > retmax {max_results}; paging up to "
              f"{min(count, hard_limit)} (hard cap {hard_limit})")
    target = min(count, hard_limit) if count else len(ids)
    fetched = list(ids)
    seen = set(ids)
    start = len(ids)
    while len(fetched) < target and ids:
        page, _ = esearch(query, max_results=max_results, days=days, api_key=api_key,
                          start_date=start_date, end_date=end_date, retstart=start)
        if not page:
            break
        for pmid in page:
            if pmid not in seen:
                seen.add(pmid)
                fetched.append(pmid)
        start += len(page)
        time.sleep(0.5)  # NCBI rate limit between pages
    if len(fetched) < target:
        msg = f"pagination incomplete: {len(fetched)}/{target} ids (count={count})"
        print(f"    [WARN] {msg}")
        _log_fetch_failure("esearch_page", query, msg)
    return fetched[:target], count


def efetch(pmids, api_key="", context=""):
    """POST-based EFetch. Retry exhaustion is logged (not silently swallowed)."""
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    if api_key:
        params["api_key"] = api_key
    req = Request("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                  data=urlencode(params).encode(),
                  headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"})
    last_err = "unknown error"
    for attempt in range(3):
        try:
            with urlopen(req, timeout=60) as resp:
                tree = ET.parse(resp)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < 2:
                time.sleep(3 ** attempt)
            continue
        articles = []
        for art in tree.findall(".//PubmedArticle"):
            try:
                pmid = art.findtext(".//PMID", "")
                title = art.findtext(".//ArticleTitle", "")
                # Always collect ALL AbstractText elements (structured abstracts)
                abs_parts = []
                for at in art.findall(".//Abstract/AbstractText"):
                    label = at.get("Label", "")
                    txt = "".join(at.itertext()).strip()
                    if txt:
                        abs_parts.append(f"[{label}] {txt}" if label else txt)
                abstract = " ".join(abs_parts) if abs_parts else ""
                journal = art.findtext(".//Journal/Title", "")
                pub_date = _extract_date(art)
                year = pub_date.year if pub_date else 0
                authors = []
                for a in art.findall(".//Author"):
                    ln = a.findtext("LastName", "")
                    fn = a.findtext("ForeName", "")
                    if ln:
                        authors.append(f"{ln} {fn}".strip())
                author_str = "; ".join(authors[:5])
                if len(authors) > 5:
                    author_str += f"; ... (+{len(authors)-5})"
                doi = ""
                for aid in art.findall(".//ArticleId"):
                    if aid.get("IdType") == "doi":
                        doi = aid.text or ""
                        break
                articles.append({
                    "pmid": pmid, "title": title, "abstract": abstract,
                    "journal": journal, "year": year,
                    "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
                    "first_author": authors[0] if authors else "",
                    "authors": author_str, "doi": doi,
                })
            except Exception:
                continue
        return articles
    _log_fetch_failure("efetch", context or (",".join(pmids[:5]) + ("..." if len(pmids) > 5 else "")),
                       last_err)
    return []


def _extract_date(art):
    for tag in [".//PubDate", ".//ArticleDate"]:
        el = art.find(tag)
        if el is None:
            continue
        y = el.findtext("Year", "") or el.findtext("year", "")
        m = el.findtext("Month", "") or "1"
        d = el.findtext("Day", "") or "1"
        if y:
            try:
                if not m.isdigit():
                    m = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                         "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}.get(m.lower()[:3],1)
                return datetime(int(y), int(m), int(d))
            except:
                try:
                    return datetime(int(y), 1, 1)
                except:
                    pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--start-date", default=None, help="Start date YYYY-MM-DD (overrides --days)")
    p.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (defaults to today)")
    p.add_argument("--max-per-query", type=int, default=200)
    p.add_argument("--output", default=str(DEFAULT_OUT))
    p.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY", ""))
    p.add_argument("--categories", default="", help="Comma-separated categories, empty=all")
    args = p.parse_args()

    # Select categories
    cats = {k: v for k, v in QUERY_CATEGORIES.items()}
    if args.categories:
        selected = set(c.strip() for c in args.categories.split(","))
        cats = {k: v for k, v in cats.items() if k in selected}

    # Load existing data
    old_data = {"papers": [], "total": 0}
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            old_data = json.load(f)
    existing_pmids = {p["pmid"] for p in old_data.get("papers", [])}
    print(f"Existing: {len(existing_pmids)} papers")

    all_pmids_category = {}  # pmid -> category
    new_articles = []  # [(article, category), ...]
    total_found = 0

    for cat_name, queries in cats.items():
        print(f"\n{'='*50}")
        print(f"Category: {cat_name} ({len(queries)} queries)")
        cat_pmids = set()
        for q in queries:
            pmids, count = esearch_paged(q, max_results=args.max_per_query, days=args.days,
                                         api_key=args.api_key,
                                         start_date=args.start_date, end_date=args.end_date)
            for pmid in pmids:
                if pmid not in cat_pmids:
                    cat_pmids.add(pmid)
                    all_pmids_category[pmid] = cat_name
            print(f"  Query ({count} found, {len(pmids)} fetched): {q[:80]}...")
            time.sleep(0.5)  # NCBI rate limit

        # Filter out already-known PMIDs for this category
        new_pmids = [pmid for pmid in cat_pmids if pmid not in existing_pmids]
        print(f"  New PMIDs: {len(new_pmids)}")
        total_found += len(new_pmids)

        if new_pmids:
            for i in range(0, len(new_pmids), 100):
                batch = new_pmids[i:i+100]
                articles = efetch(batch, api_key=args.api_key,
                                  context=f"{cat_name}: {new_pmids[0]}..{new_pmids[-1]}")
                for art in articles:
                    art["categories"] = [all_pmids_category.get(art["pmid"], cat_name)]
                    new_articles.append(art)
                print(f"    Fetched {len(articles)} details")
                time.sleep(0.5)

    # Merge
    existing = {p["pmid"]: p for p in old_data.get("papers", [])}
    added = 0
    for art in new_articles:
        pid = art["pmid"]
        if pid in existing:
            # Update categories
            old_cats = set(existing[pid].get("categories", []))
            new_cats = set(art.get("categories", []))
            existing[pid]["categories"] = sorted(old_cats | new_cats)
        else:
            art["added_date"] = datetime.now().strftime("%Y-%m-%d")
            existing[pid] = art
            added += 1

    data = {
        "papers": sorted(existing.values(), key=lambda x: x.get("year", 0) or 0, reverse=True),
        "total": len(existing),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "categories": sorted(cats.keys()),
        "new_since_update": added,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"Saved: {len(existing)} papers total ({added} new)")
    print(f"Categories: {', '.join(cats.keys())}")
    print(f"Updated: {data['last_updated']}")


if __name__ == "__main__":
    main()
