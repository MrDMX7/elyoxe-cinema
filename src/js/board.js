/* «اللوحة» in the bundle: only what the board's lazy half (src/js/board-live.js) reads from here, as K.bd (legend W2-P2a).
   The board itself is drawn before the first paint by src/js/board-paint.js (inline on home and the 404, a lazy chunk
   on a city or a cinema page), so the initial bundle carries none of it (MASTER-PLAN §7.2: the bundle's headroom). */
on("ready", function () {
  window.CINEMA.bd = { S: function () { return S; }, loc: function () { return LOC; }, G: function () { return G; }, pc: pageCity,
    days: function () { return [TODAY, TOMORROW]; }, day: daySlice, km: kmTo, kmt: kmText, nm: nm, price: priceHTML, lows: lows, sheet: sheetOpen, geo: geo };
});
