"""W1-D3 (legend MASTER-PLAN §5.2): signals. Each chain's own read time and «أسعار ريل من 18:05»; first_seen and
/data/pulse.json; /data/rank.json with yesterday's line; the seat sampler aimed at reachable shows at the busiest
cinemas; hall labels with no all-caps word."""
import gzip
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build  # noqa: E402
import refresh  # noqa: E402
import seats  # noqa: E402
from pages import pulse  # noqa: E402

FIX = ROOT / "fixtures"
DISC = str(FIX / "sample_discounts.yaml")
HOUR = ROOT / "tests" / "fixtures" / "w1_d3_hour.json"
_spec = importlib.util.spec_from_file_location("steps_occupancy_w1d3", ROOT / "steps" / "occupancy.py")
occ = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(occ)


def read(out, *parts):
    return Path(out).joinpath(*parts).read_text(encoding="utf-8")


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ================================================================ refresh sandbox (as tests/test_hourly_safe.py)

@pytest.fixture
def sandbox(tmp_path, monkeypatch, offline_steps):
    d = tmp_path / "data"
    for name, rel in [("DATA_DIR", ""), ("RAW_DIR", "raw"), ("LATEST_PATH", "latest.json"),
                      ("HEALTH_PATH", "health.json"), ("FILMS_CACHE_PATH", "films_cache.json"),
                      ("FILM_HISTORY_PATH", "film_history.json"), ("FILM_HISTORY_BACKUP_PATH", "film_history.prev.json"),
                      ("PRICE_CACHE_PATH", "price_cache.json"), ("PRICE_CACHE_BACKUP_PATH", "price_cache.prev.json"),
                      ("NEW_FILMS_PATH", "new_films.json")]:
        monkeypatch.setattr(refresh, name, d / rel if rel else d)
    monkeypatch.setattr(refresh, "FIXTURES_DIR", FIX)
    monkeypatch.setattr(refresh.enrich_mod, "enrich", lambda data, cache_path=None, offline=False: data)
    return d


def _clock(monkeypatch, *times):
    """refresh.now_iso() answers these in turn: the run's start, then each chain's read as it finishes."""
    it = iter(times)
    last = {"t": times[0]}

    def now():
        last["t"] = next(it, last["t"])
        return last["t"]
    monkeypatch.setattr(refresh, "now_iso", now)


def _readers(monkeypatch, failing=()):
    def make(chain):
        def fn(days=2, **kw):
            if chain in failing:
                raise RuntimeError(f"{chain} down")
            return json.loads((FIX / f"{chain}.json").read_text(encoding="utf-8"))
        return fn
    monkeypatch.setattr(refresh, "CHAIN_READERS", {c: make(c) for c in refresh.ALL_CHAINS})


# ================================================================ 1. each chain's own read time

def test_each_chain_carries_its_own_read_time(sandbox, monkeypatch):
    """The chains are read one after another: each one's `at` is when its own read finished, in latest.json, the
    runner's city slices and health.json — not the run's start (all seven used to carry one merge time)."""
    _readers(monkeypatch)
    _clock(monkeypatch, "2026-09-26T12:00:00+04:00", "2026-09-26T12:04:00+04:00",
           "2026-09-26T12:09:00+04:00", "2026-09-26T12:15:00+04:00")
    assert refresh.refresh(chains=["vox", "reel", "novo"], no_verdicts=True) == 0
    latest = _load(sandbox / "latest.json")
    assert latest["generated"] == "2026-09-26T12:00:00+04:00"
    assert {c: v["at"] for c, v in latest["chains"].items()} == {
        "vox": "2026-09-26T12:04:00+04:00", "reel": "2026-09-26T12:09:00+04:00", "novo": "2026-09-26T12:15:00+04:00"}
    dubai = _load(sandbox / "dubai.json")
    assert dubai["chains"]["reel"]["at"] == "2026-09-26T12:09:00+04:00" and dubai["chains"]["reel"]["ok"] is True
    assert _load(sandbox / "health.json")["vox"]["at"] == "2026-09-26T12:04:00+04:00"
    assert _load(sandbox / "raw" / "reel.json")["_read_at"] == "2026-09-26T12:09:00+04:00"   # for a resumed run
    assert "_read_at" not in json.dumps(latest)


