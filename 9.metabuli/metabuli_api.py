#!/usr/bin/env python3
"""Metabuli Contig Classification API."""

import os, json, uuid, time, subprocess, threading, shutil, re, urllib.request, urllib.parse, urllib.error, base64
import io
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template_string, Response
import sys as _sys; _sys.path.insert(0, str(Path(__file__).parent / 'primer_design'))

app = Flask(__name__)

METABULI_BIN = "/usr/local/bin/metabuli"
METABULI_DB = "/opt/plant_virus_db/ref.virus.build.metabuli_db"
JOBS_DIR = Path("/opt/plant_virus_db/metabuli_jobs")
MAX_SIZE = 100 * 1024 * 1024
os.makedirs(JOBS_DIR, exist_ok=True)
jobs = {}

# ── NCBI API endpoints & settings ──
NCBI_BLAST_URL  = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"
NCBI_CDD_URL    = "https://www.ncbi.nlm.nih.gov/Structure/bwrpsb/bwrpsb.cgi"
NCBI_BLAST_SLEEP = 10      # seconds between BLAST status polls
NCBI_CDD_SLEEP   = 10      # seconds between CDD status polls
BLAST_TIMEOUT    = 3000    # max wait for BLAST
CDD_TIMEOUT      = 3000    # max wait for CDD
BLAST_HITLIST    = 50      # top hits
BLAST_ENTREZ     = ""  # no restriction (user requested)

# 标准病毒分类 8 级 (域界门纲目科属种)
RANKS = ["realm", "kingdom", "phylum", "class", "order", "family", "genus", "species"]


def _load_taxlin(path):
    """加载 build_taxid_lineage.py 生成的权威 taxid → ICTV 8 级分类表。"""
    tl = {}
    if not path.exists():
        return tl
    with open(path, encoding="utf-8", errors="replace") as f:
        f.readline()  # header: taxid, sciname, realm..species
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            rec = {"sciname": p[1]}
            for i, r in enumerate(RANKS):
                rec[r] = p[2 + i] if 2 + i < len(p) else ""
            tl[p[0]] = rec
    return tl


def _load_genus_lens(path):
    """加载 genus_lens 文件 → {genus_name: avg_length}。"""
    gl = {}
    if not path.exists():
        return gl
    with open(path, encoding="utf-8", errors="replace") as f:
        f.readline()  # header: genus\ttotal
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            # strip g__ prefix
            name = p[0]
            if name.startswith("g__"):
                name = name[3:]
            try:
                gl[name] = float(p[1])
            except ValueError:
                pass
    return gl


TAXLIN = _load_taxlin(Path(__file__).parent / "taxid_lineage.tsv")
GENUS_LENS = _load_genus_lens(Path(__file__).parent / "genus_lens")
GENUS_LENS_LOWER = {k.lower(): v for k, v in GENUS_LENS.items()}
# Build ICTV species → clean NCBI species name (strip strain/isolate suffixes)
_ICTV2NCBI = {}
for _tid, _rec in TAXLIN.items():
    _sp = _rec.get("species", "")
    _sc = _rec.get("sciname", "")
    if not _sp or not _sc:
        continue
    # Prefer the shortest sciname for each ICTV species (species-level, not strain)
    if _sp not in _ICTV2NCBI or len(_sc) < len(_ICTV2NCBI[_sp]):
        _ICTV2NCBI[_sp] = _sc
print(f"Taxid lineage: {len(TAXLIN)} entries")
print(f"Genus lengths: {len(GENUS_LENS)} entries")
print(f"ICTV→NCBI species map: {len(_ICTV2NCBI)} entries")


def _load_genus_lens(path, taxdir=None):
    """加载 genus_lens 表，通过 NCBI taxonomy 建立属名→ICTV 属名→平均长度的映射。
    
    策略：
    1. 加载 genus_lens (NCBI 属名 → avg_len)
    2. 如果提供 taxdir，加载 names.dmp 全部名称（含 synonym），
       反向查找每个 genus 的 taxid，再通过 TAXLIN 拿到 ICTV 属名
    3. 最终输出 {ictv_genus_lower: avg_len} 的精确映射
    """
    if not path.exists():
        return {}, {}
    
    # Step 1: 解析 genus_lens → {ncbi_name: avg_len}
    ncbi_avg = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        f.readline()  # header
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            name = p[0]
            if name.startswith("g__"):
                name = name[3:]
            try:
                ncbi_avg[name] = float(p[1])
            except ValueError:
                ncbi_avg[name] = p[1]
    
    # Step 2: 如果有 taxonomy，建立 NCBI 名 → ICTV 属名 的映射
    nchi_to_ictv = {}  # ncbi_lower → ictv_genus
    if taxdir:
        names_dmp = Path(taxdir) / "names.dmp"
        if names_dmp.exists():
            # 加载 names.dmp 全部名称 → taxid (反向索引)
            name_to_taxids = {}
            with open(names_dmp, encoding="utf-8", errors="replace") as f:
                for line in f:
                    p = [x.strip() for x in line.split("\t|\t")]
                    if len(p) >= 2:
                        tid = p[0]
                        nm = p[1].lower()
                        name_to_taxids.setdefault(nm, []).append(tid)
            
            # 对每个 genus_lens 名，找到它在 TAXLIN 中的 ICTV genus
            for ncbi_name in ncbi_avg:
                tids = name_to_taxids.get(ncbi_name.lower(), [])
                for tid in tids:
                    info = TAXLIN.get(tid, {})
                    ictv_genus = info.get("genus", "")
                    if ictv_genus:
                        nchi_to_ictv[ncbi_name.lower()] = ictv_genus
                        break  # 找到第一个有 ICTV genus 的 taxid 就停
    
    # Step 3: 构建最终映射 {ictv_genus_lower: avg_len}
    gl_exact = {}
    gl_lower = {}
    for ncbi_name, avg in ncbi_avg.items():
        # 通过 taxonomy 映射找 ICTV 名；找不到则保留原名
        ictv = nchi_to_ictv.get(ncbi_name.lower(), ncbi_name)
        gl_exact[ictv] = avg
        gl_lower[ictv.lower()] = avg
    
    return gl_exact, gl_lower


