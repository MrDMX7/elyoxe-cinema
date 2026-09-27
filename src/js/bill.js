/* the home billboard (UI redesign Task 3): the city's most-shown film tonight, then four more of its top films
   (those with a trailer frame first), one at a time. The server wrote the first for Dubai and a JSON island
   (#bill-data) of every city's five:
   {f: {fid: {t, e?, h, v, w, s?, x: [facts], tr?, b?: [640, 1280] | p?: [342, 684], c}}, c: {city|"*": [[fid, price inputs]]}}.
   The slide follows the city (pickCity), turns every 6 s — never under reduced motion, and not while a pointer
   is over it, focus is in it, the tab is hidden or the visitor pressed pause — and its indicators are buttons.
   The CTA's «من X» is a price cell like any other: renderPrices() and renderHome() give it the visitor's card
   and city; until the city's shows are in, it says «…» (never the previous city's price). */
var BILL = null, billI = 0, billT = null, billHold = { hover: false, focus: false, hidden: false, user: false };
var BILL_BD = "(min-width:1024px) 100vw, 320px";   /* as Kit's BILL_BD_SIZES: a phone takes the 640w frame */
function billList() {
  var c = BILL && (BILL.c[city] && BILL.c[city].length ? BILL.c[city] : BILL.c["*"]);
  return c || [];
}
function billFrame(o) {
  var pc = ' style="--pc:' + esc(o.c) + '" aria-hidden="true"';
  if (o.b) return '<div class="bd"' + pc + '><img src="' + esc(o.b[1]) + '" srcset="' + esc(o.b[0]) + " 640w, " + esc(o.b[1]) +
    ' 1280w" sizes="' + BILL_BD + '" alt="" decoding="async" class="fr"></div>';
  if (o.p) {
    /* no frame yet (Kit's bill_frame): the 342w poster blurred full-bleed, and on a desktop a sharp copy with the glow */
    return '<div class="bd pf"' + pc + '><img src="' + esc(o.p[0]) + '" class="pb" alt="" width="342" height="513" decoding="async">' +
      '<img src="' + esc(o.p[0]) + '" srcset="' + esc(o.p[0]) + " 342w, " + esc(o.p[1]) + ' 684w" sizes="(min-width:1024px) 300px, 1px" class="ps" alt="" width="342" height="513" decoding="async"></div>';
  }
  /* nothing to show: the film's typographic tile over the velvet glow, never a flat field */
  return '<div class="bd noimg"' + pc + '><span class="pst bd-t"><span class="pst-t"' + (o.e ? ' lang="en" dir="ltr"' : "") + ">" + esc(o.t) + "</span></span></div>";
}
/* the next slide's picture, fetched ahead — only once the page has loaded and gone idle (it must never compete
   with the first picture, the page's LCP) */
