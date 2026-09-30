"""round3-gaps (2026-09-30): the «agreed but not visibly live» batch — never a real network call.

  omdb.py            the title + year fallback: the match rule, the cache (hits AND misses, per film id), the budget
  kit/tile.py        release_week(): one rule for the tile's «جديد»/«الأسبوع N», the hero's line and «عن الفيلم»
  pages/intel.py     «ليش يستاهل؟» under the verdict (intel reasons, else built from the numbers), «بدون حرق»
  pages/_core/home   «نجوم الليلة»: 6–8 faces from the most-shown and top-rated films
  steps/og.py        Stories cards: films with no card first, a stale card kept until its re-render lands
  cinema_photos.py   the size floor, a lying Content-Type, no upscaling
  pages/fav.py       «سينمتي»: the chunk on every page, the bookmark bindable
"""
import datetime as dt
import io
import json
import os
import re
import sys

import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cinema_photos as cph  # noqa: E402
import omdb  # noqa: E402
import steps.og as og_step  # noqa: E402
import verdicts  # noqa: E402
from kit.tile import TileKit  # noqa: E402
from pages import fav as fav_page  # noqa: E402
from pages import intel as intel_page  # noqa: E402
from pages._core.home import HomePages  # noqa: E402

NOW = dt.datetime.fromisoformat("2026-09-30T12:00:00+04:00")


# ============================================================================================== omdb.py
def test_title_key_folds_case_diacritics_punctuation_and_ampersand():
    assert omdb.title_key("Coyote VS Acme") == omdb.title_key("Coyote vs. Acme")
    assert omdb.title_key("Spider-Man: Brand New Day") == omdb.title_key("Spider Man Brand New Day")
    assert omdb.title_key("Amélie") == omdb.title_key("Amelie")
    assert omdb.title_key("Minions & Monsters") == omdb.title_key("Minions and Monsters")
    assert omdb.title_key("I’M Game") == omdb.title_key("I'm Game")
    assert omdb.title_key("Moana") != omdb.title_key("Moana 2")


def _found(title="Moana", year=2026, score=5.8, votes=14283, runtime=None, langs=("English",), imdb_id="tt27419466"):
    return {"title": title, "year": year, "score": score, "votes": votes, "runtime": runtime, "langs": list(langs), "imdb_id": imdb_id}


def test_accept_needs_the_same_title_and_a_year_within_one():
    assert omdb.accept("Moana", 2026, _found(year=2026))
    assert omdb.accept("Moana", 2026, _found(year=2025))
    assert omdb.accept("Moana", 2026, _found(year=2027))
    assert not omdb.accept("Moana", 2026, _found(year=2016))          # the 2016 animation is another film
    assert not omdb.accept("Moana", 2026, _found(title="Moana 2"))
    assert not omdb.accept("Moana", 2026, None)
    assert not omdb.accept("Moana", None, _found())


def test_accept_rejects_a_same_titled_film_in_another_language_or_length():
    # «Life After You» (Tagalog, in UAE cinemas) vs an American short of the same name and year
    assert not omdb.accept("Life After You", 2026, _found(title="Life After You", year=2025, langs=("English",)), lang="Tagalog")
    assert omdb.accept("Life After You", 2026, _found(title="Life After You", year=2025, langs=("Filipino", "Tagalog")), lang="Tagalog")
    assert not omdb.accept("Wake", 2026, _found(title="Wake", runtime=12), runtime=95)
    assert omdb.accept("Wake", 2026, _found(title="Wake", runtime=100), runtime=95)


def test_ref_year_prefers_its_own_year_then_the_first_dated_year_never_for_a_rerelease():
    assert omdb.ref_year({"year": 2014}) == (2014, True)
    assert omdb.ref_year({"first_seen": "2026-09-27"}) == (2026, False)
    assert omdb.ref_year({"released": "2025-12-30", "first_seen": "2026-01-02"}) == (2025, False)
    assert omdb.ref_year({"rerelease": True, "first_seen": "2026-09-27"}) == (None, False)


