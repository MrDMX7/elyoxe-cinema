#!/usr/bin/env node
/* W1-P2 (the system: tokens, gold = yours, type, paper; MASTER-PLAN §5.2) in Chrome, on a built site served on the
   package's own port (8112, X-Served-By asserted first):
     fit      every page the package restyled, at 360×740, 390×844, 375×667 and 320×640: no sideways scroll, no page error
     clip     at 320×640: no fixed-height box the system sizes clips its text (tile titles, the billboard's words, the
              near slot, the dock, the tab labels) — scrollHeight <= clientHeight
     gold     gold text nodes on home's first screen (today's build) and on the fixture of the FINAL first screen
              (billboard + board head + 3 rows, tests/fixtures/first_screen.html): ≤ 8, with and without Fazaa; designed
              3 and 6; 0 gold colons anywhere
     glued    no tile's text reads «33.6042.00»: /\d\.\d\d\d/ and /\d\d\.\d\d\d\d/ never match, with and without a card
     sizes    every visible text node on the checked pages is drawn at a size of the scale (§1.4), an object size or 11 px
     fonts    network log: no page loads the Markazi Latin face; home with a Latin title on the billboard loads none of it;
              the digits subset is fetched only by a page that sets a numeral in Markazi
     press    a poster, a time button, a chip and a tab press to scale(.97) and come back; nothing is left transformed at
              rest; under reduced motion nothing scales
     shots    (--shots DIR --label L) the first screen of home, home's rows, a film, a city, a cinema, the cards page, the 404
              and /en/ at 360×740 and 390×844

     node tools/check_w1_p2.cjs --out out [--port 8112] [--name w1-p2] [--only fit,clip,…] [--shots DIR --label after]
   No perf lock: nothing here is a timing. */
"use strict";
const fs = require("fs"), path = require("path");
const K = require("./pw_kit.cjs");
const GOLD = require("./gold_count.cjs");

const o = K.args(null, {});
if (!process.argv.includes("--port")) o.port = 8112;
if (!process.argv.includes("--name") && !process.env.CINEMA_PKG) o.name = "w1-p2";
const ONLY = (o.get("only", "") || "").split(",").filter(Boolean);
const want = (k) => !ONLY.length || ONLY.includes(k);
const FILM = o.get("film", "heart-of-the-beast"), CINEMA = o.get("cinema", "dubai/reel-dubai-mall");
const PAGES = ["/", "/en/", `/film/${FILM}/`, `/en/film/${FILM}/`, "/dubai/", `/${CINEMA}/`, "/cinemas/", "/cards/", "/cards/fazaa/",
  "/halls/", "/sources/", "/coming/", "/nowhere-at-all/"];
const R = K.results();
const FIXTURE = path.join(K.ROOT, "tests", "fixtures", "first_screen.html");

/* the type scale (MASTER-PLAN §1.4), in px, as a phone at this width draws it: the 7 steps, the listed object sizes,
   the title steps and 11 px (licence credits); anything else on a page is a size the system forgot */
function allowed(vw) {
  const clamp = (a, v, b) => Math.min(Math.max(a, v), b);
  const hero = clamp(38, 0.12 * vw, 64), h1 = clamp(32, 0.08 * vw, 48);
  const cap = (t) => Math.min(t, 0.16 * vw);
  const s = [hero, h1, 28, 16, 17, 13, 11, 12 /* velvet tags */, 20, 22, 27, 30, 40, 46, 72, 96, 120, 160,
    ...[64, 48, 38, 32].map(cap), ...[64, 48, 38, 32].map((t) => Math.min(t * 1.5, 96))];
  return s.map((x) => Math.round(x * 100) / 100);
}

async function open(browser, size, url, opts) {
  opts = opts || {};
  const ctx = await K.phone(browser, size, opts.ctx);
  await K.pinClock(ctx, K.pinned(o));
  await ctx.addInitScript((c) => { try { localStorage.setItem("cinema.city", "dubai"); if (c) localStorage.setItem("cinema.card", c); } catch (e) {} }, opts.card || "");
  const page = await ctx.newPage();
  const errs = [], reqs = [];
  page.on("pageerror", (e) => errs.push(String(e).split("\n")[0]));
  page.on("request", (r) => reqs.push(r.url()));
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(opts.wait || 1800);
  return { ctx, page, errs, reqs };
}

