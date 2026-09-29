"""filmintel.py, omdb.py and pages/intel.py (UNIT r3-film) — never a real network call (conftest's guard
fails the test at teardown on any attempt, even a caught one), so every path that could reach out is
monkeypatched with a fake client/fetcher, exactly like the rest of the suite tests verdicts.py-shaped code."""
import json

import filmintel
import omdb
import pages.intel as intel_page


class FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def create(self, **kw):
        text = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return FakeMsg(text)


class FakeClient:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


FILM = {"title": "Interstellar", "title_ar": "بين النجوم", "year": 2014, "genres": ["drama"],
        "runtime": 169,
        "rt": {"critics": 73, "critics_count": 373, "audience": 87,
               "consensus": "A visually stunning, emotionally engaging sci-fi epic."},
        "wikidata": {"qid": "Q120737"}}

GOOD = json.dumps({
    "reasons": [{"text": "نقاد Rotten Tomatoes عطوه 73%، بس الجمهور حبّه 87%.", "pos": True},
                {"text": "مدته طويلة على وايد ناس.", "pos": False}],
    "audience": [{"text": "الجمهور يقول تجربة بصرية قوية بالمجمل.", "source": "Rotten Tomatoes"}],
    "fun_fact": {"text": "صوّر الفيلم بمواقع حقيقية للمشاهد الأرضية.", "source": "Wikipedia"},
    "ending": None, "qa": [],
})

BAD_DIALECT = json.dumps({
    "reasons": [{"text": "وش رايك بهذا الفيلم؟ يستاهل وايد.", "pos": True},
                {"text": "مدته طويلة على وايد ناس.", "pos": False}],
    "audience": [], "fun_fact": None, "ending": None, "qa": [],
})


def test_has_intel_basis_needs_rt_or_wikidata():
    assert filmintel.has_intel_basis(FILM)
    assert not filmintel.has_intel_basis({"title": "x"})


def test_needs_generate_new_vs_skip_vs_stable():
    assert filmintel.needs_generate(None, FILM) is True
    assert filmintel.needs_generate({"by": "skip"}, {"title": "x"}) is False    # still no basis
    assert filmintel.needs_generate({"by": "skip"}, FILM) is True              # basis appeared
    assert filmintel.needs_generate({"by": "claude"}, FILM) is False           # stable, never auto-rewritten
    assert filmintel.needs_generate({"by": "hand"}, FILM) is False             # hand-edited, never touched


def test_validate_rejects_too_few_reasons():
    assert filmintel._validate({"reasons": [{"text": "x", "pos": True}], "audience": [], "fun_fact": None,
                                "ending": None, "qa": []}, None, []) is not None


def test_validate_rejects_ending_without_plot():
    parsed = {"reasons": [{"text": "a", "pos": True}, {"text": "b", "pos": False}],
              "audience": [], "fun_fact": None, "ending": "spoiler", "qa": []}
    assert filmintel._validate(parsed, None, []) is not None


def test_validate_requires_ending_and_qa_with_plot():
    parsed = {"reasons": [{"text": "a", "pos": True}, {"text": "b", "pos": False}],
              "audience": [], "fun_fact": None, "ending": None, "qa": []}
    assert filmintel._validate(parsed, "a long plot " * 20, []) is not None


def test_validate_rejects_reddit_echo():
    parsed = {"reasons": [{"text": "a", "pos": True}, {"text": "b", "pos": False}],
              "audience": [{"text": "this movie was absolutely incredible and life changing", "source": "Reddit"}],
              "fun_fact": None, "ending": None, "qa": []}
    reddit = ["this movie was absolutely incredible and life changing"]
    assert filmintel._validate(parsed, None, reddit) is not None


def test_validate_catches_banned_dialect_word():
    parsed = json.loads(BAD_DIALECT)
    assert filmintel._validate(parsed, None, []) is not None


def test_validate_accepts_clean_payload():
    assert filmintel._validate(json.loads(GOOD), None, []) is None


def test_generate_one_retries_past_a_dialect_violation():
    client = FakeClient([BAD_DIALECT, GOOD])
    out = filmintel._generate_one(client, "interstellar", FILM, None, [])
    assert out["by"] == "claude" and out["fun_fact"]["source"] == "Wikipedia"
    assert client.messages.calls == 2


def test_generate_one_raises_after_max_attempts_all_bad():
    client = FakeClient([BAD_DIALECT])
    try:
        filmintel._generate_one(client, "interstellar", FILM, None, [])
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    assert client.messages.calls == filmintel.MAX_ATTEMPTS


