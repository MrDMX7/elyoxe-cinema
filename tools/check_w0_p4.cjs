#!/usr/bin/env node
// W0-P4 check: data truth on a built site (legend MASTER-PLAN §4.1 #31–#36).
//
//   node tools/check_w0_p4.cjs --out <built site> --data <latest.json> [--raw <data/raw>] [--posters <dir>]
//        [--sha <short sha>] [--label after|before] [--shots <dir>]
//
// Serves --out on 127.0.0.1:8104 (W0-P4's fixed port, bound exclusively; every response carries
// X-Served-By: w0-p4-<sha>, asserted on the document and on one asset before anything is measured), then:
//   data   every Star show links to its own show (or the film-level fallback), no not-a-film event is a film,
//          «قلب الوحش» sits within 5 min of the chains' median runtime (--raw), VOX's next-day shows are priced
//          and every borrowed price is dated today;
//   pages  at 360x740 DPR3, 390x844 DPR2, 375x667 DPR2 and 320x640 DPR2 (isMobile, hasTouch): no horizontal
//          scroll and no page error on the film page, a Star cinema page and a VOX cinema page; the film page
//          prints the median runtime; every time link on the Star page ends at start + ad offset + the film's
//          runtime; the dining event has no film page; a tapped Star time books its own show.
// --label before only measures and screenshots (the live code, for the report's before shots); it never fails.
// Playwright is the site repo's copy; Chrome is the installed one (channel 'chrome').
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const OUT = path.resolve(args.out || 'out');
const DATA = path.resolve(args.data || 'data/latest.json');
const POSTERS = args.posters ? path.resolve(args.posters) : path.join(path.dirname(DATA), 'posters');
const LABEL = args.label || 'after';
const SHA = args.sha || 'dev';
const SHOTS = args.shots ? path.resolve(args.shots) : null;
const PORT = 8104;
const SERVED_BY = `w0-p4-${SHA}`;
const STRICT = LABEL !== 'before';
const STAR_SHOW = /^https:\/\/www\.starcinemas\.ae\/now-showing-single-show-booking\/(\d+)\/(\d+)\/(\d+)\/(\d+)$/;
const STAR_FILM = /^https:\/\/www\.starcinemas\.ae\/now-showing-booking\/(\d+)\/1\/$/;
const VIEWPORTS = [
  { name: '360', width: 360, height: 740, dpr: 3 },
  { name: '390', width: 390, height: 844, dpr: 2 },
  { name: '375', width: 375, height: 667, dpr: 2 },
  { name: '320', width: 320, height: 640, dpr: 2 },
];

const fails = [];
const notes = [];
function check(ok, what) { (ok ? notes : fails).push((ok ? 'ok   ' : 'FAIL ') + what); }
function note(what) { notes.push('     ' + what); }

// ------------------------------------------------------------------ the data
const data = JSON.parse(fs.readFileSync(DATA, 'utf8'));
const chainOf = (s) => (data.cinemas[s.cinema] || {}).chain;
const today = data.generated.slice(0, 10);
const addMin = (hhmm, m) => { const [h, mm] = hhmm.split(':').map(Number); const t = (h * 60 + mm + m) % 1440; return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`; };

const star = data.shows.filter((s) => chainOf(s) === 'star');
const starShow = star.filter((s) => STAR_SHOW.test(s.book || '')).length;
const starBad = star.filter((s) => !STAR_SHOW.test(s.book || '') && !STAR_FILM.test(s.book || ''));
if (STRICT) check(star.length > 0 && starBad.length === 0, `Star links: ${starShow}/${star.length} show-level, ${starBad.length} neither show- nor film-level`);
else note(`Star links: ${starShow}/${star.length} show-level`);

const dining = Object.entries(data.films).filter(([fid, f]) => /^immersive dining\s+-\s+/i.test(f.title || ''));
if (STRICT) check(dining.length === 0 && (data.event_shows || []).length > 0, `not-a-film events: ${dining.length} in films, ${(data.event_shows || []).length} in event_shows`);
else note(`not-a-film events in films: ${dining.map(([f]) => f).join(', ') || 'none'}`);

const hotb = (data.films['heart-of-the-beast'] || {}).runtime;
if (args.raw) {
  const per = {};
  for (const f of fs.readdirSync(args.raw).filter((n) => n.endsWith('.json') && !n.startsWith('.'))) {
    const raw = JSON.parse(fs.readFileSync(path.join(args.raw, f), 'utf8'));
    const rts = (raw.shows || []).filter((s) => /^heart of the beast$/i.test((s.film_title || '').trim()) && s.runtime).map((s) => s.runtime);
    if (!rts.length) continue;
    const count = {}; rts.forEach((r) => { count[r] = (count[r] || 0) + 1; });
    per[f.replace('.json', '')] = Number(Object.keys(count).sort((a, b) => count[b] - count[a] || a - b)[0]);
  }
  const v = Object.values(per).sort((a, b) => a - b);
  const med = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
  const line = `«قلب الوحش» runtime ${hotb} against the chains' median ${med} (${Object.entries(per).map(([c, r]) => c + '=' + r).join(' ')})`;
  if (STRICT) check(Math.abs(hotb - med) <= 5, line); else note(line);
} else note(`«قلب الوحش» runtime ${hotb}`);