def test_a_resumed_raw_keeps_the_time_it_was_read(sandbox, monkeypatch):
    """A killed run resumed within RESUME_WINDOW: its raw file says when it was read (`_read_at`); a raw file from
    before the tag existed reads as the unfinished run's start, never as now."""
    _readers(monkeypatch)
    raw = sandbox / "raw"
    raw.mkdir(parents=True)
    (raw / ".run.json").write_text(json.dumps({"id": "run-a", "started": "2026-09-26T10:30:00+04:00"}), encoding="utf-8")
    (raw / "vox.json").write_text(json.dumps({**_load(FIX / "vox.json"), "_run_id": "run-a",
                                              "_read_at": "2026-09-26T10:41:00+04:00"}), encoding="utf-8")
    (raw / "novo.json").write_text(json.dumps({**_load(FIX / "novo.json"), "_run_id": "run-a"}), encoding="utf-8")
    _clock(monkeypatch, "2026-09-26T12:10:00+04:00", "2026-09-26T12:14:00+04:00")
    assert refresh.refresh(chains=["vox", "novo", "reel"], no_verdicts=True) == 0
    at = {c: v["at"] for c, v in _load(sandbox / "latest.json")["chains"].items()}
    assert at == {"vox": "2026-09-26T10:41:00+04:00", "novo": "2026-09-26T10:30:00+04:00",
                  "reel": "2026-09-26T12:14:00+04:00"}


@pytest.fixture
def stale_reel(sandbox, monkeypatch):
    """Reel's last good read (its raw file) is 3 h old, 18:05: this run, 21:05, its reader fails while VOX and Novo
    read fresh."""
    _readers(monkeypatch)
    _clock(monkeypatch, "2026-09-26T18:00:00+04:00", "2026-09-26T18:02:00+04:00", "2026-09-26T18:05:00+04:00",
           "2026-09-26T18:07:00+04:00")
    assert refresh.refresh(chains=["vox", "reel", "novo"], no_verdicts=True) == 0
    _readers(monkeypatch, failing=("reel",))
    _clock(monkeypatch, "2026-09-26T21:05:00+04:00", "2026-09-26T21:09:00+04:00", "2026-09-26T21:14:00+04:00")
    assert refresh.refresh(chains=["vox", "reel", "novo"], no_verdicts=True) == 0
    return sandbox


def test_a_chain_read_3h_ago_keeps_its_own_time_in_the_slice(stale_reel):
    dubai = _load(stale_reel / "dubai.json")
    reel = dubai["chains"]["reel"]
    assert (reel["ok"], reel["at"], reel["error"]) == (False, "2026-09-26T18:05:00+04:00", "reel down")
    assert dubai["chains"]["vox"]["at"] == "2026-09-26T21:09:00+04:00" and dubai["chains"]["vox"]["ok"]
    assert _load(stale_reel / "sharjah.json")["chains"]["novo"]["at"] == "2026-09-26T21:14:00+04:00"


@pytest.fixture
def stale_site(stale_reel, tmp_path):
    out = tmp_path / "out"
    build.build(str(stale_reel / "latest.json"), DISC, str(out))
    return out


