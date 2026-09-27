/* the film page (UI redesign Task 4): its schedule laid out as the mock draws it, the dock, the ticket's empty
   state, the collapsed cinemas and cities, «يبدأ بعد N د», the verdict's «المزيد».
   The server writes each cinema's times hall by hall (with no script that is what a visitor reads: each hall's
   name and «من» price, then its times per day). fsFlat() makes each cinema one row of buttons per day in time
   order, every button carrying its hall (data-hall/data-hk, so ticket.js and seatmap.js read it off the button
   itself) and its own price cell (the cheapest seat of that show, or of its hall that day when the page was
   compact), which prices.js reprices after the card like any other. */
var FS = { btn: null, x: null, flat: false };
function fsCell(aed, chain, hall, hk, cin, asof) {
  return '<span class="p" data-aed="' + fmt(aed) + '" data-chain="' + esc(chain) + '" data-hall="' + esc(hall) + '" data-hk="' + esc(hk) +
    '" data-cin="' + esc(cin) + '"' + (asof ? ' data-asof="' + esc(asof) + '"' : "") + "></span>";
}
function fsAttrs(el, skip) {
  var o = "";
  for (var i = 0; i < el.attributes.length; i++) { var x = el.attributes[i]; if (!skip[x.name]) o += " " + x.name + '="' + esc(x.value) + '"'; }
  return o;
}
/* one string per cinema, one parse: a page of 500 times was ~350 ms of main thread done button by button */
function fsFlat() {
  if (FS.flat) return;
  FS.flat = true;
  var skip = { "class": 1 };
  qa(".cgs .cg").forEach(function (cg) {
    var cin = cg.getAttribute("data-cin"), chain = cg.getAttribute("data-chain"), byD = {}, ds = [];
    qa(":scope > .hl", cg).forEach(function (hl) {
      var code = hl.getAttribute("data-hall"), hk = hl.getAttribute("data-hk"), hn = q(".hn", hl), base = q(".hl-n .p[data-aed]", hl);
      var hnH = hn ? '<small class="hn">' + hn.innerHTML + "</small>" : "";
      qa(".times[data-d]", hl).forEach(function (box) {
        var d = box.getAttribute("data-d"), dayP = q(".pr .p[data-aed]", box) || base;
        if (!byD[d]) { byD[d] = []; ds.push(d); }
        var cell = function (pl, asof) {
          var aed = null;
          if (pl && pl.length) aed = Math.min.apply(null, pl.map(function (p) { return p[1]; }));
          else if (dayP) { aed = +dayP.getAttribute("data-aed"); asof = dayP.getAttribute("data-asof"); }
          return aed ? fsCell(aed, chain, code, hk, cin, asof) : "";
        };
        var inner = function (t, pl, asof) { return '<b class="tt">' + esc(t) + "</b>" + hnH + cell(pl, asof); };
        var hall = ' data-hall="' + esc(code) + '" data-hk="' + esc(hk) + '"';
        /* the server's buttons (every attribute kept: href, data-show, data-p …) and its started times */
        qa(".tm[data-start]", box).forEach(function (el) {
          var t = el.getAttribute("data-start"), tag = el.tagName.toLowerCase();
          byD[d].push([t, "<" + tag + ' class="' + esc(el.className) + '"' + fsAttrs(el, { "class": 1, "data-hall": 1, "data-hk": 1 }) + hall + ">" +
            inner(t, el.hasAttribute("data-p") ? PL[+el.getAttribute("data-p")] : null, el.getAttribute("data-asof")) + "</" + tag + ">"]);
        });
        /* a compact page's times as text: buttons whose ticket comes from the city's slice */
        qa(".tl", box).forEach(function (tl) {
          tl.textContent.trim().split(/\s+/).forEach(function (t) {
            if (!/^\d\d:\d\d$/.test(t)) return;
            byD[d].push([t, '<button type="button" class="tm" data-start="' + t + '"' + hall + ">" + inner(t, null, null) + "</button>"]);
          });
        });
      });
      hl.parentNode.removeChild(hl);
    });
    var html = ds.sort().map(function (d) {
      return '<div class="times tx" data-d="' + d + '">' + byD[d].sort(function (x, y) { return x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : 0; })
        .map(function (x) { return x[1]; }).join("") + "</div>";
    }).join("");
    cg.insertAdjacentHTML("beforeend", html);
    /* «الخريطة»: the cinema on Google Maps (no script: the cinema's own page has the directions) */
    var lat = cg.getAttribute("data-lat"), lng = cg.getAttribute("data-lng"), h = q(".cg-h", cg);
    if (lat && lng && h) h.insertAdjacentHTML("beforeend", '<a class="map" href="https://www.google.com/maps/dir/?api=1&destination=' + esc(lat + "," + lng) +
      '" rel="noopener" target="_blank">' + esc(TX.map) + "</a>");
  });
}
/* the visitor's city open and first (renderFilm moves it), the others folded; in it the three nearest cinemas
   (near.js sorts them once the visitor is located), the rest behind «N سينمات ثانية في <city>» */
