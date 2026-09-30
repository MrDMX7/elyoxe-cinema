/* appfeel.js (r3-app, «iPhone-app feel»): a lazy chunk (pages/appfeel.py's LAZY_JS, loaded async on every page
   through page_js["*"]) — this progressive enhancement never counts against the initial bundle's own budget
   (build.py's JS_WARN_GZ), which core.js's start-up already leaves almost no room in. Runs in its own scope
   with K = window.CINEMA (core.js's feature()/startFeatures(), the same contract drag.js and search.js use).
   - iOS Safari never fires beforeinstallprompt (pwa.js's own Android install bar): from the second visit on,
     a one-time hint toward the Share sheet, dismissible, never shown again once dismissed. K.C.ios_install/
     ios_ok are site_kit.py's T strings, not cinema.js's TX, for the same budget reason.
   - The film page's day bar: swiping the schedule left/right moves a day at a time. Decided on touchend, not
     mid-gesture, so it never fights the page's own vertical scroll or a sheet's own drag; a swipe short of
     60px or steeper than it is wide is not a swipe, and touchmove is never listened to, so pull-to-refresh
     stays entirely native. */
if (+K.get("visits") >= 2 && !K.get("noiosinstall") && !window.navigator.standalone) {
  var ua = navigator.userAgent;
  if ((/iP(hone|od|ad)/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) &&
      /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|Android/.test(ua)) {
    var bar = document.createElement("div");
    bar.className = "inst"; bar.setAttribute("role", "region"); bar.setAttribute("aria-label", K.C.ios_install);
    bar.innerHTML = "<span>" + K.esc(K.C.ios_install) + '</span><button type="button" class="lnk" data-io="1">' + K.esc(K.C.ios_ok) + "</button>";
    document.body.appendChild(bar);
    bar.addEventListener("click", function (e) { if (e.target.closest("[data-io]")) { K.set("noiosinstall", "1"); bar.remove(); } });
  }
}
var afBox = K.q(".cgs");
if (afBox) {
  var afX = 0, afY = 0;
  afBox.addEventListener("touchstart", function (e) { if (e.touches.length === 1) { afX = e.touches[0].clientX; afY = e.touches[0].clientY; } }, { passive: true });
  afBox.addEventListener("touchend", function (e) {
    var t = e.changedTouches[0]; if (!t) return;
    var dx = t.clientX - afX, dy = t.clientY - afY;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    var days = K.qa("[data-day]"), on = K.q('[data-day][aria-pressed="true"]'), i = days.indexOf(on);
    if (i < 0) return;
    var fwd = document.documentElement.dir === "rtl" ? dx > 0 : dx < 0, next = days[fwd ? i + 1 : i - 1];
    if (next) next.click();
  }, { passive: true });
}
