/* W0-P1 (trust sweep: chrome, copy and cards) acceptance check, in a real Chrome (MASTER-PLAN §5.1, §5.0).

  node tools/check_w0_p1.cjs --out <built site> --shots <dir> [--tag after] [--now 2026-09-26T23:00] [--port 8101]

It serves <out> itself on 127.0.0.1:<port> (default 8101, the package's fixed port). Node binds the port
exclusively on Windows (libuv sets SO_EXCLUSIVEADDRUSE, never SO_REUSEADDR), so a port another agent holds is an
error here, not a silent share. Every response carries `X-Served-By: w0-p1-<git short sha>`, and the script
asserts it on the document and on one asset before it measures anything. /posters/* files the local build does
not have redirect to the live site, so the tiles that used to paint over the tab bar are real images.

Phones: isMobile + hasTouch at 360×740 DPR 3, 390×844 DPR 2, 375×667 DPR 2, and a 320×640 overflow pass.
Motion stays on (prefers-reduced-motion: no-preference): the tab-bar bug only exists with it.

Checks (each one of the package's acceptance lines):
  nav4        exactly 4 tab links, and elementFromPoint over every tab returns the nav, at several scroll depths
  plancontrast the ticket's «أضف للتقويم» / «تقويم Google» / «متى أطلع» links reach ≥ 4.5:1 on the paper
  manifest    no /#mine shortcut; /#now lands with the near box at the top of the screen
  hourly      «من وين الأسعار» says «كل ساعة»
  preload     no "preload … not used" console line on a repeat visit (service worker in control)
  shareask    the "opened with your friend's settings" bar sits above the tab bar
  fazaa       the Arabic text of /cards/fazaa/ has no «Page Not Found»
  uaq         Umm Al Quwain reads «سينما وحدة» (home list and its city page)
  terms       the ticket's terms (Star + Fazaa) name each condition once
  halls       no hall heading without an upcoming time under it (server HTML, script off)
  overflow    scrollWidth == innerWidth on every page checked, 0 page errors, at every width

Exit 0 when every check passes; the JSON summary is printed and written to <shots>/<tag>-results.json. */
"use strict";
const fs = require("fs");
const path = require("path");
const http = require("http");
const { execSync } = require("child_process");

function arg(name, dflt) {
  const i = process.argv.indexOf("--" + name);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}
function loadPlaywright() {
  const tries = [process.env.PLAYWRIGHT_PATH, "playwright", "C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright"];
  for (const t of tries) { if (!t) continue; try { return require(t); } catch (e) { /* next */ } }
  throw new Error("playwright not found (set PLAYWRIGHT_PATH)");
}

const OUT = path.resolve(arg("out", "out"));
const SHOTS = path.resolve(arg("shots", "shots-w0-p1"));
const TAG = arg("tag", "after");
const NOW = arg("now", "2026-09-26T23:00");
const PORT = +arg("port", "8101");
const ROOT = path.resolve(__dirname, "..");
let SHA = "nogit";
try { SHA = execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim(); } catch (e) { /* no git */ }
const SERVED_BY = "w0-p1-" + SHA;
const BASE = "http://127.0.0.1:" + PORT;
fs.mkdirSync(SHOTS, { recursive: true });

const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml",
  ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".woff2": "font/woff2", ".xml": "application/xml", ".txt": "text/plain" };

function serve() {
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, BASE);
    let p = decodeURIComponent(u.pathname);
    let f = path.join(OUT, p);
    if (!f.startsWith(OUT)) { res.writeHead(403); return res.end(); }
    if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
    const head = { "X-Served-By": SERVED_BY, "Cache-Control": "no-cache" };
    if (!fs.existsSync(f)) {
      if (p.startsWith("/posters/")) { res.writeHead(302, { ...head, Location: "https://cinema.elyoxe.com" + p }); return res.end(); }
      const nf = path.join(OUT, "404.html");
      res.writeHead(404, { ...head, "Content-Type": TYPES[".html"] });
      return res.end(fs.existsSync(nf) ? fs.readFileSync(nf) : "not found");
    }
    if (p === "/sw.js") head["Service-Worker-Allowed"] = "/";
    res.writeHead(200, { ...head, "Content-Type": TYPES[path.extname(f)] || "application/octet-stream" });
    res.end(fs.readFileSync(f));
  });
  return new Promise((ok, bad) => { srv.once("error", bad); srv.listen({ port: PORT, host: "127.0.0.1", exclusive: true }, () => ok(srv)); });
}

