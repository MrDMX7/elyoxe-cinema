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


def test_fixture_prices_are_null_or_shaped_ok(data):
    """This fixture is a pre-pricing-feature snapshot (resampled from a `prices` run before
    the seat-selection price sampler existed), so every show still carries prices=None here.
    That is a property of *this fixture file*, not a binding rule any more -- Roxy's
    seat-selection page needs no login (see docs/probe/roxy.md and the live tests below).
    test_roxy_fixture_shape already checks the general prices shape (None or a valid list)."""
    assert all(s["prices"] is None for s in data["shows"])


def test_dates_are_today_and_tomorrow(data):
    dates = {s["date"] for s in data["shows"]}
    assert 1 <= len(dates) <= 2, f"expected 1-2 distinct dates (today+tomorrow), got {dates}"


# --- Unit tests: no network ----------------------------------------------------------------


def test_xtreme_and_gold_are_not_vox_brand_names():
    """MAX and GOLD are VOX's own brand names; Roxy's Xtreme/Gold must not be mapped onto them."""
    from readers.roxy import HALL_MAP

    assert HALL_MAP["xtreme"] != "MAX"
    assert HALL_MAP["gold"] != "GOLD"


def test_map_date_business_day_midnight_bump():
    """'Sep 25 Fri' at 00:10 is really the 26th (Roxy buckets by business day)."""
    import datetime

    from readers.roxy import _map_date

    today = datetime.date(2026, 9, 25)
    assert _map_date("Sep 25 Fri", today, time_hint="00:10") == "2026-09-26"
    assert _map_date("Sep 25 Fri", today, time_hint="23:40") == "2026-09-25"
    assert _map_date("Sep 25 Fri", today, time_hint=None) == "2026-09-25"


def test_map_date_year_rollover():
    """On Dec 31, 'Jan 01' must map to next year, not get stranded in the year that's ending."""
    import datetime

    from readers.roxy import _map_date

    today = datetime.date(2026, 12, 31)
    assert _map_date("Jan 1 Fri", today, time_hint="10:00") == "2027-01-01"

    # And the reverse: early January looking at a "Dec 31" business day (rare, but the
    # nearest-year logic must not anchor blindly on today.year here either).
    today2 = datetime.date(2027, 1, 1)
    assert _map_date("Dec 31 Thu", today2, time_hint="23:00") == "2026-12-31"


def test_map_date_unparsable_returns_none():
    import datetime

    from readers.roxy import _map_date

    assert _map_date("not a date", datetime.date(2026, 9, 25)) is None


class _FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status {self.status_code}")


def test_fetch_raises_when_now_showing_page_has_no_movie_links(monkeypatch):
    import readers.roxy as roxy

    def fake_get(self, url, **kw):
        return _FakeResp(200, text="<html>nothing here</html>")

    monkeypatch.setattr(roxy._Client, "get", fake_get)

    with pytest.raises(RuntimeError, match="zero now-showing"):
        roxy.fetch()


def test_fetch_raises_when_ajax_all_fail(monkeypatch):
    """Every movie-schedule/ajax call failing must raise (X1), not silently return zero shows."""
    import readers.roxy as roxy

    home_html = '<a href="/en/movie/heart-of-the-beast">Heart of the Beast</a>'
    movie_html = '<div data-history-node-id="178231"><h1>Heart of the Beast</h1></div>'

    def fake_get(self, url, **kw):
        if url.endswith("/en"):
            return _FakeResp(200, text=home_html)
        if "/en/movie/" in url and "ajax" not in url:
            return _FakeResp(200, text=movie_html)
        if "movie-schedule/ajax" in url:
            return _FakeResp(500, text="")
        return _FakeResp(404, text="")

    monkeypatch.setattr(roxy._Client, "get", fake_get)

    with pytest.raises(RuntimeError, match="ajax"):
        roxy.fetch()


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


