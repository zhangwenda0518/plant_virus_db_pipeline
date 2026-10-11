#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 /phylo/molecular/ 生成「叶 -> 属」映射的**派生**文件 genus_map.json。

为什么另起一个文件、而不写回 molecular_trees.json：
    molecular_trees.json 是已验收产物（且不在 git 里），改它要付差分+备份的代价。
    本项目既定做法是「给已验证产物加展示层时，另写只读构建脚本产出派生文件」，
    已验证产物的 MD5 保持不变。本脚本只读 molecular_trees.json。

映射源：docs/data/VMR_MSL41.txt（ICTV 权威表），两列
    Virus name abbreviation(s)   -> 覆盖 CWMV / PIRYV / RheMV 这类缩写叶名
    Virus GENBANK accession      -> 覆盖 NC_026592 / D84411 这类登录号叶名

⚠️ 硬规则：**必须按科约束**。缩写表是全局的（8,653 条），不按科过滤会跨科错标 ——
    实测 SCRV→Orbivirus（Reoviridae 的属标到 Rhabdoviridae 的叶上）、
    MaYMV→Begomovirus（Geminiviridae 的属标到 Solemoviridae 的叶上）。
    本脚本用 genus -> family 反查做过滤；实测 3,265 个属里没有一个跨多科，所以过滤是干净的。

用法：
    python build_genus_map.py                 # 生成 molecular/genus_map.json
    python build_genus_map.py --report        # 只打印逐科覆盖率，不写文件
