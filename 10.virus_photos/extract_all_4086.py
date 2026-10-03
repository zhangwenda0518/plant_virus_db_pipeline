#!/usr/bin/env python3
"""全量提取：全部4086篇PDF的图片 → 单一目录。支持断点续跑。"""
import os, re, json, fitz
from pathlib import Path

BASE_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\7.literature_tracker\pubmed_records")
OUT_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images")
OUT_JSON = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images.json")
PROGRESS = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_progress.txt")
FAILED = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_failed.txt")

os.makedirs(OUT_DIR, exist_ok=True)
MIN_W, MIN_H = 100, 80


def _write_failed(failed):
    """失败清单：这些 PDF 不写入 done，重跑本脚本会自动重试（审计 D4 断点污染修复）。"""
    try:
        with open(FAILED, 'w', encoding='utf-8') as f:
            f.write("# 解析失败、未标记 done 的 PDF（重跑本脚本即可重试）\n")
            for p, err in failed:
                f.write(f"{p}\t{err}\n")
    except Exception as e:
        print(f"  (write failed list error: {e})")

# ── 找所有PDF ──
all_pdfs = []
for root, dirs, files in os.walk(BASE_DIR):
    for f in files:
        if f.endswith('.pdf'):
            all_pdfs.append(os.path.join(root, f))
print(f"总PDF: {len(all_pdfs)}")

# ── 读已有进度(断点续跑) ──
done = set()
if PROGRESS.exists():
    with open(PROGRESS) as f:
        done = set(line.strip() for line in f)
    print(f"已完成: {len(done)}")

# ── 读已有元数据 ──
existing_records = []
if OUT_JSON.exists():
    with open(OUT_JSON) as f:
        existing_records = json.load(f)
    print(f"已有元数据: {len(existing_records)} 条")

# ── 处理 ──
stats = {'ok': len(done), 'fail': 0, 'imgs': len(existing_records), 'tiny': 0}
records = existing_records.copy()
failed = []   # (pdf_path, error)：解析失败的 PDF 不标 done，重跑可重试

for i, pdf_path in enumerate(all_pdfs):
    if pdf_path in done:
        continue
    
    # 从文件名提取标识
    fname = os.path.basename(pdf_path)
    doi_match = re.search(r'(10[._]\d{4,}[._/][^\s]+)', fname.replace('.pdf', ''))
    prefix = doi_match.group(1).replace('/', '_')[:60] if doi_match else fname[:60]
    
    try:
        doc = fitz.open(pdf_path)
        for pn in range(len(doc)):
            imgs = doc[pn].get_images(full=True)
            if not imgs: continue
            for idx, img_info in enumerate(imgs):
                try:
                    base = doc.extract_image(img_info[0])
                    w, h = base.get('width', 0), base.get('height', 0)
                    if w < MIN_W or h < MIN_H:
                        stats['tiny'] += 1; continue
                    
                    ext = base['ext']
                    img_fname = f"{prefix}_p{pn+1}_{idx}.{ext}"
                    fpath = OUT_DIR / img_fname
                    if not fpath.exists():
                        with open(fpath, 'wb') as f:
                            f.write(base.get('image', b''))
                    
                    stats['imgs'] += 1
                    records.append({
                        'doi_prefix': prefix, 'file': img_fname,
                        'page': pn + 1, 'size': f'{w}x{h}',
                        'pdf': fname[:80]
                    })
                except: pass
        doc.close()
        stats['ok'] += 1
        done.add(pdf_path)          # 仅成功才进 done（失败重跑可重试，审计 D4）
    except Exception as e:
        stats['fail'] += 1
        failed.append((pdf_path, f"{type(e).__name__}: {e}"[:200]))
    
    # 进度
    if stats['ok'] % 100 == 0:
        print(f"  {stats['ok']}/{len(all_pdfs)} | imgs:{stats['imgs']} tiny:{stats['tiny']} fail:{stats['fail']}")
        with open(PROGRESS, 'w') as f:
            for d in done: f.write(d + '\n')
        with open(OUT_JSON, 'w') as f:
            json.dump(records, f, ensure_ascii=False)
        _write_failed(failed)

# ── 最终输出 ──
with open(PROGRESS, 'w') as f:
    for d in done: f.write(d + '\n')
with open(OUT_JSON, 'w') as f:
    json.dump(records, f, ensure_ascii=False)
_write_failed(failed)

npapers = len(set(r['doi_prefix'] for r in records))
print(f"\n完成: OK={stats['ok']} fail={stats['fail']}")
print(f"图片总数: {stats['imgs']} (碎片跳过: {stats['tiny']})")
print(f"涉及论文: {npapers}")
print(f"失败(未标done, 重跑会重试): {len(failed)} -> {FAILED}")
print(f"输出: {OUT_DIR}")
