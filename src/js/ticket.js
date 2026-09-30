/* the ticket: a tapped time fills the page's one ticket. Phone (< 1024 px): a bottom sheet — a modal
   dialog with its focus kept inside, closed by ×, Esc, the scrim or the back button, focus going back to
   the time (on a film page the time first shows the dock, src/js/film.js, whose «التفاصيل» opens the
   sheet — «احجز» books straight from the stub). Desktop: the side panel changes in place and a live region says so.
   tkOpen, not sheetOpen: the bundle is one scope, and sheet.js's sheetOpen(id) (later in it) would win. */
var PL = (function () { var el = document.getElementById("cinema-p"); try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; } })();
var tk = q("[data-ticket]"), tkFrom = null, tkPushed = false, scrim = null, tkInert = [];
/* while the sheet is modal, everything outside it (every sibling of the sheet and of each of its ancestors)
   is inert: no focus, no clicks, not read out. Only what we made inert is restored. */
function inertOn() {
  tkInert = [];
  for (var n = tk; n && n !== body; n = n.parentElement) {
    var sibs = n.parentElement ? n.parentElement.children : [];
    for (var i = 0; i < sibs.length; i++) {
      var e = sibs[i];
      if (e === n || e === scrim || e.inert || /^(SCRIPT|STYLE|TEMPLATE)$/.test(e.tagName)) continue;
      e.inert = true; tkInert.push(e);
    }
  }
}
function inertOff() { tkInert.forEach(function (e) { e.inert = false; }); tkInert = []; }
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
  renderBook(chain);
}
/* strings this file adds (the voice table, plan §1.7) */
var TK = AR ? { gone: "هالعرض بدأ، هذي الأوقات الجاية", box: "الخصم من الشباك بس", pick: "اختار وقت" }
  : { gone: "That show has started. Here are the next ones.", box: "Discount at the box office only.", pick: "Pick a time" };

/* a card whose discount is given only at the box office (Star or Cine Royal with Fazaa…): the price the ticket
   shows is not what the chain's site charges, so the button says so and leads to the cinema, not the site */
function mapsTo(cin) {
  var c = G && G[cin];
  return c ? "https://www.google.com/maps/dir/?api=1&destination=" + c[2] + "," + c[3]
    : "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent((q("[data-tk-cin]", tk) || {}).textContent || cin);
}
function renderBook(chain) {
  var a = tk && q("[data-tk-book]", tk); if (!a) return;
  if (!a.hasAttribute("data-bk")) a.setAttribute("data-bk", a.getAttribute("href") || "");
  var cin = tk.getAttribute("data-cin") || "", r = card && D ? rule(chain, card) : null;
  var box = !!(r && r.box_office_only && after(100, chain, tk.getAttribute("data-hc"), card, tk.getAttribute("data-hkey"), cin).a != null);
  var was = a.hasAttribute("data-box");
  a.toggleAttribute("data-box", box);
  if (box) {
    a.textContent = TK.box; a.href = mapsTo(cin);
    if (!G) geo().then(function () { if (a.hasAttribute("data-box") && tk.getAttribute("data-cin") === cin) a.href = mapsTo(cin); });
  } else if (was) {   /* back from the box office: the chain's booking link and words again */
    a.href = a.getAttribute("data-bk"); a.textContent = sub(C.book_at, { chain: chainName(chain) });
  }
}

