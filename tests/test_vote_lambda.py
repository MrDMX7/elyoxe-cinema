"""«صوّتوا مع الربع» backend (infra/counter/lambdas/vote.py), no AWS: an in-memory table and a hand-made day file in
the site's own /data/<city>-<date>.json shape."""
import importlib
import json
import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "infra", "counter", "lambdas"))
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("ALLOWED_ORIGINS", "https://cinema.elyoxe.com")
vote = importlib.import_module("vote")

TODAY = date(2026, 11, 20)
DAYFILE = {   # C: [id, chain, ar, en]  F: [fid, ar, en]  H: [code, key, ar, en]  P: [[seat, aed]…]  B: [url]
    "C": [["vox-mall-of-the-emirates", "vox", "فوكس — مول الإمارات", "VOX — Mall of the Emirates"],
          ["reel-dubai-mall", "reel", "ريل — دبي مول", "Reel — Dubai Mall"]],
    "F": [["i-play-rocky", "أنا من سيؤدي دور روكي", "I Play Rocky"], ["wildwood", "وايلدوود", "Wildwood"]],
    "H": [["Standard", "vox|Standard", "عادية", "Standard"], ["IMAX", "vox|IMAX", "آيماكس", "IMAX"]],
    "P": [[["Regular", 46.0], ["Premium", 56.0]], [["Regular", 75.0]]],
    "B": ["https://uae.voxcinemas.com/booking/", "https://www.reelcinemas.com/en-ae/movie-details/2"],
    "S": [[0, 0, "19:30", 0, 0, 0, "0005-1"], [0, 0, "19:30", 1, 1, 0, "0005-2"], [1, 1, "21:00", 0, -1, 1, ""]],
}


class FakeTable:
    def __init__(self):
        self.items = {}

    def put(self, item, new=False):
        k = (item["id"], item["k"])
        if new and k in self.items:
            raise RuntimeError("ConditionalCheckFailedException")
        self.items[k] = dict(item)

    def load(self, pid):
        rows = [v for (i, _), v in self.items.items() if i == pid]
        return next((r for r in rows if r["k"] == "poll"), None), [r for r in rows if r["k"].startswith("v#")]


@pytest.fixture
def env(monkeypatch):
    t = FakeTable()
    monkeypatch.setattr(vote, "fetch_day", lambda city, day: DAYFILE)
    monkeypatch.setattr(vote, "load", t.load)
    monkeypatch.setattr(vote, "save_poll", lambda item: t.put(item, new=True))
    monkeypatch.setattr(vote, "save_vote", t.put)
    monkeypatch.setattr(vote, "count_today", lambda day: 1)
    monkeypatch.setattr(vote, "switched_off", lambda: False)
    monkeypatch.setattr(vote, "now_dubai", lambda: datetime(2026, 11, 20, 18, 0, tzinfo=vote.DUBAI))
    return t


def call(method, path, body=None, origin="https://cinema.elyoxe.com", pid=None):
    ev = {"requestContext": {"http": {"method": method, "path": path}}, "rawPath": path, "headers": {"origin": origin},
          "body": json.dumps(body) if body is not None else None}
    if pid:
        ev["pathParameters"] = {"id": pid}
    r = vote.handler(ev, None)
    return r["statusCode"], (json.loads(r["body"]) if r["body"] and r["headers"]["Content-Type"].startswith("application/json") else r["body"])


KEYS = [{"city": "dubai", "date": "2026-11-20", "cin": "vox-mall-of-the-emirates", "fid": "i-play-rocky", "time": "19:30", "hall": "IMAX"},
        {"city": "dubai", "date": "2026-11-20", "cin": "reel-dubai-mall", "fid": "wildwood", "time": "21:00"}]


def make(env, keys=KEYS, by="سيف"):
    st, out = call("POST", "/vote", {"options": keys, "by": by, "lang": "ar"})
    assert st == 201, out
    return out["id"]


def test_a_poll_holds_the_shows_as_the_site_publishes_them(env):
    pid = make(env)
    st, p = call("GET", f"/vote/{pid}", pid=pid)
    assert st == 200 and p["by"] == "سيف" and len(p["opts"]) == 2 and p["votes"] == []
    a, b = p["opts"]
    assert (a["title_ar"], a["cin_en"], a["hall_en"], a["price"]) == ("أنا من سيؤدي دور روكي", "VOX — Mall of the Emirates", "IMAX", 75.0)
    assert a["book"] == "https://uae.voxcinemas.com/booking/0005-2"              # the base and the show's own tail
    assert b["price"] is None and b["book"].startswith("https://www.reelcinemas.com/")


@pytest.mark.parametrize("keys, code", [
    ([KEYS[0]], 400),                                                            # one show is not a vote
    ([KEYS[0], dict(KEYS[1], time="22:15")], 422),                               # no such show in our data
    ([KEYS[0], dict(KEYS[1], fid="<script>")], 422),
    ([KEYS[0], dict(KEYS[1], date="2026-12-30")], 422),                          # too far from today
    ([KEYS[0], dict(KEYS[1], city="paris")], 422),
])
def test_a_poll_takes_only_real_shows(env, keys, code):
    assert call("POST", "/vote", {"options": keys})[0] == code


