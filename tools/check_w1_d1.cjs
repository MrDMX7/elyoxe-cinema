/* W1-D1 check: the frames a phone actually gets on the home billboard and a film hero, on a real-data build.

  node tools/check_w1_d1.cjs --out <built site> --posters <dir with bd-*.webp> --shots <dir> --sha <short sha>
                             [--port 8113] [--film heart-of-the-beast] [--when 2026-09-28T19:00] [--vps 360,390,375,320]
                             [--expect graded|any]

Serves <out> on 127.0.0.1:<port> with an exclusive bind (a connect probe first: a port someone else answers on is an
error) and `X-Served-By: w1-d1-<sha>`, asserted on the document and on the bundle before anything is measured.
/posters/bd-* come from --posters (the step's own output), other /posters/* redirect to the live mirror.
Chrome (channel chrome), isMobile + hasTouch, UAE clock at --when, city = dubai, service workers blocked. For home
and --film at every viewport: HTTP 200, scrollWidth == innerWidth == clientWidth, 0 page errors, the hero picture's
current source (a steps/backdrops.py frame, `bd-…`, or the poster), its natural size and a screenshot.
With --expect graded, every bd- frame the page loads must be one the W1-D1 step wrote (listed in
<posters>/../backdrops.json with "v" >= 2). Writes <shots>/results.json; exits 1 on any failure. */
"use strict";
const fs = require("fs"), path = require("path"), http = require("http"), net = require("net");
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf("--" + k); return i >= 0 ? argv[i + 1] : d; };
const OUT = path.resolve(arg("out", "out"));
const POSTERS = path.resolve(arg("posters", path.join(OUT, "posters")));
const SHOTS = path.resolve(arg("shots", "shots"));
const PORT = +arg("port", 8113);
const SERVED = "w1-d1-" + arg("sha", "nogit");
const WHEN = arg("when", "2026-09-28T19:00");
const FILM = "/film/" + arg("film", "heart-of-the-beast") + "/";
const VPS = arg("vps", "360,390,375,320").split(",").map(Number);
const EXPECT = arg("expect", "any");
const BASE = "http://127.0.0.1:" + PORT;
const { chromium } = require("C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");
fs.mkdirSync(SHOTS, { recursive: true });

let v2 = new Set();
try {
  const cache = JSON.parse(fs.readFileSync(path.join(POSTERS, "..", "backdrops.json"), "utf8"));
  for (const e of Object.values(cache)) {
    if (!e || (e.v || 1) < 2) continue;
    for (const u of [e.w1280, e.w640, e.p, ...(e.kept || []).flatMap((k) => [k.w1280, k.w640])]) if (u) v2.add(path.basename(u));
  }
} catch (e) { /* no cache next to the posters: --expect graded will fail loudly below */ }

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
  ".woff2": "font/woff2", ".webmanifest": "application/manifest+json", ".xml": "application/xml" };
function serve() {
  return new Promise((resolve, reject) => {
    const probe = net.connect(PORT, "127.0.0.1");
    probe.on("connect", () => { probe.destroy(); reject(new Error("port " + PORT + " already answers: another server owns it")); });
    probe.on("error", () => {
      const srv = http.createServer((req, res) => {
        const p = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
        const head = { "X-Served-By": SERVED, "Cache-Control": "no-store" };
        if (p.startsWith("/posters/")) {
          const f = path.join(POSTERS, path.basename(p));
          if (/^bd-/.test(path.basename(p)) && fs.existsSync(f)) {
            res.writeHead(200, Object.assign({ "Content-Type": "image/webp" }, head)); return res.end(fs.readFileSync(f));
          }
          res.writeHead(302, Object.assign({ Location: "https://cinema.elyoxe.com" + p }, head)); return res.end();
        }
        let f = path.join(OUT, p);
        if (!f.startsWith(OUT)) { res.writeHead(403, head); return res.end(); }
        if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
        if (!fs.existsSync(f)) { res.writeHead(404, head); return res.end("not found"); }
        res.writeHead(200, Object.assign({ "Content-Type": TYPES[path.extname(f)] || "application/octet-stream" }, head));
        res.end(fs.readFileSync(f));
      });
      srv.on("error", reject);
      srv.listen({ port: PORT, host: "127.0.0.1", exclusive: true }, () => resolve(srv));
    });
  });
}

