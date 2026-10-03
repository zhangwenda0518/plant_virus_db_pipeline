"""
PAmiRDB v2 Web Server -- Enhanced with position constraints, Query2, browse pages.
Pure Python stdlib. Based on Satish et al. (2019) Sci Rep 9:4627.
"""
import json, sqlite3, sys, os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "pamirdb.sqlite"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"
MIRNA_FILE = DATA_DIR / "mirna" / "plant_mirnas.json"
VIRUS_FILE = DATA_DIR / "virus_genomes" / "viruses.json"
VIRUS_FASTA = DATA_DIR / "virus_genomes" / "viruses.fasta"
VIRUS_HOST_FILE = DATA_DIR / "virus_host" / "virus_host.csv"
VIRUS_GENES_FILE = Path(__file__).parent.parent / "scripts" / "virus_genes.py"

# ── Database ───────────────────────────────────────────────────────

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
            family TEXT, genome_length INTEGER, sequence TEXT
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
            db.execute("INSERT INTO viruses (virus_id,accession,name,family,genome_length,sequence) VALUES (?,?,?,?,?,?)",
                (vid, info.get('accession',''), info.get('name',''),
                 info.get('family',''), info.get('genome_length',0), seqs.get(vid,'')))
    
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
                 p['target_start'], p['target_end'], p['score'], p['energy'],
                 p['num_mismatches'], p['num_gaps'], int(p['seed_perfect']),
                 p['query_cover'], p['identity'],
                 p.get('similarity', 0), p.get('query_start', 1),
                 p.get('query_end', 0), p.get('alignment_length', 0),
                 p.get('target_protein', ''), p.get('matching_status', ''),
                 p['alignment']))
    
    db.commit()
    return db


# ── Query engine (enhanced) ────────────────────────────────────────

COLS = ['mirna_id','mirna_seq','species_name','virus_id','virus_name',
        'virus_family','target_start','target_end','score','energy',
        'num_mismatches','num_gaps','seed_perfect','query_cover','identity',
        'similarity','query_start','query_end','alignment_length',
        'target_protein','matching_status','alignment']


def search(db, **filters):
    sql = """SELECT p.mirna_id, m.sequence, m.species_name,
                    p.virus_id, v.name, v.family,
                    p.target_start, p.target_end, p.score, p.energy,
                    p.num_mismatches, p.num_gaps, p.seed_perfect,
                    p.query_cover, p.identity,
                    p.similarity, p.query_start, p.query_end,
                    p.alignment_length, p.target_protein, p.matching_status,
                    p.alignment
             FROM predictions p
             JOIN mirnas m ON p.mirna_id=m.mirna_id
             JOIN viruses v ON p.virus_id=v.virus_id WHERE 1=1"""
    params = []
    
    col_map = {'mirna_id':'p.mirna_id','virus_id':'p.virus_id',
               'virus_family':'v.family','plant_species':'m.species_code'}
    for k in ['mirna_id','virus_id','virus_family','plant_species']:
        if k in filters:
            sql += f" AND {col_map[k]}=?"
            params.append(filters[k])
    
    for k in ['max_energy','min_identity','min_query_cover','min_similarity']:
        if k in filters:
            col = k.replace('max_','').replace('min_','')
            sql += f" AND p.{col} {'<=' if k.startswith('max') else '>='} ?"
            params.append(filters[k])
    
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
        sql += " AND p.seed_perfect=1 AND p.num_mismatches<=2 AND p.alignment_length>=18 AND p.identity>80"
    
    sql += " ORDER BY p.energy ASC"
    
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


def get_stats(db):
    n_m = db.execute("SELECT COUNT(*) FROM mirnas").fetchone()[0]
    n_v = db.execute("SELECT COUNT(*) FROM viruses").fetchone()[0]
    n_p = db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    species = dict(db.execute("SELECT species_name,COUNT(*) FROM mirnas GROUP BY species_name").fetchall())
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


def get_viruses(db, family=None):
    sql = "SELECT virus_id,accession,name,family,genome_length FROM viruses"
    params = []
    if family: sql += " WHERE family=?"; params.append(family)
    rows = db.execute(sql, params).fetchall()
    return [{"virus_id":r[0],"accession":r[1],"name":r[2],"family":r[3],"genome_length":r[4]} for r in rows]


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

INDEX_HTML = open(Path(__file__).parent / "index.html", encoding='utf-8').read() if (Path(__file__).parent / "index.html").exists() else ""


# ── HTTP Handler ───────────────────────────────────────────────────

class PAmiRDBHandler(BaseHTTPRequestHandler):
    db = None
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # Strip /pamirdb prefix for reverse proxy deployment
        if path.startswith('/pamirdb'):
            path = path[7:] or '/'  # len('/pamirdb') = 7
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        
        if path == '/' or path == '/index.html':
            self._serve_html(INDEX_HTML if INDEX_HTML else self._build_index())
        elif path == '/api/stats':
            self._json(get_stats(self.db))
        elif path == '/api/mirnas':
            self._json({"mirnas": get_mirnas(self.db, q.get('species'))})
        elif path == '/api/viruses':
            self._json({"viruses": get_viruses(self.db, q.get('family'))})
        elif path == '/api/virus-hosts':
            hosts = get_virus_hosts(self.db, q.get('virus_id'))
            self._json({"total": len(hosts), "hosts": hosts})
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
    
    def _handle_search(self, q):
        filters = {}
        for k in ['mirna_id','virus_id','virus_family','plant_species','pos_match','pos_au','mirna_list']:
            if k in q: filters[k] = q[k]
        for k in ['max_energy','min_identity','min_query_cover','min_similarity']:
            if k in q:
                try: filters[k] = float(q[k])
                except: pass
        if 'query2' in q: filters['query2'] = True
        
        results = search(self.db, **filters)
        total = len(results)
        try: off = int(q.get('offset',0))
        except: off = 0
        try: lim = int(q.get('limit',100))
        except: lim = 100
        self._json({"total":total,"offset":off,"limit":lim,"results":results[off:off+lim]})
    
    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
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
