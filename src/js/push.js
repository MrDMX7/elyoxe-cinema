/* push.js — Web Push opt-in for the Thursday reminder («ذكّرني بالخميس», owner request 2026-09-30).
   Never runs on page load, never auto-prompts: cinemaPushSubscribe() only ever runs from the button's
   own click. Wired 2026-09-30 (round-3 review: this file existed but no page's markup called it) into
   /coming/'s masthead, its only caller so far -- pages/coming.py's LAZY_JS, so this loads there alone.
   iPhone needs the site added to the home screen first (Safari's own limit); the button still shows on
   iPhone (feature-detected, not UA-sniffed), and a Safari that hasn't been added yet just rejects the
   subscribe() promise, same error row as any other failure. A lazy chunk (build.chunk_js): this file's
   own scope receives the page's helpers as K, same as src/js/vote.js. */
(function () {
  var API = "__COUNTER_API__"; // replaced by deploy tooling with the real HTTP API endpoint
  var VAPID_PUBLIC = "__VAPID_PUBLIC_KEY__";

  function b64ToUint8(b64) {
    var pad = "=".repeat((4 - (b64.length % 4)) % 4);
    var s = (b64 + pad).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(s), arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  window.cinemaPushSubscribe = function () {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || API.indexOf("__") === 0) {
      return Promise.reject(new Error("unsupported"));
    }
    return navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(VAPID_PUBLIC) });
    }).then(function (sub) {
      var raw = sub.toJSON();
      return fetch(API + "push/subscribe", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: raw.endpoint, keys: raw.keys, topic: "weekly" })
      });
    });
  };

  /* the button: only /coming/'s masthead has [data-push-row] (pages/coming.py). Unsupported browser or
     an undeployed placeholder (API still literally "__COUNTER_API__") -- the row stays hidden, same
     silent fallback the .ics line beside it uses for non-iPhone visitors. */
  var row = K.q("[data-push-row]"), btn = K.q("[data-push-btn]"), live = K.q("[data-push-live]");
  if (!row || !btn) return;
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || API.indexOf("__") === 0) return;
  var W = K.AR
    ? { ask: "ذكّرني بالخميس", on: "مفعّل، بنذكّرك", busy: "لحظة…", err: "ما قدرنا نفعّلها. جرّب تاني." }
    : { ask: "Remind me Thursday", on: "On — we'll remind you", busy: "One sec…", err: "Couldn't turn it on. Try again." };
  btn.textContent = W.ask;
  row.hidden = false;
  navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); }).then(function (sub) {
    if (sub) { btn.textContent = W.on; btn.disabled = true; }
  }).catch(function () {});
  btn.addEventListener("click", function () {
    if (btn.disabled) return;
    btn.disabled = true; btn.textContent = W.busy;
    window.cinemaPushSubscribe().then(function () {
      btn.textContent = W.on;
      if (live) live.textContent = W.on;
    }).catch(function () {
      btn.disabled = false; btn.textContent = W.ask;
      if (live) live.textContent = W.err;
    });
  });
})();
