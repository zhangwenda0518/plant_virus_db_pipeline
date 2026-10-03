#!/usr/bin/env python3
"""Normalize symptom & part vocabulary in photos data (bilingual standardization).

Adds to each record:
  symptom_table.json:  symptoms_std (str, "花叶 mosaic; 黄化 yellowing"), parts_std
  unified_gallery.json: symptoms_std (list of "花叶 mosaic"), parts_std (list)

Variants map to canonical bilingual pairs; unknown tokens pass through as-is.
Idempotent: re-running regenerates std fields from originals.
"""

import json
import re
from pathlib import Path

DATA = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data")

# variant(lower) -> (en, zh)
SYM_MAP = {
    "mosaic": ("mosaic", "花叶"), "花叶": ("mosaic", "花叶"),
    "mottle": ("mottle", "斑驳"), "斑驳": ("mottle", "斑驳"),
    "yellow": ("yellowing", "黄化"), "yellowing": ("yellowing", "黄化"),
    "yellowed": ("yellowing", "黄化"), "黄化": ("yellowing", "黄化"),
    "chlorosis": ("chlorosis", "褪绿"), "chlorotic": ("chlorosis", "褪绿"),
    "褪绿": ("chlorosis", "褪绿"),
    "necrosis": ("necrosis", "坏死"), "necrotic": ("necrosis", "坏死"),
    "坏死": ("necrosis", "坏死"), "枯斑": ("necrosis", "坏死"),
    "stunt": ("stunting", "矮化"), "stunting": ("stunting", "矮化"),
    "stunted": ("stunting", "矮化"), "矮化": ("stunting", "矮化"),
    "dwarf": ("dwarfing", "矮缩"), "dwarfing": ("dwarfing", "矮缩"),
    "dwarfed": ("dwarfing", "矮缩"), "矮缩": ("dwarfing", "矮缩"),
    "leaf curl": ("leaf curl", "曲叶"), "curl": ("leaf curl", "曲叶"),
    "curling": ("leaf curl", "曲叶"), "curled": ("leaf curl", "曲叶"),
    "curly": ("leaf curl", "曲叶"), "曲叶": ("leaf curl", "曲叶"),
    "leaf roll": ("leaf roll", "卷叶"), "roll": ("leaf roll", "卷叶"),
    "rolling": ("leaf roll", "卷叶"), "rolled": ("leaf roll", "卷叶"),
    "卷叶": ("leaf roll", "卷叶"),
    "ringspot": ("ringspot", "环斑"), "ring spot": ("ringspot", "环斑"),
    "ring-spot": ("ringspot", "环斑"), "环斑": ("ringspot", "环斑"),
    "streak": ("streak", "条纹"), "streaking": ("streak", "条纹"),
    "条纹": ("streak", "条纹"),
    "stripe": ("stripe", "条斑"), "striping": ("stripe", "条斑"),
    "条斑": ("stripe", "条斑"),
    "spot": ("spotting", "斑点"), "spots": ("spotting", "斑点"),
    "spotting": ("spotting", "斑点"), "斑点": ("spotting", "斑点"),
    "lesion": ("lesion", "病斑"), "lesions": ("lesion", "病斑"),
    "病斑": ("lesion", "病斑"),
    "wilt": ("wilt", "萎蔫"), "wilting": ("wilt", "萎蔫"),
    "wilted": ("wilt", "萎蔫"), "萎蔫": ("wilt", "萎蔫"),
    "distortion": ("distortion", "畸形"), "deformed": ("distortion", "畸形"),
    "deformation": ("distortion", "畸形"), "畸形": ("distortion", "畸形"),
    "blotch": ("blotch", "斑块"), "blotches": ("blotch", "斑块"),
    "斑块": ("blotch", "斑块"),
    "vein clearing": ("vein clearing", "脉明"), "vein-clearing": ("vein clearing", "脉明"),
    "clearing": ("vein clearing", "脉明"), "脉明": ("vein clearing", "脉明"),
    "vein yellowing": ("vein yellowing", "黄脉"), "yellow vein": ("vein yellowing", "黄脉"),
    "yellow-vein": ("vein yellowing", "黄脉"), "黄脉": ("vein yellowing", "黄脉"),
    "enation": ("enation", "耳突"), "enations": ("enation", "耳突"),
    "耳突": ("enation", "耳突"),
    "puckering": ("puckering", "皱缩"), "puckered": ("puckering", "皱缩"),
    "皱缩": ("puckering", "皱缩"), "坡缩": ("puckering", "皱缩"),
    "crinkle": ("crinkling", "皱缩"), "crinkling": ("crinkling", "皱缩"),
    "blister": ("blistering", "泡斑"), "blistering": ("blistering", "泡斑"),
    "泡斑": ("blistering", "泡斑"),
    "黄边": ("yellow margin", "黄边"), "yellow margin": ("yellow margin", "黄边"),
}
# 修饰词（不进 std）
DROP = {"mild", "severe", "systemic", "symptom", "symptoms", "general", "lightly", "highly"}

