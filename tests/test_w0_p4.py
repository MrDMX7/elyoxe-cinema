"""W0-P4 · Data truth (legend MASTER-PLAN §4.1 #31–#36): the Fold pipeline's own fixes.

#31 runtime = the median of the chains' runtimes (not the longest); every show ends on it; a chain more than
    10 min off is listed in health.json.
#32 a not-a-film session (Roxy's «Immersive Dining - …») never becomes a film; it goes to data["event_shows"].
#33 Star «احجز» opens the exact show: /now-showing-single-show-booking/<ss_id>/<screen_id>/<movie_details_id>/<movie_id>,
    falling back to the film-level link when any of the four ids is missing.
#34 a VOX later-day show with no price borrows today's price for the same cinema x hall, dated.
#35 «يستاهل IMAX؟» is off the released list and no run writes it.
#36 the verdict prompt carries the site's title and runtime; text_mismatches() finds verdicts that contradict the
    site; the hourly run rewrites only those, at most 10 a run, once per fid per title-and-runtime basis.

No network: the model client and every chain reader are fakes.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import alerts  # noqa: E402
import normalize  # noqa: E402
import price_history  # noqa: E402
import price_table  # noqa: E402
import refresh  # noqa: E402
import verdicts  # noqa: E402
from readers import star  # noqa: E402

FIX = ROOT / "fixtures"
CHAINS = ("vox", "star", "novo", "reel", "roxy", "cineroyal", "cinemacity")
STAR_SHOW = re.compile(r"^https://www\.starcinemas\.ae/now-showing-single-show-booking/(\d+)/(\d+)/(\d+)/(\d+)$")
STAR_FILM = re.compile(r"^https://www\.starcinemas\.ae/now-showing-booking/(\d+)/1/$")


def _fixture(chain):
    return json.loads((FIX / f"{chain}.json").read_text(encoding="utf-8"))


def _cinema(cid, chain, city="dubai"):
    return {"id": cid, "chain": chain, "name": cid, "name_ar": None, "city": city, "mall": cid,
            "address": "", "maps": None, "lat": None, "lng": None}


def _show(**kw):
    s = {"cinema": "vox-a", "film_title": "Heart of the Beast", "film_lang": "English", "film_rating": "PG13",
         "runtime": 100, "date": "2026-09-28", "time": "21:00", "hall": "Standard", "hall_label": "Standard",
         "prices": None, "book": "https://x"}
    s.update(kw)
    return s


NOW = "2026-09-28T12:00:00+04:00"


@pytest.fixture
def no_posters(monkeypatch):
    """A live-mode refresh mirrors posters into the repo's own data/posters.json by default; these tests stub it."""
    import types
    stub = types.ModuleType("posters")
    stub.mirror = lambda data, **kw: {"films": len(data.get("films") or {}), "with_poster": 0, "downloaded": 0, "failed": 0}
    monkeypatch.setitem(sys.modules, "posters", stub)


# ================================================================ #31 runtime = the chains' median

def _seven_chains(runtimes):
    return {chain: {"cinemas": [_cinema(f"{chain}-a", chain)],
                    "shows": [_show(cinema=f"{chain}-a", runtime=rt)]}
            for chain, rt in runtimes.items()}


HOTB = {"vox": 100, "star": 101, "cinemacity": 101, "reel": 105, "roxy": 105, "cineroyal": 105, "novo": 120}


def test_runtime_is_the_chains_median_not_the_longest():
    data = normalize.merge(_seven_chains(HOTB), None, NOW, aliases={}, event_labels={})
    film = data["films"]["heart-of-the-beast"]
    assert film["runtime"] == 105   # was 120: the longest any chain listed (Novo)
    for s in data["shows"]:   # every chain's show ends on the median + the 15 min of adverts
        assert s["ends"] == "23:00", (s["cinema"], s["ends"])


def test_a_chain_more_than_10_min_off_is_reported():
    data = normalize.merge(_seven_chains(HOTB), None, NOW, aliases={}, event_labels={})
    gaps = data["runtime_gaps"]
    assert [g["fid"] for g in gaps] == ["heart-of-the-beast"]
    assert gaps[0]["runtime"] == 105 and gaps[0]["chains"]["novo"] == 120
    agree = normalize.merge(_seven_chains({"vox": 100, "star": 101, "reel": 105}), None, NOW, aliases={}, event_labels={})
    assert "runtime_gaps" not in agree


def test_a_chain_counts_once_by_the_runtime_it_lists_most():
    assert normalize.chain_runtimes({"vox": [100, 100, 100, 150], "star": [101]}) == {"vox": 100, "star": 101}
    assert normalize.chain_runtimes({"roxy": [180, 180, 175, 175]}) == {"roxy": 175}   # a tie takes the shorter
    assert normalize.chain_runtimes({"x": [None, 0]}) == {}
    # an even count takes the midpoint, halves up
    assert normalize.median_runtime([90, 120]) == 105
    assert normalize.median_runtime([185, 185, 185, 186, 190, 190]) == 186
    assert normalize.median_runtime([]) is None


