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


# --- Unit tests: no network --------------------------------------------------------------


class _FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_fetch_raises_when_now_showing_405s(monkeypatch):
    """A 405/non-200 on /home/nowShowing must raise, not return zero shows silently."""
    import readers.cineroyal as cineroyal

    def fake_get(self, url, **kw):
        return _FakeResp(405, text="")

    monkeypatch.setattr(cineroyal.Polite, "get", fake_get)

    with pytest.raises(RuntimeError, match="nowShowing"):
        cineroyal.fetch()


def test_fetch_raises_when_showtimes_all_fail(monkeypatch):
    """Every getShowTimesByFilmAndShowDate call 405ing must raise (X1), not silently skip."""
    import readers.cineroyal as cineroyal

    now_showing_html = (
        '<a href="/home/chooseScreen?prettyUrl=heart-of-the-beast" class="movie__title">'
        "HEART OF THE BEAST<"
    )

    def fake_get(self, url, **kw):
        return _FakeResp(200, text=now_showing_html)

    def fake_post(self, url, **kw):
        return _FakeResp(405, text="")

    monkeypatch.setattr(cineroyal.Polite, "get", fake_get)
    monkeypatch.setattr(cineroyal.Polite, "post", fake_post)

    with pytest.raises(RuntimeError, match="getShowTimesByFilmAndShowDate"):
        cineroyal.fetch()


def test_price_cache_key_is_cinema_hall_date_not_screen_ref():
    """Two different screenRefIds sharing the same hall class on the same day must reuse one
    cached price sample (X: price cache key must be (cinema, hall, date))."""
    import readers.cineroyal as cineroyal
    import inspect

    src = inspect.getsource(cineroyal.fetch)
    assert "price_key = (cinema_ref, hall, show_date_iso)" in src


def test_dedup_key_present_in_source():
    import inspect
    import readers.cineroyal as cineroyal

    src = inspect.getsource(cineroyal.fetch)
    assert "dedup_key = (cinema_id, film_title, show_date_iso, time_24, hall)" in src


def test_royal_plus_is_not_gold():
    """GOLD is VOX's own brand name; Royal Plus must not be mapped onto it."""
    from readers.cineroyal import SCREEN_TYPE_TO_HALL

    assert SCREEN_TYPE_TO_HALL["ROYAL PLUS"] != "GOLD"
