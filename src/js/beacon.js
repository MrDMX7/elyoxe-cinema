/* beacon.js — the privacy-first counter's only client file (plan §3.2 W3-P6; wired on every page 2026-10-17
   through pages/beacon.py, the endpoint filled by build.fill_counter from counter.yaml). No cookie, no id:
   `uid` is a daily-rotating value computed on-device from today's date + a random value kept in localStorage
   under "cinema.salt" (never sent anywhere else, never read back by us); the server keeps it two days, only to
   count distinct visitors a day. What is sent (infra/counter/lambdas/ingest.py is the contract):
     view        once per page, on pagehide / the tab going hidden (never `unload`: it blocks bfcache)
     return      once a day, how many days since the visitor's last day here (bucketed on-device)
     book_click  a tap on a chain's own booking link («احجز من موقع …»), with how long after landing (bucketed)
   A lazy chunk (build.chunk_js): this file's own scope receives the page's helpers as K. Target ≤ 0.6 KB gz. */
(function () {
  var API = "__COUNTER_API__"; // replaced at bundle time (build.fill_counter) with the real HTTP API endpoint
  if (!API || API.indexOf("__") === 0 || !navigator.sendBeacon) return;
  var PAGES = { home: 1, film: 1, cinema: 1, city: 1, coming: 1 };
  var kind = (document.body && document.body.getAttribute("data-page")) || "_";
  if (!PAGES[kind]) kind = "_";
  var t0 = Date.now(), once = {};

  function salt() {
    try {
      var s = localStorage.getItem("cinema.salt"), today = new Date().toISOString().slice(0, 10);
      if (!s || s.split("|")[0] !== today) {
        s = today + "|" + Math.random().toString(36).slice(2);
        localStorage.setItem("cinema.salt", s);
      }
      return s;
    } catch (e) { return ""; }
  }
  function send(event, extra, one) {
    if (one) { if (once[event]) return; once[event] = 1; }
    var body = Object.assign({ page: kind, event: event, uid: salt() }, extra || {});
    try {
      // text/plain, not application/json: sendBeacon is cross-origin and application/json is not
      // CORS-safelisted, so Chromium refuses (or throws on) the beacon. ingest.py parses the body as JSON
      // regardless of Content-Type (review r3-backend, Important #4).
      navigator.sendBeacon(API + "events", new Blob([JSON.stringify(body)], { type: "text/plain" }));
    } catch (e) {}
  }
  window.cinemaBeacon = send;

  function view() { send("view", null, true); }
  addEventListener("pagehide", view);
  addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") view(); });

  // return: the visitor's own last day here, kept only on the device; one event a day, none on the first day
  try {
    var today = new Date().toISOString().slice(0, 10), last = localStorage.getItem("cinema.last");
    if (last !== today) {
      if (last) {
        var d = Math.round((Date.parse(today) - Date.parse(last)) / 864e5);
        send("return", { return_bucket: d <= 1 ? "1" : d <= 7 ? "2-7" : d <= 30 ? "8-30" : "30+" });
      }
      localStorage.setItem("cinema.last", today);
    }
  } catch (e) {}

  // book_click: a link whose brand (the label before the TLD: voxcinemas, reelcinemas…) is one of the chains'
  // own sites (CT.sites) — booking pages live on other TLDs than the home pages (reelcinemas.com vs .ae)
  function brand(h) { var p = h.replace(/^www\./, "").split("."); return p.length > 1 ? p[p.length - 2] : h; }
  var SITES = (window.CT && CT.sites) || {}, brands = {};
  Object.keys(SITES).forEach(function (k) { try { brands[brand(new URL(SITES[k]).host)] = 1; } catch (e) {} });
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    var h; try { h = new URL(a.href, location.href).host; } catch (x) { return; }
    if (h === location.host) return;
    if (!brands[brand(h)] && !a.hasAttribute("data-book")) return;
    var s = (Date.now() - t0) / 1e3;
    send("book_click", { ttb_bucket: s < 3 ? "0-3s" : s < 10 ? "3-10s" : s < 30 ? "10-30s" : "30s+" });
  }, true);
})();
