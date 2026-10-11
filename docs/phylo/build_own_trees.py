#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 4 — 从本地参考序列库选出「可以建树」的序列集，并留下可复现记录。

**为什么需要单独一步**：ICTV 的树覆盖不全（见 README M4-4），要「全科物种树」只能自己建。
但本地库不能直接拿来 align，有几个必须先处理的坑：

1. `Segment` 字段对**同一件事有十几种写法**。Geminiviridae 实测：
   `DNA-A` / `DNA A` / `A` / `A component` / `component A` 全是 A 组分；
   `DNA-B` / `DNA B` / `B` / `B component` / `component B` 全是 B 组分。
   不归一就会把 A 和 B 混进同一个 alignment —— 而它们是**不同的分子**，绝不能一起 align。
2. `Nuc_Completeness` 有 complete / partial，partial 会严重拉坏 alignment。
3. 长度范围常跨越「基因区」和「全长基因组」（如 Potyviridae 1,479..11,519），
   不按长度筛就是把苹果和橘子放一起。
4. **物种标注列 `VMR_Species` 只填了 14.7%（850/5773）**，而 `Species_ICTV` /
   `Species_NCBI` 是 100% 填充。拿 `VMR_Species` 当物种键会得出「Caulimoviridae
   只有 14 个物种」这种错结论（实际 105 条序列 / 105 个 Species_ICTV，对 MSL41
   的 109 是 96% 覆盖）。所有物种计数一律走 species_key()。

本脚本**只做筛选与导出**，不建树。建树命令写进输出的 manifest，便于复现。

用法:
    # 只看各科就绪度（不改任何东西）
    python build_own_trees.py --audit

    # 导出某个科的序列集
    python build_own_trees.py --family Caulimoviridae --segment mono --out work/Caulimoviridae.fa
    python build_own_trees.py --family Geminiviridae --segment A --out work/Gemini_DNAA.fa \
        --complete-only --derep-species
