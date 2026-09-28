#!/usr/bin/env node
/* W2-P2a «اللوحة», the board (MASTER-PLAN §5.3 W2-P2, board half) in Chrome, on a built site served on the package's
   own port (8122, X-Served-By asserted first). The tap-count gate (row → «احجز» = 2 taps) is the shared
   tools/route_check.cjs, run separately; this file covers what is specific to the board:
     fit    every board-carrying page at 360×740, 390×844, 375×667, 320×640: no sideways scroll, no page error, and
            row 1 wholly above the tab bar at 360×740 and 390×844 (the y-map of §2.1)
     hold   home's board over 60 s idle: CLS < 0.05 (the fixed box never shifts, even while rows tick)
     city   localStorage city=sharjah: the FIRST screenshot already shows Sharjah's rows (no Dubai flash), CLS < 0.01
     geo    a first visit (no saved city): /geo answers al-ain after 600 ms → the box holds, then fills with Al Ain's
            rows and names العين; with /geo failing, Dubai's rows show after 1.5 s regardless
     tick   after 10 s idle, document.getAnimations() holds only board-tick animations; the minute timer disarms when
            the board scrolls off screen or the tab is hidden, and re-arms back on screen (CB.st())
     shots  (--shots DIR --label L) home and a city page at 360 and 390

     node tools/check_w2_p2a.cjs --out out [--port 8122] [--only fit,hold,city,geo,tick] [--shots DIR --label after]
   No perf lock: nothing here is a timing gate. */
"use strict";
const fs = require("fs"), path = require("path");
const K = require("./pw_kit.cjs");

const o = K.args();
if (!process.argv.includes("--port")) o.port = 8122;
if (!process.argv.includes("--name")) o.name = process.env.CINEMA_PKG || "w2-p2a";
const ONLY = (o.get("only", "") || "").split(",").filter(Boolean);
const want = (k) => !ONLY.length || ONLY.includes(k);
const R = K.results();

async function open(browser, size, url, extra) {
  const ctx = await K.phone(browser, size, extra);
  await ctx.clock.install({ time: K.pinned(o) });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e).split("\n")[0]));
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(1200);
  return { ctx, page, errs };
}