const PHONES = {
  p360: { viewport: { width: 360, height: 740 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
  p390: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  p375: { viewport: { width: 375, height: 667 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  p320: { viewport: { width: 320, height: 640 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};
const q = (u) => BASE + u + (u.includes("?") ? "&" : "?") + "now=" + encodeURIComponent(NOW);
const FILM = "/film/heart-of-the-beast/";
const STAR_CIN = "/dubai/star-al-ghurair-centre-dubai/";
const PAGES = ["/", FILM, "/dubai/reel-dubai-mall/", "/umm-al-quwain/", "/cards/fazaa/", "/coming/", "/en/"];

function lum(rgb) {
  const c = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function contrast(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
const rgbOf = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);

const results = { tag: TAG, servedBy: SERVED_BY, now: NOW, checks: {}, errors: [] };
function record(name, ok, detail) {
  const r = results.checks[name] || (results.checks[name] = { ok: true, detail: [] });
  r.ok = r.ok && !!ok; r.detail.push(detail);
}
async function settle(page, ms) { await page.waitForLoadState("load").catch(() => {}); await page.waitForTimeout(ms || 1200); }

(async () => {
  const srv = await serve();
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    /* 0. the server that answers is ours */
    {
      const ctx = await browser.newContext();
      const r1 = await ctx.request.get(BASE + "/"), r2 = await ctx.request.get(BASE + "/assets/cinema.css");
      const ok = r1.headers()["x-served-by"] === SERVED_BY && r2.headers()["x-served-by"] === SERVED_BY;
      record("served", ok, { doc: r1.headers()["x-served-by"], asset: r2.headers()["x-served-by"] });
      await ctx.close();
      if (!ok) throw new Error("another server answered on " + PORT);
    }

    /* the manifest: no /#mine, /#now kept */
    {
      const ctx = await browser.newContext();
      const m = await (await ctx.request.get(BASE + "/manifest.webmanifest")).json();
      const urls = (m.shortcuts || []).map((s) => s.url);
      record("manifest", !urls.includes("/#mine") && urls.includes("/#now"), { urls });
      await ctx.close();
    }

    for (const [name, dev] of Object.entries(PHONES)) {
      const ctx = await browser.newContext({ ...dev, reducedMotion: "no-preference", serviceWorkers: "block" });
      const page = await ctx.newPage();
      const errs = [];
      page.on("pageerror", (e) => errs.push(String(e)));

      /* overflow + page errors on every page the package touches (the chrome is on every page) */
      for (const u of PAGES) {
        await page.goto(q(u), { waitUntil: "load" }); await settle(page, 600);
        const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth,
          nav: (() => { const n = document.querySelector("nav.nav"); return n ? { sw: n.scrollWidth, cw: n.clientWidth } : null; })() }));
        record("overflow", m.sw <= m.iw && (!m.nav || m.nav.sw <= m.nav.cw + 1), { vp: name, u, ...m });
      }
      record("pageerrors", errs.length === 0, { vp: name, errs: errs.slice(0, 5) });
      if (name === "p375" || name === "p320") { await ctx.close(); continue; }

      /* nav4: four tabs, and each one is the nav under the finger at every scroll depth */
      for (const u of ["/", FILM]) {
        await page.goto(q(u), { waitUntil: "load" }); await settle(page, 1500);
        for (const y of [0, 500, 1100, 1900, 3000]) {
          await page.evaluate((y) => window.scrollTo(0, y), y); await page.waitForTimeout(250);
          const m = await page.evaluate(() => {
            const nav = document.querySelector("nav.nav"), links = nav ? [...nav.querySelectorAll("a")] : [];
            const hits = links.map((a) => {
              const r = a.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
              const inView = x >= 0 && x < innerWidth && y >= 0 && y < innerHeight;
              const el = inView ? document.elementFromPoint(x, y) : null;
              return { t: a.textContent.trim(), inView, hit: !!(el && el.closest("nav.nav")), el: el ? el.tagName + "." + el.className : null };
            });
            return { n: links.length, hits };
          });
          const ok = m.n === 4 && m.hits.every((h) => h.inView && h.hit);
          record("nav4", ok, { vp: name, u, y, n: m.n, bad: m.hits.filter((h) => !(h.inView && h.hit)) });
        }
      }
      await page.goto(q("/"), { waitUntil: "load" }); await settle(page, 1500);
      await page.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-home-top.png`) });
      await page.evaluate(() => window.scrollTo(0, 900)); await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-home-scrolled.png`) });

      /* hourly + uaq on home; footer carries the moved links */
      const home = await page.evaluate(() => ({
        srcs: (document.querySelector(".srcs .hint") || {}).textContent || "",
        uaq: ([...document.querySelectorAll(".clist li")].find((li) => li.querySelector('a[href="/umm-al-quwain/"]')) || {}).textContent || "",
        foot: [...document.querySelectorAll(".foot a")].map((a) => a.textContent.trim()) }));
      record("hourly", /كل ساعة/.test(home.srcs) && !/ثلاث مرات/.test(home.srcs), { vp: name, text: home.srcs });
      record("uaq", /سينما وحدة/.test(home.uaq), { vp: name, where: "home", text: home.uaq.trim() });
      record("footer", ["عربي وخليجي", "فعاليات", "صباح العيال"].every((t) => home.foot.includes(t)), { vp: name, foot: home.foot });
      const cl = await page.$(".cities");
      if (cl) { await cl.scrollIntoViewIfNeeded(); await cl.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-cities.png`) }); }
      const ft = await page.$(".foot");
      if (ft) { await ft.scrollIntoViewIfNeeded(); await page.waitForTimeout(200); await page.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-footer.png`) }); }
      await page.goto(q("/umm-al-quwain/"), { waitUntil: "load" }); await settle(page, 400);
      const lead = await page.evaluate(() => (document.querySelector(".head .lead") || {}).textContent || "");
      record("uaq", /سينما وحدة/.test(lead) && !/\b1 سينما/.test(lead), { vp: name, where: "city", text: lead });

      /* /#now: the shortcut lands on the near box */
      await page.goto(BASE + "/?now=" + encodeURIComponent(NOW) + "#now", { waitUntil: "load" }); await settle(page, 2500);
      const nowm = await page.evaluate(() => { const b = document.querySelector("[data-now]"); if (!b) return null;
        const r = b.getBoundingClientRect(); return { id: b.id, hidden: b.hidden, top: Math.round(r.top), sy: Math.round(scrollY), vis: getComputedStyle(b).visibility }; });
      record("manifest", !!nowm && !nowm.hidden && nowm.top >= -2 && nowm.top <= 80 && nowm.sy > 0, { vp: name, now: nowm });
      await page.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-hash-now.png`) });

      /* the ticket's plan links on paper */
      await page.goto(q(FILM), { waitUntil: "load" }); await settle(page, 1500);
      await page.waitForSelector(".fcity .tm:not(.past)", { timeout: 8000 }).catch(() => {});
      let tm = null;
      for (const el of await page.$$(".fcity .tm:not(.past)")) { if (await el.isVisible()) { tm = el; break; } }
      if (tm) {
        await tm.scrollIntoViewIfNeeded(); await tm.tap(); await page.waitForTimeout(1500);
        const pc = await page.evaluate(() => {
          const tk = document.querySelector(".ticket.open") || document.querySelector(".ticket:not([hidden])");
          const ls = tk ? [...tk.querySelectorAll(".plan-add .lnk")] : [];
          const bg = tk ? getComputedStyle(tk).backgroundColor : null;
          return { bg, links: ls.map((l) => ({ t: l.textContent.trim(), c: getComputedStyle(l).color })) };
        });
        const worst = pc.links.length ? Math.min(...pc.links.map((l) => contrast(rgbOf(l.c), rgbOf(pc.bg)))) : 0;
        record("plancontrast", pc.links.length >= 2 && worst >= 4.5, { vp: name, bg: pc.bg, links: pc.links, worst: +worst.toFixed(2) });
        await page.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-ticket.png`) });
      } else record("plancontrast", false, { vp: name, err: "no time button on the film page" });

      /* /cards/fazaa/: no raw English leak */
      await page.goto(q("/cards/fazaa/"), { waitUntil: "load" }); await settle(page, 400);
      const fz = await page.evaluate(() => document.body.innerText);
      record("fazaa", !/Page Not Found/i.test(fz), { vp: name, hasLeak: /Page Not Found/i.test(fz) });
      const vox = await page.$$(".cardrows .row.crd");
      for (const r of vox) {
        if (/فوكس/.test(await r.innerText())) { await r.scrollIntoViewIfNeeded(); await page.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-fazaa-vox.png`) }); break; }
      }
      await ctx.close();

      /* terms: a Star show with Fazaa chosen */
      const ctx2 = await browser.newContext({ ...dev, reducedMotion: "no-preference", serviceWorkers: "block" });
      await ctx2.addInitScript(() => { try { localStorage.setItem("cinema.card", "fazaa"); localStorage.setItem("cinema.city", "dubai"); } catch (e) {} });
      const p2 = await ctx2.newPage();
      await p2.goto(q(STAR_CIN), { waitUntil: "load" }); await settle(p2, 1500);
      let st = null;
      for (const el of await p2.$$(".tm[data-show]:not(.past)")) { if (await el.isVisible()) { st = el; break; } }
      if (st) {
        await st.scrollIntoViewIfNeeded(); await st.tap(); await p2.waitForTimeout(1200);
        const t = await p2.evaluate(() => { const e = document.querySelector(".ticket.open [data-tk-terms]") || document.querySelector("[data-tk-terms]"); return e ? e.textContent : ""; });
        const parts = t.split("،").map((s) => s.trim()).filter(Boolean);
        const dup = parts.filter((s, i) => parts.indexOf(s) !== i);
        const ok = t.length > 0 && dup.length === 0 && !(/لين \d+ تذاكر/.test(t) && /تذاكر باليوم/.test(t));
        record("terms", ok, { vp: name, text: t, dup });
        await p2.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-terms.png`) });
      } else record("terms", false, { vp: name, err: "no Star time" });
      await ctx2.close();

      /* shareask: a visitor with Dubai + Fazaa saved opens a friend's Sharjah + Esaad link */
      const ctx3 = await browser.newContext({ ...dev, reducedMotion: "no-preference", serviceWorkers: "block" });
      await ctx3.addInitScript(() => { try { if (!sessionStorage.getItem("seeded")) { localStorage.setItem("cinema.city", "dubai"); localStorage.setItem("cinema.card", "fazaa"); sessionStorage.setItem("seeded", "1"); } } catch (e) {} });
      const p3 = await ctx3.newPage();
      await p3.goto(q("/?city=sharjah&card=esaad"), { waitUntil: "load" }); await settle(p3, 2000);
      const sa = await p3.evaluate(() => {
        const b = document.querySelector(".shareask"), n = document.querySelector("nav.nav");
        if (!b || !n) return { bar: !!b, nav: !!n };
        const rb = b.getBoundingClientRect(), rn = n.getBoundingClientRect();
        const x = rn.left + rn.width / 2, y = rn.top + rn.height / 2, el = document.elementFromPoint(x, y);
        return { bar: true, barBottom: Math.round(rb.bottom), navTop: Math.round(rn.top), navHit: !!(el && el.closest("nav.nav")) };
      });
      record("shareask", sa.bar && sa.barBottom <= sa.navTop + 0.5 && sa.navHit, { vp: name, ...sa });
      await p3.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-shareask.png`) });
      await ctx3.close();
    }

    /* halls: the server's schedule, script off */
    {
      const ctx = await browser.newContext({ ...PHONES.p390, javaScriptEnabled: false });
      const page = await ctx.newPage();
      for (const u of [FILM, "/dubai/reel-dubai-mall/", "/dubai/vox-mall-of-the-emirates/", STAR_CIN]) {
        await page.goto(BASE + u, { waitUntil: "load" });
        const m = await page.evaluate(() => [...document.querySelectorAll(".hl")].filter((h) => {
          const live = h.querySelectorAll(".tm:not(.past)").length;
          const text = [...h.querySelectorAll(".tl")].map((t) => t.textContent).join(" ");
          return live === 0 && !/\d\d:\d\d/.test(text);
        }).map((h) => (h.textContent || "").trim().slice(0, 40)));
        record("halls", m.length === 0, { u, empty: m.length, sample: m.slice(0, 3) });
      }
      await ctx.close();
    }

    /* preload: a repeat visit with the service worker in control prints no "preload … not used" line */
    {
      const ctx = await browser.newContext({ ...PHONES.p390, reducedMotion: "no-preference" });
      const page = await ctx.newPage();
      const msgs = [];
      page.on("console", (m) => msgs.push(m.type() + ": " + m.text()));
      await page.goto(q("/"), { waitUntil: "load" }); await settle(page, 3000);
      const reg = await page.evaluate(async () => { try { const r = await Promise.race([navigator.serviceWorker.ready, new Promise((ok) => setTimeout(() => ok(null), 8000))]); return !!r; } catch (e) { return false; } });
      await page.reload({ waitUntil: "load" }); await settle(page, 1500);
      const ctrl1 = await page.evaluate(() => !!navigator.serviceWorker.controller);
      msgs.length = 0;
      await page.reload({ waitUntil: "load" }); await page.waitForTimeout(6000);
      const ctrl = await page.evaluate(() => !!navigator.serviceWorker.controller);
      const bad = msgs.filter((m) => /preload/i.test(m));
      record("preload", reg && ctrl && bad.length === 0, { registered: reg, controlled: ctrl1 && ctrl, lines: bad.slice(0, 5) });
      await ctx.close();
    }
  } catch (e) {
    results.errors.push(String(e && e.stack || e));
  } finally {
    await browser.close();
    srv.close();
  }
  results.ok = !results.errors.length && Object.values(results.checks).every((c) => c.ok);
  fs.writeFileSync(path.join(SHOTS, `${TAG}-results.json`), JSON.stringify(results, null, 1));
  const brief = Object.fromEntries(Object.entries(results.checks).map(([k, v]) => [k, v.ok]));
  console.log(JSON.stringify({ tag: TAG, ok: results.ok, servedBy: SERVED_BY, checks: brief, errors: results.errors }, null, 1));
  process.exit(results.ok ? 0 : 1);
})();
