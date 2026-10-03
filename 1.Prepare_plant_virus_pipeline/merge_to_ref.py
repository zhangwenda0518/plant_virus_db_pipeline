#!/usr/bin/env python3
"""
merge_to_ref.py — 增量记录合并到 Plant_Virus_Ref 参考集 (通用版)
每次增量更新后运行, 自动比较新旧记录并更新 Ref
"""

import polars as pl, os, re, sys
from datetime import datetime

# 数据目录默认为服务器路径; 本机运行可设环境变量 PVDB_DATA_DIR 覆盖
# 默认取本仓库 docs/data（可用 PVDB_DATA_DIR 覆盖）；不再硬编码 /opt 服务器路径
DATA_DIR = os.environ.get("PVDB_DATA_DIR",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "data"))

# 2026-09-27 修复: 基因级记录("complete cds/gene(s)")不得凭 Nuc_Completeness 字段算作
# complete —— NCBI 上游元数据本身有此误标(294 条基因级 RefSeq 曾借此混入参考集)。
# 标题与字段冲突时以标题为准; 同级之内以更长者优先(长度项),
# 防止 615 nt 基因记录靠 RefSeq 加成击败 6,116 nt 完整基因组(实例: Tymovirus belladonnae)。
_GENE_LEVEL_RE = re.compile(r"complete\s+cds|complete\s+coding|complete\s+genes?\b|\bgene\b|\bgenes\b", re.IGNORECASE)
_PARTIAL_RE = re.compile(r"partial", re.IGNORECASE)
_COMPLETE_OK_RE = re.compile(r"complete\s+genome|complete\s+sequence|complete\s+segment", re.IGNORECASE)


def effective_completeness(row):
    title = str(row.get("GenBank_Title", "") or "")
    if _PARTIAL_RE.search(title):
        return "partial"
    # 基因级标题(泛 \bgene\b 信号)不得算 complete, 但标题同时声明 complete genome 除外
    if _GENE_LEVEL_RE.search(title) and not _COMPLETE_OK_RE.search(title):
        return "fragment"
    return str(row.get("Nuc_Completeness", "") or "").lower().strip()


def completeness_score(row):
    c = effective_completeness(row)
    return 10 if c == "complete" else (1 if c == "partial" else 0)

def parse_date(date_str):
    if not date_str or str(date_str).strip() == "": return datetime(1900,1,1)
    for fmt in ["%Y-%m-%d","%d-%b-%Y","%Y/%m/%d"]:
        try: return datetime.strptime(str(date_str).strip(), fmt)
        except: pass
    return datetime(1900,1,1)

def record_length(rec):
    try:
        return int(float(str(rec.get("Length", "0")) or 0))
    except ValueError:
        return 0

def rank_record(rec):
    score = completeness_score(rec) * 1_000_000   # 完整度: complete >> partial/unknown/fragment
    score += min(record_length(rec), 100_000)     # 同级之内越长越优(长度项压过年份与 RefSeq 加成)
    acc = str(rec.get("Accession",""))
    if acc.startswith("NC_") or acc.startswith("AC_"): score += 100
    dt = parse_date(rec.get("Release_Date",""))
    if dt.year > 1900: score += (2026 - dt.year) * 10
    return score

def is_segmented(seg):
    if not seg or str(seg).strip() in ("","None","PENDING_CLASSIFY","PENDING_VMR"): return False
    return bool(re.match(r'(RNA|DNA[ -]?[AB]?|[LMS]|Seg\d|dsRNA)', str(seg).strip(), re.IGNORECASE))

def is_segmented_rec(rec):
    """2026-09-27 修复: 节段判定优先看 Category(F2 的权威标记, 3,664 条 Segmented_*),
    其次才是 Segment/Segment_std 字段 —— 参考集 4,858 条的 Segment 字段为空,
    旧逻辑只看该字段导致节段物种被当单基因组处理(补段/替换路径全走错)。"""
    if str(rec.get("Category", "") or "").startswith("Segmented"):
        return True
    return is_segmented(rec.get("Segment") or rec.get("Segment_std"))

# Load
full = pl.read_csv(os.path.join(DATA_DIR, "Plant_Virus_Full.Info.tsv"), separator="\t", infer_schema_length=0)
ref = pl.read_csv(os.path.join(DATA_DIR, "Plant_Virus_Ref.Info.tsv"), separator="\t", infer_schema_length=0)
print(f"Full: {full.height:,}  Ref: {ref.height:,}")

ref_taxids = set(ref["Taxid"].drop_nulls().cast(pl.Utf8).unique().to_list())
ref_accs = set(ref["Accession"].to_list())

# Only process records not already in Ref
new_to_ref = full.filter(~pl.col("Accession").is_in(ref_accs))
print(f"New records to consider: {new_to_ref.height:,}")

