import csv
import json
import os
import re
import sys

# ── 结果目录解析 ──
# 【可复现性修复】原脚本硬编码 BASE = "/home/zhangwenda/onekp_results" (换机即废)。
# 现改为: 优先环境变量 ONEKP_RESULTS_DIR, 未设置时回退到脚本所在目录。
BASE = os.environ.get("ONEKP_RESULTS_DIR", "").strip() or os.path.dirname(os.path.abspath(__file__))
if not os.path.isdir(BASE):
    sys.exit(
        "❌ 结果目录不存在: {0}\n"
        "   请设置环境变量 ONEKP_RESULTS_DIR 指向 onekp 结果目录 "
        "(应含 onekp_samples_raw.json / onekp_download_links.csv / "
        "onekp_all_samples.csv / onekp_summary.csv)。".format(BASE))
print("结果目录 (BASE): {0}".format(BASE))


def detect_encoding(path):
    """按文件头 BOM/NUL 字节探测编码。

    【修复】Excel/PowerShell 导出的 CSV 常为 UTF-16-LE (带 BOM), 原代码以
    utf-8-sig 读取会 UnicodeDecodeError; 这里先读 4 字节文件头再定编码。
    """
    with open(path, "rb") as fh:
        head = fh.read(4)
    if head.startswith(b"\xff\xfe\x00\x00") or head.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16"          # 带 BOM: codec 自动识别 LE/BE 并吃掉 BOM
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if b"\x00" in head:
        return "utf-16-le"       # 无 BOM 的 UTF-16 (头部含 NUL 字节)
    return "utf-8"


def open_text(path):
    enc = detect_encoding(path)
    return open(path, encoding=enc, newline=""), enc


def load_json(path):
    fh, _ = open_text(path)
    with fh:
        return json.load(fh)


def load_rows(path):
    fh, _ = open_text(path)
    with fh:
        return list(csv.DictReader(fh))


# 1. Check raw JSON
print("=" * 60)
print("1. onekp_samples_raw.json")
raw_json = os.path.join(BASE, "onekp_samples_raw.json")
if not os.path.exists(raw_json):
    print("  ❌ 文件缺失, 跳过: {0}".format(raw_json))
else:
    print("  (编码: {0})".format(detect_encoding(raw_json)))
    d = load_json(raw_json)
    if isinstance(d, list):
        print(f"  Type: list, {len(d)} items")
        print(f"  First item keys: {list(d[0].keys())}")
        for k, v in list(d[0].items())[:10]:
            print(f"    {k}: {str(v)[:120]}")
    elif isinstance(d, dict):
        print(f"  Type: dict, {len(d)} keys")
        for k in list(d.keys())[:5]:
            v = d[k]
            if isinstance(v, dict):
                print(f"  {k}: dict, keys={list(v.keys())[:6]}")
                for k2 in list(v.keys())[:3]:
                    print(f"    {k2}: {str(v[k2])[:120]}")
            elif isinstance(v, list):
                print(f"  {k}: list, len={len(v)}")
                if v:
                    print(f"    first: {str(v[0])[:150]}")
            else:
                print(f"  {k}: {str(v)[:150]}")

# 2. Check download_links.csv - extract mapping
print()
print("=" * 60)
print("2. onekp_download_links.csv - Sample Code -> SRA Accession mapping")
links_csv = os.path.join(BASE, "onekp_download_links.csv")
mapping = {}
if not os.path.exists(links_csv):
    print("  ❌ 文件缺失, 跳过: {0}".format(links_csv))
else:
    print("  (编码: {0})".format(detect_encoding(links_csv)))
    rows = load_rows(links_csv)
    print(f"  Total rows: {len(rows)}")
    if rows:
        print(f"  Columns: {list(rows[0].keys())}")

    # Extract SRA accession from URL
    for r in rows:
        sra_url = r.get("SRA Download", "")
        # Extract ERR/SRR/DRR accession
        m = re.search(r"/([EDS]RR\d+)/", sra_url)
        if m:
            acc = m.group(1)
            mapping[acc] = {
                "sample_code": r["Sample Code"],
                "species": r["Species"],
                "clade": r["Clade"],
            }

    print(f"  Mapped accessions: {len(mapping)}")
    # Show some examples
    for i, (acc, info) in enumerate(list(mapping.items())[:5]):
        print(f"    {acc} -> {info['sample_code']} | {info['species']} | {info['clade']}")

# 3. Check all_samples.csv
print()
print("=" * 60)
print("3. onekp_all_samples.csv")
all_csv = os.path.join(BASE, "onekp_all_samples.csv")
all_rows = None
if not os.path.exists(all_csv):
    print("  ❌ 文件缺失, 跳过: {0}".format(all_csv))
else:
    print("  (编码: {0})".format(detect_encoding(all_csv)))
    all_rows = load_rows(all_csv)
    print(f"  Total rows: {len(all_rows)}")
    if all_rows:
        print(f"  Columns: {list(all_rows[0].keys())}")

# 4. Check summary
print()
print("=" * 60)
print("4. onekp_summary.csv")
summary_csv = os.path.join(BASE, "onekp_summary.csv")
if not os.path.exists(summary_csv):
    print("  ❌ 文件缺失, 跳过: {0}".format(summary_csv))
else:
    print("  (编码: {0})".format(detect_encoding(summary_csv)))
    for r in load_rows(summary_csv):
        print(f"  {r}")

# 5. Count unique clades and families
print()
print("=" * 60)
print("5. Diversity summary")
from collections import Counter

if all_rows is None:
    print("  ❌ 缺少 onekp_all_samples.csv, 跳过统计")
else:
    clades = Counter(r["Clade"] for r in all_rows)
    families = Counter(r["Family"] for r in all_rows)
    orders = Counter(r["Order"] for r in all_rows)
    tissues = Counter(r.get("Tissue", "") for r in all_rows)

    print(f"  Unique clades: {len(clades)}")
    for c, n in clades.most_common(10):
        print(f"    {n:4d}  {c}")
    print(f"  Unique families: {len(families)}")
    print(f"  Unique orders: {len(orders)}")
    print(f"  Unique tissues: {len(tissues)}")
    for t, n in tissues.most_common(10):
        if t:
            print(f"    {n:4d}  {t}")

print()
print("Done!")
