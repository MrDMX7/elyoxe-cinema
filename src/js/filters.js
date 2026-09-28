/* filters and sort: genre / عائلي / للأطفال (films), «يخلص قبل» and ربعي's late shows (times), the prayer
   switch's «أخفِ العروض المتقاطعة», and the sort (price after your card, soonest, best reviewed).
   «مع منو رايح؟» is a preset over the same controls. Anything filtered out gets class x (display:none);
   a cinema, hall or film left with no time disappears with it, and an empty list says so. */
/* the genre filter in force here: the remembered one if this page has its chip, else «الكل» */
function filt() { return effectiveFilter(ST.filt, qa("[data-filter]").map(function (b) { return b.getAttribute("data-filter"); })); }
/* the language in force: the remembered one where this page offers its chip (home's filter sheet), else any */
function flang() { return ST.flang && q('[data-flang="' + ST.flang.replace(/"/g, "") + '"]') ? ST.flang : ""; }
/* how many things are filtering (the «تصفية» chip's badge): genre, company, end time, language, prayer clashes */
function nActive() {
  /* a companion is one choice, even though it presets the genre and the end time: only a change on top counts */
  var p = whoPreset(ST.who), f = filt();
  return (f !== "all" && !(ST.who && f === p.filt)) + !!ST.who + !!(ST.before && !(ST.who && ST.before === p.before)) + !!flang() + !!(ST.prayer && ST.hide);
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
function markControls() {
  var f = filt();
  qa("[data-filter]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-filter") === f ? "true" : "false"); });
  qa("[data-who]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-who") === ST.who ? "true" : "false"); });
  qa("[data-sort]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-sort") === ST.sort ? "true" : "false"); });
  qa("select[data-ends-before]").forEach(function (s) { s.value = ST.before; if (s.value !== ST.before) s.value = ""; s.parentNode.classList.toggle("on", !!ST.before); });
  /* the filter sheet's own chips (home, city): «لازم يخلص قبل» and the language, and the chips over the grid */
  var fl = flang();
  qa("[data-before]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-before") === ST.before ? "true" : "false"); });
  qa("[data-flang]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-flang") === fl ? "true" : "false"); });
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
  var late = whoPreset(ST.who).late, hide = ST.prayer && ST.hide, timeOn = !!(ST.before || late || hide);
  qa(".tm[data-start]").forEach(function (a) {
    var sp = spanOf(a);
    a.classList.toggle("x", !endsOk(sp, ST.before) || !lateOk(sp, late) || (hide && a.classList.contains("clash")));
  });
  [".times[data-d]", ".hl", ".scin", ".cg", ".fcity"].forEach(function (sel) {
    qa(sel).forEach(function (el) { hideBy(el, timeOn && !anyTm(el)); });
  });
  qa(".film[data-fid], .srow[data-fid], .cf[data-fid]").forEach(function (el) {
    if (el.closest(".similar")) return;
    var src = el.hasAttribute("data-genres") ? el : q('.film[data-fid="' + el.getAttribute("data-fid") + '"]') || el;
    var f = { genres: (src.getAttribute("data-genres") || "").split(" "), family: src.getAttribute("data-family") === "1", kids: src.getAttribute("data-kids") === "1",
      v: src.getAttribute("data-v") };
    var ok = filmOk(f, filt()) && langOk(src.getAttribute("data-lang") || "", flang());
    if (ok && timeOn) ok = el.classList.contains("film") ? !S || el.getAttribute("data-fit") !== "0" : anyTm(el);
    hideBy(el, !ok);
  });
  var gone = hidePassed();
  sortIn(q("[data-films]"), ".film[data-fid]");
  sortIn(q(".sched"), ".srow");
  qa(".cfilms").forEach(function (c) { sortIn(c, ".cf"); });
  /* «nothing matches» is said only when the filters emptied the list, never when the day's times ran out */
  var list = (page === "film" ? qa(".cg") : page === "cinema" ? qa(".cf") : qa("[data-films] .film")).filter(function (el) { return gone.get(el) !== 1; });
  var shown = list.filter(function (el) { return !el.classList.contains("x") && !el.closest(".x"); }).length, none = list.length > 0 && !shown;
  /* «كل الأفلام»: how many are left, on the heading, on the sheet's «اعرض N فيلم», and said once, politely */
  var nn = filmsN(shown, lang);
  qa("[data-all-n]").forEach(function (e) { e.textContent = shown; });
  qa("[data-fn]").forEach(function (e) { e.textContent = nn; });
  qa("[data-fn-live]").forEach(function (e) { if (e.getAttribute("data-n") !== String(shown)) { e.setAttribute("data-n", shown); e.textContent = SH ? sub(TX.n_live, { n: nn }) : ""; } });
  qa("[data-empty]").forEach(function (e) {
    e.hidden = !none;
    if (none) e.innerHTML = esc(TX.empty) + (active() ? " " + esc(sub(TX.active, { f: active() })) : "") + ' <button type="button" class="lnk" data-reset>' + esc(TX.reset) + "</button>";
  });
  markControls();
  if (page === "film") fsCheck();   /* a chosen time filtered away goes; the desktop takes the next one */
}
/* what is filtering, in words: the pressed chips and the chosen time */
function active() {
  var out = [], f = filt(), b = f !== "all" && q('[data-filter="' + f + '"]'), w = ST.who && q('[data-who="' + ST.who + '"]'), s = q("select[data-ends-before]");
  if (w) out.push(w.textContent);
  if (b) out.push(b.textContent);
  var eb = ST.before && q('[data-before="' + ST.before + '"]'), lb = flang() && q('[data-flang="' + flang() + '"]');
  if (ST.before && eb) out.push(sub(TX.ends_b, { t: eb.textContent }));
  else if (ST.before && s && s.selectedIndex > 0) out.push(sub(TX.ends_b, { t: s.options[s.selectedIndex].text }));
  if (lb) out.push(lb.textContent);
  if (ST.prayer && ST.hide) out.push(TX.no_clash);
  return out.join(TX.sep);
}
/* «مسح» / «شيل التصفية»: everything back, the prayer switch too, and a row's preset (?f= ?sort= ?fl=) out of the
   address so a reload does not bring it back */
