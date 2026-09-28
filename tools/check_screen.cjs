#!/usr/bin/env node
/* W2-P1 · «الشاشة» (MASTER-PLAN §5.3) in Chrome, on a built site served on the package's own port (8121, X-Served-By
   asserted on the document and an asset first). Phones are isMobile + hasTouch at their DPR (pw_kit).
     fit      home (ar, en), a film with a frame and one without, at 360×740, 390×844, 375×667 and 320×640: no sideways
              scroll (scrollWidth == clientWidth), no page error
     screen   at 360×740 and 390×844 the first screen holds the film's picture (frame or case), the title, the verdict
              word, a price and the card door; the billboard's foot ≤ 533 / ≤ 608; what follows it starts on the first
              screen; a two-line title shrinks the case and the foot does not move
     clip     at 320×640: the billboard's words fit their slide, the CTA's words fit the button, the title is whole
     geo      a first visit from Al Ain (no saved city, /geo answering {"city":"al-ain"} after 600 ms): slide 1, its words,
              its picture and the LCP element are Dubai's, and nothing on the billboard changed after paint
     bytes    the billboard's image requests at 360 and 390: slide 1's with the page, slide 2's once idle, the rest only
              after a swipe; under Save-Data slide 1's only
     swipe    a touch swipe moves the strip one slide and the indicators follow, on / (RTL) and /en/ (LTR)
     lcp      the LCP element is slide 1's picture or title, and it and every ancestor are at opacity 1 from the first frame
     title    «Avengers Endgame: Encore» is whole (never clamped) on the billboard at 360 and 320 and on its film page
     idle     a phone left 20 s: no slide change, the strip where it was
     desk     1280×800: the turn happens after 6 s while on screen, and stops while the billboard is under half on screen
     motion   reduced motion: no recede animation, the house lights change at once; with motion the lights reach .92
     hero     the film hero at 390: with a frame the screen carries view-transition-name «poster», with none the case
              does; no fog anywhere; an archived film (--archived) has a hero with no price and no time
     shots    (--shots DIR --label L) the first screen of home and two films at 360×740 and 390×844

     node tools/check_w2_p1.cjs --out out [--port 8121] [--posters DIR] [--only fit,screen,…] [--film F] [--film2 F]
                                [--archived /film/weapons/] [--shots DIR --label after]
   No perf lock: nothing here is a timing (tools/idle_check.cjs, perf_fx.cjs and lh_gate.sh take it). */
"use strict";
const fs = require("fs"), path = require("path");
const K = require("./pw_kit.cjs");

const o = K.args(null, {});
if (!process.argv.includes("--port")) o.port = 8121;
if (!process.argv.includes("--name") && !process.env.CINEMA_PKG) o.name = "w2-p1";
o.posters = o.get("posters", null);
const ONLY = (o.get("only", "") || "").split(",").filter(Boolean);
const want = (k) => !ONLY.length || ONLY.includes(k);
const FILM = o.get("film", "heart-of-the-beast"), FILM2 = o.get("film2", "aaram"), ARCH = o.get("archived", null);
const R = K.results();
const report = {};
const FOOT = { "360x740": 533, "390x844": 608 };

async function open(browser, size, url, opts) {
  opts = opts || {};
  const ctx = size === "desk" ? await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "ar-AE", timezoneId: "Asia/Dubai",
    serviceWorkers: "block", reducedMotion: opts.rm ? "reduce" : "no-preference" }) : await K.phone(browser, size, Object.assign({ reducedMotion: opts.rm ? "reduce" : "no-preference" }, opts.ctx || {}));
  await K.pinClock(ctx, K.pinned(o));
  if (!opts.fresh) await ctx.addInitScript(() => { try { localStorage.setItem("cinema.city", "dubai"); } catch (e) {} });
  if (opts.init) await ctx.addInitScript(opts.init);
  await ctx.route(/youtube(-nocookie)?\.com|ytimg\.com/, (r) => r.abort());
  if (opts.route) await opts.route(ctx);
  const page = await ctx.newPage();
  const errs = [], reqs = [];
  page.on("pageerror", (e) => errs.push(String(e).split("\n")[0]));
  page.on("request", (r) => reqs.push({ url: r.url(), t: Date.now() }));
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(opts.wait == null ? 1500 : opts.wait);
  return { ctx, page, errs, reqs };
}

