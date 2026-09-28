#!/usr/bin/env node
/* Gold text nodes on the first phone screen (W1-P1 tool; MASTER-PLAN §1.2 #9, §1.5, §7.3 #8). Gold is the usher's torch:
   it lights only what is *yours*. This counts the text nodes drawn in --gold (#E2B659) inside the first viewport of a
   page (home by default), board included, with no card and with one, at each size; and the gold colons, which must
   be 0 (a board's separator is the dull part). W1-P2 writes the gate against a fixture of the final first screen; it
   binds at the W2 merge after W2-P2a and in W2-QA. Until then it records.

     node tools/gold_count.cjs --out out [--port 8111] [--size 360x740,390x844] [--page /] [--card fazaa]
                               [--max 8] [--no-gold-colons] [--json FILE]
   --max N / --no-gold-colons turn the counts into assertions (exit 1 when over). A screenshot or a functional check
   needs no perf lock; this takes none. */
"use strict";
const fs = require("fs");
const K = require("./pw_kit.cjs");

const GOLD = "rgb(226, 182, 89)";

async function count(page) {
  return page.evaluate((GOLD) => {
    const vh = innerHeight, vw = innerWidth, out = [];
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const t = n.textContent.trim();
      if (!t) continue;
      const el = n.parentElement;
      if (!el || !el.checkVisibility || !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
      const cs = getComputedStyle(el);
      if (cs.color !== GOLD) continue;
      const r = document.createRange(); r.selectNodeContents(n);
      const box = [...r.getClientRects()].find((b) => b.width > 0 && b.height > 0 && b.bottom > 0 && b.top < vh && b.right > 0 && b.left < vw);
      if (!box) continue;
      const cls = typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).join(".") : "";
      out.push({ el: el.tagName.toLowerCase() + cls, text: t.slice(0, 40), colon: /^[:：]$/.test(t) || (t.includes(":") && /^[\d: ]+$/.test(t)), y: Math.round(box.top) });
    }
    return out;
  }, GOLD);
}

(async () => {
  const o = K.args();
  const pagePath = o.get("page", "/"), card = o.get("card", "fazaa"), max = o.get("max", null), noColons = o.has("no-gold-colons");
  const R = K.results();
  const srv = await K.serve(o);
  const browser = await K.launch();
  const report = [];
  try {
    await K.assertServed(srv.base, srv.stamp);
    R.check("X-Served-By " + srv.stamp + " on the document and an asset", true);
    for (const size of o.sizes) {
      for (const withCard of [false, true]) {
        const ctx = await K.phone(browser, size);
        await ctx.clock.install({ time: K.pinned(o) });
        await ctx.addInitScript((c) => { try { localStorage.setItem("cinema.city", "dubai"); if (c) localStorage.setItem("cinema.card", c); } catch (e) {} }, withCard ? card : "");
        const page = await ctx.newPage();
        const errs = [];
        page.on("pageerror", (e) => errs.push(String(e)));
        await page.goto(srv.base + pagePath, { waitUntil: "load" });
        await page.waitForTimeout(2500);   /* the slice and the discounts are in, prices repriced */
        const got = await count(page);
        const colons = got.filter((x) => x.colon).length;
        report.push({ size, card: withCard ? card : "", n: got.length, colons, nodes: got });
        const label = `${pagePath} ${size} ${withCard ? "with " + card : "no card"}: ${got.length} gold text nodes, ${colons} gold colons`;
        if (max != null) R.check(label + " (≤ " + max + ")", got.length <= +max, got.map((x) => x.text).join(" | "));
        else R.info(label, got.map((x) => x.el + " «" + x.text + "»").join(" | "));
        if (noColons) R.check(`${size} ${withCard ? card : "no card"}: no gold colon`, colons === 0);
        if (errs.length) R.check(`${size}: no page error`, false, errs.join(" ; "));
        await ctx.close();
      }
    }
  } catch (e) {
    R.check("run", false, e.message);
  } finally {
    await browser.close(); srv.stop();
  }
  const jf = o.get("json", null);
  if (jf) fs.writeFileSync(jf, JSON.stringify(report, null, 1));
  process.exit(R.code());
})();
