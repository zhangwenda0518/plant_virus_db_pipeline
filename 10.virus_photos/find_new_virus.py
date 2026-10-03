#!/usr/bin/env python3
"""
增强版：new virus候选 + 症状照片可能性评分
大王筛选后精准提取
"""

import os, re, json, xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\7.literature_tracker\pubmed_records")
OUT = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\new_virus_candidates.tsv")

NEW_VIRUS_KW = [
    'novel virus', 'new virus', 'new plant virus', 'novel plant virus',
    'first report of', 'first record of',
    'complete genome sequence of a novel',
    'complete genome of a novel',
    'molecular characterization of a novel',
    'characterization of a novel',
    'identification of a novel',
    'discovery of a novel',
    'a novel virus infecting',
    'a new virus infecting',
    'novel species of',
    'new species of'  # might be too broad
]

# 排他关键词（review/overview等不太可能有原始症状照片）
EXCLUDE_TYPES = [
    'review', 'overview', 'perspective', 'mini-review', 'minireview',
    'special issue', 'editorial', 'commentary', 'book review',
    'meeting report', 'conference report',
]

# 症状照片可能性信号
PHOTO_SIGNALS = [
    'symptom', 'leaf', 'leaves', 'fruit', 'field', 'disease',
    'mosaic', 'necrosis', 'chlorosis', 'stunt', 'yellowing',
    'naturally infected', 'survey', 'outbreak',
]

def extract_pubmed_articles(xml_path):
    articles = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for article in root.findall('.//PubmedArticle'):
            try:
                pmid = article.find('.//PMID')
                pmid = pmid.text if pmid is not None else ''
                
                title_elem = article.find('.//ArticleTitle')
                title = title_elem.text if title_elem is not None else ''
                if not title:
                    continue
                
                abstract_parts = []
                for abs_text in article.findall('.//AbstractText'):
                    label = abs_text.get('Label', '')
                    text = abs_text.text or ''
                    abstract_parts.append(f"{label}: {text}" if label else text)
                abstract = ' '.join(abstract_parts)
                
                doi = ''
                for eid in article.findall('.//ELocationID'):
                    if eid.get('EIdType') == 'doi':
                        doi = eid.text or ''; break
                if not doi:
                    for aid in article.findall('.//ArticleId'):
                        if aid.get('IdType') == 'doi':
                            doi = aid.text or ''; break
                
                journal = ''
                jt = article.find('.//Journal/Title')
                if jt is not None: journal = jt.text or ''
                
                year = ''
                pd = article.find('.//PubDate/Year')
                if pd is not None: year = pd.text or ''
                
                # Publication type
                pub_types = []
                for pt in article.findall('.//PublicationType'):
                    pub_types.append(pt.text.lower() if pt.text else '')
                
                articles.append({
                    'pmid': pmid, 'title': title.strip(),
                    'abstract': abstract.strip()[:600],
                    'doi': doi.strip(), 'journal': journal.strip(),
                    'year': year.strip(), 'pub_types': pub_types,
                })
            except: continue
    except Exception as e:
        print(f"  Error {xml_path.name}: {e}")
    return articles

# ── 提取 ──
all_articles = []
for i, xml_path in enumerate(sorted(BASE.glob('batch_*.xml'))):
    all_articles.extend(extract_pubmed_articles(xml_path))
    if (i+1) % 8 == 0:
        print(f"  {i+1}/40 batches, {len(all_articles)} articles")

print(f"\nTotal: {len(all_articles)} articles")

# ── 筛选 + 评分 ──
def score_article(a):
    text = (a['title'] + ' ' + a['abstract']).lower()
    title = a['title'].lower()
    
    # 排除 review 类
    for ex in EXCLUDE_TYPES:
        if ex in ' '.join(a['pub_types']) or ex in title:
            return -1, 'excluded'
    
    # 必须有 new virus 关键词
    matched_kw = None
    for kw in NEW_VIRUS_KW:
        if kw in text:
            matched_kw = kw
            break
    if not matched_kw:
        return -1, 'no_match'
    
    # 症状照片可能性评分
    photo_score = 0
    for sig in PHOTO_SIGNALS:
        if sig in text:
            photo_score += 1
    
    # 标题中直接提到症状/寄主/field → 加分
    if any(w in title for w in ['infecting', 'infects', 'isolated from', 'detected in']):
        photo_score += 3
    if any(w in title for w in ['symptom', 'mosaic', 'necrosis', 'leaf curl', 'yellow']):
        photo_score += 5
    if any(w in title for w in ['field', 'survey', 'outbreak']):
        photo_score += 3
    
    # 新病毒名直接出现在标题中 → 高可能
    if 'novel virus' in title or 'new virus' in title:
        if 'infecting' in title or any(h in title for h in ['tomato','potato','cucumber','pepper','wheat','rice','maize','soybean','citrus','grape','apple','banana']):
            photo_score += 5
    
    likelihood = 'HIGH' if photo_score >= 8 else 'MED' if photo_score >= 4 else 'LOW'
    return photo_score, likelihood

candidates = []
for a in all_articles:
    score, flag = score_article(a)
    if score >= 0:
        a['photo_score'] = score
        a['likelihood'] = flag
        candidates.append(a)

candidates.sort(key=lambda x: -x['photo_score'])
print(f"Candidates: {len(candidates)}")

# ── PDF匹配 ──
pdf_index = {}
for root, dirs, files in os.walk(BASE):
    for f in files:
        if f.endswith('.pdf'):
            name = f.replace('.pdf', '')
            m = re.search(r'(10\.\d{4,}/[^\s]+)', name)
            if m: pdf_index[m.group(1)] = os.path.join(root, f)
            pdf_index[f] = os.path.join(root, f)

for a in candidates:
    doi = a['doi']
    if doi and doi in pdf_index:
        a['has_pdf'] = True
    elif doi:
        found = False
        for key in pdf_index:
            if doi.replace('/', '_') in key or doi.split('/')[-1] in key:
                a['has_pdf'] = True; found = True; break
        if not found: a['has_pdf'] = False
    else:
        a['has_pdf'] = False

# ── 输出 ──
with open(OUT, 'w', encoding='utf-8') as f:
    f.write("PMID\tYear\tPhotoLikely\tDOI\tJournal\tTitle\tFirst100_Abstract\tHasPDF\n")
    for a in candidates:
        f.write('\t'.join([
            a['pmid'], a['year'], a['likelihood'],
            a['doi'], a['journal'],
            a['title'][:300],
            a['abstract'][:100].replace('\t', ' '),
            'YES' if a['has_pdf'] else 'NO'
        ]) + '\n')

# ── 统计 ──
high = sum(1 for a in candidates if a['likelihood'] == 'HIGH' and a['has_pdf'])
med = sum(1 for a in candidates if a['likelihood'] == 'MED' and a['has_pdf'])
low = sum(1 for a in candidates if a['likelihood'] == 'LOW' and a['has_pdf'])
print(f"\n有PDF: HIGH={high} MED={med} LOW={low}")

print(f"\n=== HIGH likelihood with PDF (前20) ===")
for a in candidates:
    if a['likelihood'] == 'HIGH' and a['has_pdf']:
        print(f"  [{a['year']}] {a['title'][:110]}")
        high -= 1
        if high <= 0: break

print(f"\n输出: {OUT}")