def test_writes_come_only_from_the_site(env):
    assert call("POST", "/vote", {"options": KEYS}, origin="https://evil.example")[0] == 403


def test_votes_are_one_per_phone_and_can_change(env):
    pid = make(env)
    vk1, vk2 = "a" * 32, "b" * 32
    st, p = call("POST", f"/vote/{pid}", {"vk": vk1, "name": "  حمد‏\n ", "picks": [0, 1, 1], "note": "x" * 90}, pid=pid)
    assert st == 200 and p["me"] == vote.pub(vk1)
    me = next(v for v in p["votes"] if v["p"] == p["me"])
    assert me["name"] == "حمد" and me["picks"] == [0, 1] and len(me["note"]) == 60
    call("POST", f"/vote/{pid}", {"vk": vk2, "name": "مها", "picks": [1]}, pid=pid)
    st, p = call("POST", f"/vote/{pid}", {"vk": vk1, "name": "حمد", "picks": [], "no": True}, pid=pid)   # changed his mind
    assert len(p["votes"]) == 2 and next(v for v in p["votes"] if v["p"] == vote.pub(vk1))["no"] is True
    assert vk1 not in json.dumps(list(env.items.values()), ensure_ascii=False)   # the secret is never stored


@pytest.mark.parametrize("body", [{"vk": "short", "name": "x", "picks": [0]}, {"vk": "a" * 32, "name": "   ", "picks": [0]},
                                  {"vk": "a" * 32, "name": "x", "picks": [5]}, {"vk": "a" * 32, "name": "x", "picks": [True]}])
def test_bad_votes_are_refused(env, body):
    pid = make(env)
    assert call("POST", f"/vote/{pid}", body, pid=pid)[0] == 400


def test_a_poll_has_room_for_forty(env, monkeypatch):
    monkeypatch.setattr(vote, "VOTERS", 2)
    pid = make(env)
    for c in "ab":
        assert call("POST", f"/vote/{pid}", {"vk": c * 30, "name": c, "picks": [0]}, pid=pid)[0] == 200
    assert call("POST", f"/vote/{pid}", {"vk": "c" * 30, "name": "c", "picks": [0]}, pid=pid)[0] == 429
    assert call("POST", f"/vote/{pid}", {"vk": "a" * 30, "name": "a", "picks": [1]}, pid=pid)[0] == 200   # a voter may still change


def test_the_day_cap_and_the_switch(env, monkeypatch):
    monkeypatch.setattr(vote, "count_today", lambda day: vote.DAY_CAP + 1)
    assert call("POST", "/vote", {"options": KEYS})[0] == 429
    monkeypatch.setattr(vote, "switched_off", lambda: True)
    assert call("POST", "/vote", {"options": KEYS})[0] == 503


def test_the_leader_and_its_calendar_file(env):
    pid = make(env)
    for c, picks in (("a", [1]), ("b", [0, 1]), ("c", [0])):
        call("POST", f"/vote/{pid}", {"vk": c * 30, "name": c, "picks": picks}, pid=pid)
    st, p = call("GET", f"/vote/{pid}", pid=pid)
    assert vote.leader(p["opts"], p["votes"]) == 0                              # 2–2: the earlier show
    st, body = call("GET", f"/vote/{pid}/ics", pid=pid)
    assert st == 200 and "BEGIN:VEVENT" in body and "DTSTART:20261120T153000Z" in body and f"/v/?p={pid}" in body


def test_unknown_polls_are_404(env):
    assert call("GET", "/vote/abcdefghij", pid="abcdefghij")[0] == 404
    assert call("GET", "/vote/../etc", pid="../etc")[0] == 404


FILMS = {"i-play-rocky": {"fid": "i-play-rocky", "title_ar": "أنا من سيؤدي دور روكي", "title_en": "I Play Rocky"},
         "wildwood": {"fid": "wildwood", "title_ar": "وايلدوود", "title_en": "Wildwood"}}


def test_a_poll_on_whole_films(env, monkeypatch):
    """Owner 2026-11-20: picked on the films tab, a vote can be on the film itself (no time, no cinema)."""
    def fetch_film(fid):
        if fid not in FILMS:
            raise OSError("404")
        return FILMS[fid]
    monkeypatch.setattr(vote, "fetch_film", fetch_film)
    st, out = call("POST", "/vote", {"options": [{"fid": "i-play-rocky"}, {"fid": "wildwood"}, {"fid": "wildwood"}]})
    assert st == 201
    pid = out["id"]
    st, p = call("GET", f"/vote/{pid}", pid=pid)
    assert [(o["kind"], o["fid"], o["title_en"]) for o in p["opts"]] == [("film", "i-play-rocky", "I Play Rocky"), ("film", "wildwood", "Wildwood")]
    assert call("POST", "/vote", {"options": [{"fid": "i-play-rocky"}, {"fid": "not-showing"}]})[0] == 422
    call("POST", f"/vote/{pid}", {"vk": "a" * 30, "name": "a", "picks": [1]}, pid=pid)
    assert call("GET", f"/vote/{pid}/ics", pid=pid)[0] == 404                   # a film has no time for a calendar
    st, out = call("POST", "/vote", {"options": [{"fid": "i-play-rocky"}, KEYS[1]]})   # a film and a show may mix
    assert st == 201
