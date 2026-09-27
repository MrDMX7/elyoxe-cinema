/* City from the network (roadmap 237): on a visitor's first home or film page, with no city saved, no city page
   and no ?city=, ask the same-origin /geo once (CloudFront's own guess from the address; nothing sent, nothing
   logged), pick the city it names and say so quietly, with a way to change it. A saved city always wins, even
   one picked while the answer was on its way; a failed or empty answer changes nothing. `cinema.geo` remembers
   that the question was answered, so it is never asked again. */
var GEO_TX = AR ? { pick: "اخترنا {city} حسب شبكتك — ", change: "غيّرها" }
  : { pick: "We picked {city} from your network — ", change: "change it" };
function geoWanted() {
  return (page === "home" || page === "film") && !pageCity && !param("city") && !get("city") && !get("geo") &&
    !!C.cities && typeof fetch === "function";
}
function geoApply(j) {
  set("geo", "1");
  var c = j && j.city;
  if (!c || !C.cities[c] || get("city")) return false;
  pickCity(c);
  qa("[data-near-msg]").forEach(function (el) {
    el.textContent = sub(GEO_TX.pick, { city: C.cities[c] });
    el.insertAdjacentHTML("beforeend", '<button type="button" class="lnk" data-geo-change>' + esc(GEO_TX.change) + "</button>");
  });
  geoNote(c);
  return true;
}
/* the same words as one line under the header (the city sheet's line is out of sight until the sheet opens): said
   once, where the city was picked, and gone with ×, with «غيّرها», or with any city the visitor chooses (fix round 1, M9) */
function geoNote(c) {
  if (q("[data-geo-note]")) return;
  var n = document.createElement("div");
  n.className = "gnote"; n.setAttribute("data-geo-note", ""); n.setAttribute("role", "status");
  n.innerHTML = "<p>" + esc(sub(GEO_TX.pick, { city: C.cities[c] })) + '<button type="button" class="lnk" data-geo-change>' + esc(GEO_TX.change) + "</button></p>" +
    '<button type="button" class="gnote-x" data-geo-x aria-label="' + esc(TX.close) + '"></button>';
  var top = q(".top");
  if (top && top.parentNode) top.parentNode.insertBefore(n, top.nextSibling); else body.insertBefore(n, body.firstChild);
}
function geoNoteGone() { var n = q("[data-geo-note]"); if (n) n.parentNode.removeChild(n); }
function geoChange(e) {
  if (e.target.closest && e.target.closest("[data-geo-x], #sheet-city a[data-city], #sheet-city [data-near]")) { geoNoteGone(); return; }
  var b = e.target.closest && e.target.closest("[data-geo-change]");
  if (!b) return;
  sheetOpen("sheet-city", b.closest("[data-geo-note]") ? q("#pill-city") || b : b);
  geoNoteGone();
}
feature(function () {
  document.addEventListener("click", geoChange);
  if (!geoWanted()) return;
  /* a prerendered page (speculation rules) asks only once the visitor actually opens it */
  if (document.prerendering) document.addEventListener("prerenderingchange", geoAsk, { once: true });
  else geoAsk();
});
function geoAsk() {
  if (!geoWanted()) return;
  fetch("/geo", { credentials: "omit", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && "city" in j) geoApply(j); })
    .catch(function () {});
}