function fsCities() {
  var secs = qa(".fcity[data-city]"), here = secs.filter(function (s) { return s.getAttribute("data-city") === city; })[0];
  secs.forEach(function (s) {
    var on = s === here || (!here && s === secs[0]);
    s.open = on; s.classList.toggle("here", s === here);
    var sm = q(":scope > summary", s); if (sm) { if (s === here) sm.setAttribute("tabindex", "-1"); else sm.removeAttribute("tabindex"); }
  });
  var nc = q("[data-nc]");
  if (nc) { nc.hidden = !!here || !secs.length; nc.textContent = here ? "" : sub(C.not_in_city, { city: C.cities[city] || city }); }
  fsMore();
}
function fsMore() {
  qa(".cg.more-h").forEach(function (c) { c.classList.remove("more-h"); });
  qa("[data-more-c]").forEach(function (b) { b.parentNode.removeChild(b); });
  var sec = q(".fcity.here"); if (!sec) return;
  var cs = qa(":scope > .cg", sec).filter(function (c) { return !c.classList.contains("x"); });
  if (cs.length <= 4) return;
  var rest = cs.slice(3);
  rest.forEach(function (c) { c.classList.add("more-h"); });
  var b = document.createElement("button");
  b.type = "button"; b.className = "lnk more-c"; b.setAttribute("data-more-c", "");
  var cn = C.cities[city] || city, k = rest.length;
  b.textContent = AR && k === 2 ? "سينمتين ثانيتين في " + cn :
    sub(TX.more_cin, { n: AR ? arCount(k, ["سينما وحدة", "سينمتين", "سينمات", "سينما"]) : k + " more cinemas", city: cn });
  rest[rest.length - 1].parentNode.insertBefore(b, rest[rest.length - 1].nextSibling);
  b.addEventListener("click", function () {
    rest.forEach(function (c) { c.classList.remove("more-h"); });
    b.parentNode.removeChild(b);
    var a = q(".cg-h a", rest[0]); if (a) a.focus();
  });
}
/* the next time at each cinema, when it starts within the hour: «يبدأ بعد 40 د» in live green. Of the times already
   started, the last two stay (faded); the earlier ones leave the row, which would otherwise open on a wall of
   morning shows nobody can book any more */
function fsSoon() {
  qa(".tm .sn").forEach(function (e) { e.parentNode.removeChild(e); });
  qa(".cgs .tx").forEach(function (box) {
    var past = qa(".tm.past", box);
    past.forEach(function (a, i) { a.classList.toggle("old", i < past.length - 2); });
  });
  var n = NOW.getTime();
  qa(".cgs .times[data-d]:not([hidden])").forEach(function (box) {
    var d = box.getAttribute("data-d");
    var b = qa(".tm[data-start]", box).filter(function (a) { return !a.classList.contains("past") && !a.classList.contains("x"); })[0];
    if (!b) return;
    var m = Math.round((uae(d + "T" + b.getAttribute("data-start")).getTime() - n) / 60000);
    if (m < 0 || m > 60) return;
    var tt = q(".tt", b) || b;
    tt.insertAdjacentHTML("afterend", '<small class="sn">' + esc(m <= 0 ? TX.soon0 : sub(TX.soon, { n: m })) + "</small>");
  });
}

