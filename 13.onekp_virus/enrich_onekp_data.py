#!/usr/bin/env python3
"""
Enrich 1KP virus detection data with host plant metadata.

Inputs:
  - results/onekp/all_viruses.best.summary.tsv  (virus detection, UTF-16-LE)
  - results/onekp/high_conf.summary.tsv
  - results/onekp/onekp_download_links.csv      (Sample Code → SRA accession)
  - results/onekp/onekp_all_samples.csv          (Sample Code → host metadata)

Outputs:
  - .cache/onekp_enriched.pkl  (pickle cache for Dash)
"""

import pandas as pd
import pickle, os, re, json

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(os.path.dirname(BASE), "results", "onekp")
CACHE_DIR = os.path.join(BASE, ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

ENC = "utf-16-le"

print("1. Loading virus detection data...")
raw = pd.read_csv(os.path.join(RESULTS, "all_viruses.best.summary.tsv"),
                  sep="\t", encoding=ENC, low_memory=False)
hc = pd.read_csv(os.path.join(RESULTS, "high_conf.summary.tsv"),
                 sep="\t", encoding=ENC, low_memory=False)
disc = pd.read_csv(os.path.join(RESULTS, "high_conf.summary.discarded.tsv"),
                   sep="\t", encoding=ENC, low_memory=False)
print(f"   raw: {len(raw)} records, hc: {len(hc)}, discarded: {len(disc)}")

# 2. Load sample metadata
print("\n2. Loading host metadata...")
links = pd.read_csv(os.path.join(RESULTS, "onekp_download_links.csv"),
                    encoding="utf-16-le")
samples = pd.read_csv(os.path.join(RESULTS, "onekp_all_samples.csv"),
                      encoding="utf-16-le")
print(f"   download_links: {len(links)} rows, columns: {list(links.columns)}")
print(f"   all_samples: {len(samples)} rows, columns: {list(samples.columns)}")

# 3. Build SRA accession → host info mapping
print("\n3. Building accession→host mapping...")

# Extract SRA/ERA accession from SRA Download URL
def extract_acc(url):
    if pd.isna(url):
        return None
    m = re.search(r'/([EDS]RR\d+)/', str(url))
    return m.group(1) if m else None

links["accession"] = links["SRA Download"].apply(extract_acc)
acc_to_code = dict(zip(links["accession"], links["Sample Code"]))
code_to_info = {}
for _, r in samples.iterrows():
    code = str(r.get("Sample Code", "")).strip()
    if code:
        code_to_info[code] = {
            "host_species": str(r.get("Species", "")),
            "host_clade": str(r.get("Clade", "")),
            "host_order": str(r.get("Order", "")),
            "host_family": str(r.get("Family", "")),
            "host_tissue": str(r.get("Tissue", "")),
            "is_mislabeled": str(r.get("Is Mislabeled", "No")),
        }

# Build full accession → host mapping
acc_to_host = {}
for acc, code in acc_to_code.items():
    if code in code_to_info:
        acc_to_host[acc] = code_to_info[code]

print(f"   Mapped {len(acc_to_host)} accessions to host info")
print(f"   Unmapped accessions in links: {sum(1 for a in acc_to_code if a not in acc_to_host)}")

# 4. Enrich virus detection data
print("\n4. Enriching virus data...")

def enrich(df, label):
    df = df.copy()
    df["host_species"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_species", ""))
    df["host_clade"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_clade", ""))
    df["host_order"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_order", ""))
    df["host_family"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_family", ""))
    df["host_tissue"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_tissue", ""))
    df["is_mislabeled"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("is_mislabeled", ""))

    n_mapped = (df["host_species"] != "").sum()
    print(f"   {label}: {n_mapped}/{len(df)} records matched to host metadata")
    return df

raw_e = enrich(raw, "raw")
hc_e = enrich(hc, "hc")
disc_e = enrich(disc, "discarded")

# 5. Host diversity stats
print("\n5. Host diversity summary...")
matched_samples = raw_e[raw_e["host_species"] != ""]["Sample"].unique()
print(f"   Infected samples with host info: {len(matched_samples)}")

# Clade-level virus prevalence
raw_e["Confidence"] = "Low"
hc_e["Confidence"] = "High"
all_e = pd.concat([raw_e[raw_e["host_species"] != ""]], ignore_index=True)

host_summary = {
    "total_host_species": int(all_e["host_species"].nunique()),
    "total_host_families": int(all_e["host_family"].nunique()),
    "total_host_orders": int(all_e["host_order"].nunique()),
    "total_host_clades": int(all_e["host_clade"].nunique()),
}

# Virus per clade
clade_virus = all_e.groupby("host_clade")["Adjusted_Species"].nunique().sort_values(ascending=False)
host_summary["virus_per_clade"] = [{"clade": k, "n_virus": int(v)} for k, v in clade_virus.head(15).items()]

# Top host families with virus detections
fam_count = all_e.groupby("host_family")["Sample"].nunique().sort_values(ascending=False)
host_summary["top_host_families"] = [{"family": k, "n_samples": int(v)} for k, v in fam_count.head(20).items()]

print(f"   {host_summary['total_host_species']} host species")
print(f"   {host_summary['total_host_families']} host families")
print(f"   {host_summary['total_host_clades']} host clades")

# 6. Save
print("\n6. Saving...")
cache = {
    "all_data": raw_e,
    "hc": hc_e,
    "discarded": disc_e,
    "host_summary": host_summary,
    "mapping_count": len(acc_to_host),
}

with open(os.path.join(CACHE_DIR, "onekp_enriched.pkl"), "wb") as f:
    pickle.dump(cache, f, protocol=2)  # protocol=2 for Python 3.8 compat

# Also save JSON summary
with open(os.path.join(CACHE_DIR, "onekp_host_summary.json"), "w", encoding="utf-8") as f:
    json.dump(host_summary, f, ensure_ascii=False, indent=2)

print(f"   Pickle: {os.path.getsize(os.path.join(CACHE_DIR, 'onekp_enriched.pkl')) / 1024:.0f} KB")
print(f"   JSON: {os.path.getsize(os.path.join(CACHE_DIR, 'onekp_host_summary.json')) / 1024:.0f} KB")
print("Done!")
