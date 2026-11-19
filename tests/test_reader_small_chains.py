"""The four small readers of 2026-11-19 (owner: «السلاسل أول»): Cinema Akil, 369 Cinemas, Safeer and Galaxy — each
fixture's shape and each parser on the site's own markup or JSON, no network."""
import base64
import json
import re
from pathlib import Path

import pytest

from readers import akil, cinemas369, galaxy, safeer
from readers.common import CITIES, HALLS

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("chain,ids,book", [
    ("akil", {"akil-alserkal-avenue", "akil-25hours-hotel"}, "https://www.cinemaakil.com/now-showing-booking/"),
    ("cinemas369", {"cinemas369-al-mariah-mall"}, "https://369cinemas.ae/desktop-seat/"),
    ("safeer", {"safeer-dibba"}, "https://www.safeercinemas.com/SelectSeats.aspx?"),
    ("galaxy", {"galaxy-fujairah-mall"}, "https://www.galaxycinemas.ae/SeatLayout.aspx?"),
])
def test_fixture_shape(chain, ids, book):
    data = json.loads((ROOT / "fixtures" / f"{chain}.json").read_text(encoding="utf-8"))
    assert {c["id"] for c in data["cinemas"]} <= ids and data["cinemas"]
    for c in data["cinemas"]:
        assert c["chain"] == chain and c["city"] in CITIES
    for s in data["shows"]:
        assert s["cinema"] in ids and s["hall"] in HALLS and s["book"].startswith(book)
        assert re.match(r"^\d{4}-\d\d-\d\d$", s["date"]) and re.match(r"^\d\d:\d\d$", s["time"])
    assert any(s["prices"] for s in data["shows"])


# ---------------------------------------------------------------- Cinema Akil
AKIL = {"newFilms": [{"id": "1592", "title": "Spirited Away with The Reel Deal Film Club", "image_url": "https://api-v1.cinemaakil.com/x.webp",
                      "buy_tickets_link": "/now-showing-booking/1592/Spirited-Away-with-The-Reel-Deal-Film-Club"}],
        "films": {"Records": [{"movie_id": "1592", "original_movie_title": "Spirited Away with The Reel Deal Film Club", "rating": "PG-13",
                               "runtime": 125, "trailers": [{"trailer_link": "https://youtu.be/ByXuk9QqQkk?si=x"}],
                               "screens": [{"shows": [
                                   {"date": "2026-11-19", "shows": [{"ss_start_show_time": "19:00", "cinema_name": "CINEMA AKIL IN 25HOURS HOTEL",
                                                                     "movie_lang": "Japanese", "sub_lang_1_name": "English", "mf_name": "2D",
                                                                     "schedulePricing": [{"sst_seat_type": "Chairs", "rc_total_amount": 110}]}]},
                                   {"date": "2026-11-25", "shows": [{"ss_start_show_time": "19:00", "cinema_name": "CINEMA AKIL IN 25HOURS HOTEL"}]}]}]}]}}


def test_akil_puts_a_film_club_night_on_its_film_at_its_own_price():
    cins, shows = akil.shows_from(AKIL, {"2026-11-19", "2026-11-20"})
    assert [c["id"] for c in cins] == ["akil-25hours-hotel"]
    assert len(shows) == 1
    s = shows[0]
    assert s["film_title"] == "Spirited Away" and s["film_rating"] == "PG13" and s["lang"] == "ja" and s["subs"] == ["en"]
    assert s["prices"] == [{"seat": "Chairs", "aed": 110.0}] and s["film_trailer"] == "ByXuk9QqQkk"
    assert s["book"] == "https://www.cinemaakil.com/now-showing-booking/1592/Spirited-Away-with-The-Reel-Deal-Film-Club"
    assert akil.film_of("Fjord - TALK TO STRANGERS Moderated by: Asmahan Saleh Khalil") == "Fjord"


# ---------------------------------------------------------------- 369 Cinemas
SEAT_URL = ("https://369cinemas.ae/desktop-seat/e9925b41%26shid%3D24024%26mvid%3D654%26mvname%3DBOUMA"
            "%26timstr%3D2026-11-19+23%3A20%3A00%26dimen%3D3D%26th_id%3D1")


def test_369_reads_its_seat_link_and_seat_page():
    assert cinemas369.seat_link(SEAT_URL) == {"shid": "24024", "date": "2026-11-19", "time": "23:20", "dim": "3D"}
    page = (f"<button onclick=\"handleRedirection('{SEAT_URL}')\" data-id=\"24024\" class=\"x\" data-scid=\"2\" "
            "data-scname=\"Cinema-2\" data-exp=\"2K 7.1\">")
    assert cinemas369.screens_from_seat_page(page) == {"24024": {"scid": "2", "scname": "Cinema-2", "exp": "2K 7.1"}}
    load = {"class": {"4": {"name": "STANDARD", "rate": 36.75, "tdamt": 0, "resamt": 0}, "6": {"name": "VIP", "rate": 47.25},
                      "5": {"name": "PRIME VIEW", "rate": 42, "tdamt": 0, "resamt": 0}}}
    assert cinemas369.prices_from_classes(load) == [{"seat": "Standard", "aed": 36.75}, {"seat": "Prime View", "aed": 42.0},
                                                     {"seat": "VIP", "aed": 47.25}]
    assert cinemas369.clean_title("RAMAYANA: RISE OF A LEGEND (Malayalam)") == "Ramayana: Rise Of A Legend (Malayalam)"
    assert cinemas369.clean_title("AVENGERS DOOMSDAY - INFINITY VISION") == "Avengers Doomsday"
    assert cinemas369.hall_of("Cinema-1", "4K Laser", "AVENGERS DOOMSDAY - INFINITY VISION") == ("OTHER", "Infinity Vision")


