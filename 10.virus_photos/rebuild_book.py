"""
Rebuild book_gallery.json - 100 entries with rich captions and tags.
"""
import re, json, os, shutil
from docx import Document

DOCX = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\15587070.docx"
IMGDIR = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\images"
OUTDIR = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data\book_images"
OUTJSON = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data\book_gallery.json"

os.makedirs(IMGDIR, exist_ok=True)
os.makedirs(OUTDIR, exist_ok=True)

doc = Document(DOCX)
paragraphs = [(i, p.text.strip()) for i, p in enumerate(doc.paragraphs)]

# ---- Step 1: Parse species entries ----
species_entries = []
for idx, text in paragraphs:
    if not text:
        continue
    # "N. Chinese_name(种拉丁名：Latin)"
    m1 = re.match(r'^(\d+)\.\s*(.+?)\(种拉丁名[：:]\s*(.+?)\)$', text)
    if m1:
        num = int(m1.group(1))
        sp_cn = m1.group(2).strip()
        sp_latin = m1.group(3).strip().rstrip(')')
        if 1 <= num <= 100 and not any(e[1] == num for e in species_entries):
            species_entries.append((idx, num, sp_cn, sp_latin))
            continue
    # "N. Chinese_name" without Latin
    m2 = re.match(r'^(\d+)\.\s*(\S.+)$', text)
    if m2:
        num = int(m2.group(1))
        sp_cn = m2.group(2).strip()
        if 1 <= num <= 100 and len(sp_cn) >= 2 and not any(e[1] == num for e in species_entries):
            species_entries.append((idx, num, sp_cn, ""))

print(f"Found {len(species_entries)} species")

# ---- Step 2: For each entry, collect rich text ----
entries = []
for pi, (sidx, num, sp_cn, sp_latin) in enumerate(species_entries):
    if pi + 1 < len(species_entries):
        next_sidx = species_entries[pi + 1][0]
    else:
        next_sidx = len(paragraphs)

    related = [(i, t) for i, t in paragraphs if sidx < i < next_sidx and t]

    virus_texts = []
    desc_text = ""
    figures = []
    all_text = []

    for pidx, ptext in related:
        all_text.append(ptext)

        # Figure reference
        fm = re.match(r'图\s*(\d+)\s+', ptext)
        if fm:
            figures.append({"num": int(fm.group(1)), "caption": ptext})
            continue

        # First long paragraph = description
        if len(ptext) > 80 and not desc_text:
            desc_text = ptext
            continue

        # After description, collect virus/disease text
        virus_texts.append(ptext)

    # Build rich caption: species - virus info
    virus_full = " ".join(virus_texts)
    caption_rich = sp_cn + " - " + virus_full[:800]

    if not virus_full.strip():
        caption_rich = sp_cn

    entries.append({
        "entry_num": num,
        "species_cn": sp_cn,
        "species_latin": sp_latin,
        "num_figures": len(figures),
        "figure_nums": [f["num"] for f in figures],
        "figure_captions": [f["caption"][:200] for f in figures],
        "caption_rich": caption_rich,
        "virus_text": virus_full[:1500],
        "para_start": sidx,
        "para_end": next_sidx,
    })

# ---- Step 3: Extract images from docx and map to entries ----
nsmap = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}

# Collect all image relationships
image_rels = {}
for rel in doc.part.rels.values():
    if "image" in rel.reltype:
        image_rels[rel.rId] = rel

# Map paragraph index to image rIds
para_to_imgs = {}
for pi, para_elem in enumerate(doc.element.body):
    blips = para_elem.findall('.//a:blip', nsmap)
    for blip in blips:
        embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
        if embed and embed in image_rels:
            para_to_imgs.setdefault(pi, []).append(embed)

# Find all "图N" figure captions and which entry they belong to
fig_captions = []  # (para_idx, fig_num, entry_num)
for e in entries:
    for pi, text in paragraphs:
        if e["para_start"] <= pi < e["para_end"] and text:
            m = re.match(r'图\s*(\d+)\s+', text)
            if m:
                fig_captions.append((pi, int(m.group(1)), e["entry_num"]))
fig_captions.sort()

# Images: find nearest figure caption (by paragraph distance) and assign to that entry
entry_imgs = {e["entry_num"]: [] for e in entries}
for pi, rids in sorted(para_to_imgs.items()):
    # Find closest figure caption
    best_en, best_dist = None, 99999
    for fpi, fnum, en in fig_captions:
        dist = abs(pi - fpi)
        if dist < best_dist:
            best_dist = dist
            best_en = en
    if best_en:
        entry_imgs[best_en].extend(rids)
    elif entries:
        entry_imgs[entries[0]["entry_num"]].extend(rids)

entry_first_img = {}  # will be list per entry, not just first
for en, rids in entry_imgs.items():
    if rids:
        entry_first_img[en] = rids  # ALL images

for e in entries:
    e["total_imgs"] = len(entry_imgs.get(e["entry_num"], []))

