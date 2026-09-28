#!/usr/bin/env node
/* W1-P1 (seams and guards; MASTER-PLAN §5.2) in Chrome, on a built site served on the package's own port (8111, X-Served-By
   asserted first). Nothing here is visible to a visitor; what is checked is that nothing moved and the seams work:
     fit      every page the package touched, at 360×740, 390×844, 375×667 and 320×640: no sideways scroll, no page error
     hidden   every [hidden] element is display:none, with and without script, after the sheets open and close; a held
              slot (data-hold) keeps its box with script only
     hold     home at 360 and 390: the held slots keep their height for 60 s, and home's CLS stays under 0.05
     hooks    the hook bus in a real page: card, city, slice, day and minute arrive (minute at the UAE :00)
     key      showKey() in the page equals the FNV-1a twin
     pagecss  the 404 carries its own page-scoped sheet (and its rule applies); home carries none
     shots    (--shots DIR --label L) the first screen of home, a film, a city, a cinema and the 404 at 360 and 390

     node tools/check_w1_p1.cjs --out out [--port 8111] [--only fit,hidden,…] [--shots DIR --label after] [--film fid] [--cinema city/cid]
   No perf lock: nothing here is a timing. */
"use strict";
const fs = require("fs"), path = require("path");
const K = require("./pw_kit.cjs");

const o = K.args();
const ONLY = (o.get("only", "") || "").split(",").filter(Boolean);
const want = (k) => !ONLY.length || ONLY.includes(k);
const FILM = o.get("film", "heart-of-the-beast"), CINEMA = o.get("cinema", "dubai/reel-dubai-mall");
const PAGES = ["/", "/en/", `/film/${FILM}/`, "/dubai/", `/${CINEMA}/`, "/cinemas/", "/cards/", "/sources/", "/coming/", "/nowhere-at-all/"];
const R = K.results();

function fnv(cin, d, t, hk) {
  const s = Buffer.from([cin, d, t, hk || "Standard"].join("|"), "utf-8");
  let h = 0x811c9dc5;
  for (const b of s) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
  const k = h.toString(36);
  return k.length < 6 ? ("00000" + k).slice(-6) : k;
}

async function open(browser, size, url, extra) {
  const ctx = await K.phone(browser, size, extra);
  await ctx.clock.install({ time: K.pinned(o) });
  await ctx.addInitScript(() => { try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {} });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e).split("\n")[0]));
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(1800);
  return { ctx, page, errs };
}

const HIDDEN_STATE = () => {
  const bad = [], held = [];
  for (const el of document.querySelectorAll("[hidden]")) {
    const cs = getComputedStyle(el), js = document.documentElement.classList.contains("js");
    const k = el.tagName.toLowerCase() + (typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).join(".") : "");
    if (el.hasAttribute("data-hold") && js) {
      if (cs.display === "none" || cs.visibility !== "hidden") bad.push(k + " (held: " + cs.display + "/" + cs.visibility + ")");
      else held.push(k);
    } else if (cs.display !== "none") bad.push(k + " (" + cs.display + ")");
  }
  return { bad, held, n: document.querySelectorAll("[hidden]").length };
};

