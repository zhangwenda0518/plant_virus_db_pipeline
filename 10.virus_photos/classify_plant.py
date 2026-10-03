#!/usr/bin/env python3
"""彩色图分类：植物→plant/  非植物→non_plant/ （不删除）"""
import os, shutil
from pathlib import Path
from PIL import Image
import colorsys

COLOR_DIR = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_pdf_images\color")
PLANT_DIR = COLOR_DIR / 'plant'
NONPLANT_DIR = COLOR_DIR / 'non_plant'
os.makedirs(PLANT_DIR, exist_ok=True)
os.makedirs(NONPLANT_DIR, exist_ok=True)

SAMPLE_MAX = 5000
GREEN_H_MIN, GREEN_H_MAX = 50, 170   # 绿色H范围（HSV，0-360）
GREEN_S_MIN = 20                      # 最低饱和度
GREEN_V_MIN = 20                      # 最低明度
GREEN_RATIO = 0.08                    # 绿色像素占比≥8% → 可能是植物
WHITE_R_MAX = 0.85                    # 白色/灰色背景阈值：R>240或平均亮度>0.85

def is_plant_image(img_path):
    try:
        img = Image.open(img_path).convert('RGB')
        w, h = img.size
        total = w * h
        step = max(1, total // SAMPLE_MAX) if total > SAMPLE_MAX else 1
        
        green_count = 0
        white_count = 0
        sampled = 0
        
        pixels = img.load()
        row_step = max(1, step // max(1, w // 100)) if step > 1 else 1
        
        for y in range(0, h, row_step):
            for x in range(0, w, step if step > 1 else 1):
                r, g, b = pixels[x, y]
                
                # 白色/浅灰背景
                if r > 240 and g > 240 and b > 240:
                    white_count += 1
                
                # 绿色检测（HSV）
                rn, gn, bn = r/255.0, g/255.0, b/255.0
                mx, mn = max(rn, gn, bn), min(rn, gn, bn)
                s = 0 if mx == 0 else (mx - mn) / mx
                v = mx
                
                if s > 0:
                    if mx == rn: h = 60 * ((gn - bn) / (mx - mn))
                    elif mx == gn: h = 60 * (2 + (bn - rn) / (mx - mn))
                    else: h = 60 * (4 + (rn - gn) / (mx - mn))
                    h = h % 360
                    
                    if GREEN_H_MIN <= h <= GREEN_H_MAX and s * 100 >= GREEN_S_MIN and v * 100 >= GREEN_V_MIN:
                        green_count += 1
                
                sampled += 1
        
        img.close()
        
        green_pct = green_count / max(sampled, 1)
        white_pct = white_count / max(sampled, 1)
        
        # 白色背景太多 → 可能是图表/文字
        if white_pct > 0.70:
            return False
        
        # 绿色足够 → 植物
        return green_pct >= GREEN_RATIO
    
    except:
        return False

# ── 扫描 ──
files = [f for f in sorted(COLOR_DIR.iterdir()) if f.is_file() and f.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.bmp','.webp')]
print(f"待分类: {len(files)}")

plant_list, nonplant_list = [], []
for i, fpath in enumerate(files):
    if is_plant_image(fpath):
        shutil.move(str(fpath), str(PLANT_DIR / fpath.name))
        plant_list.append(fpath.name)
    else:
        shutil.move(str(fpath), str(NONPLANT_DIR / fpath.name))
        nonplant_list.append(fpath.name)
    
    if (i + 1) % 3000 == 0:
        print(f"  {i+1}/{len(files)} | plant:{len(plant_list)} non_plant:{len(nonplant_list)}")

print(f"\n分类完成:")
print(f"  🌿 植物: {len(plant_list)}  → {PLANT_DIR}")
print(f"  📊 非植物: {len(nonplant_list)}  → {NONPLANT_DIR}")
