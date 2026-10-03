#!/usr/bin/env python3
"""Batch-summarize papers in fresh subprocesses. Crash-proof: restarts on failure."""
import subprocess, sys, os, time, json
import os
from pathlib import Path

HERE = Path(__file__).parent
BATCH_SIZE = int(os.environ.get("SUMM_BATCH", "500"))
PAPERS = HERE / "data" / "papers.json"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")  # 明文 key 已移除 (2026-10-03)
BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-flash"

data = json.load(open(PAPERS, encoding="utf-8"))
pending = sum(1 for p in data["papers"] if not p.get("ai_done"))
total = len(data["papers"])
done = total - pending
print(f"Initial: {done}/{total} ({round(done/total*100,1)}%) done, {pending} pending")

batch = 0
max_batches = 200
while pending > 0 and batch < max_batches:
    batch += 1

    # Reload paper list to catch saved state from previous batch
    data = json.load(open(PAPERS, encoding="utf-8"))
    batch_pmids = [p["pmid"] for p in data["papers"]
                   if not p.get("ai_done") and p.get("abstract", "").strip()
                   and p.get("pmid")][:BATCH_SIZE]
    if not batch_pmids:
        print("All pending papers have no abstracts — done!")
        break

    print(f"\nBatch {batch}: {len(batch_pmids)} PMIDs")
    for retry in range(3):
        delay = 0.4 + retry * 0.2
        cmd = [
            sys.executable, str(HERE / "summarize_papers.py"),
            "--base-url", BASE_URL,
            "--model", MODEL, "--delay", str(delay),
            "--pmids", *batch_pmids,
        ]
        # key 走环境变量传递，避免出现在子进程命令行（ps 可见）
        env = dict(os.environ, LLM_API_KEY=API_KEY)
        try:
            subprocess.run(cmd, timeout=5400, cwd=str(HERE), check=False, env=env)
            break
        except subprocess.TimeoutExpired:
            print(f"  Timeout, retry {retry+2}/3 (delay={delay})...")
            time.sleep(15)
        except Exception as e:
            print(f"  Crash: {e}, retry {retry+2}/3...")
            time.sleep(15)

    # Reload and report
    data = json.load(open(PAPERS, encoding="utf-8"))
    new_done = sum(1 for p in data["papers"] if p.get("ai_done"))
    new_pending = len(data["papers"]) - new_done
    print(f"Batch {batch}: {new_done}/{total} ({round(new_done/total*100,1)}%), +{new_done-done}")
    done, pending = new_done, new_pending

print(f"\nDone: {done}/{total} ({round(done/total*100,1)}%)")