def test_roxy_twin_sessions_get_distinct_labels_and_price_health(monkeypatch):
    import datetime as _dt
    import readers.roxy as roxy
    from zoneinfo import ZoneInfo

    today = _dt.datetime.now(ZoneInfo("Asia/Dubai")).date()
    raw = f"{today:%b} {today.day} {today:%a}"
    home_html = '<a href="/en/movie/smurfs">Smurfs</a>'
    movie_html = '<div data-history-node-id="178226"><h1>Smurfs</h1></div>'
    slot = ('cinema-name="Dubai Hills Mall" cinema-id="0000000007" screen="Silver" nid="178226" '
            'date="{raw}" time="23:05" session="{sid}"')
    ajax = {"html": slot.format(raw=raw, sid="151749") + " " + slot.format(raw=raw, sid="151750")}

    def fake_get(self, url, **kw):
        if url.endswith("/en"):
            return _FakeResp(200, text=home_html)
        if "movie-schedule/ajax" in url:
            return _FakeResp(200, ajax)
        if "/en/movie/" in url:
            return _FakeResp(200, text=movie_html)
        return _FakeResp(404, text="")

    monkeypatch.setattr(roxy._Client, "get", fake_get)
    out = roxy.fetch(days=2, prices=False)
    labels = sorted(sh["hall_label"] for sh in out["shows"])
    assert labels == ["Silver (session 151749)", "Silver (session 151750)"]
    assert all("_session" not in sh for sh in out["shows"])
    assert all(k not in sh for sh in out["shows"] for k in ("_site_cid", "_nid", "_raw_date", "_raw_cname", "_hall_raw"))
    _assert_health(out, attempted=0, priced=0)


# --- Task: live seat-class prices from the seat-selection page ------------------------------


def test_seat_legend_prices_from_fixture():
    """Parser test: the seat-class legend on a real (trimmed) seat-selection page."""
    from readers.roxy import _seat_legend_prices

    html = (Path(__file__).resolve().parent / "fixtures" / "roxy_seat_selection.html").read_text(encoding="utf-8")
    prices = _seat_legend_prices(html)
    assert prices == [{"seat": "Standard", "aed": 43.0}, {"seat": "Premium View", "aed": 70.0}]


def test_seat_legend_prices_no_categories_returns_none():
    from readers.roxy import _seat_legend_prices

    assert _seat_legend_prices("<div>no legend here</div>") is None


def test_seat_selection_url_builder():
    """URL builder test: matches the live shape verified by hand, e.g.
    /en/seat-selection/0000000006/96027/177366/Al%20Khawaneej/Sep%2027%20Sun/22:30/Gold."""
    from readers.roxy import _seat_selection_url

    url = _seat_selection_url("0000000006", "96027", "177366", "Al Khawaneej", "Sep 27 Sun", "22:30", "Gold")
    assert url == ("https://www.theroxycinemas.com/en/seat-selection/0000000006/96027/177366/"
                   "Al%20Khawaneej/Sep%2027%20Sun/22:30/Gold")


def test_seat_selection_url_builder_encodes_comma_in_cinema_name():
    """'The Beach, JBR' -- a real Roxy cinema name -- must come out url-encoded (verified live)."""
    from readers.roxy import _seat_selection_url

    url = _seat_selection_url("0000000002", "227376", "178336", "The Beach, JBR", "Sep 27 Sun", "19:00", "Platinum")
    assert url == ("https://www.theroxycinemas.com/en/seat-selection/0000000002/227376/178336/"
                   "The%20Beach%2C%20JBR/Sep%2027%20Sun/19:00/Platinum")


def _seat_fixture_html() -> str:
    return (Path(__file__).resolve().parent / "fixtures" / "roxy_seat_selection.html").read_text(encoding="utf-8")


