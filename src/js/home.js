/* home + city: the city's shows from /data/<city>-<date>.json (indexed arrays, see build.slices):
   C[[cid,chain,ar,en]] F[[fid,ar,en]] H[[code,chain|key,ar,en]] P[prices] B[url prefixes]
   S[[cinema i, film i, time, hall i, price i|-1, prefix i|-1, url tail(, table date)]] E[end offsets] L/Li[lang, subs] */
/* a day's slice: the parsed JSON; false when the city has no shows that day (a day the build wrote for no city, or a
   404: the build writes a city's day only when it has shows); null when the fetch failed (the network, a 5xx, the
   offline worker). Kept in core.js's getJSON cache (JC), so the other readers share the one request */
function sliceOf(c, d) {
  var u = "/data/" + c + "-" + d + ".json";
  if (C.days && C.days.indexOf(d) < 0) return Promise.resolve(false);
  return JC[u] || (JC[u] = fetch(u).then(function (r) { return r.ok ? r.json() : r.status === 404 ? false : null; }).catch(function () { return null; }));
}
/* one day's slice as {cinemas, films, shows}; parsed once per URL. A failed fetch is not kept (the next try asks again) */
var PS = {};
/* «HH:MM» + e minutes, as the UAE wall clock reads it: plain minute arithmetic (no DST there), the same as
   hhmm(uae(d + "T" + t) + e min) without two Dates per show (a city's day is thousands of shows, and the desktop
   ticket parses one at start-up to leave a started show) */
function addMin(t, e) {
  var m = Math.floor(((+t.slice(0, 2) * 60 + +t.slice(3, 5) + e) % 1440 + 1440) % 1440);
  return (m < 600 ? "0" : "") + Math.floor(m / 60) + ":" + (m % 60 < 10 ? "0" : "") + (m % 60);
}
/* each show carries `at`, its start in ms, worked out once here from its date's UAE midnight (one Date per day, not one
   per show and per comparison: those were most of the 1.4 s frame when the city's shows arrived, MASTER-PLAN §4.2 #12).
   A day's slice is in start order (build.slices), and today's comes before tomorrow's, so S.shows is too */
function parseSlice(j, d) {
  var o = { cinemas: {}, films: {}, shows: [], bad: j === null, none: j === false };
  if (!j) return o;
  var d0 = uae(d + "T00:00").getTime();
  j.C.forEach(function (c) { o.cinemas[c[0]] = { chain: c[1], ar: c[2], en: c[3] }; });
  j.F.forEach(function (f) { o.films[f[0]] = { ar: f[1], en: f[2] }; });
  j.S.forEach(function (a, n) {
    var h = j.H[a[3]], e = j.E && j.E[n], l = j.Li && j.Li[n] >= 0 ? j.L[j.Li[n]] : null, t = a[2];
    o.shows.push({ c: j.C[a[0]][0], f: j.F[a[1]][0], d: d, t: t, h: h[0], k: h[1].slice(h[1].indexOf("|") + 1), hn: AR ? h[2] : h[3],
      p: a[4] >= 0 ? j.P[a[4]] : null, b: a[5] >= 0 ? j.B[a[5]] + a[6] : (a[6] || null), asof: a[7] || null,
      e: e ? addMin(t, e) : null, lg: l && l[0], sb: l && l[1], at: d0 + (+t.slice(0, 2) * 60 + +t.slice(3, 5)) * 60e3 });
  });
  return o;
}
function daySlice(c, d) {
  var k = c + d, u = "/data/" + c + "-" + d + ".json";
  return PS[k] ? Promise.resolve(PS[k]) : sliceOf(c, d).then(function (j) {
    if (j === null) { delete JC[u]; return parseSlice(null, d); }
    return (PS[k] = parseSlice(j, d));
  });
}
/* the city's slice did not come (a network failure, a 5xx, or no day of it on the server): the page keeps the prices the
   server wrote, says so once (§1.7 «ما قدرنا نحدّث الأوقات…»), never turns a tile into «ما يعرض» (§4.2 #7), and asks
   again at the next minute */
