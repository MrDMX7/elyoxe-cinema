/* tools/check_w1_d2.cjs — W1-D2 (MASTER-PLAN §5.2): the Arabic search and the Arabic titles, in a real Chrome on phones.

   node tools/check_w1_d2.cjs <built out/ dir> [--size 360x740|390x844|375x667|320x640 ...] [--label after] [--shots DIR]
        [--json FILE] [--port 8114] [--expect]

   Serves the built site itself on 127.0.0.1:<port> (8114, the package's port, §5.0 #6): it refuses a port something already
   answers on, and stamps every response `X-Served-By: w1-d2-<git short sha>`, which it asserts on the document and on one
   asset before it measures anything (another agent's server on the port fails the run instead of being measured).
   Per size (default 360x740 and 390x844; isMobile, hasTouch, channel chrome, service workers blocked):
     - home: no horizontal scroll, no page error;
     - the search panel: opened from the header icon, each query typed, the result paths read, the panel held inside the
       width; a screenshot with «أفنجرز» and with «دبي مول»;
     - /film/shish-dou/ and /film/heart-of-the-beast/: the h1 and document.title (the Latin title stays in <title>).
   --expect asserts the package's acceptance targets (the "after" build); without it the run only records (the "before").
   Exit 1 on a failed assertion, a page error, horizontal scroll or a wrong X-Served-By. */
const fs = require("fs"), path = require("path"), http = require("http"), net = require("net"), { execSync } = require("child_process");
const { chromium } = require("C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const all = (k) => argv.reduce((a, v, i) => (v === k ? a.concat(argv[i + 1]) : a), []);
const OUT = path.resolve(argv[0] || "out");
const PORT = +opt("--port", 8114), LABEL = opt("--label", "after"), SHOTS = opt("--shots", null), JSON_OUT = opt("--json", null);
const EXPECT = argv.includes("--expect");
const SIZES = (all("--size").length ? all("--size") : ["360x740", "390x844"]).map((s) => {
  const [w, h] = s.split("x").map(Number);
  return { w, h, dpr: w === 360 ? 3 : 2, name: s };
});
let SHA = "nogit";
try { SHA = execSync("git rev-parse --short HEAD", { cwd: path.dirname(__dirname) }).toString().trim(); } catch (e) { /* not a checkout */ }
const TAG = `w1-d2-${opt("--tag", SHA)}`;
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png", ".woff2": "font/woff2", ".xml": "application/xml",
  ".webmanifest": "application/manifest+json", ".ics": "text/calendar" };

const QUERIES = ["أفنجرز", "سبايدر", "اوديسا", "فوكس", "imax", "فوكس مول الامارات", "دبي مول"];
const EXPECTED = {   // the package's acceptance: the first film, or the first place, a query must land on
  "أفنجرز": (r) => r.films[0] === "film/avengers-endgame-encore",
  "سبايدر": (r) => r.films[0] === "film/spider-man-brand-new-day",
  "اوديسا": (r) => r.films[0] === "film/the-odyssey",
  "فوكس": (r) => r.places.length > 0 && r.places.every((p) => /\/vox-/.test(p)),
  "imax": (r) => r.places[0] === "q/where-imax",
  "فوكس مول الامارات": (r) => r.places[0] === "dubai/vox-mall-of-the-emirates",
  "دبي مول": (r) => r.places.includes("dubai/reel-dubai-mall") && r.places.includes("dubai/cinemacity-fountain-views"),
};

function portTaken(port) {
  return new Promise((res) => {
    const s = net.connect({ host: "127.0.0.1", port }, () => { s.destroy(); res(true); });
    s.on("error", () => res(false));
  });
}

function serve() {
  const srv = http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split("?")[0]);
    let f = path.join(OUT, p);
    if (!f.startsWith(OUT)) { res.writeHead(403); return res.end(); }
    if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
    const hit = fs.existsSync(f);
    if (!hit) f = path.join(OUT, "404.html");
    res.writeHead(hit ? 200 : 404, { "Content-Type": TYPES[path.extname(f)] || "application/octet-stream", "X-Served-By": TAG,
      "Cache-Control": "no-store" });
    fs.createReadStream(f).pipe(res);
  });
  return new Promise((res, rej) => { srv.once("error", rej); srv.listen({ port: PORT, host: "127.0.0.1", exclusive: true }, () => res(srv)); });
}

