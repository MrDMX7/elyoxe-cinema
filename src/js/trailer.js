/* the trailer: a youtube-nocookie player made on the tap and destroyed on close (nothing from YouTube
   loads before). No <dialog> support: the link opens the embed in a new tab, as with no script. */
function openTrailer(a) {
  var id = a.getAttribute("data-trailer"), dlg = document.createElement("dialog");
  dlg.className = "trl-d";
  dlg.setAttribute("aria-label", TX.trailer);
  dlg.innerHTML = '<button type="button" class="trl-x" aria-label="' + esc(TX.close) + '"></button><div class="trl-f"><iframe src="https://www.youtube-nocookie.com/embed/' +
    encodeURIComponent(id) + '?autoplay=1&rel=0&playsinline=1" title="' + esc(TX.trailer) + '" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>';
  document.body.appendChild(dlg);
  dlg.addEventListener("close", function () { dlg.remove(); a.focus(); });
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
