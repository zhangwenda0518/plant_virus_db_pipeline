"""
Re-download sRNA gene summaries from NCBI with correct XML parsing.
Fixes: column shift, species extraction, tab-escaping.
"""
from Bio import Entrez
from xml.etree import ElementTree as ET
import os, time
Entrez.email = os.environ.get('NCBI_EMAIL', '')
if not Entrez.email:
    raise SystemExit('ERROR: NCBI_EMAIL environment variable not set '
                     '(NCBI Entrez policy requires a valid contact email).')

OUTDIR = os.path.dirname(__file__) + "/data"

queries = {
    'DCL':  '(Viridiplantae[Organism]) AND (DCL1 OR DCL2 OR DCL3 OR DCL4 OR "Dicer-like") AND alive[Status]',
    'RDR':  '(Viridiplantae[Organism]) AND (RDR1 OR RDR2 OR RDR6 OR "RNA-dependent RNA polymerase") AND alive[Status]',
    'AGO':  '(Viridiplantae[Organism]) AND (AGO1 OR AGO4 OR AGO7 OR AGO10 OR "Argonaute") AND alive[Status]',
    'DRB':  '(Viridiplantae[Organism]) AND (DRB1 OR DRB2 OR DRB4 OR "double-stranded RNA-binding" OR HYL1) AND alive[Status]',
    'SGS3': '(Viridiplantae[Organism]) AND (SGS3 OR "SUPPRESSION OF SILENCING 3") AND alive[Status]',
    'HEN1': '(Viridiplantae[Organism]) AND (HEN1 OR "HUA ENHANCER 1" OR "small RNA methyltransferase") AND alive[Status]',
}

HEADER = 'GeneID\tSymbol\tFullName\tSpecies\tFamily\tChromosome\tOtherAliases\tOtherDesignations'

def clean(s):
    """Remove newlines only, preserve tabs."""
    return (s or '').replace('\n', ' ').replace('\r', ' ')

def search_all_ids(query, max_records=5000):
    """Search NCBI and return (ids, count). Pages via history when Count > retmax
    (same pattern as fetch_ncbi.py: search_and_fetch)."""
    handle = Entrez.esearch(db='gene', term=query, retmax=max_records, usehistory='y')
    results = Entrez.read(handle)
    handle.close()
    count = int(results['Count'])
    id_list = results['IdList']
    if count > len(id_list):
        print(f'  Count={count} > returned {len(id_list)}; paging via history...')
        webenv = results['WebEnv']
        query_key = results['QueryKey']
        all_ids = []
        batch = 10000
        for start in range(0, count, batch):
            handle = Entrez.esearch(db='gene', term=query, retmax=batch,
                                    retstart=start, usehistory='y',
                                    webenv=webenv, query_key=query_key)
            sub = Entrez.read(handle)
            handle.close()
            all_ids.extend(sub['IdList'])
            print(f'    fetched {len(all_ids)}/{count} IDs', end='\r')
        print()
        return all_ids, count
    return id_list, count

for fam, query in queries.items():
    # Search (full Count check, no silent 5000 cap)
    ids, count = search_all_ids(query)
    print(f'{fam}: Count={count}, got {len(ids)} IDs, downloading summaries...')

    fpath = os.path.join(OUTDIR, f'sRNA_{fam}_genes.tsv')
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(HEADER + '\n')

        for i in range(0, len(ids), 200):
            batch = ids[i:i+200]
            try:
                handle = Entrez.esummary(db='gene', id=','.join(batch), retmode='xml')
                xml_raw = handle.read()
                handle.close()

                root = ET.fromstring(xml_raw)
                for ds in root.findall('.//DocumentSummary'):
                    uid = ds.get('uid', '')
                    name = clean(ds.findtext('Name'))
                    desc = clean(ds.findtext('Description'))
                    org_el = ds.find('Organism')
                    org = clean(org_el.findtext('ScientificName')) if org_el is not None else ''
                    chrom = clean(ds.findtext('Chromosome'))
                    aliases = clean(ds.findtext('OtherAliases'))
                    other = clean(ds.findtext('OtherDesignations'))

                    # Build tab-separated row
                    row = '\t'.join([uid, name, desc, org, fam, chrom, aliases, other])
                    f.write(row + '\n')
                f.flush()
                print(f'  {min(i+200, len(ids))}/{len(ids)}', end='\r')
                time.sleep(0.35)
            except Exception as e:
                print(f'\n  Error at batch {i}: {e}')
                time.sleep(5)
    print(f'  Saved {len(ids)} {fam} genes')

    # Verify
    species = set()
    with open(fpath, encoding='utf-8') as f:
        next(f)
        for line in f:
            cols = line.strip().split('\t')
            if len(cols) >= 4 and cols[3]:
                species.add(cols[3])
    print(f'  Unique species: {len(species)}')
    time.sleep(0.5)

print('\nAll done!')
