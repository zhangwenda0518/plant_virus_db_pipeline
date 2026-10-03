#!/usr/bin/env python3
"""
全量提取：381篇new virus候选PDF的所有图片+Figure caption
不做症状判断，全部提取，按论文分目录
"""

import os, re, json, fitz, csv
from pathlib import Path

CANDIDATES_TSV = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\new_virus_candidates.tsv"
BASE_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\7.literature_tracker\pubmed_records")
OUT_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\new_virus_images")
OUT_JSON = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\new_virus_all_figures.json")

os.makedirs(OUT_DIR, exist_ok=True)
MIN_W, MIN_H = 200, 150  # 过滤碎片

# ── 读候选 ──
candidates = []
with open(CANDIDATES_TSV, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter='\t')
    for row in reader:
        if row['HasPDF'].strip() == 'YES':
            candidates.append(row)

print(f"有PDF候选: {len(candidates)} 篇")

# ── 索引PDF ──
pdf_map = {}  # doi → path
doi_to_path = {}
for root, dirs, files in os.walk(BASE_DIR):
    for f in files:
        if not f.endswith('.pdf'):
            continue
        full = os.path.join(root, f)
        name = f.replace('.pdf', '')
        m = re.search(r'(10[._]\d{4,}[._/][^\s]+)', name)
        if m:
            key1 = m.group(1).replace('_', '/')
            key2 = m.group(1).replace('/', '_')
            doi_to_path[key1] = full
            doi_to_path[key2] = full
        pdf_map[f] = full
        pdf_map[name] = full

print(f"Indexed: {len(doi_to_path)} DOI keys, {len(pdf_map)} filename keys")

def find_pdf(cand):
    doi = cand['DOI'].strip()
    # Try exact first, then normalized
    if doi and doi in doi_to_path:
        return doi_to_path[doi]
    if doi:
        doi_underscore = doi.replace('/', '_')
        if doi_underscore in doi_to_path:
            return doi_to_path[doi_underscore]
    # fallback: partial match
    if doi:
        for key, path in list(doi_to_path.items())[:5000]:
            if doi.split('/')[-1] in key or key.split('/')[-1] in doi:
                return path
    # PMID fallback
    pmid = cand['PMID']
    for key, path in pdf_map.items():
        if pmid in key:
            return path
    return None


# ── 提取 ──
all_figures = []
stats = {'processed': 0, 'failed': 0, 'imgs': 0, 'captions': 0}

for i, cand in enumerate(candidates):
    pdf_path = find_pdf(cand)
    if not pdf_path:
        stats['failed'] += 1
        continue
    
    doi = cand['DOI'].strip() or cand['PMID']
    safe_doi = doi.replace('/', '_').replace('\\', '_')[:60]
    paper_dir = OUT_DIR / safe_doi
    os.makedirs(paper_dir, exist_ok=True)
    
    try:
        doc = fitz.open(pdf_path)
        
        # 提取全文本
        all_text = ''
        for pi in range(min(25, len(doc))):
            all_text += doc[pi].get_text() + '\n'
        
        # 找所有Figure caption
        fig_pattern = re.compile(
            r'(?:Fig\.?|Figure)\s*(\d+[a-z]?)\s*[\.\:\s]\s*(.+?)(?=\n\s*(?:Fig\.?|Figure)\s*\d+|'
            r'\n(?:Table|Supplementary|Results|Discussion|Materials|Methods|Introduction|References|Acknowledg)|\Z)',
            re.IGNORECASE | re.DOTALL
        )
        captions = []
        for m in fig_pattern.finditer(all_text):
            captions.append({
                'num': m.group(1),
                'caption': re.sub(r'\s+', ' ', m.group(2).strip())[:400],
            })
        
        # 找每个caption所在的页面并提取图片
        paper_imgs = 0
        caption_pages = set()
        for cap in captions:
            for pi in range(min(25, len(doc))):
                if f'Fig. {cap["num"]}' in doc[pi].get_text() or f'Fig {cap["num"]}' in doc[pi].get_text():
                    caption_pages.add(pi)
                    break
        
        for pn in caption_pages:
            imgs = doc[pn].get_images(full=True)
            for idx, img_info in enumerate(imgs):
                try:
                    base = doc.extract_image(img_info[0])
                    w, h = base.get('width', 0), base.get('height', 0)
                    if w < MIN_W or h < MIN_H:
                        continue
                    
                    ext = base['ext']
                    img_fname = f"p{pn+1}_{idx}.{ext}"
                    img_path = paper_dir / img_fname
                    if not img_path.exists():
                        with open(img_path, 'wb') as f:
                            f.write(base.get('image', b''))
                    
                    paper_imgs += 1
                    stats['imgs'] += 1
                    
                    # 关联最近caption
                    best_cap = ''
                    for cap in captions:
                        if f'Fig. {cap["num"]}' in doc[pn].get_text() or f'Fig {cap["num"]}' in doc[pn].get_text():
                            best_cap = cap['caption']
                            break
                    
                    all_figures.append({
                        'doi': doi,
                        'pmid': cand['PMID'],
                        'title': cand.get('Title', ''),
                        'year': cand.get('Year', ''),
                        'likelihood': cand.get('PhotoLikely', ''),
                        'page': pn + 1,
                        'image': str(img_path.relative_to(OUT_DIR.parent)),
                        'caption': best_cap,
                        'size': f'{w}x{h}',
                    })
                except:
                    pass
        
        stats['captions'] += len(captions)
        stats['processed'] += 1
        doc.close()
        
        if (i + 1) % 30 == 0:
            print(f"  进度: {i+1}/{len(candidates)} | 论文:{stats['processed']} 图片:{stats['imgs']}")
    
    except Exception as e:
        stats['failed'] += 1
        continue

# ── 输出元数据 ──
with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(all_figures, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"处理: {stats['processed']} 篇, 失败: {stats['failed']}")
print(f"总Figure caption: {stats['captions']}")
print(f"总提取图片: {stats['imgs']}")
print(f"涉及论文: {len(set(x['doi'] for x in all_figures))} 篇")

# 按likelihood分组
from collections import Counter
lc = Counter(x['likelihood'] for x in all_figures)
print(f"按PhotoLikely: {dict(lc)}")

print(f"\n元数据: {OUT_JSON}")
print(f"图片目录: {OUT_DIR}")
