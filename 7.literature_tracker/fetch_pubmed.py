#!/usr/bin/env python3
"""Plant Virus Literature Fetcher — multi-query, categorized PubMed crawler."""

import json, os, sys, time, argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = BASE / "papers.json"

# Single source of truth: import categories from config.py
sys.path.insert(0, str(BASE))
from config import QUERY_CATEGORIES


def esearch(query, max_results=50, days=90, api_key="", start_date=None, end_date=None):
    """POST-based ESearch. If start_date/end_date given (YYYY-MM-DD), use them; else last `days`."""
    if start_date:
        mindate = start_date.replace("-", "/")
        maxdate = (end_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "/")
    else:
        mindate = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
        maxdate = datetime.now().strftime("%Y/%m/%d")
    params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "xml",
              "sort": "date", "mindate": mindate, "maxdate": maxdate, "datetype": "pdat"}
    if api_key:
        params["api_key"] = api_key
    req = Request("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                  data=urlencode(params).encode(),
                  headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                tree = ET.parse(resp)
                return [e.text for e in tree.findall(".//Id")], int(tree.findtext(".//Count") or 0)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return [], 0


def efetch(pmids, api_key=""):
    """POST-based EFetch."""
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", "rettype": "abstract"}
    if api_key:
        params["api_key"] = api_key
    req = Request("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                  data=urlencode(params).encode(),
                  headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=60) as resp:
                tree = ET.parse(resp)
        except Exception as e:
            if attempt < 2:
                time.sleep(3 ** attempt)
            continue
        articles = []
        for art in tree.findall(".//PubmedArticle"):
            try:
                pmid = art.findtext(".//PMID", "")
                title = art.findtext(".//ArticleTitle", "")
                abstract = art.findtext(".//Abstract/AbstractText", "")
                if not abstract:
                    texts = art.findall(".//Abstract/AbstractText")
                    abstract = " ".join(t.text or "" for t in texts if t.text)
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
                    "pmid": pmid, "title": title, "abstract": abstract[:2000],
                    "journal": journal, "year": year,
                    "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
                    "first_author": authors[0] if authors else "",
                    "authors": author_str, "doi": doi,
                })
            except Exception:
                continue
        return articles
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
    p.add_argument("--max-per-query", type=int, default=30)
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
            pmids, count = esearch(q, max_results=args.max_per_query, days=args.days,
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
                articles = efetch(batch, api_key=args.api_key)
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
