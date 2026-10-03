#!/usr/bin/env python3
"""Parse ALL GenBank .gb files from 3 directories to extract family/genus/species taxonomy."""
import re, os, json, sqlite3
from collections import defaultdict

VIRUS_JSON = "/opt/pamirdb/data/virus_genomes/viruses.json"
DB_PATH = "/opt/pamirdb/data/pamirdb.sqlite"

FAMILY_PAT = re.compile(r'(\w+viridae)', re.IGNORECASE)
GENUS_PAT = re.compile(r'(\w+virus)\b', re.IGNORECASE)


def find_all_gb_files():
    """Find all .gb files across all directories."""
    dirs = [
        "/opt/plant_virus_db/plant_virus_db_pipeline/13.virus_profile/genbank_records",
        "/opt/plant_virus_db/plant_virus_db_pipeline/7.literature_tracker/genbank_records",
        "/opt/plant_virus_db/plant_virus_db_pipeline/genome_annotations",
    ]
    files = set()
    for d in dirs:
        if not os.path.exists(d):
            continue
        for root, dirs2, fnames in os.walk(d):
            for fn in fnames:
                if fn.endswith('.gb'):
                    files.add(os.path.join(root, fn))
    return sorted(files)


def parse_genbank(filepath):
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            content = f.read(50000)
    except Exception:
        return None, None, None, None
    org_m = re.search(r'/organism="([^"]+)"', content)
    if not org_m:
        return None, None, None, None
    org = org_m.group(1).strip()
    org_sec = re.search(r'ORGANISM\s+(.+?)\n((?:\s{9,}.+\n?)+)', content)
    lineage = ''
    if org_sec:
        lineage = ' '.join(org_sec.group(2).split())
    families = FAMILY_PAT.findall(lineage)
    family = families[-1].lower() if families else ''
    genera = GENUS_PAT.findall(lineage)
    genus = ''
    for g in genera:
        g_clean = g.strip(';. ')
        if len(g_clean) > 6:
            genus = g_clean[0].upper() + g_clean[1:].lower()
            break
    species = ''
    parts = lineage.split(';')
    if parts:
        last = parts[-1].strip().rstrip('.')
        if ' ' in last and not last.lower().startswith('unclassified'):
            species = last
    return org, family, genus, species


def clean_name(name):
    n = name.lower().strip()
    n = re.sub(r'^(tpa:?\s*|tpa_asm:?\s*)', '', n)
    n = n.replace('"', '').replace(';', '')
    return n.strip()


def fuzzy_match(vname, tax_map, word_idx):
    """Try progressively fuzzier matching."""
    if vname in tax_map:
        return tax_map[vname]

    # Remove common suffixes
    suffixes = [
        ', complete genome', ', complete sequence',
        ' genome assembly, complete genome: monopartite',
        ' dna, complete genome', ' dna, complete sequence', ', complete cds',
        ', complete genome, complete sequence',
    ]
    for suffix in suffixes:
        shorter = vname.replace(suffix, '').strip()
        if shorter in tax_map:
            return tax_map[shorter]

    # Remove isolate/strain/clone info
    strip_pats = [
        r'\s+isolate\s+\S+.*', r'\s+strain\s+\S+.*', r'\s+clone\s+\S+.*',
        r'\s+segment\s+\S+.*', r'\s+dna-a.*', r'\s+dna-b.*', r'\s+rna\s*\d.*',
        r'\s+genome\s+assembly.*', r'\s+chromosome.*', r'\s+gene\s+.*',
        r',\s*complete\s+genome.*', r',\s*complete\s+sequence.*',
    ]
    for pat in strip_pats:
        shorter = re.sub(pat, '', vname).strip()
        if shorter in tax_map:
            return tax_map[shorter]

    # Word pair lookup
    words = vname.split()
    if len(words) >= 2:
        for j in range(len(words) - 1):
            candidates = word_idx.get((words[j], words[j + 1]), [])
            for c in candidates:
                cwords = set(c.split())
                vwords = set(words)
                common = cwords & vwords
                if len(common) >= min(3, len(cwords) * 0.6):
                    return tax_map[c]

    # Substring match (first 3 words)
    short = ' '.join(words[:3])
    if len(short) > 10:
        for org_key, info in tax_map.items():
            if short in org_key or org_key in short:
                return info

    return None