const PHONES = { 360: { w: 360, h: 740, dpr: 3 }, 390: { w: 390, h: 844, dpr: 2 }, 375: { w: 375, h: 667, dpr: 2 }, 320: { w: 320, h: 640, dpr: 2 } };
const results = [];
function check(name, ok, detail) { results.push({ name, ok: !!ok, detail: detail == null ? "" : String(detail) }); console.log((ok ? "PASS " : "FAIL ") + name + (detail ? "  | " + detail : "")); }
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const srv = await serve();
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    {
      const c = await browser.newContext();
      const p = await c.newPage();
      const r = await p.goto(BASE + "/");
      const js = await p.evaluate(() => [...document.scripts].map((s) => s.src).find((s) => /\/assets\/cinema\.[0-9a-f]+\.js$/.test(s)) || null);
      const ra = js ? await c.request.get(js) : null;
      const ok = r.headers()["x-served-by"] === SERVED && ra && ra.headers()["x-served-by"] === SERVED;
      check("served by " + SERVED + " (document and bundle)", ok, r.headers()["x-served-by"] + " / " + (ra && ra.headers()["x-served-by"]));
      await c.close();
      if (!ok) throw new Error("another server answered: refusing to measure");
    }
    for (const vp of VPS) {
      for (const [name, url] of [["home", "/"], ["film", FILM]]) {
        const ph = PHONES[vp];
        const c = await browser.newContext({ viewport: { width: ph.w, height: ph.h }, deviceScaleFactor: ph.dpr, isMobile: true, hasTouch: true,
          locale: "ar-AE", timezoneId: "Asia/Dubai", serviceWorkers: "block" });
        await c.clock.install({ time: new Date(WHEN + ":00+04:00") });
        await c.addInitScript(() => { try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {} });
        const p = await c.newPage();
        const errs = [], frames = [];
        p.on("pageerror", (e) => errs.push(e.message.split("\n")[0]));
        p.on("response", (r) => { const u = r.url(); if (/\/posters\/bd-/.test(u)) frames.push(path.basename(u.split("?")[0])); });
        const r = await p.goto(BASE + url);
        await p.waitForLoadState("load").catch(() => {});
        await p.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
        await wait(900);
        const m = await p.evaluate(() => {
          const img = document.querySelector(".bill .bd img, .fhero .bd img, .bd img");
          return { sw: document.documentElement.scrollWidth, iw: innerWidth, cw: document.documentElement.clientWidth,
            src: img ? (img.currentSrc || img.src).split("/").pop() : null, nw: img ? img.naturalWidth : 0, nh: img ? img.naturalHeight : 0,
            box: img ? [Math.round(img.getBoundingClientRect().width), Math.round(img.getBoundingClientRect().height)] : null };
        });
        const fits = m.sw === m.iw && m.cw === m.iw;
        await p.screenshot({ path: path.join(SHOTS, vp + "-" + name + ".png") });
        check(vp + " " + name + ": HTTP 200, no sideways scroll, 0 page errors", r.status() === 200 && fits && errs.length === 0,
          "status " + r.status() + " sw " + m.sw + " iw " + m.iw + " cw " + m.cw + " errors " + errs.length + (errs.length ? " [" + errs.slice(0, 2).join(" | ") + "]" : ""));
        console.log("   hero picture: " + m.src + " natural " + m.nw + "x" + m.nh + " drawn " + (m.box || []).join("x") + " CSS px at DPR " + ph.dpr +
          "; bd- frames loaded: " + (frames.join(", ") || "none"));
        results.push({ name: vp + " " + name + " picture", ok: true, detail: JSON.stringify({ src: m.src, natural: [m.nw, m.nh], box: m.box, frames }) });
        if (EXPECT === "graded") {
          const stale = frames.filter((f) => !v2.has(f));
          check(vp + " " + name + ": every frame loaded is a W1-D1 (v2, graded) frame", frames.length > 0 && stale.length === 0,
            frames.length ? (stale.length ? "not v2: " + stale.join(", ") : frames.length + " frame(s)") : "no bd- frame loaded");
        }
        await c.close();
      }
    }
  } finally {
    await browser.close();
    srv.close();
  }
  fs.writeFileSync(path.join(SHOTS, "results.json"), JSON.stringify({ servedBy: SERVED, when: WHEN, results }, null, 1));
  const failed = results.filter((r) => !r.ok).length;
  console.log(failed ? failed + " FAILED" : "all passed");
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
