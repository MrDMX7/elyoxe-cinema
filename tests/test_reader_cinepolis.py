"""Cinépolis UAE reader (owner 2026-11-19): fixtures/cinepolis.json's shape, and each parser on the API's own answers —
no network."""
import json
import re
from pathlib import Path

import pytest

from readers import cinepolis
from readers.common import CITIES, HALLS

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "cinepolis.json"


@pytest.fixture(scope="module")
def data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_shape(data):
    ids = {c["id"] for c in data["cinemas"]}
    assert ids == {"cinepolis-oasis-mall-sharjah"}
    for c in data["cinemas"]:
        assert c["chain"] == "cinepolis" and c["city"] == "sharjah" and c["city"] in CITIES
    for s in data["shows"]:
        assert s["cinema"] in ids and s["hall"] in HALLS
        assert re.match(r"^\d{4}-\d\d-\d\d$", s["date"]) and re.match(r"^\d\d:\d\d$", s["time"])
        assert s["book"].startswith("https://uae.cinepolisgulf.com/movies/HO")
    assert any(s["prices"] for s in data["shows"])


SHOWTIMES = [{"id": "1252", "name": "Oasis Mall - Sharjah", "name_ar": "الواحة مول - الشارقة ", "address": "Level 2, Oasis Mall, Al Wahda street",
              "screenTypes": [
                  {"name": "Standard", "showTimes": [{"sessionId": "1252-144918", "showtime": "2026-11-19T14:30:00.000Z", "sessionDimension": "3D"},
                                                     {"sessionId": "1252-144915", "showtime": "2026-11-19T16:00:00.000Z", "sessionDimension": None},
                                                     {"sessionId": "broken", "showtime": "2026-11-19T18:00:00.000Z"}]},
                  {"name": "Junior", "showTimes": [{"sessionId": "1252-144990", "showtime": "2026-11-20T11:00:00.000Z"}]}]}]


def test_sessions_read_the_false_utc_as_dubai_time_and_split_the_session_id():
    got = [(s["screen"], s["session"], s["date"], s["time"], s["dim"]) for s in cinepolis.sessions(SHOWTIMES)]
    assert got == [("Standard", "144918", "2026-11-19", "14:30", "3D"), ("Standard", "144915", "2026-11-19", "16:00", None),
                   ("Junior", "144990", "2026-11-20", "11:00", None)]


def test_the_cinema_is_in_sharjah_though_its_street_is_al_wahda():
    c = cinepolis._cinema(cinepolis.sessions(SHOWTIMES)[0])
    assert c["id"] == "cinepolis-oasis-mall-sharjah" and c["city"] == "sharjah" and c["mall"] == "Oasis Mall"
    assert c["name_ar"] == "الواحة مول - الشارقة"


def test_halls():
    assert cinepolis.hall_of("Junior") == ("KIDS", "Junior")
    assert cinepolis.hall_of("Standard") == ("Standard", "Standard")


def test_prices_drop_vouchers_and_promos_and_name_the_junior_seats():
    t = lambda d, c, **kw: {"Description": d, "PriceInCents": c, **kw}
    data = {"Tickets": [t("STANDARD", 4000), t("DELUXE", 5000), t("RECLINER", 7000), t("VOUCHER TEST BOGO STD 2D", 3500),
                        t("STANDARD 3D", 4800), t("FREE", 0), t("STAFF", 1000), t("MEMBER", 3000, IsThirdPartyMemberTicket=True)]}
    assert cinepolis.prices_from_tickets(data) == [{"seat": "Standard", "aed": 40.0}, {"seat": "Deluxe", "aed": 50.0},
                                                   {"seat": "Recliner", "aed": 70.0}]
    jr = {"Tickets": [t("JR LOUNGER", 4800), t("JR DBB", 9300)]}
    assert cinepolis.prices_from_tickets(jr) == [{"seat": "Junior Lounger", "aed": 48.0}, {"seat": "Junior Double Bean Bag", "aed": 93.0}]
    assert cinepolis.prices_from_tickets({"Tickets": []}) is None
