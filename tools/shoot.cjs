// One screenshot of a page (the UI redesign's visual checks; docs/superpowers/specs/ui-mock/shoot.cjs extended).
// usage: node tools/shoot.cjs <url> <out.png> <w> <h> [full] [scrollY] [click-selector]
//   w < 800 is a phone: isMobile + touch + DPR 2 (headless Chrome's CLI screenshot has a 500 px minimum —
//   never use it for phone checks). Prints innerWidth and scrollWidth: they must be equal.
//   click-selector: clicked (then 500 ms) before the shot — e.g. "#pill-city" to show the city sheet.
const { chromium } = require("C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");
(async () => {
  const [url, out, w, h, full, scrollY, click] = process.argv.slice(2);
  const b = await chromium.launch({ channel: "chrome" });
  const mobile = +w < 800;
  const p = await b.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile });
  const errors = [];
  p.on("pageerror", e => errors.push(String(e)));
  await p.goto(url, { waitUntil: "networkidle" });
  await p.waitForTimeout(800);
  if (scrollY && +scrollY) { await p.evaluate(y => scrollTo(0, +y), scrollY); await p.waitForTimeout(400); }
  if (click) { await p.click(click); await p.waitForTimeout(500); }
  const m = await p.evaluate(() => [innerWidth, document.documentElement.scrollWidth,
    document.activeElement ? document.activeElement.outerHTML.slice(0, 120) : ""]);
  await p.screenshot({ path: out, fullPage: full === "full" || full === "1" });
  console.log(out, "viewport", m[0], "scrollWidth", m[1], m[0] === m[1] ? "OK" : "OVERFLOW");
  if (click) console.log("  focus:", m[2]);
  if (errors.length) console.log("  page errors:", errors.join(" | "));
  await b.close();
})();
