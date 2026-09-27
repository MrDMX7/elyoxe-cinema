// Film page behaviour checks (UI redesign Task 4): the day bar, a time → the dock → the ticket sheet (phone) or the
// side column (desktop), the empty state, the tabs (keyboard, #hash, the hero's «قارن»), the verdict's «المزيد»,
// the «⋯» sheet, a city change, the card reprice, no duplicate ids, no sideways scroll, and the page with no script;
// fix round 1: a malformed #hash, the clock (a chosen show starting, the desktop's next show), «المزيد»'s overlay,
// the price-note marker, «N سينمات ثانية» kept open, the network-city note, the ticket column at 1280×720.
// usage: node tools/film_check.cjs <base url, e.g. http://127.0.0.1:8871> <film path, e.g. film/heart-of-the-beast/> [now]
// PLAYWRIGHT: where the playwright package is (default: the Elyoxe site's node_modules on this laptop)
const { chromium } = require(process.env.PLAYWRIGHT || "C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");
(async () => {
  const [base, path0, now] = process.argv.slice(2);
  const path = "/" + String(path0).replace(/^\/+/, "");   // "film/x/" works too (Git Bash rewrites a leading "/")
  const qs = now ? "?now=" + now : "";
  const url = base + path + qs;
  const b = await chromium.launch({ channel: "chrome" });
  const out = [], errors = [];
  const ok = (name, cond, extra) => out.push((cond ? "PASS " : "FAIL ") + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  const skip = (name, why) => out.push("SKIP " + name + "  " + why);
  const phone = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
  const desk = { viewport: { width: 1440, height: 900 } };
  const open = async (opts, u) => {
    const p = await b.newPage(opts);
    p.on("pageerror", e => errors.push(String(e)));
    await p.goto(u || url, { waitUntil: "networkidle" });
    await p.waitForTimeout(600);
    return p;
  };
  const dupIds = p => p.evaluate(() => { const c = {}; document.querySelectorAll("[id]").forEach(e => c[e.id] = (c[e.id] || 0) + 1); return Object.keys(c).filter(k => c[k] > 1); });
  const firstFree = ".fcity.here > .cg:not(.more-h) .times[data-d]:not([hidden]) .tm[data-start]:not(.past):not(.x)";
  const hasTimes = async p => !!(await p.$(firstFree));

  // ---------------------------------------------------------------- phone
  let p = await open(phone);
  ok("phone: no duplicate ids", (await dupIds(p)).length === 0, await dupIds(p));
  const w390 = await p.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
  ok("phone 390: scrollWidth == innerWidth", w390[0] === w390[1], w390);
  const dockHidden0 = await p.$eval("[data-dock]", d => d.hidden).catch(() => null);
  ok("phone: no dock before a time is chosen", dockHidden0 === true, dockHidden0);
  ok("phone: nothing pre-selected", (await p.$$(".cgs .tm.on")).length === 0);
  const cmp0 = await p.evaluate(() => [...document.scripts].some(s => /\/assets\/compare\./.test(s.src)));
  ok("phone: the compare chunk waits for its tab (not fetched at start-up)", !cmp0, cmp0);
  // the day bar
  const days = await p.$$eval("[data-day]", bs => bs.filter(x => !x.hidden).map(x => x.getAttribute("data-day")));
  if (days.length > 1) {
    for (const d of days) {
      await p.click(`[data-day="${d}"]`);
      await p.waitForTimeout(150);
      const st = await p.evaluate(d => {
        const shown = [...document.querySelectorAll(".cgs .times[data-d]")].filter(t => !t.hidden).map(t => t.getAttribute("data-d"));
        return { only: shown.every(x => x === d), n: shown.length, pressed: document.querySelector(`[data-day="${d}"]`).getAttribute("aria-pressed") };
      }, d);
      ok(`day ${d}: only its times, pressed`, st.only && st.n > 0 && st.pressed === "true", st);
    }
    await p.click(`[data-day="${days[0]}"]`);
  } else skip("day switching", "one day in this build (" + days + ")");
  // a time → the dock → the ticket sheet with that show
  if (await hasTimes(p)) {
    const tm = await p.$(firstFree);
    const want = await tm.evaluate(a => ({ t: a.getAttribute("data-start"), show: a.getAttribute("data-show"), cin: a.closest("[data-cin]").getAttribute("data-cin") }));
    await tm.click();
    await p.waitForTimeout(700);
    const dk = await p.$eval("[data-dock]", d => ({ hidden: d.hidden, s: d.querySelector("[data-dk-s]").textContent, pr: d.querySelector("[data-dk-p]").textContent }));
    ok("time → dock shows it", !dk.hidden && dk.s.includes(want.t), dk);
    const sheetOpen0 = await p.$eval("[data-ticket]", t => t.classList.contains("open"));
    ok("time → the sheet waits for «التفاصيل والحجز»", !sheetOpen0);
    await p.click("[data-dk-open]");
    await p.waitForTimeout(700);
    const tk = await p.$eval("[data-ticket]", t => ({ open: t.classList.contains("open"), time: t.querySelector("[data-tk-time]").textContent,
      cin: t.getAttribute("data-cin"), rows: t.querySelectorAll("[data-tk-rows] tr").length, focusIn: t.contains(document.activeElement),
      modal: t.getAttribute("aria-modal") }));
    ok("dock → the ticket sheet opens with that show", tk.open && tk.time === want.t && tk.cin === want.cin && tk.rows > 0 && tk.focusIn && tk.modal === "true", tk);
    await p.keyboard.press("Escape");
    await p.waitForTimeout(500);
    const back = await p.evaluate(() => ({ open: document.querySelector("[data-ticket]").classList.contains("open"), focus: document.activeElement && document.activeElement.hasAttribute("data-dk-open") }));
    ok("Esc closes the sheet, focus back on the dock's button", !back.open && back.focus, back);
    // the card reprices the dock and the buttons
    const cards = await p.$$eval("#sheet-card button[data-card]", bs => bs.map(x => x.getAttribute("data-card")).filter(Boolean));
    let moved = null;
    for (const c of cards) {
      await p.evaluate(c => document.querySelector(`#sheet-card button[data-card="${c}"]`).click(), c);
      await p.waitForTimeout(250);
      const pr = await p.$eval("[data-dk-p]", e => e.textContent);
      if (pr !== dk.pr) { moved = [c, dk.pr, pr]; break; }
    }
    if (moved) ok("a card reprices the dock (and says «بعد <card>»)", /بعد|after/.test(await p.$eval("[data-dk-s]", e => e.textContent)), moved);
    else skip("card reprices the dock", "no card discounts this show");
    await p.evaluate(() => document.querySelector('#sheet-card button[data-card=""]').click());
    await p.waitForTimeout(200);
    // a day with the chosen time out of sight drops the dock
    if (days.length > 1) {
      const other = days.find(d => d !== (want && days[0]));
      await p.click(`[data-day="${other}"]`);
      await p.waitForTimeout(300);
      ok("another day: the dock goes", await p.$eval("[data-dock]", d => d.hidden));
      await p.click(`[data-day="${days[0]}"]`);
    }
  } else skip("time → dock → ticket", "no time still to come in the visitor's city today (build date)");
  // the «⋯» sheet
  await p.click(".dmore");
  await p.waitForTimeout(400);
  const fo = await p.evaluate(() => { const s = document.getElementById("sheet-fopts"); return { open: !s.hidden, prayer: !!s.querySelector("[data-prayer]"), who: s.querySelectorAll("[data-who]").length, before: s.querySelectorAll("[data-before]").length }; });
  ok("«⋯» opens the options sheet: prayer, «مع منو», «يخلص قبل»", fo.open && fo.prayer && fo.who === 4 && fo.before === 5, fo);
  await p.keyboard.press("Escape");
  await p.waitForTimeout(300);
  // the verdict
  const vm = await p.$("[data-fv-more]:not([hidden])");
  if (vm) {
    const h0 = await p.$eval("[data-fv]", v => v.clientHeight);
    await vm.click();
    const h1 = await p.$eval("[data-fv]", v => v.clientHeight);
    ok("«المزيد» opens the verdict", h1 > h0 && (await vm.getAttribute("aria-expanded")) === "true", [h0, h1]);
  } else skip("«المزيد»", "the verdict fits in three lines");
  await p.close();
  p = await open({ ...phone, viewport: { width: 375, height: 812 } });
  const w375 = await p.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
  ok("phone 375: scrollWidth == innerWidth", w375[0] === w375[1], w375);
  await p.close();

  // ---------------------------------------------------------------- desktop
  p = await open(desk);
  ok("desktop: no duplicate ids", (await dupIds(p)).length === 0, await dupIds(p));
  // the column is the next show in the visitor's city (fix round 1, I5), «اختر وقت» only when there is none
  const nextOf = () => p.evaluate(() => {
    let best = null;
    document.querySelectorAll(".fcity.here > .cg:not(.more-h):not(.x) .tx:not([hidden]) .tm[data-start]:not(.past):not(.x)").forEach(b => {
      if (!best || b.getAttribute("data-start") < best.getAttribute("data-start")) best = b;
    });
    const t = document.querySelector("[data-ticket]");
    return { next: best && [best.getAttribute("data-start"), best.closest("[data-cin]").getAttribute("data-cin")],
      tk: !t.hidden, empty: !document.querySelector("[data-tk-empty]").hidden, time: t.querySelector("[data-tk-time]") && t.querySelector("[data-tk-time]").textContent,
      cin: t.getAttribute("data-cin"), on: [...document.querySelectorAll(".cgs .tm.on")].map(b => b.getAttribute("data-start")),
      dock: getComputedStyle(document.querySelector("[data-dock]")).display, live: (t.querySelector("[data-tk-live]") || {}).textContent || "" };
  });
  await p.waitForTimeout(400);
  const st0 = await nextOf();
  ok("desktop: the column opens on the next show in the visitor's city (quietly), «اختر وقت» only with none",
    st0.dock === "none" && (st0.next ? st0.tk && !st0.empty && st0.time === st0.next[0] && st0.cin === st0.next[1] && st0.on.join() === st0.next[0] && !st0.live
      : !st0.tk && st0.empty), st0);
  if (await hasTimes(p)) {
    const tms = await p.$$(firstFree);
    const tm = tms[tms.length - 1];
    const want = await tm.evaluate(a => ({ t: a.getAttribute("data-start"), cin: a.closest("[data-cin]").getAttribute("data-cin"), show: a.getAttribute("data-show") }));
    await tm.click();
    await p.waitForTimeout(700);
    const st1 = await p.evaluate(() => { const t = document.querySelector("[data-ticket]"); return { tk: !t.hidden, empty: !document.querySelector("[data-tk-empty]").hidden,
      time: t.querySelector("[data-tk-time]").textContent, cin: t.getAttribute("data-cin"), sticky: getComputedStyle(t.parentNode).position, open: t.classList.contains("open") }; });
    ok("desktop: a time fills the side column", st1.tk && !st1.empty && st1.time === want.t && st1.cin === want.cin && st1.sticky === "sticky" && !st1.open, st1);
    if (days.length > 1) {
      const d2 = days.find(d => d !== days[0]);
      await p.click(`[data-day="${d2}"]`);
      await p.waitForTimeout(400);
      const st2 = await nextOf();
      ok("desktop: another day → that day's next show (or «اختر وقت»)", st2.next ? st2.tk && st2.time === st2.next[0] && st2.cin === st2.next[1] : !st2.tk && st2.empty, st2);
      await p.click(`[data-day="${days[0]}"]`);
    }
  } else skip("desktop time → column", "no time still to come today");
  // tabs: a real tablist
  const tabs = await p.$$eval("[data-tabs] [role=tab]", ts => ts.map(t => [t.getAttribute("data-tab"), t.getAttribute("aria-selected"), t.tabIndex]));
  const panels = await p.$$eval("[role=tabpanel]", ps => ps.map(x => [x.id, x.hidden]));
  ok("tabs: a tablist, first selected, the other panels hidden", tabs.length > 1 && tabs[0][1] === "true" && tabs.slice(1).every(t => t[1] === "false" && t[2] === -1) &&
    panels.filter(x => !x[1]).length === 1, { tabs, panels });
  const rtl = await p.evaluate(() => document.documentElement.dir === "rtl");
  await p.focus("[data-tabs] [role=tab][aria-selected=true]");
  await p.keyboard.press(rtl ? "ArrowLeft" : "ArrowRight");
  const k1 = await p.evaluate(() => ({ sel: document.querySelector("[role=tab][aria-selected=true]").getAttribute("data-tab"), focus: document.activeElement.getAttribute("data-tab"),
    shown: [...document.querySelectorAll("[role=tabpanel]")].filter(x => !x.hidden).map(x => x.id), hash: location.hash }));
  ok("tabs: the arrow in the reading direction moves to the next", k1.sel === tabs[1][0] && k1.focus === tabs[1][0] && k1.shown.join() === tabs[1][0] && k1.hash === "#" + tabs[1][0], k1);
  await p.keyboard.press("End");
  const k2 = await p.evaluate(() => document.querySelector("[role=tab][aria-selected=true]").getAttribute("data-tab"));
  await p.keyboard.press("Home");
  const k3 = await p.evaluate(() => document.querySelector("[role=tab][aria-selected=true]").getAttribute("data-tab"));
  ok("tabs: End and Home", k2 === tabs[tabs.length - 1][0] && k3 === tabs[0][0], [k2, k3]);
  if (await p.$("[data-tab-go=compare]")) {
    await p.click("[data-tab-go=compare]");
    await p.waitForTimeout(500);
    await p.waitForTimeout(800);
    const c = await p.evaluate(() => ({ sel: document.querySelector("[role=tab][aria-selected=true]").getAttribute("data-tab"), shown: !document.getElementById("compare").hidden,
      ui: document.querySelectorAll("#compare [data-cmp-ui] select").length }));
    // the compare chunk is fetched once its tab is shown (fix round 1), and draws the two film pickers
    ok("the hero's «قارن» opens its tab, and the compare box draws", c.sel === "compare" && c.shown && c.ui === 2, c);
  } else skip("hero «قارن»", "no compare box on this page");
  await p.close();
  // a #hash opens its tab
  const last = tabs[tabs.length - 1][0];
  p = await open(desk, base + path + qs + "#" + last);
  const dl = await p.evaluate(() => ({ sel: document.querySelector("[role=tab][aria-selected=true]").getAttribute("data-tab"),
    shown: [...document.querySelectorAll("[role=tabpanel]")].filter(x => !x.hidden).map(x => x.id), top: document.querySelector("[data-tabs]").getBoundingClientRect().top, h: innerHeight,
    end: Math.ceil(scrollY + innerHeight) >= document.documentElement.scrollHeight - 2 }));
  // in view: at the top under the header, or as high as the page's end let it come (a short last tab)
  ok("#" + last + " opens that tab, in view", dl.sel === last && dl.shown.join() === last && dl.top >= 0 && dl.top < dl.h - 120, dl);
  // a city change: that city first and open
  const cities = await p.$$eval(".fcity[data-city]", s => s.map(x => x.getAttribute("data-city")));
  if (cities.length > 1) {
    const c2 = cities[cities.length - 1];
    await p.click("#pill-city");
    await p.waitForTimeout(300);
    await p.click(`#sheet-city a[data-city="${c2}"]`);
    await p.waitForTimeout(400);
    const cs = await p.evaluate(() => { const s = [...document.querySelectorAll(".fcity[data-city]")]; return { first: s[0].getAttribute("data-city"), here: s[0].classList.contains("here"), open: s.filter(x => x.open).map(x => x.getAttribute("data-city")) }; });
    ok("a city from the sheet: its cinemas first and open, the others folded", cs.first === c2 && cs.here && cs.open.join() === c2, cs);
  } else skip("city change", "one city");
  await p.close();

  // ---------------------------------------------------------------- fix round 1
  // I3: a malformed #hash is no tab and stops nothing (prices, discounts, the schedule's layout all happen)
  {
    const reqs = [];
    const pg = await b.newPage(phone);
    pg.on("pageerror", e => errors.push("[#100%] " + String(e)));
    pg.on("request", r => reqs.push(r.url()));
    await pg.goto(url + "#100%", { waitUntil: "networkidle" });
    await pg.waitForTimeout(600);
    const st = await pg.evaluate(() => ({ tabs: !!document.querySelector("[role=tablist]"), tx: document.querySelectorAll(".cgs .tx").length,
      sel: (document.querySelector("[role=tab][aria-selected=true]") || {}).textContent || "" }));
    ok("a malformed #hash (#100%): start-up runs to the end (tabs, the schedule's layout, discounts.json)",
      st.tabs && st.tx > 0 && reqs.some(u => u.includes("/data/discounts.json")), { ...st, discounts: reqs.some(u => u.includes("/data/discounts.json")) });
    await pg.close();
  }
  // I2 + I5 with a real clock: a chosen show keeps its ticket when it starts; the page's own pick moves on
  if (now) {
    const t0 = new Date(now + ":00+04:00");
    const soonest = pg => pg.evaluate(sel => {
      document.querySelectorAll("[data-pick]").forEach(b => b.removeAttribute("data-pick"));
      let best = null;
      document.querySelectorAll(sel).forEach(b => { if (!best || b.getAttribute("data-start") < best.getAttribute("data-start")) best = b; });
      if (!best) return null;
      best.setAttribute("data-pick", "");
      return { t: best.getAttribute("data-start"), d: best.closest("[data-d]").getAttribute("data-d") };
    }, firstFree);
    const mins = s => Math.ceil((new Date(s.d + "T" + s.t + ":00+04:00") - t0) / 60000);
    let pg = await b.newPage(phone);
    pg.on("pageerror", e => errors.push("[clock] " + String(e)));
    await pg.clock.install({ time: t0 });
    await pg.goto(base + path, { waitUntil: "networkidle" });
    await pg.waitForTimeout(600);
    const s = await soonest(pg);
    if (s) {
      await pg.click("[data-pick]");
      await pg.waitForTimeout(500);
      await pg.click("[data-dk-open]");
      await pg.waitForTimeout(600);
      await pg.clock.fastForward((mins(s) + 2) * 60000);
      await pg.waitForTimeout(300);
      const st = await pg.evaluate(() => { const t = document.querySelector("[data-ticket]"), b = document.querySelector("[data-pick]");
        return { open: t.classList.contains("open"), focusIn: t.contains(document.activeElement), past: b.classList.contains("past"), on: b.classList.contains("on"),
          dock: !document.querySelector("[data-dock]").hidden, time: t.querySelector("[data-tk-time]").textContent }; });
      ok("phone: the chosen show starts with its ticket open — it stays open, focused, struck and chosen (I2)",
        st.open && st.focusIn && st.past && st.on && st.dock && st.time === s.t, { ...st, after: mins(s) + 2 + " min" });
    } else skip("phone clock", "no show to come");
    await pg.close();
    pg = await b.newPage(desk);
    pg.on("pageerror", e => errors.push("[clock desk] " + String(e)));
    await pg.clock.install({ time: t0 });
    await pg.goto(base + path, { waitUntil: "networkidle" });
    await pg.waitForTimeout(600);
    const a0 = await pg.evaluate(() => { const t = document.querySelector("[data-ticket]"); return t.hidden ? null : t.querySelector("[data-tk-time]").textContent; });
    const s2 = await soonest(pg);
    if (s2 && a0 === s2.t) {
      await pg.clock.fastForward((mins(s2) + 1) * 60000);
      await pg.waitForTimeout(400);
      const st = await pg.evaluate(sel => {
        let best = null;
        document.querySelectorAll(sel).forEach(b => { if (!best || b.getAttribute("data-start") < best.getAttribute("data-start")) best = b; });
        const t = document.querySelector("[data-ticket]");
        return { next: best && best.getAttribute("data-start"), tk: !t.hidden, time: t.querySelector("[data-tk-time]").textContent, empty: !document.querySelector("[data-tk-empty]").hidden };
      }, firstFree);
      ok("desktop: the page's own pick starts → the column moves to the next show (I5)", st.next ? st.tk && st.time === st.next && st.time !== a0 : st.empty, { was: a0, ...st });
      // a pick of the visitor's own stays when it starts
      const s3 = await soonest(pg);
      if (s3) {
        await pg.click("[data-pick]");
        await pg.waitForTimeout(400);
        await pg.clock.fastForward((Math.ceil((new Date(s3.d + "T" + s3.t + ":00+04:00") - await pg.evaluate(() => Date.now())) / 60000) + 1) * 60000);
        await pg.waitForTimeout(400);
        const st3 = await pg.evaluate(() => { const t = document.querySelector("[data-ticket]"); return { tk: !t.hidden, time: t.querySelector("[data-tk-time]").textContent,
          past: document.querySelector("[data-pick]").classList.contains("past") }; });
        ok("desktop: the visitor's own pick stays in the column when it starts (I2)", st3.tk && st3.time === s3.t && st3.past, st3);
      }
    } else skip("desktop clock", "no auto pick to follow (" + JSON.stringify([a0, s2]) + ")");
    await pg.close();
  } else skip("clock checks", "no [now] given");
  // I1: «المزيد» sits over the third line's end with its fade, not on the words
  {
    const pg = await b.newPage(phone);
    await pg.goto(url, { waitUntil: "networkidle" });
    await pg.waitForTimeout(700);
    const m = await pg.evaluate(() => { const b = document.querySelector("[data-fv-more]"); if (!b || b.hidden) return null;
      const cs = getComputedStyle(b); return { pos: cs.position, bg: cs.backgroundImage, pad: parseFloat(cs.paddingInlineStart), deco: cs.textDecorationLine }; });
    if (m) ok("«المزيد»: absolute over the third line, a fade behind it, room for it (I1)", m.pos === "absolute" && m.bg !== "none" && m.pad >= 40 && m.deco === "none", m);
    else skip("«المزيد» style", "the verdict fits");
    // M10: a price with a note says so on its button (a table price's date, or a card's «للشخص» / an excluded hall:
    // the cards are tried until one gives a note)
    await pg.waitForTimeout(300);
    const cardN = await pg.evaluate(async () => {
      if (document.querySelector(".tx .tm .p small")) return "";
      for (const b of document.querySelectorAll("#sheet-card button[data-card]")) {
        if (!b.getAttribute("data-card")) continue;
        b.click(); await new Promise(r => setTimeout(r, 60));
        if (document.querySelector(".tx .tm .p small")) return b.getAttribute("data-card");
      }
      return null;
    });
    const n = await pg.evaluate(() => { const s = document.querySelector(".tx .tm .p small"); if (!s) return null;
      return { after: getComputedStyle(s.parentNode, "::after").content, shown: getComputedStyle(s).position, text: s.textContent }; });
    if (n) ok("a price's note: a gold * on the button, the words read out (M10)", n.after === '"*"' && n.shown === "absolute" && n.text.length > 0, { card: cardN, ...n });
    else skip("price note marker", "no price with a note on this page");
    await pg.close();
  }
  // M6: «N سينمات ثانية» opened stays open through a sort by distance
  {
    const ctx = await b.newContext({ ...phone, geolocation: { latitude: 25.1972, longitude: 55.2796 }, permissions: ["geolocation"] });
    const pg = await ctx.newPage();
    pg.on("pageerror", e => errors.push("[near] " + String(e)));
    await pg.goto(url, { waitUntil: "networkidle" });
    await pg.waitForTimeout(600);
    if (await pg.$("[data-more-c]")) {
      await pg.click("[data-more-c]");
      await pg.click("#pill-city");
      await pg.waitForTimeout(300);
      await pg.click("#sheet-city [data-near]");
      await pg.waitForTimeout(1500);
      const st = await pg.evaluate(() => ({ hidden: document.querySelectorAll(".fcity.here .cg.more-h").length, btn: !!document.querySelector("[data-more-c]"),
        dist: [...document.querySelectorAll(".fcity.here [data-dist]")].filter(e => e.textContent).length }));
      ok("«N سينمات ثانية» opened stays open when «قريب مني» sorts the cinemas (M6)", st.hidden === 0 && !st.btn && st.dist > 0, st);
    } else skip("M6", "four cinemas or fewer in the city");
    await ctx.close();
  }
  // M9: the city picked from the network is said once under the header, and goes with ×
  {
    const ctx = await b.newContext(phone);
    await ctx.route("**/geo", r => r.fulfill({ status: 200, contentType: "application/json", body: '{"city":"sharjah"}' }));
    const pg = await ctx.newPage();
    pg.on("pageerror", e => errors.push("[geo] " + String(e)));
    await pg.goto(base + path, { waitUntil: "networkidle" });
    await pg.waitForTimeout(800);
    const st = await pg.evaluate(() => { const n = document.querySelector("[data-geo-note]"); return n ? { text: n.textContent, pill: document.querySelector("#pill-city").textContent,
      fixed: getComputedStyle(n).position, top: n.getBoundingClientRect().top } : null; });
    ok("network city: one line under the header names the city, with «غيّرها» (M9)", !!st && /الشارقة|Sharjah/.test(st.text) && /الشارقة|Sharjah/.test(st.pill) && st.fixed === "fixed", st);
    if (st) {
      await pg.click("[data-geo-x]");
      const gone = await pg.evaluate(() => !document.querySelector("[data-geo-note]"));
      await pg.reload({ waitUntil: "networkidle" });
      await pg.waitForTimeout(600);
      const again = await pg.evaluate(() => !!document.querySelector("[data-geo-note]"));
      ok("network city note: × takes it away, and it is not said again", gone && !again, { gone, again });
    }
    await ctx.close();
  }
  // M11: on a 1280×720 screen the stuck ticket column fits, «احجز» on screen
  {
    const pg = await b.newPage({ viewport: { width: 1280, height: 720 } });
    await pg.goto(url, { waitUntil: "networkidle" });
    await pg.waitForTimeout(600);
    if (await pg.$(firstFree)) {
      await pg.click(firstFree);
      await pg.waitForTimeout(600);
      await pg.evaluate(() => { const e = document.querySelector(".cgs"); scrollTo(0, e.getBoundingClientRect().top + scrollY + 200); });
      await pg.waitForTimeout(300);
      const st = await pg.evaluate(() => { const c = document.querySelector(".tkcol").getBoundingClientRect(), bk = document.querySelector("[data-tk-book]").getBoundingClientRect();
        return { colBottom: Math.round(c.bottom), bookBottom: Math.round(bk.bottom), h: innerHeight }; });
      ok("1280×720: the ticket column fits the screen, «احجز» visible (M11)", st.colBottom <= st.h && st.bookBottom <= st.h && st.bookBottom > 0, st);
    } else skip("M11", "no time to choose");
    await pg.close();
  }

  // ---------------------------------------------------------------- no script
  p = await b.newPage({ ...phone, javaScriptEnabled: false });
  await p.goto(url, { waitUntil: "load" });
  const nj = await p.evaluate(() => ({ links: [...document.querySelectorAll("[data-tabs] a")].filter(a => getComputedStyle(a).display !== "none").map(a => a.getAttribute("href")),
    hidden: [...document.querySelectorAll(".tpn")].filter(x => x.hidden || getComputedStyle(x).display === "none").length,
    n: document.querySelectorAll(".tpn").length, bar: getComputedStyle(document.querySelector(".dbar") || document.body).display,
    times: document.querySelectorAll(".cgs .tm").length, prices: document.querySelectorAll(".cgs .hl-n .p[data-aed], .cgs .times .pr .p[data-aed]").length }));
  ok("no script: tabs are in-page links, every section shown, hall prices and times there", nj.links.every(h => h.startsWith("#")) && nj.hidden === 0 && nj.n > 0 &&
    (nj.times > 0 || nj.prices > 0), nj);
  await p.close();

  await b.close();
  out.forEach(l => console.log(l));
  if (errors.length) console.log("page errors:", errors.join(" | "));
  const fails = out.filter(l => l.startsWith("FAIL")).length;
  console.log(fails ? fails + " FAILED" : "all passed", "(" + out.filter(l => l.startsWith("PASS")).length + " pass, " + out.filter(l => l.startsWith("SKIP")).length + " skip)");
  process.exit(fails || errors.length ? 1 : 0);
})();
