"""
Build index.html homepage for the Plant Immune Gene Atlas.
Shows summary stats and jump-to links for NLR, sRNA, UPS.
"""
import json, os

OUTDIR = os.path.dirname(__file__) + "/data"
OUTHTML = os.path.dirname(__file__) + "/index.html"

# ---- Numbers loaded from generated data files (single source of truth) ----
def _load_stats(fname):
    p = os.path.join(OUTDIR, fname)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return {}

_mirna_stats = _load_stats("miRNA_final_stats.json")
MIRNA_TOTAL = _mirna_stats.get("total_miRNAs", 0)     # 83,166
MIRNA_SPECIES = _mirna_stats.get("total_species", 0)  # 799

def _count_vsirna_tsv():
    """Row/plant/virus counts measured from the cleaned PVsiRNAdb TSV."""
    path = os.path.join(OUTDIR, "pvsirnadb_vsirna.tsv")
    n = 0
    plants, indiv = set(), set()
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            fh.readline()
            for line in fh:
                cols = line.rstrip("\n\r").split("\t")
                if len(cols) != 8 or not cols[0].strip():
                    continue
                n += 1
                plants.add(cols[2].strip())
                for v in cols[3].split("+"):   # mixtures like "MCMV+SCMV"
                    indiv.add(v.strip())
    return n, len(plants), len(indiv)

VSIRNA_N, VSIRNA_PLANTS, VSIRNA_VIRUSES = _count_vsirna_tsv()

# Load data
with open(os.path.join(OUTDIR, "all_genes_classified.json"), encoding="utf-8") as f:
    data = json.load(f)

# Use RefPlantNLR data if available
refplant_file = os.path.join(OUTDIR, "refplant_nlr_data.json")
if os.path.exists(refplant_file):
    with open(refplant_file, encoding="utf-8") as f:
        rp = json.load(f)
    nlr = rp["genes"]
else:
    nlr = data.get("nlr", [])
srna = data.get("srna", [])
ups = data.get("ups", [])

# Stats
from collections import Counter
nlr_dt = Counter(g.get("domain_type","?") for g in nlr)
nlr_sp = Counter(g.get("host", g.get("species","?")) for g in nlr)
# RefPlantNLR curated set (all entries carry V = curated in the reference dataset)
nlr_v = sum(1 for g in nlr if g.get("validated")=="V")

srna_fam = Counter(g.get("family","?") for g in srna)
srna_sp = Counter(g.get("species","?") for g in srna)
# NCBI Gene 'V' status flag = NCBI-indexed record (NOT experimental validation)
srna_ncbi_v = sum(1 for g in srna if g.get("validated")=="V")

ups_fam = Counter(g.get("family","?") for g in ups)
ups_sp = Counter(g.get("species","?") for g in ups)
# NCBI Gene 'V' status flag = NCBI-indexed record (NOT experimental validation)
ups_ncbi_v = sum(1 for g in ups if g.get("validated")=="V")

# Count protein files
ups_prot = sum(1 for _ in open(os.path.join(OUTDIR,"plant_UPS_proteins.fasta")) if _.startswith(">")) if os.path.exists(os.path.join(OUTDIR,"plant_UPS_proteins.fasta")) else 0
srna_prot = sum(1 for _ in open(os.path.join(OUTDIR,"plant_sRNA_proteins.fasta")) if _.startswith(">")) if os.path.exists(os.path.join(OUTDIR,"plant_sRNA_proteins.fasta")) else 0

H = []

