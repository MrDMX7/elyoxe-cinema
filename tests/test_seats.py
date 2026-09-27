"""seats.py (hall maps per chain, best seat, the capped occupancy sampler), steps/occupancy.py (state files,
freshness, _sid never published) and pages/seats.py + src/js/seatmap.js (data files, the chunk)."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import seats  # noqa: E402

FX = Path(ROOT) / "tests" / "fixtures" / "seats"
DUBAI = seats.DUBAI


def fx(chain):
    p = FX / (f"{chain}.html" if chain == "vox" else f"{chain}.json")
    text = p.read_text(encoding="utf-8")
    return text if chain == "vox" else json.loads(text)


def tally(hall):
    return Counter(s["status"] for r in hall["rows"] for s in r["seats"])


def step():
    spec = importlib.util.spec_from_file_location("steps_occupancy_t", os.path.join(ROOT, "steps", "occupancy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- normalisers, one per chain
def test_star_suites_hall():
    h = seats.normalise("star", fx("star"))
    assert [r["name"] for r in h["rows"]] == ["E", "D", "C", "B", "A"] and h["screen_side"] == "top"
    assert tally(h) == {"free": 24, "taken": 1, "blocked": 1}        # C12 reserve type 8, C11 covid-blocked
    e = h["rows"][0]["seats"]
    assert [s["id"] for s in e][:2] == ["E26", "E25"] and e[0]["col"] == "26" and e[0]["x"] == 0
    assert e[4]["x"] == 5                                              # the aisle at column 5 keeps its width
    assert [c["name"] for c in h["classes"]] == ["STAR PLATINUM SUITES", "STAR PLATINUM FAMILY"]
    assert h["classes"][0]["aed"] == 84.0
    assert seats.counts(h) == {"free": 24, "total": 26}


def test_cineroyal_rows_taken_blocked_and_tiers():
    h = seats.normalise("cineroyal", fx("cineroyal"))
    assert [r["name"] for r in h["rows"]] == ["A", "D", "I", "J", "M"] and h["screen_side"] == "bottom"
    assert tally(h) == {"free": 90, "taken": 2, "blocked": 4}
    assert {c["name"]: c["aed"] for c in h["classes"]} == {"Premium": 59.0, "VIP": 51.75, "Standard": 40.25}
    assert h["rows"][0]["seats"][0]["id"] == "A/21" and h["rows"][0]["seats"][0]["cls"] == "Premium"


def test_novo_vista_areas():
    h = seats.normalise("novo", fx("novo"))
    assert [r["name"] for r in h["rows"]] == ["A", "B", "F", "K"] and h["screen_side"] == "top"
    assert tally(h) == {"free": 40, "taken": 1, "blocked": 1}
    assert h["rows"][0]["seats"][0]["x"] == 2                         # two aisle cells lead row A
    assert h["classes"] == [{"name": "COOL", "aed": 36.75}]


def test_cinemacity_seatpreview():
    h = seats.normalise("cinemacity", fx("cinemacity"))
    assert [r["name"] for r in h["rows"]] == ["A", "C", "F"]
    assert tally(h) == {"free": 24, "taken": 1, "blocked": 1}
    assert h["classes"] == [{"name": "VIP", "aed": None}]               # the preview carries no price
    assert h["rows"][0]["seats"][0]["id"] == "A1"


def test_reel_sold_and_wheelchair_match_the_chains_own_count():
    h = seats.normalise("reel", fx("reel"))
    assert [r["name"] for r in h["rows"]] == ["E", "D", "C", "B", "A"]
    assert tally(h) == {"free": 35, "taken": 3, "wheelchair": 1}
    assert seats.counts(h)["free"] == 36                                # Sessions.json said SeatsAvailable 36
    assert {c["name"]: c["aed"] for c in h["classes"]} == {"Premium Front": 60.0, "Premium": 70.0}


def test_vox_seat_table_and_legend():
    h = seats.normalise("vox", fx("vox"))
    assert [r["name"] for r in h["rows"]][:2] == ["I", "H"] and h["rows"][-1]["name"] == "A"
    assert tally(h) == {"free": 116, "taken": 20}
    assert {c["name"]: c["aed"] for c in h["classes"]} == {"Regular": 50.0, "Preferred View": 75.0}
    a = h["rows"][-1]
    assert {s["cls"] for s in a["seats"]} == {"Preferred View"}


def test_unknown_or_broken_layouts_are_none():
    assert seats.normalise("roxy", {}) is None
    assert seats.normalise("star", {"Records": []}) is None
    assert seats.normalise("novo", {"data": {"areas": "nope"}}) is None
    assert seats.normalise("vox", "<html>login</html>") is None


# ---------------------------------------------------------------- best seat
def grid(rows, cols, side="top", taken=(), classes=None):
    out = []
    for i in range(rows):
        name = chr(ord("A") + i)
        out.append({"name": name, "seats": [seats._seat(f"{name}{x}", x, x + 1, "taken" if (name, x) in taken else "free",
                                                        (classes or {}).get(name, "Std")) for x in range(cols)]})
    cls = sorted({s["cls"] for r in out for s in r["seats"]})
    return {"rows": out, "screen_side": side, "classes": [{"name": c, "aed": {"Std": 40, "VIP": 90}.get(c)} for c in cls]}


def test_best_seat_is_two_thirds_back_and_central():
    h = grid(11, 15)                                                   # rows A..K from the screen: G 60 %, H 70 % back
    b = seats.best_seat(h)
    assert b["row"] == "H" and b["x"] == 7 and b["col"] == "8"          # H is the closer to two thirds
    h2 = grid(11, 15, side="bottom")                                   # screen after the last row: count from K
    assert seats.best_seat(h2)["row"] == "D"


def test_best_seat_skips_taken_and_prefers_the_dearer_class():
    taken = {("H", x) for x in range(15)} | {("G", 7)}
    b = seats.best_seat(grid(11, 15, taken=taken))
    assert b["row"] == "G" and b["x"] in (6, 8)                        # H full, G's centre taken: next to it
    vip = grid(11, 15, classes={"H": "VIP"})
    assert seats.best_seat(vip)["cls"] == "VIP" and seats.best_seat(vip)["row"] == "H"


def test_best_seat_none_when_the_zone_is_full():
    zone = {(chr(ord("A") + i), x) for i in range(11) for x in range(15)}
    assert seats.best_seat(grid(11, 15, taken=zone)) is None
    assert seats.best_seat(grid(11, 15, taken=zone), statuses=False)["row"] == "H"


def test_compact_roundtrip():
    h = seats.normalise("reel", fx("reel"))
    shape, st = seats.compact(h)
    assert shape["s"] == "top" and shape["r"][0][0] == "E" and len(st) == len(shape["r"])
    assert "".join(st).count("x") == 3 and "".join(st).count("w") == 1
    back = seats.expand(shape, st)
    assert tally(back) == tally(h) and seats.counts(back) == seats.counts(h)
    assert seats.shape_key(shape) == seats.shape_key(json.loads(json.dumps(shape)))


# ---------------------------------------------------------------- freshness, picking, caps
NOW = datetime(2026, 9, 27, 18, 0, tzinfo=DUBAI)


def test_fresh_is_under_90_minutes():
    assert seats.fresh({"at": (NOW - timedelta(minutes=89)).isoformat()}, NOW)
    assert not seats.fresh({"at": (NOW - timedelta(minutes=90)).isoformat()}, NOW)
    assert seats.fresh({"at": (NOW + timedelta(minutes=4)).isoformat()}, NOW)          # stamped after the run began
    assert not seats.fresh({"at": (NOW + timedelta(minutes=6)).isoformat()}, NOW)
    assert not seats.fresh({"at": "garbage"}, NOW) and not seats.fresh(None, NOW)
    assert seats.fresh({"at": "2026-09-27T17:30:00"}, NOW.replace(tzinfo=None))   # naive = Dubai


def show(chain, cin, t, sid="1", day="2026-09-27", **kw):
    return {"cinema": cin, "film": "f", "date": day, "time": t, "hall_label": "H", "book": "https://x/launch/ticketing/" + "0" * 36,
            "_chain": chain, "_sid": sid, **kw}


def test_pick_window_round_robin_and_resample():
    shows = [show("star", "s-a", "18:00"), show("star", "s-a", "18:30", "2"), show("star", "s-a", "20:59", "3"),
             show("star", "s-a", "21:01", "4"), show("star", "s-b", "19:00", "5"), show("star", "s-b", "19:00", "5"),
             show("other", "r", "18:30"), show("star", "s-c", "18:40", sid=None), show("star", "s-a", "18:30", "9", day="2026-09-28")]
    got = seats.pick(shows, NOW)
    assert list(got) == ["star"]
    assert [(s["cinema"], s["time"]) for s in got["star"]] == [("s-a", "18:30"), ("s-b", "19:00"), ("s-a", "20:59")]
    recent = {seats.show_key(shows[1]): {"at": (NOW - timedelta(minutes=10)).isoformat()}}
    assert [s["time"] for s in seats.pick(shows, NOW, recent)["star"]] == ["20:59", "19:00"]


class Clock:
    def __init__(self): self.t = 0.0; self.sleeps = []
    def __call__(self): return self.t
    def sleep(self, d): self.sleeps.append(d); self.t += d


def test_budget_caps_requests_and_spaces_them():
    c = Clock()
    b = seats.Budget(cap=3, gap=1.0, clock=c, sleep=c.sleep)

    class S(FakeSession):
        def request(self, method, url, **kw):
            c.t += 0.2
            return super().request(method, url, **kw)
    s = S({"https://x/b": (302, "/b2")})
    m = seats._Metered(s, b)
    m.get("https://x/a"); m.get("https://x/b")
    assert b.used == 3 and not b.can()
    with pytest.raises(seats._Spent):
        m.get("https://x/c")
    assert len(s.calls) == 3 and all(abs(d - 0.8) < 1e-9 for d in c.sleeps)     # 1 s between starts


def test_sample_respects_60_per_chain_and_never_raises():
    shows = [show("novo", f"n{i}", f"{18 + i // 60:02d}:{i % 60:02d}", str(i)) for i in range(1, 150)]
    shows = [s for s in shows if s["time"] > "18:00"]
    calls = Counter()
    raw = fx("novo")

    def fake(budget):
        def fn(s):
            if not budget.can(): raise seats._Spent()
            budget.spend(1); calls["novo"] += 1
            if s["_sid"] == "10": raise ValueError("one bad show")   # cinema n10: second in the round robin
            return raw
        return fn, 1
    budgets = {}

    def budget_for(c):
        budgets[c] = seats.Budget(clock=Clock(), sleep=lambda d: None)
        return budgets[c]
    orig = seats._sampler
    seats._sampler = lambda chain, budget: fake(budget)
    try:
        got, rep = seats.sample(shows, NOW, budget_for=budget_for)
    finally:
        seats._sampler = orig
    assert calls["novo"] == 60 and rep["novo"]["requests"] == 60 and rep["novo"]["sampled"] == 59
    assert "one bad show" in rep["novo"]["error"]
    e = next(iter(got.values()))
    assert e["total"] == 42 and e["free"] == 40 and e["st"] and e["shape"]["s"] == "top"


def test_blocked_chain_stops_at_once():
    n = Counter()

    def fn(s):
        n["x"] += 1
        raise seats._Blocked("403")
    orig = seats._sampler
    seats._sampler = lambda chain, budget: (fn, 1)
    try:
        got, rep = seats.sample([show("star", "a", "18:30"), show("star", "b", "18:40", "2")], NOW)
    finally:
        seats._sampler = orig
    assert n["x"] == 1 and got == {} and rep["star"]["error"].startswith("stopped")


# ---------------------------------------------------------------- the step
def data_with(shows):
    return {"cinemas": {"n1": {"chain": "novo"}, "s1": {"chain": "star"}, "r1": {"chain": "roxy"}}, "shows": shows}


def test_step_strips_sid_keeps_maps_and_attaches_only_fresh(tmp_path, monkeypatch):
    mod = step()
    seats.KEPT.clear()
    seats.keep("novo", "n1", "2D", "2026-09-27", fx("novo"))
    seats.keep("novo", "n1", "junk", "2026-09-27", {"nope": 1})         # unusable: nothing kept, nothing raised
    shows = [{"cinema": "n1", "film": "f", "date": "2026-09-27", "time": "18:30", "hall_label": "2D", "_sid": "9|1"},
             {"cinema": "n1", "film": "g", "date": "2026-09-27", "time": "19:30", "hall_label": "2D", "_sid": "9|2"},
             {"cinema": "r1", "film": "f", "date": "2026-09-27", "time": "18:30", "hall_label": "Gold"}]
    occ = {"shows": {seats.show_key(shows[0]): {"free": 5, "total": 42, "at": (NOW - timedelta(minutes=30)).isoformat(), "m": "k1", "st": ["o"], "best": None},
                     seats.show_key(shows[1]): {"free": 9, "total": 42, "at": (NOW - timedelta(minutes=100)).isoformat(), "m": "k1", "st": ["o"], "best": None}},
           "maps": {"k1": {"s": "top", "c": [], "r": [["A", "0"]]}}}
    (tmp_path / "occupancy.json").write_text(json.dumps(occ), encoding="utf-8")
    d = data_with(shows)
    got = mod.run(d, {"offline": True, "now": NOW.isoformat(), "data_dir": str(tmp_path)})
    assert all("_sid" not in s for s in d["shows"])
    assert d["shows"][0]["seats"]["free"] == 5 and "seats" not in d["shows"][1] and "seats" not in d["shows"][2]
    assert got["maps_kept"] == 1 and got["attached"] == 1 and got["drawn"] == 2
    sm = json.loads((tmp_path / "seatmaps.json").read_text(encoding="utf-8"))
    (hk, h), = sm["halls"].items()
    k = h["m"]
    assert sm["v"] == 2 and hk == "n1|2D|#" + k and k in sm["maps"]
    assert d["shows"][0]["seatmap"] == k == d["shows"][1]["seatmap"] and "seatmap" not in d["shows"][2]
    assert set(d["seatmaps"]["maps"]) == {"k1", k}
    assert seats.KEPT == {}


def test_step_survives_a_corrupt_state_file(tmp_path):
    mod = step()
    (tmp_path / "occupancy.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "occupancy.json.bak").write_text(json.dumps({"shows": {}, "maps": {}}), encoding="utf-8")
    d = data_with([{"cinema": "s1", "film": "f", "date": "2026-09-27", "time": "18:30", "hall_label": "N", "_sid": 5}])
    mod.run(d, {"offline": True, "now": NOW.isoformat(), "data_dir": str(tmp_path)})
    assert "_sid" not in d["shows"][0] and "seatmaps" not in d
    assert any(p.name.startswith("occupancy.json.corrupt-") for p in tmp_path.iterdir())


def test_step_samples_online_and_records(tmp_path, monkeypatch):
    mod = step()
    raw = fx("reel")
    monkeypatch.setattr(seats, "_sampler", lambda chain, budget: ((lambda s: (budget.spend(1), raw)[1]), 1))
    now = datetime.now(DUBAI).replace(second=0, microsecond=0)          # a sample is stamped with the real clock
    at = now + timedelta(hours=1)
    d = {"cinemas": {"re": {"chain": "reel"}}, "shows": [
        {"cinema": "re", "film": "f", "date": at.date().isoformat(), "time": at.strftime("%H:%M"), "hall_label": "Premium 19",
         "_sid": "0001|718096|PREMIUM|Premium 19"}]}
    got = mod.run(d, {"offline": False, "now": now.isoformat(), "data_dir": str(tmp_path)})
    s = d["shows"][0]
    assert s["seats"]["free"] == 36 and s["seats"]["total"] == 39 and s["seats"]["best"]["row"]
    assert got["chains"]["reel"]["sampled"] == 1 and got["attached"] == 1
    occ = json.loads((tmp_path / "occupancy.json").read_text(encoding="utf-8"))
    assert len(occ["shows"]) == 1 and occ["maps"]


# ---------------------------------------------------------------- reader hooks
def test_reader_hook_keeps_what_the_price_sample_read(monkeypatch):
    from readers import common
    seats.KEPT.clear()
    common.keep_layout("cineroyal", "cineroyal-deerfields-mall", "ROYAL PLUS", "2026-09-27", fx("cineroyal"))
    common.keep_layout("star", "x", "y", "z", object())                   # never raises
    assert [k.rpartition("#")[0] for k in seats.KEPT] == ["cineroyal-deerfields-mall|ROYAL PLUS|"]   # no screen: per shape
    seats.KEPT.clear()


# ---------------------------------------------------------------- site: data files and the chunk
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


@pytest.fixture(scope="module")
def site_out(tmp_path_factory):
    d = json.load(open(DATA, encoding="utf-8"))
    gen = seats._parse_at(d["generated"])
    s0 = next(s for s in d["shows"] if (s["date"], s["time"]) > (gen.date().isoformat(), gen.strftime("%H:%M")))
    s1 = next(s for s in d["shows"] if s is not s0 and s["cinema"] != s0["cinema"])
    shape, st = seats.compact(seats.normalise("reel", fx("reel")))
    key = seats.shape_key(shape)
    s0["seats"] = {"free": 36, "total": 39, "at": (gen - timedelta(minutes=20)).isoformat(), "m": key, "st": st,
                   "best": {"row": "C", "x": 4}}
    s1["seats"] = {"free": 1, "total": 39, "at": (gen - timedelta(minutes=200)).isoformat(), "m": key, "st": st, "best": None}
    s1["seatmap"] = key
    d["seatmaps"] = {"maps": {key: shape}}
    p = tmp_path_factory.mktemp("seatdata") / "latest.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    out = str(tmp_path_factory.mktemp("seatsite"))
    build.build(str(p), DISC, out, noindex=False)
    return out, s0, s1, key


def test_site_writes_occupancy_and_per_cinema_maps(site_out):
    out, s0, s1, key = site_out
    occ = json.load(open(os.path.join(out, "data", "occupancy.json"), encoding="utf-8"))["o"]
    k0 = f"{s0['cinema']}|{s0['film']}|{s0['date']}|{s0['time']}"
    assert list(occ) == [k0] and occ[k0][0][1:3] == [36, 39]              # the stale one is not published
    f0 = json.load(open(os.path.join(out, "data", "seats", f"{s0['cinema']}.json"), encoding="utf-8"))
    row = f0["s"][f"{s0['film']}|{s0['date']}|{s0['time']}"][0]
    assert row[1] == key and row[2:6] == ["C", 4, 36, 39] and len(row[7]) == 5
    f1 = json.load(open(os.path.join(out, "data", "seats", f"{s1['cinema']}.json"), encoding="utf-8"))
    r1 = f1["s"][f"{s1['film']}|{s1['date']}|{s1['time']}"][0]
    assert r1[1] == key and len(r1) == 4 and r1[2]                       # shape only, with the best place in it
    assert key in f1["m"]


def test_chunk_on_ticket_pages_only(site_out):
    out = site_out[0]
    home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    assert re.search(r'"seatmap":\s*"/assets/seatmap\.[0-9a-f]{10}\.js"', home)
    card = next(p for p in Path(out, "cards").rglob("index.html"))
    assert "seatmap." not in card.read_text(encoding="utf-8")
    css = open(os.path.join(out, "assets", "cinema.css"), encoding="utf-8").read()
    assert ".tk-hall" in css


def test_no_session_handle_reaches_the_site(site_out):
    out = site_out[0]
    for p in Path(out, "data").rglob("*.json"):
        assert '"_sid"' not in p.read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_chunk_parses_and_draws(tmp_path, site_out):
    node = shutil.which("node")
    built = next(Path(site_out[0], "assets").glob("seatmap.*.js"))
    r = subprocess.run([node, "--check", str(built)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    src = Path(ROOT, "src", "js", "seatmap.js").read_text(encoding="utf-8")
    shape, st = seats.compact(seats.normalise("reel", fx("reel")))
    harness = ("var K = {AR: true, lang: 'ar', esc: function (s) { return String(s); }, q: function () { return null; },"
               " qa: function () { return []; }, getJSON: function () { return Promise.resolve(null); }, C: {}};\n" + src +
               "\nprocess.stdout.write(JSON.stringify([hallSVG(" + json.dumps(shape) + "," + json.dumps(st) + ", ['C', 4]),"
               " summary(36, 39, 'C', true, 'ar'), summary(36, 39, 'C', true, 'en'), summary(null, 39, 'G', false, 'ar'),"
               " summary(0, 39, null, true, 'ar'), leftText(23, 'ar'), leftText(1, 'en'), leftText(2, 'ar')]));\n")
    (tmp_path / "t.js").write_text(harness, encoding="utf-8")
    r = subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    svg, s_ar, s_en, s_shape, s_full, l_ar, l_en, l_two = json.loads(r.stdout)
    assert svg.startswith("<svg") and svg.count('class="s x"') == 3 and svg.count('class="s w"') == 1
    assert svg.count('class="s o best"') == 1 and 'aria-hidden="true"' in svg and "rx" not in svg
    assert s_ar == "باقي 36 مقعد من 39، أحسن مقعد متاح: الصف C وسط"
    assert s_en == "36 of 39 seats left, best seat available: row C, centre"
    assert s_shape == "القاعة فيها 39 مقعد، أحسن مكان: الصف G وسط"
    assert s_full == "ما باقي مقاعد من 39"
    assert l_ar == "باقي 23 مقعد" and l_en == "1 seat left" and l_two == "باقي مقعدين"


# ================================================================ fix round 1
def test_roxy_seat_selection_page():
    h = seats.normalise("roxy", (FX / "roxy.html").read_text(encoding="utf-8"))
    assert [r["name"] for r in h["rows"]] == ["E", "D", "C", "B", "A"] and h["screen_side"] == "top"
    assert tally(h) == {"free": 54, "taken": 1, "wheelchair": 2}
    assert seats.counts(h) == {"free": 56, "total": 57}
    assert {c["name"]: c["aed"] for c in h["classes"]} == {"Standard": 43.0, "Premium View": 70.0}
    assert h["rows"][0]["seats"][0]["id"] == "E12" and h["rows"][0]["seats"][0]["col"] == "12"
    assert h["rows"][-1]["seats"][-1]["x"] == 10                       # the trailing aisle cell (11) is not a seat


class FakeResp:
    def __init__(self, url, status=200, loc=None, body=""):
        self.url, self.status_code, self.headers, self.text, self.history = url, status, ({"location": loc} if loc else {}), body, []


class FakeSession:
    """curl_cffi-like: history stays empty; follows nothing when allow_redirects=False (asserted)."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, **kw):
        assert kw.get("allow_redirects") is False, "the meter must follow redirects itself"
        self.calls.append((method, url))
        status, loc = self.routes.get(url, (200, None))
        return FakeResp(url, status, loc)


