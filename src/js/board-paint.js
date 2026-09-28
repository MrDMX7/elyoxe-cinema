/* «اللوحة»: the board's renderer and picker (MASTER-PLAN §1.3, §2.1, §5.3 W2-P2a). Two ways in:
   - inlined by pages/board.py right after the box on home and the 404, whose board follows the visitor's city, as
     (function () {<this file> cbPaint(island, document.currentScript.parentNode)})(): the saved city is on the board in
     the first frame (no Dubai flash for Sharjah, and the box is fixed, so nothing shifts);
   - the lazy chunk «board-paint» on a city or a cinema page, whose rows the server already drew for that place: it
     starts on the island in the board's <script type="application/json" data-island>.
   window.CB is the one renderer. src/js/board-live.js (lazy, window.CBlive) keeps its minute, feeds it the city's shows
   once they are in (CB.src), reprices what it drew (CB.done) and loads more when the island runs low (CB.low). Python's
   twin is pages/board.py (pick, row_html); tests/test_w2_p2a.py holds them equal.
     I.d dates, I.f films [fid, title (escaped), latin?], I.c cinemas [cid, name (escaped), latin?, chain?],
     I.h halls [code, key], I.r {city or cinema: rows [date i, "HH:MM", film i, cinema i, hall i, price, key]},
     I.cn {city: name} (a board that follows the visitor's city), I.s strings, I.b the base path, I.g "city" (the
     visitor's) or the fixed city or cinema, I.n rows in the box (I.nd on a desktop), I.m rows under «اللوحة كاملة»,
     I.o 1: no cinema limit (one cinema's own board), I.w 1: hold the rows until /geo answers
   Every time is a UAE wall-clock minute since the epoch, from «date + time + 04:00» (?now= shifts it, as core.js does):
   never the device's own hours, so a phone set to New York still sees Dubai's board. */
