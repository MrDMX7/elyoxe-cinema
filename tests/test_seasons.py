"""Phase 2, task 6 (pages/seasons.py + the additive verdicts.py/enrich.py hooks): Hijri
windows on fixed dates, the taraweeh = isha + 60 min rule, the kids filter, the IMAX/MAX line
generated only with a cited basis, and the dialect post-check applied to it exactly as the main
verdict already does."""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build  # noqa: E402
import pages.seasons as seasons  # noqa: E402
import verdicts  # noqa: E402


# --------------------------------------------------------------------------------- Hijri windows
def test_ramadan_window_fixed_dates_2026():
    assert seasons.is_ramadan(date(2026, 3, 1)) is True         # inside the derived Ramadan window
    assert seasons.is_ramadan(date(2026, 2, 17)) is False        # the day before it starts
    assert seasons.is_ramadan(date(2026, 3, 19)) is False        # Eid al-Fitr's first day itself
    assert seasons.is_ramadan(date(2026, 6, 1)) is False


def test_eid_within_ten_days_fixed_dates():
    assert seasons.eid_within(date(2026, 3, 9)) == ("fitr", date(2026, 3, 19))   # exactly 10 days out
    assert seasons.eid_within(date(2026, 3, 8)) is None                          # 11 days out: too early
    assert seasons.eid_within(date(2026, 3, 19)) == ("fitr", date(2026, 3, 19))  # 0 days: today
    assert seasons.eid_within(date(2026, 3, 20)) is None                        # already started: not "within"
    assert seasons.eid_within(date(2026, 5, 16)) == ("adha", date(2026, 5, 26))


# ------------------------------------------------------------------------------------- taraweeh
def test_taraweeh_is_isha_plus_sixty_minutes():
    lat, lng = seasons.CITY_COORDS["dubai"]
    d = date(2026, 3, 5)
    isha = seasons.prayer_minutes(lat, lng, d)["isha"]
    assert seasons.taraweeh_minutes(lat, lng, d) == (isha + 60) % (24 * 60)


def test_taraweeh_minutes_wraps_past_midnight(monkeypatch):
    # isha at 23:45 -> taraweeh at 00:45 the same clock, never a negative or >1440 minute count
    monkeypatch.setattr(seasons, "prayer_minutes", lambda lat, lng, d: {"maghrib": 0, "isha": 23 * 60 + 45})
    assert seasons.taraweeh_minutes(0, 0, date(2026, 3, 5)) == 45


def test_iftar_and_taraweeh_lines_labelled_approx():
    # this is static site copy (never sent through Claude), so it uses the site's own mandated
    # spelling of "تقريباً" (docs/superpowers/specs/2026-09-26-phase1-design.md: "«تقريباً» on
    # estimates") rather than the model-output dialect post-check, which bans that same tanwin
    # mark in *generated* spoken lines (feedback_emirati_dialect.md) — the two rules apply to
    # different text and are not in conflict.
    d = date(2026, 3, 5)
    tara = seasons.taraweeh_note("dubai", d, "ar")
    assert "تقريباً" in tara
    iftar = seasons.iftar_line("dubai", d, "ar")
    assert "الإفطار" in iftar and "المغرب" in iftar
    assert seasons.iftar_line("nowhere", d, "ar") is None   # unknown city: no line, not a guess


# ------------------------------------------------------------------------------------ kids filter
def _site_stub():
    data = json.load(open(os.path.join(ROOT, "fixtures", "sample_latest.json"), encoding="utf-8"))
    disc = build.load_discounts(os.path.join(ROOT, "fixtures", "sample_discounts.yaml"))
    halls = build.Halls(os.path.join(ROOT, "halls.yaml"))
    return build.Site(data, disc, halls, os.path.join(ROOT, "tests", "_out_seasons"), build.discover(only=("core",)))


def test_kids_shows_filters_to_kids_flagged_films_before_cutoff():
    site = _site_stub()
    for day in (site.today, site.tomorrow):
        groups = seasons.kids_shows(site, before_hour=14, day=day)
        for city, fids in groups.items():
            for fid, shows in fids:
                assert build.film_flags(site.films[fid])[1] is True
                for s in shows:
                    assert s["date"] == day
                    assert s["time"] < "14:00"
                    assert not site.is_past(s)                  # a show already started is not offered
                    assert (site.cinemas.get(s["cinema"]) or {}).get("city") == city


