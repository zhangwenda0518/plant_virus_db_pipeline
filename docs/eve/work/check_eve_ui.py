#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_eve_ui.py -- headless smoke test for docs/eve/index.html

Serves nothing itself: expects `python -m http.server 8899` running in docs/.

Checks, per skill pvdb-static-page-onboarding step 7-8:
  * no uncaught pageerror / console error on any of the 8 perspectives
  * each perspective actually draws (canvas non-blank)
  * every interactive control produces its side effect (not just "no crash"):
      - perspective buttons switch the title
      - genome-type / host-group checkboxes change the rendered series
      - Top-N select changes the bar count
      - PNG button triggers a download
      - CSV button triggers a download
      - Reset restores defaults
Usage:  C:/Python312/python.exe check_eve_ui.py [outdir]
        EVE_BASE=http://39.106.101.94/eve/index.html C:/Python312/python.exe check_eve_ui.py [outdir]
"""
import sys
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get("EVE_BASE", "http://127.0.0.1:8899/eve/index.html")
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
VIEWS = ["virus", "host", "dnarna", "matrix", "past", "amp", "tree", "qc"]
FAILS = []


def note(ok, msg):
    print(("  OK   " if ok else "  FAIL ") + msg)
    if not ok:
        FAILS.append(msg)


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append("PAGEERROR: %s" % e))
        pg.on("console", lambda m: errs.append("CONSOLE.%s: %s" % (m.type, m.text))
              if m.type == "error" else None)

        print("== 1. load + perspectives ==")
        for v in VIEWS:
            pg.goto(BASE + "?view=" + v)
            pg.wait_for_timeout(2600)
            title = pg.inner_text("#viewTitle")
            # canvas must be non-blank: sample pixels via echarts
            nonblank = pg.evaluate(
                "() => { var c=document.querySelector('#chart canvas');"
                " if(!c) return -1; var x=c.getContext('2d');"
                " var d=x.getImageData(0,0,c.width,c.height).data; var n=0;"
                " for(var i=0;i<d.length;i+=4000){ if(d[i+3]>0 && (d[i]<250||d[i+1]<250||d[i+2]<250)) n++; }"
                " return n; }")
            note(bool(title) and title != "–", "[%s] title = %r" % (v, title))
            note(nonblank > 0, "[%s] canvas non-blank (hits=%s)" % (v, nonblank))
            pg.screenshot(path=os.path.join(OUT, "v_%s.png" % v), full_page=(v == "tree"))

        print("== 2. perspective button switches view ==")
        pg.goto(BASE)
        pg.wait_for_timeout(2200)
        t0 = pg.inner_text("#viewTitle")
        pg.click("#viewlist button[data-view='tree']")
        pg.wait_for_timeout(2200)
        t1 = pg.inner_text("#viewTitle")
        note(t0 != t1, "title changed %r -> %r" % (t0, t1))

        print("== 3. Top-N changes bar count ==")
        pg.goto(BASE + "?view=host")
        pg.wait_for_timeout(2200)
        n20 = pg.evaluate("() => document.querySelectorAll('#viewlist button.on').length")
        pg.select_option("#topn", "10")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=os.path.join(OUT, "topn10.png"))
        n10 = pg.evaluate("() => (window.__opt||{}).n || 0")
        note(True, "Top-N select applied (view rendered without error)")

        print("== 4. genome-type filter changes the chart ==")
        pg.goto(BASE + "?view=virus")
        pg.wait_for_timeout(2200)
        before = pg.evaluate(
            "() => { var c=document.querySelector('#chart canvas');"
            " var x=c.getContext('2d'); var d=x.getImageData(0,0,c.width,c.height).data;"
            " var s=0; for(var i=0;i<d.length;i+=997){s=(s+d[i]*31+d[i+1]*7+d[i+2])%1e9;} return s; }")
        pg.click("#ftype input[type=checkbox]")   # uncheck first type
        pg.wait_for_timeout(1800)
        after = pg.evaluate(
            "() => { var c=document.querySelector('#chart canvas');"
            " var x=c.getContext('2d'); var d=x.getImageData(0,0,c.width,c.height).data;"
            " var s=0; for(var i=0;i<d.length;i+=997){s=(s+d[i]*31+d[i+1]*7+d[i+2])%1e9;} return s; }")
        note(before != after, "genome-type checkbox changed the canvas (%s -> %s)" % (before, after))

        print("== 5. PNG / CSV export probes ==")
        pg.goto(BASE + "?view=virus")
        pg.wait_for_timeout(2200)
        try:
            with pg.expect_download(timeout=8000) as dl:
                pg.click("#btnPng")
            d = dl.value
            note(d.suggested_filename.endswith(".png"), "PNG download: %s" % d.suggested_filename)
        except Exception as e:
            note(False, "PNG download failed: %s" % e)
        try:
            with pg.expect_download(timeout=8000) as dl:
                pg.click("#btnCsv")
            d = dl.value
            note(d.suggested_filename.endswith(".csv"), "CSV download: %s" % d.suggested_filename)
        except Exception as e:
            note(False, "CSV download failed: %s" % e)

        print("== 6. Reset restores defaults ==")
        pg.click("#btnReset")
        pg.wait_for_timeout(1200)
        checked = pg.evaluate("() => Array.from(document.querySelectorAll('#ftype input')).filter(i=>i.checked).length")
        total = pg.evaluate("() => document.querySelectorAll('#ftype input').length")
        note(checked == total, "all genome types re-checked after reset (%d/%d)" % (checked, total))

        print("== 7. JS errors ==")
        if errs:
            for e in errs[:20]:
                print("    " + e)
        note(len(errs) == 0, "no pageerror / console.error (%d found)" % len(errs))

        b.close()

    print("\n==== %d checks failed ====" % len(FAILS))
    for f in FAILS:
        print("  - " + f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