class FakeOMDb:
    """Stands in for omdb._fetch / omdb._fetch_title and counts the calls."""

    def __init__(self, by_title=None, by_id=None):
        self.by_title, self.by_id, self.calls = by_title or {}, by_id or {}, []

    def fetch(self, imdb_id, key):
        self.calls.append(("i", imdb_id))
        return self.by_id.get(imdb_id)

    def fetch_title(self, title, year, key):
        self.calls.append(("t", title, year))
        return self.by_title.get((title, year))


@pytest.fixture
def fake(monkeypatch):
    f = FakeOMDb()
    monkeypatch.setattr(omdb, "_key", lambda: "fake-key")
    monkeypatch.setattr(omdb, "_fetch", f.fetch)
    monkeypatch.setattr(omdb, "_fetch_title", f.fetch_title)
    return f


def test_no_id_film_gets_its_score_by_title_and_year(fake, tmp_path):
    fake.by_title[("Moana", 2026)] = _found()
    data = {"films": {"moana": {"title": "Moana", "first_seen": "2026-09-27", "lang": "English", "imdb": {"id": None}}}}
    rep = omdb.fill_scores(data, str(tmp_path))
    f = data["films"]["moana"]
    assert f["imdb_score"] == 5.8 and f["imdb"] == {"id": "tt27419466", "src": "omdb-title"}
    assert rep["by_title"] == 1 and fake.calls == [("t", "Moana", 2026)]


def test_an_inferred_year_also_asks_the_year_before(fake, tmp_path):
    fake.by_title[("Pressure", 2025)] = _found(title="Pressure", year=2025, score=7.3, votes=20671)
    data = {"films": {"p": {"title": "Pressure", "first_seen": "2026-09-27"}}}
    omdb.fill_scores(data, str(tmp_path))
    assert data["films"]["p"]["imdb_score"] == 7.3
    assert fake.calls == [("t", "Pressure", 2026), ("t", "Pressure", 2025)]


def test_a_films_own_year_is_asked_once(fake, tmp_path):
    data = {"films": {"x": {"title": "Nothing Here", "year": 2026}}}
    omdb.fill_scores(data, str(tmp_path))
    assert fake.calls == [("t", "Nothing Here", 2026)]


def test_a_miss_is_cached_per_film_and_not_asked_again(fake, tmp_path):
    data = {"films": {"x": {"title": "Nothing Here", "first_seen": "2026-09-27"}}}
    omdb.fill_scores(data, str(tmp_path))
    n = len(fake.calls)
    assert n == 2 and "imdb_score" not in data["films"]["x"]
    cache = json.loads((tmp_path / "omdb_cache.json").read_text(encoding="utf-8"))
    assert cache["t:x"]["hit"] is False and cache["t:x"]["q"] == ["Nothing Here", 2026]
    omdb.fill_scores({"films": {"x": {"title": "Nothing Here", "first_seen": "2026-09-27"}}}, str(tmp_path))
    assert len(fake.calls) == n                                      # read from the cache: no request
    # a week later the miss is asked again (OMDb may have added it)
    cache["t:x"]["at"] -= omdb.TITLE_MISS_TTL + 60
    (tmp_path / "omdb_cache.json").write_text(json.dumps(cache), encoding="utf-8")
    omdb.fill_scores({"films": {"x": {"title": "Nothing Here", "first_seen": "2026-09-27"}}}, str(tmp_path))
    assert len(fake.calls) == n + 2


def test_a_hit_is_read_from_the_cache_within_the_ttl(fake, tmp_path):
    fake.by_title[("Moana", 2026)] = _found()
    for _ in range(3):
        d = {"films": {"moana": {"title": "Moana", "first_seen": "2026-09-27"}}}
        omdb.fill_scores(d, str(tmp_path))
        assert d["films"]["moana"]["imdb_score"] == 5.8
    assert len(fake.calls) == 1


