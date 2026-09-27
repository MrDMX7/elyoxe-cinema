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
  /* the filter sheet's own chips (home, city): «لازم يخلص قبل» and the language, and the chips over the grid */
  var fl = flang();
  qa("[data-before]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-before") === ST.before ? "true" : "false"); });
  qa("[data-flang]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-flang") === fl ? "true" : "false"); });
  var sb = ST.sort && q('#sheet-sort [data-sort="' + ST.sort + '"]');
  qa("[data-sort-name]").forEach(function (e) { e.textContent = sb ? sb.textContent : TX.sort0; });
  var k = nActive();
  qa("[data-fcount]").forEach(function (e) { e.hidden = !k; e.textContent = k; });
}

function applyFilters() {
  markControls();   /* first: the empty-state line reads the controls' state */
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
    var f = { genres: (src.getAttribute("data-genres") || "").split(" "), family: src.getAttribute("data-family") === "1", kids: src.getAttribute("data-kids") === "1",
      v: src.getAttribute("data-v") };
    var ok = filmOk(f, filt()) && langOk(src.getAttribute("data-lang") || "", flang());
    if (ok && timeOn) ok = el.classList.contains("film") ? !S || el.getAttribute("data-fit") !== "0" : anyTm(el);
    el.classList.toggle("x", !ok);
  });
  sortIn(q("[data-films]"), ".film[data-fid]");
  sortIn(q(".sched"), ".srow");
  qa(".cfilms").forEach(function (c) { sortIn(c, ".cf"); });
  var list = page === "film" ? qa(".cg") : page === "cinema" ? qa(".cf") : qa("[data-films] .film");
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
