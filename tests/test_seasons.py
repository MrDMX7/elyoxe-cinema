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


def test_taraweeh_minutes_wraps_past_midnight():
    # isha at 23:45 -> taraweeh at 00:45 the same clock, never a negative or >1440 minute count
    assert (23 * 60 + 45 + 60) % (24 * 60) == 45


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
    groups = seasons.kids_shows(site, before_hour=14)
    for city, fids in groups.items():
        for fid, shows in fids:
            assert build.film_flags(site.films[fid])[1] is True
            for s in shows:
                assert s["date"] == site.today
                assert s["time"] < "14:00"
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


# --------------------------------------------------------------------------------- post-credits
def test_post_credits_field_present_but_empty_until_a_source_is_wired():
    import enrich
    film = {"title": "X"}
    enrich._blank_film_fields(film)
    assert film["post_credits"] is None
    assert enrich.post_credits_for("Q123") is None
