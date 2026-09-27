/* src/js/share.js — roadmap #82: a share link (the ticket's own, plus the film/cinema ones pages/og.py
   adds) carries the sharer's ?city=&card=; opening one applies them only when nothing is saved yet or
   the saved values already agree, and otherwise asks — it never silently overwrites what the visitor
   already had. An unknown city/card (not in C.cities/C.cards) is dropped at the source in shareParams()
   itself, so neither the immediate-apply path nor the deferred "Yes" click (both read from the same
   validated sc/scard) can ever store or apply one (review fix round 1). Main bundle (pages/og.py's JS):
   concatenated with core.js into one scope (build.js_files), so `shareParams` below is hoisted and
   callable from core.js's own state block even though this file's text sits after it. */

var pendingShare = null;

/* called once, from core.js, before `city`/`card` are read for the first time */
function shareParams() {
  var sc = param("city"), scard = param("card");
  /* an unknown value (a stale, malformed or tampered share link) is dropped right here, at the source —
     never stored, never queued in pendingShare, so the deferred "Yes" click (below) can't apply it either */
  if (sc != null && C.cities && !C.cities[sc]) sc = null;
  if (scard && C.cards && !C.cards[scard]) scard = null;   // "" (explicitly no card) is always valid
  if (sc == null && scard == null) return;
  var savedCity = get("city"), savedCard = get("card");
  var hasSaved = savedCity != null || (savedCard != null && savedCard !== "");
  var agrees = (sc == null || sc === savedCity) && (scard == null || scard === (savedCard || ""));
  if (!hasSaved || agrees) {
    if (sc != null) set("city", sc);
    if (scard != null) set("card", scard);
  } else {
    pendingShare = { city: sc, card: scard };   // asked once the page has bound (feature() below)
  }
}

/* a share link's target with the CURRENT visitor's city/card appended (never the sharer's own, which
   is only ever read once, by shareParams() above, on the page they opened) */
function shareURL(base) {
  var sep = base.indexOf("?") === -1 ? "?" : "&";
  return base + sep + "city=" + encodeURIComponent(city) + (card ? "&card=" + encodeURIComponent(card) : "");
}

feature(function () {
  /* one delegated, capturing listener for every share link: the ticket's own (`[data-tk-share]`,
     src/js/ticket.js keeps building its `data-share`/`data-url`) and pages/og.py's film/cinema ones
     (`[data-share]`, `data-share-msg`/`data-share-url`). Capture + stopPropagation means this always
     runs before ticket.js's own bubble-phase listener, so a show is never shared twice. */
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-share], [data-tk-share]");
    if (!el) return;
    var isOg = el.hasAttribute("data-share-url");
    var base = el.getAttribute(isOg ? "data-share-url" : "data-url");
    var msg = el.getAttribute(isOg ? "data-share-msg" : "data-share") || "";
    if (!base) return;
    e.stopPropagation();
    var full = shareURL(base);
    el.setAttribute(isOg ? "data-share-url" : "data-url", full);
    el.href = "https://wa.me/?text=" + encodeURIComponent(msg + "\n" + full);
    if (navigator.share) {
      e.preventDefault();
      navigator.share({ title: document.title, text: msg, url: full }).catch(function () {});
    }
  }, true);

  if (!pendingShare) return;
  var cityName = (C.cities && C.cities[pendingShare.city]) || pendingShare.city || "";
  var cardName = pendingShare.card ? ((C.cards && C.cards[pendingShare.card]) || pendingShare.card) : "";
  var who = cardName ? cityName + (AR ? "، " : ", ") + cardName : cityName;
  var msg = AR ? "فتحت بإعدادات صاحبك (" + who + ") — استعملها؟" : "Opened with your friend’s settings (" + who + ") — use them?";
  var bar = document.createElement("div");
  bar.className = "shareask";
  bar.setAttribute("role", "status");
  bar.innerHTML = "<p>" + esc(msg) + "</p><button type=\"button\" data-share-yes>" + esc(AR ? "نعم" : "Yes") +
    "</button><button type=\"button\" data-share-no>" + esc(AR ? "لا" : "No") + "</button>";
  document.body.appendChild(bar);
  bar.addEventListener("click", function (e) {
    if (e.target.hasAttribute("data-share-yes")) {
      var ps = pendingShare;
      if (ps.city) pickCity(ps.city);
      if (ps.card != null) pickCard(ps.card);
    }
    pendingShare = null;
    bar.remove();
  });
});
