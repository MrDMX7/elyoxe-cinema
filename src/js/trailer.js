/* the trailer, with the house lights (W2-P1; MASTER-PLAN §1.3): «الإعلان» dims the hall — the lights go down to .92
   night over 700 ms, the player comes up in 240 ms as they settle, and on close the lights come back up in 450 ms
   (the timings live in ui-lights.css; under reduced motion every light changes at once). A youtube-nocookie player
   made on the tap and destroyed on close (nothing from YouTube loads before). No <dialog> support: the link opens the
   embed in a new tab, as with no script. Its one word is «الإعلان» (TX.bill_tr), on the page and to a screen reader. */
var LIGHTS = null;
function houseLights(down) {
  if (!LIGHTS) {
    LIGHTS = document.createElement("div"); LIGHTS.className = "lights"; LIGHTS.setAttribute("aria-hidden", "true");
    document.body.appendChild(LIGHTS);
    LIGHTS.getBoundingClientRect();   /* laid out at full light first, so the first dimming is a transition too */
  }
  LIGHTS.classList.toggle("down", down);
}
function openTrailer(a) {
  var id = a.getAttribute("data-trailer"), dlg = document.createElement("dialog");
  dlg.className = "trl-d";
  var w = TX.bill_tr || TX.trailer;
  dlg.setAttribute("aria-label", w);
  dlg.innerHTML = '<button type="button" class="trl-x" aria-label="' + esc(TX.close) + '"></button><div class="trl-f"><iframe src="https://www.youtube-nocookie.com/embed/' +
    encodeURIComponent(id) + '?autoplay=1&rel=0&playsinline=1" title="' + esc(w) + '" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>';
  houseLights(true);
  document.body.appendChild(dlg);
  dlg.addEventListener("close", function () { dlg.remove(); houseLights(false); a.focus(); });
  dlg.addEventListener("click", function (e) { if (e.target === dlg || e.target.closest(".trl-x")) dlg.close(); });
  dlg.showModal();
  q(".trl-x", dlg).focus();
}
function bindTrailer() {
  if (typeof HTMLDialogElement !== "function") return;
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-trailer]");
    if (a && !e.ctrlKey && !e.metaKey) { e.preventDefault(); openTrailer(a); }
  });
}
