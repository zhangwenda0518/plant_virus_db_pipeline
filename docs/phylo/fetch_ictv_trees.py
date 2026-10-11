#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 ICTV Report 各科章节 resources 页里的官方系统发育树文件。

ICTV 每个科的 resources 页（/report/chapter/<fam>/<fam>/resources）挂着该科
报告插图对应的 **最大似然树（Newick）** 与 **比对文件**。这是官方发布的、
真正二分叉的分子树，和我们自己按分类阶元拼的 taxonomy_tree.json 是两回事。

用法：
    # 只发现，不下载（写 manifest）
    python fetch_ictv_trees.py --discover

    # 下载树文件（默认只下树，不下比对）
    python fetch_ictv_trees.py --download

    # 连比对一起下
    python fetch_ictv_trees.py --download --with-alignments

数据来源：ICTV Report (https://ictv.global/report)，公开资源。
"""

import argparse
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://ictv.global"
CHAPTER_URL = BASE + "/report/chapter/{slug}/{slug}/resources"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "ictv_raw")
MANIFEST = os.path.join(HERE, "ictv_raw", "manifest.json")
TREE_JSON = os.path.join(HERE, "taxonomy_tree.json")

# 注意：ICTV 页面里文件链接有三种写法，必须都覆盖
#   相对：href="/sites/default/files/report_files/xxx.treefile.txt"
#   绝对：href="https://ictv.global/sites/default/files/report_files/xxx.treefile.txt"
#   带前导空格：href=" /sites/default/files/report_files/ONSR.Tospo.Fig3.treefile.txt"
LINK_RE = re.compile(
    r'href="\s*((?:https?://ictv\.global)?/sites/default/files/[^"?#]+)"', re.I)

# ICTV 各代报告的文件命名很不统一，只能按文件名里的关键词判类：
#   OPSR.Alphaflexi.Fig3.Replicase.aa.tree.nwk       -> 树
#   OSD.Gem.Fig3.v3.treefile.txt                     -> 树
#   ORTD.Caulimo.Fig4..v9_treefile.txt               -> 树
#   ONSR.Fimo.Fig3_.v4.RNA1 newick.txt               -> 树（名字里带空格）
#   OPSR.Seco.Fig4.v10.align.txt.txt                 -> 比对
#   OPSR.Alphaflexi.Fig3.Replicase.aa.align_renamed.FST -> 比对
TREE_HINT = re.compile(r"treefile|newick|contree|\.nwk|\.tre\b|_tree", re.I)
ALIGN_HINT = re.compile(r"align|\.fst|\.fasta|\.fas\b|\.aln\b|\.faa|\.fna|\.phy\b",
                        re.I)


def http_get(url, timeout=40, retries=3):
    """取回一个 URL 的字节内容（不做 gzip 协商，避免手工解压）。"""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                return r.status, data, r.geturl()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (404, 403):
                return e.code, b"", url
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    return 0, b"", url


def plant_families():
    """从已建好的分类树里取植物病毒科名单。"""
    with open(TREE_JSON, encoding="utf-8") as fh:
        meta = json.load(fh)["meta"]
    return sorted(meta["plant_family_list"])


def classify(path):
    """判断一个文件是树还是比对。返回 'tree' / 'align' / None。

    先判树：因为比对文件名里常带 'align'，而树文件名偶尔也含 'aa'/'nt' 之类，
    但绝不会同时含 treefile/newick 与 align，所以顺序是安全的。
    """
    base = os.path.basename(path)
    if TREE_HINT.search(base):
        return "tree"
    if ALIGN_HINT.search(base):
        return "align"
    return None


def quote_url(u):
    """把文件名里的空格等字符转义，但保留已有的 %XX 与 URL 结构字符。"""
    return urllib.parse.quote(u, safe=":/?&=#%+@,;~()[]!$'*")


def scrape_family(fam, verbose=True):
    """抓一个科的 resources 页，返回 {status, files:[{kind,url,name,fig,label}]}。"""
    slug = fam.lower()
    url = CHAPTER_URL.format(slug=slug)
    status, body, final = http_get(url)
    if status != 200 or not body:
        return {"family": fam, "chapter_url": url, "http": status, "files": []}

    page = body.decode("utf-8", "replace")

    # 记录每个文件链接前面最近的 "Figure N" 文字，作为该文件的图号
    files = []
    seen = set()
    for m in LINK_RE.finditer(page):
        raw = m.group(1)
        # 统一成绝对 URL（页面里相对/绝对两种写法都有）
        abspath = raw if raw.lower().startswith("http") else BASE + raw
        if abspath in seen:
            continue
        seen.add(abspath)
        kind = classify(abspath)
        if not kind:
            continue
        head = page[max(0, m.start() - 600):m.start()]
        figs = re.findall(r"Figure\s*(\d+)", head, re.I)
        fig = figs[-1] if figs else ""
        files.append({
            "kind": kind,
            "name": os.path.basename(urllib.parse.unquote(abspath)),
            "path": urllib.parse.urlparse(abspath).path,
            "url": quote_url(abspath),
            "fig": fig,
        })

    if verbose:
        ntree = sum(1 for f in files if f["kind"] == "tree")
        naln = sum(1 for f in files if f["kind"] == "align")
        print("  %-22s http=%s  tree=%d align=%d" % (fam, status, ntree, naln))
    return {"family": fam, "chapter_url": url, "http": status, "files": files}


def discover(delay=0.8):
    fams = plant_families()
    print("植物病毒科共 %d 个，开始抓 resources 页\n" % len(fams))
    out = []
    for i, fam in enumerate(fams, 1):
        print("[%2d/%d]" % (i, len(fams)), end=" ")
        out.append(scrape_family(fam))
        if i < len(fams):
            time.sleep(delay)
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump({
            "source": "ICTV Report chapter resources pages",
            "base": BASE,
            "families": out,
        }, fh, ensure_ascii=False, indent=1)
    return out


def download(with_alignments=False, delay=0.4):
    if not os.path.exists(MANIFEST):
        print("manifest 不存在，先跑 --discover", file=sys.stderr)
        return 1
    with open(MANIFEST, encoding="utf-8") as fh:
        man = json.load(fh)

    os.makedirs(RAW_DIR, exist_ok=True)
    ok = skip = fail = 0
    for entry in man["families"]:
        fam = entry["family"]
        famdir = os.path.join(RAW_DIR, fam)
        for f in entry["files"]:
            if f["kind"] == "align" and not with_alignments:
                continue
            dest = os.path.join(famdir, f["name"])
            f["local"] = os.path.relpath(dest, HERE).replace("\\", "/")
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                skip += 1
                continue
            os.makedirs(famdir, exist_ok=True)
            status, body, _ = http_get(f["url"])
            if status == 200 and body:
                with open(dest, "wb") as fh:
                    fh.write(body)
                f["bytes"] = len(body)
                ok += 1
                print("  ok   %-18s %-46s %8d B" % (fam, f["name"], len(body)))
            else:
                f["error"] = status
                fail += 1
                print("  FAIL %-18s %-46s http=%s" % (fam, f["name"], status))
            time.sleep(delay)

    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    print("\n下载完成：新增 %d，跳过 %d，失败 %d" % (ok, skip, fail))
    return 0


def summary():
    if not os.path.exists(MANIFEST):
        print("manifest 不存在", file=sys.stderr)
        return 1
    with open(MANIFEST, encoding="utf-8") as fh:
        man = json.load(fh)
    have_tree = [e for e in man["families"] if any(f["kind"] == "tree" for f in e["files"])]
    have_aln = [e for e in man["families"] if any(f["kind"] == "align" for f in e["files"])]
    ntree = sum(1 for e in man["families"] for f in e["files"] if f["kind"] == "tree")
    naln = sum(1 for e in man["families"] for f in e["files"] if f["kind"] == "align")
    print("科总数            %d" % len(man["families"]))
    print("有树文件的科      %d" % len(have_tree))
    print("有比对文件的科    %d" % len(have_aln))
    print("树文件总数        %d" % ntree)
    print("比对文件总数      %d" % naln)
    missing = [e["family"] for e in man["families"]
               if not any(f["kind"] == "tree" for f in e["files"])]
    if missing:
        print("\n无树文件的科（%d）：" % len(missing))
        for f in missing:
            print("  " + f)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="抓 resources 页，写 manifest")
    ap.add_argument("--download", action="store_true", help="按 manifest 下载文件")
    ap.add_argument("--with-alignments", action="store_true", help="连比对文件一起下")
    ap.add_argument("--summary", action="store_true", help="打印 manifest 概况")
    ap.add_argument("--delay", type=float, default=0.8, help="请求间隔秒数")
    a = ap.parse_args()
    if a.discover:
        discover(delay=a.delay)
        return summary()
    if a.download:
        return download(with_alignments=a.with_alignments, delay=a.delay)
    if a.summary:
        return summary()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
