#!/usr/bin/env python3
"""
爬取 EPPO Global Database 植物病毒病图片库

数据来源: https://gd.eppo.int/photos/virus
输出: eppo_virus_photos.tsv

字段:
  EPPO_Code     EPPO 病毒代码
  Virus_Name    病毒学名
  Virus_Name_CN 病毒中文名 (如有)
  Photo_ID      图片ID
  Thumb_URL     缩略图 URL
  Full_URL      全尺寸图 URL
  Caption       图片说明 (含症状/宿主信息)
  Photographer  拍摄者
  Photo_Page    图片页面 URL
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import os
import argparse
from urllib.parse import urljoin
import polars as pl

BASE_URL = "https://gd.eppo.int"
VIRUS_LIST_URL = f"{BASE_URL}/photos/virus"


def get_soup(url, retries=3):
    """获取页面 BeautifulSoup，带重试"""
    for i in range(retries):
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (compatible; PlantVirusDB/1.0; research use)"
            })
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if i == retries - 1:
                print(f"  ✗ Failed: {url} — {e}")
                return None
            time.sleep(2)
    return None


def scrape_virus_list():
    """爬取病毒列表页，获取所有 EPPO 代码和病毒名"""
    print(f"[1] 爬取病毒列表: {VIRUS_LIST_URL}")
    soup = get_soup(VIRUS_LIST_URL)
    if not soup:
        return []

    viruses = []
    # 列表在 #listg ul li 中
    list_items = soup.select("#listg li, ul li a[href*='/taxon/']")
    seen = set()
    for item in list_items:
        if item.name == 'a':
            link = item
        else:
            link = item.find('a')
        if not link:
            continue
        href = link.get('href', '')
        m = re.search(r'/taxon/(\w+)/photos', href)
        if m:
            code = m.group(1)
            name = link.get_text(strip=True)
            # 清理名称: 去掉末尾的 (CODE)
            name = re.sub(r'\s*\([A-Z0-9]+\)\s*$', '', name)
            if code not in seen:
                seen.add(code)
                viruses.append({"eppo_code": code, "virus_name": name})

    print(f"  → {len(viruses)} 个病毒条目")
    return viruses


def scrape_photos_page(eppo_code, virus_name):
    """爬取单个病毒的图片页

    HTML structure (from live site):
      <div class="grid-item">
        <a href="/media/.../1024x0/NNNN.jpg"><img src="/media/.../220x130/NNNN.jpg"></a>
        <p>caption text (optional)</p>
        <p><strong>Courtesy:</strong> Photographer Name</p>
      </div>
    """
    url = f"{BASE_URL}/taxon/{eppo_code}/photos"
    soup = get_soup(url)
    if not soup:
        return []

    photos = []
    # Each photo is in a .grid-item div
    grid_items = soup.select(".grid-item")
    if not grid_items:
        # Fallback: find all img tags with taxon path
        grid_items = soup.find_all('img', src=re.compile(r'/pics/'))

    for item in grid_items:
        # Find the image - either item itself or child
        if item.name == 'img':
            img = item
        else:
            img = item.find('img')
        if not img:
            continue

        img_src = img.get('src', '')
        if '/pics/' not in img_src:
            continue

        # Extract photo ID from filename (/NNNN.jpg)
        photo_id = re.search(r'/(\d+)\.jpg', img_src)
        photo_id = photo_id.group(1) if photo_id else ""

        # Thumb URL
        thumb_url = urljoin(BASE_URL, img_src)

        # Full-res URL: find parent <a> href, or replace 220x130 with 1024x0
        parent_a = img.find_parent('a') if item.name != 'img' else None
        if parent_a and parent_a.get('href'):
            full_url = urljoin(BASE_URL, parent_a['href'])
        else:
            full_url = thumb_url.replace("220x130", "1024x0")

        # Parse caption and courtesy from <p> elements
        caption = ""
        photographer = ""
        wrapper = item if item.name != 'img' else item.parent
        if wrapper:
            for p in wrapper.find_all('p'):
                text = p.get_text(strip=True)
                strong = p.find('strong')
                if strong and 'courtesy' in strong.get_text().lower():
                    photographer = text.replace(strong.get_text(), '').strip().lstrip(':').strip()
                else:
                    if text and 'courtesy' not in text.lower():
                        caption = text

        photos.append({
            "eppo_code": eppo_code,
            "virus_name": virus_name,
            "photo_id": photo_id,
            "thumb_url": thumb_url,
            "full_url": full_url,
            "caption": caption,
            "photographer": photographer,
            "photo_page": url
        })

    return photos


def main():
    parser = argparse.ArgumentParser(description="爬取 EPPO 植物病毒病图片库")
    parser.add_argument("-o", "--output", default="eppo_virus_photos.tsv", help="输出文件")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔 (秒)")
    parser.add_argument("--limit", type=int, default=0, help="限制爬取病毒数 (0=全部)")
    parser.add_argument("--start", type=int, default=0, help="从第几个病毒开始")
    args = parser.parse_args()

    viruses = scrape_virus_list()
    if args.limit > 0:
        viruses = viruses[args.start:args.start + args.limit]
    elif args.start > 0:
        viruses = viruses[args.start:]

    all_photos = []
    for i, v in enumerate(viruses):
        code = v["eppo_code"]
        name = v["virus_name"]
        print(f"[{i+1}/{len(viruses)}] {code} — {name[:60]}")
        photos = scrape_photos_page(code, name)
        all_photos.extend(photos)
        print(f"  → {len(photos)} photos")
        if photos:
            # Show sample
            for p in photos[:2]:
                print(f"     [{p['photo_id']}] {p['caption'][:80]}")
        time.sleep(args.delay)

    if all_photos:
        df = pl.DataFrame(all_photos)
        df.write_csv(args.output, separator='\t')
        print(f"\nDone: {len(all_photos)} photos -> {args.output}")
        print(f"  Viruses: {len(set(p['eppo_code'] for p in all_photos))}")
    else:
        print("\nNo photos captured")


if __name__ == "__main__":
    main()
