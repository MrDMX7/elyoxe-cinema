/* live_check.cjs — «built but not visible» guard (round3-gaps, 2026-09-30). Points real Chrome at a built «سينما»
   (the live site or a local build) and says, one line per feature, whether a visitor can actually SEE it:

     node tools/live_check.cjs https://cinema.elyoxe.com
     node tools/live_check.cjs http://127.0.0.1:8163 --now 2026-09-30T12:50 --shots tmp/shots

     --now ISO      the UAE time the pages believe (?now=, core.js): pin it for a local build made from a day's data,
                    so «مزحوم ولا فاضي؟» (a sample under 90 minutes old) can be seen. Live: leave it out.
     --shots DIR    a screenshot per feature and size (PNG)
     --size W×H,…   default 390x844,344x882 (both isMobile, hasTouch)
     --imdb-min F   the share of film pages that must show an IMDb score (default 0.25; 18/82 before round3-gaps)

   Prints «PASS <feature> — detail», «FAIL <feature> — detail» or «SKIP <feature> — why» (a data-dependent feature
   with nothing to show right now, e.g. no occupancy sample under 90 minutes old between two runs). Exit 1 on any FAIL.
   Read-only: GETs and taps inside the page (no booking link is followed, nothing is submitted). Playwright as
   tools/pw_kit.cjs finds it ($PLAYWRIGHT, else the elyoxe site's copy on the laptop), Chrome channel. Run weekly. */
"use strict";
const fs = require("fs"), path = require("path");
const kit = require("./pw_kit.cjs");

const argv = process.argv.slice(2);
const get = (k, d) => { const i = argv.indexOf("--" + k); return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : d; };
const BASE = (argv.find((a) => /^https?:\/\//.test(a)) || "https://cinema.elyoxe.com").replace(/\/+$/, "");
const NOW = get("now", null), SHOTS = get("shots", null), IMDB_MIN = +get("imdb-min", "0.25");
const SIZES = get("size", "390x844,344x882").split(",").map((s) => s.trim()).filter(Boolean);
const LIVE = !/^https?:\/\/(127\.|localhost|\[::1\])/.test(BASE);
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

let failed = 0;
const line = (st, name, detail) => { if (st === "FAIL") failed++; console.log(st + " " + name + (detail ? "  — " + detail : "")); };
const check = (name, ok, detail) => line(ok ? "PASS" : "FAIL", name, detail);
const skip = (name, why) => line("SKIP", name, why);
const url = (p, extra) => { const u = new URL(BASE + p); if (NOW) u.searchParams.set("now", NOW); if (extra) for (const k in extra) u.searchParams.set(k, extra[k]); return u.toString(); };
const shot = async (p, name, size, full) => { if (SHOTS) await p.screenshot({ path: path.join(SHOTS, `${name}-${size}.png`), fullPage: !!full }); };
const nowMs = () => NOW ? new Date(NOW.length <= 16 ? NOW + ":00+04:00" : NOW).getTime() : Date.now();

async function fetchText(u) {
  for (let i = 0; i < 3; i++) {
    try { const r = await fetch(u, { headers: { "accept-encoding": "gzip" } }); return { status: r.status, type: r.headers.get("content-type") || "", text: await r.text() }; }
    catch (e) { if (i === 2) return { status: 0, type: "", text: "" }; }
  }
}
async function fetchBuf(u) {
  const r = await fetch(u); return { status: r.status, type: r.headers.get("content-type") || "", buf: Buffer.from(await r.arrayBuffer()) };
}
/* a WebP's pixel size from its RIFF header (VP8 / VP8L / VP8X) */
function webpSize(b) {
  if (b.length < 30 || b.toString("ascii", 0, 4) !== "RIFF" || b.toString("ascii", 8, 12) !== "WEBP") return null;
  const k = b.toString("ascii", 12, 16);
  if (k === "VP8X") return { w: 1 + b.readUIntLE(24, 3), h: 1 + b.readUIntLE(27, 3) };
  if (k === "VP8 ") return { w: b.readUInt16LE(26) & 0x3fff, h: b.readUInt16LE(28) & 0x3fff };
  if (k === "VP8L") { const n = b.readUInt32LE(21); return { w: 1 + (n & 0x3fff), h: 1 + ((n >> 14) & 0x3fff) }; }
  return null;
}
async function pool(items, n, fn) {
  const out = []; let i = 0;
  await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) { const j = i++; out[j] = await fn(items[j]); } }));
  return out;
}
const has = (h, re) => re.test(h);

