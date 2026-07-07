#!/usr/bin/env python3
"""Download GenBank records for all plant virus accessions (RefSeq priority)."""

import json, os, csv, time, argparse
from pathlib import Path
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
FULL_TSV = "/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Full.Info.tsv"
GB_DIR = BASE / "genbank_records"


def load_species_accs(tsv_path):
    """Group accessions by ICTV species, prioritize RefSeq (NC_)."""
    species_accs = defaultdict(list)

    with open(tsv_path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            acc = row.get("Accession", "").strip()
            sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
            if acc and sp:
                species_accs[sp].append(acc)
            # Also add NCBI name if different from ICTV
            sp_ncbi = row.get("Species_NCBI", "").strip()
            if sp_ncbi and sp_ncbi != sp:
                species_accs[sp_ncbi].append(acc)

    # For each species, pick RefSeq first, then longest accession
    selected = {}
    for sp, accs in species_accs.items():
        refseq = [a for a in accs if a.startswith("NC_")]
        if refseq:
            selected[sp] = refseq[0]
        else:
            # Pick the first non-versioned or longest
            selected[sp] = max(accs, key=lambda a: (len(a), a))

    print(f"Loaded {len(species_accs)} species, selected {len(selected)} for download")
    return selected


def fetch_genbank(accession, rettype="gb"):
    """Download GenBank flat file."""
    acc_clean = accession.split(".")[0]
    params = {"db": "nuccore", "id": acc_clean, "rettype": rettype, "retmode": "text"}
    req = Request(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urlencode(params),
        headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"},
    )
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                if "Error" in text[:100] or "Bad Request" in text[:100]:
                    return None
                return text
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


def parse_features(text):
    """Quick feature extraction from GenBank flat file for genome plot."""
    features = []
    current_feat = None
    seq_len = 0
    seq_lines = []

    for line in text.split("\n"):
        # LOCUS line has length
        if line.startswith("LOCUS"):
            parts = line.split()
            if len(parts) >= 3:
                try:
                    seq_len = int(parts[2])
                except:
                    pass
        # Feature lines
        if line.startswith("     gene") or line.startswith("     CDS") or line.startswith("     source"):
            current_feat = {"type": line.strip().split()[0], "lines": [line.strip()]}
            features.append(current_feat)
        elif current_feat and line.startswith("                     /"):
            current_feat["lines"].append(line.strip())
        elif not line.startswith("     ") and not line.startswith("  "):
            current_feat = None
        # Sequence
        if line.startswith("ORIGIN"):
            current_feat = None
        elif line.startswith("//"):
            current_feat = None
        elif line.startswith("         "):
            seq_lines.append(line[10:].replace(" ", "").strip())

    return features, seq_len


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tsv", default=FULL_TSV)
    p.add_argument("--max", type=int, default=1000)
    p.add_argument("--output-dir", default=str(GB_DIR))
    p.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY", ""))
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    species_accs = load_species_accs(args.tsv)

    # Limit to top N species by alphabetical order (diverse sampling)
    selected = dict(sorted(species_accs.items())[:args.max])
    total = len(selected)

    # Load existing downloads
    done = set()
    for f in Path(args.output_dir).glob("*.gb"):
        done.add(f.stem)

    print(f"Already downloaded: {len(done)}")
    to_download = [(sp, acc) for sp, acc in selected.items() if sp not in done]
    print(f"To download: {len(to_download)}")

    success = 0
    for i, (sp, acc) in enumerate(to_download):
        if i % 50 == 0 and i > 0:
            print(f"  Progress: {i}/{len(to_download)} ({success} success)")
        gb_text = fetch_genbank(acc)
        if gb_text:
            # Sanitize species name for filesystem
            safe_sp = sp.replace("/", "_").replace("\\", "_").replace(":", "_")
            out_path = os.path.join(args.output_dir, f"{safe_sp}.gb")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(gb_text)
            success += 1
        else:
            print(f"  Failed: {sp} ({acc})")
        if i % 5 == 0:
            time.sleep(0.3)  # NCBI rate limit

    # Also save a summary JSON for quick lookup
    summary = {}
    for f in Path(args.output_dir).glob("*.gb"):
        sp = f.stem
        text = f.read_text(encoding="utf-8", errors="replace")
        feats, seq_len = parse_features(text)
        # Extract organism and accession
        acc_line = ""
        org_line = ""
        for line in text.split("\n")[:10]:
            if line.startswith("ACCESSION"):
                acc_line = line[12:].strip()
            elif line.startswith("  ORGANISM"):
                org_line = line[12:].strip()
        summary[sp] = {
            "accession": acc_line,
            "organism": org_line,
            "genome_len": seq_len,
            "feature_count": len(feats),
            "file": str(f),
        }

    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nDone: {success} downloaded, {len(summary)} total records")
    print(f"Summary: {os.path.join(args.output_dir, 'summary.json')}")


if __name__ == "__main__":
    main()
