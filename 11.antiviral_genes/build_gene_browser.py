"""
Gene Browser — tab-based: NLR | sRNA | Domain Architectures | Downloads
"""
import json, os

OUTDIR = os.path.dirname(__file__) + "/data"
OUTHTML = os.path.dirname(__file__) + "/gene_browser.html"

# Load RefPlantNLR data directly
refplant_file = os.path.join(OUTDIR, "refplant_nlr_data.json")
if os.path.exists(refplant_file):
    with open(refplant_file, encoding="utf-8") as f:
        rp_data = json.load(f)
    nlr = rp_data["genes"]

    # Merge GFF3 domain annotations
    domains_file = os.path.join(OUTDIR, "refplant_domains.json")
    if os.path.exists(domains_file):
        with open(domains_file, encoding="utf-8") as f:
            gene_domains = json.load(f)
        for g in nlr:
            gid = g['gene_id']
            gid_alt = gid.replace('^Col-0','').replace('^Ler','')
            if gid in gene_domains:
                g['domains'] = gene_domains[gid]
            elif gid_alt in gene_domains:
                g['domains'] = gene_domains[gid_alt]
else:
    with open(os.path.join(OUTDIR, "all_genes_classified.json"), encoding="utf-8") as f:
        all_data = json.load(f)
    nlr = all_data["nlr"]
# Load antiviral NLR validated data
antiviral_nlr_file = os.path.join(OUTDIR, "antiviral_nlr_validated.json")
antiviral_nlr = {"total": 0, "genes": []}
if os.path.exists(antiviral_nlr_file):
    with open(antiviral_nlr_file, encoding="utf-8") as f:
        antiviral_nlr = json.load(f)


with open(os.path.join(OUTDIR, "all_genes_classified.json"), encoding="utf-8") as f:
    all_data = json.load(f)
srna = all_data["srna"]

DOMAIN_ARCH = {
    "TNL": ("TIR-NBS-LRR","#e41a1c",[("TIR","PF01582",2,15,"#e41a1c"),("NB-ARC","PF00931",20,40,"#4daf4a"),("LRR","PF13855",48,95,"#377eb8")]),
    "CNL": ("CC-NBS-LRR","#ff7f00",[("CC","PF18052",2,15,"#ff7f00"),("NB-ARC","PF00931",20,40,"#4daf4a"),("LRR","PF13855",48,95,"#377eb8")]),
    "RNL": ("RPW8-NBS-LRR","#984ea3",[("RPW8","PF05659",2,18,"#984ea3"),("NB-ARC","PF00931",22,42,"#4daf4a"),("LRR","PF13855",50,95,"#377eb8")]),
    "NL":  ("NBS-LRR","#4daf4a",[("NB-ARC","PF00931",5,35,"#4daf4a"),("LRR","PF13855",40,95,"#377eb8")]),
    "AGO": ("Argonaute","#fb8072",[("N-term","PF16486",2,15,"#8dd3c7"),("PAZ","PF02170",18,30,"#ffffb3"),("MID","PF16488",35,48,"#bebada"),("PIWI","PF02171",55,95,"#fb8072")]),
    "DCL": ("Dicer-like","#80b1d3",[("DExD","PF00270",2,14,"#80b1d3"),("HELICc","PF00271",17,26,"#fdb462"),("Dimer","PF03368",28,34,"#b3de69"),("PAZ","PF02170",38,46,"#ffffb3"),("RNaseIIIa","PF00636",55,65,"#fccde5"),("RNaseIIIb","PF00636",70,80,"#fccde5"),("dsRBD","PF00035",85,95,"#d9d9d9")]),
    "RDR": ("RdRP","#8dd3c7",[("RdRP","PF05183",5,95,"#8dd3c7")]),
    "DRB": ("dsRNA-binding","#d9d9d9",[("dsRBD1","PF00035",5,20,"#d9d9d9"),("dsRBD2","PF00035",30,45,"#d9d9d9"),("dsRBD3","PF00035",55,70,"#d9d9d9"),("dsRBD4","PF00035",78,93,"#d9d9d9")]),
    "SGS3":("SGS3","#bebada",[("XS","PF16566",2,30,"#8dd3c7"),("CC","-",40,60,"#bebada"),("C-term","-",65,95,"#fb8072")]),
    "HEN1":("HEN1","#fdb462",[("Methyltr.","PF13529",5,40,"#8dd3c7"),("dsRBD","PF00035",55,70,"#d9d9d9"),("PUA","PF01472",78,95,"#fdb462")]),
    # UPS families
    "E1_UPS":("Ubiquitin-Activating E1","#1b9e77",[("UBA_E1","PF10585",5,40,"#1b9e77"),("E1_UFD","PF09358",50,90,"#66c2a5")]),
    "E2_UPS":("Ubiquitin-Conjugating E2","#d95f02",[("UQ_con","PF00179",5,95,"#d95f02")]),
    "E3_RING":("RING Finger E3 Ligase","#7570b3",[("zf-C3HC4","PF00097",10,30,"#7570b3"),("Substrate-recog.", "-",40,90,"#8da0cb")]),
    "E3_HECT":("HECT E3 Ligase","#e7298a",[("HECT","PF00632",30,95,"#e7298a")]),
    "E3_Ubox":("U-box E3 Ligase","#66a61e",[("Ubox","PF04564",10,35,"#66a61e"),("ARM repeat","-",45,90,"#a6d854")]),
    "Fbox_UPS":("F-box Substrate Receptor","#e6ab02",[("F-box","PF00646",2,20,"#e6ab02"),("Interaction domain","-",35,95,"#fee090")]),
    "BTB_UPS":("BTB/POZ Adaptor","#a6761d",[("BTB","PF00651",5,25,"#a6761d"),("BACK","PF07707",40,55,"#caa057"),("KELCH","PF01344",60,95,"#dfc27d")]),
    "Cullin_UPS":("Cullin Scaffold","#666666",[("Cullin","PF00888",5,55,"#666666"),("Cullin_Nedd8","PF10557",70,95,"#999999")]),
    "Proteasome":("20S/26S Proteasome","#e41a1c",[("Proteasome","PF00227",3,25,"#e41a1c"),("Proteasome","PF00227",35,55,"#f4a582"),("AAA_ATPase","PF00004",65,95,"#92c5de")]),
    # miRNA biogenesis
    "miRNA":("miRNA Biogenesis","#984ea3",[("DCL1","-",2,18,"#80b1d3"),("HYL1","-",22,38,"#d9d9d9"),("SE","-",42,55,"#bebada"),("HEN1","-",60,75,"#fdb462"),("AGO1","-",80,95,"#fb8072")]),
}

# ---- Build gene data JS ----
from collections import Counter
import json as jmod
ups_data = all_data.get("ups", [])
mirna_data_js = all_data.get("mirna", [])
# Load embedded vsiRNA data
vsirna_json_str = '{"rows":[],"total":0,"species":[],"viruses":[]}'
vsirna_embedded = os.path.join(OUTDIR, 'pvsirnadb_embedded.json')
if os.path.exists(vsirna_embedded):
    with open(vsirna_embedded, encoding='utf-8') as fh:
        vsirna_json_str = fh.read().strip()

# ---- Load miRNA/vsiRNA stats from generated data (single source of truth) ----
mirna_stats = {}
_mirna_stats_file = os.path.join(OUTDIR, "miRNA_final_stats.json")
if os.path.exists(_mirna_stats_file):
    with open(_mirna_stats_file, encoding="utf-8") as fh:
        mirna_stats = json.load(fh)
MIRNA_TOTAL = mirna_stats.get("total_miRNAs", 0)
MIRNA_SPECIES = mirna_stats.get("total_species", 0)

def _count_vsirna_tsv():
    """Row/plant/virus counts + size measured from the cleaned PVsiRNAdb TSV."""
    path = os.path.join(OUTDIR, "pvsirnadb_vsirna.tsv")
    n = 0
    plants, ventries, indiv = set(), set(), set()
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            fh.readline()
            for line in fh:
                cols = line.rstrip("\n\r").split("\t")
                if len(cols) != 8 or not cols[0].strip():
                    continue
                n += 1
                plants.add(cols[2].strip())
                ventries.add(cols[3].strip())
                for v in cols[3].split("+"):   # mixtures like "MCMV+SCMV"
                    indiv.add(v.strip())
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return n, len(plants), len(ventries), len(indiv), size