def test_write_missing_writes_skip_marker_with_no_network_when_no_basis(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    data = {"films": {"nobody": {"title": "Nobody Knows"}}}
    results = filmintel.write_missing(data)
    assert results == {}
    written = json.loads((tmp_path / "nobody.json").read_text(encoding="utf-8"))
    assert written["by"] == "skip"


def test_write_missing_generates_with_mocked_client_and_no_plot(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "wikipedia_plot", lambda qid: None)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])
    fake = FakeClient([GOOD])
    monkeypatch.setattr("verdicts._client", lambda: fake)
    data = {"films": {"interstellar": dict(FILM)}}
    results = filmintel.write_missing(data)
    assert "interstellar" in results
    written = json.loads((tmp_path / "interstellar.json").read_text(encoding="utf-8"))
    assert written["by"] == "claude" and written["has_plot"] is False and written["ending"] is None


def test_write_missing_respects_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "wikipedia_plot", lambda qid: None)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])
    fake = FakeClient([GOOD])
    monkeypatch.setattr("verdicts._client", lambda: fake)
    films = {f"film-{i}": dict(FILM) for i in range(5)}
    results = filmintel.write_missing({"films": films}, cap=2)
    assert len(results) == 2


def test_write_missing_isolates_a_bad_film(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "wikipedia_plot", lambda qid: None)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])

    def boom():
        raise RuntimeError("api down")

    monkeypatch.setattr("verdicts._client", boom)
    data = {"films": {"interstellar": dict(FILM)}}
    results = filmintel.write_missing(data)
    assert results == {}
    assert not (tmp_path / "interstellar.json").exists()


# --------------------------------------------------------------------------------------------------- omdb.py

def test_fill_scores_is_a_noop_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OMDB_KEY", raising=False)
    monkeypatch.setattr(omdb, "_key", lambda: None)
    data = {"films": {"x": {"imdb": {"id": "tt1234567"}}}}
    report = omdb.fill_scores(data, str(tmp_path))
    assert report.get("skipped")
    assert "imdb_score" not in data["films"]["x"]


def test_fill_scores_fetches_and_caches_with_a_key(monkeypatch, tmp_path):
    monkeypatch.setattr(omdb, "_key", lambda: "fake-key")
    calls = {"n": 0}

    def fake_fetch(imdb_id, key):
        calls["n"] += 1
        return 8.6

    monkeypatch.setattr(omdb, "_fetch", fake_fetch)
    data = {"films": {"x": {"imdb": {"id": "tt1234567"}}}}
    omdb.fill_scores(data, str(tmp_path))
    assert data["films"]["x"]["imdb_score"] == 8.6
    assert calls["n"] == 1
    # second run within the TTL reads the cache, no second fetch
    data2 = {"films": {"x": {"imdb": {"id": "tt1234567"}}}}
    omdb.fill_scores(data2, str(tmp_path))
    assert data2["films"]["x"]["imdb_score"] == 8.6
    assert calls["n"] == 1


def test_fill_scores_skips_films_with_no_imdb_id(monkeypatch, tmp_path):
    monkeypatch.setattr(omdb, "_key", lambda: "fake-key")
    monkeypatch.setattr(omdb, "_fetch", lambda imdb_id, key: 9.0)
    data = {"films": {"x": {"imdb": {"id": None}}}}
    omdb.fill_scores(data, str(tmp_path))
    assert "imdb_score" not in data["films"]["x"]


# ------------------------------------------------------------------------------------------- pages/intel.py

class FakeSite:
    def __init__(self, films):
        self.films = films


def test_film_info_slot_renders_nothing_with_no_intel():
    site = FakeSite({"x": {"title": "x"}})
    assert intel_page._film_info(site, "ar", "x") == ""


def test_film_info_slot_hides_spoilers_behind_no_answer_without_a_plot():
    film = dict(FILM)
    film["intel"] = {"reasons": [{"text": "سبب", "pos": True}], "audience": [], "fun_fact": None,
                      "ending": None, "qa": [], "has_plot": False}
    site = FakeSite({"x": film})
    html = intel_page._film_info(site, "ar", "x")
    assert "اشرح النهاية" in html and "أسئلة عن الفيلم" in html
    assert html.count(intel_page.L["no_answer"][0]) == 2   # both spoiler sections fall back


def test_film_info_slot_shows_ending_and_qa_with_a_plot():
    film = dict(FILM)
    film["intel"] = {"reasons": [{"text": "سبب", "pos": True}], "audience": [], "fun_fact": None,
                      "ending": "الفيلم ينتهي بعودة البطل لأهله بعد رحلة بالفضاء.",
                      "qa": [{"q": "ليش رجع؟", "a": "لأنه لقى طريقة عبر الثقب الدودي."}],
                      "has_plot": True}
    site = FakeSite({"x": film})
    html = intel_page._film_info(site, "ar", "x")
    assert "عودة البطل" in html and "الثقب الدودي" in html
    assert intel_page.L["no_answer"][0] not in html


def test_film_info_slot_scores_row_includes_imdb_only_when_present():
    film = dict(FILM)
    site = FakeSite({"x": film})
    assert "IMDb" not in intel_page._film_info(site, "ar", "x")
    film["imdb_score"] = 8.6
    assert "IMDb" in intel_page._film_info(site, "ar", "x")