PART_MAP = {
    "leaf": ("leaf", "叶"), "leaves": ("leaf", "叶"), "叶": ("leaf", "叶"),
    "fruit": ("fruit", "果"), "fruits": ("fruit", "果"), "果": ("fruit", "果"),
    "果实": ("fruit", "果"),
    "stem": ("stem", "茎"), "茎": ("stem", "茎"),
    "whole plant": ("whole plant", "全株"), "全株": ("whole plant", "全株"),
    "seed": ("seed", "种子"), "seeds": ("seed", "种子"), "种子": ("seed", "种子"),
    "tuber": ("tuber", "块茎"), "tubers": ("tuber", "块茎"), "块茎": ("tuber", "块茎"),
    "root": ("root", "根"), "roots": ("root", "根"), "根": ("root", "根"),
    "ear": ("ear", "穗"), "ears": ("ear", "穗"), "穗": ("ear", "穗"),
    "flower": ("flower", "花"), "flowers": ("flower", "花"), "花": ("flower", "花"),
    "tree": ("whole tree", "全树"), "全树": ("whole tree", "全树"),
    "vine": ("vine", "茎蔓"), "茎蔓": ("vine", "茎蔓"),
    "branch": ("branch", "枝"), "branches": ("branch", "枝"), "枝": ("branch", "枝"),
    "seedling": ("seedling", "苗"), "seedlings": ("seedling", "苗"), "苗": ("seedling", "苗"),
    "pod": ("pod", "荚"), "pods": ("pod", "荚"), "荚": ("pod", "荚"),
    "bark": ("bark", "树皮"), "树皮": ("bark", "树皮"),
    "trunk": ("trunk", "树干"), "树干": ("trunk", "树干"),
    "crown": ("crown", "树冠"), "树冠": ("crown", "树冠"),
    "needle": ("needle", "针叶"), "needles": ("needle", "针叶"), "针叶": ("needle", "针叶"),
    "bulb": ("bulb", "鳞茎"), "bulbs": ("bulb", "鳞茎"), "鳞茎": ("bulb", "鳞茎"),
}


def is_cjk(s):
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def std_symptoms(raw):
    """raw str -> (std_list ['花叶 mosaic',...], n_mapped, n_total)"""
    out, seen, nm, tot = [], set(), 0, 0
    for tok in re.split(r"[;,、/]", raw or ""):
        tok = tok.strip()
        if not tok:
            continue
        tot += 1
        low = tok.lower()
        if low in DROP:
            continue
        pair = SYM_MAP.get(low)
        if pair:
            nm += 1
            label = f"{pair[1]} {pair[0]}"
        elif is_cjk(tok):
            label = tok
        else:
            label = tok.lower()
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out, nm, tot


def std_parts(raw):
    out, seen = [], set()
    for tok in re.split(r"[;,、/]", raw or ""):
        tok = tok.strip()
        if not tok:
            continue
        pair = PART_MAP.get(tok.lower()) or PART_MAP.get(tok)
        if pair:
            label = f"{pair[1]} {pair[0]}"
        elif is_cjk(tok):
            label = tok
        else:
            label = tok.lower()
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def main():
    # 1. symptom_table.json
    p1 = DATA / "symptom_table.json"
    table = json.loads(p1.read_text(encoding="utf-8"))
    nm = tot = 0
    for r in table:
        std, a, b = std_symptoms(r.get("symptoms", ""))
        nm += a; tot += b
        r["symptoms_std"] = "; ".join(std)
        r["parts_std"] = "; ".join(std_parts(r.get("parts", "")))
    p1.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"symptom_table.json: {len(table)} rows, symptom tokens mapped {nm}/{tot}")

    # 2. unified_gallery.json
    p2 = DATA / "unified_gallery.json"
    gal = json.loads(p2.read_text(encoding="utf-8"))
    for r in gal:
        raw = r.get("symptoms") or []
        raw_str = "; ".join(raw) if isinstance(raw, list) else str(raw)
        std, _, _ = std_symptoms(raw_str)
        r["symptoms_std"] = std
        praw = r.get("parts") or []
        praw_str = "; ".join(praw) if isinstance(praw, list) else str(praw)
        r["parts_std"] = std_parts(praw_str)
    p2.write_text(json.dumps(gal, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"unified_gallery.json: {len(gal)} photos normalized")


if __name__ == "__main__":
    main()
