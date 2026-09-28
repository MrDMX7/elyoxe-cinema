#!/usr/bin/env node
// W1-D3 check: signals on a built site (legend MASTER-PLAN §5.2 W1-D3).
//
//   node tools/check_w1_d3.cjs --out <built site> --data <latest.json> [--stale reel] [--sha <short sha>]
//        [--label after|before] [--shots <dir>] [--posters <dir>]
//
// Serves --out on 127.0.0.1:8115 (W1-D3's fixed port, bound exclusively; every response carries
// X-Served-By: w1-d3-<sha>, asserted on the document and on one asset before anything is measured), then:
//   data   /data/pulse.json ≤ 8 KB gzipped, one row per showing film with the data's own first_seen, the coming
//          films with their release date; /data/rank.json's day lists in rank order, today and yesterday named;
//   label  every cinema page of the --stale chain says «أسعار <chain> من HH:MM» (its own read time, UAE clock)
//          under its prices, in both languages, and no cinema page of a fresh chain says anything;
//   pages  at 360x740 DPR3, 390x844 DPR2, 375x667 DPR2 and 320x640 DPR2 (isMobile, hasTouch): no horizontal
//          scroll (scrollWidth = clientWidth = innerWidth) and no page error on the stale chain's busiest cinema, a
//          fresh chain's cinema and /sources/; the label's own box fits (scrollHeight ≤ clientHeight, inside the
//          page width). Screenshots of the halls-and-prices end at 360 and 390 with --shots.
// --label before only measures and screenshots (the base code, for the report's before shots); it never fails.
// Playwright is the site repo's copy; Chrome is the installed one (channel 'chrome').
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');
const zlib = require('zlib');

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const OUT = path.resolve(args.out || 'out');
const DATA = path.resolve(args.data || 'data/latest.json');
const POSTERS = args.posters ? path.resolve(args.posters) : path.join(path.dirname(DATA), 'posters');
const LABEL = args.label || 'after';
const SHA = args.sha || 'dev';
const SHOTS = args.shots ? path.resolve(args.shots) : null;
const STALE = args.stale || null;
const PORT = 8115;
const SERVED_BY = `w1-d3-${SHA}`;
const STRICT = LABEL !== 'before';
const VIEWPORTS = [
  { name: '360', width: 360, height: 740, dpr: 3 },
  { name: '390', width: 390, height: 844, dpr: 2 },
  { name: '375', width: 375, height: 667, dpr: 2 },
  { name: '320', width: 320, height: 640, dpr: 2 },
];
const SHORT = { vox: ['فوكس', 'VOX'], star: ['ستار', 'Star'], novo: ['نوفو', 'Novo'], roxy: ['روكسي', 'Roxy'],
  reel: ['ريل', 'Reel'], cineroyal: ['سيني رويال', 'Cine Royal'], cinemacity: ['سينما سيتي', 'Cinemacity'] };

const fails = [];
const notes = [];
function check(ok, what) { if (!STRICT) return note(what); (ok ? notes : fails).push((ok ? 'ok   ' : 'FAIL ') + what); }
function note(what) { notes.push('     ' + what); }

