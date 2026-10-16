"""
Parse GenBank flat files to extract CDS/gene annotations for all viruses.
Matches to viruses_full.json by accession.

Output: data/virus_gene_annotations.json
  {accession_key: [{gene, product, start, end}, ...]}
"""

import json, re, os, time
import urllib.request
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
REPO_DIR = Path(__file__).resolve().parents[2]


def resolve_gb_dir(cli_value=None):
    """Locate the GenBank records dir: --gb-dir > $PAMIRDB_GB_DIR > known candidates."""
    candidates = []
    if cli_value:
        candidates.append(Path(cli_value))
    env = os.environ.get("PAMIRDB_GB_DIR")
    if env:
        candidates.append(Path(env))
    candidates += [
        REPO_DIR / "12.pamirdb" / "genbank_records",
        REPO_DIR / "data" / "genbank_records",
        Path("/opt/plant_virus_db/plant_virus_db_pipeline/13.virus_profile/genbank_records"),
        Path("/opt/plant_virus_db/plant_virus_db_pipeline/8.virus_profile/genbank_records"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    raise SystemExit(
        "ERROR: 未找到 GenBank 记录目录（原始 .gb 数据已随 8.virus_profile 删除）。\n"
        "  重新下载后用 --gb-dir <目录> 或环境变量 PAMIRDB_GB_DIR 指定。\n"
        "  已尝试:\n" + "\n".join(f"    - {c}" for c in candidates)
    )


GB_DIR = None  # resolved in __main__

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def load_virus_accessions():
    """Load viruses_full.json → ({acc_versionless: vid}, viruses)."""
    virus_path = DATA_DIR / "virus_genomes" / "viruses_full.json"
    with open(virus_path) as f:
        viruses = json.load(f)
    acc_map = {}
    for vid, vmeta in viruses.items():
        acc = (vmeta.get('accession') or '').split('.')[0].strip()
        if acc:
            acc_map[acc] = vid
    return acc_map, viruses


def covered_accessions(gb_dir):
    """Accessions already present as .gb records (read from file headers)."""
    covered = set()
    for fn in os.listdir(gb_dir):
        if not fn.endswith('.gb'):
            continue
        try:
            with open(os.path.join(gb_dir, fn), encoding='utf-8', errors='replace') as f:
                head = f.read(4000)
            m = re.search(r'ACCESSION\s+(\S+)', head)
            if m:
                covered.add(m.group(1).split('.')[0])
        except OSError:
            pass
    return covered


def _http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'PAmiRDB-annotation-rebuild/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


def fetch_missing_records(missing, gb_dir, batch_size=80, limit=None):
    """Download missing GenBank records from NCBI efetch into gb_dir as <acc>.gb.

    NCBI 限速：无 API key 3 req/s（sleep 0.35s），有 NCBI_API_KEY 10 req/s。
    批量拉取失败时逐条重试。
    """
    api_key = os.environ.get('NCBI_API_KEY', '')
    key_arg = f"&api_key={api_key}" if api_key else ''
    sleep = 0.12 if api_key else 0.35
    to_fetch = sorted(missing)
    if limit:
        to_fetch = to_fetch[:limit]
    print(f"  Fetching {len(to_fetch)} missing GenBank records from NCBI ...")
    ok = fail = 0
    for i in range(0, len(to_fetch), batch_size):
        batch = to_fetch[i:i + batch_size]
        text = ''
        try:
            url = f"{EUTILS_BASE}/efetch.fcgi?db=nucleotide&id={','.join(batch)}&rettype=gb&retmode=text{key_arg}"
            text = _http_get(url)
        except Exception as e:
            print(f"    batch {i // batch_size + 1}: efetch failed ({e}); per-accession fallback")
        chunks = [c for c in re.split(r'(?m)^//\s*$', text) if c.strip()] if text else []
        got = set()
        for chunk in chunks:
            m = re.search(r'ACCESSION\s+(\S+)', chunk)
            if not m:
                continue
            acc = m.group(1).split('.')[0]
            with open(os.path.join(gb_dir, acc + '.gb'), 'w', encoding='utf-8') as f:
                f.write(chunk.strip() + '\n//\n')
            got.add(acc)
        for acc in batch:
            if acc in got:
                ok += 1
                continue
            try:
                url = f"{EUTILS_BASE}/efetch.fcgi?db=nucleotide&id={acc}&rettype=gb&retmode=text{key_arg}"
                rec = _http_get(url)
                if 'ACCESSION' in rec:
                    with open(os.path.join(gb_dir, acc + '.gb'), 'w', encoding='utf-8') as f:
                        f.write(rec)
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
            time.sleep(sleep)
        time.sleep(sleep)
        if (i // batch_size + 1) % 10 == 0:
            print(f"    [{min(i + batch_size, len(to_fetch))}/{len(to_fetch)}] ok={ok} fail={fail}")
    print(f"  Downloaded: {ok}, failed: {fail}")
    return ok, fail


def parse_genbank_file(filepath):
    """Parse one GenBank flat file, return (accession, genes_list)."""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return None, []

    # Extract accession
    acc_match = re.search(r'ACCESSION\s+(\S+)', content)
    if not acc_match:
        return None, []
    acc = acc_match.group(1).split('.')[0]  # strip version

    # Extract features section
    features_match = re.search(r'FEATURES\s+Location/Qualifiers(.*?)ORIGIN', content, re.DOTALL)
    if not features_match:
        return acc, []
    features_text = features_match.group(1)

    # Feature type classification
    CODING_TYPES = {'CDS', 'gene'}
    NCR_TYPES = {
        'regulatory', 'stem_loop', 'misc_RNA', 'rep_origin', 'polyA_site',
        'TATA_signal', 'promoter', 'enhancer', 'terminator', 'RBS',
        '5\'UTR', '3\'UTR', 'mRNA', 'exon', 'intron', 'repeat_region',
        'misc_feature', 'misc_difference', 'variation', 'primer_bind',
    }
    ALL_FEAT_TYPES = CODING_TYPES | NCR_TYPES | {'source', 'mat_peptide'}

    # Parse all features
    features = []
    feat_pattern = re.compile(
        r'(?:^|\n)\s{5}(' + '|'.join(ALL_FEAT_TYPES) + r')\s+(\S.*?)\n'
        r'(.*?)(?=\n\s{5}[a-z].*\s+\S|\n\s{5}ORIGIN|\Z)',
        re.DOTALL
    )

    for match in feat_pattern.finditer(features_text):
        feat_type = match.group(1)
        location = match.group(2).strip()
        qualifiers = match.group(3)

        # Parse location
        loc_clean = location.replace('join(', '').replace(')', '').replace('complement(', '')
        loc_simple = re.match(r'<?(\d+)\.\.>?(\d+)', loc_clean)
        if not loc_simple:
            continue
        start = int(loc_simple.group(1))
        end = int(loc_simple.group(2))

        # Extract qualifiers
        prod_match = re.search(r'/product="([^"]+)"', qualifiers)
        product = prod_match.group(1) if prod_match else feat_type

        gene_match = re.search(r'/gene="([^"]+)"', qualifiers)
        if not gene_match:
            gene_match = re.search(r'/locus_tag="([^"]+)"', qualifiers)
        gene = gene_match.group(1) if gene_match else feat_type

        # Extract /note for non-coding features (often contains functional info)
        note_match = re.search(r'/note="([^"]+)"', qualifiers)
        note = note_match.group(1) if note_match else ''

        # Determine category
        if feat_type in CODING_TYPES:
            category = 'CDS'
        elif feat_type in NCR_TYPES:
            category = 'NCR'
        elif feat_type == 'mat_peptide':
            category = 'CDS'  # mature peptide is coding
        else:
            category = 'OTHER'

        features.append({
            "gene": gene,
            "product": product,
            "start": start,
            "end": end,
            "type": feat_type,
            "category": category,
            "note": note,
        })

    # Deduplicate: prefer CDS over gene at same position, prefer CDS over NCR
    priority = {'CDS': 3, 'NCR': 1, 'OTHER': 0}
    seen_positions = {}
    for f in sorted(features, key=lambda x: (priority.get(x['category'], 0), x['start'])):
        pos = (f['start'], f['end'])
        if pos not in seen_positions or priority.get(f['category'], 0) > priority.get(seen_positions[pos].get('category', ''), 0):
            seen_positions[pos] = f

    return acc, list(seen_positions.values())


def build_annotation_db(limit=None):
    """Parse all GB files and build annotation database."""
    anno = defaultdict(list)
    files = sorted(os.listdir(GB_DIR))
    total = len(files)
    matched = 0
    no_cds = 0

    if limit:
        files = files[:limit]

    for i, fname in enumerate(files):
        if not fname.endswith('.gb'):
            continue
        fpath = os.path.join(GB_DIR, fname)
        acc, genes = parse_genbank_file(fpath)
        if acc:
            anno[acc] = genes
            if genes:
                matched += 1
            else:
                no_cds += 1

        if (i + 1) % 500 == 0:
            print(f"  [{i+1}/{total}] parsed, {matched} with CDS, {no_cds} no CDS")

    print(f"\n  Total parsed: {len(anno)}")
    print(f"  With CDS annotations: {matched}")
    print(f"  Without CDS: {no_cds}")
    return anno


def match_to_virus_db(annotations):
    """Match annotations to viruses_full.json."""
    virus_path = DATA_DIR / "virus_genomes" / "viruses_full.json"
    with open(virus_path) as f:
        viruses = json.load(f)

    # For each virus, find matching annotation by accession
    matched = 0
    unmatched = 0
    total_genes = 0

    for vid, vmeta in viruses.items():
        acc = vmeta.get('accession', '')
        key = acc.split('.')[0] if '.' in acc else acc
        genes = annotations.get(key, [])
        if genes:
            vmeta['genes'] = genes
            total_genes += len(genes)
            matched += 1
        else:
            unmatched += 1

    print(f"\n  Total viruses: {len(viruses)}")
    print(f"  Matched to CDS: {matched}")
    print(f"  No CDS found: {unmatched}")
    print(f"  Total gene annotations: {total_genes}")

    # Save enriched virus database
    out_path = DATA_DIR / "virus_genomes" / "viruses_full_annotated.json"
    with open(out_path, 'w') as f:
        json.dump(viruses, f, indent=2)
    print(f"  Saved: {out_path}")

    return viruses


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=None, help='Limit GB files')
    p.add_argument('--gb-dir', default=None, help='GenBank records dir (default: $PAMIRDB_GB_DIR or known candidates)')
    p.add_argument('--fetch-missing', action='store_true',
                   help='Download .gb records from NCBI for viruses lacking a local record, then parse')
    p.add_argument('--fetch-limit', type=int, default=None, help='Max records to download (for testing)')
    p.add_argument('--exit-if-no-missing', action='store_true',
                   help='With --fetch-missing: skip reparse and exit when all records already present '
                        '(for scheduled runs)')
    args = p.parse_args()

    if args.fetch_missing:
        if args.gb_dir:
            gb_dir = Path(args.gb_dir)
        elif os.environ.get("PAMIRDB_GB_DIR"):
            gb_dir = Path(os.environ["PAMIRDB_GB_DIR"])
        else:
            gb_dir = REPO_DIR / "12.pamirdb" / "genbank_records"
        gb_dir.mkdir(parents=True, exist_ok=True)
        GB_DIR = gb_dir

        acc_map, _ = load_virus_accessions()
        covered = covered_accessions(GB_DIR)
        missing = sorted(set(acc_map) - covered)
        print(f"  Viruses with accession: {len(acc_map)}, records on disk: {len(covered)}, missing: {len(missing)}")
        if not missing:
            out_path = DATA_DIR / "virus_genomes" / "viruses_full_annotated.json"
            if args.exit_if_no_missing and out_path.exists():
                print("  Nothing to download — annotations up to date, skipping reparse.")
                raise SystemExit(0)
            print("  Nothing to download — all records present.")
        else:
            fetch_missing_records(missing, GB_DIR, limit=args.fetch_limit)
    else:
        GB_DIR = resolve_gb_dir(args.gb_dir)

    print("=" * 60)
    print("  Parsing GenBank records for CDS annotations")
    print(f"  Source: {GB_DIR}")
    print("=" * 60)

    annotations = build_annotation_db(limit=args.limit)
    viruses = match_to_virus_db(annotations)
