/* «اللوحة», the live half: a lazy chunk (K = window.CINEMA; legend W2-P2a; MASTER-PLAN §2.1, §2.2, §5.3 W2-P2) on every
   page with a board and on film pages. The renderer (src/js/board-paint.js, window.CB) draws and keeps the minute; this
   file feeds it, through the bundle's few helpers (K.bd, src/js/board.js):
   - CB.src: once the city's shows are in (main.js «slice» on home and a city page; loaded here for a cinema page and the
     404 when the island runs low, CB.low), the rows come from every show of the city, with the visitor's distance
     (near.js), and CB.done reprices them after the visitor's card (prices.js). A slice that failed changes nothing;
   - a new city (the pill, /geo) is drawn at once from the island (CB.go), then from its slice;
   - a shared minute («21:00 5 أفلام») opens the sheet of those shows;
   - it says what it drew: K.emit("board", entries). K.rankBoost(show) (W3-P1, «سينمتي») floats a favourite cinema first
     inside the same 10 minutes; until then there is none;
   - «أقرب عرض لك» on a film page. */
var B = K && K.bd, X = null, of = null, loc = 0, g = 0, rs = null, busy = 0;
if (!B) return;
function en(t) { return K.AR && !/[؀-ۿ]/.test(t) ? 1 : 0; }
function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
function at(s) { return Math.round(K.uae(s.d + "T" + s.t).getTime() / 6e4); }
function lowest(s) { var lo = 0; (s.p || []).forEach(function (p) { if (p[1] > 0 && (!lo || p[1] < lo)) lo = p[1]; }); return lo && !s.asof ? K.fmt(lo) : 0; }
/* a slice's shows (all, or one cinema's) as the painter's rows, in the board's order: start (a favourite first inside
   the same 10 minutes), then distance, cinema, film, key: pages/board.py's order when nothing is known */
function rows(Y, cid) {
  var fs = {}, cs = {}, out = [], bo = K.rankBoost;
  Y.shows.forEach(function (s) {
    if (cid && s.c !== cid) return;
    var fn = B.nm(Y.films[s.f]), cn = B.nm(Y.cinemas[s.c]), km = B.km(s.c);
    out.push({ at: at(s), f: fs[s.f] || (fs[s.f] = [s.f, K.esc(fn), en(fn)]), c: cs[s.c] || (cs[s.c] = [s.c, K.esc(cn), en(cn), Y.cinemas[s.c].chain]),
      h: [s.h, s.k], p: lowest(s), k: K.showKey(s.c, s.d, s.t, s.k), km: km == null ? "" : B.kmt(km, K.lang), v: km == null ? 1e9 : km, o: bo ? +bo(s) || 0 : 0 });
  });
  return out.sort(function (a, b) {
    return Math.floor(a.at / 10) - Math.floor(b.at / 10) || b.o - a.o || a.at - b.at || a.v - b.v || cmp(a.c[0], b.c[0]) || cmp(a.f[0], b.f[0]) || cmp(a.k, b.k);
  });
}
/* the rows the painter reads: its city's (or cinema's) shows once they are in, else null (the island) */
function src(key) {
  var cin = K.page === "cinema", Y = cin || K.page === "404" ? X : B.S();
  if (!Y || !Y.shows.length || Y.city !== (cin ? B.pc : key)) return null;
  if (of !== Y || loc !== B.loc() || g !== B.G()) { rs = rows(Y, cin ? key : null); of = Y; loc = B.loc(); g = B.G(); }
  return rs;
}
/* a cinema page and the 404 have no slice of their own: when the island runs low, the city's two days */
function load() {
  var c = K.page === "cinema" ? B.pc : K.city(), dd = B.days();
  if (busy || X && X.city === c) return;
  busy = 1;
  Promise.all([B.day(c, dd[0]), B.day(c, dd[1])]).then(function (ds) {
    var o = { cinemas: {}, films: {}, shows: [], city: c };
    ds.forEach(function (x) {
      for (var k in x.cinemas) o.cinemas[k] = x.cinemas[k];
      for (k in x.films) o.films[k] = x.films[k];
      o.shows = o.shows.concat(x.shows);
    });
    busy = 0;
    if (o.shows.length) { X = o; window.CB.draw(); }
  });
}
function price(r) { K.qa(".p[data-aed]", r).forEach(function (el) { el.innerHTML = B.price(el, false); }); }
/* what the painter drew: the price after the card, the cheapest lit, «N تبدأ خلال ساعة» (a desktop, from the slice) */
function done(b, es) {
  var n = K.q("[data-board-n]", b), t = window.CB.now(), c = 0;
  price(b); B.lows();
  if (n && rs && of === B.S()) { rs.forEach(function (r) { if (r.at >= t && r.at < t + 60) c++; }); n.textContent = c ? window.CB.I.s.h.replace("{n}", c) : ""; }
  K.emit("board", es);
}
/* a shared minute's row: its shows in the sheet (with no script the row is the first film's show link) */
function sheet(e) {
  var CB = window.CB, a = e.target.closest && e.target.closest(".br.bx"), sh = document.getElementById("sheet-board"), x;
  if (!a || !sh || !CB.es) return;
  x = CB.es.filter(function (y) { return y.x && CB.href(y) === a.getAttribute("href"); })[0];
  if (!x) return;
  e.preventDefault();
  var h = K.q("h2", sh), box = K.q("[data-bsheet]", sh), now = CB.now();
  box.innerHTML = x.x.map(function (r) { return CB.row({ at: x.at, r: r }, now); }).join("");
  price(box);
  if (!h.hasAttribute("data-t")) h.setAttribute("data-t", h.textContent);
  h.textContent = h.getAttribute("data-t").replace("{t}", CB.hm(x.at));
  B.sheet("sheet-board", a);
}
/* the minute (MASTER-PLAN §1.3): one timeout aligned to the next UAE :00, armed only while the board is on screen and
   the page is seen (never a free interval). Back on screen, back to the tab or back from the bfcache, it catches up at
   once, with no motion */
