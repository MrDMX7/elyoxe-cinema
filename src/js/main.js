/* main: the visitor's city and card (the header's pills and their sheets, src/js/sheet.js), showtime marks, the minute clock, start-up.
   It tells the other modules what happened through the hook bus (core.js on/emit, W1-P1): «ready», «slice», «card»,
   «city», «day», «minute». */

/* times already started are struck; those starting within 45 minutes (the «الحين» window) glow. Returns how
   many times changed state in this call (the minute tick re-judges the halls only then). */
function marks() {
  var n = NOW.getTime(), soon = n + 45 * 60e3, changed = 0;
  qa(".times[data-d]").forEach(function (box) {
    var d = box.getAttribute("data-d");
    qa("[data-start]", box).forEach(function (a) {
      var t = uae(d + "T" + a.getAttribute("data-start")).getTime();
      if ((t < n) !== a.classList.contains("past")) changed++;
      a.classList.toggle("past", t < n);
      if (t < n) { a.setAttribute("aria-disabled", "true"); a.setAttribute("tabindex", "-1"); }
      a.classList.toggle("nowish", t >= n && t <= soon);
    });
  });
  return changed;
}
function ago(at) {
  var m = Math.max(1, Math.floor((NOW - new Date(at)) / 60000)), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (!AR) return m < 60 ? m + " min ago" : h < 24 ? h + " hour" + (h !== 1 ? "s" : "") + " ago" : d + " day" + (d !== 1 ? "s" : "") + " ago";
  if (m < 60) return "قبل " + arCount(m, ["دقيقة", "دقيقتين", "دقايق", "دقيقة"]);
  if (h < 24) return "قبل " + arCount(h, ["ساعة", "ساعتين", "ساعات", "ساعة"]);
  return "قبل " + arCount(d, ["يوم", "يومين", "أيام", "يوم"]);
}
function ages() { qa("[data-at]").forEach(function (el) { el.textContent = C.updated + " " + ago(el.getAttribute("data-at")); }); }

/* film page: the visitor's city first and open, the others folded (film.js); a chosen time that left the view goes */
function renderFilm() {
  var secs = qa(".fcity[data-city]"); if (!secs.length) return;
  var mine = secs.filter(function (s) { return s.getAttribute("data-city") === city; });
  if (mine.length) secs[0].parentNode.insertBefore(mine[0], secs[0]);
  fsCities(); fsCheck();
}
/* the city's shows: loadCity (home.js) fills S, then «slice» says they are in, for the city still chosen */
function citySlice() { return loadCity().then(function () { if (S && S.city === city) emit("slice", S); }); }
function pickCity(c) {
  city = c; set("city", c);
  qa("[data-city-name]").forEach(function (el) { el.textContent = C.cities[c] || c; });
  qa("[data-citypick] a[data-city]").forEach(function (a) { if (a.getAttribute("data-city") === c) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current"); });
  if (page === "home") { citySlice(); billCity(); }
  if (page === "film") { renderFilm(); if (ST.prayer) applyPrayer(); }
  emit("city", c);
}
function markCard() {
  qa("button[data-card]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-card") === card ? "true" : "false"); });
  qa("[data-card-name]").forEach(function (el) { el.textContent = (card && C.cards && C.cards[card]) || C.mycard || el.textContent; });
}
/* the signature moment: a new card reprices every price on the page at once, digits turning over */
function pickCard(c) {
  card = c; set("card", c); markCard();
  renderPrices(true);
  if (page === "film") fsDock(false);
  if (S) renderHome(true); else applyFilters();
  if (tk) renderTerms(tk.getAttribute("data-chain"));
  emit("card", c);
}

/* «اليوم / بكرة» follow the visitor's clock (UAE time), not the build's: a page built last night calls
   this morning's shows «اليوم». A day already over keeps its date. */
/* one formatting per date: a film page carries ~150 day labels over two or three dates, and each
   toLocaleDateString builds a formatter (39 ms of start-up on a phone before this cache) */