def test_the_stale_chain_labels_its_prices_and_the_others_do_not(stale_site):
    """«أسعار ريل من 18:05» under Reel's prices (the voice table's line); nothing under a fresh chain's; the
    English page says "Reel prices from 18:05"; /sources/ lists each chain's own time."""
    reel = read(stale_site, "dubai", "reel-dubai-mall", "index.html")
    note = '<p class="hint" data-read-old="reel">أسعار ريل من 18:05</p>'
    assert note in reel
    assert reel.index("القاعات والأسعار") < reel.index(note)          # under the prices, not above them
    en = read(stale_site, "en", "dubai", "reel-dubai-mall", "index.html")
    assert '<p class="hint" data-read-old="reel">Reel prices from 18:05</p>' in en
    fresh = [p for p in stale_site.glob("*/*/index.html") if p.parent.name.startswith(("vox-", "novo-"))]
    assert fresh and not any("data-read-old" in p.read_text(encoding="utf-8") for p in fresh)
    sources = read(stale_site, "sources", "index.html")
    for at in ("2026-09-26T21:09:00+04:00", "2026-09-26T18:05:00+04:00", "2026-09-26T21:14:00+04:00"):
        assert sources.count(f'data-at="{at}"') == 1


class _Site:
    """What read_label and hall_label read from a site: d, now, h."""

    def __init__(self, chains, now):
        self.d = {"chains": chains}
        self.now = datetime.fromisoformat(now)
        self.h = build.Halls(str(ROOT / "halls.yaml"))


@pytest.mark.parametrize("at,now,ar,en", [
    ("2026-09-26T19:06:00+04:00", "21:05", "", ""),                                        # 1 h 59 min: fresh enough
    ("2026-09-26T19:04:00+04:00", "21:05", "أسعار ريل من 19:04", "Reel prices from 19:04"),
    ("2026-09-25T23:30:00+04:00", "21:05", "أسعار ريل من أمس 23:30", "Reel prices from yesterday 23:30"),
    ("2026-09-21T18:05:00+04:00", "21:05", "أسعار ريل من 21 سبتمبر", "Reel prices from 21 September"),
    ("2026-09-26T15:05:00+00:00", "21:06", "أسعار ريل من 19:05", "Reel prices from 19:05"),  # read in UTC, told in UAE time
])
def test_read_label(at, now, ar, en):
    site = _Site({"reel": {"ok": True, "at": at}}, f"2026-09-26T{now}:00+04:00")
    assert pulse.read_label(site, "reel", "ar") == ar
    assert pulse.read_label(site, "reel", "en") == en
    assert pulse.read_label(site, "vox", "ar") == ""                                         # no read time: no claim


def test_fresh_chains_add_nothing_to_any_page(tmp_path):
    data = _load(FIX / "sample_latest.json")
    for info in data["chains"].values():
        info.update(ok=True, at=data["generated"])
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "out"
    build.build(str(p), DISC, str(out))
    pages = list(out.rglob("index.html"))
    assert len(pages) > 50 and not any("data-read-old" in f.read_text(encoding="utf-8") for f in pages)
    # the sample data's films carry verdicts, genres and people: pulse.json codes them and names the likenesses
    p = json.loads(read(out, "data", "pulse.json"))
    want = {"yes": "y", "mixed": "m", "skip": "s"}
    for fid, f in data["films"].items():
        if f.get("status") == "archived":
            assert fid not in p                                      # gone films are not news
            continue
        assert p[fid][0] == want.get((f.get("verdict") or {}).get("verdict"), "")
    assert any(row[3] for f, row in p.items() if f != "_")


# ================================================================ 2. first_seen, pulse.json, rank.json

@pytest.fixture
def two_days(sandbox, monkeypatch, tmp_path):
    """Day 1 (the seeding run) at 2026-09-26 12:00, day 2 at 2026-09-27 12:00; the site built from day 2."""
    _readers(monkeypatch)
    _clock(monkeypatch, "2026-09-26T12:00:00+04:00")
    assert refresh.refresh(chains=["vox", "reel", "novo"], no_verdicts=True) == 0
    day1 = _load(sandbox / "latest.json")
    _clock(monkeypatch, "2026-09-27T12:00:00+04:00")
    assert refresh.refresh(chains=["vox", "reel", "novo"], no_verdicts=True) == 0
    out = tmp_path / "out2"
    build.build(str(sandbox / "latest.json"), DISC, str(out))
    return sandbox, day1, out


