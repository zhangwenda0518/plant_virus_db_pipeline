#!/usr/bin/env python3
"""
Download NCBI nuccore plant endogenous viral element sequences.
Query: (endogenous[Title] OR EPRV[Title] OR EVE[Title] OR
        florendovirus[Title] OR badnavirus[Title]) AND Viridiplantae[Organism]
Filters out: PREDICTED, patent, mRNA, UNVERIFIED entries.
Uses NCBI history (WebEnv) to paginate through all results efficiently.
"""
import urllib.request
import urllib.parse
import urllib.error
import time
import os
import re
import sys
import xml.etree.ElementTree as ET

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# NCBI 合规：联系邮箱只取自环境变量（不再硬编码个人邮箱）
EMAIL = os.environ.get("NCBI_EMAIL", "").strip()
TOOL = "plant_te_pipeline"


def _eutils_params(extra):
    """E-utilities 公共参数：始终带 tool；仅当配置了 NCBI_EMAIL 才带 email。"""
    params = {"tool": TOOL}
    if EMAIL:
        params["email"] = EMAIL
    params.update(extra)
    return params


if not EMAIL:
    print("[WARN] 环境变量 NCBI_EMAIL 未设置：E-utilities 请求将只带 tool=%s（NCBI 政策要求提供联系邮箱）" % TOOL)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(SCRIPT_DIR) == 'data' and os.path.basename(os.path.dirname(SCRIPT_DIR)) == 'te':
    OUT_DIR = SCRIPT_DIR
else:
    OUT_DIR = os.path.join(SCRIPT_DIR, "..", "docs", "te", "data")
OUT_DIR = os.path.abspath(OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)

QUERY = ('(endogenous[Title] OR EPRV[Title] OR EVE[Title] OR '
         'florendovirus[Title] OR badnavirus[Title]) AND '
         'Viridiplantae[Organism]')

FILTER_TERMS = ['PREDICTED', 'patent', 'mRNA', 'UNVERIFIED']

SUMMARY_PAGE = 500   # esummary max per call
FETCH_BATCH = 200    # efetch max per call
SLEEP = 0.4


def esearch(query):
    """Search NCBI nuccore, return (count, webenv, query_key)."""
    params = _eutils_params({
        'db': 'nuccore', 'term': query, 'retmax': 0,
        'usehistory': 'y', 'retmode': 'xml',
    })
    url = f"{BASE_URL}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    print("  Searching NCBI (esearch)...")
    with urllib.request.urlopen(url, timeout=60) as resp:
        root = ET.fromstring(resp.read())
    count = int(root.findtext('Count', '0'))
    webenv = root.findtext('WebEnv', '')
    query_key = root.findtext('QueryKey', '')
    print(f"  Total results: {count}")
    return count, webenv, query_key


def esummary_page(webenv, query_key, retstart, retmax):
    """Get one page of summaries via WebEnv."""
    params = _eutils_params({
        'db': 'nuccore', 'WebEnv': webenv, 'query_key': query_key,
        'retstart': retstart, 'retmax': retmax, 'retmode': 'xml',
    })
    url = f"{BASE_URL}/esummary.fcgi?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            root = ET.fromstring(resp.read())
        results = []
        for docsum in root.findall('.//DocSum'):
            uid = docsum.findtext('Id', '')
            title = ''
            for item in docsum.findall('Item'):
                if item.get('Name') == 'Title':
                    title = item.text or ''
                    break
            results.append((uid, title))
        return results
    except Exception as e:
        print(f"  Error: {e}")
        return []


def efetch_batch(ids):
    """Download sequences in FASTA format.

    Returns FASTA text on success, None on failure（调用方须把该批 id 记入失败清单，
    旧代码失败返回 "" 会被静默当成"0 条记录"）。"""
    params = _eutils_params({
        'db': 'nuccore', 'id': ','.join(ids),
        'rettype': 'fasta', 'retmode': 'text', 'retmax': len(ids),
    })
    url = f"{BASE_URL}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        print(f"  HTTP error: {e}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def should_filter(title):
    title_lower = title.lower()
    for term in FILTER_TERMS:
        if term.lower() in title_lower:
            return True
    return False


def parse_fasta(text):
    entries = []
    header = ""
    seq_lines = []
    for line in text.strip().split('\n'):
        if line.startswith('>'):
            if header:
                entries.append((header, ''.join(seq_lines)))
            header = line[1:].strip()
            seq_lines = []
        else:
            seq_lines.append(line.strip())
    if header:
        entries.append((header, ''.join(seq_lines)))
    return entries


def header_tokens(header):
    """FASTA header → token 集合，用于把请求的 UID（GI 或 accession.version）对照回结果。"""
    return set(t for t in re.split(r'[^A-Za-z0-9_.]+', header) if t)


