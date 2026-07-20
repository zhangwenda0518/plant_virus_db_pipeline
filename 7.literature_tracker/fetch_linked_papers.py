#!/usr/bin/env python3
"""Fetch PubMed papers linked to Plant Virus accessions via NCBI ELink.

Instead of keyword search, this script:
1. Reads all accessions from Plant_Virus_Full.Info.tsv
2. Uses NCBI ELink to find PMIDs linked to each accession
3. Fetches paper details via EFetch
4. Deduplicates and stores with category (virus family/species) metadata.

Much more precise than keyword search — only papers that actually
studied/sampled specific plant virus sequences.
"""

import json, os, time, argparse, re, random
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
from collections import defaultdict

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = BASE / "papers.json"
DEFAULT_TSV = "/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Full.Info.tsv"


def load_accessions(tsv_path, max_acc=5000):
    """Load unique accessions from Plant_Virus_Full.Info.tsv, prioritize diverse species."""
    print(f"Reading accessions from {tsv_path}...")
    accs = []  # (accession, species, family)
    seen_species = set()

    with open(tsv_path, encoding="utf-8", errors="replace") as f:
        header = f.readline().strip().split("\t")
        # Find column indices
        col_map = {h: i for i, h in enumerate(header)}
        acc_col = col_map.get("Accession", 0)
        sp_col = col_map.get("Species_ICTV", col_map.get("Species_NCBI", 1))
        fam_col = col_map.get("Family", 2)

        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) <= max(acc_col, sp_col):
                continue
            acc = parts[acc_col].strip()
            sp = parts[sp_col].strip() if sp_col < len(parts) else ""
            fam = parts[fam_col].strip() if fam_col < len(parts) else ""

            # Collect first accession per species for diversity
            if acc and sp and sp not in seen_species:
                seen_species.add(sp)
                accs.append((acc, sp, fam))
            elif acc and len(accs) < max_acc:
                accs.append((acc, sp, fam))

            if len(accs) >= max_acc:
                break

    print(f"  {len(accs)} accessions from {len(seen_species)} species")
    return accs


def elink_batch(accessions, api_key=""):
    """Use ELink to find PubMed IDs linked to accessions (batch mode)."""
    if not accessions:
        return {}

    # Strip version numbers (.1, .2) from accessions
    clean_accs = [a.split(".")[0] for a in accessions]
    ids_str = ",".join(clean_accs)
    params = {
        "dbfrom": "nuccore",
        "db": "pubmed",
        "id": ids_str,
        "retmode": "xml",
    }
    if api_key:
        params["api_key"] = api_key

    req = Request(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi",
        data=urlencode(params).encode(),
        headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"},
    )

    for attempt in range(3):
        try:
            with urlopen(req, timeout=60) as resp:
                tree = ET.parse(resp)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            continue

        # Parse LinkSetDb results
        acc_pmids = defaultdict(set)
        for linkset in tree.findall(".//LinkSet"):
            acc = linkset.findtext("IdList/Id", "")
            if not acc:
                continue
            for link in linkset.findall(".//LinkSetDb/Link/Id"):
                pmid = link.text
                if pmid and pmid != "0":
                    acc_pmids[acc].add(pmid)

        return acc_pmids

    return {}


def efetch(pmids, api_key=""):
    """Fetch article details via EFetch."""
    if not pmids:
        return []
    pmids = list(pmids)[:200]

    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
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
        except Exception:
            if attempt < 2:
                time.sleep(3 ** attempt)
            continue

        articles = []
        for art in tree.findall(".//PubmedArticle"):
            try:
                pmid = art.findtext(".//PMID", "")
                title = art.findtext(".//ArticleTitle", "")
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
    p.add_argument("--tsv", default=DEFAULT_TSV, help="Path to Plant_Virus_Full.Info.tsv")
    p.add_argument("--max-acc", type=int, default=3000, help="Max accessions to query")
    p.add_argument("--output", default=str(DEFAULT_OUT))
    p.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY", ""))
    p.add_argument("--batch-size", type=int, default=150, help="ELink batch size")
    args = p.parse_args()

    # Load accessions
    accs = load_accessions(args.tsv, args.max_acc)
    total = len(accs)

    # Load existing papers
    old_data = {"papers": [], "total": 0}
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            old_data = json.load(f)
    existing_pmids = {p["pmid"] for p in old_data.get("papers", [])}
    print(f"Existing: {len(existing_pmids)} papers")

    # Build family -> accessions mapping
    fam_accs = defaultdict(list)
    for acc, sp, fam in accs:
        if fam:
            fam_accs[fam].append(acc)
        else:
            fam_accs["Unknown"].append(acc)

    # Process by family
    all_pmids = {}  # pmid -> set of categories
    new_pmids_total = 0

    for fam, family_accs in sorted(fam_accs.items(), key=lambda x: -len(x[1])):
        # Skip tiny families
        sample = family_accs[:50]  # Sample up to 50 accessions per family
        print(f"\nFamily: {fam} ({len(family_accs)} accs, sampling {len(sample)})")

        # Query in batches
        fam_pmids = set()
        for i in range(0, len(sample), args.batch_size):
            batch = sample[i:i+args.batch_size]
            acc_pmids = elink_batch(batch, api_key=args.api_key)
            for pids in acc_pmids.values():
                fam_pmids.update(pids)
            print(f"  Batch {i//args.batch_size+1}: {len(acc_pmids)} accs linked, {len(fam_pmids)} total PMIDs")
            time.sleep(0.5)

        # Track new PMIDs
        new_in_fam = fam_pmids - existing_pmids
        new_pmids_total += len(new_in_fam)
        for pmid in fam_pmids:
            if pmid not in all_pmids:
                all_pmids[pmid] = set()
            all_pmids[pmid].add(fam)

        print(f"  New PMIDs: {len(new_in_fam)}")
        time.sleep(0.3)

    print(f"\n{'='*50}")
    print(f"Total unique PMIDs linked: {len(all_pmids)}")
    print(f"New PMIDs to fetch: {new_pmids_total}")

    # Fetch new papers in batches
    new_pmids_list = [p for p in all_pmids if p not in existing_pmids]
    new_articles = []

    for i in range(0, len(new_pmids_list), 100):
        batch = new_pmids_list[i:i+100]
        articles = efetch(batch, api_key=args.api_key)
        for art in articles:
            art["categories"] = sorted(all_pmids.get(art["pmid"], ["Unknown"]))
            art["source"] = "elink"
            new_articles.append(art)
        print(f"  Fetched {len(articles)} / {len(batch)} batch")
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
        "source": "NCBI ELink (nucleotide → pubmed)",
        "new_since_update": added,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved: {len(existing)} papers total ({added} new)")
    print(f"Updated: {data['last_updated']}")


if __name__ == "__main__":
    main()
