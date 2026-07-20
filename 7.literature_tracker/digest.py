#!/usr/bin/env python3
"""Build weekly and monthly literature digests with AI-generated narrative summaries."""
import json, os, sys, argparse
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PAPERS_JSON, WEB_DATA_DIR
from summarize_papers import summarize_digest
import os as _os

WEEKLY_DIR = WEB_DATA_DIR / "weekly"
MONTHLY_DIR = WEB_DATA_DIR / "monthly"


def load_master() -> list:
    if not PAPERS_JSON.exists():
        return []
    with open(PAPERS_JSON, encoding="utf-8") as f:
        return json.load(f).get("papers", [])


def _paper_date(p: dict) -> date:
    """Best-effort publication date."""
    pd = p.get("pub_date", "") or ""
    if len(pd) >= 10:
        try:
            return datetime.strptime(pd[:10], "%Y-%m-%d").date()
        except Exception:
            pass
    y = p.get("year", 0)
    if y:
        try:
            return date(int(y), 1, 1)
        except Exception:
            pass
    return None


def _top_papers(papers: list, n: int = 10) -> list:
    """Pick top papers by relevance level then journal quality."""
    def score(p):
        lvl = {"high": 3, "medium": 2, "low": 1}.get(p.get("relevance_level", "low"), 1)
        jq = {"high": 3, "medium": 2, "other": 1}.get(p.get("journal_quality", "other"), 1)
        return lvl * 10 + jq
    ranked = sorted(papers, key=score, reverse=True)[:n]
    fields = ["pmid", "doi", "title", "abstract", "journal", "year", "pub_date",
              "authors", "first_author", "categories",
              "virus_name", "taxonomy", "host_plant", "location", "results",
              "relevance_level", "journal_quality", "source"]
    return [{k: p.get(k, "") for k in fields} for p in ranked]


def build_weekly(weeks_back: int = 8, use_ai: bool = True, since: str = "2024-01-01"):
    """Build weekly digests. Only weeks on/after `since` (default 2024-01-01) get weekly digests.

    weeks_back: for incremental runs, limit to recent N weeks (0 = all weeks since `since`).
    """
    os.makedirs(WEEKLY_DIR, exist_ok=True)
    papers = load_master()
    print(f"Loaded {len(papers)} papers (weekly cutoff: {since})")

    since_date = datetime.strptime(since, "%Y-%m-%d").date()

    # Group by ISO week of publication date (fall back to added_date)
    by_week = defaultdict(list)
    for p in papers:
        d = _paper_date(p)
        if not d:
            ad = p.get("added_date", "")
            if len(ad) >= 10:
                try:
                    d = datetime.strptime(ad[:10], "%Y-%m-%d").date()
                except Exception:
                    d = None
        if d and d >= since_date:
            iso = d.isocalendar()
            by_week[f"{iso[0]}-W{iso[1]:02d}"].append(p)

    # Select weeks to process
    all_weeks = sorted(by_week.keys(), reverse=True)
    if weeks_back and weeks_back > 0:
        # Limit to recent N weeks (for incremental weekly runs)
        today = date.today()
        recent = set()
        for i in range(weeks_back):
            iso = (today - timedelta(weeks=i)).isocalendar()
            recent.add(f"{iso[0]}-W{iso[1]:02d}")
        target_weeks = [w for w in all_weeks if w in recent]
    else:
        target_weeks = all_weeks  # all weeks since cutoff (historical backfill)

    index = []
    for wk in target_weeks:
        wp = by_week.get(wk, [])
        if not wp:
            continue
        year, wknum = int(wk[:4]), int(wk[6:])
        wk_start = date.fromisocalendar(year, wknum, 1)
        wk_end = date.fromisocalendar(year, wknum, 7)

        cat_counts = Counter()
        for p in wp:
            for c in p.get("categories", []):
                cat_counts[c] += 1

        ai_summary = ""
        if use_ai:
            print(f"  {wk}: {len(wp)} papers, generating AI digest...")
            ai_summary = summarize_digest(wp, period="周",
                model=_os.environ.get("LLM_MODEL","gpt-4o-mini"),
                base_url=_os.environ.get("LLM_BASE_URL",""),
                api_key=_os.environ.get("LLM_API_KEY",""))

        digest = {
            "week": wk,
            "start": wk_start.strftime("%Y-%m-%d"),
            "end": wk_end.strftime("%Y-%m-%d"),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_new": len(wp),
            "by_category": dict(cat_counts.most_common()),
            "ai_summary": ai_summary,
            "top_papers": _top_papers(wp, 10),
        }
        with open(WEEKLY_DIR / f"{wk}.json", "w", encoding="utf-8") as f:
            json.dump(digest, f, ensure_ascii=False, indent=2)
        index.append({"week": wk, "start": digest["start"], "end": digest["end"],
                      "count": len(wp), "file": f"{wk}.json"})

    with open(WEEKLY_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"Weekly: {len(index)} digests written to {WEEKLY_DIR}")


