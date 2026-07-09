#!/usr/bin/env python3
"""矫正 EPPO 图库的物种名：通用名→拉丁名 (NCBI/ICTV)，同时规范植物部位"""
import polars as pl, json, re, os

import pathlib
BASE = pathlib.Path(__file__).parent.parent
EPPO = str(BASE / "10.virus_photos" / "eppo_virus_photos.tsv")
REF = str(BASE / "docs" / "data" / "Plant_Virus_Ref.Info.tsv")
OUT_JSON = str(BASE / "docs" / "data" / "eppo_gallery.json")

# ── 1. 加载参考数据 ──────────────────────
ref = pl.read_csv(REF, separator='\t', ignore_errors=True, truncate_ragged_lines=True)

# 构建病毒名映射: 通用名/NCBI/ICTV → (Species_NCBI, Species_ICTV)
virus_map = {}
for row in ref.iter_rows(named=True):
    ncbi = str(row.get('Species_NCBI', '')).strip()
    ictv = str(row.get('Species_ICTV', '')).strip()
    vn = str(row.get('Virus name(s)', '')).strip()
    if not ncbi and not ictv:
        continue
    if ncbi:
        virus_map[ncbi.lower()] = (ncbi, ictv if ictv else ncbi)
    if ictv:
        virus_map[ictv.lower()] = (ncbi, ictv)
    if vn:
        virus_map[vn.lower()] = (ncbi, ictv if ictv else ncbi)
    for word in ncbi.lower().split():
        if len(word) > 5:
            virus_map[word] = (ncbi, ictv if ictv else ncbi)