var SLICE_BAD = false;
function sliceStale(on) { SLICE_BAD = on; qa("[data-stale]").forEach(function (e) { e.hidden = !on; }); }
function loadCity() {
  var want = city;
  return Promise.all([daySlice(city, TODAY), daySlice(city, TOMORROW)]).then(function (ds) {
    if (want !== city) return;
    if (ds[0].bad || ds[1].bad && ds[0].none) { S = null; sliceStale(true); return; }
    sliceStale(false);
    var o = { cinemas: {}, films: {}, shows: [], city: want };   /* whose shows these are (bill.js asks) */
    ds.forEach(function (x) {
      Object.keys(x.cinemas).forEach(function (k) { o.cinemas[k] = x.cinemas[k]; });
      Object.keys(x.films).forEach(function (k) { o.films[k] = x.films[k]; });
      o.shows = o.shows.concat(x.shows);
    });
    S = o; renderSched(); renderHome(false);
    if (LOC) applyNear(false);
  });
}

/* a city page on a busy day ships a bounded schedule (times as text, or only the first cinemas per film):
   with the slice in hand, every film's cinemas and times are drawn here, as buttons */
function tmButton(s) {
  return '<button type="button" class="tm" data-start="' + s.t + '"' + (s.e ? ' data-ends="' + s.e + '"' : "") +
    (s.lg ? ' data-lang="' + esc(s.lg) + '"' : "") + (s.sb ? ' data-subs="' + esc(s.sb) + '"' : "") + ">" + s.t + "</button>";
}
function renderSched() {
  var box = q(".sched[data-sched]");
  if (!box || !S) return;
  qa(".srow[data-fid]", box).forEach(function (row) {
    var fid = row.getAttribute("data-fid"), sc = q(".sc", row), by = {}, order = [];
    S.shows.forEach(function (s) {
      if (s.f !== fid || s.d !== TODAY) return;
      if (!by[s.c]) { by[s.c] = []; order.push(s.c); }
      by[s.c].push(s);
    });
    if (!order.length) return;
    sc.innerHTML = order.map(function (c) {
      var hs = {}, ks = [];
      by[c].forEach(function (s) { if (!hs[s.k]) { hs[s.k] = []; ks.push(s.k); } hs[s.k].push(s); });
      ks.sort(function (a, b) { return (a !== "Standard") - (b !== "Standard"); });
      return '<div class="scin" data-cin="' + esc(c) + '" data-chain="' + esc(S.cinemas[c].chain) + '"><a class="cn" href="' + esc(c) + '/">' + esc(nm(S.cinemas[c])) + "</a>" +
        '<div class="times" data-d="' + TODAY + '">' + ks.map(function (k) {
          var h = hs[k][0];
          return '<span class="tl" data-hk="' + esc(k) + '" data-hall="' + esc(h.h) + '">' + (k !== "Standard" ? "<small>" + esc(h.hn) + "</small> " : "") + hs[k].map(tmButton).join("") + "</span>";
        }).join("") + "</div></div>";
    }).join("");
  });
  box.removeAttribute("data-sched");
  marks();
  if (LOC && G) showDistances();
  if (ST.prayer) applyPrayer(); else applyFilters();
}
/* elsewhere, a compact schedule's text times become buttons; their ticket comes from the slice */
function upgradeTimes() {
  qa(".tl").forEach(function (tl) {
    if (q(".tm", tl) || tl.closest(".cgs")) return;   /* a film page's: film.js lays them out itself */
    var sm = q("small", tl), ts = tl.textContent.replace(sm ? sm.textContent : "", "").trim().split(/\s+/).filter(function (t) { return /^\d\d:\d\d$/.test(t); });
    tl.innerHTML = (sm ? sm.outerHTML + " " : "") + ts.map(function (t) { return tmButton({ t: t }); }).join("");
  });
}
function start(s) { return s.at != null ? s.at : uae(s.d + "T" + s.t).getTime(); }
/* does a show pass the time controls («يخلص قبل», «العيال»'s daytime rule) and, with «أخفِ العروض المتقاطعة» on, stay
   clear of Maghrib and Isha in the visitor's city (prayer.js; no clash is known before adhan has loaded)? */
