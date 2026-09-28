/* sheets (UI redesign Task 2; W2-P5): any <div class="sheet" id="X" role="dialog" aria-modal="true" hidden> (Kit.sheet)
   opens from an element carrying data-sheet-open="X" — the header's city and card pills are links with no
   script (the cinemas index, the cards page) and become buttons here; a door a script draws later (the stub's) opens
   the same way, by delegation. Phone: a bottom sheet; desktop: a side panel. While one is open everything else is
   inert and focus stays inside; ×, Esc, the scrim, the back button and a drag (src/js/drag.js, loaded by chrome.js)
   close it, and focus goes back to what opened it. One sheet at a time. «sheet» on the hook bus says which opened
   (x = the element) and when none is (x = null). */
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
  return qa('a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', SH).filter(function (e) { return e.offsetParent !== null || e === document.activeElement; });
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
  dragLoad(); emit("sheet", el);
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
  emit("sheet", null);
  if (swap) return;
  if (shPushed && fromPop !== true) { try { history.back(); } catch (e) {} }
  shPushed = false;
  if (shFrom && shFrom.focus) shFrom.focus();
  shFrom = null;
}
/* leaving the page from inside an open sheet (a city pick on a city or cinema page, «قريب مني» there): the
   sheet's pushed history entry is replaced by the new page, so Back returns to the page as it was — never to a
   same-URL entry that bfcache could restore with the sheet still open */
function shGo(u) {
  if (shPushed) { shPushed = false; location.replace(u); } else location.href = u;
}
/* search triggers ([data-search]: the header's button; the tab bar's «بحث» link only while D2's flag is off) work before the lazy search
   chunk has arrived: the tap is kept, the chunk loaded if it is not on its way, and search.js opens the overlay
   for it as soon as it runs. A page without the chunk (or a chunk that never comes) follows the link. */
function searchTap(e) {
  var t = e.target.closest && e.target.closest("[data-search]");
  if (!t || e.defaultPrevented) return;   // the chunk's own listener already opened the overlay
  var u = C.chunks && C.chunks.search;
  if (!u) return;
  e.preventDefault();
  window.CINEMA_SEARCH_WANT = t;
  if (!q('script[src="' + u + '"]')) { var sc = document.createElement("script"); sc.src = u; sc.async = true; document.head.appendChild(sc); }
  setTimeout(function () { if (window.CINEMA_SEARCH_WANT === t) { window.CINEMA_SEARCH_WANT = null; if (t.href) location.href = t.href; } }, 8000);
}
/* an opener, however it came (the server's, or a door the script drew): it reads as a button that opens a dialog */
function shDecorate(r) {
  qa("[data-sheet-open]", r).forEach(function (b) {
    if (!document.getElementById(b.getAttribute("data-sheet-open")) || b.hasAttribute("aria-controls")) return;
    if (b.tagName === "A") b.setAttribute("role", "button");
    b.setAttribute("aria-haspopup", "dialog"); b.setAttribute("aria-expanded", "false"); b.setAttribute("aria-controls", b.getAttribute("data-sheet-open"));
  });
}
function bindSheets() {
  shDecorate();
  /* one listener for every opener: no such sheet on this page and the element stays what it was (a link follows) */
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-sheet-open]"), id = b && b.getAttribute("data-sheet-open");
    if (!b || !document.getElementById(id) || e.defaultPrevented) return;
    e.preventDefault(); shDecorate(b.parentNode); sheetOpen(id, b);
  });
  /* a link that became a button answers Space as a button does */
  document.addEventListener("keydown", function (e) {
    var b = e.key === " " && e.target.closest && e.target.closest("a[data-sheet-open][role=button]");
    if (b) { e.preventDefault(); b.click(); }
  });
  document.addEventListener("click", searchTap);
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
