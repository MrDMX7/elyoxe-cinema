"""Every reader samples prices once per cinema x hall x SHOW DATE (ruling 2026-09-26: weekday and
weekend prices differ, so today's sample must never price tomorrow's show), and a 3D title is its own key."""
import datetime as _dt
from zoneinfo import ZoneInfo

from readers.common import fmt3d

DUBAI = ZoneInfo("Asia/Dubai")


def _days(n):
    t = _dt.datetime.now(DUBAI).date()
    return [t + _dt.timedelta(days=i) for i in range(n)]


class _Resp:
    def __init__(self, status=200, payload=None, text="", url=""):
        self.status_code, self._payload, self.text, self.url = status, payload, text, url

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_fmt3d():
    assert fmt3d("Avatar 3D") == "3D" and fmt3d("Avatar (3D)") == "3D" and fmt3d("AVATAR - 3d") == "3D"
    assert fmt3d("Avatar") == "" and fmt3d(None) == "" and fmt3d("3Days") == ""


def test_novo_key_has_the_date():
    """novo's midnight/window test in test_reader_novo.py covers the behaviour; this pins the key shape."""
    src = open("readers/novo.py", encoding="utf-8").read()
    assert "key = (cinema_id, hall_label, cal_date)" in src


def test_vox_samples_each_show_date(monkeypatch):
    from readers import vox

    _, d1, d2 = _days(3)
    listing = ('<article class="cinema-summary" data-slug="yas-mall"><h3><a>Yas Mall</a></h3>'
               '<p>Address: Yas Island, Abu Dhabi</p><a href="/showtimes/yas-mall">Showtimes</a></article>')

    def showtimes(n):
        return ('<article class="movie-compare"><aside class="movie-hero"><h2>X</h2></aside>'
                '<div class="dates"><ol class="showtimes"><li><strong>Standard</strong>'
                f'<ol><li><a class="showtime" href="/booking/000{n}-1">8:00pm</a></li></ol></li></ol></div></article>')
    price = {1: "50.00", 2: "60.00"}
    current = {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def get(self, url, **k):
            if url.endswith("/cinemas"):
                return _Resp(200, text=listing, url=url)
            if "/showtimes/" in url:
                for n, d in ((1, d1), (2, d2)):
                    if f"d={d:%Y%m%d}" in url:
                        return _Resp(200, text=showtimes(n), url=url)
                return _Resp(200, text="", url=url)
            for n in (1, 2):
                if url.endswith(f"/booking/000{n}-1"):
                    current["n"] = n
                    return _Resp(200, text="", url=f"https://uae.voxcinemas.com/booking/o_{n}/guest")
            if url.endswith("/seats/fetch"):
                return _Resp(200, text="", url=url.replace("/fetch", "/processing"))
            if url.endswith("/seats"):
                return _Resp(200, text=f'<li class="seat" data-label="Regular" data-price="{price[current["n"]]} AED"></li>', url=url)
            return _Resp(302, text="", url=url)

    monkeypatch.setattr(vox, "_Client", FakeClient)
    out = vox.fetch(days=3)
    got = {sh["date"]: sh["prices"] for sh in out["shows"]}
    assert got == {d1.isoformat(): [{"seat": "Regular", "aed": 50.0}], d2.isoformat(): [{"seat": "Regular", "aed": 60.0}]}
    assert out["price_health"]["attempted"] == 2


def test_cinemacity_samples_each_show_date(monkeypatch):
    from readers import cinemacity

    _, d1, d2 = (d.isoformat() for d in _days(3))
    first = cinemacity.CINEMAS_RAW[0][0]

    def show(d, u):
        return {"startsAt": f"{d}T12:00:00", "tags": [], "isExpired": False,
                "data": {"ticketing": [{"provider": "default", "urls": [f"https://booking.cinemacity.ae/launch/ticketing/{u}"]}]}}
    u1, u2 = "90bb7723-7ca3-5bec-8bd9-e0c1d7d20811", "90bb7723-7ca3-5bec-8bd9-e0c1d7d20812"
    seen = []

    class FakePolite:
        def __init__(self, *a, **k):
            pass

        def get(self, url, params=None, **k):
            if url.endswith("/schedule"):
                code = params["theaters"].split('"id":"')[1].split('"')[0]
                sched = {"m1": {d1: [show(d1, u1)], d2: [show(d2, u2)]}} if code == first else {}
                return _Resp(200, {code: {"schedule": sched}})
            return _Resp(200, [{"id": "m1", "title": "X", "runtime": 5400}])

        def post(self, url, json=None, **k):
            if "seatpreview" in url:
                seen.append(f"{url} {json}")
                return _Resp(200, {"dataToken": "t", "selectSeatsModel": {"seatsLayoutModel": {
                    "areas": [{"areaNumber": "1", "name": "Deluxe"}],
                    "rows": [{"seats": [{"areaId": "1", "areaCategoryCode": "C1"}]}]}}})
            aed = 5000 if u1 in seen[-1] else 6000
            return _Resp(200, {"selectTicketsModel": {"groupedTicketTypes": [{"ticketTypeModels": [
                {"areaCategoryCode": "C1", "price": aed, "displayName": "Deluxe"}]}]}})

    monkeypatch.setattr(cinemacity, "Polite", FakePolite)
    out = cinemacity.fetch(days=3)
    got = {sh["date"]: sh["prices"] for sh in out["shows"]}
    assert out["price_health"]["attempted"] == 2
    assert got[d1] == [{"seat": "Deluxe", "aed": 50.0}] and got[d2] == [{"seat": "Deluxe", "aed": 60.0}]


def test_star_samples_each_show_date(monkeypatch):
    import readers.star as star

    _, d1, d2 = _days(3)

    def ts(d):
        return int(_dt.datetime.combine(d, _dt.time(12), DUBAI).timestamp() * 1000)
    cinemas = {"Records": [{"cinema_id": 1, "cinema_name": "National Cinema - Abu Dhabi", "cinema_address": "Abu Dhabi",
                            "cinema_location": "Abu Dhabi", "cinema_latitude": "24.1", "cinema_longitude": "54.3", "map_view_url": None}]}
    movies = {"Records": {"data": [{"movie_id": 99, "rating": "PG13"}]}}
    shows = {"Records": {"data": [
        {"cinema_id": 1, "ss_id": 5, "movie_title": "X", "screen_type_name": "NORMAL", "ss_actual_start_date_time": ts(d1)},
        {"cinema_id": 1, "ss_id": 6, "movie_title": "X", "screen_type_name": "NORMAL", "ss_actual_start_date_time": ts(d2)}]}}
    layouts = []

    def fake_get(self, url, **kw):
        if url.endswith("/cinemas"):
            return _Resp(200, cinemas)
        if url.endswith("/now-showing-movies"):
            return _Resp(200, movies)
        if "/movie-shows/" in url:
            return _Resp(200, shows)
        if "/seat-layout/" in url:
            layouts.append(url)
            return _Resp(200, {"Records": [{"sst_seat_type": "Star Select", "seat_price": "45" if url.endswith("/5") else "55"}]})
        return _Resp(404)

    monkeypatch.setattr(star, "BACKOFF_S", 0)
    monkeypatch.setattr(star.Polite, "get", fake_get)
    monkeypatch.setattr(star, "_refresh_token", lambda http: None)
    out = star.fetch(days=3)
    got = {sh["date"]: sh["prices"] for sh in out["shows"]}
    assert len(layouts) == 2
    assert got[d1.isoformat()] == [{"seat": "Star Select", "aed": 45.0}]
    assert got[d2.isoformat()] == [{"seat": "Star Select", "aed": 55.0}]


def test_reel_samples_each_show_date_and_3d_apart(monkeypatch):
    from readers import reel

    _, d1, d2 = (d.isoformat() for d in _days(3))

    def sess(sid, d, film="F1"):
        return {"CinemaId": "0001", "SessionId": sid, "ScheduledFilmId": film, "Showtime": f"{d}T20:00:00",
                "ScreenName": "Screen 1", "SessionAttributesNames": ["2D", "STANDARD"], "SeatsAvailable": 50}
    feeds = {
        "Cinemas.json": {"value": [{"ID": "0001", "Name": "Dubai Mall", "CinemaNationalId": "UAE"}]},
        "Films.json": {"value": [{"ID": "F1", "Title": "X"}, {"ID": "F2", "Title": "X 3D"}]},
        "Sessions.json": {"value": [sess("7", d1), sess("8", d2), sess("9", d1, "F2")]},
    }
    sampled = []

    class FakePolite:
        def __init__(self, *a, **k):
            pass

        def get(self, url, **k):
            return _Resp(200, feeds[url.rsplit("/", 1)[1]])

    class GoodClient:
        def login(self):
            return None

        def sample(self, cid, sid, *a):
            sampled.append(sid)
            return [{"seat": "Standard", "aed": {"7": 44.0, "8": 54.0, "9": 64.0}[sid]}]

    monkeypatch.setattr(reel, "Polite", FakePolite)
    monkeypatch.setattr(reel, "_PriceClient", GoodClient)
    out = reel.fetch(days=3)
    assert sorted(sampled) == ["7", "8", "9"]
    got = sorted((sh["date"], sh["film_title"], sh["prices"][0]["aed"]) for sh in out["shows"])
    assert got == [(d1, "X", 44.0), (d1, "X 3D", 64.0), (d2, "X", 54.0)]
