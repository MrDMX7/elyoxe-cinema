/* home + city: the city's shows from /data/<city>-<date>.json (indexed arrays, see build.slices):
   C[[cid,chain,ar,en]] F[[fid,ar,en]] H[[code,chain|key,ar,en]] P[prices] B[url prefixes]
   S[[cinema i, film i, time, hall i, price i|-1, prefix i|-1, url tail(, table date)]] E[end offsets] L/Li[lang, subs] */
function sliceOf(c, d) { return C.days && C.days.indexOf(d) < 0 ? Promise.resolve(null) : getJSON("/data/" + c + "-" + d + ".json"); }
function slice(d) { return sliceOf(city, d); }
/* one day's slice as {cinemas, films, shows}; parsed once per URL */
var PS = {};
function parseSlice(j, d) {
  var o = { cinemas: {}, films: {}, shows: [] };
  if (!j) return o;
  j.C.forEach(function (c) { o.cinemas[c[0]] = { chain: c[1], ar: c[2], en: c[3] }; });
  j.F.forEach(function (f) { o.films[f[0]] = { ar: f[1], en: f[2] }; });
  j.S.forEach(function (a, n) {
    var h = j.H[a[3]], e = j.E && j.E[n], l = j.Li && j.Li[n] >= 0 ? j.L[j.Li[n]] : null;
    o.shows.push({ c: j.C[a[0]][0], f: j.F[a[1]][0], d: d, t: a[2], h: h[0], k: h[1].slice(h[1].indexOf("|") + 1), hn: AR ? h[2] : h[3],
      p: a[4] >= 0 ? j.P[a[4]] : null, b: a[5] >= 0 ? j.B[a[5]] + a[6] : (a[6] || null), asof: a[7] || null,
      e: e ? hhmm(uae(d + "T" + a[2]).getTime() + e * 60e3) : null, lg: l && l[0], sb: l && l[1] });
  });
  return o;
}
function daySlice(c, d) {
  var k = c + d;
  return PS[k] ? Promise.resolve(PS[k]) : sliceOf(c, d).then(function (j) { return (PS[k] = parseSlice(j, d)); });
}
function loadCity() {
  var want = city;
  return Promise.all([daySlice(city, TODAY), daySlice(city, TOMORROW)]).then(function (ds) {
    if (want !== city) return;
    var o = { cinemas: {}, films: {}, shows: [] };
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
      by[c].sort(function (a, b) { return a.t < b.t ? -1 : 1; }).forEach(function (s) { if (!hs[s.k]) { hs[s.k] = []; ks.push(s.k); } hs[s.k].push(s); });
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
    if (q(".tm", tl)) return;
    var sm = q("small", tl), ts = tl.textContent.replace(sm ? sm.textContent : "", "").trim().split(/\s+/).filter(function (t) { return /^\d\d:\d\d$/.test(t); });
    tl.innerHTML = (sm ? sm.outerHTML + " " : "") + ts.map(function (t) { return tmButton({ t: t }); }).join("");
  });
}
function start(s) { return uae(s.d + "T" + s.t).getTime(); }
/* does a show pass the time controls («يخلص قبل», ربعي's late shows)? */
function showOk(s, rt) { var sp = showSpan(s.t, s.e, rt); return endsOk(sp, ST.before) && lateOk(sp, whoPreset(ST.who).late); }

function renderNow() {
  var box = q("[data-now]");
  if (!box || !S) return;
  var n = NOW.getTime();
  var s0 = pickNow(S.shows.map(function (s) { return { at: start(s), km: kmTo(s.c), s: s }; }), n, 45);
  box.hidden = !s0;
  if (!s0) return;
  var s = s0.s, b = best([s]), mins = Math.max(0, Math.round((s0.at - n) / 60000)), bits = [esc(inMinutes(mins, lang))];
  if (s0.km != null) bits.push(esc(sub(TX.away, { km: kmText(s0.km, lang) })));
  if (b) bits.push('<span class="num">' + fmt(b.pay) + "</span> " + esc(C.aed) + ppNote(b.r) + asofNote(s.asof));
  q("[data-now-film]", box).textContent = sub(C.in_cinema, { film: nm(S.films[s.f]), cinema: nm(S.cinemas[s.c]) });
  q("[data-now-where]", box).innerHTML = bits.join(TX.sep);
  flipTime(q("[data-now-time]", box), s.t);
  box.href = C.base + "film/" + s.f + "/";
}

function renderHome(go) {
  if (!S) return;
  var cn = C.cities[city] || city, n = NOW.getTime();
  qa("[data-city-name]").forEach(function (el) { el.textContent = cn; });
  var lab = q("[data-city-label]"); if (lab && page === "home") lab.textContent = AR ? " في " + cn : " in " + cn;
  var up = S.shows.filter(function (s) { return start(s) >= n; }).sort(function (a, b) { return start(a) - start(b); });
  renderNow();
  var grid = q("[data-films]"), tiles = qa(".film[data-fid]", grid || document);
  tiles.forEach(function (el) {
    var fid = el.getAttribute("data-fid"), rt = el.getAttribute("data-runtime");
    var mine = up.filter(function (s) { return s.f === fid; });
    var tonight = mine.filter(function (s) { return s.d === TODAY; }), tmr = mine.filter(function (s) { return s.d === TOMORROW; });
    var pool = tonight.length ? tonight : tmr, fit = pool.filter(function (s) { return showOk(s, rt); });
    var b = best(fit), box = q("[data-cheap]", el);
    el.classList.toggle("off", !pool.length);
    el.setAttribute("data-pay", b ? b.pay : 1e9);
    el.setAttribute("data-first", fit.length ? start(fit[0]) : 9e15);
    el.setAttribute("data-fit", fit.length);
    if (!box) return;
    if (!pool.length) { box.innerHTML = '<span class="fw">' + esc(sub(C.not_in_city, { city: cn })) + "</span>"; return; }
    if (!b) { box.innerHTML = '<span class="fp"><span class="na">' + esc(C.box) + "</span></span>"; return; }
    var pe = q(".fp .p", box), was = pe && pe.getAttribute("data-shown");
    box.innerHTML = '<span class="fp"><span class="p" data-shown="' + fmt(b.pay) + '"><b>' + payHTML(b, go, was) + "</b>" + (b.off ? '<s class="num">' + fmt(b.aed) + "</s>" : "") + ppNote(b.r) + "</span></span>" +
      '<span class="fw">' + esc(nm(S.cinemas[b.s.c])) + TX.sep + esc(b.s.t) + "</span>" + asofNote(b.s.asof);
  });
  /* the featured film's «من X درهم»: its cheapest ticket for this visitor in this city */
  qa("[data-from]").forEach(function (f) {
    var fid = f.getAttribute("data-from"), b = best(up.filter(function (s) { return s.f === fid && s.d === TODAY; }));
    var pe = q(".p", f);
    if (b && pe) {
      var was = pe.getAttribute("data-shown");
      pe.removeAttribute("data-aed"); pe.setAttribute("data-shown", fmt(b.pay));
      pe.innerHTML = "<b>" + payHTML(b, go, was) + "</b>" + (b.off ? '<s class="num">' + fmt(b.aed) + "</s>" : "") + ppNote(b.r);
    }
  });
  applyFilters();
}
