"""
PAmiRDB v2 Web Server -- Enhanced with position constraints, Query2, browse pages.
Pure Python stdlib. Based on Satish et al. (2019) Sci Rep 9:4627.
"""
import json, sqlite3, sys, os, io, math
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_DIR = Path(__file__).parent.parent / "data"
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
DB_PATH = DATA_DIR / "pamirdb.sqlite"
PREDICTIONS_FILE = DATA_DIR / "predictions_v6_conv.json"
if not PREDICTIONS_FILE.exists():
    PREDICTIONS_FILE = DATA_DIR / "predictions.json"
MIRNA_FILE = DATA_DIR / "mirna" / "plant_mirnas.json"
VIRUS_FILE = DATA_DIR / "virus_genomes" / "viruses_annotated.json"
if not VIRUS_FILE.exists():
    VIRUS_FILE = DATA_DIR / "virus_genomes" / "viruses.json"
VIRUS_FASTA = DATA_DIR / "virus_genomes" / "viruses.fasta"
VIRUS_HOST_FILE = DATA_DIR / "virus_host" / "virus_host.csv"
VIRUS_GENES_FILE = Path(__file__).parent.parent / "scripts" / "virus_genes.py"
# Supplementary accession-keyed virus index (predictions use GenBank accessions
# as target_virus_id, while viruses_annotated.json is keyed by taxid).
VIRUS_FULL_FILE = DATA_DIR / "virus_genomes" / "viruses_full.json"
VIRUS_FULL_FASTA = DATA_DIR / "virus_genomes" / "viruses_full.fasta"

# ── Database ───────────────────────────────────────────────────────

def _load_virus_full_sequences(fa_path):
    """Load accession-keyed sequences from viruses_full.fasta.

    Header format: >KEY|ACCESSION|FAMILY|NAME
    """
    seqs = {}
    try:
        cid, cseq = None, []
        for line in open(fa_path):
            line = line.strip()
            if not line:
                continue
            if line.startswith('>'):
                if cid:
                    seqs[cid] = ''.join(cseq)
                cid = line[1:].split('|')[0].split()[0].split('.')[0]
                cseq = []
            else:
                cseq.append(line)
        if cid:
            seqs[cid] = ''.join(cseq)
    except Exception:
        pass
    return seqs


def _ensure_columns(db, table, columns):
    """Add missing columns to an existing table (lightweight migration).

    CREATE TABLE IF NOT EXISTS never upgrades pre-existing legacy tables; the
    deployed pamirdb.sqlite has a viruses table without genus/species, which
    made inserts/selects referencing them fail.
    """
    have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in have:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def build_accession_virus_index(db):
    """Build the supplementary accession-keyed virus index.

    2026-10-03 fix: predictions_v7 references viruses by GenBank accession
    (target_virus_id, e.g. 'NC_014798'), but the viruses table is loaded from
    viruses_annotated.json which is keyed by taxid -- 2,442/2,442 lookups
    missed. The annotated (taxid) rows stay authoritative; accession-keyed rows
    from viruses_full.json (+ viruses_full.fasta sequences) are only inserted
    for keys not already present, so lookups resolve and /api/scan gets both
    sequence and family.
    """
    if not VIRUS_FULL_FILE.exists():
        return 0
    try:
        with open(VIRUS_FULL_FILE) as f:
            viruses = json.load(f)
    except Exception as e:
        print(f"  [WARN] could not load {VIRUS_FULL_FILE.name}: {e}")
        return 0

    seqs = _load_virus_full_sequences(str(VIRUS_FULL_FASTA)) if VIRUS_FULL_FASTA.exists() else {}
    existing = {r[0] for r in db.execute("SELECT virus_id FROM viruses")}
    added = 0
    for vid, info in viruses.items():
        if vid in existing:
            continue  # annotated table wins
        db.execute(
            "INSERT INTO viruses (virus_id,accession,name,family,genus,species,genome_length,sequence) VALUES (?,?,?,?,?,?,?,?)",
            (vid, info.get('accession', ''), info.get('name', ''),
             info.get('family', ''), info.get('genus', ''), info.get('species', ''),
             info.get('genome_length', 0), seqs.get(vid, '')))
        existing.add(vid)
        added += 1
    db.commit()
    if added:
        print(f"  Accession virus index: +{added} rows from viruses_full.json")
    return added


