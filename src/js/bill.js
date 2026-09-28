/* «الشاشة», home's billboard (W2-P1; MASTER-PLAN §2.1, §1.3, §1.6). The server wrote every slide (pages/_core/bill.py);
   slide 1, the UAE's most-shown film tonight, is the same for every visitor and nothing here swaps it after paint.
   - A phone swipes: the slides are a CSS scroll-snap strip that never turns by itself (owner decision D3; the flag
     BILL_PHONE_ROTATE brings back the approved 6 s turn, stopping for good at the first touch). The indicators follow
     the slide the strip snapped to: an IntersectionObserver on the strip, never scrollLeft maths (negative in RTL).
   - A desktop cross-fades every 6 s (the one grandfathered autonomous motion, §1.3): paused while the billboard is
     under half on screen, under the pointer, with focus inside, in a hidden tab, after the pause button, and always
     under reduced motion.
   - Pictures: slide 1's came with the page; slide 2's loads once the page has loaded and gone idle; the rest on the
     first swipe (or the desktop's turn). Under Save-Data nothing loads before a swipe.
   - The card door under the CTA is the screen's one door (§1.2 #10): it opens the card sheet and says whether the
     slide's price is after the visitor's card («السعر بعد خصم فزعة») or the card does nothing at that chain (§1.7).
   billInsert(slide), desktop only, puts a slide (an element or its HTML) right after the one showing; slide 1 is never
   replaced (W3-P1's «من قائمتك» slide). A phone answers false: there a saved film speaks in «قائمتي». */
var BILL = null, BILL_TURN = 6000, BILL_PHONE_ROTATE = false;
function billSlides() { return BILL ? qa(".slide", BILL.strip) : []; }
function billSave() { var c = navigator.connection; return !!(c && c.saveData); }
/* a slide's picture: its data-srcset / data-src become real (the <source> first, then the <img>) */
function billLoad(k) {
  var sl = billSlides()[k];
  if (!sl) return;
  qa("[data-srcset], [data-src]", sl).forEach(function (el) {
    if (el.hasAttribute("data-srcset")) { el.setAttribute("srcset", el.getAttribute("data-srcset")); el.removeAttribute("data-srcset"); }
    if (el.hasAttribute("data-src")) { el.setAttribute("src", el.getAttribute("data-src")); el.removeAttribute("data-src"); }
  });
}
/* the slide now showing: its indicator, the light its frame spills, the door's words */
function billSet(i) {
  var sl = billSlides();
  if (!sl[i]) return;
  BILL.i = i;
  sl.forEach(function (s, k) { s.classList.toggle("on", k === i); });
  qa("[data-bill-dots] button", BILL.box).forEach(function (b, k) { b.setAttribute("aria-pressed", k === i ? "true" : "false"); });
  var sp = sl[i].getAttribute("data-spill"), st = BILL.box.style;
  if (sp) { sp.split(";").forEach(function (c, k) { st.setProperty("--sp" + (k + 1), c); }); BILL.box.setAttribute("data-spill", ""); }
  else BILL.box.removeAttribute("data-spill");
  billDoor();
}
/* the visitor (a dot) or the desktop's clock asks for slide i */
function billGo(i, user) {
  var sl = billSlides(), n = sl.length;
  if (!n) return;
  i = (i + n) % n;
  billLoad(i);
  if (BILL.desk) { billSet(i); if (!billSave()) billLoad((i + 1) % n); return; }
  /* a phone: the strip scrolls to it and the observer marks it */
  sl[i].scrollIntoView({ block: "nearest", inline: "start", behavior: RM || !user ? "auto" : "smooth" });
}
/* «السعر بعد خصم فزعة ▾» when the slide's price is after the card; «ما في خصم فزعة في فوكس ▾» when the card does
   nothing at that price's chain (§1.7); «عندك بطاقة؟ شوف سعرك ▾» with no card. Read from the card's rules (prices.js
   after()), not from the repriced cell, so the order of the card's listeners never matters. */
function billDoor() {
  var d = BILL && q("[data-bill-door]", BILL.box), t = d && q("[data-door-t]", d);
  if (!t) return;
  var name = card && C.cards && C.cards[card], s = d.getAttribute("data-no");
  if (name) {
    var sl = billSlides()[BILL.i], c = sl && q(".bill-go .p[data-aed]", sl), x = null;
    if (c && !D) return;   /* the card's rules are not in yet: the door keeps its words until they are */
    if (c) x = after(+c.getAttribute("data-aed"), c.getAttribute("data-chain"), c.getAttribute("data-hall"), card, c.getAttribute("data-hk"), c.getAttribute("data-cin"));
    s = !x || x.a != null ? sub(d.getAttribute("data-yes"), { card: name })
      : sub(d.getAttribute("data-not"), { card: name, chain: chainName(c.getAttribute("data-chain")) });
  }
  if (t.textContent !== s) t.textContent = s;
}
function billPaused() {
  var h = BILL.hold;
  return RM || h.user || h.hover || h.focus || h.hidden || h.off || billSlides().length < 2 || (!BILL.desk && (!BILL_PHONE_ROTATE || BILL.touched));
}
function billTick() { if (!billPaused()) billGo(BILL.i + 1, false); }
/* the turn's clock exists only where a turn may happen (a desktop; a phone only with the flag, until a touch); each
   tick asks billPaused() first. A phone with the flag off never sets it */