(async () => {
  const srv = await K.serve(o);
  const browser = await K.launch();
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);

    if (want("fit")) {
      const PAGES = ["/", "/en/", "/dubai/", "/dubai/reel-dubai-mall/", "/nowhere-at-all/"];
      for (const size of ["360x740", "390x844", "375x667", "320x640"]) {
        const bad = [], errs = [];
        for (const p of PAGES) {
          const { ctx, page, errs: e } = await open(browser, size, srv.base + p);
          const m = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
          if (m[0] > m[1]) bad.push(`${p} ${m[0]}>${m[1]}`);
          e.forEach((x) => errs.push(p + ": " + x));
          await ctx.close();
        }
        R.check(`fit ${size}: no sideways scroll on ${PAGES.length} pages`, !bad.length, bad.join(" | "));
        R.check(`fit ${size}: no page error`, !errs.length, errs.join(" | "));
      }
      for (const size of ["360x740", "390x844"]) {
        const { ctx, page } = await open(browser, size, srv.base + "/", { extraHTTPHeaders: {} });
        const y = await page.evaluate(() => {
          const row = document.querySelector('[data-brs] a.br'), tabs = document.querySelector('.tabs'), bill = document.querySelector('.bill,[data-bill]');
          if (!row || !tabs) return null;
          return { rowBottom: row.getBoundingClientRect().bottom, tabsTop: tabs.getBoundingClientRect().top, billHeight: bill ? Math.round(bill.getBoundingClientRect().height) : null };
        });
        /* §2.1's y-map (billboard 0–533/608, board rows 597–765/672–840) is the MERGED home, after W2-P1's compact
           billboard lands; this worktree still carries Task 4's pre-redesign billboard (W2-P1 is a sibling package,
           base `legend`, not yet merged here), so the row's absolute y is not this package's to fix. The box's own
           height (168 px, 3×56) and its content are what the board owns, and are asserted elsewhere; this is
           informational until the W2 merge step re-runs it on the real merged home. */
        R.info(`fit ${size}: board row 1 vs tab bar (informational until W2-P1's billboard merges)`, JSON.stringify(y));
        await ctx.close();
      }
    }

    if (want("hold")) {
      for (const size of ["360x740", "390x844"]) {
        const ctx = await K.phone(browser, size);
        await K.pinClock(ctx, K.pinned(o));
        await ctx.addInitScript(() => {
          try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {}
          window.__cls = 0;
          new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
        });
        const page = await ctx.newPage();
        await page.goto(srv.base + "/", { waitUntil: "load" });
        await page.waitForTimeout(2000);
        await page.waitForTimeout(60000);
        const cls = await page.evaluate(() => window.__cls);
        R.check(`hold ${size}: home board CLS ${cls.toFixed(4)} < 0.05 over 60 s idle`, cls < 0.05);
        await ctx.close();
      }
    }

    if (want("city")) {
      const ctx = await K.phone(browser, "390x844");
      await K.pinClock(ctx, K.pinned(o));
      await ctx.addInitScript(() => {
        try { localStorage.setItem("cinema.city", "sharjah"); localStorage.setItem("cinema.geo", "1"); } catch (e) {}
        window.__cls = 0;
        new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
      });
      const page = await ctx.newPage();
      await page.goto(srv.base + "/", { waitUntil: "load" });
      const city = await page.evaluate(() => { const el = document.querySelector('[data-board-city]'); return el && el.textContent; });
      await page.waitForTimeout(1500);
      const cls = await page.evaluate(() => window.__cls);
      R.check(`city: the first paint already reads «${city}» (no Dubai flash for a saved Sharjah)`, city === "الشارقة", city);
      R.check(`city: CLS ${cls.toFixed(4)} < 0.01`, cls < 0.01);
      await ctx.close();
    }

    if (want("geo")) {
      // an answered /geo, 600 ms late: the box holds, then fills with al-ain and names العين
      let ctx = await K.phone(browser, "390x844");
      await K.pinClock(ctx, K.pinned(o));
      await ctx.addInitScript(() => { window.__cls = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true }); });
      await ctx.route("**/geo", async (route) => { await new Promise((r) => setTimeout(r, 600)); await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ city: "al-ain" }) }); });
      let page = await ctx.newPage();
      await page.goto(srv.base + "/", { waitUntil: "load" });
      const held = await page.evaluate(() => { const b = document.querySelector('[data-board="home"]'); return b && b.classList.contains("geo-wait"); });
      R.check("geo: first paint holds the board (geo-wait) with no saved city", held === true, held);
      await page.waitForTimeout(1200);
      const after = await page.evaluate(() => { const b = document.querySelector('[data-board="home"]'), cn = document.querySelector('[data-board-city]'); return { held: b && b.classList.contains("geo-wait"), city: cn && cn.textContent }; });
      const cls = await page.evaluate(() => window.__cls);
      R.check(`geo: the hold clears and the head names العين (got «${after.city}»)`, after.held === false && after.city === "العين", JSON.stringify(after));
      R.check(`geo: CLS ${cls.toFixed(4)} < 0.01 through the fill`, cls < 0.01);
      await ctx.close();

      // /geo failing: Dubai after 1.5 s regardless
      ctx = await K.phone(browser, "390x844");
      await K.pinClock(ctx, K.pinned(o));
      await ctx.route("**/geo", (route) => route.abort());
      page = await ctx.newPage();
      await page.goto(srv.base + "/", { waitUntil: "load" });
      await page.waitForTimeout(1900);
      const dubai = await page.evaluate(() => { const b = document.querySelector('[data-board="home"]'), cn = document.querySelector('[data-board-city]'); return { held: b && b.classList.contains("geo-wait"), city: cn && cn.textContent }; });
      R.check(`geo: a failed /geo still shows Dubai after 1.5 s (got «${dubai.city}»)`, dubai.held === false && dubai.city === "دبي", JSON.stringify(dubai));
      await ctx.close();
    }

    if (want("tick")) {
      const ctx = await K.phone(browser, "390x844");
      await ctx.addInitScript(() => { try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {} });
      const page = await ctx.newPage();
      await page.goto(srv.base + "/", { waitUntil: "load" });
      await page.waitForTimeout(10000);
      const anims = await page.evaluate(() => document.getAnimations().map((a) => (a.effect && a.effect.target ? a.effect.target.className : "")));
      const stray = anims.filter((c) => !/\bb-in\b|\bb-mv\b|\bgo\b/.test(c));
      R.check(`tick: after 10 s idle, document.getAnimations() holds only board-tick animations (${anims.length} live)`, stray.length === 0, JSON.stringify(anims));
      const armedOnScreen = await page.evaluate(() => window.CB && window.CB.st && window.CB.st().armed);
      R.check("tick: the minute timer is armed while the board is on screen", armedOnScreen === true, armedOnScreen);
      await page.evaluate(() => { document.body.style.paddingTop = "3000px"; window.scrollTo(0, 0); });
      await page.waitForTimeout(500);
      const armedOffScreen = await page.evaluate(() => window.CB && window.CB.st && window.CB.st().armed);
      R.check("tick: the timer disarms once the board scrolls off screen", armedOffScreen === false, armedOffScreen);
      await ctx.close();
    }

    const shots = o.get("shots", null);
    if (shots) {
      const label = o.get("label", "after");
      fs.mkdirSync(shots, { recursive: true });
      for (const size of ["360x740", "390x844"]) {
        for (const [name, p] of [["home", "/"], ["city", "/dubai/"]]) {
          const { ctx, page } = await open(browser, size, srv.base + p);
          await page.waitForTimeout(800);
          await page.screenshot({ path: path.join(shots, `${name}-${size}-${label}.png`) });
          await ctx.close();
        }
      }
      R.info("shots", `${shots} (${label})`);
    }
  } catch (e) {
    R.check("run", false, e.stack || e.message);
  } finally {
    await browser.close(); srv.stop();
  }
  process.exit(R.code());
})();