def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS mirnas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mirna_id TEXT UNIQUE NOT NULL, sequence TEXT NOT NULL,
            length INTEGER, species_code TEXT, species_name TEXT
        );
        CREATE TABLE IF NOT EXISTS viruses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            virus_id TEXT UNIQUE NOT NULL, accession TEXT, name TEXT,
            family TEXT, genus TEXT DEFAULT '', species TEXT DEFAULT '',
            genome_length INTEGER, sequence TEXT
        );
        CREATE TABLE IF NOT EXISTS virus_hosts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            virus_id TEXT, virus_name TEXT, host_species TEXT, host_common_name TEXT
        );
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mirna_id TEXT NOT NULL, virus_id TEXT NOT NULL,
            target_start INTEGER, target_end INTEGER,
            score REAL, energy REAL, num_mismatches INTEGER, num_gaps INTEGER,
            seed_perfect INTEGER, query_cover REAL, identity REAL,
            similarity REAL, query_start INTEGER, query_end INTEGER,
            alignment_length INTEGER, target_protein TEXT, matching_status TEXT,
            alignment TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_p_mirna ON predictions(mirna_id);
        CREATE INDEX IF NOT EXISTS idx_p_virus ON predictions(virus_id);
    """)
    
    # Legacy-schema upgrade: pre-existing viruses tables may predate the
    # genus/species columns (CREATE TABLE IF NOT EXISTS does not alter them).
    _ensure_columns(db, "viruses", {"genus": "TEXT DEFAULT ''", "species": "TEXT DEFAULT ''"})
    
    # Load data if empty
    if db.execute("SELECT COUNT(*) FROM mirnas").fetchone()[0] == 0 and MIRNA_FILE.exists():
        mirnas = json.load(open(MIRNA_FILE))
        for mid, info in mirnas.items():
            db.execute("INSERT INTO mirnas (mirna_id,sequence,length,species_code,species_name) VALUES (?,?,?,?,?)",
                (mid, info['sequence'], info.get('length',len(info['sequence'])),
                 info.get('species_code',''), info.get('species_name','')))
    
    if db.execute("SELECT COUNT(*) FROM viruses").fetchone()[0] == 0 and VIRUS_FILE.exists():
        viruses = json.load(open(VIRUS_FILE))
        seqs = {}
        if VIRUS_FASTA.exists():
            cid = None; cseq = []
            for line in open(VIRUS_FASTA):
                line = line.strip()
                if line.startswith('>'):
                    if cid: seqs[cid] = ''.join(cseq)
                    cid = line[1:].split('|')[0]; cseq = []
                else: cseq.append(line)
            if cid: seqs[cid] = ''.join(cseq)
        for vid, info in viruses.items():
            db.execute("INSERT INTO viruses (virus_id,accession,name,family,genus,species,genome_length,sequence) VALUES (?,?,?,?,?,?,?,?)",
                (vid, info.get('accession',''), info.get('name',''),
                 info.get('family',''), info.get('genus',''), info.get('species',''),
                 info.get('genome_length',0), seqs.get(vid,'')))
    
    if db.execute("SELECT COUNT(*) FROM virus_hosts").fetchone()[0] == 0 and VIRUS_HOST_FILE.exists():
        for line in open(VIRUS_HOST_FILE):
            if line.startswith('virus_id'): continue
            parts = line.strip().split(',')
            if len(parts) >= 4:
                db.execute("INSERT INTO virus_hosts (virus_id,virus_name,host_species,host_common_name) VALUES (?,?,?,?)",
                    (parts[0], parts[1], parts[2], parts[3]))
    
    if db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0 and PREDICTIONS_FILE.exists():
        preds = json.load(open(PREDICTIONS_FILE))
        for p in preds:
            db.execute("""INSERT INTO predictions 
                (mirna_id,virus_id,target_start,target_end,score,energy,
                 num_mismatches,num_gaps,seed_perfect,query_cover,identity,
                 similarity,query_start,query_end,alignment_length,
                 target_protein,matching_status,alignment)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p['mirna_id'], p.get('target_virus_id',p.get('virus_id','')),
                 p.get('target_start', 0), p.get('target_end', 0),
                 p.get('score', p.get('miranda_score', 0)), p.get('energy', p.get('miranda_energy', 0)),
                 p.get('num_mismatches', p.get('mismatches', 0)),
                 p.get('num_gaps', 0), int(p.get('seed_perfect', 1)),
                 p.get('query_cover', p.get('identity', 0)), p.get('identity', 0),
                 p.get('similarity', 0), p.get('query_start', 1),
                 p.get('query_end', 0), p.get('alignment_length', 0),
                 p.get('target_protein', ''), p.get('matching_status', ''),
                 p.get('alignment', '')))
    
    # Supplementary accession-keyed virus index (runs on every startup, only
    # fills gaps; annotated/taxid rows always win).
    build_accession_virus_index(db)
    
    db.commit()
    return db


# ── Query engine (enhanced) ────────────────────────────────────────

COLS = ['mirna_id','mirna_seq','species_name','virus_id','virus_name',
        'virus_family','target_start','target_end','score','energy',
        'num_mismatches','num_gaps','seed_perfect','query_cover','identity',
        'similarity','query_start','query_end','alignment_length',
        'target_protein','matching_status','alignment',
        # ── v7 multi-algorithm fields ──
        'consensus_level','num_algorithms','consensus_detail',
        'best_energy','best_identity','seed_quality_score',
        'miranda_score','miranda_energy','miranda_identity','miranda_similarity',
        'psrna_score','psrna_energy','psrna_alignment',
        'rnahybrid_mfe','rnahybrid_seed','rnahybrid_alignment',
        # ── v7 gene annotation ──
        'target_gene','target_product','targeting_status','targeting_category']


def search(db, **filters):
    try:
        results = _search_v7(db, **filters)
        if results:
            return results
        return _search_compat(db, **filters)
    except Exception:
        return _search_compat(db, **filters)


def _search_compat(db, **filters):
    """Fallback: query `predictions` table when predictions_v7 doesn't exist."""
    sql = """SELECT p.mirna_id, COALESCE(m.sequence,'') as mirna_seq,
                    COALESCE(m.species_name,'') as species_name,
                    p.virus_id as target_virus_id,
                    COALESCE(v.name,'')   as target_virus_name,
                    COALESCE(v.family,'') as target_virus_family,
                    p.target_start, p.target_end, p.score, p.energy,
                    p.num_mismatches, p.num_gaps, p.seed_perfect,
                    p.query_cover, p.identity, p.similarity,
                    p.query_start, p.query_end, p.alignment_length,
                    p.target_protein, p.matching_status, p.alignment,
                    CASE WHEN p.energy<=-22 AND p.identity>=80 THEN 'HIGH'
                         WHEN p.energy<=-18 AND p.identity>=70 THEN 'MEDIUM'
                         ELSE 'LOW' END as consensus_level,
                    1 as num_algorithms, 'miRanda' as consensus_detail,
                    p.energy as best_energy, p.identity as best_identity,
                    p.identity as seed_quality_score,
                    p.score as miranda_score, p.energy as miranda_energy,
                    p.identity as miranda_identity, p.similarity as miranda_similarity,
                    NULL as psrna_score, NULL as psrna_energy, NULL as psrna_alignment,
                    NULL as rnahybrid_mfe, p.seed_perfect as rnahybrid_seed, NULL as rnahybrid_alignment,
                    p.target_protein as target_gene, p.target_protein as target_product,
                    p.matching_status as targeting_status, '' as targeting_category
             FROM predictions p
             LEFT JOIN mirnas m  ON p.mirna_id  = m.mirna_id
             LEFT JOIN viruses v ON p.virus_id   = v.virus_id
             WHERE 1=1"""
    params = []
    # ----- filters -----
    mirna_list = filters.get('mirna_list', '')
    if mirna_list:
        ids = [x.strip() for x in mirna_list.split(',') if x.strip()]
        if ids:
            sql += ' AND p.mirna_id IN (%s)' % ','.join('?'*len(ids))
            params.extend(ids)
    elif filters.get('mirna_id'):
        sql += ' AND p.mirna_id LIKE ?'; params.append('%'+filters['mirna_id']+'%')
    if filters.get('virus_id'):
        sql += ' AND p.virus_id=?'; params.append(filters['virus_id'])
    if filters.get('virus_family'):
        sql += ' AND LOWER(v.family) LIKE ?'; params.append('%'+filters['virus_family'].lower()+'%')
    if filters.get('max_energy') is not None:
        sql += ' AND p.energy<=?'; params.append(filters['max_energy'])
    if filters.get('min_identity') is not None:
        sql += ' AND p.identity>=?'; params.append(filters['min_identity'])
    if filters.get('max_mismatches') is not None:
        sql += ' AND p.num_mismatches<=?'; params.append(filters['max_mismatches'])
    if filters.get('seed_perfect'):
        sql += ' AND p.seed_perfect=1'
    sql += ' ORDER BY p.energy ASC LIMIT 500'
    rows = db.execute(sql, params).fetchall()
    return [dict(zip(COLS, r)) for r in rows]


