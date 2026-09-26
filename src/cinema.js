/* «سينما» client — no framework. (Task 4 rewrites this; for now it drives the «هـ» markup minimally.)
   Reads the visitor's city + card (localStorage, optional), loads /data/discounts.json (+ the city's slice
   on home and city pages), rewrites every .p price cell to the price after the card, fills «الحين» and the
   film tiles' «cheapest for you», opens the ticket for a tapped time, marks past/soon showtimes and
   refreshes «updated X ago». Discount semantics are discounts.py's (compute): the block between disc:begin
   and disc:end mirrors it line for line, and tests/test_parity.py runs that block in node against Python.
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

  /* ---------------- discounts */
  /* disc:begin — a pure mirror of discounts.py compute(); tests/test_parity.py runs this block in node */
  function discRule(rules, chain, c) { return rules && rules[chain] && rules[chain][c] || null; }
  function discState(r, today) {
    if (!r) return "unchecked";
    if (r.status === "none_found") return "none_found";
    if (r.valid_until && String(r.valid_until) < today) return "expired";
    return r.type === "percent" || r.type === "bogo" || r.type === "fixed" ? "ok" : "none_found";
  }
  function discCovers(r, hall, hk, cin) {
    var names = [hall, hk].filter(function (h) { return h; }), ex = r.excluded_halls || r.halls_excluded || [], inc = r.included_halls;
    var any = function (list) { return names.some(function (h) { return list.indexOf(h) >= 0; }); };
    if (any(ex)) return false;
    if (inc != null && !any(inc)) return false;
    if (r.included_cinemas != null && r.included_cinemas.indexOf(cin) < 0) return false;
    return true;
  }
  function discR2(x) { return Math.round(x * 100) / 100; }
  function discPrice(r, aed) {
    if (r.type === "bogo") return discR2(aed / 2);
    if (r.type === "fixed") return discR2(Math.min(aed, +r.value || 0));
    return discR2(aed * (1 - (+r.value || 0) / 100));
  }
  // hk: a halls.yaml key, or the slices' «chain|key» (the key is after the bar)
  function discAfter(rules, today, aed, chain, hall, hk, cin, c) {
    var r = discRule(rules, chain, c), st = discState(r, today);
    if (hk && hk.indexOf("|") >= 0) hk = hk.slice(hk.indexOf("|") + 1);
    if (st !== "ok") return { a: null, st: st, r: r };
    if (!discCovers(r, hall, hk, cin)) return { a: null, st: "excluded", r: r };
    return { a: discPrice(r, aed), st: "ok", r: r };
  }
  // what a paid price needs said next to it: BOGO is per person and only with 2 tickets
  function discPayNote(r, strings) { return r && r.type === "bogo" ? strings.per_person : ""; }
  /* disc:end */
  function rule(chain, c) { return discRule(D && D.rules, chain, c); }
  function state(r) { return discState(r, TODAY); }
  function after(aed, chain, hall, c, hk, cin) { return discAfter(D && D.rules, TODAY, aed, chain, hall, hk, cin, c); }
  function ppNote(r) { var n = discPayNote(r, C); return n ? "<small class=\"per\">" + esc(n) + "</small>" : ""; }
  // a price from the fallback table (prices.yaml) carries the date it was seen, never the live «updated X ago»
  function asofNote(d) { return d ? '<small class="asof">' + sub(esc(C.asof), { date: '<bdi class="num">' + esc(d) + "</bdi>" }) + "</small>" : ""; }
  // HTML: the percentage sits in its own isolated span, or an Arabic run prints «خصم %20»
  function offer(r) {
    if (r.type === "bogo") return esc(lang === "ar" ? "تذكرتين بسعر وحدة" : "Buy one, get one");
    if (r.type === "fixed") { var f = '<span class="num" dir="ltr">' + esc(+r.value) + "</span>"; return lang === "ar" ? "التذكرة بـ" + f + " درهم" : "Tickets at AED " + f; }
    var v = '<span class="num" dir="ltr">' + esc(+r.value) + "%</span>";
    return lang === "ar" ? "خصم " + v : v + " off";
  }
  function weak(r) { return r && (r.confidence === "third-party" || r.confidence === "unconfirmed"); }

  /* ---------------- price cells */
  function renderPrices() {
    qa(".p").forEach(function (el) {
      var aed = +el.getAttribute("data-aed"), base = '<span class="num">' + fmt(aed) + "</span>", asof = asofNote(el.getAttribute("data-asof"));
      if (!card || !D) { el.innerHTML = base + asof; return; }
      var x = after(aed, el.getAttribute("data-chain"), el.getAttribute("data-hall"), card, el.getAttribute("data-hk"), el.getAttribute("data-cin"));
      if (x.a != null) el.innerHTML = '<s class="num">' + fmt(aed) + "</s><b>" + fmt(x.a) + "</b>" + ppNote(x.r) + asof;
      else el.innerHTML = base + (x.st === "excluded" ? "<small>" + esc(C.excluded) + "</small>" : "") + asof;
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
      qa("[data-start]", box).forEach(function (a) {
        var t = uae(d + "T" + a.getAttribute("data-start")).getTime();
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

  /* ---------------- home + city: «الحين» + cheapest for you */
  function best(shows) {
    var b = null;
    shows.forEach(function (s) {
      (s.p || []).forEach(function (p) {
        var x = card ? after(p[1], S.cinemas[s.c].chain, s.h, card, s.k, s.c) : { a: null };
        var pay = x.a != null ? x.a : p[1];
        if (!b || pay < b.pay) b = { pay: pay, aed: p[1], off: x.a != null, r: x.a != null ? x.r : null, s: s };
      });
    });
    return b;
  }
  function start(s) { return uae(s.d + "T" + s.t).getTime(); }
  function flip(t) {
    return t.split("").map(function (ch) { return ch === ":" ? '<span class="c">:</span>' : '<span class="d go">' + esc(ch) + "</span>"; }).join("");
  }
  function renderHome() {
    if (!S) return;
    var cn = C.cities[city] || city, n = NOW.getTime();
    qa("[data-city-name]").forEach(function (el) { el.textContent = cn; });
    var lab = document.querySelector("[data-city-label]"); if (lab && page === "home") lab.textContent = lang === "ar" ? "في " + cn : "in " + cn;
    var up = S.shows.filter(function (s) { return start(s) >= n; }).sort(function (a, b) { return start(a) - start(b); });
    var soon = up.filter(function (s) { return start(s) <= n + 45 * 60e3; });
    var now = document.querySelector("[data-now]");
    if (now) {
      var s0 = soon[0];
      now.hidden = !s0;
      if (s0) {
        var b = best([s0]), mins = Math.round((start(s0) - n) / 60000);
        now.querySelector("[data-now-film]").textContent = sub(C.in_cinema, { film: nm(S.films[s0.f]), cinema: nm(S.cinemas[s0.c]) });
        now.querySelector("[data-now-where]").innerHTML = esc(sub(C.in_min, { n: Math.max(mins, 0) })) +
          (b ? '، <span class="num">' + fmt(b.pay) + "</span> " + esc(C.aed) + ppNote(b.r) + asofNote(s0.asof) : "");
        now.querySelector("[data-now-time]").innerHTML = flip(s0.t);
        now.href = C.base + "film/" + s0.f + "/";
      }
    }
    var grid = document.querySelector("[data-films]"), tiles = qa(".film[data-fid]", grid || document), inCity = [], out = [];
    tiles.forEach(function (el) {
      var fid = el.getAttribute("data-fid"), mine = up.filter(function (s) { return s.f === fid; });
      var tonight = mine.filter(function (s) { return s.d === TODAY; }), tmr = mine.filter(function (s) { return s.d === TOMORROW; });
      var pool = tonight.length ? tonight : tmr;
      var b = best(pool), box = el.querySelector("[data-cheap]");
      el.classList.toggle("off", !pool.length);
      el.setAttribute("data-pay", b ? b.pay : 1e9);
      (pool.length ? inCity : out).push(el);
      if (!box) return;
      if (!pool.length) { box.innerHTML = '<span class="fw">' + esc(sub(C.not_in_city, { city: cn })) + "</span>"; return; }
      if (!b) { box.innerHTML = '<span class="fp"><span class="na">' + esc(C.box) + "</span></span>"; return; }
      box.innerHTML = '<span class="fp"><span class="p"><b>' + fmt(b.pay) + "</b>" + (b.off ? '<s class="num">' + fmt(b.aed) + "</s>" : "") + ppNote(b.r) + "</span></span>" +
        '<span class="fw">' + esc(nm(S.cinemas[b.s.c])) + (lang === "ar" ? "، " : ", ") + esc(b.s.t) + "</span>" + asofNote(b.s.asof);
    });
    if (grid && page === "home") inCity.concat(out).forEach(function (el, i) { el.classList.toggle("big", i === 0); grid.appendChild(el); });
    applyFilters();
    renderNote(Object.keys(S.cinemas).map(function (k) { return S.cinemas[k].chain; }));
  }
  // /data/<city>-<date>.json (indexed arrays, see build.slices): C[[cid,chain,ar,en]] F[[fid,ar,en]]
  // H[[code,key,ar,en]] P[prices] B[url prefixes] S[[cinema i, film i, time, hall i, price i|-1, prefix i|-1, url tail]]
  function slice(d) {
    return fetch("/data/" + city + "-" + d + ".json").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
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
          o.shows.push({ c: j.C[a[0]][0], f: j.F[a[1]][0], d: d, t: a[2], h: h[0], k: h[1], p: a[4] >= 0 ? j.P[a[4]] : null, b: a[5] >= 0 ? j.B[a[5]] + a[6] : (a[6] || null), asof: a[7] || null });
        });
      });
      S = o; renderHome();
    });
  }

  /* ---------------- filters (genre, family, kids, cheapest for you); «ends before» is Task 4's */
  var filt = "all", byPrice = false;
  function applyFilters() {
    qa(".film[data-fid]").forEach(function (el) {
      var ok = filt === "all" || (filt === "family" && el.getAttribute("data-family") === "1") || (filt === "kids" && el.getAttribute("data-kids") === "1") ||
        (filt.indexOf("genre:") === 0 && (" " + el.getAttribute("data-genres") + " ").indexOf(" " + filt.slice(6) + " ") >= 0);
      el.hidden = !ok;
    });
    var grid = document.querySelector("[data-films]");
    if (grid && byPrice) qa(".film[data-fid]", grid).sort(function (a, b) { return (+a.getAttribute("data-pay") || 1e9) - (+b.getAttribute("data-pay") || 1e9); }).forEach(function (el) { grid.appendChild(el); });
  }
  qa("[data-filter]").forEach(function (b) {
    b.addEventListener("click", function () {
      filt = b.getAttribute("data-filter");
      qa("[data-filter]").forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
      applyFilters();
    });
  });
  qa("[data-sort],[data-ends-before]").forEach(function (b) {
    b.addEventListener("click", function () {
      var on = b.getAttribute("aria-pressed") !== "true"; b.setAttribute("aria-pressed", on ? "true" : "false");
      if (b.hasAttribute("data-sort")) byPrice = on;
      applyFilters();
    });
  });

  /* ---------------- film page: your city first, day tabs, the prayer switch (its marking is Task 4's) */
  function renderFilm() {
    var secs = qa(".fcity[data-city]"); if (!secs.length) return;
    var parent = secs[0].parentNode, mine = secs.filter(function (s) { return s.getAttribute("data-city") === city; });
    secs.forEach(function (s) { s.classList.toggle("here", s.getAttribute("data-city") === city); });
    if (mine.length) parent.insertBefore(mine[0], secs[0]);
  }
  qa("[data-day]").forEach(function (b) {
    b.addEventListener("click", function () {
      var d = b.getAttribute("data-day");
      qa("[data-day]").forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
      qa(".cgs .times[data-d]").forEach(function (t) { t.hidden = t.getAttribute("data-d") !== d; });
    });
  });
  (function () { var first = document.querySelector("[data-day]"); if (first) first.click(); })();
  qa("[data-prayer]").forEach(function (sw) {
    sw.addEventListener("click", function () { sw.setAttribute("aria-checked", sw.getAttribute("aria-checked") === "true" ? "false" : "true"); });
  });

  /* ---------------- the ticket: a tapped time fills the page's one ticket */
  var PL = (function () { var el = document.getElementById("cinema-p"); try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; } })();
  var tk = document.querySelector("[data-ticket]");
  function openTicket(btn) {
    if (!tk || !tk.querySelector("[data-tk-rows]")) return;
    qa(".tm.on").forEach(function (o) { o.classList.remove("on"); });
    btn.classList.add("on");
    var grp = btn.closest("[data-cin]"), hl = btn.closest("[data-hall]"), box = btn.closest("[data-d]");
    var cin = grp ? grp.getAttribute("data-cin") : "", d = box ? box.getAttribute("data-d") : TODAY;
    var chain = grp && grp.getAttribute("data-chain") || (body.getAttribute("data-chains") || "").split(" ")[0];
    var hall = hl ? hl.getAttribute("data-hall") : "", hk = hl ? hl.getAttribute("data-hk") : "", asof = btn.getAttribute("data-asof");
    var h3 = grp && grp.querySelector(".cg-h h3");
    if (h3) tk.querySelector("[data-tk-cin]").textContent = h3.textContent;
    var fr = btn.closest(".cf"); if (fr && fr.querySelector("h3")) tk.querySelector("[data-tk-film]").textContent = fr.querySelector("h3").textContent;
    tk.querySelector("[data-tk-time]").textContent = btn.getAttribute("data-start");
    tk.querySelector("[data-tk-day]").textContent = d === TODAY ? C.today : d === TOMORROW ? C.tomorrow : d;
    var hn = hl && hl.querySelector(".hn"), ends = btn.getAttribute("data-ends");
    tk.querySelector("[data-tk-when]").innerHTML = (hn && hk !== "Standard" ? '<span class="tk-h"><bdi>' + esc(hn.textContent) + "</bdi></span>" : "") + (ends ? "<span>" + esc(sub(C.ends, { t: ends })) + "</span>" : "");
    var pl = PL[+btn.getAttribute("data-p")];
    tk.querySelector("[data-tk-rows]").innerHTML = pl && btn.hasAttribute("data-p") ? pl.slice().sort(function (a, b) { return a[1] - b[1]; }).map(function (p) {
      return '<tr><th scope="row"><bdi>' + esc(p[0]) + '</bdi></th><td><span class="p" data-aed="' + fmt(p[1]) + '" data-chain="' + esc(chain) + '" data-hall="' + esc(hall) + '" data-hk="' + esc(hk) + '" data-cin="' + esc(cin) + '"' + (asof ? ' data-asof="' + esc(asof) + '"' : "") + '><span class="num">' + fmt(p[1]) + "</span></span></td></tr>";
    }).join("") : '<tr><td colspan="2"><span class="na">' + esc(C.box) + "</span></td></tr>";
    var book = tk.querySelector("[data-tk-book]"), url = btn.getAttribute("data-book");
    if (book && url && book.tagName === "A") { book.href = url; if (D && D.chains) book.textContent = sub(C.book_at, { chain: D.chains[lang][chain] || chain }); }
    renderPrices(); renderTerms(chain);
    tk.classList.add("open");
  }
  function renderTerms(chain) {
    var el = tk && tk.querySelector("[data-tk-terms]"); if (!el) return;
    var r = card && D ? rule(chain, card) : null;
    el.hidden = !(r && state(r) === "ok");
    if (!el.hidden) el.innerHTML = esc(sub(C.after_card, { card: C.cards[card] })) + " " + offer(r) + (r.note_ar && lang === "ar" ? "، " + esc(r.note_ar) : "");
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button[data-show]"); if (b) { openTicket(b); return; }
    if (e.target.closest && e.target.closest("[data-tk-close]") && tk) tk.classList.remove("open");
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && tk) tk.classList.remove("open"); });

  function render() {
    renderPrices();
    if (S) renderHome(); else renderNote([]);
    if (page === "film") renderFilm();
    if (tk) renderTerms((tk.closest("body").getAttribute("data-chains") || "").split(" ")[0]);
  }

  /* ---------------- the control sentence: city links + card chips */
  qa("[data-citypick] a[data-city]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      set("city", a.getAttribute("data-city"));
      if (page === "home") { e.preventDefault(); city = a.getAttribute("data-city"); a.closest("details").open = false; loadCity(); }
    });
  });
  function markCard() {
    qa("button[data-card]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-card") === card ? "true" : "false"); });
    qa("select[data-card]").forEach(function (s) {
      var has = !!card && [].some.call(s.options, function (o) { return o.value === card; });
      s.value = has ? card : ""; s.parentNode.classList.toggle("on", has);
    });
  }
  qa("button[data-card]").forEach(function (b) { b.addEventListener("click", function () { card = b.getAttribute("data-card"); set("card", card); markCard(); render(); }); });
  qa("select[data-card]").forEach(function (s) { s.addEventListener("change", function () { card = s.value; set("card", card); markCard(); render(); }); });
  qa("[data-city-name]").forEach(function (el) { if (C.cities[city]) el.textContent = C.cities[city]; });

  markCard(); marks(); ages();
  fetch("/data/discounts.json").then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { D = j; render(); }).catch(function () {});
  if (page === "home" || page === "city") loadCity();
})();
