/* plan.js — Phase 2 Task 4 «Planning» (docs/superpowers/specs/2026-09-27-phase2-design.md, C.41-42),
   in the ticket (src/js/ticket.js). Main bundle, so it shares ticket.js/near.js/core.js's scope (tk, G,
   geo, LOC, haversine, uae, hhmm, TX, C, esc, q, qa, sub, feature, NOW, TODAY) — docs/PLUGINS.md.

   Double feature (C.43) and the mall-closing note (C.44) are server-rendered by pages/venue.py (the
   cinema.after_halls / film.info slots); nothing here duplicates that.

   No network write, no invented number: the .ics/calendar link only ever restates what the ticket
   already shows, and the drive time is always labelled «تقريباً» (an estimate, never a promise). */

/* ---- small local helpers (kept in this file only: pure.js is not this module's to edit) ---- */
function planNextDate(iso) {
  var d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}
/* the show's own wall-clock date+time -> the real UTC instant (UAE is UTC+4, no DST) */
function planUtc(iso, hm) {
  var y = +iso.slice(0, 4), mo = +iso.slice(5, 7), d = +iso.slice(8, 10), h = +hm.slice(0, 2), mi = +hm.slice(3, 5);
  return new Date(Date.UTC(y, mo - 1, d, h - 4, mi));
}
function planStampUtc(date) { return date.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z"; }
function planIcsEsc(s) { return String(s || "").replace(/\\/g, "\\\\").replace(/[,;]/g, "\\$&").replace(/\n/g, "\\n"); }

/* RFC 5545 §3.1 line folding: no content line over 75 OCTETS, continued by CRLF + one leading space.
   An Arabic title/cinema pair blows past 75 octets almost immediately (2 bytes/char), so this is not
   optional — folded on UTF-8 BYTES, never inside a multi-byte character (a continuation byte, top two
   bits 10xxxxxx, never starts a chunk). The leading space of a continuation line counts toward its own
   75-octet budget, so a continuation chunk is at most 74 content octets. */
function planFold(line) {
  var bytes = new TextEncoder().encode(line);
  if (bytes.length <= 75) return line;
  var dec = new TextDecoder(), out = [], start = 0, limit = 75;
  while (start < bytes.length) {
    var end = Math.min(start + limit, bytes.length);
    while (end > start && (bytes[end] & 0xC0) === 0x80) end--;   // back off a split mid-character
    out.push(dec.decode(bytes.slice(start, end)));
    start = end;
    limit = 74;
  }
  return out.join("\r\n ");
}

/* the .ics text: DTSTART/DTEND in Asia/Dubai (a fixed +04:00 offset, no VTIMEZONE ambiguity), a 60-min
   VALARM (design C.41), and a Google Maps link in the description since the client has the cinema's
   coordinates (data/cinemas.json) but never a street address. Every line is folded (planFold) before
   being joined — most stay one physical line (bytes.length <= 75 is a no-op), SUMMARY/LOCATION/
   DESCRIPTION with real Arabic content usually don't. */
function planIcs(x) {
  var endDate = x.endHm && x.endHm < x.time ? planNextDate(x.date) : x.date;
  var dtStart = x.date.replace(/-/g, "") + "T" + x.time.replace(":", "") + "00";
  var dtEnd = endDate.replace(/-/g, "") + "T" + (x.endHm || x.time).replace(":", "") + "00";
  var stamp = planStampUtc(new Date());
  var loc = x.lat != null ? "https://www.google.com/maps/search/?api=1&query=" + x.lat + "," + x.lng : "";
  var lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Elyoxe//Cinema//AR",
    "BEGIN:VTIMEZONE", "TZID:Asia/Dubai", "BEGIN:STANDARD", "DTSTART:19700101T000000",
    "TZOFFSETFROM:+0400", "TZOFFSETTO:+0400", "END:STANDARD", "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:" + (x.uid || (dtStart + "-" + Math.random().toString(36).slice(2))) + "@cinema.elyoxe.com",
    "DTSTAMP:" + stamp,
    "DTSTART;TZID=Asia/Dubai:" + dtStart, "DTEND;TZID=Asia/Dubai:" + dtEnd,
    "SUMMARY:" + planIcsEsc(x.film + " — " + x.cin),
    "LOCATION:" + planIcsEsc(x.cin),
    "DESCRIPTION:" + planIcsEsc(x.film + (loc ? "\n" + loc : "")),
    "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + planIcsEsc(x.film), "TRIGGER:-PT60M", "END:VALARM",
    "END:VEVENT", "END:VCALENDAR"
  ];
  return lines.map(planFold).join("\r\n") + "\r\n";
}

