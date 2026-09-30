/* chrome.js (W2-P5, MASTER-PLAN §2.0, §1.3): the chrome's behaviour, in the main bundle's one scope.
   - The phone's tab bar steps down out of the way after 12 px of scroll down and comes back after 12 px up (never
     while a sheet is open, never while the old dock sits on it), yields to the stub (on("stub"): W2-P3 emits "open" /
     "close"), and a tap on the tab of the page you are on scrolls that page back to its top.
   - --chrome-b on <html>: how much of the screen's foot the fixed chrome covers now (the tab bar, the dock, anything
     marked data-chrome-b), so the lines that float over it (the shared-link prompt, the install line) sit on top of it,
     never under it.
   - Haptics: navigator.vibrate(8) when a card is chosen, a time is chosen (the stub rises), the stamp («plan»), a save
     and a sheet reaching a detent, and only after the visitor's first tap (a trusted click: Chrome counts a touch scroll
     as a user activation too, so navigator.userActivation would let a scroll through): never on load or scroll. An
     iPhone plays its own on the switches drag.js makes native.
   - The «قائمتي» sheet (D2, until W3-P1's /me/): the card chosen, and «امسح بياناتي», which asks once more, then clears
     every «cinema.» key on this phone and loads the page again as a first visit.
   - drag.js (the sheets' drag, a lazy chunk): fetched when a phone page is idle, or at the first sheet.
   - The header over a screen (round r3, ui-chrome.css's data-hero rules): translucent at rest, solid the instant
     any of its own readable text would sit under it — never a scroll listener, two IntersectionObservers: one on
     a top-of-body sentinel (a real scroll), one on the film hero's own title with the header's height as its top
     margin (a coordinator-caught second case with NO scroll at all — the film hero's text block is anchored to
     its picture's BOTTOM, ui-fhero.css's justify-content:flex-end, so opening «ليش يستاهل؟» can grow it past the
     picture's own height and shove the title itself up to y=0; an observer keyed to scrollY alone never sees
     this, since scrollY never changes — but the title's own geometry does, and IntersectionObserver recomputes
     on that too). Both drive the same class through a shared flag object, so one can never clear what the other
     just set. */
var CH = { down: false, stub: false, y: 0, tap: false }, chRoot = document.documentElement;
function chAway() {
  var b = 0, away = CH.down || CH.stub, t = q(".tabs");
  chRoot.classList.toggle("tabs-away", away);
  if (t && !away) b = t.offsetHeight;
  qa("[data-dock],[data-chrome-b]").forEach(function (d) { if (d.offsetHeight) b = Math.max(b, parseFloat(getComputedStyle(d).bottom) + d.offsetHeight); });
  chRoot.style.setProperty("--chrome-b", b + "px");
}
function haptic() { if (CH.tap && navigator.vibrate) navigator.vibrate(8); }
function dragLoad() {
  var u = shScrim && shScrim.getAttribute("data-drag-js");
  if (u && !q('script[src="' + u + '"]')) { var s = document.createElement("script"); s.src = u; document.head.appendChild(s); }
}
feature(function () {
  /* the header-solid pair (module note above): harmless on a page with no data-hero — the class still gets set,
     nothing in the stylesheet reads it there. */
  var IO = window.IntersectionObserver, SOL = { a: false, b: false };
  function sol(k, v) { SOL[k] = v; body.classList.toggle("scrolled", SOL.a || SOL.b); }
  if (IO) {
    new IO(function (e) { sol("a", !e.pop().isIntersecting); }).observe(q("#scroll-mark"));
    var ft = q(".fhero h1.ft"), topEl = q(".top");
    if (ft && topEl) new IO(function (e) { sol("b", !e.pop().isIntersecting); },
      { rootMargin: "-" + topEl.offsetHeight + "px 0px 0px 0px" }).observe(ft);
  }
  document.addEventListener("click", function (e) { if (e.isTrusted) CH.tap = true; }, true);
  addEventListener("scroll", function () {
    var y = scrollY, dn = y > CH.y && y > 0;
    if (SH || body.classList.contains("docked")) CH.y = y;
    else if (Math.abs(y - CH.y) > 12 || y <= 0) { CH.y = y; if (CH.down !== dn) { CH.down = dn; chAway(); } }
  }, { passive: true });
  /* the old dock (above the tab bar) brings the bar back; any size change re-measures the foot */
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(function () { if (body.classList.contains("docked")) CH.down = false; chAway(); });
    qa(".tabs,[data-dock],[data-chrome-b]").forEach(function (e) { ro.observe(e); });
  }
  on("stub", function (x) { CH.stub = !!x && x !== "close"; chAway(); if (CH.stub) haptic(); });
  ["card", "plan", "save", "detent"].forEach(function (ev) { on(ev, haptic); });
  on("sheet", function (el) {
    if (!el || el.id !== "sheet-me") return;
    var c = q("[data-me-clear]", el);
    q("[data-me-card]", el).textContent = (card && C.cards && C.cards[card]) || C.nocard;
    c.sure = 0; c.textContent = c.getAttribute("data-t");
  });
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest(".tabs a[aria-current], [data-me-clear]");
    if (!a) return;
    if (!a.hasAttribute("data-me-clear")) {
      /* the tab you are on: back to the top of its page (the page itself, not a section: a city under «السينمات») */
      if (a.pathname === location.pathname) { e.preventDefault(); scrollTo({ top: 0, behavior: RM ? "auto" : "smooth" }); }
      return;
    }
    if (!a.sure) { a.sure = 1; a.textContent = a.getAttribute("data-sure"); return; }
    try { Object.keys(localStorage).forEach(function (k) { if (!k.indexOf("cinema.")) localStorage.removeItem(k); }); } catch (x) {}
    /* the sheet's own history entry is left first: Back then returns to where the visitor was, not to this page again */
    if (!shPushed) { location.reload(); return; }
    addEventListener("popstate", function () { location.reload(); }, { once: true });
    sheetClose();
  });
  chAway();
  if (!desk()) { if (window.requestIdleCallback) requestIdleCallback(dragLoad, { timeout: 4000 }); else setTimeout(dragLoad, 2000); }
});
