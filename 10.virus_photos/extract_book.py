#!/usr/bin/env python3
"""从《100种常见植物病毒病害彩色图鉴》Word文档提取文本和图片"""
import os, sys, json
from docx import Document
from collections import defaultdict

DOCX = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\15587070.docx"
OUT_DIR = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted"
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(os.path.join(OUT_DIR, "images"), exist_ok=True)

doc = Document(DOCX)

# 1. Extract all text paragraphs
print("=== Text paragraphs ===")
with open(os.path.join(OUT_DIR, "full_text.txt"), "w", encoding="utf-8") as f:
    for i, p in enumerate(doc.paragraphs):
        t = p.text.strip()
        if t:
            style = p.style.name if p.style else ""
            f.write(f"[P{i}] [{style}] {t}\n")

# 2. Extract images
print(f"\n=== Extracting {sum(1 for r in doc.part.rels.values() if 'image' in r.reltype)} images ===")
img_count = 0
for rid, rel in doc.part.rels.items():
    if "image" not in rel.reltype:
        continue
    try:
        img_data = rel.target_part.blob
        ext = os.path.splitext(rel.target_ref)[-1] or ".png"
        img_path = os.path.join(OUT_DIR, "images", f"img_{img_count:04d}{ext}")
        with open(img_path, "wb") as f:
            f.write(img_data)
        img_count += 1
    except Exception as e:
        print(f"  Error img {img_count}: {e}")

print(f"  -> {img_count} images saved")

# 3. Show first 200 text lines to understand structure
print("\n=== First 200 text lines ===")
with open(os.path.join(OUT_DIR, "full_text.txt"), "r", encoding="utf-8") as f:
    lines = f.readlines()
    for line in lines[:200]:
        print(line.rstrip())

# 4. Look for patterns: virus names numbered 1-100
print(f"\n=== Total lines: {len(lines)} ===")
print(f"\n=== Sample from middle (line 200-400) ===")
for line in lines[200:400]:
    print(line.rstrip())
