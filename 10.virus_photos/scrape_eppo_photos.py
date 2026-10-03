#!/usr/bin/env python3
"""爬取 EPPO 植物病毒病图片库 — Playwright 版 (含 Caption + Photographer)"""
import re, time, argparse, os
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
import polars as pl

BASE = "https://gd.eppo.int"
LIST = f"{BASE}/photos/virus"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("-o", "--output", default="eppo_virus_photos.tsv")
    p.add_argument("--failed-out", default="eppo_failed_pages.tsv",
                   help="导航失败的 taxon 清单 (taxon/virus/url/错误)")
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--start", type=int, default=0)
    args = p.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()

        # [1] Virus list
        print(f"[1] {LIST}")
        page.goto(LIST, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        items = page.query_selector_all("#listg li a[href*='/taxon/']")
        viruses = []
        seen = set()
        for a in items:
            href = a.get_attribute("href") or ""
            m = re.search(r'/taxon/(\w+)/photos', href)
            if m:
                code = m.group(1)
                name = re.sub(r'\s*\([A-Z0-9]+\)\s*$', '', a.inner_text().strip())
                if code not in seen:
                    seen.add(code)
                    viruses.append((code, name))
        print(f"  -> {len(viruses)} viruses")

        if args.limit > 0:
            viruses = viruses[args.start:args.start + args.limit]
        elif args.start > 0:
            viruses = viruses[args.start:]

        # [2] Scrape each virus
        all_photos = []
        failed_pages = []   # (taxon, virus_name, url, error)：导航失败 → 跳过，防照片错配
        for i, (code, name) in enumerate(viruses):
            url = f"{BASE}/taxon/{code}/photos"
            print(f"[{i+1}/{len(viruses)}] {code} {name[:50]}")
            nav_ok = False
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                nav_ok = True
                page.wait_for_timeout(1500)
                page.wait_for_selector("#portfolio img[src*='/pics/']", timeout=10000)
            except Exception as e:
                err = f"{type(e).__name__}: {e}".replace("\t", " ").replace("\n", " ")[:300]
                if not nav_ok:
                    # goto 失败 → 当前 DOM 仍是上一个 taxon 的页面，
                    # 继续采集会把照片静默错配到别的病毒（审计 D4 P0）→ 跳过并记失败清单
                    print(f"  ! SKIP (navigation failed, no photos collected): {err}")
                    failed_pages.append((code, name, url, err))
                    time.sleep(args.delay)
                    continue
                # 页面已正确加载、只是没有图集元素（如该 taxon 无照片）→ 可安全继续
                print(f"  (no photo elements: {err})")

            items = page.query_selector_all("#portfolio .element")
            photos = []
            for el in items:
                img = el.query_selector("img")
                if not img:
                    continue
                src = img.get_attribute("src") or ""
                if "/pics/" not in src:
                    continue
                pid = re.search(r'/(\d+)\.jpg', src)
                pid = pid.group(1) if pid else ""
                thumb = urljoin(BASE, src)
                full = thumb.replace("220x130", "1024x0")

                # Caption from div.pcap > p (first non-empty <p>)
                caption, photographer = "", ""
                pcap = el.query_selector(".pcap")
                if pcap:
                    ptags = pcap.query_selector_all("p")
                    for ptag in ptags:
                        t = (ptag.inner_text() or "").strip()
                        if t:
                            caption = t
                            break
                    # Photographer from .pcap > small
                    small = pcap.query_selector("small")
                    if small:
                        t = (small.inner_text() or "").strip()
                        photographer = re.sub(r'(?i)courtesy\s*:?\s*', '', t).strip()

                photos.append(dict(eppo_code=code, virus_name=name, photo_id=pid,
                                   thumb_url=thumb, full_url=full,
                                   caption=caption, photographer=photographer,
                                   photo_page=url))
            all_photos.extend(photos)
            wc = sum(1 for x in photos if x["caption"])
            wp = sum(1 for x in photos if x["photographer"])
            print(f"  -> {len(photos)} photos ({wc}c, {wp}p)")
            if photos:
                c = photos[0]['caption'][:70].encode('ascii','replace').decode()
                ph = photos[0]['photographer'][:40].encode('ascii','replace').decode()
                print(f"     [{photos[0]['photo_id']}] {c}")
                print(f"               {ph}")
            time.sleep(args.delay)

        browser.close()

    # 失败清单：始终写出（含表头），避免上一次运行的旧清单造成误读
    with open(args.failed_out, "w", encoding="utf-8", newline="") as f:
        f.write("taxon\tvirus_name\turl\terror\n")
        for code, name, url, err in failed_pages:
            f.write(f"{code}\t{name}\t{url}\t{err}\n")
    if failed_pages:
        print(f"\n[!] 导航失败 {len(failed_pages)} 个 taxon（已跳过，见 {args.failed_out}）:")
        for code, name, url, err in failed_pages[:20]:
            print(f"    {code} {name[:40]} — {err[:100]}")

    if all_photos:
        df = pl.DataFrame(all_photos)
        df.write_csv(args.output, separator='\t')
        nc = sum(1 for x in all_photos if x["caption"])
        np_ = sum(1 for x in all_photos if x["photographer"])
        print(f"\nDone: {len(all_photos)} photos -> {args.output}")
        print(f"  Viruses: {len(set(x['eppo_code'] for x in all_photos))}")
        print(f"  With caption: {nc}, With photographer: {np_}")
    print(f"  Failed taxa (navigation): {len(failed_pages)} -> {args.failed_out}")


if __name__ == "__main__":
    main()
