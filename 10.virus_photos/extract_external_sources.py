#!/usr/bin/env python3
"""
统一提取器：对DPV / Open-i / EPPO gallery JSON 统一提取
virus | host | symptom | part 标签

从caption字段提取，合并到统一格式
"""

import re, json

DPV_JSON = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data\dpv_gallery.json"
EPPO_JSON = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data\eppo_gallery.json"
OPENI_JSON = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data\openi_gallery.json"
OUT = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\external_sources_extracted.json"

# ── 宿主拉丁名 + 通用名 ──
HOST_LATIN_RE = re.compile(
    r'\b('
    r'Nicotiana\s+\w+|Solanum\s+\w+|Cucumis\s+\w+|Arabidopsis\s+\w+|'
    r'Phaseolus\s+\w+|Vigna\s+\w+|Glycine\s+\w+|Zea\s+\w+|Triticum\s+\w+|'
    r'Oryza\s+\w+|Hordeum\s+\w+|Capsicum\s+\w+|Manihot\s+\w+|Ipomoea\s+\w+|'
    r'Citrullus\s+\w+|Cucurbita\s+\w+|Brassica\s+\w+|Prunus\s+\w+|Malus\s+\w+|'
    r'Vitis\s+\w+|Musa\s+\w+|Citrus\s+\w+|Daucus\s+\w+|Allium\s+\w+|'
    r'Lactuca\s+\w+|Spinacia\s+\w+|Arachis\s+\w+|Gossypium\s+\w+|Beta\s+\w+|'
    r'Carica\s+\w+|Petunia\s+\w+|Datura\s+\w+|Chenopodium\s+\w+|Helianthus\s+\w+|'
    r'Fragaria\s+\w+|Rosa\s+\w+|Pelargonium\s+\w+|Dahlia\s+\w+|Dianthus\s+\w+|'
    r'Lilium\s+\w+|Tulipa\s+\w+|Narcissus\s+\w+|Gladiolus\s+\w+|Iris\s+\w+|'
    r'Coffea\s+\w+|Theobroma\s+\w+|Elaeis\s+\w+|Hevea\s+\w+|Cocos\s+\w+|'
    r'Persea\s+\w+|Mangifera\s+\w+|Ananas\s+\w+|Psidium\s+\w+|Actinidia\s+\w+|'
    r'Humulus\s+\w+|Linum\s+\w+|Pisum\s+\w+|Medicago\s+\w+|Trifolium\s+\w+|'
    r'Sorghum\s+\w+|Avena\s+\w+|Secale\s+\w+|Panicum\s+\w+|Saccharum\s+\w+|'
    r'Rubus\s+\w+|Vaccinium\s+\w+|Ficus\s+\w+|Olea\s+\w+|Juglans\s+\w+|'
    r'Phoenix\s+\w+|Punica\s+\w+|Passiflora\s+\w+|Camellia\s+\w+|'
    r'Cyphomandra\s+\w+|Apium\s+\w+|Petroselinum\s+\w+|Ocimum\s+\w+|Mentha\s+\w+|'
    r'Cydonia\s+\w+)'
    r'\b', re.IGNORECASE
)

HOST_COMMON = {
    'tomato': 'tomato', 'tobacco': 'tobacco', 'potato': 'potato',
    'cucumber': 'cucumber', 'pepper': 'pepper', 'capsicum': 'pepper',
    'chilli': 'chilli', 'chili': 'chilli',
    'bean': 'bean', 'soybean': 'soybean', 'pea': 'pea', 'cowpea': 'cowpea',
    'wheat': 'wheat', 'barley': 'barley', 'maize': 'maize', 'corn': 'maize',
    'rice': 'rice', 'sugarcane': 'sugarcane', 'sorghum': 'sorghum',
    'cassava': 'cassava', 'sweet potato': 'sweet potato',
    'lettuce': 'lettuce', 'spinach': 'spinach', 'cabbage': 'cabbage',
    'carrot': 'carrot', 'onion': 'onion', 'garlic': 'garlic',
    'leek': 'leek', 'celery': 'celery',
    'apple': 'apple', 'grape': 'grape', 'grapevine': 'grape',
    'banana': 'banana', 'papaya': 'papaya', 'citrus': 'citrus',
    'orange': 'citrus', 'lemon': 'citrus', 'lime': 'citrus',
    'strawberry': 'strawberry', 'peanut': 'peanut', 'groundnut': 'peanut',
    'cotton': 'cotton', 'sunflower': 'sunflower',
    'arabidopsis': 'arabidopsis', 'nicotiana': 'nicotiana',
    'squash': 'squash', 'zucchini': 'squash', 'pumpkin': 'pumpkin',
    'watermelon': 'watermelon', 'melon': 'melon',
    'alfalfa': 'alfalfa', 'lucerne': 'alfalfa', 'clover': 'clover',
    'eggplant': 'eggplant', 'okra': 'okra',
    'rose': 'rose', 'chrysanthemum': 'chrysanthemum',
    'petunia': 'petunia', 'lily': 'lily', 'orchid': 'orchid',
    'cannabis': 'cannabis', 'hemp': 'hemp',
    'lentil': 'lentil', 'chickpea': 'chickpea',
    'calla lily': 'calla lily', 'carnation': 'carnation',
    'sugar beet': 'sugar beet', 'beet': 'beet',
    'radish': 'radish', 'turnip': 'turnip',
    'raspberry': 'raspberry', 'blackberry': 'blackberry', 'blueberry': 'blueberry',
    'cherry': 'cherry', 'peach': 'peach', 'plum': 'plum', 'apricot': 'apricot',
    'pear': 'pear', 'almond': 'almond',
    'pineapple': 'pineapple', 'mango': 'mango',
    'coffee': 'coffee', 'cocoa': 'cocoa', 'coconut': 'coconut',
    'hop': 'hop', 'flax': 'flax', 'rubber': 'rubber',
    'oil palm': 'oil palm', 'date': 'date palm',
    'guava': 'guava', 'pomegranate': 'pomegranate', 'kiwi': 'kiwi',
    'avocado': 'avocado', 'fig': 'fig', 'olive': 'olive',
    'tea': 'tea', 'millet': 'millet', 'rye': 'rye', 'oat': 'oat',
    'tulip': 'tulip', 'daffodil': 'daffodil', 'gladiolus': 'gladiolus',
    'iris': 'iris', 'dahlia': 'dahlia', 'geranium': 'geranium',
    'begonia': 'begonia', 'hydrangea': 'hydrangea',
    'willow': 'willow', 'poplar': 'poplar', 'oak': 'oak', 'pine': 'pine',
}

