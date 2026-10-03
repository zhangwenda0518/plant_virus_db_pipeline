#!/usr/bin/env python3
"""
1KP Transcriptome Virus Detection — 数据预处理
将服务器产出的 UTF-16 LE TSV 转为 pickle 缓存供 Dash 加载。
同时产出 summary JSON（KPI + Top lists）供静态展示。
"""

import pandas as pd
import pickle, json, os, sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(os.path.dirname(BASE), "results", "onekp")
CACHE_DIR = os.path.join(BASE, ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

ENCODING = "utf-16-le"

print("Loading raw TSVs...")
raw = pd.read_csv(os.path.join(RESULTS, "all_viruses.best.summary.tsv"),
                  sep="\t", encoding=ENCODING, low_memory=False)
hc = pd.read_csv(os.path.join(RESULTS, "high_conf.summary.tsv"),
                 sep="\t", encoding=ENCODING, low_memory=False)
disc = pd.read_csv(os.path.join(RESULTS, "high_conf.summary.discarded.tsv"),
                   sep="\t", encoding=ENCODING, low_memory=False)

# 加载样本资源表（服务器上的原始样本列表）
res_path = os.path.join(RESULTS, "sample_resource_usage.tsv")
if os.path.exists(res_path):
    sru = pd.read_csv(res_path, sep="\t", encoding=ENCODING, low_memory=False)
    total_samples = len(sru)
else:
    total_samples = raw["Sample"].nunique()

# ── 添加置信度标签 ──
raw["Confidence"] = "Low"
hc["Confidence"] = "High"
disc["Confidence"] = "Low"

# 合并全量数据（raw 包含 hc + disc）
all_data = raw.copy()

# ── 聚合统计 ──
summary = {
    "total_samples_in_run": int(total_samples),
    "infected_samples_raw": int(raw["Sample"].nunique()),
    "infected_samples_hc": int(hc["Sample"].nunique()),
    "virus_species_raw": int(raw["Adjusted_Species"].nunique()),
    "virus_species_hc": int(hc["Adjusted_Species"].nunique()),
    "records_raw": int(len(raw)),
    "records_hc": int(len(hc)),
    "records_discarded": int(len(disc)),
    "pipeline_runtime": "1h 56m 34s",
    "peak_memory_mb": 2069.7,
}

# Top viruses by sample count
def top_viruses(df, n=20):
    vc = df.groupby("Adjusted_Species")["Sample"].nunique().sort_values(ascending=False).head(n)
    return [{"virus": v, "samples": int(c)} for v, c in vc.items()]

summary["top_viruses_raw"] = top_viruses(raw, 20)
summary["top_viruses_hc"] = top_viruses(hc, 20)

# Molecule type distribution
def mol_types(df):
    mc = df["Molecule_type"].value_counts().to_dict()
    return {str(k): int(v) for k, v in mc.items()}

summary["molecule_types_raw"] = mol_types(raw)
summary["molecule_types_hc"] = mol_types(hc)

# Coverage & depth bins
cov_bins = [(0, 25), (25, 50), (50, 75), (75, 90), (90, 100)]
cov_labels = ["0-25%", "25-50%", "50-75%", "75-90%", "90-100%"]
raw_cov = pd.cut(raw["Rep_Coverage(%)"], bins=[b[0] for b in cov_bins] + [100],
                  labels=cov_labels, include_lowest=True).value_counts().sort_index()
summary["coverage_bins"] = [{"bin": str(k), "count": int(v)} for k, v in raw_cov.items()]

# Depth bins (log scale)
depth_bins = [(0, 1), (1, 5), (5, 10), (10, 50), (50, 100), (100, 500), (500, 5000), (5000, 50000)]
depth_labels = ["<1x", "1-5x", "5-10x", "10-50x", "50-100x", "100-500x", "500-5000x", ">5000x"]
raw_depth = pd.cut(raw["Rep_MeanDepth"], bins=[b[0] for b in depth_bins] + [float("inf")],
                    labels=depth_labels, include_lowest=True).value_counts().sort_index()
summary["depth_bins"] = [{"bin": str(k), "count": int(v)} for k, v in raw_depth.items()]

# ── 保存 ──
print("Saving pickle cache...")
with open(os.path.join(CACHE_DIR, "onekp_data.pkl"), "wb") as f:
    pickle.dump({
        "all_data": all_data,
        "hc": hc,
        "discarded": disc,
        "summary": summary,
    }, f, protocol=4)

print("Saving summary JSON...")
with open(os.path.join(CACHE_DIR, "onekp_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("Done!")
print(f"  Pickle: {os.path.getsize(os.path.join(CACHE_DIR, 'onekp_data.pkl')) / 1024:.0f} KB")
print(f"  JSON:   {os.path.getsize(os.path.join(CACHE_DIR, 'onekp_summary.json')) / 1024:.0f} KB")
print(f"\nSummary:")
for k, v in summary.items():
    if not isinstance(v, list) and not isinstance(v, dict):
        print(f"  {k}: {v}")
    elif isinstance(v, dict) and len(v) < 10:
        print(f"  {k}: {v}")
