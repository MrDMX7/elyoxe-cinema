/* seatmap: a lazy chunk (pages/seats.py). «باقي N مقعد» under a time while its sample is under 90 minutes old
   (/data/occupancy.json), and in the ticket the hall drawn from the chain's own seat map with the best seat
   (/data/seats/<cinema>.json). Drawn screen on top whatever end the chain draws it on; aisles keep their width.
   Colour is never the only signal: the caption says the same in words. */
var FRESH_S = 90 * 60, OCC = null;
/* «باقي N مقعد» is scarcity, not a seat counter (R4 §300): a healthy hall (> 15 free) says nothing, on a time
   button or on the ticket — the same cap pages/seats.py already applies to the no-script badge */
var SEATS_LEFT_MAX = 15;
var W_SEAT = ["مقعد واحد", "مقعدين", "مقاعد", "مقعد"], W_MIN = ["دقيقة", "دقيقتين", "دقايق", "دقيقة"];

function arN(n, w) { return n === 1 ? w[0] : n === 2 ? w[1] : n >= 3 && n <= 10 ? n + " " + w[2] : n + " " + w[3]; }
function leftText(n, lg) { return lg === "en" ? n + (n === 1 ? " seat left" : " seats left") : "باقي " + arN(n, W_SEAT); }
/* «مزحوم ولا فاضي؟»: a question kicker before the live count, only for a sample under 90 minutes old — the count
   itself answers it, so the kicker is read out with the rest of the caption, not as its own live region */
function busyQ(lg) { return lg === "en" ? "Busy or quiet?" : "مزحوم ولا فاضي؟"; }
function summary(free, total, row, live, lg) {
  var en = lg === "en";
  if (!live) {
    return (en ? total + " seats in this hall" : "القاعة فيها " + arN(total, W_SEAT)) +
      (row ? (en ? "; best place: row " + row + ", centre" : "، أحسن مكان: الصف " + row + " وسط") : "");
  }
  if (!free) return en ? "no seats left of " + total : "ما باقي مقاعد من " + total;
  return (en ? free + " of " + total + (free === 1 ? " seat left" : " seats left") : "باقي " + arN(free, W_SEAT) + " من " + total) +
    (row ? (en ? ", best seat available: row " + row + ", centre" : "، أحسن مقعد متاح: الصف " + row + " وسط") : "");
}
function agoText(sec, lg) {
  var m = Math.max(1, Math.round(sec / 60));
  return lg === "en" ? "counted " + m + " min ago" : "آخر عدّ قبل " + arN(m, W_MIN);
}
function nowS() { return (K.now ? K.now().getTime() : Date.now()) / 1000; }
function fresh(at) { var a = nowS() - at; return typeof at === "number" && a >= -300 && a < FRESH_S; }

/* shape = {s: screen side, c: [[class, aed]], r: [[row, cells]]}, st = status rows (o x b w .), best = [row, x] */
function hallSVG(shape, st, best) {
  var rows = shape.r.map(function (r, i) { return [r[0], r[1], st ? st[i] || "" : ""]; });
  if (shape.s === "bottom") rows.reverse();
  var w = 0; rows.forEach(function (r) { w = Math.max(w, r[1].length); });
  var top = 18, h = top + rows.length * 10, out = [];
  out.push('<svg viewBox="-12 0 ' + (w * 10 + 14) + " " + h + '" aria-hidden="true" focusable="false">');
  out.push('<path class="scr" d="M4 9 Q' + (w * 5) + " 1 " + (w * 10 - 4) + ' 9"/>');
  out.push('<text class="scr-t" x="' + (w * 5) + '" y="16" text-anchor="middle">' + (K.AR ? "الشاشة" : "Screen") + "</text>");
  rows.forEach(function (r, i) {
    var y = top + i * 10;
    out.push('<text class="rn" x="-4" y="' + (y + 7.5) + '" text-anchor="middle">' + K.esc(r[0]) + "</text>");
    for (var x = 0; x < r[1].length; x++) {
      if (r[1].charAt(x) === ".") continue;
      var s = st ? (r[2].charAt(x) || "o") : "n";
      if (s === ".") continue;
      var b = best && best[0] === r[0] && best[1] === x;
      out.push('<rect class="s ' + s + (b ? " best" : "") + '" x="' + (x * 10 + 1) + '" y="' + (y + 1) + '" width="8" height="8"/>');
    }
  });
  out.push("</svg>");
  return out.join("");
}
function seatCount(shape) {
  var n = 0; shape.r.forEach(function (r) { n += r[1].replace(/\./g, "").length; }); return n;
}

/* where a time sits: the same reading the ticket makes (cinema group, film row, day box, hall row) */
function where(btn) {
  var body = document.body, grp = btn.closest("[data-cin]"), box = btn.closest("[data-d]"), fr = btn.closest(".cf, .srow"),
    hl = btn.closest("[data-hk]");
  var d = box ? box.getAttribute("data-d") : new Date(nowS() * 1000 + 4 * 36e5).toISOString().slice(0, 10);
  return { cin: grp && grp !== body ? grp.getAttribute("data-cin") : body.getAttribute("data-cin") || "",
    fid: fr ? fr.getAttribute("data-fid") : body.getAttribute("data-fid"), d: d, t: btn.getAttribute("data-start"),
    hk: hl ? hl.getAttribute("data-hk") : null };
}
function pick(list, hk) {
  if (!list || !list.length) return null;
  if (hk) { for (var i = 0; i < list.length; i++) if (list[i][0] === hk) return list[i]; return null; }
  return list.length === 1 ? list[0] : null;
}