def test_an_id_with_no_score_falls_back_to_the_title(fake, tmp_path):
    fake.by_id["tt1"] = None
    fake.by_title[("Dark Nun", 2025)] = _found(title="Dark Nun", year=2025, score=6.1, votes=900, imdb_id="tt1")
    data = {"films": {"d": {"title": "Dark Nun", "year": 2025, "imdb": {"id": "tt1"}}}}
    omdb.fill_scores(data, str(tmp_path))
    assert data["films"]["d"]["imdb_score"] == 6.1
    assert data["films"]["d"]["imdb"] == {"id": "tt1"}                # a Wikidata id is never overwritten
    assert fake.calls == [("i", "tt1"), ("t", "Dark Nun", 2025)]


def test_an_id_with_a_score_never_asks_by_title(fake, tmp_path):
    fake.by_id["tt2"] = 8.7
    data = {"films": {"i": {"title": "Interstellar", "year": 2014, "imdb": {"id": "tt2"}}}}
    omdb.fill_scores(data, str(tmp_path))
    assert data["films"]["i"]["imdb_score"] == 8.7 and fake.calls == [("i", "tt2")]


def test_too_few_votes_is_a_match_without_a_number(fake, tmp_path):
    fake.by_title[("Wake", 2026)] = _found(title="Wake", score=9.2, votes=13)
    data = {"films": {"w": {"title": "Wake", "first_seen": "2026-09-30"}}}
    omdb.fill_scores(data, str(tmp_path))
    assert "imdb_score" not in data["films"]["w"]
    cache = json.loads((tmp_path / "omdb_cache.json").read_text(encoding="utf-8"))
    assert cache["t:w"]["hit"] is True and cache["t:w"]["score"] is None


def test_a_rerelease_without_its_own_year_is_never_looked_up_by_title(fake, tmp_path):
    data = {"films": {"e": {"title": "Avengers Endgame: Encore", "rerelease": True, "first_seen": "2026-09-27"}}}
    omdb.fill_scores(data, str(tmp_path))
    assert fake.calls == []