SYMPTOM_EN = [
    'mosaic', 'mottle', 'necrosis', 'necrotic', 'chlorosis', 'chlorotic',
    'yellowing', 'yellow', 'stunting', 'stunted', 'stunt', 'dwarf', 'dwarfing',
    'ringspot', 'ring spot', 'streak', 'stripe', 'striate',
    'leaf curl', 'leaf roll', 'leafroll', 'curling', 'curl',
    'crinkle', 'crinkling', 'distortion', 'malformation', 'deformation',
    'wilt', 'wilting', 'blister', 'blistering', 'pucker', 'puckering',
    'vein clearing', 'vein banding', 'vein yellowing',
    'etch', 'etching', 'lesion', 'spot', 'spotting', 'blotch', 'blotching',
    'mild mottle', 'severe mosaic', 'systemic',
    'dieback', 'canker', 'scorch', 'scorching', 'decline',
    'rosette', 'witches broom', 'enation', 'enations',
    'reddening', 'purpling', 'bronzing', 'silvering',
    'line pattern', 'ring pattern',
    'tip necrosis', 'margin necrosis', 'internal necrosis',
    'gall', 'tumor',
]

PART_EN_MAP = {
    'leaf': '叶', 'leaves': '叶', 'leaflet': '叶', 'leaflets': '叶', 'foliage': '叶',
    'fruit': '果', 'fruits': '果', 'berry': '果', 'berries': '果',
    'pod': '果', 'pods': '果',
    'stem': '茎', 'stems': '茎', 'petiole': '茎', 'petioles': '茎',
    'root': '根', 'roots': '根',
    'flower': '花', 'flowers': '花', 'blossom': '花', 'blossoms': '花',
    'petal': '花', 'petals': '花', 'inflorescence': '花',
    'seed': '种子', 'seeds': '种子',
    'tuber': '块茎', 'tubers': '块茎',
    'shoot': '枝', 'shoots': '枝', 'branch': '枝', 'branches': '枝',
    'twig': '枝', 'twigs': '枝',
    'seedling': '苗', 'seedlings': '苗',
    'whole plant': '全株', 'entire plant': '全株',
    'bulb': '鳞茎', 'bulbs': '鳞茎',
    'corm': '球茎', 'corms': '球茎',
    'bark': '茎', 'trunk': '茎', 'crown': '全株',
    'grain': '种子', 'grains': '种子', 'ear': '种子', 'head': '种子',
    'tendril': '茎蔓', 'vine': '茎蔓',
}


def extract_all(text, virus_name_hint=''):
    """从caption+病毒名hint中提取四字段"""
    txt = (text + ' ' + virus_name_hint).lower()
    
    # 宿主
    hosts = set()
    for m in HOST_LATIN_RE.finditer(txt):
        hosts.add(m.group(1))
    for common in HOST_COMMON:
        if common in txt:
            hosts.add(common)
    
    # 症状
    symptoms = []
    for kw in SYMPTOM_EN:
        if kw in txt and kw not in symptoms:
            symptoms.append(kw)
    
    # 部位（按长度降序匹配）
    parts = set()
    sorted_parts = sorted(PART_EN_MAP.items(), key=lambda x: -len(x[0]))
    for kw, cn in sorted_parts:
        if kw in txt:
            parts.add(cn)
    
    return {
        'hosts': sorted(hosts),
        'symptoms': symptoms,
        'parts': sorted(parts),
    }


