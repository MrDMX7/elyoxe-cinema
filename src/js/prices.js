/* prices: every .p cell on the page is rewritten to the price after the visitor's card (the server wrote
   the price before any card). `go` = the visitor just changed the card: changed digits flip. What you pay comes
   first and the struck list price after it, with a space between (never «33.6042»: MASTER-PLAN §5.2 W1-P2). */
function rule(chain, c) { return discRule(D && D.rules, chain, c); }
function state(r) { return discState(r, TODAY); }
function after(aed, chain, hall, c, hk, cin) { return discAfter(D && D.rules, TODAY, aed, chain, hall, hk, cin, c); }
function ppNote(r) { var n = discPayNote(r, C); return n ? '<small class="per">' + esc(n) + "</small>" : ""; }
/* a price from the fallback table (prices.yaml) carries the date it was seen, never the live «updated X ago» */
function asofNote(d) { return d ? '<small class="asof">' + sub(esc(C.asof), { date: '<bdi class="num">' + esc(d) + "</bdi>" }) + "</small>" : ""; }
/* HTML: the percentage sits in its own isolated span, or an Arabic run prints «خصم %20» */
function offer(r) {
  if (r.type === "bogo") return esc(AR ? "تذكرتين بسعر وحدة" : "Buy one, get one");
  if (r.type === "fixed") { var f = '<span class="num" dir="ltr">' + esc(+r.value) + "</span>"; return AR ? "التذكرة بـ" + f + " درهم" : "Tickets at AED " + f; }
  var v = '<span class="num" dir="ltr">' + esc(+r.value) + "%</span>";
  return AR ? "خصم " + v : v + " off";
}
function weak(r) { return r && (r.confidence === "third-party" || r.confidence === "unconfirmed"); }
/* the offer's conditions, in one sentence, each said once: in Arabic the note is printed, so a flag it
   already states («من الشباك فقط، 4 تذاكر باليوم») is not said again (site_kit.rule_terms, the card pages);
   a note carrying the source check's raw error is dropped, as site_kit.note_ar(r, ok=True) does */
function terms(r) {
  var t = [], note = AR && r.note_ar && !/not found|\b404\b/i.test(r.note_ar) ? r.note_ar : "";
  if (r.box_office_only && note.indexOf("الشباك") < 0) t.push(AR ? "من الشباك فقط" : "box office only");
  if (r.max_tickets && !/تذاكر|تذكرة/.test(note)) t.push(esc(AR ? "لين " + r.max_tickets + " تذاكر" : "up to " + r.max_tickets + " tickets"));
  if (note) t.push(esc(note));
  if (weak(r)) t.push(esc(C.weak));
  return t.length ? TX.sep + t.join(TX.sep) : "";
}

function priceHTML(el, go) {
  var aed = +el.getAttribute("data-aed"), asof = asofNote(el.getAttribute("data-asof"));
  var x = card && D && !el.hasAttribute("data-nd") ? after(aed, el.getAttribute("data-chain"), el.getAttribute("data-hall"), card, el.getAttribute("data-hk"), el.getAttribute("data-cin")) : { a: null };
  var pay = fmt(x.a != null ? x.a : aed), was = el.getAttribute("data-shown");
  el.setAttribute("data-shown", pay);
  var d = flipDigits(pay, go && was != null && was !== pay);
  if (x.a != null) return "<b>" + d + '</b> <s class="num">' + fmt(aed) + "</s>" + ppNote(x.r) + asof;
  return '<span class="num">' + d + "</span>" + (x.st === "excluded" ? "<small>" + esc(C.excluded) + "</small>" : "") + asof;
}
function renderPrices(go) {
  qa(".p[data-aed]").forEach(function (el) { el.innerHTML = priceHTML(el, go); });
  if (page === "film") fsNotes();
  lows();
}
/* gold is yours (MASTER-PLAN §1.5): with no card, the one cheapest price of each row ([data-lo]) or price table is lit
   (.lo, the first on a tie, as kit/tile.py lights it for the first paint); with a card the prices after it are gold
   (the stylesheet's .p:has(s) b) and no list price is */
function lows() {
  qa("[data-lo], table.prices").forEach(function (g) {
    var lo = null, v;
    qa(".p", g).forEach(function (el) {
      el.classList.remove("lo");
      v = parseFloat(el.getAttribute("data-shown") || el.getAttribute("data-aed"));
      if (!card && v > 0 && !el.closest(".off") && (!lo || v < lo.v)) lo = { el: el, v: v };
    });
    if (lo) lo.el.classList.add("lo");
  });
}

/* the cheapest ticket for this visitor among shows [{c, h, k, p: [[seat, aed]…]}] */
function best(shows) {
  var b = null;
  shows.forEach(function (s) {
    (s.p || []).forEach(function (p) {
      var x = card ? after(p[1], S.cinemas[s.c].chain, s.h, card, s.k, s.c) : { a: null };
      var pay = x.a != null ? x.a : p[1];
      if (!b || pay < b.pay) b = { pay: pay, aed: p[1], off: x.a != null, r: x.a != null ? x.r : null, s: s };
    });
  });
  return b;
}
/* a price the page did not write (the best for this visitor); `was` = what the cell showed before */
function payHTML(b, go, was) { var pay = fmt(b.pay); return flipDigits(pay, go && was != null && was !== pay); }
/* that price as a cell's inside: what you pay, then (after a space) the list price struck, then its note */
function payCell(b, go, was) { return "<b>" + payHTML(b, go, was) + "</b>" + (b.off ? ' <s class="num">' + fmt(b.aed) + "</s>" : "") + ppNote(b.r); }