"""
import json, re, csv, sys, os, hashlib
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
MSL = os.path.join(HERE, '..', 'data', 'VMR_MSL41.txt')
TREES = os.path.join(HERE, 'molecular_trees.json')
OUT = os.path.join(HERE, 'molecular', 'genus_map.json')

# 与上次验收一致的口径，用于断言（防止上游数据换了却悄悄产出不同结果）
EXP_TIPS = 3341
EXP_MAPPED = 2199


def norm_name(s):
    """毒名归一：只留小写字母数字，空格分隔。"""
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def strip_ver(a):
    """登录号去版本号：NC_116488.1 -> NC_116488。"""
    return re.sub(r'\.\d+$', '', a.strip())


# --- 1. 载入 MSL41，建三张表 -------------------------------------------------
def load_msl():
    genus2fams = defaultdict(set)
    abbr2genus = defaultdict(set)
    name2genus = defaultdict(set)
    acc2genus = defaultdict(set)
    with open(MSL, encoding='utf-8', errors='replace') as fh:
        for r in csv.DictReader(fh, delimiter='\t'):
            g = (r.get('Genus') or '').strip()
            if not g:
                continue
            fam = (r.get('Family') or '').strip()
            if fam:
                genus2fams[g].add(fam)
            for a in re.split(r'[;,]', r.get('Virus name abbreviation(s)') or ''):
                a = a.strip()
                if len(a) >= 3:
                    abbr2genus[a.lower()].add(g)
            vn = (r.get('Virus name(s)') or '').strip()
            if vn:
                name2genus[norm_name(vn)].add(g)
            for a in re.split(r'[;,]', r.get('Virus GENBANK accession') or ''):
                a = strip_ver(a)
                if a:
                    acc2genus[a].add(g)
    return genus2fams, abbr2genus, name2genus, acc2genus


# 登录号写法：NC_026592 / NC 034375 / NC001410 / D84411 / AJ536613
# ⚠️ 不能用 \b 收尾 —— 叶名常是 NC_026592_-_replicase_…，'_' 也是词字符，
#    尾 \b 不成立会导致**一个都匹配不到**（踩过：首测覆盖率 0%）。
ACC_RE = re.compile(r'(?<![A-Za-z0-9])([A-Z]{1,2})[ _]?(\d{5,6})(?![0-9])')
# 蛋白登录号：TMMMV_AAT08133 里的 AAT08133
PROT_RE = re.compile(r'(?<![A-Za-z0-9])([A-Z]{2,4}\d{5})(?![0-9])')


def map_genus(label, fam, genus2fams, abbr2genus, name2genus, acc2genus, name_keys):
    """返回 (genus, how) 或 (None, reason)。how/reason 是短码，供前端解释。"""
    def ok(g):
        return fam in genus2fams.get(g, ())

    # ① 登录号
    for m in ACC_RE.finditer(label):
        for g in acc2genus.get(m.group(1) + '_' + m.group(2), ()):
            if ok(g):
                return g, 'acc'
    for m in PROT_RE.finditer(label):
        for g in acc2genus.get(m.group(1), ()):
            if ok(g):
                return g, 'acc'
    # ② 通用毒名（长名优先）
    flat = norm_name(label)
    for k in name_keys:
        if k in flat:
            for g in name2genus[k]:
                if ok(g):
                    return g, 'name'
            break
    # ③ 缩写（按词切，避免子串误配）
    for tok in re.split(r'[^A-Za-z0-9]+', label):
        t = tok.lower()
        if len(t) >= 4:
            for g in abbr2genus.get(t, ()):
                if ok(g):
                    return g, 'abbr'
    # 未映射 —— 给个粗粒度原因，供 tooltip 解释
    has_acc = bool(ACC_RE.search(label) or PROT_RE.search(label))
    if has_acc:
        return None, 'acc-not-in-msl41'
    if ' ' not in label.strip() and '_' not in label.strip() and len(label.strip()) <= 20:
        return None, 'element-name'          # Gmr1 / Osvaldo / Ulysses
    return None, 'name-not-in-msl41'


def main():
    report_only = '--report' in sys.argv
    genus2fams, abbr2genus, name2genus, acc2genus = load_msl()
    name_keys = sorted(name2genus, key=len, reverse=True)
    multi = {g: f for g, f in genus2fams.items() if len(f) > 1}
    print('MSL41: 属 %d 个（跨多科的属 %d 个）/ 缩写 %d / 毒名 %d / 登录号 %d'
          % (len(genus2fams), len(multi), len(abbr2genus), len(name2genus), len(acc2genus)))
    if multi:
        print('  ⚠️ 有跨多科的属，按科过滤可能过严：', list(multi.items())[:5])

    trees_doc = json.load(open(TREES, encoding='utf-8'))

    def tips(node, out):
        ch = node.get('ch')
        if not ch:
            out.append(node.get('n', ''))
            return
        for c in ch:
            tips(c, out)

    out_trees = {}
    tot = mapped = 0
    per_fam = defaultdict(lambda: [0, 0])
    for fam in trees_doc['families']:
        fname = fam['family']
        for t in fam['trees']:
            labels = []
            tips(t['tree'], labels)
            genus, reasons = {}, defaultdict(int)
            for lab in labels:
                g, how = map_genus(lab, fname, genus2fams, abbr2genus,
                                   name2genus, acc2genus, name_keys)
                tot += 1
                if g:
                    mapped += 1
                    genus[lab] = g
                    per_fam[fname][0] += 1
                else:
                    reasons[how] += 1
                    per_fam[fname][1] += 1
            out_trees[t['id']] = {
                'tips': len(labels),
                'mapped': len(genus),
                'unmapped': len(labels) - len(genus),
                'unmappedReasons': dict(sorted(reasons.items())),
                'genus': dict(sorted(genus.items())),
            }

    cov = mapped * 100.0 / tot
    print()
    print('%-22s %7s %7s %7s' % ('family', 'mapped', 'total', 'cover'))
    for f in sorted(per_fam, key=lambda k: per_fam[k][0] / max(1, sum(per_fam[k]))):
        a, b = per_fam[f]
        print('  %-20s %6d %7d %6.1f%%' % (f, a, a + b, a * 100.0 / max(1, a + b)))
    print()
    print('TOTAL tips=%d  mapped=%d (%.1f%%)  unmapped=%d'
          % (tot, mapped, cov, tot - mapped))

    if report_only:
        return 0

    # --- 断言：口径变了就拒绝写，避免悄悄产出与验收不符的文件 ---
    problems = []
    if tot != EXP_TIPS:
        problems.append('tips %d != 期望 %d' % (tot, EXP_TIPS))
    if mapped != EXP_MAPPED:
        problems.append('mapped %d != 期望 %d' % (mapped, EXP_MAPPED))
    if problems:
        print()
        print('❌ 拒绝写出：' + '; '.join(problems))
        print('   （若上游数据确实变了，请复核后再更新脚本里的 EXP_* 期望值）')
        return 1

    doc = {
        'meta': {
            'source': 'ICTV VMR MSL41 — Virus name abbreviation(s) + Virus GENBANK accession',
            'rule': 'family-constrained (a genus is accepted only if its family matches the tree family)',
            'note': ('ICTV 分子树的叶只有序列标识，本身没有分类阶元；这里的属是按 MSL41 映射得到的，'
                     '不是 ICTV 在这棵树上的标注。未映射的叶在页面上显式标灰。'),
            'tipsTotal': tot, 'tipsMapped': mapped, 'coverage': round(cov / 100.0, 4),
            'trees': len(out_trees),
        },
        'trees': out_trees,
    }
    txt = json.dumps(doc, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(txt)
    print()
    print('写出 %s  %d 字节  md5=%s'
          % (os.path.relpath(OUT, HERE), len(txt.encode('utf-8')),
             hashlib.md5(txt.encode('utf-8')).hexdigest()[:12]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
