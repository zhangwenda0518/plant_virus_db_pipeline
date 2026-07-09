#!/usr/bin/env python3
"""
Plant Virus Literature Tracker — Unified CLI
============================================
Commands:
  fetch       Fetch new papers from all sources
  summarize   Generate AI summaries for pending papers
  build       Merge and build web data files
  auto        Fetch + summarize + build (weekly workflow)
  stats       Print summary statistics
  historical  Batch fetch/summarize for historical period (2020-2026)
"""
import argparse, json, os, sys, time, subprocess
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Ensure we can import from this directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    PAPERS_JSON, DAILY_DIR, WEB_DATA_DIR, PUBMED_MAX_PER_QUERY,
    PUBMED_DAYS_DEFAULT, NCBI_API_KEY,
)
from dedup import dedup_key, merge_paper
from build_data import build


# ── Fetch ──

def cmd_fetch(args):
    """Fetch papers from all or specific sources."""
    days = args.days or PUBMED_DAYS_DEFAULT
    sources = args.source.split(",") if args.source else ["keyword"]

    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(DAILY_DIR, exist_ok=True)
    all_new = []

    for src in sources:
        print(f"\n{'='*50}")
        print(f"Fetching: {src} (last {days} days)")
        print(f"{'='*50}")

        if src == "keyword":
            papers = _run_fetch_pubmed(days)
        elif src == "elink":
            papers = _run_fetch_linked()
        elif src == "species":
            papers = _run_fetch_species()
        elif src == "preprint":
            papers = _run_fetch_preprints(days)
        else:
            print(f"  Unknown source: {src}")
            continue

        all_new.extend(papers)

    # Deduplicate across sources
    seen = {}
    deduped = []
    for pap in all_new:
        k = dedup_key(pap)
        if not k:
            deduped.append(pap)
        elif k in seen:
            seen[k] = merge_paper(seen[k], pap)
        else:
            seen[k] = pap
    deduped = list(seen.values()) + [p for p in all_new if not dedup_key(p)]

    # Save daily file
    daily_path = DAILY_DIR / f"{today}.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Fetched {len(all_new)} papers ({len(deduped)} after dedup)")
    print(f"  Saved: {daily_path}")


def _run_fetch_pubmed(days: int) -> list:
    """Run the keyword-based PubMed fetch."""
    script = Path(__file__).parent / "fetch_pubmed.py"
    out = Path(__file__).parent / "data" / "_tmp_keyword.json"
    cmd = [
        sys.executable, str(script),
        "--days", str(days),
        "--max-per-query", str(PUBMED_MAX_PER_QUERY),
        "--output", str(out),
    ]
    if NCBI_API_KEY:
        cmd.extend(["--api-key", NCBI_API_KEY])
    subprocess.run(cmd, check=False)
    if out.exists():
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        os.remove(out)
        return data.get("papers", [])
    return []


def _run_fetch_linked() -> list:
    """Run the ELink-based fetch."""
    script = Path(__file__).parent / "fetch_linked_papers.py"
    out = Path(__file__).parent / "data" / "_tmp_elink.json"
    cmd = [sys.executable, str(script), "--output", str(out)]
    if NCBI_API_KEY:
        cmd.extend(["--api-key", NCBI_API_KEY])
    subprocess.run(cmd, check=False)
    if out.exists():
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        os.remove(out)
        return data.get("papers", [])
    return []


def _run_fetch_species() -> list:
    """Run the species-name-based fetch."""
    script = Path(__file__).parent / "fetch_species_papers.py"
    out = Path(__file__).parent / "data" / "_tmp_species.json"
    cmd = [sys.executable, str(script), "--output", str(out)]
    if NCBI_API_KEY:
        cmd.extend(["--api-key", NCBI_API_KEY])
    subprocess.run(cmd, check=False)
    if out.exists():
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        os.remove(out)
        return data.get("papers", [])
    return []


