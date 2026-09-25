"""Offline fixture test for the VOX Cinemas UAE reader.

Loads fixtures/vox.json (a real live run, saved to disk) and asserts every
show's shape matches the Show/Cinema contract in docs/superpowers/plans/2026-09-25-cinema.md.
No network access here — the reader itself (readers/vox.py) is exercised
separately and its output saved as the fixture.
"""
import json
import re
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from readers.common import CITIES, HALLS

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "vox.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@pytest.fixture(scope="module")
def data():
    assert FIXTURE.exists(), f"missing fixture: {FIXTURE}"
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_vox_fixture_shape(data):
    assert "cinemas" in data and "shows" in data
    cinemas = data["cinemas"]
    shows = data["shows"]
    assert len(cinemas) >= 1
    assert len(shows) >= 1
    assert len(shows) <= 400

    cinema_ids = {c["id"] for c in cinemas}
    assert len(cinema_ids) == len(cinemas), "duplicate cinema ids"

    for c in cinemas:
        assert c["id"].startswith("vox-")
        assert c["chain"] == "vox"
        assert c["name"]
        assert c["city"] in CITIES, f"unknown city {c['city']!r} for cinema {c['id']}"
        assert c["mall"]
        assert c["address"]

    for s in shows:
        assert s["cinema"] in cinema_ids, f"show references unknown cinema {s['cinema']!r}"
        assert s["film_title"]
        assert DATE_RE.match(s["date"]), f"bad date {s['date']!r}"
        assert TIME_RE.match(s["time"]), f"bad time {s['time']!r}"
        assert s["hall"] in HALLS, f"unknown hall {s['hall']!r}"
        assert s["hall_label"]

        prices = s["prices"]
        if prices is not None:
            assert isinstance(prices, list) and len(prices) >= 1
            for p in prices:
                assert p["seat"]
                assert isinstance(p["aed"], (int, float)) and p["aed"] > 0

        assert s["book"], "show has no booking link"
        assert s["book"].startswith("https://"), f"book link not https: {s['book']!r}"

        if s["film_rating"] is not None:
            assert isinstance(s["film_rating"], str) and s["film_rating"]
        if s["runtime"] is not None:
            assert isinstance(s["runtime"], int) and s["runtime"] > 0
        if s["film_lang"] is not None:
            assert isinstance(s["film_lang"], str) and s["film_lang"]


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


def test_vox_fixture_has_live_prices(data):
    priced = [s for s in data["shows"] if s["prices"]]
    assert priced, "no priced show: the seat-map legend sample failed for every hall"
    assert {c["id"] for c in data["cinemas"]} == {s["cinema"] for s in data["shows"]}, "a cinema lost its shows"


def test_vox_hall_label_has_no_tooltip_text(data):
    for s in data["shows"]:
        assert "customized" not in s["hall_label"], s["hall_label"]


def test_vox_legend_prices_parse():
    from readers.vox import _legend_prices

    html = ('<ul><li class="seat sold" data-label="Unavailable"></li>'
            '<li class="seat standard" data-area="2" data-label="Regular" data-price="50.00 AED per ticket"></li>'
            '<li class="seat preferred-view" data-area="14" data-label="Preferred View" data-price="75.00 AED per ticket"></li></ul>')
    assert _legend_prices(html) == [{"seat": "Regular", "aed": 50.0}, {"seat": "Preferred View", "aed": 75.0}]


def test_vox_raises_when_showtimes_blocked(monkeypatch):
    from readers import vox

    listing = ('<article class="cinema-summary" data-slug="yas-mall"><h3><a>Yas Mall</a></h3>'
               '<p>Address: Yas Island, Abu Dhabi</p><a href="/showtimes/yas-mall">Showtimes</a></article>')

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def get(self, url, **k):
            if url.endswith("/cinemas"):
                return _Resp(200, text=listing, url=url)
            return _Resp(403, text="", url=url)

    monkeypatch.setattr(vox, "_Client", FakeClient)
    with pytest.raises(RuntimeError):
        vox.fetch(days=2)
