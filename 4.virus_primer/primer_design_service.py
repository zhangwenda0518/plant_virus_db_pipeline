#!/usr/bin/env python3
"""
Primer Design Service — Web-facing wrapper for the step2 design engine.
=======================================================================
Provides:
  1. On-demand primer design for uploaded FASTA sequences
  2. On-demand primer design for known virus species (from split FASTA)
  3. Background job management (submit → poll → retrieve results)
  4. Results export in formats compatible with step4 import

Usage (from web server):
    from primer_design_service import DesignJobManager
    mgr = DesignJobManager(jobs_dir="/path/to/jobs")
    job_id = mgr.submit(fasta_path=..., design_mode="PCR", num_pairs=5)
    status = mgr.status(job_id)
    results = mgr.results(job_id)

Architecture:
    Each design job runs in a subprocess (python step2_design_primers.py --single ...)
    to avoid blocking the Flask server. Job status and results are stored in
    per-job directories under jobs_dir.
"""

import os
import sys
import json
import uuid
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict

# ── Path resolution ──────────────────────────────────────────────────
_SERVICE_DIR = Path(__file__).resolve().parent
_STEP2_SCRIPT = _SERVICE_DIR / "step2_design_primers.py"
_SPLIT_SPECIES_DIR = Path("split_species/species")  # relative to CWD


# ======================================================================
# Data models
# ======================================================================

@dataclass
class DesignJob:
    """Track one primer design job."""
    job_id: str
    status: str = "pending"  # pending | running | completed | failed
    design_mode: str = "PCR"  # PCR | qPCR | DEGENERATE | TILED
    species_name: str = ""
    num_pairs: int = 5
    fasta_source: str = ""  # "upload" | "known_species"
    input_fasta: str = ""   # path to input FASTA
    output_dir: str = ""
    results_tsv: str = ""
    results_json: str = ""
    error: str = ""
    progress_pct: int = 0
    progress_msg: str = ""
    primer_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""


# ======================================================================
# Core design functions (in-process, light wrapper around step2)
# ======================================================================

