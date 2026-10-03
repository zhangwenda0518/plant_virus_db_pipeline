"""Full-text RAG indexer — self-contained, zero external deps.
Usage: python build_rag.py
"""
import json, os, time, pymupdf
import os
from urllib.request import urlopen, Request
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# ═══ Config ═══
EMBED_API = 'https://api.siliconflow.cn/v1/embeddings'
EMBED_KEY = os.environ.get('SILICONFLOW_API_KEY', '')  # 明文 key 已移除 (2026-10-03)
EMBED_MODEL = 'Qwen/Qwen3-Embedding-8B'
EMBED_DIM = 4096
BATCH_SIZE = 500
CHUNK_SIZE = 1600
OVERLAP = 200

BASE = os.path.dirname(os.path.abspath(__file__))
PDF_DIRS = [os.path.join(BASE, d) for d in [
    'pubmed_records/scihub_pdfs', 'pubmed_records/semantic_pdfs',
    'pubmed_records/multi_pdfs', 'pubmed_records/browser_pdfs',
    'pubmed_records/vpn_pdfs', 'pubmed_records/scihub_v2',
    'pubmed_records/pmc_fulltext',
]]
OA_JSON_DIR = os.path.join(BASE, 'pubmed_records/pv_texts')
PAPERS_JSON = os.path.join(BASE, 'data/papers.json')
QDRANT_PATH = os.path.join(BASE, 'rag_qdrant')


def embed_texts(texts: list) -> list:
    """Embed via SiliconFlow API."""
    payload = json.dumps({'model': EMBED_MODEL, 'input': texts}).encode()
    req = Request(EMBED_API, data=payload, headers={
        'Authorization': f'Bearer {EMBED_KEY}', 'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
            return [d['embedding'] for d in result['data']]
        except Exception as e:
            if attempt < 2: time.sleep(2)
    return []


def extract_text_pdf(filepath):
    try:
        doc = pymupdf.open(filepath)
        text = ' '.join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except:
        return ''


def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        start += CHUNK_SIZE - OVERLAP
    return chunks


# ── Load metadata ──
with open(PAPERS_JSON, encoding='utf-8') as f:
    papers = json.load(f)['papers']
paper_by_doi = {}
for p in papers:
    doi = (p.get('doi') or '').lower()
    if doi:
        paper_by_doi[doi.replace('/', '_')] = p

# ── Init Qdrant ──
client = QdrantClient(path=QDRANT_PATH)
if 'pv_fulltext' not in [c.name for c in client.get_collections().collections]:
    client.create_collection(collection_name='pv_fulltext',
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE))
    print('Collection created')
else:
    print('Collection exists')

# ── Gather texts ──
all_texts = []
for pdf_dir in PDF_DIRS:
    if not os.path.exists(pdf_dir): continue
    for fname in os.listdir(pdf_dir):
        if fname.endswith('.txt'):
            text = open(os.path.join(pdf_dir, fname), encoding='utf-8').read()
        elif fname.endswith('.pdf'):
            text = extract_text_pdf(os.path.join(pdf_dir, fname))
        else:
            continue
        if len(text) < 200: continue
        doi_key = fname.replace('.pdf', '')
        meta = paper_by_doi.get(doi_key, {})
        all_texts.append({'text': text, 'doi': doi_key, 'pmid': meta.get('pmid',''),
            'title': meta.get('title',''), 'year': meta.get('year',0),
            'virus': meta.get('virus_name',''), 'source': 'pdf'})

if os.path.exists(OA_JSON_DIR):
    for fname in os.listdir(OA_JSON_DIR):
        if not fname.endswith('.json'): continue
        try:
            d = json.load(open(os.path.join(OA_JSON_DIR, fname), encoding='utf-8'))
            text = d.get('text', '')
            if len(text) < 200: continue
            all_texts.append({'text': text, 'doi': d.get('doi',''),
                'pmid': str(d.get('doc_id',fname)), 'title': d.get('title',''),
                'year': d.get('year',0), 'virus': '', 'source': 'oa_json'})
        except: pass

print(f'Documents: {len(all_texts)}')

# ── Chunk ──
all_chunks = []
for doc in all_texts:
    for ci, chunk in enumerate(chunk_text(doc['text'])):
        all_chunks.append((chunk, {'chunk_index': ci, 'doi': doc['doi'],
            'pmid': doc['pmid'], 'title': doc['title'][:200],
            'year': doc['year'], 'virus': doc['virus'][:100], 'source': doc['source']}))
print(f'Chunks: {len(all_chunks)}')

# ── Embed + Index ──
total = 0
for i in range(0, len(all_chunks), BATCH_SIZE):
    batch = all_chunks[i:i+BATCH_SIZE]
    texts, metas = [c[0] for c in batch], [c[1] for c in batch]
    vecs = embed_texts(texts)
    if not vecs: continue
    points = [PointStruct(id=i+j, vector=vecs[j],
        payload={'text': texts[j][:2000], **metas[j]}) for j in range(len(batch))]
    client.upsert(collection_name='pv_fulltext', points=points)
    total += len(points)
    print(f'  {total}/{len(all_chunks)} ({total/len(all_chunks)*100:.0f}%)')

print(f'\nDone: {len(all_texts)} docs -> {total} chunks')

# ── Test ──
v = embed_texts(['plant virus resistance mechanism'])
if v:
    hits = client.search(collection_name='pv_fulltext', query_vector=v[0], limit=3)
    print('\nSearch: "plant virus resistance mechanism"')
    for h in hits:
        print(f'  {h.payload.get("title","")[:80]}')
