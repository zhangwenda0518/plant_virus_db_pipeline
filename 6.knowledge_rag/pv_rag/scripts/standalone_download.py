"""Standalone OA PDF downloader — NO Postgres, NO NEBLab project needed.

Copy this script + shard_N_docs.json to each server.
Only needs Python 3.10+ and 3 pip packages.

SETUP (once per server):
    pip install httpx pyalex pymupdf

USAGE (4 machines in parallel):
    python standalone_download.py --shard shard_0_docs.json --output ./pv_texts_0
    python standalone_download.py --shard shard_1_docs.json --output ./pv_texts_1
    python standalone_download.py --shard shard_2_docs.json --output ./pv_texts_2
    python standalone_download.py --shard shard_3_docs.json --output ./pv_texts_3

Each machine downloads OA PDFs, parses to plain text, writes one JSON per paper.
Send all pv_texts_* dirs back to merge on the master machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pyalex
import pymupdf

# ---- Config ----
OPENALEX_EMAIL = "3221020746@stu.cpu.edu.cn"

DOWNLOAD_WORKERS = 5      # concurrent PDF downloads
OA_LOOKUP_WORKERS = 3     # concurrent OpenAlex lookups
TIMEOUT = 45.0            # seconds per PDF download
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB cap per PDF


# ---- PDF URL lookup (OpenAlex) ----


def _get_pdf_url(openalex_id: str) -> str | None:
    """Look up OA PDF URL via OpenAlex API."""
    try:
        work = pyalex.Works()[openalex_id]
    except Exception:
        return None
    for key in ("best_oa_location", "primary_location"):
        loc = work.get(key) or {}
        url = loc.get("pdf_url")
        if url:
            return str(url)
    return None


# ---- Async download + parse ----


async def _download_one(
    doc: dict,
    sem: asyncio.Semaphore,
    output_dir: Path,
) -> dict:
    """Download PDF from saved URL, parse, write JSON."""
    result = {"doc_id": doc["id"], "status": "failed"}
    url = doc.get("_pdf_url")
    if not url:
        result["status"] = "no_url"
        return result

    async with sem:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "PVDB-RAG/1.0 (academic research; mailto:" + OPENALEX_EMAIL + ")"},
        ) as client:
            try:
                resp = await client.get(url)
            except httpx.HTTPError:
                result["status"] = "download_error"
                return result

    if resp.status_code != 200:
        result["status"] = f"http_{resp.status_code}"
        return result

    body = resp.content
    if len(body) > MAX_PDF_BYTES:
        result["status"] = "too_large"
        return result

    # Parse PDF
    try:
        pdf_doc = pymupdf.open(stream=body, filetype="pdf")
        pages_text = [page.get_text() for page in pdf_doc]
        text = "\n".join(pages_text)
        page_count = len(pages_text)
        pdf_doc.close()
    except Exception:
        result["status"] = "parse_error"
        return result

    text = text.strip()
    if not text:
        result["status"] = "empty_text"
        return result

    # Write result
    out_path = output_dir / f"{doc['id']}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "doc_id": doc["id"],
                "title": doc.get("title", ""),
                "openalex_id": doc.get("openalex_id"),
                "doi": doc.get("doi"),
                "year": doc.get("year"),
                "text": text,
                "page_count": page_count,
                "source_url": url,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result["status"] = "ok"
    result["chars"] = len(text)
    return result


async def main_download(shard_file: Path, output_dir: Path) -> dict:
    pyalex.config.email = OPENALEX_EMAIL

    # Load paper list
    docs = json.loads(shard_file.read_text(encoding="utf-8"))
    total = len(docs)
    print(f"Loaded {total:,} papers from {shard_file.name}")
    print(f"Output: {output_dir.resolve()}")

    # Skip already-downloaded
    existing = set(f.stem for f in output_dir.glob("*.json")) if output_dir.exists() else set()
    remaining = [d for d in docs if str(d["id"]) not in existing]
    if remaining != docs:
        print(f"  Already done: {total - len(remaining):,}  Remaining: {len(remaining):,}")
        docs = remaining
        total = len(docs)

    # Phase 1: parallel OpenAlex PDF URL lookups
    loop = asyncio.get_running_loop()

    def lookup(doc):
        oaid = doc.get("openalex_id")
        if not oaid:
            return None
        return _get_pdf_url(oaid)

    print("Phase 1: looking up PDF URLs via OpenAlex...")
    with ThreadPoolExecutor(max_workers=OA_LOOKUP_WORKERS) as pool:
        futures = [loop.run_in_executor(pool, lookup, d) for d in docs]
        urls = [await f for f in asyncio.as_completed(futures)]
        for doc, url in zip(docs, urls):
            doc["_pdf_url"] = url if isinstance(url, str) else None

    has_url = sum(1 for d in docs if d.get("_pdf_url"))
    print(f"  {has_url}/{total} have PDF URLs ({has_url/total*100:.1f}%)")

    # Phase 2: parallel download + parse
    docs_with_url = [d for d in docs if d.get("_pdf_url")]
    sem = asyncio.Semaphore(DOWNLOAD_WORKERS)
    tasks = [_download_one(d, sem, output_dir) for d in docs_with_url]

    counts = {"ok": 0, "failed": 0, "no_url": total - len(docs_with_url)}
    t0 = time.time()

    for i, coro in enumerate(asyncio.as_completed(tasks)):
        r = await coro
        counts[r["status"]] = counts.get(r["status"], 0) + 1

        if (i + 1) % 500 == 0 or (i + 1) == len(tasks):
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(tasks) - i - 1) / rate / 60 if rate > 0 else 0
            print(
                f"  [{i+1}/{len(tasks)}] "
                f"ok={counts.get('ok',0)} failed={counts.get('failed',0)} "
                f"rate={rate:.1f}/s eta={eta:.0f}min"
            )

    elapsed = time.time() - t0
    files_written = len(list(output_dir.glob("*.json")))
    print(f"\nDone: ok={counts.get('ok',0)} failed={counts.get('failed',0)} no_url={counts.get('no_url',0)} in {elapsed/60:.0f}min")
    print(f"Files in {output_dir}: {files_written}")
    return counts


def main():
    ap = argparse.ArgumentParser(description="Standalone OA PDF downloader (no Postgres needed)")
    ap.add_argument("--shard", required=True, help="Path to shard_N_docs.json")
    ap.add_argument("--output", default="./pv_texts", help="Output directory for parsed JSON files")
    args = ap.parse_args()
    asyncio.run(main_download(Path(args.shard), Path(args.output)))


if __name__ == "__main__":
    main()
