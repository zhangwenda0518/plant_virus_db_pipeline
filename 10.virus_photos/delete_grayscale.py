#!/usr/bin/env python3
"""扫描 all_pdf_images 目录，删除黑白/灰度图片，只保留彩色图"""
import os, json
from pathlib import Path
from PIL import Image

IMG_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images")
META_JSON = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images.json")

THRESHOLD = 8       # 灰度判定：RGB差异 < THRESHOLD
GRAY_RATIO = 0.95   # 灰度像素占比 ≥ 此值则判定为黑白图
SAMPLE_MAX = 5000   # 每张图最多采样像素数（加速）

def is_grayscale(img_path):
    """判断图片是否为黑白/灰度图"""
    try:
        img = Image.open(img_path)
        # 模式是 L(灰度) 或 1(二值) → 直接判定为黑白
        if img.mode in ('L', '1'):
            img.close()
            return True
        if img.mode not in ('RGB', 'RGBA'):
            img.close()
            return False
        img = img.convert('RGB')
        w, h = img.size
        total = w * h
        
        # 采样：大图取部分像素
        if total > SAMPLE_MAX:
            step = max(1, total // SAMPLE_MAX)
        else:
            step = 1
        
        gray_count = 0
        sampled = 0
        pixels = img.load()
        
        for y in range(0, h, max(1, step // max(1, w // 100) if step > 1 else 1)):
            for x in range(0, w, step if step > 1 else 1):
                r, g, b = pixels[x, y]
                if abs(r - g) < THRESHOLD and abs(r - b) < THRESHOLD and abs(g - b) < THRESHOLD:
                    gray_count += 1
                sampled += 1
        
        img.close()
        return gray_count / max(sampled, 1) >= GRAY_RATIO
    
    except Exception as e:
        return False  # 读不了的保留

# ── 扫描 ──
files = sorted(IMG_DIR.glob('*'))
print(f"总文件: {len(files)}")

gray_files = []
color_files = []
for i, fpath in enumerate(files):
    if not fpath.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
        continue
    if is_grayscale(fpath):
        gray_files.append(fpath)
    else:
        color_files.append(fpath)
    
    if (i + 1) % 3000 == 0:
        print(f"  {i+1}/{len(files)} | gray:{len(gray_files)} color:{len(color_files)}")

print(f"\n结果:")
print(f"  彩色: {len(color_files)}")
print(f"  黑白: {len(gray_files)}")

# ── 删除黑白图 ──
if gray_files:
    deleted = 0
    for fpath in gray_files:
        try:
            os.remove(fpath)
            deleted += 1
        except:
            pass
    print(f"已删除: {deleted}")
    
    # 更新JSON
    if META_JSON.exists():
        with open(META_JSON, 'r', encoding='utf-8') as f:
            records = json.load(f)
        kept_files = {f.name for f in color_files}
        new_records = [r for r in records if r.get('file', '') in kept_files]
        with open(META_JSON, 'w', encoding='utf-8') as f:
            json.dump(new_records, f, ensure_ascii=False)
        print(f"元数据更新: {len(records)} → {len(new_records)}")
else:
    print("没有黑白图需要删除")