# ── 病毒名提取 ──
VIRUS_RE = re.compile(r'([A-Z][a-z]+(?:\s+[a-z]+){1,4}\s+virus)', re.IGNORECASE)
VIRUS_ABBR = re.compile(r'\b([A-Z]{3,5}[Vv])\b')

def extract_virus(text):
    viruses = set()
    for m in VIRUS_RE.finditer(text):
        v = m.group(1).strip()
        if len(v) > 8 and v.count(' ') >= 2:
            viruses.add(v)
    for m in VIRUS_ABBR.finditer(text):
        v = m.group(1)
        if v not in {'DPV', 'FIG', 'TAB', 'PCR', 'ELISA', 'TEM', 'SEM', 'RNA', 'DNA'}:
            viruses.add(v)
    return sorted(viruses)


# ── 处理各源 ──
all_records = []

def process_source(data, source_name, virus_field='virus'):
    records = []
    for item in data:
        caption = item.get('caption', '') or ''
        virus_hint = str(item.get(virus_field, '') or item.get('virus_latin', '') or '')
        
        extracted = extract_all(caption, virus_hint)
        viruses = extract_virus(caption + ' ' + virus_hint)
        
        # 如果源数据已有标签，合并
        if source_name == 'EPPO':
            existing_hosts = item.get('hosts', [])
            existing_symp = item.get('symptoms', [])
            existing_parts = item.get('parts', [])
            # 合并去重
            all_h = list(set(existing_hosts + extracted['hosts']))
            all_s = list(set(existing_symp + extracted['symptoms']))
            all_p = list(set(existing_parts + extracted['parts']))
        else:
            all_h = extracted['hosts']
            all_s = extracted['symptoms']
            all_p = extracted['parts']
        
        virus_str = '; '.join(viruses[:10])
        host_str = '; '.join(all_h[:8])
        symp_str = '; '.join(all_s[:8])
        part_str = '; '.join(all_p[:6])

        # 无病毒名时只追加一条空 virus 记录（旧代码 `for v in (viruses or [''])`
        # 与下面 `if not viruses` 会各追加一条 → 重复记录，审计实测 1,107/3,174）
        for v in viruses:
            records.append({
                'source': source_name,
                'entry': item.get('code', item.get('photo_id', '')),
                'virus': v,
                'host_cn': host_str,
                'host_latin': '',
                'family': '',
                'symptoms': symp_str,
                'parts': part_str,
                'caption': caption[:300],
            })
        if not viruses:
            records.append({
                'source': source_name,
                'entry': item.get('code', item.get('photo_id', '')),
                'virus': '',
                'host_cn': host_str,
                'host_latin': '',
                'family': '',
                'symptoms': symp_str,
                'parts': part_str,
                'caption': caption[:300],
            })
    return records


def dedupe_records(records):
    """按唯一键 (source, entry, virus, caption) 去重兜底，保留首次出现。"""
    seen = set()
    out = []
    for r in records:
        key = (r.get('source', ''), str(r.get('entry', '')), r.get('virus', ''), r.get('caption', ''))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# DPV
with open(DPV_JSON, 'r', encoding='utf-8') as f:
    dpv = json.load(f)
dpv_records = process_source(dpv, 'DPV', 'virus')
print(f"DPV: {len(dpv_records)} 条")

# EPPO
with open(EPPO_JSON, 'r', encoding='utf-8') as f:
    eppo = json.load(f)
eppo_records = process_source(eppo, 'EPPO', 'virus')
print(f"EPPO: {len(eppo_records)} 条")

# Open-i
with open(OPENI_JSON, 'r', encoding='utf-8') as f:
    openi = json.load(f)
openi_records = process_source(openi, 'Open-i', 'virus')
print(f"Open-i: {len(openi_records)} 条")

all_records = dpv_records + eppo_records + openi_records

# 去重兜底（按 source+entry+virus+caption 唯一键；跨源因 source 不同不会互相吞掉）
_before = len(all_records)
all_records = dedupe_records(all_records)
if len(all_records) != _before:
    print(f"去重: {_before} → {len(all_records)} (移除 {_before - len(all_records)} 条重复)")

# ── 输出 ──
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(all_records, f, ensure_ascii=False)

# 统计
has_v = sum(1 for r in all_records if r['virus'])
has_h = sum(1 for r in all_records if r['host_cn'])
has_s = sum(1 for r in all_records if r['symptoms'])
has_p = sum(1 for r in all_records if r['parts'])
all4 = sum(1 for r in all_records if r['virus'] and r['host_cn'] and r['symptoms'] and r['parts'])

print(f"\n=== 三源汇总 ===")
print(f"总记录: {len(all_records)}")
print(f"有病毒: {has_v}, 有宿主: {has_h}, 有症状: {has_s}, 有部位: {has_p}")
print(f"四字段齐全: {all4}")

from collections import Counter
pc = Counter()
for r in all_records:
    for p in r['parts'].split('; '):
        if p.strip():
            pc[p.strip()] += 1
print(f"部位: {dict(pc.most_common(8))}")
print(f"\n输出: {OUT}")
