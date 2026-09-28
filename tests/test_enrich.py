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


@pytest.fixture(autouse=True)
def _no_wikidata_trailer_lookup(monkeypatch):
    """The Wikidata trailer fallback is a live lookup: stubbed for every test here (conftest refuses the network);
    a test about it replaces this stub with its own."""
    monkeypatch.setattr(enrich_mod, "_wikidata_trailer", lambda qid: None)


@pytest.fixture(autouse=True)
def _no_arabic_label_lookup_and_no_reviewed_list(monkeypatch, tmp_path):
    """W1-D2: the Arabic label refresh is a live lookup too (stubbed; tests/test_w1_d2.py tests it), and the
    owner-editable titles_ar.yaml must never decide a test here: an empty list stands in for it."""
    monkeypatch.setattr(enrich_mod, "_wikidata_ar", lambda qids: {})
    empty = tmp_path / "titles_ar.yaml"
    empty.write_text("titles: {}\n", encoding="utf-8")
    monkeypatch.setattr(enrich_mod, "TITLES_AR_PATH", str(empty))


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

    data = {"films": {"film-a": {"title": "A", "rt": {"critics": 90}}, "film-b": {"title": "B", "rt": {"critics": 90}}}}
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


# ---------------------------------------------------------------- fix wave B: re-releases, synopsis, title_ar

def _film_ent(year, label="The Dark Knight", runtime=152, sitelinks=90, lang_qid="Q1860", ar=None, enwiki=None):
    ent = {
        "labels": {"en": {"value": label}, **({"ar": {"value": ar}} if ar else {})},
        "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
            "P577": [{"mainsnak": {"datavalue": {"value": {"time": f"+{year}-07-18T00:00:00Z"}}}}],
            "P2047": [{"mainsnak": {"datavalue": {"value": {"amount": f"+{runtime}"}}}}] if runtime else [],
            "P364": [{"mainsnak": {"datavalue": {"value": {"id": lang_qid}}}}] if lang_qid else [],
            "P1258": [{"mainsnak": {"datavalue": {"value": "the_dark_knight"}}}],
        },
        "sitelinks": {f"site{i}": {} for i in range(sitelinks)},
    }
    if enwiki:
        ent["sitelinks"]["enwiki"] = {"title": enwiki}
    return ent


def _fake_wikidata(monkeypatch, ents):
    monkeypatch.setattr(enrich_mod, "_wikidata_search",
                        lambda title: [{"id": q, "description": "film"} for q in ents])
    monkeypatch.setattr(enrich_mod, "_wikidata_entities",
                        lambda ids, props="labels|claims": {i: ents[i] for i in ids if i in ents})


def test_rerelease_accepts_a_famous_exact_title_with_matching_runtime(monkeypatch, tmp_path):
    _fake_wikidata(monkeypatch, {"Q163872": _film_ent(2008, ar="فارس الظلام", enwiki="The Dark Knight")})
    seen = {}
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda t: seen.setdefault("page", t) and "Batman fights the Joker.")

    def fake_rt(rt_id, expected_year=None):
        seen["rt"] = (rt_id, expected_year)
        return {"critics": 94, "critics_count": 350, "audience": 94, "consensus": None, "url": "u"}
    monkeypatch.setattr(enrich_mod, "_rt_ratings", fake_rt)

    data = {"films": {"the-dark-knight": {"title": "The Dark Knight", "runtime": 155, "lang": "English"}}}
    film = enrich(data, cache_path=str(tmp_path / "c.json"))["films"]["the-dark-knight"]
    assert film["rerelease"] is True
    assert film["year"] == 2008 and film["title_ar"] == "فارس الظلام"
    assert seen["rt"] == ("the_dark_knight", 2008)      # the year guard accepts the film's own year
    assert film["rt"]["critics"] == 94
    assert seen["page"] == "The Dark Knight" and film["synopsis_en"] == "Batman fights the Joker."


@pytest.mark.parametrize("ent, runtime, lang", [
    (_film_ent(2008, sitelinks=5), 155, "English"),                 # a same-named obscurity
    (_film_ent(2008, runtime=107), 120, "English"),                 # Moana 2016 vs a 120-min listing
    (_film_ent(2008, label="The Dark Knight Returns"), 155, "English"),   # label is not exact
    (_film_ent(2005, lang_qid="Q1860"), 152, "Korean"),              # different original language
])
def test_rerelease_guards_reject(monkeypatch, tmp_path, ent, runtime, lang):
    _fake_wikidata(monkeypatch, {"Q1": ent})
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", _raise)
    monkeypatch.setattr(enrich_mod, "_rt_ratings", _raise)
    data = {"films": {"the-dark-knight": {"title": "The Dark Knight", "runtime": runtime, "lang": lang}}}
    film = enrich(data, cache_path=str(tmp_path / "c.json"))["films"]["the-dark-knight"]
    assert film["rerelease"] is False and film["year"] is None and film["rt"] is None