H.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Plant Immune Gene Atlas — Home</title>
<style>
/* module subnav (2026-10 统一: 全站导航由共享脚本注入) */
nav.pvdb-subnav{background:#fff;color:#2c3e50;display:flex;align-items:center;padding:0 24px;gap:2px;height:42px;border-bottom:1px solid #e3e8ee;position:sticky;top:46px;z-index:90;white-space:nowrap;overflow-x:auto;scrollbar-width:none}
nav.pvdb-subnav::-webkit-scrollbar{display:none}
nav.pvdb-subnav a{color:#4a5b6c;text-decoration:none;padding:4px 12px;font-size:12.5px;border-radius:4px;font-weight:600;flex-shrink:0}
nav.pvdb-subnav a:hover{background:#eef4f0;color:#2c6e49}
nav.pvdb-subnav a.on,nav.pvdb-subnav a.active{background:#2c6e49;color:#fff}

*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;background:#f0f2f5;color:#333}
.hero{background:linear-gradient(135deg,#1a3a5c,#2e7d6a);color:#fff;padding:40px 24px;text-align:center}
.hero h1{font-size:28px;margin:0 0 8px}.hero p{font-size:14px;opacity:.85;max-width:700px;margin:0 auto}
.wrap{max-width:1400px;margin:0 auto;padding:20px}
.big-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:20px 0}
.big-card{background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,.06);cursor:pointer;transition:all .2s;text-decoration:none;color:inherit;display:block}
.big-card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.12)}
.big-card .icon{font-size:32px;margin-bottom:8px}
.big-card h2{font-size:18px;margin:0 0 6px;color:#1a3a5c}
.big-card .desc{font-size:12px;color:#888;margin-bottom:12px}
.big-card .stats{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px}
.big-card .stat{text-align:center;padding:6px;background:#f8f9fa;border-radius:6px}
.big-card .stat .num{font-size:16px;font-weight:700;color:#1a3a5c}
.big-card .stat .lbl{color:#888;font-size:9px}
.charts-section{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:20px 0}
.chart-box{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.chart-box h3{font-size:13px;color:#1a3a5c;margin:0 0 12px}
.bar-group{margin:4px 0}
.bar-row{display:flex;align-items:center;gap:6px;margin:2px 0;font-size:10px}
.bar-row .label{min-width:70px;text-align:right;color:#555;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-row .fill{height:12px;border-radius:2px;min-width:2px;transition:width .3s}
.bar-row .val{min-width:35px;font-size:9px;color:#888}
.section-title{font-size:16px;color:#1a3a5c;margin:24px 0 12px}
.footer{text-align:center;padding:20px;color:#999;font-size:11px}
@media(max-width:900px){.big-cards,.charts-section{grid-template-columns:1fr}}
</style>
</head>
<body>
<script src="/lib/site-nav.js?v=2"></script>
<nav class="pvdb-subnav">
  <a href="index.html" class="on">Dashboard</a>
  <a href="gene_browser.html#nlr">NLR</a>
  <a href="gene_browser.html#srna">sRNA</a>
  <a href="gene_browser.html#ups">UPS</a>
  <a href="gene_browser.html#mirna">miRNA</a>
  <a href="gene_browser.html#downloads">Downloads</a>
  <a href="data/index.html">Statistics</a>
</nav>
<div class="hero">
  <h1>Plant Immune & sRNA Gene Atlas</h1>
""")
H.append(f'''  <p>RefPlantNLR 415 experimentally validated NLR immune receptors (73 species) · 11,780 sRNA pathway genes (AGO/DCL/RDR/DRB) · 3,996 UPS components · {MIRNA_TOTAL:,} miRNAs + {VSIRNA_N:,} vsiRNAs · 59 antiviral NLR effector interactions</p>
</div>
<div class="wrap">
''')

# Big cards
total = len(nlr)+len(srna)+len(ups)
H.append('<div class="big-cards">')

# NLR card
H.append(f'''<a class="big-card" href="gene_browser.html#nlr" onclick="localStorage.setItem('genesActiveTab','nlr')">
<div class="icon">🛡️</div><h2>NLR — Immune Receptors</h2>
<div class="desc">Nucleotide-binding Leucine-rich Repeat receptors — 415 experimentally validated plant NLRs from RefPlantNLR (Zenodo 3936022)</div>
<div class="stats">
  <div class="stat"><div class="num">{len(nlr):,}</div><div class="lbl">Genes</div></div>
  <div class="stat"><div class="num">{len(nlr_dt)}</div><div class="lbl">Domain Types</div></div>
  <div class="stat"><div class="num">{len(nlr_sp)}</div><div class="lbl">Species</div></div>
  <div class="stat"><div class="num">{nlr_v:,}</div><div class="lbl">RefPlantNLR (V)</div></div>
</div></a>''')

# sRNA card
H.append(f'''<a class="big-card" href="gene_browser.html#srna" onclick="localStorage.setItem('genesActiveTab','srna')">
<div class="icon">🧬</div><h2>sRNA — Small RNA Pathway</h2>
<div class="desc">AGO / DCL / RDR / DRB / SGS3 / HEN1 gene families — RNA silencing core machinery</div>
<div class="stats">
  <div class="stat"><div class="num">{len(srna):,}</div><div class="lbl">Genes</div></div>
  <div class="stat"><div class="num">{len(srna_fam)}</div><div class="lbl">Families</div></div>
  <div class="stat"><div class="num">{len(srna_sp)}</div><div class="lbl">Species</div></div>
  <div class="stat"><div class="num">{srna_prot:,}</div><div class="lbl">Proteins</div></div>
</div></a>''')

# UPS card
H.append(f'''<a class="big-card" href="gene_browser.html#ups" onclick="localStorage.setItem('genesActiveTab','ups')">
<div class="icon">♻️</div><h2>UPS — Ubiquitin-Proteasome</h2>
<div class="desc">E1/E2/E3 ubiquitin ligases, F-box, BTB, Cullin, Proteasome — protein degradation machinery</div>
<div class="stats">
  <div class="stat"><div class="num">{len(ups):,}</div><div class="lbl">Genes</div></div>
  <div class="stat"><div class="num">{len(ups_fam)}</div><div class="lbl">Families</div></div>
  <div class="stat"><div class="num">{len(ups_sp)}</div><div class="lbl">Species</div></div>
  <div class="stat"><div class="num">{ups_prot:,}</div><div class="lbl">Proteins</div></div>
</div></a>''')

H.append(f'''<a class="big-card" href="gene_browser.html#mirna" onclick="localStorage.setItem('genesActiveTab','mirna')">
<div class="icon">🔬</div><h2>miRNA — microRNA Catalog</h2>
<div class="desc">{MIRNA_TOTAL:,} miRNA sequences from {MIRNA_SPECIES} plant species, integrated from plantrg + miRBase + NCBI</div>
<div class="stats">
  <div class="stat"><div class="num">{MIRNA_TOTAL:,}</div><div class="lbl">miRNA Sequences</div></div>
  <div class="stat"><div class="num">{MIRNA_SPECIES}</div><div class="lbl">Plant Species</div></div>
  <div class="stat"><div class="num">3</div><div class="lbl">Data Sources</div></div>
  <div class="stat"><div class="num">4.7 MB</div><div class="lbl">Combined FASTA</div></div>
</div></a>''')

H.append(f'''<a class="big-card" href="gene_browser.html#downloads" style="border:2px dashed #ccc;background:#fafafa">
<div class="icon">📦</div><h2>Downloads</h2>
<div class="desc">FASTA sequences, TSV gene tables, protein files — all available for download<br><span style="font-size:10px">V = NCBI 收录标记（非实验验证）；NLR 部分为 RefPlantNLR 人工校验集</span></div>
<div class="stats">
  <div class="stat"><div class="num">{total:,}</div><div class="lbl">Total Genes</div></div>
  <div class="stat"><div class="num">{len(nlr_sp|srna_sp|ups_sp)}</div><div class="lbl">Total Species</div></div>
  <div class="stat"><div class="num">{nlr_v+srna_ncbi_v+ups_ncbi_v:,}</div><div class="lbl">NCBI 收录 (V)</div></div>
  <div class="stat"><div class="num">{srna_prot+ups_prot:,}</div><div class="lbl">Proteins</div></div>
</div></a>''')
H.append('</div>')

H.append(f"""
<div class="footer">
  Plant Immune & sRNA Gene Atlas — {total:,} genes across {len(nlr_sp|srna_sp|ups_sp)} species &middot;
  Data: RefPlantNLR &middot; NCBI Gene/Protein &middot; miRBase &middot; plantrg &middot; PVsiRNAdb &middot;
  <a href="gene_browser.html">Gene Browser</a> &middot; <a href="gene_browser.html#downloads">Downloads</a>
</div>
</div>
</body>
</html>
""")

with open(OUTHTML, "w", encoding="utf-8") as f:
    f.write("\n".join(H))

print(f"Saved index.html: {os.path.getsize(OUTHTML)/1024:.0f} KB")
print(f"Stats: {len(nlr)} NLR + {len(srna):,} sRNA + {len(ups):,} UPS = {total:,} genes")