/* the show link /film/<fid>/#s-<key>: showKey() is in core.js since W1-P1, beside its Python twin Kit.show_key */
/* a time button's cinema, date, time and hall key, read where the ticket reads them */
function showOf(b) {
  var g = b.closest("[data-cin]"), box = b.closest("[data-d]"), hl = b.closest("[data-hk]");
  return { cin: g && g !== body ? g.getAttribute("data-cin") : body.getAttribute("data-cin") || "",
    d: box ? box.getAttribute("data-d") : TODAY, t: b.getAttribute("data-start"), hk: hl ? hl.getAttribute("data-hk") : "Standard" };
}
function showKeyOf(b) { var s = showOf(b); return showKey(s.cin, s.d, s.t, s.hk); }
function tmStart(b) { var s = showOf(b); return uae(s.d + "T" + s.t).getTime(); }
function tmPast(b) { return tmStart(b) < NOW.getTime(); }
/* the buttons that have not started, soonest first (each start worked out once) */
function upcoming(bs) {
  var n = NOW.getTime();
  return bs.map(function (b) { return [tmStart(b), b]; }).filter(function (x) { return x[0] >= n; })
    .sort(function (x, y) { return x[0] - y[0]; }).map(function (x) { return x[1]; });
}
/* a time button inside a schedule (not a tile, not the ticket), in document order */
function schedTimes(scope) { return qa(".tm[data-start]", scope || document).filter(function (b) { return !!b.closest(".times[data-d]") && !tk.contains(b); }); }
/* press the day chip a time belongs to, when the page has day chips and another day is showing */
function showDay(b) {
  var d = showOf(b).d, chip = q('[data-day="' + d + '"]');
  if (chip && chip.getAttribute("aria-pressed") !== "true") chip.click();
}
function scrollNear(el) {
  var go = function () {
    var top = el.getBoundingClientRect().top + (window.scrollY || window.pageYOffset || 0) - Math.round(window.innerHeight * 0.22);
    window.scrollTo(0, Math.max(0, top));
  };
  go();
  /* on a cold landing the page keeps moving under this scroll: the web fonts swap in, and on the film page the
     cinemas above are laid out and repriced (film.js, the discounts file), so a long schedule's block drifts off
     the screen (Chrome's scroll anchoring keeps some other node in place). For the next ~150 frames, a block that
     moved is scrolled to again, unless the visitor has touched, wheeled, clicked or pressed a key meanwhile */
  var moved = false, evs = ["wheel", "touchstart", "keydown", "mousedown"], mark = function () { moved = true; };
  evs.forEach(function (e) { window.addEventListener(e, mark, { passive: true, once: true }); });
  var last = el.getBoundingClientRect().top, n = 0, raf = window.requestAnimationFrame || function (fn) { return setTimeout(fn, 16); };
  (function hold() {
    if (moved || !el.isConnected || ++n > 150) { evs.forEach(function (e) { window.removeEventListener(e, mark); }); return; }
    var t = el.getBoundingClientRect().top;
    if (Math.abs(t - last) > 4) { go(); t = el.getBoundingClientRect().top; }
    last = t;
    raf(hold);
  })();
  var f = document.fonts;
  if (f && f.ready) f.ready.then(function () { if (!moved && el.isConnected) go(); });
}
/* a tap the ticket should treat as the visitor's own (the hash, or a finger), else the page picking for them */
var tkUser = false, tkAuto = null, tkPicking = false;
function tapTime(b, user) { tkPicking = !user; try { b.click(); } finally { tkPicking = false; } }
/* the show a key names, on the film page as the server wrote it or as film.js laid it out: the cinema group, the
   day and the time. film.js lays out only the visitor's city, three cinemas of it, and a compact page prints a
   cinema's times as text until then, so the key is worked out from the markup, not only from buttons. */
function keyShow(key) {
  var hit = null;
  qa(".cgs .cg[data-cin]").some(function (cg) {
    var cin = cg.getAttribute("data-cin");
    return qa(".times[data-d]", cg).some(function (box) {
      var d = box.getAttribute("data-d"), hl = box.closest("[data-hk]"), hk0 = hl ? hl.getAttribute("data-hk") : "Standard";
      var ts = qa(".tm[data-start]", box).map(function (b) { return [b.getAttribute("data-start"), b.getAttribute("data-hk") || hk0]; });
      qa(".tl", box).forEach(function (tl) { (tl.textContent.match(/\d\d:\d\d/g) || []).forEach(function (t) { ts.push([t, hk0]); }); });
      return ts.some(function (x) { if (showKey(cin, d, x[0], x[1]) !== key) return false; hit = { cg: cg, d: d, t: x[0] }; return true; });
    });
  });
  return hit;
}
/* the film page reads #s-<key>: that show's ticket opens (phone: the sheet, over the dock; desktop: the column).
   A key whose show has started, or that the page no longer has, says so over that cinema's next times. */
