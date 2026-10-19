/* «سينما» as an app: what needs the phone. The two lists side by side (swipe or tap a tab), the genre chips, the city
   and «الأقرب», the day switch, times already started, the ticket sheet (Back closes it, a drag down closes it), the
   trailer and «اسأل الفيلم». Pages themselves are static and move with cross-document view transitions (app.css). */
(function () {
  "use strict";
  var A = window.APP || {}, d = document, html = d.documentElement;
  var q = function (s, r) { return (r || d).querySelector(s); }, qa = function (s, r) { return [].slice.call((r || d).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var store = { get: function (k) { try { return localStorage.getItem("cinema." + k); } catch (e) { return null; } },
                set: function (k, v) { try { localStorage.setItem("cinema." + k, v); } catch (e) {} } };
  var CITY_AR = { "dubai": "دبي", "abu-dhabi": "أبوظبي", "sharjah": "الشارقة", "al-ain": "العين", "ajman": "عجمان", "ras-al-khaimah": "رأس الخيمة", "fujairah": "الفجيرة", "umm-al-quwain": "أم القيوين" };

  /* UAE time (UTC+4): a show at 00:45 on a date is that night's, the next calendar day's small hours */
  function nowUAE() { return Date.now() + 4 * 3600e3; }
  function startOf(day, t) { var ms = Date.parse(day + "T" + t + ":00Z"); if (t < "04:00") ms += 864e5; return ms; }
  /* the cinema day on this phone (it turns at 4 am, like startOf): a page built yesterday (the night between runs,
     or a failed run) must not call today «بكرة» nor offer a day that is over */
  (function () {
    var cd = new Date(nowUAE() - 4 * 3600e3).toISOString().slice(0, 10);
    if (A.today && cd > A.today) { A.today = cd; A.tomorrow = new Date(Date.parse(cd + "T00:00:00Z") + 864e5).toISOString().slice(0, 10); }
  })();
  /* 12-hour times (owner 2026-10-18): «16:25» → «4:25» and «مساء»; the dirham sign from the page's <template id="aed"> */
  function t12(t) { var h = +t.slice(0, 2), m = t.slice(3, 5); return [(h % 12 || 12) + ":" + m, h < 4 ? "بالليل" : h < 12 ? "الصبح" : h === 12 ? "الظهر" : "مساء"]; }
  var AED = (q("#aed") || {}).innerHTML || " درهم";
  /* a chain's mark beside a cinema's name: its own app icon (window.APP.logos), else the coloured name tag */
  function chm(ch, name) {
    var src = A.logos && A.logos[ch];
    return src ? '<img class="chl" src="' + esc(src) + '" alt="' + esc(name) + '" width="20" height="20">' : '<i class="chm ch-' + esc(ch) + '">' + esc(name) + "</i>";
  }
  function vt(fn) { if (d.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) d.startViewTransition(fn); else fn(); }

  /* distance (km) from the visitor, when they let us know where they are (kept for the session only) */
  var here = null;
  try { here = JSON.parse(sessionStorage.getItem("cinema.here") || "null"); } catch (e) {}
  function km(el) {
    if (!here || !el.dataset.lat) return null;
    var R = 6371, toR = Math.PI / 180, la1 = here[0] * toR, la2 = +el.dataset.lat * toR, dl = (+el.dataset.lng - here[1]) * toR, dp = la2 - la1;
    var a = Math.sin(dp / 2) * Math.sin(dp / 2) + Math.cos(la1) * Math.cos(la2) * Math.sin(dl / 2) * Math.sin(dl / 2);
    return 2 * R * Math.asin(Math.sqrt(a));
  }
  function kmText(k) { return k == null ? "" : (k < 1 ? "أقل من كيلو" : Math.round(k) + " كم"); }
  function locate(ok, fail) {
    if (!navigator.geolocation) { fail(); return; }
    navigator.geolocation.getCurrentPosition(function (p) {
      here = [p.coords.latitude, p.coords.longitude];
      try { sessionStorage.setItem("cinema.here", JSON.stringify(here)); } catch (e) {}
      ok();
    }, fail, { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 });
  }

  /* ── home: the two tabs and the pager ── */
  var pager = q("[data-pager]");
  if (pager) {
    var tabs = qa(".toptabs [data-pane]"), panes = qa(".pane", pager);
    var setTab = function (i) {
      tabs.forEach(function (t, j) { t.classList.toggle("on", i === j); t.setAttribute("aria-selected", i === j ? "true" : "false"); });
      try { sessionStorage.setItem("cinema.pane", i); } catch (e) {}
    };
    tabs.forEach(function (t, i) { t.addEventListener("click", function () { panes[i].scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" }); setTab(i); }); });
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) setTab(panes.indexOf(e.target)); }); }, { root: pager, threshold: 0.6 });
      panes.forEach(function (p) { io.observe(p); });
    }
    var last = +(sessionStorage.getItem("cinema.pane") || 0);
    if (last === 1) { panes[1].scrollIntoView({ inline: "start", block: "nearest" }); setTab(1); }

    /* genre chips: the grid shows only what the chip names; the reflow is a view transition */
    var grid = q("[data-grid]"), none = q("[data-none]");
    qa("[data-chip]").forEach(function (c) {
      c.addEventListener("click", function () {
        var k = c.dataset.chip;
        vt(function () {
          qa("[data-chip]").forEach(function (x) { x.classList.toggle("on", x === c); });
          var n = 0;
          qa(".tile", grid).forEach(function (t) { var on = k === "all" || (" " + t.dataset.g + " ").indexOf(" " + k + " ") >= 0; t.hidden = !on; if (on) n++; });
          none.hidden = n > 0;
        });
        c.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
      });
    });

    /* the cinemas: a city, or the nearest first */
    var clist = q("[data-clist]"), msg = q("[data-geo-msg]");
    var showCity = function (city) {
      vt(function () {
        qa("[data-cchips] .chip").forEach(function (x) { x.classList.toggle("on", x.dataset.city === city); });
        qa(".ccard", clist).forEach(function (c) { c.hidden = c.dataset.city !== city; });
        msg.hidden = true;
      });
      store.set("city", city);
    };
    var showNear = function () {
      var cards = qa(".ccard", clist);
      cards.forEach(function (c) { var k = km(c); c._k = k == null ? 1e9 : k; q("[data-km]", c).textContent = kmText(k); });
      vt(function () {
        qa("[data-cchips] .chip").forEach(function (x) { x.classList.toggle("on", x.hasAttribute("data-near")); });
        cards.sort(function (a, b) { return a._k - b._k; }).forEach(function (c, i) { c.hidden = i >= 12; clist.appendChild(c); });
        msg.hidden = false; msg.textContent = "أقرب السينمات لك، الأقرب أول.";
      });
      var near = cards[0];
      if (near && near._k < 60) store.set("city", near.dataset.city);
    };
    qa("[data-cchips] [data-city]").forEach(function (c) { c.addEventListener("click", function () { showCity(c.dataset.city); }); });
    var nb = q("[data-near]");
    if (nb) nb.addEventListener("click", function () {
      if (here) { showNear(); return; }
      msg.hidden = false; msg.textContent = "لحظة، نحدد مكانك…";
      locate(showNear, function () { msg.textContent = "ما قدرنا نعرف مكانك — اختار مدينتك."; });
    });
    if (here) showNear(); else showCity(store.get("city") || "dubai");
  }

  /* ── the merged top (sample): the screen's dots follow the swipe; «يبدأ قريب منك» from #soon ── */
  var bill = q("[data-bill]");
  if (bill) {
    var dots = qa("[data-dots] i");
    /* the slide whose centre is nearest the row's centre is the one on screen (RTL-safe: no scrollLeft sign) */
    var onBill = function () {
      var box = bill.getBoundingClientRect(), mid = box.left + box.width / 2, best = 0, bd = 1e9;
      [].forEach.call(bill.children, function (el, j) { var r = el.getBoundingClientRect(), dd = Math.abs(r.left + r.width / 2 - mid); if (dd < bd) { bd = dd; best = j; } });
      dots.forEach(function (x, j) { x.classList.toggle("on", best === j); });
    };
    bill.addEventListener("scroll", onBill, { passive: true }); onBill();
  }
  var soonBox = q("[data-soon]");
  if (soonBox) {
    var S = null; try { S = JSON.parse(q("#soon").textContent); } catch (e) {}
    var paintSoon = function () {
      if (!S) return;
      var city = store.get("city") || "dubai", now = nowUAE(), rows = [];
      q("[data-soon-city]").textContent = "في " + (CITY_AR[city] || city);
      S.r.forEach(function (r) {
        var c = S.c[r[0]]; if (c[2] !== city) return;
        var st = startOf(S.d, r[2]); if (st < now - 5 * 60e3 || st > now + 3 * 3600e3) return;
        rows.push({ st: st, r: r, c: c });
      });
      rows.sort(function (a, b) { return a.st - b.st; });
      var seen = {}, pick = [];
      rows.forEach(function (x) { if (pick.length < 2 && !seen[x.r[1]]) { seen[x.r[1]] = 1; pick.push(x); } });   /* two films (owner) */
      q("[data-soon-rows]").innerHTML = pick.map(function (x) {
        var f = S.f[x.r[1]], mins = Math.max(0, Math.round((x.st - now) / 60e3)), tt = t12(x.r[2]);
        /* the time card: the hour large, its part of the day under it; «بعد N د» as a badge that glows under 15 minutes */
        var pst = f[2] ? '<img class="sr-p" src="' + esc(f[2]) + '" alt="" loading="lazy">' : "";
        var mark = chm(x.c[3], x.c[4]);
        return '<a class="sr" href="' + A.base + "f/" + f[0] + '/"><span class="tcard"><b>' + tt[0] + "</b><small>" + tt[1] + "</small></span>" + pst + '<span class="sr-b"><b>' + esc(f[1]) + "</b><small>" + mark + esc(x.c[1]) +
          '</small><span class="sr-m"><em class="eta' + (mins < 15 ? " hot" : "") + '">' + (mins < 1 ? "يبدأ الحين" : "بعد " + mins + " د") + "</em>" + (x.r[3] ? '<b class="pr">' + x.r[3] + AED + "</b>" : "") + "</span></span></a>";
      }).join("");
      q("[data-soon-none]").hidden = pick.length > 0;
    };
    paintSoon(); setInterval(paintSoon, 60e3);
  }

  /* ── film and cinema pages ── */
  var pg = q(".pg");
  if (pg) {
    /* the back arrow goes back (the pop slide) when we came from inside the app */
    var back = q("[data-back]");
    if (back) back.addEventListener("click", function (e) {
      if (d.referrer && d.referrer.indexOf(location.origin) === 0 && history.length > 1) { e.preventDefault(); history.back(); }
    });
    if (pg.classList.contains("film")) {
      var onScroll = function () { pg.classList.toggle("scrolled", scrollY > 160); };
      addEventListener("scroll", onScroll, { passive: true }); onScroll();
    }

    var ab = q("[data-about]");
    if (ab) {
      var cl = q("[data-clamp]", ab), mb = q("[data-more]", ab);
      if (cl.scrollHeight > cl.clientHeight + 4) mb.hidden = false;
      mb.addEventListener("click", function () { var o = ab.classList.toggle("open"); mb.textContent = o ? "أقل" : "المزيد"; });
    }
    var T = null;
    try { T = JSON.parse((q("#shows") || {}).textContent || "null"); } catch (e) {}
    var minOf = function (r) { var ss = T.s[r[6]] || []; return ss.length ? Math.min.apply(null, ss.map(function (p) { return p[1]; })) : 0; };
    var day = A.today;
    var days = qa("[data-day]").filter(function (b) {
      if (b.dataset.day < A.today) { b.remove(); return false; }
      b.textContent = b.dataset.day === A.today ? "اليوم" : b.dataset.day === A.tomorrow ? "بكرة" : b.textContent;
      return true;
    });
    if (days.length && !days.some(function (b) { return b.dataset.day === A.today; })) day = days[0].dataset.day;
    var city = null;
    var ctabs = qa("[data-ctab]");
    if (ctabs.length) {
      var want = store.get("city");
      city = ctabs.some(function (b) { return b.dataset.ctab === want; }) ? want : ctabs[0].dataset.ctab;
    }
    var paint = function () {
      var now = nowUAE(), soon = now + 45 * 60e3, left = 0;
      days.forEach(function (b) { b.classList.toggle("on", b.dataset.day === day); });
      ctabs.forEach(function (b) { b.classList.toggle("on", b.dataset.ctab === city); });
      qa(".city[data-city]").forEach(function (c) { c.hidden = c.dataset.city !== city; });
      qa(".tbtn").forEach(function (b) {
        var st = startOf(b.dataset.d, b.dataset.t), past = st < now - 10 * 60e3;
        b.hidden = b.dataset.d !== day;
        b.classList.toggle("past", past);
        b.classList.toggle("soon", !past && st < soon);
        if (!b.hidden && !past) left++;
      });
      /* a cinema (or a film on a cinema's page) with nothing that day leaves the list */
      qa(".cblock, .frow").forEach(function (r) { r.hidden = !qa(".tbtn", r).some(function (b) { return !b.hidden; }); });
      qa(".cblock, .frow").forEach(function (r) { if (!r.hidden) r.hidden = !qa(".tbtn", r).some(function (b) { return !b.hidden && !b.classList.contains("past"); }); });
      var visibleLeft = qa(".tbtn").some(function (b) { return !b.hidden && !b.classList.contains("past") && !b.closest("[hidden]"); });
      var pastMsg = q("[data-past]"); if (pastMsg) pastMsg.hidden = visibleLeft;
      /* nearest first, with the distance, once we know where the visitor is */
      if (here) qa(".city").forEach(function (c) {
        var bs = qa(".cblock", c);
        bs.forEach(function (b) { b._k = km(b); var el = q("[data-km]", b); if (el) el.textContent = kmText(b._k); });
        bs.sort(function (a, b) { return (a._k == null ? 1e9 : a._k) - (b._k == null ? 1e9 : b._k); }).forEach(function (b) { c.appendChild(b); });
      });
    };
    var nearest = q("[data-nearest]");
    var paintNearest = function () {
      if (!nearest || !T) return;
      var now = nowUAE(), best = null;
      T.r.forEach(function (r, i) {
        var c = T.c[r[7]]; if (!c || c[1] !== city) return;
        var st = startOf(r[0], r[1]); if (st < now + 5 * 60e3) return;
        if (!best || st < best.st) best = { st: st, r: r, i: i, c: c };
      });
      if (!best) { nearest.hidden = true; return; }
      var tt = t12(best.r[1]), mins = Math.round((best.st - now) / 60e3), pr = minOf(best.r);
      var eta = mins < 60 ? "بعد " + mins + " د" : (best.r[0] === A.today ? "اليوم" : "بكرة");
      q("[data-nearest-row]", nearest).innerHTML = '<button type="button" class="sr" data-open="' + best.i + '"><span class="tcard"><b>' + tt[0] + "</b><small>" + tt[1] +
        '</small></span><span class="sr-b"><b>' + chm(best.c[2], best.c[3]) + " " + esc(best.c[0]) + "</b>" + (best.r[3] ? "<small>" + esc(best.r[3]) + "</small>" : "") +
        '<span class="sr-m"><em class="eta' + (mins < 15 ? " hot" : "") + '">' + eta + "</em>" + (pr ? '<b class="pr">' + pr + AED + "</b>" : "") + "</span></span></button>";
      nearest.hidden = false;
    };
    days.forEach(function (b) { b.addEventListener("click", function () { day = b.dataset.day; vt(paint); }); });
    ctabs.forEach(function (b) { b.addEventListener("click", function () { city = b.dataset.ctab; store.set("city", city); vt(function () { paint(); paintNearest(); }); }); });
    paint(); paintNearest();
    setInterval(function () { paint(); paintNearest(); }, 60e3);

    /* the ticket */
    var sheet = q("[data-sheet]"), scrim = q("[data-scrim]"), openBtn = null;
    var close = function (fromPop) {
      if (!sheet || sheet.hidden) return;
      sheet.classList.add("closing");
      setTimeout(function () { sheet.hidden = true; sheet.classList.remove("closing"); sheet.style.transform = ""; scrim.hidden = true; }, 200);
      if (openBtn) { openBtn.classList.remove("on"); openBtn.focus({ preventScroll: true }); }
      if (!fromPop && history.state && history.state.sheet) history.back();
    };
    var open = function (b) {
      var r = T && T.r[+b.dataset.i]; if (!r) return;   /* r[7]: its cinema */
      var s = { d: r[0], t: r[1], e: r[2], h: r[3], b: r[4], l: r[5] }, seats = T.s[r[6]] || [];
      qa(".tbtn.on").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on"); openBtn = b;
      var cinEl = b.closest("[data-cin]"), filmRow = b.closest(".frow");
      q("[data-tk-cin]", sheet).textContent = cinEl ? (q(".cb-h b", cinEl) || {}).textContent || "" : (q(".chead h2") || {}).textContent || "";
      q("[data-tk-film]", sheet).textContent = filmRow ? (q(".fr-t", filmRow) || {}).textContent : (q(".ft") || {}).textContent;
      var when = [];
      if (s.h) when.push(s.h);
      if (s.e) when.push("يخلص تقريباً " + t12(s.e).join(" "));
      if (s.l) when.push(({ en: "إنجليزي", ar: "عربي", hi: "هندي", ta: "تاميل", ml: "مالايالام", te: "تيلوغو" })[s.l] || s.l);
      q("[data-tk-when]", sheet).textContent = when.join(" · ");
      var tt = t12(s.t);
      q("[data-tk-time]", sheet).textContent = tt[0];
      q("[data-tk-day]", sheet).textContent = (s.d === A.today ? "اليوم" : s.d === A.tomorrow ? "بكرة" : s.d) + " · " + tt[1];
      q("[data-tk-seats]", sheet).innerHTML = seats.length ? seats.map(function (p) { return "<tr><td>" + esc(p[0]) + "</td><td>" + esc(p[1]) + AED + "</td></tr>"; }).join("")
        : '<tr><td colspan="2">السعر في الشباك</td></tr>';
      var bk = q("[data-tk-book]", sheet); bk.href = s.b || "#";
      var altEl = q("[data-tk-alt]", sheet); if (altEl) altEl.remove();
      if (pg.classList.contains("film") && T && r[7]) {
        var mine = minOf(r), myCity = (T.c[r[7]] || [])[1], now2 = nowUAE(), cheap = null;
        T.r.forEach(function (x, i) {
          if (x[0] !== r[0] || (T.c[x[7]] || [])[1] !== myCity || startOf(x[0], x[1]) < now2 + 5 * 60e3) return;
          var p = minOf(x); if (p && (!cheap || p < cheap.p)) cheap = { p: p, x: x, i: i };
        });
        if (mine && cheap && mine - cheap.p >= 5) {
          var cc = T.c[cheap.x[7]], ttc = t12(cheap.x[1]);
          var line = d.createElement("button"); line.type = "button"; line.className = "tk-alt"; line.setAttribute("data-tk-alt", ""); line.dataset.open = cheap.i;
          line.innerHTML = "نفس الفيلم أرخص بـ<b>" + (Math.round((mine - cheap.p) * 100) / 100) + "</b>" + AED + ": " + ttc[0] + " " + ttc[1] + " في " + esc(cc[3]) + " — " + esc(cc[0]) + (cheap.x[3] ? "، " + esc(cheap.x[3]) : "");
          bk.parentNode.insertBefore(line, bk);
        }
      }
      sheet.hidden = false; scrim.hidden = false;
      history.pushState({ sheet: 1 }, "");
    };
    d.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(".tbtn");
      if (b) { open(b); return; }
      var o = e.target.closest && e.target.closest("[data-open]");
      if (o) { var tb2 = q('.tbtn[data-i="' + o.dataset.open + '"]'); if (tb2) { if (sheet && !sheet.hidden) { sheet.hidden = true; scrim.hidden = true; history.back(); } setTimeout(function () { open(tb2); }, sheet && !sheet.hidden ? 60 : 0); } return; }
      if (e.target.closest && (e.target.closest("[data-tk-close]") || e.target === scrim)) close();
    });
    addEventListener("popstate", function () { if (sheet && !sheet.hidden) close(true); });
    addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    /* drag the sheet down to close it */
    var grab = q("[data-grab]"), y0 = null;
    if (grab) {
      grab.addEventListener("pointerdown", function (e) { y0 = e.clientY; grab.setPointerCapture(e.pointerId); sheet.style.transition = "none"; });
      grab.addEventListener("pointermove", function (e) { if (y0 != null) sheet.style.transform = "translateY(" + Math.max(0, e.clientY - y0) + "px)"; });
      grab.addEventListener("pointerup", function (e) {
        var dy = e.clientY - (y0 || e.clientY); y0 = null; sheet.style.transition = "transform .2s var(--ease-out)";
        if (dy > 90) close(); else sheet.style.transform = "";
      });
    }

    /* the trailer */
    var tb = q("[data-trailer]");
    if (tb) tb.addEventListener("click", function () {
      var o = d.createElement("div");
      o.className = "trl";
      o.innerHTML = '<iframe src="https://www.youtube-nocookie.com/embed/' + encodeURIComponent(tb.dataset.trailer) + '?autoplay=1&rel=0" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen title="الإعلان"></iframe><button type="button" aria-label="سكّر">×</button>';
      d.body.appendChild(o);
      var shut = function () { o.remove(); };
      q("button", o).addEventListener("click", shut);
      o.addEventListener("click", function (e) { if (e.target === o) shut(); });
    });

    /* «اسأل الفيلم» */
    var ask = q("[data-ask]");
    var ao = q("[data-ask-open]");
    if (ao && ask) ao.addEventListener("click", function () { ask.scrollIntoView({ behavior: "smooth", block: "start" }); setTimeout(function () { q("input", ask).focus({ preventScroll: true }); }, 400); });
    if (ask && A.ask) {
      var form = q("[data-ask-form]", ask), input = q("input", form), outBox = q("[data-ask-out]", ask), busy = false;
      var salt = function () { try { return localStorage.getItem("cinema.salt") || ""; } catch (e) { return ""; } };
      var put = function (qq, inner) {
        var el = d.createElement("div"); el.className = "ask-a"; el.innerHTML = '<p class="ask-qq">' + esc(qq) + "</p>" + inner;
        outBox.insertBefore(el, outBox.firstChild); return el;
      };
      var asks = function (qq) {
        qq = String(qq || "").trim(); if (busy || qq.length < 2) return;
        busy = true;
        var el = put(qq, '<p class="ask-w">لحظة…</p>');
        fetch(A.ask + "ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fid: ask.dataset.fid, q: qq, lang: "ar", uid: salt() }) })
          .then(function (r) { return r.json().then(function (j) { return { s: r.status, j: j }; }, function () { return { s: r.status, j: {} }; }); })
          .then(function (x) {
            var j = x.j || {}, inner;
            if (x.s === 429) inner = '<p class="ask-t">وصلنا حد الأسئلة لليوم، جرّب بكرة.</p>';
            else if (x.s !== 200 || !j.answer) inner = '<p class="ask-t">ما قدرنا نجاوب الحين، جرّب مرة ثانية.</p>';
            else {
              var src = j.known ? '<small class="ask-src">' + (j.source === "plot" ? "من قصة الفيلم" : "من معلومات الفيلم") + "</small>" : "";
              var body = '<p class="ask-t">' + esc(j.answer) + "</p>" + src;
              inner = j.spoiler ? '<details class="ask-sp"><summary>يحرق — اضغط إذا تبا تعرف</summary>' + body + "</details>" : body;
            }
            el.innerHTML = '<p class="ask-qq">' + esc(qq) + "</p>" + inner;
          })
          .catch(function () { el.innerHTML = '<p class="ask-qq">' + esc(qq) + '</p><p class="ask-t">ما قدرنا نجاوب الحين، جرّب مرة ثانية.</p>'; })
          .then(function () { busy = false; });
      };
      form.addEventListener("submit", function (e) { e.preventDefault(); asks(input.value); input.value = ""; });
      qa("[data-ask-q]", ask).forEach(function (c) { c.addEventListener("click", function () { asks(c.dataset.askQ); }); });
    }
  }
})();