function showOk(s, rt) {
  var sp = showSpan(s.t, s.e, rt);
  if (!endsOk(sp, ST.before) || ST.who === "kids" && !kidsOk(sp)) return false;
  return !(ST.prayer && ST.hide && clashOf(sp, prayersFor(city, s.d)));
}

/* the billboard's «من X درهم»: its film's cheapest ticket for this visitor in this city tonight — only from this
   city's shows; with none still to come (or the city's data never arrived) the cell keeps the island's price for
   this city, the last one known to be right */
function renderFrom(go) {
  if (!S || (S.city && S.city !== city)) return;
  var n = NOW.getTime();
  qa("[data-from]").forEach(function (f) {
    var fid = f.getAttribute("data-from"), b = best(S.shows.filter(function (s) { return s.f === fid && s.d === TODAY && start(s) >= n; }));
    var pe = q(".p", f);
    if (!pe) return;
    if (b) {
      var was = pe.getAttribute("data-shown");
      pe.removeAttribute("data-aed"); pe.removeAttribute("data-wait"); pe.setAttribute("data-shown", fmt(b.pay));
      pe.innerHTML = payCell(b, go, was);
    } else if (pe.hasAttribute("data-wait")) { pe.removeAttribute("data-wait"); pe.innerHTML = priceHTML(pe, go); }
  });
}
/* the desktop hover panel (verdict word + next time): drawn here, on a pointer that hovers, not shipped in every
   tile's markup (fix round 1, I3: 13 KB of a 150 KB page) */
var HOVER = !!(window.matchMedia && window.matchMedia("(hover: hover) and (min-width: 1024px)").matches);
function hoverPanel(el, next) {
  if (!HOVER || el.classList.contains("soon")) return;
  var tp = q(".tp", el), hv = tp && q(".hv", tp);
  if (!tp) return;
  if (!hv) {
    hv = document.createElement("span"); hv.className = "hv"; hv.setAttribute("aria-hidden", "true");
    hv.innerHTML = '<span class="vw"></span><span class="nx"></span>';
    tp.appendChild(hv);
    q(".vw", hv).textContent = (C.v && C.v[el.getAttribute("data-v")]) || "";
  }
  q(".nx", hv).textContent = next || "";
}

/* the rows (MASTER-PLAN §2.1): no film sits in the first 3 slots of two rows. lead(seen, r): the fids of row r reordered
   so its first 3 slots take its films not already up front in an earlier row (`seen`), the rest following in their
   order; null when r has fewer than 4 films or not 3 new ones (the row steps aside). pages/_core/home.py dedupe() is its
   twin for the first paint */
function lead(seen, r) {
  var fresh = r.filter(function (f) { return !seen[f]; });
  if (r.length < 4 || fresh.length < 3) return null;
  var head = fresh.slice(0, 3);
  return head.concat(r.filter(function (f) { return head.indexOf(f) < 0; }));
}
/* a film's poster as the page already draws it (a show card's own, a row tile's or the grid's) */
function posterOf(fid) {
  var p = q('[data-film="' + fid + '"] .pst, .tile[data-fid="' + fid + '"] .pst');
  return p ? p.outerHTML : "";
}
/* «أرخص عرض الليلة»: each film's cheapest show for this visitor (after their card) still to start tonight, cheapest
   first, opening with films no earlier row opens with; one innerHTML for the row. Fewer than 4: the row steps aside */