def test_old_not_found_is_retried_once_for_the_rerelease_fallback(monkeypatch, tmp_path):
    fresh = datetime.now(timezone.utc).isoformat()
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"interstellar": {"ids": {}, "ids_status": "not_found", "ids_checked_at": fresh,
                                                   "synopsis_en": "A 1968 Kannada film about something else."}}), encoding="utf-8")
    _fake_wikidata(monkeypatch, {"Q13417189": _film_ent(2014, label="Interstellar", runtime=169)})
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda t: None)
    monkeypatch.setattr(enrich_mod, "_rt_ratings", lambda rt_id, expected_year=None: None)
    data = {"films": {"interstellar": {"title": "Interstellar", "runtime": 170, "lang": "English"}}}
    film = enrich(data, cache_path=str(cache))["films"]["interstellar"]
    assert film["rerelease"] is True and film["year"] == 2014
    entry = json.loads(cache.read_text(encoding="utf-8"))["interstellar"]
    assert entry["lookup_v"] == enrich_mod.LOOKUP_VERSION and entry["ids_status"] == "found"


def test_synopsis_is_dropped_when_nothing_was_matched(monkeypatch, tmp_path):
    fresh = datetime.now(timezone.utc).isoformat()
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"dhoomakethu": {"ids": {}, "ids_status": "not_found", "ids_checked_at": fresh,
                                                  "lookup_v": 2, "synopsis_en": "Dhoomakethu is a 1968 Kannada film."}}),
                     encoding="utf-8")
    monkeypatch.setattr(enrich_mod.requests, "get", _raise)
    data = {"films": {"dhoomakethu": {"title": "Dhoomakethu", "title_ar_chain": "دhoomakethu"}}}
    film = enrich(data, cache_path=str(cache))["films"]["dhoomakethu"]
    assert film["synopsis_en"] is None
    assert "synopsis_en" not in json.loads(cache.read_text(encoding="utf-8"))["dhoomakethu"]


def test_title_ar_is_never_the_english_label_and_falls_back_to_the_chains(monkeypatch, tmp_path):
    fresh = datetime.now(timezone.utc).isoformat()
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({
        "pressure": {"ids": {"qid": "Q9", "title_ar": "Pressure"}, "ids_status": "found", "ids_checked_at": fresh},
        "crawlers": {"ids": {"qid": "Q8", "title_ar": "Crawlers"}, "ids_status": "found", "ids_checked_at": fresh},
    }), encoding="utf-8")
    monkeypatch.setattr(enrich_mod.requests, "get", _raise)
    data = {"films": {"pressure": {"title": "Pressure", "title_ar_chain": "بريشر"}, "crawlers": {"title": "Crawlers"}}}
    films = enrich(data, cache_path=str(cache))["films"]
    assert films["pressure"]["title_ar"] == "بريشر"
    assert films["crawlers"]["title_ar"] is None


# ---------------------------------------------------------------- fix wave C: template verdicts, rewrites, merges

def _vfile(d, fid, **kw):
    v = {"fid": fid, "verdict": "yes", "ar": "زين.", "en": "Good.", "basis": "RT 90% (40 نقد)",
         "written": "2026-09-24", "by": "claude"}
    v.update(kw)
    (d / f"{fid}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")


def _read(d, fid):
    return json.loads((d / f"{fid}.json").read_text(encoding="utf-8"))


@pytest.fixture
def vdir(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts_mod, "VERDICTS_DIR", tmp_path)
    calls = []

    def fake_generate_one(client, fid, film, notes):
        calls.append(fid)
        return {"fid": fid, "verdict": "yes", "ar": "يستاهل.", "en": "Worth it.", "basis": "RT",
                "basis_numbers": verdicts_mod.basis_numbers(film), "written": "2026-09-26", "by": "claude"}

    monkeypatch.setattr(verdicts_mod, "_generate_one", fake_generate_one)
    monkeypatch.setattr(verdicts_mod, "_client", lambda: object())
    return tmp_path, calls


def test_no_basis_writes_the_template_without_the_model(vdir):
    d, calls = vdir
    write_missing({"films": {"aaram": {"title": "Aaram"}}})
    v = _read(d, "aaram")
    assert calls == []
    assert v["by"] == "template" and v["verdict"] == "unknown"
    assert v["ar"] == "ما لقينا تقييمات كافية لهالفيلم للحين." and v["en"] == "Not enough ratings yet."


def test_template_is_replaced_once_ratings_appear(vdir):
    d, calls = vdir
    write_missing({"films": {"x": {"title": "X"}}})
    write_missing({"films": {"x": {"title": "X", "rt": {"critics": 81, "critics_count": 30}}}})
    assert calls == ["x"] and _read(d, "x")["by"] == "claude"


