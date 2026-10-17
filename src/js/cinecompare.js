/* «وين أرخص؟» (R4 §299): on a film page, the same film across this city's other cinemas — cinema, hall, the
   cheapest price after the visitor's card, and the soonest upcoming show at that price, for the day already
   chosen (the day bar's pressed day). Everything it needs is already in the schedule the film page rendered
   (server markup, or film.js's own hydration of it), so this reads that DOM instead of shipping the data a
   second time. Sorted by price, capped at 8 rows with «الكل» to open the rest. A row is a plain #s-<key> link:
   ticket.js's own hashchange listener (always in the core bundle) opens that show's ticket, folding its cinema
   open first when it was behind «N سينمات ثانية» (film.js's fsReveal). A lazy chunk (pages/cheapest.py): K is
   window.CINEMA, so no discAfter() of its own — K.after() is the core's real one. */
var W = K.AR ? { h: "وين أرخص؟", cin: "السينما", price: "السعر", time: "الوقت", all: "الكل", alt: "نفس الفيلم أرخص بـ{d} درهم", at: "{t} في {c}", std: "قاعة عادية" }
  : { h: "Where’s it cheaper?", cin: "Cinema", price: "Price", time: "Time", all: "All", alt: "Same film, {d} AED less", at: "{t} at {c}", std: "standard hall" };
var ALT_MIN = 5;   // a saving under 5 AED is not worth a line on the ticket
var MAX = 8;

function hallLabel(b, hl) {
  var el = K.q(".hn", b) || (hl && K.q(":scope > .hl-n .hn", hl));
  return el ? el.textContent : "";
}
/* the price behind a time: inside the button itself once film.js has hydrated it (fsCell), else the ancestor
   hall's own cell — that day's split price first, else the one price the hall carries for both days */
function priceEl(b, hl, day) {
  var inside = K.q(".p[data-aed]", b);
  if (inside) return inside;
  var dp = day && K.q(":scope > .pr .p[data-aed]", day);
  return dp || (hl && K.q(":scope > .hl-n .p[data-aed]", hl));
}
function rowsOf(sec) {
  var out = [];
  K.qa(".cg[data-cin]", sec).forEach(function (cg) {
    var cin = cg.getAttribute("data-cin"), best = null;
    K.qa(".tm[data-start]", cg).forEach(function (b) {
      if (b.classList.contains("past") || b.classList.contains("x")) return;
      var day = b.closest("[data-d]"); if (day && day.hidden) return;
      var hl = b.closest("[data-hall]"); var p = priceEl(b, hl, day);
      if (!p) return;
      var aed = +p.getAttribute("data-aed"); if (!aed) return;
      var chain = p.getAttribute("data-chain") || cg.getAttribute("data-chain") || "";
      var hall = p.getAttribute("data-hall") || b.getAttribute("data-hall") || "";
      var hk = p.getAttribute("data-hk") || b.getAttribute("data-hk") || "Standard";
      var x = K.after(aed, chain, hall, K.card(), hk, cin);
      var pay = x && x.a != null ? x.a : aed;
      var d = day ? day.getAttribute("data-d") : null, t = b.getAttribute("data-start");
      if (!d || !t) return;
      var start = K.uae(d + "T" + t).getTime();
      if (!best || pay < best.pay || (pay === best.pay && start < best.start)) {
        best = { pay: pay, start: start, t: t, hn: hallLabel(b, hl), key: K.showKey(cin, d, t, hk) };
      }
    });
    if (best) out.push({ name: (K.q(".cg-h h3", cg) || {}).textContent || cin, b: best });
  });
  out.sort(function (a, b) { return a.b.pay - b.b.pay || a.b.start - b.b.start; });
  return out;
}
function row(r) {
  return "<tr><td><a href=\"#s-" + r.b.key + "\">" + K.esc(r.name) + (r.b.hn ? "<small>" + K.esc(r.b.hn) + "</small>" : "") +
    "</a></td><td><b class=\"num\">" + K.fmt(r.b.pay) + "</b></td><td><bdi class=\"num\" dir=\"ltr\">" + K.esc(r.b.t) + "</bdi></td></tr>";
}
function render(box) {
  var sec = K.q(".fcity.here");
  var rows = sec ? rowsOf(sec) : [];
  if (rows.length < 2) { box.hidden = true; box.innerHTML = ""; return; }   // one cinema: the schedule already says it
  var open = box.getAttribute("data-open") === "1", shown = open ? rows : rows.slice(0, MAX);
  box.innerHTML = "<h2 class=\"tp-h\">" + K.esc(W.h) + "</h2><div class=\"xwrap\"><table class=\"matrix cheap-t\"><thead><tr><th>" +
    K.esc(W.cin) + "</th><th>" + K.esc(W.price) + "</th><th>" + K.esc(W.time) + "</th></tr></thead><tbody>" +
    shown.map(row).join("") + "</tbody></table></div>" +
    (rows.length > MAX && !open ? "<button type=\"button\" class=\"lnk\" data-cheap-all>" + K.esc(W.all) + "</button>" : "");
  box.hidden = false;
}
/* the ticket's «نفس الفيلم أرخص» line (MASTER-PLAN §2.3 item 4): the chosen show against the cheapest of the same
   film in its city that day, both after the visitor's card — said only when the saving is ALT_MIN or more, as a
   #s-<key> link the hashchange listener opens like any other show */
