/* «سينما» client — core. build.py concatenates src/js/*.js (JS_MODULES order) into one function scope,
   so every module shares these helpers without globals. No framework.
   ?now=2026-09-25T19:00 pretends it is that UAE time (the clock still moves on from there). */
var C = window.CT || {}, lang = document.documentElement.lang === "en" ? "en" : "ar", AR = lang === "ar";
var body = document.body, page = body.getAttribute("data-page"), pageCity = body.getAttribute("data-city");
var D = null, S = null, G = null;   // discounts.json, the city's slices, cinemas.json (coordinates)
var RM = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

function get(k) { try { return window.localStorage.getItem("cinema." + k); } catch (e) { return null; } }
function set(k, v) { try { if (v === "" || v == null) window.localStorage.removeItem("cinema." + k); else window.localStorage.setItem("cinema." + k, v); } catch (e) {} }
function qa(s, r) { return [].slice.call((r || document).querySelectorAll(s)); }
function q(s, r) { return (r || document).querySelector(s); }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
function sub(s, o) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); }
function uae(s) { return new Date(s.length <= 16 ? s + ":00+04:00" : s); }
function day(d) { return new Date(d.getTime() + 4 * 3600e3).toISOString().slice(0, 10); }
function hhmm(ms) { return new Date(ms + 4 * 3600e3).toISOString().slice(11, 16); }
function nm(o) { return o ? (AR ? o.ar : o.en) : ""; }
/* a malformed value («?city=%») is no value: never an exception at start-up (fix round 1, I3's sibling) */
function param(k) { var m = new RegExp("[?&]" + k + "=([^&]+)").exec(location.search); try { return m ? decodeURIComponent(m[1]) : null; } catch (e) { return null; } }
var JC = {};
function getJSON(u) { return JC[u] || (JC[u] = fetch(u).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })); }
function desk() { return !!(window.matchMedia && window.matchMedia("(min-width: 1024px)").matches); }

/* the clock: UAE time, moving; ?now= shifts it. Every timer reads it (NOW, nowMin, TODAY), never the device's own
   hours: a visitor whose phone is set to another zone still sees Dubai's clock (tests/test_js.py runs this file under
   TZ=America/New_York, W1-P1) */
var FAKE = (function () { var v = param("now"), d = v && uae(v); return d && !isNaN(d) ? d.getTime() - Date.now() : 0; })();
var NOW, TODAY, TOMORROW;
function tick() { NOW = new Date(Date.now() + FAKE); TODAY = day(NOW); TOMORROW = day(new Date(NOW.getTime() + 864e5)); }
tick();
function nowMin() { var s = hhmm(NOW.getTime()); return +s.slice(0, 2) * 60 + +s.slice(3); }

/* the hook bus (W1-P1, MASTER-PLAN §5.2): a module listens with on(ev, fn); main.js says what happened with emit(ev, x):
   «ready» (start-up done), «slice» (the city's shows arrived; x = S), «card» (x = the card id, "" for none), «city»
   (x = the city), «day» (x = the chosen date), «minute» (x = NOW, at each UAE minute's :00). A handler that throws never
   stops the others. Wave 2 packages emit their own events the same way (board, stub, plan). */
var HOOKS = {};
function on(ev, fn) { (HOOKS[ev] = HOOKS[ev] || []).push(fn); }
function emit(ev, x) {
  (HOOKS[ev] || []).slice().forEach(function (fn) { try { fn(x); } catch (e) { if (window.console) console.error(e); } });
}

/* the show link (MASTER-PLAN §2.2): /film/<fid>/#s-<key>. key = FNV-1a 32-bit over the UTF-8 of «cinema|date|time|hall
   key», base36, left-padded to 6 characters; stable across the hourly builds because every input is. A fragment, never
   ?s=: no crawlable URLs, one service-worker entry per film page, prerender stays eligible. Its Python twin is
   site_kit.Kit.show_key (tests/test_showkey.py holds them equal over every show). Moved here from ticket.js by W1-P1. */
function showKey(cin, d, t, hk) {
  var s = unescape(encodeURIComponent([cin, d, t, hk || "Standard"].join("|"))), h = 0x811c9dc5;
  for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  var k = h.toString(36);
  return k.length < 6 ? ("00000" + k).slice(-6) : k;
}

/* state: the visitor's choices, remembered (localStorage may be off: every read has a default) */
/* ?city=&card= from a shared link (src/js/share.js, hoisted: applied here when there is nothing saved
   yet or it already agrees; a differing saved value is never silently overwritten -- share.js asks) */
shareParams();
var city = pageCity || get("city") || "dubai", card = get("card") || "";
if (C.cities && !C.cities[city]) city = "dubai";
if (C.cards && card && !C.cards[card]) card = "";
if (pageCity) set("city", pageCity);
var ST = { who: get("who") || "", filt: get("filt") || "all", before: get("before") || "", sort: get("sort") || "",
  prayer: get("prayer") === "1", hide: get("hide") === "1", flang: get("flang") || "" };