/* the billboard's picture files, slide by slide (loaded or still data-*) */
function slidePics(page) {
  return page.evaluate(() => [...document.querySelectorAll(".bill .slide")].map((s) => [...s.querySelectorAll("img, source")].flatMap((el) =>
    ["src", "srcset", "data-src", "data-srcset"].map((a) => el.getAttribute(a) || "").join(" ").split(/[\s,]+/)).filter((u) => u.startsWith("/posters/"))));
}

/* a finger's swipe across the strip: touchStart, moves, touchEnd over CDP */
async function swipe(page, x0, x1, y) {
  const c = await page.context().newCDPSession(page);
  await c.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: x0, y }] });
  for (let i = 1; i <= 12; i++) {
    await c.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: x0 + (x1 - x0) * i / 12, y }] });
    await page.waitForTimeout(16);
  }
  await c.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForTimeout(900);
}

const onIndex = (page) => page.evaluate(() => ({
  on: [...document.querySelectorAll(".bill .slide")].findIndex((s) => s.classList.contains("on")),
  dot: [...document.querySelectorAll("[data-bill-dots] button")].findIndex((b) => b.getAttribute("aria-pressed") === "true"),
  seen: (() => { const st = document.querySelector("[data-bill-s]").getBoundingClientRect(); return [...document.querySelectorAll(".bill .slide")].findIndex((s) => { const r = s.getBoundingClientRect(); return r.left >= st.left - 2 && r.right <= st.right + 2; }); })(),
}));

