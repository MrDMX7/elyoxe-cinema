#!/usr/bin/env node
/* Idle motion (W1-P1 tool; MASTER-PLAN §1.3 and §7.3 #7): «ما يتحرك شي إلا إذا تحركت المدينة». After 10 s with no input on
   a phone, the page's running animations (document.getAnimations(): CSS animations and transitions, Web Animations)
   may only be the board's minute tick; under prefers-reduced-motion: reduce there is no transform animation at all.
   Today (before the board, W2-P2) it records what runs; --assert turns the rule on.

     node tools/idle_check.cjs --out out [--port 8111] [--size 360x740,390x844] [--page /] [--idle 10] [--window 7] [--assert] [--json FILE]

   A perf tool: it takes the laptop's perf lock (tools/perf_lock.cjs) and asserts X-Served-By first. The board tick is
   an animation whose target sits inside the board ([data-board] or #now) or a flip tile (.flip). */
"use strict";
const fs = require("fs");
const K = require("./pw_kit.cjs");
const LOCK = require("./perf_lock.cjs");

async function running(page) {
  return page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running" || a.playState === "pending").map((a) => {
    const t = a.effect && a.effect.target, kf = a.effect && a.effect.getKeyframes ? a.effect.getKeyframes() : [];
    const cls = t && typeof t.className === "string" && t.className ? "." + t.className.trim().split(/\s+/).join(".") : "";
    return { kind: a.constructor.name, name: a.animationName || a.transitionProperty || a.id || "", target: t ? t.tagName.toLowerCase() + cls : "",
      board: !!(t && t.closest && t.closest("[data-board], #now, .flip")), transform: kf.some((k) => "transform" in k || "translate" in k || "scale" in k || "rotate" in k),
      iterations: a.effect && a.effect.getTiming ? a.effect.getTiming().iterations : null };
  }));
}

(async () => {
  const o = K.args();
  const pagePath = o.get("page", "/"), idle = +o.get("idle", 10), win = +o.get("window", 7), assert = o.has("assert");
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
      for (const reduce of [false, true]) {
        const ctx = await K.phone(browser, size, reduce ? { reducedMotion: "reduce" } : {});
        await K.pinClock(ctx, K.pinned(o));
        const page = await ctx.newPage();
        await page.goto(srv.base + pagePath, { waitUntil: "load" });
        await page.waitForTimeout(idle * 1000);
        /* then a window as long as the longest autonomous cycle on the page (the desktop billboard's 6 s turn): every
           animation that runs in it, sampled every 250 ms, so a periodic one is never missed between two turns */
        const seen = new Map();
        for (let t = 0; t < win * 1000; t += 250) {
          for (const x of await running(page)) seen.set(x.kind + x.name + x.target, x);
          await page.waitForTimeout(250);
        }
        const a = [...seen.values()];
        const label = `${pagePath} ${size}${reduce ? " reduced motion" : ""} after ${idle} s idle, over the next ${win} s`;
        report.push({ size, reduce, animations: a });
        const notBoard = a.filter((x) => !x.board), transforms = a.filter((x) => x.transform);
        const list = (xs) => xs.map((x) => `${x.kind} ${x.name} on ${x.target}${x.iterations === Infinity ? " (loops)" : ""}`).join(" | ") || "none";
        if (reduce) {
          if (assert) R.check(label + ": no transform animation", transforms.length === 0, list(transforms));
          else R.info(label + ": transform animations", list(transforms));
        } else if (assert) R.check(label + ": only the board's tick runs", notBoard.length === 0, list(notBoard));
        else R.info(label + ": running", list(a));
        await ctx.close();
      }
    }
  } catch (e) {
    R.check("run", false, e.message);
  } finally {
    await browser.close(); srv.stop(); lock.release();
  }
  const jf = o.get("json", null);
  if (jf) fs.writeFileSync(jf, JSON.stringify(report, null, 1));
  process.exit(R.code());
})();
