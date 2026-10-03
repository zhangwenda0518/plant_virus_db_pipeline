#!/bin/bash
# rebuild_kunpeng_db.sh — 从最新 Plant_Virus_Ref.fasta 重建 Kun-Peng 分类库
# 轻量快速（~1分钟），由 monthly_update.sh Phase 6 调用，也可手动执行。
set -e

REF_FASTA="/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Ref.fasta"
REF_INFO="/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Ref.Info.tsv"
TAXDIR="/opt/plant_virus_db/taxonomy"
KP_BIN="/opt/kunpeng/kp_centos7"
KP_DB="/opt/kunpeng/kp_db"
LINEAGE_OUT="/opt/plant_virus_db/plant_virus_db_pipeline/9.metabuli/taxid_lineage.tsv"
LOG_TAG="[kunpeng-rebuild]"
echo "$LOG_TAG $(date) start"

# 1. 重建 library（headers 带 taxid|）+ seqid2taxid.map + 刷新 taxonomy
LIB="$KP_DB/library/fna/library.fna"
rm -f "$LIB"
python3.8 - "$REF_INFO" "$REF_FASTA" "$LIB" "$KP_DB/seqid2taxid.map" << 'EOF'
import csv, os, sys
info_path, fasta_path, lib_path, map_path = sys.argv[1:5]
taxmap = {}
with open(info_path, encoding="utf-8", errors="replace") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        acc = (r.get("Accession") or "").strip().split(".")[0]
        tax = (r.get("Taxid") or "").strip()
        if acc and tax:
            taxmap[acc] = tax
name, buf, n = None, [], 0
with open(fasta_path, encoding="utf-8", errors="replace") as f, \
     open(lib_path, "w") as lib, open(map_path, "w") as mp:
    for line in f:
        if line.startswith(">"):
            if name:
                lib.write("".join(buf)); n += 1
            base = line[1:].strip().split()[0].split(".")[0]
            tax = taxmap.get(base, "")
            if tax:
                name = f"taxid|{tax} {base}"
                mp.write(f"{name}\t{tax}\n")
                buf = [line]
            else:
                name, buf = None, []
        else:
            if name:
                buf.append(line)
    if name:
        lib.write("".join(buf)); n += 1
print(f"library sequences: {n}")
EOF

# 2. 刷新 taxonomy 副本
cp "$TAXDIR/names.dmp" "$TAXDIR/nodes.dmp" "$KP_DB/taxonomy/" 2>/dev/null || true

# 3. 重建哈希库（需要 -p >= 3）
"$KP_BIN" build-db --db "$KP_DB" -p 3

# 4. 重算 taxid → 8级谱系表（供 API 的病毒提取/谱系映射）
awk -F'\t' '{print $2}' "$KP_DB/seqid2taxid.map" | sort -u > "$KP_DB/taxID_list"
python3.8 "/opt/plant_virus_db/plant_virus_db_pipeline/9.metabuli/build_taxid_lineage.py" \
    --db "$KP_DB" --out "$LINEAGE_OUT"

# 5. 重启 API 加载新血缘表
systemctl restart metabuli-api
echo "$LOG_TAG $(date) done"
