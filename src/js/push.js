/* push.js — Web Push opt-in for a saved film, only from an explicit tap («ذكّرني بالخميس»,
   owner request 2026-09-30). Never runs on page load, never auto-prompts. Not wired into any
   page's markup yet — a page that adds the button calls window.cinemaPushSubscribe() from its
   click handler. iPhone needs the site added to the home screen first (Safari's own limit). */
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
})();