def test_pulse_publishes_film_historys_first_seen(two_days):
    data_dir, _day1, out = two_days
    hist = _load(data_dir / "film_history.json")
    latest = _load(data_dir / "latest.json")
    p = json.loads(read(out, "data", "pulse.json"))
    showing = [f for f, v in latest["films"].items() if v.get("status") != "archived"]
    assert showing and all(p[f][1] == hist[f]["first_seen"] for f in showing)
    assert all(latest["films"][f]["first_seen"] == hist[f]["first_seen"] for f in showing)
    assert p["_"] == [latest["generated"], "2026-09-26"]         # the seed date: every film present then carries it


def test_pulse_shape_and_size(two_days):
    _d, _day1, out = two_days
    body = read(out, "data", "pulse.json")
    p = json.loads(body)
    for fid, row in p.items():
        if fid == "_":
            continue
        v, first, coming, sims = row
        assert v in ("y", "m", "s", "") and isinstance(first, str) and isinstance(coming, str)
        assert len(sims) <= 4 and all(o in p and re.match(r"^[dcgl]:.+", why) for o, why in sims)
    assert len(gzip.compress(body.encode("utf-8"))) <= 8 * 1024


def test_pulse_lists_coming_films_and_carries_the_release_date_once_open():
    prev = {"coming": {"new-film": {"release_date": "2026-10-01"}}, "films": {"old": {"released": "2026-09-18"}}}
    cur = {"films": {"new-film": {}, "old": {}, "gone": {"status": "archived"}}}
    refresh.carry_released(cur, prev)
    assert cur["films"] == {"new-film": {"released": "2026-10-01"}, "old": {"released": "2026-09-18"},
                            "gone": {"status": "archived"}}


def test_rank_has_yesterdays_line_after_two_days(two_days):
    data_dir, day1, out = two_days
    r = json.loads(read(out, "data", "rank.json"))
    assert (r["d"], r["y"]) == ("2026-09-27", "2026-09-26")
    assert sorted(_load(data_dir / "latest.json")["rank_days"]) == ["2026-09-26", "2026-09-27"]
    # yesterday, per city, is day 1's own read of 26 September
    y1 = refresh.day_counts(day1)["2026-09-26"]
    assert r["c"]["dubai"]["y"] and r["c"]["dubai"]["y"] == pulse.Pulse.ordered(y1["dubai"])
    # today keeps the fullest read: day 1 saw all of the 27th, day 2 only what was left after 11:30
    assert r["c"]["dubai"]["d"] == pulse.Pulse.ordered(refresh.day_counts(day1)["2026-09-27"]["dubai"])
    ranks = r["c"]["dubai"]["d"]
    assert ranks == sorted(ranks, key=lambda x: (-x[1], -x[2], x[0]))


def test_rank_uae_reads_the_price_history(two_days, tmp_path, monkeypatch):
    """UAE lists: price_history.jsonl's day lines (the /boxoffice/ source)."""
    data_dir, _day1, _out = two_days
    hist = tmp_path / "ph.jsonl"
    hist.write_text(json.dumps({"date": "2026-09-26", "at": "x", "n": 9, "priced": 9, "prices": [], "parts": [],
                                "films": {"heart-of-the-beast": [7, 3], "resident-evil": [2, 1]}}) + "\n", encoding="utf-8")
    monkeypatch.setenv("CINEMA_PRICE_HISTORY", str(hist))
    out = tmp_path / "out3"
    build.build(str(data_dir / "latest.json"), DISC, str(out))
    r = json.loads(read(out, "data", "rank.json"))
    assert r["uae"]["y"] == [["heart-of-the-beast", 7, 3], ["resident-evil", 2, 1]]
    assert r["uae"]["d"]                                                    # today from this build's own read


