/* PWA: the service worker (/sw.js) and a quiet «ثبّت سينما على شاشتك», offered only from the second visit
   on, only when the browser can install, and never again once declined. */
function bindPWA() {
  if ("serviceWorker" in navigator) window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); });
  var visits = +get("visits") || 0;
  try { if (!window.sessionStorage.getItem("cinema.seen")) { window.sessionStorage.setItem("cinema.seen", "1"); set("visits", ++visits); } } catch (e) {}
  window.addEventListener("beforeinstallprompt", function (ev) {
    ev.preventDefault();
    if (visits < 2 || get("noinstall")) return;
    var bar = document.createElement("div");
    bar.className = "inst"; bar.setAttribute("role", "region"); bar.setAttribute("aria-label", TX.install);
    bar.innerHTML = "<span>" + esc(TX.install) + '</span><button type="button" class="chip" data-i="1">' + esc(TX.install_yes) + '</button><button type="button" class="lnk" data-i="0">' + esc(TX.install_no) + "</button>";
    document.body.appendChild(bar);
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("[data-i]"); if (!b) return;
      if (b.getAttribute("data-i") === "1") ev.prompt(); else set("noinstall", "1");
      bar.remove();
    });
  });
}
