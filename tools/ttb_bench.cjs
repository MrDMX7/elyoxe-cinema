#!/usr/bin/env node
/* Time-to-Book (W1-P1 tool; MASTER-PLAN §7.3 #6). Cold cache, a phone at 4× CPU on 12 Mbps with 60 ms RTT: open home,
   tap board row 1 the moment it is visible, and stop the clock when «احجز» is on screen with a show-level chain href
   (the dock's, or the ticket's). The gate is ≤ 3.0 s from navigation start; no field number is claimed anywhere until
   the counter (W3-P6) measures one. Before the board (W2-P2) row 1 is the «يبدأ قريب منك» card (#now a[href*="#s-"]);
   today this records the baseline, and --assert turns the gate on.

     node tools/ttb_bench.cjs --out out [--port 8111] [--size 360x740,390x844] [--runs 5] [--now ISO] [--gate 3.0] [--assert] [--json FILE]

   A perf tool: it takes the perf lock (tools/perf_lock.cjs), reports the wait and the machine's load, and asserts
   X-Served-By before measuring. */
"use strict";
const fs = require("fs");
const K = require("./pw_kit.cjs");
const LOCK = require("./perf_lock.cjs");

const BOOK_VISIBLE = () => {
  const sites = Object.values((window.CT && window.CT.sites) || {}).map((u) => u.replace(/\/+$/, ""));
  return [...document.querySelectorAll("a")].some((a) => {
    if (!/احجز|Book/.test(a.textContent)) return false;
    const r = a.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && a.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }))) return false;
    const u = a.href.replace(/\/+$/, "");
    return /^https?:/.test(u) && !u.startsWith(location.origin) && !sites.includes(u);
  });
};

async function once(browser, base, size, when) {
  const ctx = await K.phone(browser, size);
  await ctx.clock.install({ time: when });
  await ctx.addInitScript(() => { try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {} });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 60, downloadThroughput: 12e6 / 8, uploadThroughput: 3e6 / 8 });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  const t0 = Date.now();
  await page.goto(base + "/", { waitUntil: "commit" });
  const row = page.locator('#now a[href*="#s-"]').first();
  await row.waitFor({ state: "visible", timeout: 20000 });
  const tRow = Date.now() - t0;
  await row.tap();
  await page.waitForURL(/\/film\/[^/]+\/#s-/, { timeout: 20000 });
  const cdp2 = await ctx.newCDPSession(page);   /* a new document: throttle it too */
  await cdp2.send("Emulation.setCPUThrottlingRate", { rate: 4 }).catch(() => {});
  await page.waitForFunction(BOOK_VISIBLE, null, { timeout: 20000, polling: 50 });
  const t = Date.now() - t0;
  await ctx.close();
  return { ms: t, rowMs: tRow };
}

(async () => {
  const o = K.args();
  const runs = +o.get("runs", 5), gate = +o.get("gate", 3.0), assert = o.has("assert");
  const R = K.results(), report = [];
  const lock = await LOCK.acquire(o.name);
  const load = await LOCK.load();
  R.info("perf lock", `waited ${(lock.waitedMs / 1000).toFixed(1)} s; machine ${load.cpuBusyPct}% busy on ${load.cpus} threads`);
  const srv = await K.serve(o);
  const browser = await K.launch();
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);
    for (const size of o.sizes) {
      const xs = [];
      for (let i = 0; i < runs; i++) {
        try { xs.push(await once(browser, srv.base, size, K.pinned(o))); } catch (e) { xs.push({ ms: null, err: e.message.split("\n")[0] }); }
      }
      const ok = xs.filter((x) => x.ms != null).map((x) => x.ms).sort((a, b) => a - b);
      const med = ok.length ? ok[Math.floor(ok.length / 2)] : null;
      report.push({ size, runs: xs, medianMs: med });
      const label = `${size} Time-to-Book median ${med == null ? "n/a" : (med / 1000).toFixed(2) + " s"} of ${ok.length}/${runs} runs (row visible at ${xs.filter((x) => x.rowMs).map((x) => (x.rowMs / 1000).toFixed(2)).join("/")} s)`;
      const detail = xs.map((x) => (x.ms == null ? "fail: " + x.err : (x.ms / 1000).toFixed(2))).join(" | ");
      if (assert) R.check(label + ` (gate ≤ ${gate} s)`, med != null && med <= gate * 1000, detail);
      else R.info(label, detail);
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
