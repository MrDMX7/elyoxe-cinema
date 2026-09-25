/* «سينما» client — no framework.
   Reads the visitor's city + card (localStorage, optional), loads /cinema/data/discounts.json (+ the city's
   slice on the home page), rewrites every .p price cell to the price after the card, fills «starting in
   the next 2 hours» and «cheapest for you tonight», marks past/soon showtimes and refreshes «updated X ago».
   Discount semantics are build.py's: percent -> price×(1-v/100); bogo -> price/2 per person;
   excluded_halls / included_halls by hall code; valid_until past -> none; status none_found -> «ما لقينا خصم».
   ?now=2026-09-25T19:00 pretends it is that UAE time (for checking the page). */
(function () {
  "use strict";
  var C = window.CT || {}, lang = document.documentElement.lang === "en" ? "en" : "ar";
  var body = document.body, page = body.getAttribute("data-page"), pageCity = body.getAttribute("data-city");
  var D = null, S = null;

  function get(k) { try { return window.localStorage.getItem("cinema." + k); } catch (e) { return null; } }
  function set(k, v) { try { window.localStorage.setItem("cinema." + k, v); } catch (e) {} }
  function qa(s, r) { return [].slice.call((r || document).querySelectorAll(s)); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function fmt(n) { return (Math.round(n * 100) / 100).toFixed(2); }
  function sub(s, o) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); }
  function uae(s) { return new Date(s.length <= 16 ? s + ":00+04:00" : s); }
  function day(d) { return new Date(d.getTime() + 4 * 3600e3).toISOString().slice(0, 10); }
  function nm(o) { return o ? (lang === "ar" ? o.ar : o.en) : ""; }

  var NOW = (function () { var m = /[?&]now=([^&]+)/.exec(location.search); var d = m && uae(decodeURIComponent(m[1])); return d && !isNaN(d) ? d : new Date(); })();
  var TODAY = day(NOW), TOMORROW = day(new Date(NOW.getTime() + 864e5));
  function param(k) { var m = new RegExp("[?&]" + k + "=([^&]+)").exec(location.search); return m ? decodeURIComponent(m[1]) : null; }
  if (param("city")) set("city", param("city"));
  if (param("card") != null) set("card", param("card"));
  var city = pageCity || get("city") || "dubai", card = get("card") || "";
  if (C.cities && !C.cities[city]) city = "dubai";
  if (C.cards && card && !C.cards[card]) card = "";
  if (pageCity) set("city", pageCity);

  /* ---------------- discounts (mirror of build.after) */
  function rule(chain, c) { return D && D.rules && D.rules[chain] && D.rules[chain][c] || null; }
  function state(r) {
    if (!r) return "unchecked";
    if (r.status === "none_found") return "none_found";
    if (r.valid_until && String(r.valid_until) < TODAY) return "expired";
    return r.type === "percent" || r.type === "bogo" ? "ok" : "none_found";
  }
  function after(aed, chain, hall, c) {
    var r = rule(chain, c), st = state(r);
    if (st !== "ok") return { a: null, st: st, r: r };
    var ex = r.excluded_halls || r.halls_excluded || [], inc = r.included_halls;
    if (ex.indexOf(hall) >= 0 || (inc && inc.indexOf(hall) < 0)) return { a: null, st: "excluded", r: r };
    var a = r.type === "bogo" ? aed / 2 : aed * (1 - (+r.value || 0) / 100);
    return { a: Math.round(a * 100) / 100, st: "ok", r: r };
  }
  // HTML: the percentage sits in its own isolated span, or an Arabic run prints «خصم %20»
  function offer(r) {
    if (r.type === "bogo") return esc(lang === "ar" ? "تذكرتين بسعر وحدة" : "Buy one, get one");
    var v = '<span class="num">' + esc(+r.value) + "%</span>";
    return lang === "ar" ? "خصم " + v : v + " off";
  }
  function weak(r) { return r && (r.confidence === "third-party" || r.confidence === "unconfirmed"); }

  /* ---------------- price cells */
  function renderPrices() {
    qa(".p").forEach(function (el) {
      var aed = +el.getAttribute("data-aed"), base = '<span class="num">' + fmt(aed) + "</span>";
      if (!card || !D) { el.innerHTML = base; return; }
      var x = after(aed, el.getAttribute("data-chain"), el.getAttribute("data-hall"), card);
      if (x.a != null) el.innerHTML = '<s class="num">' + fmt(aed) + "</s><b>" + fmt(x.a) + "</b>" + (x.r.type === "bogo" ? "<small>" + esc(C.per_person) + "</small>" : "");
      else el.innerHTML = base + (x.st === "excluded" ? "<small>" + esc(C.excluded) + "</small>" : "");
    });
  }
  function renderNote(chains) {
    var box = document.querySelector("[data-cardnote]");
    if (!box) return;
    if (!card || !D) { box.hidden = true; box.innerHTML = ""; return; }
    chains = chains || (body.getAttribute("data-chains") || "").split(" ").filter(Boolean).concat(qa(".p").map(function (e) { return e.getAttribute("data-chain"); }));
    // one line per chain with an offer; chains with the same «no» answer share one line
    var seen = {}, out = [], groups = {}, order = [];
    function cname(ch) { return (D.chains && D.chains[lang] && D.chains[lang][ch]) || ch; }
    chains.forEach(function (ch) {
      if (seen[ch]) return; seen[ch] = 1;
      var r = rule(ch, card), st = state(r);
      if (st === "ok") {
        var t = offer(r) + esc((r.box_office_only ? (lang === "ar" ? "، من الشباك فقط" : ", box office only") : "") + (weak(r) ? " — " + C.weak : ""));
        out.push("<span><b>" + esc(cname(ch)) + "</b> " + t + "</span>");
      } else { if (!groups[st]) { groups[st] = []; order.push(st); } groups[st].push(cname(ch)); }
    });
    order.forEach(function (st) { out.push("<span><b>" + esc(groups[st].join(lang === "ar" ? "، " : ", ")) + "</b> " + esc(C[st] || C.unchecked) + "</span>"); });
    if (!out.length) { box.hidden = true; return; }
    box.innerHTML = out.join("") + '<a href="' + esc(C.base + "cards/" + card + "/") + '">' + esc(sub(C["with"], { card: C.cards[card] })) + (lang === "ar" ? " — التفاصيل والشروط" : " — details and conditions") + "</a>";
    box.hidden = false;
  }

  /* ---------------- times and ages */
  function marks() {
    var soon = NOW.getTime() + 2 * 3600e3;
    qa(".times[data-d]").forEach(function (box) {
      var d = box.getAttribute("data-d");
      [].forEach.call(box.children, function (a) {
        var t = uae(d + "T" + a.textContent.slice(0, 5)).getTime();
        a.classList.toggle("past", t < NOW.getTime());
        a.classList.toggle("nowish", t >= NOW.getTime() && t <= soon);
      });
    });
  }
  function ago(at) {
    var m = Math.max(1, Math.floor((NOW - new Date(at)) / 60000)), h = Math.floor(m / 60), d = Math.floor(h / 24);
    if (lang === "en") return m < 60 ? m + " min ago" : h < 24 ? h + " hour" + (h !== 1 ? "s" : "") + " ago" : d + " day" + (d !== 1 ? "s" : "") + " ago";
    if (m < 60) return m === 1 ? "قبل دقيقة" : m === 2 ? "قبل دقيقتين" : m <= 10 ? "قبل " + m + " دقايق" : "قبل " + m + " دقيقة";
    if (h < 24) return h === 1 ? "قبل ساعة" : h === 2 ? "قبل ساعتين" : h <= 10 ? "قبل " + h + " ساعات" : "قبل " + h + " ساعة";
    return d === 1 ? "قبل يوم" : d === 2 ? "قبل يومين" : d <= 10 ? "قبل " + d + " أيام" : "قبل " + d + " يوم";
  }
  function ages() { qa("[data-at]").forEach(function (el) { el.textContent = C.updated + " " + ago(el.getAttribute("data-at")); }); }

  /* ---------------- home: on now + cheapest for you */
  function best(shows) {
    var b = null;
    shows.forEach(function (s) {
      (s.p || []).forEach(function (p) {
        var x = card ? after(p[1], S.cinemas[s.c].chain, s.h, card) : { a: null };
        var pay = x.a != null ? x.a : p[1];
        if (!b || pay < b.pay) b = { pay: pay, aed: p[1], off: x.a != null, s: s };
      });
    });
    return b;
  }
  function start(s) { return uae(s.d + "T" + s.t).getTime(); }
  function renderHome() {
    if (!S) return;
    var cn = C.cities[city] || city, n = NOW.getTime();
    var label = document.querySelector("[data-now-city]"); if (label) label.textContent = "— " + cn;
    var list = document.querySelector("[data-now-list]"), empty = document.querySelector("[data-now-empty]");
    var up = S.shows.filter(function (s) { return start(s) >= n; }).sort(function (a, b) { return start(a) - start(b); });
    var soon = up.filter(function (s) { return start(s) <= n + 2 * 3600e3; }).slice(0, 14);
    if (list) list.innerHTML = soon.map(function (s) {
      var c = S.cinemas[s.c], b = best([s]), mins = Math.round((start(s) - n) / 60000);
      return '<li><a href="' + esc(s.b || C.base + "film/" + s.f + "/") + '" rel="nofollow noopener" target="_blank">' +
        '<span class="tt">' + esc(s.t) + "</span>" + '<span class="in">' + (mins < 1 ? (lang === "ar" ? "الحين" : "now") : lang === "ar" ? "بعد " + mins + " دقيقة" : "in " + mins + " min") + "</span>" +
        '<span class="ft">' + esc(nm(S.films[s.f])) + "</span>" +
        '<span class="pl">' + esc(nm(c)) + (s.h !== "Standard" ? " · " + esc(nm({ ar: S.halls[s.k][0], en: S.halls[s.k][1] })) : "") + "</span>" +
        '<span class="pp">' + (b ? '<span class="num">' + fmt(b.pay) + "</span> " + esc(C.aed) : esc(C.box)) + "</span></a></li>";
    }).join("");
    if (empty) {
      var today = up.filter(function (s) { return s.d === TODAY; });
      empty.hidden = soon.length > 0;
      empty.textContent = today.length ? sub(C.now_empty, { city: cn, next: today[0].t + " — " + nm(S.films[today[0].f]) }) : sub(C.now_none, { city: cn });
    }
    var grid = document.querySelector(".fgrid"), tiles = qa(".film[data-fid]"), inCity = [], out = [];
    tiles.forEach(function (el) {
      var fid = el.getAttribute("data-fid"), mine = up.filter(function (s) { return s.f === fid; });
      var tonight = mine.filter(function (s) { return s.d === TODAY; }), tmr = mine.filter(function (s) { return s.d === TOMORROW; });
      var pool = tonight.length ? tonight : tmr;
      var b = best(pool), box = el.querySelector("[data-cheap]");
      el.classList.toggle("off", !pool.length);
      (pool.length ? inCity : out).push(el);
      if (!box) return;
      if (!pool.length) { box.innerHTML = '<span class="lbl">' + esc(sub(C.not_in_city, { city: cn })) + "</span>"; return; }
      if (!b) { box.innerHTML = '<span class="lbl">' + esc(C.box) + "</span>"; return; }
      box.innerHTML = '<span class="lbl">' + esc(tonight.length ? C.cheap_tonight : C.cheap_tomorrow) + "</span>" +
        '<span class="amt' + (b.off ? " you" : "") + '"><span class="num">' + fmt(b.pay) + "</span> <small>" + esc(C.aed) + "</small>" +
        (b.off ? '<s class="num">' + fmt(b.aed) + "</s>" : "") + "</span>" +
        '<span class="where">' + esc(nm(S.cinemas[b.s.c])) + " · " + '<span class="num">' + esc(b.s.t) + "</span></span>";
    });
    if (grid) inCity.concat(out).forEach(function (el) { grid.appendChild(el); });
    renderNote(Object.keys(S.cinemas).map(function (k) { return S.cinemas[k].chain; }));
  }
  // /cinema/data/<city>-<date>.json (indexed arrays, see build.slices): C[[cid,chain,ar,en]] F[[fid,ar,en]]
  // H[[code,key,ar,en]] P[prices] B[url prefixes] S[[cinema i, film i, time, hall i, price i|-1, prefix i|-1, url tail]]
  function slice(d) {
    return fetch("/cinema/data/" + city + "-" + d + ".json").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }
  function loadCity() {
    var want = city;
    return Promise.all([slice(TODAY), slice(TOMORROW)]).then(function (js) {
      if (want !== city) return;
      var o = { cinemas: {}, films: {}, halls: {}, shows: [] };
      js.forEach(function (j, i) {
        if (!j) return;
        var d = i ? TOMORROW : TODAY;
        j.C.forEach(function (c) { o.cinemas[c[0]] = { chain: c[1], ar: c[2], en: c[3] }; });
        j.F.forEach(function (f) { o.films[f[0]] = { ar: f[1], en: f[2] }; });
        j.H.forEach(function (h) { o.halls[h[1]] = [h[2], h[3]]; });
        j.S.forEach(function (a) {
          var h = j.H[a[3]];
          o.shows.push({ c: j.C[a[0]][0], f: j.F[a[1]][0], d: d, t: a[2], h: h[0], k: h[1], p: a[4] >= 0 ? j.P[a[4]] : null, b: a[5] >= 0 ? j.B[a[5]] + a[6] : (a[6] || null) });
        });
      });
      S = o; renderHome();
    });
  }

  /* ---------------- film page: your city first */
  function renderFilm() {
    var secs = qa(".fcity[data-city]"); if (!secs.length) return;
    var parent = secs[0].parentNode, mine = secs.filter(function (s) { return s.getAttribute("data-city") === city; });
    secs.forEach(function (s) { s.classList.toggle("here", s.getAttribute("data-city") === city); });
    if (mine.length) parent.insertBefore(mine[0], secs[0]);
  }

  function render() {
    renderPrices();
    if (page === "home") { if (S) renderHome(); else renderNote([]); }
    else renderNote();
    if (page === "film") renderFilm();
  }

  /* ---------------- pickers: each select is as wide as the word it shows, so the sentence reads as one line */
  function fit(sel) {
    var o = sel.options[sel.selectedIndex]; if (!o) return;
    var cs = getComputedStyle(sel), s = document.createElement("span");
    s.style.cssText = "position:absolute;visibility:hidden;white-space:pre";
    s.style.fontFamily = cs.fontFamily; s.style.fontSize = cs.fontSize; s.style.fontWeight = cs.fontWeight;
    s.textContent = o.text; document.body.appendChild(s);
    sel.style.inlineSize = Math.ceil(s.getBoundingClientRect().width + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + 2) + "px";
    s.remove();
  }
  function fitAll() { qa(".sel select").forEach(fit); }
  qa("select[data-city]").forEach(function (sel) {
    sel.value = city;
    sel.addEventListener("change", function () {
      city = sel.value; set("city", city);
      fit(sel);
      if (pageCity) { location.href = C.base + city + "/"; return; }
      if (page === "home") loadCity(); else render();
    });
  });
  qa("select[data-card]").forEach(function (sel) {
    sel.value = card;
    sel.addEventListener("change", function () { card = sel.value; set("card", card); qa("select[data-card]").forEach(function (o) { o.value = card; fit(o); }); render(); });
  });

  fitAll(); if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitAll);
  marks(); ages();
  fetch("/cinema/data/discounts.json").then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { D = j; render(); }).catch(function () {});
  if (page === "home") loadCity();
})();