def _primer3_works():
    """Check if primer3-py is usable (test via subprocess to avoid crash)."""
    import subprocess as sp
    try:
        r = sp.run(
            [sys.executable, "-c", "import primer3; primer3.calc_tm('ATGCATGCATGCATGCATGC')"],
            capture_output=True, timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False


def _import_step2():
    """Dynamically import step2 module.
    Returns module or raises ImportError if unavailable."""
    sys.path.insert(0, str(_SERVICE_DIR))
    
    if not _primer3_works():
        raise ImportError("primer3-py is not functional on this platform")
    
    import step2_design_primers as s2
    return s2


def design_from_sequences(
    sequences: List[str],
    mode: str = "PCR",
    num_pairs: int = 5,
    prod_min: int = 250,
    prod_max: int = 1000,
    do_align: bool = True,
    aligner: str = "auto",
) -> List[Dict]:
    """
    Design primers directly from a list of sequences (in-process).
    
    Falls back to pure-Python simple design if primer3/step2 unavailable.
    """
    from Bio import SeqIO
    import io
    
    # Clean sequences
    clean_seqs = [s.strip().upper().replace('U', 'T') for s in sequences if s.strip()]
    if not clean_seqs:
        return []

    # Try step2 (primer3-based) first; fall back to pure Python
    try:
        s2 = _import_step2()
        use_step2 = True
    except Exception:
        use_step2 = False

    if use_step2:
        if mode == "PCR":
            results = s2.design_primers(
                clean_seqs, num_pairs=num_pairs,
                prod_min=prod_min, prod_max=prod_max,
                do_align=do_align, aligner=aligner
            )
        elif mode == "qPCR":
            results = s2.design_qpcr(
                clean_seqs, n=num_pairs,
                amp_min=min(80, prod_min), amp_max=min(200, prod_max),
                do_align=do_align, aligner=aligner
            )
        elif mode == "DEGENERATE":
            results = _design_degenerate_external(clean_seqs, num_pairs)
        elif mode == "TILED":
            results = _design_tiled_external(clean_seqs, num_pairs)
        else:
            raise ValueError(f"Unknown design mode: {mode}")
    else:
        # Pure Python fallback
        results = _fallback_design_pcr(
            clean_seqs, num_pairs=num_pairs,
            prod_min=prod_min, prod_max=prod_max,
            mode=mode
        )

    return results


def design_from_fasta(
    fasta_path: Path,
    mode: str = "PCR",
    num_pairs: int = 5,
    prod_min: int = 250,
    prod_max: int = 1000,
    do_align: bool = True,
    aligner: str = "auto",
) -> List[Dict]:
    """Design primers from a FASTA file."""
    from Bio import SeqIO
    
    sequences = []
    for record in SeqIO.parse(str(fasta_path), "fasta"):
        sequences.append(str(record.seq))
    
    if not sequences:
        return []
    
    return design_from_sequences(
        sequences, mode=mode, num_pairs=num_pairs,
        prod_min=prod_min, prod_max=prod_max,
        do_align=do_align, aligner=aligner
    )


def _design_degenerate_external(sequences: List[str], num_pairs: int) -> List[Dict]:
    """Try varVAMP for degenerate primer design. Falls back to PCR mode."""
    varvamp = shutil.which("varvamp")
    if not varvamp:
        # Fallback: use PCR mode but flag as degenerate candidate
        s2 = _import_step2()
        results = s2.design_primers(sequences, num_pairs=num_pairs)
        for r in results:
            r["Method"] = "PCR_fallback_DEGENERATE"
        return results
    
    # Write sequences to temp FASTA, run varvamp
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            fasta_in = Path(tmpdir) / "input.fasta"
            with open(fasta_in, 'w') as f:
                for i, s in enumerate(sequences):
                    f.write(f">seq_{i}\n{s}\n")
            
            outdir = Path(tmpdir) / "output"
            outdir.mkdir()
            
            result = subprocess.run(
                [varvamp, "single", str(fasta_in), "-o", str(outdir),
                 "--n-designs", str(num_pairs)],
                capture_output=True, text=True, timeout=600
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"varVAMP failed: {result.stderr[:500]}")
            
            # Parse varVAMP output
            return _parse_varvamp_output(outdir)
    except Exception:
        # Fallback
        s2 = _import_step2()
        results = s2.design_primers(sequences, num_pairs=num_pairs)
        for r in results:
            r["Method"] = "PCR_fallback_DEGENERATE"
        return results


def _design_tiled_external(sequences: List[str], num_pairs: int) -> List[Dict]:
    """Try Olivar for tiled amplicon design. Falls back to PCR mode."""
    olivar = shutil.which("olivar")
    if not olivar:
        s2 = _import_step2()
        results = s2.design_primers(sequences, num_pairs=num_pairs*2, prod_min=200, prod_max=500)
        for i, r in enumerate(results):
            r["Method"] = "PCR_fallback_TILED"
            r["Tile_ID"] = i + 1
        return results[:num_pairs*2]
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            fasta_in = Path(tmpdir) / "input.fasta"
            with open(fasta_in, 'w') as f:
                for i, s in enumerate(sequences):
                    f.write(f">seq_{i}\n{s}\n")
            
            out_csv = Path(tmpdir) / "olivar_output.csv"
            result = subprocess.run(
                [olivar, "design", str(fasta_in), "-o", str(out_csv),
                 "--max-amplicon-length", "500"],
                capture_output=True, text=True, timeout=600
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Olivar failed: {result.stderr[:500]}")
            
            return _parse_olivar_output(out_csv)
    except Exception:
        s2 = _import_step2()
        results = s2.design_primers(sequences, num_pairs=num_pairs*2, prod_min=200, prod_max=500)
        for i, r in enumerate(results):
            r["Method"] = "PCR_fallback_TILED"
            r["Tile_ID"] = i + 1
        return results[:num_pairs*2]


def _parse_varvamp_output(outdir: Path) -> List[Dict]:
    """Parse varVAMP single-mode output TSV."""
    results = []
    tsv_files = sorted(outdir.glob("*.tsv"))
    if not tsv_files:
        return results
    
    import csv
    for tsv in tsv_files:
        with open(tsv) as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                results.append({
                    "Fwd_Seq": row.get("fwd_primer", row.get("primer_fwd", "")),
                    "Rev_Seq": row.get("rev_primer", row.get("primer_rev", "")),
                    "Fwd_Tm": float(row.get("fwd_tm", 0)),
                    "Rev_Tm": float(row.get("rev_tm", 0)),
                    "Product": int(row.get("product_size", 0)),
                    "GC_Fwd": round(float(row.get("fwd_gc", 50)), 1),
                    "GC_Rev": round(float(row.get("rev_gc", 50)), 1),
                    "Penalty": float(row.get("penalty", 10)),
                    "Method": "varVAMP",
                    "Probe_Seq": "",
                    "Probe_Tm": 0,
                })
    return results


def _parse_olivar_output(csv_path: Path) -> List[Dict]:
    """Parse Olivar tiled output CSV."""
    import csv
    results = []
    if not csv_path.exists():
        return results
    
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                "Fwd_Seq": row.get("forward_primer", row.get("fwd", "")),
                "Rev_Seq": row.get("reverse_primer", row.get("rev", "")),
                "Fwd_Tm": float(row.get("fwd_tm", 0)),
                "Rev_Tm": float(row.get("rev_tm", 0)),
                "Product": int(row.get("amplicon_size", row.get("product_size", 0))),
                "GC_Fwd": round(float(row.get("fwd_gc", 50)), 1),
                "GC_Rev": round(float(row.get("rev_gc", 50)), 1),
                "Penalty": float(row.get("penalty", 10)),
                "Method": "Olivar",
                "Probe_Seq": "",
                "Probe_Tm": 0,
                "Tile_ID": int(row.get("tile_id", row.get("amplicon_id", 1))),
            })
    return results


