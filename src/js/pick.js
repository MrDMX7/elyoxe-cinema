/* «اختار لي»: pick.js, the scorer (legend W2-P2b; MASTER-PLAN §3.1, §5.3 W2-P2). A lazy chunk (pages/board.py
   LAZY_JS, on home and the 404 — PAGE_JS also lists it on a city page, where places.py already built the held
   button): K is window.CINEMA, and K.bd is what src/js/board.js hands over from the bundle (the visitor's slice,
   distance, the price after the card through K.bd.price, disc.js). It is the one scorer behind every «اختار لي»
   and, later, «أقرب عرض لك» (film.first stays board-live.js's own soonest-show fallback until this chunk is asked
   to limit itself to one film — out of this package's scope).

   Stub scope (this package; a full W2-P2b would also carry the deck and a node-run golden fixture over the frozen
   1,522-show slice — named here, not invented, because the data or the harness is not built yet):
   - **inputs it has**: the visitor's city slice (two days), distance, the price after the card, «مع منو»/«متى»/
     «وين» (window.CINEMA.ask(), filters.js — W2-P4, already landed), and a film's verdict/«مع منو» fit/rating
     from the grid's own tile (kit/tile.py film_attrs writes data-v, data-fits, data-rating once; the pick reads
     that one copy, never a second one).
   - **inputs it does not have yet, so the code that stands in for them says so**: RT/audience scores for an
     unknown verdict (§3.1's .5 bump — plain «unknown» .3 here), seat occupancy (no "sold out" filter), the adhan
     chunk (no prayer-clash filter), and R1/R4's saved list and favourite cinemas (the personal term is 0 for
     everyone today, never guessed).
   - a film with no tile on the page (the 404 has none) scores an unknown verdict, and under «العايلة» or «العيال»
     it is excluded rather than assumed fit — the safe default, never a claim the page cannot check.

   Hard filters (a show is never picked): started, or unreachable — the film page's own travel rule
   (board-live.js `first()`, kept the same number here rather than the plan prose's: 35 min with no location,
   round(km×1.6)+20 with one; its verdict is «تجنّبه» (R1's list would spare a saved one; not built, so never
   true today); it fails the stored «مع منو» (kit/filters.who_fits, the same rule the grid applies).

   Score (§3.1, each term 0–1): verdict .28, start fit .20 (this session's «متى» — a soft term for the pick;
   «متى» hard-filters only the grid, filters.js), distance .15, price .12 (against the cheapest reachable show of
   the same film tonight), «مع منو» fit .10, personal .15 (0 until R1/R4 land, never guessed).

   Output: one card per film (its best show), at most 2 of one cinema among the top 3 kept — no randomness, the
   same inputs give the same pick. «ليش؟» prints the price and the top 3 positive terms in plain words (§3.1's
   example: «يستاهل، يبدأ بعد 35 د، 8 كم، 29 درهم بعد فزعة»); a pick that cannot explain itself does not render.
   «غيره» swaps to the next card with no flaps; the flaps (§1.3) run once, on the session's first pick this
   session (sessionStorage, never localStorage — a first impression, not a preference), then never again. A
   landed pick is announced once (aria-live) and focus moves to its «احجز». */
var PK = { list: [], i: -1, Y: null, tomorrow: null };

function pkT(ar, en) { return K.AR ? ar : en; }
function pkToMin(t) { return +t.slice(0, 2) * 60 + +t.slice(3, 5); }
/* the film-first travel rule (board-live.js's own number): never invented here a second time */
function pkReachMs(km) { return (km == null ? 35 : Math.round(km * 1.6) + 20) * 6e4; }
/* «مع منو» fit (kit/filters.who_fits' data-fits): an unknown fit under a restriction is excluded, never assumed */
function pkWhoOk(fits, who) { return !who || (" " + (fits || "") + " ").indexOf(" " + who + " ") >= 0; }
/* the film's tile, wherever the page drew one («كل الأفلام», a home row): the grid tile is the one that carries
   data-fits/data-rating (kit/tile.py, row=False); a home row's tile (row=True) has neither, so it is never picked
   over a grid tile that exists for the same film (fix round: a family/kids pick was dropping films that also had
   a row, because the row tile came first in the DOM and its missing data-fits read as "fits nothing") */
