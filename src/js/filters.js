/* filters and sort: genre / عائلي / للأطفال (films), «يخلص قبل» and ربعي's late shows (times), the prayer
   switch's «أخفِ العروض المتقاطعة», and the sort (price after your card, soonest, best reviewed).
   «مع منو رايح؟» is a preset over the same controls. Anything filtered out gets class x (display:none);
   a cinema, hall or film left with no time disappears with it, and an empty list says so. */
/* the genre filter in force here: the remembered one if this page has its chip, else «الكل» */
function filt() { return effectiveFilter(ST.filt, qa("[data-filter]").map(function (b) { return b.getAttribute("data-filter"); })); }
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
}
function markControls() {
  var f = filt();
  qa("[data-filter]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-filter") === f ? "true" : "false"); });
  qa("[data-who]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-who") === ST.who ? "true" : "false"); });
  qa("[data-sort]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-sort") === ST.sort ? "true" : "false"); });
  qa("select[data-ends-before]").forEach(function (s) { s.value = ST.before; if (s.value !== ST.before) s.value = ""; s.parentNode.classList.toggle("on", !!ST.before); });
}

/* a hall, a cinema, a film's row or a day whose every time has passed (on the day showing) is gone: the build
   leaves such a hall out, and this hides one whose last time passes while the page is open. A block with no
   time at all is not judged. The filters mark what they hide with xf; x (display:none) is xf or gone. */
var GONE = ".hl, .tl, .scin, .cg, .cf, .srow, .fcity, .day[data-d]";
function tmLive(a) { return !a.classList.contains("past") && !a.closest(".times[hidden]"); }
function isGone(el) { var ts = qa(".tm[data-start]", el); return ts.length > 0 && !ts.some(tmLive); }
function hideBy(el, v) { el.classList.toggle(el.matches(GONE) ? "xf" : "x", v); }
function hidePassed() {
  qa(GONE).forEach(function (el) {
    if (el.closest(".similar, [data-ticket]")) return;
    el.classList.toggle("x", el.classList.contains("xf") || isGone(el));
  });
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
    var f = { genres: (src.getAttribute("data-genres") || "").split(" "), family: src.getAttribute("data-family") === "1", kids: src.getAttribute("data-kids") === "1" };
    var ok = filmOk(f, filt());
    if (ok && timeOn) ok = el.classList.contains("film") ? !S || el.getAttribute("data-fit") !== "0" : anyTm(el);
    hideBy(el, !ok);
  });
  hidePassed();
  sortIn(q("[data-films]"), ".film[data-fid]");
  sortIn(q(".sched"), ".srow");
  qa(".cfilms").forEach(function (c) { sortIn(c, ".cf"); });
  /* «nothing matches» is said only when the filters emptied the list, never when the day's times ran out */
  var list = (page === "film" ? qa(".cg") : page === "cinema" ? qa(".cf") : qa("[data-films] .film")).filter(function (el) { return !isGone(el); });
  var none = list.length > 0 && !list.some(function (el) { return !el.classList.contains("x") && !el.closest(".x"); });
  qa("[data-empty]").forEach(function (e) {
    e.hidden = !none;
    if (none) e.innerHTML = esc(TX.empty) + (active() ? " " + esc(sub(TX.active, { f: active() })) : "") + ' <button type="button" class="lnk" data-reset>' + esc(TX.reset) + "</button>";
  });
  markControls();
}
/* what is filtering, in words: the pressed chips and the chosen time */
function active() {
  var out = [], f = filt(), b = f !== "all" && q('[data-filter="' + f + '"]'), w = ST.who && q('[data-who="' + ST.who + '"]'), s = q("select[data-ends-before]");
  if (w) out.push(w.textContent);
  if (b) out.push(b.textContent);
  if (ST.before && s && s.selectedIndex > 0) out.push(sub(TX.ends_b, { t: s.options[s.selectedIndex].text }));
  if (ST.prayer && ST.hide) out.push(TX.no_clash);
  return out.join(TX.sep);
}
function resetFilters() { save("filt", "all"); save("before", ""); save("who", ""); save("sort", ""); save("hide", false); applyPrayer(); }
function bindFilters() {
  qa(".film[data-fid], .srow, .cf").forEach(function (el, i) { el.setAttribute("data-o", i); });   /* the server's order */
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target : null, b;
    if (!t) return;
    if ((b = t.closest("[data-filter]"))) { save("filt", b.getAttribute("data-filter")); applyFilters(); }
    else if ((b = t.closest("[data-sort]"))) { save("sort", ST.sort === b.getAttribute("data-sort") ? "" : b.getAttribute("data-sort")); applyFilters(); }
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