function showFromHash() {
  var m = /^#s-([0-9a-z]{1,8})$/.exec(location.hash || "");
  if (!m || page !== "film" || !tk || !q("[data-tk-rows]", tk)) return false;
  var old = q("[data-gone]"); if (old) old.parentNode.removeChild(old);
  var at = keyShow(m[1]), cg = at && at.cg;
  /* its city opened and its cinema laid out (film.js draws new buttons), then its button found */
  if (cg && typeof fsReveal === "function") fsReveal(cg);
  var hit = cg ? schedTimes(cg).filter(function (b) { return showKeyOf(b) === m[1]; })[0] || null : null;
  if (hit && !tmPast(hit)) {
    showDay(hit); tkUser = true; tapTime(hit, true);
    if (!desk() && !tk.classList.contains("open")) tkOpen(hit);
    scrollNear(hit);
    return true;
  }
  var next = cg ? upcoming(schedTimes(cg))[0] : null;
  var p = document.createElement("p");
  p.className = "hint"; p.setAttribute("data-gone", ""); p.setAttribute("role", "status"); p.textContent = TK.gone;
  if (next) {
    showDay(next);
    var h = q(".cg-h", cg); if (h) h.insertAdjacentElement("afterend", p); else cg.insertAdjacentElement("afterbegin", p);
    scrollNear(cg);
  } else {
    var s = q(".cgs"); if (!s) return false;
    s.insertAdjacentElement("afterbegin", p); scrollNear(p);
  }
  if (typeof fsCheck === "function") fsCheck();   /* desktop: the column is film.js's next show (Task 4 I5), never a started one */
  return true;
}
/* desktop: the column is never a show that has started. Until the visitor picks a time it follows the next
   upcoming show in their city (priced first, as the build picks), else it asks for a time. */
function tkScope() { return page === "film" ? q('.fcity[data-city="' + city + '"]') : q(".cgs, .cfilms, .sched") ? document : null; }
function nextShow() {
  var sc = tkScope(); if (!sc) return null;
  var up = upcoming(schedTimes(sc === document ? null : sc));
  return up.filter(function (b) { return b.hasAttribute("data-p"); })[0] || up[0] || null;
}
function pickState(on) {
  var el = q("[data-tk-pick]", tk);
  if (!on) {
    if (el) el.parentNode.removeChild(el);
    qa("[data-tk-pk]", tk).forEach(function (c) { c.classList.remove("x"); c.removeAttribute("data-tk-pk"); });
    return;
  }
  if (el) return;
  [].slice.call(tk.children).forEach(function (c) { if (!c.classList.contains("x")) { c.classList.add("x"); c.setAttribute("data-tk-pk", ""); } });
  tk.insertAdjacentHTML("afterbegin", '<div class="tk-main" data-tk-pick><p class="tk-cin">' + esc(TK.pick) + "</p></div>");
  qa(".tm.on").forEach(function (o) { o.classList.remove("on"); o.removeAttribute("aria-current"); });
}
/* (the film page's column is film.js's: fsAuto/fsTick pick its next show, UI redesign Task 4 I5; this serves the
   pages not redesigned yet, a cinema's and a city's) */
function rollTicket() {
  if (!tk || page === "film" || tkUser || tk.hidden || !desk() || !q("[data-tk-rows]", tk)) return;
  var sc = tkScope(), cur = tkAuto;
  if (cur && sc && (sc === document || sc.contains(cur)) && !tmPast(cur)) return;
  var b = nextShow();
  tkAuto = b;
  if (b) tapTime(b, false); else pickState(true);
}
/* the ticket the build wrote: its show's hall and its day as the visitor's clock names it */
function ticketStart() {
  if (!tk) return;
  var sid = tk.getAttribute("data-show"), b = sid ? q('.tm[data-show="' + sid + '"]') : null;
  if (!b || tk.contains(b)) return;
  tkAuto = b;
  var hl = b.closest("[data-hall]");
  if (hl) { tk.setAttribute("data-hc", hl.getAttribute("data-hall") || ""); tk.setAttribute("data-hkey", hl.getAttribute("data-hk") || ""); }
  tkSet("[data-tk-day]", dayName(showOf(b).d));
}

/* what the ticket needs about a time: from its own attributes when the page wrote them all (a hall row
   around it, prices in #cinema-p), else from its city's slice — never a guessed hall */