def test_summer_active_only_in_july_august():
    assert seasons.summer_active(date(2026, 7, 1)) is True
    assert seasons.summer_active(date(2026, 8, 31)) is True
    assert seasons.summer_active(date(2026, 6, 30)) is False
    assert seasons.summer_active(date(2026, 9, 1)) is False


# ------------------------------------------------------------------------------- IMAX/MAX line
def test_imax_basis_only_with_a_cited_basis():
    assert verdicts.imax_basis({"runtime": 100, "genres": {"en": ["drama"]}}, {"Standard", "IMAX"}) is None
    assert verdicts.imax_basis({"runtime": 100, "genres": {"en": ["drama"]}}, {"Standard"}) is None  # no premium format at all
    assert verdicts.imax_basis({"runtime": 150, "genres": {"en": ["drama"]}}, {"Standard", "IMAX"}) == "runtime 150 min"
    assert verdicts.imax_basis({"runtime": 100, "genres": {"en": ["action"]}}, {"Standard", "MAX"}) == "genre: action"
    notes = "Critics praised the film's IMAX-worthy scale and use of large-format cinematography."
    basis = verdicts.imax_basis({"runtime": 100, "genres": {"en": ["drama"]}}, {"IMAX"}, notes)
    assert basis and "imax" in basis.lower()


class _FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class _FakeClient:
    """Returns the queued responses in order — first a rule-breaking draft (banned word), then
    a compliant one — so the test proves the same post-check the main verdict uses is applied
    here too, and a rejected draft is regenerated rather than shipped (feedback_emirati_dialect.md)."""
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0
        outer = self

        class _M:
            def create(self, **kw):
                outer.calls += 1
                return _FakeMsg(outer.texts.pop(0))
        self.messages = _M()


def test_imax_line_rejected_draft_is_regenerated_then_written(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts, "VERDICTS_DIR", tmp_path)
    bad = json.dumps({"ar": "هذا الفيلم وش رهيب فيه", "en": "Worth the big screen."})
    good = json.dumps({"ar": "يستاهل تشوفه بصيغة IMAX، الحجم واضح والصورة أكبر.", "en": "Worth the IMAX screen — the scale is real."})
    fake = _FakeClient([bad, good])
    monkeypatch.setattr(verdicts, "_client", lambda: fake)

    data = {"films": {"big-one": {"title": "Big One", "runtime": 150, "genres": {"en": ["drama"]}}}}
    results = verdicts.write_imax(data, {"big-one": {"Standard", "IMAX"}})

    assert fake.calls == 2                                  # the bad draft was rejected and retried
    assert results["big-one"]["by"] == "claude"
    assert results["big-one"]["which"] == "IMAX"
    assert verdicts._dialect_violation(results["big-one"]["ar"]) is None
    on_disk = json.loads((tmp_path / "big-one.json").read_text(encoding="utf-8"))
    assert on_disk["imax"]["basis"] == "runtime 150 min"


