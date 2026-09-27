/* the film page's tabs (UI redesign Task 4): with no script, in-page links to sections stacked one after another;
   here a tablist — one panel shown, the others hidden; arrow keys move along the tabs (in the reading direction),
   Home/End to the ends; the chosen tab goes in the address (#cast) without a history entry, and an address with
   one (or a link to it, the hero's «قارن») opens that tab. */
function bindTabs() {
  var list = q("[data-tabs]");
  if (!list) return;
  var tabs = qa("a[data-tab]", list).filter(function (t) { return document.getElementById(t.getAttribute("data-tab")); });
  if (!tabs.length) return;
  var panels = tabs.map(function (t) { return document.getElementById(t.getAttribute("data-tab")); });
  list.setAttribute("role", "tablist");
  tabs.forEach(function (t, i) {
    var id = t.getAttribute("data-tab");
    t.id = "tab-" + id; t.setAttribute("role", "tab"); t.setAttribute("aria-controls", id);
    panels[i].setAttribute("role", "tabpanel"); panels[i].setAttribute("aria-labelledby", t.id); panels[i].tabIndex = 0;
  });
  function show(i, focus) {
    tabs.forEach(function (t, j) {
      var on = i === j;
      t.setAttribute("aria-selected", on ? "true" : "false"); t.tabIndex = on ? 0 : -1;
      panels[j].hidden = !on;
    });
    if (focus) tabs[i].focus();
  }
  function byId(id) {
    var el = id && document.getElementById(id), p = el && (el.getAttribute("role") === "tabpanel" ? el : el.closest("[role=tabpanel]"));
    return p ? panels.indexOf(p) : -1;
  }
  /* an address naming a tab (or anything inside one): that tab, and the tabs brought into view under the header */
  function fromHash(smooth) {
    var i = byId(decodeURIComponent(location.hash.slice(1)));
    if (i < 0) return false;
    show(i, false);
    list.scrollIntoView({ block: "start", behavior: smooth && !RM ? "smooth" : "auto" });
    return true;
  }
  /* at start-up, again once the page has loaded (the browser's own jump to the anchor, and images above, come after) */
  if (fromHash(false)) window.addEventListener("load", function () { requestAnimationFrame(function () { list.scrollIntoView({ block: "start" }); }); });
  else show(0, false);
  list.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[role=tab]");
    if (!t) return;
    e.preventDefault();
    show(tabs.indexOf(t), true);
    try { history.replaceState(history.state, "", "#" + t.getAttribute("data-tab")); } catch (x) {}
  });
  list.addEventListener("keydown", function (e) {
    var i = tabs.indexOf(document.activeElement), n = tabs.length, k = e.key;
    if (i < 0) return;
    var fwd = AR ? "ArrowLeft" : "ArrowRight", back = AR ? "ArrowRight" : "ArrowLeft";
    var j = k === fwd ? (i + 1) % n : k === back ? (i - 1 + n) % n : k === "Home" ? 0 : k === "End" ? n - 1 : -1;
    if (j < 0) return;
    e.preventDefault();
    show(j, true);
    try { history.replaceState(history.state, "", "#" + tabs[j].getAttribute("data-tab")); } catch (x) {}
  });
  /* the hero's «قارن» (data-tab-go) and any other in-page link to a tab */
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a || a.closest("[data-tabs]")) return;
    var i = byId(decodeURIComponent(a.getAttribute("href").slice(1)));
    if (i < 0) return;
    e.preventDefault();
    show(i, false);
    try { history.replaceState(history.state, "", a.getAttribute("href")); } catch (x) {}
    list.scrollIntoView({ block: "start", behavior: RM ? "auto" : "smooth" });
    tabs[i].focus({ preventScroll: true });
  });
  window.addEventListener("hashchange", function () { fromHash(true); });
}