function pkMeta(fid) {
  var el = K.q('.film.tile[data-fid="' + fid + '"][data-v]') || K.q('[data-fid="' + fid + '"][data-v]');
  return el ? { v: el.getAttribute("data-v") || "unknown", fits: el.getAttribute("data-fits") || "", rating: el.getAttribute("data-rating") || "" }
            : { v: "unknown", fits: "", rating: "" };
}
function pkSeen(fid) {   // «شفته؟» (R10): reads the one schema §3.3 sets; never true before that package writes to it
  try { var m = JSON.parse(localStorage.getItem("cinema.me") || "null"); return !!(m && m.seen && m.seen[fid]); } catch (e) { return false; }
}
/* verdict (.28): «يستاهل» 1, «بين بين» .55, unknown .3 (the RT-informed .5 bump waits for that data feed) */
function pkVerdict(v) { return v === "yes" ? 1 : v === "mixed" ? .55 : .3; }
/* a plateau: 1 between lo and hi, ramping down over `ramp` minutes on each side */
function pkPlateau(x, lo, hi, ramp) {
  if (x < lo) return Math.max(0, 1 - (lo - x) / ramp);
  if (x <= hi) return 1;
  return Math.max(0, 1 - (x - hi) / ramp);
}
/* start fit (.20): centred by «متى» (window.CINEMA.ask().when). `dayMin` counts from the previous 06:00, so a
   00:30 show reads as 1470, staying inside the same evening as the «متى» windows describe (§3.1) */
function pkStart(mins, dayMin, when) {
  if (when === "tonight") return pkPlateau(dayMin, 1170, 1320, 90);      // 19:30–22:00
  if (when === "late") return pkPlateau(dayMin, 1290, 1410, 90);         // 21:30–23:30
  if (when === "tomorrow") return 1;                                    // already date-filtered by pkCandidates
  return pkPlateau(mins, 25, 75, mins < 25 ? 25 : 75);                   // «الحين» / no answer: 25–75 min, gone by 150
}
/* distance (.15): 1 at ≤ 3 km, 0 at ≥ 30 km, .5 with no location (a favourite cinema's "counts 1" waits for R4) */
function pkDist(km) { return km == null ? .5 : km <= 3 ? 1 : km >= 30 ? 0 : 1 - (km - 3) / 27; }
/* «مع منو» fit (.10): family scores by rating (G/PG 1, PG13 .5), kids by the flag, «كبار» is neutral */
function pkWhoFit(meta, who) {
  if (who === "family") { var r = meta.rating; return r === "G" || r === "PG" ? 1 : r === "PG13" ? .5 : meta.fits.indexOf("family") >= 0 ? 1 : 0; }
  if (who === "kids") return meta.fits.indexOf("kids") >= 0 ? 1 : 0;
  return .5;
}
/* personal (.15): what R1/R4 will feed once they land; named, not guessed, so it is 0 for everyone today */
function pkPersonal() { return 0; }

/* every reachable, allowed show as a candidate {s, meta, km, pay} — one per show; pkRank collapses to one per film.
   `Y` is already only the visitor's next two days (K.bd.day/loadCity), so no upper bound is needed here; «بكرة» asks
   for tomorrow's date only, every other «متى» (or none) leaves the plateau in pkStart to say which of the two suits */
