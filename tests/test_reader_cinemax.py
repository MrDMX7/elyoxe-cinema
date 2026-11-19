"""Cinemax reader (owner 2026-11-19): Al Shaab's platform with rakcinemax.com handed in — fixtures/cinemax.json's shape,
the site config, and the chains' registration. The parsers themselves are tested in test_reader_alshaab.py."""
import json
import re
from pathlib import Path

import pytest

from readers import alshaab, cinemax
from readers.common import CITIES, HALLS

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def data():
    return json.loads((ROOT / "fixtures" / "cinemax.json").read_text(encoding="utf-8"))


def test_fixture_shape(data):
    ids = {c["id"] for c in data["cinemas"]}
    assert ids == {"cinemax-al-naeem-mall-ras-al-khaimah"}
    for c in data["cinemas"]:
        assert c["chain"] == "cinemax" and c["city"] == "ras-al-khaimah" and c["city"] in CITIES
    for s in data["shows"]:
        assert s["cinema"] in ids and s["hall"] in HALLS
        assert re.match(r"^\d{4}-\d\d-\d\d$", s["date"]) and re.match(r"^\d\d:\d\d$", s["time"])
        assert s["book"].startswith("https://www.rakcinemax.com/booking/setsession?")
    assert any(s["prices"] for s in data["shows"])


def test_the_site_config_names_the_cinema_and_its_links():
    c = alshaab._cinema("Al Naeem Mall - Ras Al Khaimah", cinemax.SITE)
    assert c["id"] == "cinemax-al-naeem-mall-ras-al-khaimah" and c["chain"] == "cinemax" and c["name"] == "Cinemax Al Naeem Mall"
    day = ("<p>Al Naeem Mall - Ras Al Khaimah</p><ul><li><i>SCREEN P1</i>"
           "<a href = '/booking/setsession?mallId=1&showDate=2026-11-20&timeId=10072&movieId=390&screenId=22' class='time'>07:15PM</a></li></ul>")
    s = alshaab.shows_from_day(day, "2026-11-20", cinemax.BASE)[0]
    assert (s["screen"], s["time"]) == ("SCREEN P1", "19:15")
    assert s["book"] == "https://www.rakcinemax.com/booking/setsession?mallId=1&showDate=2026-11-20&timeId=10072&movieId=390&screenId=22"


def test_two_seat_categories_under_one_name_both_keep_their_price():
    seat = lambda name, cat, aed, row: {"seat_name": name, "seat_category_id": cat, "seat_price": aed, "extra_price": 0, "seat_row": row}
    payload = {"isAvail": 1, "result": [seat("NORMAL", 2, 36.75, "D"), seat("NORMAL", 2, 36.75, "E"),
                                        seat("NORMAL", 6, 42.0, "A"), seat("NORMAL", 6, 42.0, "B"), seat("VIP", 3, 52.5, "F")]}
    assert alshaab.prices_from_seats(payload) == [{"seat": "Standard", "aed": 36.75}, {"seat": "Standard (A–B)", "aed": 42.0},
                                                  {"seat": "VIP", "aed": 52.5}]


@pytest.mark.parametrize("chain", ["alshaab", "cinemax", "cinepolis"])
def test_the_new_chains_are_registered_everywhere_a_chain_is_listed(chain):
    import alerts
    import refresh
    import site_kit
    import yaml
    assert chain in refresh.CHAIN_READERS and chain in refresh.PRICE_CACHE_CHAINS and chain in alerts.CHAINS
    assert chain in site_kit.CHAIN_SITE
    assert chain in yaml.safe_load((ROOT / "chains.yaml").read_text(encoding="utf-8"))["chains"]
    assert yaml.safe_load((ROOT / "halls.yaml").read_text(encoding="utf-8"))["chains"][chain]["name_ar"]
    assert chain in (ROOT / ".github/workflows/cinema-refresh.yml").read_text(encoding="utf-8").split("CHAINS:", 1)[1].split("\n", 1)[0].split(",")
    assert f".ch-{chain}{{" in (ROOT / "app/app.css").read_text(encoding="utf-8")
    cins = yaml.safe_load((ROOT / "cinemas.yaml").read_text(encoding="utf-8"))["cinemas"]
    fx = json.loads((ROOT / "fixtures" / f"{chain}.json").read_text(encoding="utf-8"))
    for c in fx["cinemas"]:
        assert cins[c["id"]]["lat"] and cins[c["id"]]["ar"]
