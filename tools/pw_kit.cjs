/* What every browser tool shares (W1-P1, MASTER-PLAN §5.0 #3 and #6): the phone sizes, the arguments, this build's
   own server on this package's own port, and the X-Served-By check that runs before anything is measured.

     --out DIR        the build to serve (default out/)
     --port N         the package's port (default 8111, W1-P1's; §5.0 lists every package's)
     --name PKG       the package, as serve.py stamps it (default $CINEMA_PKG, else w1-p1)
     --size WxH,…     360x740 | 390x844 | 375x667 | 320x640 (default 360x740,390x844)
     --no-serve       a server is already listening on --port: use it (its stamp must still be <name>-<sha>)
     --now ISO        the UAE time the page believes (default: the build's own data time)
   Playwright: $PLAYWRIGHT, else the elyoxe site's copy on the laptop. Chrome, never the CLI's screenshots. */
"use strict";
const fs = require("fs"), path = require("path"), cp = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const PW = process.env.PLAYWRIGHT || "C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright";
const SIZES = { "360x740": { w: 360, h: 740, dpr: 3 }, "390x844": { w: 390, h: 844, dpr: 2 }, "375x667": { w: 375, h: 667, dpr: 2 },
  "320x640": { w: 320, h: 640, dpr: 2 } };

function args(argv, extra) {
  argv = argv || process.argv.slice(2);
  const get = (k, d) => { const i = argv.indexOf("--" + k); return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : d; };
  const has = (k) => argv.includes("--" + k);
  const sizes = get("size", "360x740,390x844").split(",").map((s) => s.trim()).filter(Boolean);
  for (const s of sizes) if (!SIZES[s]) throw new Error("unknown --size " + s + " (" + Object.keys(SIZES).join(", ") + ")");
  const o = { out: path.resolve(get("out", path.join(ROOT, "out"))), port: +get("port", 8111), name: get("name", process.env.CINEMA_PKG || "w1-p1"),
    sizes, serve: !has("no-serve"), now: get("now", null), get, has };
  return Object.assign(o, extra || {});
}

function sha() {
  try { return cp.execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim(); } catch (e) { return "nogit"; }
}

/* the alt build's origin (serve.py --alt-out): a second loopback literal, never "localhost", which another agent's
   wildcard server could answer on [::1] (review M2) */
const ALT = "http://127.0.0.2:";

/* start tools/serve.py on the port; resolves once it listens. It refuses a taken port (another agent's server) */
function serve(o) {
  const stamp = o.name + "-" + sha();
  if (!o.serve) return Promise.resolve({ base: "http://127.0.0.1:" + o.port, alt: o.altOut ? ALT + o.port : null, stamp, stop() {} });
  return new Promise((resolve, reject) => {
    const a = [path.join(ROOT, "tools", "serve.py"), "--out", o.out, "--port", String(o.port), "--name", o.name];
    if (o.altOut) a.push("--alt-out", o.altOut);
    if (o.posters) a.push("--posters", o.posters);
    const s = cp.spawn(process.env.PYTHON || "python", a, { stdio: ["ignore", "pipe", "pipe"] });
    let err = "", done = false;
    s.stderr.on("data", (d) => { err += d; });
    s.stdout.on("data", (d) => {
      if (!done && String(d).includes("serving")) { done = true; resolve({ base: "http://127.0.0.1:" + o.port, alt: o.altOut ? ALT + o.port : null, stamp, stop: () => s.kill() }); }
    });
    s.on("exit", (c) => { if (!done) reject(new Error("serve.py exited " + c + ": " + err.trim())); });
    process.once("exit", () => { try { s.kill(); } catch (e) {} });
  });
}

/* the document and one asset must both carry this package's stamp, else another server answered: stop */
async function assertServed(base, stamp) {
  for (const u of [base + "/", base + "/assets/cinema.css"]) {
    let got;
    try { got = (await fetch(u, { cache: "no-store" })).headers.get("x-served-by"); } catch (e) { got = "nothing (" + e.cause + ")"; }
    if (got !== stamp) throw new Error("X-Served-By on " + u + " is " + got + ", not " + stamp + ": another server answered, nothing measured");
  }
  return true;
}

/* a phone context at a size: isMobile + hasTouch + DPR, UAE locale and zone, no service worker */
async function phone(browser, size, extra) {
  const s = SIZES[size];
  return browser.newContext(Object.assign({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: s.dpr, isMobile: true, hasTouch: true,
    locale: "ar-AE", timezoneId: "Asia/Dubai", serviceWorkers: "block" }, extra || {}));
}

/* the UAE time a build's data was made at (its pages believe NOW from ?now= or the clock; tools pin it) */
function dataTime(out) {
  try {
    const f = fs.readdirSync(path.join(out, "data")).filter((x) => /-\d{4}-\d\d-\d\d\.json$/.test(x)).sort()[0];
    return JSON.parse(fs.readFileSync(path.join(out, "data", f), "utf-8")).g || null;
  } catch (e) { return null; }
}

/* Shift the page's wall clock (Date only) so it starts at `when` and runs on at real speed, on every page of the
   context. Never Playwright's ctx.clock for a measurement: it fakes performance, requestAnimationFrame and the timers,
   so frame times are the fake clock's and performance.getEntriesByType("navigation") comes back empty. */
async function pinClock(ctx, when) {
  await ctx.addInitScript((t) => {
    const R = Date, off = t - R.now();
    function D(...a) { return new.target ? (a.length ? new R(...a) : new R(R.now() + off)) : new R(R.now() + off).toString(); }
    D.prototype = R.prototype; D.now = () => R.now() + off; D.parse = R.parse; D.UTC = R.UTC;
    Object.setPrototypeOf(D, R);
    window.Date = D;
  }, +when);
}

/* the instant a tool pins the page's clock to: --now (UAE wall time, «2026-09-27T20:40»), else the data's own time */
function pinned(o) {
  const v = o.now || dataTime(o.out);
  if (!v) return new Date();
  return new Date(v.length <= 16 ? v + ":00+04:00" : v);
}

function chromium() { return require(PW).chromium; }
async function launch(opts) { return chromium().launch(Object.assign({ channel: "chrome" }, opts || {})); }

/* results: a PASS/FAIL line each, and the exit code at the end */
function results() {
  const r = [];
  return {
    list: r,
    check(name, ok, detail) { r.push({ name, ok: !!ok, detail: detail == null ? "" : String(detail) }); console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && detail !== "" ? "  — " + detail : "")); return !!ok; },
    info(name, detail) { r.push({ name, ok: true, info: true, detail: String(detail) }); console.log("INFO " + name + "  — " + detail); },
    code() { return r.some((x) => !x.ok) ? 1 : 0; },
  };
}

module.exports = { ROOT, SIZES, args, sha, serve, assertServed, phone, launch, chromium, dataTime, pinned, pinClock, results };