(async () => {
  const srv = await K.serve(o);
  const browser = await K.launch();
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);

    if (want("fit")) {
      for (const size of ["360x740", "390x844", "375x667", "320x640"]) {
        const bad = [], errs = [];
        for (const p of PAGES) {
          const { ctx, page, errs: e } = await open(browser, size, srv.base + p);
          const m = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth, innerWidth]);
          if (m[0] > m[1] || m[0] > m[2]) bad.push(`${p} ${m[0]}>${m[1]}`);
          e.forEach((x) => errs.push(p + ": " + x));
          await ctx.close();
        }
        R.check(`fit ${size}: no sideways scroll on ${PAGES.length} pages`, !bad.length, bad.join(" | "));
        R.check(`fit ${size}: no page error`, !errs.length, errs.join(" | "));
      }
    }

    if (want("hidden")) {
      for (const p of ["/", `/film/${FILM}/`, "/dubai/", `/${CINEMA}/`]) {
        for (const js of [true, false]) {
          const { ctx, page } = await open(browser, "390x844", srv.base + p, { javaScriptEnabled: js });
          let st = await page.evaluate(HIDDEN_STATE);
          const states = [["load", st]];
          if (js) {
            await page.click("#pill-city"); await page.waitForTimeout(500);
            states.push(["city sheet open", await page.evaluate(HIDDEN_STATE)]);
            await page.keyboard.press("Escape"); await page.waitForTimeout(500);
            states.push(["city sheet closed", await page.evaluate(HIDDEN_STATE)]);
            if (p.startsWith("/film/")) {
              const tm = page.locator(".cgs .tm:not(.past)").first();
              if (await tm.count()) { await tm.click(); await page.waitForTimeout(600); states.push(["a time chosen", await page.evaluate(HIDDEN_STATE)]); }
            }
          }
          for (const [label, s] of states)
            R.check(`hidden ${p} ${js ? "script" : "no script"} ${label}: ${s.n} [hidden], each hidden` + (s.held.length ? `; held with its box: ${s.held.join(", ")}` : ""), !s.bad.length, s.bad.join(" | "));
          await ctx.close();
        }
      }
    }

    if (want("hold")) {
      for (const size of ["360x740", "390x844"]) {
        const ctx = await K.phone(browser, size);
        await ctx.clock.install({ time: K.pinned(o) });
        await ctx.addInitScript(() => {
          try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {}
          window.__cls = 0;
          new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
        });
        const page = await ctx.newPage();
        await page.goto(srv.base + "/", { waitUntil: "load" });
        await page.waitForTimeout(2000);
        const box = () => page.evaluate(() => [...document.querySelectorAll("[data-hold]")].map((el) => [el.id || el.className, Math.round(el.getBoundingClientRect().height), el.hidden]));
        const a = await box();
        await page.waitForTimeout(60000);
        const b = await box(), cls = await page.evaluate(() => window.__cls);
        const same = JSON.stringify(a.map((x) => x.slice(0, 2))) === JSON.stringify(b.map((x) => x.slice(0, 2)));
        R.check(`hold ${size}: after 60 s the held slots keep their height (${b.map((x) => x[0] + " " + x[1] + " px" + (x[2] ? " held" : " filled")).join(", ")})`, same, JSON.stringify(a) + " → " + JSON.stringify(b));
        R.check(`hold ${size}: home CLS ${cls.toFixed(4)} < 0.05 over the first minute`, cls < 0.05);
        await ctx.close();
      }
    }

    if (want("hooks")) {
      const { ctx, page, errs } = await open(browser, "390x844", srv.base + "/");
      await page.evaluate(() => {
        window.__ev = [];
        for (const ev of ["card", "city", "slice", "day", "minute"]) window.CINEMA.on(ev, (x) => window.__ev.push([ev, ev === "minute" ? [x.getUTCSeconds(), x.getUTCMilliseconds()] : ev === "slice" ? x && x.city : x]));
      });
      R.check("hooks: window.CINEMA carries on, emit and showKey", await page.evaluate(() => ["on", "emit", "showKey"].every((k) => typeof window.CINEMA[k] === "function")));
      await page.click("#pill-card"); await page.waitForTimeout(400);
      const cardId = await page.evaluate(() => { const b = document.querySelector('#sheet-card button[data-card]:not([data-card=""])'); return b && b.getAttribute("data-card"); });
      if (cardId) await page.click(`#sheet-card button[data-card="${cardId}"]`);
      await page.waitForTimeout(400);
      await page.click("#pill-city"); await page.waitForTimeout(400);
      await page.click('#sheet-city [data-citypick] a[data-city="abu-dhabi"]');
      await page.waitForTimeout(3000);
      await ctx.clock.runFor(61000);
      await page.waitForTimeout(500);
      const ev = await page.evaluate(() => window.__ev);
      const has = (k, v) => ev.some((e) => e[0] === k && (v === undefined || JSON.stringify(e[1]) === JSON.stringify(v)));
      R.check(`hooks: «card» with the picked card (${cardId})`, has("card", cardId), JSON.stringify(ev));
      R.check("hooks: «city» then «slice» for abu-dhabi", has("city", "abu-dhabi") && has("slice", "abu-dhabi") &&
        ev.findIndex((e) => e[0] === "city") < ev.findIndex((e) => e[0] === "slice"), JSON.stringify(ev));
      const mins = ev.filter((e) => e[0] === "minute");
      R.check(`hooks: «minute» at the UAE :00 (${mins.length} in 61 s)`, mins.length >= 1 && mins.every((e) => e[1][0] === 0 && e[1][1] < 500), JSON.stringify(mins));
      R.check("hooks: no page error", !errs.length, errs.join(" | "));
      await ctx.close();
      const f = await open(browser, "390x844", srv.base + `/film/${FILM}/`);
      await f.page.evaluate(() => { window.__ev = []; window.CINEMA.on("day", (d) => window.__ev.push(d)); });
      const other = await f.page.evaluate(() => { const b = [...document.querySelectorAll("[data-day]")].find((x) => !x.hidden && x.getAttribute("aria-pressed") !== "true"); return b && b.getAttribute("data-day"); });
      if (other) { await f.page.click(`[data-day="${other}"]`); await f.page.waitForTimeout(300); }
      const days = await f.page.evaluate(() => window.__ev);
      if (other) R.check(`hooks: «day» with the chosen date (${other})`, days.includes(other), JSON.stringify(days));
      else R.info("hooks: «day»", "the film page has one day only");
      await f.ctx.close();
    }

    if (want("key")) {
      const { ctx, page } = await open(browser, "390x844", srv.base + "/");
      const rows = [["reel-dubai-mall", "2026-09-27", "21:30", "IMAX"], ["vox-mall-of-the-emirates", "2026-09-28", "00:05", "Standard"], ["سينما", "2026-09-28", "22:10", "قاعة"]];
      const got = await page.evaluate((rs) => rs.map((r) => window.CINEMA.showKey(r[0], r[1], r[2], r[3])), rows);
      R.check("key: showKey() in the page is the FNV-1a twin", JSON.stringify(got) === JSON.stringify(rows.map((r) => fnv(...r))), got.join(" "));
      await ctx.close();
    }

    if (want("pagecss")) {
      const { ctx, page } = await open(browser, "390x844", srv.base + "/nowhere-at-all/");
      const r = await page.evaluate(() => ({ links: [...document.querySelectorAll('link[rel="stylesheet"]')].map((l) => l.getAttribute("href")),
        pad: getComputedStyle(document.querySelector(".nf")).paddingBlockStart }));
      /* ui-edge.css (page-scoped, W2-P10's) is empty until the leader: a kind whose partials hold no rule links nothing */
      const pageCss = r.links.filter((h) => /\/assets\/page-404\./.test(h));
      const edge = fs.readFileSync(path.join(K.ROOT, "src", "css", "ui-edge.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "").trim();
      R.check(`pagecss: the 404 ${edge ? "links its own sheet" : "links no page sheet while ui-edge.css is empty"}; .nf still pads it (${r.pad})`,
        (edge ? pageCss.length === 1 : pageCss.length === 0) && r.pad === "60px", JSON.stringify(r));
      await ctx.close();
      const h = await open(browser, "390x844", srv.base + "/");
      const n = await h.page.evaluate(() => document.querySelectorAll('link[rel="stylesheet"]').length);
      R.check("pagecss: home loads the shared sheet only", n === 1, n);
      await h.ctx.close();
    }

    const shots = o.get("shots", null);
    if (shots) {
      const label = o.get("label", "after");
      fs.mkdirSync(shots, { recursive: true });
      for (const size of ["360x740", "390x844"]) {
        for (const [name, p] of [["home", "/"], ["film", `/film/${FILM}/`], ["city", "/dubai/"], ["cinema", `/${CINEMA}/`], ["404", "/nowhere-at-all/"]]) {
          const { ctx, page } = await open(browser, size, srv.base + p);
          await page.waitForTimeout(800);
          const f = path.join(shots, `${name}-${size}-${label}.png`);
          await page.screenshot({ path: f });
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
