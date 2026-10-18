/* «اسأل الفيلم» (pages/ask.py): the film page's question box. A lazy chunk (K = window.CINEMA): it sends {fid, q, lang,
   uid} to the backend (__ASK_API__, filled at bundle time from counter.yaml's ask_api), and draws the answer above the
   earlier ones — a spoiler behind a <details> «يحرق — اضغط إذا تبا تعرف», closed until the visitor opens it. uid is the
   same on-device daily value the counter uses (cinema.salt), so one visitor's daily cap holds without any id. */
(function () {
  var API = "__ASK_API__";
  var box = K.q("[data-ask]");
  if (!box || !API || API.indexOf("__") === 0 || typeof fetch !== "function") return;
  box.hidden = false;
  var W = K.AR ? { wait: "لحظة…", spoil: "يحرق — اضغط إذا تبا تعرف", none: "ما عندنا هالمعلومة عن الفيلم للحين.",
                   cap: "وصلنا حد الأسئلة لليوم، جرّب بكرة.", off: "«اسأل الفيلم» متوقف شوي، جرّب بعدين.", err: "ما قدرنا نجاوب الحين، جرّب مرة ثانية.",
                   from: { plot: "من قصة الفيلم", facts: "من معلومات الفيلم" } }
    : { wait: "One moment…", spoil: "Spoiler — tap to read", none: "We don't have that about this film yet.",
        cap: "That's today's limit of questions — try again tomorrow.", off: "Ask the film is paused for now.", err: "Couldn't answer just now, try again.",
        from: { plot: "From the film's story", facts: "From the film's facts" } };
  var form = K.q("[data-ask-form]", box), input = K.q("input", form), btn = K.q("button[type=submit]", form), out = K.q("[data-ask-out]", box);
  var fid = box.getAttribute("data-fid"), busy = false;
  function uid() { try { return localStorage.getItem("cinema.salt") || ""; } catch (e) { return ""; } }
  function item(q, html, cls) {
    var d = document.createElement("div");
    d.className = "ask-a" + (cls ? " " + cls : "");
    d.innerHTML = '<p class="ask-qq">' + K.esc(q) + "</p>" + html;
    out.insertBefore(d, out.firstChild);
    while (out.children.length > 6) out.removeChild(out.lastChild);
    return d;
  }
  function ask(q) {
    q = String(q || "").trim();
    if (busy || q.length < 2) return;
    busy = true; btn.disabled = true;
    var d = item(q, '<p class="ask-w">' + K.esc(W.wait) + "</p>", "pending");
    fetch(API + "ask", { method: "POST", headers: { "Content-Type": "application/json" },
                         body: JSON.stringify({ fid: fid, q: q, lang: K.AR ? "ar" : "en", uid: uid() }) })
      .then(function (r) { return r.json().then(function (j) { return { s: r.status, j: j }; }, function () { return { s: r.status, j: {} }; }); })
      .then(function (x) {
        var j = x.j || {}, html;
        if (x.s === 429) html = '<p class="ask-e">' + K.esc(W.cap) + "</p>";
        else if (x.s === 503) html = '<p class="ask-e">' + K.esc(W.off) + "</p>";
        else if (x.s !== 200 || !j.answer) html = '<p class="ask-e">' + K.esc(W.err) + "</p>";
        else {
          var src = j.known && W.from[j.source] ? '<small class="ask-src">' + K.esc(W.from[j.source]) + "</small>" : "";
          var body = '<p class="ask-t">' + K.esc(j.answer) + "</p>" + src;
          html = j.spoiler ? '<details class="ask-sp"><summary>' + K.esc(W.spoil) + "</summary>" + body + "</details>" : body;
        }
        d.className = "ask-a"; d.innerHTML = '<p class="ask-qq">' + K.esc(q) + "</p>" + html;
      })
      .catch(function () { d.className = "ask-a"; d.innerHTML = '<p class="ask-qq">' + K.esc(q) + '</p><p class="ask-e">' + K.esc(W.err) + "</p>"; })
      .then(function () { busy = false; btn.disabled = false; });
  }
  form.addEventListener("submit", function (e) { e.preventDefault(); ask(input.value); input.value = ""; });
  box.addEventListener("click", function (e) {
    var c = e.target.closest && e.target.closest("[data-ask-q]");
    if (c) ask(c.getAttribute("data-ask-q"));
  });
})();
