/* filters and sort: the one question on top of the «تصفية» sheet («مع منو» / «متى» / «وين», MASTER-PLAN §2.0 and §3.1),
   genre / «يستاهل» (films), «يخلص قبل» (times), the language, the prayer switch's «أخفِ العروض المتقاطعة», and the sort
   (price after your card, soonest, best reviewed). Anything filtered out gets class x (display:none); a cinema, hall or
   film left with no time disappears with it, and an empty list says so (§1.7).
   The question's answers are stored once each — cinema.who ("" = «كبار», family, kids), cinema.when ("" = any time today,
   now, tonight, late, tomorrow) and cinema.where ("" = anywhere, near, mine) — and read by the grid here and by the pick
   (W2-P2b: window.CINEMA.ask(), .askOpen(from) opens this sheet at its top, and «ask» is emitted on every change).
   Nothing else is set behind the visitor's back: the old «مع منو رايح؟» preset (genre, end time, sort, «ربعي»'s late
   shows) is deleted with «بروحي» and «ربعي» (§4.2 #26). */

/* pure (tests/test_w2_p4.py runs these in node) ---------------------------------------------------------------------- */
/* «مع منو» on a film: its tile's data-fits lists the answers it passes (kit/filters.who_fits); «كبار» ("") passes all */
function whoOk(fits, who) { return !who || (" " + (fits || "") + " ").indexOf(" " + who + " ") >= 0; }
/* «العيال»: a show from 06:00 that is over by 21:00 (span in minutes after its date's midnight, pure.js showSpan) */
function kidsOk(span) { return !span || (span[0] >= 360 && span[1] <= 1260); }
/* «متى»: [from, to) in ms at UAE time n (ms), or null for any time. «الحين» the next 2 h 30; «الليلة» from 18:00 and
   «بعد العشا» from 21:30, both to 03:00 (the night's last shows are dated the next day); «بكرة» the next day from 06:00
   to 03:00 after it. Between midnight and 03:00 the night still running is «الليلة», and «بكرة» is the day that starts. */
function whenWin(when, n) {
  var H = 3600e3, d0 = n - (n + 4 * H) % (24 * H), early = n - d0 < 3 * H, t0 = early ? d0 : d0 + 24 * H, from = { tonight: 18, late: 21.5 }[when];
  if (when === "now") return [n, n + 2.5 * H];
  if (from) return [early ? n : Math.max(n, d0 + from * H), t0 + 3 * H];
  return when === "tomorrow" ? [Math.max(n, t0 + 6 * H), t0 + 27 * H] : null;
}
/* «قريب مني»: the cinemas within 10 km of you, and never fewer than your 3 nearest (a city with none that close still
   answers). km = {cid: distance}; returns {cid: 1} */
function nearSet(km) {
  var ids = Object.keys(km).sort(function (a, b) { return km[a] - km[b]; }), out = {};
  ids.forEach(function (c, i) { if (i < 3 || km[c] <= 10) out[c] = 1; });
  return out;
}

/* the page ------------------------------------------------------------------------------------------------------------ */
/* «سينمتي»: the cinemas the visitor keeps (cinema.me cins, written by W3-P1's me.js); read only, never written here */
function mine() {
  try { var m = JSON.parse(localStorage.getItem("cinema.me") || "null"); return m && m.cins && m.cins.length ? m.cins : null; } catch (e) { return null; }
}
/* the cinemas «وين» allows, or null for any: «قريب مني» once the location is known (near.js), «سينمتي» once there is one */
function whereSet() {
  if (ST.where === "near" && LOC && G) { var km = {}; Object.keys(G).forEach(function (c) { var d = kmTo(c); if (d != null) km[c] = d; }); return nearSet(km); }
  var m = ST.where === "mine" && mine(), o = null;
  if (m) { o = {}; m.forEach(function (c) { o[c] = 1; }); }
  return o;
}
function ask() { return { who: ST.who || "", when: ST.when || "", where: ST.where || "" }; }
/* the pick's line «لـ: كبار، الحين، قريب مني ▾» opens this sheet, scrolled to its top (the question) */
function askOpen(from) { if (sheetOpen("sheet-filter", from)) { var s = q("#sheet-filter"); if (s) s.scrollTop = 0; } }

