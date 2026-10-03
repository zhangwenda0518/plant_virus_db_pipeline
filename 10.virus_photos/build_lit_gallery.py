#!/usr/bin/env python3
"""Build literature symptom-image gallery entries + staged image files.

1. list all_pdf_images.tgz contents
2. match the 3,989 symptom-relevant TSV rows to exact files (DOI-stem or
   title-stem + page; nearest-page fallback, max 2)
3. extract matched files to pdf_stage/
4. emit lit_gallery_entries.json in unified_gallery schema (with
   symptoms_std bilingual labels from normalize_symptoms)
"""

import csv
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from normalize_symptoms import std_symptoms, std_parts

HERE = Path(__file__).parent
EX = HERE / "extracted"
TSV = EX / "all_papers_structured.tsv"
TGZ = EX / "all_pdf_images.tgz"
STAGE = EX / "pdf_stage"
OUT_JSON = EX / "lit_gallery_entries.json"
FILELIST = EX / "selected_files.txt"

MIN_W, MIN_H = 200, 150


def main():
    # ---- 1. tgz listing ----
    print("listing tgz ...", flush=True)
    listing = subprocess.run(["tar", "-tzf", str(TGZ)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.splitlines()
    avail = set(x.strip() for x in listing if x.strip())
    # (stem, page) -> [files]; stem = name minus _p{N}_{M}.ext
    idx = defaultdict(list)
    stems = set()
    for a in avail:
        m = re.match(r"^(.*)_p(\d+)_(\d+)\.(jpeg|jpg|png)$", a)
        if not m:
            continue
        stem, page = m.group(1), int(m.group(2))
        idx[(stem, page)].append(a)
        stems.add(stem)
    print(f"tgz files: {len(avail)}, stems: {len(stems)}")

    # ---- 2. TSV rows -> files ----
    rows = []
    with open(TSV, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r.get("HasVirus") == "YES" and r.get("HasHost") == "YES" and r.get("HasSymptom") == "YES":
                rows.append(r)
    print(f"full-match rows: {len(rows)}")

    chosen = {}   # filename -> row (first wins)
    matched_rows = 0
    for r in rows:
        doi_stem = (r.get("DOI") or "").strip().replace("/", "_").replace(" ", "_")
        try:
            page = int(re.search(r"_p(\d+)_", r["File"]).group(1))
        except Exception:
            page = None
        cands = None
        for stem in (doi_stem, os.path.splitext(r["File"])[0]):
            if not stem:
                continue
            if page is not None and (stem, page) in idx:
                cands = sorted(idx[(stem, page)])
                break
        if not cands:
            # nearest-page fallback (same stem, max 2 files)
            for stem in (doi_stem, os.path.splitext(r["File"])[0]):
                if not stem:
                    continue
                pages = [p for (s, p) in idx if s == stem]
                if pages:
                    best = min(pages, key=lambda p: abs(p - (page or 0)))
                    cands = sorted(idx[(stem, best)])[:2]
                    break
        if not cands:
            continue
        matched_rows += 1
        for fn in cands:
            if fn not in chosen:
                chosen[fn] = r
    print(f"rows matched: {matched_rows}/{len(rows)}, unique files: {len(chosen)}")

    # ---- 3. extract ----
    STAGE.mkdir(exist_ok=True)
    with open(FILELIST, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(chosen)))
    print("extracting ...", flush=True)
    subprocess.run(["tar", "-xzf", str(TGZ), "-C", str(STAGE), "-T", str(FILELIST)],
                   check=True)
    # size filter
    kept = []
    dropped = 0
    for fn in sorted(chosen):
        p = STAGE / fn
        if not p.exists() or p.stat().st_size < 4096:
            dropped += 1
            continue
        kept.append(fn)
    print(f"extracted+kept: {len(kept)} (dropped {dropped} missing/tiny)")

    # ---- 4. gallery entries ----
    entries = []
    for fn in kept:
        r = chosen[fn]
        viruses = [v.strip() for v in re.split(r"[;,]", r.get("Viruses") or "") if v.strip()]
        hosts = [h.strip() for h in re.split(r"[;,]", r.get("Hosts") or "") if h.strip()]
        virus = viruses[0] if viruses else ""
        sym_raw = r.get("Symptoms") or ""
        sym_std, _, _ = std_symptoms(sym_raw)
        parts_std = std_parts(r.get("Parts") or "")
        doi = (r.get("DOI") or "").strip()
        try:
            page = int(re.search(r"_p(\d+)_", r["File"]).group(1))
        except Exception:
            page = 0
        sym_list = [s.strip() for s in re.split(r"[;,]", sym_raw) if s.strip()]
        entries.append({
            "code": "PDF",
            "virus": virus,
            "virus_latin": virus,
            "virus_ictv": virus,
            "photo_id": fn,
            "thumb": f"/photos/data/pdf_images/{fn}",
            "full": f"/photos/data/pdf_images/{fn}",
            "caption": f"Symptom figure from research paper" + (f" (doi:{doi})" if doi else ""),
            "photographer": "",
            "hosts": hosts[:6],
            "hosts_latin": hosts[:6],
            "hosts_cn": [],
            "symptoms": sym_list[:8],
            "symptoms_std": sym_std[:8],
            "parts": [],
            "parts_std": parts_std[:6],
            "page": page,
            "source": "PDF",   # 统一标签：与 build_unified_gallery.py / docs/photos.html 的 'PDF' 一致
            "doi": doi,
        })
    OUT_JSON.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    print(f"entries written: {len(entries)} -> {OUT_JSON}")
    total_mb = sum((STAGE / f).stat().st_size for f in kept) / 1e6
    print(f"staging size: {total_mb:.0f} MB")


if __name__ == "__main__":
    main()
