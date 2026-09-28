/* places-live: the city and cinema pages' behaviour (W2-P6, MASTER-PLAN §2.4, §2.5). A lazy chunk (pages/venue.py
   LAZY_JS, on those two page kinds only): K is window.CINEMA, and K.pl what src/js/places.js hands over from the bundle
   (the city's slice, the price after the card, the clock's names for days). It loads after start-up, so it first
   catches up with what already happened, then listens. Nothing here moves by itself: the city clock's digits turn over
   only when the UAE minute changes (the board's law), counts and the next start are text swaps, the hero's light is a
   colour, and a folded list opens only when tapped.

   City: the clock (72 px tiles), the pulse sentence, each cinema's «التالي 21:30، 18 عرض باقي», each film's next start
   and «من 42» after the card in «كل الأوقات», the hero's light by the hour (--lit), the first rows of posters and
   cinemas until «اعرض الكل». Cinema: the times already started fold under «+12 عرض فات», tomorrow's heading follows
   the clock and opens by itself once tomorrow is today. */

/* ---- the words, twins of pages/_core/places.py (tests/test_w2_p6.py runs these in node against the Python) */
var PL_LEFT = ["عرض واحد باقي", "عرضين باقيين", "عروض باقية", "عرض باقي"], PL_PAST = ["عرض واحد فات", "عرضين فاتوا", "عروض فاتت", "عرض فات"];
function plCount(n, f) { return n === 1 ? f[0] : n === 2 ? f[1] : n + " " + (n >= 3 && n <= 10 ? f[2] : f[3]); }
function plLeft(n, ar) { return ar ? plCount(n, PL_LEFT) : n + " left"; }
function plPast(n, ar) { return ar ? (n > 2 ? "+" : "") + plCount(n, PL_PAST) : "+" + n + " earlier"; }
function plWhen(h, ar) { return h >= 17 ? (ar ? "الليلة" : "tonight") : (ar ? "اليوم" : "today"); }
function plPulse(left, soon, when, ar) {
  if (!ar) return left + (left === 1 ? " show" : " shows") + " left " + when + (soon ? ", " + soon + (soon === 1 ? " starts" : " start") + " within the hour" : "");
  return plCount(left, PL_LEFT) + " " + when + (soon ? "، " + (soon === 1 ? "واحد منها يبدأ خلال ساعة" : soon + " تبدأ خلال ساعة") : "");
}
function plNext(t, n, ar) {
  if (!n) return ar ? "ما في عروض باقية اليوم" : "no shows left today";
  return ar ? "التالي " + t + "، " + plLeft(n, ar) : "next " + t + ", " + plLeft(n, ar);
}
/* velvet at full before 21:00, deeper toward night, deepest after midnight (places.py lit) */
function plLit(h) { return h >= 6 && h < 21 ? 1 : h === 21 ? 0.8 : h === 22 ? 0.7 : h === 23 ? 0.6 : 0.45; }
/* «HH:MM» of an instant, in UAE time */
function plHM(ms) { return new Date(ms + 4 * 3600e3).toISOString().slice(11, 16); }

