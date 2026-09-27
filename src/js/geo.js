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
  return true;
}
function geoChange(e) {
  var b = e.target.closest && e.target.closest("[data-geo-change]");
  if (!b) return;
  var d = q("details[data-citypick]");
  if (d) { d.open = true; var s = q("summary", d); if (s) s.focus(); }
}
feature(function () {
  document.addEventListener("click", geoChange);
  if (!geoWanted()) return;
  fetch("/geo", { credentials: "omit", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && "city" in j) geoApply(j); })
    .catch(function () {});
});
