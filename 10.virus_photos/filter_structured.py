#!/usr/bin/env python3
"""对 new_virus_candidates.tsv 做结构化筛选（病毒名/宿主/症状）+ 完整性评分 → new_virus_filtered.tsv。

注：此前全文缺少 import，脚本从未跑通（审计 D4）。
"""
import csv
import re

CANDIDATES = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\new_virus_candidates.tsv"
OUT = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\new_virus_filtered.tsv"

# ── 病毒名提取 ──
VIRUS_RE = re.compile(r'([A-Z][a-z]+(?:\s+[a-z]+){1,4}\s+virus)', re.IGNORECASE)
VIRUS_ABBR = re.compile(r'\b([A-Z]{3,5}[Vv])\b')
VIRUS_EXCLUDE = {'DPV','FIG','TAB','PCR','ELISA','TEM','SEM','RNA','DNA','cDNA','This','That','Both','Such','Most','Some','Other','Plant','From','These','Those','First','Novel','Nov.'}

# ── 宿主提取 ──
HOST_LATIN = re.compile(
    r'\b(Nicotiana\s+\w+|Solanum\s+\w+|Cucumis\s+\w+|Arabidopsis\s+\w+|'
    r'Phaseolus\s+\w+|Vigna\s+\w+|Glycine\s+\w+|Zea\s+\w+|Triticum\s+\w+|'
    r'Oryza\s+\w+|Hordeum\s+\w+|Capsicum\s+\w+|Manihot\s+\w+|Citrullus\s+\w+|'
    r'Cucurbita\s+\w+|Brassica\s+\w+|Prunus\s+\w+|Malus\s+\w+|Vitis\s+\w+|'
    r'Musa\s+\w+|Citrus\s+\w+|Beta\s+\w+|Carica\s+\w+|Petunia\s+\w+|'
    r'Chenopodium\s+\w+|Helianthus\s+\w+|Fragaria\s+\w+|Rosa\s+\w+|'
    r'Arachis\s+\w+|Gossypium\s+\w+|Daucus\s+\w+|Allium\s+\w+|'
    r'Lactuca\s+\w+|Spinacia\s+\w+|Ipomoea\s+\w+|Pisum\s+\w+|'
    r'Medicago\s+\w+|Sorghum\s+\w+|Saccharum\s+\w+|Datura\s+\w+|'
    r'Dianthus\s+\w+|Lilium\s+\w+|Tulipa\s+\w+|Gladiolus\s+\w+|'
    r'Iris\s+\w+|Pelargonium\s+\w+|Dahlia\s+\w+|Rubus\s+\w+|'
    r'Vaccinium\s+\w+|Ficus\s+\w+|Olea\s+\w+|Coffea\s+\w+|'
    r'Theobroma\s+\w+|Cocos\s+\w+|Persea\s+\w+|Mangifera\s+\w+|'
    r'Ananas\s+\w+|Actinidia\s+\w+|Humulus\s+\w+|Linum\s+\w+|'
    r'Secale\s+\w+|Avena\s+\w+|Panicum\s+\w+|Passiflora\s+\w+|'
    r'Camellia\s+\w+|Apium\s+\w+|Petroselinum\s+\w+|Ocimum\s+\w+|'
    r'Mentha\s+\w+|Cydonia\s+\w+|Juglans\s+\w+|Phoenix\s+\w+|'
    r'Punica\s+\w+|Hevea\s+\w+|Elaeis\s+\w+|Psidium\s+\w+|'
    r'Persea\s+\w+|Cyphomandra\s+\w+|Abelmoschus\s+\w+|Lens\s+\w+|'
    r'Cicer\s+\w+|Zantedeschia\s+\w+|Raphanus\s+\w+|Populus\s+\w+|'
    r'Salix\s+\w+|Quercus\s+\w+|Pinus\s+\w+|Cannabis\s+\w+|'
    r'Cynara\s+\w+|Eucalyptus\s+\w+|Agave\s+\w+|Yucca\s+\w+|'
    r'Catharanthus\s+\w+|Gomphrena\s+\w+|Tetragonia\s+\w+)\b', re.IGNORECASE)

HOST_CMN = ['tomato','tobacco','potato','cucumber','pepper','capsicum','chilli',
    'bean','soybean','pea','cowpea','wheat','barley','maize','corn','rice',
    'sugarcane','sorghum','cassava','lettuce','spinach','cabbage','carrot','onion',
    'garlic','apple','grape','grapevine','banana','papaya','citrus','strawberry',
    'peanut','cotton','sunflower','arabidopsis','nicotiana','squash','zucchini',
    'pumpkin','watermelon','melon','alfalfa','clover','eggplant','rose',
    'chrysanthemum','petunia','lily','cannabis','lentil','chickpea',
    'sugar beet','beet','radish','cherry','peach','plum','celery','okra',
    'carnation','calla lily','sweet potato','yam','cassava','rubber','tea',
    'coffee','cocoa','coconut','pineapple','mango','guava','kiwi','avocado',
    'hop','hemp','flax','millet','rye','oat','tulip','daffodil','iris',
    'dahlia','geranium','begonia','hydrangea','willow','poplar','oak','pine',
    'raspberry','blueberry','blackberry','almond','apricot','pear','fig','olive',
    'pomegranate','date','oil palm','orchid','gladiolus','parsley','basil','mint',
    'turnip','leek','chickpea','cowpea','groundnut',
]