def test_the_title_requests_stop_at_the_cap(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(omdb, "TITLE_CAP", 4)
    data = {"films": {f"f{i}": {"title": f"Film {i}", "first_seen": "2026-09-27"} for i in range(10)}}
    rep = omdb.fill_scores(data, str(tmp_path))
    assert rep["title_requests"] == 4 and len(fake.calls) == 4


def test_fetch_title_reduces_omdbs_answer(monkeypatch):
    monkeypatch.setattr(omdb, "_get", lambda params, key: {
        "Response": "True", "Title": "The Odyssey", "Year": "2026", "imdbID": "tt33764258", "imdbRating": "8.4",
        "imdbVotes": "477,953", "Runtime": "172 min", "Language": "English, Greek"})
    got = omdb._fetch_title("The Odyssey", 2026, "k")
    assert got == {"title": "The Odyssey", "year": 2026, "imdb_id": "tt33764258", "score": 8.4, "votes": 477953,
                   "runtime": 172, "langs": ["English", "Greek"]}
    monkeypatch.setattr(omdb, "_get", lambda params, key: {"Response": "False", "Error": "Movie not found!"})
    assert omdb._fetch_title("Nope", 2026, "k") is None


# ============================================================================== kit/tile.py release_week
class WeekSite(TileKit):
    def __init__(self, films):
        self.films, self.now = films, NOW


def test_release_week_is_the_one_rule_for_tile_and_hero():
    site = WeekSite({"x": {"first_seen": "2026-09-30"}, "old": {"first_seen": "2026-09-27"}})
    assert site.release_week("x") == ("2026-09-30", 1)
    assert site.week_tag("x", "ar") == "جديد"
    line = site.release_line("x", "ar")
    assert "في السينما من 30 سبتمبر 2026، الأسبوع" in line and ">1<" not in line and line.endswith("الأسبوع 1")
    assert site.release_line("x", "en") == "In cinemas since 30 September 2026, week 1"
    # the tracking seed is not a release date: no line at all, never an invented one
    assert site.release_week("old") is None and site.release_line("old", "ar") == ""


def test_release_week_counts_weeks_from_released_and_never_before_it():
    site = WeekSite({"x": {"released": "2026-09-16", "first_seen": "2026-09-20"}, "y": {"released": "2026-10-01"},
                     "seed": {"first_seen": "2026-01-01"}})
    assert site.release_week("x") == ("2026-09-16", 3) and site.week_tag("x", "ar") == "الأسبوع 3"
    assert site.release_week("y") is None                         # a preview night before the release


# ================================================================================ pages/intel.py film.why
class IntelSite:
    def __init__(self, films):
        self.films = films


def test_fallback_reasons_read_every_number_the_film_has():
    film = {"rt": {"critics": 96, "critics_count": 293, "audience": 94}, "imdb_score": 7.6}
    rs = intel_page.fallback_reasons(film, "ar")
    assert [p for _, p in rs] == [True, True, True]
    assert rs[0][0] == "النقاد عطوه 96% من 293 مراجعة على Rotten Tomatoes"
    assert "94%" in rs[1][0] and "7.6 من 10" in rs[2][0]
    low = intel_page.fallback_reasons({"rt": {"critics": 35, "audience": 55}, "imdb_score": 4.3}, "ar")
    assert [p for _, p in low] == [False, None, False]
    assert intel_page.fallback_reasons({"rt": {"critics": None, "audience": None}}, "ar") == []
    assert intel_page.fallback_reasons({}, "en") == []
    # the verdict's own basis numbers count when the rt block is absent
    assert "73%" in intel_page.fallback_reasons({"verdict": {"basis_numbers": {"rt": 73, "rt_count": 12}}}, "ar")[0][0]


def test_fallback_arabic_passes_the_sites_dialect_gate():
    for film in ({"rt": {"critics": 96, "critics_count": 293, "audience": 94}, "imdb_score": 7.6},
                 {"rt": {"critics": 35, "critics_count": 20, "audience": 60}, "imdb_score": 6.0},
                 {"rt": {"critics": 50, "audience": 30}, "imdb_score": 4.0}):
        for text, _ in intel_page.fallback_reasons(film, "ar"):
            assert verdicts._dialect_violation(text) is None, text
            assert not re.search("[٠-٩]", text)
    for k in ("why_yes", "why_skip", "why_mixed", "nospoil", "gate"):
        assert verdicts._dialect_violation(intel_page.L[k][0]) is None, k


def test_why_is_one_details_line_from_the_numbers_without_intel():
    site = IntelSite({"x": {"rt": {"critics": 96, "audience": 94}, "imdb_score": 7.6, "verdict": {"verdict": "yes"}}})
    h = intel_page._why(site, "ar", "x")
    assert h.startswith('<details class="fwhy" data-why="numbers"><summary><span>ليش يستاهل؟</span></summary>')
    assert h.count("<li") == 3 and '<span class="num">7.6</span>' in h
    site.films["x"]["verdict"]["verdict"] = "skip"
    assert "ليش لا؟" in intel_page._why(site, "ar", "x")
    site.films["x"]["verdict"]["verdict"] = "mixed"
    assert "ليش يستاهل وليش لا؟" in intel_page._why(site, "ar", "x")
    assert intel_page._why(IntelSite({"n": {"verdict": {"verdict": "unknown"}}}), "ar", "n") == ""


def test_why_prefers_the_films_own_intel_reasons_on_the_arabic_page():
    site = IntelSite({"x": {"rt": {"critics": 73}, "verdict": {"verdict": "mixed"},
                            "intel": {"reasons": [{"text": "سبب من الذكاء", "pos": False}]}}})
    ar = intel_page._why(site, "ar", "x")
    assert 'data-why="intel"' in ar and "سبب من الذكاء" in ar and 'class="neg"' in ar
    en = intel_page._why(site, "en", "x")
    assert 'data-why="numbers"' in en and "سبب" not in en


def test_the_spoilers_sit_under_a_visible_no_spoilers_switch_on_by_default():
    film = {"intel": {"reasons": [], "audience": [], "fun_fact": None, "consensus_ar": None, "has_plot": True,
                      "ending": "النهاية هني.", "qa": [{"q": "سؤال؟", "a": "جواب."}]}}
    h = intel_page._film_info(IntelSite({"x": film}), "ar", "x")
    sw = h.index('<label class="i-ns"><input type="checkbox" checked data-nospoil><span>بدون حرق</span></label>')
    assert sw < h.index("اشرح النهاية") < h.index("أسئلة عن الفيلم")
    assert h.count('class="i-gate"') == 2 and h.count('class="i-body"') == 2
    assert "i-fact" not in h                                          # fun_fact null: no row at all
    css = open(os.path.join(ROOT, "src", "css", "intel.css"), encoding="utf-8").read()
    assert ".i-sp:has(.i-ns input:checked) .i-body{display:none}" in css


def test_the_intel_file_s_fun_fact_row_shows_only_with_text():
    base = {"reasons": [], "audience": [], "consensus_ar": None, "has_plot": False, "ending": None, "qa": []}
    with_fact = intel_page._film_info(IntelSite({"x": {"intel": dict(base, fun_fact={"text": "معلومة حلوة", "source": "Wikipedia"})}}), "ar", "x")
    assert 'class="i-fact"' in with_fact and "معلومة حلوة" in with_fact
    for ff in (None, {"text": ""}, {}):
        assert 'class="i-fact"' not in intel_page._film_info(IntelSite({"x": {"intel": dict(base, fun_fact=ff)}}), "ar", "x")


def test_film_why_slot_is_declared_and_registered():
    import site_kit
    assert "film.why" in site_kit.Kit.SLOTS
    assert set(intel_page.register(None).slots) == {"film.info", "film.why"}


# ============================================================================= «نجوم الليلة» (home.py)
class StarSite(HomePages):
    def __init__(self, films, people):
        self.films, self.d = films, {"people": people}

    def ftitle(self, fid, lang):
        return fid

    def rail(self, lang, key, title, tiles, **kw):
        return f'<section data-key="{key}">{tiles}</section>'


def _person(q):
    return {"name_en": f"Actor {q}", "name_ar": f"ممثل {q}",
            "photo": {"src": f"/posters/people/{q.lower()}-aaaaaaaaaa-160.webp", "src2x": f"/posters/people/{q.lower()}-aaaaaaaaaa-320.webp"}}


def _stars(n_films=12, rated=()):
    films, people = {}, {}
    for i in range(n_films):
        q = f"Q{i + 1}"
        films[f"f{i}"] = {"cast": [q], "verdict": {"verdict": "yes" if f"f{i}" in rated else "unknown"},
                          "rt": {"critics": 90 if f"f{i}" in rated else None}}
        people[q] = _person(q)
    return StarSite(films, people)


def test_stars_row_draws_six_to_eight_faces_not_two():
    site = _stars(12)
    films = [f"f{i}" for i in range(12)]
    h = site.stars_row("ar", films)
    assert h.count('class="tile star"') == site.STARS_MAX == 8
    assert all(f'href="/film/f{i}/"' in h for i in range(8)) or h.count("/film/") == 8
    assert "-320.webp" in h and "srcset" not in h                       # one file per face (the home's 150 KB)


def test_star_order_alternates_most_shown_and_top_rated():
    site = _stars(10, rated=("f9", "f8"))
    site.films["f9"]["rt"]["critics"] = 97                               # the best rated of the two
    order = site.star_order([f"f{i}" for i in range(10)])
    assert order[:4] == ["f0", "f9", "f1", "f8"]                        # busiest, best rated, next busiest, next rated
    assert len(order) == len(set(order)) == 10


def test_stars_skip_films_without_a_real_photo_and_repeat_no_actor():
    site = _stars(4)
    site.films["f1"]["cast"] = ["Q1"]                                   # the same actor as f0: skipped for f1
    site.d["people"]["Q3"]["photo"] = {"src": "https://elsewhere/x.jpg", "src2x": "https://elsewhere/y.jpg"}
    h = site.stars_row("ar", ["f0", "f1", "f2", "f3"])
    assert h.count('class="tile star"') == 2 and "/film/f0/" in h and "/film/f3/" in h
    assert _stars(0).stars_row("ar", []) == ""


# ============================================================================== steps/og.py Stories cards
def _poster(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (342, 513), (80, 40, 20)).save(path, "WEBP")


def _catalogue(cache, n, price=35):
    data = {"generated": "2026-09-27T12:00:00+04:00", "cinemas": {"c1": {"chain": "vox", "city": "dubai"}}, "films": {}, "shows": []}
    for i in range(n):
        fid = f"film-{i:02d}"
        _poster(cache / "posters" / f"{fid}-684.webp")
        data["films"][fid] = {"title": f"Film {i}", "title_ar": f"فيلم {i}", "status": "showing",
                              "poster": f"https://cinema.elyoxe.com/posters/{fid}-342.webp",
                              "poster_2x": f"https://cinema.elyoxe.com/posters/{fid}-684.webp"}
        data["shows"].append({"film": fid, "cinema": "c1", "date": "2026-09-27", "time": "19:00", "prices": [{"seat": "R", "aed": price}]})
    return data


def test_stories_reach_every_film_even_when_the_first_films_keep_changing(tmp_path, monkeypatch):
    """The live bug: the first 5 films (dict order) re-rendered every run and the cap never reached the rest."""
    monkeypatch.setattr(og_step, "STORY_CAP", 4)
    monkeypatch.setattr(og_step, "_story_card", lambda *a, **k: b"RIFF0000WEBPstub")
    monkeypatch.setattr(og_step, "_card", lambda *a, **k: b"png")
    cache = tmp_path / "data"
    n = 6
    for run in range(4):
        data = _catalogue(cache, n, price=35 + run)                      # every film's price moves every run
        og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
        have = sorted(f for f, x in data["films"].items() if x.get("og_story", {}).get("ar"))
        if run == 0: assert have == ["film-00", "film-01"]              # 4 renders = 2 films x 2 languages
        if run == 1: assert have == ["film-00", "film-01", "film-02", "film-03"]   # the new ones first
    assert len(have) == n                                                # nobody starves
    # every card named on a page is on disk (a stale one stays until its replacement lands)
    for x in data["films"].values():
        for name in x["og_story"].values():
            assert (cache / "og" / name).is_file()


def test_a_stale_story_card_is_pruned_once_its_rerender_lands(tmp_path, monkeypatch):
    monkeypatch.setattr(og_step, "_card", lambda *a, **k: b"png")
    monkeypatch.setattr(og_step, "_story_card", lambda *a, **k: b"RIFF0000WEBPstub")
    cache = tmp_path / "data"
    d1 = _catalogue(cache, 1, price=35)
    og_step.run(d1, {"data_dir": str(cache), "now": d1["generated"]})
    old = d1["films"]["film-00"]["og_story"]["ar"]
    d2 = _catalogue(cache, 1, price=50)
    og_step.run(d2, {"data_dir": str(cache), "now": d2["generated"]})
    new = d2["films"]["film-00"]["og_story"]["ar"]
    assert new != old and (cache / "og" / new).is_file() and not (cache / "og" / old).exists()


def test_last_story_never_takes_another_films_card(tmp_path):
    (tmp_path / "cats-ar-story-0123456789ab.webp").write_bytes(b"x")
    (tmp_path / "cats-2-ar-story-0123456789ab.webp").write_bytes(b"x")
    assert og_step._last_story(tmp_path, "cats", "ar") == "cats-ar-story-0123456789ab.webp"
    assert og_step._last_story(tmp_path, "cats", "en") is None
    assert og_step._last_story(tmp_path, "cats-2", "ar") == "cats-2-ar-story-0123456789ab.webp"


# ============================================================================== cinema_photos.py
def _jpeg(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (60, 90, 80)).save(buf, "JPEG")
    return buf.getvalue()


def _mirror(tmp_path, blob):
    src = tmp_path / "cp.yaml"
    src.write_text('cinemas:\n  c1: "https://chain.example/c1.jpg"\n', encoding="utf-8")
    data = {"cinemas": {"c1": {}}}
    stats = cph.mirror(data, sources_path=src, cache_path=tmp_path / "cp.json", out_dir=tmp_path / "posters", fetch=lambda u: blob)
    return data, stats


def test_a_thumbnail_is_too_small_for_the_header_band(tmp_path):
    data, stats = _mirror(tmp_path, _jpeg(250, 188))                     # Star's 250 px list thumbnails
    assert "photo" not in data["cinemas"]["c1"] and stats["failed"] == 1


def test_a_1075px_photo_is_kept_at_its_own_width_never_upscaled(tmp_path):
    data, _ = _mirror(tmp_path, _jpeg(1075, 520))                        # Cine Royal's gallery size
    ph = data["cinemas"]["c1"]["photo"]
    big = Image.open(tmp_path / "posters" / ph["w1280"].rsplit("/", 1)[1])
    assert big.width == 1075
    assert Image.open(tmp_path / "posters" / ph["w640"].rsplit("/", 1)[1]).width == 640


def test_the_sources_file_lists_only_real_https_urls_for_known_cinemas():
    srcs = cph.load_sources()
    assert len(srcs) >= 27
    import yaml
    known = set((yaml.safe_load(open(os.path.join(ROOT, "cinemas.yaml"), encoding="utf-8")) or {}).get("cinemas") or {})
    for cid, url in srcs.items():
        assert cid in known, cid
        assert url.startswith("https://") and "&amp;" not in url, cid


def test_the_default_fetch_trusts_pillow_not_the_content_type():
    assert cph.MAX_BYTES >= 20 * 1024 * 1024 and cph.CHECK_CAP >= 10
    img = cph._open(_jpeg(1200, 800))                                    # the bytes decide, whatever the header said
    assert img.size == (1200, 800)


# ============================================================================== «سينمتي» (pages/fav.py)
def test_fav_chunk_loads_on_every_page_kind():
    assert fav_page.LAZY_JS == ("fav",)
    assert fav_page.register(None).page_js == {"*": ("fav",)}
    js = open(os.path.join(ROOT, "src", "js", "fav.js"), encoding="utf-8").read()
    for must in ('localStorage.getItem("cinema.me")', "K.rankBoost", "b.hidden = false", '"sheet-me"', "aria-pressed"):
        assert must in js, must


def test_the_cinema_head_bookmark_carries_both_labels_and_no_gold():
    src = open(os.path.join(ROOT, "pages", "_core", "places.py"), encoding="utf-8").read()
    assert 'data-on="' in src and 'data-off="' in src and 'class="fav-l"' in src
    css = open(os.path.join(ROOT, "src", "css", "places-page.css"), encoding="utf-8").read()
    fav_rules = [r for r in css.split("}") if r.strip().startswith(".fav")]
    assert fav_rules and not any("--gold" in r for r in fav_rules)       # gold is the visitor's own numbers only