def build_monthly(start: str = "2020-01", end: str = None, use_ai: bool = True):
    """Build monthly digests for each month in range that has papers."""
    os.makedirs(MONTHLY_DIR, exist_ok=True)
    papers = load_master()
    print(f"Loaded {len(papers)} papers")

    # Group by publication month
    by_month = defaultdict(list)
    for p in papers:
        d = _paper_date(p)
        if d:
            by_month[f"{d.year}-{d.month:02d}"].append(p)

    if end is None:
        end = datetime.now().strftime("%Y-%m")

    index = []
    # Iterate all months in range
    y0, m0 = int(start[:4]), int(start[5:7])
    y1, m1 = int(end[:4]), int(end[5:7])
    cur_y, cur_m = y0, m0
    while (cur_y, cur_m) <= (y1, m1):
        mkey = f"{cur_y}-{cur_m:02d}"
        mp = by_month.get(mkey, [])
        if mp:
            cat_counts = Counter()
            for p in mp:
                for c in p.get("categories", []):
                    cat_counts[c] += 1

            ai_summary = ""
            if use_ai:
                print(f"  {mkey}: {len(mp)} papers, generating AI digest...")
                ai_summary = summarize_digest(mp, period="月",
                    model=_os.environ.get("LLM_MODEL","gpt-4o-mini"),
                    base_url=_os.environ.get("LLM_BASE_URL",""),
                    api_key=_os.environ.get("LLM_API_KEY",""))

            digest = {
                "month": mkey,
                "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total": len(mp),
                "by_category": dict(cat_counts.most_common()),
                "ai_summary": ai_summary,
                "top_papers": _top_papers(mp, 12),
            }
            with open(MONTHLY_DIR / f"{mkey}.json", "w", encoding="utf-8") as f:
                json.dump(digest, f, ensure_ascii=False, indent=2)
            index.append({"month": mkey, "count": len(mp), "file": f"{mkey}.json"})

        # Advance month
        if cur_m == 12:
            cur_y, cur_m = cur_y + 1, 1
        else:
            cur_m += 1

    with open(MONTHLY_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"Monthly: {len(index)} digests written to {MONTHLY_DIR}")


def main():
    p = argparse.ArgumentParser(description="Build literature digests")
    p.add_argument("mode", choices=["weekly", "monthly"], help="Digest type")
    p.add_argument("--weeks-back", type=int, default=8, help="0 = all weeks since --since (backfill)")
    p.add_argument("--since", default="2024-01-01", help="Weekly cutoff (no weekly before this)")
    p.add_argument("--start", default="2020-01", help="Monthly start YYYY-MM")
    p.add_argument("--end", default=None, help="Monthly end YYYY-MM")
    p.add_argument("--no-ai", action="store_true", help="Skip AI narrative summary")
    args = p.parse_args()

    if args.mode == "weekly":
        build_weekly(args.weeks_back, use_ai=not args.no_ai, since=args.since)
    else:
        build_monthly(args.start, args.end, use_ai=not args.no_ai)


if __name__ == "__main__":
    main()