/* «العيال» after 20:00 tonight: nothing is over by 9 any more, so the sheet and the empty grid offer tomorrow morning */
function kidsLate() { return ST.who === "kids" && ST.when !== "tomorrow" && nowMin() >= 1200; }
/* the genre filter in force here: the remembered one if this page has its chip, else «الكل» */
function filt() { return effectiveFilter(ST.filt, qa("[data-filter]").map(function (b) { return b.getAttribute("data-filter"); })); }
/* the language in force: the remembered one where this page offers its chip (home's filter sheet), else any */
function flang() { return ST.flang && q('[data-flang="' + ST.flang.replace(/"/g, "") + '"]') ? ST.flang : ""; }
/* how many things are filtering (the «تصفية» chip's badge): who, when, where, genre, end time, language, prayer clashes */
function nActive() {
  return !!ST.who + !!ST.when + !!ST.where + (filt() !== "all") + !!ST.before + !!flang() + !!(ST.prayer && ST.hide);
}
function tmOn(a) { return !a.classList.contains("x") && !a.classList.contains("past") && !a.closest(".times[hidden]"); }
function anyTm(el) { return qa(".tm[data-start]", el).some(tmOn); }
function firstStart(el) {
  var m = 1e9;
  qa(".tm[data-start]", el).forEach(function (a) { if (tmOn(a)) { var sp = spanOf(a); if (sp && sp[0] < m) m = sp[0]; } });
  return m;
}
function payOf(fid) { var t = q('.film[data-fid="' + fid + '"]'); return t ? +t.getAttribute("data-pay") || 1e9 : 1e9; }
/* «الأحسن تقييم»: films with both a critics and an audience score first, then those with one, then those with
   none; inside each, the higher score (critics + audience); the verdict only breaks ties. sc = [critics,
   audience] from the page's #cinema-sc (pages/scores.py), either may be null. */
function scoreRank(sc, v) {
  var c = sc && typeof sc[0] === "number" ? sc[0] : null, a = sc && typeof sc[1] === "number" ? sc[1] : null;
  var tier = c != null && a != null ? 0 : c != null || a != null ? 1 : 2;
  var miss = tier === 0 ? 200 - c - a : tier === 1 ? 2 * (100 - (c != null ? c : a)) : 0;
  return tier * 1e4 + Math.max(0, miss) * 10 + verdictRank(v);
}
var SCORES = null;
function scoresOf(fid) {
  if (!SCORES) { var el = document.getElementById("cinema-sc"); try { SCORES = el ? JSON.parse(el.textContent) || {} : {}; } catch (e) { SCORES = {}; } }
  return SCORES[fid] || null;
}
function sortKey(el) {
  var o = +el.getAttribute("data-o") || 0, tile = el.classList.contains("film"), off = tile && el.classList.contains("off") ? 1e7 : 0;
  var fid = el.getAttribute("data-fid");
  if (ST.sort === "price") return off + (tile ? +el.getAttribute("data-pay") || 1e9 : payOf(fid)) * 1e3 + o;
  if (ST.sort === "time") return off + (tile ? +el.getAttribute("data-first") / 6e4 || 1e9 : firstStart(el)) * 1e3 + o;
  if (ST.sort === "verdict") { var t = el.hasAttribute("data-v") ? el : q('.film[data-fid="' + fid + '"]') || el; return (off ? 1e11 : 0) + scoreRank(scoresOf(fid), t.getAttribute("data-v")) * 1e3 + o; }
  return off + o;
}
function sortIn(box, sel) {
  if (!box) return;
  var els = qa(sel, box).filter(function (e) { return e.parentNode === box; });
  var to = els.map(function (e) { return [sortKey(e), e]; }).sort(function (a, b) { return a[0] - b[0]; });
  if (to.every(function (p, i) { return p[1] === els[i]; })) return;   /* already in order: no reflow, focus kept */
  to.forEach(function (p) { box.appendChild(p[1]); });
  /* a sideways row (the «الليلة» posters) would stay scrolled to where the old first tile went: a new order
     starts at its first film */
  if (box.scrollWidth > box.clientWidth) box.scrollLeft = 0;
}
function pressed(sel, attr, v) { qa(sel).forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute(attr) === v ? "true" : "false"); }); }
function markControls() {
  var f = filt();
  pressed("[data-filter]", "data-filter", f);
  pressed("[data-who]", "data-who", ST.who || "");
  pressed("[data-when]", "data-when", ST.when || "");
  pressed("[data-where]", "data-where", ST.where || "");
  pressed("[data-sort]", "data-sort", ST.sort);
  qa('[data-where="mine"]').forEach(function (b) { b.hidden = !mine(); });
  qa("select[data-ends-before]").forEach(function (s) { s.value = ST.before; if (s.value !== ST.before) s.value = ""; s.parentNode.classList.toggle("on", !!ST.before); });
  /* the filter sheet's own chips (home, city): «لازم يخلص قبل» and the language, and the chips over the grid */
  pressed("[data-before]", "data-before", ST.before);
  pressed("[data-flang]", "data-flang", flang());
  var sb = ST.sort && q('#sheet-sort [data-sort="' + ST.sort + '"]');
  qa("[data-sort-name]").forEach(function (e) { e.textContent = sb ? sb.textContent : TX.sort0; });
  var k = nActive();
  qa("[data-fcount]").forEach(function (e) { e.hidden = !k; e.textContent = k; });
}

