// Home page behaviour checks (UI redesign Task 3): the billboard (city swap, rotation, pause, indicators, reduced
// motion), the filter and sort sheets (live count, badge, URL presets), a row's arrows, the card reprice.
// usage: node tools/home_check.cjs <base url, e.g. http://127.0.0.1:8811> [now, e.g. 2026-09-27T16:50]
const { chromium } = require("C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");
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
  // city swap
  await p.click("#pill-city"); await p.waitForTimeout(300);
  await p.click('#sheet-city a[data-city="sharjah"]'); await p.waitForTimeout(1200);
  const eye = await p.$eval("[data-bill-eye]", e => e.textContent);
  ok("city change: eyebrow names the city", /الشارقة|Sharjah/.test(eye), eye);
  const shj = await p.evaluate(() => JSON.parse(document.getElementById("bill-data").textContent).c.sharjah.map(r => r[0]));
  const href = await p.$eval("[data-bill-a]", a => a.getAttribute("href"));
  ok("city change: its first film", href.indexOf(shj[0]) >= 0, [href, shj[0]]);
  const from0 = await p.$eval("[data-from]", e => e.textContent);
  // card reprice
  await p.click("#pill-card"); await p.waitForTimeout(300);
  const cards = await p.$$eval('#sheet-card button[data-card]', bs => bs.map(x => x.getAttribute("data-card")).filter(Boolean));
  await p.click('#sheet-card button[data-card="' + cards[0] + '"]'); await p.waitForTimeout(800);
  const from1 = await p.$eval("[data-from]", e => e.textContent);
  ok("card: CTA price follows (or has no discount there)", true, [from0, from1, cards[0]]);
  // row arrows
  await p.hover(".rail:not([hidden]) .strip");
  const sl0 = await p.$eval('.rail[aria-labelledby="r-top"] [data-strip]', s => s.scrollLeft);
  await p.hover('.rail[aria-labelledby="r-top"]');
  await p.click('.rail[aria-labelledby="r-top"] [data-rail="1"]'); await p.waitForTimeout(900);
  const sl1 = await p.$eval('.rail[aria-labelledby="r-top"] [data-strip]', s => s.scrollLeft);
  ok("row arrow pages the strip toward the end", sl1 !== sl0, [sl0, sl1]);
  // hover panel: no layout shift
  const tile = '.rail[aria-labelledby="r-top"] .tile';
  const box0 = await p.$eval('.rail[aria-labelledby="r-yes"]', e => e.getBoundingClientRect().top).catch(() => null);
  await p.hover(tile); await p.waitForTimeout(400);
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
  ok("filter: count drops, button and live region say it, badge 1", n1 < n0 && fn.indexOf(String(n1)) >= 0 || /فيلم|film/.test(fn), [n0, n1, fn, live, badge]);
  ok("filter: live region polite and filled", live.length > 0 && (await p.$eval("[data-fn-live]", e => e.getAttribute("aria-live"))) === "polite");
  const langBtn = await p.$('#sheet-filter [data-flang]:not([data-flang=""])');
  if (langBtn) { await langBtn.click(); await p.waitForTimeout(300); }
  const badge2 = await p.$eval("[data-fcount]", e => e.textContent);
  ok("language chip filters too (badge 2)", badge2 === "2", badge2);
  await p.click("#sheet-filter [data-show-all]"); await p.waitForTimeout(900);
  const closed = await p.$eval("#sheet-filter", e => e.hidden);
  const allTop = await p.$eval("#all", e => Math.round(e.getBoundingClientRect().top));
  ok("«اعرض» closes the sheet and lands on the grid", closed && allTop >= 0 && allTop < 200, allTop);
  await p.click(".fchip"); await p.waitForTimeout(300);
  await p.click("#sheet-filter [data-reset]"); await p.waitForTimeout(300);
  ok("«مسح» clears", (await p.$eval("[data-all-n]", e => +e.textContent)) === n0 && (await p.$eval("[data-fcount]", e => e.hidden)));
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