def _seg_key(rec):
    """节段类型归一化(与 refinfo/common.norm_seg 同口径): 用于识别『该物种尚缺哪种节段』。
    2026-09-27 扩展: 功能命名(RNAREP/RNATGB/RNACP)、组件别名(ACOMPONENT 等)、
    分离株变体后缀(RNA3A→RNA3, DNAC1→DNA-C)、卫星标签(SAT:* 单列)。"""
    s = str(rec.get("Segment_std") or rec.get("Segment") or "").strip().upper()
    for ch in (" ", "_", "-"):
        s = s.replace(ch, "")
    if not s:
        return "(未标注)"
    if s.startswith("SAT"):
        return "SAT:" + s
    if s == "RNAREP": return "RNA1"
    if s == "RNATGB": return "RNA2"
    if s == "RNACP": return "RNA3"
    m = re.match(r"RNA(\d+)[AB]$", s)
    if m: return f"RNA{m.group(1)}"
    m = re.match(r"DNA([RSCMN])(\d)$", s)
    if m: return f"DNA-{m.group(1)}"
    m = re.match(r"DNAU(\d)$", s)
    if m: return f"DNA-U{m.group(1)}"
    if s in ("A", "DNAA", "COMPONENTA", "ACOMPONENT", "DNA1"): return "DNA-A"
    if s in ("B", "DNAB", "COMPONENTB", "BCOMPONENT", "DNA2"): return "DNA-B"
    if s.startswith("COMPONENT") and len(s) > 9 and s[9:].isalpha(): return f"DNA-{s[9:]}"
    if s.startswith("BBTV") and len(s) > 4 and s[4:].isalpha(): return f"DNA-{s[4:]}"
    if s in ("S", "DNAS", "SMALL"): return "DNA-S"
    if s in ("M", "DNAM", "MEDIUM"): return "DNA-M"
    if s in ("L", "DNAL", "LARGE"): return "DNA-L"
    if s.startswith("RNA") and s[3:].isdigit(): return f"RNA{int(s[3:])}"
    if s.isdigit(): return f"RNA{int(s)}"
    if s.startswith("DNA") and s[3:].isalpha(): return f"DNA-{s[3:]}"
    return s


new_rows = []
replaced = 0; added = 0; kept = 0; topup = 0

# Process existing Ref taxids: check for better replacements
for tid in ref_taxids:
    old_recs = ref.filter(pl.col("Taxid").cast(pl.Utf8) == tid)
    new_recs = new_to_ref.filter(pl.col("Taxid").cast(pl.Utf8) == tid)

    if new_recs.height == 0:
        for row in old_recs.iter_rows(named=True): new_rows.append(dict(row))
        kept += old_recs.height
        continue

    old_best = max(old_recs.iter_rows(named=True), key=rank_record)
    new_best = max(new_recs.iter_rows(named=True), key=rank_record)

    if is_segmented_rec(old_best):
        # 2026-09-27 修复: 节段病毒只增不删(旧逻辑按 best 整组替换会丢已收录节段)。
        # 补段 = 只补「该 taxid 参考集尚缺的节段类型」里最优的一条干净 complete 记录;
        # 已有节段类型的新分离株不收, 避免参考集被同种多分离株灌水。
        have = {_seg_key(r) for r in old_recs.iter_rows(named=True)}
        best_missing = {}
        for row in new_recs.iter_rows(named=True):
            if effective_completeness(row) != "complete":
                continue
            if "defective" in str(row.get("GenBank_Title", "")).lower():
                continue  # 缺陷分子不是基因组节段, 不作为补段候选
            k = _seg_key(row)
            if k in have or k == "(未标注)":
                continue
            if k not in best_missing or rank_record(row) > rank_record(best_missing[k]):
                best_missing[k] = row
        for row in old_recs.iter_rows(named=True):
            new_rows.append(dict(row))
        for row in best_missing.values():
            row = dict(row)
            # 补段记录来自全量集(无 Category 列), 按其 complete 属性标记
            row["Category"] = row.get("Category") or "Segmented_Complete"
            new_rows.append(dict(row)); topup += 1
    else:
        # 2026-10-03 体检修复: 旧实现只追加 old_best(或 new_best) 一条, 同 TaxID 其余行被
        # 静默丢弃(与节段分支"只增不删"不一致, 且丢行不进日志)。现在保留全部旧行。
        if rank_record(new_best) > rank_record(old_best):
            nb = dict(new_best)
            # 注释列继承: 全量集记录无 VMR/Category 列, 而被替换的旧行已带注释 ——
            # 不继承的话每次替换都会制造一批"无属无名"行(2026-09-27)
            for c in ("VMR_Species", "VMR_Family", "VMR_Genus", "Virus name(s)",
                      "Virus GENBANK accession", "Genome coverage"):
                if not (nb.get(c) or "").strip():
                    nb[c] = old_best.get(c, "")
            if not (nb.get("Category") or "").strip():
                nb["Category"] = (("Segmented_" if is_segmented_rec(nb) else "NonSegmented_")
                                  + ("Complete" if effective_completeness(nb) == "complete" else "Other_Partial"))
            new_rows.append(nb); replaced += 1
        for row in old_recs.iter_rows(named=True):
            new_rows.append(dict(row)); kept += 1

