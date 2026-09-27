/* the home billboard (UI redesign Task 3): the city's five most-shown films tonight, one at a time, over a frame of
   each one's trailer. The server wrote the first for Dubai and a JSON island (#bill-data) of every city's five:
   {f: {fid: {t, e?, h, v, w, s?, x: [facts], tr?, b?: [640, 1280] | p?: poster, c}}, c: {city|"*": [[fid, price inputs]]}}.
   The slide follows the city (pickCity), turns every 6 s — never under reduced motion, and not while a pointer
   is over it, focus is in it or the tab is hidden — and its indicators are buttons. The CTA's «من X» is a price
   cell like any other: renderPrices() and renderHome() give it the visitor's card and city. */
var BILL = null, billI = 0, billT = null, billHold = { hover: false, focus: false, hidden: false };
function billList() {
  var c = BILL && (BILL.c[city] && BILL.c[city].length ? BILL.c[city] : BILL.c["*"]);
  return c || [];
}
function billFrame(o) {
  if (o.b) return '<div class="bd" style="--pc:' + esc(o.c) + '" aria-hidden="true"><img src="' + esc(o.b[1]) + '" srcset="' + esc(o.b[0]) + " 640w, " + esc(o.b[1]) +
    ' 1280w" sizes="100vw" alt="" decoding="async" class="fr"></div>';
  if (o.p) {
    /* no frame yet: the poster (Kit's bill_frame): full-bleed on a phone, a sharp copy over its blur on a desktop */
    var ss = 'src="' + esc(o.p[0]) + '" srcset="' + esc(o.p[0]) + " 342w, " + esc(o.p[1]) + ' 684w" sizes="(min-width:1024px) 300px, 100vw" alt="" width="342" height="513" decoding="async"';
    return '<div class="bd pf" style="--pc:' + esc(o.c) + '" aria-hidden="true"><img class="pb" ' + ss + '><img class="ps" ' + ss + "></div>";
  }
  return '<div class="bd noimg" style="--pc:' + esc(o.c) + '" aria-hidden="true"></div>';
}
/* a frame is fetched before its slide comes up, so the turn never shows a half-loaded picture */
function billWarm(o) {
  if (!o || !(o.b || o.p)) return;
  var im = new Image();
  if (o.b) { im.sizes = "100vw"; im.srcset = o.b[0] + " 640w, " + o.b[1] + " 1280w"; im.src = o.b[1]; }
  else { im.sizes = "(min-width:1024px) 300px, 100vw"; im.srcset = o.p[0] + " 342w, " + o.p[1] + " 684w"; im.src = o.p[0]; }
}
function billShow(i, go) {
  var box = q("[data-bill]"), list = billList();
  if (!box || !list.length) return;
  billI = (i + list.length) % list.length;
  var row = list[billI], fid = row[0], o = BILL.f[fid], p = row[1];
  if (!o) return;
  var cn = C.cities[city] || city;
  q("[data-bill-eye]", box).textContent = BILL.c[city] && BILL.c[city].length ? sub(TX.top_in, { city: cn }) : TX.top;
  var a = q("[data-bill-a]", box);
  a.textContent = o.t; a.href = o.h;
  if (o.e) { a.setAttribute("lang", "en"); a.setAttribute("dir", "ltr"); } else { a.removeAttribute("lang"); a.removeAttribute("dir"); }
  q("[data-bill-v]", box).innerHTML = '<b class="v-' + esc(o.v) + '">' + esc(o.w) + (AR || o.s ? "." : "") + "</b>" + (o.s ? " " + o.s : "");
  q("[data-bill-f]", box).innerHTML = o.x.map(function (x) { return "<span>" + x + "</span>"; }).join("");
  q("[data-bill-go]", box).href = o.h;
  var fr = q("[data-from]", box);
  fr.setAttribute("data-from", fid);
  fr.hidden = !p;
  if (p) {
    fr.innerHTML = esc(TX.from) + ' <span class="p" data-aed="' + esc(p[0]) + '" data-chain="' + esc(p[1]) + '" data-hall="' + esc(p[2]) + '" data-hk="' + esc(p[3]) + '" data-cin="' + esc(p[4]) + '"' +
      (p[5] ? ' data-asof="' + esc(p[5]) + '"' : "") + "></span>";
    var cell = q(".p", fr); cell.innerHTML = priceHTML(cell, false);
    if (S) renderFrom(false);
  }
  var tr = q("[data-bill-tr]", box);
  tr.hidden = !o.tr;
  if (o.tr) { tr.setAttribute("data-trailer", o.tr); tr.href = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(o.tr); } else tr.removeAttribute("data-trailer");
  var bd = q("[data-bill-bd]", box), old = bd.firstElementChild;
  bd.insertAdjacentHTML("beforeend", billFrame(o));
  var nu = bd.lastElementChild, im = q("img", nu);
  if (old && old !== nu) {
    /* the new frame fades in over the old one once it has loaded (at once under reduced motion) */
    nu.classList.add("in");
    var done = function () { nu.classList.remove("in"); setTimeout(function () { if (old.parentNode) old.remove(); }, RM ? 0 : 700); };
    if (!im || im.complete) requestAnimationFrame(done); else { im.addEventListener("load", done); im.addEventListener("error", done); }
  }
  if (im) im.addEventListener("error", function () { var p2 = im.parentNode; if (p2) p2.classList.add("noimg"); im.remove(); });
  qa("[data-bill-dots] button", box).forEach(function (b, k) { b.setAttribute("aria-pressed", k === billI ? "true" : "false"); });
  q("[data-bill-slide]", box).setAttribute("aria-live", go ? "polite" : "off");
  var nx = list[(billI + 1) % list.length]; billWarm(nx && BILL.f[nx[0]]);
}
function billDots() {
  var d = q("[data-bill-dots]"), list = billList();
  if (!d) return;
  d.innerHTML = list.length > 1 ? list.map(function (r, k) {
    var o = BILL.f[r[0]] || {};
    return '<button type="button" aria-label="' + esc(o.t) + '" aria-pressed="' + (k === billI ? "true" : "false") + '"><i></i></button>';
  }).join("") : "";
}
/* the city changed: its own five, from the first */
function billCity() {
  if (!BILL) return;
  billDots(); billShow(0, false);
}
function billPaused() { return RM || billHold.hover || billHold.focus || billHold.hidden || billList().length < 2; }
function billTick() { if (!billPaused()) billShow(billI + 1, false); }
function bindBill() {
  var box = q("[data-bill]"), j = q("#bill-data");
  if (!box || !j) return;
  try { BILL = JSON.parse(j.textContent); } catch (e) { return; }
  var list = billList();
  /* the server drew Dubai's first film; a visitor whose city is another gets theirs before anything else moves */
  if (city !== "dubai") billCity(); else { billDots(); var n = list[1]; billWarm(n && BILL.f[n[0]]); }
  box.addEventListener("mouseenter", function () { billHold.hover = true; });
  box.addEventListener("mouseleave", function () { billHold.hover = false; });
  box.addEventListener("focusin", function () { billHold.focus = true; });
  box.addEventListener("focusout", function (e) { if (!box.contains(e.relatedTarget)) billHold.focus = false; });
  document.addEventListener("visibilitychange", function () { billHold.hidden = document.hidden; });
  q("[data-bill-dots]", box).addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button");
    if (!b) return;
    billShow(qa("[data-bill-dots] button", box).indexOf(b), true);
  });
  if (!RM) billT = setInterval(billTick, 6000);
}
