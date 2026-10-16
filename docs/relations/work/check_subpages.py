# -*- coding: utf-8 -*-
"""验收：/relations/ 的四个 hash 是否真的成了「子页面」。
   ① 各自独立 title  ② permalink 指本页  ③ 按钮打开本页 hash  ④ 切语言 title 跟着变
用法（随页面部署在 /relations/work/，默认打线上）：
    C:/Python312/python.exe check_subpages.py
    REL_SKIP=vector ...          # 跳过某个视图（本地无 /vector/ 时用）
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get('REL_BASE', 'http://39.106.101.94/relations/')
SKIP = set(x for x in (os.environ.get('REL_SKIP') or '').split(',') if x)
ALL = ['sankey', 'graph', 'tvh', 'vector']
VIEWS = [v for v in ALL if v not in SKIP]
EXPECT_TITLE = {
    'sankey': 'Association flow',
    'graph': 'Virus – host network',
    'tvh': 'Vector – virus – host network',
    'vector': 'Vector & evidence library',
}
SUFFIX = 'Virus–Vector–Host Relations'

fails, passes = [], []
def check(cond, msg):
    (passes if cond else fails).append(msg)
    print(('  PASS  ' if cond else '  FAIL  ') + msg)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1440, 'height': 900})
    titles = {}
    for h in VIEWS:
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(BASE + '#' + h, wait_until='domcontentloaded')
        page.wait_for_selector('#stage iframe')
        page.wait_for_timeout(2200)
        d = page.evaluate("""() => {
          const on = document.querySelector('.strip button.vtab.on');
          const pm = document.querySelector('.head .desc .from a');
          const bo = document.getElementById('btn-open');
          return {active: on ? on.dataset.view : null,
                  title: document.title,
                  permalinkHref: pm ? pm.getAttribute('href') : null,
                  permalinkText: pm ? pm.innerText.trim() : null,
                  btnLabel: bo ? bo.innerText.trim() : null,
                  btnTarget: bo ? bo.dataset.target : null};
        }""")
        print('\n[%s]' % h)
        print('   title      = %r' % d['title'])
        print('   permalink  = %r -> %r' % (d['permalinkText'], d['permalinkHref']))
        print('   btn-open   = %r  target=%s' % (d['btnLabel'], d['btnTarget']))
        check(d['active'] == h, '[%s] hash 直达对应视图' % h)
        check(EXPECT_TITLE[h] in d['title'] and SUFFIX in d['title'],
              '[%s] title 含视图名与站点名（%r）' % (h, d['title']))
        check(d['permalinkHref'] == '#' + h,
              '[%s] permalink 指向本页锚点（%r）' % (h, d['permalinkHref']))
        check('/relations/' in (d['permalinkText'] or ''),
              '[%s] permalink 文案是 /relations/#%s' % (h, h))
        check('Open in new tab' in d['btnLabel'],
              '[%s] 按钮文案已改（%r）' % (h, d['btnLabel']))
        check(not errs, '[%s] 无 JS 错误（%d）' % (h, len(errs)))
        titles[h] = d['title']
        page.close()

    check(len(set(titles.values())) == len(titles),
          '四个子页面 title 互不相同（%d 个唯一）' % len(set(titles.values())))

    # 按钮真的打开本页 hash，而不是独立路由
    page = ctx.new_page()
    page.goto(BASE + '#graph', wait_until='domcontentloaded')
    page.wait_for_selector('#stage iframe')
    page.wait_for_timeout(2000)
    with ctx.expect_page() as pi:
        page.click('#btn-open')
    np = pi.value
    np.wait_for_load_state('domcontentloaded')
    u = np.url
    check('/relations/#graph' in u, '点按钮打开的是本页子页面（%s）' % u)
    check('/network/' not in u, '点按钮不再打开独立路由 /network/')
    np.close()

    # 切语言：title 要跟着变中文
    page.evaluate("localStorage.removeItem('pvdb_lang')")
    page.reload(wait_until='domcontentloaded')
    page.wait_for_selector('#stage iframe')
    page.wait_for_timeout(1800)
    t_en = page.title()
    page.click('.acts button.act.langtab')
    page.wait_for_timeout(1200)
    t_zh = page.title()
    print('\n[语言] en=%r  ->  zh=%r' % (t_en, t_zh))
    check(t_en != t_zh, '切语言后 title 跟着变')
    check('病毒-媒介-宿主关系' in t_zh, '中文 title 含中文站点名')
    check('病毒–宿主网络' in t_zh, '中文 title 含当前子页面名（%r）' % t_zh)
    page.close()
    b.close()

print('\n' + '=' * 66)
print('RESULT  %d passed, %d failed' % (len(passes), len(fails)))
for f in fails:
    print('  FAIL: ' + f)
sys.exit(1 if fails else 0)
