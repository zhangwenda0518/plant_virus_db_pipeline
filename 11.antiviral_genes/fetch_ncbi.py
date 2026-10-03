"""
Fetch plant antiviral genes from NCBI using Entrez queries.
Downloads Gene (tabular), Nucleotide (FASTA), Protein (FASTA).
"""
import os, time
from Bio import Entrez

# NCBI requires a contact email for Entrez; keep it out of the source tree.
Entrez.email = os.environ.get("NCBI_EMAIL", "")
if not Entrez.email:
    raise SystemExit("ERROR: NCBI_EMAIL environment variable not set "
                     "(NCBI Entrez policy requires a valid contact email).")

OUTDIR = os.path.dirname(__file__) + "/data"
os.makedirs(OUTDIR, exist_ok=True)

def search_and_fetch(db, query, max_records=5000):
    """Search NCBI and return all IDs."""
    print(f"\n=== Searching {db} ===")
    print(f"Query: {query[:100]}...")

    handle = Entrez.esearch(db=db, term=query, retmax=max_records, usehistory="y")
    results = Entrez.read(handle)
    handle.close()

    count = int(results["Count"])
    id_list = results["IdList"]
    print(f"Found: {count} records, got {len(id_list)} IDs")

    if count > len(id_list):
        print(f"Fetching remaining IDs via history (total: {count})...")
        # Use history to fetch all
        webenv = results["WebEnv"]
        query_key = results["QueryKey"]
        all_ids = []
        batch = 10000
        for start in range(0, count, batch):
            handle = Entrez.esearch(db=db, term=query, retmax=batch,
                                    retstart=start, usehistory="y",
                                    webenv=webenv, query_key=query_key)
            sub = Entrez.read(handle)
            handle.close()
            all_ids.extend(sub["IdList"])
            print(f"  Fetched {len(all_ids)}/{count} IDs", end="\r")
        print(f"\n  Total IDs fetched: {len(all_ids)}")
        return all_ids

    return id_list


# ===== 1. GENE DATABASE =====
GENE_QUERY = (
    '(("Viridiplantae"[Organism]) AND '
    '("antiviral"[Title/Abstract] OR "virus resistance"[Title/Abstract] OR '
    '"viral resistance"[Title/Abstract] OR "recessive resistance"[Title/Abstract])) '
    'AND "alive"[Status]'
)

gene_ids = search_and_fetch("gene", GENE_QUERY)

