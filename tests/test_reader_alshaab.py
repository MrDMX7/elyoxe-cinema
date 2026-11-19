"""Al Shaab Cinema reader (owner 2026-11-19): fixtures/alshaab.json's shape, and each parser on the site's own markup —
no network."""
import json
import re
from pathlib import Path

import pytest

from readers import alshaab
from readers.common import CITIES, HALLS

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "alshaab.json"


@pytest.fixture(scope="module")
def data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_shape(data):
    assert {"cinemas", "shows"} <= set(data) <= {"cinemas", "shows", "price_health"}
    ids = {c["id"] for c in data["cinemas"]}
    assert ids == {"alshaab-al-shaab-village-sharjah"}
    for c in data["cinemas"]:
        assert c["chain"] == "alshaab" and c["city"] in CITIES and c["mall"] and c["address"]
    for s in data["shows"]:
        assert s["cinema"] in ids
        assert re.match(r"^\d{4}-\d\d-\d\d$", s["date"]) and re.match(r"^\d\d:\d\d$", s["time"])
        assert s["hall"] in HALLS
        assert s["book"].startswith("https://www.alshaabcinema.com/Booking/SetSession?")
        assert s["prices"] is None or all(p["seat"] and p["aed"] > 0 for p in s["prices"])
    assert any(s["prices"] for s in data["shows"])


def test_every_fixture_cinema_has_a_display_name_and_coordinates():
    import yaml
    y = yaml.safe_load((FIXTURE.parent.parent / "cinemas.yaml").read_text(encoding="utf-8"))["cinemas"]
    c = y["alshaab-al-shaab-village-sharjah"]
    assert c["ar"].startswith("سينما الشعب") and c["lat"] and c["lng"]


HOME = """
<div id="nowshowing" class="text more"><div class="row movie-tabs">
  <div class="col-md-3 col-sm-4 single-movie">
    <div class="movie-img"><a href="/movies/om-chapter-1-udhiramthe-blood-wood-tamil/1318">
      <img src="/Assets/mthumbnails/OMTamil.jpg" alt="OM -CHAPTER 1: UDHIRAM-THE BLOOD WOOD (TAMIL)" /></a></div>
    <div class="movie-des">
      <div class="col-md-12 no-space"><h3 class="no-underline">OM -CHAPTER 1: UDH...</h3></div>
      <div class="col-md-12 no-space"><span class="title">Adventure | Action</span></div>
      <div class="col-md-6 no-space"><h5 class="no-underline">
          Tamil
      </h5></div>
      <div class="col-md-6 no-space"><span class="certificate">PG 15</span></div>
      <div class="col-md-12 no-space"><p class="bttn-link book-btn"><a href="/movies/om-chapter-1-udhiramthe-blood-wood-tamil/1318#showtimes">Book Now</a></p></div>
    </div>
  </div>
  <div class="col-md-3 col-sm-4 single-movie">
    <div class="movie-img"><a href="/movies/om-chapter-1-udhiramthe-blood-wood-tamil/1318">
      <img src="/Assets/mthumbnails/OMTamil.jpg" alt="OM -CHAPTER 1: UDHIRAM-THE BLOOD WOOD (TAMIL)" /></a></div>
  </div>
</div></div>
"""


def test_home_takes_the_whole_title_from_the_poster_alt_once_per_film():
    films = alshaab.films_from_home(HOME)
    assert len(films) == 1
    f = films[0]
    assert f["id"] == "1318" and f["path"] == "/movies/om-chapter-1-udhiramthe-blood-wood-tamil/1318"
    assert f["title"] == "OM -CHAPTER 1: UDHIRAM-THE BLOOD WOOD (TAMIL)"
    assert f["genres"] == ["Adventure", "Action"] and f["lang"] == "Tamil" and f["rating"] == "PG15"
    assert f["poster"] == "https://www.alshaabcinema.com/Assets/mthumbnails/OMTamil.jpg"


def test_nice_title():
    assert alshaab.nice_title("BACHELOR PARTY D’EUX (MALAYALAM)") == "Bachelor Party D’Eux (Malayalam)"
    assert alshaab.nice_title("Already Mixed Case") == "Already Mixed Case"


FILM = """
<div id="content_hero" class="banner-top"><div class="buttons">
  <span class="certificate">
      3D
  </span>
  <a href="//http://www.youtube.com/watch?v=f7mFVeWnVLw" data-vbtype="video" class="venobox btn">Play trailer</a>
</div></div>
<h2>Synopsis</h2>
<ul class="movie-info"><li><i>Running time</i>2 Hrs 58 Mins</li></ul>
<div id="tabs"><ul><li><a href="#2026-11-20">Today</a></li><li><a href="#2026-11-21">Tomorrow</a></li></ul></div>
"""