var cbPaint = function (I, b) {
  var w = window, CB = w.CB = { I: I, b: b, F: 0 }, S = I.s;
  var mm = function (s) { return !!(w.matchMedia && w.matchMedia(s).matches); }, RM = mm("(prefers-reduced-motion: reduce)");
  var N = I.nd && mm("(min-width:1024px)") ? I.nd : I.n, m = /[?&]now=([^&]+)/.exec(location.search), v = null;
  try { v = m && decodeURIComponent(m[1]); } catch (e) {}
  var F = v ? Date.parse(v.length < 17 ? v + ":00+04:00" : v) - Date.now() : 0;
  CB.F = F === F ? F : 0;
  function ls(k) { try { return w.localStorage.getItem("cinema." + k); } catch (e) { return null; } }
  function en(o) { return o ? ' lang="en" dir="ltr"' : ""; }
  CB.now = function () { return Math.floor((Date.now() + CB.F) / 6e4); };
  CB.at = function (dt, t) { return Date.parse(dt + "T" + t + ":00+04:00") / 6e4; };
  CB.hm = function (x) { return new Date(x * 6e4 + 144e5).toISOString().slice(11, 16); };
  /* the island's rows for a city or a cinema, as row objects, in the board's order (Python sorted them). A capped
     shared-minute member carries the true count as x[7] ('gx', pages/board.py's flat()) */
  CB.rows = function (key) {
    return (I.r[key] || []).map(function (x) {
      var r = { at: CB.at(I.d[x[0]], x[1]), f: I.f[x[2]], c: I.c[x[3]], h: I.h[x[4]], p: x[5], k: x[6] };
      if (x.length > 7) r.gx = x[7];
      return r;
    });
  };
  /* what starts next, in the rows' order: one row per film on the whole board; any three rows in a row hold at most
     two of one cinema (unless free: one cinema's own board); a minute three films or more share is one entry
     {at, x: [each film's first row]}, «3 أفلام» */
  CB.pick = function (rows, now, n, free) {
    var out = [], used = {}, i = 0;
    rows = rows.filter(function (r) { return r.at >= now; });
    while (i < rows.length && out.length < n) {
      var a = rows[i].at, g = [], x = [], one = {};
      while (i < rows.length && rows[i].at === a) g.push(rows[i++]);
      g.forEach(function (r) { if (!used[r.f[0]] && !one[r.f[0]]) { one[r.f[0]] = 1; x.push(r); } });
      if (x.length > 2) { x.forEach(function (r) { used[r.f[0]] = 1; }); out.push({ at: a, x: x }); continue; }
      g.forEach(function (r) {
        var p = out[out.length - 1], q = out[out.length - 2];
        if (out.length >= n || used[r.f[0]] || !free && p && q && p.r && q.r && p.r.c[0] === r.c[0] && q.r.c[0] === r.c[0]) return;
        used[r.f[0]] = 1; out.push({ at: a, r: r });
      });
    }
    return out;
  };
  /* a row's link, and its identity from one minute to the next: its show (a shared minute's, its first film's) */
  CB.href = function (e) { var r = e.r || e.x[0]; return I.b + "film/" + r.f[0] + "/#s-" + r.k; };
  /* the time for a screen reader, then split-flap tiles, one per digit (the colon is the dull part); a digit that
     differs from `old` turns over */
  CB.time = function (t, old) {
    for (var j = 0, s = ""; j < 5; j++) s += j === 2 ? "<b>:</b>" : "<i" + (old && old[j] !== t[j] ? ' class="go" style="--i:' + j + '"' : "") + ">" + t[j] + "</i>";
    return '<span class="vh">' + t + '</span><span class="bt" aria-hidden="true">' + s + "</span>";
  };
  /* one row: the time; the film, then the cinema (and how far, once board-live.js knows: r.km); «بعد N د» in live
     green within 30 minutes; the price. A shared minute: «3 أفلام» and the titles, a link to the first film's show
     (board-live.js opens the list). `a` = the row's motion attributes */
  CB.row = function (e, now, a) {
    var r = e.r || e.x[0], n = e.at - now, z = n > 30 ? "" : '<span class="bs">' + (n > 0 ? S.n.replace("{n}", n) : S.z) + "</span>";
    var h = '<a class="br' + (e.x ? " bx" : "") + (a || "") + '" href="' + CB.href(e) + '">' + CB.time(CB.hm(e.at)) + '<span class="bm">';
    if (e.x) {
      var nx = e.x[0].gx || e.x.length;
      return h + '<span class="bf">' + (nx > 10 ? S.x11 : S.x).replace("{n}", nx) + '</span><span class="bc">' +
        e.x.map(function (x) { return "<bdi" + en(x.f[2]) + ">" + x.f[1] + "</bdi>"; }).join(S.sep) + '</span></span><span class="be">' + z + "</span></a>";
    }
    return h + '<bdi class="bf"' + en(r.f[2]) + ">" + r.f[1] + '</bdi><span class="bc"><bdi' + en(r.c[2]) + ">" + r.c[1] + "</bdi>" +
      (r.km ? S.sep + '<span class="num">' + r.km + "</span>" : "") + '</span></span><span class="be">' + z +
      (r.p ? '<span class="p" data-aed="' + r.p + '" data-chain="' + (r.c[3] || r.c[0].split("-")[0]) + '" data-hall="' + r.h[0] + '" data-hk="' + r.h[1] +
        '" data-cin="' + r.c[0] + '"><span class="num">' + r.p + "</span></span>" : "") + "</span></a>";
  };
  CB.city = function () {
    var q = /[?&]city=([a-z-]+)/.exec(location.search), c = ls("city") || q && q[1];
    return I.cn[c] ? c : "dubai";
  };
  /* draw the board at this minute, from the city's shows once board-live.js has them (CB.src), else the island. With
     `anim` a passed row leaves (240 ms, inside the fixed box), the rows below move up, a new one comes in from below,
     and the clock's changed digits turn over. With no card, the box's one cheapest price is lit (.lo), as prices.js
     lows() does after every repricing */
  CB.draw = function (anim) {
    var now = CB.now(), src = CB.src && CB.src(CB.k), rowsAll = src || CB.rows(CB.k), es = CB.pick(rowsAll, now, N + I.m, I.o), lo = null;
    var q = function (s) { return b.querySelector(s); }, box = q("[data-brs]"), more = q("[data-brs-more]"), ck = q("[data-board-clock]"), cn = q("[data-board-city]");
    var old = [].map.call(box.querySelectorAll(".br"), function (a) { return a.getAttribute("href"); }), keys = es.slice(0, N).map(CB.href);
    var mv = anim && !RM && old.length && old.join() !== keys.join(), t = CB.hm(now), was = ck && ck.getAttribute("data-t");
    CB.es = es; CB.last = now;
    if (es.length < N && !src && CB.low) CB.low();
    function put() {
      box.innerHTML = es.slice(0, N).map(function (e, i) {
        var o = old.indexOf(keys[i]);
        return CB.row(e, now, !mv ? "" : o < 0 ? " in" : o > i ? ' mv" style="--dy:' + (o - i) : "");
      }).join("");
      if (!box.innerHTML) {
        /* nothing left tonight: name the next show instead of claiming a refresh that will not change anything
           (fix round review §Important 5, honesty §1.2 #8) */
        var nx = rowsAll.filter(function (r) { return r.at >= now; }).sort(function (a, b) { return a.at - b.at; })[0];
        box.innerHTML = '<p class="bw">' + (nx ? S.at.replace("{t}", CB.hm(nx.at)) : S.w) + "</p>";
      }
      if (!ls("card")) [].forEach.call(box.querySelectorAll(".p[data-aed]"), function (p) { if (!lo || +p.getAttribute("data-aed") < +lo.getAttribute("data-aed")) lo = p; });
      if (lo) lo.classList.add("lo");
      if (more) { more.innerHTML = es.slice(N, N + I.m).map(function (e) { return CB.row(e, now); }).join(""); more.parentNode.hidden = !more.firstChild; }
      if (CB.done) CB.done(b, es);
    }
    if (mv) {
      [].forEach.call(box.querySelectorAll(".br"), function (a) { if (keys.indexOf(a.getAttribute("href")) < 0) a.classList.add("out"); });
      setTimeout(put, 240);
    } else put();
    if (ck && was !== t) { ck.setAttribute("data-t", t); ck.innerHTML = CB.time(t, anim && !RM && was); }
    if (cn && I.cn[CB.k]) cn.textContent = I.cn[CB.k];
  };
  /* a new city (the pill, /geo): its rows at once, the hold over */
  CB.go = function (c) { if (I.g === "city" && I.cn[c]) { CB.k = c; b.classList.remove("geo-wait"); CB.draw(); } };
  I.cn = I.cn || {};
  CB.k = I.g === "city" ? CB.city() : I.g;
  CB.draw();
  /* a first visit (no saved city, /geo not asked yet): the box and its head keep their place and the rows wait for /geo
     (src/js/geo.js picks the city, board-live.js calls CB.go); Dubai's show after 1.5 s whatever happens */
  if (I.w && !ls("city") && !ls("geo") && !/[?&]city=/.test(location.search)) {
    b.classList.add("geo-wait");
    setTimeout(function () { b.classList.remove("geo-wait"); }, 1500);
  }
  if (w.CBlive) w.CBlive(CB);
};
/* as the lazy chunk (K = window.CINEMA): a city's or a cinema's board, from its island */
if (typeof K === "object" && K && !window.CB) [].forEach.call(document.querySelectorAll("[data-board] > script[data-island]"), function (s) {
  cbPaint(JSON.parse(s.textContent), s.parentNode);
});
