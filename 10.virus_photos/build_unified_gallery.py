#!/usr/bin/env python3
"""
构建统一 Gallery JSON → docs/data/unified_gallery.json
合并: EPPO + DPV + Book + PDF 四个源
+ 复制图片到 docs/data/ 目录
"""

import json, os, shutil, re
from pathlib import Path

DOCS_DATA = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data")
EXTRACTED = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted")
OUT_JSON = DOCS_DATA / "unified_gallery.json"

os.makedirs(DOCS_DATA / "book_images", exist_ok=True)
os.makedirs(DOCS_DATA / "pdf_images", exist_ok=True)


def save_gallery_json():
    gallery = []
    
    # ── 1. EPPO ──
    eppo_path = DOCS_DATA / "eppo_gallery.json"
    if eppo_path.exists():
        with open(eppo_path, 'r', encoding='utf-8') as f:
            eppo = json.load(f)
        for item in eppo:
            if item.get('full'):
                gallery.append({**item, 'source': 'EPPO'})
        print(f"EPPO: {len(eppo)} entries")
    
    # ── 2. DPV ──
    dpv_path = DOCS_DATA / "dpv_gallery.json"
    if dpv_path.exists():
        with open(dpv_path, 'r', encoding='utf-8') as f:
            dpv = json.load(f)
        for item in dpv:
            if item.get('full'):
                gallery.append({**item, 'source': 'DPV'})
        print(f"DPV: {len(dpv)} entries")
    
    # ── 3. Book (专著) - 使用已有的 book_gallery.json ──
    book_gallery_path = DOCS_DATA / "book_gallery.json"
    if book_gallery_path.exists():
        with open(book_gallery_path, 'r', encoding='utf-8') as f:
            book_g = json.load(f)
        for item in book_g:
            if item.get('full'):
                item['source'] = 'Book'
                # 标准化字段
                if 'virus_latin' not in item:
                    item['virus_latin'] = item.get('virus', '')
                gallery.append(item)
        print(f"Book: {len(book_g)} entries (from existing gallery)")
    
    # ── 4. PDF文献 ──
    pdf_meta_path = EXTRACTED / "pdf_images_metadata.json"
    pdf_imgs_dir = EXTRACTED / "pdf_images"
    if pdf_meta_path.exists() and pdf_imgs_dir.exists():
        with open(pdf_meta_path, 'r', encoding='utf-8') as f:
            pdf_meta = json.load(f)
        
        # 复制图片
        imgs_copied = 0
        for f in os.listdir(pdf_imgs_dir):
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                src = pdf_imgs_dir / f
                dst = DOCS_DATA / "pdf_images" / f
                if not dst.exists():
                    shutil.copy2(src, dst)
                imgs_copied += 1
        
        # 构建gallery
        pdf_count = 0
        seen = set()
        for m in pdf_meta:
            img_file = m.get('image_file', '')
            if img_file in seen:
                continue
            seen.add(img_file)
            
            thumb = f"data/pdf_images/{img_file}"
            full = thumb
            
            # 从caption提取病毒名
            caption = m.get('caption', '')
            virus_match = re.search(r'([A-Z][a-z]+(?:\s+[a-z]+){1,4}\s+virus)', caption, re.IGNORECASE)
            virus_latin = virus_match.group(1) if virus_match else ''
            
            gallery.append({
                'code': f"PDF{pdf_count:04d}",
                'virus': virus_latin,
                'virus_latin': virus_latin,
                'photo_id': m.get('figure_num', ''),
                'thumb': thumb,
                'full': full,
                'caption': caption[:300],
                'photographer': '',
                'hosts': [],
                'hosts_latin': [],
                'hosts_cn': '',
                'symptoms': [],
                'parts': [],
                'family': '',
                'page': '',
                'source': 'PDF',   # 统一标签（build_lit_gallery.py 同步为 'PDF'；docs/photos.html 按小写比较，兼容）
                'source_file': m.get('source_file', ''),
                'score': m.get('score', 0),
            })
            pdf_count += 1
        
        print(f"PDF: {pdf_count} entries, {imgs_copied} images")
    
    # 5. Open-i (if exists)
    openi_path = DOCS_DATA / "openi_gallery.json"
    if openi_path.exists():
        with open(openi_path, 'r', encoding='utf-8') as f:
            openi = json.load(f)
        for item in openi:
            if item.get('full'):
                gallery.append({**item, 'source': 'Open-i'})
        print(f"Open-i: {len(openi)} entries")
    
    # ── 写 JSON ──
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(gallery, f, ensure_ascii=False)
    
    # stats
    sources = {}
    for g in gallery:
        s = g.get('source', 'Unknown')
        sources[s] = sources.get(s, 0) + 1
    
    print(f"\n统一Gallery: {len(gallery)} entries")
    for s, c in sorted(sources.items()):
        print(f"  {s}: {c}")
    
    return gallery


if __name__ == '__main__':
    save_gallery_json()