function planGCalUrl(x) {
  var s = planStampUtc(planUtc(x.date, x.time));
  var endIso = x.endHm && x.endHm < x.time ? planNextDate(x.date) : x.date;
  var e = planStampUtc(planUtc(endIso, x.endHm || x.time));
  var q0 = { action: "TEMPLATE", text: x.film + " — " + x.cin, dates: s + "/" + e, details: x.film,
    location: x.lat != null ? x.lat + "," + x.lng : x.cin };
  return "https://calendar.google.com/calendar/render?" + Object.keys(q0).map(function (k) {
    return k + "=" + encodeURIComponent(q0[k]);
  }).join("&");
}

/* «اطلع من البيت الساعة…» (C.42): road distance ≈ straight-line × 1.35 (haversine, pure.js), 60 km/h
   inside one city and 90 km/h once the straight line alone is past 30 km (a rough «that’s not local
   traffic anymore» cut — there is no per-trip road-network figure to read instead), + 10 min parking.
   Always «تقريباً»: this is an estimate, not a promise. */
function planLeaveBy(x, loc) {
  if (!loc || x.lat == null) return null;
  var km = haversine(loc.lat, loc.lng, x.lat, x.lng), road = km * 1.35;
  var speed = km > 30 ? 90 : 60, mins = Math.round(road / speed * 60) + 10;
  var t = planUtc(x.date, x.time).getTime() - mins * 60000;
  return hhmm(t);   // hhmm() itself adds the UAE +4h back onto a UTC instant
}

function planRender(box, x, loc) {
  var ics = "data:text/calendar;charset=utf-8," + encodeURIComponent(planIcs(x));
  var cal = AR ? "أضف للتقويم" : "Add to calendar", gcal = AR ? "تقويم Google" : "Google Calendar";
  var html = '<a class="lnk" download="cinema.ics" href="' + ics + '">' + esc(cal) + '</a>' +
    ' <a class="lnk" href="' + esc(planGCalUrl(x)) + '" rel="noopener" target="_blank">' + esc(gcal) + '</a>';
  var leave = planLeaveBy(x, loc);
  if (leave) {
    html += '<p class="plan-leave">' + esc(sub(AR ? "اطلع من البيت الساعة {t} تقريباً" : "Leave home around {t}, approximately", { t: leave })) + '</p>';
  } else if (x.lat != null) {
    html += '<button type="button" class="lnk" data-plan-loc>' + esc(AR ? "متى أطلع من البيت؟" : "When should I leave home?") + '</button>';
  }
  box.innerHTML = html;
}

function planFromTicket() {
  if (!tk) return null;
  var cid = tk.getAttribute("data-cin");
  if (!cid) return null;
  var film = (q("[data-tk-film]", tk) || {}).textContent || "";
  var cin = (q("[data-tk-cin]", tk) || {}).textContent || "";
  var time = (q("[data-tk-time]", tk) || {}).textContent || "";
  var dayTxt = (q("[data-tk-day]", tk) || {}).textContent || "";
  var date = dayTxt === C.today ? TODAY : dayTxt === C.tomorrow ? TOMORROW : dayTxt;
  if (!film || !time || !/^\d{4}-\d{2}-\d{2}$/.test(date || "")) return null;
  var whenEl = q("[data-tk-when]", tk), times = whenEl ? (whenEl.textContent.match(/\d\d:\d\d/g) || []) : [];
  var endHm = times.length > 1 ? times[times.length - 1] : null;
  var g = G && G[cid];
  return { film: film, cin: cin, date: date, time: time, endHm: endHm, lat: g ? g[2] : null, lng: g ? g[3] : null, uid: cid + "-" + date + "-" + time };
}

function planMount() {
  var go = q("[data-tk-go]", tk);
  var box = q("[data-plan]", tk);
  if (!box) {
    box = document.createElement("div");
    box.className = "plan-add";
    box.setAttribute("data-plan", "");
    (go || tk).insertAdjacentElement(go ? "afterend" : "beforeend", box);
  }
  return box;
}

function planRefresh() {
  var x = planFromTicket();
  if (!x) return;
  geo().then(function () {
    x = planFromTicket() || x;   // G may only just have loaded
    planRender(planMount(), x, LOC);
  });
}

feature(function () {
  if (!tk) return;
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-plan-loc]")) {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition(function (p) {
        LOC = { lat: Math.round(p.coords.latitude * 1e3) / 1e3, lng: Math.round(p.coords.longitude * 1e3) / 1e3 };
        set("loc", LOC.lat + "," + LOC.lng + "," + Date.now());
        planRefresh();
      }, function () {});
    }
  });
  if (tk.getAttribute("data-cin")) planRefresh();   // the page's own server-rendered next show, if any
  var mo = new MutationObserver(function () { planRefresh(); });
  mo.observe(tk, { attributes: true, attributeFilter: ["data-cin"] });
});