def test_rank_days_keep_the_fullest_read_and_drop_old_dates():
    prev = {"rank_days": {"2026-09-20": {"dubai": {"a": [5, 1]}},
                          "2026-09-26": {"dubai": {"a": [10, 2], "b": [4, 1]}}}}
    cur = {"cinemas": {"c1": {"city": "dubai"}}, "films": {"a": {}, "b": {}},
           "shows": [{"cinema": "c1", "film": "a", "date": "2026-09-26", "time": "22:00"},
                     {"cinema": "c1", "film": "b", "date": "2026-09-27", "time": "10:00"}]}
    days = refresh.update_rank_days(cur, prev, "2026-09-27T00:20:00+04:00")
    assert days == {"2026-09-26": {"dubai": {"a": [10, 2], "b": [4, 1]}}, "2026-09-27": {"dubai": {"b": [1, 1]}}}


# ================================================================ 3. the sampler's aim

def _hour():
    """The fixture hour: every VOX, Reel and Star show starting 19:25–22:25 on 28 Sep (the Fold's real data)."""
    fx = json.loads(HOUR.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(fx["now"])
    shows = [{"cinema": c, "date": fx["date"], "time": t, "film": f, "hall_label": h, "_chain": fx["chains"][c],
              "_sid": "sid", **({"book": "https://example.invalid/b"} if b else {})} for c, t, f, h, b in fx["shows"]]
    day = [{"cinema": c, "date": fx["date"]} for c, n in fx["busy"].items() for _ in range(n)]
    return fx, now, shows, day


def test_a_fixture_hour_samples_shows_starting_within_3h():
    """The package's acceptance: in a fixture hour ≥ 60 % of the sampled shows start within 3 h (all do), and
    most are reachable (30 to 180 min out); each chain gets what its 60-request cap can read."""
    _fx, now, shows, day = _hour()
    sel = occ.aim(shows, now, day_shows=day)
    lead = [(seats._start(s) - now).total_seconds() / 60 for s in sel]
    assert sel and sum(1 for x in lead if 0 < x <= 180) / len(sel) >= 0.6
    assert sum(1 for x in lead if 30 <= x <= 180) / len(sel) >= 0.8
    assert {c: sum(1 for s in sel if s["_chain"] == c) for c in ("vox", "reel", "star")} == {"vox": 6, "reel": 19, "star": 60}


def test_vox_goes_to_its_busiest_cinemas_one_each():
    """Before: the six alphabetically first VOX cinemas, every hour. Now: the six busiest, one show each."""
    fx, now, shows, day = _hour()
    vox = [s for s in occ.aim(shows, now, day_shows=day) if s["_chain"] == "vox"]
    busiest = sorted((c for c in fx["busy"] if c.startswith("vox-")), key=lambda c: (-fx["busy"][c], c))
    with_shows = [c for c in busiest if any(s["cinema"] == c and s.get("book") for s in shows)]
    assert [s["cinema"] for s in vox] == with_shows[:6]
    assert "vox-mall-of-the-emirates" in {s["cinema"] for s in vox}
    old = {s["cinema"] for s in seats.pick(shows, now)["vox"][:occ.capacity("vox")]}
    assert old == set(sorted({s["cinema"] for s in shows if s["_chain"] == "vox" and s.get("book")})[:6])
    assert old != {s["cinema"] for s in vox}


def test_aim_skips_a_recent_sample_and_puts_an_older_one_after_the_unsampled():
    now = datetime.fromisoformat("2026-09-28T19:00:00+04:00")
    base = {"_chain": "vox", "date": "2026-09-28", "film": "f", "hall_label": "Standard", "book": "https://x.invalid/b"}
    a = {**base, "cinema": "vox-a", "time": "21:00"}
    b = {**base, "cinema": "vox-b", "time": "21:00"}
    c = {**base, "cinema": "vox-c", "time": "21:00"}
    d = {**base, "cinema": "vox-d", "time": "19:10"}       # 10 min out: after every reachable one
    recent = {seats.show_key(a): {"at": "2026-09-28T18:40:00+04:00"},    # 20 min old: not sampled again
              seats.show_key(b): {"at": "2026-09-28T17:55:00+04:00"}}    # 65 min old: still shown, so after c
    busy = [{"cinema": x, "date": "2026-09-28"} for x in ("vox-d", "vox-d", "vox-b", "vox-b", "vox-c")]
    assert [s["cinema"] for s in occ.aim([a, b, c, d], now, recent=recent, day_shows=busy)] == ["vox-c", "vox-b", "vox-d"]
    assert [s["cinema"] for s in occ.aim([a, b, c, d], now, recent=recent, day_shows=busy, cap=10)] == ["vox-c"]


def test_aim_prefers_the_show_about_two_hours_out_inside_a_cinema():
    now = datetime.fromisoformat("2026-09-28T19:00:00+04:00")
    base = {"_chain": "star", "date": "2026-09-28", "film": "f", "hall_label": "NORMAL", "_sid": "s", "cinema": "star-a"}
    shows = [{**base, "time": t} for t in ("19:40", "20:50", "21:10", "21:55")]
    assert [s["time"] for s in occ.aim(shows, now, cap=2)] == ["20:50", "21:10"]     # 110 and 130 min out


def test_capacity_is_what_the_sampler_can_read_under_the_cap():
    assert seats.MAX_REQ == 60
    assert {c: occ.capacity(c) for c in seats.SUPPORTED} == {
        "star": 60, "cineroyal": 59, "novo": 60, "cinemacity": 60, "reel": 19, "vox": 6, "roxy": 60}
    pytest.importorskip("curl_cffi")
    _fn, cost = seats._sampler("vox", seats.Budget())
    assert cost() == occ.COST["vox"]


def test_the_step_hands_the_sampler_only_the_aimed_shows(monkeypatch, tmp_path):
    fx, now, shows, _day = _hour()
    data = {"cinemas": {c: {"chain": ch} for c, ch in fx["chains"].items()},
            "shows": [{k: v for k, v in s.items() if k != "_chain"} for s in shows]}
    seen = {}

    def fake_sample(todo, t, recent=None, **kw):
        seen["todo"] = todo
        return {}, {"vox": {"requests": 0, "sampled": 0, "picked": 0, "error": None}}
    monkeypatch.setattr(seats, "sample", fake_sample)
    got = occ.run(data, {"now": now.isoformat(), "data_dir": str(tmp_path), "offline": False})
    per = {c: sum(1 for s in seen["todo"] if s["_chain"] == c) for c in ("vox", "reel", "star")}
    assert per["vox"] == 6 and per["reel"] <= 19 and per["star"] <= 60
    assert got["chains"]["vox"]["aimed"] == 6 and got["chains"]["vox"]["requests"] == 0
    assert all("_sid" not in s for s in data["shows"])                  # the handles are still never published


# ================================================================ 4. hall labels

REAL_HALLS = [   # every (chain, hall code, raw label) in the real data on 2026-09-28 (the Fold and cinema-legend)
    ('cinemacity', 'IMAX', 'IMAX'), ('cinemacity', 'OTHER', 'Arthouse'), ('cinemacity', 'OTHER', 'InfinityVision'),
    ('cinemacity', 'OTHER', 'PLF'), ('cinemacity', 'Standard', 'Standard'), ('cinemacity', 'VIP', 'Luxury Seats'),
    ('cinemacity', 'VIP', 'VIP'), ('cineroyal', 'KIDS', 'ROYAL KIDS'), ('cineroyal', 'OTHER', 'ROYAL PLUS'),
    ('cineroyal', 'Standard', 'STANDARD'), ('cineroyal', 'VIP', 'ROYAL CLASS'), ('novo', 'Standard', '2D'),
    ('reel', 'KIDS', 'Reel Junior Screen 6'), ('reel', 'OTHER', 'Dolby Screen 7'),
    ('reel', 'OTHER', 'Screen 2 Dolby'), ('reel', 'OTHER', 'Screen 21 – Dolby'), ('reel', 'SCREENX', 'Screen 8'),
    ('reel', 'SUITES', 'Platinum Suite 6'), ('reel', 'SUITES', 'Platinum Suites 1'),
    ('reel', 'SUITES', 'Platinum Suites 2'), ('reel', 'SUITES', 'Platinum Suites 3'),
    ('reel', 'SUITES', 'Platinum Suites 4'), ('reel', 'SUITES', 'Platinum Suites 5'),
    ('reel', 'Standard', 'Screen 1'), ('reel', 'Standard', 'Screen 10'), ('reel', 'Standard', 'Screen 11'),
    ('reel', 'Standard', 'Screen 12'), ('reel', 'Standard', 'Screen 13'), ('reel', 'Standard', 'Screen 14'),
    ('reel', 'Standard', 'Screen 2'), ('reel', 'Standard', 'Screen 3'), ('reel', 'Standard', 'Screen 4'),
    ('reel', 'Standard', 'Screen 5'), ('reel', 'Standard', 'Screen 6'), ('reel', 'Standard', 'Screen 7'),
    ('reel', 'Standard', 'Screen 9'), ('reel', 'VIP', 'Premium 15'), ('reel', 'VIP', 'Premium 16'),
    ('reel', 'VIP', 'Premium 17'), ('reel', 'VIP', 'Premium 18'), ('reel', 'VIP', 'Premium 19'),
    ('roxy', 'OTHER', '2L'), ('roxy', 'OTHER', 'BRONZE'), ('roxy', 'OTHER', 'GOLD'), ('roxy', 'OTHER', 'Gold'),
    ('roxy', 'OTHER', 'Immersive'), ('roxy', 'OTHER', 'Xtreme'), ('roxy', 'SUITES', 'Private Screen'),
    ('roxy', 'Standard', 'Silver'), ('roxy', 'Standard', 'Silver (session 151805)'),
    ('roxy', 'Standard', 'Silver (session 152433)'), ('roxy', 'VIP', 'Platinum'), ('star', 'KIDS', 'KIDS'),
    ('star', 'OTHER', '2D'), ('star', 'OTHER', 'ATMOS'), ('star', 'OTHER', 'DOLBY'), ('star', 'OTHER', 'PREMIUM'),
    ('star', 'SUITES', 'SUITES'), ('star', 'Standard', 'NORMAL'), ('vox', '4DX', '4DX'), ('vox', 'GOLD', 'GOLD'),
    ('vox', 'IMAX', 'IMAX'), ('vox', 'KIDS', 'Kids'), ('vox', 'MAX', 'MAX'), ('vox', 'OTHER', 'Couch - 2 Seater'),
    ('vox', 'OTHER', 'Premier'), ('vox', 'OTHER', 'Premium'), ('vox', 'OTHER', 'Private Cinema'),
    ('vox', 'OTHER', 'SAMSUNG ONYX'), ('vox', 'OTHER', 'THEATRE PODS in IMAX'), ('vox', 'Standard', 'Standard'),
    ('vox', 'THEATRE', 'THEATRE'),
]
ALL_CAPS = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]*[A-Z]{2}[A-Z0-9]*(?![A-Za-z0-9])")


