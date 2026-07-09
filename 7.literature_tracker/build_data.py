#!/usr/bin/env python3
"""Build web data from papers.json: merge, dedup, journal lookup, yearly splits."""
import json, os, re, sys, argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter

from config import (
    PAPERS_JSON, DAILY_DIR, WEB_DIR, WEB_DATA_DIR, TOP_JOURNALS, MID_JOURNALS,
    JOURNAL_INFO_TSV, QUERY_CATEGORIES,
)
from dedup import dedup_key, merge_paper, normalize_title, normalize_doi


def load_journal_info() -> dict:
    """Load journal_info.tsv into lookup dict."""
    journals = {}
    if not JOURNAL_INFO_TSV.exists():
        return journals
    with open(JOURNAL_INFO_TSV, encoding="utf-8", errors="replace") as f:
        # Skip header
        header = f.readline()
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 4:
                continue
            name = parts[0].strip().lower()
            journals[name] = {
                "if": parts[1].strip() if len(parts) > 1 else "",
                "jcr": parts[2].strip() if len(parts) > 2 else "",
                "cas": parts[3].strip() if len(parts) > 3 else "",
            }
    return journals


def journal_quality(journal_name: str, journals: dict) -> dict:
    """Get journal quality metadata."""
    if not journal_name:
        return {"journal_quality": "unknown"}
    name = journal_name.lower().strip()
    # Direct lookup
    if name in journals:
        return journals[name]
    # Fuzzy: check if any known journal is substring
    for known, info in journals.items():
        if known in name or name in known:
            return info
    # Check TOP8/MID7
    for top in TOP_JOURNALS:
        if top in name:
            return {"jcr": "Q1(Q2)", "journal_quality": "high"}
    for mid in MID_JOURNALS:
        if mid in name:
            return {"journal_quality": "medium"}
    return {"journal_quality": "other"}


def relevance_score(paper: dict, categories: dict) -> dict:
    """Compute relevance score via keyword matching."""
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()
    text = title + " " + abstract
    cats = paper.get("categories", [])

    hits = []
    score = 0.0
    for cat_name, queries in (categories or QUERY_CATEGORIES).items():
        for q in queries:
            q_lower = q.lower()
            # Extract key terms from query (remove OR/AND/operators)
            terms = []
            for part in re.split(r'\b(?:OR|AND|NOT|\[Title/Abstract\]|"[^"]*")\b', q_lower):
                term = part.strip().strip('"()')
                if term and len(term) > 4:
                    terms.append(term)
            for term in terms:
                if term in text:
                    hits.append(term)
                    if cat_name in (cats or []):
                        score += 2  # Category match bonus
                    else:
                        score += 1  # Term match

    level = "low"
    if score >= 10:
        level = "high"
    elif score >= 3:
        level = "medium"

    return {
        "relevance_score": min(score, 100),
        "relevance_level": level,
        "matched_topic": cats[0] if cats else "",
        "keyword_hits": sorted(set(hits))[:20],
    }


