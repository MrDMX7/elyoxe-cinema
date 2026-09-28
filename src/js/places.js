/* places.js: the city and cinema pages' part of the main bundle (W2-P6). Their behaviour is the lazy chunk
   src/js/places-live.js (pages/venue.py LAZY_JS, loaded on those two kinds after start-up), which runs in its own scope:
   this hands it the few things of the bundle it reads (the city's slice, the price after the card, the day names). */
on("ready", function () {
  if (page === "city" || page === "cinema") window.CINEMA.pl = { S: function () { return S; }, best: best, payCell: payCell, day: dayName, TX: TX, RM: RM,
    today: function () { return [TODAY, TOMORROW]; } };
});