"""
import argparse
import collections
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 注意：序列库在 docs/data/，不在 docs/phylo/data/（后者放的是 MSL41 分类表）
DATA = os.path.join(HERE, os.pardir, 'data')
INFO = os.path.join(DATA, 'Plant_Virus.complete_ref_info.tsv')
FASTA = os.path.join(DATA, 'Plant_Virus.complete_ref.fasta')

# 归一后 monophyletic（单分体）用的内部标签
MONO = 'mono'


def norm_segment(raw):
    """把 Segment 的各种写法归一成 A / B / mono / 其他。

    实测见过的写法（Geminiviridae）：
        DNA-A, DNA A, A, A component, component A   -> A
        DNA-B, DNA B, B, B component, component B   -> B
        (空)                                         -> mono
        DNA-beta                                     -> BETA（卫星，不是基因组组分）
        1, I                                         -> 原样返回，由 --audit 报出来人工确认
    """
    s = (raw or '').strip().upper()
    s = re.sub(r'[_\-]+', ' ', s)
    s = re.sub(r'[^A-Z0-9]+', ' ', s).strip()
    s = re.sub(r'\s+', ' ', s)
    if s in ('', 'NA', 'N A', 'NONE', 'SINGLE', 'MONO', 'MONOPARTITE'):
        return MONO
    s = re.sub(r'^(DNA|RNA)\s*', '', s)          # DNA A / RNA2 / RNA 2 -> A / 2 / 2
    s = re.sub(r'^(COMPONENT)\s+', '', s)        # component A  -> A
    s = re.sub(r'\s+(COMPONENT|SEGMENT|PART)$', '', s)   # A component -> A
    return s or MONO


def species_key(r):
    """物种键（去冗余 / 计数都用它）。

    **不能只用 VMR_Species**：该列在本库仅 14.7% 有值，而 Species_ICTV 是 100%。
    早期版本用 VMR_Species 作 --derep-species 的键，结果 85% 的行键都是空串，
    整科会被塌成 1 条序列。按 VMR_Species -> Species_ICTV -> Species_NCBI ->
    登录号 的顺序回退，保证键非空且稳定。
    """
    for col in ('VMR_Species', 'Species_ICTV', 'Species_NCBI'):
        v = (r.get(col) or '').strip()
        if v:
            return v
    return r['Accession']


def load_info():
    with open(INFO, encoding='utf-8') as fh:
        return list(csv.DictReader(fh, delimiter='\t'))


def load_fasta(wanted):
    """流式读 FASTA，只留 wanted 里的登录号。"""
    out, acc, buf = {}, None, []
    with open(FASTA, encoding='utf-8') as fh:
        for line in fh:
            if line.startswith('>'):
                if acc and acc in wanted:
                    out[acc] = ''.join(buf)
                acc = line[1:].strip().split()[0]
                buf = []
            else:
                buf.append(line.strip())
    if acc and acc in wanted:
        out[acc] = ''.join(buf)
    return out


def audit(rows):
    fam = collections.Counter(r['VMR_Family'] for r in rows)
    print('参考序列总数: %d   科数: %d' % (len(rows), len(fam)))
    print()
    print('%-22s %6s %6s %6s %7s %7s  %s' %
          ('family', 'seqs', '完成', '单分体', '物种', '长度', '备注'))
    print('  （物种 = species_key 去重后的个数，等价于 Species_ICTV 的物种数）')
    for f, n in fam.most_common():
        if not f:
            continue
        sub = [r for r in rows if r['VMR_Family'] == f]
        comp = [r for r in sub if r['Nuc_Completeness'].strip().lower() == 'complete']
        mono = [r for r in comp if norm_segment(r['Segment']) == MONO]
        pool = mono if mono else comp
        ln = [int(r['Length']) for r in pool if r['Length'].isdigit()]
        if not ln:
            continue
        note = '' if mono else '无单分体，须按组分拆'
        if max(ln) > 3 * min(ln):
            note = (note + ' ' if note else '') + '长度跨度 >3x，疑混基因区'
        print('%-22s %6d %6d %6d %7d %4d..%-6d %s' % (
            f, n, len(comp), len(mono), len({species_key(r) for r in pool}),
            min(ln), max(ln), note))

    print()
    print('=== Segment 字段原始写法 -> 归一结果（全部科合计）===')
    raw = collections.Counter(r['Segment'] for r in rows)
    unmapped = []
    for k, v in raw.most_common():
        nk = norm_segment(k)
        flag = ''
        if nk not in ('A', 'B', MONO):
            flag = '   <-- 需人工确认'
            unmapped.append((k, nk, v))
        print('   %-14r -> %-8s %6d%s' % (k, nk, v, flag))
    if unmapped:
        print()
        print('[注意] 以下 %d 种写法无法自动归类，未被计入 A/B/mono：%s'
              % (len(unmapped), ', '.join('%r->%s' % (k, n) for k, n, _ in unmapped)))
    else:
        print()
        print('[OK] 所有 Segment 写法都能自动归类。')


def select(rows, args):
    sub = [r for r in rows if r['VMR_Family'] == args.family]
    if not sub:
        raise SystemExit('[FATAL] 库里没有科 %r' % args.family)

    steps = [('库内该科全部', len(sub))]

    if args.complete_only:
        sub = [r for r in sub if r['Nuc_Completeness'].strip().lower() == 'complete']
        steps.append(('仅 complete', len(sub)))

    if args.segment:
        sub = [r for r in sub if norm_segment(r['Segment']) == args.segment]
        steps.append(('Segment=%s' % args.segment, len(sub)))

    if args.min_len:
        sub = [r for r in sub if r['Length'].isdigit() and int(r['Length']) >= args.min_len]
        steps.append(('长度 >= %d' % args.min_len, len(sub)))
    if args.max_len:
        sub = [r for r in sub if r['Length'].isdigit() and int(r['Length']) <= args.max_len]
        steps.append(('长度 <= %d' % args.max_len, len(sub)))

    if args.refseq_only:
        sub = [r for r in sub if r['Sequence_Type'].strip() == 'RefSeq']
        steps.append(('仅 RefSeq', len(sub)))

    if args.derep_species:
        # 物种键必须是 species_key（见其 docstring）；取该物种最长的一条作代表。
        best = {}
        for r in sub:
            k = species_key(r)
            ln = int(r['Length']) if r['Length'].isdigit() else 0
            if k not in best or ln > (int(best[k]['Length']) if best[k]['Length'].isdigit() else 0):
                best[k] = r
        sub = list(best.values())
        steps.append(('每物种留最长一条', len(sub)))

    return sub, steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--audit', action='store_true', help='只报告各科就绪度，不导出')
    ap.add_argument('--family')
    ap.add_argument('--out', help='输出 FASTA 路径')
    ap.add_argument('--segment', help='A / B / mono（按归一后的组分筛）')
    ap.add_argument('--complete-only', action='store_true')
    ap.add_argument('--min-len', type=int)
    ap.add_argument('--max-len', type=int)
    ap.add_argument('--refseq-only', action='store_true')
    ap.add_argument('--derep-species', action='store_true', help='每物种只留最长一条')
    args = ap.parse_args()

    if not os.path.exists(INFO):
        raise SystemExit('[FATAL] 找不到 %s' % INFO)
    rows = load_info()

    if args.audit or not args.family:
        audit(rows)
        return 0

    if not args.out:
        raise SystemExit('[FATAL] 需要 --out')

    sub, steps = select(rows, args)
    if not sub:
        raise SystemExit('[FATAL] 筛选后为空，检查 --segment / --complete-only 等条件')

    wanted = {r['Accession'] for r in sub}
    seqs = load_fasta(wanted)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)

    tip = {}
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fo:
        for r in sorted(sub, key=lambda x: x['Accession']):
            a = r['Accession']
            if a not in seqs:
                continue
            sp = re.sub(r'[^A-Za-z0-9]+', '_', species_key(r)).strip('_')
            tip[a] = '%s_%s' % (a, sp)
            fo.write('>%s\n' % tip[a])
            s = seqs[a]
            for i in range(0, len(s), 70):
                fo.write(s[i:i + 70] + '\n')

    man = os.path.splitext(args.out)[0] + '.manifest.tsv'
    with open(man, 'w', encoding='utf-8', newline='\n') as fo:
        fo.write('# 筛选步骤\n')
        for k, v in steps:
            fo.write('#   %-24s %6d\n' % (k, v))
        fo.write('# 实际写出序列: %d\n' % len(tip))
        fo.write('accession\ttip_label\tspecies\tgenus\tsegment_raw\tsegment_norm\t'
                 'length\tcompleteness\tseq_type\n')
        for r in sorted(sub, key=lambda x: x['Accession']):
            a = r['Accession']
            if a not in tip:
                continue
            fo.write('\t'.join([
                a, tip[a], species_key(r), r['VMR_Genus'], r['Segment'],
                norm_segment(r['Segment']), r['Length'],
                r['Nuc_Completeness'], r['Sequence_Type'],
            ]) + '\n')

    print('[OK] %s  (%d 条序列)' % (args.out, len(tip)))
    print('     物种数: %d   属数: %d' % (
        len({species_key(r) for r in sub if r['Accession'] in tip}),
        len({r['VMR_Genus'] for r in sub if r['Accession'] in tip})))
    print('     筛选步骤:')
    for k, v in steps:
        print('       %-24s %6d' % (k, v))
    ln = [int(r['Length']) for r in sub if r['Accession'] in tip and r['Length'].isdigit()]
    if ln:
        print('     长度范围: %d..%d' % (min(ln), max(ln)))
    print('     可复现记录: %s' % man)
    print()
    print('     建树命令（**在大内存机器上执行**；MAFFT v7.525 / IQ-TREE 3.1.3）:')
    print('       # 服务器 39.106.101.94 只有 2 核 / 3.5GB，全长基因组比对跑不过去')
    print('       # （实测 105 条 × 7.8kb 要 2.93GB，被 OOM killer 杀；见 README M9）。')
    print('       # 不要加 ulimit -v —— 它限虚拟地址空间，会远早于真实内存压力就失败。')
    print('       mafft --retree 2 --maxiterate 0 --6merpair --thread 2 %s > %s.aln'
          % (args.out, args.out))
    print('       iqtree -s %s.aln -m MFP -B 1000 --seed 42 -T 2 -pre %s'
          % (args.out, args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