def main():
    print("=" * 60)
    print("Downloading NCBI Plant Endogenous Viral Elements")
    print(f"Query: {QUERY}")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)

    # Step 1: Search
    total, webenv, query_key = esearch(QUERY)
    if total == 0:
        print("No results found!")
        return

    # Step 2: Paginate through ALL summaries, filter out unwanted
    print(f"\nStep 2: Fetching summaries (paginating through {total} results)...")
    good_ids = []
    filtered_count = 0
    page = 0

    for retstart in range(0, total, SUMMARY_PAGE):
        summaries = esummary_page(webenv, query_key, retstart, SUMMARY_PAGE)
        if not summaries and retstart > 0:
            # retry once
            time.sleep(2)
            summaries = esummary_page(webenv, query_key, retstart, SUMMARY_PAGE)

        for uid, title in summaries:
            if should_filter(title):
                filtered_count += 1
            else:
                good_ids.append(uid)

        page += 1
        if page % 5 == 0 or retstart == 0:
            pct = min(100, int((retstart + SUMMARY_PAGE) / total * 100))
            print(f"  [{pct}%] {min(total, retstart + SUMMARY_PAGE)}/{total} "
                  f"(kept {len(good_ids)}, filtered {filtered_count})")
        time.sleep(SLEEP)

    print(f"\n  Final: {len(good_ids)} kept, {filtered_count} filtered out")

    if not good_ids:
        print("Nothing to download!")
        return

    # Step 3: Download
    print(f"\nStep 3: Downloading {len(good_ids)} sequences...")
    all_entries = []
    failed_ids = []      # efetch 失败/未返回的 UID（重跑清单）

    for i in range(0, len(good_ids), FETCH_BATCH):
        batch = good_ids[i:i + FETCH_BATCH]
        fasta_text = efetch_batch(batch)
        if fasta_text is None:
            # 旧代码静默返回空串 → 整批丢数据且无痕；现在记失败清单
            failed_ids.extend(batch)
            print(f"  [!] efetch FAILED for batch {i // FETCH_BATCH + 1} ({len(batch)} ids) → recorded as failed")
            time.sleep(SLEEP)
            continue
        entries = parse_fasta(fasta_text)
        all_entries.extend(entries)
        # 批内对账：请求的 UID 未出现在返回 header 中 → 记为缺失（可重跑补齐）
        got_tokens = set()
        for header, _seq in entries:
            got_tokens |= header_tokens(header)
        # UID 可能是 GI 号（header 中 gi|UID|）或 accession[.version]（header 中同名 token），
        # 故除精确匹配外，再按去掉版本号的 basename 匹配一次
        got_bases = set(t.split('.')[0] for t in got_tokens)
        missing = [x for x in batch
                   if x not in got_tokens and x.split('.')[0] not in got_bases]
        if missing:
            failed_ids.extend(missing)
            print(f"  [!] {len(missing)}/{len(batch)} requested ids missing in response")
        pct = min(100, int((i + FETCH_BATCH) / len(good_ids) * 100))
        print(f"  [{pct}%] {min(len(good_ids), i + FETCH_BATCH)}/{len(good_ids)} "
              f"(batch: {len(entries)}, total: {len(all_entries)})")
        time.sleep(SLEEP)

    # Step 4: Save
    out_path = os.path.join(OUT_DIR, "plant_ncbi_eve.fasta")
    with open(out_path, 'w', encoding='utf-8') as f:
        for header, seq in all_entries:
            f.write(f">{header}\n")
            for j in range(0, len(seq), 80):
                f.write(seq[j:j + 80] + '\n')

    # ── Step 5: 对账 good_ids vs 成功写入 ──
    n_expected, n_written = len(good_ids), len(all_entries)
    fail_path = os.path.join(OUT_DIR, "ncbi_eve_failed_ids.txt")
    if n_written == n_expected:
        print(f"\n对账通过: 期望 {n_expected} 条 = 实际写入 {n_written} 条")
    else:
        print(f"\n[!] 对账不一致: 期望 {n_expected} 条, 实际写入 {n_written} 条, 差额 {n_expected - n_written}")

    failed_ids = sorted(set(failed_ids))
    if failed_ids or n_written != n_expected:
        with open(fail_path, 'w', encoding='utf-8') as f:
            if failed_ids:
                f.write("\n".join(failed_ids) + "\n")
            if n_written != n_expected:
                f.write(f"# count mismatch: expected={n_expected} written={n_written} "
                        f"diff={n_expected - n_written}\n")
        print(f"失败/缺失 ID {len(failed_ids)} 个 → {fail_path}（重跑该清单即可补齐）")
    elif os.path.exists(fail_path):
        os.remove(fail_path)   # 本次全部成功 → 清掉旧清单，避免误导
        print(f"本次全部成功，已清理旧失败清单 {fail_path}")

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"\n{'=' * 60}")
    print(f"DONE: {len(all_entries)} sequences -> plant_ncbi_eve.fasta ({size_mb:.2f} MB)")
    print(f"Path: {out_path}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