function annotate() {
  if (!OCC || !OCC.o) return;
  K.qa(".tm[data-start]:not(.past):not([data-occ])").forEach(function (b) {
    b.setAttribute("data-occ", "");
    var c = where(b), e = pick(OCC.o[c.cin + "|" + c.fid + "|" + c.d + "|" + c.t], c.hk);
    if (!e || !fresh(e[3]) || !(e[1] > 0) || e[1] > SEATS_LEFT_MAX) return;
    var s = document.createElement("small"); s.className = "lf"; s.textContent = leftText(e[1], K.lang);
    b.appendChild(s);
  });
}

function drawTicket(tk, c, f) {
  var old = K.q("[data-tk-hall]", tk); if (old) old.parentNode.removeChild(old);
  var e = f && f.s ? pick(f.s[c.fid + "|" + c.d + "|" + c.t], c.hk) : null;
  if (!e) return;
  var shape = e[1] && f.m ? f.m[e[1]] : null, live = e.length > 6 && fresh(e[6]);
  if (!shape) return;
  var best = e[2] != null && (live || e.length <= 4) ? [e[2], e[3]] : null;
  var total = live ? e[5] : seatCount(shape);
  var fig = document.createElement("figure");
  fig.className = "tk-hall"; fig.setAttribute("data-tk-hall", "");
  fig.innerHTML = '<div class="tk-hall-d">' + hallSVG(shape, live ? e[7] : null, best) + "</div><figcaption>" +
    (live ? '<b class="q">' + K.esc(busyQ(K.lang)) + "</b> " : "") +
    K.esc(summary(live ? e[4] : null, total, best && best[0], live, K.lang)) +
    (live ? '<small class="ago">' + K.esc(agoText(nowS() - e[6], K.lang)) + "</small>" : "") + "</figcaption>";
  var tbl = K.q(".tk-seats", tk);
  if (tbl && tbl.parentNode) tbl.parentNode.insertBefore(fig, tbl.nextSibling); else tk.appendChild(fig);
  /* the ticket's own simple badge (kit/ticket.py's, filled first from the button's build-time data-left): once
     the live sample is in hand it always has the last word, scarce (timestamped «قبل X دقيقة», R4 §300) or not
     (hidden — a show that was scarce at build time but has since freed up says nothing false) */
  var le = K.q("[data-tk-seats]", tk);
  if (le && live) {
    if (e[4] > 0 && e[4] <= SEATS_LEFT_MAX) { le.hidden = false; le.textContent = leftText(e[4], K.lang) + (K.AR ? "، " : ", ") + agoText(nowS() - e[6], K.lang); }
    else { le.hidden = true; le.textContent = ""; }
  }
}

/* the core fills the ticket after its own click handler (maybe after a slice fetch): wait for this time */
function whenFilled(tk, c, fn) {
  var n = 0;
  (function poll() {
    var t = K.q("[data-tk-time]", tk);
    if (!tk.hidden && t && t.textContent === c.t && tk.getAttribute("data-cin") === c.cin) return fn();
    if (++n < 60) setTimeout(poll, 50);
  })();
}
/* /data/seats/index.json lists the cinemas that have a seats file: only those are asked for (a missing one
   was a 404 on every ticket tap). A cinema without one still clears the last show's drawing. */
function forTime(tk, btn, wait) {
  var c = where(btn);
  if (!c.cin || !c.fid) return;
  K.getJSON("/data/seats/index.json").then(function (ix) {
    var has = !!ix && ix.indexOf && ix.indexOf(c.cin) >= 0;
    return has ? K.getJSON("/data/seats/" + encodeURIComponent(c.cin) + ".json") : null;
  }).then(function (f) {
    if (wait) whenFilled(tk, c, function () { drawTicket(tk, c, f); }); else drawTicket(tk, c, f);
  });
}

function start() {
  var tk = K.q("[data-ticket]");
  K.getJSON("/data/occupancy.json").then(function (j) {
    OCC = j; annotate();
    if (window.MutationObserver) {
      var pend = 0;
      new MutationObserver(function () { if (!pend) pend = setTimeout(function () { pend = 0; annotate(); }, 250); })
        .observe(document.body, { childList: true, subtree: true });
    }
  });
  if (!tk) return;
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest(".tm[data-start]");
    if (b && !b.classList.contains("past")) forTime(tk, b, true);
  });
  /* the time the ticket holds now: the page may already have moved it off the build's show (a started show,
     a show link), and the selected time carries .on */
  var sid = tk.getAttribute("data-show"), first = K.q(".tm.on[data-start]") || (sid ? K.q('.tm[data-show="' + sid + '"]') : null);
  if (first && !tk.hidden && !first.classList.contains("past")) forTime(tk, first, false);
}
if (typeof document !== "undefined" && K.q) start();
