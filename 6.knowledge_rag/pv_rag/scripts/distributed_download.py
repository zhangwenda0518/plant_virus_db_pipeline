"""Distributed OA PDF downloader — runs on one shard of the full paper set.

Usage (one machine):
  python scripts/distributed_download.py --id-mod 4 --id-rem 0 --output ./parsed_texts
  python scripts/distributed_download.py --id-mod 4 --id-rem 1 --output ./parsed_texts
  python scripts/distributed_download.py --id-mod 4 --id-rem 2 --output ./parsed_texts
  python scripts/distributed_download.py --id-mod 4 --id-rem 3 --output ./parsed_texts

Each machine downloads ~20K OA papers. Output: ./parsed_texts/{doc_id}.json per paper.

Merge: copy all JSON files to one machine, run:
  python scripts/distributed_download.py --merge ./parsed_texts
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from sqlalchemy import select

# Ensure the project root is on sys.path
_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from neblab_rag.config import get_settings
from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.providers.parser import PyMuPDFParser
from plant_virus_rag.db.engine import get_pv_session
from plant_virus_rag.db.models import PvDocument
from plant_virus_rag.db.repositories import PvFullTextRepository

DEFAULT_CONCURRENCY = 5  # downloads per machine
DEFAULT_OA_WORKERS = 3    # OpenAlex URL lookups per machine
DEFAULT_TIMEOUT = 45.0
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


async def _download_one(
    doc: PvDocument,
    url,
    sem: asyncio.Semaphore,
    parser: PyMuPDFParser,
    output_dir: Path,
) -> dict:
    """Download + parse one PDF, write to output_dir/doc_id.json."""
    result = {"doc_id": doc.id, "status": "failed", "text": ""}

    async with sem:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "NEBLab-RAG/1.0 (academic research)"},
        ) as client:
            try:
                resp = await client.get(url)
            except httpx.HTTPError:
                return result

    if resp.status_code != 200:
        result["status"] = f"http_{resp.status_code}"
        return result

    body = resp.content
    if len(body) > DEFAULT_MAX_BYTES:
        result["status"] = "too_large"
        return result

    try:
        parsed = parser.parse(body)
    except Exception:
        result["status"] = "parse_error"
        return result

    if not parsed.text.strip():
        result["status"] = "empty_text"
        return result

    # Save to file
    out_path = output_dir / f"{doc.id}.json"
    data = {
        "doc_id": doc.id,
        "title": doc.title,
        "openalex_id": doc.openalex_id,
        "doi": doc.doi,
        "year": doc.year,
        "text": parsed.text,
        "page_count": parsed.page_count,
        "source_url": url,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result["status"] = "ok"
    result["chars"] = len(parsed.text)
    return result


async def download_shard(
    mod: int,
    rem: int,
    output_dir: Path,
    *,
    oa_workers: int = DEFAULT_OA_WORKERS,
    download_concurrency: int = DEFAULT_CONCURRENCY,
) -> dict:
    """Download all OA papers where doc.id % mod == rem."""
    settings = get_settings()
    oa_client = OpenAlexClient(email=settings.openalex_email)
    parser = PyMuPDFParser()

    output_dir.mkdir(parents=True, exist_ok=True)

    with get_pv_session() as session:
        stmt = (
            select(PvDocument)
            .where(
                PvDocument.is_oa.is_(True),
                PvDocument.openalex_id.isnot(None),
                PvDocument.id % mod == rem,
            )
            .order_by(PvDocument.id)
        )
        docs = list(session.execute(stmt).scalars().all())
        total = len(docs)

    print(f"Shard: id % {mod} == {rem}  →  {total:,} papers")
    print(f"Output: {output_dir.resolve()}")

    # Phase 1: parallel OpenAlex URL lookup
    loop = asyncio.get_running_loop()

    def lookup(doc):
        if not doc.openalex_id:
            return (doc.id, None)
        url = oa_client.get_pdf_url(doc.openalex_id)
        return (doc.id, url)

    doc_urls: dict[int, str | None] = {}
    with ThreadPoolExecutor(max_workers=oa_workers) as pool:
        futures = [loop.run_in_executor(pool, lookup, doc) for doc in docs]
        for fut in asyncio.as_completed(futures):
            doc_id, url = await fut
            doc_urls[doc_id] = url

    has_url = sum(1 for v in doc_urls.values() if v)
    print(f"Phase 1: {has_url}/{total} have PDF URLs")

    # Phase 2: parallel download
    docs_with_url = [d for d in docs if doc_urls.get(d.id)]
    sem = asyncio.Semaphore(download_concurrency)

    tasks = [
        _download_one(d, doc_urls[d.id], sem, parser, output_dir)
        for d in docs_with_url
    ]

    counts = {"ok": 0, "failed": 0, "total": total}
    t0 = time.time()

    for i, coro in enumerate(asyncio.as_completed(tasks)):
        result = await coro
        if result["status"] == "ok":
            counts["ok"] += 1
        else:
            counts["failed"] += 1

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(tasks) - i - 1) / rate / 60 if rate > 0 else 0
            print(
                f"  [{i+1}/{len(tasks)}] "
                f"ok={counts['ok']} failed={counts['failed']} "
                f"rate={rate:.1f}/s  eta={eta:.0f}min"
            )

    elapsed = time.time() - t0
    print(f"\nDone: ok={counts['ok']} failed={counts['failed']} in {elapsed/60:.0f}min")
    print(f"Files in {output_dir}: {len(list(output_dir.glob('*.json')))}")
    return counts


def merge_fulltext(source_dir: str) -> None:
    """Import all parsed JSON files from source_dir into local Postgres."""
    from plant_virus_rag.db.repositories import PvFullTextRepository

    source = Path(source_dir)
    files = sorted(source.glob("*.json"))
    print(f"Found {len(files)} files in {source_dir}")

    with get_pv_session() as session:
        ft_repo = PvFullTextRepository(session)
        imported = 0
        skipped = 0

        for fpath in files:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            doc_id = data["doc_id"]
            text = data.get("text", "")
            if not text.strip():
                skipped += 1
                continue

            ft_repo.upsert(
                document_id=doc_id,
                text=text,
                page_count=data.get("page_count", 0),
                parser_name="PyMuPDF",
                source_url=data.get("source_url", ""),
            )
            imported += 1

            if imported % 100 == 0:
                session.flush()
                print(f"  Imported {imported}...")

        session.commit()
    print(f"Merge done: imported={imported} skipped={skipped}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Distributed OA PDF downloader")
    ap.add_argument("--id-mod", type=int, help="Modulus for sharding")
    ap.add_argument("--id-rem", type=int, help="Remainder for sharding")
    ap.add_argument("--output", default="./parsed_texts", help="Output directory")
    ap.add_argument(
        "--oa-workers", type=int, default=DEFAULT_OA_WORKERS,
        help="OpenAlex URL lookup thread workers"
    )
    ap.add_argument(
        "--download-concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help="Concurrent PDF downloads"
    )
    ap.add_argument(
        "--merge", type=str, default=None,
        help="Import mode: merge parsed JSON files from this directory into Postgres"
    )
    args = ap.parse_args()

    if args.merge:
        merge_fulltext(args.merge)
        return

    if args.id_mod is None or args.id_rem is None:
        ap.error("--id-mod and --id-rem are required for download mode")

    asyncio.run(
        download_shard(
            mod=args.id_mod,
            rem=args.id_rem,
            output_dir=Path(args.output),
            oa_workers=args.oa_workers,
            download_concurrency=args.download_concurrency,
        )
    )


if __name__ == "__main__":
    main()
