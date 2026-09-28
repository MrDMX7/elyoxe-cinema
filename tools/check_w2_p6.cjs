/* W2-P6 check: the city and cinema pages on a built site (legend MASTER-PLAN §2.4, §2.5, §5.3 W2-P6).

     node tools/check_w2_p6.cjs --out <built site> [--port 8126] [--name w2-p6] [--date 2026-09-26]
          [--city dubai] [--cinema reel-dubai-mall] [--busy vox-mall-of-the-emirates] [--shots DIR] [--label after]

   Serves --out with tools/serve.py on W2-P6's port (8126, bound exclusively; X-Served-By w2-p6-<sha> asserted on the
   document and one asset before anything is measured), then with Chrome (isMobile, hasTouch) at 360x740 DPR3,
   390x844 DPR2, 375x667 DPR2 and 320x640 DPR2, each page's clock pinned with ?now= on the data's own date (--date):
     width      scrollWidth = clientWidth = innerWidth on every page, 0 page errors
     height     /<city>/ is ≤ 6,000 px tall at 390 (21 screens before)
     past       at ?now=<date>T20:00 no time before 20:00 is visible on the city page (every film's times opened) or the
                cinema page; at 23:00 the cinema page folds the ones started under «+N عرض فات» and shows them on a tap
     first      the cinema page's first film block starts at y ≤ 900
     light      the city hero's glow differs between ?now=…T20:00 and ?now=…T01:00 (--lit), and its clock says the time
     caps       the city page shows its first 9 films and 8 cinemas; «اعرض الكل» shows the rest
     caps words no hall or seat label in all capitals except the acronyms (IMAX, MAX, 4DX, MX4D, VIP, XXL, PLF, 2D, 3D, 4K)
     targets    the three ways there, «اعرض الكل», «تصفية», a film's line in «كل الأوقات» are ≥ 44 px tall
     fit        at 320 the clock's tiles and the one-line film titles hold their text (scrollHeight ≤ clientHeight)
   --label before only measures and screenshots (the base build, for the report); it never fails.
   Screenshots (--shots): each page at 360 and 390, the first screen and the whole page (content-visibility off for
   the whole-page shot, so rows below the fold are painted). */
"use strict";
const path = require("path"), fs = require("fs");
const kit = require("./pw_kit.cjs");

