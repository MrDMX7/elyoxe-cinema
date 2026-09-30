/* «كم بتكلفني الطلعة؟» (R4 §298): the ticket's 1–8 ticket-count stepper, default from «مع منو» (family 4, else
   2 — K.who()), total after the visitor's card. Unit price: the ticket's own cheapest row (gold-is-yours, the
   rest of the site's own convention). A card's own max_tickets (discounts.yaml) caps how many of the N get the
   discount; the rest is said in one line, never averaged silently into the total — box_office_only and hall
   coverage need nothing extra here (K.after() already answers null for an excluded hall, and where you pay does
   not change how many tickets a card covers). A lazy chunk on every page kind that can hold a ticket
   (pages/tkqty.py), so the always-loaded bundle carries none of its weight; kit/ticket.py writes only the slot,
   <div data-tk-qty hidden>, and this fills it. K is window.CINEMA. */
var W = K.AR ? { h: "كم بتكلفني الطلعة؟", t: "الإجمالي", d: "أقل", i: "أكثر", part: "{card} يغطي {n} تذاكر، الباقي بالسعر العادي" }
  : { h: "How much for the outing?", t: "Total", d: "Fewer", i: "More", part: "{card} covers {n} tickets, the rest at the regular price" };
var n = null;
function base(tk) {
  var el = null;
  K.qa(".p[data-aed]", tk).forEach(function (p) { if (!p.hasAttribute("data-nd") && (!el || +p.getAttribute("data-aed") < +el.getAttribute("data-aed"))) el = p; });
  return el;
}
function total(tk, q) {
  var el = base(tk); if (!el) return null;
  var aed = +el.getAttribute("data-aed"), card = K.card();
  var x = card ? K.after(aed, el.getAttribute("data-chain"), el.getAttribute("data-hall"), card, el.getAttribute("data-hk"), el.getAttribute("data-cin")) : { a: null };
  if (x.a == null) return { v: aed * q };
  var max = x.r && x.r.max_tickets;
  if (max && q > max) return { v: max * x.a + (q - max) * aed, note: K.sub(W.part, { card: (K.C.cards || {})[card] || card, n: max }) };
  return { v: x.a * q };
}
function render() {
  var tk = K.q("[data-ticket]"), box = tk && K.q("[data-tk-qty]", tk); if (!box) return;
  if (!box.firstChild) box.innerHTML = '<span class="tk-q-l">' + K.esc(W.h) + '</span><div class="tk-q-c" role="group" aria-label="' + K.esc(W.h) +
    '"><button type="button" class="tk-q-b" data-tk-q="-1" aria-label="' + K.esc(W.d) + '">−</button><b class="tk-q-n num" data-tk-q-n aria-live="polite"></b>' +
    '<button type="button" class="tk-q-b" data-tk-q="1" aria-label="' + K.esc(W.i) + '">+</button></div><p class="tk-q-t" data-tk-q-t></p>';
  if (n == null) n = K.who() === "family" ? 4 : 2;
  var t = total(tk, n);
  box.hidden = !t;
  if (!t) return;
  K.q("[data-tk-q-n]", box).textContent = n;
  K.qa("[data-tk-q]", box).forEach(function (b) { var d = +b.getAttribute("data-tk-q"); b.disabled = d < 0 ? n <= 1 : n >= 8; });
  K.q("[data-tk-q-t]", box).innerHTML = K.esc(W.t) + ' <b class="num">' + K.fmt(t.v) + "</b> " + K.esc(K.C.aed) + (t.note ? "<small>" + K.esc(t.note) + "</small>" : "");
}
document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest("[data-tk-q]");
  if (!b || b.disabled) return;
  e.preventDefault();
  n = Math.max(1, Math.min(8, (n == null ? (K.who() === "family" ? 4 : 2) : n) + (+b.getAttribute("data-tk-q"))));
  render();
});
K.on("card", render);
K.on("rules", render);
K.on("ticket", function () { n = null; render(); });   /* a new show: the default follows «مع منو» again */
render();
