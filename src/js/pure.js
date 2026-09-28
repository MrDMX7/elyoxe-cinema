/* pure: no page, no state — every function here takes what it needs and returns a value.
   tests/test_js.py runs this file in node as it is. */

/* Arabic counted nouns: 1 دقيقة · 2 دقيقتين · 3–10 دقايق · 11+ دقيقة (the singular again) */
function arCount(n, w) { return n === 1 ? w[0] : n === 2 ? w[1] : n >= 3 && n <= 10 ? n + " " + w[2] : n + " " + w[3]; }
function inMinutes(n, lg) {
  if (n <= 0) return lg === "en" ? "starting now" : "يبدأ الحين";
  if (lg === "en") return "in " + n + " min";
  return "بعد " + arCount(n, ["دقيقة", "دقيقتين", "دقايق", "دقيقة"]);
}
function seatsLeft(n, lg) {
  if (lg === "en") return n + (n === 1 ? " seat left" : " seats left");
  return "باقي " + arCount(n, ["مقعد واحد", "مقعدين", "مقاعد", "مقعد"]);
}

/* a price as the site prints it: «42» for whole dirhams, «33.60» only when a card makes the fils real. Rounded to the
   fils half up (Math.round); site_kit.money() is its twin (tests/test_w1_p2.py holds them equal, MASTER-PLAN §1.4) */
function fmt(n) { var k = Math.round(n * 100); return k % 100 ? (k / 100).toFixed(2) : String(k / 100); }

/* great-circle distance in km */
function haversine(lat1, lng1, lat2, lng2) {
  var r = Math.PI / 180, a = Math.sin((lat2 - lat1) * r / 2), b = Math.sin((lng2 - lng1) * r / 2);
  var h = a * a + Math.cos(lat1 * r) * Math.cos(lat2 * r) * b * b;
  return 12742 * Math.asin(Math.min(1, Math.sqrt(h)));
}
function kmText(km, lg) {
  var v = km < 10 ? (Math.round(km * 10) / 10).toFixed(1) : String(Math.round(km));
  return v + (lg === "en" ? " km" : " كم");
}

/* times as minutes after the show date's midnight. One convention everywhere (the data's, marks(), the
   ticket, prayer times): a show's date is its calendar date — a 00:30 show dated the 27th starts in the
   first minutes of the 27th. An end before the start is past midnight (+24 h). */
function toMin(t) { var m = /^(\d\d):(\d\d)$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : null; }
function showSpan(start, ends, runtime) {
  var s = toMin(start), e = toMin(ends);
  if (s == null) return null;
  if (e == null) e = s + (runtime ? +runtime + 15 : 150);
  else { while (e < s) e += 1440; }
  return [s, e];
}
/* «يخلص قبل»: "" = any time, "24:00" = midnight */
function endsOk(span, before) { var b = toMin(before); return b == null || !span || span[1] <= b; }
/* ربعي's late shows: from 21:00, and the small hours (before 06:00) count as late too */
function lateOk(span, late) { return !late || !span || span[0] >= 21 * 60 || span[0] < 6 * 60; }
/* a show overlaps a prayer when the prayer falls inside it, or the show starts in the prayer's first
   `win` minutes (the time it takes to pray in congregation) */
function overlaps(span, p, win) { return !!span && p != null && span[0] < p + (win || 0) && span[1] > p; }

/* film filters: all · family · kids · yes (the verdict) · genre:<key> */
function filmOk(f, filt) {
  if (!filt || filt === "all") return true;
  if (filt === "family") return !!f.family;
  if (filt === "kids") return !!f.kids;
  if (filt === "yes") return f.v === "yes";   /* «يستاهل» (home's filter sheet) */
  if (filt.indexOf("genre:") === 0) return (f.genres || []).indexOf(filt.slice(6)) >= 0;
  return true;
}
/* the language filter (home's filter sheet): "" = any; else the film's own language, as the data spells it */
function langOk(lg, want) { return !want || lg === want; }
/* «23 فيلم», «فيلمين», «5 أفلام» / "23 films" — as site_kit.films_n */
function filmsN(n, lg) {
  if (lg === "en") return n + (n === 1 ? " film" : " films");
  return arCount(n, ["فيلم واحد", "فيلمين", "أفلام", "فيلم"]);
}
/* a remembered filter applies only where the page offers it (each page has its own genre chips):
   anything else reads as «الكل» there, and stays remembered for the pages that have it */
function effectiveFilter(filt, offered) { return filt && offered.indexOf(filt) >= 0 ? filt : "all"; }
/* «مع منو رايح؟»: each companion is a preset over the same controls */
function whoPreset(who) {
  return who === "family" ? { filt: "family", before: "", late: false, sort: "time" }
    : who === "kids" ? { filt: "kids", before: "21:00", late: false, sort: "time" }
    : who === "friends" ? { filt: "all", before: "", late: true, sort: "time" }
    : { filt: "all", before: "", late: false, sort: "" };
}
function verdictRank(v) { return { yes: 0, mixed: 1, unknown: 2, skip: 3 }[v] != null ? { yes: 0, mixed: 1, unknown: 2, skip: 3 }[v] : 2; }

/* «الحين»: among shows [{at: start ms, km: distance or null}], the one starting within `win` minutes of
   now — the nearest cinema first when distances are known, else the soonest */
function pickNow(shows, now, win) {
  var end = now + win * 60e3;
  var c = shows.filter(function (s) { return s.at >= now && s.at <= end; });
  c.sort(function (a, b) {
    var da = a.km == null ? 1e9 : a.km, db = b.km == null ? 1e9 : b.km;
    return da - db || a.at - b.at;
  });
  return c[0] || null;
}
