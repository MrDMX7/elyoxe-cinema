#!/usr/bin/env node
/* Scroll smoothness, control against variant, interleaved (W1-P1 tool, from proposal A's pa/perf_a3.cjs; MASTER-PLAN
   §5.0 #5, §7.3 #3–#4). The absolute numbers on this laptop are noise; the relative comparison is the test. Each round
   loads the control and then the variant, each in a fresh phone context at 4× CPU, scrolls home with two synthesized
   gestures and records every frame's time (rAF), then 3 s of idle frames, and the long animation frames after FCP.
   Pass: the variant's median p95 frame time stays inside the control's own spread (its min…max over the rounds), and no
   long animation frame over 200 ms after FCP.

     node tools/perf_fx.cjs --out CONTROL [--variant-out VARIANT | --variant-css FILE] [--port 8111] [--size 390x844]
                            [--rounds 5] [--page /] [--now ISO] [--assert] [--json FILE]

   The variant build is served on the same port (serve.py --alt-out answers Host: localhost:<port>): one port per
   package, two origins, no shared cache. With neither variant flag it runs the control against itself (A/A: how much
   the laptop moves). Takes the perf lock, reports the wait and the load, asserts X-Served-By on both builds. */
"use strict";
const fs = require("fs");
const K = require("./pw_kit.cjs");
const LOCK = require("./perf_lock.cjs");

async function measure(browser, url, size, when, css) {
  const ctx = await K.phone(browser, size);
  await ctx.clock.install({ time: when });
  await ctx.addInitScript(() => {
    try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {}
    window.__loaf = [];
    try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__loaf.push([e.startTime, e.duration]); }).observe({ type: "long-animation-frame", buffered: true }); } catch (e) {}
  });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(2200);
  if (css) await page.addStyleTag({ content: css });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await page.waitForTimeout(600);
  await page.evaluate(() => {
    window.__f = []; let last = performance.now();
    const loop = (t) => { window.__f.push(t - last); last = t; if (!window.__stop) requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  });
  const vp = K.SIZES[size];
  await cdp.send("Input.synthesizeScrollGesture", { x: Math.round(vp.w / 2), y: Math.round(vp.h * 0.7), yDistance: -2600, speed: 1300, gestureSourceType: "touch", repeatCount: 1 });
  await cdp.send("Input.synthesizeScrollGesture", { x: Math.round(vp.w / 2), y: Math.round(vp.h * 0.35), yDistance: 1800, speed: 1600, gestureSourceType: "touch", repeatCount: 1 });
  await page.evaluate(() => { window.__stop = true; window.scrollTo(0, 0); window.__g = []; let last = performance.now(); window.__stop2 = false;
    const loop = (t) => { window.__g.push(t - last); last = t; if (!window.__stop2) requestAnimationFrame(loop); }; requestAnimationFrame(loop); });
  await page.waitForTimeout(3000);
  const m = await page.evaluate(() => {
    window.__stop2 = true;
    const f = window.__f.slice(2), s = [...f].sort((a, b) => a - b), n = f.length;
    const g = window.__g.slice(2), gs = [...g].sort((a, b) => a - b);
    const fcp = (performance.getEntriesByName("first-contentful-paint")[0] || {}).startTime || 0;
    const loaf = window.__loaf.filter((x) => x[0] > fcp);
    return { fps: +(1000 * n / f.reduce((a, b) => a + b, 0)).toFixed(1), p95: +s[Math.floor(n * 0.95)].toFixed(1), jank: +(100 * f.filter((x) => x > 25).length / n).toFixed(1),
      idleP95: +gs[Math.floor(gs.length * 0.95)].toFixed(1), loafMax: Math.round(Math.max(0, ...loaf.map((x) => x[1]))), loaf200: loaf.filter((x) => x[1] > 200).length };
  });
  await ctx.close();
  return m;
}

(async () => {
  const o = K.args(null);
  if (!process.argv.includes("--size")) o.sizes = ["390x844"];
  const rounds = +o.get("rounds", 5), pagePath = o.get("page", "/"), assert = o.has("assert");
  const vOut = o.get("variant-out", null), vCss = o.get("variant-css", null);
  if (vOut) o.altOut = require("path").resolve(vOut);
  const css = vCss ? fs.readFileSync(vCss, "utf-8") : null;
  const R = K.results(), report = {};
  const lock = await LOCK.acquire(o.name);
  const load = await LOCK.load();
  R.info("perf lock", `waited ${(lock.waitedMs / 1000).toFixed(1)} s; machine ${load.cpuBusyPct}% busy on ${load.cpus} threads`);
  const srv = await K.serve(o);
  const browser = await K.launch();
  try {
    await K.assertServed(srv.base, srv.stamp);
    if (srv.alt) await K.assertServed(srv.alt, srv.stamp + "-alt");
    R.check("X-Served-By on the document and an asset" + (srv.alt ? " of both builds" : ""), true);
    const when = K.pinned(o);
    for (const size of o.sizes) {
      const res = { control: [], variant: [] };
      for (let r = 0; r < rounds; r++) {
        res.control.push(await measure(browser, srv.base + pagePath, size, when, null));
        res.variant.push(await measure(browser, (srv.alt || srv.base) + pagePath, size, when, css));
        console.error(`round ${r + 1}/${rounds} at ${size} done`);
      }
      const med = (xs, k) => { const a = xs.map((x) => x[k]).sort((p, q) => p - q); return a[Math.floor(a.length / 2)]; };
      const cp = res.control.map((x) => x.p95), lo = Math.min(...cp), hi = Math.max(...cp);
      const vm = med(res.variant, "p95"), cm = med(res.control, "p95");
      const loaf = Math.max(...res.variant.map((x) => x.loafMax));
      report[size] = { control: res.control, variant: res.variant, controlSpread: [lo, hi], controlMedian: cm, variantMedian: vm };
      const line = `${size}: variant median p95 ${vm} ms against the control's ${cm} (spread ${lo}–${hi}); jank ${med(res.variant, "jank")}% vs ${med(res.control, "jank")}%; longest animation frame after FCP ${loaf} ms`;
      if (assert) {
        R.check(line, vm <= hi);
        R.check(`${size}: no long animation frame over 200 ms after FCP (variant)`, res.variant.every((x) => x.loaf200 === 0), loaf + " ms");
      } else R.info(line, vm <= hi ? "inside the control's spread" : "outside the control's spread");
    }
  } catch (e) {
    R.check("run", false, e.message);
  } finally {
    await browser.close(); srv.stop(); lock.release();
  }
  const jf = o.get("json", null);
  if (jf) fs.writeFileSync(jf, JSON.stringify({ load, waitedMs: lock.waitedMs, report }, null, 1));
  process.exit(R.code());
})();