def _search_v7(db, **filters):
    # Use predictions_v7 table which has all fields embedded (no JOIN needed)
    sql = """SELECT p.mirna_id, p.mirna_seq, '' as species_name, -- species from mirna_sp lookup by frontend
                    p.target_virus_id, p.target_virus_name, p.target_virus_family,
                    p.target_start, p.target_end, 0 as score, p.best_energy as energy,
                    p.miranda_mismatches as num_mismatches, p.miranda_gaps as num_gaps, p.seed_perfect,
                    p.query_cover, p.best_identity as identity,
                    p.miranda_similarity as similarity, p.query_start, p.query_end,
                    p.alignment_length, p.target_product as target_protein, p.targeting_status as matching_status,
                    p.alignment,
                    p.consensus_level, p.num_algorithms, p.consensus_detail,
                    p.best_energy, p.best_identity, p.seed_quality_score,
                    p.miranda_score, p.miranda_energy, p.miranda_identity, p.miranda_similarity,
                    p.psrna_score, p.psrna_energy, p.psrna_alignment,
                    p.rnahybrid_mfe, p.rnahybrid_seed, p.rnahybrid_alignment,
                    p.target_gene, p.target_product, p.targeting_status, p.targeting_category
             FROM predictions_v7 p WHERE 1=1"""
    params = []

    col_map = {'mirna_id':'p.mirna_id','virus_id':'p.target_virus_id',
               'virus_family':'p.target_virus_family','plant_species':'p.mirna_id'}
    for k in ['mirna_id','virus_id','virus_family','plant_species']:
        if k in filters:
            sql += f" AND {col_map[k]}=?"
            params.append(filters[k])

    for k in ['max_energy','min_identity','min_query_cover','min_similarity']:
        if k in filters:
            col = k.replace('max_','').replace('min_','')
            if col == 'energy': col = 'best_energy'
            elif col == 'identity': col = 'best_identity'
            elif col == 'similarity': col = 'miranda_similarity'
            sql += f" AND p.{col} {'<=' if k.startswith('max') else '>='} ?"
            params.append(filters[k])

    if 'max_mismatches' in filters:
        sql += " AND p.miranda_mismatches <= ?"
        params.append(int(filters['max_mismatches']))

    if 'seed_perfect' in filters:
        sql += " AND p.seed_perfect = ?"
        params.append(int(filters['seed_perfect']))
    
    # NEW: position constraints - check that specified positions are paired
    # We filter post-query since position_binding isn't in SQLite
    # (stored in alignment string, check in Python)
    
    # NEW: multi-miRNA batch (comma-separated)
    if 'mirna_list' in filters:
        ids = [x.strip() for x in filters['mirna_list'].split(',') if x.strip()]
        if ids:
            placeholders = ','.join(['?']*len(ids))
            sql += f" AND p.mirna_id IN ({placeholders})"
            params.extend(ids)
    
    # Query2 preset
    if filters.get('query2'):
        sql += " AND p.seed_perfect=1 AND p.miranda_mismatches<=2 AND p.alignment_length>=18 AND p.best_identity>80"
    
    sql += " ORDER BY p.best_energy ASC"
    
    if 'limit' in filters:
        sql += f" LIMIT {int(filters['limit'])}"
    if 'offset' in filters:
        sql += f" OFFSET {int(filters['offset'])}"
    
    rows = db.execute(sql, params).fetchall()
    results = [dict(zip(COLS, row)) for row in rows]
    
    # Post-filter: position constraints
    if 'pos_match' in filters or 'pos_au' in filters:
        filtered = []
        pos_match = [int(x) for x in filters.get('pos_match','').split(',') if x.strip().isdigit()]
        pos_au = [int(x) for x in filters.get('pos_au','').split(',') if x.strip().isdigit()]
        
        for r in results:
            keep = True
            aln = r.get('alignment', '')
            # Extract position binding from alignment
            if pos_match and not _check_aln_positions(aln, pos_match):
                keep = False
            # Check A/U at positions from mirna_seq
            if keep and pos_au:
                seq = r.get('mirna_seq', '')
                for pos in pos_au:
                    if pos < 1 or pos > len(seq) or seq[pos-1].upper() not in ('A','U'):
                        keep = False; break
            if keep:
                filtered.append(r)
        results = filtered
    
    return results


def _check_aln_positions(alignment_str, positions):
    """Check if specified positions are paired in the alignment."""
    try:
        lines = alignment_str.split('\n')
        if len(lines) < 2: return False
        pipes = lines[1].strip()
        mirna_line = lines[0]
        # Strip prefix/suffix
        mirna_line = mirna_line.replace("miRNA  5' ","").replace(" 3'","").strip()
        
        # Ensure same length
        n = min(len(mirna_line), len(pipes))
        mirna_pos = 0
        for i in range(n):
            m_char = mirna_line[i]
            p_char = pipes[i]
            if m_char != '-':
                mirna_pos += 1
                if mirna_pos in positions:
                    if p_char != '|':
                        return False
        return True
    except Exception:
        return False


def get_mirna_tree(db):
    """返回 {species_code: {name, mirnas:[{id,seq,len}]}} 结构，供前端多级筛选。"""
    rows = db.execute(
        "SELECT species_code, species_name, mirna_id, sequence, length "
        "FROM mirnas WHERE species_code != '' ORDER BY species_name, mirna_id"
    ).fetchall()
    tree = {}
    for code, name, mid, seq, ln in rows:
        if code not in tree:
            tree[code] = {"code": code, "name": name or code, "mirnas": []}
        tree[code]["mirnas"].append({"id": mid, "seq": seq, "len": ln or len(seq or "")})
    return sorted(tree.values(), key=lambda x: x["name"])


def get_mirnas_for_species(db, species_code):
    rows = db.execute(
        "SELECT mirna_id, sequence, length FROM mirnas "
        "WHERE species_code = ? ORDER BY mirna_id", (species_code,)
    ).fetchall()
    return [{"id": r[0], "seq": r[1], "len": r[2] or len(r[1] or "")} for r in rows]