VSIRNA_N, VSIRNA_PLANTS, VSIRNA_VENTRIES, VSIRNA_VIRUSES, VSIRNA_SIZE = _count_vsirna_tsv()
VSIRNA_MB = f"{VSIRNA_SIZE/1024/1024:.1f} MB"

def write_gene_data_js(outdir, updates):
    """Merge var declarations into data/gene_data.js.

    Reads the existing file first and keeps any variables written by other
    scripts (add_nlr_virus.py / archive/fix_nlr_ids.py) plus declaration order,
    so running those scripts after this builder no longer drops variables
    (previously: this script wrote 5 vars, the others rewrote only 4)."""
    import re
    path = os.path.join(outdir, "gene_data.js")
    existing, order = {}, []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r'^var\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*);\s*$', line)
                if m:
                    if m.group(1) not in existing:
                        order.append(m.group(1))
                    existing[m.group(1)] = m.group(2)
    for name, value in updates.items():
        if name not in existing:
            order.append(name)
        existing[name] = value
    with open(path, "w", encoding="utf-8") as fh:
        for name in order:
            fh.write("var " + name + " = " + existing[name] + ";\n")

write_gene_data_js(OUTDIR, {
    "NLR_DATA": json.dumps(nlr, ensure_ascii=False),
    "SRNA_DATA": json.dumps(srna, ensure_ascii=False),
    "UPS_DATA": json.dumps(ups_data, ensure_ascii=False),
    "MIRNA_DATA": json.dumps(mirna_data_js, ensure_ascii=False),
    "ANTIVIRAL_NLR_DATA": json.dumps(antiviral_nlr["genes"], ensure_ascii=False),
})

# ---- Build HTML ----
H = []

