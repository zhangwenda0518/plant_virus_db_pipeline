#!/usr/bin/env python3
"""全量PDF解析：判断含病毒名+宿主+症状的论文。支持断点续跑。"""
import os, re, csv, fitz, json
from pathlib import Path

BASE = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\7.literature_tracker\pubmed_records")
OUT = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_papers_structured.tsv")
PROGRESS = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_papers_progress.txt")
FAILED = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\all_papers_failed.txt")


def _write_failed(failed):
    """失败清单：解析失败的 PDF 不写入 done，重跑自动重试（审计 D4 断点污染修复）。"""
    try:
        with open(FAILED, 'w', encoding='utf-8') as f:
            f.write("# 解析失败、未标记 done 的 PDF（重跑本脚本即可重试）\n")
            for p, err in failed:
                f.write(f"{p}\t{err}\n")
    except Exception as e:
        print(f"  (write failed list error: {e})")

# ── 提取器（同前） ──
VIRUS_RE = re.compile(r'([A-Z][a-z]+(?:\s+[a-z]+){1,4}\s+virus)', re.IGNORECASE)
VIRUS_ABBR = re.compile(r'\b([A-Z]{3,5}[Vv])\b')
VIRUS_EXCLUDE = {'DPV','FIG','TAB','PCR','ELISA','TEM','SEM','RNA','DNA','cDNA'}

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
    r'Cyphomandra\s+\w+|Abelmoschus\s+\w+|Lens\s+\w+|Cicer\s+\w+|'
    r'Zantedeschia\s+\w+|Raphanus\s+\w+|Populus\s+\w+|Salix\s+\w+|'
    r'Quercus\s+\w+|Pinus\s+\w+|Cannabis\s+\w+|Cynara\s+\w+|'
    r'Eucalyptus\s+\w+|Agave\s+\w+|Yucca\s+\w+|Catharanthus\s+\w+|'
    r'Gomphrena\s+\w+|Tetragonia\s+\w+)\b', re.IGNORECASE)

HOST_CMN = ['tomato','tobacco','potato','cucumber','pepper','capsicum','chilli',
    'bean','soybean','pea','cowpea','wheat','barley','maize','corn','rice',
    'sugarcane','sorghum','cassava','lettuce','spinach','cabbage','carrot','onion',
    'garlic','apple','grape','grapevine','banana','papaya','citrus','strawberry',
    'peanut','cotton','sunflower','arabidopsis','nicotiana','squash','zucchini',
    'pumpkin','watermelon','melon','alfalfa','clover','eggplant','rose',
    'chrysanthemum','petunia','lily','cannabis','lentil','chickpea',
    'sugar beet','beet','radish','cherry','peach','plum','celery','okra',
    'carnation','calla lily','sweet potato','yam','rubber','tea','coffee',
    'cocoa','coconut','pineapple','mango','guava','kiwi','avocado','hop','hemp',
    'flax','millet','rye','oat','tulip','daffodil','iris','dahlia','geranium',
    'begonia','hydrangea','willow','poplar','oak','pine','raspberry','blueberry',
    'blackberry','almond','apricot','pear','fig','olive','pomegranate','date',
    'oil palm','orchid','gladiolus','parsley','basil','mint','turnip','leek',
    'groundnut',
]

SYMP = ['symptom','mosaic','mottle','necrosis','necrotic','chlorosis','chlorotic',
    'yellowing','yellow','stunting','stunted','stunt','dwarf','ringspot','ring spot',
    'streak','stripe','leaf curl','leaf roll','leafroll','curling','crinkle',
    'distortion','malformation','deformation','wilt','wilting','blister','blistering',
    'vein clearing','vein banding','etch','lesion','spot','blotch','dieback','canker',
    'scorch','decline','rosette','enation','reddening','mild mottle','severe',
    'systemic','mosaic symptom','vein yellowing','tip necrosis','internal necrosis',
    'gall','tumor','witches broom','line pattern','ring pattern',
]

def extract_fields(text):
    tl = text.lower()
    viruses = set()
    for m in VIRUS_RE.finditer(text):
        v = m.group(1).strip()
        if len(v) > 8 and v.count(' ') >= 2: viruses.add(v)
    for m in VIRUS_ABBR.finditer(text):
        v = m.group(1)
        if v not in VIRUS_EXCLUDE: viruses.add(v)
    for m in re.finditer(r'(?:named|tentatively named|designated|proposed)\s+([A-Z][a-z]+(?:\s+[a-z]+){0,3}\s+virus)', text, re.IGNORECASE):
        viruses.add(m.group(1))
    
    hosts = set()
    for m in HOST_LATIN.finditer(text):
        hosts.add(m.group(1))
    for h in HOST_CMN:
        if h in tl: hosts.add(h)
    
    symptoms = [k for k in SYMP if k in tl]
    return sorted(viruses), sorted(hosts), symptoms