# Extract all images
ext_count = 0
rid_to_file = {}
for en, rids in entry_imgs.items():
    for rid in rids:
        if rid not in rid_to_file:
            rel = image_rels[rid]
            ext = os.path.splitext(rel.target_ref)[1] or '.png'
            if ext.lower() not in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                ext = '.png'
            fname = f"book_img_{ext_count:04d}{ext}"
            rid_to_file[rid] = fname
            ext_count += 1

# Save all images to extracted/
for rid, fname in rid_to_file.items():
    rel = image_rels[rid]
    out_path = os.path.join(IMGDIR, fname)
    if not os.path.exists(out_path):
        with open(out_path, 'wb') as f:
            f.write(rel.target_part.blob)

print(f"Extracted {ext_count} images")

# ---- Step 4: Build gallery JSON ----
# HOST common→Latin map
HOST_MAP = {
    'tomato': 'Solanum lycopersicum', 'tobacco': 'Nicotiana tabacum',
    'potato': 'Solanum tuberosum', 'cucumber': 'Cucumis sativus',
    'pepper': 'Capsicum annuum', 'bean': 'Phaseolus vulgaris',
    'soybean': 'Glycine max', 'pea': 'Pisum sativum',
    'cowpea': 'Vigna unguiculata', 'wheat': 'Triticum aestivum',
    'barley': 'Hordeum vulgare', 'maize': 'Zea mays', 'corn': 'Zea mays',
    'rice': 'Oryza sativa', 'sugarcane': 'Saccharum officinarum',
    'cotton': 'Gossypium hirsutum', 'grape': 'Vitis vinifera',
    'apple': 'Malus domestica', 'peanut': 'Arachis hypogaea',
    'cassava': 'Manihot esculenta', 'strawberry': 'Fragaria x ananassa',
    'watermelon': 'Citrullus lanatus', 'melon': 'Cucumis melo',
    'pumpkin': 'Cucurbita moschata', 'squash': 'Cucurbita pepo',
    'zucchini': 'Cucurbita pepo', 'celery': 'Apium graveolens',
    'banana': 'Musa spp.', 'papaya': 'Carica papaya',
    'sweet potato': 'Ipomoea batatas', 'garlic': 'Allium sativum',
    'onion': 'Allium cepa', 'carrot': 'Daucus carota',
    'lettuce': 'Lactuca sativa', 'spinach': 'Spinacia oleracea',
    'cabbage': 'Brassica oleracea', 'broccoli': 'Brassica oleracea',
    'cauliflower': 'Brassica oleracea', 'sunflower': 'Helianthus annuus',
    'sorghum': 'Sorghum bicolor', 'oat': 'Avena sativa',
    'peach': 'Prunus persica', 'plum': 'Prunus domestica',
    'cherry': 'Prunus avium', 'pear': 'Pyrus communis',
    'apricot': 'Prunus armeniaca', 'rose': 'Rosa spp.',
    'chrysanthemum': 'Chrysanthemum morifolium',
    'petunia': 'Petunia x hybrida', 'dahlia': 'Dahlia pinnata',
    'sugar beet': 'Beta vulgaris', 'beet': 'Beta vulgaris',
    'alfalfa': 'Medicago sativa', 'clover': 'Trifolium spp.',
    'radish': 'Raphanus sativus', 'turnip': 'Brassica rapa',
    'canna': 'Canna indica', 'ginger': 'Zingiber officinale',
    'hibiscus': 'Hibiscus rosa-sinensis', 'eggplant': 'Solanum melongena',
    'coffee': 'Coffea arabica', 'cocoa': 'Theobroma cacao',
    'coconut': 'Cocos nucifera', 'mango': 'Mangifera indica',
    'olive': 'Olea europaea', 'almond': 'Prunus dulcis',
    'walnut': 'Juglans regia', 'pineapple': 'Ananas comosus',
    'date': 'Phoenix dactylifera', 'fig': 'Ficus carica',
    'guava': 'Psidium guajava', 'pomegranate': 'Punica granatum',
    'kiwi': 'Actinidia deliciosa', 'passion fruit': 'Passiflora edulis',
    'hop': 'Humulus lupulus', 'hemp': 'Cannabis sativa',
    'rubber': 'Hevea brasiliensis', 'tea': 'Camellia sinensis',
}

def build_hosts_latin(hosts):
    result = []
    for h in hosts:
        common = ''
        for c, l in HOST_MAP.items():
            if l == h:
                common = c
                break
        result.append({'latin': h, 'cn': common or h, 'common': common})
    return result

