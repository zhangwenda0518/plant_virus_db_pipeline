#!/usr/bin/env python3
"""Fetch PubMed papers for each plant virus species from Plant_Virus_Full.Info.tsv.

Strategy: Extract unique Species_ICTV names, search PubMed with each species name.
This is more targeted than generic keywords but more comprehensive than ELink.
Saves category = virus family for each paper.
"""

import json, os, time, argparse
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote
from xml.etree import ElementTree as ET
from collections import defaultdict
import random

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = BASE / "papers.json"
DEFAULT_TSV = "/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Full.Info.tsv"


def load_species(tsv_path, max_species=500):
    """Extract unique species names with family, prioritize by record count."""
    species_family = defaultdict(int)
    species_count = defaultdict(int)

    with open(tsv_path, encoding="utf-8", errors="replace") as f:
        header = f.readline().strip().split("\t")
        col_map = {h: i for i, h in enumerate(header)}
        sp_col = col_map.get("Species_ICTV", col_map.get("Species_NCBI", 1))
        fam_col = col_map.get("Family", 2)

        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("\t")
            if sp_col >= len(parts):
                continue
            sp = parts[sp_col].strip()
            fam = parts[fam_col].strip() if fam_col < len(parts) else ""
            if sp:
                species_count[sp] += 1
                if fam:
                    species_family[sp] = fam

    # Sort by record count, pick top species
    sorted_species = sorted(species_count.items(), key=lambda x: -x[1])
    result = [(sp, species_family.get(sp, ""), cnt)
              for sp, cnt in sorted_species[:max_species]]

    print(f"  {len(result)} species selected (from {len(sorted_species)} total)")
    return result


def esearch(query, max_results=10, api_key=""):
    """Quick search for a specific species."""
    params = {
        "db": "pubmed", "term": query, "retmax": max_results,
        "retmode": "xml", "sort": "date",
    }
    if api_key:
        params["api_key"] = api_key
    req = Request(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        data=urlencode(params).encode(),
        headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"},
    )
    try:
        with urlopen(req, timeout=15) as resp:
            tree = ET.parse(resp)
            return [e.text for e in tree.findall(".//Id")]
    except:
        return []


def efetch(pmids, api_key=""):
    """Fetch article details."""
    if not pmids:
        return []
    pmids = list(pmids)[:200]
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", "rettype": "abstract"}
    if api_key:
        params["api_key"] = api_key
    req = Request(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        data=urlencode(params).encode(),
        headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"},
    )
    for attempt in range(3):
        try:
            with urlopen(req, timeout=60) as resp:
                tree = ET.parse(resp)
        except:
            if attempt < 2:
                time.sleep(2 ** attempt)
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
            except:
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
    p.add_argument("--tsv", default=DEFAULT_TSV)
    p.add_argument("--max-species", type=int, default=300)
    p.add_argument("--max-per-species", type=int, default=5)
    p.add_argument("--output", default=str(DEFAULT_OUT))
    p.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY", ""))
    args = p.parse_args()

    species_list = load_species(args.tsv, args.max_species)
    total_species = len(species_list)

    # Load existing
    old_data = {"papers": [], "total": 0}
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            old_data = json.load(f)
    existing_pmids = {p["pmid"] for p in old_data.get("papers", [])}
    print(f"Existing: {len(existing_pmids)} papers")

    # Group species by family
    fam_species = defaultdict(list)
    for sp, fam, cnt in species_list:
        fam_species[fam or "Unknown"].append((sp, cnt))

    all_new_pmids = {}  # pmid -> {categories}
    species_processed = 0

    for fam in sorted(fam_species.keys(), key=lambda f: -len(fam_species[f])):
        spp = fam_species[fam]
        print(f"\nFamily: {fam} ({len(spp)} species)")

        for sp, cnt in spp[:50]:  # Max 50 per family
            species_processed += 1
            # Search with exact phrase
            query = f'"{sp}"[Title/Abstract]'
            pmids = esearch(query, max_results=args.max_per_species, api_key=args.api_key)
            if not pmids:
                query = f'"{sp}"[All Fields]'
                pmids = esearch(query, max_results=args.max_per_species, api_key=args.api_key)

            for pmid in pmids:
                if pmid not in all_new_pmids:
                    all_new_pmids[pmid] = set()
                all_new_pmids[pmid].add(fam)

            if species_processed % 50 == 0:
                print(f"  Processed {species_processed}/{total_species} species, "
                      f"{len(all_new_pmids)} unique PMIDs found")

            if species_processed % 20 == 0:
                time.sleep(0.3)  # Rate limit

    new_pmids = [p for p in all_new_pmids if p not in existing_pmids]
    print(f"\n{'='*50}")
    print(f"Total unique PMIDs: {len(all_new_pmids)}, New: {len(new_pmids)}")

    # Fetch new papers
    new_articles = []
    for i in range(0, len(new_pmids), 100):
        batch = new_pmids[i:i+100]
        articles = efetch(batch, api_key=args.api_key)
        for art in articles:
            art["categories"] = sorted(all_new_pmids.get(art["pmid"], ["Unknown"]))
        new_articles.extend(articles)
        print(f"  Fetched {len(articles)} / {len(batch)}")
        time.sleep(0.5)

    # Merge
    existing = {p["pmid"]: p for p in old_data.get("papers", [])}
    added = 0
    for art in new_articles:
        pid = art["pmid"]
        if pid in existing:
            old_cats = set(existing[pid].get("categories", []))
            existing[pid]["categories"] = sorted(old_cats | set(art.get("categories", [])))
        else:
            art["added_date"] = datetime.now().strftime("%Y-%m-%d")
            existing[pid] = art
            added += 1

    data = {
        "papers": sorted(existing.values(), key=lambda x: x.get("year", 0) or 0, reverse=True),
        "total": len(existing),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Species-level PubMed search from Plant_Virus_Full.Info.tsv",
        "new_since_update": added,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved: {len(existing)} papers total ({added} new)")
    print(f"Updated: {data['last_updated']}")


if __name__ == "__main__":
    main()
