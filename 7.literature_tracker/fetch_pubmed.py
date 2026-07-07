#!/usr/bin/env python3
"""Plant Virus Literature Fetcher — multi-query, categorized PubMed crawler."""

import json, os, time, argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = BASE / "papers.json"
CATEGORY_FILE = BASE / "query_categories.json"

# ── 分类检索词 ──
QUERY_CATEGORIES = {
    "General": [
        '"plant virus"[Title/Abstract] OR "plant viroid"[Title/Abstract] OR "phytovirus"[Title/Abstract]',
        '"plant RNA virus"[Title/Abstract] OR "plant DNA virus"[Title/Abstract]',
        '"viroid"[Title/Abstract]',
    ],
    "Gemini_Begomo": [
        '"Geminiviridae"[Title/Abstract] OR "begomovirus"[Title/Abstract] OR "mastrevirus"[Title/Abstract] OR "curtovirus"[Title/Abstract] OR "topocuvirus"[Title/Abstract]',
        '"tomato yellow leaf curl virus"[Title/Abstract] OR "Begomovirus coheni"[Title/Abstract]',
        '"cassava mosaic virus"[Title/Abstract] OR "maize streak virus"[Title/Abstract] OR "Mastrevirus maydis"[Title/Abstract]',
        '"cotton leaf curl virus"[Title/Abstract] OR "chilli leaf curl virus"[Title/Abstract] OR "okra yellow vein mosaic virus"[Title/Abstract]',
    ],
    "Potyviridae": [
        '"Potyviridae"[Title/Abstract] OR "potyvirus"[Title/Abstract] OR "ipomovirus"[Title/Abstract] OR "macluravirus"[Title/Abstract] OR "tritimovirus"[Title/Abstract] OR "bymovirus"[Title/Abstract] OR "rymovirus"[Title/Abstract]',
        '"potato virus Y"[Title/Abstract] OR "Potyvirus yituberosi"[Title/Abstract] OR "plum pox virus"[Title/Abstract] OR "Potyvirus plumpoxi"[Title/Abstract]',
        '"turnip mosaic virus"[Title/Abstract] OR "Potyvirus rapae"[Title/Abstract] OR "lettuce mosaic virus"[Title/Abstract]',
        '"papaya ringspot virus"[Title/Abstract] OR "Potyvirus papayanuli"[Title/Abstract] OR "watermelon mosaic virus"[Title/Abstract]',
    ],
    "Tobamo_Virga": [
        '"Virgaviridae"[Title/Abstract] OR "tobamovirus"[Title/Abstract] OR "furovirus"[Title/Abstract] OR "hordeivirus"[Title/Abstract] OR "pomovirus"[Title/Abstract]',
        '"tobacco mosaic virus"[Title/Abstract] OR "Tobamovirus tabaci"[Title/Abstract] OR "cucumber green mottle mosaic virus"[Title/Abstract]',
        '"pepino mosaic virus"[Title/Abstract] OR "Potexvirus pepini"[Title/Abstract]',
    ],
    "Tospo_Bunya": [
        '"Tospoviridae"[Title/Abstract] OR "tospovirus"[Title/Abstract] OR "Orthotospovirus"[Title/Abstract]',
        '"tomato spotted wilt virus"[Title/Abstract] OR "Orthotospovirus tomatomaculae"[Title/Abstract]',
        '"groundnut bud necrosis virus"[Title/Abstract]',
    ],
    "Luteo_Solemo": [
        '"Luteoviridae"[Title/Abstract] OR "Solemoviridae"[Title/Abstract] OR "luteovirus"[Title/Abstract] OR "polerovirus"[Title/Abstract]',
        '"barley yellow dwarf virus"[Title/Abstract] OR "Luteovirus hordei"[Title/Abstract] OR "potato leafroll virus"[Title/Abstract]',
    ],
    "Clostero_Beta": [
        '"Closteroviridae"[Title/Abstract] OR "Betaflexiviridae"[Title/Abstract] OR "closterovirus"[Title/Abstract] OR "crinivirus"[Title/Abstract]',
        '"citrus tristeza virus"[Title/Abstract] OR "Closterovirus tristezae"[Title/Abstract]',
    ],
    "Seco_Bromo_Tombus": [
        '"Secoviridae"[Title/Abstract] OR "Bromoviridae"[Title/Abstract] OR "Tombusviridae"[Title/Abstract]',
        '"nepovirus"[Title/Abstract] OR "comovirus"[Title/Abstract] OR "fabavirus"[Title/Abstract]',
        '"grapevine fanleaf virus"[Title/Abstract] OR "Nepovirus vitis"[Title/Abstract] OR "cucumber mosaic virus"[Title/Abstract] OR "Cucumovirus CMV"[Title/Abstract]',
        '"cowpea mosaic virus"[Title/Abstract] OR "Comovirus vignae"[Title/Abstract]',
    ],
    "Rhabdo_Reo_Fiji_Tenu": [
        '"Rhabdoviridae"[Title/Abstract] OR "Reoviridae"[Title/Abstract]',
        '"cytorhabdovirus"[Title/Abstract] OR "nucleorhabdovirus"[Title/Abstract] OR "fijivirus"[Title/Abstract] OR "oryzavirus"[Title/Abstract] OR "tenuivirus"[Title/Abstract]',
        '"rice stripe virus"[Title/Abstract] OR "Tenuivirus oryzae"[Title/Abstract] OR "rice dwarf virus"[Title/Abstract] OR "southern rice black-streaked dwarf virus"[Title/Abstract]',
    ],
    "Nanoviridae": [
        '"Nanoviridae"[Title/Abstract] OR "babuvirus"[Title/Abstract]',
        '"banana bunchy top virus"[Title/Abstract] OR "Babuvirus musae"[Title/Abstract]',
    ],
    "Caulimo_Badna_Tungro": [
        '"Caulimoviridae"[Title/Abstract] OR "caulimovirus"[Title/Abstract] OR "badnavirus"[Title/Abstract]',
        '"rice tungro bacilliform virus"[Title/Abstract] OR "rice tungro spherical virus"[Title/Abstract]',
    ],
    "Endorna_Parti_Amalga": [
        '"Endornaviridae"[Title/Abstract] OR "Partitiviridae"[Title/Abstract] OR "Amalgaviridae"[Title/Abstract]',
    ],
    "Viroid": [
        '"Pospiviroidae"[Title/Abstract] OR "Avsunviroidae"[Title/Abstract]',
        '"potato spindle tuber viroid"[Title/Abstract] OR "Pospiviroid fusituberis"[Title/Abstract]',
        '"citrus exocortis viroid"[Title/Abstract] OR "chrysanthemum stunt viroid"[Title/Abstract]',
        '"hop stunt viroid"[Title/Abstract] OR "Hostuviroid impedihumuli"[Title/Abstract]',
        '"avocado sunblotch viroid"[Title/Abstract] OR "peach latent mosaic viroid"[Title/Abstract] OR "Pelamoviroid latenspruni"[Title/Abstract]',
    ],
    "Methods_Resistance": [
        '"plant virus resistance"[Title/Abstract] OR "plant virus detection"[Title/Abstract]',
        '"plant virus CRISPR"[Title/Abstract] OR "plant virus RNAi"[Title/Abstract] OR "plant virus siRNA"[Title/Abstract]',
    ],
    "Methods_Omics": [
        '"plant virus genome"[Title/Abstract] OR "plant virus evolution"[Title/Abstract] OR "plant virus phylogeny"[Title/Abstract]',
        '"plant virus metagenomics"[Title/Abstract] OR "plant virus proteomics"[Title/Abstract] OR "plant virus NGS"[Title/Abstract]',
    ],
    "Transmission_Epi": [
        '"plant virus transmission"[Title/Abstract] OR "plant virus vector"[Title/Abstract] OR "plant virus epidemiology"[Title/Abstract]',
    ],
}


def esearch(query, max_results=50, days=90, api_key=""):
    """POST-based ESearch."""
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
            pmids, count = esearch(q, max_results=args.max_per_query, days=args.days, api_key=args.api_key)
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