/* a time picked (ticket.js has filled the ticket): desktop shows it in the side column; a phone shows the dock */
function fsPicked(btn, x) {
  FS.btn = btn; FS.x = x;
  var em = q("[data-tk-empty]"); if (em) em.hidden = true;
  if (desk()) { tk.hidden = false; return; }
  fsDock(true);
}
function fsDock(say) {
  var dk = q("[data-dock]"), x = FS.x;
  if (!dk || !x) return;
  var low = (x.p || []).reduce(function (m, p) { return m == null || p[1] < m ? p[1] : m; }, null);
  var known = x.hall != null && x.hk != null, r = card && D && known && low != null ? after(low, x.chain, x.hall, card, x.hk, x.cin) : { a: null };
  q("[data-dk-p]", dk).innerHTML = low != null ? '<span class="num">' + fmt(r.a != null ? r.a : low) + "</span> " + esc(C.aed) + (r.a != null && ppNote(r.r) ? " " + ppNote(r.r) : "")
    : '<span class="na">' + esc(C.box) + "</span>";
  var bits = [x.t + " " + x.cname];
  if (x.hk && x.hn) bits.push(x.hn);
  if (r.a != null) bits.push(sub(TX.after_c, { card: C.cards[card] }));
  q("[data-dk-s]", dk).textContent = dayName(x.d) + " " + bits.join(TX.sep);
  dk.hidden = false; body.classList.add("docked");
  if (say) q("[data-dk-live]", dk).textContent = sub(TX.ticket, { film: x.film, cin: x.cname, t: x.t });
}
/* nothing chosen (or the chosen time went out of sight: another day, another city, filtered, or started): the desktop
   column says «اختر وقت», a phone drops the dock */
function fsClear() {
  qa(".tm.on").forEach(function (o) { o.classList.remove("on"); o.removeAttribute("aria-current"); });
  FS.btn = null; FS.x = null;
  var dk = q("[data-dock]"); if (dk) dk.hidden = true;
  body.classList.remove("docked");
  if (tk && tk.classList.contains("open")) closeTicket();
  if (tk) tk.hidden = true;
  var em = q("[data-tk-empty]"); if (em) em.hidden = false;
}
function fsSeen(b) {
  return !!b && b.isConnected && !b.classList.contains("past") && !b.classList.contains("x") && !b.closest("[hidden], .x, .more-h, details:not([open])");
}
function fsCheck() { if (!fsSeen(FS.btn)) fsClear(); }

function bindFilm() {
  if (page !== "film" || !q(".cgs")) { bindVerdict(); return; }
  fsFlat(); bindVerdict();
  /* the server's pick (the next show in Dubai) stands on a desktop while it is in view; a phone starts with nothing
     chosen (no dock until a time is tapped), and a desktop with no pick to show says «اختر وقت» */
  var on = q(".cgs .tm.on");
  if (desk()) { if (on && tk) FS.btn = on; else fsClear(); }
  else if (on) { on.classList.remove("on"); on.removeAttribute("aria-current"); }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-dk-open]");
    if (b && tk) tkOpen(b);
    /* the visitor's city is the schedule, not a fold: its heading does not close it */
    if (e.target.closest && e.target.closest(".fcity.here > summary")) e.preventDefault();
  });
}
/* the verdict: three lines, «المزيد» opens the rest (only when there is more) */
function bindVerdict() {
  var v = q("[data-fv]"), b = q("[data-fv-more]");
  if (!v || !b) return;
  function fit() { if (!v.classList.contains("open")) b.hidden = v.scrollHeight <= v.clientHeight + 2; }
  /* measured after the first frame, not in start-up's task (a forced layout of the whole page there) */
  requestAnimationFrame(function () { setTimeout(fit, 0); });
  if (window.ResizeObserver) new ResizeObserver(function () { fit(); }).observe(v);
  b.addEventListener("click", function () {
    var open = v.classList.toggle("open");
    b.setAttribute("aria-expanded", open ? "true" : "false");
    b.textContent = open ? TX.less : TX.more;
  });
}