var HUMAN_DAY = {};
function humanDay(d) {
  if (HUMAN_DAY[d]) return HUMAN_DAY[d];
  try { return (HUMAN_DAY[d] = new Date(d + "T12:00:00Z").toLocaleDateString(AR ? "ar-AE-u-nu-latn" : "en-GB", { timeZone: "UTC", day: "numeric", month: "long" })); }
  catch (e) { return d; }
}
function dayName(d) { return d === TODAY ? C.today : d === TOMORROW ? C.tomorrow : humanDay(d); }
function relabelDays() {
  /* the film page's day bar: «اليوم»/«بكرة» over the weekday and date; a day that is neither says its weekday */
  var later = qa("[data-day]").some(function (o) { return o.getAttribute("data-day") >= TODAY; });
  qa("[data-day]").forEach(function (b) {
    var d = b.getAttribute("data-day"), t = q("b", b), n = q("span", b), named = d === TODAY || d === TOMORROW;
    /* a day already over (the page was built the night before) has nothing left to book: its button goes — decided
       first, so it is never labelled (its date would be the page's first toLocaleDateString, ~200 ms of ICU on a
       slow phone, fix round 1 M1) */
    b.hidden = d < TODAY && later;
    if (b.hidden) return;
    if (!t) { b.textContent = dayName(d); return; }
    t.textContent = named ? dayName(d) : b.getAttribute("data-wd") || dayName(d);
    if (n && !named) n.textContent = humanDay(d);
  });
  /* (a film page's hall rows are laid out anew by film.js, without these labels: not worth formatting a date for) */
  qa(".times[data-d] > .dl").forEach(function (l) { if (!l.closest(".cgs")) l.textContent = dayName(l.parentNode.getAttribute("data-d")); });
  /* a day heading already carries the human date in its <small>: a day that is neither today nor
     tomorrow keeps only that, never the ISO date twice */
  qa(".day[data-d] > h2").forEach(function (h) {
    var d = h.parentNode.getAttribute("data-d"), t = h.firstChild;
    if (t && t.nodeType === 3) t.textContent = d === TODAY || d === TOMORROW ? dayName(d) + " " : "";
  });
}
/* a poster that fails to load gives way to the film's typographic tile (never a broken image) */
function posterFallback() {
  function drop(im) { var p = im.parentNode; if (p && p.classList) p.classList.remove("img"); im.remove(); }
  qa(".pst.img img, .bd img").forEach(function (im) {
    if (im.complete && im.naturalWidth === 0 && im.currentSrc) drop(im);
    else im.addEventListener("error", function () { drop(im); });
  });
}

/* posters in a sideways row: lazy images inside a scroller may wait too long — load each as it comes near */
function lazyRow() {
  if (!("IntersectionObserver" in window)) return;
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      var tile = e.target.closest(".film, .tile"), n = tile, k = 0;
      while (n && k++ < 3) { var im = q("img[loading=lazy]", n); if (im) { im.loading = "eager"; io.unobserve(im); } n = n.nextElementSibling; }
    });
  }, { rootMargin: "200px" });
  qa(".posters img[loading=lazy], .strip img[loading=lazy]").forEach(function (im) { io.observe(im); });
}
/* a home row's arrows (desktop): a strip's width at a time, toward the inline end or back (RTL scrolls negative) */
function bindRails() {
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-rail]");
    if (!b) return;
    var st = q("[data-strip]", b.closest(".rail"));
    if (st) st.scrollBy({ left: +b.getAttribute("data-rail") * st.clientWidth * 0.9 * (AR ? -1 : 1), behavior: RM ? "auto" : "smooth" });
  });
}

