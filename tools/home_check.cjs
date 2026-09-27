// Home page behaviour checks (UI redesign Task 3): the billboard (city swap, rotation, pause, indicators, reduced
// motion), the filter and sort sheets (live count, badge, URL presets), a row's arrows, the card reprice.
// usage: node tools/home_check.cjs <base url, e.g. http://127.0.0.1:8811> [now, e.g. 2026-09-27T16:50]
// PLAYWRIGHT: where the playwright package is (default: the Elyoxe site's node_modules on this laptop)
const { chromium } = require(process.env.PLAYWRIGHT || "C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");
(async () => {
  const [base, now] = process.argv.slice(2);
  const qs = now ? "?now=" + now : "";
  const b = await chromium.launch({ channel: "chrome" });
  const out = [], errors = [];
  const ok = (name, cond, extra) => out.push((cond ? "PASS " : "FAIL ") + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  const page = async (opts, url) => {
    const p = await b.newPage(opts);
    p.on("pageerror", e => errors.push(String(e)));
    await p.goto(url, { waitUntil: "networkidle" });
    await p.waitForTimeout(600);
    return p;
  };
  const title = p => p.$eval("[data-bill-a]", a => a.textContent);
  // desktop
  let p = await page({ viewport: { width: 1440, height: 900 } }, base + "/" + qs);
  const t0 = await title(p);
  const dots = await p.$$eval("[data-bill-dots] button", bs => bs.map(x => [x.getAttribute("aria-label"), x.getAttribute("aria-pressed")]));
  ok("indicators are labelled buttons, first pressed", dots.length > 1 && dots.every(d => d[0]) && dots[0][1] === "true", dots.length);
  await p.mouse.move(5, 890);   // not over the billboard
  await p.waitForTimeout(6600);
  const t1 = await title(p);
  ok("rotates after 6 s", t1 !== t0, [t0, t1]);
  await p.hover(".bill-in");
  const t2 = await title(p);
  await p.waitForTimeout(6600);
  ok("hover pauses", (await title(p)) === t2);
  await p.mouse.move(5, 890);
  await p.click("[data-bill-dots] button:nth-child(3)");
  await p.waitForTimeout(300);
  const lab3 = await p.$eval("[data-bill-dots] button:nth-child(3)", x => x.getAttribute("aria-label"));
  ok("indicator shows its film", (await title(p)) === lab3, lab3);
  // stale layers: a burst of indicator presses leaves one picture layer
  for (let k = 0; k < 4; k++) { await p.click("[data-bill-dots] button:nth-child(" + (k % 2 + 1) + ")"); await p.waitForTimeout(60); }
  await p.waitForTimeout(1600);
  ok("one picture layer after a burst", (await p.$$eval("[data-bill-bd] > .bd", e => e.length)) === 1);
  // city swap
  await p.click("#pill-city"); await p.waitForTimeout(300);
  await p.click('#sheet-city a[data-city="sharjah"]'); await p.waitForTimeout(1200);
  const eye = await p.$eval("[data-bill-eye]", e => e.textContent);
  ok("city change: eyebrow names the city", /الشارقة|Sharjah/.test(eye), eye);
  const shj = await p.evaluate(() => JSON.parse(document.getElementById("bill-data").textContent).c.sharjah.map(r => r[0]));
  const href = await p.$eval("[data-bill-a]", a => a.getAttribute("href"));
  ok("city change: its first film", href.indexOf(shj[0]) >= 0, [href, shj[0]]);
  const from0 = await p.$eval("[data-from]", e => e.textContent);
  ok("city change: CTA priced (never «…» once the city's data is in)", from0.indexOf("…") < 0, from0);
  // card reprice
  await p.click("#pill-card"); await p.waitForTimeout(300);
  const cards = await p.$$eval('#sheet-card button[data-card]', bs => bs.map(x => x.getAttribute("data-card")).filter(Boolean));
  await p.keyboard.press("Escape"); await p.waitForTimeout(200);
  // a card that discounts this film's cheapest ticket here moves the CTA: try them in turn, and the struck old
  // price must be the pre-card one
  let from1 = from0, used = null;
  for (const c of cards) {
    await p.click("#pill-card"); await p.waitForTimeout(250);
    await p.click('#sheet-card button[data-card="' + c + '"]'); await p.waitForTimeout(600);
    from1 = await p.$eval("[data-from]", e => e.textContent);
    if (from1 !== from0) { used = c; break; }
  }
  const struck = await p.$eval("[data-from]", e => { const s = e.querySelector("s"); return s ? s.textContent : null; });
  // the price paid after the card is below the price before it; the struck one is that ticket's own pre-card price
  // (the cheapest after a card can be a dearer ticket before it, e.g. a two-for-one)
  const paid = await p.$eval("[data-from] .p b", e => +e.textContent).catch(() => NaN), before = +(from0.match(/[\d.]+/) || [NaN])[0];
  ok("card: CTA price follows the card (old price struck)", used && struck && paid < before && +struck > paid, [from0, from1, used, struck]);
  await p.click("#pill-card"); await p.waitForTimeout(250);
  await p.click('#sheet-card button[data-card=""]'); await p.waitForTimeout(500);
  ok("card: no card puts the price back", (await p.$eval("[data-from]", e => e.textContent)) === from0);
  // row arrows
  await p.hover(".rail:not([hidden]) .strip");
  // from its start (a strip may have been scrolled by an earlier step's focus)
  await p.$eval('.rail[aria-labelledby="r-top"] [data-strip]', s => { s.style.scrollBehavior = "auto"; s.scrollLeft = 0; s.style.scrollBehavior = ""; });
  await p.waitForTimeout(200);
  const sl0 = await p.$eval('.rail[aria-labelledby="r-top"] [data-strip]', s => s.scrollLeft);
  await p.hover('.rail[aria-labelledby="r-top"]');
  await p.click('.rail[aria-labelledby="r-top"] [data-rail="1"]'); await p.waitForTimeout(900);
  const sl1 = await p.$eval('.rail[aria-labelledby="r-top"] [data-strip]', s => s.scrollLeft);
  ok("row arrow pages the strip toward the end", sl1 !== sl0, [sl0, sl1]);
  // hover panel: no layout shift
  const tile = '.rail[aria-labelledby="r-top"] .tile';
  const box0 = await p.$eval('.rail[aria-labelledby="r-yes"]', e => e.getBoundingClientRect().top).catch(() => null);
  await p.hover(tile); await p.waitForTimeout(800);
  const box1 = await p.$eval('.rail[aria-labelledby="r-yes"]', e => e.getBoundingClientRect().top).catch(() => null);
  const hv = await p.$eval(tile + " .hv", e => [getComputedStyle(e).opacity, e.textContent]);
  ok("tile hover panel shows, nothing moves", hv[0] === "1" && box0 === box1, hv);
  await p.close();

  // phone: filter sheet, live count, badge, sort sheet
  const mob = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
  p = await page(mob, base + "/" + qs);
  const n0 = await p.$eval("[data-all-n]", e => +e.textContent);
  await p.click(".fchip"); await p.waitForTimeout(400);
  await p.click('#sheet-filter [data-filter="family"]'); await p.waitForTimeout(300);
  const n1 = await p.$eval("[data-all-n]", e => +e.textContent);
  const fn = await p.$eval("[data-fn]", e => e.textContent);
  const live = await p.$eval("[data-fn-live]", e => e.textContent);
  const badge = await p.$eval("[data-fcount]", e => [e.hidden, e.textContent]);
  const words = n => n === 1 ? "فيلم واحد" : n === 2 ? "فيلمين" : n <= 10 ? n + " أفلام" : n + " فيلم";   // as filmsN (Arabic page)
  ok("filter: count drops, button and live region say it, badge 1",
     n1 < n0 && fn === words(n1) && live.indexOf(words(n1)) === 0 && !badge[0] && badge[1] === "1", [n0, n1, fn, live, badge]);
  ok("filter: live region polite and filled", live.length > 0 && (await p.$eval("[data-fn-live]", e => e.getAttribute("aria-live"))) === "polite");
  const langBtn = await p.$('#sheet-filter [data-flang]:not([data-flang=""])');
  if (langBtn) {
    await langBtn.click(); await p.waitForTimeout(300);
    const badge2 = await p.$eval("[data-fcount]", e => e.textContent);
    ok("language chip filters too (badge 2)", badge2 === "2", badge2);
  } else out.push("SKIP language chip: this build's films have one language only");
  // a companion is one filter, not two
  await p.click("#sheet-filter [data-reset]"); await p.waitForTimeout(200);
  await p.click('#sheet-filter [data-who="family"]'); await p.waitForTimeout(200);
  ok("a companion counts as one filter", (await p.$eval("[data-fcount]", e => e.textContent)) === "1");
  await p.click('#sheet-filter [data-filter="family"]'); await p.waitForTimeout(200);
  await p.click("#sheet-filter [data-show-all]"); await p.waitForTimeout(900);
  const closed = await p.$eval("#sheet-filter", e => e.hidden);
  const allTop = await p.$eval("#all", e => Math.round(e.getBoundingClientRect().top));
  ok("«اعرض» closes the sheet and lands on the grid", closed && allTop >= 0 && allTop < 200, allTop);
  await p.click(".fchip"); await p.waitForTimeout(300);
  await p.click('#sheet-filter [data-prayer]'); await p.waitForTimeout(300);
  await p.click("#sheet-filter [data-reset]"); await p.waitForTimeout(300);
  ok("«مسح» clears, the prayer switch too", (await p.$eval("[data-all-n]", e => +e.textContent)) === n0 && (await p.$eval("[data-fcount]", e => e.hidden)) &&
     (await p.$eval("#sheet-filter [data-prayer]", e => e.getAttribute("aria-checked"))) === "false");
  await p.keyboard.press("Escape"); await p.waitForTimeout(300);
  await p.click('[data-sheet-open="sheet-sort"]'); await p.waitForTimeout(300);
  await p.click('#sheet-sort [data-sort="price"]'); await p.waitForTimeout(500);
  const sn = await p.$eval("[data-sort-name]", e => e.textContent);
  ok("sort sheet picks and closes", (await p.$eval("#sheet-sort", e => e.hidden)) && /الأرخص|Cheapest/.test(sn), sn);
  await p.click('[data-sheet-open="sheet-sort"]'); await p.waitForTimeout(300);
  await p.click('#sheet-sort [data-sort="time"]'); await p.waitForTimeout(400);
  await p.evaluate(() => { localStorage.removeItem("cinema.sort"); });
  const sw = await p.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
  ok("no sideways scroll at 390", sw[0] === sw[1], sw);
  await p.close();

  // URL presets from a row's «الكل»
  p = await page(mob, base + "/" + (qs ? qs + "&" : "?") + "f=family#all");
  const pf = await p.$eval('#sheet-filter [data-filter="family"]', e => e.getAttribute("aria-pressed"));
  ok("?f=family preselects the family chip", pf === "true");
  await p.click(".fchip"); await p.waitForTimeout(300);
  await p.click("#sheet-filter [data-reset]"); await p.waitForTimeout(300);
  ok("«مسح» takes ?f= out of the address", p.url().indexOf("f=family") < 0, p.url());
  await p.close();
  p = await page(mob, base + "/" + (qs ? qs + "&" : "?") + "f=yes#all");
  const yesOnly = await p.$$eval("[data-films] .film:not(.x)", els => els.every(e => e.getAttribute("data-v") === "yes") && els.length > 0);
  ok("«يستاهل» → الكل shows only «يستاهل» films", yesOnly);
  // pause button: a touch visitor stops the rotation
  const pt0 = await title(p);
  await p.click("[data-bill-pp]"); await p.waitForTimeout(6800);
  ok("pause button stops the rotation", (await title(p)) === pt0 && (await p.$eval("[data-bill-pp]", e => e.getAttribute("aria-pressed"))) === "true");
  await p.close();

  // reduced motion: no rotation
  p = await page({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" }, base + "/" + qs);
  await p.mouse.move(5, 890);
  const r0 = await title(p); await p.waitForTimeout(6800);
  ok("reduced motion: never rotates", (await title(p)) === r0);
  await p.close();

  // hidden tab pauses (visibility)
  p = await page({ viewport: { width: 1440, height: 900 } }, base + "/" + qs);
  await p.mouse.move(5, 890);
  await p.evaluate(() => { Object.defineProperty(document, "hidden", { value: true, configurable: true }); document.dispatchEvent(new Event("visibilitychange")); });
  const h0 = await title(p); await p.waitForTimeout(6800);
  ok("hidden tab pauses", (await title(p)) === h0);
  await p.close();

  out.forEach(l => console.log(l));
  if (errors.length) console.log("page errors:", errors.join(" | "));
  await b.close();
})();
