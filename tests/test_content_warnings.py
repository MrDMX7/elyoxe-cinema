"""steps/content_warnings.py (owner 2026-10-20): Does the Dog Die? community ratings → film["content"], the film page's
«للعائلة» and the ask facts. Never a network call here."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))
from steps import content_warnings as cw  # noqa: E402


def stat(tid, y, n):
    return {"TopicId": tid, "yesSum": y, "noSum": n}


def test_a_topic_counts_only_with_enough_votes_and_a_clear_majority():
    assert cw.verdict(stat(1, 3, 1)) is True
    assert cw.verdict(stat(1, 2, 0)) is None          # too few votes
    assert cw.verdict(stat(1, 5, 4)) is None          # no clear majority
    assert cw.verdict(stat(1, 0, 6)) is False


def test_summary_keeps_only_our_topics_and_the_credits_answer():
    media = {"item": {"id": 7, "numRatings": 99},
             "topicItemStats": [stat(188, 9, 0), stat(197, 1, 8), stat(999, 9, 0), stat(cw.CREDITS, 6, 0), stat(158, 4, 1)]}
    s = cw.summarize(media)
    assert s["flags"] == ["blood", "child_dies"] and s["credits"] is True and s["votes"] == 99
    assert s["url"].endswith("/media/7")


def test_a_film_matches_by_imdb_id_first_then_exact_title_and_year():
    items = [{"id": 1, "name": "It Ends", "releaseYear": "2019", "imdbId": "tt1"},
             {"id": 2, "name": "It Ends", "releaseYear": "2026", "imdbId": "tt2"}]
    assert cw._match(items, {"imdb": {"id": "tt2"}, "title": "x"})["id"] == 2
    assert cw._match(items, {"title": "It Ends", "year": 2026})["id"] == 2
    assert cw._match(items, {"title": "It Ends", "year": 2010}) is None


def test_offline_and_cached_runs_make_no_call(tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    assert cw.run({}, {"offline": True}) == {"skipped": "offline"}
    import datetime as dt
    (tmp_path / "dtdd.json").write_text(json.dumps({"f1": {"at": dt.date.today().isoformat(),
                                                           "content": {"flags": ["blood"], "credits": False, "votes": 5, "url": None}}}))
    data = {"films": {"f1": {"title": "F"}}, "shows": [{"film": "f1"}]}
    r = cw.run(data, {"data_dir": str(tmp_path)})
    assert r["api_calls"] == 0 and data["films"]["f1"]["content"]["flags"] == ["blood"]


def test_the_family_section_names_the_original_cut_and_credits_the_source():
    import build_app
    app = build_app.App.__new__(build_app.App)
    h = app.family({"content": {"flags": ["blood", "jump_scares", "child_dies"], "credits": True, "url": "https://www.doesthedogdie.com/media/7"}})
    assert "فيه مشهد بعد النهاية" in h and "دم وعنف" in h and "النسخة الأصلية" in h
    assert 'href="https://www.doesthedogdie.com/media/7"' in h and "Does the Dog Die" in h
    assert h.index("<details") < h.index("يموت طفل")                  # a death sits behind a tap
    assert app.family({}) == "" and app.family({"content": {"flags": [], "credits": None}}) == ""