(async () => {
  console.log(`INFO base ${BASE}${NOW ? "  now " + NOW : ""}  sizes ${SIZES.join(", ")}`);
  /* ------------------------------------------------ the pages, read as a crawler reads them (no browser) */
  const sm = await fetchText(BASE + "/sitemap.xml");
  const locs = [...sm.text.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => new URL(m[1]).pathname);
  const filmPaths = [...new Set(locs.filter((p) => /^\/film\/[^/]+\/$/.test(p)))];
  const cinPaths = [...new Set(locs.filter((p) => /^\/(dubai|abu-dhabi|sharjah|ajman|al-ain|fujairah|ras-al-khaimah|umm-al-quwain)\/[^/]+\/$/.test(p)))];
  const films = (await pool(filmPaths, 6, async (p) => ({ p, h: (await fetchText(BASE + p)).text }))).filter((x) => x.h);
  const showing = films.filter((x) => !/data-archived="1"/.test(x.h));
  console.log(`INFO ${films.length} film pages (${showing.length} showing), ${cinPaths.length} cinema pages in the sitemap`);

  /* 1. IMDb */
  const withImdb = showing.filter((x) => has(x.h, /<dt>IMDb<\/dt><dd><span class="num">\d/));
  const share = showing.length ? withImdb.length / showing.length : 0;
  check("imdb-coverage", share >= IMDB_MIN, `${withImdb.length}/${showing.length} showing films show an IMDb score (floor ${Math.round(IMDB_MIN * 100)}%)`);

  /* 2. hero release line: wherever «عن الفيلم» dates the film, the hero says it too */
  const hero = (h) => { const a = h.indexOf('<section class="fhero'), b = h.indexOf("</section>", a); return a >= 0 ? h.slice(a, b) : ""; };
  const aboutRel = showing.filter((x) => has(x.h, /<dt>في السينما من<\/dt>/));
  const heroRel = showing.filter((x) => has(hero(x.h), /class="frel"[^>]*>في السينما من [^<]*?(<bdi[^>]*>[^<]*<\/bdi>)?[^<]*الأسبوع \d+/));
  const miss = aboutRel.filter((x) => !heroRel.includes(x)).map((x) => x.p);
  check("hero-release-week", heroRel.length > 0 && miss.length === 0,
    `${heroRel.length} film heroes say «في السينما من …، الأسبوع N»` + (miss.length ? `; missing on ${miss.slice(0, 3).join(" ")}` : ""));

  /* 3a. «ليش يستاهل؟» right under the verdict, for every film with a number to back it */
  const rated = showing.filter((x) => has(hero(x.h), /class="basis rates"|<dt>IMDb<\/dt>/) || has(x.h, /<dt>IMDb<\/dt>/));
  const whyAfterVerdict = (h) => /<\/p>(<button[^>]*data-fv-more[^>]*>[^<]*<\/button>)?<\/div><details class="fwhy" data-why="(intel|numbers)"><summary>(<span>)?ليش/.test(hero(h));
  const noWhy = rated.filter((x) => !whyAfterVerdict(x.h)).map((x) => x.p);
  const fallback = showing.filter((x) => has(hero(x.h), /data-why="numbers"/));
  check("why-under-verdict", rated.length > 0 && noWhy.length === 0,
    `${rated.length - noWhy.length}/${rated.length} rated films have «ليش يستاهل؟» directly under the verdict (${fallback.length} from the numbers, no intel file)` +
    (noWhy.length ? `; missing on ${noWhy.slice(0, 3).join(" ")}` : ""));

  /* 3b. every film WITH intel: every section, and the fun fact's row hidden when it has none */
  const intelFilms = showing.filter((x) => has(x.h, /data-intel="1"/)), intelFilm = intelFilms[0];
  if (!intelFilm) skip("intel-sections", "no showing film carries an intel file today");
  else {
    const need = { reasons: /data-why="intel"/, ending: /<summary>اشرح النهاية<\/summary>/,
      qa: /<summary>أسئلة عن الفيلم<\/summary>/, "no-spoilers switch": /class="i-ns"><input type="checkbox" checked/ };
    const probs = [], facts = [];
    for (const x of intelFilms) {
      const gone = Object.keys(need).filter((k) => !need[k].test(x.h));
      if (/class="i-fact"><b>[^<]*<\/b>\s*(<span class="src">[^<]*<\/span>)?<\/p>/.test(x.h)) gone.push("an EMPTY fun-fact row");
      if (gone.length) probs.push(`${x.p} ${gone.join(", ")}`);
      facts.push(/class="i-fact"/.test(x.h) ? 1 : 0);
    }
    const cons = intelFilms.filter((x) => /class="consensus"/.test(x.h)).length;
    const aud = intelFilms.filter((x) => /class="i-d i-audience"/.test(x.h)).length;   // optional: hidden when no source has audience reviews
    check("intel-sections", !probs.length, `${intelFilms.length} films with intel: reasons, ending, Q&A, «بدون حرق» on each; audience on ${aud}; consensus on ${cons}; ` +
      `fun fact shown on ${facts.filter(Boolean).length}, row hidden (null) on ${facts.filter((f) => !f).length}` + (probs.length ? `; PROBLEMS: ${probs.slice(0, 3).join(" | ")}` : ""));
  }

  /* 4. cinema photos */
  const cins = await pool(cinPaths, 6, async (p) => ({ p, h: (await fetchText(BASE + p)).text }));
  const withPhoto = cins.filter((x) => has(x.h, /class="head wrap chead chead-photo"/));
  check("cinema-photos", withPhoto.length > 0, `${withPhoto.length}/${cins.length} cinema pages open on a real photo of the cinema`);

  /* 10a. story cards: linked from the hero's share row, 1080x1920 WebP */
  // hero-clean (2026-09-30): the card moved from the hero row into the «شارك» sheet — look for it anywhere on the page
  const storyLinks = showing.map((x) => (x.h.match(/href="([^"]+-story-[0-9a-f]{12}\.webp)"/) || [])[1]).filter(Boolean);
  let storyOk = false, storyDetail = `${storyLinks.length}/${showing.length} showing films link a Stories card in the «شارك» sheet`;
  if (storyLinks.length) {
    const u = storyLinks[0].replace(/^https:\/\/cinema\.elyoxe\.com/, LIVE ? "https://cinema.elyoxe.com" : BASE);
    const r = await fetchBuf(u), sz = webpSize(r.buf);
    storyOk = r.status === 200 && /image\/webp/.test(r.type) && sz && sz.w === 1080 && sz.h === 1920;
    storyDetail += `; ${u.split("/").pop()} → ${r.status} ${r.type} ${sz ? sz.w + "x" + sz.h : "?"}`;
  }
  // Stories cards fill 10 per run (steps/og.py), newest films first: a working card with a growing share passes
  check("story-images", storyOk && storyLinks.length >= showing.length * 0.25, storyDetail);

  /* ------------------------------------------------ in Chrome, at each size */
  const br = await kit.launch();
  const ctxFor = (size, extra) => {
    const [w, h] = size.split("x").map(Number);
    return br.newContext(Object.assign({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
      locale: "ar-AE", timezoneId: "Asia/Dubai", serviceWorkers: "block" }, extra || {}));
  };
  const occ = JSON.parse((await fetchText(BASE + "/data/occupancy.json")).text || "{}");
  const seatIx = JSON.parse((await fetchText(BASE + "/data/seats/index.json")).text || "[]");
  const cinCity = {}; cinPaths.forEach((p) => { const m = p.split("/"); cinCity[m[2]] = m[1]; });

  for (const size of SIZES) {
    const ctx = await ctxFor(size);
    const p = await ctx.newPage(), errs = [];
    p.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
    const noHScroll = async () => p.evaluate(() => document.scrollingElement.scrollWidth <= window.innerWidth + 1);

    /* 5. «نجوم الليلة» */
    await p.goto(url("/"), { waitUntil: "load" }); await p.waitForTimeout(800);
    const stars = p.locator("a.tile.star");
    const nStars = await stars.count();
    if (nStars) { await stars.first().scrollIntoViewIfNeeded(); await p.waitForTimeout(300); }
    const starInfo = await p.evaluate(async () => {
      const a = [...document.querySelectorAll("a.tile.star")];
      for (const x of a) { const i = x.querySelector("img"); if (i) { i.loading = "eager"; if (!i.complete) await new Promise((r) => { i.onload = i.onerror = r; setTimeout(r, 4000); }); } }
      return a.map((x) => ({ href: x.getAttribute("href"), ok: !!(x.querySelector("img") && x.querySelector("img").naturalWidth > 0), name: (x.querySelector(".t") || {}).textContent }));
    });
    const bad = starInfo.filter((s) => !s.ok || !/\/film\/[^/]+\/$/.test(s.href || ""));
    await shot(p, "stars", size);
    check(`stars ${size}`, nStars >= 6 && nStars <= 8 && !bad.length, `${nStars} faces (want 6–8)` + (bad.length ? `; ${bad.length} without a photo or a film link` : "") +
      `: ${starInfo.map((s) => s.name).join("، ")}`);
    check(`no-hscroll home ${size}`, await noHScroll());

    /* 6a. the dock: tap a time, the paper stub rises with «احجز» */
    /* the busiest films first (most time buttons in their HTML): the first with a time still to come on screen */
    const byTimes = showing.map((x) => ({ x, n: (x.h.match(/class="tm/g) || []).length })).filter((y) => y.n).sort((a, b) => b.n - a.n);
    let pickFilm = null, tm = null;
    for (const { x } of byTimes.slice(0, 6)) {
      await p.goto(url(x.p), { waitUntil: "load" }); await p.waitForTimeout(700);
      const c = p.locator(".cgs .tm[data-start]:not(.past):visible").first();
      if (await c.count()) { pickFilm = x; tm = c; break; }
    }
    if (!tm) skip(`dock ${size}`, "no bookable time visible now on the six busiest films");
    else {
      await tm.scrollIntoViewIfNeeded(); await tm.click(); await p.waitForTimeout(900);
      const dk = await p.evaluate(() => {
        const d = document.querySelector("[data-dock]"), b = d && d.querySelector("[data-dk-book]"), perf = d && d.querySelector(".perf");
        if (!d || d.hidden || !d.offsetHeight) return null;
        const rb = b.getBoundingClientRect(), rp = perf.getBoundingClientRect(), rtl = document.documentElement.dir === "rtl";
        return { paper: d.classList.contains("paper"), book: b.textContent.trim(), href: b.href, overlap: rtl ? rb.left < rp.right - 1 : rb.right > rp.left + 1 };
      });
      await shot(p, "dock", size);
      check(`dock ${size}`, dk && dk.paper && /احجز/.test(dk.book) && /^https?:/.test(dk.href) && !dk.overlap,
        dk ? `«${dk.book}» → ${dk.href.slice(0, 60)}${dk.overlap ? "; the button runs over the perforation" : ""}` : "no dock after tapping a time");
    }
    check(`no-hscroll film ${size}`, await noHScroll());

    /* 3c. «بدون حرق» visible next to the spoilers, and it gates them */
    if (intelFilm) {
      await p.goto(url(intelFilm.p), { waitUntil: "load" }); await p.waitForTimeout(500);
      const sw = p.locator(".i-ns").first();
      await sw.scrollIntoViewIfNeeded();
      const end = p.locator(".i-spoiler summary", { hasText: "اشرح النهاية" }).first();
      await end.click(); await p.waitForTimeout(200);
      const gated = await p.evaluate(() => { const d = document.querySelector(".i-spoiler[open]"); return d && getComputedStyle(d.querySelector(".i-body")).display === "none" && getComputedStyle(d.querySelector(".i-gate")).display !== "none"; });
      const near = await p.evaluate(() => { const a = document.querySelector(".i-ns").getBoundingClientRect(), b = document.querySelector(".i-spoiler summary").getBoundingClientRect(); return a.height > 0 && Math.abs(b.top - a.bottom) < 160; });
      await shot(p, "spoilers-on", size);
      await sw.click(); await p.waitForTimeout(200);
      const open = await p.evaluate(() => { const d = document.querySelector(".i-spoiler[open]"); return d && getComputedStyle(d.querySelector(".i-body")).display !== "none"; });
      await shot(p, "spoilers-off", size);
      check(`no-spoilers-switch ${size}`, gated && near && open, `visible right above «اشرح النهاية»: ${near}; on hides the ending: ${gated}; off shows it: ${open}`);
      await p.locator(".fwhy summary").first().scrollIntoViewIfNeeded();
      await p.locator(".fwhy summary").first().click(); await p.waitForTimeout(200);
      await shot(p, "why-intel", size);
    }
    if (fallback.length) {
      await p.goto(url(fallback[0].p), { waitUntil: "load" }); await p.waitForTimeout(400);
      await p.locator(".fwhy summary").first().click(); await p.waitForTimeout(200);
      const n = await p.locator(".fwhy[open] li").count();
      await shot(p, "why-fallback", size);
      check(`why-fallback ${size}`, n > 0, `${fallback[0].p}: ${n} reasons from the numbers, opened with one tap`);
    }
    if (heroRel.length) {
      await p.goto(url(heroRel[0].p), { waitUntil: "load" }); await p.waitForTimeout(300);
      const vis = await p.evaluate(() => { const e = document.querySelector(".fhero .frel"); return e && e.getBoundingClientRect().height > 0 ? e.textContent : null; });
      await shot(p, "hero-release", size);
      check(`hero-release-visible ${size}`, !!vis, vis || "the line is not drawn");
    }

    /* 6b/6c. best seat and «مزحوم ولا فاضي؟»: a show with a sample under 90 minutes old, still to start */
    const nowS = nowMs() / 1000;
    const fresh = Object.entries(occ.o || {}).map(([k, v]) => ({ k, v: v[0] })).filter(({ k, v }) => {
      const [cin, , d, t] = k.split("|"); const start = new Date(`${d}T${t}:00+04:00`).getTime() / 1000;
      return seatIx.includes(cin) && nowS - v[3] < 85 * 60 && nowS - v[3] > -300 && start > nowS + 300 && v[1] > 0 && cinCity[cin];
    });
    if (!fresh.length) {
      const newest = Math.max(0, ...Object.values(occ.o || {}).map((v) => v[0][3]));
      skip(`best-seat ${size}`, `no seat sample under 90 minutes old right now (newest ${newest ? Math.round(nowS / 60 - newest / 60) + " min old" : "none"})`);
      skip(`busy-or-quiet ${size}`, "same: «مزحوم ولا فاضي؟» shows only for a sample under 90 minutes old");
    } else {
      let got = null;
      for (const { k } of fresh.slice(0, 6)) {
        const [cin, fid, d, t] = k.split("|");
        await p.goto(url(`/film/${fid}/`, { city: cinCity[cin] }), { waitUntil: "load" }); await p.waitForTimeout(700);
        if (d !== await p.evaluate(() => { const b = document.querySelector('[data-day][aria-pressed="true"]'); return b && b.getAttribute("data-day"); })) {
          const db = p.locator(`[data-day="${d}"]`); if (await db.count()) { await db.click(); await p.waitForTimeout(300); }
        }
        const b = p.locator(`[data-cin="${cin}"] .tm[data-start="${t}"]:visible`).first();
        if (!(await b.count())) continue;
        await b.scrollIntoViewIfNeeded(); await b.click(); await p.waitForTimeout(1500);
        got = await p.evaluate(() => { const f = document.querySelector("[data-tk-hall] figcaption"); return f ? f.textContent : null; });
        if (got) {
          const more = p.locator("[data-dk-open]"); if (await more.isVisible().catch(() => false)) { await more.click(); await p.waitForTimeout(500); }
          await shot(p, "ticket-seat", size);
          const close = p.locator(".sheet:not([hidden]) [data-sheet-close]").first(); if (await close.count()) await close.click().catch(() => {});
          got = { k, cap: got }; break;
        }
      }
      check(`best-seat ${size}`, got && /أحسن مقعد متاح/.test(got.cap), got ? `${got.k}: «${got.cap.trim().slice(0, 90)}»` : "no ticket hall drawing for a fresh show");
      check(`busy-or-quiet ${size}`, got && /مزحوم ولا فاضي؟/.test(got.cap), got ? "kicker on the fresh ticket" : "no ticket drawn");
    }

    /* 6d. «سينمتي»: pin a cinema, it stays pinned, «قائمتي» lists it */
    const cinP = (withPhoto[0] || cins[0]).p, cid = cinP.split("/")[2];
    await p.goto(url(cinP), { waitUntil: "load" }); await p.waitForTimeout(900);
    const fav = p.locator(".fav[data-fav]");
    const favVis = await fav.isVisible().catch(() => false);
    let favOk = false, favDetail = "the «سينمتي» button is not visible";
    if (favVis) {
      await shot(p, "cinema-head", size);
      await fav.click(); await p.waitForTimeout(200);
      await p.reload({ waitUntil: "load" }); await p.waitForTimeout(900);
      const pressed = await fav.getAttribute("aria-pressed");
      const stored = await p.evaluate(() => { try { return (JSON.parse(localStorage.getItem("cinema.me")) || {}).cins || []; } catch (e) { return []; } });
      const meTab = p.locator("[data-me-tab]").first();
      let listed = false;
      if (await meTab.isVisible().catch(() => false)) {
        await meTab.click(); await p.waitForTimeout(600);
        listed = await p.evaluate((c) => !!document.querySelector(`#sheet-me [data-me-favs] a[href$="/${c}/"]`), cid);
        await shot(p, "my-cinemas", size);
      }
      favOk = pressed === "true" && stored.includes(cid) && listed;
      favDetail = `${cid}: pressed after reload ${pressed}, kept ${stored.includes(cid)}, in «قائمتي» ${listed}`;
      await p.evaluate(() => localStorage.removeItem("cinema.me"));
    }
    check(`my-cinema ${size}`, favOk, favDetail);
    if (withPhoto.length) {
      await p.goto(url(withPhoto[0].p), { waitUntil: "load" }); await p.waitForTimeout(700);
      const ph = await p.evaluate(() => { const i = document.querySelector(".chead-bd img"); return i && i.complete && i.naturalWidth > 0 ? i.naturalWidth : 0; });
      await shot(p, "cinema-photo", size);
      check(`cinema-photo-drawn ${size}`, ph > 0, `${withPhoto[0].p}: header photo ${ph ? ph + " px wide, loaded" : "not loaded"}`);
    }
    check(`no-hscroll cinema ${size}`, await noHScroll());

    /* 6e. Arabic search finds the transliterations */
    await p.goto(url("/"), { waitUntil: "load" }); await p.waitForTimeout(500);
    const cases = [["أفنجرز", /\/film\/avengers[^/]*\//, "Avengers"], ["فوكس", /\/[a-z-]+\/vox-[^/]+\//, "a VOX cinema"], ["ايماكس", /imax/i, "IMAX"]];
    const res = [];
    for (const [qq, re, what] of cases) {
      await p.locator("[data-search]").first().click();
      await p.waitForSelector("#srch:not([hidden])", { timeout: 15000 }); await p.waitForTimeout(400);
      await p.fill("#srch-input", qq); await p.waitForTimeout(600);
      const hrefs = await p.$$eval("#srch .srch-r a", (a) => a.map((x) => x.getAttribute("href")));
      res.push([qq, what, hrefs.some((h) => re.test(h)), hrefs.length]);
      if (qq === "أفنجرز") await shot(p, "search", size);
      await p.keyboard.press("Escape"); await p.waitForTimeout(200);
    }
    check(`arabic-search ${size}`, res.every((r) => r[2]), res.map((r) => `«${r[0]}» → ${r[1]} ${r[2] ? "found" : "NOT found"} (${r[3]} rows)`).join("; "));
    if (errs.length) line("INFO", `page errors ${size}`, errs.slice(0, 3).join(" | "));
    await ctx.close();
  }

  /* 6f. the iOS install hint: iOS Safari only */
  const UA = {
    safari: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    crios: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0.0.0 Mobile/15E148 Safari/604.1",
    android: "Mozilla/5.0 (Linux; Android 14; SM-F936B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
  };
  const hint = async (ua, asSafari) => {
    const c = await ctxFor(SIZES[0], { userAgent: ua });
    await c.addInitScript((s) => {
      try { localStorage.setItem("cinema.visits", "3"); sessionStorage.setItem("cinema.seen", "1"); } catch (e) {}
      if (s) {   /* the engine as real Safari presents it: no window.chrome, Apple's vendor, the iPhone platform */
        try { delete window.chrome; } catch (e) {}
        Object.defineProperty(window, "chrome", { get: () => undefined, configurable: true });
        Object.defineProperty(Navigator.prototype, "vendor", { get: () => "Apple Computer, Inc.", configurable: true });
        Object.defineProperty(Navigator.prototype, "platform", { get: () => "iPhone", configurable: true });
      }
    }, !!asSafari);
    const pg = await c.newPage();
    await pg.goto(url("/"), { waitUntil: "load" }); await pg.waitForTimeout(1500);
    const shown = await pg.evaluate(() => { const b = document.querySelector(".inst [data-io]"); return !!(b && b.closest(".inst").offsetHeight > 0); });
    if (asSafari) await shot(pg, "ios-hint", SIZES[0]);
    await c.close();
    return shown;
  };
  const onSafari = await hint(UA.safari, true), onCriOS = await hint(UA.crios, false), onAndroid = await hint(UA.android, false), onSpoof = await hint(UA.safari, false);
  check("ios-install-hint", onSafari && !onCriOS && !onAndroid && !onSpoof,
    `iOS Safari ${onSafari ? "shows" : "does NOT show"}; Chrome on iPhone ${onCriOS ? "SHOWS" : "hidden"}; Android Chrome ${onAndroid ? "SHOWS" : "hidden"}; Chromium pretending to be Safari ${onSpoof ? "SHOWS" : "hidden"}`);

  await br.close();
  console.log(failed ? `\n${failed} FAIL` : "\nall PASS (SKIP lines are data-dependent: nothing to show at this hour)");
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error("FAIL live_check crashed: " + (e && e.stack || e)); process.exit(2); });
