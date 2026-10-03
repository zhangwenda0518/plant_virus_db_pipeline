"""Download PMC full-text from already-downloaded PubMed XML."""
import json, os, time, urllib.request, xml.etree.ElementTree as ET, glob, pathlib

MOD_DIR = pathlib.Path(__file__).resolve().parent
OUT_DIR = MOD_DIR / "pubmed_records/pmc_fulltext"
os.makedirs(OUT_DIR, exist_ok=True)
API_KEY = os.environ.get('NCBI_API_KEY', '')

print('Step 1: Extract PMCID from PubMed XML...')
# Load PMID -> PMCID from downloaded XML
pmid_to_pmcid = {}
xml_dir = MOD_DIR / 'pubmed_records'
for fpath in sorted(glob.glob(str(xml_dir / 'batch_*.xml'))):
    try:
        tree = ET.parse(fpath)
        for art in tree.findall('.//PubmedArticle'):
            pmid = art.findtext('.//PMID', '')
            for aid in art.findall('.//ArticleId'):
                if aid.get('IdType') == 'pmc':
                    pmcid = (aid.text or '').replace('PMC', '')
                    if pmid and pmcid:
                        pmid_to_pmcid[pmid] = pmcid
                    break
    except: pass
print(f'  Found {len(pmid_to_pmcid)} PMID->PMCID mappings')

# Find remaining papers
data = json.load(open(MOD_DIR / 'data/papers.json', 'r', encoding='utf-8'))
papers = [p for p in data['papers'] if p.get('virus_name') and p.get('virus_name') != '未提及']
all_files = set()
for d in ['scihub_pdfs','semantic_pdfs','multi_pdfs','browser_pdfs','vpn_pdfs','scihub_v2','pv_texts','europepmc_pdfs','pmc_fulltext']:
    p = MOD_DIR / f'pubmed_records/{d}'
    if os.path.exists(p):
        for f in os.listdir(p): all_files.add(f.rsplit('.', 1)[0])

# Get PMCIDs for remaining papers
remaining_pmc = []
for p in papers:
    doi_key = p['doi'].replace('/', '_')
    if doi_key not in all_files and p['pmid'] in pmid_to_pmcid:
        remaining_pmc.append((p['pmid'], pmid_to_pmcid[p['pmid']]))

print(f'Remaining with PMC: {len(remaining_pmc)}')

# Phase 2: Download full-text via efetch (200 PMCIDs per batch)
ok = 0
for i in range(0, len(remaining_pmc), 50):
    batch = remaining_pmc[i:i+50]
    pmcids = [pc for _, pc in batch]
    try:
        url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={",".join(pmcids)}&rettype=xml&retmode=xml&api_key={API_KEY}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            xml_content = resp.read().decode('utf-8', errors='replace')
        
        tree = ET.fromstring(xml_content)
        for article in tree.findall('.//article'):
            pmcid_el = None
            for aid in article.findall('.//article-id'):
                if aid.get('pub-id-type') in ('pmcid', 'pmc'):
                    pmcid_el = aid
                    break
            if pmcid_el is None: continue
            pmcid = pmcid_el.text
            body = article.find('.//body')
            if body is None: continue
            text = ' '.join(body.itertext())
            if len(text) > 200:
                fpath = os.path.join(OUT_DIR, f'PMC{pmcid}.txt')
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(text)
                ok += 1
    except Exception as e:
        pass
    
    if ok % 100 == 0 and ok > 0:
        print(f'  [{ok}] {i}/{len(remaining_pmc)}')
    time.sleep(0.3)

print(f'\nDone: {ok} full texts')