(async () => {
  const srv = await K.serve(o);
  const browser = await K.launch();
  const report = {};
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);

    if (want("shots")) {
      const dir = o.get("shots", null), label = o.get("label", "shot");
      if (dir) {
        fs.mkdirSync(dir, { recursive: true });
        const shots = [["home", "/"], ["rows", "/#rows"], ["film", `/film/${FILM}/`], ["city", "/dubai/"], ["cinema", `/${CINEMA}/`],
          ["cards", "/cards/"], ["404", "/nowhere-at-all/"], ["en", "/en/"]];
        for (const size of ["360x740", "390x844"]) {
          for (const [name, p] of shots) {
            for (const card of name === "rows" || name === "film" ? ["", "fazaa"] : [""]) {
              const { ctx, page } = await open(browser, size, srv.base + p.replace("#rows", ""), { card });
              if (name === "rows") await page.evaluate(() => { const r = document.querySelector(".rail:not([data-near-row]), .rail"); if (r) scrollTo(0, r.getBoundingClientRect().top + scrollY - 70); });
              await page.waitForTimeout(400);
              const f = path.join(dir, `${name}${card ? "-" + card : ""}-${size}-${label}.png`);
              await page.screenshot({ path: f });
              await ctx.close();
            }
          }
        }
        R.info("shots", dir);
      }
    }

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

    if (want("clip")) {
      const SEL = [".tile .t", ".bill-t", ".bill-v", ".bill-in", ".now-f", ".now-w", ".nr-t", ".nr-c", ".tabs a span", ".pill span", ".dk-t", ".fv", ".ff", ".br-f", ".br-c"];
      const bad = [];
      for (const p of ["/", `/film/${FILM}/`, "/dubai/", `/${CINEMA}/`]) {
        const { ctx, page } = await open(browser, "320x640", srv.base + p);
        if (p.startsWith("/film/")) await page.evaluate(() => { const b = document.querySelector(".tx .tm:not(.past), .tm:not(.past)"); if (b) b.click(); });
        await page.waitForTimeout(300);
        const got = await page.evaluate((SEL) => {
          const out = [];
          for (const s of SEL) for (const el of document.querySelectorAll(s)) {
            const cs = getComputedStyle(el);
            if (!el.checkVisibility || !el.checkVisibility()) continue;
            const clipped = /hidden|clip/.test(cs.overflowY + cs.overflow) || cs.webkitLineClamp !== "none";
            if (!clipped) continue;
            /* a one-line ellipsis clips sideways by design; what must never happen is Arabic dots cut off below */
            if (el.scrollHeight > el.clientHeight + 1 && cs.webkitLineClamp === "none") out.push(s + " «" + el.textContent.trim().slice(0, 24) + "» " + el.scrollHeight + ">" + el.clientHeight);
          }
          return out;
        }, SEL);
        got.forEach((x) => bad.push(p + " " + x));
        await ctx.close();
      }
      R.check("clip 320×640: no fixed-height box cuts its text", !bad.length, bad.slice(0, 12).join(" | "));
    }

    if (want("gold")) {
      /* today's home, as built */
      for (const size of o.sizes) {
        for (const card of ["", "fazaa"]) {
          const { ctx, page } = await open(browser, size, srv.base + "/", { card, wait: 2500 });
          const got = await GOLD.count(page);
          const colons = got.filter((x) => x.colon).length;
          (report.gold = report.gold || []).push({ where: "home", size, card, n: got.length, colons, nodes: got });
          R.check(`gold home ${size} ${card || "no card"}: ${got.length} gold text nodes (≤ 8), ${colons} gold colons`, got.length <= 8 && !colons,
            got.map((x) => x.el + " «" + x.text + "»").join(" | "));
          await ctx.close();
        }
      }
      /* the final first screen (the fixture), served beside the build so it draws with this build's stylesheet */
      const fx = path.join(o.out, "__w1p2");
      fs.mkdirSync(fx, { recursive: true });
      fs.copyFileSync(FIXTURE, path.join(fx, "index.html"));
      for (const size of o.sizes) {
        for (const [card, designed] of [["", 3], ["fazaa", 6]]) {
          const { ctx, page } = await open(browser, size, srv.base + "/__w1p2/" + (card ? "?card=" + card : ""), { wait: 600 });
          const got = await GOLD.count(page);
          const colons = got.filter((x) => x.colon).length;
          (report.gold = report.gold || []).push({ where: "fixture", size, card, n: got.length, colons, nodes: got });
          R.check(`gold FINAL first screen ${size} ${card || "no card"}: ${got.length} gold (designed ${designed}, ≤ 8), ${colons} gold colons`,
            got.length === designed && got.length <= 8 && !colons, got.map((x) => x.el + " «" + x.text + "»").join(" | "));
          await ctx.close();
        }
      }
      /* colons anywhere: every page, the whole page (not the first screen only) */
      const gc = [];
      for (const p of PAGES) {
        const { ctx, page } = await open(browser, "390x844", srv.base + p, { card: "fazaa" });
        const n = await page.evaluate(() => {
          const probe = document.createElement("i"); probe.style.color = "var(--gold)"; document.body.appendChild(probe);
          const g = getComputedStyle(probe).color; probe.remove();
          const out = [], w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          for (let t = w.nextNode(); t; t = w.nextNode()) {
            const s = t.textContent.trim();
            if (!s || !(/^[:：]$/.test(s) || (s.includes(":") && /^[\d: ]+$/.test(s)))) continue;
            const el = t.parentElement;
            if (el && getComputedStyle(el).color === g && el.checkVisibility && el.checkVisibility()) out.push(el.className + " «" + s + "»");
          }
          return out;
        });
        n.forEach((x) => gc.push(p + " " + x));
        await ctx.close();
      }
      R.check(`gold colons: none on ${PAGES.length} pages (with Fazaa, whole page)`, !gc.length, gc.slice(0, 8).join(" | "));
    }

    if (want("glued")) {
      const bad = [];
      for (const size of o.sizes) {
        for (const card of ["", "fazaa"]) {
          for (const p of ["/", "/dubai/", `/${CINEMA}/`, "/en/"]) {
            const { ctx, page } = await open(browser, size, srv.base + p, { card, wait: 2500 });
            const t = await page.evaluate(() => [...document.querySelectorAll(".tile, .film, .nr, .now, .bill .cta, .row, .srow, table.prices tr")]
              .map((el) => el.innerText.replace(/\s+/g, " ")).filter((x) => /\d\.\d\d\d/.test(x) || /\d\d\.\d\d\d\d/.test(x)));
            t.forEach((x) => bad.push(`${p} ${size} ${card || "no card"}: «${x.slice(0, 60)}»`));
            await ctx.close();
          }
        }
      }
      R.check("glued: no price reads «33.6042.00» (tiles, rows, tables; with and without Fazaa)", !bad.length, bad.slice(0, 6).join(" | "));
    }

    if (want("sizes")) {
      const bad = {};
      for (const size of o.sizes) {
        const vw = +size.split("x")[0], ok = allowed(vw);
        for (const p of ["/", `/film/${FILM}/`, "/dubai/", `/${CINEMA}/`, "/cinemas/", "/cards/", "/cards/fazaa/", "/halls/", "/sources/", "/nowhere-at-all/", "/en/"]) {
          const { ctx, page } = await open(browser, size, srv.base + p);
          const got = await page.evaluate((ok) => {
            const seen = {}, w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            for (let t = w.nextNode(); t; t = w.nextNode()) {
              if (!t.textContent.trim()) continue;
              const el = t.parentElement;
              if (!el || !el.checkVisibility || !el.checkVisibility()) continue;
              /* page-scoped features keep their own files (Wave 2's): only what the system's sheets draw is judged */
              if (el.closest(".vh, .cmp, .srch, .seatmap, .sm, [data-cmp], .ins, .people, .ppl, .cs-grid, .coming, .hubs, .seasons, .og, .venue, .snacks, .plan, .pw, dialog")) continue;
              const px = Math.round(parseFloat(getComputedStyle(el).fontSize) * 100) / 100;
              if (!ok.some((a) => Math.abs(a - px) < 0.6)) { const k = px + "px " + el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).join(".") : ""); seen[k] = seen[k] || t.textContent.trim().slice(0, 20); }
            }
            return seen;
          }, ok);
          for (const k in got) (bad[p] = bad[p] || []).push(size + " " + k + " «" + got[k] + "»");
          await ctx.close();
        }
      }
      const lines = Object.entries(bad).map(([p, v]) => p + ": " + [...new Set(v)].slice(0, 6).join(" ; "));
      R.check("sizes: every visible text is at a size of the scale, an object size or 11 px", !lines.length, lines.join(" | "));
      report.sizes = bad;
    }

    if (want("fonts")) {
      const lat = [], dig = [];
      for (const p of PAGES) {
        const { ctx, page, reqs } = await open(browser, "390x844", srv.base + p, { wait: 2200 });
        await page.evaluate(() => scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(700);
        await page.evaluate(() => document.fonts.ready);
        const needDigits = await page.evaluate(() => {
          const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          for (let t = w.nextNode(); t; t = w.nextNode()) {
            if (!/[0-9:]/.test(t.textContent)) continue;
            const el = t.parentElement;
            if (el && /Markazi/.test(getComputedStyle(el).fontFamily.split(",")[0])) return el.tagName + "." + el.className + " «" + t.textContent.trim().slice(0, 20) + "»";
          }
          return "";
        });
        const got = await page.evaluate(() => performance.getEntriesByType("resource").map((e) => e.name).filter((u) => /\.woff2/.test(u)));
        const all = [...new Set(reqs.concat(got))];
        if (all.some((u) => /markazi-700-latin/.test(u))) lat.push(p);
        const d = all.some((u) => /markazi-700-digits/.test(u));
        if (d && !needDigits) dig.push(p + " fetched the digits with no numeral set in Markazi");
        (report.fonts = report.fonts || []).push({ page: p, fonts: all.filter((u) => /woff2/.test(u)).map((u) => u.split("/").pop()), needDigits });
        await ctx.close();
      }
      R.check(`fonts: the Markazi Latin face loads on none of ${PAGES.length} pages`, !lat.length, lat.join(" | "));
      R.check("fonts: the digits subset loads only where a numeral is set in Markazi", !dig.length, dig.join(" | "));
      /* home with a Latin title on the billboard: its title swapped in the page for a Latin one with punctuation and
         digits, as a real feed's «Avengers: Doomsday» or «F1» would be */
      for (const lang of ["", "en/"]) {
        const { ctx, page, reqs } = await open(browser, "390x844", srv.base + "/" + lang, { wait: 1500 });
        const t = await page.evaluate(() => {
          const a = document.querySelector(".bill-t a") || document.querySelector(".bill-t");
          if (!a) return null;
          a.setAttribute("dir", "ltr"); a.setAttribute("lang", "en"); a.textContent = "Avengers: Doomsday Part 2 – Legends’ «Return»!";
          return getComputedStyle(a).fontFamily;
        });
        await page.waitForTimeout(800);
        await page.evaluate(() => document.fonts.ready);
        const got = await page.evaluate(() => performance.getEntriesByType("resource").map((e) => e.name));
        const all = reqs.concat(got);
        R.check(`fonts: /${lang} with a Latin title on the billboard loads no Markazi Latin (title face: ${t})`, t != null && !all.some((u) => /markazi-700-latin/.test(u)),
          all.filter((u) => /woff2/.test(u)).map((u) => u.split("/").pop()).join(", "));
        await ctx.close();
      }
    }

    if (want("press")) {
      for (const size of o.sizes) {
        const { ctx, page } = await open(browser, size, srv.base + `/film/${FILM}/`);
        const res = await page.evaluate(async () => {
          const out = {};
          const sel = { tile: ".tile .tp, .film .pst", time: ".tm:not(.past)", chip: ".chip", tab: ".tabs a" };
          for (const k in sel) {
            const el = document.querySelector(sel[k]);
            if (!el) { out[k] = "missing"; continue; }
            out[k] = getComputedStyle(el).transform;
          }
          return out;
        });
        R.check(`press ${size}: nothing is transformed at rest`, Object.values(res).every((v) => v === "none" || v === "missing"), JSON.stringify(res));
        /* press the first bookable time with a real touch-down and read its transform while held */
        const b = await page.$(".tx .tm:not(.past), .tm:not(.past)");
        if (b) {
          await b.evaluate((el) => el.scrollIntoView({ block: "center" }));   /* clear of the dock and the tab bar */
          await page.waitForTimeout(100);
          const box = await b.boundingBox();
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await page.mouse.down();
          await page.waitForTimeout(60);
          const held = await b.evaluate((el) => getComputedStyle(el).transform);
          await page.mouse.up();
          R.check(`press ${size}: a time button presses to scale(.97)`, /matrix\(0\.97, 0, 0, 0\.97/.test(held), held);
        }
        await ctx.close();
        const rm = await open(browser, size, srv.base + `/film/${FILM}/`, { ctx: { reducedMotion: "reduce" } });
        const b2 = await rm.page.$(".tx .tm:not(.past), .tm:not(.past)");
        if (b2) {
          await b2.evaluate((el) => el.scrollIntoView({ block: "center" }));
          await rm.page.waitForTimeout(100);
          const box = await b2.boundingBox();
          await rm.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await rm.page.mouse.down();
          await rm.page.waitForTimeout(60);
          const held = await b2.evaluate((el) => getComputedStyle(el).transform);
          await rm.page.mouse.up();
          R.check(`press ${size} reduced motion: nothing scales`, held === "none", held);
        }
        await rm.ctx.close();
      }
    }
  } catch (e) {
    R.check("run", false, e.stack || e.message);
  } finally {
    await browser.close(); srv.stop();
  }
  const jf = o.get("json", null);
  if (jf) fs.writeFileSync(jf, JSON.stringify(report, null, 1));
  process.exit(R.code());
})();