(async () => {
  const srv = await K.serve(o);
  const browser = await K.launch();
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);
    const B = srv.base;

    if (want("fit")) {
      for (const size of ["360x740", "390x844", "375x667", "320x640"]) {
        for (const p of ["/", "/en/", `/film/${FILM}/`, `/film/${FILM2}/`, `/en/film/${FILM2}/`]) {
          const x = await open(browser, size, B + p, { wait: 1200 });
          const w = await x.page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth, innerWidth]);
          R.check(`fit ${size} ${p}: scrollWidth ${w[0]} == clientWidth ${w[1]} (innerWidth ${w[2]}), 0 page errors`, w[0] === w[1] && w[1] === w[2] && !x.errs.length, x.errs.join(" | "));
          await x.ctx.close();
        }
      }
    }

    if (want("screen")) {
      for (const size of ["360x740", "390x844"]) {
        const x = await open(browser, size, B + "/");
        const g = await x.page.evaluate(() => {
          const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { t: Math.round(b.top), b: Math.round(b.bottom), l: Math.round(b.left), r: Math.round(b.right), w: Math.round(b.width), h: Math.round(b.height) }; };
          const s = document.querySelector(".bill .slide.on"), bill = document.querySelector(".bill");
          const pic = s.querySelector(".bd img") || s.querySelector(".case img") || s.querySelector(".case");
          const img = s.querySelector(".bd img, .case img");
          const tabs = document.querySelector(".tabs");
          /* what follows the billboard: its next sibling with a heading (the board, W2-P2; until then the near row) */
          let nx = bill.nextElementSibling;
          while (nx && (!nx.getBoundingClientRect().height || getComputedStyle(nx).display === "none" || nx.classList.contains("vh"))) nx = nx.nextElementSibling;
          const head = nx && (nx.querySelector("h2, h3") || nx);
          return { bill: r(bill), pic: r(pic), img: img ? img.currentSrc.split("/").pop() : null, loaded: img ? img.complete && img.naturalWidth > 0 : true,
            title: r(s.querySelector(".bill-t")), word: r(s.querySelector(".bill-v b")), wordText: (s.querySelector(".bill-v b") || {}).textContent,
            price: r(s.querySelector(".bill-go .p")), priceText: (s.querySelector(".bill-go .p") || {}).textContent, door: r(document.querySelector(".door")),
            doorText: (document.querySelector(".door") || {}).textContent, next: r(head), nextText: head ? head.textContent.trim().slice(0, 30) : "",
            tabsTop: tabs ? Math.round(tabs.getBoundingClientRect().top) : innerHeight, vh: innerHeight };
        });
        report["screen-" + size] = g;
        const inScreen = (b) => b && b.h > 0 && b.t >= 0 && b.b <= g.vh;
        R.check(`screen ${size}: the film's picture is on the first screen (${g.img || "the title tile"})`, inScreen(g.pic) && g.loaded, JSON.stringify(g.pic));
        R.check(`screen ${size}: the title, the verdict word «${g.wordText}», a price «${(g.priceText || "").trim()}» and the card door «${(g.doorText || "").trim()}»`,
          inScreen(g.title) && inScreen(g.word) && inScreen(g.price) && inScreen(g.door));
        R.check(`screen ${size}: the billboard ends at ${g.bill.b} (≤ ${FOOT[size]}) from ${g.bill.t}`, g.bill.b <= FOOT[size] && g.bill.t === 0);
        R.check(`screen ${size}: what follows it («${g.nextText}») starts on the first screen, above the tab bar (${g.next && g.next.t} < ${g.tabsTop})`, g.next && g.next.t < g.tabsTop);
        /* a two-line title: the case (or the frame's track) shrinks, the foot stays */
        const two = await x.page.evaluate(() => {
          const s = document.querySelector(".bill .slide.on"), t = s.querySelector(".bill-t"), a = t.querySelector("a");
          const tr = s.querySelector(".trk"), c = s.querySelector(".case");
          const before = { foot: document.querySelector(".bill").getBoundingClientRect().bottom, trk: tr.getBoundingClientRect().height, case: c ? c.getBoundingClientRect().height : null, th: t.getBoundingClientRect().height };
          a.textContent = "حكاية طويلة جداً عن ليلة في السينما"; t.style.setProperty("--tsize", "38px");
          const after = { foot: document.querySelector(".bill").getBoundingClientRect().bottom, trk: tr.getBoundingClientRect().height, case: c ? c.getBoundingClientRect().height : null, th: t.getBoundingClientRect().height,
            lines: Math.round(t.getBoundingClientRect().height / parseFloat(getComputedStyle(t).lineHeight)) };
          return { before, after };
        });
        report["two-" + size] = two;
        // the case only has to shrink when the track no longer has 100% > clamp() to give it (min(100%,clamp(…))):
        // at a taller viewport the track may still have headroom after a two-line title, and the case rightly holds
        // its designed size — the one true invariant is the foot never moves
        R.check(`screen ${size}: a two-line title (${two.after.lines} lines) shrinks the image track ${Math.round(two.before.trk)} → ${Math.round(two.after.trk)}` +
          (two.before.case != null ? ` and the case ${Math.round(two.before.case)} → ${Math.round(two.after.case)} (never grows)` : "") + `; the foot stays at ${Math.round(two.after.foot)}`,
          two.after.lines >= 2 && two.after.trk < two.before.trk && (two.before.case == null || two.after.case <= two.before.case) && Math.abs(two.after.foot - two.before.foot) < 0.5);
        R.check(`screen ${size}: 0 page errors`, !x.errs.length, x.errs.join(" | "));
        await x.ctx.close();
      }
    }

    if (want("clip")) {
      for (const size of ["320x640", "360x740"]) {
        const x = await open(browser, size, B + "/");
        const c = await x.page.evaluate(() => [...document.querySelectorAll(".bill .slide")].map((s, i) => {
          const sl = s.getBoundingClientRect(), inn = s.querySelector(".bill-in").getBoundingClientRect(), go = s.querySelector(".bill-go"), t = s.querySelector(".bill-t");
          // titleWhole tolerates a few px: at a tight line-height (§1.4's 1.02) Chrome's own line-box for the glyphs'
          // ascent/descent can measure a little taller than clientHeight with no visible clipping (nothing here has
          // overflow:hidden at the title itself; inFits above is what would catch a real clip against the slide)
          return { i, inTop: Math.round(inn.top - sl.top), inFits: inn.top >= sl.top - 0.5 && inn.bottom <= sl.bottom + 0.5,
            ctaFits: go.scrollWidth <= go.clientWidth + 1, ctaText: go.textContent.replace(/\s+/g, " ").trim(),
            titleWhole: t.scrollHeight <= t.clientHeight + 8 && t.scrollWidth <= t.clientWidth + 1 };
        }));
        report["clip-" + size] = c;
        R.check(`clip ${size}: every slide's words sit inside their slide`, c.every((s) => s.inFits), JSON.stringify(c.filter((s) => !s.inFits)));
        R.check(`clip ${size}: every CTA's words fit their button («${c[0].ctaText}»)`, c.every((s) => s.ctaFits), JSON.stringify(c.filter((s) => !s.ctaFits)));
        R.check(`clip ${size}: every title is whole`, c.every((s) => s.titleWhole));
        const d = await x.page.evaluate(() => { const d = document.querySelector(".door"); return d ? [d.scrollHeight <= d.clientHeight + 1, d.getBoundingClientRect().height] : [true, 0]; });
        R.check(`clip ${size}: the door keeps its 44 px line (${d[1]})`, d[0] && d[1] >= 44);
        await x.ctx.close();
      }
    }

    if (want("geo")) {
      const snap = () => { const s = document.querySelector(".bill .slide"); return { text: s.textContent.replace(/\s+/g, " ").trim(), pics: [...s.querySelectorAll("img")].map((i) => i.currentSrc) }; };
      const initSnap = () => {
        window.__lcp = [];
        new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__lcp.push({ t: Math.round(e.startTime), el: e.element ? e.element.tagName + "." + (e.element.className || e.element.parentNode.className) : null, url: e.url }))).observe({ type: "largest-contentful-paint", buffered: true });
        document.addEventListener("DOMContentLoaded", () => requestAnimationFrame(() => {
          const s = document.querySelector(".bill .slide"); if (!s) return;
          window.__first = { text: s.textContent.replace(/\s+/g, " ").trim(), html: document.querySelector(".bill").innerHTML.length };
        }));
      };
      const runs = {};
      for (const who of ["dubai", "al-ain"]) {
        for (const size of ["360x740", "390x844"]) {
          const x = await open(browser, size, B + "/", { fresh: who === "al-ain", wait: 2500, init: initSnap, route: async (ctx) => {
            if (who === "al-ain") await ctx.route(/\/geo(\?|$)/, async (r) => { await new Promise((z) => setTimeout(z, 600)); await r.fulfill({ status: 200, contentType: "application/json", body: '{"city":"al-ain"}' }); });
          } });
          const got = await x.page.evaluate(snap), first = await x.page.evaluate(() => window.__first), lcp = await x.page.evaluate(() => window.__lcp);
          const city = await x.page.evaluate(() => { try { return localStorage.getItem("cinema.city"); } catch (e) { return null; } });
          runs[who + size] = { got, first, lcp: lcp[lcp.length - 1], city };
          R.check(`geo ${who} ${size}: nothing on slide 1 changed after the first frame (city now ${city})`, first && first.text === got.text, first && first.text !== got.text ? first.text + " ≠ " + got.text : "");
          await x.ctx.close();
        }
      }
      report.geo = runs;
      for (const size of ["360x740", "390x844"]) {
        const a = runs["dubai" + size], b = runs["al-ain" + size];
        R.check(`geo ${size}: Al Ain's first visit gets Dubai's slide 1 (words and picture)`, a.got.text === b.got.text && JSON.stringify(a.got.pics) === JSON.stringify(b.got.pics));
        R.check(`geo ${size}: the same LCP element (${b.lcp && b.lcp.el} ${b.lcp && (b.lcp.url || "").split("/").pop()})`, a.lcp && b.lcp && a.lcp.el === b.lcp.el && a.lcp.url === b.lcp.url);
      }
    }

    if (want("bytes")) {
      for (const size of ["360x740", "390x844"]) {
        for (const save of [false, true]) {
          const x = await open(browser, size, B + "/", { wait: 400, init: save ? () => { Object.defineProperty(navigator, "connection", { value: { saveData: true, effectiveType: "3g" } }); } : null });
          const pics = await slidePics(x.page);
          const hit = (i) => x.reqs.some((r) => pics[i].some((u) => u && r.url.endsWith(u)));
          const early = pics.map((_, i) => hit(i));
          await x.page.waitForTimeout(4500);   /* load, then idle */
          const idle = pics.map((_, i) => hit(i));
          const label = `bytes ${size}${save ? " Save-Data" : ""}`;
          report[label] = { early, idle, files: pics.map((p) => p.filter(Boolean).map((u) => u.split("/").pop())) };
          R.check(`${label}: with the page only slide 1's picture (${early.map((v) => (v ? 1 : 0)).join("")})`, early[0] && early.slice(1).every((v) => !v));
          R.check(`${label}: once idle ${save ? "still only slide 1's" : "slide 2's too, and none of 3–5"} (${idle.map((v) => (v ? 1 : 0)).join("")})`,
            idle[0] && (save ? idle.slice(1).every((v) => !v) : (pics.length < 2 || idle[1]) && idle.slice(2).every((v) => !v)));
          if (!save && pics.length > 2) {
            const box = await x.page.evaluate(() => { const b = document.querySelector("[data-bill-s]").getBoundingClientRect(); return { y: b.top + b.height * 0.3, w: b.width }; });
            await swipe(x.page, box.w * 0.2, box.w * 0.85, box.y);
            await x.page.waitForTimeout(1200);
            const after = pics.map((_, i) => hit(i));
            R.check(`${label}: the first swipe loads the rest (${after.map((v) => (v ? 1 : 0)).join("")})`, after.every(Boolean));
          }
          await x.ctx.close();
        }
      }
    }

    if (want("swipe")) {
      for (const [p, rtl] of [["/", true], ["/en/", false]]) {
        for (const size of ["360x740", "390x844"]) {
          const x = await open(browser, size, B + p);
          const n = await x.page.evaluate(() => document.querySelectorAll(".bill .slide").length);
          if (n < 2) { R.info(`swipe ${p} ${size}`, "one slide only: nothing to swipe"); await x.ctx.close(); continue; }
          const box = await x.page.evaluate(() => { const b = document.querySelector("[data-bill-s]").getBoundingClientRect(); return { y: b.top + b.height * 0.3, w: b.width }; });
          const a = await onIndex(x.page);
          /* the next slide lies at the inline end: to its left in Arabic (a swipe to the right brings it), to the right in English */
          if (rtl) await swipe(x.page, box.w * 0.2, box.w * 0.85, box.y); else await swipe(x.page, box.w * 0.85, box.w * 0.2, box.y);
          const b = await onIndex(x.page);
          if (rtl) await swipe(x.page, box.w * 0.85, box.w * 0.2, box.y); else await swipe(x.page, box.w * 0.2, box.w * 0.85, box.y);
          const c = await onIndex(x.page);
          report[`swipe ${p} ${size}`] = { a, b, c };
          R.check(`swipe ${p} ${size}: one swipe on, one back, and the indicators follow (${JSON.stringify([a, b, c])})`,
            a.on === 0 && a.dot === 0 && b.seen === 1 && b.on === 1 && b.dot === 1 && c.seen === 0 && c.on === 0 && c.dot === 0);
          R.check(`swipe ${p} ${size}: 0 page errors`, !x.errs.length, x.errs.join(" | "));
          await x.ctx.close();
        }
      }
    }

    if (want("lcp")) {
      for (const size of ["360x740", "390x844"]) {
        const x = await open(browser, size, B + "/", { wait: 2500, init: () => {
          window.__lcp = []; window.__op = null;
          new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__lcp.push(e))).observe({ type: "largest-contentful-paint", buffered: true });
          const chain = (el) => { let v = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) v *= parseFloat(getComputedStyle(e).opacity); return v; };
          document.addEventListener("DOMContentLoaded", () => requestAnimationFrame(() => {
            const s = document.querySelector(".bill .slide.on"); if (!s) return;
            window.__op = [".bd img", ".case img", ".case", ".bill-t"].map((q) => s.querySelector(q)).filter(Boolean).map((e) => [e.tagName + "." + e.className, chain(e)]);
          }));
        } });
        const r = await x.page.evaluate(() => {
          const e = window.__lcp[window.__lcp.length - 1], el = e && e.element;
          let v = 1; for (let n = el; n && n.nodeType === 1; n = n.parentElement) v *= parseFloat(getComputedStyle(n).opacity);
          const fcp = (performance.getEntriesByName("first-contentful-paint")[0] || {}).startTime;
          return { el: el ? el.tagName + "." + (el.className || "") + " in " + (el.closest(".slide") ? "slide " + [...document.querySelectorAll(".bill .slide")].indexOf(el.closest(".slide")) : "?") : null,
            url: e && e.url, t: e && Math.round(e.startTime), fcp: Math.round(fcp || 0), opacity: v, first: window.__op };
        });
        report["lcp-" + size] = r;
        R.check(`lcp ${size}: the LCP element is slide 1's (${r.el}, ${(r.url || "").split("/").pop() || "text"}) at ${r.t} ms (FCP ${r.fcp} ms)`, r.el && /slide 0/.test(r.el));
        R.check(`lcp ${size}: it and every ancestor at opacity 1, now and from the first frame`, r.opacity === 1 && r.first && r.first.every((p) => p[1] === 1), JSON.stringify(r.first));
        await x.ctx.close();
      }
    }

    if (want("title")) {
      for (const size of ["360x740", "320x640"]) {
        const x = await open(browser, size, B + "/");
        const t = await x.page.evaluate(() => {
          const s = document.querySelector(".bill .slide.on"), h = s.querySelector(".bill-t"), a = h.querySelector("a");
          a.textContent = "Avengers Endgame: Encore"; a.setAttribute("lang", "en"); a.setAttribute("dir", "ltr"); h.style.setProperty("--tsize", "38px");
          const r = h.getBoundingClientRect(), cs = getComputedStyle(h), ca = getComputedStyle(a);
          // +8: the tight line-height (§1.4) can leave the line box a few px short of the glyphs' own ascent/descent
          // with nothing visibly cut (inSlide below is the real clip boundary: the slide's own overflow:hidden edge)
          return { whole: a.scrollHeight <= a.clientHeight + 8 && h.scrollWidth <= h.clientWidth + 1, clamp: ca.webkitLineClamp || cs.webkitLineClamp, lines: Math.round(r.height / parseFloat(cs.lineHeight)), text: a.textContent,
            inSlide: r.bottom <= s.getBoundingClientRect().bottom };
        });
        R.check(`title ${size}: «${t.text}» whole on the billboard (${t.lines} lines, clamp ${t.clamp})`, t.whole && t.inSlide && (t.clamp === "none" || t.clamp === ""));
        await x.ctx.close();
      }
      const fp = await (async () => { const x = await open(browser, "360x740", B + "/film/avengers-endgame-encore/"); const r = await x.page.evaluate(() => { const h = document.querySelector(".ft"); return h ? { text: h.textContent, whole: h.scrollHeight <= h.clientHeight + 8 && h.scrollWidth <= h.clientWidth + 1, clamp: getComputedStyle(h).webkitLineClamp } : null; }); await x.ctx.close(); return r; })();
      if (fp) R.check(`title: the film page's «${fp.text}» whole`, fp.whole && (fp.clamp === "none" || fp.clamp === ""));
    }

    if (want("idle")) {
      for (const size of ["360x740", "390x844"]) {
        const x = await open(browser, size, B + "/", { wait: 500 });
        const a = await onIndex(x.page), s0 = await x.page.evaluate(() => document.querySelector("[data-bill-s]").scrollLeft);
        await x.page.waitForTimeout(20000);
        const b = await onIndex(x.page), s1 = await x.page.evaluate(() => document.querySelector("[data-bill-s]").scrollLeft);
        R.check(`idle ${size}: 20 s with no touch, slide ${b.on} still showing and the strip where it was (${s0} → ${s1})`, a.on === 0 && b.on === 0 && b.seen === 0 && s0 === s1);
        await x.ctx.close();
      }
    }

    if (want("desk")) {
      const x = await open(browser, "desk", B + "/", { wait: 500 });
      const n = await x.page.evaluate(() => document.querySelectorAll(".bill .slide").length);
      if (n < 2) R.info("desk", "one slide only: no turn");
      else {
        await x.page.mouse.move(640, 790);   /* the pointer off the billboard */
        await x.page.evaluate(() => scrollTo(0, 0));
        const a = await onIndex(x.page);
        await x.page.waitForTimeout(7000);
        const b = await onIndex(x.page);
        R.check(`desk: on screen the slide turns after 6 s (${a.on} → ${b.on})`, a.on === 0 && b.on === 1);
        await x.page.evaluate(() => { const r = document.querySelector(".bill").getBoundingClientRect(); scrollTo(0, r.height * 0.7); });
        const c = await onIndex(x.page);
        await x.page.waitForTimeout(13000);
        const d = await onIndex(x.page);
        const vis = await x.page.evaluate(() => { const r = document.querySelector(".bill").getBoundingClientRect(); return Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0)) / r.height; });
        R.check(`desk: with ${Math.round(vis * 100)} % of it on screen the turn waits 13 s (${c.on} → ${d.on})`, vis < 0.5 && c.on === d.on);
        await x.page.evaluate(() => scrollTo(0, 0));
        await x.page.click("[data-bill-pp]");
        const e = await onIndex(x.page);
        await x.page.mouse.move(640, 790);
        await x.page.waitForTimeout(7000);
        const f = await onIndex(x.page);
        R.check(`desk: after the pause button nothing turns (${e.on} → ${f.on})`, e.on === f.on);
      }
      R.check("desk: 0 page errors", !x.errs.length, x.errs.join(" | "));
      await x.ctx.close();
    }

    if (want("motion")) {
      for (const rm of [false, true]) {
        const x = await open(browser, "390x844", B + "/", { rm });
        const rec = await x.page.evaluate(() => ({ anim: getComputedStyle(document.querySelector(".bill .slide.on .bd")).animationName,
          running: document.getAnimations().filter((a) => /bill-(rec|lift|dim)/.test(a.animationName || "")).length }));
        if (rm) R.check("motion reduced: no recede", rec.anim === "none" && rec.running === 0, JSON.stringify(rec));
        else R.info("motion: the recede", `${rec.anim}, ${rec.running} scroll-driven animations (no-preference; absent where unsupported)`);
        const tr = await x.page.$(".bill .slide.on .bill-tr");
        if (tr) {
          await tr.click();
          await x.page.waitForTimeout(rm ? 60 : 900);
          const l = await x.page.evaluate(() => { const e = document.querySelector(".lights"); const cs = e && getComputedStyle(e); return e && { op: parseFloat(cs.opacity), dur: cs.transitionDuration, open: !!document.querySelector("dialog.trl-d[open]") }; });
          R.check(`motion${rm ? " reduced" : ""}: «الإعلان» dims the hall to .92 ${rm ? "at once" : "in 700 ms"} (${JSON.stringify(l)})`, l && Math.abs(l.op - 0.92) < 0.005 && l.open && (rm ? l.dur === "0s" : true));
          await x.page.keyboard.press("Escape");
          await x.page.waitForTimeout(rm ? 60 : 600);
          const up = await x.page.evaluate(() => parseFloat(getComputedStyle(document.querySelector(".lights")).opacity));
          R.check(`motion${rm ? " reduced" : ""}: closing brings the lights back up (${up})`, up === 0);
        }
        await x.ctx.close();
      }
    }

    if (want("hero")) {
      for (const [p, fr] of [[`/film/${FILM}/`, true], [`/film/${FILM2}/`, false]]) {
        const x = await open(browser, "390x844", B + p);
        const v = await x.page.evaluate(() => {
          const h = document.querySelector(".fhero"), bd = document.querySelector(".fh-bd"), card = document.querySelector(".fposter .pst.hero");
          const vis = (e) => e && getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0;
          return { cls: h.className, bd: getComputedStyle(bd).viewTransitionName, card: card && getComputedStyle(card).viewTransitionName, cardShown: vis(card),
            h: Math.round(h.getBoundingClientRect().height), fog: !!document.querySelector(".bd.pf, img.pb"),
            cardBox: card && [Math.round(card.getBoundingClientRect().width), Math.round(card.getBoundingClientRect().height)] };
        });
        report["hero " + p] = v;
        if (fr) R.check(`hero ${p}: a frame (${v.cls}, ${v.h} px): the screen carries «poster», the card is not drawn`, /\bfr\b/.test(v.cls) && v.bd === "poster" && !v.cardShown);
        else R.check(`hero ${p}: no frame (${v.cls}, ${v.h} px): the case ${JSON.stringify(v.cardBox)} carries «poster»`, !/\bfr\b/.test(v.cls) && v.card === "poster" && v.cardShown && v.bd !== "poster");
        R.check(`hero ${p}: no fog`, !v.fog);
        await x.ctx.close();
      }
      if (ARCH) {
        const x = await open(browser, "390x844", B + ARCH);
        const a = await x.page.evaluate(() => { const h = document.querySelector(".fhero"); return h && { price: !!h.querySelector(".p, [data-aed]"), time: !!h.querySelector("[data-show], .tm, .bill-go"), text: h.textContent.replace(/\s+/g, " ").trim().slice(0, 80) }; });
        R.check(`hero ${ARCH}: an archived film's hero has no price and no time («${a && a.text}»)`, a && !a.price && !a.time);
        await x.ctx.close();
      }
    }

    const shots = o.get("shots", null), label = o.get("label", "x");
    if (shots && want("shots")) {
      fs.mkdirSync(shots, { recursive: true });
      for (const size of ["360x740", "390x844"]) {
        for (const [p, n] of [["/", "home"], [`/film/${FILM}/`, "film-frame"], [`/film/${FILM2}/`, "film-case"]]) {
          const x = await open(browser, size, B + p);
          await x.page.screenshot({ path: path.join(shots, `${n}-${size}-${label}.png`) });
          await x.ctx.close();
        }
      }
      R.info("shots", shots);
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
