#!/usr/bin/env python3
"""
爬取 EPPO Global Database 植物病毒病图片库 (Selenium 版)

数据来源: https://gd.eppo.int/photos/virus
输出: eppo_virus_photos.tsv

使用 Selenium WebDriver 渲染 JS 页面，获取完整元数据 (caption + photographer)。

Usage:
  python scrape_eppo_photos.py -o eppo_virus_photos.tsv --delay 2.0
  python scrape_eppo_photos.py -o eppo_virus_photos.tsv --limit 5 --delay 2.0
"""

import re
import time
import argparse
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import polars as pl

BASE_URL = "https://gd.eppo.int"
VIRUS_LIST_URL = f"{BASE_URL}/photos/virus"


def create_driver(headless=True, browser="chrome"):
    """创建 WebDriver, 优先 Chrome, 回退 Edge"""
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("user-agent=Mozilla/5.0 (compatible; PlantVirusDB/1.0; research)")

    if browser == "edge":
        from selenium.webdriver import Edge, EdgeOptions
        eopts = EdgeOptions()
        if headless:
            eopts.add_argument("--headless=new")
        eopts.add_argument("--no-sandbox")
        eopts.add_argument("--disable-gpu")
        return Edge(options=eopts)

    try:
        return webdriver.Chrome(options=opts)
    except Exception:
        print("  Chrome not found, trying Edge...")
        from selenium.webdriver import Edge, EdgeOptions
        eopts = EdgeOptions()
        if headless:
            eopts.add_argument("--headless=new")
        eopts.add_argument("--no-sandbox")
        return Edge(options=eopts)


def wait_for_element(driver, selector, timeout=10):
    """等待 JS 渲染完成"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return True
    except TimeoutException:
        return False


def scrape_virus_list(driver):
    """用 Selenium 爬取病毒列表"""
    print(f"[1] 加载病毒列表: {VIRUS_LIST_URL}")
    driver.get(VIRUS_LIST_URL)

    # 等待列表渲染
    if not wait_for_element(driver, "#listg li", timeout=15):
        print("  ⚠ 列表加载超时，尝试备用选择器")
        wait_for_element(driver, "a[href*='/taxon/']", timeout=15)

    time.sleep(1)  # extra settle

    viruses = []
    items = driver.find_elements(By.CSS_SELECTOR, "#listg li a[href*='/taxon/'], ul li a[href*='/taxon/']")
    seen = set()
    for link in items:
        href = link.get_attribute('href') or ''
        m = re.search(r'/taxon/(\w+)/photos', href)
        if m:
            code = m.group(1)
            name = link.text.strip()
            name = re.sub(r'\s*\([A-Z0-9]+\)\s*$', '', name)
            if code not in seen:
                seen.add(code)
                viruses.append({"eppo_code": code, "virus_name": name})

    print(f"  -> {len(viruses)} viruses found")
    return viruses


def scrape_photos_page(driver, eppo_code, virus_name):
    """用 Selenium 爬取单个病毒的图片页"""
    url = f"{BASE_URL}/taxon/{eppo_code}/photos"
    driver.get(url)

    # 等待图片网格加载 (Isotope)
    wait_for_element(driver, "#portfolio img[src*='/pics/']", timeout=15)
    time.sleep(0.5)  # allow Isotope to finish layout

    photos = []
    # 找所有 grid-item 或直接找 #portfolio 内的 img
    items = driver.find_elements(By.CSS_SELECTOR, "#portfolio .grid-item, #portfolio a[href*='/pics/']")

    for item in items:
        try:
            # Find image
            try:
                img = item.find_element(By.TAG_NAME, "img")
            except:
                continue

            img_src = img.get_attribute('src') or ''
            if '/pics/' not in img_src:
                continue

            # Photo ID
            m = re.search(r'/(\d+)\.jpg', img_src)
            photo_id = m.group(1) if m else ""

            # Thumb + Full URLs
            thumb_url = img_src
            parent_a = None
            try:
                parent_a = item.find_element(By.TAG_NAME, "a")
            except:
                pass
            if parent_a:
                full_url = parent_a.get_attribute('href') or thumb_url.replace("220x130", "1024x0")
            else:
                full_url = thumb_url.replace("220x130", "1024x0")

            # Caption & Photographer from sibling <p> elements
            caption = ""
            photographer = ""
            # Get wrapper (either .grid-item or the <a> parent)
            wrapper = item
            if item.tag_name == 'img':
                wrapper = item.find_element(By.XPATH, "..")  # parent

            # Find all <p> in the wrapper
            p_elements = []
            try:
                p_elements = wrapper.find_elements(By.TAG_NAME, "p")
            except:
                pass
            # If <a> has no <p>, look at the .grid-item level
            if not p_elements:
                try:
                    grid_wrapper = wrapper.find_element(By.XPATH, "..")
                    p_elements = grid_wrapper.find_elements(By.TAG_NAME, "p")
                except:
                    pass

            for p in p_elements:
                text = (p.text or '').strip()
                if 'courtesy' in text.lower():
                    # Extract photographer name after "Courtesy:"
                    photographer = re.sub(r'(?i)courtesy\s*:?\s*', '', text).strip()
                elif text:
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
        except Exception as e:
            continue

    return photos


def main():
    parser = argparse.ArgumentParser(description="爬取 EPPO 植物病毒病图片库 (Selenium)")
    parser.add_argument("-o", "--output", default="eppo_virus_photos.tsv")
    parser.add_argument("--delay", type=float, default=2.0, help="页面间等待 (秒)")
    parser.add_argument("--limit", type=int, default=0, help="限制病毒数 (0=全部)")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口")
    args = parser.parse_args()

    driver = create_driver(headless=not args.no_headless)

    try:
        viruses = scrape_virus_list(driver)
        if args.limit > 0:
            viruses = viruses[args.start:args.start + args.limit]
        elif args.start > 0:
            viruses = viruses[args.start:]

        all_photos = []
        for i, v in enumerate(viruses):
            code = v["eppo_code"]
            name = v["virus_name"]
            print(f"[{i+1}/{len(viruses)}] {code} — {name[:60]}")
            photos = scrape_photos_page(driver, code, name)
            all_photos.extend(photos)
            print(f"  -> {len(photos)} photos")
            if photos:
                for p in photos[:2]:
                    c = p['caption'][:80] if p['caption'] else '(no caption)'
                    ph = p['photographer'][:40] if p['photographer'] else '(no photographer)'
                    print(f"     [{p['photo_id']}] caption={c}")
                    print(f"               photographer={ph}")
            time.sleep(args.delay)

        if all_photos:
            df = pl.DataFrame(all_photos)
            df.write_csv(args.output, separator='\t')
            n_cap = sum(1 for p in all_photos if p['caption'])
            n_phot = sum(1 for p in all_photos if p['photographer'])
            print(f"\nDone: {len(all_photos)} photos -> {args.output}")
            print(f"  Viruses: {len(set(p['eppo_code'] for p in all_photos))}")
            print(f"  With caption: {n_cap}, With photographer: {n_phot}")
        else:
            print("\nNo photos captured")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