function resetFilters() {
  save("filt", "all"); save("before", ""); save("who", ""); save("sort", ""); save("hide", false); save("flang", ""); save("prayer", false);
  try {
    var u = new URL(location.href);
    ["f", "sort", "fl"].forEach(function (k) { u.searchParams.delete(k); });
    if (u.href !== location.href) history.replaceState(history.state, "", u.pathname + u.search + u.hash);
  } catch (e) {}
  applyPrayer();
}
function bindFilters() {
  qa(".film[data-fid], .srow, .cf").forEach(function (el, i) { el.setAttribute("data-o", i); });   /* the server's order */
  qa("[data-strip]").forEach(function (r) { qa(".tile[data-fid]", r).forEach(function (el, i) { el.setAttribute("data-o", i); }); });
  /* a home row's «الكل» opens «كل الأفلام» with its sort or filter chosen: ?sort= ?f= ?fl= (for this visit only) */
  var ps = param("sort"), pf = param("f"), pl = param("fl");
  if (ps && q('[data-sort="' + ps.replace(/"/g, "") + '"]')) ST.sort = ps;
  if (pf && q('[data-filter="' + pf.replace(/"/g, "") + '"]')) ST.filt = pf;
  if (pl) ST.flang = pl;
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target : null, b;
    if (!t) return;
    if ((b = t.closest("[data-filter]"))) { save("filt", b.getAttribute("data-filter")); applyFilters(); }
    else if ((b = t.closest("[data-sort]"))) {
      var pick = b.closest("[data-sort-pick]");   /* the sort sheet chooses (and closes); elsewhere a pressed sort lets go */
      save("sort", !pick && ST.sort === b.getAttribute("data-sort") ? "" : b.getAttribute("data-sort")); applyFilters();
      if (pick && SH) sheetClose();
    }
    else if ((b = t.closest("[data-before]"))) { save("before", b.getAttribute("data-before")); if (S) renderHome(false); else applyFilters(); }
    else if ((b = t.closest("[data-flang]"))) { save("flang", b.getAttribute("data-flang")); applyFilters(); }
    else if (t.closest("[data-show-all]")) { var all = q("#all"); if (all) setTimeout(function () { all.scrollIntoView({ block: "start", behavior: RM ? "auto" : "smooth" }); }, 60); }
    else if ((b = t.closest("[data-who]"))) {
      var w = ST.who === b.getAttribute("data-who") ? "" : b.getAttribute("data-who"), p = whoPreset(w);
      save("who", w); save("filt", p.filt); save("before", p.before); save("sort", p.sort);
      if (S) renderHome(false); else applyFilters();
    }
    else if (t.closest("[data-reset]")) { resetFilters(); if (S) renderHome(false); }
    else if ((b = t.closest("[data-prayer]"))) { save("prayer", !ST.prayer); applyPrayer(); }
    else if ((b = t.closest("[data-hide-clash]"))) { save("hide", !ST.hide); applyPrayer(); }
  });
  qa("select[data-ends-before]").forEach(function (s) {
    s.addEventListener("change", function () { save("before", s.value); if (S) renderHome(false); else applyFilters(); });
  });
}
