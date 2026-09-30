/* the film page (UI redesign Task 4): its schedule laid out as the mock draws it, the dock, the ticket's empty
   state, the collapsed cinemas and cities, «يبدأ بعد N د», the verdict's «المزيد».
   The server writes each cinema's times hall by hall (with no script that is what a visitor reads: each hall's
   name and «من» price, then its times per day). fsFlat() makes each cinema one row of buttons per day in time
   order, every button carrying its hall (data-hall/data-hk, so ticket.js and seatmap.js read it off the button
   itself) and its own price cell (the cheapest seat of that show, or of its hall that day when the page was
   compact), which prices.js reprices after the card like any other. */
var FS = { btn: null, x: null, auto: false, ready: false, open: {} };
function fsCell(aed, chain, hall, hk, cin, asof) {
  return '<span class="p" data-aed="' + fmt(aed) + '" data-chain="' + esc(chain) + '" data-hall="' + esc(hall) + '" data-hk="' + esc(hk) +
    '" data-cin="' + esc(cin) + '"' + (asof ? ' data-asof="' + esc(asof) + '"' : "") + "></span>";
}
function fsAttrs(el, skip) {
  var o = "";
  for (var i = 0; i < el.attributes.length; i++) { var x = el.attributes[i]; if (!skip[x.name]) o += " " + x.name + '="' + esc(x.value) + '"'; }
  return o;
}
/* one string per cinema, one parse (a page of 500 times was ~350 ms of main thread done button by button); and only
   the cinemas on screen: at start-up the visitor's city's first three, the rest when they are shown («N سينمات ثانية»,
   a sort by distance) or their city is opened (fsHydrate) — a folded cinema is never seen before that (fix round 1,
   M2). Returns the cinemas it laid out. */