def test_redirects_are_counted_and_spaced_even_with_an_empty_history():
    c = Clock()
    b = seats.Budget(cap=10, gap=1.0, clock=c, sleep=c.sleep)
    s = FakeSession({"https://x/a": (302, "/b"), "https://x/b": (303, "https://x/c")})
    r = seats._Metered(s, b).get("https://x/a")
    assert r.url == "https://x/c" and b.used == 3 and [u for _, u in s.calls] == ["https://x/a", "https://x/b", "https://x/c"]
    assert len(c.sleeps) == 2                                          # every hop waited for the gap
    r = seats._Metered(s, b).get("https://x/a", allow_redirects=False)
    assert r.status_code == 302 and b.used == 4                        # the caller's own no-follow is kept


def test_cap_stops_inside_a_redirect_chain():
    b = seats.Budget(cap=2, clock=Clock(), sleep=lambda d: None)
    s = FakeSession({"https://x/a": (302, "/b"), "https://x/b": (302, "/c")})
    with pytest.raises(seats._Spent):
        seats._Metered(s, b).get("https://x/a")
    assert b.used == 2 and len(s.calls) == 2


def test_stops_are_not_swallowed_by_except_exception():
    for exc in (seats._Spent, seats._Blocked):
        try:
            try:
                raise exc("x")
            except Exception:                                          # what the readers' clients catch
                pytest.fail(f"{exc.__name__} was caught by except Exception")
        except exc:
            pass