def build(from_daily: bool = True, journal_filter: bool = False) -> dict:
    """Merge all papers, compute stats, write web data files."""
    print("[1/4] Loading master database...")
    master = []
    if PAPERS_JSON.exists():
        with open(PAPERS_JSON, encoding="utf-8") as f:
            master = json.load(f).get("papers", [])
    print(f"  Existing: {len(master)} papers")

    # Merge daily files
    if from_daily and DAILY_DIR.exists():
        merged = 0
        existing_keys = set()
        for p in master:
            k = dedup_key(p)
            if k:
                existing_keys.add(k)

        key_to_paper = {}
        for p in master:
            k = dedup_key(p)
            if k:
                key_to_paper[k] = p

        for df in sorted(DAILY_DIR.glob("*.json")):
            with open(df, encoding="utf-8") as f:
                daily_papers = json.load(f)
                if isinstance(daily_papers, list):
                    papers = daily_papers
                else:
                    papers = daily_papers.get("papers", daily_papers.get("data", []))
            for pap in papers:
                k = dedup_key(pap)
                if not k:
                    continue
                if k in key_to_paper:
                    key_to_paper[k] = merge_paper(key_to_paper[k], pap)
                else:
                    key_to_paper[k] = pap
                    merged += 1
        master = list(key_to_paper.values())
        if merged:
            print(f"  Merged {merged} new from daily files")

    # Save master
    with open(PAPERS_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "papers": master,
            "total": len(master),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, f, ensure_ascii=False, indent=2)

    # Sort by year desc
    master.sort(key=lambda x: x.get("year", 0) or 0, reverse=True)

    # Journal lookup
    print("[2/4] Journal quality lookup...")
    journals = load_journal_info()
    for pap in master:
        jn = pap.get("journal", "")
        quality = journal_quality(jn, journals)
        pap.update(quality)

    # Relevance scoring
    print("[3/4] Computing relevance scores...")
    for pap in master:
        score_info = relevance_score(pap, QUERY_CATEGORIES)
        pap.update(score_info)

    # Stats
    years = defaultdict(int)
    cat_counts = defaultdict(int)
    journal_counts = defaultdict(int)
    for pap in master:
        y = pap.get("year", 0)
        if y:
            years[str(y)] += 1
        for cat in pap.get("categories", []):
            cat_counts[cat] += 1
        j = pap.get("journal", "")
        if j:
            journal_counts[j] += 1

    stats = {
        "total": len(master),
        "by_year": {k: years[k] for k in sorted(years.keys())},
        "by_category": dict(Counter(cat_counts).most_common(20)),
        "top_journals": Counter(journal_counts).most_common(30),
        "ai_summarized": sum(1 for p in master if p.get("ai_done")),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Write output
    print("[4/4] Writing web data...")
    os.makedirs(WEB_DATA_DIR, exist_ok=True)

    # Frontend-optimized fields
    web_fields = [
        "pmid", "doi", "title", "abstract", "journal", "year", "pub_date",
        "first_author", "authors", "categories", "source", "source_strategy",
        "summary_zh", "innovation", "limitation", "study_object", "disease",
        "sample_size", "method_zh", "contributions", "ai_done",
        "relevance_score", "relevance_level", "matched_topic",
        "journal_quality", "journal_jcr", "added_date", "keyword_hits",
    ]

    def trim_for_web(p):
        return {k: p.get(k, "") for k in web_fields if k in p or k in web_fields}

    # Master web data
    web_data = [trim_for_web(p) for p in master]
    with open(WEB_DATA_DIR / "data.json", "w", encoding="utf-8") as f:
        json.dump(web_data, f, ensure_ascii=False, indent=2)

    # Yearly splits
    by_year = defaultdict(list)
    for p in master:
        y = p.get("year", 0)
        if y:
            by_year[str(y)].append(trim_for_web(p))

    for year, papers in sorted(by_year.items()):
        with open(WEB_DATA_DIR / f"{year}.json", "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)

    # Year index
    year_index = [{"year": y, "count": len(pps), "file": f"{y}.json"}
                  for y, pps in sorted(by_year.items())]
    with open(WEB_DATA_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(year_index, f, ensure_ascii=False, indent=2)

    # Stats
    with open(WEB_DATA_DIR / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # Trend milestones — auto-detect New_Virus + first-report + high-relevance papers
    milestones = []
    for p in master:
        cats = p.get("categories", [])
        title = (p.get("title") or "")
        is_new = "New_Virus" in cats
        is_first = "first report" in title.lower() or "novel" in title.lower()
        is_high = p.get("relevance_level") == "high" and p.get("journal_quality") == "high"
        if is_new or (is_first and is_high):
            milestones.append({
                "date": p.get("pub_date", "") or (str(p.get("year", "")) + "-01-01"),
                "year": p.get("year", 0),
                "title": title,
                "category": cats[0] if cats else "",
                "pmid": p.get("pmid", ""),
                "doi": p.get("doi", ""),
                "journal": p.get("journal", ""),
                "note": p.get("summary_zh", "") if p.get("ai_done") else "",
                "type": "new_virus" if is_new else "milestone",
            })
    milestones.sort(key=lambda x: x.get("date", ""), reverse=True)
    with open(WEB_DATA_DIR / "trend_milestones.json", "w", encoding="utf-8") as f:
        json.dump(milestones[:200], f, ensure_ascii=False, indent=2)

    print(f"\n  Master: {len(master)} papers total")
    print(f"  AI summarized: {stats['ai_summarized']}")
    print(f"  Milestones: {len(milestones)}")
    if years:
        print(f"  Years: {len(years)} ({min(years.keys())}-{max(years.keys())})")
    print(f"  Files written to {WEB_DATA_DIR}")
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-daily", action="store_true", help="Skip merging daily files")
    p.add_argument("--journal-filter", action="store_true", help="Filter low-quality journals")
    args = p.parse_args()
    build(from_daily=not args.no_daily, journal_filter=args.journal_filter)


if __name__ == "__main__":
    main()
