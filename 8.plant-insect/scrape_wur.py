#!/usr/bin/env python3
"""Scrape WUR virus database — full structured extraction including references."""

import requests, re, time, csv, json
from pathlib import Path

BASE = "https://library.wur.nl/WebQuery/virus"
OUT = Path(__file__).parent / "wur_virus_full.tsv"
PER_PAGE = 20

def fetch_page(offset=0):
    url = f"{BASE}?q=*&wq_ofs={offset}&wq_max={PER_PAGE}"
    try:
        resp = requests.get(url, headers={"User-Agent": "PlantVirusDB/1.0"}, timeout=30)
        return resp.text if resp.status_code == 200 else None
    except:
        return None

def parse_page(html):
    records = []
    name_matches = list(re.finditer(r'<td>([^<]{5,150})</td>', html))
    if not name_matches: return records

    for m in name_matches:
        name = m.group(1).strip()
        if not name or len(name) < 5: continue

        rec = {"name": name, "family": "", "genus": "", "vector_org": "",
               "transmission": "", "ref_count": "0", "refs": ""}
        pos = m.end()
        chunk = html[pos:pos+8000]

        # Family/Genus/Vector from spans
        fm = re.search(r'<b>Family:\s*</b>\s*(\w+viridae)', chunk)
        if fm: rec["family"] = fm.group(1)
        gm = re.search(r'<b>Genus:\s*</b>\s*(\w+(?:virus|viroid))', chunk)
        if gm: rec["genus"] = gm.group(1)
        vm = re.search(r'<b>Vector organisms:\s*</b>\s*([^<]+)', chunk)
        if vm: rec["vector_org"] = vm.group(1).strip()

        # Modes of transmission (short)
        tm = re.search(r'<b>Modes of transmission:\s*</b>\s*(.+?)(?:<br|<li)', chunk, re.DOTALL)
        if tm: rec["transmission"] = tm.group(1).strip()[:200]

        # References — extract with full structure
        refs = re.findall(r'<li class="list-group-item">(.*?)</li>', chunk, re.DOTALL)
        rec["ref_count"] = str(len(refs))
        clean_refs = []
        for r in refs[:5]:
            clean = r.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            parts = [re.sub(r'<[^>]+>', '', p).strip() for p in clean.split('<br>') if p.strip()]
            parts = [p for p in parts if p]
            clean_refs.append(" | ".join(parts[:4]))  # detail | title | authors | citation
        rec["refs"] = " || ".join(clean_refs).replace("\n", " ").replace("\r", "") if clean_refs else ""

        records.append(rec)
    return records


def scrape_all():
    all_records, offset = [], 0
    html = fetch_page(0)
    if not html: return []
    total_m = re.search(r'Records\s+\d+\s+-\s+\d+\s+/\s+(\d+)', html)
    total = int(total_m.group(1)) if total_m else 1654
    print(f"Total: {total} records")

    while offset < total:
        html = fetch_page(offset)
        if not html: break
        records = parse_page(html)
        all_records.extend(records)
        print(f"  Offset {offset}: +{len(records)} = {len(all_records)}")
        if len(records) < PER_PAGE: break
        offset += PER_PAGE
        time.sleep(0.3)
    return all_records


if __name__ == "__main__":
    data = scrape_all()
    if data:
        fields = ["name", "family", "genus", "vector_org", "transmission", "ref_count", "refs"]
        with open(OUT, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, delimiter="\t", fieldnames=fields)
            w.writeheader()
            w.writerows(data)
        print(f"\nSaved {len(data)} records")