var T = null, seen = 1, ticks = 0;
function arm() {
  var CB = window.CB;
  clearTimeout(T); T = null;
  if (seen && !document.hidden) T = setTimeout(function () { T = null; ticks++; CB.draw(1); arm(); }, 6e4 - (Date.now() + CB.F) % 6e4 + 30);
}
function wake() { var CB = window.CB; if (seen && !document.hidden && CB.last !== CB.now()) CB.draw(); arm(); }
function attach(CB) {
  if (CB.src) return;
  CB.src = src; CB.done = done;
  CB.st = function () { return { armed: !!T, ticks: ticks }; };
  if (K.page === "cinema" || K.page === "404") CB.low = load;
  K.on("slice", function () { CB.draw(); });
  K.on("city", function (c) { CB.go(c); });
  document.addEventListener("click", sheet);
  /* a city chosen (or named by /geo) before this file arrived */
  if (CB.I.g === "city" && CB.k !== K.city()) CB.go(K.city()); else CB.draw();
  document.addEventListener("visibilitychange", wake);
  window.addEventListener("pagehide", function () { clearTimeout(T); T = null; });
  window.addEventListener("pageshow", function (e) { if (e.persisted) wake(); });
  if (window.IntersectionObserver) new IntersectionObserver(function (es) { seen = es[es.length - 1].isIntersecting; wake(); }).observe(CB.b);
  else arm();
}
window.CBlive = attach;
if (window.CB) attach(window.CB);

/* «أقرب عرض لك»: this film's soonest show in the visitor's city that they can still reach (travel as the pick counts
   it: 25 min with no location, km × 1.6 + 10 with one, and 10 more), from the city's two days; the minute moves it on.
   The box was held before the first paint only where the build knows a show of this film */
var f = K.q('[data-board="film"]');
function first() {
  var fid = document.body.getAttribute("data-fid"), W = JSON.parse(f.getAttribute("data-s") || "{}"), c = K.city(), dd = B.days();
  if ((" " + f.getAttribute("data-cities") + " ").indexOf(" " + c + " ") < 0) { f.hidden = true; f.classList.remove("hold"); return; }
  Promise.all([B.day(c, dd[0]), B.day(c, dd[1]), B.loc() && !B.G() ? B.geo() : 0]).then(function (ds) {
    var now = Math.floor(K.now().getTime() / 6e4), b = null;
    ds.slice(0, 2).forEach(function (x) {
      x.shows.forEach(function (s) {
        if (s.f !== fid) return;
        var a = at(s), km = B.km(s.c), v = km == null ? 1e9 : km;
        if (a < now + (km == null ? 35 : Math.round(km * 1.6) + 20) || b && (a > b.a || a === b.a && v >= b.v)) return;
        b = { s: s, a: a, km: km, v: v, c: x.cinemas[s.c] };
      });
    });
    f.classList.remove("hold");
    if (!b) { f.hidden = true; return; }
    var s = b.s, cn = B.nm(b.c), n = b.a - now, p = lowest(s), t = "";
    for (var j = 0; j < 5; j++) t += j === 2 ? "<b>:</b>" : "<i>" + s.t[j] + "</i>";
    f.innerHTML = '<a class="br" href="#s-' + K.showKey(s.c, s.d, s.t, s.k) + '"><span class="vh">' + s.t + '</span><span class="bt" aria-hidden="true">' + t +
      '</span><span class="bm"><bdi class="bf"' +
      (en(cn) ? ' lang="en" dir="ltr"' : "") + ">" + K.esc(cn) + '</bdi><span class="bc">' + K.esc(W.l) +
      (b.km != null ? K.esc(W.sep) + '<span class="num">' + B.kmt(b.km, K.lang) + "</span>" : "") + '</span></span><span class="be">' +
      (n <= 60 ? '<span class="bs">' + K.esc(W.n.replace("{n}", n)) + "</span>" : "") +
      (p ? '<span class="p" data-aed="' + p + '" data-chain="' + K.esc(b.c.chain) + '" data-hall="' + K.esc(s.h) + '" data-hk="' + K.esc(s.k) + '" data-cin="' +
        K.esc(s.c) + '"></span>' : "") + "</span></a>";
    price(f);
    f.hidden = false;
  });
}
if (f) {
  if (window.requestIdleCallback) requestIdleCallback(first, { timeout: 2000 }); else setTimeout(first, 300);
  K.on("minute", function () { if (!f.hidden) first(); });
  K.on("city", first);
}