def test_429_stops_at_once():
    b = seats.Budget(cap=10, clock=Clock(), sleep=lambda d: None)
    s = FakeSession({"https://x/a": (429, None)})
    with pytest.raises(seats._Blocked):
        seats._Metered(s, b).get("https://x/a")
    assert len(s.calls) == 1


def test_deadline_stops_a_late_thread():
    c = Clock()
    b = seats.Budget(cap=10, clock=c, sleep=c.sleep, deadline=5.0)
    m = seats._Metered(FakeSession({}), b)
    m.get("https://x/a")
    c.t = 6.0
    with pytest.raises(seats._Spent):
        m.get("https://x/b")


def test_vox_abandons_the_order_when_the_cap_stops_mid_sample():
    from readers import vox
    order = "abc_0002-1"
    base = vox.BASE
    routes = {f"{base}/booking/0002-1": (302, f"/booking/{order}/guest"),
              f"{base}/booking/{order}/seats/fetch": (302, f"/booking/{order}/seats/processing")}
    s = FakeSession(routes)
    b = seats.Budget(cap=5, clock=Clock(), sleep=lambda d: None, reserve=1)
    client = seats._Direct(seats._Metered(s, b, reserve_for=seats.ABANDON))
    with pytest.raises(seats._Spent):
        vox._sample_prices(client, f"{base}/booking/0002-1")
    urls = [u for _, u in s.calls]
    assert any("/abandon" in u for u in urls) and b.used == 5 and len(urls) == 5