def _fixture_halls():
    """(chain, code, label) from every reader fixture and the sample site data."""
    out = set()
    for f in FIX.glob("*.json"):
        d = _load(f)
        cins = d.get("cinemas") or {}
        chain_of = ({c["id"]: c.get("chain") for c in cins if isinstance(c, dict)} if isinstance(cins, list)
                    else {cid: c.get("chain") for cid, c in cins.items()})
        for s in d.get("shows") or []:
            out.add((chain_of.get(s.get("cinema")) or f.stem, s.get("hall") or "OTHER", s.get("hall_label") or ""))
    return out


def test_every_real_hall_label_has_no_all_caps_word_but_the_acronyms():
    site = _Site({}, "2026-09-28T12:00:00+04:00")
    acr = set(pulse.labels()["acronyms"])
    assert {"IMAX", "4DX", "VIP", "MAX"} <= acr
    for chain, code, raw in sorted(set(REAL_HALLS) | _fixture_halls()):
        for lang in ("ar", "en"):
            lab = pulse.hall_label(site, chain, code, raw, lang)
            bad = [w for w in ALL_CAPS.findall(lab) if w not in acr]
            assert lab and not bad, (chain, code, raw, lang, lab)
        ar = pulse.hall_label(site, chain, code, raw, "ar")
        assert re.search(r"[؀-ۿ]", ar) or all(w in acr or w == "ScreenX" for w in ar.split()), (chain, raw, ar)