def test_claude_unknown_without_basis_becomes_the_template(vdir):
    d, calls = vdir
    _vfile(d, "moana", verdict="unknown", ar="ما لقينا تفاصيل واضحة، والمعلومات المتوفرة غامضة.", basis="unknown")
    write_missing({"films": {"moana": {"title": "Moana"}}})
    assert calls == [] and _read(d, "moana")["by"] == "template"


def test_claude_verdict_kept_unless_the_basis_moves_materially(vdir):
    d, calls = vdir
    _vfile(d, "f", basis="RT 90% (40 نقد)")
    write_missing({"films": {"f": {"title": "F", "rt": {"critics": 92, "critics_count": 60}}}})
    assert calls == []
    write_missing({"films": {"f": {"title": "F", "rt": {"critics": 95, "critics_count": 60}}}})
    assert calls == ["f"]
    calls.clear()
    write_missing({"films": {"f": {"title": "F", "rt": {"critics": 95, "critics_count": 130}}}})  # count doubled
    assert calls == ["f"]


def test_claude_unknown_gets_a_real_verdict_when_a_rerelease_gets_rt(vdir):
    d, calls = vdir
    _vfile(d, "the-dark-knight", verdict="unknown", ar="ما لقينا تقييمات كافية لهالفيلم للحين.", basis="unknown")
    write_missing({"films": {"the-dark-knight": {"title": "The Dark Knight", "rt": {"critics": 94, "critics_count": 350}}}})
    assert calls == ["the-dark-knight"]


def test_hand_edited_is_never_touched(vdir):
    d, calls = vdir
    _vfile(d, "h", by="saif", ar="مو زين — كتبه المالك بيده.")
    write_missing({"films": {"h": {"title": "H", "rt": {"critics": 10, "critics_count": 400}}}}, force=True)
    assert calls == [] and _read(d, "h")["by"] == "saif"


def test_claude_verdict_with_a_banned_phrase_is_regenerated(vdir):
    d, calls = vdir
    _vfile(d, "dark-nun", verdict="mixed", ar="تقييم متوسط، مو الأقوى بنوعه.", basis="RT 53% (17 نقد)")
    write_missing({"films": {"dark-nun": {"title": "Dark Nun", "rt": {"critics": 53, "critics_count": 17}}}})
    assert calls == ["dark-nun"]


@pytest.mark.parametrize("line", [
    "ما لقينا معلومات واضحة، الملخص المتوفر يتكلم عن أغنية.",
    "البيانات اللي وصلتنا ناقصة.",
    "ما لقينا تقييمات، والمعلومات المتوفرة ناقصة.",
    "ما نقدر نحكم عليه للحين.",
    "بنحدّث المعلومات أول ما تتوفر.",
    "نتابعه ونحدّث لكم.",
    "تقييم متوسط، مو الأقوى.",
    "لو تبغي رأي واضح ترّى شوي.",
])
def test_meta_talk_and_non_emirati_words_are_banned(line):
    assert _dialect_violation(line)


def test_english_meta_talk_is_banned():
    assert verdicts_mod._english_violation("The summary we have is about a song.")
    assert verdicts_mod._english_violation("We'll update once ratings arrive.")
    assert verdicts_mod._english_violation("Worth it: 94% of critics.") is None


def test_prompt_carries_a_synopsis_only_for_a_matched_film():
    film = {"title": "Dhoomakethu", "synopsis_en": "Dhoomakethu is a 1968 Kannada film.", "wikidata": {"qid": None}}
    assert "1968" not in verdicts_mod._film_prompt("dhoomakethu", film, None)
    film["wikidata"] = {"qid": "Q1"}
    assert "1968" in verdicts_mod._film_prompt("dhoomakethu", film, None)


def test_fold_merged_moves_or_deletes(vdir):
    d, _ = vdir
    _vfile(d, "fall-2", verdict="mixed")
    _vfile(d, "fall-2-deadpoint", verdict="mixed")
    _vfile(d, "moana-live-action", verdict="mixed", basis="RT 35% · CinemaScore A-")
    _vfile(d, "moana", verdict="unknown", ar="غامض.")
    _vfile(d, "the-vvaan", verdict="skip")
    done = verdicts_mod.fold_merged({"fall-2": "fall-2-deadpoint", "moana-live-action": "moana",
                                     "the-vvaan": "the-vvaan-force-of-the-forest", "not-there": "x"})
    assert done == {"fall-2": "deleted", "moana-live-action": "moved -> moana",
                    "the-vvaan": "moved -> the-vvaan-force-of-the-forest"}
    assert not (d / "fall-2.json").exists() and (d / "fall-2-deadpoint.json").exists()
    assert _read(d, "moana")["verdict"] == "mixed" and _read(d, "moana")["fid"] == "moana"
    assert _read(d, "the-vvaan-force-of-the-forest")["verdict"] == "skip"