function save(k, v) { ST[k] = v; set(k, v === true ? "1" : v === false ? "" : v); }
var LOC = (function () {
  var v = get("loc"), m = v && /^(-?[\d.]+),(-?[\d.]+),(\d+)$/.exec(v);
  if (!m || Date.now() - +m[3] > 30 * 864e5) { if (v) set("loc", ""); return null; }
  return { lat: +m[1], lng: +m[2] };
})();

/* strings the pages do not carry (window.CT holds the shared ones) */
var TX = AR ? {
  starts: "الفيلم يبدأ تقريباً {s} ويخلص تقريباً {e}", at: "يبدأ الساعة {s}", subs: "ترجمة {s}", sep: "، ",
  near_ask: "نشوف وين أقرب سينما…", near_no: "ما قدرنا نعرف موقعك. عادي، اختار مدينتك من فوق.",
  near_pick: "أقرب سينما لك {cin}، على بعد {km}، فاخترنا لك {city}.", near_same: "أقرب سينما لك {cin}، على بعد {km}.",
  near_here: "تبعد عنك {km}.",
  empty: "ما في شي يطابق. خفّف التصفية شوي", reset: "شيل التصفية", forget: "انسَ موقعي",
  clash: "يتقاطع مع {p}", maghrib: "المغرب", isha: "العشاء", ptimes: "المغرب {m}، العشاء {i}",
  ticket: "التذكرة: {film}، {cin}، {t}", close: "سكّر", trailer: "العرض الترويجي",
  install: "ثبّت سينما على شاشتك", install_yes: "ثبّت", install_no: "لا، شكراً", share_t: "{film} في {cin}، {day} {t}",
  top: "الأكثر عرضاً الليلة", top_in: "الأكثر عرضاً في {city} الليلة", from: "من", next: "أقرب عرض {t}، {cin}",
  sort0: "الأكثر عرضاً", times: "الأوقات والأسعار", bill_tr: "الإعلان", show: "اعرض {n}", n_live: "{n} بعد التصفية",
  map: "الخريطة", more_cin: "{n} ثانية في {city}", soon: "يبدأ بعد {n} د", soon0: "يبدأ الحين", after_c: "بعد {card}", more: "المزيد", less: "أقل"
} : {
  starts: "The film starts around {s} and ends around {e}", at: "Starts at {s}", subs: "{s} subtitles", sep: ", ",
  near_ask: "Finding the nearest cinema…", near_no: "We couldn’t get your location. No problem, pick your city above.",
  near_pick: "Nearest to you: {cin}, {km} away, so we picked {city}.", near_same: "Nearest to you: {cin}, {km} away.",
  near_here: "{km} from you.",
  empty: "Nothing matches. Loosen the filters a little.", reset: "Clear filters", forget: "Forget my location",
  clash: "Overlaps {p}", maghrib: "Maghrib", isha: "Isha", ptimes: "Maghrib {m}, Isha {i}",
  ticket: "Ticket: {film}, {cin}, {t}", close: "Close", trailer: "Trailer",
  install: "Add Cinema to your home screen", install_yes: "Add", install_no: "No, thanks", share_t: "{film} at {cin}, {day} {t}",
  top: "Most shown tonight", top_in: "Most shown in {city} tonight", from: "from", next: "Next {t}, {cin}",
  sort0: "Most shown", times: "Times and prices", bill_tr: "Trailer", show: "Show {n}", n_live: "{n} after filtering",
  map: "Map", more_cin: "{n} in {city}", soon: "in {n} min", soon0: "starting now", after_c: "after {card}", more: "More", less: "Less"
};

/* features (docs/PLUGINS.md): a module in this bundle (pages/<feature>.py JS) calls feature(fn), and fn runs at
   start-up after the core has bound the page; one that throws never stops the others. A lazy chunk
   (LAZY_JS, /assets/<feature>.<hash>.js, listed in CT.chunks on the pages that ask for it) runs in its own
   scope with the helpers below as K = window.CINEMA. */
var FEAT = [];
function feature(fn) { FEAT.push(fn); }
function startFeatures() {
  FEAT.forEach(function (fn) { try { fn(); } catch (e) { if (window.console) console.error(e); } });
  window.CINEMA = { C: C, lang: lang, AR: AR, page: page, q: q, qa: qa, esc: esc, fmt: fmt, sub: sub, uae: uae, getJSON: getJSON,
    get: get, set: set, now: function () { return NOW; }, city: function () { return city; }, card: function () { return card; },
    on: on, emit: emit, showKey: showKey };
  Object.keys(C.chunks || {}).forEach(function (n) {
    var s = document.createElement("script"); s.src = C.chunks[n]; s.async = true; document.head.appendChild(s);
  });
}
