/* fav.js — «سينمتي», the visitor's pinned cinemas (round3-gaps; the W3-P1 package that was to bind the cinema page's
   bookmark never shipped, so the button stayed `hidden` on every page). A lazy chunk (pages/fav.py, every page kind),
   its own scope with K = window.CINEMA. Kept on this phone only, in localStorage «cinema.me»:
     {"cins": [cid, …], "at": {cid: {"c": city, "n": the name as the page showed it}}}
   `cins` is the key src/js/filters.js already reads for «وين: سينمتي» (its option shows once there is one).
   - The cinema page: the bookmark shows, pressed when this cinema is pinned; a tap pins/unpins and says so.
   - K.rankBoost(show): a pinned cinema's show floats first inside the same 10 minutes of the board (board-live.js).
   - «قائمتي» (the header's sheet): the pinned cinemas as links, each with its own «شيل» (unpin). */
(function () {
  var K = window.CINEMA;
  if (!K) return;
  var AR = K.AR;
  function read() {
    try { var m = JSON.parse(localStorage.getItem("cinema.me") || "null"); return m && typeof m === "object" ? m : {}; } catch (e) { return {}; }
  }
  function write(m) { try { localStorage.setItem("cinema.me", JSON.stringify(m)); } catch (e) {} }
  function cins() { var m = read(); return Array.isArray(m.cins) ? m.cins.filter(function (c) { return typeof c === "string"; }) : []; }
  function pinned(cid) { return cins().indexOf(cid) >= 0; }
  function toggle(cid, city, name) {
    var m = read(), list = cins(), i = list.indexOf(cid);
    m.at = m.at && typeof m.at === "object" ? m.at : {};
    if (i >= 0) { list.splice(i, 1); delete m.at[cid]; } else { list.push(cid); m.at[cid] = { c: city || "", n: name || cid }; }
    m.cins = list;
    write(m);
    K.emit("save", cid);
    return i < 0;
  }
  K.rankBoost = function (s) { return s && pinned(s.c) ? 1 : 0; };
  K.favs = cins;

  var b = K.q("[data-fav]");
  if (b) {
    var cid = b.getAttribute("data-fav"), lab = K.q(".fav-l", b), h1 = K.q(".chead .pt");
    var paint = function () {
      var on = pinned(cid);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      if (lab) lab.textContent = b.getAttribute(on ? "data-on" : "data-off");
    };
    paint();
    b.hidden = false;
    b.addEventListener("click", function () {
      toggle(cid, b.getAttribute("data-city"), h1 ? h1.textContent.trim() : cid);
      paint();
    });
  }

  function meList(el) {
    var box = K.q("[data-me-favs]", el);
    if (!box) {
      box = document.createElement("div");
      box.className = "sec me-favs"; box.setAttribute("data-me-favs", "");
      var rows = K.q(".me-rows", el);
      if (rows && rows.parentNode) rows.parentNode.insertBefore(box, rows.nextSibling); else el.appendChild(box);
    }
    var list = cins(), at = read().at || {}, base = K.lang === "en" ? "/en/" : "/";
    if (!list.length) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = '<h3 class="l">' + K.esc(AR ? "سينمتي" : "My cinemas") + "</h3>" + list.map(function (c) {
      var a = at[c] || {}, href = a.c ? base + encodeURIComponent(a.c) + "/" + encodeURIComponent(c) + "/" : null;
      return '<p class="me-fav" style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin:8px 0">' + (href ? '<a href="' + K.esc(href) + '">' + K.esc(a.n || c) + "</a>" : K.esc(a.n || c)) +
        ' <button type="button" class="lnk" data-unfav="' + K.esc(c) + '">' + K.esc(AR ? "شيل" : "Remove") + "</button></p>";
    }).join("");
  }
  K.on("sheet", function (el) { if (el && el.id === "sheet-me") meList(el); });
  document.addEventListener("click", function (e) {
    var x = e.target.closest && e.target.closest("[data-unfav]");
    if (!x) return;
    toggle(x.getAttribute("data-unfav"));
    var sh = x.closest(".sheet");
    if (sh) meList(sh);
    if (b && b.getAttribute("data-fav") === x.getAttribute("data-unfav")) { b.setAttribute("aria-pressed", "false"); var l = K.q(".fav-l", b); if (l) l.textContent = b.getAttribute("data-off"); }
  });
})();