function openTicket(btn, quiet) {   /* quiet: the page's own pick (film.js fsAuto) — nothing said */
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
      left: +btn.getAttribute("data-left") || 0, quiet: !!quiet,
      book: btn.getAttribute("data-book") || (s && s.b) || btn.getAttribute("href") || (C.sites && C.sites[chain]) || "",
      cname: ((grp && grp !== body && q(".cg-h h3, .cn", grp)) || q("h1.pt") || {}).textContent || "",
      film: ((fr ? q(".cf-b h3, .sf .t", fr) : q("h1.ft")) || {}).textContent || ""
    });
  });
}
function fillTicket(btn, x) {
  var dname = dayName(x.d), lines = [];
  pickState(false);
  tk.setAttribute("data-hc", x.hall || ""); tk.setAttribute("data-hkey", x.hk || "");
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
  emit("ticket", x);   /* the qty-stepper chunk (R4 §298, tkqty.js): a new show, its default follows «مع منو» again */
  renderTerms(x.chain);
  /* the booking link is this show's, else its chain's site: never the last show's */
  var book = q("[data-tk-book]", tk);
  if (book && x.book) { book.href = x.book; book.setAttribute("data-bk", x.book); book.classList.remove("off"); book.textContent = sub(C.book_at, { chain: chainName(x.chain) }); }
  renderBook(x.chain);
  var sh = q("[data-tk-share]", tk), msg = sub(TX.share_t, { film: x.film, cin: x.cname, day: dname, t: x.t });
  var link = location.origin + (x.fid ? C.base + "film/" + x.fid + "/" : location.pathname);
  if (sh) { sh.setAttribute("data-share", msg); sh.setAttribute("data-url", link); sh.href = "https://wa.me/?text=" + encodeURIComponent(msg + "\n" + link); }
  geo().then(function () { var g = q("[data-tk-go]", tk), h = goLinks(x.cin); if (g && h) g.innerHTML = '<span class="go">' + h + "</span>"; });
  if (!x.quiet) tkSet("[data-tk-live]", sub(TX.ticket, { film: x.film, cin: x.cname, t: x.t }));
  tk.hidden = false;
  if (desk()) { tk.setAttribute("role", "region"); tk.removeAttribute("aria-modal"); }
  if (page === "film") { fsPicked(btn, x); return; }
  if (!desk() && !tk.classList.contains("open")) tkOpen(btn);
}

function focusables() { return qa('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])', tk).filter(function (e) { return e.offsetParent !== null || e === document.activeElement; }); }
/* the dock/history race (w2-p3a-review-lean.md #4): history.back() is async. If the sheet reopens before its
   popstate lands, a naive pushState would race the pending pop, which then closes the new sheet instead of the
   old one. tkClosing marks that a pop is in flight; a tkOpen while it is in flight is queued (tkReopen) and runs
   only once that pop has landed, so the reopen never races it. */
var tkClosing = false, tkReopen = null;
function tkOpen(btn) {
  if (tkClosing) { tkReopen = btn; return; }
  tkFrom = btn;
  tk.setAttribute("role", "dialog"); tk.setAttribute("aria-modal", "true"); tk.setAttribute("tabindex", "-1");
  if (!scrim) { scrim = document.createElement("div"); scrim.className = "scrim"; scrim.addEventListener("click", closeTicket); document.body.appendChild(scrim); }
  scrim.classList.add("on");
  tk.classList.add("open");
  inertOn();
  if (!tkPushed) { try { history.pushState({ tk: 1 }, ""); tkPushed = true; } catch (e) {} }
  var x = q("[data-tk-close]", tk);
  setTimeout(function () { (x || tk).focus(); }, 30);
}
function closeTicket(fromPop) {
  if (!tk || !tk.classList.contains("open")) return;
  tk.classList.remove("open"); tk.removeAttribute("aria-modal");
  inertOff();
  if (scrim) scrim.classList.remove("on");
  if (tkPushed && fromPop !== true) { tkPushed = false; tkClosing = true; try { history.back(); } catch (e) { tkClosing = false; } }
  else tkPushed = false;
  if (tkFrom) { tkFrom.focus(); tkFrom = null; }
}
function bindTicket() {
  if (!tk) return;
  if (desk()) { tk.setAttribute("role", "region"); tk.setAttribute("aria-label", AR ? "التذكرة" : "Ticket"); }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".tm[data-start]");
    if (b) {
      if (b.classList.contains("past")) { e.preventDefault(); return; }
      haptic();
      if (q("[data-tk-rows]", tk)) { e.preventDefault(); tkFrom = b; if (tkPicking) tkAuto = b; else tkUser = true; openTicket(b); }
      return;
    }
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
  window.addEventListener("popstate", function () {
    tkClosing = false;
    if (tk.classList.contains("open")) { tkPushed = false; closeTicket(true); }
    if (tkReopen) { var b = tkReopen; tkReopen = null; tkOpen(b); }
  });
  window.addEventListener("hashchange", showFromHash);
  ticketStart();
}
