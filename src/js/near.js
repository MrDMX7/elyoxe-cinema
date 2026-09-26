/* «أقرب سينما لي»: the location is asked for only when the button is tapped, kept (rounded to 0.001°,
   about 110 m) for at most 30 days so the next page already knows it, never asked for again on its own,
   never sent anywhere, and forgotten with «انسَ موقعي». Distances come from
   /data/cinemas.json {cid: [city, chain, lat, lng, ar, en]}. */
function geo() { return getJSON("/data/cinemas.json").then(function (j) { G = j || {}; return G; }); }
function kmTo(cid) { var c = G && G[cid]; return c && LOC ? haversine(LOC.lat, LOC.lng, c[2], c[3]) : null; }
function nearMsg(t) {
  qa("[data-near-msg]").forEach(function (el) {
    el.textContent = t || "";
    if (t && LOC) el.insertAdjacentHTML("beforeend", ' <button type="button" class="lnk" data-forget>' + esc(TX.forget) + "</button>");
  });
}
function forgetLoc() { LOC = null; set("loc", ""); nearMsg(""); qa("[data-dist]").forEach(function (e) { e.textContent = ""; }); if (S) renderNow(); }

function sortByKm(els) {
  if (els.length < 2) return;
  var par = els[0].parentNode;
  els.slice().sort(function (a, b) { return (kmTo(a.getAttribute("data-cin")) || 1e9) - (kmTo(b.getAttribute("data-cin")) || 1e9); })
    .forEach(function (el) { par.appendChild(el); });
}
function showDistances() {
  if (!LOC || !G) return;
  qa("[data-cin]").forEach(function (el) {
    var d = q("[data-dist]", el), km = kmTo(el.getAttribute("data-cin"));
    if (d && km != null && el.contains(d) && d.closest("[data-cin]") === el) d.textContent = kmText(km, lang);
  });
  if (page === "cinema") {
    var km = kmTo(body.getAttribute("data-cin")), m = q(".head .meta");
    if (km != null && m && !q("[data-dist]", m)) m.insertAdjacentHTML("afterbegin", '<span data-dist>' + esc(sub(TX.near_here, { km: kmText(km, lang) })) + "</span>");
  }
  sortByKm(qa(".rows > .row.cin"));
  qa(".fcity").forEach(function (sec) { sortByKm(qa(":scope > .cg", sec)); });
  qa(".srow .sc").forEach(function (sc) { sortByKm(qa(":scope > .scin", sc)); });
}
function nearest() {
  var b = null;
  Object.keys(G || {}).forEach(function (cid) { var km = kmTo(cid); if (km != null && (!b || km < b.km)) b = { cid: cid, km: km, city: G[cid][0] }; });
  return b;
}
function applyNear(fromTap) {
  return geo().then(function () {
    showDistances();
    if (S) renderNow();
    if (!fromTap && LOC) qa("[data-near-msg]").forEach(function (el) { if (!el.firstChild) el.innerHTML = '<button type="button" class="lnk" data-forget>' + esc(TX.forget) + "</button>"; });
    var n = nearest();
    if (!n || !fromTap) return;
    var cin = AR ? G[n.cid][4] : G[n.cid][5], km = kmText(n.km, lang), cn = C.cities[n.city] || n.city;
    var same = n.city === city;
    if (page === "cinema") { nearMsg(sub(TX.near_same, { cin: cin, km: km })); return; }
    if (!same && C.cities[n.city]) {
      var msg = sub(TX.near_pick, { cin: cin, km: km, city: cn });
      city = n.city; set("city", city);
      if (page === "city") { set("nearnote", msg); location.href = C.base + n.city + "/"; return; }
      nearMsg(msg);
      pickCity(city);
      return;
    }
    nearMsg(sub(TX.near_same, { cin: cin, km: km }));
  });
}
function askNear() {
  if (!navigator.geolocation) { nearMsg(TX.near_no); return; }
  nearMsg(TX.near_ask);
  navigator.geolocation.getCurrentPosition(function (p) {
    LOC = { lat: Math.round(p.coords.latitude * 1e3) / 1e3, lng: Math.round(p.coords.longitude * 1e3) / 1e3 };
    set("loc", LOC.lat + "," + LOC.lng + "," + Date.now());
    applyNear(true);
  }, function () { nearMsg(TX.near_no); }, { timeout: 12000, maximumAge: 6e5 });
}
