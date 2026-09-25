"""Offline fixture test for the Cinema City UAE reader.

Loads fixtures/cinemacity.json (a real live run, saved to disk) and asserts every
show's shape matches the Show/Cinema contract in docs/superpowers/plans/2026-09-25-cinema.md.
No network access here — the reader itself (readers/cinemacity.py) is exercised
separately and its output saved as the fixture.
"""
import json
import re
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from readers.common import CITIES, HALLS

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "cinemacity.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@pytest.fixture(scope="module")
def data():
    assert FIXTURE.exists(), f"missing fixture: {FIXTURE}"
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_cinemacity_fixture_shape(data):
    assert "cinemas" in data and "shows" in data
    cinemas = data["cinemas"]
    shows = data["shows"]
    assert len(cinemas) >= 1
    assert len(shows) >= 1
    assert len(shows) <= 400

    cinema_ids = {c["id"] for c in cinemas}
    assert len(cinema_ids) == len(cinemas), "duplicate cinema ids"

    for c in cinemas:
        assert c["id"].startswith("cinemacity-")
        assert c["chain"] == "cinemacity"
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


def test_cinemacity_fixture_has_live_prices(data):
    priced = [s for s in data["shows"] if s["prices"]]
    assert priced, "no priced show: the seatpreview/GetTickets sample failed for every hall"
    assert {c["id"] for c in data["cinemas"]} == {s["cinema"] for s in data["shows"]}, "a cinema lost its shows"


def test_cinemacity_dates_are_calendar_dates(data):
    # a 00:xx show belongs to the day it actually starts, not the 03:00 business day
    for s in data["shows"]:
        assert s["date"] >= "2026-01-01"


def test_cinemacity_no_vox_brands(data):
    assert not {s["hall"] for s in data["shows"]} & {"MAX", "GOLD"}


def test_cinemacity_raises_on_zero_shows(monkeypatch):
    from readers import cinemacity

    class FakePolite:
        def __init__(self, *a, **k):
            pass

        def get(self, url, params=None, **k):
            if url.endswith("/schedule"):
                code = params["theaters"].split('"id":"')[1].split('"')[0]
                return _Resp(200, {code: {"schedule": {}}})
            return _Resp(200, [])

        def post(self, *a, **k):
            raise AssertionError("no price call without shows")

    monkeypatch.setattr(cinemacity, "Polite", FakePolite)
    with pytest.raises(RuntimeError):
        cinemacity.fetch(days=2)


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


def test_cinemacity_price_health_and_parse_failure_is_contained(monkeypatch):
    import datetime as _dt
    from zoneinfo import ZoneInfo
    from readers import cinemacity

    tmrw = (_dt.datetime.now(ZoneInfo("Asia/Dubai")) + _dt.timedelta(days=1)).date().isoformat()
    uuid = "90bb7723-7ca3-5bec-8bd9-e0c1d7d20810"
    show = {"startsAt": f"{tmrw}T12:00:00", "tags": [], "isExpired": False,
            "data": {"ticketing": [{"provider": "default",
                                    "urls": [f"https://booking.cinemacity.ae/launch/ticketing/{uuid}"]}]}}
    first = cinemacity.CINEMAS_RAW[0][0]

    def run(tickets_payload):
        class FakePolite:
            def __init__(self, *a, **k):
                pass

            def get(self, url, params=None, **k):
                if url.endswith("/schedule"):
                    code = params["theaters"].split('"id":"')[1].split('"')[0]
                    sched = {"m1": {tmrw: [show]}} if code == first else {}
                    return _Resp(200, {code: {"schedule": sched}})
                return _Resp(200, [{"id": "m1", "title": "X", "runtime": 5400}])

            def post(self, url, json=None, **k):
                if "seatpreview" in url:
                    return _Resp(200, {"dataToken": "t", "selectSeatsModel": {"seatsLayoutModel": {
                        "areas": [{"areaNumber": "1", "name": "Deluxe"}],
                        "rows": [{"seats": [{"areaId": "1", "areaCategoryCode": "C1"}]}]}}})
                return _Resp(200, tickets_payload)

        monkeypatch.setattr(cinemacity, "Polite", FakePolite)
        return cinemacity.fetch(days=2)

    ok = run({"selectTicketsModel": {"groupedTicketTypes": [{"ticketTypeModels": [
        {"areaCategoryCode": "C1", "price": 5000, "displayName": "AQ Deluxe"}]}]}})
    assert ok["shows"][0]["prices"] == [{"seat": "Deluxe", "aed": 50.0}]
    _assert_health(ok, attempted=1, priced=1)

    bad = run({"selectTicketsModel": {"groupedTicketTypes": ["not-a-dict"]}})  # parse error
    assert bad["shows"][0]["prices"] is None
    assert bad["price_health"]["priced"] == 0 and bad["price_health"]["error"]
