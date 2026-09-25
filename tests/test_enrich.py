"""Tests for enrich.py — cache hits skip the network, unknown films never crash.

Network is always mocked here (monkeypatching enrich.requests / enrich._polite_get);
tests never call the real Wikidata/RT/Wikipedia endpoints.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import enrich as enrich_mod
from enrich import enrich
import verdicts as verdicts_mod
from verdicts import _dialect_violation, write_missing


def _raise(*a, **kw):
    raise AssertionError("network was called when the cache should have been used")


def test_cache_hit_makes_no_network_call(tmp_path, monkeypatch):
    cache_path = tmp_path / "films_cache.json"
    fresh_at = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(json.dumps({
        "heart-of-the-beast": {
            "ids": {
                "qid": "Q1", "title_ar": "قلب الوحش", "year": 2026, "runtime": 101,
                "genres": {"en": ["Adventure"], "ar": ["مغامرة"]},
                "director": "David Ayer", "cast": ["Brad Pitt"],
                "imdb_id": "tt1234567", "rt_id": "heart_of_the_beast",
            },
            "synopsis_en": "A soldier and his dog survive a plane crash.",
            "ratings": {"critics": 92, "critics_count": 37, "audience": None,
                        "consensus": "Moving.", "url": "https://www.rottentomatoes.com/m/heart_of_the_beast"},
            "ratings_at": fresh_at,
        }
    }), encoding="utf-8")

    monkeypatch.setattr(enrich_mod.requests, "get", _raise)

    data = {"films": {"heart-of-the-beast": {"title": "Heart of the Beast"}}}
    out = enrich(data, cache_path=str(cache_path))

    film = out["films"]["heart-of-the-beast"]
    assert film["title_ar"] == "قلب الوحش"
    assert film["year"] == 2026
    assert film["rt"]["critics"] == 92
    assert film["imdb"]["id"] == "tt1234567"
    assert film["imdb_score"] is None


def test_offline_never_touches_network(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich_mod.requests, "get", _raise)
    data = {"films": {"some-film": {"title": "Some Film"}}}
    out = enrich(data, cache_path=str(tmp_path / "films_cache.json"), offline=True)
    film = out["films"]["some-film"]
    assert film["title"] == "Some Film"
    assert film["poster"] is None
    assert film["rt"] is None
    assert film["imdb_score"] is None


def test_unknown_film_keeps_title_and_stays_null_without_crashing(monkeypatch, tmp_path):
    """Wikidata has nothing for it; the RT id never exists; nothing raises."""
    def fake_get(url, **kw):
        class R:
            status_code = 200
            def json(self):
                if "wbsearchentities" in url:
                    return {"search": []}
                return {}
        return R()

    monkeypatch.setattr(enrich_mod.requests, "get", fake_get)
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda title: None)

    data = {"films": {"totally-obscure-film": {"title": "Totally Obscure Film"}}}
    out = enrich(data, cache_path=str(tmp_path / "films_cache.json"))

    film = out["films"]["totally-obscure-film"]
    assert film["title"] == "Totally Obscure Film"
    assert film["poster"] is None
    assert film["rt"] is None
    assert film["title_ar"] is None
    assert film["imdb"]["id"] is None


def test_stale_ratings_are_refetched_ids_are_not(tmp_path, monkeypatch):
    stale_at = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    cache_path = tmp_path / "films_cache.json"
    cache_path.write_text(json.dumps({
        "some-film": {
            "ids": {"qid": "Q9", "title_ar": "فيلم", "rt_id": "some_film", "genres": {"en": [], "ar": []}},
            "ratings": {"critics": 10, "critics_count": 1, "audience": None, "consensus": None, "url": "x"},
            "ratings_at": stale_at,
        }
    }), encoding="utf-8")

    called = {"wikidata": False, "rt": False}

    def fake_wikidata_ids(title, accepted_years=None):
        called["wikidata"] = True
        return {}

    def fake_rt_ratings(rt_id, expected_year=None):
        called["rt"] = True
        return {"critics": 77, "critics_count": 50, "audience": 80, "consensus": "Better now.",
                "url": "https://www.rottentomatoes.com/m/some_film"}

    monkeypatch.setattr(enrich_mod, "_wikidata_ids", fake_wikidata_ids)
    monkeypatch.setattr(enrich_mod, "_rt_ratings", fake_rt_ratings)

    data = {"films": {"some-film": {"title": "Some Film"}}}
    out = enrich(data, cache_path=str(cache_path))

    assert called["wikidata"] is False  # ids are permanent, never refetched once cached
    assert called["rt"] is True         # ratings older than the 3-day TTL are refetched
    assert out["films"]["some-film"]["rt"]["critics"] == 77


# ---------- verdicts.py: dialect post-check ----------

def test_dialect_check_rejects_arabic_indic_digits():
    assert _dialect_violation("الفيلم حصل ٩١٪ من النقاد.") is not None


def test_dialect_check_rejects_banned_word():
    assert _dialect_violation("وش رايك فيه؟ فيلم زين.") is not None


def test_dialect_check_rejects_tanwin():
    assert _dialect_violation("الفيلم عدداً صحيحاً من المشاهد.") is not None


def test_dialect_check_accepts_clean_emirati_line():
    assert _dialect_violation("حلو وايد، النقاد عطوه 91% والجمهور مب بعيد عنهم.") is None


# ---------- verdicts.py: write_missing ----------

def test_write_missing_skips_hand_edited_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts_mod, "VERDICTS_DIR", tmp_path)

    hand_edited = tmp_path / "some-film.json"
    hand_edited.write_text(json.dumps({
        "fid": "some-film", "verdict": "yes", "ar": "المالك عدّل هذا بنفسه.",
        "en": "Owner edited this himself.", "basis": "manual", "written": "2026-09-20", "by": "owner",
    }, ensure_ascii=False), encoding="utf-8")

    def fail_client():
        raise AssertionError("the Anthropic client must never be built for a hand-edited film")

    monkeypatch.setattr(verdicts_mod, "_client", fail_client)

    data = {"films": {"some-film": {"title": "Some Film"}}}
    results = write_missing(data)

    assert results == {}
    # the file on disk is untouched
    assert json.loads(hand_edited.read_text(encoding="utf-8"))["by"] == "owner"


def test_write_missing_skips_existing_claude_verdict_without_force(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts_mod, "VERDICTS_DIR", tmp_path)
    path = tmp_path / "some-film.json"
    path.write_text(json.dumps({
        "fid": "some-film", "verdict": "yes", "ar": "زين.", "en": "Good.",
        "basis": "RT 90%", "written": "2026-09-24", "by": "claude",
    }, ensure_ascii=False), encoding="utf-8")

    def fail_client():
        raise AssertionError("no client should be built when nothing needs writing")

    monkeypatch.setattr(verdicts_mod, "_client", fail_client)

    data = {"films": {"some-film": {"title": "Some Film"}}}
    results = write_missing(data)
    assert results == {}


# ---------- verdicts.py: round-1 controller fixes ----------

def test_dialect_check_rejects_lexicon_words():
    for word in ("وش", "يجي", "جوّا", "يوريك", "زي", "طيب", "كذا", "مين", "سيارة"):
        assert _dialect_violation(f"هذا فيه كلمة {word} داخل الجملة.") is not None, word


def test_dialect_check_rejects_screening_count_phrase_is_not_a_hard_rule_but_lein_lisa_is():
    assert _dialect_violation("وودي وباز لين لسا يشدّون.") is not None


def test_write_missing_only_fids_limits_regeneration(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts_mod, "VERDICTS_DIR", tmp_path)
    for fid in ("film-a", "film-b"):
        (tmp_path / f"{fid}.json").write_text(json.dumps({
            "fid": fid, "verdict": "yes", "ar": "زين.", "en": "Good.",
            "basis": "RT 90%", "written": "2026-09-24", "by": "claude",
        }, ensure_ascii=False), encoding="utf-8")

    calls = []

    def fake_generate_one(client, fid, film, notes):
        calls.append(fid)
        return {"fid": fid, "verdict": "yes", "ar": "زين جداً.", "en": "Great.",
                "basis": "RT 95%", "written": "2026-09-26", "by": "claude"}

    monkeypatch.setattr(verdicts_mod, "_generate_one", fake_generate_one)
    monkeypatch.setattr(verdicts_mod, "_client", lambda: object())

    data = {"films": {"film-a": {"title": "A"}, "film-b": {"title": "B"}}}
    results = write_missing(data, force=True, only_fids={"film-a"})

    assert calls == ["film-a"]
    assert set(results) == {"film-a"}
    assert json.loads((tmp_path / "film-b.json").read_text(encoding="utf-8"))["basis"] == "RT 90%"


# ---------- verdicts.py: round-2 controller fixes (the exact strings flagged) ----------

def test_dialect_check_rejects_round2_flagged_strings():
    cases = [
        "الفيلم يجيك بتقييم حلو.",                  # يجيك — inflected form of the "يجي" root
        "يجي وقته لما تشوفه.",                       # يجي itself
        "وودي وباز لين لسا يشدّون.",                  # لين لسا (phrase)
        "لسا ما طلع تقييم رسمي.",                     # لسا alone
        "والي تباها بتجربة الجمهور من يديد.",         # والي — typo for واللي
        "شاهده في السينما لو تقدر.",                  # شاهده — MSA register
        "الجمهور فرح فيه أكثر من النقاد.",            # فرح فيه (phrase)
        "يصلح لمحبين ستاذم بس.",                      # ستاذم — garbled "Statham"
        "فيلم Digger فيه آراء متضاربة.",              # "فيلم X" opener
    ]
    for text in cases:
        assert _dialect_violation(text) is not None, text


def test_dialect_check_catches_other_yiji_inflections_not_just_yijik():
    # the controller's exact question: "يجيك" passing proved the check only matched the bare
    # root — these are other inflections that must be caught by the same root-prefix rule.
    for text in ("بيجي بكرة.", "تجيك النتيجة قريب.", "يجينا خبر منه."):
        assert _dialect_violation(text) is not None, text


# ---------- enrich.py: round-3 controller review (no stale-year matches, no caching errors) ----------

def test_best_film_in_hits_rejects_old_same_title_film_no_fallback():
    """Two film-shaped hits for one title: one from an accepted year, one old. The old one
    must never come back, even as a "best we found" fallback — a wrong-film match (e.g. the
    2016 "The Odyssey" instead of the 2026 one) is worse than no match at all."""
    hits = [
        {"id": "Q_OLD", "description": "2016 film directed by Someone Else"},
        {"id": "Q_NEW", "description": "2026 film directed by Christopher Nolan"},
    ]

    def fake_entities(ids):
        by_id = {
            "Q_OLD": {"claims": {
                "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
                "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2016-01-01T00:00:00Z"}}}}],
            }},
            "Q_NEW": {"claims": {
                "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
                "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2026-01-01T00:00:00Z"}}}}],
            }},
        }
        return {i: by_id[i] for i in ids if i in by_id}

    enrich_mod._wikidata_entities = fake_entities
    try:
        # Only the old film is available this round — must return None, not Q_OLD.
        assert enrich_mod._best_film_in_hits([hits[0]], {2025, 2026}) is None
        # With both available, the accepted-year one is returned.
        assert enrich_mod._best_film_in_hits(hits, {2025, 2026}) == "Q_NEW"
    finally:
        enrich_mod._wikidata_entities = _real_wikidata_entities


_real_wikidata_entities = enrich_mod._wikidata_entities


def test_find_film_qid_returns_none_when_only_an_old_match_exists(monkeypatch):
    """End-to-end through _find_film_qid: plain search and both "(2026 film)"/"(2025 film)"
    retries only ever turn up the old film — the function must give up with None, not return
    the old qid as a last resort."""
    old_hit = {"id": "Q_OLD", "description": "2016 film directed by Someone Else"}

    def fake_search(title):
        return [old_hit]

    def fake_entities(ids):
        return {"Q_OLD": {"claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
            "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2016-01-01T00:00:00Z"}}}}],
        }}}

    monkeypatch.setattr(enrich_mod, "_wikidata_search", fake_search)
    monkeypatch.setattr(enrich_mod, "_wikidata_entities", fake_entities)

    assert enrich_mod._find_film_qid("The Odyssey", {2025, 2026}) is None


def test_network_failure_on_first_lookup_is_not_cached_as_not_found(tmp_path, monkeypatch):
    """A transient error during a film's first-ever Wikidata lookup must be retried on a
    future run, not permanently recorded as "confirmed absent" the way a real empty result
    is."""
    cache_path = tmp_path / "films_cache.json"

    def raise_lookup_failed(title, accepted_years):
        raise enrich_mod.LookupFailed("simulated outage")

    monkeypatch.setattr(enrich_mod, "_wikidata_ids", raise_lookup_failed)
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda title: None)

    data = {"films": {"new-film": {"title": "Brand New Film"}}}
    enrich(data, cache_path=str(cache_path))

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["new-film"]
    assert entry["ids_status"] == "error"          # not "not_found"
    assert entry.get("ids") in (None, {}, [])       # nothing was confirmed, nothing invented
    assert entry["ids_checked_at"]                  # timestamped so ERROR_TTL can expire it

    # Once the error TTL has passed and the network is healthy again, it must retry and
    # succeed — proving it wasn't permanently poisoned.
    stale_error_at = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    cache["new-film"]["ids_checked_at"] = stale_error_at
    cache_path.write_text(json.dumps(cache), encoding="utf-8")

    def fake_wikidata_ids(title, accepted_years):
        return {"qid": "Q123", "title_ar": "فيلم يديد", "genres": {"ar": [], "en": []}}

    monkeypatch.setattr(enrich_mod, "_wikidata_ids", fake_wikidata_ids)

    data2 = {"films": {"new-film": {"title": "Brand New Film"}}}
    out2 = enrich(data2, cache_path=str(cache_path))
    assert out2["films"]["new-film"]["title_ar"] == "فيلم يديد"

    cache2 = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache2["new-film"]["ids_status"] == "found"


def test_genuine_not_found_is_retried_after_its_own_ttl(tmp_path, monkeypatch):
    """A real (successfully-queried) empty result is cached, but only for NOT_FOUND_TTL —
    unlike "found", it is not permanent, since a brand-new release may gain a Wikidata item
    a few days later."""
    cache_path = tmp_path / "films_cache.json"
    stale_not_found_at = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    cache_path.write_text(json.dumps({
        "obscure-film": {"ids": {}, "ids_status": "not_found", "ids_checked_at": stale_not_found_at},
    }), encoding="utf-8")

    called = {"wikidata": False}

    def fake_wikidata_ids(title, accepted_years):
        called["wikidata"] = True
        return {"qid": "Q999", "genres": {"ar": [], "en": []}}

    monkeypatch.setattr(enrich_mod, "_wikidata_ids", fake_wikidata_ids)
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda title: None)

    data = {"films": {"obscure-film": {"title": "Obscure Film"}}}
    enrich(data, cache_path=str(cache_path))

    assert called["wikidata"] is True  # 4 days > NOT_FOUND_TTL (3 days) — retried