var LAST = null;
function alt(x) {
  if (x) LAST = x; x = LAST;
  var el = K.q("[data-tk-alt]"); if (!el || !x) return;
  el.hidden = true; el.innerHTML = "";
  var ps = (x.p || []).map(function (p) { return p[1]; }).filter(function (v) { return v > 0; });
  if (!ps.length || x.hall == null || x.hk == null) return;
  var low = Math.min.apply(null, ps), now = K.after(low, x.chain, x.hall, K.card(), x.hk, x.cin);
  var pay = now && now.a != null ? now.a : low;
  var sec = K.q('.fcity[data-city="' + x.city + '"]') || K.q(".fcity.here"), r = sec ? rowsOf(sec)[0] : null;
  var mine = K.showKey(x.cin, x.d, x.t, x.hk || "Standard");
  if (!r || r.b.key === mine || pay - r.b.pay < ALT_MIN) return;
  /* the hall too: a VIP recliner against a regular seat is a different evening, said so plainly */
  var hall = r.b.hn || (x.hk && x.hk !== "Standard" ? W.std : "");
  el.innerHTML = '<a href="#s-' + r.b.key + '"><b>' + K.esc(K.sub(W.alt, { d: K.fmt(pay - r.b.pay) })) + "</b>: " +
    K.esc(K.sub(W.at, { t: r.b.t, c: r.name }) + (hall ? (K.AR ? "، " : ", ") + hall : "")) + "</a>";
  el.hidden = false;
}
function start() {
  K.on("ticket", alt); K.on("card", function () { alt(); }); K.on("rules", function () { alt(); });
  var box = K.q("[data-cheapest]"); if (!box) return;
  function redraw() { render(box); }
  box.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-cheap-all]")) { box.setAttribute("data-open", "1"); redraw(); }
  });
  redraw();
  K.on("card", redraw); K.on("rules", redraw); K.on("city", redraw); K.on("day", redraw);
  /* the schedule changes under this without any of those hooks too (film.js hydrating a folded city, a day's
     times paging in) — the same catch-all seatmap.js already uses for the same reason */
  if (window.MutationObserver) {
    var pend = 0;
    new MutationObserver(function () { if (!pend) pend = setTimeout(function () { pend = 0; redraw(); }, 200); })
      .observe(document.body, { childList: true, subtree: true });
  }
}
if (typeof document !== "undefined" && K.q) start();
