/* W0-P2 · Trust sweep: pages — the package's acceptance checks against a served build (MASTER-PLAN §4.1 #11–#22,
   #37; §5.1 W0-P2), plus the definition of done's phone pass on every page the package touches.

   node tools/check_w0_p2.cjs [--base http://127.0.0.1:8102] [--served w0-p2] [--day 2026-09-27] [--shots <dir> --tag after]
                              [--only acceptance|phones]

   The build must come from real data with a daytime clock (the check reads its own «today» from /data/compare.json
   unless --day is given). Every check first asserts the X-Served-By header on the document and on one asset, so a
   number is never taken from another package's server on a shared port. Exit 1 on any failure. Playwright from the
   elyoxe site's node_modules, system Chrome (never a CLI screenshot). */
"use strict";
const path = require("path");
const fs = require("fs");
const { chromium } = require(process.env.PLAYWRIGHT || "C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");

const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const BASE = arg("base", "http://127.0.0.1:8102");
const SERVED = arg("served", "w0-p2");
const SHOTS = arg("shots", "");
const TAG = arg("tag", "after");
const ONLY = arg("only", "");
const PHONES = [
  { name: "360", width: 360, height: 740, dpr: 3 },
  { name: "390", width: 390, height: 844, dpr: 2 },
  { name: "375", width: 375, height: 667, dpr: 2 },
  { name: "320", width: 320, height: 640, dpr: 2 },
];
const fails = [], notes = [];
const ok = (cond, what) => { (cond ? notes : fails).push((cond ? "ok   " : "FAIL ") + what); };

async function served(ctx, url) {
  const r = await ctx.request.get(BASE + url);
  const h = r.headers()["x-served-by"] || "";
  if (!h.startsWith(SERVED)) throw new Error(`${url}: X-Served-By is "${h}", not ${SERVED}* — another server answered`);
  return r;
}