@pytest.mark.parametrize("chain,code,raw,ar,en", [
    ("vox", "THEATRE", "THEATRE", "ثياتر", "Theatre"),
    ("vox", "GOLD", "GOLD", "جولد", "Gold"),
    ("vox", "KIDS", "Kids", "كيدز", "Kids"),
    ("vox", "OTHER", "Premier", "بريمير", "Premier"),
    ("vox", "OTHER", "SAMSUNG ONYX", "سامسونج أونكس", "Samsung Onyx"),
    ("vox", "IMAX", "IMAX", "IMAX", "IMAX"),
    ("vox", "4DX", "4DX", "4DX", "4DX"),
    ("reel", "KIDS", "Reel Junior Screen 6", "ريل جونيور", "Reel Junior"),
    ("reel", "SCREENX", "Screen 8", "ScreenX", "ScreenX"),
    ("star", "Standard", "NORMAL", "عادية", "Standard"),
    ("novo", "OTHER", "SKY", "سكاي", "Sky"),
    ("roxy", "OTHER", "XtrmPremiumView", "إكستريم", "Xtreme"),        # site_kit.clean_label cuts it to «Xtrm»
    ("vox", "OTHER", "BRAND NEW HALL", "Brand New Hall", "Brand New Hall"),       # an unknown label: Title Case
])
def test_hall_label(chain, code, raw, ar, en):
    site = _Site({}, "2026-09-28T12:00:00+04:00")
    assert pulse.hall_label(site, chain, code, raw, "ar") == ar
    assert pulse.hall_label(site, chain, code, raw, "en") == en