def test_real_fixtures_heart_of_the_beast_sits_on_the_chains_median():
    """The acceptance: «قلب الوحش» within 5 min of the chains' median, computed here independently of merge()."""
    per_chain = {}
    for chain in CHAINS:
        rts = [s["runtime"] for s in _fixture(chain)["shows"]
               if normalize.film_fid(s["film_title"]) == "heart-of-the-beast" and s.get("runtime")]
        if rts:
            per_chain[chain] = max(set(rts), key=rts.count)
    vals = sorted(per_chain.values())
    assert len(vals) == 7
    median = vals[len(vals) // 2]
    data = normalize.merge({c: _fixture(c) for c in CHAINS}, None, "2026-09-25T00:00:00")
    assert abs(data["films"]["heart-of-the-beast"]["runtime"] - median) <= 5


def test_real_fixtures_every_film_more_than_10_off_is_listed():
    """The health report lists every film with a chain > 10 min from the median -- and only those."""
    data = normalize.merge({c: _fixture(c) for c in CHAINS}, None, "2026-09-25T00:00:00")
    mapping = data.get("merged") or {}
    per: dict = {}
    for chain in CHAINS:
        for s in _fixture(chain)["shows"]:
            fid = normalize.film_fid(s["film_title"])
            fid = mapping.get(fid, fid)
            if s.get("runtime") and fid in data["films"]:
                per.setdefault(fid, {}).setdefault(chain, []).append(s["runtime"])
    expected = set()
    for fid, chains in per.items():
        one = {c: max(set(v), key=lambda x: (v.count(x), -x)) for c, v in chains.items()}
        med = normalize.median_runtime(one.values())
        if any(abs(v - med) > 10 for v in one.values()):
            expected.add(fid)
    got = {g["fid"] for g in data.get("runtime_gaps") or []}
    assert "heart-of-the-beast" in got
    assert got == expected


def test_a_carried_show_keeps_its_own_end():
    prev = normalize.merge(_seven_chains({"vox": 100, "star": 101}), None, NOW, aliases={}, event_labels={})
    carried = next(s for s in prev["shows"] if s["cinema"] == "star-a")
    carried["ends"] = "22:59"   # what the previous run computed
    data = normalize.merge({"vox": _seven_chains({"vox": 110})["vox"], "star": None}, prev, NOW,
                           aliases={}, event_labels={})
    by = {s["cinema"]: s for s in data["shows"]}
    assert by["star-a"]["ends"] == "22:59"
    assert by["vox-a"]["ends"] == "23:05"   # read fresh: 21:00 + 15 + 110


# ================================================================ #32 not-a-film events

LABELS = normalize.load_event_labels()


def test_immersive_dining_is_an_event_not_a_film():
    assert normalize.event_label("Immersive Dining - IV Elements of Hoshena", LABELS) == "immersive dining"
    assert normalize.event_label("Exhuma (K-Fest)", LABELS) is None   # a festival screening is still a film
    assert normalize.event_label("Spider-Man: Brand New Day", LABELS) is None
    assert normalize.event_label("Mission - Impossible", LABELS) is None


def test_roxy_fixture_has_no_dining_film_and_keeps_the_sessions():
    roxy = _fixture("roxy")
    dining = [s for s in roxy["shows"] if s["film_title"].startswith("Immersive Dining")]
    assert dining, "the Roxy fixture carries the dining sessions this test is about"
    data = normalize.merge({"roxy": roxy}, None, "2026-09-25T00:00:00")
    assert not [fid for fid in data["films"] if "dining" in fid]
    assert not [s for s in data["shows"] if "dining" in s["film"]]
    ev = data["event_shows"]
    assert len(ev) == len(dining)
    assert {e["event"] for e in ev} == {"immersive dining"}
    assert all(e["book"].startswith("https://") and e["cinema"].startswith("roxy-") for e in ev)
    assert "exhuma" in data["films"]   # a K-Fest screening stays a film


def test_a_previous_run_dining_film_is_not_carried_over():
    prev = normalize.merge({"roxy": _fixture("roxy")}, None, "2026-09-25T00:00:00", event_labels={})
    assert "immersive-dining-iv-elements-of-hoshena" in prev["films"]   # the old behaviour, as on the Fold today
    data = normalize.merge({"roxy": None}, prev, "2026-09-25T00:00:00")
    assert "immersive-dining-iv-elements-of-hoshena" not in data["films"]
    assert not [s for s in data["shows"] if s["film"] == "immersive-dining-iv-elements-of-hoshena"]


def test_history_never_archives_an_event_into_a_film_page():
    history = {"immersive-dining-iv-elements-of-hoshena": {
        "first_seen": "2026-09-20", "last_seen": "2026-09-20", "absent_since": "2026-09-20T12:00:00+04:00",
        "archived": False, "chains": ["roxy"], "members": [], "redirect_from": [],
        "snapshot": {"title": "Immersive Dining - IV Elements of Hoshena", "runtime": 120}}}
    merged = {"films": {}, "shows": [], "chains": {"roxy": {"ok": True}}}
    new_history, new_films = refresh.update_film_history(merged, history, NOW, fresh_chains={"roxy"})
    assert "immersive-dining-iv-elements-of-hoshena" not in new_history
    assert "immersive-dining-iv-elements-of-hoshena" not in merged["films"]
    assert new_films == []


# ================================================================ #33 Star show-level link

def test_star_show_level_link_from_the_four_ids():
    rec = {"ss_id": 1032022, "screen_id": 79, "movie_details_id": 5182}
    assert star._book_url(2389, rec) == \
        "https://www.starcinemas.ae/now-showing-single-show-booking/1032022/79/5182/2389"
    assert star._book_url(2389, {"ss_id": "1032022", "screen_id": "79", "movie_details_id": "5182"}) == \
        "https://www.starcinemas.ae/now-showing-single-show-booking/1032022/79/5182/2389"


@pytest.mark.parametrize("change", [
    {"ss_id": None}, {"screen_id": None}, {"movie_details_id": None}, {"screen_id": 0},
    {"ss_id": "abc"}, {"movie_details_id": True}, {"screen_id": -4},
])
def test_star_link_falls_back_to_the_film_when_an_id_is_missing(change):
    rec = {"ss_id": 1032022, "screen_id": 79, "movie_details_id": 5182, **change}
    assert star._book_url(2389, rec) == "https://www.starcinemas.ae/now-showing-booking/2389/1/"


def test_star_link_falls_back_without_a_movie_id():
    assert not STAR_SHOW.match(star._book_url(0, {"ss_id": 1, "screen_id": 2, "movie_details_id": 3}))
    assert STAR_FILM.match(star._book_url(2389, None))


def test_every_star_show_in_the_fixture_opens_its_own_show():
    shows = _fixture("star")["shows"]
    assert len(shows) > 100
    bad = [s["book"] for s in shows if not STAR_SHOW.match(s["book"])]
    assert bad == []
    sessions = [STAR_SHOW.match(s["book"]).group(1) for s in shows]
    assert len(set(sessions)) == len(sessions), "one session id per show"


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._p, self.text = status, payload or {}, ""

    def json(self):
        return self._p


def test_star_fetch_links_each_show_and_falls_back_on_a_changed_payload(monkeypatch):
    """A record carrying the four ids gets its seat page; one missing a field keeps the film link."""
    import datetime as dt
    day = dt.datetime.now(star.DUBAI).replace(hour=20, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
    ms = int(day.timestamp() * 1000)
    cinemas = {"Records": [{"cinema_id": 6, "cinema_name": "Bawadi Mall - Al Ain", "cinema_address": "Al Ain",
                            "cinema_location": "Al Ain", "cinema_latitude": "24.1", "cinema_longitude": "55.7"}]}
    movies = {"Records": {"data": [{"movie_id": 2389, "rating": "PG13"}]}}
    base = {"cinema_id": 6, "movie_title": "Heart of the Beast", "lang_name": "English", "mrrdr_runtime": 101,
            "screen_type_name": "SUITES", "movie_id": 2389, "ss_actual_start_date_time": ms}
    recs = [dict(base, ss_id=1032022, screen_id=79, movie_details_id=5182),
            dict(base, ss_id=1032023, movie_details_id=5182, ss_actual_start_date_time=ms + 3 * 3600 * 1000)]

    def fake_get(self, url, **kw):
        if url.endswith("/cinemas"):
            return _Resp(200, cinemas)
        if url.endswith("/now-showing-movies"):
            return _Resp(200, movies)
        if "/movie-shows/" in url:
            return _Resp(200, {"Records": {"data": recs}})
        return _Resp(404)

    monkeypatch.setattr(star.Polite, "get", fake_get)
    out = star.fetch(days=3)
    books = sorted(s["book"] for s in out["shows"])
    assert books == ["https://www.starcinemas.ae/now-showing-booking/2389/1/",
                     "https://www.starcinemas.ae/now-showing-single-show-booking/1032022/79/5182/2389"]


# ================================================================ #34 VOX later days borrow today's price

TODAY, TOMORROW = "2026-09-28", "2026-09-29"
LIVE = [{"seat": "Regular", "aed": 50.0}, {"seat": "Premium", "aed": 60.0}]


def _vox_raw(*shows, chain="vox"):
    return {"cinemas": [_cinema("vox-a", chain), _cinema("vox-b", chain)], "shows": [dict(s) for s in shows]}


def test_vox_tomorrow_borrows_todays_same_hall_price_dated():
    raw = _vox_raw(_show(date=TODAY, prices=LIVE), _show(date=TOMORROW, time="19:00"))
    assert price_table.carry_today(raw, TODAY) == 1
    t = raw["shows"][1]
    assert sorted(p["aed"] for p in t["prices"]) == [50.0, 60.0]
    assert t["price_source"] == "table" and t["price_checked"] == TODAY and t["price_basis"] == "today"
    # dated on every page («السعر بتاريخ …»), never a live price, never in the price history
    from site_kit import Kit
    assert Kit.table_date(t) == TODAY
    assert price_history.show_price(t) is None


def test_carry_never_crosses_a_hall_a_cinema_3d_or_a_chain():
    raw = _vox_raw(_show(date=TODAY, prices=LIVE),
                   _show(date=TOMORROW, hall_label="IMAX", hall="IMAX"),
                   _show(date=TOMORROW, cinema="vox-b"),
                   _show(date=TOMORROW, film_title="Heart of the Beast 3D"))
    assert price_table.carry_today(raw, TODAY) == 0
    assert all(s["prices"] is None for s in raw["shows"][1:])
    other = _vox_raw(_show(date=TODAY, prices=LIVE), _show(date=TOMORROW), chain="reel")
    assert price_table.carry_today(other, TODAY) == 0


def test_carry_leaves_a_live_price_alone_and_never_spreads_a_table_price():
    own = [{"seat": "Regular", "aed": 55.0}]
    raw = _vox_raw(_show(date=TODAY, prices=LIVE), _show(date=TOMORROW, prices=own))
    assert price_table.carry_today(raw, TODAY) == 0
    assert raw["shows"][1]["prices"] == own and "price_source" not in raw["shows"][1]
    tabled = _vox_raw(_show(date=TODAY, prices=LIVE, price_source="table", price_checked="2026-09-25"),
                      _show(date=TOMORROW))
    assert price_table.carry_today(tabled, TODAY) == 0


def test_refresh_carries_vox_tomorrow_and_says_so_in_health(tmp_path, monkeypatch, offline_steps, no_posters):
    d = tmp_path / "data"
    for name, rel in [("DATA_DIR", ""), ("RAW_DIR", "raw"), ("LATEST_PATH", "latest.json"),
                      ("HEALTH_PATH", "health.json"), ("FILMS_CACHE_PATH", "films_cache.json"),
                      ("FILM_HISTORY_PATH", "film_history.json"), ("FILM_HISTORY_BACKUP_PATH", "film_history.prev.json"),
                      ("PRICE_CACHE_PATH", "price_cache.json"), ("PRICE_CACHE_BACKUP_PATH", "price_cache.prev.json"),
                      ("NEW_FILMS_PATH", "new_films.json")]:
        monkeypatch.setattr(refresh, name, d / rel if rel else d)
    monkeypatch.setattr(refresh.enrich_mod, "enrich", lambda data, cache_path=None, offline=False: data)
    monkeypatch.setattr(refresh, "now_iso", lambda: NOW)
    raw = _vox_raw(_show(date=TODAY, time="20:00", prices=LIVE), _show(date=TOMORROW, time="19:00"))
    monkeypatch.setattr(refresh, "CHAIN_READERS", {"vox": lambda days=2, **kw: json.loads(json.dumps(raw))})
    assert refresh.refresh(chains=["vox"], no_verdicts=True) == 0
    latest = json.loads((d / "latest.json").read_text(encoding="utf-8"))
    tomorrow = next(s for s in latest["shows"] if s["date"] == TOMORROW)
    assert tomorrow["price_basis"] == "today" and tomorrow["price_checked"] == TODAY
    health = json.loads((d / "health.json").read_text(encoding="utf-8"))
    assert health["vox"]["carried_today"] == 1
    assert health["runtime"] == {"ok": True, "error": None, "gaps": []}


# ================================================================ #35 «يستاهل IMAX؟» is not released

def test_imax_line_is_off_the_released_list():
    road = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    released = road.split("## Phase 2 — RELEASED", 1)[1].split("\n## ", 1)[0]
    listed = released.split("\n")[1]
    assert "IMAX" not in listed
    assert "Not released" in released and "«يستاهل IMAX؟»" in released


def test_no_run_writes_the_imax_line():
    runners = [ROOT / "refresh.py", ROOT / "build.py", ROOT / "run.sh", ROOT / "deploy.sh", ROOT / "seed_verdicts.py",
               *sorted((ROOT / "steps").glob("*.py")), *sorted((ROOT / "pages").glob("*.py"))]
    callers = [p.name for p in runners if p.exists() and "write_imax(" in p.read_text(encoding="utf-8")]
    assert callers == []


# ================================================================ #36 verdict text against the site

RE_FILM = {"title": "Resident Evil", "title_ar": "ريزدنت ايفل", "runtime": 97, "genres": ["horror", "action"],
           "lang": "English", "rt": {"critics": 96, "critics_count": 249, "audience": 91}}
AV_FILM = {"title": "Avengers Endgame: Encore", "title_ar": None, "runtime": 190, "genres": ["action"],
           "rt": {"critics": 94, "critics_count": 500}}


def test_prompt_carries_the_sites_title_and_runtime():
    p = verdicts._film_prompt("resident-evil", RE_FILM, None)
    assert "«ريزدنت ايفل»" in p and "97 دقيقة" in p
    assert "رعب" in p and "أكشن" in p   # genres as the site's keys -> Arabic labels (a list used to crash here)
    assert "لغة الفيلم: English" in p
    p2 = verdicts._film_prompt("avengers-endgame-encore", AV_FILM, None)
    assert "Avengers Endgame: Encore" in p2 and "190 دقيقة" in p2


def _write_verdict(d, fid, ar, en="", by="claude", verdict="yes"):
    (d / f"{fid}.json").write_text(json.dumps({"fid": fid, "verdict": verdict, "ar": ar, "en": en, "basis": "RT",
                                               "basis_numbers": {"rt": 96, "rt_count": 249, "cinemascore": None},
                                               "written": "2026-09-26", "by": by}, ensure_ascii=False),
                                   encoding="utf-8")


@pytest.fixture
def vdir(tmp_path, monkeypatch):
    d = tmp_path / "verdicts"
    d.mkdir()
    monkeypatch.setattr(verdicts, "VERDICTS_DIR", d)
    return d


def test_text_mismatches_flags_both_audit_cases(vdir):
    _write_verdict(vdir, "resident-evil", "رزدنت إيفل حصل 96% من النقاد على روتن توميتوز.")
    _write_verdict(vdir, "avengers-endgame-encore",
                   "Avengers: Endgame Encore عرض ثاني للفيلم اللي عرفه الكل، مدته 3 ساعات ودقيقة.",
                   "Avengers: Endgame Encore brings the 2019 hit back, runtime 3h01.")
    found = verdicts.text_mismatches({"films": {"resident-evil": RE_FILM, "avengers-endgame-encore": AV_FILM}})
    assert set(found) == {"resident-evil", "avengers-endgame-encore"}
    assert "ريزدنت ايفل" in found["resident-evil"]
    assert "181" in found["avengers-endgame-encore"] and "190" in found["avengers-endgame-encore"]


@pytest.mark.parametrize("ar, en", [
    ("ريزدنت إيفل حصل 96% من النقاد.", ""),                       # the site's spelling (hamza folded)
    ("وريزدنت ايفل رعب حقيقي، مدته ساعة و37 دقيقة.", ""),          # attached «و», runtime 97
    ("96% من النقاد، ورعب حقيقي من أول دقيقة.", "96% with critics."),  # no title, no runtime
    ("آخر 20 دقيقة أقوى شي فيه، و72 ساعة ما تكفي تنساه.", ""),     # minutes and hours that are not a runtime
    ("ريزدنت ايفل يمشي 100 دقيقة بلا ملل.", "Resident Evil runs 100 minutes."),   # within 5 of 97
])
def test_text_mismatches_flags_nothing_on_a_matching_verdict(vdir, ar, en):
    _write_verdict(vdir, "resident-evil", ar, en)
    assert verdicts.text_mismatches({"films": {"resident-evil": RE_FILM}}) == {}


def test_template_and_archived_verdicts_are_not_checked(vdir):
    _write_verdict(vdir, "resident-evil", "رزدنت إيفل", by="template")
    _write_verdict(vdir, "old-one", "رزدنت إيفل")
    films = {"resident-evil": RE_FILM, "old-one": dict(RE_FILM, status="archived")}
    assert verdicts.text_mismatches({"films": films}) == {}


def test_the_latin_title_where_the_page_shows_an_arabic_one_is_a_mismatch(vdir):
    _write_verdict(vdir, "dark-nun", "Dark Nun تقييم النقاد 53% بس.")
    film = {"title": "Dark Nun", "title_ar": "راهبات الظلام", "runtime": 120}
    assert "Latin" in verdicts.text_mismatches({"films": {"dark-nun": film}})["dark-nun"]


@pytest.mark.parametrize("text, minutes", [
    ("مدته 3 ساعات ودقيقة", [181]), ("مدته ساعتين و41 دقيقة", [161]), ("ساعة ونص من الأكشن", [90]),
    ("مدته ساعتين إلا ربع", [105]), ("181 دقيقة", [181]), ("runtime 3h01.", [181]),
    ("2 hours 30 minutes", [150]), ("a 181-minute epic", [181]),
    ("72 ساعة قبل D-Day", []), ("آخر 20 دقيقة", []), ("أول ساعة بطيئة", []), ("كل ساعة", []),
])
def test_stated_runtimes(text, minutes):
    assert verdicts.stated_runtimes(text) == minutes


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:
    def __init__(self, text):
        self.content = [_Block(text)]


class FakeClient:
    """Counts model calls; answers with `ar_for(fid-less prompt)`."""

    def __init__(self, ar_for):
        self.calls = 0
        self.ar_for = ar_for
        self.messages = self

    def create(self, model, max_tokens, system, messages):
        self.calls += 1
        prompt = messages[0]["content"]
        return _Msg(json.dumps({"verdict": "yes", "ar": self.ar_for(prompt), "en": "Critics like it.",
                                "basis": "RT 96%"}, ensure_ascii=False))


def _site_title(prompt):
    m = re.search(r"اسم الفيلم على موقعنا بالعربي: «([^»]+)»", prompt)
    return m.group(1) if m else "هذا العرض"


def _mismatched_films(vdir, n):
    films = {}
    for i in range(n):
        fid = f"film-{i:02d}"
        films[fid] = dict(RE_FILM, title=f"Film {i}", title_ar=f"ريزدنت ايفل {i}")
        _write_verdict(vdir, fid, f"رزدنت إيفل {i} حصل 96% من النقاد.")
    return films


def test_the_hourly_fix_is_capped_at_10_model_calls(vdir, monkeypatch):
    client = FakeClient(lambda p: f"{_site_title(p)} حصل 96% من النقاد، ورعب حقيقي.")
    monkeypatch.setattr(verdicts, "_client", lambda: client)
    data = {"films": _mismatched_films(vdir, 12)}
    state, report = verdicts.fix_text_mismatches(data, {}, today=TODAY)
    assert client.calls == 10
    assert len(report["rewritten"]) == 10 and len(report["deferred"]) == 2 and report["unfixed"] == []
    assert report["ok"] is True and state == {}
    # the next hour takes the two that waited, and nothing else
    state, report = verdicts.fix_text_mismatches(data, state, today=TODAY)
    assert client.calls == 12 and len(report["rewritten"]) == 2
    assert verdicts.text_mismatches(data) == {}
    new = json.loads((vdir / "film-00.json").read_text(encoding="utf-8"))
    assert new["ar"].startswith("ريزدنت ايفل 0") and new["by"] == "claude"


def test_a_fid_is_tried_once_per_basis_and_then_waits_in_the_report(vdir, monkeypatch):
    client = FakeClient(lambda p: "رزدنت إيفل حصل 96% من النقاد.")   # the model keeps the wrong spelling
    monkeypatch.setattr(verdicts, "_client", lambda: client)
    data = {"films": {"resident-evil": RE_FILM}}
    _write_verdict(vdir, "resident-evil", "رزدنت إيفل حصل 96% من النقاد.")
    state, report = verdicts.fix_text_mismatches(data, {}, today=TODAY)
    assert client.calls == verdicts.MAX_ATTEMPTS   # the post-check rejected every draft: one fid, one bounded try
    assert report["unfixed"] == ["resident-evil"] and report["ok"] is False and report["error"]
    assert state["resident-evil"]["basis"] == "ريزدنت ايفل|97"
    # same title and runtime next hour: no model call, still reported
    state, report = verdicts.fix_text_mismatches(data, state, today=TODAY)
    assert client.calls == verdicts.MAX_ATTEMPTS and report["unfixed"] == ["resident-evil"]
    # a new basis (W1-D2's Arabic titles, a runtime the chains changed) earns one more try
    data2 = {"films": {"resident-evil": dict(RE_FILM, runtime=90)}}
    verdicts.fix_text_mismatches(data2, state, today=TODAY)
    assert client.calls == 2 * verdicts.MAX_ATTEMPTS


def test_a_hand_edited_verdict_is_never_rewritten(vdir, monkeypatch):
    client = FakeClient(lambda p: "x")
    monkeypatch.setattr(verdicts, "_client", lambda: client)
    _write_verdict(vdir, "resident-evil", "رزدنت إيفل حصل 96% من النقاد.", by="owner")
    state, report = verdicts.fix_text_mismatches({"films": {"resident-evil": RE_FILM}}, {}, today=TODAY)
    assert client.calls == 0 and report["hand"] == ["resident-evil"] and state == {}


# --- review finding 1: the real resident-evil has no basis in the data (no RT, no CinemaScore), and a
# forced rewrite used to replace its researched 96 % «yes» with the "not enough ratings" template.
RE_NO_BASIS = {k: v for k, v in RE_FILM.items() if k != "rt"}
RE_ON_FILE = {"ar": "رزدنت إيفل حصل 96% من النقاد على روتن توميتوز، ووايد ناس يقولون أحسن فيلم مقتبس من لعبة.",
              "basis": "RT 96% (249 ناقد) · الجمهور 91%", "by": "claude",
              "en": "Resident Evil scored 96% with critics on Rotten Tomatoes.", "fid": "resident-evil",
              "verdict": "yes", "written": "2026-09-26"}   # the real file: no basis_numbers line


def _put(d, fid, v):
    path = d / f"{fid}.json"
    path.write_text(json.dumps(v, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


class _VerdictClient(FakeClient):
    """Like FakeClient, but answers with a chosen verdict and keeps every prompt."""

    def __init__(self, ar_for, verdict="yes"):
        super().__init__(ar_for)
        self.verdict, self.prompts = verdict, []

    def create(self, model, max_tokens, system, messages):
        self.calls += 1
        self.prompts.append(messages[0]["content"])
        return _Msg(json.dumps({"verdict": self.verdict, "ar": self.ar_for(messages[0]["content"]),
                                "en": "Critics love it.", "basis": "RT 96% (249 ناقد)"}, ensure_ascii=False))


def test_a_text_fix_of_a_film_with_no_basis_rewrites_from_its_own_verdict(vdir, monkeypatch):
    assert not verdicts.has_basis(RE_NO_BASIS)
    _put(vdir, "resident-evil", RE_ON_FILE)
    client = _VerdictClient(lambda p: f"{_site_title(p)} حصل 96% من النقاد، ورعب حقيقي بأجواء اللعبة.")
    monkeypatch.setattr(verdicts, "_client", lambda: client)
    state, report = verdicts.fix_text_mismatches({"films": {"resident-evil": RE_NO_BASIS}}, {}, today=TODAY)
    assert client.calls == 1
    assert report["rewritten"] == ["resident-evil"] and report["no_basis"] == ["resident-evil"] and report["ok"]
    new = json.loads((vdir / "resident-evil.json").read_text(encoding="utf-8"))
    assert new["by"] == "claude" and new["verdict"] == "yes"            # never the template
    assert new["ar"].startswith("ريزدنت ايفل حصل 96%") and new["ar"] != verdicts.TEMPLATE_AR
    assert new["basis_numbers"] == {"rt": 96, "rt_count": 249, "cinemascore": None}   # what it stood on
    # the model saw the verdict on file as its notes, and the site's own spelling
    assert "النص الحالي بالعربي: رزدنت إيفل حصل 96%" in client.prompts[0] and "«ريزدنت ايفل»" in client.prompts[0]
    assert verdicts.text_mismatches({"films": {"resident-evil": RE_NO_BASIS}}) == {}


def test_a_no_basis_film_whose_rewrite_fails_keeps_its_file_byte_for_byte(vdir, monkeypatch):
    path = _put(vdir, "resident-evil", RE_ON_FILE)
    before = path.read_bytes()
    client = _VerdictClient(lambda p: "رزدنت إيفل حصل 96% من النقاد.")   # the model keeps the wrong spelling
    monkeypatch.setattr(verdicts, "_client", lambda: client)
    state, report = verdicts.fix_text_mismatches({"films": {"resident-evil": RE_NO_BASIS}}, {}, today=TODAY)
    assert client.calls == verdicts.MAX_ATTEMPTS and report["unfixed"] == ["resident-evil"]
    assert path.read_bytes() == before


def test_a_forced_run_with_nothing_to_write_from_never_templates_a_researched_verdict(vdir, monkeypatch):
    """write_missing itself (seed_verdicts --fix goes through it too): no RT, no CinemaScore, no notes."""
    path = _put(vdir, "resident-evil", RE_ON_FILE)
    before = path.read_bytes()
    client = _VerdictClient(lambda p: "x")
    monkeypatch.setattr(verdicts, "_client", lambda: client)
    assert verdicts.write_missing({"films": {"resident-evil": RE_NO_BASIS}}, force=True,
                                  only_fids={"resident-evil"}) == {}
    assert client.calls == 0 and path.read_bytes() == before
    # a claude «unknown» with nothing behind it still becomes the template, as on the regular path
    _put(vdir, "u", dict(RE_ON_FILE, fid="u", verdict="unknown", ar="ما عندنا شي عنه."))
    assert verdicts.write_missing({"films": {"u": {"title": "U"}}}, force=True)["u"]["by"] == "template"


@pytest.mark.parametrize("film", [RE_FILM, RE_NO_BASIS])
def test_a_text_fix_never_changes_the_verdict_itself(vdir, monkeypatch, film):
    path = _put(vdir, "resident-evil", RE_ON_FILE)
    before = path.read_bytes()
    client = _VerdictClient(lambda p: f"{_site_title(p)} رعب عادي ومب لازم تستعجل عليه.", verdict="skip")
    monkeypatch.setattr(verdicts, "_client", lambda: client)
    state, report = verdicts.fix_text_mismatches({"films": {"resident-evil": film}}, {}, today=TODAY)
    assert client.calls == 1 and path.read_bytes() == before
    assert report["unfixed"] == ["resident-evil"] and "'yes' into 'skip'" in report["error"]
    assert state["resident-evil"]["ok"] is False   # waits for a new basis, never loops


# --- review finding 2: true sentences the runtime check used to flag
@pytest.mark.parametrize("text, runtime", [
    ("الفيلم أطول من ساعتين بس ما تحس فيها.", 186),   # a bound («طول» inside «أطول» was read as a runtime cue)
    ("آخر ساعة ونص من الفيلم أقوى شي.", 105),         # a stretch of the film
    ("أول 90 دقيقة بطيئة.", 150),
    ("the first 90 minutes drag", 150),
    ("over 2 hours of action", 186),
    ("قرابة 3 ساعات، بس تستاهل.", 186),               # a rounded figure
    ("3 ساعات تقريباً", 186),
    ("about 3 hours", 186),
    ("ما يوصل ساعتين", 105),
])
def test_true_runtime_sentences_are_not_flagged(text, runtime):
    assert verdicts.text_mismatch({"ar": text}, {"runtime": runtime}) is None


@pytest.mark.parametrize("text, runtime, why", [
    ("الفيلم أطول من ساعتين", 105, "over 120"),
    ("over 2 hours of action", 100, "over 120"),
    ("قرابة 3 ساعات", 150, "about 180"),
    ("ما يوصل ساعتين", 140, "under 120"),
    ("مدته 3 ساعات ودقيقة", 190, "181"),
])
def test_a_broken_bound_or_a_far_rounded_figure_is_still_flagged(text, runtime, why):
    assert why in verdicts.text_mismatch({"ar": text}, {"runtime": runtime})


def test_the_construct_state_of_a_title_with_al_is_its_own_spelling():
    film = {"title": "The Odyssey", "title_ar": "الأوديسة", "runtime": 180}
    for ok in ("أوديسة نولان تحفة.", "الأوديسة تحفة.", "للأوديسة جمهورها."):
        assert verdicts.text_mismatch({"ar": ok}, film) is None
    assert "Latin" in verdicts.text_mismatch({"ar": "The Odyssey تحفة."}, film)
    assert verdicts.text_mismatch({"ar": "رزدنت إيفل"}, RE_FILM)   # the audit case still flags


def test_refresh_rewrites_only_the_mismatch_and_reports_it(tmp_path, monkeypatch, offline_steps, no_posters):
    """The hourly wiring: every other verdict is left alone, the mismatch goes through the model once, and
    health.json says what happened. Two runs: the second makes no call."""
    d = tmp_path / "data"
    for name, rel in [("DATA_DIR", ""), ("RAW_DIR", "raw"), ("LATEST_PATH", "latest.json"),
                      ("HEALTH_PATH", "health.json"), ("FILMS_CACHE_PATH", "films_cache.json"),
                      ("FILM_HISTORY_PATH", "film_history.json"), ("FILM_HISTORY_BACKUP_PATH", "film_history.prev.json"),
                      ("PRICE_CACHE_PATH", "price_cache.json"), ("PRICE_CACHE_BACKUP_PATH", "price_cache.prev.json"),
                      ("NEW_FILMS_PATH", "new_films.json")]:
        monkeypatch.setattr(refresh, name, d / rel if rel else d)
    vdir = tmp_path / "verdicts"
    vdir.mkdir()
    monkeypatch.setattr(verdicts, "VERDICTS_DIR", vdir)
    monkeypatch.setattr(refresh, "now_iso", lambda: NOW)

    def enrich(data, cache_path=None, offline=False):
        for fid, f in data["films"].items():
            f["title_ar"] = "قلب الوحش" if fid == "heart-of-the-beast" else None
            f["rt"] = {"critics": 88, "critics_count": 125}
        return data
    monkeypatch.setattr(refresh.enrich_mod, "enrich", enrich)
    raw = {"cinemas": [_cinema("vox-a", "vox")],
           "shows": [_show(date=TODAY, time="20:00", prices=LIVE),
                     _show(date=TODAY, time="21:00", film_title="Toy Story 5", runtime=105, prices=LIVE)]}
    monkeypatch.setattr(refresh, "CHAIN_READERS", {"vox": lambda days=2, **kw: json.loads(json.dumps(raw))})
    for fid, ar in (("heart-of-the-beast", "قلب الوحوش ياب 88% من النقاد."), ("toy-story-5", "93% من النقاد.")):
        (vdir / f"{fid}.json").write_text(json.dumps(
            {"fid": fid, "verdict": "yes", "ar": ar, "en": "Good.", "basis": "RT 88%", "by": "claude",
             "basis_numbers": {"rt": 88, "rt_count": 125, "cinemascore": None}, "written": "2026-09-26"},
            ensure_ascii=False), encoding="utf-8")
    client = FakeClient(lambda p: f"{_site_title(p)} ياب 88% من النقاد، ويستاهل المشوار.")
    monkeypatch.setattr(verdicts, "_client", lambda: client)

    assert refresh.refresh(chains=["vox"], no_verdicts=False) == 0
    assert client.calls == 1
    health = json.loads((d / "health.json").read_text(encoding="utf-8"))
    assert health["verdict_text"]["rewritten"] == ["heart-of-the-beast"]
    assert health["verdict_text"]["ok"] is True
    fixed = json.loads((vdir / "heart-of-the-beast.json").read_text(encoding="utf-8"))
    assert fixed["ar"].startswith("قلب الوحش ياب")
    assert json.loads((vdir / "toy-story-5.json").read_text(encoding="utf-8"))["ar"] == "93% من النقاد."
    # the secondary alert stays quiet for a report with nothing unfixed
    _, line = alerts.health_line({}, health, NOW)
    assert "verdict_text" not in line and "runtime" not in line

    assert refresh.refresh(chains=["vox"], no_verdicts=False) == 0
    assert client.calls == 1


def test_refresh_offline_never_calls_the_fix(tmp_path, monkeypatch, offline_steps):
    called = []
    monkeypatch.setattr(verdicts, "fix_text_mismatches", lambda *a, **k: called.append(1) or ({}, {}))
    d = tmp_path / "data"
    for name, rel in [("DATA_DIR", ""), ("RAW_DIR", "raw"), ("LATEST_PATH", "latest.json"),
                      ("HEALTH_PATH", "health.json"), ("FILMS_CACHE_PATH", "films_cache.json"),
                      ("FILM_HISTORY_PATH", "film_history.json"), ("FILM_HISTORY_BACKUP_PATH", "film_history.prev.json"),
                      ("PRICE_CACHE_PATH", "price_cache.json"), ("PRICE_CACHE_BACKUP_PATH", "price_cache.prev.json"),
                      ("NEW_FILMS_PATH", "new_films.json")]:
        monkeypatch.setattr(refresh, name, d / rel if rel else d)
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    assert refresh.refresh(chains=["roxy"], offline=True) == 0
    assert called == []
    latest = json.loads((d / "latest.json").read_text(encoding="utf-8"))
    assert not [fid for fid in latest["films"] if "dining" in fid]
    assert latest["event_shows"] and all(e["event"] == "immersive dining" for e in latest["event_shows"])
    slices = [json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.json")
              if p.stem in {"dubai", "abu-dhabi", "sharjah", "ajman", "al-ain"}]
    assert slices and all("event_shows" not in s for s in slices)   # the city slices stay the same shape
