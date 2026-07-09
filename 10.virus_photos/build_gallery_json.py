#!/usr/bin/env python3
"""将 EPPO 图片数据转为网页 JSON, 自动提取 host/symptom/part 标签"""
import polars as pl, json, re

EPPO = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\eppo_virus_photos.tsv"
OUT = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data\eppo_gallery.json"

df = pl.read_csv(EPPO, separator='\t', ignore_errors=True)

# Keyword dictionaries
HOSTS = [
    'potato','tomato','tobacco','pepper','cucumber','melon','watermelon','squash','zucchini',
    'pumpkin','bean','soybean','pea','cowpea','chickpea','peanut','groundnut','sunflower',
    'wheat','barley','oat','rye','rice','maize','corn','sorghum','sugarcane',
    'apple','pear','plum','peach','cherry','apricot','citrus','orange','lemon','lime','grapefruit',
    'grape','grapevine','banana','papaya','strawberry','blueberry','raspberry','blackberry',
    'cassava','sweet potato','yam','taro','carrot','onion','garlic','leek','cabbage',
    'cauliflower','broccoli','lettuce','spinach','celery','parsley','beetroot','radish',
    'cotton','flax','hemp','hop','tea','coffee','cocoa','rubber','oil palm','coconut',
    'rose','chrysanthemum','carnation','orchid','lily','tulip','daffodil','iris',
    'petunia','zinnia','impatiens','geranium','begonia','hydrangea','dahlia',
    'oak','pine','spruce','fir','birch','maple','elm','poplar','willow',
    'alfalfa','clover','ryegrass','fescue','bentgrass','bermuda','st augustine',
    'capsicum','chilli','eggplant','courgette','marrow','gourd','okra',
    'Nicotiana','Solanum','Cucumis','Citrullus','Phaseolus','Vigna','Arachis',
    'Prunus','Malus','Pyrus','Vitis','Musa','Fragaria','Rubus','Manihot',
    'Chenopodium','Datura','Petunia','Nicandra',
]
SYMPTOMS = [
    'mosaic','mottle','yellow','chlorosis','chlorotic','necrosis','necrotic',
    'wilt','wilting','stunt','stunted','dwarf','dwarfing','ringspot','ring spot',
    'leaf curl','leafroll','leaf roll','crinkle','crinkling','pucker','puckering',
    'blister','blistering','vein clearing','vein banding','vein yellowing',
    'streak','stripe','striate','line pattern','etch','etching',
    'blotch','blotching','spot','spotting','lesion','scorch','scorching',
    'dieback','canker','gall','tumor','enation','enations',
    'distortion','deformation','malformation','rosette','witches broom',
    'reddening','purpling','bronzing','silvering',
    'tip necrosis','margin necrosis','internal necrosis','net necrosis',
    'fruit necrosis','stem necrosis','leaf necrosis','vein necrosis',
]
PARTS = [
    'leaf','leaves','fruit','fruits','stem','stems','root','roots','tuber','tubers',
    'flower','flowers','blossom','blossoms','petal','petals','seed','seeds','pod','pods',
    'shoot','shoots','twig','twigs','branch','branches','bark','trunk','crown',
    'seedling','seedlings','plant','plants','tree','trees','vine','vines',
    'grain','grains','ear','ears','head','heads','berry','berries','bulb','bulbs',
    'corm','corms','rhizome','needle','needles','whole plant','canopy',
]

output = []
for row in df.iter_rows(named=True):
    cap = (row.get('caption') or '').lower()
    name = (row.get('virus_name') or '')

    # Extract hosts
    hosts = []
    for h in HOSTS:
        if h.lower() in cap or h.lower() in name.lower():
            if h not in hosts:
                hosts.append(h)

    # Extract symptoms
    symps = []
    for s in SYMPTOMS:
        if s in cap:
            symps.append(s)

    # Extract plant parts
    parts = []
    for p in PARTS:
        if p in cap:
            parts.append(p)

    output.append({
        "code": row.get('eppo_code',''),
        "virus": name,
        "photo_id": str(row.get('photo_id','')),
        "thumb": row.get('thumb_url',''),
        "full": row.get('full_url',''),
        "caption": row.get('caption',''),
        "photographer": row.get('photographer',''),
        "hosts": hosts[:10],
        "symptoms": symps[:8],
        "parts": parts[:6],
        "page": row.get('photo_page','')
    })

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False)

print(f"Gallery JSON: {len(output)} photos -> {OUT}")

# Stats
all_hosts = {}; all_symps = {}; all_parts = {}
for r in output:
    for h in r['hosts']: all_hosts[h] = all_hosts.get(h,0)+1
    for s in r['symptoms']: all_symps[s] = all_symps.get(s,0)+1
    for p in r['parts']: all_parts[p] = all_parts.get(p,0)+1
for label, d in [("Hosts",all_hosts),("Symptoms",all_symps),("Parts",all_parts)]:
    top = sorted(d.items(), key=lambda x:-x[1])[:15]
    print(f"\nTop {label}: {', '.join(f'{k}({v})' for k,v in top)}")