# ======================================================================
# Pure Python fallback (when primer3-py is unavailable)
# ======================================================================

def _est_tm_simple(seq):
    """Wallace rule Tm estimate (2°C for A/T, 4°C for G/C)."""
    clean = ''.join(c for c in seq.upper() if c in 'ATGC')
    if len(clean) < 14:
        return 2 * (clean.count('A') + clean.count('T')) + 4 * (clean.count('G') + clean.count('C'))
    # NN approximation
    gc = clean.count('G') + clean.count('C')
    return 64.9 + 41 * (gc - 16.4) / max(len(clean), 1)


def _gc_pct(seq):
    """GC percentage."""
    clean = ''.join(c for c in seq.upper() if c in 'ATGC')
    if not clean:
        return 50.0
    return (clean.count('G') + clean.count('C')) / len(clean) * 100


def _fallback_design_pcr(sequences, num_pairs=5, prod_min=250, prod_max=1000, mode="PCR"):
    """
    Pure Python primer design without primer3 dependency.
    Uses a sliding-window k-mer approach with basic quality filters:
      - GC 40-60%
      - Tm 52-62°C
      - 3' GC clamp (last 5bp: 1-3 G/C)
      - No poly-X >5
      - Product size in range
      - Tm difference <= 3°C
    """
    from Bio.Seq import Seq
    
    ref = sequences[0].replace('-', '')
    if not ref:
        return []
    
    L = len(ref)
    candidates = []
    
    # Collect candidate primers
    for pos in range(0, L - 23, 3):
        for plen in [19, 20, 21, 22]:
            if pos + plen > L:
                break
            oligo = ref[pos:pos + plen]
            if any(c not in 'ATGC' for c in oligo):
                continue
            
            gc = _gc_pct(oligo)
            if gc < 40 or gc > 60:
                continue
            
            tm = _est_tm_simple(oligo)
            if tm < 52 or tm > 62:
                continue
            
            # 3' GC clamp: last 5bp has 1-3 G/C
            gc_end = oligo[-5:].count('G') + oligo[-5:].count('C')
            if gc_end < 1 or gc_end > 3:
                continue
            
            # Poly-X check
            if any(nt * 6 in oligo for nt in 'ATGC'):
                continue
            
            candidates.append({
                "pos": pos, "len": plen, "seq": oligo,
                "gc": gc, "tm": tm
            })
    
    if not candidates:
        return []
    
    # Pair candidates
    results = []
    seen = set()
    for f in candidates:
        for r in candidates:
            if f["pos"] >= r["pos"]:
                continue
            
            ps = r["pos"] + r["len"] - f["pos"]
            if ps < prod_min or ps > prod_max:
                continue
            
            if abs(f["tm"] - r["tm"]) > 3:
                continue
            
            # Amplicon GC check
            amp_seq = ref[f["pos"]:r["pos"] + r["len"]]
            amp_gc = _gc_pct(amp_seq)
            if amp_gc < 40 or amp_gc > 60:
                continue
            
            # Spatial dedup: same 50bp grid
            rk = (f["pos"] // 50, r["pos"] // 50)
            if rk in seen:
                continue
            seen.add(rk)
            
            rev_seq = str(Seq(r["seq"]).reverse_complement())
            
            # Composite penalty
            tm_score = abs(f["tm"] - 60) + abs(r["tm"] - 60)
            gc_score = abs(f["gc"] - 50) * 0.5 + abs(r["gc"] - 50) * 0.5
            size_score = abs(f["len"] - 21) * 0.3 + abs(r["len"] - 21) * 0.3
            penalty = round(tm_score + gc_score + size_score, 2)
            
            method = f"Simple_Thermo_{mode}"
            
            results.append({
                "Fwd_Seq": f["seq"],
                "Rev_Seq": rev_seq,
                "Fwd_Tm": round(f["tm"], 1),
                "Rev_Tm": round(r["tm"], 1),
                "Fwd_Start": f["pos"] + 1,
                "Rev_Start": r["pos"] + 1,
                "Product": ps,
                "GC_Fwd": round(f["gc"], 1),
                "GC_Rev": round(r["gc"], 1),
                "Penalty": penalty,
                "Method": method,
                "Probe_Seq": "",
                "Probe_Tm": 0,
            })
            
            if len(results) >= num_pairs * 5:
                break
        if len(results) >= num_pairs * 5:
            break
    
    # Sort by penalty, return top N
    results.sort(key=lambda x: x["Penalty"])
    
    # Spatial diversity filter
    diverse = []
    for p in results:
        mid = (p.get("Fwd_Start", 0) + p.get("Rev_Start", 0)) / 2
        if all(abs(mid - (d.get("Fwd_Start", 0) + d.get("Rev_Start", 0)) / 2) >= max(prod_min // 4, 60)
               for d in diverse):
            diverse.append(p)
            if len(diverse) >= num_pairs:
                break
    
    return diverse[:num_pairs] if diverse else results[:num_pairs]


# ======================================================================
# Job Manager
# ======================================================================

class DesignJobManager:
    """
    Manages background primer design jobs.
    
    Each job is a subprocess that runs step2 for a single FASTA input.
    Status and results are stored in per-job directories.
    
    Args:
        jobs_dir: Directory for job storage (default: ./design_jobs/)
        species_fasta_dir: Directory with per-species FASTA files from step1
    """
    
    def __init__(
        self,
        jobs_dir: Path = None,
        species_fasta_dir: Path = None
    ):
        self.jobs_dir = Path(jobs_dir) if jobs_dir else Path("design_jobs")
        self.species_dir = Path(species_fasta_dir) if species_fasta_dir else _SPLIT_SPECIES_DIR
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
    def submit(
        self,
        fasta_path: Path = None,
        sequences: List[str] = None,
        species_name: str = None,
        design_mode: str = "PCR",
        num_pairs: int = 5,
        prod_min: int = 250,
        prod_max: int = 1000,
        do_align: bool = True,
        aligner: str = "auto",
    ) -> str:
        """
        Submit a design job. Returns job_id.
        
        Three modes:
          1. fasta_path: Design from uploaded FASTA file
          2. sequences: Design from list of sequences directly
          3. species_name: Design for known species (reads from species_fasta_dir)
        """
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine input FASTA
        if sequences:
            input_fasta = job_dir / "input.fasta"
            with open(input_fasta, 'w') as f:
                for i, s in enumerate(sequences):
                    f.write(f">seq_{i}\n{s.strip().upper().replace('U', 'T')}\n")
            source = "upload"
            sp_name = species_name or "custom_input"
        elif species_name and self.species_dir.exists():
            # Look for species FASTA
            candidate = self.species_dir / f"{species_name}.fasta"
            if not candidate.exists():
                # Try to match by partial name
                matches = sorted(self.species_dir.glob(f"*{species_name[:30]}*.fasta"))
                candidate = matches[0] if matches else None
            if not candidate or not candidate.exists():
                raise FileNotFoundError(
                    f"No FASTA found for species '{species_name}' in {self.species_dir}"
                )
            input_fasta = candidate
            source = "known_species"
            sp_name = species_name
        elif fasta_path and fasta_path.exists():
            input_fasta = fasta_path
            source = "upload"
            sp_name = species_name or fasta_path.stem
        else:
            raise ValueError("Must provide fasta_path, sequences, or species_name")
        
        # Create job record
        job = DesignJob(
            job_id=job_id,
            status="pending",
            design_mode=design_mode,
            species_name=sp_name,
            num_pairs=num_pairs,
            fasta_source=source,
            input_fasta=str(input_fasta),
            output_dir=str(job_dir),
        )
        
        # Save job metadata
        with open(job_dir / "job.json", 'w') as f:
            json.dump(asdict(job), f, indent=2, ensure_ascii=False)
        
        # Launch in background thread
        thread = threading.Thread(
            target=self._run_design,
            args=(job, prod_min, prod_max, do_align, aligner),
            daemon=True
        )
        thread.start()
        
        return job_id
    
    def status(self, job_id: str) -> Optional[Dict]:
        """Get job status. Returns None if job not found."""
        job_file = self.jobs_dir / job_id / "job.json"
        if not job_file.exists():
            return None
        
        try:
            with open(job_file) as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, FileNotFoundError):
            # File being written — return a minimal status
            return {
                "job_id": job_id,
                "status": "pending",
                "progress_msg": "Initializing...",
                "progress_pct": 0
            }
    
    def results(self, job_id: str) -> Optional[List[Dict]]:
        """Get design results. Returns None if not completed or not found."""
        status = self.status(job_id)
        if not status or status["status"] != "completed":
            return None
        
        results_file = Path(status.get("results_json", ""))
        if not results_file.exists():
            results_file = self.jobs_dir / job_id / "results.json"
        
        if results_file.exists():
            with open(results_file) as f:
                return json.load(f)
        return None
    
    def results_tsv(self, job_id: str) -> Optional[str]:
        """Get results as TSV string."""
        status = self.status(job_id)
        if not status or status["status"] != "completed":
            return None
        
        tsv_file = Path(status.get("results_tsv", ""))
        if not tsv_file.exists():
            tsv_file = self.jobs_dir / job_id / "results.tsv"
        
        if tsv_file.exists():
            return tsv_file.read_text(encoding='utf-8')
        return None
    
    def list_jobs(self, limit: int = 50) -> List[Dict]:
        """List recent jobs."""
        jobs = []
        for job_dir in sorted(
            self.jobs_dir.iterdir(),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        ):
            if not job_dir.is_dir():
                continue
            job_file = job_dir / "job.json"
            if job_file.exists():
                with open(job_file) as f:
                    jobs.append(json.load(f))
            if len(jobs) >= limit:
                break
        return jobs
    
    def list_known_species(self, query: str = "", limit: int = 100) -> List[Dict]:
        """List known virus species with FASTA files available for design."""
        species_list = []
        if not self.species_dir.exists():
            return species_list
        
        ql = query.lower().strip()
        for fa in sorted(self.species_dir.glob("*.fasta")):
            sp_name = fa.stem
            if ql and ql not in sp_name.lower():
                continue
            
            # Count sequences in FASTA
            try:
                from Bio import SeqIO
                n_seqs = sum(1 for _ in SeqIO.parse(str(fa), "fasta"))
            except Exception:
                n_seqs = 0
            
            species_list.append({
                "species_name": sp_name,
                "n_sequences": n_seqs,
                "fasta_path": str(fa),
                "file_size_kb": round(fa.stat().st_size / 1024, 1),
            })
            
            if len(species_list) >= limit:
                break
        
        return species_list
    
    def _run_design(self, job: DesignJob, pmin: int, pmax: int,
                    do_align: bool, aligner: str):
        """Run design in background, update job status."""
        job_dir = Path(job.output_dir)
        
        try:
            # Update status
            job.status = "running"
            job.progress_msg = "Loading sequences..."
            self._save_job(job)
            
            # Convert input FASTA to list of sequences
            from Bio import SeqIO
            sequences = [
                str(r.seq).upper().replace('U', 'T')
                for r in SeqIO.parse(job.input_fasta, "fasta")
            ]
            
            if not sequences:
                raise ValueError("No sequences found in input FASTA")
            
            job.progress_msg = f"Designing {job.design_mode} primers for {len(sequences)} sequences..."
            job.progress_pct = 30
            self._save_job(job)
            
            # Run design
            results = design_from_sequences(
                sequences=sequences,
                mode=job.design_mode,
                num_pairs=job.num_pairs,
                prod_min=pmin,
                prod_max=pmax,
                do_align=do_align,
                aligner=aligner
            )
            
            job.progress_pct = 80
            job.progress_msg = f"Designed {len(results)} primer pairs. Saving..."
            self._save_job(job)
            
            # Add species info to each result
            for r in results:
                r["Species"] = job.species_name
                r["Type"] = job.design_mode
                r.setdefault("Fwd_Start", 0)
                r.setdefault("Rev_Start", 0)
                r.setdefault("Probe_Seq", "")
                r.setdefault("Probe_Tm", 0)
                r.setdefault("Tile_ID", 0)
            
            # Save results
            results_json = job_dir / "results.json"
            with open(results_json, 'w') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            # Save TSV
            results_tsv = job_dir / "results.tsv"
            self._write_tsv(results, results_tsv)
            
            # Complete
            job.status = "completed"
            job.progress_pct = 100
            job.progress_msg = "Complete"
            job.primer_count = len(results)
            job.completed_at = datetime.now().isoformat()
            job.results_json = str(results_json)
            job.results_tsv = str(results_tsv)
            self._save_job(job)
            
        except Exception as e:
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.progress_msg = job.error
            self._save_job(job)
    
    def _write_tsv(self, results: List[Dict], path: Path):
        """Write results as TSV compatible with step4 import."""
        if not results:
            return
        
        # Collect all keys
        all_keys = list(results[0].keys())
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            f.write('\t'.join(all_keys) + '\n')
            for r in results:
                f.write('\t'.join(str(r.get(k, '')) for k in all_keys) + '\n')
    
    def _save_job(self, job: DesignJob):
        """Thread-safe atomic save of job metadata."""
        import tempfile
        job_file = Path(job.output_dir) / "job.json"
        # Atomic write: write to temp then rename
        with self._lock:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=job_file.parent, suffix='.json', prefix='.tmp_job_'
            )
            try:
                with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                    json.dump(asdict(job), f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, job_file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise


# ======================================================================
# Quick test
# ======================================================================

if __name__ == "__main__":
    # Test with a simple sequence
    test_seq = (
        "ATGGCTAGCGCTAGCGCTAGCTAGCATCGATCGATCGTAGCTAGCTAGCTGATCGTAGCTAGCTAGCT"
        "AGCATCGATCGTACGATCGATCGATCGTACGATCGATCGTAGCTAGCATCGATCGTACGATCGATCGT"
        "ATCGATCGTAGCTAGCATCGATCGATCGTACGATCGATCGTAGCTAGCATCGATCGTACGATCGATCG"
        "TAGCTAGCATCGATCGTACGATCGATCGTAGCTAGCATCGATCGTACGATCGATCGTAGCTAGCATCG"
        "ATCGTACGATCGATCGTAGCTAGCATCGATCGTACGATCGATCGTAGCTAGCATCGATCGTACGATCG"
        "ATCGTAGCTAGCATCGATCGTACGATCGATCGTAGCTAGCATCGATCGTACGATCGATCGTAGCTA"
    )
    
    results = design_from_sequences([test_seq], mode="PCR", num_pairs=3)
    print(f"Designed {len(results)} primer pairs:")
    for i, r in enumerate(results):
        print(f"  Pair {i+1}: Fwd={r['Fwd_Seq']}, Rev={r['Rev_Seq']}, "
              f"Product={r['Product']}bp, Penalty={r['Penalty']}")
