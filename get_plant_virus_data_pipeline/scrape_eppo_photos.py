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
        for i, (code, name) in enumerate(viruses):
            url = f"{BASE}/taxon/{code}/photos"
            print(f"[{i+1}/{len(viruses)}] {code} {name[:50]}")
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)
                page.wait_for_selector("#portfolio img[src*='/pics/']", timeout=10000)
            except:
                pass

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

    if all_photos:
        df = pl.DataFrame(all_photos)
        df.write_csv(args.output, separator='\t')
        nc = sum(1 for x in all_photos if x["caption"])
        np_ = sum(1 for x in all_photos if x["photographer"])
        print(f"\nDone: {len(all_photos)} photos -> {args.output}")
        print(f"  Viruses: {len(set(x['eppo_code'] for x in all_photos))}")
        print(f"  With caption: {nc}, With photographer: {np_}")


if __name__ == "__main__":
    main()
