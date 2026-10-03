#!/bin/bash
# rebuild_metabuli_db.sh — 从最新 Plant_Virus_Ref.fasta 重建 Metabuli 分类库
# 步骤: taxonomy刷新(best-effort) → acc2taxid(3列,合并不可用的) → 过滤死taxid
#       → metabuli build(新目录) → taxid_lineage 重算 → 原子换库 → 重启 API
set -e

REF_FASTA="/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Ref.fasta"
REF_INFO="/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Ref.Info.tsv"
TAXDIR="/opt/plant_virus_db/taxonomy"
DB_DIR="/opt/plant_virus_db/ref.virus.build.metabuli_db"
NEW_DIR="${DB_DIR}.new"
PREV_DIR="${DB_DIR}.prev"
BIN=/usr/local/bin/metabuli
META_DIR="/opt/plant_virus_db/plant_virus_db_pipeline/9.metabuli"
LOG_TAG="[metabuli-rebuild]"
echo "$LOG_TAG $(date) start"

# 0a. 临时 swapfile（merge 阶段需要大块分配，缺它必 bad_alloc）
SWAPF=/tmp/swap_build
SWAP_CREATED=0
if ! swapon --show=NAME 2>/dev/null | grep -q "^$SWAPF"; then
    dd if=/dev/zero of="$SWAPF" bs=1M count=4096 status=none
    chmod 600 "$SWAPF"
    mkswap "$SWAPF" > /dev/null
    swapon "$SWAPF"
    SWAP_CREATED=1
    echo "$LOG_TAG temp swapfile 4G enabled"
fi

# 0b. taxonomy 刷新（best-effort；失败则用现有 dump，最新accessions会被丢弃）
TAX_AGE_DAYS=$(( ( $(date +%s) - $(stat -c %Y "$TAXDIR/nodes.dmp") ) / 86400 ))
if [ "$TAX_AGE_DAYS" -ge 14 ]; then
    echo "$LOG_TAG taxonomy is $TAX_AGE_DAYS days old, refreshing..." || true
    mkdir -p /tmp/taxdump_new
    ( cd /tmp/taxdump_new && for i in 1 2 3 4 5 6 7 8; do
        wget -q -c --timeout=90 "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/new_taxdump.tar.gz" && break; sleep 5
      done
      gzip -t new_taxdump.tar.gz 2>/dev/null && tar xzf new_taxdump.tar.gz ) || true
    if [ -f /tmp/taxdump_new/nodes.dmp ]; then
        rm -rf "${TAXDIR}_old"
        mv "$TAXDIR" "${TAXDIR}_old"
        mkdir -p "$TAXDIR"
        for f in names.dmp nodes.dmp merged.dmp delnodes.dmp; do
            cp "/tmp/taxdump_new/$f" "$TAXDIR/" 2>/dev/null || true
        done
        echo "$LOG_TAG taxonomy refreshed"
    fi
fi

# 1. acc2taxid（NCBI 三列）+ 死taxid过滤（merged.dmp 重映射，无法映射的剔除）
python3.8 - "$REF_INFO" "$TAXDIR" > /tmp/acc2taxid.new 2>/tmp/acc2taxid.err << 'EOF'
import csv, sys
taxdir = sys.argv[2]
nodes = set()
with open(f"{taxdir}/nodes.dmp", encoding="utf-8", errors="replace") as f:
    for line in f:
        nodes.add(line.split("\t|\t")[0].strip())
merged = {}
with open(f"{taxdir}/merged.dmp", encoding="utf-8", errors="replace") as f:
    for line in f:
        p = line.split("|")
        if len(p) >= 2:
            merged[p[0].strip()] = p[1].strip()
excluded = []
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    rd = csv.DictReader(f, delimiter="\t")
    for r in rd:
        acc = (r.get("Accession") or "").strip()
        tax = (r.get("Taxid") or "").strip()
        if not acc or not tax:
            continue
        if tax not in nodes:
            if tax in merged:
                tax = merged[tax]
            else:
                excluded.append(acc)
                continue
        base = acc.split(".")[0]
        print(f"{base}\t{acc}\t{tax}")
with open("/tmp/excluded_accessions.txt", "w") as f:
    f.write("\n".join(excluded))
print(f"excluded {len(excluded)} dead-taxid accessions", file=sys.stderr)
EOF
LINES=$(wc -l < /tmp/acc2taxid.new)
echo "$LOG_TAG acc2taxid entries: $LINES"

# 2. 过滤 fasta（剔除死taxid序列）
python3.8 /dev/stdin << 'EOF'
excluded = set()
with open("/tmp/excluded_accessions.txt") as f:
    excluded = set(l.strip() for l in f if l.strip())
src = "/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/Plant_Virus_Ref.fasta"
dst = "/tmp/ref_build.fasta"
import os
if os.path.exists(dst): os.remove(dst)
name, buf, kept, dropped = None, [], 0, 0
def flush(name, buf):
    global kept, dropped
    if name is None:
        return
    if name.split(".")[0] in excluded:
        dropped += 1
    else:
        kept += 1
        with open(dst, "a") as f:
            f.write(">" + name + "\n")
            for j in range(0, len(buf), 70):
                f.write("".join(buf[j:j+70]) + "\n")
with open(src, encoding="utf-8", errors="replace") as f:
    for line in f:
        if line.startswith(">"):
            flush(name, buf)
            name, buf = line[1:].strip(), []
        else:
            buf.append(line.strip())
flush(name, buf)
print(f"fasta filtered: kept {kept}, dropped {dropped}")
EOF
echo "$REF_FASTA" > /dev/null
BUILD_FASTA=/tmp/ref_build.fasta
# metabuli 的第2参数是「FASTA 路径清单」文件（每行一个路径），不是 fasta 本身
printf '%s\n' "$BUILD_FASTA" > /tmp/ref_build_list.txt
BUILD_LIST=/tmp/ref_build_list.txt

# 3. 构建（新目录）
rm -rf "$NEW_DIR"
$BIN build "$NEW_DIR" "$BUILD_LIST" /tmp/acc2taxid.new \
    --taxonomy-path "$TAXDIR" --max-ram 2 --threads 2
echo "$LOG_TAG build done: $(du -sh "$NEW_DIR" | cut -f1)"

# 4. 重算 taxid_lineage（指向新库）
python3.8 "$META_DIR/build_taxid_lineage.py" --db "$NEW_DIR" --out "$META_DIR/taxid_lineage.tsv"
echo "$LOG_TAG taxid_lineage regenerated"

# 5. 原子换库 + 重启 API
rm -rf "$PREV_DIR"
[ -d "$DB_DIR" ] && mv "$DB_DIR" "$PREV_DIR"
mv "$NEW_DIR" "$DB_DIR"
systemctl restart metabuli-api
echo "$LOG_TAG swapped + metabuli-api restarted. previous db kept at $PREV_DIR"

# 6. 收掉临时 swapfile
if [ "$SWAP_CREATED" = "1" ]; then
    swapoff "$SWAPF" && rm -f "$SWAPF"
    echo "$LOG_TAG temp swapfile removed"
fi
echo "$LOG_TAG $(date) all done"
