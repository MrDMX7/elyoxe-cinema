#!/usr/bin/env node
/* W2-P5 · Chrome, doors and sheets, in Chrome (MASTER-PLAN §2.0, §5.3 W2-P5 acceptance, §5.0 #3).

     node tools/check_w2_p5.cjs --out out [--port 8125] [--name w2-p5] [--only a,b] [--size …]
     node tools/check_w2_p5.cjs --out DIR --shots DIR --tag before|after      (the report's screenshots only)

   Sections (every one asserts X-Served-By first, on this package's own port):
     fit      /, /en/, a film, a city, a cinema, /cinemas/, /cards/, the 404 at 360×740, 390×844, 375×667, 320×640:
              scrollWidth = clientWidth = innerWidth, no page error; at 320 the tab labels and the sheets' rows fit
     tabs     the bar hides after more than 12 px down, comes back after more than 12 px up, and at the top
     stub     a synthetic «stub» open hides the bar, «close» brings it back; --chrome-b follows
     retap    a tap on the tab of the page you are on scrolls it to the top, in place
     haptic   a vibrate spy: nothing on load, scroll or script events before a tap; one tick on choosing a card after it
     chips    the pressed chip's computed border and words are gold, its fill clear
     first    «قريب مني» and «بدون بطاقة» are the first rows, full width; counts and best numbers drawn
     drag     a touch drag of the city sheet: 1:1, the scrim fades, back under 30 %, closed past it, closed by a flick;
              focus back on the pill and the sheet's history entry gone
     detents  the filter sheet: opens at 60 %, «اعرض» at the screen's edge, holds; up to 92 % and holds; back to 60 %
     header   the header's night layer: clear at the top, solid past 56 px (at once under reduced motion); solid on a page
              with no screen
     shared   a friend's link with other settings: the «فتحت بإعدادات صاحبك» bar sits on the tab bar, then on the dock
     me       «قائمتي»: the sheet, its rows open their sheets, «امسح بياناتي» asks, then clears and Back leaves the page
     switch   where the browser has <input switch> (a shim here: Chrome has none), the prayer toggle becomes one and
              follows aria-checked
     prefetch drag.js arrives on a phone page left idle, with no tap; not on a desktop until a sheet opens
     reduced  under reduced motion: no sheet animation, a released sheet lands at once, the bar does not slide */
"use strict";
const fs = require("fs"), path = require("path");
const K = require("./pw_kit.cjs");

const PAGES = ["/", "/en/", "/film/heart-of-the-beast/", "/dubai/", "/dubai/reel-dubai-mall/", "/cinemas/", "/cards/", "/404.html"];
const wait = (p, ms) => p.waitForTimeout(ms);

async function open(browser, o, size, extra, init) {
  const ctx = await K.phone(browser, size, extra);
  await K.pinClock(ctx, K.pinned(o));
  if (init) await ctx.addInitScript(init);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push(String(e)));
  return { ctx, page };
}
async function go(page, url) { await page.goto(url, { waitUntil: "load" }); await wait(page, 700); }
async function frame(page) { await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))); }
async function scrollTo(page, y) { await page.evaluate((y) => scrollTo(0, y), y); await frame(page); await wait(page, 60); }
async function tabsState(page) {
  return page.evaluate(() => { const t = document.querySelector(".tabs"), r = t.getBoundingClientRect();
    return { away: document.documentElement.classList.contains("tabs-away"), top: Math.round(r.top), vh: innerHeight, b: getComputedStyle(document.documentElement).getPropertyValue("--chrome-b").trim() }; });
}
async function sheetBox(page, id) {
  return page.evaluate((id) => { const s = document.getElementById(id); if (!s) return null; const r = s.getBoundingClientRect(), m = /matrix\(.*?,\s*(-?[\d.]+)\)/.exec(getComputedStyle(s).transform);
    return { hidden: s.hidden, top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height), ty: m ? +(+m[1]).toFixed(1) : 0, vh: innerHeight,
      scrim: getComputedStyle(document.querySelector("[data-sheet-scrim]")).opacity }; }, id);
}
async function dragReady(page) {
  for (let i = 0; i < 40; i++) { if (await page.evaluate(() => !!document.querySelector('script[src*="/assets/drag."]'))) break; await wait(page, 100); }
  await wait(page, 300);
}
/* a real touch drag (CDP): pointer events of type touch, as a thumb makes them */
async function touchDrag(page, x, y0, dy, stepPx, stepMs, mid) {
  const s = await page.context().newCDPSession(page);
  await s.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: y0 }] });
  const n = Math.max(1, Math.ceil(Math.abs(dy) / stepPx)); let y = y0, seen = null;
  for (let i = 1; i <= n; i++) {
    y = y0 + (i === n ? dy : Math.sign(dy) * stepPx * i);
    await wait(page, stepMs);
    await s.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y }] });
    if (mid && i === Math.floor(n / 2)) { await frame(page); seen = { dy: y - y0, box: await mid() }; }
  }
  await s.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await s.detach();
  return seen;
}
async function headXY(page, id) {
  return page.evaluate((id) => { const r = document.querySelector("#" + id + " .sheet-t").getBoundingClientRect(); return [Math.round(r.left + r.width / 2), Math.round(r.top + 10)]; }, id);
}
async function tapPill(page, id) { await page.tap("#" + id); await wait(page, 450); }

