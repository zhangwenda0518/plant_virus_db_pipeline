#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 1 — 把 ICTV Master Species List 41 v1 的 MSL 主表导出为 TSV。

ICTV 官方发布的是 .xlsx（本机环境无 openpyxl/pandas），这里用标准库
zipfile + ElementTree 流式解析，避免一次性把 14 MB 的 sheet XML 读进内存。

用法:
    python export_msl41.py --xlsx "E:/谷歌下载/ICTV_Master_Species_List_2025_MSL41.v1 (4).xlsx" \
                           --out  data/MSL41_species.tsv
"""
import argparse
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

# MSL 主表里真正参与建树的 8 个主分类阶元。
# Subrealm / Subkingdom / Subclass 在 MSL41 中为空；Subphylum / Suborder /
# Subfamily / Subgenus 有值但层级过细，建树时并入父级，故这里一并导出留存。
RANK_COLS = [
    'Realm', 'Subrealm', 'Kingdom', 'Subkingdom', 'Phylum', 'Subphylum',
    'Class', 'Subclass', 'Order', 'Suborder', 'Family', 'Subfamily',
    'Genus', 'Subgenus', 'Species',
]
EXTRA_COLS = ['ICTV_ID', 'Genome']


def col_to_idx(ref):
    m = re.match(r'([A-Z]+)', ref)
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def load_shared_strings(z):
    out = []
    with z.open('xl/sharedStrings.xml') as f:
        for _, el in ET.iterparse(f, events=('end',)):
            if el.tag == NS + 'si':
                out.append(''.join(t.text or '' for t in el.iter(NS + 't')))
                el.clear()
    return out


def find_sheet(z, wanted):
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rid2t = {r.get('Id'): r.get('Target') for r in rels}
    for sh in wb.iter(NS + 'sheet'):
        if sh.get('name') == wanted:
            tgt = rid2t[sh.get(RNS + 'id')]
            return tgt if tgt.startswith('xl/') else 'xl/' + tgt.lstrip('/')
    raise SystemExit(f'[FATAL] sheet {wanted!r} not found')


def iter_rows(z, target, sst):
    with z.open(target) as f:
        for _, el in ET.iterparse(f, events=('end',)):
            if el.tag == NS + 'row':
                row = []
                for c in el.iter(NS + 'c'):
                    ref = c.get('r') or ''
                    idx = col_to_idx(ref) if ref else len(row)
                    while len(row) < idx:
                        row.append('')
                    t = c.get('t')
                    v = c.find(NS + 'v')
                    if t == 's' and v is not None:
                        val = sst[int(v.text)]
                    elif t == 'inlineStr':
                        isel = c.find(NS + 'is')
                        val = ''.join(x.text or '' for x in isel.iter(NS + 't')) if isel is not None else ''
                    else:
                        val = v.text if v is not None and v.text else ''
                    row.append(val)
                yield row
                el.clear()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--xlsx', required=True, help='ICTV MSL41 .xlsx 路径')
    ap.add_argument('--out', required=True, help='输出 TSV 路径')
    ap.add_argument('--sheet', default='MSL', help='主表 sheet 名 (默认 MSL)')
    args = ap.parse_args()

    if not os.path.exists(args.xlsx):
        raise SystemExit(f'[FATAL] 找不到输入文件: {args.xlsx}')

    z = zipfile.ZipFile(args.xlsx)
    sst = load_shared_strings(z)
    target = find_sheet(z, args.sheet)

    it = iter_rows(z, target, sst)
    hdr = [h.strip() for h in next(it)]
    idx = {h: i for i, h in enumerate(hdr)}

    missing = [c for c in RANK_COLS + EXTRA_COLS if c not in idx]
    if missing:
        raise SystemExit(f'[FATAL] MSL 表缺少列: {missing}\n实际列: {hdr}')

    keep = RANK_COLS + EXTRA_COLS
    n = 0
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8', newline='') as fo:
        fo.write('\t'.join(keep) + '\n')
        for r in it:
            if not any(x.strip() for x in r):
                continue
            row = [(r[idx[c]] if idx[c] < len(r) else '').strip() for c in keep]
            if not row[keep.index('Species')]:
                continue
            fo.write('\t'.join(row) + '\n')
            n += 1

    print(f'[OK] {n} 条 species 记录 -> {args.out}')
    print(f'     列: {keep}')


if __name__ == '__main__':
    main()