function renderCheap(row, idx, n, end, seen, go) {
  var box = q("[data-strip]", row), picks = [];
  Object.keys(idx).forEach(function (f) {
    var b = best(idx[f].all.filter(function (s) { return s.at >= n && s.at < end; }));
    if (b) picks.push({ f: f, b: b });
  });
  picks.sort(function (a, b) { return a.b.pay - b.b.pay || a.b.s.at - b.b.s.at || (a.f < b.f ? -1 : 1); });
  var fresh = picks.filter(function (p) { return !seen[p.f]; }).slice(0, 3);
  picks = fresh.concat(picks.filter(function (p) { return fresh.indexOf(p) < 0; })).slice(0, 10);
  row.hidden = picks.length < 4;
  if (row.hidden) return [];
  picks.forEach(function (p) { if (p.b.s.at < NEXT_AT) NEXT_AT = p.b.s.at; });
  box.innerHTML = picks.map(function (p) {
    var s = p.b.s;
    return '<a class="tile shc" href="' + esc(C.base + "film/" + p.f + "/#s-" + showKey(s.c, s.d, s.t, s.k)) + '" data-film="' + esc(p.f) + '"><span class="tp">' + posterOf(p.f) +
      '</span><span class="vh" dir="auto">' + esc(nm(S.films[p.f])) + '</span><span class="st"><b class="num">' + esc(s.t) + "</b> <bdi>" + esc(nm(S.cinemas[s.c])) +
      '</bdi></span><span class="m"><span class="p" data-shown="' + fmt(p.b.pay) + '">' + payCell(p.b, go, null) + "</span></span></a>";
  }).join("");
  return fresh.map(function (p) { return p.f; });
}
/* the rows follow the visitor: «الأكثر عرضاً الليلة» by the city's shows (a film not showing in the city goes to the end),
   «أرخص عرض الليلة» redrawn from the city's slice, then every row's first 3 slots made unique again (dedupe) */
function sortRows(count, idx, n, end, go) {
  var seen = {};
  qa(".rail [data-strip]").forEach(function (box) {
    var r = box.closest(".rail");
    if (r.hasAttribute("data-rail-cheap")) { renderCheap(r, idx, n, end, seen, go).forEach(function (f) { seen[f] = 1; }); return; }
    var els = qa(".tile[data-fid]", box);
    if (!els.length) return;
    if (r.getAttribute("data-rail-sort") === "count") {
      var key = function (el) { return (el.classList.contains("off") ? 1e12 : 0) - (count[el.getAttribute("data-fid")] || 0) * 1e3 + (+el.getAttribute("data-o") || 0); };
      els = els.map(function (e) { return [key(e), e]; }).sort(function (a, b) { return a[0] - b[0]; }).map(function (p) { return p[1]; });
    }
    var fids = els.map(function (el) { return el.getAttribute("data-fid"); }), o = lead(seen, fids);
    r.hidden = !o;
    if (!o) return;
    o.slice(0, 3).forEach(function (f) { seen[f] = 1; });
    var to = o.map(function (f) { return els[fids.indexOf(f)]; }), was = qa(".tile[data-fid]", box);
    if (!to.every(function (e, i) { return e === was[i]; })) to.forEach(function (e) { box.appendChild(e); });
  });
  /* the cheap row's card door: «بعد خصم فزعة ▾» once a card is chosen, else its own words */
  qa("[data-door]").forEach(function (b) {
    b.firstChild.nodeValue = card && C.cards && C.cards[card] ? sub(C.after_card, { card: C.cards[card] }) : b.getAttribute("data-door");
  });
}

/* a tile's line (MASTER-PLAN §2.1): with a card, yours after it and the list price struck («33.60 42»); with no card,
   after 17:00 the next show tonight («التالي 21:30 ريل دبي مول»), by day «من 42»; «السعر في الشباك» with no price;
   «ما يعرض في دبي» when the city's (arrived) shows have none of it */
var FX = AR ? { next: "التالي {t} {cin}" } : { next: "Next {t} {cin}" };
function tileLine(el, showing, fit, b, go, cn) {
  var box = q("[data-cheap]", el);
  if (!box) return;
  if (!showing) { box.innerHTML = '<span class="fw">' + esc(sub(C.not_in_city, { city: cn })) + "</span>"; return; }
  if (!fit.length) return;   /* filtered out of the grid: hidden, its line left as it was */
  if (!b) { box.innerHTML = '<span class="na">' + esc(C.box) + "</span>"; return; }
  var nx = fit[0];
  if (!card && nowMin() >= 1020 && (nx.d === TODAY || nx.t < "03:00")) {
    box.innerHTML = '<span class="nx">' + sub(esc(FX.next), { t: esc(nx.t), cin: "<bdi>" + esc(nm(S.cinemas[nx.c])) + "</bdi>" }) + "</span>"; return;
  }
  var pe = q(".p", box), was = pe && pe.getAttribute("data-shown");
  box.innerHTML = esc(TX.from) + ' <span class="p" data-shown="' + fmt(b.pay) + '">' + payCell(b, go, was) + "</span>" + asofNote(b.s.asof);
}