# Download Gene tabular data
if gene_ids:
    gene_file = os.path.join(OUTDIR, "plant_antiviral_genes.tsv")
    print(f"\nFetching gene summaries for {len(gene_ids)} IDs...")

    with open(gene_file, "w", encoding="utf-8") as f:
        # Header
        f.write("GeneID\tSymbol\tFullName\tSpecies\tChromosome\tMapLocation\tDescription\tGeneType\tNomenclatureStatus\tOtherDesignations\n")

        # Fetch in batches of 200
        batch_size = 200
        total = len(gene_ids)
        for i in range(0, total, batch_size):
            batch = gene_ids[i:i+batch_size]
            try:
                handle = Entrez.esummary(db="gene", id=",".join(batch))
                summaries = Entrez.read(handle)
                handle.close()

                for doc in summaries['DocumentSummarySet']['DocumentSummary']:
                    # Extract fields safely
                    uid = doc.get('Id', '')
                    name = doc.get('Name', '')
                    desc = doc.get('Description', '')
                    org = doc.get('Organism', {}).get('ScientificName', '')
                    chrom = doc.get('Chromosome', '')
                    maploc = doc.get('MapLocation', '')
                    gtype = doc.get('GeneType', '')
                    nstatus = doc.get('NomenclatureStatus', '')
                    other = doc.get('OtherDesignations', '')

                    row = "\t".join([
                        uid, name, desc, org, chrom, maploc,
                        "",  # truncated description
                        gtype, nstatus, other
                    ]).replace("\n", " ")
                    f.write(row + "\n")
                f.flush()
                print(f"  Downloaded {min(i+batch_size, total)}/{total} genes", end="\r")
            except Exception as e:
                print(f"\n  Error at batch {i}: {e}")
                time.sleep(5)
        print(f"\n  Done! Saved to {gene_file}")

    # Show sample
    print(f"\nSample records:")
    with open(gene_file, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i <= 5:
                print(f"  {line.strip()[:150]}")
    time.sleep(1)
else:
    print("No gene records found.")


# ===== 2. NUCLEOTIDE DATABASE =====
NUCL_QUERY = (
    '("Viridiplantae"[Organism]) AND '
    '("antiviral"[Title/Abstract] OR "virus resistance"[Title/Abstract] OR '
    '"immune receptor"[Title/Abstract]) AND '
    '(srcdb_refseq[Properties] AND "biomol mRNA"[Properties])'
)

nucl_ids = search_and_fetch("nucleotide", NUCL_QUERY, max_records=5000)

if nucl_ids:
    nucl_file = os.path.join(OUTDIR, "plant_antiviral_mRNA.fasta")
    print(f"\nFetching {len(nucl_ids)} nucleotide sequences...")

    with open(nucl_file, "w", encoding="utf-8") as f:
        batch_size = 200
        total = len(nucl_ids)
        for i in range(0, total, batch_size):
            batch = nucl_ids[i:i+batch_size]
            try:
                handle = Entrez.efetch(db="nucleotide", id=",".join(batch),
                                       rettype="fasta", retmode="text")
                f.write(handle.read())
                handle.close()
                f.flush()
                print(f"  Downloaded {min(i+batch_size, total)}/{total} sequences", end="\r")
                time.sleep(0.4)  # NCBI rate limit
            except Exception as e:
                print(f"\n  Error at batch {i}: {e}")
                time.sleep(5)
        print(f"\n  Done! Saved to {nucl_file}")

    # Count sequences
    with open(nucl_file) as f:
        seq_count = sum(1 for line in f if line.startswith(">"))
    print(f"  Sequences: {seq_count}")
    time.sleep(1)
else:
    print("No nucleotide records found.")


# ===== 3. PROTEIN DATABASE =====
PROT_QUERY = (
    '("Viridiplantae"[Organism]) AND '
    '("antiviral protein"[Title/Abstract] OR "virus resistance protein"[Title/Abstract] OR '
    '"silencing effector"[Title/Abstract]) AND '
    '"refseq"[Filter]'
)

prot_ids = search_and_fetch("protein", PROT_QUERY, max_records=5000)

if prot_ids:
    prot_file = os.path.join(OUTDIR, "plant_antiviral_proteins.fasta")
    print(f"\nFetching {len(prot_ids)} protein sequences...")

    with open(prot_file, "w", encoding="utf-8") as f:
        batch_size = 200
        total = len(prot_ids)
        for i in range(0, total, batch_size):
            batch = prot_ids[i:i+batch_size]
            try:
                handle = Entrez.efetch(db="protein", id=",".join(batch),
                                       rettype="fasta", retmode="text")
                f.write(handle.read())
                handle.close()
                f.flush()
                print(f"  Downloaded {min(i+batch_size, total)}/{total} sequences", end="\r")
                time.sleep(0.4)
            except Exception as e:
                print(f"\n  Error at batch {i}: {e}")
                time.sleep(5)
        print(f"\n  Done! Saved to {prot_file}")

    with open(prot_file) as f:
        seq_count = sum(1 for line in f if line.startswith(">"))
    print(f"  Sequences: {seq_count}")
else:
    print("No protein records found.")


# ===== SUMMARY =====
print("\n" + "=" * 60)
print("DOWNLOAD COMPLETE")
print("=" * 60)
for fname in os.listdir(OUTDIR):
    fpath = os.path.join(OUTDIR, fname)
    size_kb = os.path.getsize(fpath) / 1024
    print(f"  {fname}: {size_kb:.1f} KB")