const days = [...new Set(data.shows.map((s) => s.date))].sort();
const later = days.filter((d) => d > today);
for (const d of later) {
  const vox = data.shows.filter((s) => chainOf(s) === 'vox' && s.date === d);
  const priced = vox.filter((s) => s.prices && s.prices.length).length;
  const borrowed = vox.filter((s) => s.price_basis === 'today');
  const dated = borrowed.every((s) => s.price_source === 'table' && s.price_checked === today);
  const line = `VOX ${d}: ${priced}/${vox.length} priced (${Math.round(100 * priced / Math.max(vox.length, 1))}%), ${borrowed.length} borrowed from today`;
  if (STRICT) check(dated && priced / Math.max(vox.length, 1) >= 0.9, line + (dated ? ', every one dated today' : ', NOT all dated'));
  else note(line);
}

// ------------------------------------------------------------------ the server
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.xml': 'application/xml', '.txt': 'text/plain; charset=utf-8',
  '.webmanifest': 'application/manifest+json', '.ics': 'text/calendar' };
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

function head(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (r) => { r.resume(); r.on('end', () => resolve({ status: r.statusCode, by: r.headers['x-served-by'], type: r.headers['content-type'] })); }).on('error', reject);
  });
}

// ------------------------------------------------------------------ the pages
async function main() {
  const server = await listenExclusive();
  // a second bind on the same port must fail: nothing else can answer in our place
  const probe = await new Promise((resolve) => {
    const s = http.createServer(() => {});
    s.once('error', (e) => resolve(e.code));
    s.listen({ host: '127.0.0.1', port: PORT }, () => { s.close(); resolve('BOUND'); });
  });
  check(probe === 'EADDRINUSE' || probe === 'EACCES', `port ${PORT} held exclusively (a second bind got ${probe})`);
  const base = `http://127.0.0.1:${PORT}`;
  const doc = await head(base + '/');
  const homeHtml = fs.readFileSync(path.join(OUT, 'index.html'), 'utf8');
  const asset = (homeHtml.match(/(?:href|src)="(\/[^"]+\.(?:css|js))"/) || [])[1];
  const as = asset ? await head(base + asset) : { by: null };
  check(doc.by === SERVED_BY && as.by === SERVED_BY, `X-Served-By ${SERVED_BY} on / and ${asset}`);
  const ev = await head(base + '/film/immersive-dining-iv-elements-of-hoshena/');
  if (STRICT) check(ev.status === 404, `/film/immersive-dining-iv-elements-of-hoshena/ answers ${ev.status}`);
  else note(`/film/immersive-dining-iv-elements-of-hoshena/ answers ${ev.status}`);

  const starCinema = Object.keys(data.cinemas).find((cid) => cid === 'star-bawadi-mall-al-ain') || Object.keys(data.cinemas).find((cid) => data.cinemas[cid].chain === 'star');
  const voxCinema = (() => {
    const n = {};
    data.shows.filter((s) => s.price_basis === 'today').forEach((s) => { n[s.cinema] = (n[s.cinema] || 0) + 1; });
    return Object.keys(n).sort((a, b) => n[a] - n[b])[0] || Object.keys(data.cinemas).find((cid) => data.cinemas[cid].chain === 'vox');
  })();
  const pages = [
    ['film', '/film/heart-of-the-beast/'],
    ['star', `/${data.cinemas[starCinema].city}/${starCinema}/`],
    ['vox', `/${data.cinemas[voxCinema].city}/${voxCinema}/`],
  ];
  const offsets = {}; Object.entries(data.chains).forEach(([c, v]) => { offsets[c] = v.ad_offset_min ?? 15; });

  const { chromium } = require('C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright');
  const browser = await chromium.launch({ channel: 'chrome' });
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.dpr, isMobile: true, hasTouch: true });
    for (const [name, url] of pages) {
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(String(e)));
      await page.goto(base + url, { waitUntil: 'load' });
      await page.waitForTimeout(600);
      const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
      check(m.sw === m.iw && errors.length === 0, `${vp.name} ${url}: scrollWidth ${m.sw} = innerWidth ${m.iw}, ${errors.length} page error(s)${errors.length ? ' ' + errors[0] : ''}`);

      if (name === 'film' && vp.name === '360') {
        const rt = await page.evaluate(() => {
          const dt = [...document.querySelectorAll('dt')].find((x) => x.textContent.trim() === 'المدة');
          return dt ? dt.nextElementSibling.textContent.trim() : null;
        });
        if (STRICT) check(rt === `${hotb} د`, `film page «المدة» reads «${rt}» (data: ${hotb})`); else note(`film page «المدة» reads «${rt}»`);
      }
      if (name === 'star' && vp.name === '360') {
        const links = await page.$$eval('a.tm', (as) => as.map((a) => ({ href: a.getAttribute('href'), start: a.dataset.start, ends: a.dataset.ends, show: a.dataset.show })));
        const bad = links.filter((l) => !STAR_SHOW.test(l.href));
        // ends = start + the chain's ad offset + the film's (median) runtime, for every time on the page
        const byBook = {}; data.shows.forEach((s) => { if (s.cinema === starCinema) byBook[s.book] = s; });
        const wrongEnd = links.filter((l) => { const s = byBook[l.href]; const f = s && data.films[s.film]; return s && f && f.runtime && l.ends !== addMin(l.start, f.runtime + (offsets.star ?? 15)); });
        if (STRICT) check(links.length > 0 && bad.length === 0 && wrongEnd.length === 0, `${url}: ${links.length} time links, ${bad.length} not show-level, ${wrongEnd.length} ending off the film's runtime`);
        else note(`${url}: ${links.length} time links, ${links.length - bad.length} show-level`);
      }
      if (SHOTS && (vp.name === '360' || vp.name === '390')) {
        if (name === 'film') {
          await page.evaluate(() => { const dt = [...document.querySelectorAll('dt')].find((x) => x.textContent.trim() === 'المدة'); if (dt) dt.scrollIntoView({ block: 'center' }); });
          await page.waitForTimeout(300);
          await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${vp.name}-film-runtime.png`) });
        }
        if (name === 'star') {
          // the first Heart of the Beast time still open to book (a started show is disabled by the page)
          const sid = await page.evaluate(() => {
            const open = [...document.querySelectorAll('a.tm')].filter((a) => !a.matches('[aria-disabled="true"],[disabled],.past,.off'));
            const a = open.find((x) => /\/2389\/?(1\/)?$/.test(x.getAttribute('href'))) || open[0];
            return a ? a.dataset.show : null;
          });
          const hb = sid && await page.$(`a.tm[data-show="${sid}"]`);
          if (hb) {
            await hb.scrollIntoViewIfNeeded();
            await hb.click();
            await page.waitForTimeout(900);
            const clicked = await hb.getAttribute('href');
            const book = await page.evaluate(() => [...document.querySelectorAll('[data-tk-book]')]
              .filter((x) => x.offsetParent).map((x) => ({ href: x.getAttribute('href'), text: x.textContent.trim() })));
            if (STRICT) check(book.length > 0 && book.every((b) => b.href === clicked && STAR_SHOW.test(b.href)),
              `${vp.name} Star ticket: «${book.map((b) => b.text).join('/')}» opens ${book.map((b) => b.href).join(' ')} (the tapped show: ${clicked})`);
            else note(`${vp.name} Star ticket: «${book.map((b) => b.text).join('/')}» opens ${book.map((b) => b.href).join(' ')}`);
            const endsText = await page.evaluate(() => { const t = document.body.innerText.match(/يخلص تقريباً[^\n]*/); return t ? t[0] : null; });
            note(`${vp.name} ticket: ${endsText}`);
            await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${vp.name}-star-ticket.png`) });
          }
        }
      }
      await page.close();
    }
    await ctx.close();
  }
  await browser.close();
  server.close();
  console.log(`W0-P4 check (${LABEL}) on ${OUT}, data ${DATA} generated ${data.generated}`);
  console.log(notes.concat(fails).join('\n'));
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nall checks passed');
  process.exit(fails.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