# Process new taxids
new_taxids = set(new_to_ref["Taxid"].drop_nulls().cast(pl.Utf8).unique().to_list()) - ref_taxids
for tid in new_taxids:
    recs = new_to_ref.filter(pl.col("Taxid").cast(pl.Utf8) == tid)
    if any(is_segmented(r.get("Segment","")) for r in recs.iter_rows(named=True)):
        # 节段病毒新 taxid: 同样只收干净 complete 记录
        kept_recs = [r for r in recs.iter_rows(named=True) if effective_completeness(r) == "complete"]
        for row in kept_recs:
            row = dict(row); row["Category"] = row.get("Category") or "Segmented_Complete"
            new_rows.append(row); added += 1
    else:
        best = max(recs.iter_rows(named=True), key=rank_record)
        best = dict(best)
        if not (best.get("Category") or "").strip():
            best["Category"] = (("Segmented_" if is_segmented_rec(best) else "NonSegmented_")
                                + ("Complete" if effective_completeness(best) == "complete" else "Other_Partial"))
        new_rows.append(best); added += 1

print(f"Kept: {kept}  Replaced: {replaced}  Added: {added}  SegmentTopUp: {topup}  Total: {len(new_rows)}")

# 2026-10-03 体检修复: 输出行数 vs 输入行数对账 (丢行必须显式暴露, 不得静默)
_expected_total = ref.height + replaced + added + topup
if len(new_rows) != _expected_total:
    print(f"⚠️ 对账不一致: 输出 {len(new_rows):,} 行 != Ref输入 {ref.height:,} "
          f"+ 替换 {replaced} + 新增 {added} + 补段 {topup} = {_expected_total:,}")
else:
    print(f"✅ 对账: Ref输入 {ref.height:,} 行 + 替换 {replaced} + 新增 {added} + "
          f"补段 {topup} → 输出 {len(new_rows):,} 行 (丢行 0)")
print(f"   候选池: Full {full.height:,} 行中 Ref 未收录 {new_to_ref.height:,} 行")

# Align schema and write
ref_cols = list(ref.columns)
uniform = [{c: r.get(c,"") for c in ref_cols} for r in new_rows]
ref_df = pl.DataFrame(uniform, schema={c: pl.Utf8 for c in ref_cols})

# 2026-09-27: 补段记录来自全量集(无 VMR 注释列) —— 用同物种(Species_ICTV)已有记录回填,
# 避免新增行成为"无属无名"的裸行
_vmr_cols = ["VMR_Species", "VMR_Family", "VMR_Genus", "Virus name(s)"]
_sib = (ref_df.filter((pl.col("VMR_Genus").fill_null("") != "") & (pl.col("Species_ICTV").fill_null("") != ""))
        .unique(subset=["Species_ICTV"], keep="first")
        .select(["Species_ICTV"] + _vmr_cols)
        .rename({c: c + "_sib" for c in _vmr_cols}))
if _sib.height:
    ref_df = (ref_df.join(_sib, on="Species_ICTV", how="left")
              .with_columns([
                  # 空字符串也算"无注释"(全量集来的行是 "" 而非 null, coalesce 不认空串)
                  pl.when(pl.col(c).fill_null("").str.len_chars() == 0)
                    .then(pl.col(c + "_sib")).otherwise(pl.col(c)).alias(c)
                  for c in _vmr_cols])
              .drop([c + "_sib" for c in _vmr_cols]))

out = os.path.join(DATA_DIR, "Plant_Virus_Ref.Info.tsv")
if os.path.exists(out): os.rename(out, out + ".bak")
ref_df.write_csv(out, separator="\t")

# Rebuild Ref FASTA
ref_accs_new = set(ref_df["Accession"].to_list())
fasta_in = os.path.join(DATA_DIR, "Plant_Virus_Full.fasta")
fasta_out = os.path.join(DATA_DIR, "Plant_Virus_Ref.fasta")
if os.path.exists(fasta_out): os.rename(fasta_out, fasta_out + ".bak")

k = 0
with open(fasta_out, "w", encoding="utf-8") as out:
    cur = []; acc = None; keep = False
    with open(fasta_in, encoding="utf-8") as f:
        for line in f:
            if line.startswith(">"):
                if keep and cur: out.write("".join(cur)); k += 1
                cur = [line]; acc = line[1:].split()[0]
                keep = acc in ref_accs_new or acc.split(".")[0] in ref_accs_new
            else: cur.append(line)
        if keep and cur: out.write("".join(cur)); k += 1

print(f"Ref FASTA: {k} records")
print("Done")