const SECTIONS = {
  async fit(ctx0, R, browser, o, srv) {
    for (const size of ["360x740", "390x844", "375x667", "320x640"]) {
      const { ctx, page } = await open(browser, o, size);
      for (const u of PAGES) {
        await go(page, srv.base + u);
        const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, iw: innerWidth }));
        R.check(`fit ${size} ${u}: scrollWidth = clientWidth = innerWidth`, m.sw === m.cw && m.cw === m.iw, JSON.stringify(m));
      }
      if (size === "320x640") {
        await go(page, srv.base + "/");
        const tabs = await page.evaluate(() => [...document.querySelectorAll(".tabs a")].filter((a) => a.offsetWidth).map((a) => {
          const s = a.querySelector("span"); return { t: s.textContent, fit: s.scrollWidth <= s.clientWidth + 0.5 && a.scrollHeight <= a.clientHeight + 0.5, h: a.offsetHeight }; }));
        R.check("fit 320: the four tab labels fit their tabs (60 px, no clipping)", tabs.length === 4 && tabs.every((x) => x.fit && x.h >= 60), JSON.stringify(tabs));
        for (const [pill, id] of [["pill-city", "sheet-city"], ["pill-card", "sheet-card"], [null, "sheet-me"]]) {
          if (pill) await tapPill(page, pill); else { await page.tap(".tabs [data-me-tab]"); await wait(page, 450); }
          const m = await page.evaluate((id) => { const s = document.getElementById(id); const rows = [...s.querySelectorAll(".opt")].filter((e) => e.offsetWidth);
            return { sw: s.scrollWidth, cw: s.clientWidth, clipped: rows.filter((e) => e.scrollWidth > e.clientWidth + 0.5).map((e) => e.textContent.trim()) }; }, id);
          R.check(`fit 320: ${id} has no sideways scroll and no clipped row`, m.sw <= m.cw && !m.clipped.length, JSON.stringify(m));
          await page.keyboard.press("Escape"); await wait(page, 300);
        }
      }
      R.check(`fit ${size}: no page error`, !page.errs.length, page.errs.join(" | "));
      await ctx.close();
    }
  },

  async tabs(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size);
      await go(page, srv.base + "/");
      const seq = [];
      for (const y of [12, 25, 14, 12, 0]) { await scrollTo(page, y); await wait(page, 300); seq.push([y, (await tabsState(page)).away]); }
      const s = await tabsState(page);
      R.check(`tabs ${size}: 12 px down keeps the bar, 25 hides it, 11 up keeps it hidden, 13 up and the top bring it back`,
        JSON.stringify(seq.map((x) => x[1])) === "[false,true,true,false,false]", JSON.stringify(seq));
      await scrollTo(page, 300); await wait(page, 350);
      const down = await tabsState(page);
      R.check(`tabs ${size}: hidden means out of the screen (top ${down.top} ≥ ${down.vh}), --chrome-b 0`, down.away && down.top >= down.vh - 1 && down.b === "0px", JSON.stringify(down));
      await scrollTo(page, 280); await wait(page, 350);
      const up = await tabsState(page);
      R.check(`tabs ${size}: back on the way up, --chrome-b = the bar's height`, !up.away && up.top < up.vh && parseFloat(up.b) >= 60, JSON.stringify(up));
      R.check(`tabs ${size}: no page error`, !page.errs.length, page.errs.join(" | "));
      await ctx.close();
    }
  },

  async stub(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size);
      await go(page, srv.base + "/film/heart-of-the-beast/");
      await page.evaluate(() => window.CINEMA.emit("stub", "open")); await wait(page, 350);
      const a = await tabsState(page);
      await page.evaluate(() => window.CINEMA.emit("stub", "close")); await wait(page, 350);
      const b = await tabsState(page);
      R.check(`stub ${size}: a «stub» open hides the bar (one bottom bar at a time), «close» brings it back`,
        a.away && a.top >= a.vh - 1 && !b.away && b.top < b.vh, JSON.stringify({ open: a, close: b }));
      await ctx.close();
    }
  },

  async retap(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size);
      await go(page, srv.base + "/");
      await page.evaluate(() => { window.__same = 1; });
      await scrollTo(page, 1500); await scrollTo(page, 1400); await wait(page, 300);   /* up a little: the bar is back */
      await page.tap('.tabs a[aria-current="page"]'); await wait(page, 1200);
      const m = await page.evaluate(() => ({ y: scrollY, same: window.__same === 1, url: location.pathname + location.hash }));
      R.check(`retap ${size}: «الرئيسية» on home scrolls it to the top, in place`, m.y < 2 && m.same && m.url === "/", JSON.stringify(m));
      await ctx.close();
    }
  },

  async haptic(ctx0, R, browser, o, srv) {
    const spy = () => { const f = (...a) => { (window.__vib = window.__vib || []).push(a); return true; }; try { Object.defineProperty(Navigator.prototype, "vibrate", { value: f, configurable: true }); } catch (e) {} };
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size, {}, spy);
      await go(page, srv.base + "/");
      const s = await page.context().newCDPSession(page);   /* a touch scroll is not an activation */
      await s.send("Input.synthesizeScrollGesture", { x: 180, y: 500, yDistance: -600, speed: 1200, gestureSourceType: "touch" }); await s.detach();
      await page.evaluate(() => { ["card", "plan", "save", "detent"].forEach((e) => window.CINEMA.emit(e, 1)); window.CINEMA.emit("stub", "open"); window.CINEMA.emit("stub", "close"); });
      const before = await page.evaluate(() => ({ n: (window.__vib || []).length, active: navigator.userActivation.hasBeenActive }));
      await scrollTo(page, 0);
      await tapPill(page, "pill-card");
      await page.tap('#sheet-card button[data-card="fazaa"]'); await wait(page, 400);
      const after = await page.evaluate(() => ({ vib: window.__vib || [], active: navigator.userActivation.hasBeenActive }));
      /* Chrome counts the touch scroll as a user activation (before.active): the gate is a tap, not the activation */
      R.check(`haptic ${size}: no vibrate on load, a touch scroll or five hook events before a tap`, before.n === 0, JSON.stringify(before));
      R.check(`haptic ${size}: choosing a card after a tap: one 8 ms tick`, JSON.stringify(after.vib) === "[[8]]" && after.active, JSON.stringify(after));
      await ctx.close();
    }
  },

  async chips(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size);
      await go(page, srv.base + "/");
      const gold = await page.evaluate(() => { const p = document.createElement("i"); p.style.color = "var(--gold)"; document.body.appendChild(p); const c = getComputedStyle(p).color; p.remove(); return c; });
      await tapPill(page, "pill-card");
      const look = (sel) => page.evaluate((sel) => { const e = document.querySelector(sel), s = getComputedStyle(e); return { border: s.borderTopColor, color: s.color, bg: s.backgroundColor, pressed: e.getAttribute("aria-pressed") }; }, sel);
      const none = await look('#sheet-card button[data-card=""]');
      await page.tap('#sheet-card button[data-card="fazaa"]'); await wait(page, 400);
      await tapPill(page, "pill-card");
      const fz = await look('#sheet-card button[data-card="fazaa"]'), nc = await look('#sheet-card button[data-card=""]');
      const clear = (bg) => bg === "rgba(0, 0, 0, 0)" || bg === "transparent";
      R.check(`chips ${size}: the chosen chip is a gold outline with gold words, never a white fill`,
        none.pressed === "true" && none.border === gold && none.color === gold && clear(none.bg) && fz.pressed === "true" && fz.border === gold && clear(fz.bg) && nc.border !== gold,
        JSON.stringify({ gold, none, fazaa: fz, nocardAfter: nc }));
      await ctx.close();
    }
  },

  async first(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size);
      await go(page, srv.base + "/");
      const row = (id) => page.evaluate((id) => { const s = document.getElementById(id), b = s.querySelector(".sheet-b"), opts = [...b.querySelectorAll(".opt")].filter((e) => e.offsetWidth);
        const f = opts[0], sec = f.closest(".sec"), top = Math.min(...opts.map((e) => e.getBoundingClientRect().top));
        return { first: f.textContent.trim(), w: Math.round(f.getBoundingClientRect().width), secW: Math.round(sec.getBoundingClientRect().width), isTop: f.getBoundingClientRect().top === top,
          counts: [...b.querySelectorAll(".opt .n")].map((e) => e.closest(".opt").textContent.trim()).slice(0, 3),
          best: [...b.querySelectorAll(".opt .best")].slice(0, 3).map((e) => [e.closest(".opt").textContent.trim(), getComputedStyle(e).color]) }; }, id);
      await tapPill(page, "pill-city");
      const c = await row("sheet-city");
      await page.keyboard.press("Escape"); await wait(page, 300);
      await tapPill(page, "pill-card");
      const k = await row("sheet-card");
      R.check(`first ${size}: the city sheet's first row is «قريب مني», full width, on top; cities carry counts`,
        c.first === "قريب مني" && c.w === c.secW && c.isTop && c.counts.length === 3 && /\d+ سينما|سينمات|سينمتين/.test(c.counts.join()), JSON.stringify(c));
      R.check(`first ${size}: the card sheet's first row is «بدون بطاقة», full width; cards carry their best number`,
        k.first === "بدون بطاقة" && k.w === k.secW && k.isTop && k.best.length === 3, JSON.stringify(k));
      await ctx.close();
    }
  },

  async drag(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size);
      await go(page, srv.base + "/");
      await tapPill(page, "pill-city"); await dragReady(page);
      const b0 = await sheetBox(page, "sheet-city"), [x, y] = await headXY(page, "sheet-city");
      const h = b0.h, small = Math.round(h * 0.2), big = Math.round(h * 0.4);
      const mid = await touchDrag(page, x, y, small, 4, 20, () => sheetBox(page, "sheet-city"));
      await wait(page, 500);
      const b1 = await sheetBox(page, "sheet-city");
      R.check(`drag ${size}: the sheet follows the finger 1:1 and the scrim fades (moved ${mid.dy} px, sheet at ${mid.box.ty})`,
        Math.abs(mid.box.ty - mid.dy) <= 2 && +mid.box.scrim < 1, JSON.stringify(mid));
      R.check(`drag ${size}: released under 30 % (${small} of ${h} px) it returns and stays open`, !b1.hidden && Math.abs(b1.ty) < 1 && b1.top === b0.top, JSON.stringify({ b0, b1 }));
      await touchDrag(page, x, y, big, 4, 20); await wait(page, 600);
      const b2 = await sheetBox(page, "sheet-city");
      const after = await page.evaluate(() => ({ focus: document.activeElement && document.activeElement.id, state: history.state, open: document.documentElement.classList.contains("sheet-open") }));
      R.check(`drag ${size}: released past 30 % (${big} of ${h} px) it closes; focus back on the pill, the sheet's history entry gone`,
        b2.hidden && after.focus === "pill-city" && !(after.state && after.state.sheet) && !after.open, JSON.stringify({ b2, after }));
      await tapPill(page, "pill-city"); await wait(page, 200);
      /* a flick: 90 px in three moves as fast as CDP sends them (~35 ms apart, ~0.9 px/ms; a thumb's 60–120 Hz is faster) */
      const fl = await page.evaluate(() => { window.__mv = []; document.addEventListener("pointermove", (e) => window.__mv.push([e.timeStamp, e.clientY]), true); return 1; });
      await touchDrag(page, x, y, 90, 30, 0); await wait(page, 600);
      const b3 = await sheetBox(page, "sheet-city"), mv = await page.evaluate(() => window.__mv);
      const v = mv.length > 1 ? (mv[mv.length - 1][1] - mv[0][1]) / (mv[mv.length - 1][0] - mv[0][0]) : 0;
      R.check(`drag ${size}: a flick closes it short of 30 % (90 of ${h} px at ${v.toFixed(2)} px/ms)`, fl && b3.hidden && 90 / h < 0.3 && v > 0.5, JSON.stringify(b3));
      R.check(`drag ${size}: no page error`, !page.errs.length, page.errs.join(" | "));
      await ctx.close();
    }
  },

  async detents(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size);
      await go(page, srv.base + "/");
      await page.evaluate(() => document.querySelector('[data-sheet-open="sheet-filter"]').scrollIntoView({ block: "center" })); await wait(page, 300);
      await page.tap('[data-sheet-open="sheet-filter"]'); await dragReady(page); await wait(page, 400);
      const go_ = () => page.evaluate(() => { const g = document.querySelector("#sheet-filter .go button.main"), r = g.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight }; });
      const a = await sheetBox(page, "sheet-filter"), ga = await go_();
      await wait(page, 1000);
      const a2 = await sheetBox(page, "sheet-filter");
      R.check(`detents ${size}: opens at 60 % (top ${a.top} ≈ ${Math.round(a.vh * 0.4)}), and holds a second later`,
        Math.abs(a.top - a.vh * 0.4) <= 2 && a2.top === a.top, JSON.stringify({ a, a2 }));
      R.check(`detents ${size}: «اعرض» sits at the screen's edge, in reach`, ga.bottom <= ga.vh && ga.bottom >= ga.vh - 24 && ga.top > a.top, JSON.stringify(ga));
      const [x, y] = await headXY(page, "sheet-filter");
      await touchDrag(page, x, y, -Math.round(a.vh * 0.28), 4, 20); await wait(page, 500);
      const b = await sheetBox(page, "sheet-filter"); await wait(page, 1000);
      const b2 = await sheetBox(page, "sheet-filter"), gb = await go_();
      R.check(`detents ${size}: dragged up it stops at 92 % (top ${b.top} ≈ ${Math.round(b.vh * 0.08)}) and holds`,
        Math.abs(b.top - b.vh * 0.08) <= 2 && b2.top === b.top && gb.bottom <= gb.vh, JSON.stringify({ b, b2, gb }));
      const [x2, y2] = await headXY(page, "sheet-filter");
      await touchDrag(page, x2, y2, Math.round(b.vh * 0.25), 4, 20); await wait(page, 500);
      const c = await sheetBox(page, "sheet-filter");
      R.check(`detents ${size}: dragged down part-way it settles back at 60 %`, !c.hidden && Math.abs(c.top - c.vh * 0.4) <= 2, JSON.stringify(c));
      R.check(`detents ${size}: no page error`, !page.errs.length, page.errs.join(" | "));
      await ctx.close();
    }
  },

  async header(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      for (const reduce of [false, true]) {
        const { ctx, page } = await open(browser, o, size, reduce ? { reducedMotion: "reduce" } : {});
        await go(page, srv.base + "/");
        const op = async (y) => { await scrollTo(page, y); await wait(page, 120); return page.evaluate(() => +getComputedStyle(document.querySelector(".top"), "::before").opacity); };
        const v = [await op(0), await op(28), await op(80)];
        const ok = reduce ? v[0] === 0 && v[1] === 0 && v[2] === 1 : v[0] === 0 && v[1] > 0.2 && v[1] < 0.8 && v[2] === 1;
        R.check(`header ${size}${reduce ? " reduced motion" : ""}: the night layer at 0, 28 and 80 px: ${v.map((x) => x.toFixed(2)).join(", ")}`, ok, JSON.stringify(v));
        if (!reduce) {
          await go(page, srv.base + "/cards/");
          const bg = await page.evaluate(() => [getComputedStyle(document.querySelector(".top")).backgroundColor, getComputedStyle(document.querySelector(".top"), "::before").content]);
          R.check(`header ${size}: a page with no screen keeps the solid night header`, bg[0] === "rgb(15, 11, 12)" && bg[1] === "none", JSON.stringify(bg));
        }
        await ctx.close();
      }
    }
  },

  async shared(ctx0, R, browser, o, srv) {
    const seed = () => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem("cinema.city", "dubai"); localStorage.setItem("cinema.card", "fazaa"); sessionStorage.setItem("seeded", "1"); } };
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size, {}, seed);
      await go(page, srv.base + "/film/heart-of-the-beast/?city=sharjah&card=esaad");
      const m = () => page.evaluate(() => { const r = (s) => { const e = document.querySelector(s); return e && e.offsetHeight ? e.getBoundingClientRect() : null; }, b = r(".shareask"), t = r(".tabs"), d = r("[data-dock]");
        return { bar: b && [Math.round(b.top), Math.round(b.bottom)], tabs: t && Math.round(t.top), dock: d && Math.round(d.top) }; });
      const a = await m();
      R.check(`shared ${size}: the friend's-settings bar sits on the tab bar`, a.bar && a.tabs != null && a.bar[1] <= a.tabs + 0.5, JSON.stringify(a));
      const tm = page.locator(".cgs .tm:not(.past):visible").first();
      if (await tm.count()) {
        await tm.scrollIntoViewIfNeeded(); await tm.tap(); await wait(page, 900);
        const b = await m();
        R.check(`shared ${size}: with a time chosen, the bar sits on the dock, not under it`, b.bar && b.dock != null && b.bar[1] <= b.dock + 0.5, JSON.stringify(b));
        if (o.shotsDir) await page.screenshot({ path: path.join(o.shotsDir, `shared-dock-${size}-${o.tag}.png`) });
      } else R.check(`shared ${size}: a time to choose`, false, "no upcoming time on the film page");
      await ctx.close();
    }
  },

  async me(ctx0, R, browser, o, srv) {
    const seed = () => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem("cinema.card", "fazaa"); localStorage.setItem("cinema.loc", "25.2,55.3," + Date.now()); localStorage.setItem("x.other", "1"); sessionStorage.setItem("seeded", "1"); } };
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size, {}, seed);
      await go(page, srv.base + "/cards/");
      await page.tap('.tabs a[href="/"]'); await page.waitForLoadState("load"); await wait(page, 800);
      await page.tap(".tabs [data-me-tab]"); await wait(page, 450);
      const s = await page.evaluate(() => { const e = document.getElementById("sheet-me"); return { open: !e.hidden, card: e.querySelector("[data-me-card]").textContent, city: e.querySelector("[data-city-name]").textContent, url: location.pathname + location.hash }; });
      R.check(`me ${size}: «قائمتي» opens its sheet, saying the city and the card this phone keeps`, s.open && s.card === "فزعة" && s.city === "دبي" && s.url === "/", JSON.stringify(s));
      await page.tap('#sheet-me [data-sheet-open="sheet-city"]'); await wait(page, 400);
      const sw = await page.evaluate(() => [document.getElementById("sheet-me").hidden, document.getElementById("sheet-city").hidden]);
      R.check(`me ${size}: «مدينتك» opens the city sheet in its place`, sw[0] && !sw[1], JSON.stringify(sw));
      await page.keyboard.press("Escape"); await wait(page, 300);
      await page.tap(".tabs [data-me-tab]"); await wait(page, 450);
      await page.tap("#sheet-me [data-me-clear]"); await wait(page, 200);
      const ask = await page.evaluate(() => [document.querySelector("#sheet-me [data-me-clear]").textContent, localStorage.getItem("cinema.card")]);
      R.check(`me ${size}: the first tap on «امسح بياناتي» only asks`, ask[0] === "متأكد؟ اضغط مرة ثانية" && ask[1] === "fazaa", JSON.stringify(ask));
      await Promise.all([page.waitForEvent("load"), page.tap("#sheet-me [data-me-clear]")]); await wait(page, 600);
      const gone = await page.evaluate(() => ({ keys: Object.keys(localStorage).filter((k) => k.indexOf("cinema.") === 0), other: localStorage.getItem("x.other"), url: location.pathname }));
      R.check(`me ${size}: the second clears every «cinema.» key (nothing else) and loads the page again`, gone.keys.length === 0 && gone.other === "1" && gone.url === "/", JSON.stringify(gone));
      await page.goBack({ waitUntil: "load" }); await wait(page, 400);
      R.check(`me ${size}: Back then leaves for the page before (not this page again)`, (await page.evaluate(() => location.pathname)) === "/cards/", await page.evaluate(() => location.pathname));
      R.check(`me ${size}: no page error`, !page.errs.length, page.errs.join(" | "));
      await ctx.close();
    }
  },

  async switch(ctx0, R, browser, o, srv) {
    const shim = () => { Object.defineProperty(HTMLInputElement.prototype, "switch", { get() { return this.hasAttribute("switch"); }, set(v) { this.toggleAttribute("switch", !!v); }, configurable: true }); };
    const size = o.sizes[0];
    const { ctx, page } = await open(browser, o, size, {}, shim);
    await go(page, srv.base + "/");
    await page.evaluate(() => document.querySelector('[data-sheet-open="sheet-filter"]').scrollIntoView({ block: "center" })); await wait(page, 300);
    await page.tap('[data-sheet-open="sheet-filter"]'); await dragReady(page); await wait(page, 300);
    const q = () => page.evaluate(() => { const e = document.querySelector("#sheet-filter [data-prayer]"); return { tag: e.tagName, type: e.type, sw: e.hasAttribute("switch"), role: e.getAttribute("role"), checked: e.checked, aria: e.getAttribute("aria-checked"), label: e.getAttribute("aria-labelledby") }; });
    const a = await q();
    await page.evaluate(() => document.querySelector("#sheet-filter [data-prayer]").scrollIntoView({ block: "center" })); await wait(page, 200);
    await page.tap("#sheet-filter [data-prayer]"); await wait(page, 700);
    const b = await q();
    R.check(`switch ${size}: the prayer toggle becomes <input type=checkbox switch> (a shim stands in for Safari's)`, a.tag === "INPUT" && a.type === "checkbox" && a.sw && a.role === "switch" && a.label, JSON.stringify(a));
    R.check(`switch ${size}: tapped, it turns on and its checked state follows aria-checked`, b.aria === "true" && b.checked === true, JSON.stringify(b));
    const plain = await open(browser, o, size);
    await go(plain.page, srv.base + "/");
    await plain.page.evaluate(() => document.querySelector('[data-sheet-open="sheet-filter"]').scrollIntoView({ block: "center" })); await wait(plain.page, 300);
    await plain.page.tap('[data-sheet-open="sheet-filter"]'); await dragReady(plain.page);
    const c = await plain.page.evaluate(() => document.querySelector("#sheet-filter [data-prayer]").tagName);
    R.check(`switch ${size}: in Chrome (no <input switch>) the toggle stays the drawn button`, c === "BUTTON", c);
    await plain.ctx.close(); await ctx.close();
  },

  async prefetch(ctx0, R, browser, o, srv) {
    const size = o.sizes[0];
    const { ctx, page } = await open(browser, o, size);
    const got = []; page.on("request", (r) => { if (/\/assets\/drag\./.test(r.url())) got.push(r.url()); });
    await go(page, srv.base + "/"); await wait(page, 5000);
    R.check(`prefetch ${size}: drag.js arrives while the phone page is idle, with no tap`, got.length === 1, JSON.stringify(got));
    await ctx.close();
    const dctx = await browser.newContext({ viewport: { width: 1280, height: 800 } }); await K.pinClock(dctx, K.pinned(o));
    const dp = await dctx.newPage(); const dg = []; dp.on("request", (r) => { if (/\/assets\/drag\./.test(r.url())) dg.push(r.url()); });
    await dp.goto(srv.base + "/", { waitUntil: "load" }); await wait(dp, 5000);
    const idle = dg.length;
    await dp.click("#pill-city"); await wait(dp, 800);
    R.check("prefetch desktop: not on idle; at the first sheet (for the switches)", idle === 0 && dg.length === 1, JSON.stringify({ idle, after: dg.length }));
    await dctx.close();
  },

  async reduced(ctx0, R, browser, o, srv) {
    for (const size of o.sizes) {
      const { ctx, page } = await open(browser, o, size, { reducedMotion: "reduce" });
      await go(page, srv.base + "/");
      await tapPill(page, "pill-city"); await dragReady(page);
      const anim = await page.evaluate(() => [getComputedStyle(document.getElementById("sheet-city")).animationName, getComputedStyle(document.querySelector("[data-sheet-scrim]")).animationName]);
      const [x, y] = await headXY(page, "sheet-city"), h = (await sheetBox(page, "sheet-city")).h;
      await touchDrag(page, x, y, Math.round(h * 0.2), 4, 20); await wait(page, 40);
      const land = await page.evaluate(() => { const s = document.getElementById("sheet-city"); return [getComputedStyle(s).transitionDuration, document.getAnimations().filter((a) => a.effect && a.effect.target === s).length]; });
      const b = await sheetBox(page, "sheet-city");
      await page.keyboard.press("Escape"); await wait(page, 200);
      const tr = await page.evaluate(() => getComputedStyle(document.querySelector(".tabs")).transitionDuration);
      R.check(`reduced ${size}: no sheet or scrim animation, a released sheet lands at once, the bar does not slide`,
        anim.every((a) => a === "none") && land[0].split(",").every((d) => parseFloat(d) === 0) && land[1] === 0 && Math.abs(b.ty) < 1 && tr === "0s", JSON.stringify({ anim, land, ty: b.ty, tr }));
      await ctx.close();
    }
  },
};

