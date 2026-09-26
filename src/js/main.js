/* main: the control sentence «أنا في [المدينة] وعندي [البطاقة]», showtime marks, the minute clock, start-up. */

/* times already started are struck; those starting within 45 minutes (the «الحين» window) glow */
function marks() {
  var n = NOW.getTime(), soon = n + 45 * 60e3;
  qa(".times[data-d]").forEach(function (box) {
    var d = box.getAttribute("data-d");
    qa("[data-start]", box).forEach(function (a) {
      var t = uae(d + "T" + a.getAttribute("data-start")).getTime();
      a.classList.toggle("past", t < n);
      if (t < n) { a.setAttribute("aria-disabled", "true"); a.setAttribute("tabindex", "-1"); }
      a.classList.toggle("nowish", t >= n && t <= soon);
    });
  });
}
function ago(at) {
  var m = Math.max(1, Math.floor((NOW - new Date(at)) / 60000)), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (!AR) return m < 60 ? m + " min ago" : h < 24 ? h + " hour" + (h !== 1 ? "s" : "") + " ago" : d + " day" + (d !== 1 ? "s" : "") + " ago";
  if (m < 60) return "قبل " + arCount(m, ["دقيقة", "دقيقتين", "دقايق", "دقيقة"]);
  if (h < 24) return "قبل " + arCount(h, ["ساعة", "ساعتين", "ساعات", "ساعة"]);
  return "قبل " + arCount(d, ["يوم", "يومين", "أيام", "يوم"]);
}
function ages() { qa("[data-at]").forEach(function (el) { el.textContent = C.updated + " " + ago(el.getAttribute("data-at")); }); }

/* film page: the visitor's city first */
function renderFilm() {
  var secs = qa(".fcity[data-city]"); if (!secs.length) return;
  var mine = secs.filter(function (s) { return s.getAttribute("data-city") === city; });
  secs.forEach(function (s) { s.classList.toggle("here", s.getAttribute("data-city") === city); });
  if (mine.length) secs[0].parentNode.insertBefore(mine[0], secs[0]);
}
function pickCity(c) {
  city = c; set("city", c);
  qa("[data-city-name]").forEach(function (el) { el.textContent = C.cities[c] || c; });
  qa("[data-citypick] a[data-city]").forEach(function (a) { if (a.getAttribute("data-city") === c) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current"); });
  if (page === "home") loadCity();
  if (page === "film") { renderFilm(); if (ST.prayer) applyPrayer(); }
}
function markCard() {
  qa("button[data-card]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-card") === card ? "true" : "false"); });
  qa("select[data-card]").forEach(function (s) {
    var has = !!card && [].some.call(s.options, function (o) { return o.value === card; });
    s.value = has ? card : ""; s.parentNode.classList.toggle("on", has);
  });
}
/* the signature moment: a new card reprices every price on the page at once, digits turning over */
function pickCard(c) {
  card = c; set("card", c); markCard();
  renderPrices(true);
  if (S) renderHome(true); else applyFilters();
  if (tk) renderTerms(tk.getAttribute("data-chain"));
}

/* «اليوم / بكرة» follow the visitor's clock (UAE time), not the build's: a page built last night calls
   this morning's shows «اليوم». A day already over keeps its date. */
function dayName(d) { return d === TODAY ? C.today : d === TOMORROW ? C.tomorrow : d; }
function relabelDays() {
  qa("[data-day]").forEach(function (b) { b.textContent = dayName(b.getAttribute("data-day")); });
  qa(".times[data-d] > .dl").forEach(function (l) { l.textContent = dayName(l.parentNode.getAttribute("data-d")); });
  qa(".day[data-d] > h2").forEach(function (h) { var t = h.firstChild; if (t && t.nodeType === 3) t.textContent = dayName(h.parentNode.getAttribute("data-d")) + " "; });
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
      var tile = e.target.closest(".film"), n = tile, k = 0;
      while (n && k++ < 3) { var im = q("img[loading=lazy]", n); if (im) { im.loading = "eager"; io.unobserve(im); } n = n.nextElementSibling; }
    });
  }, { rootMargin: "200px" });
  qa(".posters img[loading=lazy]").forEach(function (im) { io.observe(im); });
}

(function init() {
  qa("[data-citypick] a[data-city]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      var c = a.getAttribute("data-city");
      set("city", c);
      if (page === "home" || page === "film") { e.preventDefault(); a.closest("details").open = false; pickCity(c); }
    });
  });
  qa("button[data-card]").forEach(function (b) { b.addEventListener("click", function () { pickCard(b.getAttribute("data-card")); }); });
  qa("select[data-card]").forEach(function (s) { s.addEventListener("change", function () { pickCard(s.value); }); });
  qa("[data-city-name]").forEach(function (el) { if (C.cities && C.cities[city]) el.textContent = C.cities[city]; });
  qa("[data-near]").forEach(function (b) { b.addEventListener("click", askNear); });
  qa("[data-day]").forEach(function (b) {
    b.addEventListener("click", function () {
      var d = b.getAttribute("data-day");
      qa("[data-day]").forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
      qa(".cgs .times[data-d]").forEach(function (t) { t.hidden = t.getAttribute("data-d") !== d; });
      applyFilters();
    });
  });
  relabelDays();
  var days = qa("[data-day]"), cur = days.filter(function (b) { return b.getAttribute("data-day") === TODAY; })[0] ||
    days.filter(function (b) { return b.getAttribute("data-day") > TODAY; })[0] || days[0];
  if (cur) cur.click();
  document.addEventListener("click", function (e) { if (e.target.closest && e.target.closest("[data-forget]")) forgetLoc(); });
  var note = get("nearnote"); if (note) { set("nearnote", ""); nearMsg(note); }
  upgradeTimes(); posterFallback();
  markCard(); marks(); ages(); renderPrices(false);
  if (page === "film") renderFilm();
  bindFilters(); bindTicket(); bindTrailer(); bindPWA(); lazyRow();
  applyFilters();
  if (ST.prayer) applyPrayer();
  if (LOC) applyNear(false);
  getJSON("/data/discounts.json").then(function (j) {
    D = j; renderPrices(false);
    if (S) renderHome(false);
    if (tk) renderTerms(tk.getAttribute("data-chain"));
  });
  if (page === "home" || page === "city") loadCity();
  /* the clock: every minute «الحين», the struck times and the ages move on */
  setInterval(function () { var d = TODAY; tick(); if (d !== TODAY) relabelDays(); marks(); ages(); renderNow(); }, 60e3);
})();
