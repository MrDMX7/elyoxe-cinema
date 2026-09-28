/* drag.js (W2-P5, MASTER-PLAN §2.0, §1.3): the sheets follow the thumb. A lazy chunk (pages/core.py LAZY_JS) that
   src/js/chrome.js fetches when a phone page is idle, or at the first sheet; it runs in its own scope with
   K = window.CINEMA (the hook bus: K.on / K.emit). Budget: 1.5 KB gz (tests/test_w2_p5.py).
   - A phone sheet (Kit.sheet's .sheet, or any panel marked data-drag) is dragged by its head (.sheet-t, or
     [data-drag-h]): it follows the finger 1:1, and the scrim fades with it below the sheet's lowest stop.
   - On release it closes past 30 % of its height below its lowest stop, or when flicked down faster than 0.5 px/ms
     from there; otherwise it settles in 220 ms (--ease-sheet) at the nearest stop, or at the next one a flick
     points to.
   - A sheet with data-detents="60 92" (the filter sheet) stops at 60 % and 92 % of the screen and opens at the lower.
     Resting on a stop, the sheet's end is padded by --dt (ui-sheet.css), so nothing is out of reach below the
     screen's edge. Reaching another stop says «detent» on the hook bus (a haptic tick, chrome.js).
   - Closing presses the sheet's own close button ([data-sheet-close] or [data-drag-close]), so focus, history and the
     inert page come back exactly as a tap on × brings them.
   - iPhone: a real toggle (button[role=switch]) becomes <input type=checkbox switch> where the browser has one (Safari),
     so iOS plays its own haptic; its checked state follows aria-checked, which the page's own script keeps.
   Under reduced motion nothing animates (ui-sheet.css): the sheet still follows the finger, and settles at once. */
if (K && window.PointerEvent) (function () {
  /* ms: the settle; under reduced motion ui-sheet.css turns every such transition off (the sheet lands at once) */
  var d = document, G = 0, used = [], ms = 220;
  function phone() { return innerWidth < 1024; }
  function scrim() { return d.querySelector("[data-sheet-scrim]"); }
  /* sh.S: where each stop puts the sheet (translateY, px), highest first; none = one stop at 0. sh.at: where it rests */
  function set(sh, y, t) {
    var s = scrim(), S = sh.S || [0], l = S[S.length - 1], h = sh.offsetHeight, tr = t ? t + "ms var(--ease-sheet)" : "";
    used.push(sh);
    sh.style.transition = tr && "transform " + tr;
    sh.style.transform = "translateY(" + y + "px)";
    if (s) { s.style.transition = tr && "opacity " + tr; s.style.opacity = y > l ? Math.max(0, (h - y) / (h - l)) : ""; }
  }
  /* at rest on a stop: --dt, how much of the sheet is below the screen, pads its end (ui-sheet.css), so the last row
     and the sticky foot (.go) sit at the screen's edge, not the sheet's (a layout at rest, never during a drag) */
  function rest(sh, y) { sh.at = y; sh.style.setProperty("--dt", y + "px"); set(sh, y, 0); }
  /* a sheet (and a data-drag panel) carries no inline style of its own: everything here goes when it closes */
  function clear(sh) {
    sh.removeAttribute("style"); sh.S = sh.at = 0;
    var s = scrim(); if (s) s.removeAttribute("style");
  }
  function onSheet(sh) {
    used.splice(0).forEach(clear);
    if (!sh) return;
    /* iPhone's switch: the same control, native; a click still reaches the page's own handler, which sets aria-checked */
    [].forEach.call("switch" in HTMLInputElement.prototype ? sh.querySelectorAll("button[role=switch]") : [], function (b) {
      var i = d.createElement("input"), a = b.attributes, n = a.length;
      while (n--) i.setAttribute(a[n].name, a[n].value);
      i.type = "checkbox"; i.className = "sw"; i.setAttribute("switch", "");
      function on() { i.checked = i.getAttribute("aria-checked") === "true"; }
      on(); new MutationObserver(on).observe(i, { attributes: true });
      b.replaceWith(i);
    });
    /* data-detents: the stops as percentages of the screen's height, lowest first; the sheet is as tall as the highest */
    var P = (sh.getAttribute("data-detents") || "").split(" "), top = P[P.length - 1] * innerHeight / 100;
    if (!top || !phone()) return;
    sh.style.blockSize = sh.style.maxBlockSize = top + "px";
    sh.S = P.map(function (p) { return Math.round(top - p * innerHeight / 100); }).reverse();
    rest(sh, sh.S[sh.S.length - 1]);
  }
  K.on("sheet", onSheet);
  d.addEventListener("pointerdown", function (e) {
    var h = e.target.closest(".sheet-t, [data-drag-h]"), sh = h && h.closest(".sheet, [data-drag]");
    if (!sh || sh.hidden || G || !phone() || e.button || e.target.closest("button, a")) return;
    G = { sh: sh, id: e.pointerId, y0: e.clientY, t0: sh.at || 0, p: [] };
    try { h.setPointerCapture(e.pointerId); } catch (x) {}
  });
  d.addEventListener("pointermove", function (e) {
    if (!G || e.pointerId !== G.id || (!G.p.length && Math.abs(e.clientY - G.y0) < 3)) return;
    G.p.push([e.timeStamp, e.clientY]);
    set(G.sh, Math.max(0, G.t0 + e.clientY - G.y0), 0);
  });
  /* the release is judged at the last move (a cancelled pointer too): where the sheet is, and how fast it went over
     the last 100 ms (px/ms, down is positive) */
  function up(e) {
    var g = G;
    if (!g || e.pointerId !== g.id) return;
    G = 0;
    if (!g.p.length) return;   /* a tap, not a drag */
    var sh = g.sh, L = g.p[g.p.length - 1], y = Math.max(0, g.t0 + L[1] - g.y0), S = sh.S || [0], l = S[S.length - 1], to,
      p = g.p.filter(function (q) { return L[0] - q[0] < 100; })[0], v = L[0] > p[0] ? (L[1] - p[1]) / (L[0] - p[0]) : 0;
    if (v > 0.5) to = S.filter(function (s) { return s > y + 1; })[0];                /* flicked down: the next stop, or away */
    else if (v < -0.5) to = S.filter(function (s) { return s < y - 1; }).pop() || 0;  /* flicked up: the next stop up */
    else if (y <= l + 0.3 * (sh.offsetHeight - l)) to = S.reduce(function (a, b) { return Math.abs(b - y) < Math.abs(a - y) ? b : a; });
    /* away: out of sight, then the sheet's own close button */
    set(sh, to == null ? sh.offsetHeight : to, ms);
    setTimeout(function () {
      if (to == null) { var x = sh.querySelector("[data-sheet-close], [data-drag-close]"); if (x) x.click(); clear(sh); }
      else if (!sh.hidden) { if (sh.S) rest(sh, to); if (to !== g.t0) K.emit("detent", to); }
    }, ms);
  }
  d.addEventListener("pointerup", up);
  d.addEventListener("pointercancel", up);
  /* a sheet opened before this chunk arrived */
  onSheet(d.querySelector(".sheet:not([hidden])"));
})();
