/* prices: every .p cell on the page is rewritten to the price after the visitor's card (the server wrote
   the price before any card). `go` = the visitor just changed the card: changed digits flip. */
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
/* the offer's conditions, in one sentence */
function terms(r) {
  var t = [];
  if (r.box_office_only) t.push(AR ? "من الشباك فقط" : "box office only");
  if (r.max_tickets) t.push(esc(AR ? "لين " + r.max_tickets + " تذاكر" : "up to " + r.max_tickets + " tickets"));
  if (AR && r.note_ar) t.push(esc(r.note_ar));
  if (weak(r)) t.push(esc(C.weak));
  return t.length ? TX.sep + t.join(TX.sep) : "";
}

function priceHTML(el, go) {
  var aed = +el.getAttribute("data-aed"), asof = asofNote(el.getAttribute("data-asof"));
  var x = card && D && !el.hasAttribute("data-nd") ? after(aed, el.getAttribute("data-chain"), el.getAttribute("data-hall"), card, el.getAttribute("data-hk"), el.getAttribute("data-cin")) : { a: null };
  var pay = fmt(x.a != null ? x.a : aed), was = el.getAttribute("data-shown");
  el.setAttribute("data-shown", pay);
  var d = flipDigits(pay, go && was != null && was !== pay);
  if (x.a != null) return '<s class="num">' + fmt(aed) + "</s><b>" + d + "</b>" + ppNote(x.r) + asof;
  return '<span class="num">' + d + "</span>" + (x.st === "excluded" ? "<small>" + esc(C.excluded) + "</small>" : "") + asof;
}
function renderPrices(go) {
  qa(".p[data-aed]").forEach(function (el) { el.innerHTML = priceHTML(el, go); });
  if (page === "film") fsNotes();
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