function pkCandidates(Y, nowMs, ask, tomorrow) {
  var out = [];
  (Y.shows || []).forEach(function (s) {
    if (s.at < nowMs + pkReachMs(K.bd.km(s.c))) return;
    if (ask.when === "tomorrow" && s.d !== tomorrow) return;
    var meta = pkMeta(s.f);
    if (meta.v === "skip") return;              // «تجنّبه»
    if (pkSeen(s.f)) return;                     // «شفته؟»
    if (!pkWhoOk(meta.fits, ask.who)) return;
    /* the cheapest *sold* price, or 0 with none (fix round, Critical #1: concat([0]) before the min used to make
       every result 0 — board-live.js `lowest()` is the same "positives only, else 0" rule) */
    var prices = (s.p || []).map(function (p) { return p[1]; }).filter(function (v) { return v > 0; });
    var pay = prices.length ? Math.min.apply(null, prices) : 0;
    out.push({ s: s, meta: meta, km: K.bd.km(s.c), pay: pay });
  });
  return out;
}

/* rank(): §3.1's score, one card per film, then the diversity rule (≤ 2 of one cinema among the 3 kept) */
function pkRank(cand, nowMs, ask) {
  var byFilm = {}, minPay = {};
  cand.forEach(function (c) { if (c.pay && (!minPay[c.s.f] || c.pay < minPay[c.s.f])) minPay[c.s.f] = c.pay; });
  cand.forEach(function (c) {
    var mins = Math.round((c.s.at - nowMs) / 6e4), dm = pkToMin(c.s.t); if (dm < 360) dm += 1440;
    var t = { v: pkVerdict(c.meta.v), start: pkStart(mins, dm, ask.when), dist: pkDist(c.km),
      price: c.pay ? Math.min(1, (minPay[c.s.f] || c.pay) / c.pay) : .5, who: pkWhoFit(c.meta, ask.who), personal: pkPersonal() };
    var score = t.v * .28 + t.start * .2 + t.dist * .15 + t.price * .12 + t.who * .1 + t.personal * .15;
    if (!byFilm[c.s.f] || score > byFilm[c.s.f].score) byFilm[c.s.f] = { c: c, score: score, t: t, mins: mins };
  });
  var ranked = Object.keys(byFilm).map(function (f) { return byFilm[f]; }).sort(function (a, b) { return b.score - a.score; });
  var out = [], perCinema = {};
  for (var i = 0; i < ranked.length && out.length < 3; i++) {
    var r = ranked[i], cid = r.c.s.c, n = perCinema[cid] || 0;
    if (n >= 2) continue;
    perCinema[cid] = n + 1; out.push(r);
  }
  return out;
}

function pkChain(cid) { return PK.Y && PK.Y.cinemas[cid] ? PK.Y.cinemas[cid].chain : ""; }
/* the price after the card, through the one function the board and every price cell already use (disc.js).
   `data-asof` is passed through (fix round, Important #6) so a fallback-table price is never presented as live —
   board-live.js `lowest()` already refuses those; `off` says whether the card actually changed it, for pkWhyPrice */
function pkPrice(c) {
  if (!c.pay) return { html: "", pay: 0, off: false };
  var el = document.createElement("span");
  el.setAttribute("data-aed", c.pay); el.setAttribute("data-cin", c.s.c); el.setAttribute("data-hall", c.s.h);
  el.setAttribute("data-hk", c.s.k); el.setAttribute("data-chain", pkChain(c.s.c));
  if (c.s.asof) el.setAttribute("data-asof", c.s.asof);
  el.innerHTML = K.bd.price(el, false);
  return { html: el.innerHTML, pay: +el.getAttribute("data-shown") || c.pay, off: /<s[ >]/.test(el.innerHTML) };
}
/* the price term for «ليش؟»: only the pay figure plus «درهم», and «بعد {card}» once it actually changed the price
   (§3.1's own example: «29 درهم بعد فزعة») — never the struck list price or the asof note run in beside it
   (fix round, Important #6: the stripped-tags version used to read "29 42" with no unit) */
function pkWhyPrice(pr) {
  if (!pr.html) return "";
  var s = '<span class="num">' + pr.pay + "</span> " + K.esc(K.C.aed || "");
  var cn = pr.off && K.C.cards && K.C.cards[K.card()];
  if (cn) s += " " + K.esc(K.sub(K.C.after_card, { card: cn }));
  return s;
}
/* the start-fit line, worded from the show's own date/time, never a fixed «الليلة» (fix round, Important #5: a
   tomorrow show, or a same-day show hours out, used to be captioned "tonight" regardless) */
