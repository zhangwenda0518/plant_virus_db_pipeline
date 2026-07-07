#!/usr/bin/env python3
"""
fetch_examples.py — 抓取全长 RefSeq 基因组作为 Metabuli 演示示例 → metabuli_examples.json

CP 基因太短(~300bp)分类不准，改用全长参考基因组。CMV 为三分体，取 3 条 RNA。
Mix = TMV + PVY + CMV(3 段) + PSTVd 全长混合。
"""
import json
import os
import time
import urllib.request

ACC = {
    "tmv":   ["NC_001367.1"],                              # Tobacco mosaic virus, 6395 bp
    "pvy":   ["NC_001616.1"],                              # Potato virus Y, 9704 bp
    "cmv":   ["NC_002034.1", "NC_002035.1", "NC_001440.1"],  # Cucumber mosaic virus RNA1/2/3
    "pstvd": ["NC_002030.1"],                              # Potato spindle tuber viroid, 359 bp
}
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id={}&rettype=fasta&retmode=text"


def fetch(acc):
    for _ in range(3):
        try:
            with urllib.request.urlopen(EFETCH.format(acc), timeout=30) as r:
                return r.read().decode("utf-8", "replace").strip()
        except Exception:
            time.sleep(2)
    return ""


def main():
    ex = {}
    for key, accs in ACC.items():
        parts = [fetch(a) for a in accs]
        ex[key] = "\n".join(p for p in parts if p)
        time.sleep(0.4)
    ex["mix"] = "\n".join(ex[k] for k in ["tmv", "pvy", "cmv", "pstvd"] if ex.get(k))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metabuli_examples.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(ex, f, ensure_ascii=False)
    print("wrote", out, {k: len(v) for k, v in ex.items()})


if __name__ == "__main__":
    main()
