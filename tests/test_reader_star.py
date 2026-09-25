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


# --- Unit tests: no network, no fixture --------------------------------------------------


def test_extract_token_from_bundle_snippet():
    """The token-refresh regex must find STARCINEMAS_TOKEN="..." in a real (trimmed) bundle
    snippet, not just in the hand-written hardcoded string."""
    from readers.star import extract_token

    snippet = (Path(__file__).parent / "fixtures" / "star_bundle_snippet.js").read_text(encoding="utf-8")
    token = extract_token(snippet)
    assert token is not None
    assert token.startswith("eyJ")
    assert "ROTATEDfake" in token  # the fixture's deliberately-different token, not the real one


def test_extract_token_fallback_bare_token_var():
    from readers.star import extract_token

    snippet = 'a=1,b=2,TOKEN="eyJhbGciOiJIUzI1NiJ9.fake.sig",c=3'
    assert extract_token(snippet) == "eyJhbGciOiJIUzI1NiJ9.fake.sig"


def test_extract_token_missing_returns_none():
    from readers.star import extract_token

    assert extract_token("no token anywhere in this bundle") is None


class _FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_fetch_raises_when_movie_shows_all_403(monkeypatch):
    """A rotated token (or any block) that 403s every listing call must raise RuntimeError,
    not silently return zero shows — X1/star token-rot fix."""
    import readers.star as star

    cinemas_payload = {
        "Records": [
            {
                "cinema_id": 1,
                "cinema_name": "National Cinema - Abu Dhabi",
                "cinema_address": "Abu Dhabi",
                "cinema_location": "Abu Dhabi",
                "cinema_latitude": "24.1",
                "cinema_longitude": "54.3",
                "map_view_url": None,
            }
        ]
    }
    movies_payload = {"Records": {"data": [{"movie_id": 99, "rating": "PG13"}]}}

    def fake_get(self, url, **kw):
        if url.endswith("/cinemas"):
            return _FakeResp(200, cinemas_payload)
        if url.endswith("/now-showing-movies"):
            return _FakeResp(200, movies_payload)
        if "/movie-shows/" in url:
            return _FakeResp(403, {"isAuthorization": True, "message": "You are not authorized"})
        return _FakeResp(404)

    monkeypatch.setattr(star, "BACKOFF_S", 0)
    monkeypatch.setattr(star.Polite, "get", fake_get)
    monkeypatch.setattr(star, "_refresh_token", lambda http: None)

    with pytest.raises(RuntimeError, match="movie-shows"):
        star.fetch()


def test_fetch_raises_on_zero_shows(monkeypatch):
    """Everything 200s but no show lands in the requested window -> still must raise, not
    return {"cinemas": [...], "shows": []}."""
    import readers.star as star

    cinemas_payload = {
        "Records": [
            {
                "cinema_id": 1,
                "cinema_name": "National Cinema - Abu Dhabi",
                "cinema_address": "Abu Dhabi",
                "cinema_location": "Abu Dhabi",
                "cinema_latitude": "24.1",
                "cinema_longitude": "54.3",
                "map_view_url": None,
            }
        ]
    }
    movies_payload = {"Records": {"data": [{"movie_id": 99, "rating": "PG13"}]}}

    def fake_get(self, url, **kw):
        if url.endswith("/cinemas"):
            return _FakeResp(200, cinemas_payload)
        if url.endswith("/now-showing-movies"):
            return _FakeResp(200, movies_payload)
        if "/movie-shows/" in url:
            return _FakeResp(200, {"Records": {"data": []}})
        return _FakeResp(404)

    monkeypatch.setattr(star.Polite, "get", fake_get)

    with pytest.raises(RuntimeError, match="zero shows"):
        star.fetch()


def test_fetch_raises_naming_token_when_refresh_also_fails(monkeypatch):
    """A 401 that survives the refresh attempt must raise a message naming the token."""
    import readers.star as star

    def fake_get(self, url, **kw):
        if url.endswith("/cinemas"):
            return _FakeResp(401, {"message": "not authorized"})
        return _FakeResp(404)

    monkeypatch.setattr(star, "BACKOFF_S", 0)
    monkeypatch.setattr(star.Polite, "get", fake_get)
    monkeypatch.setattr(star, "_refresh_token", lambda http: None)

    with pytest.raises(RuntimeError, match="TOKEN"):
        star.fetch()


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


def _star_payloads():
    import datetime as _dt
    from zoneinfo import ZoneInfo

    tomorrow_noon = (_dt.datetime.now(ZoneInfo("Asia/Dubai")) + _dt.timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0)
    cinemas = {"Records": [{"cinema_id": 1, "cinema_name": "National Cinema - Abu Dhabi",
                            "cinema_address": "Abu Dhabi", "cinema_location": "Abu Dhabi",
                            "cinema_latitude": "24.1", "cinema_longitude": "54.3", "map_view_url": None}]}
    movies = {"Records": {"data": [{"movie_id": 99, "rating": "PG13"}]}}
    shows = {"Records": {"data": [{"cinema_id": 1, "ss_id": 5, "movie_title": "X", "screen_type_name": "NORMAL",
                                   "ss_actual_start_date_time": int(tomorrow_noon.timestamp() * 1000)}]}}
    seats = {"Records": [{"sst_seat_type": "Star Select", "seat_price": "45"}]}
    return cinemas, movies, shows, seats


def test_star_price_health_and_single_403_backoff(monkeypatch):
    import readers.star as star

    cinemas, movies, shows, seats = _star_payloads()
    calls = {"cinemas": 0}

    def fake_get(self, url, **kw):
        if url.endswith("/cinemas"):
            calls["cinemas"] += 1
            return _FakeResp(403 if calls["cinemas"] == 1 else 200, cinemas)  # one transient 403
        if url.endswith("/now-showing-movies"):
            return _FakeResp(200, movies)
        if "/movie-shows/" in url:
            return _FakeResp(200, shows)
        if "/seat-layout/" in url:
            return _FakeResp(200, seats)
        return _FakeResp(404)

    refreshed = []
    monkeypatch.setattr(star, "BACKOFF_S", 0)
    monkeypatch.setattr(star.Polite, "get", fake_get)
    monkeypatch.setattr(star, "_refresh_token", lambda http: refreshed.append(1) or None)
    out = star.fetch(days=2)
    assert calls["cinemas"] == 2 and not refreshed, "one 403 must back off and retry, not refresh the token"
    assert out["shows"][0]["prices"] == [{"seat": "Star Select", "aed": 45.0}]
    _assert_health(out, attempted=1, priced=1)