const ACR = new Set(["IMAX", "MAX", "4DX", "MX4D", "VIP", "XXL", "PLF", "2D", "3D", "4K"]);
(async () => {
  const o = kit.args(process.argv.slice(2));
  if (!process.argv.includes("--port")) o.port = 8126;
  if (!process.argv.includes("--name")) o.name = "w2-p6";
  if (!process.argv.includes("--size")) o.sizes = ["360x740", "390x844", "375x667", "320x640"];
  const date = o.get("date", (kit.dataTime(o.out) || "2026-09-26T22:56").slice(0, 10));
  const cityP = "/" + o.get("city", "dubai") + "/", cinP = cityP + o.get("cinema", "reel-dubai-mall") + "/", busyP = cityP + o.get("busy", "vox-mall-of-the-emirates") + "/";
  const label = o.get("label", "after"), strict = label !== "before", shots = o.get("shots", null);
  const R = kit.results();
  const check = (name, ok, detail) => strict ? R.check(name, ok, detail) : R.info(name, (ok ? "ok " : "no ") + (detail || ""));
  if (shots) fs.mkdirSync(shots, { recursive: true });
  const srv = await kit.serve(o);
  await kit.assertServed(srv.base, srv.stamp);
  R.info("served", srv.stamp + " on " + srv.base);
  const br = await kit.launch();
  const at = (p, t) => srv.base + p + "?now=" + date + "T" + t;
  async function open(size, url, extra) {
    const ctx = await kit.phone(br, size, extra);
    const p = await ctx.newPage(), errs = [];
    p.on("pageerror", (e) => errs.push(String(e)));
    await p.goto(url, { waitUntil: "load" });
    await p.waitForTimeout(1500);   /* the slice, discounts and the lazy chunk */
    return { ctx, p, errs };
  }
  const width = (p) => p.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth, innerWidth]);
  const slug = (u) => u.replace(/\//g, "_").replace(/^_|_$/g, "") || "home";
  const pages = [cityP, cinP, busyP, "/en" + cityP, "/en" + cinP];
  for (const size of o.sizes) {
    for (const pg of pages) {
      const { ctx, p, errs } = await open(size, at(pg, "21:00"));
      const [sw, cw, iw] = await width(p);
      check(`width ${size} ${pg}`, sw === cw && cw === iw, `scrollWidth ${sw}, clientWidth ${cw}, innerWidth ${iw}`);
      check(`errors ${size} ${pg}`, errs.length === 0, errs.slice(0, 2).join(" | ") || "none");
      const m = await p.evaluate((acr) => {
        const vis = (e) => !!(e.offsetParent || e.getClientRects().length);
        const words = [...document.querySelectorAll("main .hn, main .hp .hh th, main .hp tbody th[scope=row]")].filter(vis).map((e) => e.textContent.trim());
        const caps = words.filter((w) => (w.match(/[A-Za-z0-9]+/g) || []).some((x) => /[A-Z]{2}/.test(x) && x === x.toUpperCase() && !acr.includes(x)));
        const small = [...document.querySelectorAll("main .go-b, main [data-cap-open], main .here-h .chip, main .tt .sf, main .cf-past")].filter(vis)
          .filter((e) => e.getBoundingClientRect().height < 44).map((e) => e.className + " " + Math.round(e.getBoundingClientRect().height));
        const clip = [...document.querySelectorAll(".cclock .d, .tt .sf .t")].filter(vis).filter((e) => e.scrollHeight > e.clientHeight + 1).length;
        const cf = document.querySelector("main .cf"), h = document.documentElement.scrollHeight;
        return { caps, small, clip, cf: cf ? Math.round(cf.getBoundingClientRect().top + scrollY) : null, h, words: words.length };
      }, [...ACR]);
      check(`caps ${size} ${pg}`, m.caps.length === 0, m.caps.length ? m.caps.slice(0, 4).join(", ") : `${m.words} hall and seat labels, none in capitals`);
      check(`targets ${size} ${pg}`, m.small.length === 0, m.small.slice(0, 3).join("; ") || "all ≥ 44 px");
      if (size === "320x640") check(`fit 320 ${pg}`, m.clip === 0, `${m.clip} boxes clip their text`);
      if (pg === cinP || pg === busyP) check(`first ${size} ${pg}`, m.cf != null && m.cf <= 900, `first film block at y ${m.cf}`);
      if (pg === cityP) {
        const ok = size !== "390x844" || m.h <= 6000;
        check(`height ${size} ${pg}`, ok, `${m.h} px (≤ 6,000 at 390)`);
      }
      if (shots && (size === "360x740" || size === "390x844") && !pg.startsWith("/en")) {
        await p.screenshot({ path: path.join(shots, `${slug(pg)}-${size}-${label}.png`) });
        await p.addStyleTag({ content: "*{content-visibility:visible!important}" });
        await p.waitForTimeout(200);
        await p.screenshot({ path: path.join(shots, `${slug(pg)}-${size}-${label}-full.png`), fullPage: true });
      }
      await ctx.close();
    }
  }
  /* past times at 20:00: none visible (the city page's films opened, the cinema page's tomorrow opened) */
  for (const size of ["360x740", "390x844"]) {
    for (const pg of [cityP, cinP, busyP]) {
      const { ctx, p } = await open(size, at(pg, "20:00"));
      const bad = await p.evaluate((d) => {
        document.querySelectorAll("details").forEach((x) => { x.open = true; });
        return [...document.querySelectorAll('main .times[data-d="' + d + '"] .tm[data-start]')]
          .filter((e) => (e.offsetParent || e.getClientRects().length) && e.getAttribute("data-start") < "20:00").map((e) => e.getAttribute("data-start"));
      }, date);
      check(`past 20:00 ${size} ${pg}`, bad.length === 0, bad.length ? `${bad.length} visible: ${bad.slice(0, 5).join(" ")}` : "no time before 20:00 visible");
      await ctx.close();
    }
  }
  /* the fold at 23:00 on the cinema page: started times hidden, «+N عرض فات» says how many, a tap shows them */
  for (const size of ["360x740", "390x844"]) {
    const { ctx, p } = await open(size, at(busyP, "23:00"));
    const f = await p.evaluate((d) => {
      const vis = (e) => !!(e.offsetParent || e.getClientRects().length);
      const early = () => [...document.querySelectorAll('main .times[data-d="' + d + '"] .tm[data-start]')].filter((e) => vis(e) && e.getAttribute("data-start") < "23:00");
      const b = [...document.querySelectorAll("[data-past]")].find(vis);
      const before = early().length, txt = b ? b.textContent : "";
      if (b) b.click();
      const cf = b && b.closest(".cf"), shown = cf ? [...cf.querySelectorAll(".tm.past")].filter(vis).length : 0;
      return { before, txt, shown, n: document.querySelectorAll("[data-past]").length };
    }, date);
    check(`fold 23:00 ${size} ${busyP}`, f.before === 0 && f.n > 0 && f.shown > 0, `${f.before} started times visible, ${f.n} «+N» buttons, first «${f.txt}» shows ${f.shown} on a tap`);
    await ctx.close();
  }
  /* the city hero: its light by the hour, its clock; the caps */
  for (const size of ["360x740", "390x844"]) {
    const glow = {};
    for (const t of ["20:00", "01:00"]) {
      const { ctx, p } = await open(size, at(cityP, t));
      glow[t] = await p.evaluate(() => ({ bg: getComputedStyle(document.body, "::before").backgroundImage, lit: document.body.style.getPropertyValue("--lit"),
        clock: (document.querySelector("[data-cclock] .vh") || {}).textContent }));
      if (t === "20:00") {
        const c = await p.evaluate(() => {
          const vis = (e) => !!(e.offsetParent || e.getClientRects().length);
          const films = () => [...document.querySelectorAll("[data-films] > .film")].filter(vis).length;
          const cins = () => [...document.querySelectorAll(".cins .row.cin")].filter(vis).length;
          const r = { films0: films(), cins0: cins(), all: document.querySelectorAll("[data-films] > .film").length, allc: document.querySelectorAll(".cins .row.cin").length };
          document.querySelectorAll("[data-cap-open]").forEach((b) => { if (vis(b)) b.click(); });
          r.films1 = films(); r.cins1 = cins(); r.focus = document.activeElement && document.activeElement.className;
          return r;
        });
        check(`caps ${size} ${cityP}`, c.films0 === Math.min(9, c.all) && c.cins0 === Math.min(8, c.allc) && c.films1 === c.all && c.cins1 === c.allc,
          `films ${c.films0} of ${c.all} then ${c.films1}; cinemas ${c.cins0} of ${c.allc} then ${c.cins1}; focus on «${c.focus}»`);
      }
      await ctx.close();
    }
    check(`light ${size} ${cityP}`, glow["20:00"].bg !== glow["01:00"].bg && glow["20:00"].clock === "20:00" && glow["01:00"].clock === "01:00",
      `--lit ${glow["20:00"].lit} at 20:00, ${glow["01:00"].lit} at 01:00; the clocks say ${glow["20:00"].clock} and ${glow["01:00"].clock}`);
  }
  await br.close(); srv.stop();
  const bad = R.list.filter((x) => !x.ok).length;
  console.log(`${R.list.length - bad} passed, ${bad} failed`);
  process.exit(strict ? R.code() : 0);
})().catch((e) => { console.error(e); process.exit(1); });