/* ---- the page */
function plBoot() {
  var P = K.pl, AR = K.AR, q = K.q, qa = K.qa, page = K.page, body = document.body;
  var now = function () { return K.now().getTime(); }, today = function () { return P.today()[0]; };

  /* the city's clock on its tiles; `go`: a digit that changed turns over (never at start-up, never under reduced motion) */
  function clock(go) {
    var el = q("[data-cclock]");
    if (!el) return;
    var t = plHM(now()), old = el.getAttribute("data-t") || "";
    if (old === t) return;
    el.setAttribute("data-t", t);
    el.innerHTML = '<span class="vh">' + t + "</span>" + t.split("").map(function (ch, i) {
      return ch === ":" ? '<span class="c" aria-hidden="true">:</span>'
        : '<span class="d' + (go && !P.RM && old.charAt(i) !== ch ? " go" : "") + '" aria-hidden="true">' + ch + "</span>";
    }).join("");
  }
  function light() { body.style.setProperty("--lit", String(plLit(+plHM(now()).slice(0, 2)))); }
  /* the city's numbers from its slice: today's shows still to come (the minute counts, as the build's is_past does) */
  function city(go) {
    var S = P.S();
    if (!S || S.city !== K.city()) return;
    var hm = plHM(now()), later = plHM(now() + 36e5), d0 = today(), by = {}, byF = {};
    var up = S.shows.filter(function (s) { return s.d === d0 && s.t >= hm; }).sort(function (a, b) { return a.t < b.t ? -1 : a.t > b.t ? 1 : 0; });
    var soon = up.filter(function (s) { return later > hm ? s.t <= later : true; }).length;
    var pu = q("[data-pulse]"), txt = up.length ? plPulse(up.length, soon, plWhen(+hm.slice(0, 2), AR), AR) : K.sub(K.C.now_none, { city: K.C.cities[K.city()] || K.city() });
    if (pu && pu.textContent !== txt) pu.textContent = txt;
    up.forEach(function (s) { (by[s.c] = by[s.c] || []).push(s); (byF[s.f] = byF[s.f] || []).push(s); });
    qa(".row.cin[data-cin]").forEach(function (r) {
      var e = q("[data-cnext]", r), l = by[r.getAttribute("data-cin")] || [];
      if (e) e.textContent = plNext(l.length ? l[0].t : "", l.length, AR);
    });
    qa(".srow[data-fid]").forEach(function (d) {
      var l = byF[d.getAttribute("data-fid")] || [], nx = q("[data-nx]", d), fr = q("[data-fr]", d), b = l.length ? P.best(l) : null;
      if (nx) nx.textContent = l.length ? l[0].t : "";
      if (!fr || !b) return;
      var pe = q(".p", fr), was = pe && pe.getAttribute("data-shown");
      fr.innerHTML = K.esc(P.TX.from) + ' <span class="p" data-shown="' + K.fmt(b.pay) + '">' + P.payCell(b, go, was) + "</span>";
    });
  }
  /* «اعرض الكل»: shown only while the cap hides something the filters left (a filter can leave fewer than the cap) */
  function caps() {
    qa("[data-cap]").forEach(function (box) {
      var n = +box.getAttribute("data-cap"), b = q("[data-cap-open]", box);
      if (!b) return;
      var items = qa("[data-films] > .film, .rows > .row", box).filter(function (e) { return !e.classList.contains("x"); });
      b.hidden = box.classList.contains("open") || items.length <= n;
    });
  }
  /* each film's times already started today fold under one button; tapping it shows them struck, again hides them */
  function pastFold() {
    qa('.day[data-d="' + today() + '"] .cf').forEach(function (cf) {
      var n = qa(".tm.past", cf).length, cb = q(".cf-b", cf), b = cb && q(":scope > [data-past]", cb);
      if (!cb) return;
      if (!n) { if (b) b.hidden = true; return; }
      if (!b) {
        b = document.createElement("button"); b.type = "button"; b.className = "cf-past"; b.setAttribute("data-past", "");
        b.setAttribute("aria-expanded", cf.classList.contains("all-t") ? "true" : "false"); cb.appendChild(b);
      }
      b.hidden = false;
      b.textContent = plPast(n, AR);
    });
  }
  /* tomorrow folds under its heading: the heading says «اليوم» once the clock reaches its date, and opens once */
  function days() {
    var t = P.today();
    qa("details.day[data-d]").forEach(function (dd) {
      var d = dd.getAttribute("data-d"), h = q(":scope > summary > h2", dd), tx = h && h.firstChild;
      if (tx && tx.nodeType === 3) tx.textContent = (d === t[0] || d === t[1] ? P.day(d) : "") + " ";
      if (d <= t[0] && !dd.hasAttribute("data-opened")) { dd.setAttribute("data-opened", ""); dd.open = true; }
    });
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target : null, b;
    if (!t) return;
    if ((b = t.closest("[data-cap-open]"))) {
      var box = b.closest("[data-cap]"), n = +box.getAttribute("data-cap");
      box.classList.add("open"); b.hidden = true;
      /* the keyboard goes on where the list went on */
      var nx = qa("[data-films] > .film, .rows > .row .nm", box).filter(function (x) { return !x.closest(".x"); })[n];
      if (nx && nx.focus) nx.focus({ preventScroll: true });
      return;
    }
    if ((b = t.closest("[data-past]"))) {
      var cf = b.closest(".cf"), on = !cf.classList.contains("all-t");
      cf.classList.toggle("all-t", on); b.setAttribute("aria-expanded", on ? "true" : "false");
      return;
    }
    if (page === "city") setTimeout(caps, 0);   /* a filter or the sort may have changed what the cap hides */
  });
  if (page === "city") {
    clock(false); light(); city(false); caps();
    K.on("slice", function () { city(false); caps(); });
    K.on("card", function () { city(true); });
    K.on("minute", function () { clock(true); light(); city(false); caps(); });
  } else {
    pastFold(); days();
    K.on("minute", function () { pastFold(); days(); });
  }
}
if (K && K.pl && (K.page === "city" || K.page === "cinema")) plBoot();
