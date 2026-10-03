#!/usr/bin/env python3
"""Open-i NIH 植物病毒图片爬虫"""
import requests, json, time, re, pathlib, os

API = "https://openi.nlm.nih.gov/api/search"
BASE_IMG = "https://openi.nlm.nih.gov"
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs/data/openi_gallery.json"

# 植物病毒检索词
VIRUS_TERMS = [
    "tobacco mosaic virus symptoms",
    "tomato spotted wilt virus symptoms",
    "cucumber mosaic virus symptoms",
    "potato virus Y symptoms",
    "tomato yellow leaf curl virus symptoms",
    "plum pox virus symptoms",
    "bean common mosaic virus symptoms",
    "papaya ringspot virus symptoms",
    "barley yellow dwarf virus symptoms",
    "citrus tristeza virus symptoms",
    "maize streak virus symptoms",
    "rice dwarf virus symptoms",
    "sugarcane mosaic virus symptoms",
    "wheat streak mosaic virus symptoms",
    "peanut stunt virus symptoms",
    "squash mosaic virus symptoms",
    "alfalfa mosaic virus symptoms",
    "grapevine fanleaf virus symptoms",
    "lettuce mosaic virus symptoms",
    "cauliflower mosaic virus symptoms",
    "sweet potato virus symptoms",
    "cassava mosaic virus symptoms",
    "cowpea mosaic virus symptoms",
    "turnip mosaic virus symptoms",
    "watermelon mosaic virus symptoms",
    "zucchini yellow mosaic virus symptoms",
    "brome mosaic virus symptoms",
    "carnation mottle virus symptoms",
    "potato leafroll virus symptoms",
    "southern bean mosaic virus symptoms",
    "tobacco rattle virus symptoms",
    "tobacco ringspot virus symptoms",
    "tomato ringspot virus symptoms",
    "arabis mosaic virus symptoms",
    "cherry leaf roll virus symptoms",
    "raspberry ringspot virus symptoms",
    "tomato bushy stunt virus symptoms",
    "carnation ringspot virus symptoms",
    "apple chlorotic leaf spot virus symptoms",
    "potato mop-top virus symptoms",
    "beet necrotic yellow vein virus symptoms",
    "rice stripe virus symptoms",
    "plant virus leaf symptoms",
    "virus infected plant leaf",
    "viral disease crop plants",
    "mosaic virus plant symptoms",
    "geminivirus symptoms",
    "potyvirus symptoms plant",
    "tobamovirus symptoms",
]

# 联系邮箱：取自环境变量 NCBI_EMAIL（与其它模块统一），不再用假邮箱 contact@example.com
CONTACT_EMAIL = os.environ.get("NCBI_EMAIL", "").strip()
if not CONTACT_EMAIL:
    print("[WARN] 环境变量 NCBI_EMAIL 未设置：User-Agent 将标注 contact 未配置（爬取外部站点建议配置真实联系邮箱）")
HEADERS = {'User-Agent': 'PlantVirusDB/1.0 (research; '
           + (CONTACT_EMAIL if CONTACT_EMAIL else 'contact not configured') + ')'}

def search_openi(query, max_results=999):
    """搜索并获取所有结果"""
    all_results = []
    for start in range(1, max_results, 100):
        params = {'query': query, 'it': 'p', 'n': 100, 'm': start}
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=90)
            r.raise_for_status()
            data = r.json()
            items = data.get('list', [])
            if not items:
                break
            all_results.extend(items)
            if len(items) < 100:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"  Error at {start}: {e}")
            break
    return all_results


def is_plant_related(item):
    """判断是否为植物病毒相关"""
    title = (item.get('title') or '').lower()
    mesh = str(item.get('MeSH', '')).lower()
    journal = (item.get('journal_title') or '').lower()
    text = title + ' ' + mesh + ' ' + journal

    plant_keywords = ['plant', 'leaf', 'leaves', 'crop', 'tomato', 'tobacco', 'potato',
                      'wheat', 'rice', 'maize', 'soybean', 'cucumber', 'pepper', 'citrus',
                      'apple', 'grape', 'bean', 'pea', 'cassava', 'arabidopsis',
                      'nicotiana', 'solanum', 'brassica', 'agro']
    virus_keywords = ['virus', 'viral', 'viroid', 'mosaic', 'geminivirus',
                      'potyvirus', 'tobamovirus', 'potexvirus', 'cucumovirus']

    plant_score = sum(1 for k in plant_keywords if k in text)
    virus_score = sum(1 for k in virus_keywords if k in text)

    return plant_score >= 1 and virus_score >= 1


def main():
    all_photos = []
    seen_pmc = set()

    for i, term in enumerate(VIRUS_TERMS):
        print(f"[{i+1}/{len(VIRUS_TERMS)}] {term[:60]}")
        results = search_openi(term, 200)

        plant_related = 0
        for item in results:
            uid = item.get('uid', '')
            pmc = item.get('pmcid', '')
            img = item.get('imgLarge', '')
            if not img:
                continue
            if pmc in seen_pmc:
                continue
            seen_pmc.add(pmc)

            if not is_plant_related(item):
                continue
            plant_related += 1

            img_url = BASE_IMG + img
            thumb_url = BASE_IMG + (item.get('imgThumb') or img)
            title = item.get('title', '')
            journal = item.get('journal_title', '')
            mesh = str(item.get('MeSH', '') or '')[:200]
            pmc_url = item.get('pmc_url', '')

            all_photos.append({
                'uid': uid,
                'pmcid': pmc,
                'title': title,
                'journal': journal,
                'mesh': str(mesh or '')[:200],
                'thumb': thumb_url,
                'full': img_url,
                'pmc_url': pmc_url,
                'source': 'Open-i NIH',
                'virus': term,
                'virus_latin': term,
                'hosts': [],
                'symptoms': [],
                'parts': [],
                'caption': title[:200],
                'photographer': '',
                'code': 'OPENI',
                'photo_id': uid,
                'page': pmc_url
            })

        print(f"  -> {len(results)} results, {plant_related} plant-related, total {len(all_photos)}")
        time.sleep(0.8)

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(all_photos, f, ensure_ascii=False)

    print(f"\nDone: {len(all_photos)} photos -> {OUT}")
    print(f"Unique PMCIDs: {len(set(p['pmcid'] for p in all_photos))}")


if __name__ == '__main__':
    main()
