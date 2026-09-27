/* «راعِ أوقات الصلاة» (off by default, remembered): Maghrib and Isha for the page's city and each show's
   date, computed here with adhan (MIT, /assets/adhan.<hash>.js, fetched only when the switch goes on).
   Method and offsets copied from saas/tools/src/assets/prayer.js (the /tools prayer-times tool): the
   Dubai/IACAD method (18.2°) with asr −1, maghrib +1, isha +1 minutes — measured there against the
   published UAE timetable on 2026-09-24 (25 of 30 cells exact, the rest within a minute). City
   coordinates are that file's too. A show is marked when a prayer falls inside it or it starts within
   20 minutes after one. */
var PRAY_AT = { "abu-dhabi": [24.4539, 54.3773], dubai: [25.2048, 55.2708], sharjah: [25.3463, 55.4209], "al-ain": [24.2075, 55.7447],
  ajman: [25.4052, 55.5136], "umm-al-quwain": [25.5647, 55.5552], "ras-al-khaimah": [25.8007, 55.9762], fujairah: [25.1288, 56.3265] };
var PRAY_WIN = 20, PT = {}, adhanP = null;
function loadAdhan() {
  if (window.adhan) return Promise.resolve(window.adhan);
  return adhanP || (adhanP = new Promise(function (ok, no) {
    var s = document.createElement("script");
    s.src = C.adhan; s.async = true;
    s.onload = function () { ok(window.adhan); }; s.onerror = function () { adhanP = null; no(); };
    document.head.appendChild(s);
  }));
}
function prayParams(A) {
  var p = A.CalculationMethod.Dubai();
  p.adjustments.asr = -1; p.adjustments.maghrib = 1; p.adjustments.isha = 1;
  return p;
}
/* {maghrib, isha} as minutes after the date's midnight, UAE time */
function prayersFor(cid, d) {
  var k = cid + d, c = PRAY_AT[cid], A = window.adhan;
  if (PT[k] || !c || !A) return PT[k] || null;
  var ymd = d.split("-"), pt = new A.PrayerTimes(new A.Coordinates(c[0], c[1]), new Date(+ymd[0], +ymd[1] - 1, +ymd[2]), prayParams(A));
  var m = function (t) { var s = hhmm(t.getTime()); return +s.slice(0, 2) * 60 + +s.slice(3); };
  return (PT[k] = { maghrib: m(pt.maghrib), isha: m(pt.isha) });
}
function clashOf(span, pr) {
  if (!pr) return "";
  return overlaps(span, pr.maghrib, PRAY_WIN) ? TX.maghrib : overlaps(span, pr.isha, PRAY_WIN) ? TX.isha : "";
}
function spanOf(a) {
  var rt = a.closest("[data-runtime]");
  return showSpan(a.getAttribute("data-start"), a.getAttribute("data-ends"), rt && rt.getAttribute("data-runtime"));
}
function mm(m) { return ("0" + Math.floor(m / 60)).slice(-2) + ":" + ("0" + m % 60).slice(-2); }

/* the home and city tiles work out which shows still fit (renderHome's showOk reads the clashes); elsewhere the
   time buttons were just marked */
function prayerDone() { if (S && (page === "home" || page === "city")) renderHome(false); else applyFilters(); }
function applyPrayer() {
  qa("[data-prayer]").forEach(function (sw) { sw.setAttribute("aria-checked", ST.prayer ? "true" : "false"); });
  qa("[data-hide-clash]").forEach(function (b) { b.hidden = !ST.prayer; b.setAttribute("aria-pressed", ST.hide ? "true" : "false"); });
  if (!ST.prayer) {
    qa(".tm.clash").forEach(function (a) { a.classList.remove("clash"); a.removeAttribute("title"); var z = q(".pz", a); if (z) z.remove(); });
    qa("[data-prayer-times]").forEach(function (el) { el.textContent = ""; });
    prayerDone();
    return Promise.resolve();
  }
  return loadAdhan().then(function () {
    qa(".times[data-d]").forEach(function (box) {
      var sec = box.closest("[data-city]"), cid = sec ? sec.getAttribute("data-city") : pageCity, d = box.getAttribute("data-d");
      var pr = cid && prayersFor(cid, d);
      qa(".tm[data-start]", box).forEach(function (a) {
        var p = clashOf(spanOf(a), pr), z = q(".pz", a);
        a.classList.toggle("clash", !!p);
        if (p) { var t = sub(TX.clash, { p: p }); a.title = t; if (!z) a.insertAdjacentHTML("beforeend", '<small class="pz">' + esc(t) + "</small>"); else z.textContent = t; }
        else { a.removeAttribute("title"); if (z) z.remove(); }
      });
    });
    var today = prayersFor(pageCity || city, TODAY);
    qa("[data-prayer-times]").forEach(function (el) { el.textContent = today ? sub(TX.ptimes, { m: mm(today.maghrib), i: mm(today.isha) }) : ""; });
    prayerDone();
  }).catch(function () {});
}