def _roxy_one_session_fake(monkeypatch, seat_calls, seat_status=200):
    """One movie, one cinema, one session -- everything a fetch() needs to reach the
    pricing pass, wired through the module's own _Client.get."""
    import datetime as _dt
    from zoneinfo import ZoneInfo

    import readers.roxy as roxy

    today = _dt.datetime.now(ZoneInfo("Asia/Dubai")).date()
    raw_date = f"{today:%b} {today.day} {today:%a}"
    home_html = '<a href="/en/movie/heart-of-the-beast">Heart of the Beast</a>'
    movie_html = '<div data-history-node-id="178231"><h1>Heart of the Beast</h1></div>'
    slot = ('cinema-name="Citywalk" cinema-id="0000000001" screen="Silver" nid="178231" '
            f'date="{raw_date}" time="23:10" session="227630"')
    ajax_payload = {"html": slot}

    def fake_get(self, url, **kw):
        if url.endswith("/en"):
            return _FakeResp(200, text=home_html)
        if "movie-schedule/ajax" in url:
            return _FakeResp(200, ajax_payload)
        if "/en/seat-selection/" in url:
            seat_calls.append(url)
            return _FakeResp(seat_status, text=_seat_fixture_html() if seat_status == 200 else "")
        if "/en/movie/" in url:
            return _FakeResp(200, text=movie_html)
        return _FakeResp(404, text="")

    monkeypatch.setattr(roxy._Client, "get", fake_get)
    return roxy


def test_roxy_seat_selection_url_built_from_schedule_fields(monkeypatch):
    """fetch() must build the seat-selection URL out of the fields already on the schedule
    session tag (cinema-id, session, nid, cinema-name, date, time, screen) -- no extra request."""
    import datetime as _dt
    from urllib.parse import quote
    from zoneinfo import ZoneInfo

    seat_calls: list[str] = []
    roxy = _roxy_one_session_fake(monkeypatch, seat_calls)

    roxy.fetch(days=1)

    today = _dt.datetime.now(ZoneInfo("Asia/Dubai")).date()
    raw_date = f"{today:%b} {today.day} {today:%a}"
    assert len(seat_calls) == 1
    assert seat_calls[0] == (
        f"https://www.theroxycinemas.com/en/seat-selection/0000000001/227630/178231/"
        f"Citywalk/{quote(raw_date)}/23:10/Silver"
    )


def test_roxy_reuses_a_same_day_cached_sample_instead_of_resampling(monkeypatch):
    """Cache reuse test: a second fetch() with the same persisted cache dict must not
    re-request the seat-selection page (mirrors test_price_cache.py's cineroyal test)."""
    seat_calls: list[str] = []
    roxy = _roxy_one_session_fake(monkeypatch, seat_calls)
    persisted_cache: dict = {}

    out1 = roxy.fetch(days=1, cache=persisted_cache)
    assert len(seat_calls) == 1
    assert out1["price_health"]["attempted"] == 1
    assert out1["price_health"]["priced"] == 1
    assert out1["price_health"].get("cached", 0) == 0
    assert persisted_cache

    out2 = roxy.fetch(days=1, cache=persisted_cache)
    assert len(seat_calls) == 1  # still just the one network call
    assert out2["price_health"]["attempted"] == 0
    assert out2["price_health"]["cached"] == 1
    expected = [{"seat": "Standard", "aed": 43.0}, {"seat": "Premium View", "aed": 70.0}]
    assert all(sh["prices"] == expected for sh in out2["shows"])


def test_roxy_price_sampling_never_fails_the_chain_on_error(monkeypatch):
    """A broken/blocked seat-selection page must not raise -- price_health.error records it,
    the chain still returns its shows with prices=None."""
    seat_calls: list[str] = []
    roxy = _roxy_one_session_fake(monkeypatch, seat_calls, seat_status=403)

    out = roxy.fetch(days=1)

    assert out["shows"]
    assert out["price_health"]["attempted"] == 1
    assert out["price_health"]["priced"] == 0
    assert isinstance(out["price_health"]["error"], str) and out["price_health"]["error"]
    assert all(sh["prices"] is None for sh in out["shows"])


def test_roxy_prices_false_skips_sampling_entirely(monkeypatch):
    seat_calls: list[str] = []
    roxy = _roxy_one_session_fake(monkeypatch, seat_calls)

    out = roxy.fetch(days=1, prices=False)

    assert seat_calls == []
    _assert_health(out, attempted=0, priced=0)
