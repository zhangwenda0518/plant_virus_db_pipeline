"""
Scrape all vsiRNA data from PVsiRNAdb via Playwright.
"""
from playwright.sync_api import sync_playwright
import json, os, urllib.parse, re

OUTDIR = os.path.dirname(__file__) + "/data"

def extract_rows_from_page(page):
    """Extract all rows from current DataTable page."""
    return page.evaluate('''()=>{
        return Array.from(document.querySelectorAll("#employee-grid tbody tr")).map(tr=>{
            var tds = tr.querySelectorAll("td");
            if(tds.length < 8) return null;
            return [tds[0]?tds[0].textContent.trim():"", tds[1]?tds[1].textContent.trim():"",
                    tds[2]?tds[2].textContent.trim():"", tds[3]?tds[3].textContent.trim():"",
                    tds[4]?tds[4].textContent.replace(/<[^>]+>/g,"").trim():"",
                    tds[5]?tds[5].textContent.replace(/<[^>]+>/g,"").trim():"",
                    tds[6]?tds[6].textContent.trim():"",
                    tds[7]?tds[7].textContent.replace(/<[^>]+>/g,"").trim():""];
        }).filter(r=>r);
    }''')

def clean_rows(rows, seen_ids):
    """Filter placeholder rows and deduplicate by PVsiRNA_ID.

    Returns (kept_rows, n_placeholder, n_dupe).
    """
    kept, n_ph, n_dup = [], 0, 0
    for r in rows:
        pid = (r[0] or '').strip() if r else ''
        if not pid or pid.startswith('No matching records'):
            n_ph += 1
            continue
        if pid in seen_ids:
            n_dup += 1
            continue
        seen_ids.add(pid)
        kept.append(r)
    return kept, n_ph, n_dup


def main():
    seen_ids = set()
    page_mismatches = []
    n_placeholder = n_dupe = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Get browse entries
        page.goto('http://14.139.61.8/PVsiRNAdb/bro.php', timeout=30000)
        page.wait_for_timeout(3000)
        entries = page.evaluate('''()=>{
            return Array.from(document.querySelectorAll('a')).map(a=>{
                var href = a.getAttribute('href') || '';
                var m = href.match(/n=([^&]+)/);
                return m ? decodeURIComponent(m[1]) : null;
            }).filter(n=>n && !/^\\d+$/.test(n));
        }''')
        entries = sorted(list(set(entries)))
        print(f'Found {len(entries)} browse entries', flush=True)

        all_data = {}
        total = 0
        tsv_path = os.path.join(OUTDIR, 'pvsirnadb_vsirna.tsv')
        with open(tsv_path, 'w') as f:
            f.write('PVsiRNA_ID\tPlant_Common\tPlant_Scientific\tVirus_Abbr\tVirus_Name\tPMID\tTissue\tSequence\n')

        for i, entry in enumerate(entries):
            encoded = urllib.parse.quote(entry)
            url = f'http://14.139.61.8/PVsiRNAdb/plant1.php?n={encoded}&bs=2'

            try:
                page.goto(url, timeout=60000, wait_until='networkidle')
                page.wait_for_timeout(1000)
            except:
                print(f'  [{i+1}/{len(entries)}] {entry[:50]} - NO DATA', flush=True)
                page_mismatches.append((entry, 'goto failed'))
                continue

            # Get total count
            info = page.evaluate('()=>{var el=document.querySelector("#employee-grid_info");return el?el.textContent:"";}')
            m = re.search(r'of\s+([\d,]+)\s+entries', info)
            total_count = int(m.group(1).replace(',','')) if m else 0

            if total_count == 0:
                print(f'  [{i+1}/{len(entries)}] {entry[:50]} - EMPTY', flush=True)
                continue

            # Use DataTable API to show all rows at once
            page.evaluate(f'''()=>{{
                var table = $('#employee-grid').DataTable();
                table.page.len({total_count}).draw(false);
            }}''')

            # Wait for all rows to render
            try:
                page.wait_for_function(f'()=>document.querySelectorAll("#employee-grid tbody tr").length >= {total_count}', timeout=30000)
            except:
                pass
            page.wait_for_timeout(2000)

            rows_raw = extract_rows_from_page(page)

            # Page-integrity check: extracted rows must match the page's own total
            if len(rows_raw) != total_count:
                page_mismatches.append(
                    (entry, f'page_total={total_count} extracted={len(rows_raw)}'))

            # Dedup by PVsiRNA_ID + skip placeholder rows
            rows_data, n_ph, n_dup = clean_rows(rows_raw, seen_ids)
            n_placeholder += n_ph
            n_dupe += n_dup

            all_data[entry] = rows_data
            total += len(rows_data)

            print(f'  [{i+1}/{len(entries)}] {entry[:50]:50s} -> {len(rows_data):>6} rows '
                  f'(dupes {n_dup}, placeholders {n_ph}, total {total:,})', flush=True)

            # Save incrementally
            with open(tsv_path, 'a') as f:
                for r in rows_data:
                    f.write('\t'.join(r) + '\n')

        browser.close()

    # Save JSON
    with open(os.path.join(OUTDIR, 'pvsirnadb_all_data.json'), 'w') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f'\nTotal: {len(entries)} entries, {total:,} vsiRNA records '
          f'({n_dupe:,} duplicate IDs and {n_placeholder:,} placeholder rows removed)', flush=True)

    # Final assertion: every entry's extracted row count must equal the page total_count
    if page_mismatches:
        for entry, why in page_mismatches[:20]:
            print(f'  MISMATCH: {entry[:60]} -> {why}', flush=True)
        raise AssertionError(
            f'{len(page_mismatches)} entries where extracted rows != page total_count; '
            'scrape is incomplete -- do not use the TSV until fixed')

if __name__ == '__main__':
    main()
