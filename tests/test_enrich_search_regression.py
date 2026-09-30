"""Regression tests for the 2026-09-28 matching outage (fix landed 2026-09-30).

Real symptom (the phone's data/films_cache.json, 2026-09-28): resident-evil, digger, the-odyssey and
most other current films came back "not_found" and stayed that way, dropping the site from ~all films
having a Wikidata/RT match to 26/82 qid and 21/82 rt. Root cause, confirmed against the live Wikidata
API from the laptop (network allowed there, never in this suite): wbsearchentities alone (the only
search enrich.py ever used) is a label/alias *prefix* match ranked by sitelink count. A brand-new,
barely-linked film routinely loses that ranking to an older or unrelated work sharing its title —
"Resident Evil" (2026, Zach Cregger) doesn't surface even 50 hits deep behind the video-game franchise
and its entries; "Digger" (2026, Iñárritu) and "The Odyssey" (2026, Nolan) both rank past position 6
(the limit _wikidata_search used) behind an older film/game/epic poem of the same title. None of this
is a year-guard or "wrong match" problem — round-3's year filter and re-release guards were correct and
stay exactly as strict. It is a candidate-discovery problem: the right item was never among the hits
_best_film_in_hits was even allowed to look at.

Every test here mocks the network (this suite refuses real sockets — see conftest.py); each one is
built to fail against the pre-fix code (verified separately by running this file against the
2026-09-28 revision of enrich.py) and pass against the fix in this branch.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import enrich as enrich_mod
from enrich import enrich


def _ent(year, label="Title", p31="Q11424", runtime=None, sitelinks=0, lang_qid=None):
    claims = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": p31}}}}],
              "P577": [{"mainsnak": {"datavalue": {"value": {"time": f"+{year}-01-01T00:00:00Z"}}}}]}
    if runtime:
        claims["P2047"] = [{"mainsnak": {"datavalue": {"value": {"amount": f"+{runtime}"}}}}]
    if lang_qid:
        claims["P364"] = [{"mainsnak": {"datavalue": {"value": {"id": lang_qid}}}}]
    return {"labels": {"en": {"value": label}}, "claims": claims,
            "sitelinks": {f"s{i}": {} for i in range(sitelinks)}}


# ---------------------------------------------------------------------------------------------
# The dominant case: a brand-new release wbsearchentities buries, that a full-text search finds.

def test_new_release_buried_in_wbsearchentities_is_found_via_fulltext_merge(monkeypatch):
    """"Resident Evil" (2026): wbsearchentities' top hits are all the media franchise/video games
    (no accepted-year film among them, exactly the real top-6 for this title); a plain full-text
    search doesn't surface the film either (real behaviour — it also loses to the franchise's much
    larger text footprint). Only appending " film" to the full-text query finds it (real behaviour,
    verified live: rank 2 of 10). _find_film_qid must still return it."""
    wrong_hits = [{"id": "Q_FRANCHISE", "description": "media franchise"},
                  {"id": "Q_GAME", "description": "1996 survival horror video game"}]
    entities = {
        "Q_FRANCHISE": _ent(0, label="Resident Evil", p31="Q196600"),   # not a film at all
        "Q_GAME": _ent(1996, label="Resident Evil", p31="Q7889"),       # video game, wrong year too
        "Q_NEW": _ent(2026, label="Resident Evil"),                     # the real film
    }

    def fake_search(title):
        return wrong_hits  # wbsearchentities: same buried result whatever the query text

    def fake_fulltext(query):
        if query == "Resident Evil film":
            return [{"id": "Q_NEW", "description": "2026 film directed by Zach Cregger"}]
        return []  # plain "Resident Evil", and the "(YYYY film)" retries, all empty (real behaviour)

    monkeypatch.setattr(enrich_mod, "_wikidata_search", fake_search)
    monkeypatch.setattr(enrich_mod, "_wikidata_fulltext_search", fake_fulltext)
    monkeypatch.setattr(enrich_mod, "_wikidata_entities",
                        lambda ids, props="labels|claims": {i: entities[i] for i in ids if i in entities})

    assert enrich_mod._find_film_qid("Resident Evil", {2025, 2026}) == "Q_NEW"


def test_new_release_ranked_past_the_wbsearchentities_limit_is_found_via_fulltext(monkeypatch):
    """"Digger"/"The Odyssey"-shape: wbsearchentities' first 6 hits are unrelated (a given name, an
    excavator, older films/games); the accepted-year film ranks 7th+ there but 1st in a full-text
    search — real behaviour for both real titles."""
    wrong_hits = [{"id": "Q_NAME", "description": "given name"},
                  {"id": "Q_TOOL", "description": "type of construction equipment"}]
    entities = {
        "Q_NAME": _ent(0, label="Digger", p31="Q202444"),
        "Q_TOOL": _ent(0, label="digger", p31="Q1183543"),
        "Q_NEW": _ent(2026, label="Digger"),
    }

    def fake_search(title):
        return wrong_hits

    def fake_fulltext(query):
        if query == "Digger":
            return [{"id": "Q_NEW", "description": "2026 film directed by Alejandro G. Iñárritu"}]
        return []

    monkeypatch.setattr(enrich_mod, "_wikidata_search", fake_search)
    monkeypatch.setattr(enrich_mod, "_wikidata_fulltext_search", fake_fulltext)
    monkeypatch.setattr(enrich_mod, "_wikidata_entities",
                        lambda ids, props="labels|claims": {i: entities[i] for i in ids if i in entities})

    assert enrich_mod._find_film_qid("Digger", {2025, 2026}) == "Q_NEW"


def test_wbsearchentities_alone_still_matches_a_well_known_current_release(monkeypatch):
    """The merge must never break the easy case: a film that wbsearchentities already finds directly
    (e.g. "Coyote vs. Acme", the one film in the sample set that kept its match through the
    regression) needs no full-text help at all."""
    hit = [{"id": "Q_COYOTE", "description": "2026 American film directed by Dave Green"}]
    entities = {"Q_COYOTE": _ent(2026, label="Coyote vs. Acme")}

    monkeypatch.setattr(enrich_mod, "_wikidata_search", lambda title: hit)
    monkeypatch.setattr(enrich_mod, "_wikidata_fulltext_search",
                        lambda title: pytest.fail("fulltext should not be needed when wbsearch already lands"))
    monkeypatch.setattr(enrich_mod, "_wikidata_entities",
                        lambda ids, props="labels|claims": {i: entities[i] for i in ids if i in entities})

    assert enrich_mod._find_film_qid("Coyote VS Acme", {2025, 2026}) == "Q_COYOTE"


# ---------------------------------------------------------------------------------------------
# Prefer an exact title match once merging makes more than one accepted-year candidate possible.

def test_prefers_exact_title_match_over_a_same_year_partial_match():
    hits = [{"id": "Q_PARTIAL", "description": "film"}, {"id": "Q_EXACT", "description": "film"}]
    entities = {
        "Q_PARTIAL": _ent(2026, label="The Odyssey Part One"),
        "Q_EXACT": _ent(2026, label="The Odyssey"),
    }
    real = enrich_mod._wikidata_entities
    enrich_mod._wikidata_entities = lambda ids, props="labels|claims": {i: entities[i] for i in ids if i in entities}
    try:
        # Without a title to prefer, hit order decides (unchanged pre-fix behaviour).
        assert enrich_mod._best_film_in_hits(hits, {2026}) == "Q_PARTIAL"
        # With one, the exact label match wins even though it is not first in hit order.
        assert enrich_mod._best_film_in_hits(hits, {2026}, want_title="The Odyssey") == "Q_EXACT"
    finally:
        enrich_mod._wikidata_entities = real


# ---------------------------------------------------------------------------------------------
# A themed re-release listed under a promotional suffix ("Avengers Endgame: Encore") — no search
# finds anything under the full listing title at all; the search query is truncated word by word
# (the label comparison itself stays a prefix-of-the-full-title check, never loosened further).

def test_rerelease_with_promotional_suffix_is_found_by_truncating_the_search_query(monkeypatch):
    entities = {"Q_CLASSIC": _ent(2019, label="Avengers: Endgame", runtime=181, sitelinks=90, lang_qid="Q1860")}

    def fake_search(query):
        return []  # wbsearchentities: real behaviour — zero hits for every variant tried

    def fake_fulltext(query):
        # real behaviour: the full promotional title (and dropping just "Encore") finds nothing;
        # dropping "Encore" AND the trailing colon fragment does.
        if query == "Avengers Endgame:":
            return [{"id": "Q_CLASSIC", "description": "2019 Marvel Studios film"}]
        return []

    monkeypatch.setattr(enrich_mod, "_wikidata_search", fake_search)
    monkeypatch.setattr(enrich_mod, "_wikidata_fulltext_search", fake_fulltext)
    monkeypatch.setattr(enrich_mod, "_wikidata_entities",
                        lambda ids, props="labels|claims": {i: entities[i] for i in ids if i in entities})

    qid = enrich_mod._find_rerelease_qid("Avengers Endgame: Encore", runtime=181, lang="English")
    assert qid == "Q_CLASSIC"


def test_rerelease_falls_back_to_the_enwiki_sitelink_when_the_item_has_no_english_label(monkeypatch):
    """Live discovery (2026-09-30): Q23781155 — "Avengers: Endgame" itself — carries no English *label*
    at all on Wikidata despite 90 sitelinks and an enwiki article titled exactly "Avengers: Endgame";
    the label and sitelink genuinely disagree. Confirmed against the real API (not asserted here, since
    this suite never touches the network) with a plain wbgetentities call for Q23781155: labels == {}."""
    entities = {"Q_CLASSIC": {
        "labels": {},  # no "en" entry at all — only the enwiki sitelink carries the English title
        "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
            "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2019-01-01T00:00:00Z"}}}}],
            "P2047": [{"mainsnak": {"datavalue": {"value": {"amount": "+181"}}}}],
            "P364": [{"mainsnak": {"datavalue": {"value": {"id": "Q1860"}}}}],
        },
        "sitelinks": {**{f"s{i}": {} for i in range(89)}, "enwiki": {"title": "Avengers: Endgame"}},
    }}

    monkeypatch.setattr(enrich_mod, "_wikidata_search", lambda query: [])

    def fake_fulltext(query):
        if query == "Avengers Endgame:":
            return [{"id": "Q_CLASSIC", "description": "2019 Marvel Studios film"}]
        return []

    monkeypatch.setattr(enrich_mod, "_wikidata_fulltext_search", fake_fulltext)
    monkeypatch.setattr(enrich_mod, "_wikidata_entities",
                        lambda ids, props="labels|claims": {i: entities[i] for i in ids if i in entities})

    qid = enrich_mod._find_rerelease_qid("Avengers Endgame: Encore", runtime=186, lang="English")
    assert qid == "Q_CLASSIC"


def test_rerelease_truncation_never_accepts_a_label_that_is_not_a_prefix_of_the_full_title(monkeypatch):
    """The truncated *query* only ever widens what is searched for, never what is accepted: a hit whose
    label is not a leading prefix of the full listing title is still rejected, guards unchanged."""
    entities = {"Q_UNRELATED": _ent(2005, label="Batman Begins", runtime=140, sitelinks=90, lang_qid="Q1860")}

    monkeypatch.setattr(enrich_mod, "_wikidata_search", lambda query: [])

    def fake_fulltext(query):
        return [{"id": "Q_UNRELATED", "description": "2005 film"}]  # some hit, wrong film, every query

    monkeypatch.setattr(enrich_mod, "_wikidata_fulltext_search", fake_fulltext)
    monkeypatch.setattr(enrich_mod, "_wikidata_entities",
                        lambda ids, props="labels|claims": {i: entities[i] for i in ids if i in entities})

    assert enrich_mod._find_rerelease_qid("Avengers Endgame: Encore", runtime=181, lang="English") is None


# ---------------------------------------------------------------------------------------------
# LOOKUP_VERSION bump: a "not found" cached under an older version is retried, capped per run.

def test_not_found_version_retry_is_capped_and_oldest_checked_first(monkeypatch, tmp_path):
    monkeypatch.setattr(enrich_mod, "NOT_FOUND_RELOOKUP_CAP", 2)
    cache_path = tmp_path / "films_cache.json"
    now = datetime.now(timezone.utc)
    fids = ["film-a", "film-b", "film-c", "film-d"]
    # staggered ids_checked_at, all *fresh* (well within NOT_FOUND_TTL) so the only reason any of
    # them would be retried at all is the version-cap path this test is about; film-a is the
    # oldest-checked of the four, film-d the most recent.
    cache = {
        fid: {"ids": {}, "ids_status": "not_found", "lookup_v": 1,
              "ids_checked_at": (now - timedelta(minutes=i)).isoformat()}
        for i, fid in enumerate(reversed(fids))  # film-a gets the largest offset -> oldest
    }
    cache_path.write_text(json.dumps(cache), encoding="utf-8")

    attempted = []

    def fake_wikidata_ids(title, accepted_years):
        attempted.append(title)
        return {}

    monkeypatch.setattr(enrich_mod, "_wikidata_ids", fake_wikidata_ids)
    # a "not found" from _wikidata_ids also tries the re-release fallback (enrich()'s own logic);
    # stub it too so this test is only ever exercising the version-cap gate, nothing past it.
    monkeypatch.setattr(enrich_mod, "_rerelease_ids", lambda title, runtime, lang: {})
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda t: None)

    data = {"films": {fid: {"title": fid} for fid in fids}}
    enrich(data, cache_path=str(cache_path))

    assert len(attempted) == 2                      # capped at NOT_FOUND_RELOOKUP_CAP
    assert set(attempted) == {"film-a", "film-b"}    # the two oldest-checked, not an arbitrary two


def test_not_found_version_retry_cap_does_not_starve_ttl_expired_entries(monkeypatch, tmp_path):
    """A genuinely TTL-expired not_found (independent of the version bump) is still retried even when
    the version-bump cap for *other* films is already exhausted — the cap only bounds the version-bump
    flood, not the pre-existing, already-time-throttled TTL retry path."""
    monkeypatch.setattr(enrich_mod, "NOT_FOUND_RELOOKUP_CAP", 0)
    cache_path = tmp_path / "films_cache.json"
    stale_ttl = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    cache_path.write_text(json.dumps({
        "ttl-expired": {"ids": {}, "ids_status": "not_found", "lookup_v": enrich_mod.LOOKUP_VERSION,
                         "ids_checked_at": stale_ttl},
    }), encoding="utf-8")

    attempted = []
    monkeypatch.setattr(enrich_mod, "_wikidata_ids", lambda title, accepted_years: (attempted.append(title), {})[1])
    monkeypatch.setattr(enrich_mod, "_rerelease_ids", lambda title, runtime, lang: {})
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda t: None)

    enrich({"films": {"ttl-expired": {"title": "TTL Expired"}}}, cache_path=str(cache_path))
    assert attempted == ["TTL Expired"]