def _run_fetch_preprints(days: int) -> list:
    """Fetch from arXiv + bioRxiv."""
    script = Path(__file__).parent / "fetch_preprints.py"
    if not script.exists():
        print("  fetch_preprints.py not yet implemented — skipping")
        return []
    out = Path(__file__).parent / "data" / "_tmp_preprint.json"
    cmd = [sys.executable, str(script), "--days", str(days), "--output", str(out)]
    subprocess.run(cmd, check=False)
    if out.exists():
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        os.remove(out)
        return data if isinstance(data, list) else data.get("papers", [])
    return []


# ── Summarize ──

def cmd_summarize(args):
    """Generate AI summaries."""
    from summarize_papers import summarize_papers
    out_path = args.output or str(PAPERS_JSON)

    if not args.input and not Path(args.input).exists() if args.input else not PAPERS_JSON.exists():
        print("No papers.json found. Run 'fetch' first.")
        return

    in_path = args.input or str(PAPERS_JSON)
    with open(in_path, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])
    if args.pmids:
        pmid_set = set(args.pmids)
        papers = [p for p in papers if p.get("pmid") in pmid_set]
    if args.max_papers:
        papers = sorted(papers, key=lambda x: x.get("year", 0) or 0, reverse=True)
        papers = papers[:args.max_papers]

    summarize_papers(papers, force=args.force)
    data["papers"] = papers

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    done = sum(1 for p in papers if p.get("ai_done"))
    print(f"Done: {done}/{len(papers)} summarized → {out_path}")


# ── Build ──

def cmd_build(args):
    """Build web data files."""
    build(from_daily=not args.no_daily, journal_filter=args.journal_filter)


# ── Auto ──

def cmd_auto(args):
    """Fetch + summarize + build."""
    days = args.days or PUBMED_DAYS_DEFAULT
    print(f"=== AUTO: fetch({days}d) + summarize + build ===\n")

    cmd_fetch(args)
    cmd_build(args)

    # Summarize newly added papers
    if PAPERS_JSON.exists():
        with open(PAPERS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        pending = [p for p in data.get("papers", [])
                   if not p.get("ai_done") and p.get("added_date")]
        if pending:
            print(f"\nSummarizing {len(pending)} new papers...")
            args.max_papers = len(pending)
            cmd_summarize(args)
            cmd_build(args)

    print(f"\nDone.")


# ── Stats ──

def cmd_stats(args):
    """Print statistics."""
    if not PAPERS_JSON.exists():
        print("No papers.json — run 'fetch' first.")
        return

    with open(PAPERS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])
    years = defaultdict(int)
    cats = defaultdict(int)
    for p in papers:
        y = p.get("year", 0)
        if y: years[y] += 1
        for c in p.get("categories", []):
            cats[c] += 1

    print(f"Total papers: {len(papers)}")
    print(f"AI summarized: {sum(1 for p in papers if p.get('ai_done'))}")
    print(f"Years: {min(years.keys())}-{max(years.keys())}" if years else "No years")
    print(f"\nBy year:")
    for y in sorted(years.keys(), reverse=True):
        bar = "#" * (years[y] // max(1, max(years.values()) // 40))
        print(f"  {y}: {years[y]:>5} {bar}")
    print(f"\nBy category (top 15):")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1])[:15]:
        print(f"  {cat:<30s}: {cnt:>5}")


# ── Historical ──

