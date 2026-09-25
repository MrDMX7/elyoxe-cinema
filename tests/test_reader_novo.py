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


# --- Task 1c: live prices + failure paths -------------------------------------------------

class _Resp:
    def __init__(self, status=200, payload=None, text="", url=""):
        self.status_code, self._payload, self.text, self.url = status, payload, text, url

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_novo_fixture_has_live_prices(data):
    priced = [s for s in data["shows"] if s["prices"]]
    assert priced, "no priced show: the seat-layout sample failed for every hall"
    for s in priced:
        assert all(p["aed"] > 0 for p in s["prices"])


def test_novo_unknown_label_is_other_not_standard():
    from readers.novo import _hall_for

    assert _hall_for("2D") == "Standard"
    assert _hall_for("3D") == "Standard"
    assert _hall_for("IMAX 2D") == "IMAX"
    assert _hall_for("Dolby Cinema") == "OTHER"


def test_novo_raises_when_sessions_are_blocked(monkeypatch):
    from readers import novo

    class FakePolite:
        def __init__(self, *a, **k):
            pass

        def get(self, url, params=None, **k):
            if url.endswith("/cinemas"):
                return _Resp(200, {"data": [{"name": "Dragon Mart", "name_ar": "", "lat": "", "long": "", "address": ""}]})
            if url.endswith("/movies"):
                return _Resp(200, {"data": {"movies": [{"movie_id": 1, "movie_title": "X"}]}})
            return _Resp(403, {"message": "Forbidden"})

    monkeypatch.setattr(novo, "Polite", FakePolite)
    with pytest.raises(RuntimeError):
        novo.fetch(days=2)
