import sys
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:8899/eve/index.html"
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console.%s: %s" % (m.type, m.text)) if m.type == "error" else None)

    pg.goto(BASE + "?view=dnarna"); pg.wait_for_timeout(2500)
    pg.click("#submodes button:nth-child(2)"); pg.wait_for_timeout(1800)
    pg.screenshot(path=OUT + "/x_dnarna_identified.png")

    pg.goto(BASE + "?view=matrix"); pg.wait_for_timeout(2500)
    pg.click("#submodes button:nth-child(2)"); pg.wait_for_timeout(1800)
    pg.screenshot(path=OUT + "/x_matrix_genus.png")

    pg.goto(BASE + "?view=host"); pg.wait_for_timeout(2500)
    pg.click("#submodes button:nth-child(3)"); pg.wait_for_timeout(1800)
    pg.screenshot(path=OUT + "/x_host_rna.png")

    pg.goto(BASE + "?view=tree"); pg.wait_for_timeout(3000)
    pg.screenshot(path=OUT + "/x_tree_top.png")

    print("errors:", errs[:10] if errs else "none")
    b.close()