# 宿主通用名 → 拉丁名
HOST_MAP = {
    'tomato': ('Solanum lycopersicum', '番茄'),
    'potato': ('Solanum tuberosum', '马铃薯'),
    'tobacco': ('Nicotiana tabacum', '烟草'),
    'pepper': ('Capsicum annuum', '辣椒'),
    'capsicum': ('Capsicum annuum', '辣椒'),
    'chilli': ('Capsicum annuum', '辣椒'),
    'bell pepper': ('Capsicum annuum', '甜椒'),
    'cucumber': ('Cucumis sativus', '黄瓜'),
    'melon': ('Cucumis melo', '甜瓜'),
    'watermelon': ('Citrullus lanatus', '西瓜'),
    'squash': ('Cucurbita pepo', '西葫芦'),
    'zucchini': ('Cucurbita pepo', '西葫芦'),
    'courgette': ('Cucurbita pepo', '西葫芦'),
    'pumpkin': ('Cucurbita moschata', '南瓜'),
    'marrow': ('Cucurbita pepo', '西葫芦'),
    'gourd': ('Lagenaria siceraria', '葫芦'),
    'bean': ('Phaseolus vulgaris', '菜豆'),
    'soybean': ('Glycine max', '大豆'),
    'soya': ('Glycine max', '大豆'),
    'pea': ('Pisum sativum', '豌豆'),
    'cowpea': ('Vigna unguiculata', '豇豆'),
    'chickpea': ('Cicer arietinum', '鹰嘴豆'),
    'peanut': ('Arachis hypogaea', '花生'),
    'groundnut': ('Arachis hypogaea', '花生'),
    'sunflower': ('Helianthus annuus', '向日葵'),
    'wheat': ('Triticum aestivum', '小麦'),
    'barley': ('Hordeum vulgare', '大麦'),
    'oat': ('Avena sativa', '燕麦'),
    'rye': ('Secale cereale', '黑麦'),
    'rice': ('Oryza sativa', '水稻'),
    'maize': ('Zea mays', '玉米'),
    'corn': ('Zea mays', '玉米'),
    'sorghum': ('Sorghum bicolor', '高粱'),
    'sugarcane': ('Saccharum officinarum', '甘蔗'),
    'apple': ('Malus domestica', '苹果'),
    'pear': ('Pyrus communis', '梨'),
    'plum': ('Prunus domestica', '李子'),
    'peach': ('Prunus persica', '桃'),
    'cherry': ('Prunus avium', '樱桃'),
    'apricot': ('Prunus armeniaca', '杏'),
    'citrus': ('Citrus spp.', '柑橘'),
    'orange': ('Citrus sinensis', '甜橙'),
    'lemon': ('Citrus limon', '柠檬'),
    'lime': ('Citrus aurantiifolia', '酸橙'),
    'grapefruit': ('Citrus paradisi', '葡萄柚'),
    'grape': ('Vitis vinifera', '葡萄'),
    'grapevine': ('Vitis vinifera', '葡萄'),
    'banana': ('Musa acuminata', '香蕉'),
    'papaya': ('Carica papaya', '番木瓜'),
    'strawberry': ('Fragaria ananassa', '草莓'),
    'blueberry': ('Vaccinium corymbosum', '蓝莓'),
    'raspberry': ('Rubus idaeus', '树莓'),
    'blackberry': ('Rubus fruticosus', '黑莓'),
    'cassava': ('Manihot esculenta', '木薯'),
    'sweet potato': ('Ipomoea batatas', '甘薯'),
    'yam': ('Dioscorea spp.', '薯蓣'),
    'taro': ('Colocasia esculenta', '芋头'),
    'carrot': ('Daucus carota', '胡萝卜'),
    'onion': ('Allium cepa', '洋葱'),
    'garlic': ('Allium sativum', '大蒜'),
    'leek': ('Allium porrum', '韭葱'),
    'cabbage': ('Brassica oleracea var. capitata', '甘蓝'),
    'cauliflower': ('Brassica oleracea var. botrytis', '花椰菜'),
    'broccoli': ('Brassica oleracea var. italica', '西兰花'),
    'lettuce': ('Lactuca sativa', '生菜'),
    'spinach': ('Spinacia oleracea', '菠菜'),
    'celery': ('Apium graveolens', '芹菜'),
    'parsley': ('Petroselinum crispum', '欧芹'),
    'beetroot': ('Beta vulgaris', '甜菜'),
    'radish': ('Raphanus sativus', '萝卜'),
    'cotton': ('Gossypium hirsutum', '棉花'),
    'flax': ('Linum usitatissimum', '亚麻'),
    'hemp': ('Cannabis sativa', '大麻'),
    'hop': ('Humulus lupulus', '啤酒花'),
    'tea': ('Camellia sinensis', '茶'),
    'coffee': ('Coffea arabica', '咖啡'),
    'cocoa': ('Theobroma cacao', '可可'),
    'rubber': ('Hevea brasiliensis', '橡胶'),
    'oil palm': ('Elaeis guineensis', '油棕'),
    'coconut': ('Cocos nucifera', '椰子'),
    'rose': ('Rosa spp.', '玫瑰'),
    'chrysanthemum': ('Chrysanthemum morifolium', '菊花'),
    'carnation': ('Dianthus caryophyllus', '康乃馨'),
    'orchid': ('Orchidaceae spp.', '兰花'),
    'lily': ('Lilium spp.', '百合'),
    'tulip': ('Tulipa gesneriana', '郁金香'),
    'petunia': ('Petunia hybrida', '矮牵牛'),
    'zinnia': ('Zinnia elegans', '百日菊'),
    'impatiens': ('Impatiens walleriana', '凤仙花'),
    'geranium': ('Pelargonium hortorum', '天竺葵'),
    'begonia': ('Begonia spp.', '秋海棠'),
    'hydrangea': ('Hydrangea macrophylla', '绣球花'),
    'dahlia': ('Dahlia pinnata', '大丽花'),
    'canna': ('Canna indica', '美人蕉'),
    'oak': ('Quercus spp.', '橡树'),
    'pine': ('Pinus spp.', '松树'),
    'spruce': ('Picea spp.', '云杉'),
    'fir': ('Abies spp.', '冷杉'),
    'birch': ('Betula spp.', '桦树'),
    'maple': ('Acer spp.', '枫树'),
    'elm': ('Ulmus spp.', '榆树'),
    'poplar': ('Populus spp.', '杨树'),
    'willow': ('Salix spp.', '柳树'),
    'alfalfa': ('Medicago sativa', '苜蓿'),
    'clover': ('Trifolium spp.', '三叶草'),
    'eggplant': ('Solanum melongena', '茄子'),
    'okra': ('Abelmoschus esculentus', '秋葵'),
    'avocado': ('Persea americana', '鳄梨'),
    'mango': ('Mangifera indica', '芒果'),
    'lablab': ('Lablab purpureus', '扁豆'),
    'Chenopodium': ('Chenopodium quinoa', '藜麦'),
    'Nicotiana': ('Nicotiana benthamiana', '本氏烟'),
    'Datura': ('Datura stramonium', '曼陀罗'),
}

# 部位标准化
PART_MAP = {
    'leaf': 'leaf', 'leaves': 'leaf',
    'fruit': 'fruit', 'fruits': 'fruit',
    'stem': 'stem', 'stems': 'stem', 'stalk': 'stem', 'petiole': 'stem',
    'root': 'root', 'roots': 'root',
    'tuber': 'tuber', 'tubers': 'tuber',
    'flower': 'flower', 'flowers': 'flower', 'blossom': 'flower', 'blossoms': 'flower',
    'petal': 'flower', 'petals': 'flower',
    'seed': 'seed', 'seeds': 'seed',
    'pod': 'pod', 'pods': 'pod',
    'shoot': 'shoot', 'shoots': 'shoot',
    'twig': 'twig', 'twigs': 'twig',
    'branch': 'branch', 'branches': 'branch',
    'bark': 'bark', 'trunk': 'trunk',
    'crown': 'crown', 'canopy': 'crown',
    'seedling': 'seedling', 'seedlings': 'seedling',
    'plant': 'plant', 'plants': 'plant', 'tree': 'tree', 'trees': 'tree',
    'vine': 'vine', 'vines': 'vine',
    'grain': 'grain', 'grains': 'grain',
    'ear': 'ear', 'ears': 'ear', 'head': 'ear', 'heads': 'ear',
    'berry': 'berry', 'berries': 'berry',
    'bulb': 'bulb', 'bulbs': 'bulb',
    'corm': 'corm', 'corms': 'corm',
    'rhizome': 'rhizome', 'needle': 'needle', 'needles': 'needle',
}


