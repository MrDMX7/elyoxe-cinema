// Film page behaviour checks (UI redesign Task 4): the day bar, a time → the dock → the ticket sheet (phone) or the
// side column (desktop), the empty state, the tabs (keyboard, #hash, the hero's «قارن»), the verdict's «المزيد»,
// the «⋯» sheet, a city change, the card reprice, no duplicate ids, no sideways scroll, and the page with no script.
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
  const firstFree = ".fcity.here .times[data-d]:not([hidden]) .tm[data-start]:not(.past):not(.x)";
  const hasTimes = async p => !!(await p.$(firstFree));

  // ---------------------------------------------------------------- phone
  let p = await open(phone);
  ok("phone: no duplicate ids", (await dupIds(p)).length === 0, await dupIds(p));
  const w390 = await p.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
  ok("phone 390: scrollWidth == innerWidth", w390[0] === w390[1], w390);
  const dockHidden0 = await p.$eval("[data-dock]", d => d.hidden).catch(() => null);
  ok("phone: no dock before a time is chosen", dockHidden0 === true, dockHidden0);
  ok("phone: nothing pre-selected", (await p.$$(".cgs .tm.on")).length === 0);
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
  const st0 = await p.evaluate(() => ({ tk: !document.querySelector("[data-ticket]").hidden, empty: !document.querySelector("[data-tk-empty]").hidden,
    on: !!document.querySelector(".cgs .tm.on"), dock: getComputedStyle(document.querySelector("[data-dock]")).display }));
  ok("desktop: the ticket column shows a pick or «اختر وقت», never both", st0.tk !== st0.empty && (st0.tk ? st0.on : true) && st0.dock === "none", st0);
  if (await hasTimes(p)) {
    const tm = await p.$(firstFree);
    const want = await tm.evaluate(a => ({ t: a.getAttribute("data-start"), cin: a.closest("[data-cin]").getAttribute("data-cin"), show: a.getAttribute("data-show") }));
    await tm.click();
    await p.waitForTimeout(700);
    const st1 = await p.evaluate(() => { const t = document.querySelector("[data-ticket]"); return { tk: !t.hidden, empty: !document.querySelector("[data-tk-empty]").hidden,
      time: t.querySelector("[data-tk-time]").textContent, cin: t.getAttribute("data-cin"), sticky: getComputedStyle(t.parentNode).position, open: t.classList.contains("open") }; });
    ok("desktop: a time fills the side column", st1.tk && !st1.empty && st1.time === want.t && st1.cin === want.cin && st1.sticky === "sticky" && !st1.open, st1);
    if (days.length > 1) {
      await p.click(`[data-day="${days.find(d => d !== days[0])}"]`);
      await p.waitForTimeout(300);
      const st2 = await p.evaluate(() => ({ tk: !document.querySelector("[data-ticket]").hidden, empty: !document.querySelector("[data-tk-empty]").hidden }));
      ok("desktop: another day → «اختر وقت»", !st2.tk && st2.empty, st2);
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
    const c = await p.evaluate(() => ({ sel: document.querySelector("[role=tab][aria-selected=true]").getAttribute("data-tab"), shown: !document.getElementById("compare").hidden }));
    ok("the hero's «قارن» opens its tab", c.sel === "compare" && c.shown, c);
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
