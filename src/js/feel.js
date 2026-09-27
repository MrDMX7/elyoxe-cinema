/* Feel (roadmap 203, 204): what makes the next page arrive at once.
   Prerender (the speculation rules in src/page.html) opens a film, city or cinema page before the tap lands.
   A prerendered page is not seen yet, so it must not act yet: src/page.html's «boot» loader does not even run
   this bundle until the page is shown. whenActive(fn) and the feature() wrapper below are a second line
   (a feature registered after this file also waits for activation), for a bundle ever loaded another way.
   View transitions (src/css/transitions.css): on the page being left, the tapped poster tile is named «poster»
   so it grows into the film page's hero. */
function whenActive(fn) {
  if (!document.prerendering) { fn(); return; }
  document.addEventListener("prerenderingchange", function () { fn(); }, { once: true });
}
/* after the core has bound the page, each feature starts in a task of its own, in order: the main thread
   is given back between them (scheduler.yield where the browser has it, else a zero timeout), so start-up
   is a row of short tasks instead of one long one */
function nextTask(fn) {
  var s = window.scheduler;
  if (s && typeof s.yield === "function") s.yield().then(fn, fn); else setTimeout(fn, 0);
}
var featureNow = feature, featQ = [], featBusy = false;
function featDrain() {
  var fn = featQ.shift();
  if (!fn) { featBusy = false; return; }
  try { fn(); } catch (e) { if (window.console) console.error(e); }
  nextTask(featDrain);
}
feature = function (fn) {
  featureNow(function () {
    whenActive(function () {
      featQ.push(fn);
      if (!featBusy) { featBusy = true; nextTask(featDrain); }
    });
  });
};

/* the film a link opens: "/film/<fid>/" or "/en/film/<fid>/" (same origin only) */
function filmOf(href) {
  try {
    var u = new URL(href, location.href);
    var m = u.origin === location.origin && /^\/(?:en\/)?film\/([^\/]+)\/?$/.exec(u.pathname);
    return m ? decodeURIComponent(m[1]) : null;
  } catch (e) { return null; }
}
/* the «الحين» shortcut (manifest) opens /#now: the box shows once the city's slice is in, then it comes into view */
feature(function () {
  var box = q("[data-now]");
  if (!box || page !== "home" || location.hash !== "#now") return;
  box.id = "now";
  function go() { box.scrollIntoView({ block: "start", behavior: "instant" }); }
  if (!box.hidden) { go(); return; }
  var mo = new MutationObserver(function () { if (!box.hidden) { mo.disconnect(); go(); } });
  mo.observe(box, { attributes: true, attributeFilter: ["hidden"] });
});
var vtTapped = null, vtNamed = [];
function vtName(el, n) { el.style.viewTransitionName = n; vtNamed.push(el); }
function vtClear() { vtNamed.forEach(function (el) { el.style.viewTransitionName = ""; }); vtNamed = []; }
feature(function () {
  if (RM || !("onpageswap" in window)) return;
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[href]");
    vtTapped = a && filmOf(a.href) ? a : null;
  }, true);
  window.addEventListener("pageswap", function (e) {
    vtClear();
    if (!e.viewTransition) return;
    var to = e.activation && e.activation.entry && filmOf(e.activation.entry.url);
    var hero = q(".fposter .pst.hero");
    /* the same film in the other language: the hero stays the hero; anywhere else it leaves with the page */
    if (to && page === "film" && body.getAttribute("data-fid") === to) return;
    if (hero) vtName(hero, "none");
    var link = to && vtTapped && filmOf(vtTapped.href) === to ? vtTapped : null;
    var tile = link && (q(".pst", link) || (link.closest(".film") && q(".pst", link.closest(".film"))));
    if (tile) vtName(tile, "poster");             /* a text link: the page slides, nothing morphs */
  });
  /* back from the film page into a page kept in memory: no stale names */
  window.addEventListener("pageshow", function (e) { if (e.persisted) { vtClear(); vtTapped = null; } });
});
