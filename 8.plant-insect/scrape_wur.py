#!/usr/bin/env python3
"""Scrape WUR virus database — full structured extraction including references."""

import requests, re, time, csv, json
from collections import Counter
from pathlib import Path

BASE = "https://library.wur.nl/WebQuery/virus"
OUT = Path(__file__).parent / "wur_virus_full.tsv"
PER_PAGE = 20
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5  # 秒, 线性退避


def fetch_page(offset=0):
    """抓取一页。瞬时网络错误/非 200 重试 MAX_RETRIES 次 (审计修复: 原裸 except 吞掉一切);
    全部失败返回 None 并由调用方统一做截断比对。"""
    url = f"{BASE}?q=*&wq_ofs={offset}&wq_max={PER_PAGE}"
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": "PlantVirusDB/1.0"}, timeout=30)
        except requests.exceptions.RequestException as e:  # 连接/超时/SSL 等具体异常
            last_err = f"{type(e).__name__}: {e}"
        else:
            if resp.status_code == 200:
                return resp.text
            last_err = f"HTTP {resp.status_code}"
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * attempt)
    print(f"  [warn] offset={offset} 抓取失败 (已重试 {MAX_RETRIES} 次): {last_err}")
    return None

def parse_page(html):
    records = []
    name_matches = list(re.finditer(r'<td>([^<]{5,150})</td>', html))
    if not name_matches: return records

    for m in name_matches:
        name = m.group(1).strip()
        if not name or len(name) < 5: continue

        rec = {"name": name, "family": "", "genus": "", "vector_org": "",
               "modes": "", "transmission": "", "ref_count": "0", "refs": ""}
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

        # 传播方式:
        #   modes = WUR「Modes of transmission」受控途径(sap/seed/soil/water/vegetative...)
        #   transmission = modes 摘要 + 每条参考的「Vector or means」明细(自由文本, 供展示)
        parts = []
        mm = re.search(r'<b>Modes of transmission:\s*</b>\s*([^<]*)', chunk)
        if mm and mm.group(1).strip():
            rec["modes"] = mm.group(1).strip()
            parts.append(mm.group(1).strip())
        for vm2 in re.findall(r'<b>Vector or means of transmission:\s*</b>\s*([^<]+)', chunk):
            vm2 = vm2.strip()
            if vm2 and vm2 not in parts:
                parts.append(vm2)
        rec["transmission"] = "; ".join(parts)

        # References — 每条参考各自带一个「Vector or means of transmission」，成对结构化提取。
        # 输出为 JSON 数组: [{title, authors, citation, means, doi}, ...]
        ref_pairs = re.findall(
            r'(?:<b>Vector or means of transmission:\s*</b>\s*([^<]*)\s*<br\s*/?>\s*)?'
            r'<li class="list-group-item">(.*?)</li>',
            chunk, re.DOTALL)
        rec["ref_count"] = str(len(ref_pairs))
        ref_objs = []
        for trans, li in ref_pairs[:10]:
            doi_m = re.search(r'href="([^"]*?(?:doi\.org|/doi/)[^"]*)"', li)
            doi = doi_m.group(1) if doi_m else ""
            clean = li.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            clean = re.sub(r'<p>.*?</p>', '', clean, flags=re.DOTALL)   # 去摘要
            parts = [re.sub(r'<[^>]+>', '', p).strip() for p in clean.split('<br>') if p.strip()]
            parts = [p for p in parts if p]
            ref_objs.append({
                "title": parts[0] if len(parts) > 0 else "",
                "authors": parts[1] if len(parts) > 1 else "",
                "citation": parts[2] if len(parts) > 2 else "",
                "means": (trans or "").strip(),
                "doi": doi,
            })
        rec["refs"] = json.dumps(ref_objs, ensure_ascii=False).replace("\t", " ").replace("\n", " ").replace("\r", "")

        records.append(rec)
    return records


def mark_duplicates(records):
    """按 virus name 审查重名: 重名条目全部保留, 追加 duplicated 标记列 (1=存在同名条目)。
    审计修复: 原输出无去重也无标记, 21 组重名 (其中 20 组内容互相矛盾) 不可审计。"""
    counts = Counter(r["name"] for r in records)
    for r in records:
        r["duplicated"] = "1" if counts[r["name"]] > 1 else "0"
    n_dup = sum(1 for r in records if r["duplicated"] == "1")
    if n_dup:
        print(f"  [note] {n_dup} 条记录存在同名条目 (已标 duplicated=1, 保留原样)")
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

    # 截断比对: 已抓条数 vs 页面声明 total, 不一致写警告文件 (审计修复: 原实现静默截断)
    if len(all_records) != total:
        warn_path = Path(__file__).parent / "scrape_warning.txt"
        fetched = len(all_records)
        with open(warn_path, "w", encoding="utf-8") as fw:
            fw.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WUR scrape count mismatch\n"
                     f"page_total={total}\nfetched={fetched}\nlast_offset={offset}\n"
                     f"missing={total - fetched}\n")
        print(f"  [warn] 已抓 {fetched} 条 != 页面 total {total} 条 → 警告已写 {warn_path.name}")
    return all_records


if __name__ == "__main__":
    data = scrape_all()
    if data:
        data = mark_duplicates(data)
        fields = ["name", "family", "genus", "vector_org", "modes", "transmission",
                  "ref_count", "refs", "duplicated"]
        with open(OUT, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, delimiter="\t", fieldnames=fields)
            w.writeheader()
            w.writerows(data)
        print(f"\nSaved {len(data)} records")