# ── 找所有PDF ──
all_pdfs = []
for root, dirs, files in os.walk(BASE):
    for f in files:
        if f.endswith('.pdf'): all_pdfs.append(os.path.join(root, f))
print(f"总PDF: {len(all_pdfs)}")

# ── 断点续跑 ──
done = set()
if PROGRESS.exists():
    with open(PROGRESS) as f:
        done = set(line.strip() for line in f)

existing = []
if OUT.exists():
    with open(OUT, 'r', encoding='utf-8') as f:
        existing = list(csv.reader(f, delimiter='\t'))
    print(f"已有结果: {len(existing)-1} 行")

# ── 处理 ──
results = existing[1:] if len(existing) > 1 else []  # skip header
stats = {'ok': len(done), 'fail': 0, 'all3': sum(1 for r in results if len(r) > 12 and r[12] == '3')}
failed = []   # (pdf_path, error)：失败不进 done（audit D4：解析失败也标 done 致断点污染）

for i, pdf_path in enumerate(all_pdfs):
    if pdf_path in done: continue
    fname = os.path.basename(pdf_path)
    
    # 提取DOI
    doi_m = re.search(r'(10[._]\d{4,}[._/][^\s]+)', fname.replace('.pdf', ''))
    doi = doi_m.group(1).replace('_', '/') if doi_m else ''
    
    try:
        doc = fitz.open(pdf_path)
        text = ''
        for pi in range(min(10, len(doc))):
            text += doc[pi].get_text() + '\n'
        doc.close()
        
        if len(text) < 100:
            # 文本过少（扫描件/损坏）：不标 done，重跑可重试；记入失败清单
            stats['fail'] += 1
            failed.append((pdf_path, f"text too short ({len(text)} chars)"))
        else:
            viruses, hosts, symptoms = extract_fields(text)
            hv, hh, hs = len(viruses) > 0, len(hosts) > 0, len(symptoms) > 0
            score = (1 if hv else 0) + (1 if hh else 0) + (1 if hs else 0)
            
            results.append([
                doi, fname[:80],
                '; '.join(viruses[:10]), '; '.join(hosts[:10]), '; '.join(symptoms[:10]),
                'YES' if hv else 'NO', 'YES' if hh else 'NO', 'YES' if hs else 'NO',
                str(score), str(len(text))
            ])
            
            stats['ok'] += 1
            if hv and hh and hs: stats['all3'] += 1
            done.add(pdf_path)          # 仅成功才进 done，重跑不重做
    except Exception as e:
        stats['fail'] += 1
        failed.append((pdf_path, f"{type(e).__name__}: {e}"[:200]))
    
    if stats['ok'] % 500 == 0:
        print(f"  {stats['ok']}/{len(all_pdfs)} | all3:{stats['all3']} fail:{stats['fail']}")
        with open(PROGRESS, 'w') as f:
            for d in done: f.write(d + '\n')
        with open(OUT, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, delimiter='\t')
            w.writerow(['DOI','File','Viruses','Hosts','Symptoms','HasVirus','HasHost','HasSymptom','Score','TextLen'])
            w.writerows(results)
        _write_failed(failed)

# ── 最终 ──
with open(PROGRESS, 'w') as f:
    for d in done: f.write(d + '\n')
with open(OUT, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, delimiter='\t')
    w.writerow(['DOI','File','Viruses','Hosts','Symptoms','HasVirus','HasHost','HasSymptom','Score','TextLen'])
    w.writerows(results)
_write_failed(failed)

all3 = sum(1 for r in results if r[8] == '3')
v = sum(1 for r in results if r[5] == 'YES')
h = sum(1 for r in results if r[6] == 'YES')
s = sum(1 for r in results if r[7] == 'YES')
print(f"\n完成: OK={stats['ok']} fail={stats['fail']}")
print(f"三要素齐全: {all3}")
print(f"有病毒: {v} 有宿主: {h} 有症状: {s}")
print(f"失败(未标done, 重跑会重试): {len(failed)} -> {FAILED}")
print(f"输出: {OUT}")
