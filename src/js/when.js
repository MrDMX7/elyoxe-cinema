/* when (pages/venue.py, pages/seasons.py): blocks that come and go with the clock, not with the build. A lazy
   chunk: K is window.CINEMA, and K.now() is the visitor's UAE time (?now= shifts it, as everywhere).
     data-until="2026-09-28T21:00"  hidden from that UAE time on (a double-feature pair once its first film starts);
                                    a bare "21:00" takes its day from the nearest data-d around it
     data-from="2026-09-28T14:00"   hidden until that UAE time (/kids/: tomorrow morning, once today's has passed)
     data-when-group                hidden when none of the timed blocks inside it is left
   The build already leaves out what had passed when it ran; this keeps a page read later honest. */
function when() {
  var n = K.now().getTime();
  K.qa("[data-until],[data-from]").forEach(function (el) {
    var u = el.getAttribute("data-until"), f = el.getAttribute("data-from"), d = el.closest("[data-d]");
    if (u && u.length === 5 && d) u = d.getAttribute("data-d") + "T" + u;
    el.hidden = !!((u && n >= K.uae(u).getTime()) || (f && n < K.uae(f).getTime()));
  });
  K.qa("[data-when-group]").forEach(function (g) {
    g.hidden = !K.qa("[data-until],[data-from]", g).some(function (el) { return !el.hidden; });
  });
}
when();
setInterval(when, 60e3);