function pkWhyStart(r, tomorrow) {
  if (r.mins > 0 && r.mins <= 90) return pkT("يبدأ بعد " + r.mins + " د", "starts in " + r.mins + " min");
  if (r.c.s.d === tomorrow) return pkT("بكرة " + r.c.s.t, "tomorrow " + r.c.s.t);
  return pkT(r.c.s.t, r.c.s.t);
}
/* «ليش؟»: the price, then the top 3 positive terms in plain words (§3.1's example) */
function pkWhy(r, priceText, tomorrow) {
  var t = r.t, why = [];
  if (r.c.meta.v === "yes") why.push({ w: 1, s: pkT("يستاهل", "worth it") });
  else if (r.c.meta.v === "mixed") why.push({ w: .3, s: pkT("بين بين", "mixed") });
  why.push({ w: t.start, s: pkWhyStart(r, tomorrow) });
  if (r.c.km != null) why.push({ w: t.dist, s: K.bd.kmt(r.c.km, K.lang) });
  why.sort(function (a, b) { return b.w - a.w; });
  var top = why.slice(0, 3).map(function (x) { return x.s; });
  if (priceText) top.push(priceText);
  return top.join(pkT("، ", ", "));
}

var PK_T = {
  head: pkT("اخترنا لك", "We picked"), why: pkT("ليش؟", "Why?"), again: pkT("غيره", "Something else"),
  book: pkT("احجز من {c}", "Book at {c}"),
  empty: pkT("ما لقينا عرض يناسب الحين. جرّب تغيّر «مع منو» أو «متى»", "Nothing fits right now. Try changing who's coming or when."),
  said: pkT("اخترنا لك: {t} {f}، {c}", "We picked: {t} {f}, {c}")
};

function pkRender(box, flap) {
  var r = PK.list[PK.i];
  if (!r) { pkEmpty(box); return; }
  var s = r.c.s, cn = K.bd.nm((PK.Y.cinemas || {})[s.c] || {}), fn = K.bd.nm((PK.Y.films || {})[s.f] || {});
  var pr = pkPrice(r.c), chain = pkChain(s.c), why = pkWhy(r, pkWhyPrice(pr), PK.tomorrow);
  box.className = "pk-stub paper" + (flap ? " pk-flap" : "");
  box.innerHTML =
    '<div class="pk-body"><p class="pk-h">' + K.esc(PK_T.head) + '</p>'
    + '<p class="pk-when"><b class="num" dir="ltr">' + K.esc(s.t) + '</b> <bdi' + (K.AR && !/[؀-ۿ]/.test(fn) ? ' lang="en" dir="ltr"' : "") + '>' + K.esc(fn) + '</bdi></p>'
    + '<p class="pk-cin"><bdi>' + K.esc(cn) + '</bdi></p>'
    + (pr.html ? '<p class="pk-p">' + pr.html + '</p>' : "")
    + '<p class="pk-why"><b>' + K.esc(PK_T.why) + '</b> ' + why + '</p></div>'
    /* the fallback (no booking URL yet) opens the film page's own anchor, same as home.js's tile — never a bare
       "#s-…" on the page pick.js rendered on (home/404 have no such anchor), fix round Minor #3 */
    + '<div class="pk-act"><a class="btn main velvet" href="' + K.esc(s.b || (K.C.base + "film/" + s.f + "/#s-" + K.showKey(s.c, s.d, s.t, s.k))) + '"'
    + (s.b ? ' rel="noopener nofollow" target="_blank"' : "") + ' data-pk-book>'
    + K.esc(PK_T.book.replace("{c}", (K.C.chains && K.C.chains[chain]) || chain || cn)) + '</a>'
    + '<button type="button" class="btn ghost" data-pk-again>' + K.esc(PK_T.again) + "</button></div>";
  var live = document.getElementById("pk-live");
  /* textContent never needs K.esc: escaping is for innerHTML, and here it double-escapes (fix round, Minor #2) */
  if (live) live.textContent = PK_T.said.replace("{t}", s.t).replace("{f}", fn).replace("{c}", cn);
  var go = K.q("[data-pk-book]", box);
  if (go) { if (flap) setTimeout(function () { go.focus(); }, 920); else go.focus(); }
}

