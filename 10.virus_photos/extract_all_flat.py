#!/usr/bin/env python3
"""
全量提取：4086篇PDF → 单一目录
- 扫描 BASE_DIR 下所有 .pdf 文件
- DOI 从文件名正则提取
- 断点续跑：输出目录中已有该 DOI 开头的文件则跳过
- 最小尺寸 100×80
"""

import os, re, json, fitz
from pathlib import Path

BASE_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\7.literature_tracker\pubmed_records")
OUT_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images")
OUT_JSON = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images.json")

os.makedirs(OUT_DIR, exist_ok=True)
MIN_W, MIN_H = 100, 80
DOI_RE = re.compile(r'(10[._]\d{4,}[._/][^\s]+)')

# ── 加载已有文件的 DOI 集合（断点续跑） ──
print("扫描已有输出文件（断点续跑）...")
existing_dois = set()
doi_key_re = re.compile(r'^(10[._]\d{4,}[._/][^\s/\\]+)_p\d+_\d+\.')
for f in os.listdir(OUT_DIR):
    m = doi_key_re.match(f)
    if m:
        key = m.group(1).replace('_', '/')
        existing_dois.add(key)

print(f"已有 {len(existing_dois)} 篇论文的图片在输出目录中")

# ── 收集所有 PDF ──
print("扫描 PDF 文件...")
all_pdfs = []  # (pdf_path, doi)
for root, dirs, files in os.walk(BASE_DIR):
    for f in files:
        if not f.endswith('.pdf'):
            continue
        full = os.path.join(root, f)
        name = f.replace('.pdf', '')
        m = DOI_RE.search(name)
        if m:
            doi = m.group(1).replace('_', '/')
            all_pdfs.append((full, doi))

total = len(all_pdfs)
print(f"找到 {total} 个 PDF")

# ── 过滤已处理的 ──
pending = [(p, d) for p, d in all_pdfs if d not in existing_dois]
print(f"已处理 {total - len(pending)} 篇，待处理 {len(pending)} 篇")

# ── 处理 ──
all_records = []
# 加载已有 JSON（如果存在）
if OUT_JSON.exists():
    try:
        with open(OUT_JSON, 'r', encoding='utf-8') as f:
            all_records = json.load(f)
        print(f"加载已有 JSON 记录: {len(all_records)} 条")
    except:
        print("JSON 文件损坏，从头开始")

stats = {'ok': 0, 'fail': 0, 'skip': 0, 'imgs': len(all_records), 'tiny': 0}

START_STR = f"{len(existing_dois):,}" if existing_dois else "0"
print(f"\n开始提取 (已有 {START_STR} 篇，剩余 {len(pending)} 篇)...")

for i, (pdf_path, doi) in enumerate(pending):
    safe = doi.replace('/', '_').replace('\\', '_')[:80]
    
    try:
        doc = fitz.open(pdf_path)
        paper_imgs = 0
        
        for pn in range(len(doc)):
            page = doc[pn]
            imgs = page.get_images(full=True)
            if not imgs:
                continue
            
            for idx, img_info in enumerate(imgs):
                try:
                    base = doc.extract_image(img_info[0])
                    w, h = base.get('width', 0), base.get('height', 0)
                    if w < MIN_W or h < MIN_H:
                        stats['tiny'] += 1
                        continue
                    
                    ext = base['ext']
                    fname = f"{safe}_p{pn+1}_{idx}.{ext}"
                    fpath = OUT_DIR / fname
                    if not fpath.exists():
                        with open(fpath, 'wb') as f:
                            f.write(base.get('image', b''))
                    
                    stats['imgs'] += 1
                    paper_imgs += 1
                    all_records.append({
                        'doi': doi,
                        'file': fname,
                        'page': pn + 1,
                        'size': f'{w}x{h}',
                    })
                except:
                    pass
        
        doc.close()
        stats['ok'] += 1
        
        if stats['ok'] % 100 == 0:
            print(f"  已处理 {stats['ok']}/{len(pending)} | OK:{stats['ok']} fail:{stats['fail']} imgs:{stats['imgs']} tiny:{stats['tiny']}")
    
    except Exception as e:
        stats['fail'] += 1
        if stats['fail'] <= 5:
            print(f"  失败: {pdf_path} → {e}")

# ── 输出 ──
with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(all_records, f, ensure_ascii=False)

npapers = len(set(r['doi'] for r in all_records))
print(f"\n{'='*60}")
print(f"完成: OK={stats['ok']} fail={stats['fail']} skip={stats['skip']}")
print(f"总图片: {stats['imgs']} 张 (跳过碎片: {stats['tiny']})")
print(f"涉及论文: {npapers} 篇")
print(f"输出目录: {OUT_DIR}")
print(f"JSON:     {OUT_JSON}")
