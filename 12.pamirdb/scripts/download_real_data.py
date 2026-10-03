"""
PAmiRDB v4.1 — Real data downloader from miRBase and NCBI GenBank.

Downloads:
  1. miRBase mature miRNA sequences (all species → filter 7 plant species)
  2. Geminiviridae complete genomes from NCBI
  3. Potyviridae complete genomes from NCBI
  4. Virus-host data from Virus-Host DB

Strategy: try multiple mirrors; fall back to pre-filtered bundled data.
"""
import urllib.request
import gzip
import json
import os
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
MIRNA_DIR = DATA_DIR / "mirna"
VIRUS_DIR = DATA_DIR / "virus_genomes"
VH_DIR = DATA_DIR / "virus_host"

# Target 7 plant species (miRBase 3-letter codes)
TARGET_SPECIES = ['ath', 'gma', 'osa', 'sbi', 'sly', 'vvi', 'zma']

# Species name mapping
SPECIES_NAMES = {
    'ath': 'Arabidopsis thaliana', 'gma': 'Glycine max',
    'osa': 'Oryza sativa', 'sbi': 'Sorghum bicolor',
    'sly': 'Solanum lycopersicum', 'vvi': 'Vitis vinifera',
    'zma': 'Zea mays',
}


def download_mirbase_mature():
    """Download mature.fa from miRBase and filter for target species."""
    urls = [
        "https://www.mirbase.org/download/mature.fa",
        "https://mirbase.org/download/mature.fa",
        "ftp://mirbase.org/pub/mirbase/CURRENT/mature.fa",
    ]
    
    for url in urls:
        try:
            print(f"  Trying: {url}")
            req = urllib.request.Request(url, headers={
                'User-Agent': 'PAmiRDB/4.0 (bioinformatics; mailto:research@example.com)'
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
                # Check if gzipped
                if content[:2] == b'\x1f\x8b':
                    content = gzip.decompress(content)
                text = content.decode('utf-8', errors='replace')
                print(f"  Downloaded {len(text):,} chars")
                return text
        except Exception as e:
            print(f"  Failed: {e}")
            continue
    
    print("  All miRBase URLs failed. Using bundled representative data.")
    return None


def download_genbank_family(family_name: str, max_records: int = 50):
    """
    Download complete genome sequences for a virus family from NCBI.
    Uses NCBI Entrez API.
    """
    from urllib.parse import quote
    
    # Step 1: Search for accessions
    search_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        f"db=nucleotide&term={quote(family_name)}+complete+genome"
        f"&retmax={max_records}&retmode=json"
    )
    
    try:
        print(f"  Searching NCBI for {family_name}...")
        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'PAmiRDB/4.0 (mailto:research@example.com)'
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        id_list = data.get('esearchresult', {}).get('idlist', [])
        print(f"  Found {len(id_list)} records")
        
        if not id_list:
            return []
        
        # Step 2: Fetch summaries (FASTA)
        ids = ','.join(id_list[:max_records])
        fetch_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eu"
            f"tils/efetch.fcgi?db=nucleotide&id={ids}"
            f"&rettype=fasta&retmode=text"
        )
        
        print(f"  Fetching {len(id_list[:max_records])} sequences...")
        req = urllib.request.Request(fetch_url, headers={
            'User-Agent': 'PAmiRDB/4.0 (mailto:research@example.com)'
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            fasta_text = resp.read().decode('utf-8', errors='replace')
        
        # Parse FASTA
        records = _parse_fasta(fasta_text)
        print(f"  Parsed {len(records)} FASTA records")
        return records
        
    except Exception as e:
        print(f"  NCBI download failed: {e}")
        return []


def _parse_fasta(text: str) -> list:
    """Parse FASTA text into list of (header, sequence) tuples."""
    records = []
    current_header = None
    current_seq = []
    
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('>'):
            if current_header:
                records.append((current_header, ''.join(current_seq)))
            current_header = line[1:]
            current_seq = []
        elif line:
            current_seq.append(line)
    
    if current_header:
        records.append((current_header, ''.join(current_seq)))
    
    return records


def download_virushost_data():
    """Download virus-host relationships."""
    # Virus-Host DB provides a summary file
    urls = [
        "https://www.genome.jp/ftp/db/virushostdb/virushostdb.tsv",
        "https://www.genome.jp/virushostdb/summary.tsv",
    ]
    
    for url in urls:
        try:
            print(f"  Trying: {url}")
            req = urllib.request.Request(url, headers={
                'User-Agent': 'PAmiRDB/4.0'
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode('utf-8', errors='replace')
                print(f"  Downloaded {len(text):,} chars")
                return text
        except Exception as e:
            print(f"  Failed: {e}")
            continue
    
    return None


def process_mirbase_data(text: str) -> dict:
    """Filter miRBase mature.fa for target 7 species."""
    records = _parse_fasta(text)
    filtered = {}
    
    for header, seq in records:
        # miRBase headers: >ath-miR156a-5p MIMAT0000167 Arabidopsis thaliana ...
        parts = header.split()
        if not parts:
            continue
        mirna_id = parts[0]
        
        # Extract species prefix
        prefix = mirna_id.split('-')[0] if '-' in mirna_id else ''
        if prefix in TARGET_SPECIES:
            seq_clean = seq.upper().replace('T', 'U')
            if len(seq_clean) >= 18 and len(seq_clean) <= 26:  # typical miRNA length
                filtered[mirna_id] = {
                    "sequence": seq_clean,
                    "species_code": prefix,
                    "species_name": SPECIES_NAMES.get(prefix, prefix),
                    "length": len(seq_clean),
                }
    
    return filtered


def save_mirna_data(mirnas: dict):
    """Save miRNA data to FASTAs and JSON."""
    fasta_path = MIRNA_DIR / "plant_mirnas.fasta"
    json_path = MIRNA_DIR / "plant_mirnas.json"
    
    with open(fasta_path, 'w') as f:
        for mirna_id, info in sorted(mirnas.items()):
            f.write(f">{mirna_id} [{info['species_name']}]\n{info['sequence']}\n")
    
    with open(json_path, 'w') as f:
        json.dump(mirnas, f, indent=2)
    
    print(f"  Saved {len(mirnas)} miRNAs to {fasta_path.name} and {json_path.name}")


def save_virus_data(records: list, family: str):
    """Save virus genome data."""
    fasta_path = VIRUS_DIR / f"{family}.fasta"
    json_path = VIRUS_DIR / "viruses.json"
    
    # Append to fasta
    with open(fasta_path, 'w') as f:
        for header, seq in records:
            # Short ID from accession
            acc = header.split()[0] if header else "unknown"
            vid = acc.split('.')[0] if '.' in acc else acc[:15]
            name = ' '.join(header.split()[1:4]) if len(header.split()) > 1 else header[:50]
            f.write(f">{vid}|{acc}|{family}|{name}\n{seq}\n")
    
    # Update JSON metadata
    viruses = {}
    if json_path.exists():
        with open(json_path) as f:
            viruses = json.load(f)
    
    for header, seq in records:
        acc = header.split()[0] if header else "unknown"
        vid = acc.split('.')[0] if '.' in acc else acc[:15]
        name = ' '.join(header.split()[1:4]) if len(header.split()) > 1 else header[:50]
        viruses[vid] = {
            "accession": acc,
            "name": name[:100],
            "family": family,
            "genome_length": len(seq),
        }
    
    with open(json_path, 'w') as f:
        json.dump(viruses, f, indent=2)
    
    print(f"  Saved {len(records)} records to {fasta_path.name}")


def main():
    print("=" * 60)
    print("  PAmiRDB v4.1 — Real Data Download")
    print("=" * 60)
    
    # 1. miRBase
    print("\n[1/3] Downloading miRBase mature sequences...")
    mirbase_text = download_mirbase_mature()
    
    if mirbase_text:
        mirnas = process_mirbase_data(mirbase_text)
        print(f"  Filtered to {len(mirnas)} miRNAs from 7 target species")
        if len(mirnas) > 50:
            save_mirna_data(mirnas)
        else:
            print("  Too few miRNAs filtered. Keeping existing bundled data.")
    else:
        print("  miRBase download failed. Using existing bundled data.")
    
    # 2. GenBank virus genomes
    print("\n[2/3] Downloading virus genomes from NCBI...")
    
    for family in ['Geminiviridae', 'Potyviridae']:
        records = download_genbank_family(family, max_records=30)
        if records:
            save_virus_data(records, family.lower())
        else:
            print(f"  {family}: download failed, keeping existing data")
    
    # 3. Virus-Host DB
    print("\n[3/3] Downloading Virus-Host DB...")
    vh_text = download_virushost_data()
    if vh_text:
        vh_path = VH_DIR / "virus_host.tsv"
        with open(vh_path, 'w') as f:
            f.write(vh_text)
        print(f"  Saved virus-host data to {vh_path.name}")
    
    print("\n[OK] v4.1 data download complete")


if __name__ == '__main__':
    main()
