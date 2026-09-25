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


def test_novo_price_health_midnight_and_window(monkeypatch):
    import datetime as _dt
    from zoneinfo import ZoneInfo
    from readers import novo

    today = _dt.datetime.now(ZoneInfo("Asia/Dubai")).date()
    yday, tmrw = today - _dt.timedelta(days=1), today + _dt.timedelta(days=1)
    key = "Buhairah Centre~9~false~x"

    def sess(sid, t, midnight=False):
        return {"show_time": t, "experience": "2D", "cinemaId": 9, "session_id": sid,
                "sessionDisabled": False, "isMidnightShow": midnight}

    by_day = {
        yday.isoformat(): [sess("1", "12:30 AM", True)],          # really today 00:30 -> kept
        today.isoformat(): [],
        tmrw.isoformat(): [sess("2", "08:00 PM"), sess("3", "01:00 AM", True)],  # 3 -> day+2, dropped
    }
    layouts = []

    class FakePolite:
        def __init__(self, *a, **k):
            pass

        def get(self, url, params=None, **k):
            if url.endswith("/cinemas"):
                return _Resp(200, {"data": [{"name": "Buhairah Centre", "name_ar": "", "lat": "", "long": "", "address": ""}]})
            if url.endswith("/movies"):
                return _Resp(200, {"data": {"movies": [{"movie_id": 1, "movie_title": "X"}]}})
            if "/seat-layout/" in url:
                layouts.append(url)
                return _Resp(200, {"success": True, "data": {"areas": [{"name": "COOL", "priceInCents": 3675}]}})
            d = url.rsplit("/", 1)[1]
            rows = by_day.get(d) or []
            if not rows:
                return _Resp(400, {"success": False, "message": "No sessions found"})
            return _Resp(200, {"success": True, "data": {"sessions": {d: {key: rows}}}})

    monkeypatch.setattr(novo, "Polite", FakePolite)
    out = novo.fetch(days=2)
    got = sorted((sh["date"], sh["time"]) for sh in out["shows"])
    assert got == [(today.isoformat(), "00:30"), (tmrw.isoformat(), "20:00")]
    # prices are sampled per cinema x hall x show DATE: tomorrow's show gets its own sample; today's
    # 00:30 show has already started (inside the one-hour margin), so today stays unpriced rather than
    # borrowing tomorrow's (possibly weekend) price
    by_date = {sh["date"]: sh["prices"] for sh in out["shows"]}
    assert by_date[tmrw.isoformat()] == [{"seat": "COOL", "aed": 36.75}]
    assert by_date[today.isoformat()] is None
    assert len(layouts) == 1
    _assert_health(out, attempted=1, priced=1)