def test_title_case_keeps_acronyms_and_brands():
    acr = ("IMAX", "4DX", "VIP", "XXL")
    assert pulse.title_case("THEATRE PODS in IMAX", acr) == "Theatre Pods in IMAX"
    assert pulse.title_case("VIP seats", acr) == "VIP seats"
    assert pulse.title_case("ScreenX", acr) == "ScreenX"
    assert pulse.title_case("XXL Screen", acr) == "XXL Screen"


# ================================================================ 5. real data (skipped where there is none)

def test_pulse_is_small_on_real_data(tmp_path):
    """≤ 8 KB gzipped on the real data (data/latest.json, first_seen from data/film_history.json when present)."""
    real = ROOT / "data" / "latest.json"
    if not real.exists():
        pytest.skip("no data/latest.json (a checkout without the runner's data)")
    data = _load(real)
    hist_p = ROOT / "data" / "film_history.json"
    hist = _load(hist_p) if hist_p.exists() else {f: {"first_seen": "2026-09-27"} for f in data["films"]}
    refresh.attach_first_seen(data, hist)
    site = build.Site(data, build.load_discounts(str(ROOT / "discounts.yaml")), build.Halls(str(ROOT / "halls.yaml")),
                      str(tmp_path), modules=build.discover(only=("core", "pulse")))
    body = json.dumps(pulse.Pulse(site).pulse(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(gzip.compress(body)) <= 8 * 1024
