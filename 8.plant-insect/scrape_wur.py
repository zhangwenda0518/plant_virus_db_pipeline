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
        # 将 chunk 精确限定到下一条记录起点，避免 findall 越界到相邻记录
        nxt = html.find('id="record_', pos)
        chunk = html[pos:nxt] if nxt != -1 else html[pos:pos + 8000]

        # Family/Genus/Vector from spans
        fm = re.search(r'<b>Family:\s*</b>\s*(\w+viridae)', chunk)
        if fm: rec["family"] = fm.group(1)
        gm = re.search(r'<b>Genus:\s*</b>\s*(\w+(?:virus|viroid))', chunk)
        if gm: rec["genus"] = gm.group(1)
        vm = re.search(r'<b>Vector organisms:\s*</b>\s*([^<]+)', chunk)
        if vm: rec["vector_org"] = vm.group(1).strip()

        # 传播方式：合并「Modes of transmission」摘要 + 每条参考的「Vector or means
        # of transmission」明细(去重)。WUR 现用 <div> 布局，值以纯文本止于下一个 '<'。
        parts = []
        mm = re.search(r'<b>Modes of transmission:\s*</b>\s*([^<]*)', chunk)
        if mm and mm.group(1).strip():
            parts.append(mm.group(1).strip())
        for vm2 in re.findall(r'<b>Vector or means of transmission:\s*</b>\s*([^<]+)', chunk):
            vm2 = vm2.strip()
            if vm2 and vm2 not in parts:
                parts.append(vm2)
        rec["transmission"] = "; ".join(parts)

        # References — 每条参考各自带一个「Vector or means of transmission」，成对提取。
        # 结构: <b>Vector or means of transmission:</b>TRANS<br><li>...TITLE...AUTHORS...CITATION...</li>
        ref_pairs = re.findall(
            r'(?:<b>Vector or means of transmission:\s*</b>\s*([^<]*)\s*<br\s*/?>\s*)?'
            r'<li class="list-group-item">(.*?)</li>',
            chunk, re.DOTALL)
        rec["ref_count"] = str(len(ref_pairs))
        clean_refs = []
        for trans, li in ref_pairs[:5]:
            clean = li.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            parts = [re.sub(r'<[^>]+>', '', p).strip() for p in clean.split('<br>') if p.strip()]
            parts = [p for p in parts if p]
            ref_str = " | ".join(parts[:3])       # title | authors | citation
            t = (trans or "").strip()
            if t:
                ref_str += " | means: " + t       # 该参考对应的传播方式
            clean_refs.append(ref_str)
        rec["refs"] = " || ".join(clean_refs).replace("\n", " ").replace("\r", "")

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