H.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Plant Immune & sRNA Gene Atlas</title>
<style>
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;background:#f0f2f5;color:#333}
nav{background:#1a3a5c;color:#fff;padding:0 20px;display:flex;align-items:center;height:48px;position:sticky;top:0;z-index:10}
nav a{color:rgba(255,255,255,.75);text-decoration:none;padding:10px 14px;font-size:13px}
nav a:hover,nav a.on{color:#fff;background:rgba(255,255,255,.12)}
nav span{font-weight:700;font-size:14px;margin-right:12px}
.wrap{max-width:1500px;margin:0 auto;padding:14px}
.tabs{display:flex;gap:4px;margin-bottom:0}
.tab{padding:8px 18px;border:none;border-radius:6px 6px 0 0;font-size:13px;cursor:pointer;background:#dde;color:#555}
.tab.on{background:#1a3a5c;color:#fff}
.panel{background:#fff;border-radius:0 0 8px 8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06);display:none}
.panel.on{display:block}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin-bottom:16px}
.card{background:#f8f9fa;padding:10px;border-radius:6px;text-align:center;cursor:pointer;transition:all .12s;border:2px solid transparent}
.card:hover{transform:translateY(-1px);box-shadow:0 3px 8px rgba(0,0,0,.10)}
.card.sel{border-color:#1a3a5c;background:#eaf0f6}
.card .v{font-size:18px;font-weight:700;color:#1a3a5c}
.card .l{font-size:10px;color:#888;margin-top:2px}
.filt-row{display:flex;gap:8px;margin:10px 0;flex-wrap:wrap;align-items:center}
.filt-row input,.filt-row select{padding:6px 10px;border:1px solid #ccc;border-radius:5px;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:#f0f3f5;padding:6px 8px;text-align:left;border-bottom:2px solid #ccc;position:sticky;top:0}
td{padding:4px 8px;border-bottom:1px solid #f0f0f0}
tr:hover td{background:#f8faff}
a{color:#1a3a5c;text-decoration:none}a:hover{text-decoration:underline}
.badge{display:inline-block;padding:1px 6px;border-radius:8px;font-size:9px;color:#fff}
.badge.AGO{background:#fb8072}.badge.DCL{background:#80b1d3}.badge.RDR{background:#8dd3c7}
.badge.DRB{background:#999}.badge.SGS3{background:#bebada}.badge.HEN1{background:#fdb462}
.badge.TNL{background:#e41a1c}.badge.CNL{background:#ff7f00}.badge.RNL{background:#984ea3}.badge.NLR{background:#4daf4a}.badge.R-gene{background:#ff7f00}.badge.Other{background:#999}
.badge.V{background:#27ae60}.badge.P{background:#e67e22}
.species-tag{color:#1a3a5c;font-style:italic;font-size:10px}
.dom-card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px;margin:8px 0}
.dom-bar{position:relative;height:22px;background:#f0f0f0;border-radius:3px;margin:6px 0}
.dom-bar .seg{position:absolute;height:100%;border-radius:2px;display:flex;align-items:center;justify-content:center;font-size:8px;overflow:hidden}
.dom-bar .seg:hover{filter:brightness(0.85)}
.dom-legend{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0;font-size:9px}
.dom-legend span{padding:1px 5px;border-radius:3px}
.dl-item{display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px dotted #eee;font-size:12px}
.dl-btn{display:inline-block;padding:4px 12px;background:#1a3a5c;color:#fff;border-radius:4px;font-size:11px;text-decoration:none}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.stat-box{background:#f8f9fa;border-radius:6px;padding:10px}
.stat-box h5{font-size:11px;color:#1a3a5c;margin:0 0 6px}
.stat-bar{display:flex;align-items:center;gap:6px;margin:2px 0;font-size:10px}
.stat-bar .label{min-width:90px;text-align:right;color:#555;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stat-bar .bar{height:14px;background:#1a3a5c;border-radius:3px;min-width:2px;transition:width .3s}
.stat-bar .cnt{min-width:35px;font-size:9px;color:#888}
.dl-btn:hover{background:#2a5a7c}.btn-act{padding:3px 10px;border:1px solid #ccc;border-radius:3px;background:#fff;cursor:pointer;font-size:11px;margin:0 2px}.btn-act:hover{background:#f0f0f0}
.count-info{font-size:11px;color:#888;margin-left:auto}
</style>
</head>
<body>
<nav>
  <a href="/" style="font-weight:700;font-size:14px;color:#fff;text-decoration:none;margin-right:12px">Plant Virus DB</a>
  <a href="/genes/">Dashboard</a>
  <a href="#nlr" onclick="showPanel('nlr')" id="navNLR">NLR</a>
  <a href="#srna" onclick="showPanel('srna')" id="navSRNA">sRNA</a>
  <a href="#ups" onclick="showPanel('ups')" id="navUPS">UPS</a>
  <a href="#mirna" onclick="showPanel('mirna')" id="navMIRNA">miRNA</a>
  <a href="#downloads" onclick="showPanel('downloads')" id="navDL">Downloads</a>
</nav>
<div class="wrap">
""")

# Load references
import json
ref_file = os.path.join(OUTDIR, "gene_references.json")
refs_data = {}
if os.path.exists(ref_file):
    with open(ref_file, encoding="utf-8") as fh:
        refs_list = json.load(fh)
    for r in refs_list:
        refs_data.setdefault(r["category"], []).append(r)

def render_refs(categories, out):
    """Append reference HTML for given categories to out list."""
    out.append('<details style="margin-top:16px"><summary style="cursor:pointer;font-size:12px;color:#1a3a5c;font-weight:600">Validating References</summary>')
    for cat in categories:
        if cat not in refs_data: continue
        out.append('<h4 style="margin:12px 0 6px;color:#555;font-size:11px">' + cat + '</h4>')
        for r in refs_data[cat]:
            pmid = r.get("pmid","")
            doi = r.get("doi","")
            pmid_str = ' <a href="https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/" target=_blank style="font-size:10px">PMID:' + pmid + '</a>' if pmid else ''
            doi_str = ' <a href="https://doi.org/' + doi + '" target=_blank style="font-size:10px">DOI</a>' if doi else ''
            out.append('<div style="padding:4px 0;border-bottom:1px dotted #eee">')
            out.append('<div style="font-size:12px;font-weight:600"><a href="' + r["url"] + '" target=_blank>' + r["title"] + '</a></div>')
            out.append('<div style="font-size:10px;color:#666;margin:1px 0">' + r["authors"] + ' - <i>' + r["journal"] + '</i> (' + r["year"] + ')' + pmid_str + doi_str + '</div>')
            out.append('<div style="font-size:10px;color:#888">' + r["desc"] + '</div>')
            out.append('</div>')
    out.append('</details>')

# ========================
# PANEL 1: NLR
# ========================
nlr_dt = Counter(g["domain_type"] for g in nlr)
nlr_sp = Counter(g.get("species","Unknown") for g in nlr)
nlr_val = Counter(g.get("validated","V") for g in nlr)

def make_stats(dt_counter, sp_counter, val_counter, max_bars=8, show_validation=True):
    """Generate HTML stat bars for species distribution and domain types."""
    out = []
    out.append('<div class="stats-grid">')
    # Domain type distribution
    out.append('<div class="stat-box"><h5>Domain Types</h5>')
    total = sum(dt_counter.values())
    for dt, cnt in dt_counter.most_common(8):
        pct = cnt/total*100 if total else 0
        out.append(f'<div class="stat-bar"><span class="label">{dt}</span><span class="bar" style="width:{pct}%"></span><span class="cnt">{cnt} ({pct:.0f}%)</span></div>')
    out.append('</div>')
    # Top species
    out.append('<div class="stat-box"><h5>Top Species</h5>')
    total = sum(sp_counter.values())
    for sp, cnt in sp_counter.most_common(max_bars):
        pct = cnt/total*100 if total else 0
        sp_short = sp[:35] if len(sp)>35 else sp
        out.append(f'<div class="stat-bar"><span class="label" title="{sp}">{sp_short}</span><span class="bar" style="width:{pct}%;background:#e74c3c"></span><span class="cnt">{cnt}</span></div>')
    out.append('</div>')
    # NCBI RefSeq/validated-flag status (V = NCBI 收录标记; NOT experimental validation)
    if show_validation:
        out.append('<div class="stat-box"><h5>NCBI 收录状态 (V marker)</h5>')
        vc = val_counter.get('V',0)
        pc = val_counter.get('P',0)
        total = vc+pc
        if total:
            vp = vc/total*100
            pp = pc/total*100
            out.append(f'<div class="stat-bar"><span class="label">NCBI 收录 (V)</span><span class="bar" style="width:{vp}%;background:#27ae60"></span><span class="cnt">{vc} ({vp:.0f}%)</span></div>')
            out.append(f'<div class="stat-bar"><span class="label">Predicted (P)</span><span class="bar" style="width:{pp}%;background:#e67e22"></span><span class="cnt">{pc} ({pp:.0f}%)</span></div>')
        out.append('</div>')
    out.append('</div>')
    return out

# ========================
# PANEL 1: NLR
# ========================
H.append('<div id="pnlNLR" class="panel">')

# KPI cards
H.append('<div class="cards">')
for dt in ["CNL","TNL","NLR","RNL"]:
    cnt = nlr_dt.get(dt, 0)
    if not cnt: continue
    vc = sum(1 for g in nlr if g["domain_type"]==dt)
    H.append(f'<div class="card" id="card_{dt}" onclick="filterNLR(\'{dt}\')"><div class="v">{cnt}</div><div class="l">RefPlantNLR {dt}</div></div>')
H.append('</div>')

# RefPlantNLR Stats
from collections import Counter
nlr_dt = Counter(g["domain_type"] for g in nlr)
nlr_sp = Counter(g["host"] for g in nlr if g.get("host"))
H.append('<div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap">')
H.append(f'<div class="stat-box" style="flex:0 0 160px"><h5>RefPlantNLR</h5><div style="font-size:28px;font-weight:700;text-align:center;color:#1a3a5c;padding:8px">{len(nlr)}</div><div style="text-align:center;font-size:10px;color:#888">Validated NLRs<br>{len(nlr_sp)} species</div></div>')
H.append(f'<div class="stat-box" style="flex:1;min-width:220px"><h5>Domain Types</h5>')
for dt in ["CNL","TNL","NLR","RNL"]:
    cnt = nlr_dt.get(dt, 0)
    if cnt:
        pct = cnt/len(nlr)*100
        H.append(f'<div class="stat-bar"><span class="label">{dt}</span><span class="bar" style="width:{pct}%"></span><span class="cnt">{cnt} ({pct:.0f}%)</span></div>')
H.append('</div>')
H.append(f'<div class="stat-box" style="flex:1;min-width:220px"><h5>Top Species</h5>')
for sp, cnt in nlr_sp.most_common(8):
    pct = cnt/len(nlr)*100
    H.append(f'<div class="stat-bar"><span class="label" title="{sp}">{sp[:30]}</span><span class="bar" style="width:{pct}%;background:#e74c3c"></span><span class="cnt">{cnt}</span></div>')
H.append('</div></div>')

# NLR domain diagrams
H.append('<details open style="margin-bottom:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">Domain Architecture</summary>')
for fam in ["TNL","CNL","RNL","NL"]:
    arch = DOMAIN_ARCH.get(fam)
    if not arch: continue
    desc, color, domains = arch
    H.append(f'<div class="dom-card nlr-dom" id="dom_NLR_{fam}"><h4 style="margin:0 0 6px;font-size:13px">{fam} ({desc})</h4><div class="dom-bar">')
    for d in domains:
        name, pfam, s, e, c = d
        H.append(f'<div class="seg" style="left:{s}%;width:{e-s}%;background:{c}" title="{name} ({pfam})">{name}</div>')
    H.append('</div><div class="dom-legend">')
    for d in domains:
        name, pfam, s, e, c = d
        H.append(f'<span style="background:{c}">{name} ({pfam})</span>')
    H.append('</div></div>')
H.append('</details>')

# Antiviral NLR Validation Table
H.append('<details style="margin-top:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">Antiviral NLR Validation ({})</summary>'.format(antiviral_nlr["total"]))
H.append('<div class="filt-row">')
H.append('<select id="avNlrPlant" onchange="renderAntiviralNLR()"><option value="">All Plants</option></select>')
H.append('<select id="avNlrVirus" onchange="renderAntiviralNLR()"><option value="">All Viruses</option></select>')
H.append('<input id="avNlrQ" placeholder="Search gene..." oninput="renderAntiviralNLR()" style="width:160px">')
H.append('<span class="count-info" id="avNlrCount"></span>')
H.append('</div>')
H.append('<div style="max-height:50vh;overflow:auto">')
H.append('<table><thead><tr><th>NLR</th><th>Plant</th><th>NLR Type</th><th>Virus</th><th>Effector</th><th>Year</th><th>Reference</th></tr></thead>')
H.append('<tbody id="avNlrBody"></tbody></table></div>')
H.append('</details>')


# Table
H.append('<hr style="margin:16px 0 8px;border:none;border-top:2px solid #1a3a5c">')
H.append('<details open style="margin-top:8px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">RefPlantNLR — 415 Experimentally Validated NLRs</summary>')
H.append("""<div class="filt-row">
  <select id="nlrType" onchange="renderNLR()"><option value="">All NLR Types</option></select>
  <input id="nlrSp" placeholder="Species..." oninput="renderNLR()" style="width:160px">
  <input id="nlrQ" placeholder="Search gene ID..." oninput="renderNLR()" style="width:180px">
  <span class="count-info" id="nlrCount"></span>
</div>
<div style="max-height:60vh;overflow:auto">
<table><thead><tr><th>Gene ID</th><th>Structure</th><th>Species</th><th>Domains</th><th>Length</th><th>Type</th><th>GenPept</th><th>NCBI</th></tr></thead>
<tbody id="nlrBody"></tbody></table></div>
""")
H.append('</details>')
# NLR Resources table
H.append('<details open style="margin-top:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">NLR Resources & Tools</summary>')
H.append('<table style="font-size:12px;margin-top:8px"><thead><tr><th style="width:90px">Category</th><th>Resource</th><th>Description</th></tr></thead><tbody>')

# Database entries
dbs = [
    ('Database','PlantRG','http://plantrg.bio2db.com','Currently the most comprehensive RGA database; integrates 2.16M RGAs across 1062 species, with functional annotations, SSR markers, miRNA regulation & gene editing targets'),
    ('Database','PRGdb 4.0','https://prgdb.org/prgdb4/','Biotic stress resistance gene database; v4.0 contains 580K putative R genes from 182 genomes, plus disease transcriptome data for 5 major crops'),
    ('Database','PlantASRG','https://bioinfor.nefu.edu.cn/PlantASRG/','Abiotic stress resistance gene database; 208K candidate genes from 337 plant species for drought/salinity/cold stress, integrated with AlphaFold2 predicted structures'),
    ('Database','NLRscape','https://nlrscape.biochim.ro/','Plant NLR protein sequence & structure atlas; >80K NLR sequences from UniProt with interactive clustering, domain annotation & phylogenetic tools'),
    ('Database','RefPlantNLR','https://zenodo.org/records/3936022','Experimentally validated NLR reference set; 442 validated plant NLRs, gold standard for NLR classification, evolution & software benchmarking'),
    ('Database','PlantNLRatlas','https://zenodo.org/records/10354350','Multi-species NLR genome dataset; 68K full-length & partial NLR sequences from 100 high-quality plant genomes'),
]

# Software entries
tools = [
    ('Software','PRGminer','https://kaabil.net/prgminer/','Deep learning-based R gene prediction; classifies R genes into 8 functional categories. GitHub: <a href="https://github.com/usubioinfo/PRGminer" target=_blank>usubioinfo/PRGminer</a>'),
    ('Software','PlantDRPpred','https://webs.iiitd.edu.in/raghava/plantdrppred','Hybrid prediction platform combining BLAST alignment, motif search (MERCI) & ML models for plant resistance protein prediction and design'),
    ('Software','NLRSeek','https://github.com/Wang-Mengda/NLRSeek','Genome re-annotation pipeline for NLR mining; recovers mis-annotated NLRs in non-model species via de novo scanning'),
    ('Software','resistify','https://github.com/SwiftSeal/resistify','Lightweight CLI tool for rapid NLR identification and classification from input protein sequences'),
]

for cat, name, url, desc in dbs + tools:
    badge_color = '#1a3a5c' if cat == 'Database' else '#e74c3c'
    H.append(f'<tr><td><span style="background:{badge_color};color:#fff;padding:2px 8px;border-radius:3px;font-size:10px">{cat}</span></td><td style="white-space:nowrap"><a href="{url}" target=_blank>{name}</a></td><td style="color:#555;font-size:11px">{desc}</td></tr>')

H.append('</tbody></table></details>')


ref_lines = []
render_refs(["NLR","TNL","CNL"], ref_lines)
for line in ref_lines:
    H.append(line)
H.append('</div>')

# ========================
# PANEL 2: sRNA
# ========================
H.append('<div id="pnlSRNA" class="panel">')

H.append('<div class="cards">')
for fam in ["AGO","DCL","RDR","DRB","SGS3","HEN1"]:
    cnt = sum(1 for g in srna if g["family"]==fam)
    vc = sum(1 for g in srna if g["family"]==fam and g["validated"]=="V")
    H.append(f'<div class="card" id="card_{fam}" onclick="filterSRNA(\'{fam}\')"><div class="v">{cnt:,}</div><div class="l">sRNA {fam} ({vc:,} NCBI-V)</div></div>')
H.append('</div>')

# sRNA Stats
srna_fam = Counter(g["family"] for g in srna)
srna_sp = Counter(g.get("species","Unknown") for g in srna)
H.append('<div class="stats-grid">')
H.append('<div class="stat-box"><h5>sRNA Families</h5>')
for fam, cnt in srna_fam.most_common(6):
    pct = cnt/len(srna)*100
    H.append(f'<div class="stat-bar"><span class="label">{fam}</span><span class="bar" style="width:{pct}%;background:#377eb8"></span><span class="cnt">{cnt:,} ({pct:.0f}%)</span></div>')
H.append('</div>')
H.append('<div class="stat-box"><h5>Top Species</h5>')
for sp, cnt in srna_sp.most_common(8):
    pct = cnt/len(srna)*100
    H.append(f'<div class="stat-bar"><span class="label" title="{sp}">{sp[:30]}</span><span class="bar" style="width:{pct}%;background:#e74c3c"></span><span class="cnt">{cnt}</span></div>')
H.append('</div></div>')


# sRNA domain diagrams
H.append('<details open style="margin-bottom:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">Domain Architecture</summary>')
for fam in ["AGO","DCL","RDR","DRB","SGS3","HEN1"]:
    arch = DOMAIN_ARCH.get(fam)
    if not arch: continue
    desc, color, domains = arch
    H.append(f'<div class="dom-card srna-dom" id="dom_SRNA_{fam}"><h4 style="margin:0 0 6px;font-size:13px">{fam} ({desc})</h4><div class="dom-bar">')
    for d in domains:
        name, pfam, s, e, c = d
        H.append(f'<div class="seg" style="left:{s}%;width:{e-s}%;background:{c}" title="{name} ({pfam})">{name}</div>')
    H.append('</div><div class="dom-legend">')
    for d in domains:
        name, pfam, s, e, c = d
        H.append(f'<span style="background:{c}">{name} ({pfam})</span>')
    H.append('</div></div>')
H.append('</details>')

H.append("""<div class="filt-row">
  <select id="srnaType" onchange="renderSRNA()"><option value="">All sRNA families</option></select>
  <input id="srnaSp" placeholder="Species..." oninput="renderSRNA()" style="width:160px">
  <input id="srnaQ" placeholder="Search..." oninput="renderSRNA()" style="width:180px">
  <span class="count-info" id="srnaCount"></span>
</div>
<div style="max-height:60vh;overflow:auto">
<table><thead><tr><th>Gene ID</th><th>Symbol</th><th>Full Name</th><th>Species</th><th>Family</th><th>NCBI</th><th>CDD</th></tr></thead>
<tbody id="srnaBody"></tbody></table></div>
""")
ref_lines2 = []
render_refs(["sRNA","AGO","DCL","RDR","DRB","SGS3","HEN1"], ref_lines2)
for line in ref_lines2:
    H.append(line)
H.append('</div>')

# ========================
# ========================
# PANEL 3: UPS
# ========================
# Count proteins per family from FASTA files
ups_counts = {}
ups_fam_map = {'E1_UPS':'E1','E2_UPS':'E2','E3_RING':'E3_RING','E3_HECT':'E3_HECT',
               'E3_Ubox':'E3_Ubox','Fbox_UPS':'Fbox','BTB_UPS':'BTB','Cullin_UPS':'Cullin','Proteasome':'Proteasome'}
for fam_key, fam_name in ups_fam_map.items():
    pf = os.path.join(OUTDIR, f'protein_UPS_{fam_name}.fasta')
    if os.path.exists(pf):
        with open(pf) as fh:
            ups_counts[fam_name] = sum(1 for l in fh if l.startswith('>'))
    else:
        ups_counts[fam_name] = 0

ups_total = sum(ups_counts.values())

H.append('<div id="pnlUPS" class="panel">')


# Cards
H.append('<div class="cards">')
for fam_name in ['E1','E2','E3_RING','E3_HECT','E3_Ubox','Fbox','BTB','Cullin','Proteasome']:
    cnt = ups_counts.get(fam_name, 0)
    if cnt:
        H.append(f'<div class="card" style="cursor:default"><div class="v">{cnt:,}</div><div class="l">UPS {fam_name}</div></div>')
H.append('</div>')

# UPS Stats
ups_sp = Counter(g.get("species","Unknown") for g in all_data.get("ups",[]))
H.append('<div class="stats-grid">')
H.append('<div class="stat-box"><h5>UPS Families</h5>')
for fam_name in ['E1','E2','E3_RING','E3_HECT','E3_Ubox','Fbox','BTB','Cullin','Proteasome']:
    cnt = ups_counts.get(fam_name, 0)
    if cnt:
        pct = cnt/ups_total*100
        H.append(f'<div class="stat-bar"><span class="label">{fam_name}</span><span class="bar" style="width:{pct}%;background:#4daf4a"></span><span class="cnt">{cnt:,} ({pct:.0f}%)</span></div>')
H.append('</div>')
H.append('<div class="stat-box"><h5>Top Species</h5>')
for sp, cnt in ups_sp.most_common(8):
    pct = cnt/len(all_data.get("ups",[]))*100
    H.append(f'<div class="stat-bar"><span class="label" title="{sp}">{sp[:30]}</span><span class="bar" style="width:{pct}%;background:#e74c3c"></span><span class="cnt">{cnt}</span></div>')
H.append('</div></div>')


# Domain diagrams
H.append('<details open style="margin-bottom:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">Domain Architecture</summary>')
for fam_key, fam_name in ups_fam_map.items():
    arch = DOMAIN_ARCH.get(fam_key)
    if not arch: continue
    desc, color, domains = arch
    cnt = ups_counts.get(fam_name, 0)
    H.append(f'<div class="dom-card" id="dom_UPS_{fam_name}"><h4 style="margin:0 0 6px;font-size:13px">{fam_name} ({desc}) <span style="font-weight:400;font-size:10px;color:#888">({cnt} proteins)</span></h4><div class="dom-bar">')
    for d in domains:
        name, pfam, s, e, c = d
        H.append(f'<div class="seg" style="left:{s}%;width:{e-s}%;background:{c}" title="{name} ({pfam})">{name}</div>')
    H.append('</div><div class="dom-legend">')
    for d in domains:
        name, pfam, s, e, c = d
        H.append(f'<span style="background:{c}">{name} ({pfam})</span>')
    H.append('</div></div>')
H.append('</details>')

# UPS Gene Table
H.append('<details open style="margin-top:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">UPS Gene Table — 3,996 Genes</summary>')
H.append('<div class="filt-row">')
H.append('<select id="upsType" onchange="renderUPS()"><option value="">All UPS families</option></select>')
H.append('<input id="upsSp" placeholder="Species..." oninput="renderUPS()" style="width:160px">')
H.append('<input id="upsQ" placeholder="Search..." oninput="renderUPS()" style="width:180px">')
H.append('<span class="count-info" id="upsCount"></span>')
H.append('</div>')
H.append('<div style="max-height:50vh;overflow:auto">')
H.append('<table><thead><tr><th>Gene ID</th><th>Symbol</th><th>Full Name</th><th>Species</th><th>Family</th><th>NCBI</th><th>CDD</th></tr></thead>')
H.append('<tbody id="upsBody"></tbody></table></div>')
H.append('</details>')

# IPR table
ups_file = os.path.join(OUTDIR, "ups_references.json")
if os.path.exists(ups_file):
    with open(ups_file, encoding="utf-8") as fh:
        ups = json.load(fh)
    H.append('<details style="margin-bottom:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">IPR/Pfam Reference & NCBI Search Links</summary>')
    H.append('<table style="font-size:12px"><thead><tr><th>Family</th><th>IPR</th><th>Pfam</th><th>NCBI Gene</th><th>NCBI Protein</th></tr></thead><tbody>')
    for f in ups["families"]:
        H.append(f'<tr><td style="font-weight:600">{f["family"]}</td>')
        H.append(f'<td style="font-family:monospace;font-size:10px">{f["ipr"]}</td>')
        H.append(f'<td style="font-family:monospace;font-size:10px">{f["pfam"]}</td>')
        H.append(f'<td><a href="{f["ncbi_gene"]}" target=_blank style="padding:3px 8px;background:#1a3a5c;color:#fff;border-radius:4px;font-size:10px">Gene</a></td>')
        H.append(f'<td><a href="{f["ncbi_prot"]}" target=_blank style="padding:3px 8px;background:#e74c3c;color:#fff;border-radius:4px;font-size:10px">Protein</a></td></tr>')
    H.append('</tbody></table>')
    H.append('</details>')

    # References
    H.append('<details open style="margin-bottom:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">Key References</summary>')
    for r in ups["references"]:
        pmid_str = ' <a href="https://pubmed.ncbi.nlm.nih.gov/' + r.get("pmid","") + '/" target=_blank style="font-size:10px">PMID:' + r.get("pmid","") + '</a>' if r.get("pmid") else ''
        doi_str = ' <a href="https://doi.org/' + r.get("doi","") + '" target=_blank style="font-size:10px">DOI</a>' if r.get("doi") else ''
        H.append('<div style="padding:4px 0;border-bottom:1px dotted #eee">')
        H.append('<div style="font-size:12px;font-weight:600"><a href="' + r["url"] + '" target=_blank>' + r["title"] + '</a></div>')
        H.append('<div style="font-size:10px;color:#666">' + r["authors"] + ' - <i>' + r["journal"] + '</i> (' + r["year"] + ')' + pmid_str + doi_str + '</div>')
        H.append('<div style="font-size:10px;color:#888">' + r["desc"] + '</div>')
        H.append('</div>')
    H.append('</details>')

H.append('</div>')

# ========================
# PANEL: miRNA
# ========================
H.append('<div id="pnlMIRNA" class="panel">')

# miRNA data summary — TOP
H.append('<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">')
H.append(f'<div class="stat-box" style="flex:1;min-width:150px"><h5>miRNA Sequences</h5><div style="font-size:22px;font-weight:700;color:#1a3a5c;text-align:center">{MIRNA_TOTAL:,}</div><div style="text-align:center;font-size:10px;color:#888">plantrg + miRBase + NCBI<br>{MIRNA_SPECIES} plant species</div></div>')
H.append(f'<div class="stat-box" style="flex:1;min-width:150px"><h5>vsiRNA</h5><div style="font-size:22px;font-weight:700;color:#1a3a5c;text-align:center">{VSIRNA_N:,}</div><div style="text-align:center;font-size:10px;color:#888">PVsiRNAdb<br>{VSIRNA_PLANTS} plant species, {VSIRNA_VIRUSES} viruses</div></div>')
H.append('<div class="stat-box" style="flex:1;min-width:180px"><h5>Downloads</h5><div style="font-size:10px;padding:6px"><a href=\"data/pvsirnadb_vsirna.tsv\" download>pvsirnadb_vsirna.tsv</a> (' + VSIRNA_MB + ')<br><a href=\"data/miRBase_plant_mature.fa\" download>miRBase_mature.fa</a> (904 KB)<br><a href=\"data/plantrg_all_mirna_extended.fa\" download>miRNA_sequences.fa</a> (525 KB)<br><a href=\"data/miRBase_plant_hairpin.fa\" download>miRBase_hairpin.fa</a> (1.7 MB)</div></div>')
H.append('</div>')
# miRNA Stats
H.append('<div class="stats-grid">')
H.append('<div class="stat-box"><h5>miRNA Sources</h5>')
H.append('<div class="stat-bar"><span class="label">plantrg</span><span class="bar" style="width:60%;background:#377eb8"></span><span class="cnt">~60%</span></div>')
H.append('<div class="stat-bar"><span class="label">miRBase</span><span class="bar" style="width:30%;background:#4daf4a"></span><span class="cnt">~30%</span></div>')
H.append('<div class="stat-bar"><span class="label">NCBI</span><span class="bar" style="width:10%;background:#ff7f00"></span><span class="cnt">~10%</span></div>')
H.append('</div>')
H.append('<div class="stat-box"><h5>Summary</h5>')
H.append(f'<div style="font-size:11px;padding:4px 0"><b>{MIRNA_TOTAL:,}</b> miRNA sequences</div>')
H.append(f'<div style="font-size:11px;padding:2px 0"><b>{MIRNA_SPECIES}</b> plant species</div>')
H.append(f'<div style="font-size:11px;padding:2px 0"><b>{VSIRNA_N:,}</b> vsiRNA entries</div>')
H.append(f'<div style="font-size:11px;padding:2px 0"><b>{VSIRNA_PLANTS}</b> plant + <b>{VSIRNA_VIRUSES}</b> virus hosts</div>')
H.append('</div></div>')


# PVsiRNAdb vsiRNA table
H.append(f'<details open style="margin-bottom:12px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">Virus-derived siRNA (PVsiRNAdb — {VSIRNA_N:,} entries, {VSIRNA_PLANTS} plant species)</summary>')
H.append('<div class="filt-row">')
H.append('<select id="vsirSp" onchange="renderVsiRNA()"><option value="">All species</option></select>')
H.append('<select id="vsirVirus" onchange="renderVsiRNA()"><option value="">All viruses</option></select>')
H.append('<input id="vsirQ" placeholder="Search sequence..." oninput="renderVsiRNA()" style="width:180px">')
H.append('<span class="count-info" id="vsirCount"></span></div>')
H.append('<div style="max-height:45vh;overflow:auto"><table><thead><tr><th>PVsiRNA ID</th><th>Plant</th><th>Virus</th><th>Sequence</th><th>Tissue</th><th>PMID</th></tr></thead>')
H.append('<tbody id="vsirBody"></tbody></table></div>')
H.append(f'<p style="font-size:10px;color:#888;margin-top:4px">Top 1000 entries. <a href="data/pvsirnadb_vsirna.tsv" download>Download full TSV</a> ({VSIRNA_N:,} rows, {VSIRNA_MB})</p>')
H.append('</details>')

# References
H.append('<details style="margin-top:16px"><summary style="cursor:pointer;font-size:13px;color:#1a3a5c;font-weight:600">External Resources & References</summary>')
for r in [
    {'t':'plantrg — Plant Resistance Gene & miRNA Database','u':'http://plantrg.bio2db.com/mirna.html','d':'128,925 miRNA-target interactions across 780 plant species (local copy downloaded)','p':''},
    {'t':'miRBase — miRNA registry','u':'https://mirbase.org/','d':'The primary microRNA database — 48,885 total mature miRNAs','p':''},
    {'t':'PmiREN — Plant miRNA Encyclopedia','u':'https://pmiren.com/','d':'16,000+ miRNAs from 200+ plant species','p':''},
    {'t':'PAmiRDB — Plant anti-viral miRNA prediction (self-built)','u':'/pamirdb/','d':'1,706 miRNA-virus interactions — local prediction pipeline with seed pairing + MFE validation','p':'30874591'},
    {'t':'AntiVIRmiR — antiviral miRNA repository','u':'https://pubmed.ncbi.nlm.nih.gov/36159991/','d':'Server offline — experimentally validated antiviral miRNAs','p':'36159991'},
    {'t':'PVsiRNAdb — virus-derived siRNA database','u':'http://14.139.61.8/PVsiRNAdb/','d':f'{VSIRNA_N:,} vsiRNA entries — {VSIRNA_PLANTS} plant species, {VSIRNA_VENTRIES} virus entries ({VSIRNA_VIRUSES} viruses counting mixtures)','p':'30307523'},
]:
    pmid = ' <a href=\"https://pubmed.ncbi.nlm.nih.gov/'+r['p']+'/\" target=_blank style=\"font-size:10px\">PMID:'+r['p']+'</a>' if r['p'] else ''
    H.append('<div style="padding:3px 0;border-bottom:1px dotted #eee"><span style="font-size:11px;font-weight:600"><a href=\"'+r['u']+'\" target=_blank>'+r['t']+'</a></span>'+pmid+'<br><span style="font-size:10px;color:#888">'+r['d']+'</span></div>')
H.append('</details></div>')

# ========================
H.append('<div id="pnlDownloads" class="panel">')
groups = {
    "RefPlantNLR (Zenodo 3936022)": [
        "RefPlantNLR_Supplemental_dataset_1_RefPlantNLR_v.20200528_415_AA.fasta",
        "RefPlantNLR_Supplemental_dataset_2_RefPlantNLR_v.20200528_415_CDS.fasta",
        "RefPlantNLR_Supplemental_dataset_6_RefPlantNLR_v.20200528_415_SSF52540.fasta",
        "RefPlantNLR_Supplemental_dataset_7_RefPlantNLR_v.20200528_415_SSF52540_Unique.fasta",
        "RefPlantNLR_Supplemental_dataset_10_RefPlantNLR_v.20200528_415_Representative90.fasta",
        "RefPlantNLR_Supplemental_dataset_11_RefPlantNLR_v.20200528_415_Representative90_SSF52540.fasta",
    ],
    "NLR Gene Tables": ["NLR_all_genes.tsv"],
    "sRNA Proteins": ["protein_sRNA_AGO.fasta","protein_sRNA_DCL.fasta","protein_sRNA_RDR.fasta","protein_sRNA_DRB.fasta","protein_sRNA_SGS3.fasta","protein_sRNA_HEN1.fasta","protein_sRNA_other.fasta"],
    "sRNA mRNA Sequences": ["plant_sRNA_mRNA_all.fasta","plant_antiviral_expanded_mRNA.fasta","plant_antiviral_mRNA.fasta"],
    "UPS Proteins": ["protein_UPS_E1.fasta","protein_UPS_E2.fasta","protein_UPS_E3_RING.fasta","protein_UPS_E3_HECT.fasta","protein_UPS_E3_Ubox.fasta","protein_UPS_Fbox.fasta","protein_UPS_Cullin.fasta","protein_UPS_BTB.fasta","protein_UPS_Proteasome.fasta","plant_UPS_proteins.fasta"],
    "miRNA Sequences": ["miRBase_plant_mature.fa","miRBase_plant_hairpin.fa","plantrg_all_mirna.fa","miRNA_precursors.fasta"],
    "miRNA-Target Data": ["plantrg_mirna_targets.tsv","miRNA_genes.tsv"],
    "Gene Tables": ["sRNA_AGO_genes.tsv","sRNA_DCL_genes.tsv","sRNA_RDR_genes.tsv","sRNA_DRB_genes.tsv","sRNA_SGS3_genes.tsv","sRNA_HEN1_genes.tsv","UPS_all_genes.tsv","sRNA_all_genes.tsv"],
}

existing = set(os.listdir(OUTDIR))
for grp, files in groups.items():
    H.append(f'<h4 style="margin:14px 0 6px;color:#555">{grp}</h4>')
    for fname in files:
        if fname not in existing: continue
        fpath = os.path.join(OUTDIR, fname)
        size = os.path.getsize(fpath)
        sz = f'{size/1024/1024:.1f} MB' if size > 1024*1024 else f'{size/1024:.0f} KB'
        extra = ''
        if fname.endswith('.fasta'):
            with open(fpath) as fh:
                n = sum(1 for l in fh if l.startswith('>'))
            extra = f'{n:,} seqs'
        elif fname.endswith('.tsv'):
            try:
                with open(fpath, encoding='utf-8-sig') as fh:
                    n = sum(1 for _ in fh) - 1
                extra = f'{n:,} rows'
            except: pass
        H.append(f'<div class="dl-item"><span style="flex:1;font-family:monospace;font-size:11px">{fname}</span><span style="font-size:10px;color:#888;min-width:50px">{sz}</span><span style="font-size:10px;color:#888;min-width:70px">{extra}</span><a class="dl-btn" href="data/{fname}" download>Download</a></div>')
H.append('</div>')

# ========================
# ========================
# JS
# ========================
H.append("""
<script src="data/gene_data.js?v=3"></script>
""" + '<script>var VSIRNA_DATA = ' + vsirna_json_str + ';</script>' + """
<script>
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;');}
function ncbiUrl(id,upid){if(/^\\d+$/.test(id)||id.startsWith('LOC'))return'https://www.ncbi.nlm.nih.gov/gene/'+id;if(upid)return'https://www.uniprot.org/uniprot/'+upid;return'https://www.ncbi.nlm.nih.gov/gene/?term='+encodeURIComponent(id);}
function cddUrl(id){return 'https://www.ncbi.nlm.nih.gov/Structure/cdd/wrpsb.cgi?SEQUENCE='+id+'&INPUT_TYPE=live';}
function $(id){return document.getElementById(id);}

// Check hash for initial panel before anything renders
var hash = window.location.hash.replace('#','');
var currentPanel = (['nlr','srna','ups','mirna','downloads'].indexOf(hash) >= 0) ? hash : 'nlr';
// Set initial active panel immediately to avoid flash
(function(){
  var initId = currentPanel;
  var elId='pnl'+(initId==='downloads'?'Downloads':(initId==='mirna'?'MIRNA':initId.toUpperCase()));
  var navId='nav'+(initId==='downloads'?'DL':(initId==='mirna'?'MIRNA':initId.toUpperCase()));
  var allPanels = ['pnlNLR','pnlSRNA','pnlUPS','pnlMIRNA','pnlDownloads'];
  var allNavs = ['navNLR','navSRNA','navUPS','navMIRNA','navDL'];
  for(var i=0;i<allPanels.length;i++){
    var pe=document.getElementById(allPanels[i]);
    if(pe)pe.style.display = (allPanels[i]===elId?'block':'none');
    var ne=document.getElementById(allNavs[i]);
    if(ne)ne.className = (allNavs[i]===navId?'on':'');
  }
})();

function showPanel(id){
  if(currentPanel===id) return;
  currentPanel=id;
  ['nlr','srna','ups','mirna','downloads'].forEach(function(p){
    var elId='pnl'+(p==='downloads'?'Downloads':(p==='mirna'?'MIRNA':p.toUpperCase()));
    var el=$(elId); if(el)el.style.display=(p===id?'block':'none');
    var navId='nav'+(p==='downloads'?'DL':(p==='mirna'?'MIRNA':p.toUpperCase()));
    var nav=$(navId); if(nav)nav.className=(p===id?'on':'');
  });
  if(id==='nlr') renderNLR();
  if(id==='srna') renderSRNA();
}

// ---- NLR Table ----
function filterNLR(dt){
  if(currentPanel!=='nlr') showPanel('nlr');
  $('nlrType').value=dt||'';
  $('nlrSp').value=''; $('nlrQ').value='';
  renderNLR();
  document.querySelectorAll('#pnlNLR .card').forEach(function(c){c.classList.toggle('sel',c.id==='card_'+dt);});
  document.querySelectorAll('.nlr-dom').forEach(function(d){d.style.display='none';});
  if(!dt) document.querySelectorAll('.nlr-dom').forEach(function(d){d.style.display='block';});
  else {var dd=$('dom_NLR_'+dt);if(dd)dd.style.display='block';}
}

function renderNLR(pg){
  var dt=$('nlrType').value;
  var sp=($('nlrSp').value||'').toLowerCase(), q=($('nlrQ').value||'').toLowerCase();
  nlrRows=NLR_DATA.filter(function(g){
    if(dt && g.domain_type!==dt)return false;
    if(sp && (g.host||g.species||'').toLowerCase().indexOf(sp)<0)return false;
    if(q && (g.gene_id+' '+g.structure+' '+(g.host||g.species||'')).toLowerCase().indexOf(q)<0)return false;
    return true;
  });
  if(pg) nlrPage=pg; else nlrPage=1;
  var total=nlrRows.length, pages=Math.ceil(total/PAGE);
  var start=(nlrPage-1)*PAGE, end=start+PAGE;
  var pageRows=nlrRows.slice(start,end);
  $('nlrBody').innerHTML=pageRows.map(function(g){
    var gp = g.genpept||''; var locus = g.locus||'';
    var protLink = gp && gp!=='NA' ? 'https://www.ncbi.nlm.nih.gov/protein/'+gp : '';
    var geneLink = '';
    if(locus && locus.match(/^AT\\dG\\d+/)) geneLink = 'https://www.ncbi.nlm.nih.gov/gene/?term='+locus;
    else if(gp && gp!=='NA') geneLink = 'https://www.ncbi.nlm.nih.gov/protein/'+gp;
    var len = g.length_aa||'';
    var doms = (g.domains||[]).slice(0,5).join(', ');
    return'<tr><td><b>'+esc(g.gene_id)+'</b></td>'+
      '<td style=font-size:10px>'+esc(g.structure||'')+'</td>'+
      '<td class=species-tag>'+esc(g.host||g.species||'')+'</td>'+
      '<td style=font-size:9px;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap title=\"'+esc(doms)+'\">'+esc(doms)+'</td>'+
      '<td>'+esc(String(len))+' aa</td>'+
      '<td><span class=\"badge '+esc(g.domain_type||'')+'\">'+esc(g.domain_type||'')+'</span></td>'+
      '<td>'+(gp&&gp!=='NA'?'<a href=\"'+protLink+'\" target=_blank>'+esc(gp)+'</a>':'')+'</td>'+
      '<td>'+(geneLink?'<a href=\"'+geneLink+'\" target=_blank>NCBI</a>':'')+'</td></tr>';
  }).join('');
  var nav='<span style=font-size:11px>Page '+nlrPage+'/'+pages+' ('+total+' genes)</span> ';
  if(nlrPage>1) nav+='<button class=btn-act onclick=renderNLR('+(nlrPage-1)+')>Prev</button> ';
  if(nlrPage<pages) nav+='<button class=btn-act onclick=renderNLR('+(nlrPage+1)+')>Next</button>';
  $('nlrCount').innerHTML=nav;
}

// ---- sRNA Table ----
function filterSRNA(fam){
  if(currentPanel!=='srna') showPanel('srna');
  $('srnaType').value=fam||'';
  $('srnaSp').value=''; $('srnaQ').value='';
  renderSRNA();
  document.querySelectorAll('#pnlSRNA .card').forEach(function(c){c.classList.toggle('sel',c.id==='card_'+fam);});
  document.querySelectorAll('.srna-dom').forEach(function(d){d.style.display='none';});
  if(!fam) document.querySelectorAll('.srna-dom').forEach(function(d){d.style.display='block';});
  else {var dd=$('dom_SRNA_'+fam);if(dd)dd.style.display='block';}
}

var nlrPage=1, nlrRows=[], srnaPage=1, srnaRows=[], upsPage=1, upsRows=[], avNlrPage=1, avNlrRows=[], PAGE=50;

function renderSRNA(pg){
  var dt=$('srnaType').value;
  var sp=($('srnaSp').value||'').toLowerCase(), q=($('srnaQ').value||'').toLowerCase();
  srnaRows=SRNA_DATA.filter(function(g){
    if(dt && g.family!==dt)return false;
    
    if(sp && (g.species||'').toLowerCase().indexOf(sp)<0)return false;
    if(q && (g.gene_id+' '+g.symbol+' '+g.full_name+' '+g.species).toLowerCase().indexOf(q)<0)return false;
    return true;
  });
  if(pg) srnaPage=pg; else srnaPage=1;
  var total=srnaRows.length, pages=Math.ceil(total/PAGE);
  var start=(srnaPage-1)*PAGE, end=start+PAGE;
  var pageRows=srnaRows.slice(start,end);
  $('srnaBody').innerHTML=pageRows.map(function(g){
    return'<tr><td><a href=\"'+ncbiUrl(g.gene_id)+'\" target=_blank>'+esc(g.gene_id)+'</a></td>'+
      '<td><b>'+esc(g.symbol||'')+'</b></td>'+
      '<td style=max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap title=\"'+esc(g.full_name||'')+'\">'+esc((g.full_name||'').substring(0,80))+'</td>'+
      '<td class=species-tag>'+esc(g.species||'')+'</td>'+
      '<td><span class=\"badge '+esc(g.family||'')+'\">'+esc(g.family||'')+'</span></td>'+
      '<td><a href=\"'+ncbiUrl(g.gene_id,g.uniprot)+'\" target=_blank>'+(g.uniprot?'UniProt':'NCBI')+'</a></td>'+
      '<td><a href=\"'+cddUrl(g.gene_id)+'\" target=_blank>CDD</a></td></tr>';
  }).join('');
  var nav='<span style=font-size:11px>Page '+srnaPage+'/'+pages+' ('+total+' genes)</span> ';
  if(srnaPage>1) nav+='<button class=btn-act onclick=renderSRNA('+(srnaPage-1)+')>Prev</button> ';
  if(srnaPage<pages) nav+='<button class=btn-act onclick=renderSRNA('+(srnaPage+1)+')>Next</button>';
  $('srnaCount').innerHTML=nav;
}

// ---- UPS Table ----
function filterUPS(fam){
  showPanel('ups');
  $('upsType').value=fam||'';
  $('upsSp').value=''; $('upsQ').value='';
  renderUPS();
}

function renderUPS(pg){
  var dt=$('upsType').value;
  var sp=($('upsSp').value||'').toLowerCase(), q=($('upsQ').value||'').toLowerCase();
  upsRows=UPS_DATA.filter(function(g){
    if(dt && g.family!==dt)return false;
    if(sp && (g.species||'').toLowerCase().indexOf(sp)<0)return false;
    if(q && (g.gene_id+' '+g.symbol+' '+g.full_name+' '+g.species).toLowerCase().indexOf(q)<0)return false;
    return true;
  });
  if(pg) upsPage=pg; else upsPage=1;
  var total=upsRows.length, pages=Math.ceil(total/PAGE);
  var start=(upsPage-1)*PAGE, end=start+PAGE;
  var pageRows=upsRows.slice(start,end);
  $('upsBody').innerHTML=pageRows.map(function(g){
    return'<tr><td><a href="'+ncbiUrl(g.gene_id)+'" target=_blank>'+esc(g.gene_id)+'</a></td>'+
      '<td><b>'+esc(g.symbol||'')+'</b></td>'+
      '<td style=max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap title="'+esc(g.full_name||'')+'">'+esc((g.full_name||'').substring(0,70))+'</td>'+
      '<td class=species-tag>'+esc(g.species||'')+'</td>'+
      '<td><span class="badge '+esc(g.family||'')+'">'+esc(g.family||'')+'</span></td>'+
      '<td><a href="'+ncbiUrl(g.gene_id,g.uniprot)+'" target=_blank>'+(g.uniprot?'UniProt':'NCBI')+'</a></td>'+
      '<td><a href="'+cddUrl(g.gene_id)+'" target=_blank>CDD</a></td></tr>';
  }).join('');
  var nav='<span style=font-size:11px>Page '+upsPage+'/'+pages+' ('+total+' genes)</span> ';
  if(upsPage>1) nav+='<button class=btn-act onclick=renderUPS('+(upsPage-1)+')>Prev</button> ';
  if(upsPage<pages) nav+='<button class=btn-act onclick=renderUPS('+(upsPage+1)+')>Next</button>';
  $('upsCount').innerHTML=nav;
}

// ---- plantrg miRNA Table ----
function renderVsiRNA(){
  var sp = $('vsirSp').value, virus = $('vsirVirus').value, q = ($('vsirQ').value||'').toLowerCase();
  var rows = (typeof VSIRNA_DATA !== 'undefined' ? VSIRNA_DATA.rows : []).filter(function(r){
    if(sp && r.plant !== sp) return false;
    if(virus && r.virus !== virus) return false;
    if(q && r.seq.toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  $('vsirBody').innerHTML = rows.slice(0, 500).map(function(r){
    return '<tr><td>'+esc(r.id)+'</td>'+
      '<td class=species-tag>'+esc(r.plant)+'</td>'+
      '<td>'+esc(r.virus)+'</td>'+
      '<td style=\"font-family:monospace;font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">'+esc(r.seq)+'</td>'+
      '<td>'+esc(r.tissue)+'</td>'+
      '<td><a href=\"https://pubmed.ncbi.nlm.nih.gov/'+esc(r.pmid)+'/\" target=_blank>'+esc(r.pmid)+'</a></td></tr>';
  }).join('');
  var total = typeof VSIRNA_DATA !== 'undefined' ? VSIRNA_DATA.total : 0;
  $('vsirCount').textContent = 'Showing ' + Math.min(rows.length, 500) + ' of ' + total + ' entries';
}

// ---- Antiviral NLR Table ----
function renderAntiviralNLR(pg){
  var plant=$('avNlrPlant').value, virus=$('avNlrVirus').value;
  var q=($('avNlrQ').value||'').toLowerCase();
  avNlrRows=(typeof ANTIVIRAL_NLR_DATA!=='undefined'?ANTIVIRAL_NLR_DATA:[]).filter(function(g){
    if(plant && g.plant!==plant)return false;
    if(virus && g.virus!==virus)return false;
    if(q && (g.gene+' '+g.plant+' '+g.virus+' '+g.nlr_type).toLowerCase().indexOf(q)<0)return false;
    return true;
  });
  if(pg) avNlrPage=pg; else avNlrPage=1;
  var total=avNlrRows.length, pages=Math.ceil(total/PAGE);
  var start=(avNlrPage-1)*PAGE, end=start+PAGE;
  var pageRows=avNlrRows.slice(start,end);
  $('avNlrBody').innerHTML=pageRows.map(function(g){
    var doiHtml = g.doi ? ' <a href="'+g.doi+'" target=_blank style="font-size:9px">DOI</a>' : '';
    return'<tr><td><b>'+esc(g.gene)+'</b></td>'+
      '<td class=species-tag>'+esc(g.plant)+'</td>'+
      '<td style=font-size:10px>'+esc(g.nlr_type)+'</td>'+
      '<td>'+esc(g.virus)+'</td>'+
      '<td style=font-size:10px>'+esc(g.effector||'-')+'</td>'+
      '<td>'+esc(String(g.year))+'</td>'+
      '<td style=font-size:10px;max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap title="'+esc(g.reference||'')+'">'+esc((g.reference||'').substring(0,80))+doiHtml+'</td></tr>';
  }).join('');
  var nav='<span style=font-size:11px>Page '+avNlrPage+'/'+pages+' ('+total+' entries)</span> ';
  if(avNlrPage>1) nav+='<button class=btn-act onclick=renderAntiviralNLR('+(avNlrPage-1)+')>Prev</button> ';
  if(avNlrPage<pages) nav+='<button class=btn-act onclick=renderAntiviralNLR('+(avNlrPage+1)+')>Next</button>';
  $('avNlrCount').innerHTML=nav;
}

// Init dropdown options
(function(){
  ['CNL','TNL','NLR','RNL'].forEach(function(t){
    if(NLR_DATA.some(function(g){return g.domain_type===t;}))
      $('nlrType').innerHTML+='<option value=\"'+t+'\">'+t+'</option>';
  });
  ['AGO','DCL','RDR','DRB','SGS3','HEN1'].forEach(function(t){
    $('srnaType').innerHTML+='<option value=\"'+t+'\">'+t+'</option>';
  });
  ['E1','E2','E3_RING','E3_HECT','E3_Ubox','Fbox','BTB','Cullin','Proteasome'].forEach(function(t){
    $('upsType').innerHTML+='<option value=\"'+t+'\">'+t+'</option>';
  });
  if(typeof VSIRNA_DATA !== 'undefined'){
    VSIRNA_DATA.species.forEach(function(s){$('vsirSp').innerHTML+='<option value=\"'+s+'\">'+s+'</option>';});
    VSIRNA_DATA.viruses.forEach(function(v){$('vsirVirus').innerHTML+='<option value=\"'+v+'\">'+v+'</option>';});
    renderVsiRNA();
  }
  renderNLR();
  renderUPS();
  if(typeof ANTIVIRAL_NLR_DATA!=='undefined'){
    var avPlants=[...new Set(ANTIVIRAL_NLR_DATA.map(function(g){return g.plant;}))].sort();
    var avViruses=[...new Set(ANTIVIRAL_NLR_DATA.map(function(g){return g.virus;}))].sort();
    avPlants.forEach(function(s){$('avNlrPlant').innerHTML+='<option value=\"'+s+'\">'+s+'</option>';});
    avViruses.forEach(function(v){$('avNlrVirus').innerHTML+='<option value=\"'+v+'\">'+v+'</option>';});
    renderAntiviralNLR();
  }
})();
</script>
""")

H.append(f"""
<div style="text-align:center;padding:16px;color:#999;font-size:11px">
  Plant Immune & sRNA Gene Atlas — {len(nlr)+len(srna):,} genes (NLR: {len(nlr)}, sRNA: {len(srna):,})
</div>
</div>
</body>
</html>
""")

with open(OUTHTML, "w", encoding="utf-8") as f:
    f.write("\n".join(H))

print(f"Saved: {OUTHTML}")
print(f"Size: {os.path.getsize(OUTHTML)/1024:.0f} KB")
print(f"Genes: {len(nlr)} NLR + {len(srna):,} sRNA")
