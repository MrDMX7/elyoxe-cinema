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

function openTicket(btn) {
  if (!tk || !q("[data-tk-rows]", tk)) return;
  qa(".tm.on").forEach(function (o) { o.classList.remove("on"); o.removeAttribute("aria-current"); });
  btn.classList.add("on");
  var grp = btn.closest("[data-cin]"), hl = btn.closest("[data-hall]"), box = btn.closest("[data-d]");
  var cin = grp && grp !== body ? grp.getAttribute("data-cin") : body.getAttribute("data-cin") || "";
  var d = box ? box.getAttribute("data-d") : TODAY;
  var chain = (grp && grp.getAttribute("data-chain")) || (body.getAttribute("data-chains") || "").split(" ")[0];
  var fr = btn.closest(".cf, .srow"), fid = fr ? fr.getAttribute("data-fid") : body.getAttribute("data-fid");
  /* a city page's time has no hall row around it: its hall comes from the city's slice */
  var sl = !hl && S && S.shows.filter(function (s) { return s.c === cin && s.f === fid && s.d === d && s.t === btn.getAttribute("data-start"); })[0];
  var hall = hl ? hl.getAttribute("data-hall") : sl ? sl.h : "Standard", hk = hl ? hl.getAttribute("data-hk") : sl ? sl.k.slice(sl.k.indexOf("|") + 1) : "Standard";
  var asof = btn.getAttribute("data-asof"), t = btn.getAttribute("data-start"), ends = btn.getAttribute("data-ends");
  var cname = ((grp && grp !== body && q(".cg-h h3, .cn", grp)) || q("h1.pt") || {}).textContent || "";
  var film = ((fr ? q(".cf-b h3, .sf .t", fr) : q("h1.ft")) || {}).textContent || "";
  var dname = d === TODAY ? C.today : d === TOMORROW ? C.tomorrow : d;
  tkSet("[data-tk-cin]", cname); tkSet("[data-tk-film]", film); tkSet("[data-tk-time]", t); tkSet("[data-tk-day]", dname);
  var hn = hl && q(".hn", hl), sm = q("small:not(.pz)", btn), lines = [];
  var hname = hk !== "Standard" ? (hn ? hn.textContent : sm ? sm.textContent : "") : "";
  if (hname) lines.push('<span class="tk-h"><bdi>' + esc(hname) + "</bdi></span>");
  if (ends) {
    var ad = (C.ad && C.ad[chain]) || 15, st = hhmm(uae(d + "T" + t).getTime() + ad * 60e3);
    lines.push("<span>" + esc(sub(TX.starts, { s: st, e: ends })) + "</span>");
  } else lines.push("<span>" + esc(sub(TX.at, { s: t })) + "</span>");
  var lg = btn.getAttribute("data-lang"), sb = btn.getAttribute("data-subs");
  if (lg) lines.push("<span>" + esc(words(lg)) + (sb ? TX.sep + esc(sub(TX.subs, { s: words(sb) })) : "") + "</span>");
  tkSet("[data-tk-when]", lines.join(""), true);
  var left = +btn.getAttribute("data-left"), le = q("[data-tk-seats]", tk);
  if (le) { le.hidden = !left; le.textContent = left ? seatsLeft(left, lang) : ""; }
  var pl = PL[+btn.getAttribute("data-p")];
  tkSet("[data-tk-rows]", pl && btn.hasAttribute("data-p") ? pl.slice().sort(function (a, b) { return a[1] - b[1]; }).map(function (p) {
    return '<tr><th scope="row"><bdi lang="en">' + esc(p[0]) + '</bdi></th><td><span class="p" data-aed="' + fmt(p[1]) + '" data-chain="' + esc(chain) + '" data-hall="' + esc(hall) + '" data-hk="' + esc(hk) + '" data-cin="' + esc(cin) + '"' + (asof ? ' data-asof="' + esc(asof) + '"' : "") + "></span></td></tr>";
  }).join("") : '<tr><td colspan="2"><span class="na">' + esc(C.box) + "</span></td></tr>", true);
  qa(".p[data-aed]", tk).forEach(function (el) { el.innerHTML = priceHTML(el, false); });
  tk.setAttribute("data-chain", chain); tk.setAttribute("data-cin", cin);
  renderTerms(chain);
  /* the booking link is this show's, else its chain's site (the time's own href): never the last show's */
  var book = q("[data-tk-book]", tk), url = btn.getAttribute("data-book") || btn.getAttribute("href");
  if (book && url) { book.href = url; book.classList.remove("off"); book.textContent = sub(C.book_at, { chain: chainName(chain) }); }
  var sh = q("[data-tk-share]", tk), msg = sub(TX.share_t, { film: film, cin: cname, day: dname, t: t });
  var link = location.origin + (fid ? C.base + "film/" + fid + "/" : location.pathname);
  if (sh) { sh.setAttribute("data-share", msg); sh.setAttribute("data-url", link); sh.href = "https://wa.me/?text=" + encodeURIComponent(msg + "\n" + link); }
  geo().then(function () { var g = q("[data-tk-go]", tk), h = goLinks(cin); if (g && h) g.innerHTML = '<span class="go">' + h + "</span>"; });
  tkSet("[data-tk-live]", sub(TX.ticket, { film: film, cin: cname, t: t }));
  tk.hidden = false;
  if (!desk()) sheetOpen(btn);
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
    var b = e.target.closest && e.target.closest(".tm[data-show]");
    if (b) { if (b.classList.contains("past")) { e.preventDefault(); return; } if (q("[data-tk-rows]", tk)) { e.preventDefault(); openTicket(b); } return; }
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
