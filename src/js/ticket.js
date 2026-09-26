/* the ticket: a tapped time fills the page's one ticket. Phone (< 1024 px): a bottom sheet — a modal
   dialog with its focus kept inside, closed by ×, Esc, the scrim or the back button, focus going back to
   the time. Desktop: the side panel changes in place and a live region says so. */
var PL = (function () { var el = document.getElementById("cinema-p"); try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; } })();
var tk = q("[data-ticket]"), tkFrom = null, tkPushed = false, scrim = null;
function tkSet(sel, v, html) { var el = q(sel, tk); if (el) { if (html) el.innerHTML = v; else el.textContent = v; } return el; }
function chainName(ch) { return (D && D.chains && D.chains[lang] && D.chains[lang][ch]) || ch; }
function words(v) { return String(v || "").split("+").filter(Boolean).map(function (k) { return (C.langs && C.langs[k]) || k; }).join(TX.sep); }
function goLinks(cid) {
  var c = G && G[cid];
  if (!c) return "";
  var ll = c[2] + "," + c[3];
  return (AR ? "الاتجاهات: " : "Directions: ") + '<a href="https://www.google.com/maps/dir/?api=1&destination=' + ll + '" rel="noopener" target="_blank" lang="en">Google Maps</a>' +
    TX.sep + '<a href="https://waze.com/ul?ll=' + ll + '&navigate=yes" rel="noopener" target="_blank" lang="en">Waze</a>';
}
function renderTerms(chain) {
  var el = tk && q("[data-tk-terms]", tk); if (!el) return;
  var r = card && D ? rule(chain, card) : null;
  el.hidden = !(r && state(r) === "ok");
  if (!el.hidden) el.innerHTML = esc(sub(C.after_card, { card: C.cards[card] })) + " " + offer(r) + terms(r);
}

/* what the ticket needs about a time: from its own attributes when the page wrote them all (a hall row
   around it, prices in #cinema-p), else from its city's slice — never a guessed hall */
function openTicket(btn) {
  if (!tk || !q("[data-tk-rows]", tk)) return;
  qa(".tm.on").forEach(function (o) { o.classList.remove("on"); o.removeAttribute("aria-current"); });
  btn.classList.add("on");
  var grp = btn.closest("[data-cin]"), hl = btn.closest("[data-hall]"), box = btn.closest("[data-d]");
  var cin = grp && grp !== body ? grp.getAttribute("data-cin") : body.getAttribute("data-cin") || "";
  var d = box ? box.getAttribute("data-d") : TODAY, t = btn.getAttribute("data-start");
  var fr = btn.closest(".cf, .srow"), fid = fr ? fr.getAttribute("data-fid") : body.getAttribute("data-fid");
  var cityId = (btn.closest("[data-city]") || body).getAttribute("data-city") || city;
  var hk0 = hl && hl.getAttribute("data-hk");
  var rich = !!hl && btn.hasAttribute("data-show");
  (rich ? Promise.resolve(null) : daySlice(cityId, d)).then(function (sl) {
    var s = sl && sl.shows.filter(function (x) { return x.c === cin && x.f === fid && x.t === t && (!hk0 || x.k === hk0); })[0] || null;
    var chain = (grp && grp.getAttribute("data-chain")) || (sl && sl.cinemas[cin] && sl.cinemas[cin].chain) || (G && G[cin] && G[cin][1]) ||
      (body.getAttribute("data-chains") || "").split(" ")[0];
    fillTicket(btn, {
      cin: cin, d: d, t: t, fid: fid, chain: chain,
      hall: hl ? hl.getAttribute("data-hall") : s ? s.h : null, hk: hk0 || (s ? s.k : null),
      hn: (hl && q(".hn", hl) && q(".hn", hl).textContent) || (hl && q("small", hl) && q("small", hl).textContent) || (s && s.hn) || "",
      ends: btn.getAttribute("data-ends") || (s && s.e), lg: btn.getAttribute("data-lang") || (s && s.lg), sb: btn.getAttribute("data-subs") || (s && s.sb),
      p: btn.hasAttribute("data-p") ? PL[+btn.getAttribute("data-p")] : s && s.p, asof: btn.getAttribute("data-asof") || (s && s.asof),
      left: +btn.getAttribute("data-left") || 0,
      book: btn.getAttribute("data-book") || (s && s.b) || btn.getAttribute("href") || (C.sites && C.sites[chain]) || "",
      cname: ((grp && grp !== body && q(".cg-h h3, .cn", grp)) || q("h1.pt") || {}).textContent || "",
      film: ((fr ? q(".cf-b h3, .sf .t", fr) : q("h1.ft")) || {}).textContent || ""
    });
  });
}
function fillTicket(btn, x) {
  var dname = x.d === TODAY ? C.today : x.d === TOMORROW ? C.tomorrow : x.d, lines = [];
  tkSet("[data-tk-cin]", x.cname); tkSet("[data-tk-film]", x.film); tkSet("[data-tk-time]", x.t); tkSet("[data-tk-day]", dname);
  if (x.hk && x.hk !== "Standard" && x.hn) lines.push('<span class="tk-h"><bdi>' + esc(x.hn) + "</bdi></span>");
  if (x.ends) {
    var ad = (C.ad && C.ad[x.chain]) || 15, st = hhmm(uae(x.d + "T" + x.t).getTime() + ad * 60e3);
    lines.push("<span>" + esc(sub(TX.starts, { s: st, e: x.ends })) + "</span>");
  } else lines.push("<span>" + esc(sub(TX.at, { s: x.t })) + "</span>");
  if (x.lg) lines.push("<span>" + esc(words(x.lg)) + (x.sb ? TX.sep + esc(sub(TX.subs, { s: words(x.sb) })) : "") + "</span>");
  tkSet("[data-tk-when]", lines.join(""), true);
  var le = q("[data-tk-seats]", tk);
  if (le) { le.hidden = !x.left; le.textContent = x.left ? seatsLeft(x.left, lang) : ""; }
  /* an unknown hall (no slice) gets no after-discount price: a card may exclude it */
  var known = x.hall != null && x.hk != null;
  tkSet("[data-tk-rows]", x.p && x.p.length ? x.p.slice().sort(function (a, b) { return a[1] - b[1]; }).map(function (p) {
    return '<tr><th scope="row"><bdi lang="en">' + esc(p[0]) + '</bdi></th><td><span class="p" data-aed="' + fmt(p[1]) + '" data-chain="' + esc(x.chain) + '" data-hall="' + esc(x.hall || "") +
      '" data-hk="' + esc(x.hk || "") + '" data-cin="' + esc(x.cin) + '"' + (known ? "" : " data-nd") + (x.asof ? ' data-asof="' + esc(x.asof) + '"' : "") + "></span></td></tr>";
  }).join("") : '<tr><td colspan="2"><span class="na">' + esc(C.box) + "</span></td></tr>", true);
  qa(".p[data-aed]", tk).forEach(function (el) { el.innerHTML = priceHTML(el, false); });
  tk.setAttribute("data-chain", x.chain); tk.setAttribute("data-cin", x.cin);
  renderTerms(x.chain);
  /* the booking link is this show's, else its chain's site: never the last show's */
  var book = q("[data-tk-book]", tk);
  if (book && x.book) { book.href = x.book; book.classList.remove("off"); book.textContent = sub(C.book_at, { chain: chainName(x.chain) }); }
  var sh = q("[data-tk-share]", tk), msg = sub(TX.share_t, { film: x.film, cin: x.cname, day: dname, t: x.t });
  var link = location.origin + (x.fid ? C.base + "film/" + x.fid + "/" : location.pathname);
  if (sh) { sh.setAttribute("data-share", msg); sh.setAttribute("data-url", link); sh.href = "https://wa.me/?text=" + encodeURIComponent(msg + "\n" + link); }
  geo().then(function () { var g = q("[data-tk-go]", tk), h = goLinks(x.cin); if (g && h) g.innerHTML = '<span class="go">' + h + "</span>"; });
  tkSet("[data-tk-live]", sub(TX.ticket, { film: x.film, cin: x.cname, t: x.t }));
  tk.hidden = false;
  if (desk()) { tk.setAttribute("role", "region"); tk.removeAttribute("aria-modal"); }
  else if (!tk.classList.contains("open")) sheetOpen(btn);
}

