/* sheets (UI redesign Task 2): any <div class="sheet" id="X" role="dialog" aria-modal="true" hidden> (Kit.sheet)
   opens from an element carrying data-sheet-open="X" — the header's city and card pills are links with no
   script (the cinemas index, the cards page) and become buttons here. Phone: a bottom sheet; desktop: a side
   panel. While one is open everything else is inert and focus stays inside; ×, Esc, the scrim and the back
   button close it, and focus goes back to what opened it. One sheet at a time. */
var SH = null, shFrom = null, shPushed = false, shInert = [], shScrim = q("[data-sheet-scrim]");
function shInertOn(el) {
  shInert = [];
  for (var n = el; n && n !== body; n = n.parentElement) {
    var sibs = n.parentElement ? n.parentElement.children : [];
    for (var i = 0; i < sibs.length; i++) {
      var e = sibs[i];
      if (e === n || e === shScrim || e.inert || /^(SCRIPT|STYLE|TEMPLATE)$/.test(e.tagName)) continue;
      e.inert = true; shInert.push(e);
    }
  }
}
function shFocusables() {
  return qa('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])', SH).filter(function (e) { return e.offsetParent !== null || e === document.activeElement; });
}
function shOpeners(id) { return qa('[data-sheet-open="' + id + '"]'); }
function sheetOpen(id, from) {
  var el = document.getElementById(id);
  if (!el) return false;
  var back = shFrom;
  if (SH) sheetClose(false, true);
  SH = el; shFrom = back || from || document.activeElement;
  el.hidden = false;
  if (shScrim) shScrim.hidden = false;
  document.documentElement.classList.add("sheet-open");
  shOpeners(id).forEach(function (b) { b.setAttribute("aria-expanded", "true"); });
  shInertOn(el);
  if (!shPushed) { try { history.pushState({ sheet: id }, ""); shPushed = true; } catch (e) {} }
  /* focus the chosen option (the current city, the pressed card), else the first thing in the sheet */
  var pick = q('[aria-current="true"], [aria-pressed="true"]', el) || shFocusables()[0] || el;
  setTimeout(function () { pick.focus(); }, 30);
  return true;
}
/* fromPop: the back button already left the pushed entry. swap: another sheet opens at once (its history entry,
   and where focus goes back to, carry over) */
function sheetClose(fromPop, swap) {
  if (!SH) return;
  var id = SH.id;
  SH.hidden = true; SH = null;
  if (shScrim) shScrim.hidden = true;
  document.documentElement.classList.remove("sheet-open");
  shOpeners(id).forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
  shInert.forEach(function (e) { e.inert = false; }); shInert = [];
  if (swap) return;
  if (shPushed && fromPop !== true) { try { history.back(); } catch (e) {} }
  shPushed = false;
  if (shFrom && shFrom.focus) shFrom.focus();
  shFrom = null;
}
/* the header over a hero: a gradient until the page has moved 40 px, then solid night. A 40 px sentinel at the
   top of the page says when (an IntersectionObserver, not a scroll listener) */
function bindTop() {
  var top = q(".top");
  if (!top || !body.hasAttribute("data-hero")) return;
  if (!("IntersectionObserver" in window)) { top.classList.add("solid"); return; }
  var s = document.createElement("div"); s.className = "top-sent"; s.setAttribute("aria-hidden", "true");
  body.insertBefore(s, body.firstChild);
  new IntersectionObserver(function (es) { top.classList.toggle("solid", !es[es.length - 1].isIntersecting); }).observe(s);
}
function bindSheets() {
  bindTop();
  qa("[data-sheet-open]").forEach(function (b) {
    var id = b.getAttribute("data-sheet-open");
    if (!document.getElementById(id)) return;   // no such sheet on this page: the element stays what it was
    if (b.tagName === "A") b.setAttribute("role", "button");
    b.setAttribute("aria-haspopup", "dialog"); b.setAttribute("aria-expanded", "false"); b.setAttribute("aria-controls", id);
    b.addEventListener("click", function (e) { e.preventDefault(); sheetOpen(id, b); });
    /* a link that became a button answers Space as a button does */
    if (b.tagName === "A") b.addEventListener("keydown", function (e) { if (e.key === " ") { e.preventDefault(); b.click(); } });
  });
  document.addEventListener("click", function (e) { if (SH && e.target.closest && e.target.closest("[data-sheet-close]")) sheetClose(); });
  if (shScrim) shScrim.addEventListener("click", function () { sheetClose(); });
  document.addEventListener("keydown", function (e) {
    if (!SH) return;
    if (e.key === "Escape") { e.preventDefault(); sheetClose(); return; }
    if (e.key !== "Tab") return;
    var f = shFocusables(); if (!f.length) return;
    var a = f[0], z = f[f.length - 1];
    if (e.shiftKey && (document.activeElement === a || !SH.contains(document.activeElement))) { e.preventDefault(); z.focus(); }
    else if (!e.shiftKey && (document.activeElement === z || !SH.contains(document.activeElement))) { e.preventDefault(); a.focus(); }
  });
  window.addEventListener("popstate", function () { if (SH) { shPushed = false; sheetClose(true); } });
}
