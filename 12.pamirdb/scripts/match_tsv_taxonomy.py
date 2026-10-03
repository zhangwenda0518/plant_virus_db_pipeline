#!/usr/bin/env python3
"""Match viruses.json to Plant_Virus.complete_ref_info.tsv for taxonomy."""
import re, json, sqlite3

TSV = '/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus.complete_ref_info.tsv'
VJSON = '/opt/pamirdb/data/virus_genomes/viruses.json'
DB = '/opt/pamirdb/data/pamirdb.sqlite'


def load_tsv():
    tax = {}
    with open(TSV, encoding='utf-8') as f:
        hdr = f.readline().rstrip('\n\r').split('\t')
        cols = {n: i for i, n in enumerate(hdr)}
        for line in f:
            row = line.rstrip('\n\r').split('\t')
            if len(row) < len(hdr):
                continue
            acc = (row[0] or '').split('.')[0]
            title = (row[cols.get('GenBank_Title', '')] or '').strip().lower()
            vnames = (row[cols.get('Virus name(s)', '')] or '').strip().lower()
            sp_ncbi = (row[cols.get('Species_NCBI', '')] or '').strip()
            sp_ictv = (row[cols.get('Species_ICTV', '')] or '').strip()
            family = (row[cols.get('VMR_Family', '')] or '').strip().lower()
            genus = (row[cols.get('VMR_Genus', '')] or '').strip()
            if not family and not genus:
                continue
            tax[acc] = {
                'title': title, 'vnames': vnames,
                'family': family, 'genus': genus,
                'sp_ncbi': sp_ncbi, 'sp_ictv': sp_ictv,
            }
    return tax


def clean_name(n):
    n = (n or '').lower().strip()
    n = re.sub(r'^(tpa:?\s*|tpa_asm:?\s*)', '', n)
    n = n.replace('"', '').replace(';', '')
    return n.strip()


def match_virus(vname, vacc, tax_map, title_idx):
    cname = clean_name(vname)

    # 1. By accession
    if vacc:
        akey = vacc.split('.')[0]
        if akey in tax_map and tax_map[akey]['family']:
            return tax_map[akey]

    # 2. By GenBank title exact match
    if cname in title_idx:
        return title_idx[cname]

    # 3. Remove suffixes and try again
    for suffix in [
        ', complete genome', ', complete sequence',
        ' genome assembly, complete genome: monopartite',
        ' dna, complete genome', ' dna, complete sequence',
    ]:
        shorter = cname.replace(suffix, '').strip()
        if shorter in title_idx:
            return title_idx[shorter]

    # 4. Strip isolate/strain/clone/segment info
    for pat in [
        r'\s+isolate\s+\S+.*', r'\s+strain\s+\S+.*', r'\s+clone\s+\S+.*',
        r'\s+segment\s+\S+.*', r'\s+dna-a.*', r'\s+dna-b.*', r'\s+rna\s*\d.*',
    ]:
        shorter = re.sub(pat, '', cname).strip()
        if shorter in title_idx:
            return title_idx[shorter]

    # 5. By first 3 words
    words = cname.split()
    if len(words) >= 3:
        prefix3 = ' '.join(words[:3])
        for title, info in title_idx.items():
            if title.startswith(prefix3) or prefix3 in title:
                return info

    # 6. By first 2 words
    if len(words) >= 2:
        prefix2 = ' '.join(words[:2])
        for title, info in title_idx.items():
            if title.startswith(prefix2):
                return info

    # 7. By alternate virus names
    for acc, info in tax_map.items():
        vn = info['vnames']
        if vn and (vn in cname or cname in vn):
            return info

    return None


def main():
    print('Loading TSV...')
    tax_map = load_tsv()
    print('Entries: %d' % len(tax_map))

    # Build title index for fast lookup
    title_idx = {v['title']: v for v in tax_map.values() if v['title']}
    print('Unique titles: %d' % len(title_idx))

    print('Loading viruses.json...')
    with open(VJSON) as f:
        viruses = json.load(f)
    print('Viruses: %d' % len(viruses))

    up_fam = up_gen = up_sp = no_match = 0
    for vid, vdata in viruses.items():
        old_fam = vdata.get('family', '')
        need_fam = (not old_fam or old_fam == 'other_plant_virus')
        old_gen = vdata.get('genus', '')
        need_gen = (not old_gen or old_gen == '?')
        if not need_fam and not need_gen:
            continue

        info = match_virus(
            vdata.get('name', ''), vdata.get('accession', ''),
            tax_map, title_idx
        )
        if info:
            if need_fam and info['family']:
                vdata['family'] = info['family']
                up_fam += 1
            if need_gen and info['genus']:
                vdata['genus'] = info['genus']
                up_gen += 1
            sp = info['sp_ictv'] or info['sp_ncbi']
            if sp:
                vdata['species'] = sp
                up_sp += 1
        else:
            no_match += 1

    print('Family: %d  Genus: %d  Species: %d  Unmatched: %d' % (
        up_fam, up_gen, up_sp, no_match))

    with open(VJSON, 'w') as f:
        json.dump(viruses, f)

    print('Updating DB...')
    db = sqlite3.connect(DB)
    try:
        db.execute('ALTER TABLE viruses ADD COLUMN genus TEXT DEFAULT ""')
    except Exception:
        pass
    try:
        db.execute('ALTER TABLE viruses ADD COLUMN species TEXT DEFAULT ""')
    except Exception:
        pass

    for vid, vdata in viruses.items():
        updates = []
        params = []
        for col, val in [
            ('family', vdata.get('family', '')),
            ('genus', vdata.get('genus', '')),
            ('species', vdata.get('species', '')),
        ]:
            if val and val not in ('other_plant_virus', '?'):
                updates.append(col + '=?')
                params.append(val)
        if updates:
            params.append(vid)
            db.execute(
                'UPDATE viruses SET ' + ', '.join(updates) + ' WHERE virus_id=?',
                params
            )
    db.commit()

    print('\nFamily distribution:')
    fams = db.execute(
        'SELECT family, COUNT(*) FROM viruses GROUP BY family ORDER BY COUNT(*) DESC'
    ).fetchall()
    for r in fams:
        print('  %s: %d' % (r[0], r[1]))

    print('\nGenus (top 30):')
    for r in db.execute(
        'SELECT genus, COUNT(*) FROM viruses WHERE genus!="" '
        'GROUP BY genus ORDER BY COUNT(*) DESC LIMIT 30'
    ).fetchall():
        print('  %s: %d' % (r[0], r[1]))

    still = db.execute(
        'SELECT COUNT(*) FROM viruses '
        'WHERE family="other_plant_virus" OR family="" OR family IS NULL'
    ).fetchone()[0]
    print('\nStill other_plant_virus: %d / %d' % (still, len(viruses)))


if __name__ == '__main__':
    main()