gallery = []
for e in entries:
    en = e["entry_num"]
    code = f"BOOK{en:03d}"
    caption = e["caption_rich"]
    virus_latin = e["species_latin"]
    rids = entry_imgs.get(en, [])

    if rids:
        for ii, rid in enumerate(rids):
            fname = rid_to_file.get(rid, '')
            if not fname:
                fname = f"book_img_{ii:04d}.png"
            img_path = f"data/book_images/{fname}"
            ext = os.path.splitext(fname)[1] or '.png'
            photo_id = f"book_{en:03d}_{ii+1:02d}{ext}"
            gallery.append({
                "code": code,
                "virus": e["species_cn"],
                "virus_latin": virus_latin,
                "photo_id": photo_id,
                "thumb": img_path,
                "full": img_path,
                "caption": caption,
                "photographer": "Yang Caixia",
                "hosts": [],
                "hosts_latin": [],
                "symptoms": [],
                "parts": [],
                "page": "",
                "source": "Book"
            })
    else:
        gallery.append({
            "code": code,
            "virus": e["species_cn"],
            "virus_latin": virus_latin,
            "photo_id": f"book_{en:03d}_na",
            "thumb": "",
            "full": "",
            "caption": caption,
            "photographer": "Yang Caixia",
            "hosts": [],
            "hosts_latin": [],
            "symptoms": [],
            "parts": [],
            "page": "",
            "source": "Book"
        })

# ---- Step 5: Extract tags ----
SYMP_KW = {
    'mosaic': 'mosaic', 'mottle': 'mottle', 'necrosis': 'necrosis',
    'chlorosis': 'chlorosis', 'yellowing': 'yellowing', 'yellow': 'yellowing',
    'stunt': 'stunting', 'ringspot': 'ringspot', 'spot': 'spot',
    'streak': 'streak', 'wilt': 'wilt', 'leaf curl': 'leaf curl',
    'curl': 'leaf curl', 'blister': 'blister', 'distortion': 'distortion',
    'crinkle': 'crinkle', 'vein banding': 'vein banding',
    'vein clearing': 'vein clearing', 'etch': 'etch', 'lesion': 'lesion',
    'dwarf': 'dwarf', 'rosette': 'rosette', 'mild mottle': 'mottle',
}

PART_KW = {
    'leaf': 'leaf', 'leaves': 'leaf', 'fruit': 'fruit', 'fruits': 'fruit',
    'stem': 'stem', 'stems': 'stem', 'root': 'root', 'roots': 'root',
    'flower': 'flower', 'flowers': 'flower', 'seed': 'seed', 'seeds': 'seed',
    'pod': 'pod', 'pods': 'pod', 'shoot': 'shoot', 'shoots': 'shoot',
    'tuber': 'tuber', 'tubers': 'tuber', 'bulb': 'bulb', 'bulbs': 'bulb',
    'bark': 'bark', 'branch': 'branch', 'branches': 'branch',
    'grain': 'grain', 'berry': 'fruit', 'berries': 'fruit',
    'seedling': 'seedling', 'seedlings': 'seedling', 'leaflet': 'leaf',
}

for d in gallery:
    cap_lower = (d['caption'] + ' ' + d['virus'] + ' ' + d['virus_latin']).lower()

    # Hosts from common name mentions
    hosts = []
    for common, latin in HOST_MAP.items():
        if common.lower() in cap_lower and latin not in hosts:
            hosts.append(latin)
    # Also add the species itself as host
    if d['virus_latin'] and d['virus_latin'] not in hosts:
        hosts.append(d['virus_latin'])
    d['hosts'] = hosts
    d['hosts_latin'] = build_hosts_latin(hosts)

    # Symptoms
    symptoms = []
    for kw, std in SYMP_KW.items():
        if kw in cap_lower and std not in symptoms:
            symptoms.append(std)
    d['symptoms'] = symptoms

    # Parts
    parts = []
    for kw, std in PART_KW.items():
        if kw in cap_lower and std not in parts:
            parts.append(std)
    d['parts'] = parts

# ---- Save ----
with open(OUTJSON, 'w', encoding='utf-8') as f:
    json.dump(gallery, f, ensure_ascii=False, indent=2)

# Copy images to OUTDIR
existing = set(os.listdir(OUTDIR))
copied = 0
for rids in entry_imgs.values():
    for rid in rids:
        fname = rid_to_file[rid]
        if fname not in existing:
            src = os.path.join(IMGDIR, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(OUTDIR, fname))
                copied += 1

# Stats
has_h = sum(1 for x in gallery if x.get('hosts') and len(x['hosts']) > 0)
has_s = sum(1 for x in gallery if x.get('symptoms') and len(x['symptoms']) > 0)
has_p = sum(1 for x in gallery if x.get('parts') and len(x['parts']) > 0)
no_img = sum(1 for x in gallery if not x['full'])
unique_codes = len(set(x['code'] for x in gallery))

print(f"\nFinal gallery: {len(gallery)} entries, {unique_codes} species")
print(f"Has hosts: {has_h}, Has symptoms: {has_s}, Has parts: {has_p}")
print(f"Entries without images: {no_img}")
print(f"Images in OUTDIR: {len(os.listdir(OUTDIR))}")

# Show a few entries
for d in gallery[:3]:
    print(f"\n--- {d['code']} ---")
    print(f"Caption: {d['caption'][:150]}")
    print(f"Hosts: {d['hosts'][:3]}")
    print(f"Symptoms: {d['symptoms'][:5]}")
    print(f"Parts: {d['parts'][:3]}")
    print(f"Image: {d['full']}")
