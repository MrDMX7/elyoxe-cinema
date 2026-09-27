/* compare (pages/insights.py): two films side by side, from /data/compare.json — verdict, ratings, runtime, the
   cheapest ticket in the visitor's city after their card, and the nearest times still to come. A lazy chunk:
   K is window.CINEMA. The box is [data-cmp] (its value the film already chosen, on a film page), hidden
   until this runs: with no script there is nothing half-drawn. */
var boxes = K.qa("[data-cmp]");
if (boxes.length) {
  K.getJSON("/data/compare.json").then(function (J) {
    if (!J || !J.f) return;
    boxes.forEach(function (el) { setup(el, J); });
  });
}
var W = K.AR ? {
  a: "الفيلم الأول", b: "الفيلم الثاني", pick: "اختار فيلم", verdict: "الحكم", critics: "النقاد", aud: "الجمهور", imdb: "IMDb",
  runtime: "المدة", min: "دقيقة", cheap: "أرخص تذكرة في {city}", card: "ببطاقة {card}", aed: "درهم", box: "السعر في الشباك",
  soon: "أقرب الأوقات في {city}", none: "ما في عروض باقية", today: "اليوم", tomorrow: "باكر", rating: "التصنيف"
} : {
  a: "First film", b: "Second film", pick: "Pick a film", verdict: "Verdict", critics: "Critics", aud: "Audience", imdb: "IMDb",
  runtime: "Runtime", min: "min", cheap: "Cheapest ticket in {city}", card: "with {card}", aed: "AED", box: "Price at the box office",
  soon: "Next times in {city}", none: "No shows left", today: "Today", tomorrow: "Tomorrow", rating: "Rating"
};
function title(J, id) { var f = J.f[id]; return f ? (K.AR ? f[0] : f[1]) || f[1] : ""; }
function select(J, ids, cur, label) {
  var o = '<option value="">' + K.esc(W.pick) + "</option>" + ids.map(function (id) {
    return '<option value="' + K.esc(id) + '"' + (id === cur ? " selected" : "") + ">" + K.esc(title(J, id)) + "</option>";
  }).join("");
  return "<label>" + K.esc(label) + "<select>" + o + "</select></label>";
}
function setup(el, J) {
  var ids = Object.keys(J.f).sort(function (x, y) { return title(J, x).localeCompare(title(J, y), K.lang); });
  if (ids.length < 2) return;
  var a = J.f[el.getAttribute("data-cmp")] ? el.getAttribute("data-cmp") : "";
  var b = "";
  var ui = K.q("[data-cmp-ui]", el), out = K.q("[data-cmp-out]", el);
  ui.className = "cmp-ui";
  ui.innerHTML = select(J, ids, a, W.a) + select(J, ids, b, W.b);
  var sels = [].slice.call(ui.querySelectorAll("select"));
  function draw() {
    a = sels[0].value; b = sels[1].value;
    out.innerHTML = a && b && a !== b ? table(J, [a, b]) : "";
  }
  sels.forEach(function (s) { s.addEventListener("change", draw); });
  /* the card or the city changes in the page's own controls: redraw once the core has taken the choice */
  document.addEventListener("click", function (e) { if (e.target.closest && e.target.closest("[data-card]")) setTimeout(draw, 0); });
  document.addEventListener("change", function (e) { if (e.target.matches && e.target.matches("select[data-card]")) setTimeout(draw, 0); });
  el.hidden = false;
  draw();
}
function pct(v) { return v == null ? "" : '<span class="num" dir="ltr">' + K.esc(v) + "%</span>"; }
function cheapest(J, id) {
  var city = K.city(), card = K.card(), p = (J.p[id] || {})[city];
  if (!p) return K.esc(W.box);
  var pay = card && p[1][card] != null ? p[1][card] : p[0];
  var h = '<span class="p"><span class="num">' + K.fmt(pay) + "</span></span> " + K.esc(W.aed);
  if (card && p[1][card] != null) h += " <small>" + K.esc(K.sub(W.card, { card: (K.C.cards || {})[card] || card })) + "</small>";
  return h;
}
function soon(J, id) {
  var city = K.city(), now = K.now(), list = ((J.n[id] || {})[city] || []).filter(function (x) { return K.uae(x[0] + "T" + x[1]) >= now; });
  if (!list.length) return K.esc(W.none);
  var day = function (ms) { return new Date(ms + 4 * 3600e3).toISOString().slice(0, 10); };
  var t0 = day(now.getTime()), t1 = day(now.getTime() + 864e5);
  return list.slice(0, 3).map(function (x) {
    var d = x[0] === t0 ? W.today : x[0] === t1 ? W.tomorrow : x[0];
    return '<span class="num">' + K.esc(x[1]) + "</span> <small>" + K.esc(d) + "</small>";
  }).join("<br>");
}
function table(J, pair) {
  var cityName = (K.C.cities || {})[K.city()] || K.city();
  var rows = [
    [W.verdict, function (f) { return '<span class="vw v-' + K.esc(f[2]) + '">' + K.esc((K.C.v || {})[f[2]] || "") + "</span>"; }],
    [W.critics, function (f) { return pct(f[3]); }],
    [W.aud, function (f) { return pct(f[4]); }],
    [W.imdb, function (f) { return f[5] == null ? "" : '<span class="num">' + K.esc(f[5]) + "</span>"; }],
    [W.runtime, function (f) { return f[6] ? '<span class="num">' + K.esc(f[6]) + "</span> " + K.esc(W.min) : ""; }],
    [W.rating, function (f) { return f[7] ? '<bdi class="num" dir="ltr">' + K.esc(f[7]) + "</bdi>" : ""; }],
    [K.sub(W.cheap, { city: cityName }), function (f, id) { return cheapest(J, id); }],
    [K.sub(W.soon, { city: cityName }), function (f, id) { return soon(J, id); }]
  ];
  var head = "<tr><th></th>" + pair.map(function (id) {
    return '<th scope="col"><a href="' + K.esc((K.C.base || "/") + "film/" + id + "/") + '">' + K.esc(title(J, id)) + "</a></th>";
  }).join("") + "</tr>";
  var body = rows.map(function (r) {
    var cells = pair.map(function (id) { return "<td>" + (r[1](J.f[id], id) || "") + "</td>"; });
    return '<tr><th scope="row">' + K.esc(r[0]) + "</th>" + cells.join("") + "</tr>";
  }).join("");
  return '<div class="xwrap"><table class="matrix cmp-t"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
}