const data = JSON.parse(fs.readFileSync(DATA, 'utf8'));
const uaeHM = (iso) => { const t = new Date(iso); const m = (t.getUTCHours() * 60 + t.getUTCMinutes() + 240) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`; };

// ------------------------------------------------------------------ the server
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.woff2': 'font/woff2',
  '.xml': 'application/xml', '.txt': 'text/plain; charset=utf-8', '.webmanifest': 'application/manifest+json' };
function serve(req, res) {
  const url = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
  const send = (code, body, type) => { res.writeHead(code, { 'Content-Type': type, 'X-Served-By': SERVED_BY, 'Cache-Control': 'no-store' }); res.end(body); };
  let file = path.join(OUT, url);
  if (url.startsWith('/posters/') && !fs.existsSync(file)) file = path.join(POSTERS, url.slice('/posters/'.length));
  if (!file.startsWith(OUT) && !file.startsWith(POSTERS)) return send(403, 'no', 'text/plain');
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  if (!fs.existsSync(file)) {
    const nf = path.join(OUT, '404.html');
    return send(404, fs.existsSync(nf) ? fs.readFileSync(nf) : 'not found', 'text/html; charset=utf-8');
  }
  send(200, fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
}
function listenExclusive() {
  return new Promise((resolve, reject) => {
    const server = http.createServer(serve);
    server.once('error', (e) => reject(new Error(`port ${PORT} is taken (${e.code}); another server must not answer this check`)));
    server.listen({ host: '127.0.0.1', port: PORT, exclusive: true }, () => resolve(server));
  });
}
function get(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (r) => { const b = []; r.on('data', (c) => b.push(c)); r.on('end', () => resolve({ status: r.statusCode, by: r.headers['x-served-by'], body: Buffer.concat(b) })); }).on('error', reject);
  });
}

// ------------------------------------------------------------------ the checks
async function main() {
  const server = await listenExclusive();
  const probe = await new Promise((resolve) => {
    const s = http.createServer(() => {});
    s.once('error', (e) => resolve(e.code));
    s.listen({ host: '127.0.0.1', port: PORT }, () => { s.close(); resolve('BOUND'); });
  });
  check(probe === 'EADDRINUSE' || probe === 'EACCES', `port ${PORT} held exclusively (a second bind got ${probe})`);
  const base = `http://127.0.0.1:${PORT}`;
  const doc = await get(base + '/');
  const asset = (doc.body.toString('utf8').match(/(?:href|src)="(\/assets\/[^"?]+\.(?:css|js))(?:\?[^"]*)?"/) || [])[1];
  const as = asset ? await get(base + asset) : { by: null };
  if (doc.by !== SERVED_BY || as.by !== SERVED_BY) { console.error(`X-Served-By ${doc.by} / ${as.by}, expected ${SERVED_BY}`); process.exit(2); }
  notes.push(`ok   X-Served-By ${SERVED_BY} on / and ${asset}`);

  // data files
  const pr = await get(base + '/data/pulse.json');
  const rr = await get(base + '/data/rank.json');
  if (pr.status === 200) {
    const gz = zlib.gzipSync(pr.body, { level: 9 }).length;
    const p = JSON.parse(pr.body.toString('utf8'));
    const showing = Object.entries(data.films).filter(([, f]) => f.status !== 'archived');
    const wrong = showing.filter(([fid, f]) => !p[fid] || p[fid][1] !== (f.first_seen || ''));
    const coming = Object.entries(data.coming || {}).filter(([fid, c]) => !p[fid] || p[fid][2] !== (c.release_date || ''));
    check(gz <= 8192, `/data/pulse.json ${pr.body.length} B, ${gz} B gzipped (≤ 8192)`);
    check(wrong.length === 0, `pulse.json: ${showing.length} showing films, ${wrong.length} missing or off film_history's first_seen; seed ${p._ && p._[1]}`);
    check(coming.length === 0, `pulse.json: ${Object.keys(data.coming || {}).length} coming films with their release date, ${coming.length} off`);
  } else check(false, `/data/pulse.json answers ${pr.status}`);
  if (rr.status === 200) {
    const r = JSON.parse(rr.body.toString('utf8'));
    const lists = [r.uae.d, r.uae.y, ...Object.values(r.c).flatMap((x) => [x.d, x.y])];
    const ordered = lists.every((l) => l.every((x, i) => i === 0 || l[i - 1][1] > x[1] || (l[i - 1][1] === x[1] && (l[i - 1][2] > x[2] || (l[i - 1][2] === x[2] && l[i - 1][0] < x[0])))));
    check(r.d === data.generated.slice(0, 10) && ordered, `/data/rank.json ${rr.body.length} B, ${zlib.gzipSync(rr.body).length} B gzipped: today ${r.d}, yesterday ${r.y}, UAE ${r.uae.d.length}/${r.uae.y.length} films, ${Object.keys(r.c).length} cities (yesterday per city in ${Object.values(r.c).filter((x) => x.y.length).length}), every list in rank order`);
  } else check(false, `/data/rank.json answers ${rr.status}`);

  // the label on the stale chain's prices (static HTML: every cinema page of every chain)
  const cinemas = Object.entries(data.cinemas).filter(([, c]) => c.city);
  if (STALE) {
    const at = data.chains[STALE].at;
    const [ar, en] = SHORT[STALE];
    const want = [`أسعار ${ar} من ${uaeHM(at)}`, `${en} prices from ${uaeHM(at)}`];
    let good = 0, bad = [];
    for (const [cid, c] of cinemas) {
      for (const [lang, pre] of [[0, ''], [1, 'en']]) {
        const f = path.join(OUT, pre, c.city, cid, 'index.html');
        if (!fs.existsSync(f)) continue;
        const h = fs.readFileSync(f, 'utf8');
        const m = h.match(/<p class="hint" data-read-old="([^"]*)">([^<]*)<\/p>/);
        if (c.chain === STALE) (m && m[1] === STALE && m[2] === want[lang] ? good++ : bad.push(`${pre}/${cid}: ${m ? m[2] : 'no label'}`));
        else if (m) bad.push(`${pre}/${cid}: ${m[2]} on a fresh chain`);
      }
    }
    check(good > 0 && bad.length === 0, `«${want[0]}» / "${want[1]}" on ${good} ${STALE} cinema pages, ${bad.length} wrong${bad.length ? ': ' + bad.slice(0, 3).join('; ') : ''}`);
  }

  // phones
  const count = {}; data.shows.forEach((s) => { count[s.cinema] = (count[s.cinema] || 0) + 1; });
  const busiest = (chain) => cinemas.filter(([, c]) => c.chain === chain).sort((a, b) => (count[b[0]] || 0) - (count[a[0]] || 0))[0];
  const staleCin = busiest(STALE || 'reel');
  const freshCin = busiest(STALE === 'vox' ? 'star' : 'vox');
  const pages = [['stale', `/${staleCin[1].city}/${staleCin[0]}/`], ['fresh', `/${freshCin[1].city}/${freshCin[0]}/`], ['sources', '/sources/']];
  const { chromium } = require('C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright');
  const browser = await chromium.launch({ channel: 'chrome' });
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.dpr, isMobile: true, hasTouch: true });
    for (const [name, url] of pages) {
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(String(e)));
      await page.goto(base + url, { waitUntil: 'load' });
      await page.waitForTimeout(500);
      const m = await page.evaluate(() => {
        const el = document.querySelector('[data-read-old]');
        const r = el && el.getBoundingClientRect();
        return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, iw: window.innerWidth,
          label: el ? { text: el.textContent, sh: el.scrollHeight, ch: el.clientHeight, left: r.left, right: r.right, color: getComputedStyle(el).color } : null };
      });
      check(m.sw === m.cw && m.cw === m.iw && errors.length === 0,
        `${vp.name} ${url}: scrollWidth ${m.sw} = clientWidth ${m.cw} = innerWidth ${m.iw}, ${errors.length} page error(s)${errors.length ? ' ' + errors[0] : ''}`);
      if (name === 'stale' && STALE) {
        const l = m.label;
        check(l && l.sh <= l.ch && l.left >= 0 && l.right <= m.iw,
          `${vp.name} label «${l && l.text}» fits: scrollHeight ${l && l.sh} ≤ clientHeight ${l && l.ch}, box ${l && Math.round(l.left)}–${l && Math.round(l.right)} in ${m.iw}, colour ${l && l.color}`);
      }
      if (name === 'fresh') check(!m.label, `${vp.name} ${url}: no label on a fresh chain`);
      if (SHOTS && name === 'stale' && (vp.name === '360' || vp.name === '390')) {
        await page.evaluate(() => {
          // the same spot before and after: the end of «القاعات والأسعار» (its last price table), label or not
          const hs = [...document.querySelectorAll('h2')].find((h) => /القاعات والأسعار|Halls and prices/.test(h.textContent));
          const sec = hs && hs.closest('section');
          const tables = sec ? sec.querySelectorAll('table.prices') : [];
          const target = tables.length ? tables[tables.length - 1] : sec;
          if (target) target.scrollIntoView({ block: 'start' });
        });
        await page.waitForTimeout(300);
        fs.mkdirSync(SHOTS, { recursive: true });
        await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${vp.name}-${staleCin[0]}.png`) });
      }
      if (SHOTS && name === 'sources' && (vp.name === '360' || vp.name === '390')) {
        await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${vp.name}-sources.png`), fullPage: true });
      }
      await page.close();
    }
    await ctx.close();
  }
  await browser.close();
  server.close();
  console.log(`W1-D3 check (${LABEL}) on ${OUT}, data ${DATA} generated ${data.generated}${STALE ? `, stale chain ${STALE} read ${data.chains[STALE].at}` : ''}`);
  console.log(notes.concat(fails).join('\n'));
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nall checks passed');
  process.exit(fails.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