function pkFlapOnce() {
  try { if (sessionStorage.getItem("cinema.pkFlap")) return false; sessionStorage.setItem("cinema.pkFlap", "1"); return true; } catch (e) { return true; }
}

/* the box lands after the flex row that holds the button (home's `.bh-top`, places.py's `.ch-t`), never as a
   third item squeezed into that row itself — the 404's `.bh-nolabel` has no such row, so the old "after the
   button" default still applies there (fix round, Important #2: the stub used to render inside `.bh-top`'s own
   flex layout on home, at 360/390 too). `btn._pkBox` (not DOM position) is how pkGo finds it again, since the
   box is no longer always the button's next sibling. */
function pkMount(btn) {
  if (!document.getElementById("pk-live")) {
    var live = document.createElement("p"); live.id = "pk-live"; live.className = "vh"; live.setAttribute("aria-live", "polite");
    document.body.appendChild(live);
  }
  var box = document.createElement("div"); box.className = "pk-stub"; box.setAttribute("data-pk-box", "");
  var row = btn.closest(".bh-top") || btn.closest(".ch-t");
  (row || btn).insertAdjacentElement("afterend", box);
  btn._pkBox = box;
  return box;
}

function pkRun(box, city, ask) {
  var nowMs = K.now().getTime(), dd = K.bd.days();
  PK.tomorrow = dd[1];
  PK.list = pkRank(pkCandidates(PK.Y, nowMs, ask, dd[1]), nowMs, ask);
  PK.i = 0;
  pkRender(box, pkFlapOnce());
}

function pkEmpty(box) { box.className = "pk-stub"; box.innerHTML = '<p class="pk-empty">' + K.esc(PK_T.empty) + "</p>"; }

function pkGo(btn) {
  var city = btn.getAttribute("data-pick") || K.city();
  var box = btn._pkBox || pkMount(btn);
  var ask = window.CINEMA.ask ? window.CINEMA.ask() : { who: "", when: "", where: "" };
  var have = K.bd.S();
  if (have && have.city === city) { PK.Y = have; pkRun(box, city, ask); return; }
  var dd = K.bd.days();
  /* a slice fetch can fail (offline, a bad response): «غيره» would then tap on nothing forever, so a failure
     says the same "nothing fits" line rather than the button going silent (fix round, Minor #1) */
  Promise.all([K.bd.day(city, dd[0]), K.bd.day(city, dd[1])]).then(function (ds) {
    var o = { cinemas: {}, films: {}, shows: [], city: city };
    ds.forEach(function (x) { for (var k in x.cinemas) o.cinemas[k] = x.cinemas[k]; for (k in x.films) o.films[k] = x.films[k]; o.shows = o.shows.concat(x.shows); });
    PK.Y = o;
    if (!o.shows.length) { pkEmpty(box); return; }
    pkRun(box, city, ask);
  }).catch(function () { pkEmpty(box); });
}

document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest("[data-pick]");
  if (b) { e.preventDefault(); pkGo(b); return; }
  var again = e.target.closest && e.target.closest("[data-pk-again]");
  if (again) { e.preventDefault(); PK.i = (PK.i + 1) % (PK.list.length || 1); pkRender(again.closest("[data-pk-box]"), false); }
});
/* the button sat hidden («held for the pick», places.py, board.py): only this chunk knows it can answer */
K.qa("[data-pick]").forEach(function (b) { b.hidden = false; b.classList.remove("hold"); });
