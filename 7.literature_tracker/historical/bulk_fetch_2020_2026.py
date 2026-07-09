#!/usr/bin/env python3
"""
Bulk fetch plant virus papers for historical period (2020-2026).
Processes month-by-month and saves daily JSONs for each month.
Resumable: skips months already processed.
"""
import json, os, sys, time, argparse, subprocess
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DAILY_DIR, PAPERS_JSON, NCBI_API_KEY

SCRIPT_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FETCH_KEYWORD = SCRIPT_DIR / "fetch_pubmed.py"
FETCH_LINKED = SCRIPT_DIR / "fetch_linked_papers.py"
FETCH_SPECIES = SCRIPT_DIR / "fetch_species_papers.py"
STATE_FILE = SCRIPT_DIR / "data" / "pipeline_state.json"


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"processed_months": [], "total_papers": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def month_range(start: str, end: str) -> list:
    """Generate (date_from, date_to, label) tuples for each month."""
    start_dt = datetime.strptime(start, "%Y-%m")
    end_dt = datetime.strptime(end, "%Y-%m")
    months = []
    current = start_dt
    while current <= end_dt:
        y, m = current.year, current.month
        date_from = f"{y}-{m:02d}-01"
        if m == 12:
            next_m = datetime(y + 1, 1, 1)
        else:
            next_m = datetime(y, m + 1, 1)
        date_to = (next_m - timedelta(days=1)).strftime("%Y-%m-%d")
        months.append((date_from, date_to, f"{y}-{m:02d}"))
        current = next_m
    return months


def fetch_historical(source: str = "keyword"):
    """Batch fetch for historical period, month by month, all sources."""
    state = load_state()
    all_months = month_range("2020-01", "2026-12")
    months_left = [m for m in all_months if m[2] not in state["processed_months"]]
    print(f"Total months: {len(all_months)}, Done: {len(state['processed_months'])}, "
          f"Remaining: {len(months_left)}")

    for date_from, date_to, label in months_left:
        print(f"\n{'='*60}")
        print(f"[{label}] {date_from} to {date_to}")
        print(f"{'='*60}")

        all_papers = []
        scripts = [(source, 50)]

        for script_name, max_ppq in scripts:
            tmp_out = SCRIPT_DIR / "data" / f"_hist_{label}.json"
            if script_name == "keyword":
                script = FETCH_KEYWORD
            elif script_name == "elink":
                script = FETCH_LINKED
            elif script_name == "species":
                script = FETCH_SPECIES
            else:
                continue

            if not script.exists():
                print(f"  SKIP {script_name}: not found")
                continue

            cmd = [
                sys.executable, str(script),
                "--start-date", date_from,
                "--end-date", date_to,
                "--output", str(tmp_out),
            ]
            if script_name != "species":
                cmd.extend(["--max-per-query", str(max_ppq)])
            if NCBI_API_KEY:
                cmd.extend(["--api-key", NCBI_API_KEY])

            print(f"  Running: {' '.join(cmd[:4])}...")
            subprocess.run(cmd, check=False)

            if tmp_out.exists():
                with open(tmp_out, encoding="utf-8") as f:
                    data = json.load(f)
                    papers = data.get("papers", [])
                    print(f"    Fetched: {len(papers)} papers")
                    all_papers.extend(papers)
                os.remove(tmp_out)

            time.sleep(1)  # Rate limit between scripts

        if all_papers:
            os.makedirs(DAILY_DIR, exist_ok=True)
            daily_path = DAILY_DIR / f"{date_to}.json"
            with open(daily_path, "w", encoding="utf-8") as f:
                json.dump(all_papers, f, ensure_ascii=False, indent=2)
            print(f"  Saved {len(all_papers)} papers → {daily_path}")

        state["processed_months"].append(label)
        state["total_papers"] += len(all_papers)
        state["last_processed"] = label
        save_state(state)

        # Extra rate limit between months
        time.sleep(2)

    print(f"\n{'='*60}")
    print(f"Historical fetch complete!")
    print(f"Processed: {len(state['processed_months'])} months")
    print(f"Total papers: {state['total_papers']}")
    print(f"Output: {DAILY_DIR}/")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="keyword", help="keyword, elink, species (keyword is fastest)")
    p.add_argument("--dry-run", action="store_true", help="List months without fetching")
    args = p.parse_args()

    if args.dry_run:
        months = month_range("2020-01", "2026-12")
        state = load_state()
        for d1, d2, lbl in months:
            done = "✓" if lbl in state["processed_months"] else " "
            print(f"  [{done}] {lbl}: {d1} → {d2}")
        return

    fetch_historical(args.source)


if __name__ == "__main__":
    main()
