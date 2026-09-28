#!/usr/bin/env node
/* W0-P3 (the trust sweep, client behaviour; plan §4.1 #23–#30): drives a built site in Chrome at phone sizes and
   checks what the package promises. It serves the build itself, on its own port, and asserts its own
   X-Served-By header on the document and on an asset before measuring anything (plan §5.0, measurement
   isolation: another agent's server on the same port must not answer for this one).

     node tools/check_w0_p3.cjs --out out [--port 8103] [--shots DIR --label after] [--no-assert] [--only a,b]

   Needs a build of real data whose shows include 2026-09-27 evening in Dubai (the Fold's latest.json of 26–27
   September). Playwright: PLAYWRIGHT (a path to the package), else the elyoxe site's copy on the laptop.
   Scenarios: now (#24 pick, #23 link and landing), gone (#23 a started show, on screen after a cold landing), sort
   (#25), late (#26 late line and VALARM), desk (#27), deskgone (#23 + #27, a started show's link on desktop), box
   (#28), seats (#29), gonedeep (#23, a started show far down the page, cold), hall (#30), oracle (#30, every block judged after the clock runs), focus (#26, the minute
   keeps a focused link), fit (no sideways scroll, no page error at 360/390/375/320). "now" feeds "gone" and
   "deskgone". */
"use strict";
const fs = require("fs"), path = require("path"), http = require("http"), net = require("net"), cp = require("child_process");

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf("--" + k); return i >= 0 ? argv[i + 1] : d; };
const flag = (k) => argv.includes("--" + k);
const ROOT = path.resolve(__dirname, "..");
const OUT = path.resolve(arg("out", path.join(ROOT, "out")));
const PORT = +arg("port", 8103);
const SHOTS = arg("shots", null);
const LABEL = arg("label", "after");
const ASSERT = !flag("no-assert");
const ONLY = (arg("only", "") || "").split(",").filter(Boolean);
const PW = process.env.PLAYWRIGHT || "C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright";
const { chromium } = require(PW);

let sha = "nogit";
try { sha = cp.execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim(); } catch (e) {}
const SERVED = "w0-p3-" + sha;
const BASE = "http://127.0.0.1:" + PORT;
const DAY = "2026-09-27";
const at = (hm, d) => new Date((d || DAY) + "T" + hm + ":00+04:00");

/* ---------------------------------------------------------------- the server (this build, this port only) */
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
  ".woff2": "font/woff2", ".webmanifest": "application/manifest+json", ".xml": "application/xml", ".txt": "text/plain; charset=utf-8" };
function serve() {
  return new Promise((resolve, reject) => {
    const probe = net.connect(PORT, "127.0.0.1");
    probe.on("connect", () => { probe.destroy(); reject(new Error("port " + PORT + " is already answering: another server owns it")); });
    probe.on("error", () => {
      const srv = http.createServer((req, res) => {
        let p = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
        let f = path.join(OUT, p);
        if (!f.startsWith(OUT)) { res.writeHead(403); return res.end(); }
        if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
        const head = { "X-Served-By": SERVED, "Cache-Control": "no-store" };
        if (!fs.existsSync(f)) {
          const nf = path.join(OUT, "404.html");
          res.writeHead(404, Object.assign({ "Content-Type": TYPES[".html"] }, head));
          return res.end(fs.existsSync(nf) && !p.startsWith("/data/") ? fs.readFileSync(nf) : "not found");
        }
        res.writeHead(200, Object.assign({ "Content-Type": TYPES[path.extname(f)] || "application/octet-stream" }, head));
        res.end(fs.readFileSync(f));
      });
      srv.on("error", reject);
      srv.listen({ port: PORT, host: "127.0.0.1", exclusive: true }, () => resolve(srv));
    });
  });
}

