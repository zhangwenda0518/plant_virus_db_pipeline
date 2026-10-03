#!/usr/bin/env python3
import sys
# 极简 taxonkit 替身: 只实现本试验用到的两个子命令
if len(sys.argv) >= 2 and sys.argv[1] == "name2taxid":
    M = {"tomato": "4081", "Nicotiana tabacum": "4087", "Frankliniella occidentalis": "13946",
         "Homo sapiens": "9606", "Sarcina maxima": "52558"}
    for line in open(sys.argv[2], encoding="utf-8"):
        n = line.strip()
        print(f"{n}	{M.get(n, '')}")
elif len(sys.argv) >= 2 and sys.argv[1] == "lineage":
    FULL = {"4081": "cellular organisms;Eukaryota;Viridiplantae;Streptophyta;Magnoliopsida;Solanales;Solanaceae;Solanum;Solanum lycopersicum;syn",
            "4087": "cellular organisms;Eukaryota;Viridiplantae;Streptophyta;Magnoliopsida;Solanales;Solanaceae;Nicotiana;Nicotiana tabacum;syn",
            "13946": "cellular organisms;Eukaryota;Metazoa;Arthropoda;Insecta;Thysanoptera;Thripidae;Frankliniella;Frankliniella occidentalis;",
            "9606": "cellular organisms;Eukaryota;Opisthokonta;Metazoa;Chordata;Craniata;Vertebrata;Mammalia;Primates;Homo sapiens;",
            "52558": "cellular organisms;Bacteria;Bacillota;Clostridia;Eubacteriales;Clostridiaceae;Sarcina;Sarcina maxima;"}
    if "-n" in sys.argv:  # lineage -n: taxid, 全量lineage, name
        for line in open([a for a in sys.argv if a.endswith(".txt")][0], encoding="utf-8"):
            t = line.strip()
            if t in FULL: print(f"{t}	{FULL[t]}	name")
    else:                 # 旧版 C2 的用法: taxid, 全量lineage
        for line in open([a for a in sys.argv if a.endswith(".txt")][0], encoding="utf-8"):
            t = line.strip()
            if t in FULL: print(f"{t}	{FULL[t]}")
elif len(sys.argv) >= 2 and sys.argv[1] == "reformat":
    # 从 stdin 的 lineage 列(-i 2)截取 9 字段定长 (与真 reformat 的 rank 语义简化一致)
    FMT_IDX = {"{d}":1, "{K}":None, "{p}":None, "{c}":None, "{o}":None, "{f}":None, "{g}":-3, "{s}":-2, "{t}":-1}
    for line in sys.stdin:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2: continue
        lin = parts[1].split(";")
        # 9字段: d=Eukaryota/Bacteria; K=界; p..o=中间; g=倒数第3; s=倒数第2; t=倒数第1
        if lin[1] in ("Viridiplantae", "Fungi", "Metazoa") or lin[0] == "Eukaryota":
            d, K = lin[0], lin[1] if lin[1] not in ("Eukaryota",) else lin[1]
        else:
            d, K = lin[0], lin[1]
        nine = ";".join([lin[0], lin[1] if lin[1]!="Eukaryota" else lin[1], lin[2] if len(lin)>4 else "", lin[3] if len(lin)>5 else "", lin[4] if len(lin)>6 else "", lin[-3], lin[-2], lin[-1], ""])
        print(f"{parts[0]}	{parts[1] if len(parts)>2 else ''}	{parts[2] if len(parts)>2 else ''}	{nine}")
