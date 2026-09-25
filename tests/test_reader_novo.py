"""Offline shape test for the Novo Cinemas reader — loads fixtures/novo.json, never the network."""
import json
import re
from pathlib import Path

import pytest

from readers.common import CITIES, HALLS

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "novo.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@pytest.fixture(scope="module")
def data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_has_cinemas_and_shows(data):
    assert data["cinemas"], "fixture has no cinemas"
    assert data["shows"], "fixture has no shows"
    assert len(data["shows"]) <= 400


def test_cinemas_shape(data):
    for c in data["cinemas"]:
        assert c["id"].startswith("novo-")
        assert c["chain"] == "novo"
        assert c["name"]
        assert c["city"] in CITIES, f"{c['id']} has bad/missing city {c['city']!r}"
        assert c["mall"]
        assert isinstance(c["address"], str) and c["address"]
        assert c["lat"] is None or isinstance(c["lat"], float)
        assert c["lng"] is None or isinstance(c["lng"], float)


def test_novo_fixture_shape(data):
    cinema_ids = {c["id"] for c in data["cinemas"]}
    assert cinema_ids, "no cinemas to validate shows against"

    for show in data["shows"]:
        assert show["cinema"] in cinema_ids, f"show references unknown cinema {show['cinema']!r}"
        assert show["film_title"]
        assert show["film_lang"] is None or isinstance(show["film_lang"], str)
        assert show["film_rating"] is None or isinstance(show["film_rating"], str)
        assert show["runtime"] is None or (isinstance(show["runtime"], int) and show["runtime"] > 0)
        assert DATE_RE.match(show["date"]), f"bad date {show['date']!r}"
        assert TIME_RE.match(show["time"]), f"bad time {show['time']!r}"
        assert show["hall"] in HALLS, f"bad hall {show['hall']!r}"
        assert show["hall_label"]

        prices = show["prices"]
        assert prices is None or isinstance(prices, list)
        if prices:
            for p in prices:
                assert isinstance(p["seat"], str) and p["seat"]
                assert isinstance(p["aed"], (int, float)) and p["aed"] > 0

        assert show["book"].startswith("https://"), f"bad book url {show['book']!r}"


def test_all_novo_shows_are_standard_or_known_hall(data):
    # Regression guard: every hall_label seen so far ("2D") should map to a real HALLS entry,
    # not silently fall through — if Novo ever adds IMAX/4DX this should still pass.
    for show in data["shows"]:
        assert show["hall"] in HALLS