async function open(ctx, url, errors) {
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(url + ": " + e.message));
  await page.goto(BASE + url, { waitUntil: "load" });
  // lazy chunks (when.js, compare.js) load after start-up: wait for every chunk the page lists to have run
  await page.waitForFunction(() => {
    const want = Object.values((window.CT || {}).chunks || {});
    return want.every((u) => performance.getEntriesByName(location.origin + u).length);
  }, null, { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(300);
  return page;
}

async function acceptance(browser, day) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const errors = [];
  const text = async (url) => { const p = await open(ctx, url, errors); const t = await p.evaluate(() => document.body.innerText); await p.close(); return t; };

  // #11, #12 /coming/: release weeks open on Thursday, and no dead «نبّهني»
  let p = await open(ctx, "/coming/", errors);
  const coming = await p.evaluate(() => ({
    disabled: document.querySelectorAll("button[disabled]").length,
    notify: document.body.innerText.includes("نبّهني"),
    anbil: [...document.querySelectorAll(".cs-week")].filter((s) => s.textContent.includes("Anbil Avan")).map((s) => s.querySelector("h2").textContent),
  }));
  ok(coming.disabled === 0 && !coming.notify, `/coming/ has ${coming.disabled} disabled buttons and no «نبّهني»`);
  if (coming.anbil.length) ok(coming.anbil.every((h) => h.startsWith("1 أكتوبر")), `/coming/ files «Anbil Avan» (Fri 2 Oct) under ${JSON.stringify(coming.anbil)}`);
  await p.close();

  // #13 «آخر فرصة»: nowhere
  for (const u of ["/", "/dubai/", "/al-ain/", "/en/"]) {
    const t = await text(u);
    ok(!t.includes("آخر فرصة") && !t.includes("Last chance"), `${u} renders no «آخر فرصة»`);
  }

  // #14 film pages: no double feature; #37 + #18 + #17 the compare box
  p = await open(ctx, "/film/heart-of-the-beast/?now=" + day + "T21:45", errors);
  ok((await p.locator(".dfeat").count()) === 0, "the film page has no .dfeat");
  await p.waitForSelector("[data-cmp]:not([hidden]) select", { timeout: 10000 });
  const sels = p.locator("[data-cmp-ui] select");
  await sels.nth(1).selectOption("resident-evil");
  await p.waitForFunction(() => {
    const row = [...document.querySelectorAll(".cmp-t tbody tr")].find((r) => /أقرب الأوقات/.test(r.querySelector("th").textContent));
    return row && [...row.querySelectorAll("td")].every((td) => td.textContent.trim());
  }, null, { timeout: 10000 });
  const cmp = await p.evaluate(() => {
    const rows = {};
    document.querySelectorAll(".cmp-t tbody tr").forEach((r) => { rows[r.querySelector("th").textContent] = [...r.querySelectorAll("td")].map((td) => td.textContent.trim()); });
    return rows;
  });
  const soonKey = Object.keys(cmp).find((k) => k.startsWith("أقرب الأوقات"));
  const times = (cmp[soonKey] || []).join(" ").match(/\d\d:\d\d(?= اليوم)/g) || [];
  ok(!cmp[soonKey].some((c) => c.includes("ما في عروض باقية")) || times.length > 0, `compare at 21:45 lists next times: ${JSON.stringify(cmp[soonKey])}`);
  ok(times.every((t) => t >= "21:45"), `compare's times today are all at or after 21:45 (${times.join(", ")})`);
  ok(!Object.keys(cmp).some((k) => /imdb/i.test(k)), "compare has no IMDb row");
  const re = await (await ctx.request.get(BASE + "/data/compare.json")).json();
  const ref = re.f["resident-evil"];
  if (ref && ref[3] != null) ok(cmp["النقاد"][1] === ref[3] + "%" && cmp["الجمهور"][1] === ref[4] + "%",
    `compare shows Resident Evil's critics and audience ${cmp["النقاد"][1]} / ${cmp["الجمهور"][1]}`);
  await p.close();
  const fp = await open(ctx, "/film/resident-evil/", errors);
  const rates = await fp.evaluate(() => (document.querySelector(".basis.rates") || {}).textContent || "");
  if (ref) ok(rates.includes(ref[3] + "%") && rates.includes(ref[4] + "%"), `the film page's own rates «${rates}» match compare.json (${ref[3]}/${ref[4]})`);
  await fp.close();

  // #15 the cinema page's double feature: only pairs still ahead, written «ثم», gone when none is left
  for (const at of ["15:00", "21:45", "23:59"]) {
    p = await open(ctx, "/dubai/vox-mall-of-the-emirates/?now=" + day + "T" + at, errors);
    const df = await p.evaluate(() => {
      const d = document.querySelector("details.dfeat");
      if (!d) return null;
      d.open = true;
      const vis = [...d.querySelectorAll("[data-until]")].filter((s) => !s.hidden && !s.closest("[hidden]"));
      return { hidden: d.hidden, starts: vis.map((s) => s.getAttribute("data-until")), text: d.innerText,
        emptyLines: [...d.querySelectorAll("li")].filter((li) => !li.hidden && ![...li.querySelectorAll("[data-until]")].some((s) => !s.hidden)).length };
    });
    if (df) {
      ok(df.starts.every((s) => s >= at), `cinema page at ${at}: ${df.starts.length} visible pairs, first starts ${df.starts.slice(0, 3).join(", ")}`);
      ok(df.emptyLines === 0, `cinema page at ${at}: no line left without a time`);
      ok(df.hidden === (df.starts.length === 0), `cinema page at ${at}: the list is ${df.hidden ? "hidden" : "shown"}`);
      if (!df.hidden) ok(df.text.includes(" ثم ") && !/[←→]/.test(df.text), "pairs are written «ثم», no arrows");
    } else notes.push("note the cinema page has no double feature in this build");
    await p.close();
  }

  // #19 «4DX» reads whole on the question pages. The DOM text says «4DX» either way; the bug is where the glyphs
  // land, so this measures them: in the answer, the format's first character must sit left of its second.
  for (const [u, fmt] of [["/q/where-4dx/", "4DX"], ["/q/4dx-ticket-price-dubai/", "4DX"], ["/q/fab-at-reel/", "2D"]]) {
    const r = await ctx.request.get(BASE + u);
    if (r.status() !== 200) continue;
    p = await open(ctx, u, errors);
    const ltr = await p.evaluate((f) => {
      const ans = document.querySelector(".qa .ans");
      if (!ans) return null;
      const w = document.createTreeWalker(ans, NodeFilter.SHOW_TEXT), nodes = [];
      let t = "";
      while (w.nextNode()) { nodes.push([w.currentNode, t.length]); t += w.currentNode.textContent; }
      const i = t.indexOf(f);
      if (i < 0) return null;
      const at = (k) => { for (const [n, o] of nodes) if (k >= o && k < o + n.textContent.length) { const g = document.createRange(); g.setStart(n, k - o); g.setEnd(n, k - o + 1); return g.getBoundingClientRect().left; } };
      return at(i) < at(i + 1);
    }, fmt);
    if (ltr !== null) ok(ltr, `${u}: «${fmt}» in the answer reads left to right (${ltr ? "in order" : "flipped"})`);
    await p.close();
  }

  // #20 /prices/: the read day, and two columns on a phone
  p = await open(ctx, "/prices/", errors);
  const pr = await p.evaluate(() => {
    const h = document.querySelector(".pi h2"), w = document.querySelector(".pi .xwrap");
    const cols = [...document.querySelectorAll(".pidx thead th")].filter((th) => getComputedStyle(th).display !== "none").length;
    return { h: h && h.textContent, cols, fits: w ? w.scrollWidth <= w.clientWidth : null };
  });
  const dd = new Date(day + "T12:00:00Z").toLocaleDateString("ar-AE-u-nu-latn", { timeZone: "UTC", day: "numeric", month: "long" });
  ok(pr.h && pr.h.includes(dd), `/prices/ heading «${pr.h}» carries the read day (${dd})`);
  ok(pr.cols === 2 && pr.fits, `/prices/ table at 390: ${pr.cols} columns, fits ${pr.fits}`);
  await p.close();

  // #21 /kids/: tomorrow morning after 14:00, this morning before it
  for (const [at, want] of [["16:00", "بكرة الصبح"], ["09:00", "اليوم الصبح"]]) {
    p = await open(ctx, "/kids/?now=" + day + "T" + at, errors);
    const k = await p.evaluate(() => [...document.querySelectorAll(".kids-day")].filter((s) => !s.hidden).map((s) => ({ h: s.querySelector("h2").textContent, rows: s.querySelectorAll(".row").length })));
    ok(k.length === 1 && k[0].h === want, `/kids/ at ${at} shows ${JSON.stringify(k)}`);
    await p.close();
  }

  // #22 /summer/ is not built
  ok((await ctx.request.get(BASE + "/summer/")).status() === 404, "/summer/ is a 404");

  ok(errors.length === 0, `0 page errors (${errors.join(" | ")})`);
  await ctx.close();
}