def main():
    print('Phase 1: Scanning all GB files...')
    all_files = find_all_gb_files()
    print('Total .gb files: %d' % len(all_files))

    tax_map = {}
    dup_count = 0
    for i, fpath in enumerate(all_files):
        org, family, genus, species = parse_genbank(fpath)
        if org and family:
            key = org.lower()
            if key not in tax_map:
                tax_map[key] = (family, genus, species)
            else:
                dup_count += 1
        if (i + 1) % 5000 == 0:
            print('  [%d/%d] %d unique species' % (i + 1, len(all_files), len(tax_map)))
    print('Unique species: %d (duplicates: %d)' % (len(tax_map), dup_count))

    # Build word-pair index
    word_idx = defaultdict(list)
    for org_key in tax_map:
        words = org_key.split()
        if len(words) >= 2:
            for j in range(len(words) - 1):
                word_idx[(words[j], words[j + 1])].append(org_key)

    print('\nPhase 2: Matching viruses.json by name...')
    with open(VIRUS_JSON) as f:
        viruses = json.load(f)

    up_fam = up_gen = up_sp = no_match = 0

    for vid, vdata in viruses.items():
        name = (vdata.get('name', '') or '').strip()
        if not name:
            continue

        old_fam = vdata.get('family', '')
        old_gen = vdata.get('genus', '')

        # Only process those needing taxonomy
        need_fam = (not old_fam or old_fam == 'other_plant_virus')
        need_gen = (not old_gen or old_gen == '?')
        if not need_fam and not need_gen:
            continue

        cname = clean_name(name)
        info = fuzzy_match(cname, tax_map, word_idx)

        if info:
            family, genus, species = info
            if need_fam and family:
                vdata['family'] = family
                up_fam += 1
            if need_gen and genus:
                vdata['genus'] = genus
                up_gen += 1
            if species:
                vdata['species'] = species
                up_sp += 1
        else:
            no_match += 1

    print('Family updated: %d, Genus: %d, Species: %d, No match: %d' % (
        up_fam, up_gen, up_sp, no_match))

    with open(VIRUS_JSON, 'w') as f:
        json.dump(viruses, f)

    print('\nUpdating database...')
    db = sqlite3.connect(DB_PATH)
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
        fam = vdata.get('family', '')
        gen = vdata.get('genus', '')
        sp = vdata.get('species', '')
        if fam and fam != 'other_plant_virus':
            updates.append('family=?')
            params.append(fam)
        if gen and gen != '?':
            updates.append('genus=?')
            params.append(gen)
        if sp:
            updates.append('species=?')
            params.append(sp)
        if updates:
            params.append(vid)
            db.execute('UPDATE viruses SET ' + ', '.join(updates) + ' WHERE virus_id=?', params)
    db.commit()

    print('\nFinal family distribution:')
    for r in db.execute(
        'SELECT family, COUNT(*) FROM viruses GROUP BY family ORDER BY COUNT(*) DESC'
    ).fetchall():
        print('  %s: %d' % (r[0], r[1]))

    print('\nGenus distribution (top 30):')
    for r in db.execute(
        'SELECT genus, COUNT(*) FROM viruses WHERE genus!="" GROUP BY genus ORDER BY COUNT(*) DESC LIMIT 30'
    ).fetchall():
        print('  %s: %d' % (r[0], r[1]))

    still = db.execute(
        'SELECT COUNT(*) FROM viruses WHERE family="other_plant_virus" OR family="" OR family IS NULL'
    ).fetchone()[0]
    print('\nStill other_plant_virus: %d / %d' % (still, len(viruses)))


if __name__ == '__main__':
    main()