function fsFlat(sec) {
  var done = [];
  if (!sec) return done;
  qa(":scope > .cg:not(.more-h):not([data-flat])", sec).forEach(function (cg) {
    cg.setAttribute("data-flat", ""); done.push(cg);
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
          /* data-occ left out: seatmap.js's «باقي N مقعد» is drawn again on the new button */
          byD[d].push([t, "<" + tag + ' class="' + esc(el.className) + '"' + fsAttrs(el, { "class": 1, "data-hall": 1, "data-hk": 1, "data-occ": 1 }) + hall + ">" +
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
  return done;
}
/* a time's price with a note (a table price's date, «للشخص — بشرط تذكرتين», an excluded hall) gets a gold * (fix round
   1, M10); the note itself is read out with the price */
function fsNotes(r) { qa(".tx .tm .p[data-aed]", r).forEach(function (p) { p.classList.toggle("nb", !!q("small", p)); }); }
/* a city laid out after start-up: its day shown, its times struck or not, its prices after the card, the filters,
   the prayer marks, «يبدأ بعد» — what start-up did for the first */
function fsHydrate(sec) {
  var cgs = fsFlat(sec);
  if (!cgs.length || !FS.ready) return;
  var on = q('[data-day][aria-pressed="true"]'), d = on && on.getAttribute("data-day");
  cgs.forEach(function (cg) {
    if (d) qa(".times[data-d]", cg).forEach(function (t) { t.hidden = t.getAttribute("data-d") !== d; });
    qa(".p[data-aed]", cg).forEach(function (el) { el.innerHTML = priceHTML(el, false); });
    fsNotes(cg);
  });
  marks();
  if (ST.prayer) applyPrayer(); else applyFilters();
  fsSoon();
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
  if (!here && secs[0]) fsHydrate(secs[0]);
}
function fsMore() {
  qa(".cg.more-h").forEach(function (c) { c.classList.remove("more-h"); });
  qa("[data-more-c]").forEach(function (b) { b.parentNode.removeChild(b); });
  var sec = q(".fcity.here");
  if (!sec) return;
  qa(".fcity[data-city]").forEach(function (s) { s.setAttribute("data-more", ""); });   /* the classes below rule now, not the first paint's CSS */
  if (FS.open[city]) { fsHydrate(sec); return; }   /* opened once: it stays open (a day switch, a sort) */
  var cs = qa(":scope > .cg", sec).filter(function (c) { return !c.classList.contains("x"); });
  if (cs.length <= 4) { fsHydrate(sec); return; }
  var rest = cs.slice(3);
  rest.forEach(function (c) { c.classList.add("more-h"); });
  var b = document.createElement("button");
  b.type = "button"; b.className = "lnk more-c"; b.setAttribute("data-more-c", "");
  var cn = C.cities[city] || city, k = rest.length;
  b.textContent = AR && k === 2 ? "سينمتين ثانيتين في " + cn :
    sub(TX.more_cin, { n: AR ? arCount(k, ["سينما وحدة", "سينمتين", "سينمات", "سينما"]) : k + " more cinemas", city: cn });
  rest[rest.length - 1].parentNode.insertBefore(b, rest[rest.length - 1].nextSibling);
  fsHydrate(sec);   /* the three on screen */
  b.addEventListener("click", function () {
    FS.open[city] = true;
    rest.forEach(function (c) { c.classList.remove("more-h"); });
    fsHydrate(sec);
    b.parentNode.removeChild(b);
    var a = q(".cg-h a", rest[0]); if (a) a.focus();
  });
}
/* a show link (#s-…, ticket.js showFromHash) names a time in a cinema that may not be laid out yet: its city opened,
   the cinema shown (a city's «N سينمات ثانية» opened with it) and laid out, before its new button is looked up */
function fsReveal(cg) {
  var sec = cg && cg.closest(".fcity[data-city]");
  if (!sec) return;
  if (!sec.open) sec.open = true;
  if (cg.classList.contains("more-h")) {
    FS.open[sec.getAttribute("data-city")] = true;
    qa(".cg.more-h", sec).forEach(function (c) { c.classList.remove("more-h"); });
    qa("[data-more-c]", sec).forEach(function (b) { b.parentNode.removeChild(b); });
  }
  fsHydrate(sec);
}
/* the next time at each cinema, when it starts within the hour: «يبدأ بعد 40 د» in live green. Of the times already
   started, the last two stay (faded); the earlier ones leave the row, which would otherwise open on a wall of
   morning shows nobody can book any more */
function fsSoon() {
  qa(".tm .sn").forEach(function (e) { e.parentNode.removeChild(e); });
  qa(".cgs .tx").forEach(function (box) {
    var past = qa(".tm.past", box);
    past.forEach(function (a, i) { a.classList.toggle("old", i < past.length - 2 && !a.classList.contains("on")); });
  });
  var n = NOW.getTime();
  qa(".cgs .tx:not([hidden])").forEach(function (box) {
    var d = box.getAttribute("data-d");
    var b = qa(".tm[data-start]", box).filter(function (a) { return !a.classList.contains("past") && !a.classList.contains("x"); })[0];
    if (!b) return;
    var m = Math.round((uae(d + "T" + b.getAttribute("data-start")).getTime() - n) / 60000);
    if (m < 0 || m > 60) return;
    var tt = q(".tt", b) || b;
    tt.insertAdjacentHTML("afterend", '<small class="sn">' + esc(m <= 0 ? TX.soon0 : sub(TX.soon, { n: m })) + "</small>");
  });
}

/* a time picked (ticket.js has filled the ticket): desktop shows it in the side column; a phone shows the dock.
   x.quiet: the page chose it (the desktop's next show), not the visitor — no dock, nothing said */
function fsPicked(btn, x) {
  FS.btn = btn; FS.x = x; FS.auto = !!x.quiet;
  var em = q("[data-tk-empty]"); if (em) em.hidden = true;
  if (desk()) { tk.hidden = false; return; }
  if (!x.quiet) fsDock(true);
}
/* d/m from an ISO date, for the stamp («رايح 30/9»): the stub's own dating, never the full ticket's day words */
function dkDMY(iso) { var p = String(iso || "").split("-"); return p.length === 3 ? +p[2] + "/" + +p[1] : iso; }
function fsDock(say) {
  var dk = q("[data-dock]"), x = FS.x;
  if (!dk || !x || FS.auto) return;
  var low = (x.p || []).reduce(function (m, p) { return m == null || p[1] < m ? p[1] : m; }, null);
  var known = x.hall != null && x.hk != null, r = card && D && known && low != null ? after(low, x.chain, x.hall, card, x.hk, x.cin) : { a: null, st: null, r: null };
  /* a card with no confirmed rule at this chain at all («card door»): the existing honest state words, never a
     made-up line; excluded (a rule that does not cover this hall) reads the same way as the price grid does */
  var note = low != null && card && r.st && r.st !== "ok" && C[r.st] ? C[r.st] : "";
  q("[data-dk-p]", dk).innerHTML = low == null ? '<span class="na">' + esc(C.box) + "</span>"
    : note ? '<span class="num">' + fmt(low) + "</span> " + esc(C.aed) + '<small class="per">' + esc(note) + "</small>"
    : '<span class="num">' + fmt(r.a != null ? r.a : low) + "</span> " + esc(C.aed) +
      (r.a != null ? '<small class="per">' + esc(sub(TX.after_c, { card: C.cards[card] })) + "</small>" + ppNote(r.r) : "");
  q("[data-dk-time]", dk).textContent = x.t;
  var bits = [x.cname];
  if (x.hk && x.hn) bits.push(x.hn);
  q("[data-dk-s]", dk).textContent = dayName(x.d) + TX.sep + bits.join(TX.sep);
  var box = !!(r.r && r.r.box_office_only && r.a != null), bk = q("[data-dk-book]", dk);
  if (bk) {
    bk.classList.toggle("box", box);
    if (box) {
      bk.textContent = TK.box; bk.href = mapsTo(x.cin);
      if (!G) geo().then(function () { if (FS.x === x && bk.classList.contains("box")) bk.href = mapsTo(x.cin); });
    } else {
      /* the show's own booking link, else the chain's site (book_url never leaves this at "#": kit/sched.py) */
      bk.textContent = sub(C.book_at, { chain: chainName(x.chain) }); bk.href = x.book || "";
    }
  }
  dk.hidden = false; dk.removeAttribute("data-stamped"); body.classList.add("docked");
  emit("stub", "open");
  /* said once the dock is on screen (a live region filled in the task that shows it can go unsaid, fix round 1 M5);
     the region itself sits outside the dock, always rendered */
  var live = q("[data-dk-live]");
  if (say && live) {
    live.textContent = "";
    requestAnimationFrame(function () { live.textContent = sub(TX.ticket, { film: x.film, cin: x.cname, t: x.t }); });
  }
}
/* «احجز» tapped: the chain opens in a new tab (the anchor's own href/target do that — nothing to prevent here) and
   the stub stamps «رايح» with the date on the perforation, aria-hidden, never touching the price or any text; it
   emits 'plan' for the memory layer (chrome.js's haptic already listens for it) */
function fsStamp(x) {
  var dk = q("[data-dock]"); if (!dk) return;
  dk.setAttribute("data-stamped", "");
  var s = q("[data-dk-stamp]", dk); if (s) s.textContent = (AR ? "رايح " : "Going ") + dkDMY(x && x.d);
  emit("plan", x);
}
/* nothing chosen (or the chosen time went out of sight: another day, another city, filtered, folded): a phone drops
   the dock; the desktop column says «اختر وقت» until fsAuto finds the next show */
function fsClear() {
  qa(".tm.on").forEach(function (o) { o.classList.remove("on"); o.removeAttribute("aria-current"); });
  FS.btn = null; FS.x = null; FS.auto = false;
  var dk = q("[data-dock]"); if (dk) { dk.hidden = true; dk.removeAttribute("data-stamped"); }
  body.classList.remove("docked");
  emit("stub", "close");
  if (tk && tk.classList.contains("open")) closeTicket();
  if (tk) tk.hidden = true;
  var em = q("[data-tk-empty]"); if (em) em.hidden = false;
}
/* in sight: a show that has started stays chosen (the ticket says the film itself begins ~15 minutes later, and the
   chains sell during the ads); only a day, a city, a filter or a fold takes it away (fix round 1, I2) */
function fsSeen(b) {
  return !!b && b.isConnected && !b.classList.contains("x") && !b.closest("[hidden], .x, .more-h, details:not([open])");
}
/* the desktop column is never empty while the visitor's city has a show to come on the chosen day: the next one
   there, among the cinemas on screen (fix round 1, I5) */
function fsNext() {
  var best = null;
  qa(".fcity.here > .cg:not(.more-h):not(.x) .tx:not([hidden]) .tm[data-start]:not(.past):not(.x)").forEach(function (b) {
    if (!best || b.getAttribute("data-start") < best.getAttribute("data-start")) best = b;
  });
  return best;
}
function fsAuto() {
  if (!FS.ready || !tk || !desk() || (FS.btn && fsSeen(FS.btn))) return;
  var n = fsNext();
  if (n) openTicket(n, true); else fsClear();
}
/* after a day, city, filter or fold change */
function fsCheck() {
  if (!FS.ready) return;
  if (FS.btn && !fsSeen(FS.btn)) fsClear();
  fsAuto();
}
/* the minute clock: a show the visitor chose stays chosen when it starts (struck, its ticket open); the page's own
   pick moves on to the next show */
function fsTick() {
  if (!FS.ready) return;
  if (FS.btn && FS.auto && FS.btn.classList.contains("past")) { FS.btn.classList.remove("on"); FS.btn.removeAttribute("aria-current"); FS.btn = null; }
  fsAuto();
}
/* start-up, once the visitor's city and day are known (main.js init) */
function fsStart() {
  FS.ready = true;
  fsSoon();
  fsAuto();
}

function bindFilm() {
  if (page !== "film" || !q(".cgs")) { bindVerdict(); return; }
  bindVerdict();
  /* the server's pick (the next show in Dubai when the page was built) is let go: renderFilm lays out the visitor's
     city, and on a desktop fsAuto chooses its next show; a phone starts with nothing chosen (no dock until a tap) */
  qa(".cgs .tm.on").forEach(function (o) { o.classList.remove("on"); o.removeAttribute("aria-current"); });
  /* a folded city is laid out the first time it opens */
  qa(".fcity[data-city]").forEach(function (sec) {
    sec.addEventListener("toggle", function () { if (sec.open) fsHydrate(sec); fsCheck(); });
  });
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-dk-open]");
    if (b && tk) tkOpen(b);
    /* «احجز» on the stub itself (the tap-count win, §2.3): the anchor's own href/target open the chain, nothing
       to prevent; a box-office-only card link goes to directions instead and is never stamped */
    var bk = e.target.closest && e.target.closest("[data-dk-book]");
    if (bk && !bk.classList.contains("box") && bk.getAttribute("href")) fsStamp(FS.x);
    /* the visitor's city is the schedule, not a fold: its heading does not close it */
    if (e.target.closest && e.target.closest(".fcity.here > summary")) e.preventDefault();
  });
  renderFilm();   /* the visitor's city first and laid out, before the day is chosen and the prices drawn */
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