def get_species_list(db, family=None, genus=None):
    sql = ("SELECT species_code, species_name, COUNT(*) FROM mirnas "
           "WHERE species_name != '' AND species_code != ''")
    params = []
    if family:
        sql += " AND plant_family = ?"
        params.append(family)
    if genus:
        sql += " AND plant_genus = ?"
        params.append(genus)
    sql += " GROUP BY species_code, species_name ORDER BY COUNT(*) DESC"
    rows = db.execute(sql, params).fetchall()
    return [{"code": r[0], "name": r[1], "count": r[2]} for r in rows]


def get_mirna_families(db):
    rows = db.execute(
        "SELECT plant_family, COUNT(DISTINCT species_name) as sc, COUNT(*) as mc "
        "FROM mirnas WHERE plant_family != '' "
        "GROUP BY plant_family ORDER BY mc DESC"
    ).fetchall()
    return [{"family": r[0], "species_count": r[1], "mirna_count": r[2]} for r in rows]


def get_mirna_genera(db, family=None):
    sql = ("SELECT plant_genus, COUNT(DISTINCT species_name) as sc, COUNT(*) as mc "
           "FROM mirnas WHERE plant_genus != '' AND plant_family != ''")
    params = []
    if family:
        sql += " AND plant_family = ?"
        params.append(family)
    sql += " GROUP BY plant_genus ORDER BY mc DESC"
    rows = db.execute(sql, params).fetchall()
    return [{"genus": r[0], "species_count": r[1], "mirna_count": r[2]} for r in rows]

def get_virus_detail(db, vid):
    row = db.execute(
        "SELECT virus_id, accession, name, family, genome_length, sequence, genus "
        "FROM viruses WHERE virus_id=? OR accession=?",
        (vid, vid)
    ).fetchone()
    if not row:
        row = db.execute(
            "SELECT virus_id, accession, name, family, genome_length, sequence, genus "
            "FROM viruses WHERE name LIKE ? LIMIT 1",
            (f"%{vid}%",)
        ).fetchone()
    if row:
        seq = row[5]
        if (not seq or len(seq) < 10) and VIRUS_FASTA.exists():
            seq = _load_virus_sequence_from_fasta(vid, str(VIRUS_FASTA))
        # Load gene annotations from virus_genes table
        try:
            genes = db.execute(
                "SELECT gene, product, start, end, strand FROM virus_genes WHERE virus_id=? ORDER BY start",
                (row[0],)
            ).fetchall()
            gene_list = [{"gene": g[0], "product": g[1], "start": g[2], "end": g[3], "strand": g[4] or "+"} for g in genes]
        except Exception:
            gene_list = []
        return {"virus_id": row[0], "accession": row[1], "name": row[2],
                "family": row[3], "genome_length": row[4], "sequence": seq,
                "genus": row[6] or "", "genes": gene_list}
    return None

def _load_virus_sequence_from_fasta(vid, fa_path):
    """Load a virus sequence from FASTA by matching virus_id or accession."""
    try:
        cid = None; cseq = []
        for line in open(fa_path):
            line = line.strip()
            if line.startswith('>'):
                if cid and cid == vid:
                    return ''.join(cseq)
                # Parse header: ">KEY|ACCESSION|..." or ">ACCESSION ..."
                h = line[1:]
                parts = h.split('|')
                cid = parts[0].split()[0].split('.')[0]
                # Also register accession
                if len(parts) >= 2:
                    if parts[1].split('.')[0] == vid:
                        cid = vid  # match by accession
                cseq = []
            else:
                cseq.append(line)
        if cid and cid == vid:
            return ''.join(cseq)
    except Exception:
        pass
    return ""

def get_network_detail(db, dtype, did):
    if dtype == 'species':
        rows = db.execute(
            "SELECT p.mirna_id, p.target_protein, COUNT(*) c "
            "FROM predictions p JOIN mirnas m ON p.mirna_id=m.mirna_id "
            "WHERE m.species_name=? AND p.target_protein!='' AND p.target_protein!='Unknown' "
            "GROUP BY p.mirna_id, p.target_protein ORDER BY c DESC LIMIT 200",
            (did,)
        ).fetchall()
    elif dtype == 'mirna':
        rows = db.execute(
            "SELECT v.name, p.target_protein, COUNT(*) c "
            "FROM predictions p JOIN viruses v ON p.virus_id=v.virus_id "
            "WHERE p.mirna_id=? AND p.target_protein!='' AND p.target_protein!='Unknown' "
            "GROUP BY v.name, p.target_protein ORDER BY c DESC LIMIT 100",
            (did,)
        ).fetchall()
    else:
        return []
    return [{"source": r[0], "target": r[1], "count": r[2]} for r in rows]

def get_stats(db):
    try:
        n_m = db.execute("SELECT COUNT(DISTINCT mirna_id) FROM predictions_v7").fetchone()[0]
        n_v = db.execute("SELECT COUNT(DISTINCT target_virus_id) FROM predictions_v7").fetchone()[0]
        n_p = db.execute("SELECT COUNT(*) FROM predictions_v7").fetchone()[0]
    except Exception:
        n_m = db.execute("SELECT COUNT(*) FROM mirnas").fetchone()[0]
        n_v = db.execute("SELECT COUNT(*) FROM viruses").fetchone()[0]
        n_p = db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    species = dict(db.execute("SELECT species_name,COUNT(*) FROM mirnas GROUP BY species_name ORDER BY COUNT(*) DESC LIMIT 50").fetchall())
    families = dict(db.execute("SELECT family,COUNT(*) FROM viruses GROUP BY family").fetchall())
    
    # Protein distribution
    proteins = dict(db.execute(
        "SELECT target_protein,COUNT(*) FROM predictions WHERE target_protein!='' GROUP BY target_protein ORDER BY COUNT(*) DESC LIMIT 10"
    ).fetchall())
    
    # Matching status
    match_status = dict(db.execute(
        "SELECT matching_status,COUNT(*) FROM predictions WHERE matching_status!='' GROUP BY matching_status"
    ).fetchall())
    
    return {"total_mirnas":n_m,"total_viruses":n_v,"total_predictions":n_p,
            "species_distribution":species,"virus_family_distribution":families,
            "protein_distribution":proteins,"matching_status":match_status}