function focusables() { return qa('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])', tk).filter(function (e) { return e.offsetParent !== null || e === document.activeElement; }); }
function sheetOpen(btn) {
  tkFrom = btn;
  tk.setAttribute("role", "dialog"); tk.setAttribute("aria-modal", "true"); tk.setAttribute("tabindex", "-1");
  if (!scrim) { scrim = document.createElement("div"); scrim.className = "scrim"; scrim.addEventListener("click", closeTicket); document.body.appendChild(scrim); }
  scrim.classList.add("on");
  tk.classList.add("open");
  if (!tkPushed) { try { history.pushState({ tk: 1 }, ""); tkPushed = true; } catch (e) {} }
  var x = q("[data-tk-close]", tk);
  setTimeout(function () { (x || tk).focus(); }, 30);
}
function closeTicket(fromPop) {
  if (!tk || !tk.classList.contains("open")) return;
  tk.classList.remove("open"); tk.removeAttribute("aria-modal");
  if (scrim) scrim.classList.remove("on");
  if (tkPushed && fromPop !== true) { tkPushed = false; try { history.back(); } catch (e) {} }
  tkPushed = false;
  if (tkFrom) { tkFrom.focus(); tkFrom = null; }
}
function bindTicket() {
  if (!tk) return;
  if (desk()) { tk.setAttribute("role", "region"); tk.setAttribute("aria-label", AR ? "التذكرة" : "Ticket"); }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".tm[data-start]");
    if (b) { if (b.classList.contains("past")) { e.preventDefault(); return; } if (q("[data-tk-rows]", tk)) { e.preventDefault(); tkFrom = b; openTicket(b); } return; }
    if (e.target.closest && e.target.closest("[data-tk-close]")) { closeTicket(); return; }
    var sh = e.target.closest && e.target.closest("[data-tk-share]");
    if (sh && navigator.share) {
      e.preventDefault();
      navigator.share({ title: document.title, text: sh.getAttribute("data-share"), url: sh.getAttribute("data-url") || location.href }).catch(function () {});
    }
  });
  document.addEventListener("keydown", function (e) {
    if (!tk.classList.contains("open")) return;
    if (e.key === "Escape") { e.preventDefault(); closeTicket(); return; }
    if (e.key !== "Tab") return;
    var f = focusables(); if (!f.length) return;
    var a = f[0], z = f[f.length - 1];
    if (e.shiftKey && (document.activeElement === a || !tk.contains(document.activeElement))) { e.preventDefault(); z.focus(); }
    else if (!e.shiftKey && (document.activeElement === z || !tk.contains(document.activeElement))) { e.preventDefault(); a.focus(); }
  });
  window.addEventListener("popstate", function () { if (tk.classList.contains("open")) { tkPushed = false; closeTicket(true); } });
}