/* a hall, a cinema, a film's row or a day whose every time has passed (on the day showing) is gone: the build
   leaves such a hall out, and this hides one whose last time passes while the page is open. A block with no
   time at all is not judged. The filters mark what they hide with xf; x (display:none) is xf or gone. */
var GONE = ".hl, .tl, .scin, .cg, .cf, .srow, .fcity, .day[data-d]";
function hideBy(el, v) { el.classList.toggle(el.matches(GONE) ? "xf" : "x", v); }
/* one pass over the times (hundreds on a busy film page), grouped by their parent (a hall's run holds several):
   each parent marks the blocks above it as having a time, and as having a time to come when one of its times has
   not started on the day showing; a block with times and none to come is gone. A walk up stops at a block that
   already knows as much, because the walk that raised it raised every block above it too. */
function hidePassed() {
  var els = qa(GONE).filter(function (el) { return !el.closest(".similar, [data-ticket]"); }), st = new Map(), par = new Map();
  if (!els.length) return st;
  els.forEach(function (el) { st.set(el, 0); });   /* 0 no time, 1 times all passed, 2 a time to come */
  qa(".tm[data-start]").forEach(function (a) {
    /* the chosen time (.on) counts as one to come: a show the visitor chose stays on screen after it starts
       (the film page's rule, UI redesign Task 4 I2), and its ticket with it */
    var p = a.parentElement, v = a.classList.contains("past") && !a.classList.contains("on") ? 1 : 2;
    if (p && !(par.get(p) >= v)) par.set(p, v);
  });
  par.forEach(function (v, p) {
    if (v === 2 && p.closest(".times[hidden]")) v = 1;   /* a day not showing has nothing to come on the day showing */
    for (var n = p; n && n !== body; n = n.parentElement) {
      var s = st.get(n);
      if (s === undefined) continue;
      if (s >= v) break;
      st.set(n, v);
    }
  });
  els.forEach(function (el) { el.classList.toggle("x", el.classList.contains("xf") || st.get(el) === 1); });
  return st;
}
function applyFilters() {
  markControls();   /* first: the empty-state line reads the controls' state */
  var kids = ST.who === "kids", hide = ST.prayer && ST.hide, timeOn = !!(ST.before || kids || hide);
  /* «متى» and «وين» are judged on the grid's tiles (home.js renderHome: data-fit); the times on a page follow the rest */
  var gridOn = timeOn || !!ST.when || !!whereSet();
  qa(".tm[data-start]").forEach(function (a) {
    var sp = spanOf(a);
    a.classList.toggle("x", !endsOk(sp, ST.before) || kids && !kidsOk(sp) || (hide && a.classList.contains("clash")));
  });
  [".times[data-d]", ".hl", ".scin", ".cg", ".fcity"].forEach(function (sel) {
    qa(sel).forEach(function (el) { hideBy(el, timeOn && !anyTm(el)); });
  });
  qa(".film[data-fid], .srow[data-fid], .cf[data-fid]").forEach(function (el) {
    if (el.closest(".similar")) return;
    var src = el.hasAttribute("data-genres") ? el : q('.film[data-fid="' + el.getAttribute("data-fid") + '"]') || el;
    var f = { genres: (src.getAttribute("data-genres") || "").split(" "), family: src.getAttribute("data-family") === "1", kids: src.getAttribute("data-kids") === "1",
      v: src.getAttribute("data-v") };
    var ok = filmOk(f, filt()) && langOk(src.getAttribute("data-lang") || "", flang()) && whoOk(src.getAttribute("data-fits"), ST.who);
    if (ok && gridOn) ok = el.classList.contains("film") ? !S || el.getAttribute("data-fit") !== "0" : !timeOn || anyTm(el);
    hideBy(el, !ok);
  });
  var gone = hidePassed();
  sortIn(q("[data-films]"), ".film[data-fid]");
  sortIn(q(".sched"), ".srow");
  qa(".cfilms").forEach(function (c) { sortIn(c, ".cf"); });
  /* «nothing matches» is said only when the filters emptied the list, never when the day's times ran out */
  var list = (page === "film" ? qa(".cg") : page === "cinema" ? qa(".cf") : qa("[data-films] .film")).filter(function (el) { return gone.get(el) !== 1; });
  var shown = list.filter(function (el) { return !el.classList.contains("x") && !el.closest(".x"); }).length, none = list.length > 0 && !shown, late = none && kidsLate();
  /* «كل الأفلام»: how many are left, on the heading, on the sheet's «اعرض N فيلم», and said once, politely; with none
     the button is disabled and says «ولا فيلم، خفّف التصفية» (§1.7), never «اعرض 0 فيلم» */
  var nn = filmsN(shown, lang);
  qa("[data-all-n]").forEach(function (e) { e.textContent = shown; });
  qa("[data-fn]").forEach(function (e) { e.textContent = nn; });
  qa("[data-show-all]").forEach(function (b) { b.disabled = none; });   /* its words follow (ui-grid.css) */
  qa("[data-fn-live]").forEach(function (e) { if (e.getAttribute("data-n") !== String(shown)) { e.setAttribute("data-n", shown); e.textContent = SH ? sub(TX.n_live, { n: nn }) : ""; } });
  qa("[data-empty]").forEach(function (e) {
    e.hidden = !none || late;
    if (none && !e.firstChild) e.innerHTML = esc(TX.empty) + ' <button type="button" class="lnk" data-reset>' + esc(TX.reset) + "</button>";
  });
  qa("[data-kids-late]").forEach(function (e) { e.hidden = !late; });
  if (page === "film") fsCheck();   /* a chosen time filtered away goes; the desktop takes the next one */
}
/* «مسح» / «شيل التصفية»: everything back, the question and the prayer switch too, and a row's preset (?f= ?sort= ?who= ?fl=)
   out of the address so a reload does not bring it back */
