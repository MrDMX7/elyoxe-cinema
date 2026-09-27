/* search.js — phase 3, task A5: bilingual fuzzy search over /data/search.json (pages/search.py). A lazy
   chunk (docs/PLUGINS.md), loaded on every page (page_js "*"), so this file runs once per page and owns its
   panel: the page's own [data-search] triggers open it (the header's search button and the phone tab bar's
   «بحث», UI redesign Task 2; a page without one gets a button injected into .top-in as before), a "/"
   shortcut, and a panel with an ARIA combobox. Focus goes back to whichever trigger opened it. K is window.CINEMA: q, qa, esc, getJSON, lang, AR, C, get/set, now(), city(), card(). */
var AR = K.AR, esc = K.esc, q = K.q, qa = K.qa;
var STR = AR ? {
    ph: "دور على فيلم، سينما أو أحد الطاقم…", open: "بحث", close: "سكّر",
    films: "أفلام", cinemas: "سينمات", people: "ناس", archived: "انتهى عرضه",
    empty: "ما لقينا شي يطابق بحثك — جرّب كلمة غير."
  } : {
    ph: "Search a film, cinema or someone in the cast…", open: "Search", close: "Close",
    films: "Films", cinemas: "Cinemas", people: "People", archived: "No longer showing",
    empty: "Nothing matches your search — try a different word."
  };

  /* ---- the same fold pages/search.py's normalize() applies at build time ---- */
  var DIA = /[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ࣓-࣡ـ]/g;
  var ALEF = /[إأآٱ]/g;
  var KEEP = /[^a-z0-9ء-ي]/g;
  function norm(s) {
    s = String(s == null ? "" : s).normalize("NFKC").toLowerCase();
    s = s.replace(DIA, "").replace(ALEF, "ا");
    s = s.replace(/ة/g, "ه").replace(/ى/g, "ي").replace(/ؤ/g, "و").replace(/ئ/g, "ي").replace(/ء/g, "");
    return s.replace(KEEP, "");
  }

  /* bounded Levenshtein: never explores past `max`, so a bad candidate bails in O(max*len) not O(n*m) */
  function bounded(a, b, max) {
    if (a === b) return 0;
    var la = a.length, lb = b.length;
    if (Math.abs(la - lb) > max) return max + 1;
    var prev = [];
    for (var j = 0; j <= lb; j++) prev[j] = j;
    for (var i = 1; i <= la; i++) {
      var cur = [i], best = i;
      for (j = 1; j <= lb; j++) {
        var cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        cur[j] = v;
        if (v < best) best = v;
      }
      if (best > max) return max + 1;
      prev = cur;
    }
    return prev[lb];
  }

  function score(query, keys) {
    var best = -1;
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (!k) continue;
      if (k === query) { best = Math.max(best, 100); continue; }
      if (k.indexOf(query) === 0) { best = Math.max(best, 80); continue; }
      if (k.indexOf(query) !== -1) { best = Math.max(best, 60); continue; }
      var max = query.length <= 3 ? 0 : query.length <= 8 ? 1 : 2;
      if (max > 0) {
        var d = bounded(query, k, max);
        if (d <= max) best = Math.max(best, 40 - d * 8);
      }
    }
    return best;
  }

  var DATA = null, LOADING = null;
  function load() {
    if (DATA) return Promise.resolve(DATA);
    LOADING = LOADING || K.getJSON("/data/search.json").then(function (j) { DATA = j || []; return DATA; });
    return LOADING;
  }

  function href(p) { return K.C.base + p + "/"; }

  function icon(t) {
    return '<span class="srch-i srch-i-' + t + '" aria-hidden="true"></span>';
  }

  function thumb(item) {
    if (item.i) return '<img src="' + esc(item.i) + '" alt="" width="32" height="40" loading="lazy" decoding="async">';
    return icon(item.t);
  }

  function name(item) {
    return (AR ? item.a : item.e) || item.a || item.e || "";
  }

  var GROUPS = [
    { key: "f", label: STR.films },
    { key: "cm", label: STR.cinemas },
    { key: "p", label: STR.people }
  ];
  function groupOf(t) { return t === "c" || t === "m" ? "cm" : t; }

  var panel, input, list, empty, btn, opener = null, activeId = -1, items = [];

  function render(matches) {
    items = matches;
    var byGroup = {};
    matches.forEach(function (m) {
      var g = groupOf(m.t);
      (byGroup[g] = byGroup[g] || []).push(m);
    });
    var html = "", n = 0;
    GROUPS.forEach(function (g) {
      var rows = byGroup[g.key];
      if (!rows || !rows.length) return;
      var gid = "srch-g-" + g.key, opts = "";
      rows.slice(0, 8).forEach(function (m) {
        var id = "srch-opt-" + n++;
        var arch = m.x ? '<small class="srch-arc">' + esc(STR.archived) + "</small>" : "";
        opts += '<li id="' + id + '" role="option" class="srch-r' + (m.x ? " srch-r-x" : "") + '" data-p="' + esc(m.p) + '">'
          + '<a tabindex="-1" href="' + esc(href(m.p)) + '">' + thumb(m)
          + '<span' + (AR && !m.a ? ' lang="en" dir="ltr"' : "") + ">" + esc(name(m)) + "</span>" + arch + "</a></li>";
      });
      /* a labelled ARIA group under the listbox, not a plain unlabelled heading row */
      html += '<li role="group" aria-labelledby="' + gid + '"><p id="' + gid + '" class="srch-g">' + esc(g.label)
        + '</p><ul class="srch-g-rows">' + opts + "</ul></li>";
    });
    list.innerHTML = html;
    activeId = -1;
    input.removeAttribute("aria-activedescendant");
    var has = n > 0;
    input.setAttribute("aria-expanded", has ? "true" : "false");
    empty.textContent = matches.length === 0 && input.value.trim() ? STR.empty : "";
  }

  function search(raw) {
    var query = norm(raw);
    if (!query) { render([]); return; }
    if (!DATA) { load().then(function () { search(raw); }); return; }
    var scored = [];
    for (var i = 0; i < DATA.length; i++) {
      var s = score(query, DATA[i].k || []);
      if (s >= 0) scored.push({ s: s, e: DATA[i] });
    }
    /* a showing match always outranks an archived one, whatever their scores -- the archived film is
       still found (its page is real and useful), just never ahead of one you can actually watch */
    scored.sort(function (x, y) {
      var ax = x.e.x ? 1 : 0, ay = y.e.x ? 1 : 0;
      return ax !== ay ? ax - ay : y.s - x.s;
    });
    render(scored.slice(0, 40).map(function (x) { return x.e; }));
  }

  function options() { return qa('[role="option"]', list); }

  function move(dir) {
    var opts = options();
    if (!opts.length) return;
    var i = opts.findIndex(function (o) { return o.id === input.getAttribute("aria-activedescendant"); });
    i = i < 0 ? (dir > 0 ? 0 : opts.length - 1) : (i + dir + opts.length) % opts.length;
    opts.forEach(function (o) { o.removeAttribute("aria-selected"); });
    opts[i].setAttribute("aria-selected", "true");
    input.setAttribute("aria-activedescendant", opts[i].id);
    opts[i].scrollIntoView({ block: "nearest" });
  }

  function go(el) {
    var p = el && el.getAttribute("data-p");
    if (p) location.href = href(p);
  }

  function open(e) {
    if (e && e.preventDefault) e.preventDefault();
    opener = (e && e.currentTarget) || btn;
    panel.hidden = false;
    document.documentElement.classList.add("srch-open");
    input.value = "";
    render([]);
    setTimeout(function () { input.focus(); }, 0);
    load();
  }

  function close() {
    panel.hidden = true;
    document.documentElement.classList.remove("srch-open");
    (opener || btn).focus();
  }

  function build() {
    var triggers = qa("[data-search]");
    if (!triggers.length) {
      var host = q(".top-in");
      if (!host) return;
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "srch-btn";
      btn.setAttribute("aria-haspopup", "dialog");
      btn.setAttribute("aria-label", STR.open);
      var alt = q(".alt", host);
      host.insertBefore(btn, alt || null);
      triggers = [btn];
    }
    btn = btn || triggers[0];
    triggers.forEach(function (t) { t.setAttribute("aria-controls", "srch"); });

    panel = document.createElement("div");
    panel.id = "srch";
    panel.className = "srch";
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-label", STR.open);
    panel.innerHTML = '<div class="srch-box"><div class="srch-in">'
      + '<input type="text" id="srch-input" role="combobox" aria-autocomplete="list" aria-expanded="false"'
      + ' aria-controls="srch-list" autocomplete="off" placeholder="' + esc(STR.ph) + '">'
      + '<button type="button" class="srch-x" id="srch-close" aria-label="' + esc(STR.close) + '"></button>'
      + '</div><ul id="srch-list" class="srch-list" role="listbox"></ul>'
      + '<p class="srch-empty" id="srch-empty" aria-live="polite"></p></div>';
    document.body.appendChild(panel);

    input = q("#srch-input", panel);
    list = q("#srch-list", panel);
    empty = q("#srch-empty", panel);

    triggers.forEach(function (t) { t.addEventListener("click", open); });
    q("#srch-close", panel).addEventListener("click", close);
    panel.addEventListener("click", function (e) { if (e.target === panel) close(); });
    input.addEventListener("input", function () { search(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { close(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") { e.preventDefault(); go(q('[aria-selected="true"]', list)); }
    });
    list.addEventListener("click", function (e) {
      var li = e.target.closest ? e.target.closest('[role="option"]') : null;
      if (li) { e.preventDefault(); go(li); }
    });
    document.addEventListener("keydown", function (e) {
      var t = e.target || {}, tag = t.tagName || "";
      if (panel.hidden && e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(tag) && !t.isContentEditable) {
        e.preventDefault(); open();
      } else if (!panel.hidden && e.key === "Escape") {
        close();
      }
    });
  }

build();
