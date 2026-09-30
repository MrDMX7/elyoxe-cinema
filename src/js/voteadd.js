/* voteadd.js — lazy chunk (pages/voteadd.py, page_js["*"]): the ticket's «اسأل القروب: أي واحد؟» /
   «+ للتصويت» button (`[data-v-add]`, ticket.actions slot; src/js/ticket.js keeps its data-v-* in step
   with the open show). Queues 2-4 shows in localStorage and shows a floating «التصويت (n) — أرسل» bar
   that opens WhatsApp with a numbered text + the /v/ link. No backend, no tally: same note as vote.js
   -- WhatsApp is the ballot, this only ever builds the link and text on the visitor's own device. */
(function () {
  var STORE = "vote", MAX = 4;
  var W = K.AR ? {
    start: "اسأل القروب: أي واحد؟", add: "+ للتصويت", added: "مُضاف — شيله",
    bar: "التصويت ({n})", send: "أرسل", need: "زد عرض وحد أقل", clear: "امسح",
    ask: "وين نروح؟", reply: "ردّوا بالرقم", aed: "{p} درهم"
  } : {
    start: "Ask the group: which one?", add: "+ Add to vote", added: "Added — remove",
    bar: "Vote ({n})", send: "Send", need: "Add one more show", clear: "Clear",
    ask: "Where to?", reply: "Reply with the number", aed: "{p} AED"
  };

  function vGet() { try { var v = JSON.parse(K.get(STORE) || "[]"); return Array.isArray(v) ? v.slice(0, MAX) : []; } catch (e) { return []; } }
  function vSet(list) { K.set(STORE, JSON.stringify(list)); }

  function itemOf(b) {
    return {
      city: b.getAttribute("data-v-city") || "", date: b.getAttribute("data-v-date") || "",
      key: b.getAttribute("data-v-key") || "", fid: b.getAttribute("data-v-fid") || "",
      title: b.getAttribute("data-v-title") || "", cin: b.getAttribute("data-v-cin") || "",
      time: b.getAttribute("data-v-time") || "",
      price: b.hasAttribute("data-v-price") ? +b.getAttribute("data-v-price") : null
    };
  }
  function idxOf(list, it) {
    for (var i = 0; i < list.length; i++) if (list[i].key === it.key && list[i].fid === it.fid) return i;
    return -1;
  }

  var bar = null, barN, barSend;
  function ensureBar() {
    if (bar) return;
    bar = document.createElement("div");
    bar.className = "v-bar"; bar.hidden = true; bar.setAttribute("role", "status");
    bar.innerHTML = '<span class="v-bar-n" data-v-n></span><button type="button" class="v-bar-send" data-v-send></button>'
      + '<button type="button" class="v-bar-x" data-v-clear aria-label="' + K.esc(W.clear) + '">&times;</button>';
    document.body.appendChild(bar);
    barN = K.q("[data-v-n]", bar); barSend = K.q("[data-v-send]", bar);
    barSend.addEventListener("click", function () {
      var list = vGet();
      if (list.length < 2) return;
      window.open("https://wa.me/?text=" + encodeURIComponent(waMsg(list)), "_blank", "noopener");
    });
    K.q("[data-v-clear]", bar).addEventListener("click", function () { vSet([]); render(); });
  }

  function waMsg(list) {
    var lines = list.map(function (it, i) {
      var price = it.price != null ? (K.AR ? "، " : ", ") + K.sub(W.aed, { p: K.fmt(it.price) }) : "";
      return (i + 1) + ") " + it.title + " " + it.time + (K.AR ? "، " : ", ") + it.cin + price;
    });
    var frag = list.map(function (it) { return [it.city, it.date, it.key, it.fid].join("."); }).join("+");
    return W.ask + "\n" + lines.join("\n") + "\n" + location.origin + K.C.base + "v/#" + frag + "\n" + W.reply;
  }

  function syncButton() {
    var b = K.q("[data-v-add]"); if (!b) return;
    var it = itemOf(b);
    if (!it.key || !it.fid) { b.hidden = true; return; }
    b.hidden = false;
    var idx = idxOf(vGet(), it);
    b.classList.toggle("on", idx >= 0);
    b.textContent = idx >= 0 ? W.added : (vGet().length ? W.add : W.start);
  }

  function render() {
    ensureBar();
    var list = vGet();
    bar.hidden = !list.length;
    if (list.length) {
      barN.textContent = K.sub(W.bar, { n: list.length });
      barSend.disabled = list.length < 2;
      barSend.textContent = list.length < 2 ? W.need : W.send;
    }
    syncButton();
  }

  function toggle(b) {
    var it = itemOf(b); if (!it.key || !it.fid) return;
    var list = vGet(), idx = idxOf(list, it);
    if (idx >= 0) list.splice(idx, 1);
    else { if (list.length >= MAX) return; list.push(it); }
    vSet(list);
    render();
  }

  var addBtn = K.q("[data-v-add]");
  if (addBtn && window.MutationObserver) {
    new MutationObserver(syncButton).observe(addBtn, { attributes: true, attributeFilter: ["data-v-key"] });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-v-add]");
    if (!b) return;
    e.preventDefault();
    toggle(b);
  });
  render();
})();
