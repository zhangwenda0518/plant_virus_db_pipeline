#!/usr/bin/env python3
"""分类：彩色→color/ 黑白→grayscale/（不删除，只移动）"""
import os, json, shutil
from pathlib import Path
from PIL import Image

IMG_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images")
META_JSON = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images.json")

COLOR_DIR = IMG_DIR / 'color'
GRAY_DIR = IMG_DIR / 'grayscale'
os.makedirs(COLOR_DIR, exist_ok=True)
os.makedirs(GRAY_DIR, exist_ok=True)

THRESHOLD = 8
GRAY_RATIO = 0.95
SAMPLE_MAX = 5000

def is_grayscale(img_path):
    try:
        img = Image.open(img_path)
        if img.mode in ('L', '1'):
            img.close(); return True
        if img.mode not in ('RGB', 'RGBA', 'P'):
            img.close(); return True  # 未知模式按黑白处理
        img = img.convert('RGB')
        w, h = img.size
        total = w * h
        step = max(1, total // SAMPLE_MAX) if total > SAMPLE_MAX else 1
        
        gray = 0; sampled = 0
        pixels = img.load()
        row_step = max(1, step // max(1, w // 100)) if step > 1 else 1
        for y in range(0, h, row_step):
            for x in range(0, w, step if step > 1 else 1):
                r, g, b = pixels[x, y]
                if abs(r-g) < THRESHOLD and abs(r-b) < THRESHOLD and abs(g-b) < THRESHOLD:
                    gray += 1
                sampled += 1
        img.close()
        return gray / max(sampled, 1) >= GRAY_RATIO
    except:
        return True  # 读不了归黑白

# ── 扫描（只处理当前目录下的文件，跳过子目录） ──
files = [f for f in sorted(IMG_DIR.iterdir()) if f.is_file() and f.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.bmp','.webp')]
print(f"待分类: {len(files)}")

color_list, gray_list = [], []
for i, fpath in enumerate(files):
    if is_grayscale(fpath):
        shutil.move(str(fpath), str(GRAY_DIR / fpath.name))
        gray_list.append(fpath.name)
    else:
        shutil.move(str(fpath), str(COLOR_DIR / fpath.name))
        color_list.append(fpath.name)
    
    if (i + 1) % 5000 == 0:
        print(f"  {i+1}/{len(files)} | color:{len(color_list)} gray:{len(gray_list)}")

print(f"\n分类完成:")
print(f"  彩色: {len(color_list)}  → {COLOR_DIR}")
print(f"  黑白: {len(gray_list)}  → {GRAY_DIR}")

# 保存分类清单
with open(IMG_DIR / 'color_list.txt', 'w') as f:
    for n in color_list: f.write(n + '\n')
with open(IMG_DIR / 'grayscale_list.txt', 'w') as f:
    for n in gray_list: f.write(n + '\n')

# 更新JSON（标记每张图的分类）
if META_JSON.exists():
    with open(META_JSON, 'r', encoding='utf-8') as f:
        records = json.load(f)
    gray_set = set(gray_list)
    color_set = set(color_list)
    for r in records:
        fn = r.get('file', '')
        if fn in gray_set:
            r['color_type'] = 'grayscale'
        elif fn in color_set:
            r['color_type'] = 'color'
    with open(META_JSON, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False)
    print(f"元数据已更新 (标记color_type字段)")
