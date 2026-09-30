/* «سينما» service worker (build.py writes it to /sw.js; __V__ = the build's source hash).
   Pages: network first, the cached copy when offline, else /offline.html.
   /assets and /posters: cache first (their names or ?v= change when they do).
   /data: stale-while-revalidate, a cached slice served for at most 10 minutes.
   Every cache is capped (oldest entries go first); only plain same-origin 200s are kept — never a redirect,
   an opaque or an error response (a redirected response cannot answer a navigation). */
var V = "__V__", PAGES = "cinema-pages-" + V, STATIC = "cinema-static-" + V, DATA = "cinema-data", DATA_MAX = 10 * 60e3;
var CAP = {}; CAP[PAGES] = 60; CAP[STATIC] = 150; CAP[DATA] = 24;
function ok(res) { return res && res.ok && res.status === 200 && res.type === "basic" && !res.redirected; }
function trim(name) {
  return caches.open(name).then(function (c) {
    return c.keys().then(function (ks) { return Promise.all(ks.slice(0, Math.max(0, ks.length - CAP[name])).map(function (k) { return c.delete(k); })); });
  });
}

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(PAGES).then(function (c) { return c.addAll(["/offline.html"]); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== PAGES && k !== STATIC && k !== DATA; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function put(name, req, res) {
  if (ok(res)) { var c = res.clone(); caches.open(name).then(function (ca) { return ca.delete(req).then(function () { return ca.put(req, c); }); }).then(function () { return trim(name); }); }
  return res;
}

self.addEventListener("fetch", function (e) {
  var r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin) return;
  if (r.mode === "navigate" || (r.headers.get("accept") || "").indexOf("text/html") >= 0) {
    e.respondWith(fetch(r).then(function (res) { return put(PAGES, r, res); }).catch(function () {
      return caches.match(r).then(function (m) { return m || caches.match("/offline.html"); });
    }));
    return;
  }
  if (u.pathname.indexOf("/assets/") === 0 || u.pathname.indexOf("/posters/") === 0) {
    e.respondWith(caches.match(r).then(function (m) { return m || fetch(r).then(function (res) { return put(STATIC, r, res); }); }));
    return;
  }
  if (u.pathname.indexOf("/data/") === 0) {
    e.respondWith(caches.open(DATA).then(function (c) {
      return c.match(r).then(function (m) {
        var net = fetch(r).then(function (res) {
          if (ok(res)) { var h = new Headers(res.headers); h.set("x-sw-at", String(Date.now()));
            return res.clone().blob().then(function (b) { return c.delete(r).then(function () { return c.put(r, new Response(b, { status: 200, headers: h })); }).then(function () { trim(DATA); return res; }); }); }
          return res;
        });
        var fresh = m && Date.now() - (+m.headers.get("x-sw-at") || 0) < DATA_MAX;
        if (fresh) { e.waitUntil(net.catch(function () {})); return m; }
        return net.catch(function () { return m || Response.error(); });
      });
    }));
  }
});

/* Web Push (review r3-backend, Important #2): without these two handlers Chrome falls back to a
   generic "site updated in background" notification, and iOS Safari revokes a subscription that
   receives pushes with no notification shown — so both handlers are required, not cosmetic.
   Payload comes from push_weekly.py's build_payload(): {title, body, url}. */
self.addEventListener("push", function (e) {
  var data = { title: "سينما", body: "أفلام جديدة هالخميس", url: "https://cinema.elyoxe.com/coming/" };
  try { if (e.data) data = Object.assign(data, e.data.json()); } catch (err) {}
  e.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    icon: "/assets/icon-192.png",
    badge: "/assets/badge-72.png",
    data: { url: data.url },
    tag: "cinema-weekly"
  }));
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || "https://cinema.elyoxe.com/coming/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].url === url && "focus" in list[i]) return list[i].focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  }));
});