def test_film_page():
    assert alshaab.film_page(FILM) == {"dates": ["2026-11-20", "2026-11-21"], "fmt": "3D",
                                       "trailer": "f7mFVeWnVLw", "runtime": 178}


DAY = ("<div class='row'><div class='col-sm-12 col-sm-push-1 theater-name'><p>Al Shaab Village - Sharjah</p>"
       "<ul class='show-times'><li><i>CINEMA 5</i>"
       "<a href = '/Booking/SetSession?mallId=1&showDate=2026-11-20&timeId=63220&movieId=1318&screenId=12' class='time'>06:00AM</a>"
       "<a href = '/Booking/SetSession?mallId=1&showDate=2026-11-20&timeId=63218&movieId=1318&screenId=12' class='time'>08:45PM</a>"
       "<a href = '/Booking/SetSession?mallId=1&showDate=2026-11-20&timeId=63253&movieId=1318&screenId=12' class='time'>12:15AM</a>"
       "</li><li><i>PEARL SUITE</i>"
       "<a href = '/Booking/SetSession?mallId=1&showDate=2026-11-20&timeId=63239&movieId=1318&screenId=13' class='time'>12:00PM</a>"
       "</li></ul></div></div>")


def test_a_day_of_shows_puts_the_after_midnight_show_on_the_next_day_and_a_6am_fan_show_on_its_own():
    got = [(s["screen"], s["date"], s["time"]) for s in alshaab.shows_from_day(DAY, "2026-11-20")]
    assert got == [("CINEMA 5", "2026-11-20", "06:00"), ("CINEMA 5", "2026-11-20", "20:45"),
                   ("CINEMA 5", "2026-11-21", "00:15"), ("PEARL SUITE", "2026-11-20", "12:00")]
    s = alshaab.shows_from_day(DAY, "2026-11-20")[0]
    assert s["theatre"] == "Al Shaab Village - Sharjah"
    assert s["book"] == "https://www.alshaabcinema.com/Booking/SetSession?mallId=1&showDate=2026-11-20&timeId=63220&movieId=1318&screenId=12"
    assert alshaab.shows_from_day("", "2026-11-20") == []


def test_halls():
    assert alshaab.hall_of("PEARL SUITE") == ("SUITES", "Pearl Suite")
    assert alshaab.hall_of("CINEMA 4") == ("Standard", "Standard")


def test_prices_from_the_seat_map_one_per_class_cheapest_first():
    seat = lambda name, aed, extra=0.0, blank=0: {"seat_name": name, "seat_price": aed, "extra_price": extra, "isBlank": blank}
    payload = {"isAvail": 1, "result": [seat("VIP", 52.5), seat("NORMAL", 36.75), seat("NORMAL", 36.75),
                                        seat("", 0, blank=1), seat("NORMAL", 36.75, 5.0)]}
    assert alshaab.prices_from_seats(payload) == [{"seat": "Standard", "aed": 36.75}, {"seat": "VIP", "aed": 52.5}]
    assert alshaab.prices_from_seats({"isAvail": 1, "result": [seat("PEARL SUIT", 105.0)]}) == [{"seat": "Pearl Suite", "aed": 105.0}]
    assert alshaab.prices_from_seats({"isAvail": 0, "url": "/"}) is None


def test_a_theatre_the_reader_does_not_know_still_becomes_a_cinema_in_its_city():
    c = alshaab._cinema("Makani Zakhar Mall - Al Ain")
    assert c["id"] == "alshaab-makani-zakhar-mall-al-ain" and c["city"] == "al-ain" and c["mall"] == "Makani Zakhar Mall"
    with pytest.raises(ValueError):
        alshaab._cinema("Somewhere Unknown")


def test_the_chain_is_registered_everywhere_a_chain_is_listed():
    import alerts
    import refresh
    import yaml
    root = FIXTURE.parent.parent
    assert "alshaab" in refresh.CHAIN_READERS and "alshaab" in refresh.PRICE_CACHE_CHAINS and "alshaab" in alerts.CHAINS
    assert "alshaab" in yaml.safe_load((root / "chains.yaml").read_text(encoding="utf-8"))["chains"]
    assert yaml.safe_load((root / "halls.yaml").read_text(encoding="utf-8"))["chains"]["alshaab"]["name_ar"] == "سينما الشعب"
    assert "alshaab" in (root / ".github/workflows/cinema-refresh.yml").read_text(encoding="utf-8").split("CHAINS:", 1)[1].split("\n", 1)[0]
    assert ".ch-alshaab{" in (root / "app/app.css").read_text(encoding="utf-8")
