// usage: node shoot.cjs <url> <out.png> <w> <h> [full]
const { chromium } = require("C:/Users/requi/workspace/web/elyoxe/site/node_modules/playwright");
(async () => {
  const [url, out, w, h, full] = process.argv.slice(2);
  const b = await chromium.launch({ channel: "chrome" });
  const mobile = +w < 800;
  const p = await b.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile });
  await p.goto(url, { waitUntil: "networkidle" });
  await p.waitForTimeout(800); if (process.argv[7]) { await p.evaluate(y => scrollTo(0, +y), process.argv[7]); await p.waitForTimeout(400); }
  const m = await p.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
  await p.screenshot({ path: out, fullPage: !!full });
  console.log(out, "viewport", m[0], "scrollWidth", m[1]);
  await b.close();
})();