def get_mirnas(db, species=None):
    sql = "SELECT mirna_id,sequence,species_code,species_name,length FROM mirnas"
    params = []
    if species: sql += " WHERE species_code=?"; params.append(species)
    rows = db.execute(sql, params).fetchall()
    return [{"mirna_id":r[0],"sequence":r[1],"species_code":r[2],"species_name":r[3],"length":r[4]} for r in rows]


def get_viruses(db, family=None, genus=None, search=None, limit=100, offset=0):
    sql = "SELECT virus_id,accession,name,family,genus,genome_length FROM viruses WHERE 1=1"
    params = []
    if family:
        sql += " AND family=?"
        params.append(family)
    if genus:
        sql += " AND genus=?"
        params.append(genus)
    if search:
        sql += " AND (name LIKE ? OR accession LIKE ? OR virus_id LIKE ?)"
        kw = f"%{search}%"
        params.extend([kw, kw, kw])
    sql += " ORDER BY name"
    count_sql = sql.replace("SELECT virus_id,accession,name,family,genus,genome_length", "SELECT COUNT(*)")
    total = db.execute(count_sql, params).fetchone()[0]
    sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
    rows = db.execute(sql, params).fetchall()
    return {
        "total": total,
        "viruses": [{"virus_id":r[0],"accession":r[1],"name":r[2],"family":r[3],"genus":r[4],"genome_length":r[5]} for r in rows]
    }


def get_genera(db, family=None):
    sql = "SELECT genus, COUNT(*) c FROM viruses WHERE genus!='' "
    params = []
    if family:
        sql += "AND family=? "
        params.append(family)
    sql += "GROUP BY genus ORDER BY c DESC"
    rows = db.execute(sql, params).fetchall()
    return [{"genus": r[0], "count": r[1]} for r in rows]


def get_virus_hosts(db, virus_id=None):
    sql = "SELECT virus_id,virus_name,host_species,host_common_name FROM virus_hosts"
    params = []
    if virus_id: sql += " WHERE virus_id=?"; params.append(virus_id)
    rows = db.execute(sql, params).fetchall()
    return [{"virus_id":r[0],"virus_name":r[1],"host_species":r[2],"host_common_name":r[3]} for r in rows]


def get_browse_species(db, species_code):
    """Get pre-computed browse page data for a species."""
    sql = """SELECT p.mirna_id,m.sequence,p.virus_id,v.name,v.family,
                    p.energy,p.num_mismatches,p.seed_perfect,p.identity,
                    p.similarity,p.target_protein,p.matching_status,p.alignment
             FROM predictions p
             JOIN mirnas m ON p.mirna_id=m.mirna_id
             JOIN viruses v ON p.virus_id=v.virus_id
             WHERE m.species_code=?
             ORDER BY p.energy ASC"""
    rows = db.execute(sql, [species_code]).fetchall()
    return [{"mirna_id":r[0],"sequence":r[1],"virus_id":r[2],"virus_name":r[3],
             "family":r[4],"energy":r[5],"mismatches":r[6],"seed_perfect":r[7],
             "identity":r[8],"similarity":r[9],"target_protein":r[10],
             "matching_status":r[11],"alignment":r[12]} for r in rows]


def get_browse_family(db, family):
    """Get pre-computed browse page data for a virus family."""
    sql = """SELECT p.mirna_id,m.species_name,p.virus_id,v.name,
                    p.energy,p.num_mismatches,p.seed_perfect,p.identity,
                    p.similarity,p.target_protein,p.matching_status,p.alignment
             FROM predictions p
             JOIN mirnas m ON p.mirna_id=m.mirna_id
             JOIN viruses v ON p.virus_id=v.virus_id
             WHERE v.family=?
             ORDER BY p.energy ASC"""
    rows = db.execute(sql, [family]).fetchall()
    return [{"mirna_id":r[0],"species":r[1],"virus_id":r[2],"virus_name":r[3],
             "energy":r[4],"mismatches":r[5],"seed_perfect":r[6],"identity":r[7],
             "similarity":r[8],"target_protein":r[9],"matching_status":r[10],
             "alignment":r[11]} for r in rows]


# ── HTML pages ─────────────────────────────────────────────────────

_here = Path(__file__).parent
def _read_html(name):
    p = _here / name
    return p.read_text(encoding='utf-8') if p.exists() else ""

INDEX_NEW_HTML  = _read_html("index_new.html")
INDEX_HTML      = _read_html("index.html")
# Default to new workbench; fall back to old browse
_MAIN_HTML = INDEX_NEW_HTML if INDEX_NEW_HTML else INDEX_HTML


# ── Real-time miRNA sliding-window scan (no external tools needed) ──

def _rna_pair(a, b):
    a, b = a.upper().replace('T','U'), b.upper().replace('T','U')
    if (a,b) in {('A','U'),('U','A'),('G','C'),('C','G')}: return 'WC'
    if (a,b) in {('G','U'),('U','G')}: return 'WC'  # count wobble as pair for seed
    return 'MM'

def _scan_seed_wc(aln_str):
    """Count Watson-Crick pairs in miRNA seed region (positions 2-8)."""
    lines = aln_str.split('\n')
    if len(lines) < 2: return 0
    mline = lines[0].replace("miRNA  5' ","").replace(" 3'","")
    pipes  = lines[1].strip()
    pos = 0; wc = 0
    for mc, pc in zip(mline, pipes):
        if mc != '-':
            pos += 1
            if 2 <= pos <= 8 and pc == '|': wc += 1
    return wc

def _scan_max_cons_mm(aln_str):
    """Count maximum consecutive mismatches in alignment pipe line."""
    lines = aln_str.split('\n')
    pipes = lines[1].strip() if len(lines) >= 2 else ''
    best = cur = 0
    for p in pipes:
        if p != '|': cur += 1; best = max(best, cur)
        else: cur = 0
    return best

def _approx_mfe(aln_str):
    """Nearest-neighbour MFE approximation from alignment (kcal/mol)."""
    lines = aln_str.split('\n')
    if len(lines) < 3: return 0.0
    mline = lines[0].replace("miRNA  5' ","").replace(" 3'","")
    tline = lines[2].replace("target 3' ","").replace(" 5'","")
    NN = {('A','U'):-2.0,('U','A'):-2.0,('G','C'):-3.1,('C','G'):-3.1,
          ('G','U'):-1.0,('U','G'):-1.0}
    mfe = 3.4  # init penalty
    for mc, tc in zip(mline, tline):
        mc_u = mc.upper().replace('T','U'); tc_u = tc.upper().replace('T','U')
        if mc == '-' or tc == '-': mfe += 1.5
        else: mfe += NN.get((mc_u, tc_u), 1.8)
    return round(mfe, 2)

