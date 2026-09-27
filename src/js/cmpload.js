/* cmpload (pages/insights.py): a compare box names its lazy chunk (data-cmp-src); load it only where one is,
   so film pages without a box (archived films) and every other page never fetch it. */
feature(function () {
  var box = q("[data-cmp-src]"), src = box && box.getAttribute("data-cmp-src");
  if (!src) return;
  function go() { var s = document.createElement("script"); s.src = src; s.async = true; document.head.appendChild(s); }
  /* on a film page the box is the «قارن» tab: fetched (and its film list built, ~150 ms on a slow phone) only once
     that tab comes near the screen — not at start-up (UI redesign Task 4 fix round 1) */
  var panel = box.closest("[role=tabpanel]");
  if (!panel || !("IntersectionObserver" in window)) { go(); return; }
  var io = new IntersectionObserver(function (es) {
    if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); go(); }
  }, { rootMargin: "300px" });
  io.observe(panel);
});