def test_cineroyal_warm_up_is_counted_once(monkeypatch):
    import requests
    seen = []

    def fake(self, method, url, **kw):
        seen.append(url)
        r = requests.models.Response(); r.status_code = 200; r._content = b"{}"; r.url = url
        return r
    monkeypatch.setattr(requests.Session, "request", fake)
    b = seats.Budget(clock=Clock(), sleep=lambda d: None)
    fn, cost = seats._sampler("cineroyal", b)
    assert cost() == 2
    fn({"_sid": "2|7|2026-09-27|11:40PM|x"})
    assert cost() == 1
    fn({"_sid": "2|7|2026-09-27|11:50PM|x"})
    assert b.used == 3 and seen[0].endswith("/home/nowShowing") and sum("nowShowing" in u for u in seen) == 1


def test_shapes_are_per_screen_and_ambiguous_labels_show_nothing(tmp_path):
    mod = step()
    seats.KEPT.clear()
    novo = fx("novo")
    reel = fx("reel")
    seats.keep("star", "s1", "NORMAL", "2026-09-27", {"Records": fx("star")["Records"]}, screen="SCREEN 1")
    seats.keep("novo", "s1", "NORMAL", "2026-09-27", novo, screen="SCREEN 2")          # another screen, same label
    seats.keep("reel", "r1", "Premium 19", "2026-09-27", reel, screen="Premium 19")
    seats.keep("novo", "n1", "2D", "2026-09-27", novo)                                   # no screen known, one shape
    seats.keep("novo", "v1", "Std", "2026-09-27", novo)
    seats.keep("reel", "v1", "Std", "2026-09-28", reel)                                  # no screen, two shapes seen
    base = {"film": "f", "date": "2026-09-27", "time": "18:30"}
    shows = [{**base, "cinema": "s1", "hall_label": "NORMAL", "_screen": "SCREEN 1"},
             {**base, "cinema": "s1", "hall_label": "NORMAL", "_screen": "SCREEN 2", "time": "19:00"},
             {**base, "cinema": "s1", "hall_label": "NORMAL", "time": "20:00"},
             {**base, "cinema": "r1", "hall_label": "Premium 19", "_screen": "Premium 19"},
             {**base, "cinema": "n1", "hall_label": "2D"},
             {**base, "cinema": "v1", "hall_label": "Std"}]
    d = {"cinemas": {c: {"chain": "novo"} for c in ("s1", "r1", "n1", "v1")}, "shows": shows}
    mod.run(d, {"offline": True, "now": NOW.isoformat(), "data_dir": str(tmp_path)})
    got = [s.get("seatmap") for s in d["shows"]]
    k_star = seats.shape_key(seats.compact(seats.normalise("star", fx("star")))[0])
    k_novo = seats.shape_key(seats.compact(seats.normalise("novo", novo))[0])
    k_reel = seats.shape_key(seats.compact(seats.normalise("reel", reel))[0])
    assert got == [k_star, k_novo, None, k_reel, k_novo, None]
    assert all("_screen" not in s for s in d["shows"]) and set(d["seatmaps"]["maps"]) == {k_star, k_novo, k_reel}


def test_step_strips_private_keys_even_when_seats_cannot_load(tmp_path, monkeypatch):
    mod = step()
    monkeypatch.setitem(sys.modules, "seats", None)                   # `import seats` now raises ImportError
    d = data_with([{"cinema": "s1", "film": "f", "date": "2026-09-27", "time": "18:30", "_sid": 5, "_screen": "S"}])
    with pytest.raises(ImportError):
        mod.run(d, {"offline": True, "now": NOW.isoformat(), "data_dir": str(tmp_path)})
    assert d["shows"][0] == {"cinema": "s1", "film": "f", "date": "2026-09-27", "time": "18:30"}


def test_build_drops_private_show_keys():
    import pages.seats as ps
    shows = [{"cinema": "a", "_sid": 1, "_screen": "x", "time": "18:00"}]
    ps.private_off(shows)
    assert shows == [{"cinema": "a", "time": "18:00"}]