def cmd_historical(args):
    """Batch fetch for historical period."""
    start = args.start  # YYYY-MM
    end = args.end  # YYYY-MM
    source = args.source or "keyword"

    start_dt = datetime.strptime(start, "%Y-%m")
    end_dt = datetime.strptime(end, "%Y-%m")

    current = start_dt
    month_count = 0
    while current <= end_dt:
        y, m = current.year, current.month
        if m == 12:
            next_dt = datetime(y + 1, 1, 1)
        else:
            next_dt = datetime(y, m + 1, 1)
        date_to = (next_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        date_from = current.strftime("%Y-%m-%d")

        month_count += 1
        print(f"\n{'='*60}")
        print(f"[{month_count}] {date_from} to {date_to}")
        print(f"{'='*60}")

        # Run the existing fetch_pubmed.py with date range
        script = Path(__file__).parent / "fetch_pubmed.py"
        out = Path(__file__).parent / "data" / "_tmp_hist.json"
        cmd = [
            sys.executable, str(script),
            "--start-date", date_from,
            "--end-date", date_to,
            "--max-per-query", "50",
            "--output", str(out),
        ]
        if NCBI_API_KEY:
            cmd.extend(["--api-key", NCBI_API_KEY])
        subprocess.run(cmd, check=False)

        if out.exists():
            with open(out, encoding="utf-8") as f:
                papers = json.load(f).get("papers", [])
            print(f"  Fetched: {len(papers)} papers")
            # Save to daily
            os.makedirs(DAILY_DIR, exist_ok=True)
            daily_path = DAILY_DIR / f"{date_to}.json"
            with open(daily_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
            os.remove(out)

        current = next_dt
        time.sleep(1)  # Extra rate limit between months

    # Build after all
    print("\nBuilding web data...")
    build(from_daily=True)

    if args.summarize:
        print("\nSummarizing...")
        cmd_summarize(argparse.Namespace(
            input=str(PAPERS_JSON), output=str(PAPERS_JSON),
            max_papers=None, pmids=None, force=False, model=None,
            base_url=None, api_key=None, delay=None,
        ))
        build(from_daily=False)

    print(f"\n[OK] Historical processing complete ({month_count} months)")


# ── Main CLI ──

def main():
    parser = argparse.ArgumentParser(
        description="Plant Virus Literature Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py fetch --days 7            # Fetch last week
  python pipeline.py auto --days 7             # Fetch + summarize + build
  python pipeline.py summarize --force         # Re-summarize all
  python pipeline.py stats                     # View statistics
  python pipeline.py historical --start 2026-01 --end 2026-06  # Batch 6 months
""")
    sub = parser.add_subparsers(dest="command", help="Commands")

    # fetch
    p_fetch = sub.add_parser("fetch", help="Fetch new papers")
    p_fetch.add_argument("--days", type=int, default=7)
    p_fetch.add_argument("--source", default="keyword", help="keyword,elink,species,preprint (comma-separated)")
    p_fetch.set_defaults(func=cmd_fetch)

    # summarize
    p_summ = sub.add_parser("summarize", help="Generate AI summaries")
    p_summ.add_argument("--input", default=None)
    p_summ.add_argument("--output", default=None)
    p_summ.add_argument("--force", action="store_true")
    p_summ.add_argument("--max-papers", type=int, default=None)
    p_summ.add_argument("--model", default=None)
    p_summ.add_argument("--pmids", nargs="+", default=None)
    p_summ.set_defaults(func=cmd_summarize)

    # build
    p_build = sub.add_parser("build", help="Build web data files")
    p_build.add_argument("--no-daily", action="store_true")
    p_build.add_argument("--journal-filter", action="store_true")
    p_build.set_defaults(func=cmd_build)

    # auto
    p_auto = sub.add_parser("auto", help="Fetch + summarize + build")
    p_auto.add_argument("--days", type=int, default=7)
    p_auto.add_argument("--source", default="keyword")
    p_auto.set_defaults(func=cmd_auto)

    # stats
    p_stats = sub.add_parser("stats", help="Print statistics")
    p_stats.set_defaults(func=cmd_stats)

    # historical
    p_hist = sub.add_parser("historical", help="Batch fetch historical period")
    p_hist.add_argument("--start", required=True, help="Start YYYY-MM")
    p_hist.add_argument("--end", required=True, help="End YYYY-MM")
    p_hist.add_argument("--source", default="keyword")
    p_hist.add_argument("--summarize", action="store_true", help="Also generate AI summaries")
    p_hist.set_defaults(func=cmd_historical)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
