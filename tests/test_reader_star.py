"""Offline shape test for readers/star.py, run against the committed fixture.

No network here — this only checks that a real live run (fixtures/star.json) matches the
Cinema/Show contract in docs/superpowers/plans/2026-09-25-cinema.md.
"""
import json
import re
from pathlib import Path

import pytest

from readers.common import CITIES, HALLS

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "star.json"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@pytest.fixture(scope="module")
def data():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_fixture_has_cinemas_and_shows(data):
    assert data["cinemas"], "fixture must have at least one cinema"
    assert data["shows"], "fixture must have at least one show"


def test_star_cinema_shape(data):
    for c in data["cinemas"]:
        assert c["id"].startswith("star-")
        assert c["chain"] == "star"
        assert c["name"]
        assert c["name_ar"] is None or isinstance(c["name_ar"], str)
        assert c["city"] in CITIES, f"{c['id']} has unknown city {c['city']!r}"
        assert c["mall"] is None or isinstance(c["mall"], str)
        assert isinstance(c["address"], str)
        assert c["maps"] is None or c["maps"].startswith("http")
        assert c["lat"] is None or isinstance(c["lat"], (int, float))
        assert c["lng"] is None or isinstance(c["lng"], (int, float))


def test_star_fixture_shape(data):
    cinema_ids = {c["id"] for c in data["cinemas"]}
    assert cinema_ids, "no cinemas in fixture"

    for s in data["shows"]:
        assert s["cinema"] in cinema_ids, f"show references unknown cinema {s['cinema']!r}"
        assert s["film_title"], "show has no film_title"
        assert s["film_lang"] is None or isinstance(s["film_lang"], str)
        assert s["film_rating"] is None or isinstance(s["film_rating"], str)
        assert s["runtime"] is None or isinstance(s["runtime"], int)

        assert _DATE_RE.match(s["date"]), f"bad date {s['date']!r}"
        assert _TIME_RE.match(s["time"]), f"bad time {s['time']!r}"
        hh, mm = s["time"].split(":")
        assert 0 <= int(hh) <= 23
        assert 0 <= int(mm) <= 59

        assert s["hall"] in HALLS, f"hall {s['hall']!r} not in {HALLS}"
        assert isinstance(s["hall_label"], str) and s["hall_label"]

        assert s["prices"] is None or isinstance(s["prices"], list)
        if isinstance(s["prices"], list):
            assert s["prices"], "prices, if present, must be a non-empty list"
            for p in s["prices"]:
                assert isinstance(p["seat"], str) and p["seat"]
                assert isinstance(p["aed"], (int, float)) and p["aed"] > 0

        assert s["book"].startswith("https://"), f"book url not https: {s['book']!r}"


def test_star_has_at_least_one_priced_show(data):
    # The whole point of reading seat-layout is to get real seat-class prices; a fixture
    # with every show's prices null would mean the pricing path silently broke.
    assert any(s["prices"] for s in data["shows"])


def test_star_covers_multiple_cities(data):
    cities = {c["city"] for c in data["cinemas"]}
    assert len(cities) >= 3, f"expected Star cinemas spread across several cities, got {cities}"
