"""Tests for the cross-run price cache (Task 6, part 3): readers/common.py's cache_get/cache_set
helpers, and one reader (cineroyal) actually reusing a same-day sample instead of re-requesting
it. refresh.py's own load/prune/save-per-date logic is exercised in test_film_history.py's
sandbox (test_price_cache_resets_on_a_new_date and test_price_cache_persisted_and_reused_next_run)
since that needs the full refresh() pipeline, not just the reader.
"""
import json

from readers.common import CACHE_MISS, cache_get, cache_set


def test_cache_get_miss_on_none_cache():
    assert cache_get(None, ("a", "b", "2026-09-27")) is CACHE_MISS


def test_cache_get_miss_on_empty_cache():
    assert cache_get({}, ("a", "b", "2026-09-27")) is CACHE_MISS


def test_cache_set_then_get_round_trips_a_real_value():
    cache: dict = {}
    key = ("cineroyal-dalma-mall", "STANDARD", "2026-09-27")
    cache_set(cache, key, [{"seat": "Standard", "aed": 40.0}])
    assert cache_get(cache, key) == [{"seat": "Standard", "aed": 40.0}]


def test_cache_set_then_get_round_trips_a_legitimate_null():
    """A sampled-but-priceless hall must be distinguishable from "never sampled" -- both are
    reused (no new call), but only a real MISS should ever trigger a fresh sample."""
    cache: dict = {}
    key = ("novo-deira-city-centre", "2D", "2026-09-27")
    cache_set(cache, key, None)
    assert cache_get(cache, key) is None  # found, and it's legitimately null
    assert cache_get(cache, ("other", "key", "2026-09-27")) is CACHE_MISS  # never stored


def test_cache_is_json_round_trippable():
    """The whole point: data/price_cache.json is plain JSON, so every key this cache produces
    must be a plain string, not a tuple."""
    cache: dict = {}
    cache_set(cache, ("vox-burjuman", "IMAX", "2026-09-27", "3D"), [{"seat": "IMAX", "aed": 65.0}])
    dumped = json.loads(json.dumps(cache))
    assert dumped == {"vox-burjuman|IMAX|2026-09-27|3D": [{"seat": "IMAX", "aed": 65.0}]}


# --- one reader actually reusing the cache instead of re-sampling ---------------------------

class _FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _cineroyal_fake(monkeypatch):
    import datetime as _dt
    from zoneinfo import ZoneInfo

    import readers.cineroyal as cineroyal

    today = _dt.datetime.now(ZoneInfo("Asia/Dubai")).date()
    now_showing_html = ('<a href="/home/chooseScreen?prettyUrl=heart-of-the-beast" class="movie__title">'
                        "HEART OF THE BEAST<")
    showtimes = {"film": {"rating": "PG13", "length": "120 min", "language": "English"},
                 "shows": [{"cinemaRefId": 2, "screenType": "STANDARD", "filmShowTimeList": [
                     {"screenRefId": 11, "showDate": today.isoformat(), "formattedShowTime": "10:00AM"},
                 ]}]}
    seat_calls = []

    def fake_get(self, url, **kw):
        return _FakeResp(200, text=now_showing_html)

    def fake_post(self, url, **kw):
        if url.endswith("/getShowTimesByFilmAndShowDate"):
            return _FakeResp(200, showtimes)
        if url.endswith("/getSeatsByScreenRef"):
            seat_calls.append(json.loads(kw["data"]))
            return _FakeResp(200, {"rowSeats": {"A": {"seats": [{"tierName": "Standard", "unitPrice": 40}]}}})
        return _FakeResp(404)

    monkeypatch.setattr(cineroyal.Polite, "get", fake_get)
    monkeypatch.setattr(cineroyal.Polite, "post", fake_post)
    return cineroyal, seat_calls


def test_cineroyal_reuses_a_same_day_cached_sample_instead_of_resampling(monkeypatch):
    cineroyal, seat_calls = _cineroyal_fake(monkeypatch)
    persisted_cache: dict = {}  # stands in for refresh.py's data/price_cache.json[chain][today]

    out1 = cineroyal.fetch(days=1, cache=persisted_cache)
    assert len(seat_calls) == 1
    assert out1["price_health"]["attempted"] == 1
    assert out1["price_health"].get("cached", 0) == 0
    assert persisted_cache  # the reader wrote its sample back into the external cache

    # a second "run" gets the same persisted dict (as refresh.py would hand it back, same date)
    out2 = cineroyal.fetch(days=1, cache=persisted_cache)
    assert len(seat_calls) == 1  # still just the one network call -- no re-sample
    assert out2["price_health"]["attempted"] == 0
    assert out2["price_health"]["cached"] == 1
    assert all(sh["prices"] == [{"seat": "Standard", "aed": 40.0}] for sh in out2["shows"])