# ---------------------------------------------------------------- Safeer
def _enc(v):
    return base64.b64encode(v.encode()).decode().replace("=", "%3d") + "-sig%3d"


def test_safeer_reads_the_signed_date_and_puts_a_late_show_on_the_next_day():
    link = lambda d: f"SelectSeats.aspx?EventID=x&amp;ReqDate={_enc(d)}&amp;CancelURL=y"
    page = ("<div id='tab_1' class='tab-pane active'><h4 style='x'>Safeer Cinemas - Dibba</h4><ul>"
            f"<li><a href={link('2026-11-19')}>11:45 PM <div class='cinema-screen'>Screen-5</div></a></li>"
            f"<li><a href={link('2026-11-19')}>12:30 AM <div class='cinema-screen'>Safeer Elite</div></a></li></ul></div>")
    got = [(s["venue"], s["screen"], s["date"], s["time"]) for s in safeer.shows_from_page(page)]
    assert got == [("Safeer Cinemas - Dibba", "Screen-5", "2026-11-19", "23:45"), ("Safeer Cinemas - Dibba", "Safeer Elite", "2026-11-20", "00:30")]
    assert safeer.b64("MjAyNi0xMS0xOQ%3d%3d-ldlXf%2fyJhvU%3d") == "2026-11-19"
    assert safeer.hall_of("Safeer Elite") == ("VIP", "Safeer Elite") and safeer.hall_of("Screen-2") == ("Standard", "Standard")


def test_safeer_prices_name_an_unnamed_section_by_its_rows_or_by_its_hall():
    sec = lambda name, aed, rows: (f"<div class='section'><div class='section-title premium-title'>{name}</div>"
                                   f"<div class='price-info'>{name} - <span><img src='aed.png'></span>{aed}</div><div class='seat-grid'>"
                                   + "".join(f"<div class='seat-row'><div class='row-label'>{r}</div></div>" for r in rows) + "</div></div> ")
    two = sec("", "42.00", "AB") + sec("STANDARD", "36.75", "CDE")
    assert safeer.prices_from_seats(two) == [{"seat": "Standard", "aed": 36.75}, {"seat": "Rows A–B", "aed": 42.0}]
    assert safeer.prices_from_seats(sec("", "90.00", "ABCDEF"), "Safeer Elite") == [{"seat": "Safeer Elite", "aed": 90.0}]


def test_safeer_details():
    page = ("<h3>Bachelor Party Deux (PG15)</h3>       <p>Malayalam</p>       <h4>Action,Drama</h4>       <h5><span>2D</span></h5>"
            "<a rel='external' href=https://www.youtube.com/watch?v=nY-fbL50LsA title='t'>"
            "<div><b>Rating :</b> PG15</div><div><b>Running Time :</b> 130 min</div><div><b>Language :</b> Malayalam</div>"
            "<div><b>Subtitle(s) :</b> Arabic </div><a href='MovieShowTime.aspx?movieid=Mzk5Mg%3d%3d-x'>")
    d = safeer.details(page)
    assert (d["title"], d["lang"], d["fmt"], d["rating"], d["runtime"], d["trailer"]) == (
        "Bachelor Party Deux", "Malayalam", "2D", "PG15", 130, "nY-fbL50LsA")
    assert d["showtimes"] == "MovieShowTime.aspx?movieid=Mzk5Mg%3d%3d-x" and d["genres"] == ["Action", "Drama"]


# ---------------------------------------------------------------- Galaxy
def test_galaxy_takes_the_show_instant_from_its_link():
    page = ("<h1>HADOOTA</h1><p><span>Genre:</span>Drama,Comedy</p><p><span>Run time:</span>120</p><p><span>Rating:</span>PG-13</p>"
            "<p><span>Language:</span>Arabic</p><a href='' onclick='TrailerLink(\"https://www.youtube.com/embed/ISPqPzVa9go?si=x\");'>"
            "<div class='movieimage'><img src='https://www.galaxycinemas.ae/Admin/MovieImages//283_411/3400.jpg' /></div>"
            "<div><a href='SeatLayout.aspx?cid=a&amp;scheid=b&amp;date=1795026600000&amp;time=1795079400000&amp;levelid=1'>02:40:PM</a></div>"
            "<div><a href='SeatLayout.aspx?cid=a&amp;scheid=c&amp;date=1795026600000&amp;time=1795120200000&amp;levelid=1'>02:00:AM</a></div>")
    fp = galaxy.film_page(page)
    assert (fp["title"], fp["rating"], fp["lang"], fp["runtime"], fp["trailer"]) == ("Hadoota", "PG13", "Arabic", 120, "ISPqPzVa9go")
    assert [(s["date"], s["time"]) for s in fp["shows"]] == [("2026-11-19", "14:40"), ("2026-11-20", "02:00")]
    assert fp["shows"][0]["book"] == "https://www.galaxycinemas.ae/SeatLayout.aspx?cid=a&scheid=b&date=1795026600000&time=1795079400000&levelid=1"
    seat = "<p id='ticdesc0'>VIP</p><p id='pTicAmt0'>AED 42</p><p id='ticdesc1'>STANDARD</p><p id='pTicAmt1'>AED 36.75</p>"
    assert galaxy.prices_from_seat_page(seat) == [{"seat": "Standard", "aed": 36.75}, {"seat": "VIP", "aed": 42.0}]