const PAGES = (day) => [
  ["coming", "/coming/"],
  ["cinema", "/dubai/vox-mall-of-the-emirates/?now=" + day + "T15:00", "details.dfeat"],
  ["filmtop", "/film/heart-of-the-beast/", "details.dfeat, .fcity"],
  ["film", "/film/heart-of-the-beast/?now=" + day + "T21:45", "[data-cmp]"],
  ["prices", "/prices/", ".pi"],
  ["kids", "/kids/?now=" + day + "T16:00", ".kids-day"],
  ["q4dx", "/q/where-4dx/", ".qa"],
  ["home", "/"],
];

async function phones(browser, day) {
  for (const v of PHONES) {
    const ctx = await browser.newContext({ viewport: { width: v.width, height: v.height }, deviceScaleFactor: v.dpr, isMobile: true, hasTouch: true });
    const errors = [];
    for (const [name, url, focus] of PAGES(day)) {
      const r = await ctx.request.get(BASE + url);
      if (r.status() !== 200) { notes.push(`note ${v.name} ${url}: ${r.status()}, skipped`); continue; }
      const p = await open(ctx, url, errors);
      if (name === "film") {
        await p.waitForSelector("[data-cmp]:not([hidden]) select", { timeout: 10000 }).catch(() => {});
        if (await p.locator("[data-cmp-ui] select").count()) {
          await p.locator("[data-cmp-ui] select").nth(1).selectOption("resident-evil").catch(() => {});
          await p.waitForTimeout(600);
        }
      }
      if (name === "cinema") await p.evaluate(() => { const d = document.querySelector("details.dfeat"); if (d) d.open = true; });
      const m = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
      ok(m.sw === m.iw, `${v.name} ${url}: scrollWidth ${m.sw} == innerWidth ${m.iw}`);
      if (SHOTS && (v.name === "360" || v.name === "390")) {
        if (focus) await p.evaluate((sel) => { const el = document.querySelector(sel); if (el) el.scrollIntoView({ block: "start" }); window.scrollBy(0, -70); }, focus);
        await p.waitForTimeout(150);
        fs.mkdirSync(SHOTS, { recursive: true });
        await p.screenshot({ path: path.join(SHOTS, `${TAG}-${name}-${v.name}.png`) });
      }
      await p.close();
    }
    ok(errors.length === 0, `${v.name}: 0 page errors (${errors.join(" | ")})`);
    await ctx.close();
  }
}

(async () => {
  const browser = await chromium.launch({ channel: "chrome" });
  const ctx = await browser.newContext();
  await served(ctx, "/");
  const css = (await (await served(ctx, "/")).text()).match(/\/assets\/cinema\.css\?v=\w+/);
  if (css) await served(ctx, css[0]);
  const day = arg("day", "") || (await (await served(ctx, "/data/compare.json")).json()).t;
  await ctx.close();
  notes.push(`base ${BASE}, served by ${SERVED}*, day ${day}`);
  if (ONLY !== "phones") await acceptance(browser, day);
  if (ONLY !== "acceptance") await phones(browser, day);
  await browser.close();
  console.log(notes.concat(fails).join("\n"));
  console.log(fails.length ? `\n${fails.length} FAILED` : "\nall passed");
  process.exit(fails.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