/* ---------------------------------------------------------------- results */
const results = [];
function check(name, ok, detail) { results.push({ name, ok: !!ok, detail: detail == null ? "" : String(detail) }); console.log((ok ? "PASS " : "FAIL ") + name + (detail ? "  — " + detail : "")); }
const PHONES = { 360: { w: 360, h: 740, dpr: 3 }, 390: { w: 390, h: 844, dpr: 2 }, 375: { w: 375, h: 667, dpr: 2 }, 320: { w: 320, h: 640, dpr: 2 } };
const errors = [];
let browser;
async function ctxAt(vp, when, opts) {
  opts = opts || {};
  const phone = PHONES[vp];
  const c = await browser.newContext(phone
    ? { viewport: { width: phone.w, height: phone.h }, deviceScaleFactor: phone.dpr, isMobile: true, hasTouch: true, locale: "ar-AE", timezoneId: "Asia/Dubai", serviceWorkers: "block" }
    : { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1, locale: "ar-AE", timezoneId: "Asia/Dubai", serviceWorkers: "block" });
  await c.clock.install({ time: when });
  const ls = Object.assign({ "cinema.city": "dubai" }, opts.ls || {});
  await c.addInitScript((kv) => { try { for (const k in kv) localStorage.setItem(k, kv[k].replace("{NOW}", String(Date.now()))); } catch (e) {} }, ls);
  const p = await c.newPage();
  p.on("pageerror", (e) => errors.push(vp + " " + p.url() + " " + e.message));
  return { c, p };
}
async function shot(p, name) { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await p.screenshot({ path: path.join(SHOTS, LABEL + "-" + name + ".png") }); } }
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
function slice(city, d) { return JSON.parse(fs.readFileSync(path.join(OUT, "data", city + "-" + d + ".json"), "utf8")); }
function shows(city, d) {
  const j = slice(city, d);
  return j.S.map((a) => ({ c: j.C[a[0]][0], chain: j.C[a[0]][1], f: j.F[a[1]][0], t: a[2], k: j.H[a[3]][1].split("|").slice(1).join("|"), d: d }));
}
const GEO = () => JSON.parse(fs.readFileSync(path.join(OUT, "data", "cinemas.json"), "utf8"));

/* ---------------------------------------------------------------- scenarios */
async function headerCheck() {
  const { c, p } = await ctxAt(390, at("22:03"));
  const r = await p.goto(BASE + "/");
  const js = await p.evaluate(() => [...document.scripts].map((s) => s.src).filter((s) => /\/assets\/cinema\.[0-9a-f]+\.js$/.test(s))[0] || null);
  const ra = js ? await c.request.get(js) : null;
  check("served by this package (document and bundle carry X-Served-By " + SERVED + ")",
    r.headers()["x-served-by"] === SERVED && ra && ra.headers()["x-served-by"] === SERVED, r.headers()["x-served-by"]);
  await c.close();
  if (r.headers()["x-served-by"] !== SERVED) throw new Error("another server answered: refusing to measure");
}