GENUS_LENS, GENUS_LENS_LOWER = _load_genus_lens(
    Path(__file__).parent / "genus_lens",
    taxdir="/opt/plant_virus_db/taxonomy"
)
print(f"Genus lens: {len(GENUS_LENS)} entries")


def _lookup_genus_avg_len(genus_ictv):
    """根据 ICTV 属名查找属平均长度。先精确匹配，再忽略大小写匹配（处理 ICTV/NCBI 命名不一致）。"""
    if not genus_ictv:
        return ""
    # 1) 精确匹配
    v = GENUS_LENS.get(genus_ictv)
    if v is not None:
        return v
    # 2) 忽略大小写
    v = GENUS_LENS_LOWER.get(genus_ictv.lower())
    if v is not None:
        return v
    return ""


def _parse_fasta(path):
    """纯 Python 解析 FASTA，键为 header 首个空白前的 token（与 Metabuli contig 名一致）。"""
    seqs, name, buf = {}, None, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(">"):
                if name is not None:
                    seqs[name] = "".join(buf)
                name = line[1:].strip().split()[0] if line[1:].strip() else ""
                buf = []
            else:
                buf.append(line.strip())
    if name is not None:
        seqs[name] = "".join(buf)
    return seqs


def _wrap(seq, w=70):
    return "\n".join(seq[i:i + w] for i in range(0, len(seq), w))


# ── Sequence-type detection ──
def _is_protein(seq):
    """Heuristic: if >80% of letters are amino-acid-like (not just ACGTU), treat as protein."""
    nuc = set("ACGTRYSWKMBDHVNacgtryswkmbdhvn")
    clean = "".join(c for c in seq if c.isalpha())
    if not clean:
        return False
    non_nuc = sum(1 for c in clean if c not in nuc)
    return (non_nuc / len(clean)) > 0.2


# ── Simple 6-frame translation ──
_CODON = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","TCT":"S","TCC":"S","TCA":"S","TCG":"S",
    "TAT":"Y","TAC":"Y","TAA":"*","TAG":"*","TGT":"C","TGC":"C","TGA":"*","TGG":"W",
    "CTT":"L","CTC":"L","CTA":"L","CTG":"L","CCT":"P","CCC":"P","CCA":"P","CCG":"P",
    "CAT":"H","CAC":"H","CAA":"Q","CAG":"Q","CGT":"R","CGC":"R","CGA":"R","CGG":"R",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","ACT":"T","ACC":"T","ACA":"T","ACG":"T",
    "AAT":"N","AAC":"N","AAA":"K","AAG":"K","AGT":"S","AGC":"S","AGA":"R","AGG":"R",
    "GTT":"V","GTC":"V","GTA":"V","GTG":"V","GCT":"A","GCC":"A","GCA":"A","GCG":"A",
    "GAT":"D","GAC":"D","GAA":"E","GAG":"E","GGT":"G","GGC":"G","GGA":"G","GGG":"G",
}

def _translate_dna(dna):
    """6-frame translation → list of (frame_label, protein_seq)."""
    dna = dna.upper().replace("U", "T")
    rc = {"A":"T","T":"A","C":"G","G":"G","R":"Y","Y":"R","S":"S","W":"W","K":"M",
          "M":"K","B":"V","V":"B","D":"H","H":"D","N":"N"}
    def _rc(s):
        return "".join(rc.get(c, "N") for c in reversed(s))
    rev = _rc(dna)
    frames = []
    for strand, label_s, seq in [("+", "forward", dna), ("-", "reverse", rev)]:
        for offset in range(3):
            prot = []
            for i in range(offset, len(seq) - 2, 3):
                codon = seq[i:i+3]
                prot.append(_CODON.get(codon, "X"))
            frames.append((f"{label_s} frame {offset+1}", "".join(prot)))
    return frames


def _longest_orf(frames):
    """From 6-frame translations, pick the longest stretch between * and *."""
    best_label, best_seq = frames[0]
    best_len = 0
    for label, prot in frames:
        parts = prot.split("*")
        for part in parts:
            if len(part) > best_len:
                best_len = len(part)
                best_label = label
                best_seq = part
    return best_label, best_seq


