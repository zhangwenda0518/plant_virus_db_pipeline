import os, sys
from playwright.sync_api import sync_playwright
BASE = os.environ.get("EVE_BASE", "http://127.0.0.1:8899/eve/index.html")
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(BASE); pg.wait_for_timeout(2500)
    # i18n.js reads localStorage; must clear it first or the click flips zh->en
    pg.evaluate("() => localStorage.removeItem('pvdb_lang')")
    pg.reload(); pg.wait_for_timeout(2500)
    lang0 = pg.evaluate("() => document.documentElement.lang")
    title0 = pg.inner_text("#viewTitle")
    pg.click("#pvdb-lang-btn"); pg.wait_for_timeout(1700)
    lang1 = pg.evaluate("() => document.documentElement.lang")
    title1 = pg.inner_text("#viewTitle")
    v2 = pg.inner_text("#viewlist button:nth-child(2)")
    g1 = pg.inner_text("#fgroup label:nth-child(1)")
    print("html.lang : %s -> %s" % (lang0, lang1))
    print("viewTitle : %s -> %s" % (title0, title1))
    print("view btn2 : %s" % v2)
    print("group lbl : %s" % g1)
    pg.screenshot(path=OUT + "/x_zh_virus.png")
    pg.click("#viewlist button[data-view='host']"); pg.wait_for_timeout(2200)
    pg.screenshot(path=OUT + "/x_zh_host.png")
    pg.click("#viewlist button[data-view='dnarna']"); pg.wait_for_timeout(2000)
    pg.screenshot(path=OUT + "/x_zh_dnarna.png")
    print("errors:", errs[:8] if errs else "none")
    b.close()
