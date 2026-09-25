"""Offline shape test for the Roxy reader fixture.

Run: pytest tests/test_reader_roxy.py -q
"""
import json
import re
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "roxy.json"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from readers.common import CITIES, HALLS  # noqa: E402

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@pytest.fixture(scope="module")
def data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_exists_and_nonempty(data):
    assert data["cinemas"], "fixture has no cinemas"
    assert data["shows"], "fixture has no shows"
    assert len(data["shows"]) <= 500


def test_cinemas_shape(data):
    seen_ids = set()
    for c in data["cinemas"]:
        assert c["id"].startswith("roxy-")
        assert c["id"] not in seen_ids, f"duplicate cinema id {c['id']}"
        seen_ids.add(c["id"])
        assert c["chain"] == "roxy"
        assert c["name"]
        assert c["city"] in CITIES, f"bad city {c['city']!r} for {c['id']}"
        assert c["mall"]
        assert c["address"]
        for key in ("name_ar", "maps", "lat", "lng"):
            assert key in c


def test_roxy_fixture_shape(data):
    cinema_ids = {c["id"] for c in data["cinemas"]}
    assert cinema_ids, "no cinemas to reference"

    for s in data["shows"]:
        # every show references a known cinema
        assert s["cinema"] in cinema_ids, f"show references unknown cinema {s['cinema']!r}"

        assert s["film_title"] and isinstance(s["film_title"], str)

        assert DATE_RE.match(s["date"]), f"bad date {s['date']!r}"
        assert TIME_RE.match(s["time"]), f"bad time {s['time']!r}"
        hh, mm = s["time"].split(":")
        assert 0 <= int(hh) <= 23
        assert 0 <= int(mm) <= 59

        assert s["hall"] in HALLS, f"bad hall {s['hall']!r}"
        assert s["hall_label"], "hall_label must be set (raw site label)"

        assert s["prices"] is None or (
            isinstance(s["prices"], list)
            and all(
                isinstance(p, dict) and "seat" in p and "aed" in p and p["aed"] > 0
                for p in s["prices"]
            )
        ), f"bad prices {s['prices']!r}"

        assert s["book"].startswith("https://"), f"bad book url {s['book']!r}"

        if s["runtime"] is not None:
            assert isinstance(s["runtime"], int) and s["runtime"] > 0
        if s["film_rating"] is not None:
            assert isinstance(s["film_rating"], str)
        if s["film_lang"] is not None:
            assert isinstance(s["film_lang"], str)


def test_roxy_prices_are_null_no_seat_hold(data):
    """Binding rule: Roxy requires login to see a session's price (a seat-hold flow),
    so every show in this reader's fixture must carry prices=None."""
    assert all(s["prices"] is None for s in data["shows"])


def test_dates_are_today_and_tomorrow(data):
    dates = {s["date"] for s in data["shows"]}
    assert 1 <= len(dates) <= 2, f"expected 1-2 distinct dates (today+tomorrow), got {dates}"