/* the report's screenshots: the same states on any build (before = legend, after = this package) */
async function shots(browser, o, srv) {
  fs.mkdirSync(o.shotsDir, { recursive: true });
  const seed = () => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem("cinema.city", "dubai"); localStorage.setItem("cinema.card", "fazaa"); sessionStorage.setItem("seeded", "1"); } };
  for (const size of ["360x740", "390x844"]) {
    const shot = async (page, name) => { await page.screenshot({ path: path.join(o.shotsDir, `${name}-${size}-${o.tag}.png`) }); };
    let { ctx, page } = await open(browser, o, size);
    await go(page, srv.base + "/"); await shot(page, "home");
    await scrollTo(page, 300); await scrollTo(page, 700); await wait(page, 500); await shot(page, "home-scrolled");
    await scrollTo(page, 0); await wait(page, 400);
    await tapPill(page, "pill-city"); await wait(page, 400); await shot(page, "sheet-city"); await page.keyboard.press("Escape"); await wait(page, 300);
    await tapPill(page, "pill-card"); await wait(page, 400); await shot(page, "sheet-card"); await page.keyboard.press("Escape"); await wait(page, 300);
    await page.evaluate(() => document.querySelector('[data-sheet-open="sheet-filter"]').scrollIntoView({ block: "center" })); await wait(page, 300);
    await page.tap('[data-sheet-open="sheet-filter"]'); await wait(page, 1500); await shot(page, "sheet-filter"); await page.keyboard.press("Escape"); await wait(page, 300);
    await scrollTo(page, 0); await wait(page, 400);
    const me = page.locator(".tabs [data-me-tab]");
    if (await me.count()) { await me.tap(); await wait(page, 500); await shot(page, "sheet-me"); }
    await ctx.close();
    ({ ctx, page } = await open(browser, o, size, {}, seed));
    await go(page, srv.base + "/film/heart-of-the-beast/?city=sharjah&card=esaad"); await wait(page, 300);
    const tm = page.locator(".cgs .tm:not(.past):visible").first();
    if (await tm.count()) { await tm.scrollIntoViewIfNeeded(); await tm.tap(); await wait(page, 900); }
    await shot(page, "shared-dock");
    await ctx.close();
  }
}

(async () => {
  const o = K.args(null, {});
  o.port = +o.get("port", 8125); o.name = o.get("name", "w2-p5");
  o.shotsDir = o.get("shots", null); o.tag = o.get("tag", "after");
  const only = o.get("only", null), R = K.results();
  const srv = await K.serve(o), browser = await K.launch();
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);
    if (o.shotsDir && !only) await shots(browser, o, srv);
    else for (const [name, fn] of Object.entries(SECTIONS)) {
      if (only && !only.split(",").includes(name)) continue;
      try { await fn(null, R, browser, o, srv); } catch (e) { R.check(name + " ran", false, e.stack.split("\n").slice(0, 3).join(" | ")); }
    }
  } catch (e) {
    R.check("run", false, e.message);
  } finally {
    await browser.close(); srv.stop();
  }
  const jf = o.get("json", null);
  if (jf) fs.writeFileSync(jf, JSON.stringify(R.list, null, 1));
  process.exit(R.code());
})();