def normalize_host(caption, virus_name):
    """从 caption/virus_name 提取并归一化宿主名"""
    text = (caption + ' ' + virus_name).lower()
    found = []
    for common, (latin, cn) in HOST_MAP.items():
        if common in text:
            if common not in found:
                found.append(common)
    return found


def normalize_virus(eppo_name):
    """用关键词匹配把 EPPO 病毒名映射到 NCBI/ICTV 拉丁名"""
    name_lower = eppo_name.lower().strip()
    # Direct lookup (full name, Virus name(s), etc.)
    if name_lower in virus_map:
        return virus_map[name_lower]
    # Try without trailing 'virus' word
    stripped = re.sub(r'\s+virus$', '', name_lower).strip()
    if stripped in virus_map:
        return virus_map[stripped]
    # Word-by-word: find the best match (longest matching word)
    words = name_lower.split()
    best = None
    for w in words:
        if len(w) > 4 and w in virus_map:
            if best is None or len(w) > len(best):
                best = w
    if best and best in virus_map:
        return virus_map[best]
    return (eppo_name, eppo_name)


def normalize_parts(caption):
    """标准化植物部位"""
    text = caption.lower()
    parts = set()
    for orig, std in PART_MAP.items():
        if orig in text:
            parts.add(std)
    return sorted(parts)


def normalize_symptoms(caption):
    """提取并标准化症状关键词"""
    SYM = [
        'mosaic', 'mottle', 'yellowing', 'chlorosis', 'chlorotic',
        'necrosis', 'necrotic', 'wilt', 'wilting', 'stunting', 'stunted', 'dwarfing',
        'ringspot', 'leaf curl', 'leafroll', 'crinkle', 'crinkling',
        'vein clearing', 'vein banding', 'streak', 'stripe',
        'blotch', 'spot', 'spotting', 'lesion', 'scorch',
        'dieback', 'canker', 'distortion', 'malformation',
        'mosaic symptom', 'yellow vein', 'yellow mosaic',
    ]
    text = caption.lower()
    found = []
    for s in SYM:
        if s in text:
            found.append(s)
    return found


# ── 2. 处理数据 ──────────────────────────
df = pl.read_csv(EPPO, separator='\t', ignore_errors=True)

output = []
for row in df.iter_rows(named=True):
    cap = row.get('caption') or ''
    vname = row.get('virus_name') or ''

    # Virus: try to map to Latin
    virus_latin = normalize_virus(vname)

    # Host
    host_common = normalize_host(cap, vname)
    host_latin = []
    for hc in host_common:
        info = HOST_MAP.get(hc)
        if info:
            host_latin.append({'latin': info[0], 'cn': info[1], 'common': hc})

    # Parts
    parts = normalize_parts(cap)

    # Symptoms
    symptoms = normalize_symptoms(cap)

    output.append({
        "code": row.get('eppo_code', ''),
        "virus": vname,
        "virus_latin": virus_latin[0],
        "virus_ictv": virus_latin[1],
        "photo_id": str(row.get('photo_id', '')),
        "thumb": row.get('thumb_url', ''),
        "full": row.get('full_url', ''),
        "caption": cap,
        "photographer": row.get('photographer', ''),
        "hosts": [h['common'] for h in host_latin],
        "hosts_latin": [h['latin'] for h in host_latin],
        "hosts_cn": [h['cn'] for h in host_latin],
        "symptoms": symptoms,
        "parts": parts,
        "page": row.get('photo_page', '')
    })

with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False)

print(f"Normalized: {len(output)} photos -> {OUT_JSON}")

# Stats
with_latin = sum(1 for r in output if r['virus'] != r['virus_latin'])
with_host = sum(1 for r in output if r['hosts_latin'])
with_part = sum(1 for r in output if r['parts'])
with_symp = sum(1 for r in output if r['symptoms'])
print(f"  Virus Latin matched: {with_latin}/{len(output)}")
print(f"  Host matched: {with_host}")
print(f"  Parts matched: {with_part}")
print(f"  Symptoms matched: {with_symp}")

# Show samples
for r in output[:5]:
    print(f"\n  [{r['code']}] {r['virus'][:50]} → {r['virus_latin'][:50]}")
    if r['hosts_latin']:
        print(f"    Hosts: {', '.join(r['hosts_latin'][:3])}")
    if r['parts']:
        print(f"    Parts: {', '.join(r['parts'][:5])}")
    if r['symptoms']:
        print(f"    Symptoms: {', '.join(r['symptoms'][:5])}")