# ── FASTA reader ──
def _read_fasta(path_or_text, is_path=True):
    """Return list of (header, seq) from FASTA file or text."""
    text = Path(path_or_text).read_text(encoding="utf-8", errors="replace") if is_path else path_or_text
    seqs = []
    name, buf = None, []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                seqs.append((name, "".join(buf)))
            name = line[1:].strip()
            buf = []
        else:
            buf.append(line.strip())
    if name is not None:
        seqs.append((name, "".join(buf)))
    return seqs


# ── NCBI BLAST submit + poll ──
def _submit_blast(program, database, query_fasta, entrez_query=""):
    """Submit BLAST job → (rid, rtoe). rtoe is estimated seconds."""
    params = {
        "CMD": "Put",
        "PROGRAM": program,
        "DATABASE": database,
        "QUERY": query_fasta,
        "FORMAT_TYPE": "JSON2_S",
        "HITLIST_SIZE": str(BLAST_HITLIST),
        "ALIGNMENTS": str(BLAST_HITLIST),
        "DESCRIPTIONS": str(BLAST_HITLIST),
    }
    if entrez_query:
        params["ENTREZ_QUERY"] = entrez_query
    if program == "blastn":
        params["MEGABLAST"] = "on"
    data = urllib.parse.urlencode(params).encode("ascii")
    req = urllib.request.Request(NCBI_BLAST_URL, data=data)
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    # Parse QBlastInfo block
    rid_match = re.search(r"QBlastInfoBegin\s+RID\s*=\s*(\S+)", body)
    rtoe_match = re.search(r"QBlastInfoBegin\s+RTOE\s*=\s*(\d+)", body)
    if not rid_match:
        # Check for error
        err = re.search(r"QBlastInfoBegin\s+Error\s*=\s*(.*)", body)
        raise RuntimeError(err.group(1) if err else f"BLAST submission failed:\n{body[:500]}")
    return rid_match.group(1), int(rtoe_match.group(1)) if rtoe_match else 30


def _poll_blast(rid, max_wait=BLAST_TIMEOUT):
    """Poll BLAST job → parsed hits list."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        params = {"CMD": "Get", "RID": rid, "FORMAT_TYPE": "JSON2_S"}
        url = NCBI_BLAST_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
        # Try JSON first (real result)
        try:
            result = json.loads(body)
            return _parse_blast_json(result)
        except (json.JSONDecodeError, ValueError):
            pass
        # Not JSON — check if still running
        if "Status=WAITING" in body or "Status=READY" in body:
            time.sleep(NCBI_BLAST_SLEEP)
            continue
        # Unknown response
        if "QBlastInfo" in body:
            err = re.search(r"Error\s*=\s*(.*)", body)
            raise RuntimeError(f"BLAST error: {err.group(1) if err else body[:200]}")
        time.sleep(NCBI_BLAST_SLEEP)
    raise TimeoutError(f"BLAST job {rid} timed out after {max_wait}s")


def _parse_blast_json(result):
    """Extract hits from BLAST JSON output (BlastOutput2 format)."""
    hits = []
    try:
        outputs = result.get("BlastOutput2", [])
    except Exception:
        return hits
    for output in outputs:
        report = output.get("report", {})
        search = (report.get("results", {}) or {}).get("search", {}) or {}
        query_title = search.get("query_title", "query")
        for hit in search.get("hits", []):
            desc_list = hit.get("description", [])
            desc = desc_list[0] if desc_list else {}
            hsps = hit.get("hsps", [])
            best = hsps[0] if hsps else {}
            hits.append({
                "query": query_title,
                "accession": desc.get("accession", ""),
                "title": desc.get("title", ""),
                "taxid": desc.get("taxid", ""),
                "sciname": desc.get("sciname", ""),
                "identity": best.get("identity", 0),
                "align_len": best.get("align_len", 0),
                "query_from": best.get("query_from", 0),
                "query_to": best.get("query_to", 0),
                "hit_from": best.get("hit_from", 0),
                "hit_to": best.get("hit_to", 0),
                "evalue": best.get("evalue", ""),
                "bit_score": best.get("bit_score", 0),
                "gaps": best.get("gaps", 0),
                "qseq": best.get("qseq", ""),
                "hseq": best.get("hseq", ""),
                "midline": best.get("midline", ""),
            })
    return hits


# ── NCBI Batch CD-Search: submit → cdsid → poll → parse ──
def _submit_cdd(query_fasta):
    """Submit to NCBI Batch CD-Search → (cdsid, status_code)."""
    form = {
        "queries": query_fasta,
        "smode": "auto",
        "db": "cdd",
        "evalue": "0.01",
        "maxhit": "500",
        "useid1": "true",
        "filter": "false",
        "compbasedadj": "1",
        "tdata": "hits",
        "dmode": "rep",
        "qdefl": "true",
        "cddefl": "true",
    }
    data = urllib.parse.urlencode(form).encode("ascii")
    req = urllib.request.Request(NCBI_CDD_URL, data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "PlantVirusDB/1.0")
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    cdsid = _read_cdd_tag(text, "cdsid")
    status = _read_cdd_tag(text, "status")
    if not cdsid:
        raise RuntimeError(f"CDD did not return Search ID:\n{text[:500]}")
    return cdsid, (status or "3")


def _poll_cdd(cdsid, max_wait=CDD_TIMEOUT):
    """Poll Batch CD-Search with cdsid → (hits_list, raw_text)."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        form = {
            "cdsid": cdsid,
            "tdata": "hits",
            "dmode": "rep",
            "qdefl": "true",
            "cddefl": "true",
        }
        data = urllib.parse.urlencode(form).encode("ascii")
        req = urllib.request.Request(NCBI_CDD_URL, data=data)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("User-Agent", "PlantVirusDB/1.0")
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        status = (_read_cdd_tag(text, "status") or "").lower()
        if status in ("0", "4", "success"):
            hits = _parse_cdd_hits(text)
            return hits, text
        if status in ("1", "2", "5"):
            raise RuntimeError(f"CDD job {cdsid} failed: status={status}")
        # status=3 (running) → keep polling
        time.sleep(NCBI_CDD_SLEEP)
    raise TimeoutError(f"CDD job {cdsid} timed out after {max_wait}s")


