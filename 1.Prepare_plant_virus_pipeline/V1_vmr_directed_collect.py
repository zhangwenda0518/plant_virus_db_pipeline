#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V1 — VMR 定向补收 (2026-10-26)

背景：序列入库通道按 NCBI 宿主谱系 (Viridiplantae) 收录，但 NCBI 宿主标注不全——
ICTV VMR 里大量基线内植物病毒种的 GenBank 记录宿主谱系没挂 Viridiplantae，
导致 C2 收不到（曾造成 397 个基线种未覆盖）。

本脚本以 VMR 收录号为依据做**定向补收**：
  基线种（docs/phylo/data/plant_taxa.tsv rank=species）中精选库无记录、
  但 VMR 列有 GenBank accession 的，批量下载序列与元数据入精选库。

幂等：已在 Ref 的 accession 自动跳过；无缺失秒退。
NCBI 无序列的种（VMR 无收录号，如早年文献表型命名的占位种）无法补，属永久缺口。

用法:
  python3 V1_vmr_directed_collect.py --vmr docs/data/VMR_MSL41.txt
  python3 V1_vmr_directed_collect.py --dry-run
"""
import argparse
import csv
import os
import re
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REF_INFO = os.path.join(REPO, 'docs', 'data', 'Plant_Virus_Ref.Info.tsv')
REF_FASTA = os.path.join(REPO, 'docs', 'data', 'Plant_Virus_Ref.fasta')
PLANT_TAXA = os.path.join(REPO, 'docs', 'phylo', 'data', 'plant_taxa.tsv')

ACC_RE = re.compile(r'[A-Z]{2}_?\d+(?:\.\d+)?')
# 噪声过滤：NA 开头不存在；WGS 中间格式（如 GEFV01158142/FV01018191，8 位以上数字）efetch 取不到


def valid_acc(a):
    return not re.match(r'^NA\d', a) and not re.match(r'^[A-Z]{2}\d{8,}$', a)


MOL = {'ss-RNA': 'RNA', 'cRNA': 'RNA', 'ds-RNA': 'RNA', 'ds-cRNA': 'RNA', 'mRNA': 'RNA',
       'ss-DNA': 'DNA', 'DNA': 'DNA', 'RNA': 'RNA'}


def norm_mol(v):
    v = (v or '').strip()
    if not v:
        return ''
    if v in MOL:
        return MOL[v]
    if 'DNA' in v:
        return 'DNA'
    if 'RNA' in v.lower():
        return 'RNA'
    return v


def baseline_families():
    """42 科基线（来自 docs/phylo/data/plant_taxa.tsv 的 family 列）。"""
    fams = set()
    with open(PLANT_TAXA, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            v = (r.get('family') or '').strip()
            if v:
                fams.add(v)
    return fams


def post_efetch(ids, rettype):
    url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
    data = urllib.parse.urlencode({'db': 'nucleotide', 'id': ','.join(ids),
                                   'rettype': rettype, 'retmode': 'text'}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={'User-Agent': 'plant-virus-db/1.0'})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode('utf-8', errors='replace')
        except Exception as e:
            print(f'   retry {attempt}: {e}')
            time.sleep(5)
    return ''


def parse_gb(text):
    recs = {}
    for block in text.split('\n//\n'):
        if 'LOCUS' not in block:
            continue
        g = {}
        m = re.search(r'^LOCUS\s+(\S+)\s+(\d+) bp\s+(\S+)\s+(linear|circular)\s+(\S+)\s+(\d{2}-\w{3}-\d{4})',
                      block, re.M | re.I)
        if m:
            g.update(length=m.group(2), mol=m.group(3), topo=m.group(4).capitalize(), date=m.group(6))
        m = re.search(r'^VERSION\s+(\S+)', block, re.M)
        if m:
            g['version'] = m.group(1)
        m = re.search(r'taxon:(\d+)', block)
        if m:
            g['taxid'] = m.group(1)
        m = re.search(r'^DEFINITION\s+(.+?)(?=\nACCESSION|\nVERSION)', block, re.M | re.S)
        if m:
            g['title'] = re.sub(r'\s+', ' ', m.group(1)).strip()
        m = re.search(r'^ORGANISM\s+(.+)$', block, re.M)
        if m:
            g['organism'] = m.group(1).strip()
        for key, tag in (('host', '/host="'), ('isolation_source', '/isolation_source="'),
                         ('collection_date', '/collection_date="'), ('country', '/country="'),
                         ('segment', '/segment="')):
            m = re.search(re.escape(tag) + r'([^"]*)"', block)
            if m:
                g[key] = re.sub(r'\s+', ' ', m.group(1)).strip()
        if g.get('version'):
            recs[g['version'].split('.')[0]] = g
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vmr', default=os.path.join(REPO, 'docs', 'data', 'VMR_MSL41.txt'))
    ap.add_argument('--ref-info', default=REF_INFO,
                    help='精选库元数据 TSV（run_all 全量重建时传 G2 产物路径）')
    ap.add_argument('--ref-fasta', default=REF_FASTA,
                    help='精选库 FASTA（同上）')
    ap.add_argument('--encoding', default='auto',
                    help='VMR 文件编码：auto=先 utf-8 后 latin-1；也可显式 utf-8 / latin-1')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.vmr):
        raise SystemExit(f'[FATAL] VMR 不存在: {args.vmr}')

    def read_vmr():
        raw = open(args.vmr, 'rb').read()
        if args.encoding != 'auto':
            return raw.decode(args.encoding, errors='replace')
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('latin-1')

    # 1. 基线种集合与 42 科基线
    baseline = set()
    fams_all = set()
    with open(PLANT_TAXA, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            v = (r.get('species') or '').strip()
            fm = (r.get('family') or '').strip()
            if (r.get('rank') or '').strip() == 'species' and v:
                baseline.add(v)
            if fm:
                fams_all.add(fm)

    # 2. Ref 现有 accession 与现有种
    ref_accs = set()
    ref_species = set()
    with open(args.ref_info, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            a = (r.get('Accession') or '').split('.')[0]
            if a:
                ref_accs.add(a)
            v = (r.get('Species_ICTV') or '').strip()
            if v:
                ref_species.add(v)

    # 3. 缺失基线种 → VMR accession
    targets = {}
    seen_species = set()
    vmr_text = read_vmr().replace('\r\n', '\n')
    for r in csv.DictReader(vmr_text.splitlines(), delimiter='\t'):
            sp = (r.get('Species') or '').strip()
            if sp not in baseline or sp in ref_species or sp in seen_species:
                continue
            seen_species.add(sp)
            fam = (r.get('Family') or '').strip()
            if fam not in fams_all:
                continue
            for a in ACC_RE.findall(r.get('Virus GENBANK accession') or ''):
                if valid_acc(a) and a not in ref_accs and a not in targets:
                    targets[a] = (sp, (r.get('Genus') or '').strip(), fam)

    print(f'[V1] 基线 {len(baseline)} 种 | 精选库已含 {len(ref_species)} 种 | '
          f'待补收 accession: {len(targets)}')
    if not targets:
        print('[V1] 无缺失，秒退')
        return
    if args.dry_run:
        for a, (sp, g, f) in sorted(targets.items(), key=lambda x: x[1][0])[:20]:
            print(f'   [dry] {a}  {sp[:45]}')
        print(f'   [dry] 共 {len(targets)} 个 accession 待补收')
        return

    # 4. 批量下载
    accs = sorted(targets)
    gb_text, fa_text = '', ''
    BATCH = 40
    for i in range(0, len(accs), BATCH):
        b = accs[i:i + BATCH]
        gb_text += post_efetch(b, 'gb')
        time.sleep(0.4)
        fa_text += post_efetch(b, 'fasta')
        time.sleep(0.4)
        print(f'   下载批次 {i // BATCH + 1}: gb {len(gb_text) // 1024}KB / fa {len(fa_text) // 1024}KB')
    grecs = parse_gb(gb_text)
    farecs = {}
    for block in fa_text.split('>'):
        if not block.strip():
            continue
        nl = block.find('\n')
        farecs[block[:nl].split('.')[0].strip()] = re.sub(r'\s+', '', block[nl + 1:])

    # 5. 构建并追加（列序对齐现有表头）
    with open(args.ref_info, encoding='utf-8', errors='replace') as f:
        hdr = [h.strip() for h in f.readline().rstrip('\n').split('\t')]
    added = 0
    failed = []
    with open(args.ref_info, 'a', encoding='utf-8', newline='') as f:
        for acc in accs:
            sp, gen, fam = targets[acc]
            g = grecs.get(acc)
            if not g or not g.get('taxid'):
                failed.append((acc, sp))
                continue
            ver = g.get('version', acc)
            title = g.get('title', '')
            complete = 'complete' in title.lower()
            row = {c: '' for c in hdr}
            row.update({'Accession': ver, 'Taxid': g.get('taxid', ''),
                        'Species_NCBI': g.get('organism', ''), 'Species_ICTV': sp,
                        'Family': fam, 'Segment': g.get('segment', ''),
                        'Topology': g.get('topo', ''),
                        'Molecule_type': g.get('mol', ''),
                        'Molecule_Type2': norm_mol(g.get('mol', '')),
                        'Sequence_Type': 'GenBank', 'Length': g.get('length', ''),
                        'Nuc_Completeness': 'complete' if complete else 'partial',
                        'GenBank_Title': title, 'Geo_Location': g.get('country', ''),
                        'USA': 'USA' if g.get('country', '').startswith('USA') else '',
                        'Host': g.get('host', ''),
                        'Isolation_Source': g.get('isolation_source', ''),
                        'Collection_Date': g.get('collection_date', ''),
                        'Release_Date': g.get('date', ''),
                        'VMR_Species': sp, 'VMR_Genus': gen, 'VMR_Family': fam,
                        'Virus GENBANK accession': acc,
                        'Genome coverage': 'Complete genome' if complete else '',
                        'Species_Canonical': sp,
                        'Species_Canonical_Source': 'vmr_accession'})
            f.write('\t'.join(row.get(c, '') for c in hdr) + '\n')
            added += 1

    # 6. FASTA 追加
    have = set()
    for line in open(args.ref_fasta, encoding='utf-8', errors='replace'):
        if line.startswith('>'):
            have.add(line[1:].strip().split()[0].split('.')[0])
    with open(args.ref_fasta, 'a', encoding='utf-8') as f:
        for a, s in farecs.items():
            if a not in have:
                f.write('>' + a + '\n' + s + '\n')

    print(f'[V1] 完成: 入库 {added} 条 | 下载失败 {len(failed)} 条'
          + (f' → {failed[:5]}' if failed else '（下轮运行自动重试）'))


if __name__ == '__main__':
    main()