(function init() {
  /* a city from the sheet: picked in place, except on a page that IS a city (its city page, a cinema's page),
     where the link goes on to the chosen city's page */
  qa("[data-citypick] a[data-city]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      var c = a.getAttribute("data-city");
      set("city", c);
      if (page === "city" || page === "cinema") { e.preventDefault(); shGo(a.href); return; }
      e.preventDefault(); pickCity(c);
      if (a.closest("[role=dialog]")) sheetClose();
    });
  });
  qa("button[data-card]").forEach(function (b) {
    b.addEventListener("click", function () { pickCard(b.getAttribute("data-card")); if (b.closest("[role=dialog]")) sheetClose(); });
  });
  qa("[data-city-name]").forEach(function (el) { if (C.cities && C.cities[city]) el.textContent = C.cities[city]; });
  qa("[data-near]").forEach(function (b) { b.addEventListener("click", askNear); });
  qa("[data-day]").forEach(function (b) {
    b.addEventListener("click", function () {
      var d = b.getAttribute("data-day");
      qa("[data-day]").forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
      qa(".cgs .times[data-d]").forEach(function (t) { t.hidden = t.getAttribute("data-d") !== d; });
      applyFilters();
      if (page === "film") { fsMore(); fsSoon(); fsCheck(); }
      emit("day", d);
    });
  });
  upgradeTimes(); bindFilm();
  relabelDays();
  /* the day showing first: today while it still has a time to come, else the next day that has one (read from the
     text, so a compact schedule's times, still text in a cinema film.js has not laid out, count too) */
  var hm = hhmm(NOW.getTime()), days = qa("[data-day]"), cur = null, ahead = function (b) {
    var d = b.getAttribute("data-day");
    return d >= TODAY && qa('.times[data-d="' + d + '"]').some(function (t) {   /* stops at the first box that has one */
      var ts = t.textContent.match(/\d\d:\d\d/g) || [];
      return d > TODAY ? ts.length > 0 : ts.some(function (x) { return x >= hm; });
    });
  };
  for (var i = 0; i < days.length && !cur; i++) if (ahead(days[i])) cur = days[i];
  cur = cur || days.filter(function (b) { return b.getAttribute("data-day") === TODAY; })[0] ||
    days.filter(function (b) { return b.getAttribute("data-day") > TODAY; })[0] || days[0];
  if (cur) cur.click();
  document.addEventListener("click", function (e) { if (e.target.closest && e.target.closest("[data-forget]")) forgetLoc(); });
  var note = get("nearnote"); if (note) { set("nearnote", ""); nearMsg(note); }
  posterFallback();
  markCard(); marks(); ages(); renderPrices(false);
  bindSheets(); bindFilters(); bindBill(); bindRails(); bindTicket(); bindTabs(); bindTrailer(); bindPWA(); lazyRow();
  startFeatures();
  applyFilters();
  if (ST.prayer) applyPrayer();
  if (page === "film") fsStart();   /* the city and the day are known: «يبدأ بعد», the desktop's next show */
  if (LOC) applyNear(false);
  getJSON("/data/discounts.json").then(function (j) {
    D = j; renderPrices(false);
    if (S) renderHome(false);
    if (tk) renderTerms(tk.getAttribute("data-chain"));
  });
  if (page === "home" || page === "city") citySlice();
  /* a show link (#s-…) opens its ticket; else the desktop column moves off a show that has started (on a film page
     film.js's fsStart has chosen already: rollTicket serves the cinema and city pages) */
  if (!showFromHash()) rollTicket();
  /* the clock: at each UAE minute's :00 «الحين», the struck times, the halls whose last time passed, the desktop
     ticket, the leave-by line and the ages move on, then «minute» is emitted. One timeout aligned to the next :00
     and set again each time (never a free setInterval, which drifts off the minute: MASTER-PLAN §1.3, W1-P1) */
  function minute() {
    var d = TODAY; tick();
    if (d !== TODAY) {
      relabelDays();
      var gone = q('[data-day][aria-pressed="true"][hidden]'), nx = qa("[data-day]").filter(function (b) { return !b.hidden; })[0];
      if (gone && nx) nx.click();
    }
    if (marks()) hidePassed();   /* a hall can only run out when one of its times has just changed */
    ages(); renderNow(); renderNear(); rollTicket();
    if (page === "film") { fsSoon(); fsTick(); }
    if (typeof planRefresh === "function" && tk && !tk.hidden && (desk() || tk.classList.contains("open"))) planRefresh();
    emit("minute", NOW);
  }
  (function nextMinute() { setTimeout(function () { minute(); nextMinute(); }, 60e3 - (Date.now() + FAKE) % 60e3 + 20); })();
  emit("ready");
})();
