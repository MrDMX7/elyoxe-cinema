"""src/sw.js (2026-10-17): pages and older data slices race the network against RACE ms. Run in Node with a fake
`caches` and `fetch` (RACE shortened to 60 ms): a slow network with a cached copy answers from the cache in time; a
slow network with none still waits for the network (never a guessed /offline.html); a dead network falls back to
the copy, else /offline.html; a fast network always wins."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")

HARNESS = r"""
var H = {}, STORE = {};
global.self = { addEventListener: function (t, f) { H[t] = f; }, skipWaiting: function () {}, clients: { claim: function () {} },
                registration: { showNotification: function () {} } };
global.location = { origin: "https://x" };
function key(r) { return typeof r === "string" ? (r.indexOf("http") ? "https://x" + r : r) : r.url; }
function cacheObj() { return { match: function (r) { return Promise.resolve(STORE[key(r)]); }, put: function (r, v) { STORE[key(r)] = v; return Promise.resolve(); },
  delete: function (r) { delete STORE[key(r)]; return Promise.resolve(true); }, keys: function () { return Promise.resolve([]); },
  addAll: function () { return Promise.resolve(); } }; }
global.caches = { match: function (r) { return Promise.resolve(STORE[key(r)] ? STORE[key(r)].clone() : undefined); },
                  open: function () { return Promise.resolve(cacheObj()); }, keys: function () { return Promise.resolve([]); }, delete: function () { return Promise.resolve(true); } };
var NET = { ms: 0, fail: false, body: "net" };
global.fetch = function () {
  return new Promise(function (ok, no) { setTimeout(function () { if (NET.fail) no(new TypeError("offline")); else ok(new Response(NET.body, { status: 200 })); }, NET.ms); });
};
SW_SOURCE
function ask(url, html) {
  var resp = null, t0 = Date.now();
  var e = { request: { method: "GET", url: "https://x" + url, mode: html ? "navigate" : "cors", headers: new Headers({ accept: html ? "text/html" : "*/*" }) },
            respondWith: function (p) { resp = p; }, waitUntil: function () {} };
  H.fetch(e);
  return Promise.resolve(resp).then(function (r) { return r.text(); }).then(function (b) { return { body: b, ms: Date.now() - t0 }; });
}
(async function () {
  var out = {};
  STORE["https://x/offline.html"] = new Response("offline");
  STORE["https://x/film/a/"] = new Response("cached");
  NET = { ms: 400, fail: false, body: "net" }; out.slowCached = await ask("/film/a/", true);
  NET = { ms: 10, fail: false, body: "net" }; out.fastCached = await ask("/film/a/", true);
  NET = { ms: 200, fail: false, body: "net" }; out.slowNone = await ask("/film/b/", true);
  NET = { ms: 10, fail: true }; out.deadNone = await ask("/film/c/", true);
  STORE["https://x/film/a/"] = new Response("cached");
  NET = { ms: 10, fail: true }; out.deadCached = await ask("/film/a/", true);
  var h = new Headers(); h.set("x-sw-at", "1");
  STORE["https://x/data/dubai-2026-10-17.json"] = new Response("old-slice", { status: 200, headers: h });
  NET = { ms: 400, fail: false, body: "new-slice" }; out.slowOldData = await ask("/data/dubai-2026-10-17.json", false);
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_pages_and_old_slices_race_the_network():
    sw = open(os.path.join(ROOT, "src", "sw.js"), encoding="utf-8").read()
    assert "var RACE = 3000;" in sw
    script = HARNESS.replace("SW_SOURCE", sw.replace("var RACE = 3000;", "var RACE = 60;"))
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["slowCached"]["body"] == "cached" and o["slowCached"]["ms"] < 300          # the copy, well before the network
    assert o["fastCached"]["body"] == "net"                                             # a fast network always wins
    assert o["slowNone"]["body"] == "net" and o["slowNone"]["ms"] >= 150                # no copy: wait, never guess offline
    assert o["deadNone"]["body"] == "offline"                                           # a dead network, no copy
    assert o["deadCached"]["body"] == "cached"                                          # a dead network, a copy
    assert o["slowOldData"]["body"] == "old-slice" and o["slowOldData"]["ms"] < 300     # an older slice, same race
