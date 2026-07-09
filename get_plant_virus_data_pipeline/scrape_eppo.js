/**
 * EPPO 植物病毒图片爬虫 — Puppeteer 版
 *
 * Usage:
 *   node scrape_eppo.js --limit 5 --delay 2000 -o eppo_photos.tsv
 */
const puppeteer = require('puppeteer');

const BASE = 'https://gd.eppo.int';
const LIST_URL = BASE + '/photos/virus';

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const args = process.argv.slice(2);
  const getArg = (name, def) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : def;
  };
  const limit = parseInt(getArg('--limit', '0'));
  const delay = parseInt(getArg('--delay', '2000'));
  const output = getArg('-o', 'eppo_virus_photos.tsv');

  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  await page.setUserAgent('Mozilla/5.0 (compatible; PlantVirusDB/1.0; research)');

  // Step 1: Get virus list
  console.log(`[1] Loading virus list: ${LIST_URL}`);
  await page.goto(LIST_URL, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(1000);

  const viruses = await page.evaluate(() => {
    const items = document.querySelectorAll('#listg li a[href*="/taxon/"]');
    return [...items].map(a => {
      const href = a.getAttribute('href') || '';
      const m = href.match(/\/taxon\/(\w+)\/photos/);
      return m ? { eppo_code: m[1], virus_name: a.textContent.replace(/\s*\([A-Z0-9]+\)\s*$/, '').trim() } : null;
    }).filter(Boolean);
  });
  console.log(`  -> ${viruses.length} viruses`);

  const toProcess = limit > 0 ? viruses.slice(0, limit) : viruses;

  // Step 2: Scrape each virus photo page
  const allPhotos = [];
  for (let i = 0; i < toProcess.length; i++) {
    const v = toProcess[i];
    const url = `${BASE}/taxon/${v.eppo_code}/photos`;
    console.log(`[${i+1}/${toProcess.length}] ${v.eppo_code} — ${v.virus_name.slice(0,60)}`);

    try {
      await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
      await sleep(1500);

      const photos = await page.evaluate((baseUrl) => {
        const items = document.querySelectorAll('#portfolio .grid-item');
        return [...items].map(item => {
          const img = item.querySelector('img');
          if (!img) return null;
          const src = img.getAttribute('src') || '';
          if (!src.includes('/pics/')) return null;
          const m = src.match(/\/(\d+)\.jpg/);
          const photoId = m ? m[1] : '';
          const thumbUrl = src.startsWith('http') ? src : baseUrl + src;
          const fullUrl = thumbUrl.replace('220x130', '1024x0');

          // Parse caption & photographer from <p> tags
          let caption = '', photographer = '';
          const paragraphs = item.querySelectorAll('p');
          paragraphs.forEach(p => {
            const text = p.textContent.trim();
            if (/courtesy/i.test(text)) {
              photographer = text.replace(/courtesy\s*:?\s*/i, '').trim();
            } else if (text) {
              caption = text;
            }
          });
          return { photo_id: photoId, thumb_url: thumbUrl, full_url: fullUrl, caption, photographer };
        }).filter(Boolean);
      }, BASE);

      photos.forEach(p => {
        p.eppo_code = v.eppo_code;
        p.virus_name = v.virus_name;
        p.photo_page = url;
      });
      allPhotos.push(...photos);

      const wCap = photos.filter(p => p.caption).length;
      const wPhot = photos.filter(p => p.photographer).length;
      console.log(`  -> ${photos.length} photos (${wCap} captions, ${wPhot} photographers)`);
      if (photos.length > 0) {
        const p = photos[0];
        console.log(`     [${p.photo_id}] ${(p.caption || '(no caption)').slice(0, 80)}`);
        console.log(`               ${p.photographer || '(no photographer)'}`);
      }
    } catch (e) {
      console.log(`  ! Error: ${e.message}`);
    }
    await sleep(delay);
  }

  // Write TSV
  const fs = require('fs');
  const header = 'eppo_code\tvirus_name\tphoto_id\tthumb_url\tfull_url\tcaption\tphotographer\tphoto_page\n';
  const rows = allPhotos.map(p =>
    [p.eppo_code, p.virus_name, p.photo_id, p.thumb_url, p.full_url, p.caption, p.photographer, p.photo_page]
      .map(v => (v || '').replace(/\t/g, ' ').replace(/\n/g, ' '))
      .join('\t')
  ).join('\n');

  fs.writeFileSync(output, header + rows, 'utf-8');
  console.log(`\nDone: ${allPhotos.length} photos -> ${output}`);

  const nCap = allPhotos.filter(p => p.caption).length;
  const nPhot = allPhotos.filter(p => p.photographer).length;
  console.log(`  Viruses: ${new Set(allPhotos.map(p => p.eppo_code)).size}`);
  console.log(`  With caption: ${nCap}, With photographer: ${nPhot}`);

  await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
