#!/usr/bin/env python3
"""Virus Profile — comprehensive single-virus detail pages."""

import os, json, csv, re
from pathlib import Path
from flask import Flask, request, render_template_string

app = Flask(__name__)

BASE = Path("/opt/plant_virus_db/plant_virus_db_pipeline")
FULL_TSV = str(BASE / "docs/data/Plant_Virus_Full.Info.tsv")
REF_TSV = str(BASE / "docs/data/Plant_Virus_Ref.Info.tsv")
GENOME_DIR = BASE / "genome_annotations"
PAPERS_JSON = str(BASE / "7.literature_tracker/papers.json")
PRIMER_TSV = str(BASE / "docs/data/primers/primer_reference.tsv")
MAP_TSV = str(BASE / "docs/data/name_mapping.tsv")


def load_name_map():
    m = {}
    if os.path.exists(MAP_TSV):
        with open(MAP_TSV, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                m[row.get("Lookup_Key", "").lower()] = row
    return m


def get_species_info(name):
    """Get species metadata from ref TSV."""
    results = []
    with open(REF_TSV, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
            if sp.lower() == name.lower():
                results.append(row)
    return results[0] if results else None


def search_species(query):
    """Search species by partial name."""
    q = query.lower().strip()
    results = []
    seen = set()
    with open(REF_TSV, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
            if q in sp.lower() and sp not in seen:
                seen.add(sp)
                results.append({"name": sp, "family": row.get("Family", ""), "count": 1})
                if len(results) >= 30:
                    break
    return results


# ── Routes ──────────────────────────────────

@app.route("/virus/")
@app.route("/virus")
def virus_search():
    q = request.args.get("q", "").strip()
    results = search_species(q) if q else []
    return render_template_string(SEARCH_PAGE, query=q, results=results, count=len(results))


@app.route("/virus/<path:name>")
def virus_detail(name):
    info = get_species_info(name)
    if not info:
        return render_template_string(NOT_FOUND, name=name), 404

    # Get annotations from local genome_annotations
    accs = []
    sp_safe = name.replace("/", "_")
    sp_dir = GENOME_DIR / sp_safe
    if sp_dir.exists():
        for gb_file in sorted(sp_dir.glob("*.gb")):
            ac = gb_file.stem
            files = {
                "genome": f"/virus/files/{sp_safe}/{ac}_genome.fasta",
                "cds": f"/virus/files/{sp_safe}/{ac}_cds.fasta",
                "protein": f"/virus/files/{sp_safe}/{ac}_protein.fasta",
                "gff3": f"/virus/files/{sp_safe}/{ac}.gff3",
                "gb": f"/virus/files/{sp_safe}/{ac}.gb",
            }
            # Check which files actually exist
            for key in list(files.keys()):
                if key == "gb":
                    continue
                local_path = sp_dir / f"{ac}_{'genome' if key == 'genome' else key}.fasta" if key != "gff3" else sp_dir / f"{ac}.gff3"
                if not local_path.exists():
                    del files[key]
            accs.append({"name": ac, "files": files})

    # Parse proteins from first GB
    proteins = []
    gb_path = sp_dir / f"{accs[0]['name']}.gb" if accs and sp_dir.exists() else None
    if gb_path and gb_path.exists():
        gb_text = gb_path.read_text(encoding="utf-8", errors="replace")
        for line in gb_text.split("\n"):
            if line.startswith("     CDS"):
                m = re.search(r'(\d+\.\.\d+)', line)
                pos = m.group(1) if m else ""
                prot_match = re.search(r'product="([^"]*)"', gb_text[gb_text.index(line):])
                prot = prot_match.group(1) if prot_match else ""
                prot_id_match = re.search(r'protein_id="([^"]*)"', gb_text[gb_text.index(line):])
                prot_id = prot_id_match.group(1) if prot_id_match else ""
                if prot:
                    proteins.append({"product": prot, "position": pos, "protein_id": prot_id})

    # Get linked papers
    papers = []
    if os.path.exists(PAPERS_JSON):
        with open(PAPERS_JSON, encoding="utf-8") as f:
            all_papers = json.load(f).get("papers", [])
            nl = name.lower()
            for p in all_papers:
                cats = p.get("categories", [])
                if info.get("Family", "") in cats or nl in str(p.get("title", "")).lower():
                    papers.append(p)
            papers = papers[:20]

    # Get primer count
    primers_count = 0
    if os.path.exists(PRIMER_TSV):
        with open(PRIMER_TSV, encoding="utf-8") as pf:
            for row in csv.DictReader(pf, delimiter="\t"):
                if name.lower() in (row.get("Species", "")).lower():
                    primers_count += 1

    return render_template_string(DETAIL_PAGE, info=info, accs=accs,
        proteins=proteins, papers=papers, primers_count=primers_count, len=len)


@app.route("/virus/files/<path:filepath>")
def serve_file(filepath):
    """Serve local annotation files."""
    full_path = GENOME_DIR / filepath
    if full_path.exists():
        from flask import send_file
        return send_file(str(full_path))
    return "Not found", 404


# ── Templates ────────────────────────────────

SEARCH_PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Virus Search</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{font-family:sans-serif;background:#f5f5f5;margin:0}
nav{background:#1a5276;display:flex;align-items:center;padding:0 24px;height:52px}
nav a{color:rgba(255,255,255,.8);text-decoration:none;padding:14px 18px;font-size:14px}
.hero{background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff;padding:24px}
.main{max-width:900px;margin:0 auto;padding:16px}
.card{background:#fff;border-radius:8px;padding:16px;margin:8px 0;box-shadow:0 1px 3px rgba(0,0,0,.04);display:flex;justify-content:space-between}
.card a{color:#1a5276;font-weight:600;text-decoration:none}.card a:hover{text-decoration:underline}
</style></head><body>
<nav><a href="/virus/" style="font-weight:700;color:#fff;font-size:16px">Virus Profile</a><a href="/reference/">Reference DB</a><a href="/explorer/">Explorer</a><a href="/vector/">Vectors</a></nav>
<div class="hero"><h1 style="margin:0">Virus Profile</h1><p style="margin:4px 0 0;opacity:.85">Comprehensive plant virus detail pages — GenBank, genome maps, proteins, papers, primers</p></div>
<div class="main"><form><input name="q" value="{{query}}" placeholder="Search species name..." autofocus style="width:100%;padding:10px;border:2px solid #e0e0e0;border-radius:8px;font-size:15px;outline:none" onchange="this.form.submit()"></form>
<div style="margin-top:16px">{% if results %}{% for r in results %}<div class="card"><a href="/virus/{{r.name|urlencode}}">{{r.name}}</a><span style="font-size:12px;color:#888">{{r.family}}</span></div>{% endfor %}{% elif query %}<div style="text-align:center;padding:40px;color:#999">No results for "{{query}}"</div>{% else %}<div style="text-align:center;padding:40px;color:#999">Enter a species name above</div>{% endif %}</div></div></body></html>'''

NOT_FOUND = r'''<html><body style="font-family:sans-serif;text-align:center;padding:60px"><h1>Not Found</h1><p>{{name}}</p><a href="/virus/">Back</a></body></html>'''

DETAIL_PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>{{info.get('Species_ICTV', info.get('Species_NCBI',''))}}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{font-family:sans-serif;background:#f5f5f5;margin:0}
nav{background:#1a5276;display:flex;align-items:center;padding:0 24px;height:52px}
nav a{color:rgba(255,255,255,.8);text-decoration:none;padding:14px 18px;font-size:14px}
.hero{background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff;padding:24px}
.hero h1{margin:0;font-size:20px}.hero p{margin:4px 0 0;opacity:.85;font-size:13px}
.main{max-width:1100px;margin:0 auto;padding:16px}
.section{background:#fff;border-radius:8px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.section h2{font-size:15px;color:#1a5276;margin:0 0 12px;border-bottom:2px solid #e8e8e8;padding-bottom:8px}
.badge{display:inline-block;padding:3px 8px;border-radius:3px;font-size:10px;font-weight:600}
.bg-blue{background:#e3f2fd;color:#1565c0}.bg-green{background:#e8f5e9;color:#2e7d32}
table{font-size:12px;width:100%}th{background:#f5f5f5;padding:6px}td{padding:6px;border-bottom:1px solid #f0f0f0}
.btn-dl{padding:4px 10px;border-radius:4px;font-size:11px;text-decoration:none;margin:2px;display:inline-block}
.btn-dl-primary{background:#1a5276;color:#fff}.btn-dl-success{background:#27ae60;color:#fff}
.btn-dl-secondary{background:#666;color:#fff}
</style></head><body>
<nav><a href="/virus/" style="font-weight:700;color:#fff;font-size:16px">Virus Profile</a><a href="/reference/">Reference DB</a><a href="/explorer/">Explorer</a><a href="/vector/">Vectors</a></nav>
<div class="hero"><h1>{{info.get('Species_ICTV', info.get('Species_NCBI',''))}}</h1><p>{{info.get('Family','')}} | {{info.get('Molecule_type','')}} | {{info.get('Topology','')}} | {{info.get('Length','')}}bp | {{accs|length}} accessions</p></div>
<div class="main">

{% if accs %}<div class="section"><h2>Downloads</h2><div style="display:flex;flex-wrap:wrap;gap:8px">
{% for a in accs %}{% for type,url in a.files.items() %}
<a href="{{url}}" class="btn-dl {% if 'genome' in type %}btn-dl-primary{% elif 'protein' in type or 'cds' in type %}btn-dl-success{% else %}btn-dl-secondary{% endif %}">{{a.name}} {{type}}</a>
{% endfor %}{% endfor %}</div></div>{% endif %}

{% if proteins %}<div class="section"><h2>Proteins ({{proteins|length}})</h2><table><thead><tr><th>Product</th><th>Position</th><th>Protein ID</th></tr></thead><tbody>{% for p in proteins %}<tr><td><strong>{{p.product}}</strong></td><td>{{p.position}}</td><td><code style="font-size:10px">{{p.protein_id}}</code></td></tr>{% endfor %}</tbody></table></div>{% endif %}

{% if papers %}<div class="section"><h2>Related Papers ({{papers|length}})</h2>{% for p in papers %}<div style="padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:12px"><span class="badge bg-green">{{p.year}}</span> <a href="https://pubmed.ncbi.nlm.nih.gov/{{p.pmid}}" target="_blank" style="color:#1a5276;font-weight:600">{{p.title}}</a><br><span style="color:#888">{{p.journal}} · {{p.first_author}} et al.</span></div>{% endfor %}{% endif %}

{% if primers_count > 0 %}<div class="section"><h2>Primers ({{primers_count}})</h2><a href="/primers/search?q={{info.get('Species_ICTV','')|urlencode}}" target="_blank">View in Primer DB →</a></div>{% endif %}

</div></body></html>'''


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5006)), debug=False)
