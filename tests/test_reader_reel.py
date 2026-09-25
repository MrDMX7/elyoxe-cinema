"""Offline fixture test for the Reel Cinemas UAE reader.

Loads fixtures/reel.json (a real live run, saved to disk) and asserts every
show's shape matches the Show/Cinema contract in docs/superpowers/plans/2026-09-25-cinema.md.
No network access here — the reader itself (readers/reel.py) is exercised
separately and its output saved as the fixture.
"""
import json
import re
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from readers.common import CITIES, HALLS

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "reel.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@pytest.fixture(scope="module")
def data():
    assert FIXTURE.exists(), f"missing fixture: {FIXTURE}"
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_reel_fixture_shape(data):
    assert "cinemas" in data and "shows" in data
    cinemas = data["cinemas"]
    shows = data["shows"]
    assert len(cinemas) >= 1
    assert len(shows) >= 1
    assert len(shows) <= 400

    cinema_ids = {c["id"] for c in cinemas}
    assert len(cinema_ids) == len(cinemas), "duplicate cinema ids"

    for c in cinemas:
        assert c["id"].startswith("reel-")
        assert c["chain"] == "reel"
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


def test_reel_fixture_has_live_prices(data):
    priced = [s for s in data["shows"] if s["prices"]]
    assert priced, "no priced show: the guest getSeatLayout sample failed for every hall"


def test_reel_no_vox_brands(data):
    assert not {s["hall"] for s in data["shows"]} & {"MAX", "GOLD"}


def test_reel_hall_mapping():
    from readers.reel import _hall_of

    assert _hall_of({"SessionAttributesNames": ["INFINITY V", "DOLBY"], "ScreenName": "Screen 2 Dolby"})[0] == "OTHER"
    assert _hall_of({"SessionAttributesNames": ["2D", "PREMIUM"], "ScreenName": "Premium 15"})[0] == "VIP"
    assert _hall_of({"SessionAttributesNames": ["2D", "PLATINUM"], "ScreenName": "Platinum 1"})[0] == "SUITES"


def test_reel_raises_on_zero_shows(monkeypatch):
    from readers import reel

    class FakePolite:
        def __init__(self, *a, **k):
            pass

        def get(self, url, **k):
            if url.endswith("Cinemas.json"):
                return _Resp(200, {"value": [{"ID": "0001", "Name": "Dubai Mall", "CinemaNationalId": "UAE"}]})
            return _Resp(200, {"value": []})

    monkeypatch.setattr(reel, "Polite", FakePolite)
    with pytest.raises(RuntimeError):
        reel.fetch(days=2, prices=False)


# --- Review round 2: price_health + behavioural tests ---------------------------------------

def _assert_health(out, attempted=None, priced=None, error_is_none=True):
    h = out["price_health"]
    assert set(h) == {"attempted", "priced", "error"}
    assert isinstance(h["attempted"], int) and isinstance(h["priced"], int)
    assert 0 <= h["priced"] <= h["attempted"]
    if attempted is not None:
        assert h["attempted"] == attempted
    if priced is not None:
        assert h["priced"] == priced
    if error_is_none:
        assert h["error"] is None
    else:
        assert isinstance(h["error"], str) and h["error"]


def test_reel_unknown_screen_has_its_own_price_key():
    from readers.reel import _hall_of

    hall, _, code = _hall_of({"SessionAttributesNames": ["2D"], "ScreenName": "Screen 99"})
    assert hall == "OTHER" and code != "STANDARD"


def test_reel_cancel_order_always_called_even_on_failure(monkeypatch):
    from readers import reel

    pc = reel._PriceClient()
    paths = []

    def fake_call(method, path, **kw):
        paths.append(path)
        if path.startswith("seats/getSeatLayout"):
            return _Resp(200, {"statusCode": 11, "statusMessage": "problem"})
        if path == "order/cancelOrder":
            return _Resp(500, {"code": 500})
        return _Resp(200, {})

    monkeypatch.setattr(pc, "_call", fake_call)
    with pytest.raises(reel._SampleError):
        pc.sample("0001", "1", "STANDARD", "Screen 1")
    assert paths[-1] == "order/cancelOrder"


def test_reel_price_health_login_failure_sets_error(monkeypatch, capsys):
    import datetime as _dt
    from zoneinfo import ZoneInfo
    from readers import reel

    tmrw = (_dt.datetime.now(ZoneInfo("Asia/Dubai")) + _dt.timedelta(days=1)).date().isoformat()
    feeds = {
        "Cinemas.json": {"value": [{"ID": "0001", "Name": "Dubai Mall", "CinemaNationalId": "UAE"}]},
        "Films.json": {"value": [{"ID": "F1", "Title": "X"}]},
        "Sessions.json": {"value": [{"CinemaId": "0001", "SessionId": "7", "ScheduledFilmId": "F1",
                                     "Showtime": f"{tmrw}T20:00:00", "ScreenName": "Screen 1",
                                     "SessionAttributesNames": ["2D", "STANDARD"], "SeatsAvailable": 50}]},
    }

    class FakePolite:
        def __init__(self, *a, **k):
            pass

        def get(self, url, **k):
            return _Resp(200, feeds[url.rsplit("/", 1)[1]])

    class FakeClient:
        def login(self):
            return "loginAsGuest failed: status=403 statusCode=None"

    monkeypatch.setattr(reel, "Polite", FakePolite)
    monkeypatch.setattr(reel, "_PriceClient", FakeClient)
    out = reel.fetch(days=2)
    assert out["shows"][0]["prices"] is None
    _assert_health(out, attempted=0, priced=0, error_is_none=False)
    assert "loginAsGuest" in capsys.readouterr().err

    class GoodClient:
        def login(self):
            return None

        def sample(self, *a):
            return [{"seat": "Standard", "aed": 44.0}]

    monkeypatch.setattr(reel, "_PriceClient", GoodClient)
    out = reel.fetch(days=2)
    assert out["shows"][0]["prices"] == [{"seat": "Standard", "aed": 44.0}]
    _assert_health(out, attempted=1, priced=1)