function resetFilters() {
  save("filt", "all"); save("before", ""); save("who", ""); save("when", ""); save("where", ""); save("sort", ""); save("hide", false); save("flang", ""); save("prayer", false);
  try {
    var u = new URL(location.href);
    ["f", "sort", "fl", "who"].forEach(function (k) { u.searchParams.delete(k); });
    if (u.href !== location.href) history.replaceState(history.state, "", u.pathname + u.search + u.hash);
  } catch (e) {}
  applyPrayer();
}
/* a change the tiles must be worked out again for (their data-fit): with the city's shows, renderHome; else the filters */
function refilter() { markControls(); if (S) renderHome(false); else applyFilters(); }
function bindFilters() {
  /* the stored answers; «بروحي» and «ربعي» (deleted) read as «كبار» and are forgotten */
  if (ST.who !== "family" && ST.who !== "kids" && ST.who) save("who", "");
  ST.when = /^(now|tonight|late|tomorrow)$/.test(get("when") || "") ? get("when") : "";
  ST.where = /^(near|mine)$/.test(get("where") || "") ? get("where") : "";
  /* the lazy pick (W2-P2b) reads the answers as K.ask() and opens this sheet with K.askOpen(from) (window.CINEMA is made
     at start-up, before «ready»); home.js's minute */
  on("ready", function () { if (window.CINEMA) { window.CINEMA.ask = ask; window.CINEMA.askOpen = askOpen; } });
  on("minute", homeMinute);
  qa(".film[data-fid], .srow, .cf").forEach(function (el, i) { el.setAttribute("data-o", i); });   /* the server's order */
  qa("[data-strip]").forEach(function (r) { qa(".tile[data-fid]", r).forEach(function (el, i) { el.setAttribute("data-o", i); }); });
  /* a home row's «الكل» opens «كل الأفلام» with its sort, filter or company chosen: ?sort= ?f= ?who= ?fl= (this visit only) */
  var ps = param("sort"), pf = param("f"), pl = param("fl"), pw = param("who");
  if (ps && q('[data-sort="' + ps.replace(/"/g, "") + '"]')) ST.sort = ps;
  if (pf && q('[data-filter="' + pf.replace(/"/g, "") + '"]')) ST.filt = pf;
  if (pl) ST.flang = pl;
  if (pw === "family" || pw === "kids") ST.who = pw;
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target : null, b, v, k;
    if (!t) return;
    if ((b = t.closest("[data-filter]"))) { save("filt", b.getAttribute("data-filter")); applyFilters(); }
    else if ((b = t.closest("[data-sort]"))) {
      var pick = b.closest("[data-sort-pick]");   /* the sort sheet chooses (and closes); elsewhere a pressed sort lets go */
      save("sort", !pick && ST.sort === b.getAttribute("data-sort") ? "" : b.getAttribute("data-sort")); applyFilters();
      if (pick && SH) sheetClose();
    }
    else if ((b = t.closest("[data-before]"))) { save("before", b.getAttribute("data-before")); refilter(); }
    else if ((b = t.closest("[data-flang]"))) { save("flang", b.getAttribute("data-flang")); applyFilters(); }
    else if (t.closest("[data-show-all]")) { var all = q("#all"); if (all) setTimeout(function () { all.scrollIntoView({ block: "start", behavior: RM ? "auto" : "smooth" }); }, 60); }
    else if ((b = t.closest("[data-prayer]"))) { save("prayer", !ST.prayer); applyPrayer(); }
    else if ((b = t.closest("[data-hide-clash]"))) { save("hide", !ST.hide); applyPrayer(); }
    else {
      /* the question: one value each; a pressed answer lets go (back to the default), «قريب مني» asks for the location */
      if ((b = t.closest("[data-who],[data-when],[data-where]"))) {
        k = b.hasAttribute("data-who") ? "who" : b.hasAttribute("data-when") ? "when" : "where";
        v = b.getAttribute("data-" + k);
        if (k === "who" && v !== "family" && v !== "kids") v = "";   /* the film page's «بروحي»/«ربعي» until W2-P3 drops them */
        save(k, v && ST[k] === v ? "" : v);
        if (k === "where" && ST.where === "near" && !LOC) askNear();
      }
      else if (t.closest("[data-kids-am]")) save("when", "tomorrow");
      else if (t.closest("[data-reset]")) resetFilters();
      else return;
      /* the grid again, and the pick hears the answers (W2-P2b) */
      refilter(); emit("ask", ask());
    }
  });
  qa("select[data-ends-before]").forEach(function (s) {
    s.addEventListener("change", function () { save("before", s.value); refilter(); });
  });
}
