#!/usr/bin/env python3
"""Build local annotation files for each Plant_Virus_Ref accession.

For each reference accession:
  genbank_records/<species>/
    ├── <acc>_genome.fasta   # Full genome sequence
    ├── <acc>_cds.fasta      # CDS nucleotide
    ├── <acc>_protein.fasta  # Translated protein
    ├── <acc>.gff3           # Gene annotation
    └── <acc>.gb             # Raw GenBank record

Segmented viruses: multiple accessions under one species dir.
"""

import os, csv, re, time, gzip
from pathlib import Path
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.parse import urlencode

REF_TSV = "/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Ref.Info.tsv"
GB_DIR = Path("/opt/plant_virus_db/plant_virus_db_pipeline/7.literature_tracker/genbank_records")
GENOME_DIR = Path("/opt/plant_virus_db/plant_virus_db_pipeline/genome_annotations")


def load_ref_accs():
    """Load reference accessions grouped by species."""
    species_accs = defaultdict(list)  # species_name -> [(acc, seg, row)]
    with open(REF_TSV, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            acc = row.get("Accession", "").strip()
            sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
            seg = row.get("Segment", "").strip()
            if acc and sp:
                species_accs[sp].append((acc, seg, row))
    return species_accs


def sanitize(name):
    return name.replace("/", "_").replace("\\", "_").replace(":", "_")


def fetch_genbank(accession):
    """Download GenBank flat file from NCBI."""
    acc_clean = accession.split(".")[0]
    params = {"db": "nuccore", "id": acc_clean, "rettype": "gb", "retmode": "text"}
    req = Request(
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{urlencode(params)}",
        headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"},
    )
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                if "Error" in text[:50]:
                    return None
                return text
        except:
            if attempt < 2: time.sleep(2 ** attempt)
    return None


def fetch_fasta(accession, rettype="fasta"):
    """Download FASTA from NCBI."""
    acc_clean = accession.split(".")[0]
    params = {"db": "nuccore", "id": acc_clean, "rettype": rettype, "retmode": "text"}
    req = Request(
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{urlencode(params)}",
        headers={"User-Agent": "PlantVirusDB/1.0 (x@x.com)"},
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except:
        return None


def genbank_to_gff3(gb_text, source="GenBank"):
    """Convert GenBank features to GFF3 format."""
    lines = ["##gff-version 3"]
    seqid = ""
    current_feat = None
    feats = []

    for line in gb_text.split("\n"):
        if line.startswith("VERSION"):
            seqid = line[12:].strip().split()[0]
        elif line.startswith("     gene") or line.startswith("     CDS"):
            parts = line.strip().split()
            current_feat = {"type": parts[0], "position": ""}
            # Extract position
            m = re.search(r"(\d+\.\.\d+)", line)
            if m: current_feat["position"] = m.group(1)
            m = re.search(r"complement\((\d+\.\.\d+)\)", line)
            if m: current_feat["position"] = m.group(1); current_feat["strand"] = "-"
            if "strand" not in current_feat: current_feat["strand"] = "+"
            current_feat["attrs"] = []
            feats.append(current_feat)
        elif current_feat and line.startswith("                     /"):
            current_feat["attrs"].append(line.strip())

    for feat in feats:
        pos = feat.get("position", "1..1")
        parts = pos.split("..")
        start, end = parts[0], parts[1] if len(parts) > 1 else parts[0]

        tags = {}
        for attr in feat["attrs"]:
            m = re.search(r'/(\w+)="([^"]*)"', attr)
            if m: tags[m.group(1)] = m.group(2)

        product = tags.get("product", tags.get("note", feat["type"]))
        locus = tags.get("locus_tag", "")
        attrs_str = f"ID={feat['type']}_{start}_{end};product={product}"
        if locus: attrs_str += f";locus_tag={locus}"
        if tags.get("protein_id"): attrs_str += f";protein_id={tags['protein_id']}"

        lines.append(f"{seqid}\tGenBank\t{feat['type']}\t{start}\t{end}\t.\t{feat['strand']}\t.\t{attrs_str}")

    return "\n".join(lines)


def build_for_accession(acc, species, out_dir):
    """Build all annotation files for one accession."""
    acc_clean = acc.split(".")[0]
    os.makedirs(out_dir, exist_ok=True)

    # Check if already built
    existing = list(out_dir.glob(f"{acc_clean}_*")) + list(out_dir.glob(f"{acc_clean}.*"))
    gb_existing = list(out_dir.glob(f"*.gb"))
    if len(existing) >= 4 and gb_existing:
        return True  # Already done

    # 1. GenBank record
    gb_path = out_dir / f"{acc_clean}.gb"
    gb_text = None
    if not gb_path.exists():
        gb_text = fetch_genbank(acc)
        if gb_text:
            gb_path.write_text(gb_text, encoding="utf-8")
    else:
        gb_text = gb_path.read_text(encoding="utf-8", errors="replace")

    if not gb_text:
        return False

    # 2. Genome FASTA
    genome_path = out_dir / f"{acc_clean}_genome.fasta"
    if not genome_path.exists():
        fa = fetch_fasta(acc, "fasta")
        if fa:
            genome_path.write_text(fa, encoding="utf-8")

    # 3. CDS FASTA
    cds_path = out_dir / f"{acc_clean}_cds.fasta"
    if not cds_path.exists():
        cds = fetch_fasta(acc, "fasta_cds_na")
        if cds:
            cds_path.write_text(cds, encoding="utf-8")

    # 4. Protein FASTA
    prot_path = out_dir / f"{acc_clean}_protein.fasta"
    if not prot_path.exists():
        prot = fetch_fasta(acc, "fasta_cds_aa")
        if prot:
            prot_path.write_text(prot, encoding="utf-8")

    # 5. GFF3
    gff3_path = out_dir / f"{acc_clean}.gff3"
    if not gff3_path.exists() and gb_text:
        gff3 = genbank_to_gff3(gb_text)
        gff3_path.write_text(gff3, encoding="utf-8")

    return True


def main():
    species_accs = load_ref_accs()
    print(f"Species: {len(species_accs)}, Total accs: {sum(len(v) for v in species_accs.values())}")

    # Count missing
    missing = 0
    for sp, accs in sorted(species_accs.items()):
        safe_sp = sanitize(sp)
        # Check if we have GB files already (old naming by species)
        old_gb = GB_DIR / f"{safe_sp}.gb"
        new_dir = GENOME_DIR / safe_sp

        if not new_dir.exists() and not old_gb.exists():
            missing += 1

    print(f"Species with no GB file: {missing}")

    success = 0
    for sp, accs in sorted(species_accs.items()):
        safe_sp = sanitize(sp)
        new_dir = GENOME_DIR / safe_sp

        # Check old GB file
        old_gb = GB_DIR / f"{safe_sp}.gb"
        if old_gb.exists() and not list(new_dir.glob("*.gb")):
            # Copy old GB to new location, rename to accession
            os.makedirs(new_dir, exist_ok=True)
            acc = accs[0][0].split(".")[0]
            old_text = old_gb.read_text(encoding="utf-8", errors="replace")
            (new_dir / f"{acc}.gb").write_text(old_text, encoding="utf-8")

        for acc, seg, row in accs:
            ok = build_for_accession(acc, sp, new_dir)
            if ok: success += 1

        if success % 100 == 0 and success > 0:
            print(f"  Progress: {success} accessions processed")

    print(f"\nDone: {success} accessions processed")

    # Stats
    dirs = list(GENOME_DIR.glob("*"))
    print(f"Species dirs: {len(dirs)}")
    gb_count = sum(1 for d in dirs for _ in d.glob("*.gb"))
    gff3_count = sum(1 for d in dirs for _ in d.glob("*.gff3"))
    print(f"GB files: {gb_count}, GFF3 files: {gff3_count}")


if __name__ == "__main__":
    main()
