#!/usr/bin/env node
/* Tap count to the chain's page for a show (W1-P1 tool; MASTER-PLAN §1.2 #7, §3.4 X1, §7.3 #5). Each route ends on a
   visible «احجز» whose href is the chain's page for that show (not the chain's home page, not ours); the «احجز» tap
   itself counts, and is not made (no chain site is opened).
     row   a board row → «احجز»                      the claim: 2 taps (its navigation should activate a prerender)
     pick  «اختار لي» → «احجز»                        2 taps (W2-P2b; skipped while the page has no pick)
     tile  a film tile → a time → «احجز»              3 taps
   Before the board (W2-P2) a row is the «يبدأ قريب منك» card, the one show link on home today (#now a[href*="#s-"]);
   the board inherits id="now". Today it records the baseline; W2-P2 and W2-P3 turn on --assert.

     node tools/route_check.cjs --out out [--port 8111] [--size 360x740,390x844] [--now 2026-09-27T20:40] [--assert] [--json FILE]
   A functional check: no perf lock. X-Served-By is asserted first. */
"use strict";
const fs = require("fs");
const K = require("./pw_kit.cjs");

const BOOK = 'a[data-tk-book], a[data-book-show], a.book';

/* a visible «احجز» with a show-level href, else null */
async function bookable(page) {
  return page.evaluate((sel) => {
    const sites = Object.values((window.CT && window.CT.sites) || {}).map((u) => u.replace(/\/+$/, ""));
    const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) && r.bottom > 0 && r.top < innerHeight; };
    const c = [...document.querySelectorAll(sel + ", a")].filter((a) => /احجز|Book/.test(a.textContent) && vis(a));
    for (const a of c) {
      const u = a.href.replace(/\/+$/, "");
      const level = /^https?:/.test(u) && !u.startsWith(location.origin) && !sites.includes(u);
      if (level) return { text: a.textContent.trim().slice(0, 40), href: a.href };
    }
    return c.length ? { text: c[0].textContent.trim().slice(0, 40), href: c[0].href, notShowLevel: true } : null;
  }, BOOK);
}

/* taps that reveal «احجز» when it is not on screen yet (today: the phone dock's «التفاصيل والحجز») */
async function reveal(page, max) {
  let n = 0, hit = await bookable(page);
  while ((!hit || hit.notShowLevel) && n < max) {
    const b = page.locator("[data-dk-open]:visible, [data-stub-open]:visible").first();
    if (!(await b.count())) break;
    await b.tap(); n++;
    await page.waitForTimeout(700);
    hit = await bookable(page);
  }
  return { n, hit };
}

async function route(page, base, name) {
  const res = { route: name, taps: null, detail: "" };
  await page.goto(base + "/", { waitUntil: "load" });
  if (name === "row") {
    const row = page.locator('#now a[href*="#s-"]').first();
    try { await row.waitFor({ state: "visible", timeout: 10000 }); } catch (e) { res.detail = "no show link on home (no board row, no near card)"; return res; }
    await row.scrollIntoViewIfNeeded();
    await Promise.all([page.waitForURL(/\/film\/[^/]+\/#s-/, { timeout: 15000 }), row.tap()]);
    await page.waitForLoadState("load"); await page.waitForTimeout(1500);
    res.activationStart = await page.evaluate(() => { const n = performance.getEntriesByType("navigation")[0]; return n ? Math.round(n.activationStart || 0) : null; });
    const r = await reveal(page, 2);
    res.taps = r.hit && !r.hit.notShowLevel ? 1 + r.n + 1 : null;
    res.detail = r.hit ? `«${r.hit.text}» → ${r.hit.href}` : "no «احجز» on screen";
  } else if (name === "pick") {
    const p = page.locator("[data-pick]:visible").first();
    if (!(await p.count())) { res.detail = "no «اختار لي» on this build (W2-P2b)"; res.skip = true; return res; }
    await p.tap(); await page.waitForTimeout(1500);
    const r = await reveal(page, 1);
    res.taps = r.hit && !r.hit.notShowLevel ? 1 + r.n + 1 : null;
    res.detail = r.hit ? `«${r.hit.text}» → ${r.hit.href}` : "no «احجز» on screen";
  } else {
    const tile = page.locator('.rail:not([data-near-row]) .tile[href*="/film/"]').first();
    await tile.scrollIntoViewIfNeeded();
    await Promise.all([page.waitForURL(/\/film\//, { timeout: 15000 }), tile.tap()]);
    await page.waitForLoadState("load"); await page.waitForTimeout(1500);
    const tm = page.locator(".cgs .tm:not(.past):visible, .cgs a[id^='s-']:visible").first();
    if (!(await tm.count())) { res.detail = "no upcoming time on the film page"; return res; }
    await tm.scrollIntoViewIfNeeded(); await tm.tap(); await page.waitForTimeout(900);
    const r = await reveal(page, 2);
    res.taps = r.hit && !r.hit.notShowLevel ? 2 + r.n + 1 : null;
    res.detail = r.hit ? `«${r.hit.text}» → ${r.hit.href}` : "no «احجز» on screen";
  }
  return res;
}

(async () => {
  const o = K.args();
  const assert = o.has("assert"), CLAIM = { row: 2, pick: 2, tile: 3 };
  const R = K.results(), report = [];
  const srv = await K.serve(o);
  const browser = await K.launch();
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);
    for (const size of o.sizes) {
      for (const name of ["row", "pick", "tile"]) {
        const ctx = await K.phone(browser, size);
        await ctx.clock.install({ time: K.pinned(o) });
        await ctx.addInitScript(() => { try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {} });
        const page = await ctx.newPage();
        let r;
        try { r = await route(page, srv.base, name); } catch (e) { r = { route: name, taps: null, detail: e.message.split("\n")[0] }; }
        r.size = size; report.push(r);
        const label = `${size} ${name}: ${r.taps == null ? "no bookable end" : r.taps + " taps"} (claim ${CLAIM[name]})` + (r.activationStart != null ? `, activationStart ${r.activationStart} ms` : "");
        if (r.skip) R.info(label, r.detail);
        else if (assert) {
          R.check(label, r.taps != null && r.taps <= CLAIM[name], r.detail);
          if (name === "row") R.check(`${size} row: the navigation activated a prerender (activationStart > 0)`, r.activationStart > 0, r.activationStart);
        } else R.info(label, r.detail);
        await ctx.close();
      }
    }
  } catch (e) {
    R.check("run", false, e.message);
  } finally {
    await browser.close(); srv.stop();
  }
  const jf = o.get("json", null);
  if (jf) fs.writeFileSync(jf, JSON.stringify(report, null, 1));
  process.exit(R.code());
})();