/* #24 + #23: «الحين» picks a film worth it inside the window, links to its show, and the tap opens that ticket */
async function scenarioNow(vp) {
  const { c, p } = await ctxAt(vp, at("22:03"));
  await p.goto(BASE + "/");
  await p.waitForFunction(() => { const b = document.querySelector("[data-now]"); return b && !b.hidden && (b.querySelector("[data-now-film]") || {}).textContent; }, null, { timeout: 15000 });
  const box = p.locator("[data-now]");
  await box.scrollIntoViewIfNeeded();
  await shot(p, "home-now-" + vp);
  const href = await box.getAttribute("href");
  const verd = await p.evaluate(() => { const o = {}; document.querySelectorAll("[data-fid][data-v]").forEach((e) => { o[e.getAttribute("data-fid")] = e.getAttribute("data-v"); }); return o; });
  const lo = at("22:03").getTime(), hi = lo + 45 * 60e3;
  const win = shows("dubai", DAY).filter((s) => { const t = at(s.t).getTime(); return t >= lo && t <= hi; });
  const good = win.filter((s) => verd[s.f] === "yes" || verd[s.f] === "mixed").sort((a, b) => at(a.t) - at(b.t));
  const m = /^\/film\/([^/?#]+)\/#s-([0-9a-z]{6,7})$/.exec(href || "");
  check(vp + " «الحين» links to /film/<fid>/#s-<key> with no ? anywhere", m && href.indexOf("?") < 0, href);
  const fid = m ? m[1] : null;
  check(vp + " «الحين» at 22:03 picks a «يستاهل»/«بين بين» film when one starts inside the window",
    !good.length || verd[fid] === "yes" || verd[fid] === "mixed", fid + " (" + verd[fid] + "); first good: " + (good[0] ? good[0].f + " " + good[0].t : "none"));
  const exp = good[0] || win.sort((a, b) => at(a.t) - at(b.t))[0];
  const nowTime = await p.locator("[data-now-time]").getAttribute("data-t");
  await box.tap();
  await p.waitForURL(/\/film\//, { timeout: 15000 });
  let opened = false;
  try { await p.waitForSelector(".ticket.open, .ticket[role=region]", { timeout: 6000 }); opened = true; } catch (e) {}
  await wait(500);
  const tk = await p.evaluate(() => { const t = document.querySelector("[data-ticket]"); return t ? { open: t.classList.contains("open"), cin: t.getAttribute("data-cin"), time: (t.querySelector("[data-tk-time]") || {}).textContent, search: location.search, hash: location.hash } : null; });
  await shot(p, "now-tap-" + vp);
  check(vp + " the tap lands on the film page with that show's ticket open",
    opened && tk && tk.open && tk.time === nowTime && (!exp || tk.cin === exp.c) && tk.search === "" && /^#s-/.test(tk.hash),
    JSON.stringify(tk) + " expected " + (exp ? exp.c + " " + exp.t : "?") + " now-box " + nowTime);
  await c.close();
  return { href, exp };
}

/* #23: a show link whose show has started says so over that cinema's next times */
async function scenarioGone(vp, link) {
  if (!link || !link.exp) { check(vp + " started show link (no link to test)", false); return; }
  const start = at(link.exp.t).getTime();
  const { c, p } = await ctxAt(vp, new Date(start + 7 * 60e3));
  await p.goto(BASE + link.href);
  let msg = null;
  try { await p.waitForSelector("[data-gone]", { timeout: 6000 }); msg = await p.locator("[data-gone]").textContent(); } catch (e) {}
  const open = await p.evaluate(() => { const t = document.querySelector("[data-ticket]"); return !!(t && t.classList.contains("open")); });
  /* a fresh context is a cold landing (no cached fonts): the line must be on screen after the web fonts swap in,
     without the check scrolling to it (review M1) */
  await p.evaluate(() => document.fonts.ready); await wait(500);
  const pos = await p.evaluate(() => { const e = document.querySelector("[data-gone]"); if (!e) return null; const r = e.getBoundingClientRect();
    return { top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight, fonts: document.fonts.status }; });
  await shot(p, "gone-" + vp);
  check(vp + " a started show's link says «هالعرض بدأ، هذي الأوقات الجاية» and opens no ticket", msg === "هالعرض بدأ، هذي الأوقات الجاية" && !open, msg);
  check(vp + " on a cold landing the line is on screen once the fonts are in (not scrolled to by the check)",
    pos && pos.top >= 0 && pos.bottom <= pos.vh, JSON.stringify(pos));
  await c.close();
}

/* the show key, as ticket.js computes it (FNV-1a 32 over the UTF-8 of «cinema|date|time|hall key», base36, pad 6) */
function showKey(cin, d, t, hk) {
  let h = 0x811c9dc5;
  for (const b of Buffer.from([cin, d, t, hk || "Standard"].join("|"), "utf8")) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
  const k = h.toString(36);
  return k.length < 6 ? ("00000" + k).slice(-6) : k;
}
/* #23, review M1: a started show far down the heaviest film page (a cinema block thousands of pixels below the top,
   where the font swap moves it most), on a cold landing: the line is on screen once the fonts are in */
async function scenarioGoneDeep(vp) {
  const fid = "heart-of-the-beast", list = shows("dubai", DAY).filter((s) => s.f === fid);
  const by = {}; list.forEach((s) => { (by[s.c] = by[s.c] || []).push(s); });
  const cands = Object.keys(by).map((c) => by[c].sort((a, b) => (a.t < b.t ? -1 : 1))).filter((xs) => xs.length > 1 && xs[0].t >= "10:00");
  const pickC = cands.find((xs) => xs[0].c === "vox-city-centre-mirdif") || cands[cands.length - 1];
  if (!pickC) { check(vp + " deep started-show link (no case)", false); return; }
  const s = pickC[0], when = new Date(at(s.t).getTime() + 10 * 60e3);
  const { c, p } = await ctxAt(vp, when);
  await p.goto(BASE + "/film/" + fid + "/#s-" + showKey(s.c, s.d, s.t, s.k));
  await p.waitForSelector("[data-gone]", { timeout: 6000 }).catch(() => {});
  await p.evaluate(() => document.fonts.ready); await wait(600);
  const pos = await p.evaluate(() => { const e = document.querySelector("[data-gone]"); if (!e) return null; const r = e.getBoundingClientRect();
    return { top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight, sy: Math.round(scrollY), sh: document.documentElement.scrollHeight }; });
  await shot(p, "gone-deep-" + vp);
  check(vp + " cold landing on a started show deep in the page (" + s.c + " " + s.t + " " + s.k + "): the line is on screen once the fonts are in",
    pos && pos.top >= 0 && pos.bottom <= pos.vh, JSON.stringify(pos));
  await c.close();
}

/* #23 + #27 on desktop: a started show's link leaves the column on an upcoming show from the start (review M2) */
async function scenarioDeskGone(link) {
  if (!link || !link.exp) { check("desktop started-show link (no link to test)", false); return; }
  const when = new Date(at(link.exp.t).getTime() + 7 * 60e3);
  const { c, p } = await ctxAt("desk", when);
  await p.goto(BASE + link.href);
  await p.waitForSelector("[data-gone]", { timeout: 6000 }).catch(() => {});
  await wait(800);
  const got = await p.evaluate(() => {
    const t = document.querySelector("[data-ticket]"), on = document.querySelector(".cgs .tm.on"), pick = t && t.querySelector("[data-tk-pick]");
    const d = on && on.closest("[data-d]") && on.closest("[data-d]").getAttribute("data-d");
    return { gone: !!document.querySelector("[data-gone]"), pick: pick ? pick.textContent : null, time: t && (t.querySelector("[data-tk-time]") || {}).textContent,
      d: d, t: on && on.getAttribute("data-start"), city: on && on.closest(".fcity") && on.closest(".fcity").getAttribute("data-city") };
  });
  const up = got.d && got.t && new Date(got.d + "T" + got.t + ":00+04:00").getTime() >= when.getTime();
  check("desktop, a started show's link: the line shows and the column is an upcoming show in the visitor's city at once (or «اختار وقت»)",
    got.gone && (got.pick === "اختار وقت" || (up && got.city === "dubai" && got.time === got.t)), JSON.stringify(got));
  await c.close();
}

/* #26 (review I1): the minute rewrites the leave-by line, never the links, so a focused «أضف للتقويم» keeps its focus,
   on desktop and inside the phone sheet, with and without a place */
async function scenarioFocus() {
  for (const vp of ["desk", 390]) {
    for (const withLoc of [false, true]) {
      const ls = withLoc ? { "cinema.loc": "25.2,55.3,{NOW}" } : {};
      const { c, p } = await ctxAt(vp, at("12:40"), { ls });
      await p.goto(BASE + "/film/heart-of-the-beast/");
      await wait(1200);
      if (vp !== "desk") {
        const tm = p.locator(".cgs .tm[data-start]:not(.past):not(.x)").first();
        await tm.scrollIntoViewIfNeeded(); await tm.tap();
        await p.waitForSelector(".ticket.open .plan-add a[download]", { timeout: 8000 }).catch(() => {});
        await wait(600);
      }
      const st = () => p.evaluate(() => { const a = document.activeElement, l = document.querySelector(".ticket .plan-leave");
        return { cal: !!a && a.matches('.ticket .plan-add a[download]'), inTicket: !!a && !!a.closest(".ticket"), tag: a && a.tagName, line: l ? l.textContent : null }; });
      const ok = await p.evaluate(() => { const a = document.querySelector(".ticket .plan-add a[download]"); if (!a) return false; a.focus(); return document.activeElement === a; });
      const a0 = await st();
      await c.clock.runFor(61e3); await wait(300);
      const a1 = await st();
      const lineOk = !withLoc || (a0.line && a1.line && (a0.line.indexOf("لو طلعت") !== 0 || a0.line !== a1.line));
      check((vp === "desk" ? "desktop" : vp + " phone sheet") + (withLoc ? ", place known" : ", no place") + ": «أضف للتقويم» keeps the focus across the minute",
        ok && a0.cal && a1.cal && a1.inTicket && lineOk, JSON.stringify({ before: a0, after: a1 }));
      await c.close();
    }
  }
}

/* #30 in the page: after the clock has run, every block with times and none to come is hidden, and no other block is
   hidden for the clock's sake (the filters' own xf aside) */
async function scenarioOracle(vp) {
  const { c, p } = await ctxAt(vp, new Date(DAY + "T21:58:30+04:00"));
  await p.goto(BASE + "/film/heart-of-the-beast/");
  await p.waitForSelector(".cgs .tm[data-start]", { timeout: 10000 });
  const past0 = await p.evaluate(() => document.querySelectorAll(".cgs .tm.past").length);
  await c.clock.runFor(180e3); await wait(300);
  const got = await p.evaluate(() => {
    const GONE = ".hl, .tl, .scin, .cg, .cf, .srow, .fcity, .day[data-d]", bad = [];
    let n = 0, ran = 0;
    document.querySelectorAll(GONE).forEach((el) => {
      if (el.closest(".similar, [data-ticket]")) return;
      const ts = [...el.querySelectorAll(".tm[data-start]")];
      const r = ts.length > 0 && !ts.some((a) => !a.classList.contains("past") && !a.closest(".times[hidden]"));
      n++; if (r) ran++;
      if (el.classList.contains("x") !== (el.classList.contains("xf") || r)) bad.push(el.className + " " + (el.getAttribute("data-cin") || el.getAttribute("data-hk") || ""));
    });
    return { n, ran, bad: bad.slice(0, 4), past: document.querySelectorAll(".cgs .tm.past").length, empty: [...document.querySelectorAll("[data-empty]")].some((e) => !e.hidden) };
  });
  check(vp + " film page, 3 minutes of the clock (" + (got.past - past0) + " times struck): the hidden blocks are exactly those with no time to come, and no «ما في شي يطابق»",
    got.bad.length === 0 && got.past > past0 && got.ran > 0 && !got.empty, JSON.stringify(got));
  await c.close();
}

/* #25: «الأحسن تقييم» puts scored films first (both scores, then one, then none) */
async function scenarioSort(vp) {
  const { c, p } = await ctxAt(vp, at("20:00"));
  await p.goto(BASE + "/");
  await p.waitForFunction(() => { const b = document.querySelector("[data-now]"); return b && !b.hidden; }, null, { timeout: 15000 });
  const chip = p.locator('[data-sort="verdict"]').first();
  await chip.scrollIntoViewIfNeeded(); await chip.tap(); await wait(300);
  const got = await p.evaluate(() => {
    let sc = null; try { sc = JSON.parse(document.getElementById("cinema-sc").textContent); } catch (e) {}
    const tiles = [...document.querySelectorAll("[data-films] .film[data-fid]")].filter((e) => !e.classList.contains("x") && !e.classList.contains("off"));
    const r = tiles[0] && tiles[0].getBoundingClientRect();
    return { sc, order: tiles.map((e) => [e.getAttribute("data-fid"), e.getAttribute("data-v")]), firstInView: !!r && r.right > 0 && r.left < innerWidth };
  });
  check(vp + " after the sort, the row starts at its first film (in view)", got.firstInView, got.order[0] && got.order[0][0]);
  await p.locator("[data-films]").scrollIntoViewIfNeeded();
  await shot(p, "sort-" + vp);
  if (!got.sc) { check(vp + " «الأحسن تقييم» has the page's scores (#cinema-sc)", false, "no #cinema-sc"); await c.close(); return; }
  const tier = (f) => { const s = got.sc[f[0]]; if (!s) return 2; return s[0] != null && s[1] != null ? 0 : 1; };
  const sum = (f) => { const s = got.sc[f[0]] || []; return (s[0] || 0) + (s[1] || 0); };
  let ok = true, why = "";
  for (let i = 1; i < got.order.length; i++) {
    const a = got.order[i - 1], b = got.order[i];
    if (tier(a) > tier(b) || (tier(a) === tier(b) && tier(a) === 0 && sum(a) < sum(b))) { ok = false; why = a[0] + " before " + b[0]; break; }
  }
  check(vp + " «الأحسن تقييم» ranks scored films first, by critics + audience", ok && got.order.length > 3, why || got.order.slice(0, 6).map((f) => f[0]).join(" > "));
  await c.close();
}

/* #26: a leave-by already past gives the late line; the .ics alarm is at the leave-by */
async function scenarioLate(vp) {
  const geo = GEO();
  const s = shows("dubai", DAY).filter((x) => x.f === "heart-of-the-beast" && x.t >= "22:00" && geo[x.c])[0];
  if (!s) { check(vp + " late leave-by (no show to test)", false); return; }
  const g = geo[s.c], loc = { lat: +(g[2] + 0.05).toFixed(3), lng: +g[3].toFixed(3) };
  const R = Math.PI / 180, dl = Math.sin((loc.lat - g[2]) * R / 2), dg = Math.sin((loc.lng - g[3]) * R / 2);
  const km = 12742 * Math.asin(Math.min(1, Math.sqrt(dl * dl + Math.cos(g[2] * R) * Math.cos(loc.lat * R) * dg * dg)));
  const mins = Math.round(km * 1.35 / (km > 30 ? 90 : 60) * 60) + 10;
  const start = at(s.t).getTime(), now = start - mins * 60e3 + 11 * 60e3;
  const { c, p } = await ctxAt(vp, new Date(now), { ls: { "cinema.loc": loc.lat + "," + loc.lng + ",{NOW}" } });
  await p.goto(BASE + "/film/" + s.f + "/");
  const sel = '.cg[data-cin="' + s.c + '"] .hl[data-hk="' + s.k + '"] .times[data-d="' + DAY + '"] .tm[data-start="' + s.t + '"]';
  await p.waitForSelector(sel, { timeout: 10000 });
  const b = p.locator(sel).first();
  await b.scrollIntoViewIfNeeded(); await b.tap();
  let line = null;
  try { await p.waitForSelector(".ticket.open .plan-leave", { timeout: 8000 }); line = await p.locator(".ticket .plan-leave").textContent(); } catch (e) {}
  const ics = await p.evaluate(() => { const a = document.querySelector('.ticket a[download="cinema.ics"]'); return a ? decodeURIComponent(a.getAttribute("href").split(",").slice(1).join(",")) : ""; });
  const trig = (/TRIGGER:(\S+)/.exec(ics) || [])[1];
  const arrive = new Date(start + 11 * 60e3 + 4 * 3600e3).toISOString().slice(11, 16);
  await wait(700);   /* the sheet's slide-in is a real-time CSS transition */
  await p.evaluate(() => { const t = document.querySelector(".ticket.open"); const l = t && t.querySelector(".plan-leave"); if (l) l.scrollIntoView({ block: "center" }); });
  await wait(200);
  await shot(p, "late-" + vp);
  check(vp + " leave-by passed 11 min ago: the late line («لو طلعت الحين توصل " + arrive + "…»)",
    !!line && line.indexOf("لو طلعت الحين توصل " + arrive) === 0 && line.indexOf("بعد ما يبدأ بـ11 دقيقة") > 0, line);
  check(vp + " the .ics VALARM is the leave-by (" + mins + " min before the start)", trig === "-PT" + mins + "M", trig);
  await c.close();
}

/* #27: the desktop ticket is never a show that has started */
async function scenarioDesk() {
  const when = at("22:30");
  const { c, p } = await ctxAt("desk", when);
  await p.goto(BASE + "/film/heart-of-the-beast/");
  await wait(1200);
  const got = await p.evaluate(() => {
    const t = document.querySelector("[data-ticket]"), on = document.querySelector(".cgs .tm.on");
    const pick = t && t.querySelector("[data-tk-pick]");
    const d = on && on.closest("[data-d]") && on.closest("[data-d]").getAttribute("data-d");
    return { pick: pick ? pick.textContent : null, time: t && (t.querySelector("[data-tk-time]") || {}).textContent, d: d, t: on && on.getAttribute("data-start"),
      city: on && on.closest(".fcity") && on.closest(".fcity").getAttribute("data-city"), cin: t && t.getAttribute("data-cin") };
  });
  await shot(p, "desk-ticket-1280");
  const up = got.d && got.t && new Date(got.d + "T" + got.t + ":00+04:00").getTime() >= when.getTime();
  check("desktop film ticket at 22:30 is the next upcoming show in the visitor's city (or «اختار وقت»)",
    got.pick === "اختار وقت" || (up && got.city === "dubai" && got.time === got.t), JSON.stringify(got));
  await c.close();
  /* a visitor whose city has no show of this film left: the column asks for a time instead of offering another city's */
  const inCity = (cty) => new Set([].concat(...["2026-09-26", DAY].map((d) => { try { return shows(cty, d).map((s) => s.f); } catch (e) { return []; } })));
  const fuj = inCity("fujairah"), fid = [...inCity("dubai")].filter((f) => !fuj.has(f) && shows("dubai", DAY).some((s) => s.f === f && s.t > "22:45"))[0];
  if (!fid) return;
  const x = await ctxAt("desk", when, { ls: { "cinema.city": "fujairah" } });
  await x.p.goto(BASE + "/film/" + fid + "/");
  await wait(1200);
  const pk = await x.p.evaluate(() => { const t = document.querySelector("[data-ticket]"), e = t && t.querySelector("[data-tk-pick]");
    return { pick: e ? e.textContent : null, shown: t ? [...t.children].filter((c) => getComputedStyle(c).display !== "none").length : -1 }; });
  await shot(x.p, "desk-pick-1280");
  check("desktop ticket, visitor in Fujairah, film not showing there: «اختار وقت» and nothing else on the paper",
    pk.pick === "اختار وقت" && pk.shown === 1, fid + " " + JSON.stringify(pk));
  const tm = x.p.locator(".cgs .tm[data-start]:not(.past):not(.x)").first();
  await tm.scrollIntoViewIfNeeded(); await tm.click(); await wait(1200);
  const back = await x.p.evaluate(() => { const t = document.querySelector("[data-ticket]");
    return { pick: !!t.querySelector("[data-tk-pick]"), top: getComputedStyle(t.querySelector(".tk-top")).display !== "none",
      plan: !!t.querySelector(".plan-add"), time: (t.querySelector("[data-tk-time]") || {}).textContent }; });
  check("a tapped time fills the paper again after «اختار وقت» (the plan links come back)", !back.pick && back.top && back.plan, JSON.stringify(back));
  await x.c.close();
}

/* #28: Star + Fazaa (box office only) leads with «الخصم من الشباك بس» and the way there */
async function scenarioBox(vp) {
  const cin = Object.entries(GEO()).filter(([k, v]) => v[0] === "dubai" && v[1] === "star")
    .map(([k]) => k).filter((k) => shows("dubai", DAY).some((s) => s.c === k && s.t >= "22:10"))[0];
  if (!cin) { check(vp + " Star + Fazaa (no Star cinema with a show)", false); return; }
  const { c, p } = await ctxAt(vp, at("22:03"), { ls: { "cinema.card": "fazaa" } });
  await p.goto(BASE + "/dubai/" + cin + "/");
  const b = p.locator('.day[data-d="' + DAY + '"] .tm[data-start]:not(.past)').first();
  await b.scrollIntoViewIfNeeded(); await b.tap();
  await p.waitForSelector(".ticket.open", { timeout: 8000 }).catch(() => {});
  await wait(1200);
  const a = await p.evaluate(() => { const x = document.querySelector("[data-tk-book]"); return x ? { text: x.textContent, href: x.getAttribute("href") } : null; });
  await p.evaluate(() => { const x = document.querySelector("[data-tk-book]"); if (x) x.scrollIntoView({ block: "end" }); });
  await shot(p, "star-fazaa-" + vp);
  check(vp + " Star + Fazaa: the ticket's button says «الخصم من الشباك بس» and leads to the cinema",
    a && a.text === "الخصم من الشباك بس" && /^https:\/\/www\.google\.com\/maps\//.test(a.href), JSON.stringify(a));
  await c.close();
}

/* #29: no request for a seats file that does not exist, across 20 ticket taps */
async function scenarioSeats(vp) {
  const { c, p } = await ctxAt(vp, at("18:00"));
  const miss = [], asked = [];
  p.on("response", (r) => { if (/\/data\/seats\//.test(r.url())) { asked.push(r.url()); if (r.status() === 404) miss.push(r.url()); } });
  await p.goto(BASE + "/film/heart-of-the-beast/");
  await p.waitForSelector(".cgs .tm[data-start]", { timeout: 10000 });
  const n = await p.evaluate(() => document.querySelectorAll(".cgs .tm[data-start]:not(.past):not(.x)").length);
  let taps = 0;
  for (let i = 0; i < n && taps < 20; i += Math.max(1, Math.floor(n / 25))) {
    const b = p.locator(".cgs .tm[data-start]:not(.past):not(.x)").nth(i);
    if (!(await b.isVisible())) continue;
    await b.scrollIntoViewIfNeeded(); await b.tap(); taps++;
    await p.waitForSelector(".ticket.open", { timeout: 5000 }).catch(() => {});
    await wait(250);
    await p.keyboard.press("Escape"); await wait(250);
  }
  await wait(800);
  check(vp + " " + taps + " ticket taps: 0 requests to a missing /data/seats/*.json", taps >= 20 && miss.length === 0,
    miss.length + " missing of " + asked.length + " seats requests (" + [...new Set(asked.map((u) => u.split("/data/seats/")[1]))].slice(0, 5).join(", ") + ")");
  await c.close();
}

/* #30: a hall whose last time passes hides without a reload */
async function scenarioHall(vp) {
  const probe = await ctxAt(vp, at("12:00"));
  const cins = Object.entries(GEO()).filter(([k, v]) => v[0] === "dubai").map(([k]) => k);
  let pick = null;
  for (const cin of cins) {
    await probe.p.goto(BASE + "/dubai/" + cin + "/");
    pick = await probe.p.evaluate((DAY) => {
      const hls = [...document.querySelectorAll('.day[data-d="' + DAY + '"] .cf .hl')];
      for (const hl of hls) {
        const ts = [...hl.querySelectorAll(".tm[data-start]")].map((a) => a.getAttribute("data-start")).sort();
        const last = ts[ts.length - 1], cf = hl.closest(".cf");
        const later = [...cf.querySelectorAll(".hl")].some((o) => o !== hl && [...o.querySelectorAll(".tm[data-start]")].some((a) => a.getAttribute("data-start") > last));
        if (last && last >= "17:00" && last <= "21:30" && later) return { fid: cf.getAttribute("data-fid"), hk: hl.getAttribute("data-hk"), last };
      }
      return null;
    }, DAY);
    if (pick) { pick.cin = cin; break; }
  }
  await probe.c.close();
  if (!pick) { check(vp + " hall hides (no hall to test)", false); return; }
  const last = at(pick.last).getTime();
  const { c, p } = await ctxAt(vp, new Date(last - 60e3));
  await p.goto(BASE + "/dubai/" + pick.cin + "/");
  const sel = '.day[data-d="' + DAY + '"] .cf[data-fid="' + pick.fid + '"] .hl[data-hk="' + pick.hk + '"]';
  await p.waitForSelector(sel, { timeout: 10000 });
  const before = await p.locator(sel).isVisible();
  await p.locator(sel).scrollIntoViewIfNeeded();
  await c.clock.runFor(150e3);
  await wait(300);
  const after = await p.locator(sel).isVisible();
  const cfOn = await p.locator('.day[data-d="' + DAY + '"] .cf[data-fid="' + pick.fid + '"]').isVisible();
  check(vp + " a hall hides without reload when its last time (" + pick.cin + " " + pick.hk + " " + pick.last + ") passes",
    before && !after && cfOn, "before " + before + ", after " + after + ", its film still listed " + cfOn);
  await c.close();
}

/* no sideways scroll and no page error on the pages this package touches, at every phone size */
async function scenarioFit() {
  for (const vp of [360, 390, 375, 320]) {
    const { c, p } = await ctxAt(vp, at("22:03"));
    for (const u of ["/", "/dubai/", "/film/heart-of-the-beast/", "/dubai/star-al-ghurair-centre-dubai/", "/en/"]) {
      await p.goto(BASE + u);
      await wait(700);
      const tm = p.locator(".tm[data-start]:not(.past):not(.x)").first();
      if (u !== "/" && u !== "/en/" && await tm.count()) { await tm.scrollIntoViewIfNeeded(); await tm.tap(); await wait(600); }
      const w = await p.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
      check(vp + " " + u + " no sideways scroll", w[0] <= w[1], w.join(" <= "));
    }
    await c.close();
  }
}

(async () => {
  const srv = await serve();
  browser = await chromium.launch({ channel: "chrome" });
  const on = (n) => !ONLY.length || ONLY.includes(n);
  try {
    await headerCheck();
    let lastLink = null;
    for (const vp of [360, 390]) {
      let link = null;
      if (on("now")) { try { link = lastLink = await scenarioNow(vp); } catch (e) { check(vp + " now: " + e.message.split("\n")[0], false); } }
      if (on("gone")) { try { await scenarioGone(vp, link); } catch (e) { check(vp + " gone: " + e.message.split("\n")[0], false); } }
      if (on("gonedeep")) { try { await scenarioGoneDeep(vp); } catch (e) { check(vp + " gonedeep: " + e.message.split("\n")[0], false); } }
      if (on("sort")) { try { await scenarioSort(vp); } catch (e) { check(vp + " sort: " + e.message.split("\n")[0], false); } }
      if (on("late")) { try { await scenarioLate(vp); } catch (e) { check(vp + " late: " + e.message.split("\n")[0], false); } }
      if (on("box")) { try { await scenarioBox(vp); } catch (e) { check(vp + " box: " + e.message.split("\n")[0], false); } }
    }
    if (on("desk")) { try { await scenarioDesk(); } catch (e) { check("desk: " + e.message.split("\n")[0], false); } }
    if (on("deskgone")) { try { await scenarioDeskGone(lastLink); } catch (e) { check("deskgone: " + e.message.split("\n")[0], false); } }
    if (on("focus")) { try { await scenarioFocus(); } catch (e) { check("focus: " + e.message.split("\n")[0], false); } }
    if (on("oracle")) { try { await scenarioOracle(390); } catch (e) { check("oracle: " + e.message.split("\n")[0], false); } }
    if (on("seats")) { try { await scenarioSeats(360); } catch (e) { check("seats: " + e.message.split("\n")[0], false); } }
    if (on("hall")) { try { await scenarioHall(390); } catch (e) { check("hall: " + e.message.split("\n")[0], false); } }
    if (on("fit")) { try { await scenarioFit(); } catch (e) { check("fit: " + e.message.split("\n")[0], false); } }
    check("0 page errors", errors.length === 0, errors.slice(0, 5).join(" | "));
  } finally {
    await browser.close(); srv.close();
  }
  const bad = results.filter((r) => !r.ok);
  console.log("\n" + (results.length - bad.length) + "/" + results.length + " passed" + (SHOTS ? "; screenshots in " + SHOTS : ""));
  process.exit(ASSERT && bad.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
