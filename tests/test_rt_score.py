"""Rotten Tomatoes renamed the Tomatometer's number (found 2026-11-19): the scorecard JSON now carries
"scorePercent": "88%" where it had "score": "88", so every film read since then had critics None beside a full
review count, every new verdict fell to the «not enough ratings» template, and I Play Rocky (160 reviews, 88%)
said we had found nothing."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import enrich as enrich_mod  # noqa: E402
from enrich import enrich  # noqa: E402


class _Resp:
    status_code = 200

    def __init__(self, text):
        self.text = text


def _page(critics, audience):
    card = {"criticsScore": critics, "audienceScore": audience}
    return (f'<html><script id="media-scorecard-json" type="application/json">{json.dumps(card)}</script>'
            '<div id="critics-consensus"><h2>Critics Consensus</h2><p>A <em>good</em> one.</p></div></html>')


def test_the_new_score_percent_is_read(monkeypatch):
    html = _page({"likedCount": 141, "notLikedCount": 19, "reviewCount": 160, "scorePercent": "88%", "title": "Tomatometer"},
                 {"scorePercent": "98%", "title": "Popcornmeter"})
    monkeypatch.setattr(enrich_mod, "_polite_get", lambda url, **k: _Resp(html))
    r = enrich_mod._rt_ratings("i_play_rocky")
    assert (r["critics"], r["critics_count"], r["audience"]) == (88, 160, 98)
    assert r["consensus"] == "A good one."


def test_the_old_score_still_reads(monkeypatch):
    html = _page({"score": "91", "reviewCount": 37}, {"score": "80"})
    monkeypatch.setattr(enrich_mod, "_polite_get", lambda url, **k: _Resp(html))
    r = enrich_mod._rt_ratings("x")
    assert (r["critics"], r["critics_count"], r["audience"]) == (91, 37, 80)


def test_a_count_without_a_score_falls_back_to_liked_over_rated(monkeypatch):
    html = _page({"likedCount": 3, "notLikedCount": 1, "reviewCount": 4}, {})
    monkeypatch.setattr(enrich_mod, "_polite_get", lambda url, **k: _Resp(html))
    assert enrich_mod._rt_ratings("x")["critics"] == 75


def test_no_reviews_is_no_score(monkeypatch):
    html = _page({"reviewCount": 0, "likedCount": 0, "notLikedCount": 0, "scorePercent": ""}, {})
    monkeypatch.setattr(enrich_mod, "_polite_get", lambda url, **k: _Resp(html))
    r = enrich_mod._rt_ratings("x")
    assert r["critics"] is None and r["audience"] is None


def test_ratings_read_under_the_old_name_are_fetched_again_at_once(monkeypatch, tmp_path):
    """A cached rating with reviews but no score is the old parser's miss: it is read again on the next run
    instead of waiting out RATINGS_TTL (3 days), so the verdicts follow in the same run."""
    fresh = datetime.now(timezone.utc).isoformat()
    cache = tmp_path / "c.json"
    entry = {"ids": {"qid": "Q1", "rt_id": "i_play_rocky", "year": 2026}, "ids_status": "found", "ids_checked_at": fresh,
             "lookup_v": enrich_mod.LOOKUP_VERSION, "ratings_at": fresh,
             "ratings": {"critics": None, "critics_count": 150, "audience": None, "consensus": "c", "url": "u"}}
    cache.write_text(json.dumps({"i-play-rocky": entry}), encoding="utf-8")
    seen = []

    def fake_rt(rt_id, expected_year=None):
        seen.append(rt_id)
        return {"critics": 88, "critics_count": 160, "audience": 98, "consensus": "c", "url": "u"}
    monkeypatch.setattr(enrich_mod, "_rt_ratings", fake_rt)
    monkeypatch.setattr(enrich_mod, "_wikipedia_summary", lambda t: None)
    monkeypatch.setattr(enrich_mod, "_wikidata_entities", lambda ids, props="labels|claims": {})
    data = {"films": {"i-play-rocky": {"title": "I Play Rocky", "runtime": 128, "lang": "English"}}}
    film = enrich(data, cache_path=str(cache))["films"]["i-play-rocky"]
    assert seen == ["i_play_rocky"] and film["rt"]["critics"] == 88