var billWarmOK = false;
function billWarm(o) {
  if (!billWarmOK || !o || !(o.b || o.p)) return;
  var im = new Image();
  if (o.b) { im.sizes = BILL_BD; im.srcset = o.b[0] + " 640w, " + o.b[1] + " 1280w"; im.src = o.b[1]; }
  else im.src = o.p[0];
}
function billNext() { var list = billList(), nx = list[(billI + 1) % list.length]; billWarm(nx && BILL.f[nx[0]]); }
/* the slide's price cell: priced from the city's own shows (renderFrom) once they are in, «…» until then */
function billPrice(p) {
  return esc(TX.from) + ' <span class="p" data-aed="' + esc(p[0]) + '" data-chain="' + esc(p[1]) + '" data-hall="' + esc(p[2]) + '" data-hk="' + esc(p[3]) + '" data-cin="' + esc(p[4]) + '"' +
    (p[5] ? ' data-asof="' + esc(p[5]) + '"' : "") + ' data-wait><span class="num">…</span></span>';
}
var PLAY = '<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
function billShow(i, go) {
  var box = q("[data-bill]"), list = billList();
  if (!box || !list.length) return;
  billI = (i + list.length) % list.length;
  var row = list[billI], fid = row[0], o = BILL.f[fid], p = row[1];
  if (!o) return;
  var slide = q("[data-bill-slide]", box), cn = C.cities[city] || city;
  /* said once, politely, only when the visitor picked it (set before the words change, never during rotation) */
  slide.setAttribute("aria-live", go ? "polite" : "off");
  /* the slide is written anew, into a box of a fixed height (cinema.css): new nodes and a box that keeps its
     size, so a turn never counts as a layout shift */
  var eye = BILL.c[city] && BILL.c[city].length ? sub(TX.top_in, { city: cn }) : TX.top, en = o.e ? ' lang="en" dir="ltr"' : "";
  slide.innerHTML = '<p class="eyebrow" data-bill-eye>' + esc(eye) + "</p>" +
    '<h2 class="bill-t"><a href="' + esc(o.h) + '" data-bill-a' + en + ">" + esc(o.t) + "</a></h2>" +
    '<p class="bill-v" data-bill-v><b class="v-' + esc(o.v) + '">' + esc(o.w) + (AR || o.s ? "." : "") + "</b>" + (o.s ? " " + o.s : "") + "</p>" +
    '<p class="bill-f" data-bill-f>' + o.x.map(function (x) { return "<span>" + x + "</span>"; }).join("") + "</p>" +
    '<p class="cta"><a class="btn main" href="' + esc(o.h) + '" data-bill-go>' + esc(TX.times) +
    '<span class="from" data-from="' + esc(fid) + '"' + (p ? ">" + billPrice(p) : " hidden>") + "</span></a>" +
    (o.tr ? '<a class="btn ghost" data-bill-tr href="https://www.youtube-nocookie.com/embed/' + encodeURIComponent(o.tr) + '" data-trailer="' + esc(o.tr) + '" rel="noopener" target="_blank">' + PLAY + esc(TX.bill_tr) + "</a>" : "") + "</p>";
  if (p && S && S.city === city) renderFrom(false);
  var bd = q("[data-bill-bd]", box);
  bd.insertAdjacentHTML("beforeend", billFrame(o));
  var nu = bd.lastElementChild, im = q("img", nu);
  /* the new picture fades in over the old once loaded (at once under reduced motion); then every older layer
     goes — however fast the indicators were pressed, one layer stays */
  nu.classList.add("in");
  var done = function () {
    nu.classList.remove("in");
    setTimeout(function () { [].slice.call(bd.children).forEach(function (c) { if (c !== nu && bd.lastElementChild === nu) c.remove(); }); }, RM ? 0 : 700);
  };
  if (!im || im.complete) requestAnimationFrame(done); else { im.addEventListener("load", done); im.addEventListener("error", done); }
  qa("img", nu).forEach(function (x) { x.addEventListener("error", function () { x.remove(); }); });
  qa("[data-bill-dots] button", box).forEach(function (b, k) { b.setAttribute("aria-pressed", k === billI ? "true" : "false"); });
  billNext();
}
function billDots() {
  var d = q("[data-bill-dots]"), list = billList(), pp = q("[data-bill-pp]");
  if (!d) return;
  d.innerHTML = list.length > 1 ? list.map(function (r, k) {
    var o = BILL.f[r[0]] || {};
    return '<button type="button" aria-label="' + esc(o.t) + '" aria-pressed="' + (k === billI ? "true" : "false") + '"><i></i></button>';
  }).join("") : "";
  if (pp) pp.hidden = RM || list.length < 2;
}
/* the city changed: its own five, from the first */
function billCity() {
  if (!BILL) return;
  billDots(); billShow(0, false);
}
function billPaused() { return RM || billHold.user || billHold.hover || billHold.focus || billHold.hidden || billList().length < 2; }
function billTick() { if (!billPaused()) billShow(billI + 1, false); }
function bindBill() {
  var box = q("[data-bill]"), j = q("#bill-data");
  if (!box || !j) return;
  try { BILL = JSON.parse(j.textContent); } catch (e) { return; }
  /* the server drew Dubai's first film; a visitor whose city is another gets theirs before anything else moves */
  if (city !== "dubai") billCity(); else billDots();
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
  /* pause / play: the rotation stops for as long as the visitor wants (WCAG 2.2.2), a touch screen included */
  var pp = q("[data-bill-pp]", box);
  if (pp) pp.addEventListener("click", function () { billHold.user = !billHold.user; pp.setAttribute("aria-pressed", billHold.user ? "true" : "false"); });
  var idle = function () { billWarmOK = true; billNext(); };
  var afterLoad = function () { if (window.requestIdleCallback) requestIdleCallback(idle, { timeout: 3000 }); else setTimeout(idle, 1500); };
  if (document.readyState === "complete") afterLoad(); else window.addEventListener("load", afterLoad);
  if (!RM) billT = setInterval(billTick, 6000);
}
