/* filters and sort: genre / عائلي / للأطفال (films), «يخلص قبل» and ربعي's late shows (times), the prayer
   switch's «أخفِ العروض المتقاطعة», and the sort (price after your card, soonest, best reviewed).
   «مع منو رايح؟» is a preset over the same controls. Anything filtered out gets class x (display:none);
   a cinema, hall or film left with no time disappears with it, and an empty list says so. */
var GENRE_ON = !!q("[data-filter]");
function tmOn(a) { return !a.classList.contains("x") && !a.classList.contains("past") && !a.closest(".times[hidden]"); }
function anyTm(el) { return qa(".tm[data-start]", el).some(tmOn); }
function firstStart(el) {
  var m = 1e9;
  qa(".tm[data-start]", el).forEach(function (a) { if (tmOn(a)) { var sp = spanOf(a); if (sp && sp[0] < m) m = sp[0]; } });
  return m;
}
function payOf(fid) { var t = q('.film[data-fid="' + fid + '"]'); return t ? +t.getAttribute("data-pay") || 1e9 : 1e9; }
function sortKey(el) {
  var o = +el.getAttribute("data-o") || 0, tile = el.classList.contains("film"), off = tile && el.classList.contains("off") ? 1e7 : 0;
  var fid = el.getAttribute("data-fid");
  if (ST.sort === "price") return off + (tile ? +el.getAttribute("data-pay") || 1e9 : payOf(fid)) * 1e3 + o;
  if (ST.sort === "time") return off + (tile ? +el.getAttribute("data-first") / 6e4 || 1e9 : firstStart(el)) * 1e3 + o;
  if (ST.sort === "verdict") { var t = el.hasAttribute("data-v") ? el : q('.film[data-fid="' + fid + '"]') || el; return off + verdictRank(t.getAttribute("data-v")) * 1e5 + o; }
  return off + o;
}
function sortIn(box, sel) {
  if (!box) return;
  var els = qa(sel, box).filter(function (e) { return e.parentNode === box; });
  els.map(function (e) { return [sortKey(e), e]; }).sort(function (a, b) { return a[0] - b[0]; }).forEach(function (p) { box.appendChild(p[1]); });
}
function markControls() {
  qa("[data-filter]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-filter") === ST.filt ? "true" : "false"); });
  qa("[data-who]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-who") === ST.who ? "true" : "false"); });
  qa("[data-sort]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-sort") === ST.sort ? "true" : "false"); });
  qa("select[data-ends-before]").forEach(function (s) { s.value = ST.before; if (s.value !== ST.before) s.value = ""; s.parentNode.classList.toggle("on", !!ST.before); });
}

function applyFilters() {
  var late = whoPreset(ST.who).late, hide = ST.prayer && ST.hide, timeOn = !!(ST.before || late || hide);
  qa(".tm[data-start]").forEach(function (a) {
    var sp = spanOf(a);
    a.classList.toggle("x", !endsOk(sp, ST.before) || !lateOk(sp, late) || (hide && a.classList.contains("clash")));
  });
  [".times[data-d]", ".hl", ".scin", ".cg", ".fcity"].forEach(function (sel) {
    qa(sel).forEach(function (el) { el.classList.toggle("x", timeOn && !anyTm(el)); });
  });
  qa(".film[data-fid], .srow[data-fid], .cf[data-fid]").forEach(function (el) {
    if (el.closest(".similar")) return;
    var src = el.hasAttribute("data-genres") ? el : q('.film[data-fid="' + el.getAttribute("data-fid") + '"]') || el;
    var f = { genres: (src.getAttribute("data-genres") || "").split(" "), family: src.getAttribute("data-family") === "1", kids: src.getAttribute("data-kids") === "1" };
    var ok = !GENRE_ON || filmOk(f, ST.filt);
    if (ok && timeOn) ok = el.classList.contains("film") ? !S || el.getAttribute("data-fit") !== "0" : anyTm(el);
    el.classList.toggle("x", !ok);
  });
  sortIn(q("[data-films]"), ".film[data-fid]");
  sortIn(q(".sched"), ".srow");
  qa(".cfilms").forEach(function (c) { sortIn(c, ".cf"); });
  var list = page === "film" ? qa(".cg") : page === "cinema" ? qa(".cf") : qa("[data-films] .film");
  var none = list.length > 0 && !list.some(function (el) { return !el.classList.contains("x") && !el.closest(".x"); });
  qa("[data-empty]").forEach(function (e) {
    e.hidden = !none;
    if (none && !e.firstChild) e.innerHTML = esc(TX.empty) + ' <button type="button" class="lnk" data-reset>' + esc(TX.reset) + "</button>";
  });
  markControls();
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
