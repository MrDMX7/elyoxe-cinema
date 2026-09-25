"""Offline fixture test for the Cine Royal reader — no network calls.

Loads fixtures/cineroyal.json (one real live run of readers/cineroyal.fetch())
and checks the shape every reader must produce: shows reference a real
cinema id, date/time formats, hall enum membership, city enum membership,
prices shape, and an https booking link.
"""
import json
import re
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "cineroyal.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")

try:
    from readers.common import CITIES, HALLS
except ImportError:  # pragma: no cover - readers/common.py is required for this repo
    CITIES, HALLS = [], []


@pytest.fixture(scope="module")
def data():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_fixture_exists_and_has_both_top_level_keys(data):
    assert set(data.keys()) == {"cinemas", "shows"}
    assert isinstance(data["cinemas"], list) and len(data["cinemas"]) > 0
    assert isinstance(data["shows"], list) and len(data["shows"]) > 0


def test_shows_under_cap(data):
    assert len(data["shows"]) <= 400


def test_cinemas_shape(data):
    for c in data["cinemas"]:
        assert c["id"].startswith("cineroyal-")
        assert c["chain"] == "cineroyal"
        assert isinstance(c["name"], str) and c["name"]
        assert c["name_ar"] is None or isinstance(c["name_ar"], str)
        assert c["city"] in CITIES, f"unknown city {c['city']!r} for {c['id']}"
        assert isinstance(c["mall"], str) and c["mall"]
        assert isinstance(c["address"], str) and c["address"]
        assert c["maps"] is None or isinstance(c["maps"], str)
        assert c["lat"] is None or isinstance(c["lat"], (int, float))
        assert c["lng"] is None or isinstance(c["lng"], (int, float))


def test_every_cinema_has_a_city(data):
    for c in data["cinemas"]:
        assert c["city"], f"{c['id']} has no city"


def test_five_uae_cinemas_present(data):
    ids = {c["id"] for c in data["cinemas"]}
    expected = {
        "cineroyal-khalidiyah-mall",
        "cineroyal-dalma-mall",
        "cineroyal-al-dhannah-mall",
        "cineroyal-deerfields-mall",
        "cineroyal-wtc-mall-abu-dhabi",
    }
    assert expected <= ids


def test_shows_reference_known_cinema(data):
    cinema_ids = {c["id"] for c in data["cinemas"]}
    for sh in data["shows"]:
        assert sh["cinema"] in cinema_ids, f"show references unknown cinema {sh['cinema']!r}"


def test_show_date_format(data):
    for sh in data["shows"]:
        assert DATE_RE.match(sh["date"]), f"bad date {sh['date']!r}"


def test_show_time_format(data):
    for sh in data["shows"]:
        assert TIME_RE.match(sh["time"]), f"bad time {sh['time']!r}"
        hh, mm = sh["time"].split(":")
        assert 0 <= int(hh) <= 23
        assert 0 <= int(mm) <= 59


def test_show_hall_in_enum(data):
    for sh in data["shows"]:
        assert sh["hall"] in HALLS, f"hall {sh['hall']!r} not in {HALLS}"


def test_show_hall_label_present(data):
    for sh in data["shows"]:
        assert isinstance(sh["hall_label"], str) and sh["hall_label"]


def test_show_prices_shape(data):
    for sh in data["shows"]:
        prices = sh["prices"]
        if prices is None:
            continue
        assert isinstance(prices, list) and len(prices) > 0
        for p in prices:
            assert isinstance(p["seat"], str) and p["seat"]
            assert isinstance(p["aed"], (int, float))
            assert p["aed"] > 0


def test_show_book_is_https(data):
    for sh in data["shows"]:
        assert sh["book"].startswith("https://")


def test_show_film_title_present(data):
    for sh in data["shows"]:
        assert isinstance(sh["film_title"], str) and sh["film_title"]


def test_show_optional_fields_types(data):
    for sh in data["shows"]:
        assert sh["film_lang"] is None or isinstance(sh["film_lang"], str)
        assert sh["film_rating"] is None or isinstance(sh["film_rating"], str)
        assert sh["runtime"] is None or isinstance(sh["runtime"], int)


def test_at_least_some_shows_are_priced(data):
    priced = [sh for sh in data["shows"] if sh["prices"]]
    assert len(priced) > 0, "expected at least some shows to carry prices"


def test_fetch_is_importable():
    from readers.cineroyal import fetch
    assert callable(fetch)
