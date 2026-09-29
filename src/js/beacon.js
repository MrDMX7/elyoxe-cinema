/* beacon.js — the privacy-first counter's only client file (plan §3.2 W3-P6). No cookie, no id:
   a daily-rotating salted hash (`uid`) computed on-device from today's date + a random value kept
   in localStorage under "cinema.salt" (never sent anywhere else, never read back by us). Sent on
   `pagehide`, never `unload` (unload blocks bfcache). Not wired into any page yet — the endpoint
   below is filled in by infra/counter/deploy.sh's output; a page that wants counting calls
   window.cinemaBeacon(event, extra) after loading this file.
   Target: <= 0.4 KB gz on its own (plan budget), lazy — load it on idle, not blocking. */
(function () {
  var API = "__COUNTER_API__"; // replaced by deploy tooling with the real HTTP API endpoint
  function salt() {
    try {
      var s = localStorage.getItem("cinema.salt");
      var today = new Date().toISOString().slice(0, 10);
      if (!s || s.split("|")[0] !== today) {
        s = today + "|" + Math.random().toString(36).slice(2);
        localStorage.setItem("cinema.salt", s);
      }
      return s;
    } catch (e) { return ""; }
  }
  window.cinemaBeacon = function (event, extra) {
    if (!API || API.indexOf("__") === 0) return;
    var body = Object.assign({ page: window.cinemaPageKind || "_", event: event, uid: salt() }, extra || {});
    try {
      var blob = new Blob([JSON.stringify(body)], { type: "application/json" });
      if (navigator.sendBeacon) navigator.sendBeacon(API + "events", blob);
    } catch (e) {}
  };
  window.addEventListener("pagehide", function () { window.cinemaBeacon("view"); }, { once: true });
})();