async function checkServedBy(base) {
  const doc = await fetch(base + "/");
  const html = await doc.text();
  const css = (html.match(/href="(\/assets\/cinema[^"]*\.css[^"]*)"/) || [])[1];
  const asset = css ? await fetch(base + css) : null;
  const got = [doc.headers.get("x-served-by"), asset && asset.headers.get("x-served-by")];
  if (got[0] !== TAG || got[1] !== TAG) throw new Error(`X-Served-By mismatch: ${got} (want ${TAG}); another server answers on ${PORT}?`);
  return got;
}

async function overflow(page) {
  return page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
}

async function main() {
  if (await portTaken(PORT)) throw new Error(`port ${PORT} already answers: not measuring someone else's server`);
  const srv = await serve();
  const base = `http://127.0.0.1:${PORT}`;
  const report = { label: LABEL, tag: TAG, servedBy: await checkServedBy(base), sizes: {} };
  const fails = [];
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    for (const sz of SIZES) {
      const ctx = await browser.newContext({ viewport: { width: sz.w, height: sz.h }, deviceScaleFactor: sz.dpr, isMobile: true,
        hasTouch: true, serviceWorkers: "block", locale: "ar-AE" });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(String(e && e.message || e)));
      const r = (report.sizes[sz.name] = { errors, pages: {}, search: {} });

      await page.goto(base + "/", { waitUntil: "load" });
      r.pages.home = await overflow(page);
      await page.locator(".top [data-search], header [data-search]").first().click();
      await page.waitForSelector("#srch:not([hidden])", { timeout: 15000 });
      for (const q of QUERIES) {
        await page.fill("#srch-input", q);
        await page.waitForFunction(() => document.querySelectorAll("#srch-list [role=option]").length > 0
          || (document.getElementById("srch-empty") || {}).textContent, null, { timeout: 15000 }).catch(() => {});
        const paths = await page.$$eval("#srch-list [role=option]", (els) => els.map((e) => e.getAttribute("data-p")));
        const names = await page.$$eval("#srch-list [role=option] a > span", (els) => els.map((e) => e.textContent));
        const res = { films: paths.filter((p) => p.startsWith("film/")), places: paths.filter((p) => !/^(film|people)\//.test(p)), names };
        res.box = await page.evaluate(() => { const b = document.querySelector(".srch-box"); return b ? { sw: b.scrollWidth, cw: b.clientWidth } : null; });
        r.search[q] = res;
        if (EXPECT && EXPECTED[q] && !EXPECTED[q](res)) fails.push(`${sz.name} «${q}» -> ${JSON.stringify(res)}`);
        if (res.box && res.box.sw > res.box.cw) fails.push(`${sz.name} search panel overflows with «${q}»: ${JSON.stringify(res.box)}`);
        if (SHOTS && (q === "أفنجرز" || q === "دبي مول") && sz.w >= 360) {
          await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${sz.w}-search-${q === "أفنجرز" ? "avengers" : "dubaimall"}.png`) });
        }
      }
      r.pages.search_open = await overflow(page);
      for (const fid of ["shish-dou", "heart-of-the-beast"]) {
        await page.goto(`${base}/film/${fid}/`, { waitUntil: "load" });
        const head = await page.evaluate(() => ({ title: document.title, h1: (document.querySelector("h1") || {}).textContent || "",
          fte: (document.querySelector(".fte") || {}).textContent || "" }));
        r.pages[fid] = { ...head, ...(await overflow(page)) };
        if (SHOTS && sz.w >= 360) await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${sz.w}-film-${fid}.png`) });
      }
      if (EXPECT) {
        if (!/شيش دو/.test(r.pages["shish-dou"].h1) || !/Shish Dou/.test(r.pages["shish-dou"].title)) fails.push(`${sz.name} shish-dou head ${JSON.stringify(r.pages["shish-dou"])}`);
        if (!/Heart of the Beast/.test(r.pages["heart-of-the-beast"].title)) fails.push(`${sz.name} heart-of-the-beast <title> lost its Latin`);
      }
      for (const [k, v] of Object.entries(r.pages)) if (v.scrollWidth > v.clientWidth) fails.push(`${sz.name} ${k} scrolls sideways ${v.scrollWidth}>${v.clientWidth}`);
      if (errors.length) fails.push(`${sz.name} page errors: ${errors.join(" | ")}`);
      await ctx.close();
    }
  } finally {
    await browser.close();
    srv.close();
  }
  report.fails = fails;
  const txt = JSON.stringify(report, null, 1);
  if (JSON_OUT) fs.writeFileSync(JSON_OUT, txt);
  console.log(txt);
  process.exit(fails.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
