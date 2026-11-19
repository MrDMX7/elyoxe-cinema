/* «سينما» as an app: what needs the phone. The two lists side by side (swipe or tap a tab), the genre chips, the city
   and «الأقرب», the day switch, times already started, the ticket sheet (Back closes it, a drag down closes it), the
   trailer and «اسأل الفيلم». Pages themselves are static and move with cross-document view transitions (app.css). */
(function () {
  "use strict";
  var A = window.APP || {}, d = document, html = d.documentElement;
  /* the page's language: English pages carry window.APP.t (Arabic phrase → English); Arabic pages carry nothing */
  var tx = function (k) { return (A.t && A.t[k]) || k; };
  var q = function (s, r) { return (r || d).querySelector(s); }, qa = function (s, r) { return [].slice.call((r || d).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var store = { get: function (k) { try { return localStorage.getItem("cinema." + k); } catch (e) { return null; } },
                set: function (k, v) { try { localStorage.setItem("cinema." + k, v); } catch (e) {} } };
  /* disc:inline */
  /* the visitor's card (owner 2026-11-19): the one the site's card sheet saved («cinema.card»), or one picked in a ticket.
     Its rules are /data/discounts.json and its arithmetic discAfter(), above (build_app inlines src/js/disc.js's block):
     the same file and code as the cards page, so a price after a card reads the same on every page */
  var card = store.get("card") || "", DISC = null, discP = null;
  var loadDisc = function () {
    if (!discP) discP = fetch("/data/discounts.json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { DISC = j && j.rules ? j : null; return DISC; }, function () { return null; });
    return discP;
  };
  /* «33.60» when there are fils, «42» when not: site_kit.money / src/js/pure.js fmt() */
  var fmt = function (n) { var k = Math.round(n * 100); return k % 100 ? (k / 100).toFixed(2) : String(k / 100); };
  var cardName = function (id) {
    var c = DISC && (DISC.cards || []).filter(function (x) { return x.id === id; })[0];
    return c ? (A.lang === "en" ? c.name_en : c.name_ar) || id : id;
  };
  var CITY_AR = A.cities || { "dubai": "دبي", "abu-dhabi": "أبوظبي", "sharjah": "الشارقة", "al-ain": "العين", "ajman": "عجمان", "ras-al-khaimah": "رأس الخيمة", "fujairah": "الفجيرة", "umm-al-quwain": "أم القيوين" };

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
  function t12(t) { var h = +t.slice(0, 2), m = t.slice(3, 5); return [(h % 12 || 12) + ":" + m, h < 4 ? tx("بالليل") : h < 12 ? tx("الصبح") : h === 12 ? tx("الظهر") : tx("مساء")]; }
  var AED = (q("#aed") || {}).innerHTML || " " + tx("درهم");
  /* «من الساعة» (owner 2026-11-19): only what starts at the picked hour or later. Kept for the day it was picked
     («cinema.hour» = «17|2026-11-19»), so tomorrow opens on every time again. The film and cinema pages hide the times
     before it; the home hides the films with no show in the visitor's city from it. */
  var hourEl = q("[data-hour]"), onHour = null;
  var hour = (function () { var v = (store.get("hour") || "").split("|"); return v[1] === A.today && +v[0] ? +v[0] : 0; })();
  /* a show of day at time t passes when it starts at the hour or after (00:45 is that night's, so it passes «من 9») */
  var hourOk = function (day, t) { return !hour || startOf(day, t) >= startOf(day, hour + ":00"); };
  /* «من 5 العصر» for the empty lines; «from 5 pm» inside an English sentence */
  var hourSays = function (s) { return A.lang === "en" ? s.toLowerCase() : s; };
  var hourLabel = function () { return hourEl && hourEl.selectedIndex > 0 ? hourSays(hourEl.options[hourEl.selectedIndex].text) : ""; };
  if (hourEl) {
    hourEl.value = hour ? String(hour) : "";
    hourEl.parentNode.classList.toggle("on", !!hour);
    hourEl.addEventListener("change", function () {
      hour = +hourEl.value || 0;
      store.set("hour", hour ? hour + "|" + A.today : "");
      hourEl.parentNode.classList.toggle("on", !!hour);
      buzz();
      if (onHour) onHour();
    });
  }
  /* a chain's mark beside a cinema's name: its own app icon (window.APP.logos), else the coloured name tag */
  function chm(ch, name) {
    var src = A.logos && A.logos[ch];
    return src ? '<img class="chl" src="' + esc(src) + '" alt="' + esc(name) + '" width="20" height="20">' : '<i class="chm ch-' + esc(ch) + '">' + esc(name) + "</i>";
  }
  /* a short buzz on a tap that changes something (Android; iPhones ignore it) */
  function buzz() { try { if (navigator.vibrate && !matchMedia("(prefers-reduced-motion: reduce)").matches) navigator.vibrate(8); } catch (e) {} }
  var toastEl = q("[data-toast]"), toastT = 0;
  function toast(msg) {
    if (!toastEl) return;
    toastEl.innerHTML = "<span>" + esc(msg) + "</span>"; toastEl.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(function () { toastEl.hidden = true; }, 2200);
  }
  /* share: the phone's sheet, else the link to the clipboard */
  function share(title, text, url) {
    var data = { title: title, text: text, url: url };
    if (navigator.share) { navigator.share(data).catch(function () {}); return; }
    var s = (text ? text + "\n" : "") + url;
    if (navigator.clipboard) navigator.clipboard.writeText(s).then(function () { toast(tx("انحفظ الرابط")); }, function () { toast(url); });
    else toast(url);
  }
  d.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-share]");
    if (b) { buzz(); share(b.dataset.share, b.dataset.share, location.origin + location.pathname); }
  });
  /* سينماتي (owner 2026-10-22): starred cinemas, kept on this phone */
  var favs = [];
  try { favs = JSON.parse(store.get("favs") || "[]"); if (!Array.isArray(favs)) favs = []; } catch (e) { favs = []; }
  function paintFavs() {
    qa("[data-fav]").forEach(function (b) { var on = favs.indexOf(b.dataset.fav) >= 0; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on ? "true" : "false"); });
  }
  d.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-fav]");
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    var cid = b.dataset.fav, i = favs.indexOf(cid);
    if (i >= 0) favs.splice(i, 1); else favs.push(cid);
    store.set("favs", JSON.stringify(favs)); buzz(); paintFavs();
    toast(i >= 0 ? tx("انشالت من سينماتي") : tx("انضافت لسينماتي"));
    if (typeof paintFavList === "function") paintFavList();
  }, true);
  paintFavs();
  /* a poster fades in when it has loaded; until then its frame shimmers */
  function posterReady(img) { img.classList.add("ok"); var f = img.closest(".pst"); if (f) f.classList.add("ok"); }
  qa(".pst img").forEach(function (img) {
    if (img.complete && img.naturalWidth) posterReady(img);
    else { img.addEventListener("load", function () { posterReady(img); }); img.addEventListener("error", function () { posterReady(img); }); }
  });
  qa(".pst:not(:has(img))").forEach(function (f) { f.classList.add("ok"); });
  /* the poster travels (owner 2026-10-22): the tapped tile's poster is the one the film page's hero grows from, and
     coming back it returns to its tile */
  function nameTile(tile) { qa(".pst.vt").forEach(function (x) { x.classList.remove("vt"); }); var ps = tile && q(".pst", tile); if (ps) ps.classList.add("vt"); }
  d.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".tile[href]");
    if (t) { buzz(); nameTile(t); }
  });
  addEventListener("pagereveal", function (e) {
    var a = window.navigation && navigation.activation;
    if (e.viewTransition && a && a.from && a.navigationType === "traverse") {
      var from = a.from.url || "", t = qa(".tile[href]").filter(function (x) { return from.indexOf(x.getAttribute("href")) >= 0; })[0];
      if (t) { nameTile(t); e.viewTransition.finished.finally(function () { q(".pst", t).classList.remove("vt"); }); }
    }
  });

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
  function kmText(k) { return k == null ? "" : (k < 1 ? tx("أقل من كيلو") : Math.round(k) + " " + tx("كم")); }
  function locate(ok, fail) {
    if (!navigator.geolocation) { fail(); return; }
    navigator.geolocation.getCurrentPosition(function (p) {
      here = [p.coords.latitude, p.coords.longitude];
      try { sessionStorage.setItem("cinema.here", JSON.stringify(here)); } catch (e) {}
      ok();
    }, fail, { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 });
  }

  /* ── home: the bottom bar and the pager (owner 2026-10-19: السينمات · الأفلام · قريباً) ── */
  var pager = q("[data-pager]");
  if (pager) {
    var tabs = qa(".tabbar [data-tab]"), panes = qa(".pane", pager), ttl = q("[data-tab-title]");
    var KEYS = panes.map(function (p) { return p.dataset.key; });
    var setTab = function (i) {
      tabs.forEach(function (t, j) { t.classList.toggle("on", i === j); t.setAttribute("aria-selected", i === j ? "true" : "false"); });
      if (ttl) ttl.textContent = panes[i].getAttribute("aria-label");
      store.set("tab", KEYS[i]);
    };
    var go = function (i, smooth) { panes[i].scrollIntoView({ behavior: smooth ? "smooth" : "auto", inline: "start", block: "nearest" }); setTab(i); };
    tabs.forEach(function (t, i) { t.addEventListener("click", function () {
      if (t.classList.contains("on")) panes[i].scrollTo({ top: 0, behavior: "smooth" });   /* the active tab again: back to its top */
      buzz(); go(i, true);
    }); });
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) setTab(panes.indexOf(e.target)); }); }, { root: pager, threshold: 0.6 });
      panes.forEach(function (p) { io.observe(p); });
    }
    /* first: a link's #films / #coming, else the tab this visitor used last, else السينمات */
    var tab0 = location.hash.slice(1) || store.get("tab") || "cinemas";
    if (location.hash) history.replaceState(history.state, "", location.pathname + location.search);
    var wi = KEYS.indexOf(tab0);
    go(wi < 0 ? 0 : wi, false);

    /* ── search (owner 2026-10-22): films and cinemas by their Arabic or English names, as the visitor types ── */
    var srch = q("[data-search]"), sin = q("[data-search-in]"), sout = q("[data-search-out]"), IDX = null;
    try { IDX = JSON.parse((q("#idx") || {}).textContent || "null"); } catch (e) {}
    var fold = function (t) {
      return String(t || "").toLowerCase().replace(/[ً-ْـ]/g, "").replace(/[أإآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/[^؀-ۿa-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
    };
    var hit = function (hay, needle) { var h = fold(hay); return h.indexOf(needle) >= 0 || h.split(" ").some(function (w) { return w.indexOf(needle) === 0; }); };
    var openSearch = function () {
      if (!srch) return;
      srch.hidden = false; html.style.overflow = "hidden";
      history.pushState({ search: 1 }, "");
      setTimeout(function () { sin.focus(); }, 50);
    };
    var closeSearch = function (fromPop) {
      if (!srch || srch.hidden) return;
      srch.hidden = true; html.style.overflow = ""; sin.value = ""; sout.innerHTML = "";
      if (!fromPop && history.state && history.state.search) history.back();
    };
    var paintSearch = function () {
      var needle = fold(sin.value);
      if (!IDX || needle.length < 2) { sout.innerHTML = ""; return; }
      var fs = IDX.f.filter(function (f) { return hit(f[1], needle) || hit(f[2], needle); }).slice(0, 12);
      var cs = IDX.c.filter(function (c) { return hit(c[1], needle) || hit(c[2], needle) || hit(c[3] + " " + c[1], needle) || hit(c[4], needle); }).slice(0, 12);
      var out = "";
      if (fs.length) out += '<p class="srch-h">' + tx("الأفلام") + '</p>' + fs.map(function (f) {
        return '<a class="sr-r" href="' + esc(f[4]) + '"><span class="pst ok">' + (f[3] ? '<img class="ok" src="' + esc(f[3]) + '" alt="" loading="lazy">' : "") + "</span><span><b>" + esc(f[1]) + "</b>" + (f[2] && f[2] !== f[1] ? "<small>" + esc(f[2]) + "</small>" : "") + "</span></a>";
      }).join("");
      if (cs.length) out += '<p class="srch-h">' + tx("السينمات") + '</p>' + cs.map(function (c) {
        return '<a class="sr-r" href="' + esc(c[6]) + '">' + chm(c[5], c[3]).replace('class="chl"', 'class="chl" width="34" height="34" style="inline-size:34px;block-size:34px;border-radius:9px"') + "<span><b>" + esc(c[1]) + "</b><small>" + esc(c[3]) + " · " + esc(c[4]) + "</small></span></a>";
      }).join("");
      sout.innerHTML = out || '<p class="empty">' + tx("ما لقينا شي بهالاسم") + '.</p>';
    };
    if (srch) {
      q("[data-search-open]").addEventListener("click", function () { buzz(); openSearch(); });
      q("[data-search-close]").addEventListener("click", function () { closeSearch(false); });
      sin.addEventListener("input", paintSearch);
      sin.addEventListener("keydown", function (e) { if (e.key === "Escape") closeSearch(false); });
      addEventListener("popstate", function (e) { if (!(e.state && e.state.search)) closeSearch(true); });
      addEventListener("keydown", function (e) { if (e.key === "/" && srch.hidden && d.activeElement.tagName !== "INPUT") { e.preventDefault(); openSearch(); } });
    }

    /* ── sort (owner 2026-10-22): the most shown, the best rated, the newest ── */
    var grid = q("[data-grid]"), none = q("[data-none]");
    var sortMenu = q("[data-sort-menu]"), sortLabel = q("[data-sort-label]");
    var sortTiles = function (key) {
      var tiles = qa(".tile", grid);
      tiles.sort(function (a, b) {
        if (key === "sc") return (+b.dataset.sc || 0) - (+a.dataset.sc || 0) || (+b.dataset.n || 0) - (+a.dataset.n || 0);
        if (key === "rel") return (b.dataset.rel || "").localeCompare(a.dataset.rel || "") || (+b.dataset.n || 0) - (+a.dataset.n || 0);
        return (+b.dataset.n || 0) - (+a.dataset.n || 0);
      });
      tiles.forEach(function (t) { grid.appendChild(t); });
      if (typeof soon2hOn === "function" && soon2hOn()) paintSoon2h();
      qa("[data-sort]", sortMenu).forEach(function (b) { b.classList.toggle("on", b.dataset.sort === key); if (b.dataset.sort === key) sortLabel.textContent = b.textContent; });
      store.set("sort", key);
    };
    var applySort = function (key) { vt(function () { sortTiles(key); }); };
    if (sortMenu) {
      q("[data-sort-open]").addEventListener("click", function (e) {
        e.stopPropagation(); buzz();
        var r = e.currentTarget.getBoundingClientRect();
        sortMenu.style.top = (r.bottom + 6) + "px"; sortMenu.style.right = Math.max(8, innerWidth - r.right) + "px";
        sortMenu.hidden = !sortMenu.hidden;
      });
      qa("[data-sort]", sortMenu).forEach(function (b) { b.addEventListener("click", function () { sortMenu.hidden = true; buzz(); applySort(b.dataset.sort); }); });
      d.addEventListener("click", function () { sortMenu.hidden = true; });
      var s0 = store.get("sort"); if (s0 && s0 !== "n") applySort(s0);
    }

    /* genre chips: the grid shows only what the chip names; the reflow is a view transition.
       «يبدأ خلال ساعتين» (owner 2026-10-23): the films with a show in the visitor's city starting within two hours,
       earliest first, each tile saying when and where — from the same board as «يبدأ قريب منك» (#soon). */
    var S2 = null; try { S2 = JSON.parse((q("#soon") || {}).textContent || "null"); } catch (e) {}
    /* the hour on the home: after any chip, the tiles left are the films with a show still to start in the visitor's
       city at the hour or after (#soon carries all of today's) */
    var gateTiles = function () {
      if (!hour || !S2) return;
      var city = store.get("city") || "dubai", now = nowUAE(), ok = {}, n = 0, cut = 0;
      S2.r.forEach(function (r) {
        if (S2.c[r[0]][2] !== city || startOf(S2.d, r[2]) < now - 10 * 60e3 || !hourOk(S2.d, r[2])) return;
        ok[S2.f[r[1]][0]] = 1;
      });
      qa(".tile", grid).forEach(function (t) {
        if (!t.hidden && !ok[t.dataset.fid]) { t.hidden = true; cut++; }
        if (!t.hidden) n++;
      });
      if (!n && cut) none.textContent = tx("ما في أفلام") + " " + hourLabel() + " " + tx("في") + " " + (CITY_AR[city] || city) + ".";
      none.hidden = n > 0;
    };
    var paintSoon2h = function () {
      var city = store.get("city") || "dubai", now = nowUAE(), best = {};
      if (S2) S2.r.forEach(function (r) {
        var c = S2.c[r[0]]; if (c[2] !== city) return;
        var st = startOf(S2.d, r[2]); if (st < now - 10 * 60e3 || st > now + 2 * 3600e3) return;
        var fid = S2.f[r[1]][0];
        if (!best[fid] || st < best[fid].st) best[fid] = { st: st, c: c, t: r[2] };
      });
      var tiles = qa(".tile", grid), n = 0;
      tiles.forEach(function (t) {
        var b = best[t.dataset.fid]; t.hidden = !b; if (!b) return;
        n++;
        var mins = Math.max(0, Math.round((b.st - now) / 60e3)), e = q(".tm .eta", t);
        if (!e) { e = d.createElement("em"); e.className = "eta"; q(".tm", t).appendChild(e); }
        e.className = "eta" + (mins < 15 ? " hot" : "");
        e.textContent = (mins < 1 ? tx("يبدأ الحين") : tx("بعد") + " " + mins + " " + tx("د")) + " · " + b.c[1];
      });
      tiles.filter(function (t) { return !t.hidden; }).sort(function (x, y) { return best[x.dataset.fid].st - best[y.dataset.fid].st; }).forEach(function (t) { grid.appendChild(t); });
      none.textContent = tx("ما في فيلم يبدأ خلال ساعتين في") + " " + (CITY_AR[city] || city) + ".";
      none.hidden = n > 0;
      gateTiles();
    };
    /* the hall chips (owner 2026-11-18): data-h = «city:imax,vip;city:…» from today's shows; the visitor's city, else any */
    var hallOn = function (t, hall, city) {
      return (t.dataset.h || "").split(";").some(function (part) {
        var i = part.indexOf(":"); if (i < 0) return false;
        return (!city || part.slice(0, i) === city) && part.slice(i + 1).split(",").indexOf(hall) >= 0;
      });
    };
    var soon2hOn = function () { var c = q('[data-chip="soon2h"]'); return !!(c && c.classList.contains("on")); };
    var paintChip = function (k) {
      if (k === "soon2h") { paintSoon2h(); return; }
      qa(".tm .eta", grid).forEach(function (e) { e.remove(); });
      var n = 0, hall = k.indexOf("h-") === 0 ? k.slice(2) : null, city = store.get("city");
      qa(".tile", grid).forEach(function (t) {
        var on = k === "all" || (hall ? hallOn(t, hall, city) : (" " + t.dataset.g + " ").indexOf(" " + k + " ") >= 0);
        t.hidden = !on; if (on) n++;
      });
      none.textContent = hall ? tx("ما في أفلام بهالقاعة اليوم في") + " " + (CITY_AR[city] || city || "") + "."
                              : tx("ما في أفلام بهالتصنيف اليوم") + ".";
      none.hidden = n > 0;
      gateTiles();
      if (sortMenu) sortTiles(store.get("sort") || "n");   /* the chip's own order back, in the same transition */
    };
    var chipNow = function () { var c = q("[data-chip].on"); return c ? c.dataset.chip : "all"; };
    qa("[data-chip]").forEach(function (c) {
      c.addEventListener("click", function () {
        buzz();
        vt(function () {
          qa("[data-chip]").forEach(function (x) { x.classList.toggle("on", x === c); });
          paintChip(c.dataset.chip);
        });
        c.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
      });
    });
    onHour = function () { vt(function () { paintChip(chipNow()); }); };
    if (hour) paintChip(chipNow());
    setInterval(function () { if (soon2hOn()) paintSoon2h(); }, 60e3);
    var apple = /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
    if (!apple) qa("a.crem[data-gcal]").forEach(function (a) {
      a.href = a.dataset.gcal; a.removeAttribute("download"); a.target = "_blank"; a.rel = "noopener";
    });

    /* السينمات: the cities first; a city (or «أقرب سينما») opens its cinemas, and the phone's back returns */
    var clist = q("[data-clist]"), msg = q("[data-geo-msg]"), cities = q("[data-cities]"), cv = q("[data-cv]"), cvT = q("[data-cv-title]");
    var ccs = qa(".ccard", clist), order = ccs.slice();
    var favBox = q("[data-favs]"), favList = q("[data-favlist]");
    var paintFavList = function () {
      if (!favBox) return;
      favList.innerHTML = "";
      favs.forEach(function (cid) { var c = ccs.filter(function (x) { return x.dataset.cid === cid; })[0]; if (c) { var k = c.cloneNode(true); k.hidden = false; q("[data-km]", k).textContent = kmText(km(c)); favList.appendChild(k); } });
      favBox.hidden = !favList.children.length;
      paintFavs();
    };
    window.paintFavList = paintFavList;
    paintFavList();
    var cur = "cities|";
    var cvShow = function (mode, city) {
      if (cur === mode + "|" + (city || "")) return;   /* a back that only closed a ticket */
      cur = mode + "|" + (city || "");
      vt(function () {
        cities.hidden = mode !== "cities";
        cv.hidden = clist.hidden = mode === "cities";
        if (mode === "city") {
          order.forEach(function (c) { var k = km(c); q("[data-km]", c).textContent = kmText(k); c.hidden = c.dataset.city !== city; clist.appendChild(c); });
          var b = q('.crow[data-city="' + city + '"] b'); cvT.textContent = b ? b.textContent : "";
          msg.hidden = true;
        } else if (mode === "near") {
          ccs.forEach(function (c) { var k = km(c); c._k = k == null ? 1e9 : k; q("[data-km]", c).textContent = kmText(k); });
          ccs.slice().sort(function (a, b) { return a._k - b._k; }).forEach(function (c, i) { c.hidden = i >= 12; clist.appendChild(c); });
          cvT.textContent = tx("أقرب سينما لك");
          msg.hidden = true;
        }
      });
      panes[0].scrollTo({ top: 0 });
    };
    var cvOpen = function (mode, city) {
      history.pushState({ cv: mode, city: city || "" }, "");
      cvShow(mode, city);
      if (mode === "city") store.set("city", city);
    };
    qa(".crow", cities).forEach(function (r) { r.addEventListener("click", function () { cvOpen("city", r.dataset.city); }); });
    q("[data-cv-back]").addEventListener("click", function () { history.state && history.state.cv ? history.back() : cvShow("cities"); });
    addEventListener("popstate", function (e) { var st = e.state || {}; cvShow(st.cv === "near" && !here ? "cities" : (st.cv || "cities"), st.city); });
    var nb = q("[data-near]");
    if (nb) nb.addEventListener("click", function () {
      var done = function () {
        var cs = ccs.filter(function (c) { return km(c) != null; }).sort(function (a, b) { return km(a) - km(b); });
        if (cs[0] && km(cs[0]) < 60) store.set("city", cs[0].dataset.city);
        cvOpen("near");
      };
      if (here) { done(); return; }
      msg.hidden = false; msg.textContent = tx("لحظة، نحدد مكانك…");
      locate(done, function () { msg.textContent = tx("ما قدرنا نعرف مكانك — اختار مدينتك") + "."; });
    });
    /* back from a cinema page into a reloaded home: the view it left */
    var st0 = history.state || {};
    if (st0.cv === "city" || (st0.cv === "near" && here)) cvShow(st0.cv, st0.city);
  }

  /* a trailer, from any [data-trailer] (a film's button, a coming film's poster) */
  d.addEventListener("click", function (e) {
    var tb = e.target.closest && e.target.closest("[data-trailer]");
    if (!tb) return;
    var o = d.createElement("div");
    o.className = "trl";
    o.innerHTML = '<iframe src="https://www.youtube-nocookie.com/embed/' + encodeURIComponent(tb.dataset.trailer) + '?autoplay=1&rel=0" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen title="' + tx("الإعلان") + '"></iframe><button type="button" aria-label="' + tx("سكّر") + '">×</button>';
    d.body.appendChild(o);
    var shut = function () { o.remove(); };
    q("button", o).addEventListener("click", shut);
    o.addEventListener("click", function (ev) { if (ev.target === o) shut(); });
  });

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
      q("[data-soon-city]").textContent = tx("في") + " " + (CITY_AR[city] || city);
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
        return '<a class="sr" href="' + A.film + f[0] + '/"><span class="tcard"><b>' + tt[0] + "</b><small>" + tt[1] + "</small></span>" + pst + '<span class="sr-b"><b>' + esc(f[1]) + "</b><small>" + mark + esc(x.c[1]) +
          '</small><span class="sr-m"><em class="eta' + (mins < 15 ? " hot" : "") + '">' + (mins < 1 ? tx("يبدأ الحين") : tx("بعد") + " " + mins + " " + tx("د")) + "</em>" + (x.r[3] ? '<b class="pr">' + x.r[3] + AED + "</b>" : "") + "</span></span></a>";
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
      mb.addEventListener("click", function () { var o = ab.classList.toggle("open"); mb.textContent = o ? tx("أقل") : tx("المزيد"); });
    }
    var T = null;
    try { T = JSON.parse((q("#shows") || {}).textContent || "null"); } catch (e) {}
    /* one seat of a show after card c: discAfter()'s {a: the price after it or null, st, r: the rule} */
    var cut = function (r, aed, c) {
      var cc = T.c[r[7]], hp = (T.h || [])[r[8]] || [];
      return c && DISC && cc ? discAfter(DISC.rules, A.today, aed, cc[2], hp[0], hp[1], r[7], c, r[0]) : { a: null };
    };
    /* the least a visitor with card c pays for a show (its list price where the card does not apply); 0 = no price */
    var payOf = function (r, c) {
      var b = 0;
      (T.s[r[6]] || []).forEach(function (p) { var x = cut(r, p[1], c), v = x.a != null ? x.a : p[1]; if (v > 0 && (!b || v < b)) b = v; });
      return b;
    };
    var listOf = function (r) { var ss = T.s[r[6]] || []; return ss.length ? Math.min.apply(null, ss.map(function (p) { return p[1]; })) : 0; };
    var minOf = function (r) { return payOf(r, card); };
    var day = A.today;
    var days = qa("[data-day]").filter(function (b) {
      if (b.dataset.day < A.today) { b.remove(); return false; }
      b.textContent = b.dataset.day === A.today ? tx("اليوم") : b.dataset.day === A.tomorrow ? tx("بكرة") : b.textContent;
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
        b.hidden = b.dataset.d !== day || !hourOk(b.dataset.d, b.dataset.t);
        b.classList.toggle("past", past);
        b.disabled = past;
        b.classList.toggle("soon", !past && st < soon);
        if (!b.hidden && !past) left++;
      });
      /* a cinema (or a film on a cinema's page) with nothing that day leaves the list */
      qa(".cblock, .frow").forEach(function (r) { r.hidden = !qa(".tbtn", r).some(function (b) { return !b.hidden; }); });
      qa(".cblock, .frow").forEach(function (r) { if (!r.hidden) r.hidden = !qa(".tbtn", r).some(function (b) { return !b.hidden && !b.classList.contains("past"); }); });
      var visibleLeft = qa(".tbtn").some(function (b) { return !b.hidden && !b.classList.contains("past") && !b.closest("[hidden]"); });
      var pastMsg = q("[data-past]");
      if (pastMsg) {
        /* nothing left only because of the hour: say the hour, not «خلصت عروض اليوم» */
        if (pastMsg._t == null) pastMsg._t = pastMsg.textContent;
        var byHour = !visibleLeft && hour && qa(".tbtn").some(function (b) {
          return b.dataset.d === day && !b.classList.contains("past") && !b.closest(".city[hidden]");
        });
        pastMsg.textContent = byHour ? tx("ما في عروض") + " " + hourLabel() + " " + hourSays(day === A.today ? tx("اليوم") : tx("بكرة")) + "." : pastMsg._t;
        pastMsg.hidden = visibleLeft;
      }
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
        var st = startOf(r[0], r[1]); if (st < now + 5 * 60e3 || !hourOk(r[0], r[1])) return;
        if (!best || st < best.st) best = { st: st, r: r, i: i, c: c };
      });
      if (!best) { nearest.hidden = true; return; }
      var tt = t12(best.r[1]), mins = Math.round((best.st - now) / 60e3), pr = minOf(best.r);
      var eta = mins < 60 ? tx("بعد") + " " + mins + " " + tx("د") : (best.r[0] === A.today ? tx("اليوم") : tx("بكرة"));
      q("[data-nearest-row]", nearest).innerHTML = '<button type="button" class="sr" data-open="' + best.i + '"><span class="tcard"><b>' + tt[0] + "</b><small>" + tt[1] +
        '</small></span><span class="sr-b"><b>' + chm(best.c[2], best.c[3]) + " " + esc(best.c[0]) + "</b>" + (best.r[3] ? "<small>" + esc(best.r[3]) + "</small>" : "") +
        '<span class="sr-m"><em class="eta' + (mins < 15 ? " hot" : "") + '">' + eta + "</em>" + (pr ? '<b class="pr">' + fmt(pr) + AED + "</b>" : "") + "</span></span></button>";
      nearest.hidden = false;
    };
    /* each time button's «from» price: the least after the visitor's card where the card lowers it (.cp), else the list
       price the page wrote */
    var paintPrices = function () {
      if (!T) return;
      qa(".tbtn[data-i]").forEach(function (b) {
        var r = T.r[+b.dataset.i], i = q("i", b); if (!r || !i) return;
        if (i._list == null) i._list = i.innerHTML;
        var m = payOf(r, card), on = !!(card && m && m < listOf(r));
        i.innerHTML = on ? fmt(m) + AED : i._list;
        i.classList.toggle("cp", on);
      });
    };
    days.forEach(function (b) { b.addEventListener("click", function () { day = b.dataset.day; vt(paint); }); });
    ctabs.forEach(function (b) { b.addEventListener("click", function () { city = b.dataset.ctab; store.set("city", city); vt(function () { paint(); paintNearest(); }); }); });
    onHour = function () { vt(function () { paint(); paintNearest(); }); };
    paint(); paintNearest();
    setInterval(function () { paint(); paintNearest(); }, 60e3);
    if (card && T) loadDisc().then(function () { paintPrices(); paintNearest(); });

    /* the ticket */
    var sheet = q("[data-sheet]"), scrim = q("[data-scrim]"), openBtn = null, tkRow = null;
    /* «صوّتوا مع الربع» (2026-11-20): the open show joins the tray (cinema.vote, at most 4) or leaves it */
    var voteCur = null, voteBtn = q("[data-tk-vote]", sheet || d);
    var sameShow = function (a, b2) { return a.k.fid === b2.k.fid && a.k.cin === b2.k.cin && a.k.date === b2.k.date && a.k.time === b2.k.time; };
    var paintVoteBtn = function () {
      if (!voteBtn) return;
      voteBtn.hidden = !voteCur || !A.vote;
      if (!voteCur) return;
      var inIt = vtray().some(function (x) { return sameShow(x, voteCur); });
      voteBtn.textContent = inIt ? tx("✓ في التصويت") : tx("+ للتصويت مع الربع");
      voteBtn.classList.toggle("on", inIt);
    };
    if (voteBtn) voteBtn.addEventListener("click", function () {
      if (!voteCur) return;
      buzz();
      var v = vtray(), at = -1;
      v.forEach(function (x, i) { if (sameShow(x, voteCur)) at = i; });
      if (at >= 0) { v.splice(at, 1); toast(tx("انشال من التصويت")); }
      else if (v.length >= 4) { toast(tx("التصويت فيه 4 عروض")); return; }
      else { v.push(voteCur); toast(tx("انضاف للتصويت")); }
      vsave(v); paintVoteBtn();
    });
    /* what the ticket says about money, redrawn when the card changes or the rules arrive: each seat after the card (the
       list price struck after it), a line on the card (its terms, or why it does not apply here) with the cards that lower
       this show's price as chips, and «نفس الفيلم أرخص» measured after the card too */
    var fillTicket = function () {
      var r = tkRow; if (!r || !sheet) return;
      var seats = T.s[r[6]] || [], c = T.c[r[7]] || [];
      q("[data-tk-seats]", sheet).innerHTML = seats.length ? seats.map(function (p) {
        var x = cut(r, p[1], card);
        return "<tr><td>" + esc(p[0]) + (x.a != null && x.r.type === "bogo" ? "<small>" + tx("للشخص، مع تذكرتين") + "</small>" : "") + "</td><td>" +
          (x.a != null ? "<b>" + fmt(x.a) + "</b>" + AED + " <s>" + fmt(p[1]) + "</s>" : esc(p[1]) + AED) + "</td></tr>";
      }).join("") : '<tr><td colspan="2">' + tx("السعر في الشباك") + "</td></tr>";
      var box = q("[data-tk-card]", sheet);
      if (box) {
        var list = listOf(r), mine = card && seats.length ? cut(r, seats[0][1], card) : null, html2 = "";
        /* the government cards first (most of who asks), then the cheapest; six shown, «المزيد» opens the rest (VOX has 17) */
        var opts = DISC && list ? (DISC.cards || []).map(function (k) { return { id: k.id, g: k.kind === "gov" ? 0 : 1, n: payOf(r, k.id), x: cut(r, list, k.id) }; })
          .filter(function (o) { return o.n && o.n < list && o.id !== card; }).sort(function (a, b) { return a.g - b.g || a.n - b.n; }) : [];
        if (mine && mine.a != null) {
          var tm = [];
          if (mine.r.box_office_only) tm.push(tx("من الشباك بس، مب في الحجز أونلاين"));
          if (mine.r.max_tickets) tm.push(tx("لين") + " " + mine.r.max_tickets + " " + tx("تذاكر"));
          html2 = '<p class="tkc-h"><span><b>' + tx("السعر بعد") + " " + esc(cardName(card)) + "</b>" + (tm.length ? "<small>" + esc(tm.join(" · ")) + "</small>" : "") +
            '</span><button type="button" class="tkc-chg" data-tkc-chg>' + tx("غيّر") + "</button></p>";
        } else if (mine && DISC) {
          html2 = '<p class="tkc-h"><span>' + esc(cardName(card)) + " " + (mine.st === "excluded" ? tx("ما تشمل هالقاعة") : tx("ما لقينا لها خصم في") + " " + esc(c[3] || "")) + "</span></p>";
        } else if (opts.length) {
          html2 = '<p class="tkc-h"><span><b>' + tx("عندك بطاقة خصم؟") + "</b></span></p>";
        }
        if (html2 && (opts.length || card)) html2 += '<div class="tkc-opts">' + opts.map(function (o, i) {
          return '<button type="button" class="tkc' + (i >= 6 ? " xtra" : "") + '" data-card="' + esc(o.id) + '">' + esc(cardName(o.id)) + " <b>" +
            (o.x.r && o.x.r.type === "bogo" ? "1+1" : fmt(o.n) + AED) + "</b></button>";
        }).join("") + (opts.length > 6 ? '<button type="button" class="tkc tkc-more" data-tkc-more>' + tx("المزيد") + " <b>" + (opts.length - 6) + "</b></button>" : "") +
          (card ? '<button type="button" class="tkc" data-card="">' + tx("بدون بطاقة") + "</button>" : "") + "</div>";
        box.innerHTML = html2; box.hidden = !html2; box.classList.remove("all");
        box.classList.toggle("shut", !!(mine && mine.a != null));
      }
      var altEl = q("[data-tk-alt]", sheet), bk = q("[data-tk-book]", sheet); if (altEl) altEl.remove();
      if (pg.classList.contains("film") && r[7]) {
        var me = minOf(r), myCity = c[1], now2 = nowUAE(), cheap = null;
        T.r.forEach(function (x, i) {
          if (x[0] !== r[0] || (T.c[x[7]] || [])[1] !== myCity || startOf(x[0], x[1]) < now2 + 5 * 60e3 || !hourOk(x[0], x[1])) return;
          var p = minOf(x); if (p && (!cheap || p < cheap.p)) cheap = { p: p, x: x, i: i };
        });
        if (me && cheap && me - cheap.p >= 5) {
          var cc = T.c[cheap.x[7]], ttc = t12(cheap.x[1]);
          var line = d.createElement("button"); line.type = "button"; line.className = "tk-alt"; line.setAttribute("data-tk-alt", ""); line.dataset.open = cheap.i;
          line.innerHTML = tx("نفس الفيلم أرخص بـ") + "<b>" + fmt(me - cheap.p) + "</b>" + AED + ": " + ttc[0] + " " + ttc[1] + " " + tx("في") + " " + esc(cc[3]) + " — " + esc(cc[0]) + (cheap.x[3] ? "، " + esc(cheap.x[3]) : "");
          bk.parentNode.insertBefore(line, bk);
        }
      }
    };
    /* a card chip: it becomes the visitor's card on every page (the site's card sheet reads the same «cinema.card»);
       «غيّر» opens the chips under a card that applies */
    if (sheet) sheet.addEventListener("click", function (e) {
      var k = e.target.closest && e.target.closest("[data-card]"), chg = e.target.closest && e.target.closest("[data-tkc-chg]");
      if (chg) { var bx = q("[data-tk-card]", sheet); if (bx) bx.classList.toggle("shut"); return; }
      if (e.target.closest && e.target.closest("[data-tkc-more]")) { var bm = q("[data-tk-card]", sheet); if (bm) bm.classList.add("all"); return; }
      if (!k) return;
      buzz(); card = k.dataset.card; store.set("card", card);
      fillTicket(); paintPrices(); paintNearest();
      toast(card ? tx("الأسعار الحين بعد") + " " + cardName(card) : tx("بدون بطاقة"));
    });
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
      if (s.e) when.push(tx("يخلص تقريباً") + " " + t12(s.e).join(" "));
      if (s.l) when.push(({ en: tx("إنجليزي"), ar: tx("عربي"), hi: tx("هندي"), ta: tx("تاميل"), ml: tx("مالايالام"), te: tx("تيلوغو") })[s.l] || s.l);
      q("[data-tk-when]", sheet).textContent = when.join(" · ");
      var tt = t12(s.t);
      q("[data-tk-time]", sheet).textContent = tt[0];
      q("[data-tk-day]", sheet).textContent = (s.d === A.today ? tx("اليوم") : s.d === A.tomorrow ? tx("بكرة") : s.d) + " · " + tt[1];
      q("[data-tk-book]", sheet).href = s.b || "#";
      tkRow = r; fillTicket();
      var fidEl = b.closest("[data-fid]") || q(".pg.film[data-fid]"), cinRow = T.c[r[7]] || [];
      voteCur = fidEl && cinRow[1] ? { k: { city: cinRow[1], date: r[0], cin: r[7], fid: fidEl.dataset.fid, time: r[1], hall: r[3] || "" },
        t: q("[data-tk-film]", sheet).textContent, c: q("[data-tk-cin]", sheet).textContent, d: r[0], tm: r[1] } : null;
      paintVoteBtn();
      if (!DISC) loadDisc().then(function () { if (tkRow === r) fillTicket(); paintPrices(); paintNearest(); });
      sheet.hidden = false; scrim.hidden = false;
      history.pushState({ sheet: 1 }, "");
      var sh = q("[data-tk-share]", sheet);
      if (sh) sh.onclick = function () {
        buzz();
        var film = q("[data-tk-film]", sheet).textContent, cin = q("[data-tk-cin]", sheet).textContent;
        share(film, film + " — " + cin + "، " + q("[data-tk-day]", sheet).textContent.replace(" · ", " ") + " " + tt[0], location.origin + location.pathname);
      };
    };
    /* سينماتي first in «وين يعرض» (the starred cinemas of the city at the top) */
    if (favs.length) qa(".city[data-city]").forEach(function (cityEl) {
      qa(".cblock[data-cin]", cityEl).reverse().forEach(function (blk) { if (favs.indexOf(blk.dataset.cin) >= 0) cityEl.insertBefore(blk, cityEl.firstChild); });
    });
    d.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(".tbtn");
      if (b) { if (!b.classList.contains("past")) { buzz(); open(b); } return; }
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
        var el = put(qq, '<p class="ask-w">' + tx("لحظة…") + '</p>');
        fetch(A.ask + "ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fid: ask.dataset.fid, q: qq, lang: A.lang || "ar", uid: salt() }) })
          .then(function (r) { return r.json().then(function (j) { return { s: r.status, j: j }; }, function () { return { s: r.status, j: {} }; }); })
          .then(function (x) {
            var j = x.j || {}, inner;
            if (x.s === 429) inner = '<p class="ask-t">' + tx("وصلنا حد الأسئلة لليوم، جرّب بكرة") + '.</p>';
            else if (x.s !== 200 || !j.answer) inner = '<p class="ask-t">' + tx("ما قدرنا نجاوب الحين، جرّب مرة ثانية") + '.</p>';
            else {
              var src = j.known ? '<small class="ask-src">' + (j.source === "plot" ? tx("من قصة الفيلم") : tx("من معلومات الفيلم")) + "</small>" : "";
              var body = '<p class="ask-t">' + esc(j.answer) + "</p>" + src;
              inner = j.spoiler ? '<details class="ask-sp"><summary>' + tx("يحرق — اضغط إذا تبا تعرف") + '</summary>' + body + "</details>" : body;
            }
            el.innerHTML = '<p class="ask-qq">' + esc(qq) + "</p>" + inner;
          })
          .catch(function () { el.innerHTML = '<p class="ask-qq">' + esc(qq) + '</p><p class="ask-t">' + tx("ما قدرنا نجاوب الحين، جرّب مرة ثانية") + '.</p>'; })
          .then(function () { busy = false; });
      };
      form.addEventListener("submit", function (e) { e.preventDefault(); asks(input.value); input.value = ""; });
      qa("[data-ask-q]", ask).forEach(function (c) { c.addEventListener("click", function () { asks(c.dataset.askQ); }); });
    }
  }

  // «عروض مجانية» (2026-11-19): the emirate chips filter the cards in place; a date or a section with nothing left hides,
  // and the page says so when the emirate has none. It opens on the visitor's own city when that city has screenings.
  var fcity = q("[data-free-city]");
  if (fcity) {
    var fnone = q("[data-free-none]");
    var paintFree = function (c) {
      qa(".chip", fcity).forEach(function (b) { b.classList.toggle("on", (b.dataset.c || "") === c); });
      var shown = 0;
      qa(".fgrp").forEach(function (g) {
        var any = 0;
        qa(".fcard", g).forEach(function (a) { var ok = !c || a.dataset.city === c; a.hidden = !ok; if (ok) any++; });
        g.hidden = !any;
        var h = g.previousElementSibling;
        if (h && (h.classList.contains("cday") || h.classList.contains("fh"))) h.hidden = !any;
        shown += any;
      });
      if (fnone) fnone.hidden = shown > 0;
    };
    fcity.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest(".chip") : null;
      if (!b) return;
      buzz();
      vt(function () { paintFree(b.dataset.c || ""); });
    });
    var mine = store.get("city");
    if (mine && q('.chip[data-c="' + mine + '"]', fcity)) paintFree(mine);
  }

  // «صوّتوا مع الربع» (2026-11-20): the tray bar (the shows collected from tickets) and the poll page /v/?p=<id>,
  // both on the counter API (infra/counter/lambdas/vote.py). The poll holds the shows as the site publishes them.
  var VAPI = A.vote || "";
  var vbar = q("[data-vbar]");
  function vtray() { try { var v = JSON.parse(store.get("vote") || "[]"); return Array.isArray(v) ? v.slice(0, 4) : []; } catch (e) { return []; } }
  function vsave(v) { store.set("vote", v.length ? JSON.stringify(v.slice(0, 4)) : ""); paintVbar(); }
  function paintVbar() {
    if (!vbar) return;
    var v = vtray();
    vbar.hidden = !v.length || !VAPI;
    if (!v.length) return;
    q("[data-vbar-t]", vbar).textContent = v.length === 1 ? tx("عرض واحد للتصويت، ضيف عرض ثاني") : v.length + " " + tx("عروض للتصويت");
    q("[data-vbar-send]", vbar).disabled = v.length < 2;
  }
  if (vbar) {
    paintVbar();
    var vname = q("[data-vbar-name]", vbar);
    q("[data-vbar-clear]", vbar).addEventListener("click", function () { buzz(); vsave([]); vname.hidden = true; toast(tx("انشال التصويت")); });
    q("[data-vbar-send]", vbar).addEventListener("click", function () {
      var v = vtray(), btn = this;
      if (v.length < 2) return;
      var name = store.get("vname") || "";
      if (!name) {
        if (vname.hidden) { vname.hidden = false; vname.focus(); return; }
        name = (vname.value || "").trim().slice(0, 24);
        if (!name) { vname.focus(); return; }
        store.set("vname", name);
      }
      buzz(); btn.disabled = true;
      fetch(VAPI + "vote", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ options: v.map(function (x) { return x.k; }), by: name, lang: A.lang }) })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          btn.disabled = false;
          if (!res.ok || !res.j.id) {
            toast(res.j && res.j.error === "show" ? tx("عرض من العروض خلص أو تغيّر، شيله وجرّب") : tx("ما قدرنا ننشئ التصويت، جرّب بعد شوي"));
            return;
          }
          var url = location.origin + (A.lang === "en" ? "/en" : "") + "/v/?p=" + res.j.id;
          vsave([]); vname.hidden = true;
          var go = function () { location.href = url; }, text = name + " " + tx("يبا يعرف شو يناسبكم، صوّتوا هني:");
          if (navigator.share) navigator.share({ title: tx("وين نروح؟"), text: text, url: url }).then(go, go);
          else { share(tx("وين نروح؟"), text, url); setTimeout(go, 1500); }
        }, function () { btn.disabled = false; toast(tx("ما قدرنا ننشئ التصويت، جرّب بعد شوي")); });
    });
  }

  var poll = q("[data-poll]");
  if (poll) {
    var pid = (new URLSearchParams(location.search).get("p") || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 10);
    var mineKey = "v." + pid, me = null;
    try { me = JSON.parse(store.get(mineKey) || "null"); } catch (e) {}
    if (!me || !me.vk) {
      var rnd = new Uint8Array(18);
      (window.crypto || window.msCrypto).getRandomValues(rnd);
      me = { vk: btoa(String.fromCharCode.apply(null, rnd)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""), p: "" };
    }
    var vstate = null, myPicks = null, busy = false, myName = store.get("vname") || "";
    var errEl = q("[data-v-err]", poll), optsEl = q("[data-v-opts]", poll), listEl = q("[data-v-list]", poll);
    var who = q("[data-v-who]", poll), nameIn = q("[data-v-name]", poll), noteIn = q("[data-v-note]", poll);
    var isApple = /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && "ontouchend" in d);
    var timer = 0;
    var fail = function (msg) { errEl.textContent = msg; errEl.hidden = false; optsEl.innerHTML = ""; clearInterval(timer); };
    var dayWord = function (dd) { return dd === A.today ? tx("اليوم") : dd === A.tomorrow ? tx("بكرة") : dd.slice(8, 10) + "/" + dd.slice(5, 7); };
    var pick = function (o, ar, en) { return A.lang === "en" ? o[en] || o[ar] : o[ar] || o[en]; };
    var calHref = function (o) {
      if (isApple) return VAPI + "vote/" + pid + "/ics";
      var p2 = function (n) { return (n < 10 ? "0" : "") + n; };
      var t0 = new Date(o.date + "T" + o.time + ":00+04:00"), t1 = new Date(t0.getTime() + 150 * 60000);
      var z = function (t) { return t.getUTCFullYear() + p2(t.getUTCMonth() + 1) + p2(t.getUTCDate()) + "T" + p2(t.getUTCHours()) + p2(t.getUTCMinutes()) + "00Z"; };
      return "https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + encodeURIComponent(pick(o, "title_ar", "title_en") + " — " + pick(o, "cin_ar", "cin_en")) +
        "&dates=" + z(t0) + "/" + z(t1) + "&details=" + encodeURIComponent(location.href);
    };
    var render = function () {
      var st = vstate;
      if (!st) return;
      q("[data-v-by]", poll).textContent = st.by ? st.by + " " + tx("يبا يعرف شو يناسبكم") : tx("اختاروا العرض اللي يناسبكم");
      var mine = st.votes.filter(function (v) { return me.p && v.p === me.p; })[0];
      if (myPicks === null) myPicks = mine ? mine.picks.slice() : [];
      var per = st.opts.map(function (_, i) { return st.votes.filter(function (v) { return v.picks.indexOf(i) >= 0; }); });
      var best = -1, bestN = 0;
      per.forEach(function (vs, i) { if (vs.length > bestN) { best = i; bestN = vs.length; } });
      optsEl.innerHTML = st.opts.map(function (o, i) {
        var t = t12(o.time), on = myPicks.indexOf(i) >= 0, lead = i === best, hall = pick(o, "hall_ar", "hall_en");
        return '<article class="vopt' + (lead ? " lead" : "") + '"><div class="vo-when"><b>' + t[0] + "</b><small>" + t[1] + " · " + dayWord(o.date) + "</small></div>" +
          '<div class="vo-b"><h3 dir="auto">' + esc(pick(o, "title_ar", "title_en")) + '</h3><p class="vo-c">' + esc(pick(o, "cin_ar", "cin_en")) +
          (hall && hall !== "Standard" && hall !== "عادية" ? " · " + esc(hall) : "") + "</p>" +
          (o.price ? '<p class="vo-pr">' + tx("من") + " <b>" + fmt(o.price) + "</b>" + AED + "</p>" : "") +
          '<p class="vo-n">' + (per[i].length ? per[i].map(function (v) { return '<span class="vchip' + (me.p && v.p === me.p ? " me" : "") + '">' + esc(v.name) + "</span>"; }).join("")
            : '<span class="vo-0">' + tx("محد اختاره للحين") + "</span>") + "</p>" +
          '<button type="button" class="vo-pick' + (on ? " on" : "") + '" data-pick="' + i + '" aria-pressed="' + on + '">' + (on ? "✓ " : "") + tx("أنا معكم") + "</button>" +
          (lead ? '<div class="vo-go">' + (o.book ? '<a class="btn velvet" href="' + esc(o.book) + '" target="_blank" rel="noopener nofollow" data-book>' + tx("احجز") + "</a>" : "") +
            '<a class="btn ghost" href="' + esc(calHref(o)) + '"' + (isApple ? "" : ' target="_blank" rel="noopener"') + ">" + tx("أضف للتقويم") + "</a></div>" : "") +
          "</div></article>";
      }).join("");
      listEl.innerHTML = st.votes.length ? st.votes.map(function (v) {
        var what = v.no ? tx("ما يقدر هالمرة") : v.picks.map(function (i) { var o = st.opts[i]; return o ? t12(o.time)[0] + " " + pick(o, "title_ar", "title_en") : ""; }).join("، ");
        return "<li><b>" + esc(v.name) + "</b><span>" + esc(what) + "</span>" + (v.note ? "<q>" + esc(v.note) + "</q>" : "") + "</li>";
      }).join("") : '<li class="vo-0">' + tx("محد صوّت للحين، كن أول واحد") + "</li>";
      q("[data-v-no]", poll).classList.toggle("on", !!(mine && mine.no));
      who.hidden = !!myName;
      q("[data-v-me]", poll).hidden = !myName;
      q("[data-v-myname]", poll).textContent = myName;
      if (mine && d.activeElement !== noteIn) noteIn.value = mine.note || "";
    };
    var load = function () {
      if (!pid || !VAPI || d.hidden || busy) return;
      fetch(VAPI + "vote/" + pid, { cache: "no-store" })
        .then(function (r) { if (r.status === 404) { fail(tx("هالتصويت خلص أو الرابط غلط.")); return null; } return r.ok ? r.json() : null; })
        .then(function (j) { if (j && j.opts && !busy) { vstate = j; errEl.hidden = true; render(); } }, function () {});
    };
    var send = function (no) {
      if (!myName) { who.hidden = false; nameIn.focus(); toast(tx("اكتب اسمك أول")); return; }
      busy = true;
      fetch(VAPI + "vote/" + pid, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vk: me.vk, name: myName, picks: no ? [] : myPicks, no: !!no, note: (noteIn.value || "").slice(0, 60) }) })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          busy = false;
          if (!res.ok) { toast(tx("ما انحفظ صوتك، جرّب مرة ثانية")); return; }
          me.p = res.j.me; store.set(mineKey, JSON.stringify(me)); vstate = res.j; render();
        }, function () { busy = false; toast(tx("ما انحفظ صوتك، جرّب مرة ثانية")); });
    };
    if (!pid || !VAPI) fail(tx("الرابط ناقص. اطلب من اللي أرسله رابط جديد."));
    else {
      load();
      timer = setInterval(load, 10000);
      d.addEventListener("visibilitychange", function () { if (!d.hidden) load(); });
    }
    optsEl.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-pick]");
      if (!b || myPicks === null) return;
      buzz();
      var i = +b.dataset.pick, k = myPicks.indexOf(i);
      if (k >= 0) myPicks.splice(k, 1); else myPicks.push(i);
      render(); send(false);
    });
    q("[data-v-no]", poll).addEventListener("click", function () { buzz(); myPicks = []; render(); send(true); });
    who.addEventListener("submit", function (e) {
      e.preventDefault();
      var v = (nameIn.value || "").trim().slice(0, 24);
      if (!v) return;
      myName = v; store.set("vname", v); render();
      if (myPicks && myPicks.length) send(false);
    });
    q("[data-v-rename]", poll).addEventListener("click", function () { myName = ""; store.set("vname", ""); nameIn.value = ""; render(); nameIn.focus(); });
    noteIn.addEventListener("change", function () {
      var mine = vstate && vstate.votes.filter(function (v) { return me.p && v.p === me.p; })[0];
      if (myName && mine) send(!!mine.no);
    });
    q("[data-v-share]", poll).addEventListener("click", function () { buzz(); share(tx("وين نروح؟"), tx("صوّتوا هني:"), location.href); });
  }
})();