/* renderHome: every tile of the rows and the grid, redrawn for the visitor's city, card, clock and filters. Rail by rail,
   the ones on screen first, a yield before each (scheduler.yield, else setTimeout 0), so the city's shows arriving never
   hold the page in one long frame (MASTER-PLAN §2.1 «Speed», §4.2 #12: it was 1.4 s at 4× CPU). A newer call stops an
   older one still yielding. */
var HGEN = 0, NEXT_AT = 9e15;
function later() { return window.scheduler && scheduler.yield ? scheduler.yield() : new Promise(function (r) { setTimeout(r, 0); }); }
function renderHome(go) {
  if (!S) return;
  var gen = ++HGEN, cn = C.cities[city] || city, n = NOW.getTime(), count = {}, idx = {}, win = whenWin(ST.when, n), cins = whereSet();
  var H = 3600e3, d0 = n - (n + 4 * H) % (24 * H), end = d0 + (n - d0 < 3 * H ? 3 : 27) * H;   /* tonight: to 03:00 */
  qa("[data-city-name]").forEach(function (el) { el.textContent = cn; });
  var lab = q("[data-city-label]"); if (lab && page === "home") lab.textContent = "";
  S.shows.forEach(function (s) {
    if (s.d === TODAY) count[s.f] = (count[s.f] || 0) + 1;
    if (s.at < n) return;
    var o = idx[s.f] || (idx[s.f] = { all: [], today: [], tmr: [] });
    o.all.push(s); (s.d === TODAY ? o.today : o.tmr).push(s);
  });
  NEXT_AT = 9e15;
  function paint(el) {
    if (el.closest(".similar")) return;
    var fid = el.getAttribute("data-fid"), rt = el.getAttribute("data-runtime"), o = idx[fid] || { all: [], today: [], tmr: [] };
    var grid = el.classList.contains("film"), pool = grid && win ? o.all.filter(function (s) { return s.at >= win[0] && s.at < win[1]; })
      : o.today.length ? o.today : o.tmr;
    var fit = grid ? pool.filter(function (s) { return showOk(s, rt) && (!cins || cins[s.c]); }) : pool, b = best(fit), showing = !!(o.today.length || o.tmr.length);
    el.classList.toggle("off", !showing);
    el.setAttribute("data-pay", b ? b.pay : 1e9);
    el.setAttribute("data-first", fit.length ? fit[0].at : 9e15);
    el.setAttribute("data-fit", fit.length);
    if (fit.length && fit[0].at < NEXT_AT) NEXT_AT = fit[0].at;
    hoverPanel(el, fit.length ? sub(TX.next, { t: fit[0].t, cin: nm(S.cinemas[fit[0].c]) }) : "");
    tileLine(el, showing, fit, b, go, cn);
  }
  /* the batches: each rail's tiles, then the grid's in 24s; those on screen first */
  var vh = innerHeight, batches = [];
  qa(".rail [data-strip], [data-films]").forEach(function (box) {
    var r = box.getBoundingClientRect(), els = qa(".tile[data-fid]", box), on = r.top < vh && r.bottom > 0;
    for (var i = 0; i < els.length; i += 24) batches.push({ on: on, els: els.slice(i, i + 24) });
  });
  batches.sort(function (a, b) { return b.on - a.on; });
  renderFrom(go);
  var p = Promise.resolve();
  batches.forEach(function (bt) {
    p = p.then(later).then(function () { if (gen === HGEN) bt.els.forEach(paint); });
  });
  return p.then(later).then(function () {
    if (gen !== HGEN) return;
    sortRows(count, idx, n, end, go);
    applyFilters();
    lows();
  });
}
/* each minute: a city update that failed is asked for again; once the soonest time a tile or a show card names has
   passed, the tiles move on (a text swap, no motion). Nothing else on them changes by the clock. bindFilters hooks it
   to «minute» */
function homeMinute() {
  if (SLICE_BAD) citySlice();
  else if (S && NOW.getTime() >= NEXT_AT) renderHome(false);
}
