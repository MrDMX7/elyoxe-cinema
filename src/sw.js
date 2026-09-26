/* «سينما» service worker (build.py writes it to /sw.js; __V__ = the build's source hash).
   Pages: network first, the cached copy when offline, else /offline.html.
   /assets and /posters: cache first (their names or ?v= change when they do).
   /data: stale-while-revalidate, a cached slice served for at most 10 minutes. */
var V = "__V__", PAGES = "cinema-pages-" + V, STATIC = "cinema-static-" + V, DATA = "cinema-data", DATA_MAX = 10 * 60e3;

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(PAGES).then(function (c) { return c.addAll(["/offline.html"]); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== PAGES && k !== STATIC && k !== DATA; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function put(name, req, res) { if (res && res.ok && res.type === "basic") { var c = res.clone(); caches.open(name).then(function (ca) { ca.put(req, c); }); } return res; }

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
          if (res.ok) { var h = new Headers(res.headers); h.set("x-sw-at", String(Date.now()));
            return res.clone().blob().then(function (b) { c.put(r, new Response(b, { status: res.status, headers: h })); return res; }); }
          return res;
        });
        var fresh = m && Date.now() - (+m.headers.get("x-sw-at") || 0) < DATA_MAX;
        if (fresh) { e.waitUntil(net.catch(function () {})); return m; }
        return net.catch(function () { return m || Response.error(); });
      });
    }));
  }
});