# ── 症状提取 ──
SYMPTOMS = ['symptom','mosaic','mottle','necrosis','necrotic','chlorosis','chlorotic',
    'yellowing','yellow','stunting','stunted','stunt','dwarf','ringspot','ring spot',
    'streak','stripe','leaf curl','leaf roll','leafroll','curling','crinkle',
    'distortion','malformation','deformation','wilt','wilting','blister','blistering',
    'vein clearing','vein banding','etch','lesion','spot','blotch','dieback','canker',
    'scorch','decline','rosette','enation','reddening','mild mottle','severe',
    'systemic','mosaic symptom','vein yellowing','tip necrosis','internal necrosis',
    'gall','tumor','witches broom','line pattern','ring pattern',
]


def extract_fields(text):
    """从文本提取病毒名/宿主/症状"""
    tl = text.lower()
    
    viruses = set()
    for m in VIRUS_RE.finditer(text):
        v = m.group(1).strip()
        if len(v) > 8 and v.count(' ') >= 2:
            viruses.add(v)
    for m in VIRUS_ABBR.finditer(text):
        v = m.group(1)
        if v not in VIRUS_EXCLUDE:
            viruses.add(v)
    # 也匹配" named X virus" 模式
    for m in re.finditer(r'(?:named|tentatively named|designated|proposed)\s+([A-Z][a-z]+(?:\s+[a-z]+){0,3}\s+virus)', text, re.IGNORECASE):
        viruses.add(m.group(1))
    
    hosts = set()
    for m in HOST_LATIN.finditer(text):
        hosts.add(m.group(1))
    for h in HOST_CMN:
        if h in tl:
            hosts.add(h)
    
    symptoms = [k for k in SYMPTOMS if k in tl]
    
    return sorted(viruses), sorted(hosts), symptoms


# ── 筛选 ──
with open(CANDIDATES, 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))

print(f"Total candidates: {len(rows)}")

results = []
for r in rows:
    text = (r.get('Title','') + ' ' + r.get('First100_Abstract','')).strip()
    viruses, hosts, symptoms = extract_fields(text)
    
    has_v = len(viruses) > 0
    has_h = len(hosts) > 0
    has_s = len(symptoms) > 0
    
    # 评分：三要素齐全的排前面
    score = (3 if has_v else 0) + (2 if has_h else 0) + (1 if has_s else 0)
    
    results.append({
        **r,
        'viruses_found': '; '.join(viruses[:8]),
        'hosts_found': '; '.join(hosts[:8]),
        'symptoms_found': '; '.join(symptoms[:8]),
        'has_virus': 'YES' if has_v else 'NO',
        'has_host': 'YES' if has_h else 'NO',
        'has_symptom': 'YES' if has_s else 'NO',
        'completeness': score,
    })

results.sort(key=lambda x: -x['completeness'])

# ── 统计 ──
all3 = sum(1 for r in results if r['completeness'] >= 6)  # 病毒+宿主都有的
has_pdf_all3 = sum(1 for r in results if r['completeness'] >= 6 and r['HasPDF'] == 'YES')
v_only = sum(1 for r in results if r['has_virus'] == 'YES')
h_only = sum(1 for r in results if r['has_host'] == 'YES')
s_only = sum(1 for r in results if r['has_symptom'] == 'YES')

print(f"病毒+宿主+症状齐全: {all3}")
print(f"  其中有PDF: {has_pdf_all3}")
print(f"有病毒名: {v_only}")
print(f"有宿主: {h_only}")
print(f"有症状: {s_only}")

# ── 输出 ──
with open(OUT, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f, delimiter='\t')
    writer.writerow(['PMID','Year','DOI','Journal','Title','Viruses','Hosts','Symptoms','HasVirus','HasHost','HasSymp','Score','HasPDF','First100'])
    for r in results:
        writer.writerow([
            r['PMID'], r['Year'], r['DOI'], r['Journal'],
            r['Title'][:250],
            r['viruses_found'], r['hosts_found'], r['symptoms_found'],
            r['has_virus'], r['has_host'], r['has_symptom'],
            r['completeness'], r['HasPDF'],
            r.get('First100_Abstract','')[:100]
        ])

print(f"\n输出: {OUT}")

# Top 20
print(f"\n=== 三要素齐全且有PDF (前20) ===")
for r in results:
    if r['completeness'] >= 6 and r['HasPDF'] == 'YES':
        print(f"  [{r['Year']}] {r['Title'][:100]}")
        print(f"    V: {r['viruses_found'][:100]}")
        print(f"    H: {r['hosts_found'][:80]}")
        print(f"    S: {r['symptoms_found'][:80]}")
        has_pdf_all3 -= 1
        if has_pdf_all3 <= 0: break