function billClock() {
  if (BILL.t) { clearInterval(BILL.t); BILL.t = null; }
  if (!RM && billSlides().length > 1 && (BILL.desk || (BILL_PHONE_ROTATE && !BILL.touched))) BILL.t = setInterval(billTick, BILL_TURN);
}
/* the billboard is the country's (§2.1): a new city moves nothing on it (main.js pickCity still calls this) */
function billCity() {}
function billInsert(el) {
  if (!BILL || !BILL.desk) return false;
  if (typeof el === "string") { var w = document.createElement("div"); w.innerHTML = el; el = w.firstElementChild; }
  if (!el || !el.classList || !el.classList.contains("slide")) return false;
  el.classList.remove("on");
  var cur = billSlides()[BILL.i];
  cur.parentNode.insertBefore(el, cur.nextSibling);
  var dots = q("[data-bill-dots]", BILL.box);
  if (dots) {
    var b = document.createElement("button"), a = q(".bill-t a", el);
    b.type = "button"; b.setAttribute("aria-label", a ? a.textContent : ""); b.setAttribute("aria-pressed", "false"); b.innerHTML = "<i></i>";
    dots.insertBefore(b, dots.children[BILL.i + 1] || null);
  }
  billClock();
  return true;
}
function bindBill() {
  var box = q("[data-bill]"), strip = box && q("[data-bill-s]", box);
  if (!strip) return;
  var mq = window.matchMedia && window.matchMedia("(min-width: 1024px)");
  BILL = { box: box, strip: strip, i: 0, t: null, desk: !!(mq && mq.matches), swiped: false, touched: false,
    hold: { user: false, hover: false, focus: false, hidden: document.hidden, off: false } };
  var h = BILL.hold;
  if ("IntersectionObserver" in window) {
    /* a phone: the snapped slide is the one at least 60 % inside the strip */
    var snap = new IntersectionObserver(function (es) {
      if (BILL.desk) return;
      es.forEach(function (e) {
        if (e.isIntersecting && e.intersectionRatio >= 0.6) { var k = billSlides().indexOf(e.target); if (k >= 0 && k !== BILL.i) billSet(k); }
      });
    }, { root: strip, threshold: 0.6 });
    billSlides().forEach(function (s) { snap.observe(s); });
    /* the turn waits while the billboard is under half on screen */
    new IntersectionObserver(function (es) { h.off = es[es.length - 1].intersectionRatio < 0.5; }, { threshold: [0, 0.5, 1] }).observe(box);
  }
  /* the first swipe loads the other slides' pictures; a touch ends the phone's turn for good (when the flag is on) */
  strip.addEventListener("scroll", function () { if (!BILL.swiped && !BILL.desk) { BILL.swiped = true; billSlides().forEach(function (s, k) { billLoad(k); }); } }, { passive: true });
  strip.addEventListener("pointerdown", function () { if (!BILL.touched) { BILL.touched = true; billClock(); } }, { passive: true });
  box.addEventListener("mouseenter", function () { h.hover = true; });
  box.addEventListener("mouseleave", function () { h.hover = false; });
  box.addEventListener("focusin", function () { h.focus = true; });
  box.addEventListener("focusout", function (e) { if (!box.contains(e.relatedTarget)) h.focus = false; });
  document.addEventListener("visibilitychange", function () { h.hidden = document.hidden; });
  var dots = q("[data-bill-dots]", box);
  if (dots) dots.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button");
    if (b) billGo(qa("button", dots).indexOf(b), true);
  });
  /* pause / play (WCAG 2.2.2): the desktop's turn stops for as long as the visitor wants */
  var pp = q("[data-bill-pp]", box);
  if (pp) pp.addEventListener("click", function () { h.user = !h.user; pp.setAttribute("aria-pressed", h.user ? "true" : "false"); });
  /* the width crossed 1024 px: a phone's strip or a desktop's stack, and the clock follows */
  if (mq) {
    var flip = function () {
      BILL.desk = mq.matches;
      if (!BILL.desk) billSlides()[BILL.i].scrollIntoView({ block: "nearest", inline: "start" });
      billClock();
    };
    if (mq.addEventListener) mq.addEventListener("change", flip); else if (mq.addListener) mq.addListener(flip);
  }
  /* slide 2's picture once the page has loaded and gone idle (never beside slide 1's, the page's LCP) */
  var idle = function () { if (!billSave()) billLoad(1); };
  var afterLoad = function () { if (window.requestIdleCallback) requestIdleCallback(idle, { timeout: 3000 }); else setTimeout(idle, 1500); };
  if (document.readyState === "complete") afterLoad(); else window.addEventListener("load", afterLoad);
  on("ready", function () { billDoor(); getJSON("/data/discounts.json").then(billDoor); });
  on("card", billDoor);
  billClock();
}