def test_imax_no_basis_writes_nothing_and_clears_a_stale_one(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts, "VERDICTS_DIR", tmp_path)
    monkeypatch.setattr(verdicts, "_client", lambda: (_ for _ in ()).throw(AssertionError("no model call expected")))

    data = {"films": {"quiet-one": {"title": "Quiet One", "runtime": 90, "genres": {"en": ["drama"]}}}}
    results = verdicts.write_imax(data, {"quiet-one": {"Standard"}})
    assert results == {}
    assert not (tmp_path / "quiet-one.json").exists()

    # a stale "imax" entry (format dropped, or basis no longer holds) is removed, not left stranded
    (tmp_path / "quiet-one.json").write_text(json.dumps({"fid": "quiet-one", "imax": {"ar": "x", "en": "y", "basis": "old"}}),
                                              encoding="utf-8")
    results = verdicts.write_imax(data, {"quiet-one": {"Standard"}})
    assert results == {"quiet-one": None}
    assert "imax" not in json.loads((tmp_path / "quiet-one.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------- page-level builds
def _build(tmp_path, mutate=None):
    """Full build (core + seasons only) from a mutated copy of fixtures/sample_latest.json."""
    data = json.load(open(os.path.join(ROOT, "fixtures", "sample_latest.json"), encoding="utf-8"))
    if mutate:
        mutate(data)
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(data), encoding="utf-8")
    out = str(tmp_path / "out")
    build.build(str(data_path), os.path.join(ROOT, "fixtures", "sample_discounts.yaml"), out,
                noindex=False, modules=build.discover(only=("core", "seasons")))
    return out


def _read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def test_build_eid_page_in_window_uses_the_coming_dict_not_a_list(tmp_path):
    # 2026-03-10 is 9 days before Eid al-Fitr's first day (2026-03-19) -- within the 10-day window.
    # data["coming"] is a dict keyed by fid (steps/coming.py's real contract), not a list of
    # records: this is the exact shape that crashed build_eid before the fix.
    def m(d):
        d["generated"] = "2026-03-10T09:00:00+04:00"
        d["coming"] = {"heart-of-the-beast": {"title": "Heart of the Beast", "title_ar": None,
                                                "release_date": "2026-03-19", "poster": None,
                                                "trailer": None, "genres": [], "chains": ["vox"]},
                       "not-a-real-film": {"title": "Nope", "title_ar": None, "release_date": "2026-03-19",
                                            "poster": None, "trailer": None, "genres": [], "chains": ["vox"]}}
    out = _build(tmp_path, m)
    eid = _read(out, "eid", "index.html")
    assert 'href="/film/heart-of-the-beast/"' in eid       # in data["coming"] and in data["films"]
    assert "not-a-real-film" not in eid                        # coming entry with no matching film: dropped
    home = _read(out, "index.html")
    assert '<a href="/eid/">' in home                          # nav link present while Eid is within 10 days


def test_build_eid_page_in_window_without_coming_feed_falls_back_to_showing(tmp_path):
    def m(d):
        d["generated"] = "2026-03-10T09:00:00+04:00"
        d.pop("coming", None)
    out = _build(tmp_path, m)
    eid = _read(out, "eid", "index.html")
    assert 'href="/film/heart-of-the-beast/"' in eid       # a showing film, no coming feed to restrict it


def test_build_eid_page_absent_outside_the_ten_day_window(tmp_path):
    def m(d):
        d["generated"] = "2026-04-01T09:00:00+04:00"           # neither Eid is within 10 days here
    out = _build(tmp_path, m)
    assert not os.path.exists(os.path.join(out, "eid"))
    home = _read(out, "index.html")
    assert '/eid/' not in home


def _kids_film(d):
    d["films"]["heart-of-the-beast"].update(rating="G", genres=["animation"], family=True, kids=True)


def _ct(html):
    import re
    return json.loads(re.search(r"<script>window\.CT = (.*?);</script>", html).group(1))


def test_kids_page_in_the_morning_has_this_morning_then_tomorrow_waiting(tmp_path):
    """Before 14:00: this morning shows, tomorrow morning is in the page but hidden until 14:00 (when.js)."""
    import re

    def m(d):
        d["generated"] = "2026-09-25T09:00:00+04:00"
        _kids_film(d)
    out = _build(tmp_path, m)
    for lang, parts in (("ar", ("kids", "index.html")), ("en", ("en", "kids", "index.html"))):
        kids = _read(out, *parts)
        today = re.search(r'<section class="wrap kids-day" data-until="2026-09-25T14:00">(.*?)</section>', kids, re.S).group(1)
        tomorrow = re.search(r'<section class="wrap kids-day" data-from="2026-09-25T14:00" hidden>(.*?)</section>', kids, re.S).group(1)
        assert ("اليوم الصبح" if lang == "ar" else "This morning") in today
        assert ("بكرة الصبح" if lang == "ar" else "Tomorrow morning") in tomorrow
        for block in (today, tomorrow):
            assert "/film/heart-of-the-beast/" in block and "10:30" in block and "15:30" not in block
        assert re.match(r"/assets/when\.[0-9a-f]{10}\.js$", _ct(kids)["chunks"]["when"])


def test_kids_page_after_two_pm_lists_tomorrow_morning(tmp_path):
    """After 14:00 the page used to say there was nothing (MASTER-PLAN §4.1 #21): now it is tomorrow morning."""
    def m(d):
        d["generated"] = "2026-09-25T16:00:00+04:00"
        _kids_film(d)
    out = _build(tmp_path, m)
    kids = _read(out, "kids", "index.html")
    assert "data-until" not in kids and "اليوم الصبح" not in kids
    assert '<section class="wrap kids-day" data-from="2026-09-25T14:00"><h2>بكرة الصبح</h2>' in kids
    assert 'href="/film/heart-of-the-beast/"' in kids and "ما فيه عروض عيال قبل الظهر اليوم" not in kids


def test_kids_page_says_tomorrow_is_not_in_yet(tmp_path):
    def m(d):
        d["generated"] = "2026-09-25T16:00:00+04:00"
        _kids_film(d)
        d["shows"] = [x for x in d["shows"] if x["date"] != "2026-09-26"]
    kids = _read(_build(tmp_path, m), "kids", "index.html")
    assert "ما عندنا عروض عيال بكرة الصبح للحين" in kids


def test_build_kids_page_lists_only_kids_flagged_films_before_1400(tmp_path):
    def m(d):
        # the fixture already sets explicit "family"/"kids" (False) on this film, so film_flags()
        # never falls back to deriving from rating/genre -- set the explicit flag itself.
        d["films"]["heart-of-the-beast"].update(rating="G", genres=["animation"], family=True, kids=True)
    out = _build(tmp_path, m)
    kids = _read(out, "kids", "index.html")
    assert 'href="/film/heart-of-the-beast/"' in kids       # 10:30 show, G + animation
    assert 'href="/film/resident-evil/"' not in kids        # not kids-flagged


def test_build_summer_page_in_season_has_no_time_cutoff_and_no_noindex(tmp_path):
    def m(d):
        d["generated"] = "2026-07-15T09:00:00+04:00"
        d["films"]["heart-of-the-beast"].update(family=True, kids=False)
        # a show after 14:00, on the summer-mutated "today" -- must still appear (no morning cutoff)
        d["shows"].append({"cinema": "cinemacity-zero6-mall", "film": "heart-of-the-beast",
                            "date": "2026-07-15", "time": "20:00", "hall": "Standard",
                            "hall_label": "Screen 3", "prices": [{"seat": "Regular", "aed": 35}], "book": None})
    out = _build(tmp_path, m)
    summer = _read(out, "summer", "index.html")
    assert "noindex" not in summer
    assert 'href="/film/heart-of-the-beast/"' in summer     # the 20:00 show counted, not just a morning one
    home = _read(out, "index.html")
    assert '<a href="/summer/">' in home


def test_summer_page_is_not_built_out_of_season(tmp_path):
    """The empty noindex placeholder is deleted (W0-P2, MASTER-PLAN §4.1 #22): out of July and August there is
    no /summer/ at all, and a folder an older build left in out/ is cleared ("summer" stays in DIRS)."""
    stale = tmp_path / "out" / "summer"
    stale.mkdir(parents=True)
    (stale / "index.html").write_text("old placeholder", encoding="utf-8")

    def m(d):
        d["generated"] = "2026-01-15T09:00:00+04:00"
    out = _build(tmp_path, m)
    assert not os.path.exists(os.path.join(out, "summer")) and not os.path.exists(os.path.join(out, "en", "summer"))
    assert "/summer/" not in _read(out, "index.html") and "/summer/" not in _read(out, "sitemap.xml")
    assert "summer" in seasons.DIRS


def test_summer_in_season_is_in_the_sitemap(tmp_path):
    def m(d):
        d["generated"] = "2026-07-15T09:00:00+04:00"
    out = _build(tmp_path, m)
    sm = _read(out, "sitemap.xml")
    assert "https://cinema.elyoxe.com/summer/" in sm and "/en/summer/" in sm


# --------------------------------------------------------------------------------- post-credits
def test_post_credits_field_present_but_empty_until_a_source_is_wired():
    import enrich
    film = {"title": "X"}
    enrich._blank_film_fields(film)
    assert film["post_credits"] is None
    assert enrich.post_credits_for("Q123") is None