def _read_cdd_tag(text, tag):
    """Parse '#tag  value' lines from Batch CD-Search response."""
    m = re.search(rf"^#{re.escape(tag)}\s+(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


def _parse_cdd_hits(text):
    """Parse Batch CD-Search tab-separated hits table → list of dicts."""
    hits = []
    lines = text.splitlines()
    # Find the header line "Query\tHit type\t..."
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("Query\t") and "Hit type" in line:
            header_idx = i
            break
    if header_idx is None:
        return hits
    headers = lines[header_idx].split("\t")
    for line in lines[header_idx + 1:]:
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        row = {}
        for j, h in enumerate(headers):
            row[h.strip()] = parts[j].strip() if j < len(parts) else ""
        # Normalize field names for frontend
        hits.append({
            "query": row.get("Query", ""),
            "hit_type": row.get("Hit type", ""),
            "pssm_id": row.get("PSSM-ID", ""),
            "accession": row.get("Accession", ""),
            "short_name": row.get("Short name", ""),
            "description": row.get("Incomplete", ""),
            "evalue": row.get("E-Value", ""),
            "bit_score": row.get("Bit score", ""),
            "query_from": row.get("From", ""),
            "query_to": row.get("To", ""),
            "superfamily": row.get("Superfamily", ""),
        })
    return hits


def _extract_virus(job_id, outdir, cls_path, fasta_path):
    """提取被分类(视为病毒)的 contig：输出分类表 TSV + 序列 FASTA。
    分类等级取自权威 taxid_lineage 表(NCBI/ICTV 完整谱系)。
    返回 (virus_fasta_path, virus_tsv_path, n_virus, n_total, rows)。"""
    contigs, n_total = [], 0
    with open(cls_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            n_total += 1
            if p[0] != "1":          # is_classified != 1 → 未分类，跳过
                continue
            contigs.append((p[1], p[2], p[3] if len(p) > 3 else "", p[4] if len(p) > 4 else "", p[5] if len(p) > 5 else ""))
    seqs = _parse_fasta(fasta_path) if fasta_path.exists() else {}
    vtsv = outdir / f"{job_id}_virus_classification.tsv"
    vfa = outdir / f"{job_id}_virus_sequences.fasta"
    rows = []
    with open(vtsv, "w", encoding="utf-8") as ft, open(vfa, "w", encoding="utf-8") as fa:
        ft.write("contig\ttaxid\ttaxon\t" + "\t".join(RANKS) + "\tlength\tscore\te_value\tgenus_avg_len\n")
        for name, taxid, length, score, evalue in contigs:
            info = TAXLIN.get(taxid, {})
            taxon_raw = info.get("sciname", "")
            ictv_species = info.get("species", "")
            # Use species-level NCBI name (strip strain/isolate if available)
            taxon = _ICTV2NCBI.get(ictv_species, taxon_raw) if ictv_species else taxon_raw
            rankvals = [info.get(r, "") for r in RANKS]
            genus_name = info.get("genus", "")
            genus_avg = _lookup_genus_avg_len(genus_name)
            ft.write("\t".join([name, taxid, taxon] + rankvals + [length, score, evalue, str(genus_avg)]) + "\n")
            row = {"contig": name, "taxid": taxid, "taxon": taxon, "length": length, "score": score, "e_value": evalue, "genus_avg_len": genus_avg}
            for r in RANKS:
                row[r] = info.get(r, "")
            rows.append(row)
            seq = seqs.get(name)
            if seq:
                lineage = ";".join(v for v in rankvals if v)
                fa.write(f">{name} taxid={taxid} taxon={taxon.replace(' ', '_')} lineage={lineage}\n{_wrap(seq)}\n")
    return str(vfa), str(vtsv), len(contigs), n_total, rows

def _classify(job_id, fasta_path):
    job = jobs.get(job_id)
    if not job: return
    outdir = JOBS_DIR / job_id / "output"
    os.makedirs(outdir, exist_ok=True)
    job["status"] = "running"
    try:
        subprocess.run([METABULI_BIN, "classify", str(fasta_path), METABULI_DB, str(outdir),
            job_id, "--seq-mode","3", "--threads","2", "--max-ram","1"],
            capture_output=True, text=True, timeout=600)
        tsv = outdir / f"{job_id}_classifications.tsv"
        rept = outdir / f"{job_id}_report.tsv"
        kr = outdir / f"{job_id}_krona.html"
        ok = tsv.exists() or rept.exists()
        job["status"] = "done" if ok else "no_result"
        job["files"] = {"classifications": str(tsv) if tsv.exists() else None,
            "report": str(rept) if rept.exists() else None,
            "krona": str(kr) if kr.exists() else None}
        if rept.exists():
            top = []
            with open(rept) as f:
                for line in f:
                    if line.startswith("#") or not line.strip(): continue
                    p = line.strip().split("\t")
                    if len(p) >= 6: top.append({"proportion":p[0],"count":p[1],"taxon_count":p[2],"rank":p[3],"taxid":p[4],"name":p[5]})
                    if len(top) >= 15: break
            job["summary"] = top
        # 病毒序列分类结果 + 序列提取（在删除输入前完成）
        if tsv.exists():
            try:
                vfa, vtsv, n_virus, n_total, vrows = _extract_virus(job_id, outdir, tsv, fasta_path)
                job["files"]["virus_fasta"] = vfa if n_virus > 0 else None
                job["files"]["virus_tsv"] = vtsv if n_virus > 0 else None
                job["virus_summary"] = {"virus_contigs": n_virus, "total_contigs": n_total}
                job["virus_contigs"] = vrows[:5000]
            except Exception as e:
                job["virus_error"] = str(e)
        # 保存所有 contig 序列（用于 CDD/BLAST 一键分析）
        try:
            if fasta_path.exists():
                job["sequences"] = _parse_fasta(fasta_path)
        except Exception:
            job["sequences"] = {}
        if fasta_path.exists(): fasta_path.unlink()
        def _c():
            time.sleep(7200)
            d = JOBS_DIR / job_id
            if d.exists(): shutil.rmtree(d, ignore_errors=True)
            jobs.pop(job_id, None)
        threading.Thread(target=_c, daemon=True).start()
    except subprocess.TimeoutExpired:
        job["status"] = "timeout"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


# ── BLAST worker (blastn / blastx) ──
def _blast_worker(job_id, query_text, program, database):
    """Run NCBI BLAST asynchronously. Supports multi-FASTA batch."""
    job = jobs.get(job_id)
    if not job:
        return
    job["status"] = "submitting"
    try:
        seqs = _read_fasta(query_text, is_path=False)
        if not seqs:
            raise ValueError("No sequences found")
        job["n_queries"] = len(seqs)

        # Submit all jobs
        tasks = []
        max_rtoe = 30
        for i, (header, seq) in enumerate(seqs):
            fasta = f">{header}\n{seq}\n"
            rid, rtoe = _submit_blast(program, database, fasta, BLAST_ENTREZ)
            tasks.append({"idx": i, "header": header, "rid": rid, "rtoe": rtoe})
            if rtoe > max_rtoe:
                max_rtoe = rtoe
        job["rids"] = [t["rid"] for t in tasks]
        job["status"] = "running"
        job["progress_msg"] = f"Submitted {len(tasks)} job(s), waiting (est. {max_rtoe}s)..."

        # Wait for estimated time before polling (avoids wasted API calls & rate limiting)
        wait_time = min(max_rtoe * 0.85, 120)  # cap at 2 min initial wait
        if wait_time > 5:
            time.sleep(wait_time)

        # Single sequence: poll directly. Multi: ThreadPool.
        all_hits = []
        if len(tasks) == 1:
            hits = _poll_blast(tasks[0]["rid"])
            for h in hits:
                h["query"] = tasks[0]["header"]
            all_hits = hits
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            futures = {}
            with ThreadPoolExecutor(max_workers=3) as pool:
                for t in tasks:
                    fut = pool.submit(_poll_blast, t["rid"])
                    futures[fut] = t
                for fut in as_completed(futures, timeout=600):
                    t = futures[fut]
                    try:
                        hits = fut.result()
                        for h in hits:
                            h["query"] = t["header"]
                        all_hits.extend(hits)
                    except Exception as e:
                        all_hits.append({"query": t["header"], "error": str(e), "accession": "", "title": "BLAST failed", "evalue": "", "identity": 0, "align_len": 0, "bit_score": 0})
        all_hits.sort(key=lambda h: float(h.get("evalue") or "999"))
        job["status"] = "done"
        job["hits"] = all_hits
        job["hit_count"] = len(all_hits)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        def _c():
            time.sleep(7200)
            d = JOBS_DIR / job_id
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            jobs.pop(job_id, None)
        threading.Thread(target=_c, daemon=True).start()


# ── CDD worker ──
def _cdd_worker(job_id, query_text):
    """Submit to NCBI Batch CD-Search. Nucleotide input → 6-frame translation."""
    job = jobs.get(job_id)
    if not job:
        return
    job["status"] = "submitting"
    try:
        # If nucleotide, translate to 6-frame protein
        seqs = _read_fasta(query_text, is_path=False)
        cdd_queries = []
        for header, seq in seqs:
            if _is_protein(seq):
                cdd_queries.append(f">{header}\n{seq}")
            else:
                frames = _translate_dna(seq)
                for label, prot in frames:
                    cdd_queries.append(f">{header}|{label}\n{prot}")
        query_text = "\n".join(cdd_queries) + "\n"

        cdsid, _ = _submit_cdd(query_text)
        job["cdsid"] = cdsid
        job["status"] = "running"
        hits, _ = _poll_cdd(cdsid)
        job["status"] = "done"
        job["hits"] = hits
        job["hit_count"] = len(hits)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        def _c():
            time.sleep(7200)
            d = JOBS_DIR / job_id
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            jobs.pop(job_id, None)
        threading.Thread(target=_c, daemon=True).start()

def _start(content, fname):
    jid = uuid.uuid4().hex[:12]
    jd = JOBS_DIR / jid; os.makedirs(jd, exist_ok=True)
    fp = jd / "input.fasta"; fp.write_bytes(content)
    jobs[jid] = {"id":jid, "status":"queued", "created":datetime.now().isoformat(),
        "filename":fname, "size":len(content), "files":{}}
    threading.Thread(target=_classify, args=(jid, fp), daemon=True).start()
    return jsonify({"job_id":jid, "status":"queued"})

@app.route("/metabuli/classify", methods=["POST"])
def classify():
    f = request.files.get("file")
    if f and f.filename and f.filename.lower().endswith((".fasta",".fa",".fna",".faa")):
        c = f.read()
        if len(c) > MAX_SIZE: return jsonify({"error":"File >100MB"}), 400
        return _start(c, f.filename)
    data = request.get_json(silent=True) or {}
    seq = data.get("sequence","").strip()
    if seq:
        if not seq.startswith(">"): return jsonify({"error":"Must start with >"}), 400
        if len(seq) > MAX_SIZE: return jsonify({"error":"Input >100MB"}), 400
        return _start(seq.encode(), "pasted.fasta")
    return jsonify({"error":"No input"}), 400

@app.route("/metabuli/status/<job_id>")
def status(job_id):
    j = jobs.get(job_id)
    return jsonify(j) if j else (jsonify({"error":"Not found"}), 404)

@app.route("/metabuli/classifications/<job_id>")
def classifications_json(job_id):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get("classifications")
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    data = []
    with open(p) as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            parts = line.strip().split("\t")
            if len(parts) >= 8:
                data.append({"classified":parts[0],"name":parts[1],"taxid":parts[2],
                    "length":parts[3],"score":parts[4],"evalue":parts[5],"rank":parts[6],
                    "lineage":parts[7] if len(parts)>7 else ""})
    return jsonify(data)

@app.route("/metabuli/report/<job_id>")
def report_json(job_id):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get("report")
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    data = []
    with open(p) as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            parts = line.strip().split("\t")
            if len(parts) >= 6:
                data.append({"proportion":parts[0],"count":parts[1],"taxon_count":parts[2],
                    "rank":parts[3],"taxid":parts[4],"name":parts[5]})
    return jsonify(data)


@app.route("/metabuli/virus_contigs/<job_id>")
def virus_contigs_json(job_id):
    j = jobs.get(job_id, {})
    return jsonify({"summary": j.get("virus_summary", {}), "contigs": j.get("virus_contigs", [])})


def _strip_unclassified(html):
    """从 Krona HTML 中移除 unclassified 叶节点，并把父节点 'all' 的总量相应减少，
    使 classified 部分占满 100%。找不到则原样返回（安全回退）。"""
    m = re.search(r'<node name="unclassified"><magnitude><val>([\d.]+)</val></magnitude></node>', html)
    if not m:
        return html
    u = float(m.group(1))
    html = html[:m.start()] + html[m.end():]
    am = re.search(r'(<node name="all"><magnitude><val>)([\d.]+)(</val>)', html)
    if am:
        new = float(am.group(2)) - u
        newstr = str(int(new)) if new == int(new) else ("%g" % new)
        html = html[:am.start()] + am.group(1) + newstr + am.group(3) + html[am.end():]
    return html


@app.route("/metabuli/krona/<job_id>")
def krona_view(job_id):
    j = jobs.get(job_id, {})
    p = j.get("files", {}).get("krona")
    if not p or not os.path.exists(p):
        return jsonify({"error": "Not found"}), 404
    # 默认隐藏 unclassified；?unclassified=1 时显示原图
    if request.args.get("unclassified") == "1":
        return send_file(p)
    html = Path(p).read_text(encoding="utf-8", errors="replace")
    return Response(_strip_unclassified(html), mimetype="text/html")

@app.route("/metabuli/download/<job_id>/<ftype>")
def download(job_id, ftype):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get(ftype)
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    return send_file(p, as_attachment=True)


# ── CDD Domain Search ──
@app.route("/metabuli/cdd", methods=["POST"])
def cdd_search():
    """Submit protein (or nucleotide → auto-translated) for NCBI CD-Search."""
    jid = uuid.uuid4().hex[:12]
    jobs[jid] = {"id": jid, "status": "queued", "created": datetime.now().isoformat(),
                  "tool": "cdd"}
    query_text = ""
    f = request.files.get("file")
    if f and f.filename:
        query_text = f.read().decode("utf-8", errors="replace")
    else:
        data = request.get_json(silent=True) or {}
        query_text = data.get("sequence", "").strip()
        if not query_text:
            return jsonify({"error": "No sequence provided"}), 400
    if not query_text.startswith(">"):
        query_text = ">query\n" + query_text
    if len(query_text) > MAX_SIZE:
        return jsonify({"error": "Input >100MB"}), 400
    threading.Thread(target=_cdd_worker, args=(jid, query_text), daemon=True).start()
    return jsonify({"job_id": jid, "status": "queued", "tool": "cdd"})


@app.route("/metabuli/cdd_status/<job_id>")
def cdd_status(job_id):
    j = jobs.get(job_id)
    return jsonify(j) if j else (jsonify({"error": "Not found"}), 404)


# ── BLASTN ──
@app.route("/metabuli/blastn", methods=["POST"])
def blastn_search():
    """Submit nucleotide query for NCBI BLASTN (nt database)."""
    jid = uuid.uuid4().hex[:12]
    jobs[jid] = {"id": jid, "status": "queued", "created": datetime.now().isoformat(),
                  "tool": "blastn", "program": "blastn", "database": "core_nt"}
    query_text = ""
    f = request.files.get("file")
    if f and f.filename:
        query_text = f.read().decode("utf-8", errors="replace")
    else:
        data = request.get_json(silent=True) or {}
        query_text = data.get("sequence", "").strip()
        if not query_text:
            return jsonify({"error": "No sequence provided"}), 400
    if not query_text.startswith(">"):
        query_text = ">query\n" + query_text
    if len(query_text) > MAX_SIZE:
        return jsonify({"error": "Input >100MB"}), 400
    threading.Thread(target=_blast_worker, args=(jid, query_text, "blastn", "core_nt"), daemon=True).start()
    return jsonify({"job_id": jid, "status": "queued", "tool": "blastn"})


# ── BLASTX ──
@app.route("/metabuli/blastx", methods=["POST"])
def blastx_search():
    """Submit nucleotide query for NCBI BLASTX (nr protein database)."""
    jid = uuid.uuid4().hex[:12]
    jobs[jid] = {"id": jid, "status": "queued", "created": datetime.now().isoformat(),
                  "tool": "blastx", "program": "blastx", "database": "nr_cluster_seq"}
    query_text = ""
    f = request.files.get("file")
    if f and f.filename:
        query_text = f.read().decode("utf-8", errors="replace")
    else:
        data = request.get_json(silent=True) or {}
        query_text = data.get("sequence", "").strip()
        if not query_text:
            return jsonify({"error": "No sequence provided"}), 400
    if not query_text.startswith(">"):
        query_text = ">query\n" + query_text
    if len(query_text) > MAX_SIZE:
        return jsonify({"error": "Input >100MB"}), 400
    threading.Thread(target=_blast_worker, args=(jid, query_text, "blastx", "nr_cluster_seq"), daemon=True).start()
    return jsonify({"job_id": jid, "status": "queued", "tool": "blastx"})


@app.route("/metabuli/blast_status/<job_id>")
def blast_status(job_id):
    j = jobs.get(job_id)
    return jsonify(j) if j else (jsonify({"error": "Not found"}), 404)

# Separate HTML file for cleaner maintenance
HTML_FILE = Path(__file__).parent / "metabuli_page.html"
EXAMPLES_FILE = Path(__file__).parent / "metabuli_examples.json"


@app.route("/metabuli/contig_seq/<job_id>/<path:contig_name>")
def contig_seq(job_id, contig_name):
    """返回某条 contig 的 FASTA 序列（用于 CDD/BLAST 一键分析）。"""
    j = jobs.get(job_id, {})
    seqs = j.get("sequences", {})
    seq = seqs.get(contig_name)
    if not seq:
        # Try virus_fasta file as fallback
        vfa = j.get("files", {}).get("virus_fasta")
        if vfa and os.path.exists(vfa):
            vseqs = _parse_fasta(Path(vfa))
            seq = vseqs.get(contig_name)
    if not seq:
        return jsonify({"error": f"Contig '{contig_name}' not found"}), 404
    fasta_text = f">{contig_name}\n{_wrap(seq)}\n"
    return jsonify({"name": contig_name, "sequence": seq, "fasta": fasta_text})


# ── Primer Design (using primer_design_service) ──
from primer_design_service import DesignJobManager as _DesignJobManager
_primer_mgr = _DesignJobManager(
    jobs_dir=Path("/opt/plant_virus_db/metabuli_jobs/primer_design"),
    species_fasta_dir=Path("/opt/plant_virus_db/primer_design_server/split_species/species")
)

@app.route("/metabuli/primer_design", methods=["POST"])
def primer_design():
    try:
        seqs = None
        species_name = request.form.get("species_name", "").strip()
        mode = request.form.get("mode", "PCR").strip()
        num_pairs = int(request.form.get("num_pairs", "5"))
        prod_min = int(request.form.get("prod_min", "250"))
        prod_max = int(request.form.get("prod_max", "1000"))
        if "file" in request.files:
            f = request.files["file"]
            raw = f.read().decode("utf-8", errors="replace")
            from Bio import SeqIO
            seqs = [str(r.seq).upper().replace("U", "T") for r in SeqIO.parse(io.StringIO(raw), "fasta")]
        elif request.form.get("sequence"):
            raw = request.form["sequence"]
            from Bio import SeqIO
            seqs = [str(r.seq).upper().replace("U", "T") for r in SeqIO.parse(io.StringIO(raw), "fasta")]
        if not seqs:
            return jsonify({"error": "No valid FASTA sequences found"}), 400
        job_id = _primer_mgr.submit(sequences=seqs, species_name=species_name or "custom_input",
                                     design_mode=mode, num_pairs=num_pairs,
                                     prod_min=prod_min, prod_max=prod_max)
        return jsonify({"job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/metabuli/primer_status/<job_id>")
def primer_status(job_id):
    s = _primer_mgr.status(job_id)
    if not s:
        return jsonify({"status": "not_found"}), 404
    result = {"status": "done" if s["status"] == "completed" else
                       "running" if s["status"] in ("pending", "running") else
                       "failed",
              "progress_pct": s.get("progress_pct", 0),
              "progress_msg": s.get("progress_msg", ""),
              "error": s.get("error", ""),
              "species_name": s.get("species_name", ""),
              "design_mode": s.get("design_mode", "")}
    return jsonify(result)

@app.route("/metabuli/primer_results/<job_id>")
def primer_results(job_id):
    fmt = request.args.get("format", "json")
    s = _primer_mgr.status(job_id)
    if not s or s["status"] != "completed":
        return jsonify({"error": "Job not completed"}), 400
    results = _primer_mgr.results(job_id) or []
    if fmt == "tsv":
        tsv = _primer_mgr.results_tsv(job_id)
        return Response(tsv, mimetype="text/plain; charset=utf-8")
    if fmt == "fasta":
        lines = []
        sp = s.get("species_name", "unknown")
        md = s.get("design_mode", "")
        for i, r in enumerate(results):
            lines.append(f">{sp}|{md}|{i+1}|FWD")
            lines.append(r.get("Fwd_Seq", ""))
            lines.append(f">{sp}|{md}|{i+1}|REV")
            lines.append(r.get("Rev_Seq", ""))
        return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")
    return jsonify({"results": results, "species_name": s.get("species_name",""),
                     "design_mode": s.get("design_mode","")})

# Add io import for SeqIO

@app.route("/metabuli/examples")
def examples():
    if EXAMPLES_FILE.exists():
        with open(EXAMPLES_FILE, encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({})


@app.route("/metabuli/")
def index():
    if HTML_FILE.exists():
        return render_template_string(HTML_FILE.read_text(encoding="utf-8"))
    return "<h1>Page not found</h1>", 404


# ── GenBank feature extraction ──
GB_CACHE_DIR = Path("/opt/plant_virus_db/genbank_cache")
GB_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _fetch_gb(accession):
    """Fetch GenBank record from NCBI (with local cache). Returns Bio.SeqRecord or None."""
    cache_path = GB_CACHE_DIR / f"{accession}.gb"
    if cache_path.exists():
        from Bio import SeqIO
        with open(cache_path) as f:
            return SeqIO.read(f, "genbank")
    try:
        from Bio import Entrez, SeqIO
        Entrez.email = "plantvirusdb@example.com"
        handle = Entrez.efetch(db="nucleotide", id=accession, rettype="gb", retmode="text")
        record = SeqIO.read(handle, "genbank")
        handle.close()
        with open(cache_path, "w") as f:
            SeqIO.write(record, f, "genbank")
        return record
    except Exception as e:
        print(f"GenBank fetch error for {accession}: {e}")
        return None


def _extract_features(record):
    """Extract CDS/gene/mat_peptide features from GenBank record."""
    features = []
    for feat in record.features:
        ftype = feat.type
        if ftype not in ("CDS", "gene", "mat_peptide", "5'UTR", "3'UTR"):
            continue
        loc = feat.location
        try:
            start = int(loc.start) + 1  # 1-based
            end = int(loc.end)
        except Exception:
            continue
        quals = {}
        for q in ("gene", "product", "note", "locus_tag", "protein_id"):
            if q in feat.qualifiers:
                quals[q] = feat.qualifiers[q][0]
        label = quals.get("gene") or quals.get("product", "")[:30] or ftype
        features.append({
            "type": ftype,
            "start": start,
            "end": end,
            "label": label,
            "product": quals.get("product", ""),
            "gene": quals.get("gene", "")
        })
    return features


@app.route("/metabuli/genbank/<accession>")
def genbank_features(accession):
    """Return CDS/gene features from GenBank record as JSON."""
    record = _fetch_gb(accession)
    if not record:
        return jsonify({"error": f"Failed to fetch {accession}"}), 404
    features = _extract_features(record)
    return jsonify({
        "accession": accession,
        "length": len(record.seq),
        "organism": record.annotations.get("organism", ""),
        "features": features
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5004)), debug=False)
