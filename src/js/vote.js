/* vote.js — /v/ «أي واحد؟» (W3-P4, MASTER-PLAN §2.12), a lazy chunk (K = window.CINEMA), its own scope.
   No backend: the choice travels in the link itself, #<city>.<date>.<showkey>.<fid>+... (2-4 of them), each
   key naming one city-day slice -- the same /data/<city>-<date>.json files home and city pages already
   publish -- so a first-time visit from WhatsApp fetches only the slices its own keys name, never the
   visitor's own saved city or card (those never travel in this link at all). The city in the key is the
   SHOW's own cinema city (needed to find its data slice at all, since data is partitioned by city), never
   the sender's saved/home city -- the plan's "no city" acceptance line is about the visitor's own state,
   not the film's screening location (review Minor: flagged for the owner to confirm this reading).
   "أنا مع هذا" opens WhatsApp with that option's own time as the reply key, no numbering: the chat itself
   is the ballot box. */
(function () {
  var tray = K.q("[data-v-tray]"), empty = K.q("[data-v-empty]");
  if (!tray) return;
  var raw = location.hash.slice(1);
  var keys = [];
  try { raw = decodeURIComponent(raw); } catch (e) {}
  raw.split("+").forEach(function (s) {
    var p = s.split(".");
    if (p.length === 4 && p[0] && p[1] && p[2] && p[3]) keys.push({ city: p[0], date: p[1], key: p[2], fid: p[3] });
  });
  if (keys.length < 2 || keys.length > 4) { if (empty) empty.hidden = false; return; }

  function resolve(k, j) {
    if (!j || !j.S || !j.C || !j.F || !j.H) return null;
    var fi = -1;
    for (var x = 0; x < j.F.length; x++) if (j.F[x][0] === k.fid) { fi = x; break; }
    if (fi < 0) return null;
    for (var i = 0; i < j.S.length; i++) {
      var s = j.S[i];
      if (s[1] !== fi) continue;
      var cin = j.C[s[0]], hall = j.H[s[3]];
      var hk = (hall[1] && hall[1].split("|")[1]) || "Standard";
      if (K.showKey(cin[0], k.date, s[2], hk) !== k.key) continue;
      var price = s[4] >= 0 && j.P[s[4]] && j.P[s[4]][0] ? j.P[s[4]][0][1] : null;
      return { fid: k.fid, title: K.AR ? j.F[fi][1] : j.F[fi][2], cin: K.AR ? cin[2] : cin[3],
        date: k.date, time: s[2], price: price, key: k.key };
    }
    return null;
  }

  var W = K.AR ? {
    ask: "وين نروح؟", empty: "ما لقينا أي عرض من هذا الرابط. اطلب رابط جديد.", past: "فات",
    join: "أنا مع هذا", from: "من {p} درهم", ask_group: "اسأل القروب"
  } : {
    ask: "Where to?", empty: "None of these shows were found. Ask for a new link.", past: "Started",
    join: "I'm in", from: "From {p} AED", ask_group: "Ask the group"
  };

  function dubaiDay(d) { return new Date(d.getTime() + 4 * 3600e3).toISOString().slice(0, 10); }   // core.js's day(), inlined:
    // comparing raw UTC ISO dates put every show after 20:00 Dubai time (= 00:00 UTC next day) a day off
  function waLine(o) {
    var same = o.date === dubaiDay(K.now());
    var when = same ? o.time : (o.time + " " + o.date);
    return (K.AR ? "أنا مع " : "I'm in for ") + when + (K.AR ? " " : " ") + o.title + (K.AR ? "، " : ", ") + o.cin;
  }

  function draw(opts) {
    var now = K.now().getTime();
    tray.innerHTML = opts.map(function (o) {
      var started = Date.parse(o.date + "T" + o.time + ":00+04:00") <= now;
      var price = o.price != null ? ' <span class="v-p">' + K.sub(W.from, { p: K.fmt(o.price) }) + '</span>' : "";
      var line = K.esc(waLine(o));
      var join = started ? "" :
        '<a class="btn velvet v-join" target="_blank" rel="noopener" href="https://wa.me/?text=' + encodeURIComponent(line) + '">' + K.esc(W.join) + "</a>";
      return '<li class="v-opt' + (started ? " v-past" : "") + '"><p class="v-t">' + K.esc(o.title) + "</p>"
        + '<p class="v-m">' + K.esc(o.time) + (K.AR ? "، " : ", ") + K.esc(o.cin) + price + "</p>"
        + (started ? '<span class="v-done">' + K.esc(W.past) + "</span>" : join) + "</li>";
    }).join("");
    tray.hidden = false;
    if (K.get("prayer") === "1" && K.C.adhan) {
      var sc = document.createElement("script"); sc.src = K.C.adhan; sc.async = true; document.head.appendChild(sc);
    }
  }

  var cities = {};
  keys.forEach(function (k) { (cities[k.city] = cities[k.city] || {})[k.date] = true; });
  var loads = [];
  Object.keys(cities).forEach(function (c) {
    Object.keys(cities[c]).forEach(function (d) {
      loads.push(K.getJSON("/data/" + c + "-" + d + ".json").then(function (j) { return { c: c, d: d, j: j }; }));
    });
  });
  Promise.all(loads).then(function (slices) {
    var by = {};
    slices.forEach(function (s) { by[s.c + "|" + s.d] = s.j; });
    var opts = keys.map(function (k) { return resolve(k, by[k.city + "|" + k.date]); }).filter(Boolean);
    if (opts.length < 2) { if (empty) { empty.textContent = W.empty; empty.hidden = false; } return; }
    draw(opts);
  });
})();