def run_mirna_scan(mirna_id, mirna_seq, virus_id, virus_name, virus_family, virus_seq,
                   tier='moderate', limit=50):
    """
    Sliding window miRNA:target scan across a virus genome.
    Returns list of dicts compatible with /api/search result format.
    Uses pure Python alignment engine — no external tools needed.
    """
    try:
        from alignment import align_mirna_to_target, MAX_GAPS
    except ImportError:
        return []

    mirna_seq = mirna_seq.upper().replace('T','U')
    virus_seq = virus_seq.upper().replace('T','U')
    mlen = len(mirna_seq)
    slack = max(5, mlen // 4)
    window_sz = mlen + slack
    step = max(1, mlen // 2)

    TIERS = {
        'strict':   dict(max_mm=3, max_cons=2, min_e=-20.0, min_seed=6),
        'moderate': dict(max_mm=5, max_cons=3, min_e=-14.0, min_seed=4),
        'loose':    dict(max_mm=7, max_cons=4, min_e=-10.0, min_seed=2),
    }
    TH = TIERS.get(tier, TIERS['moderate'])

    hits = []
    for start in range(0, max(1, len(virus_seq) - mlen + 1), step):
        window = virus_seq[start : start + window_sz]
        r = align_mirna_to_target(mirna_id, mirna_seq, virus_id, window)
        if r is None: continue

        seed_wc  = _scan_seed_wc(r.alignment_str)
        max_cons = _scan_max_cons_mm(r.alignment_str)
        mfe      = _approx_mfe(r.alignment_str) if r.energy == 0 else r.energy

        if (r.num_mismatches <= TH['max_mm'] and
            r.num_gaps      <= MAX_GAPS and   # gap-cap: no gap-riddled garbage hits
            max_cons        <= TH['max_cons'] and
            mfe             <= TH['min_e'] and
            seed_wc         >= TH['min_seed']):

            # Translate window-local coordinates to genome coordinates
            abs_start = start + (r.target_start or 0)
            abs_end   = start + (r.target_end   or mlen)

            # Consensus level
            if   mfe <= -22 and r.identity >= 78 and r.num_mismatches <= 1: level = 'HIGH'
            elif mfe <= -18 and r.identity >= 70 and r.num_mismatches <= 3: level = 'MEDIUM'
            else: level = 'LOW'

            hits.append({
                'mirna_id': mirna_id, 'mirna_seq': mirna_seq,
                'species_name': '', 'virus_id': virus_id,
                'virus_name': virus_name, 'virus_family': virus_family,
                'target_start': abs_start, 'target_end': abs_end,
                'score': round(r.score, 1), 'energy': round(mfe, 2),
                'num_mismatches': r.num_mismatches, 'num_gaps': r.num_gaps,
                'seed_perfect': int(seed_wc >= 6),
                'query_cover': round(r.query_cover, 1),
                'identity': round(r.identity, 1),
                'similarity': round(r.similarity, 1),
                'alignment': r.alignment_str,
                # Extra fields expected by normalizeDBResult()
                'best_energy': round(mfe, 2),
                'best_identity': round(r.identity, 1),
                'seed_perfect_wc': seed_wc,
                'consensus_level': level,
                'num_algorithms': 1, 'total_algorithms': 1,
                '_scan_mode': True,
            })

    # Deduplicate overlapping hits (keep best energy within mlen/2 window)
    hits.sort(key=lambda h: h['energy'])
    deduped = []
    for h in hits:
        overlap = any(abs(h['target_start'] - d['target_start']) < mlen // 2 for d in deduped)
        if not overlap:
            deduped.append(h)

    return deduped[:limit]


# ── HTTP Handler ───────────────────────────────────────────────────

class PAmiRDBHandler(BaseHTTPRequestHandler):
    db = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # Support /pamirdb/api/... as alias for /api/...
        if path.startswith('/pamirdb/'):
            path = path[len('/pamirdb'):]
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        if path in ('/', '/index.html', '/index_new.html', '/predict'):
            self._serve_html(_MAIN_HTML if _MAIN_HTML else self._build_index())
        elif path in ('/network', '/network.html'):
            fn = Path(__file__).parent / 'network.html'
            self._serve_html(fn.read_text(encoding='utf-8') if fn.exists() else '<h1>network.html not found</h1>')
        elif path == '/classic':
            self._serve_html(INDEX_HTML if INDEX_HTML else self._build_index())
        elif path == '/api/stats':
            self._json(get_stats(self.db))
        elif path == '/api/mirnas':
            self._json({"mirnas": get_mirnas(self.db, q.get('species'))})
        elif path == '/api/viruses':
            try: lim = min(int(q.get('limit', 100)), 500)
            except: lim = 100
            try: off = int(q.get('offset', 0))
            except: off = 0
            self._json(get_viruses(self.db, q.get('family'), q.get('genus'), q.get('search'), lim, off))
        elif path == '/api/virus-hosts':
            hosts = get_virus_hosts(self.db, q.get('virus_id'))
            self._json({"total": len(hosts), "hosts": hosts})
        elif path == '/api/species':
            family = q.get('family', '')
            genus = q.get('genus', '')
            self._json(get_species_list(self.db, family if family else None, genus if genus else None))
        elif path == '/api/mirna_families':
            self._json(get_mirna_families(self.db))
        elif path == '/api/mirna_genera':
            family = q.get('family', '')
            self._json(get_mirna_genera(self.db, family if family else None))
        elif path == '/api/mirnas_by_species':
            spe = q.get('species', '')
            self._json(get_mirnas_for_species(self.db, spe) if spe else [])
        elif path == '/api/mirna_tree':
            self._json(get_mirna_tree(self.db))
        elif path == '/api/families':
            try:
                rows = self.db.execute(
                    "SELECT target_virus_family, COUNT(*) c FROM predictions_v7 WHERE target_virus_family!='' GROUP BY target_virus_family ORDER BY c DESC"
                ).fetchall()
            except Exception:
                rows = self.db.execute(
                    "SELECT family, COUNT(*) c FROM viruses WHERE family!='' GROUP BY family ORDER BY c DESC"
                ).fetchall()
            self._json([{"family": r[0], "count": r[1]} for r in rows])
        elif path == '/api/genera':
            family = q.get('family', '')
            self._json(get_genera(self.db, family if family else None))
        elif path.startswith('/api/virus/'):
            vid = path.split('/')[-1]
            self._json(get_virus_detail(self.db, vid))
        elif path == '/api/export':
            self._csv_export()
        elif path == '/api/network/detail':
            q2 = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            self._json(get_network_detail(self.db, q2.get('type',''), q2.get('id','')))
        elif path == '/api/search':
            self._handle_search(q)
        elif path == '/api/query2':
            # Query2 preset: A/U@10-11, compulsory, >=18nt, <=2mm, >80% identity
            filters = {'query2': True, 'pos_au': '10,11', 'pos_match': '10,11'}
            for k in ['virus_family', 'plant_species', 'limit', 'offset']:
                if k in q: filters[k] = q[k]
            results = search(self.db, **filters)
            total = len(results)
            try: off = int(q.get('offset',0))
            except: off = 0
            try: lim = int(q.get('limit',100))
            except: lim = 100
            self._json({"total":total,"query_type":"Query2 - A/U@10-11","results":results[off:off+lim]})
        elif path.startswith('/browse/species/'):
            code = path.split('/')[-1]
            data = get_browse_species(self.db, code)
            self._json({"species": code, "total": len(data), "results": data})
        elif path.startswith('/browse/family/'):
            family = path.split('/')[-1]
            data = get_browse_family(self.db, family)
            self._json({"family": family, "total": len(data), "results": data})
        else:
            self.send_error(404)
    
    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith('/pamirdb/'):
            path = path[len('/pamirdb'):]
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode('utf-8')) if length > 0 else {}

        if path == '/api/predict':
            self._handle_predict_single(body)
        elif path == '/api/predict_batch':
            self._handle_predict_batch(body)
        elif path == '/api/scan':
            self._handle_scan(body)
        else:
            self.send_error(404)

    def _run_one_predict(self, mid, mseq, tid, tname, tfam, tseq, fast, body):
        from consensus import run_consensus_prediction, to_dict
        mseq = mseq.strip().upper().replace('T', 'U')
        tseq = tseq.strip().upper().replace('T', 'U')
        if len(mseq) < 15 or len(tseq) < 20:
            return {"error": "sequence too short", "mirna_id": mid}
        # 2026-10-03 fix: run_consensus_prediction() did not accept `algorithms`,
        # so every call raised TypeError (live P0). The signature now accepts it
        # (consensus.py) and unknown tokens are ignored there.
        algorithms = body.get('algorithms', ['miranda', 'psrna', 'rnahybrid'])
        if not isinstance(algorithms, list):
            algorithms = ['miranda', 'psrna', 'rnahybrid']
        algorithms = [str(a) for a in algorithms]
        # Honour an explicit request for the slow local layers unless fast_mode
        # was set explicitly by the caller.
        if 'fast_mode' not in body and any(
                a.strip().lower() in ('rna22', 'tapir', 'psrobot') for a in algorithms):
            fast = False
        cr = run_consensus_prediction(mid, mseq, tid, tname, tfam, tseq,
                                      fast_mode=fast, algorithms=algorithms)
        if cr is None:
            return {"mirna_id": mid, "consensus_level": "NONE", "num_algorithms": 0,
                    "error": "No valid alignment found"}
        result = to_dict(cr)
        result['mirna_id'] = mid
        result['mirna_seq'] = mseq
        result['target_seq'] = tseq
        try:
            from validation_amirna import get_validation_status, extract_family
            fam = extract_family(mid)
            val = get_validation_status(fam)
            result['experimentally_validated'] = val.get('validated', False)
            if val.get('validated'):
                result['validation_evidence'] = val.get('evidence', '')
        except Exception:
            pass
        try:
            from vsirna_conservation import get_hotspot_recommendation
            hs = get_hotspot_recommendation(tid, result.get('target_start', 0),
                                            result.get('target_end', 0))
            result['in_vsirna_hotspot'] = bool(hs)
        except Exception:
            pass
        return result

    def _handle_predict_single(self, body):
        try:
            result = self._run_one_predict(
                body.get('mirna_id', 'user-mirna'),
                body.get('mirna_seq', ''),
                body.get('target_id', 'user-target'),
                body.get('target_name', 'Custom target'),
                body.get('target_family', ''),
                body.get('target_seq', ''),
                body.get('fast_mode', True),
                body
            )
            self._json(result)
        except Exception as e:
            self._json({"error": str(e)}, status=500)

    def _handle_predict_batch(self, body):
        """多miRNA批量预测：mirnas=[{id,seq}], target_seq, target_id, ..."""
        try:
            mirnas = body.get('mirnas', [])
            if not mirnas:
                self._json({"error": "mirnas list required"}, status=400)
                return
            tid = body.get('target_id', 'user-target')
            tname = body.get('target_name', 'Custom target')
            tfam = body.get('target_family', '')
            tseq = body.get('target_seq', '')
            fast = body.get('fast_mode', True)
            max_batch = 20
            results = []
            for item in mirnas[:max_batch]:
                mid = item.get('id', 'mirna')
                mseq = item.get('seq', '')
                r = self._run_one_predict(mid, mseq, tid, tname, tfam, tseq, fast, body)
                results.append(r)
            # Sort by energy ascending (best first)
            results.sort(key=lambda x: x.get('best_energy', 0) or 0)
            self._json({"total": len(results), "results": results})
        except Exception as e:
            self._json({"error": str(e)}, status=500)

    def _handle_scan(self, body):
        """
        Real-time sliding-window scan:  POST /api/scan
        Body: {mirna_id, mirna_seq, virus_id, [virus_seq],
               [virus_name], [virus_family], [tier], [limit]}
        If virus_seq not supplied, look it up from DB viruses table.
        """
        try:
            mirna_id   = body.get('mirna_id', 'user-mirna').strip()
            mirna_seq  = body.get('mirna_seq', '').strip().upper().replace('T','U')
            virus_id   = body.get('virus_id', 'user-virus').strip()
            virus_seq  = body.get('virus_seq', '').strip().upper().replace('T','U')
            virus_name = body.get('virus_name', virus_id)
            virus_fam  = body.get('virus_family', '')
            tier       = body.get('tier', 'moderate')
            limit      = min(int(body.get('limit', 50)), 200)

            # Strip FASTA header if present
            if mirna_seq.startswith('>'):
                mirna_seq = ''.join(l.strip() for l in mirna_seq.splitlines() if not l.startswith('>')).upper().replace('T','U')
            if virus_seq.startswith('>'):
                virus_seq = ''.join(l.strip() for l in virus_seq.splitlines() if not l.startswith('>')).upper().replace('T','U')

            if len(mirna_seq) < 15:
                self._json({"error": "miRNA sequence too short (min 15 nt)"}, status=400)
                return

            # If no virus sequence provided, fetch from DB.
            # Lookup order: annotated table by virus_id first, then fall back to
            # the accession index (predictions store GenBank accessions).
            if not virus_seq:
                row = self.db.execute(
                    "SELECT sequence, name, family FROM viruses WHERE virus_id=?",
                    (virus_id,)
                ).fetchone()
                if not row:
                    row = self.db.execute(
                        "SELECT sequence, name, family FROM viruses "
                        "WHERE accession=? OR accession LIKE ? LIMIT 1",
                        (virus_id, virus_id + '.%')
                    ).fetchone()
                if row:
                    virus_seq  = (row[0] or '').upper().replace('T','U')
                    if not virus_name or virus_name == virus_id:
                        virus_name = row[1] or virus_id
                    if not virus_fam:
                        virus_fam = row[2] or ''

            if len(virus_seq) < 20:
                self._json({
                    "error": "No virus sequence available for '%s'. "
                             "Please paste the virus genome sequence in the custom input box." % virus_id,
                    "no_sequence": True
                }, status=200)
                return

            hits = run_mirna_scan(mirna_id, mirna_seq, virus_id, virus_name, virus_fam,
                                  virus_seq, tier=tier, limit=limit)

            # Enrich with miRNA species info if ID found in DB
            species_name = ''
            row2 = self.db.execute(
                "SELECT species_name FROM mirnas WHERE mirna_id=?", (mirna_id,)
            ).fetchone()
            if row2:
                species_name = row2[0] or ''
            for h in hits:
                h['species_name'] = species_name
                h['_scan_mode'] = True
                # Scan mode runs ONLY the local SW-DP engine (the MFE/seed
                # numbers come from inline heuristics of that same engine) --
                # "3 algorithms" was a false claim (2026-10-03 fix).
                h['total_algorithms'] = 1

            # Enrich with gene annotations from virus_genes table
            # (table may be absent in slim/legacy DBs -> degrade gracefully
            #  instead of 500-ing the whole scan)
            try:
                genes = self.db.execute(
                    "SELECT gene, product, start, end FROM virus_genes WHERE virus_id=? ORDER BY start",
                    (virus_id,)
                ).fetchall()
            except Exception:
                genes = []
            if genes:
                for h in hits:
                    t_start = h.get('target_start', 0)
                    t_end = h.get('target_end', 0)
                    for g in genes:
                        if t_start <= g[3] and t_end >= g[2]:  # overlap
                            h['target_gene'] = g[0] or g[1] or 'CDS'
                            h['target_product'] = g[1] or g[0] or ''
                            break
                    if 'target_gene' not in h:
                        h['target_gene'] = 'Intergenic'
                        h['target_product'] = ''

            self._json({"total": len(hits), "results": hits, "scan_mode": True,
                        "virus_seq_len": len(virus_seq), "tier": tier})
        except Exception as e:
            self._json({"error": str(e)}, status=500)

    def _handle_search(self, q):
        filters = {}
        for k in ['mirna_id','virus_id','virus_family','plant_species','pos_match','pos_au','mirna_list']:
            if k in q: filters[k] = q[k]
        for k in ['max_energy','min_identity','min_query_cover','min_similarity']:
            if k in q:
                try: filters[k] = float(q[k])
                except: pass
        if 'query2' in q: filters['query2'] = True

        # Filter Tier presets — override individual thresholds when tier is set
        tier = q.get('tier', '').upper()
        if tier == 'STRICT':
            filters.setdefault('max_energy', -20.0)
            filters.setdefault('min_identity', 85.0)
            filters['max_mismatches'] = 1
        elif tier == 'MODERATE':
            filters.setdefault('max_energy', -15.0)
            filters.setdefault('min_identity', 75.0)
            filters['max_mismatches'] = 3
        elif tier == 'LOOSE':
            filters.setdefault('max_energy', -10.0)
            filters.setdefault('min_identity', 60.0)
            filters['max_mismatches'] = 5

        # Seed-only filter
        if q.get('seed_only') == '1':
            filters['seed_perfect'] = 1

        try:
            results = search(self.db, **filters)
        except Exception as e:
            self._json({"error": str(e), "total": 0, "results": []}, status=500)
            return
        total = len(results)
        try: off = int(q.get('offset',0))
        except: off = 0
        try: lim = int(q.get('limit',100))
        except: lim = 100
        self._json({"total":total,"offset":off,"limit":lim,"results":results[off:off+lim]})
    
    def _csv_export(self):
        import io, csv
        rows = search(self.db, limit=10000)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["mirna_id","species","virus_name","virus_family","energy","num_mismatches","seed_perfect","identity"])
        for r in rows:
            w.writerow([r.get("mirna_id",""), r.get("species_name",""), r.get("virus_name",""),
                       r.get("virus_family",""), r.get("energy",""), r.get("num_mismatches",""),
                       r.get("seed_perfect",""), r.get("identity","")])
        body = buf.getvalue().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","text/csv; charset=utf-8")
        self.send_header("Content-Disposition","attachment; filename=pamirdb_predictions.csv")
        self.send_header("Content-Length",len(body))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',len(body))
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(body)
    
    def _serve_html(self, html):
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def _build_index(self):
        return """<html><head><meta charset="UTF-8"><title>PAmiRDB v2</title></head>
<body><h1>PAmiRDB v2</h1><p>Server running. API at <a href="/api/stats">/api/stats</a></p></body></html>"""
    
    def log_message(self, format, *args):
        pass  # quiet


def main(port=8000):
    print("="*60)
    print("  PAmiRDB v2 Server")
    print("="*60)
    print("  Initializing database...")
    db = init_db()
    PAmiRDBHandler.db = db
    stats = get_stats(db)
    print(f"  miRNAs: {stats['total_mirnas']}  Viruses: {stats['total_viruses']}  Predictions: {stats['total_predictions']}")
    print(f"  Open: http://localhost:{port}")
    print("="*60)
    HTTPServer(('0.0.0.0', port), PAmiRDBHandler).serve_forever()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    main(port)
