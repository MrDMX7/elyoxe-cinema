"""filmintel.py, omdb.py and pages/intel.py (UNIT r3-film, fix round) — never a real network call (conftest's
guard fails the test at teardown on any attempt, even a caught one), so every path that could reach out is
monkeypatched with a fake client/fetcher, exactly like the rest of the suite tests verdicts.py-shaped code.
One deliberate exception (round 3 QA): test_fill_scores_real_omdb_call_heart_of_the_beast opts into the
`live_network` fixture to prove the real OMDb integration, and skips itself when no key is configured."""
import json
import os
from datetime import date, timedelta

import pytest

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

OPEN_GOOD = json.dumps({
    "reasons": [{"text": "نقاد Rotten Tomatoes عطوه 73%، بس الجمهور حبّه 87%.", "pos": True},
                {"text": "مدته طويلة على وايد ناس.", "pos": False}],
    "audience": [{"text": "الجمهور يقول تجربة بصرية قوية بالمجمل.", "source": "Rotten Tomatoes"}],
    "fun_fact": None,
    "consensus_ar": "النقاد يشوفونه ملحمة بصرية مؤثرة.",
})

OPEN_BAD_DIALECT = json.dumps({
    "reasons": [{"text": "وش رايك بهذا الفيلم؟ يستاهل وايد.", "pos": True},
                {"text": "مدته طويلة على وايد ناس.", "pos": False}],
    "audience": [], "fun_fact": None, "consensus_ar": "النقاد يشوفونه ملحمة بصرية مؤثرة.",
})

SPOILER_GOOD = json.dumps({
    "ending": "البطل يرجع لأهله بعد رحلة بالفضاء.",
    "qa": [{"q": "ليش رجع؟", "a": "لأنه لقى طريقة عبر الثقب الدودي."},
           {"q": "منو ساعده؟", "a": "TARS الروبوت."},
           {"q": "وين انتهت الرحلة؟", "a": "بمحطة فضائية قريبة من زحل."},
           {"q": "شو صار لابنته؟", "a": "كبرت وصارت مسؤولة عن المحطة."}],
})

SPOILER_NO_ENDING = json.dumps({"ending": None, "qa": []})


def test_has_intel_basis_needs_rt_or_wikidata():
    assert filmintel.has_intel_basis(FILM)
    assert not filmintel.has_intel_basis({"title": "x"})


def test_is_released_true_with_no_release_field():
    assert filmintel.is_released(FILM) is True


def test_is_released_false_for_a_future_release_date():
    future = (date.today() + timedelta(days=10)).isoformat()
    assert filmintel.is_released({**FILM, "released": future}) is False


def test_is_released_true_for_a_past_release_date():
    past = (date.today() - timedelta(days=10)).isoformat()
    assert filmintel.is_released({**FILM, "released": past}) is True


def test_needs_generate_new_vs_skip_vs_stable():
    assert filmintel.needs_generate(None, FILM) is True
    assert filmintel.needs_generate({"by": "skip"}, {"title": "x"}) is False    # still no basis
    assert filmintel.needs_generate({"by": "skip"}, FILM) is True              # basis appeared
    assert filmintel.needs_generate({"by": "claude", "has_plot": True}, FILM) is False   # stable, done
    assert filmintel.needs_generate({"by": "hand"}, FILM) is False             # hand-edited, never touched


def test_needs_generate_retries_claude_record_with_no_ending_yet():
    # a "claude" record written before a plot existed keeps trying for the spoiler half (review, Important #4)
    assert filmintel.needs_generate({"by": "claude", "has_plot": False}, FILM) is True


def test_needs_generate_respects_backoff_window():
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert filmintel.needs_generate({"by": "failed", "next_check": tomorrow}, FILM) is False
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert filmintel.needs_generate({"by": "failed", "next_check": yesterday}, FILM) is True


def test_validate_open_rejects_too_few_reasons():
    parsed = {"reasons": [{"text": "x", "pos": True}], "audience": [], "fun_fact": None, "consensus_ar": None}
    assert filmintel._validate_open(parsed, [], False) is not None


def test_validate_open_requires_consensus_ar_when_consensus_given():
    parsed = {"reasons": [{"text": "a", "pos": True}, {"text": "b", "pos": False}],
              "audience": [], "fun_fact": None, "consensus_ar": None}
    assert filmintel._validate_open(parsed, [], True) is not None


def test_validate_open_rejects_consensus_ar_when_none_given():
    parsed = {"reasons": [{"text": "a", "pos": True}, {"text": "b", "pos": False}],
              "audience": [], "fun_fact": None, "consensus_ar": "ملخص غير مطلوب"}
    assert filmintel._validate_open(parsed, [], False) is not None


def test_validate_open_rejects_reddit_source_when_no_reddit_given():
    parsed = {"reasons": [{"text": "a", "pos": True}, {"text": "b", "pos": False}],
              "audience": [{"text": "رأي غير مرتبط بأي عنوان", "source": "Reddit"}],
              "fun_fact": None, "consensus_ar": None}
    assert filmintel._validate_open(parsed, [], False) is not None


def test_validate_open_rejects_reddit_echo():
    parsed = {"reasons": [{"text": "a", "pos": True}, {"text": "b", "pos": False}],
              "audience": [{"text": "this movie was absolutely incredible and life changing", "source": "Reddit"}],
              "fun_fact": None, "consensus_ar": None}
    reddit = ["this movie was absolutely incredible and life changing"]
    assert filmintel._validate_open(parsed, reddit, False) is not None


def test_validate_open_catches_banned_dialect_word():
    assert filmintel._validate_open(json.loads(OPEN_BAD_DIALECT), [], True) is not None


def test_validate_open_accepts_clean_payload():
    assert filmintel._validate_open(json.loads(OPEN_GOOD), [], True) is None


def test_validate_spoiler_allows_null_ending_when_text_has_none():
    # round-1 review, Critical #1: a plot with no narrated ending must not be forced to invent one
    assert filmintel._validate_spoiler({"ending": None, "qa": []}, "a short premise " * 20) is None


def test_validate_spoiler_rejects_qa_without_an_ending():
    parsed = {"ending": None, "qa": [{"q": "x", "a": "y"}]}
    assert filmintel._validate_spoiler(parsed, "a long plot " * 20) is not None


def test_validate_spoiler_requires_qa_count_with_a_real_ending():
    parsed = {"ending": "شرح حقيقي", "qa": []}
    assert filmintel._validate_spoiler(parsed, "a long plot " * 20) is not None


def test_validate_spoiler_accepts_clean_payload():
    assert filmintel._validate_spoiler(json.loads(SPOILER_GOOD), "a long plot " * 20) is None


def test_generate_one_retries_past_a_dialect_violation():
    client = FakeClient([OPEN_BAD_DIALECT, OPEN_GOOD])
    out = filmintel._generate_one(client, "interstellar", FILM, None, [])
    assert out["by"] == "claude" and out["has_plot"] is False
    assert client.messages.calls == 2


def test_generate_one_raises_after_max_attempts_all_bad():
    client = FakeClient([OPEN_BAD_DIALECT])
    try:
        filmintel._generate_one(client, "interstellar", FILM, None, [])
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    assert client.messages.calls == filmintel.MAX_ATTEMPTS


def test_generate_one_with_a_plot_makes_a_second_call_for_the_spoiler_half():
    client = FakeClient([OPEN_GOOD, SPOILER_GOOD])
    out = filmintel._generate_one(client, "interstellar", FILM, "a long plot " * 30, [])
    assert out["has_plot"] is True and out["ending"] and len(out["qa"]) == 4
    assert client.messages.calls == 2


def test_generate_one_reuses_open_half_from_an_existing_claude_record():
    existing = {"by": "claude", "reasons": [{"text": "قديم", "pos": True}], "audience": [],
                "fun_fact": None, "consensus_ar": None, "has_plot": False}
    client = FakeClient([SPOILER_GOOD])   # only the spoiler call — the open half must not be re-requested
    out = filmintel._generate_one(client, "interstellar", FILM, "a long plot " * 30, [], existing=existing)
    assert out["reasons"] == existing["reasons"]
    assert client.messages.calls == 1


def test_generate_one_a_plot_with_no_real_ending_stays_has_plot_false():
    client = FakeClient([OPEN_GOOD, SPOILER_NO_ENDING])
    out = filmintel._generate_one(client, "interstellar", FILM, "a short premise " * 20, [])
    assert out["has_plot"] is False and out["ending"] is None and out["qa"] == []
    assert "next_check" in out


def test_write_missing_writes_skip_marker_with_no_network_when_no_basis(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    data = {"films": {"nobody": {"title": "Nobody Knows"}}}
    results = filmintel.write_missing(data)
    assert results == {}
    written = json.loads((tmp_path / "nobody.json").read_text(encoding="utf-8"))
    assert written["by"] == "skip" and "next_check" in written


def test_write_missing_generates_with_mocked_client_and_no_plot(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "wikipedia_plot", lambda qid: None)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])
    fake = FakeClient([OPEN_GOOD])
    monkeypatch.setattr("verdicts._client", lambda: fake)
    data = {"films": {"interstellar": dict(FILM)}}
    results = filmintel.write_missing(data)
    assert "interstellar" in results
    written = json.loads((tmp_path / "interstellar.json").read_text(encoding="utf-8"))
    assert written["by"] == "claude" and written["has_plot"] is False and written["ending"] is None


def test_write_missing_never_fetches_a_plot_before_release(tmp_path, monkeypatch):
    future = (date.today() + timedelta(days=10)).isoformat()
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)

    def boom(qid):
        raise AssertionError("wikipedia_plot must not be called before release")

    monkeypatch.setattr(filmintel, "wikipedia_plot", boom)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])
    fake = FakeClient([OPEN_GOOD])
    monkeypatch.setattr("verdicts._client", lambda: fake)
    data = {"films": {"interstellar": {**FILM, "released": future}}}
    results = filmintel.write_missing(data)
    assert results["interstellar"]["has_plot"] is False


def test_write_missing_respects_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "wikipedia_plot", lambda qid: None)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])
    fake = FakeClient([OPEN_GOOD])
    monkeypatch.setattr("verdicts._client", lambda: fake)
    films = {f"film-{i}": dict(FILM) for i in range(5)}
    results = filmintel.write_missing({"films": films}, cap=2)
    assert len(results) == 2


def test_write_missing_records_a_backed_off_failure_marker_instead_of_nothing(tmp_path, monkeypatch):
    # review, Important #5: a bad film must not silently stay retriable every run forever, eating the cap
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "wikipedia_plot", lambda qid: None)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])

    def boom():
        raise RuntimeError("api down")

    monkeypatch.setattr("verdicts._client", boom)
    data = {"films": {"interstellar": dict(FILM)}}
    results = filmintel.write_missing(data)
    assert results == {}
    written = json.loads((tmp_path / "interstellar.json").read_text(encoding="utf-8"))
    assert written["by"] == "failed" and "next_check" in written


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


def test_fill_scores_ttl_is_exactly_3_days(monkeypatch, tmp_path):
    """Round 3 QA: OMDb free tier is 1000 req/day, so a cached entry is only re-fetched once it is older
    than 3 days -- neither shorter (which would waste the quota) nor the old 30-day value (too stale)."""
    assert omdb.OMDB_TTL == 3 * 24 * 3600

    monkeypatch.setattr(omdb, "_key", lambda: "fake-key")
    calls = {"n": 0}
    monkeypatch.setattr(omdb, "_fetch", lambda imdb_id, key: (calls.__setitem__("n", calls["n"] + 1), 7.5)[1])

    data = {"films": {"x": {"imdb": {"id": "tt7526136"}}}}
    omdb.fill_scores(data, str(tmp_path))
    assert calls["n"] == 1

    # just under 3 days old: still cached, no re-fetch
    cache = json.loads((tmp_path / "omdb_cache.json").read_text(encoding="utf-8"))
    cache["tt7526136"]["at"] -= (3 * 24 * 3600 - 60)
    (tmp_path / "omdb_cache.json").write_text(json.dumps(cache), encoding="utf-8")
    data2 = {"films": {"x": {"imdb": {"id": "tt7526136"}}}}
    omdb.fill_scores(data2, str(tmp_path))
    assert calls["n"] == 1 and data2["films"]["x"]["imdb_score"] == 7.5

    # just over 3 days old: re-fetched
    cache = json.loads((tmp_path / "omdb_cache.json").read_text(encoding="utf-8"))
    cache["tt7526136"]["at"] -= (3 * 24 * 3600 + 60)
    (tmp_path / "omdb_cache.json").write_text(json.dumps(cache), encoding="utf-8")
    data3 = {"films": {"x": {"imdb": {"id": "tt7526136"}}}}
    omdb.fill_scores(data3, str(tmp_path))
    assert calls["n"] == 2


def test_fill_scores_real_omdb_call_heart_of_the_beast(live_network):
    """Real network call (round 3 QA fix): tt7526136 is «Heart of the Beast» -- OMDb's own published rating
    for it is 7.5. Skipped when no OMDb key is configured anywhere (env OMDB_KEY, else AWS SSM
    /elyoxe/omdb/key) -- this test proves the live integration works when a key exists, it is not the gate
    that decides whether one is provisioned."""
    key = os.environ.get("OMDB_KEY") or omdb._key()
    if not key:
        pytest.skip("no OMDb key configured (env OMDB_KEY / AWS SSM /elyoxe/omdb/key)")
    score = omdb._fetch("tt7526136", key)
    assert score == 7.5


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
                      "consensus_ar": None, "ending": None, "qa": [], "has_plot": False}
    site = FakeSite({"x": film})
    html = intel_page._film_info(site, "ar", "x")
    assert "اشرح النهاية" in html and "أسئلة عن الفيلم" in html
    assert html.count(intel_page.L["no_answer"][0]) == 2   # both spoiler sections fall back


def test_film_info_slot_shows_ending_and_qa_with_a_plot():
    film = dict(FILM)
    film["intel"] = {"reasons": [{"text": "سبب", "pos": True}], "audience": [], "fun_fact": None,
                      "consensus_ar": None,
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


def test_film_info_slot_hides_arabic_intel_on_the_english_mirror():
    # review, Important #6: /en/ must never render the Arabic reasons/audience/fun-fact/spoiler prose
    film = dict(FILM)
    film["imdb_score"] = 8.6
    film["intel"] = {"reasons": [{"text": "سبب مهم", "pos": True}], "audience": [], "fun_fact": None,
                      "consensus_ar": "ملخص عربي", "ending": "نهاية عربية", "qa": [], "has_plot": True}
    site = FakeSite({"x": film})
    html_en = intel_page._film_info(site, "en", "x")
    assert "IMDb" in html_en
    assert "سبب مهم" not in html_en and "ملخص عربي" not in html_en and "نهاية عربية" not in html_en
    html_ar = intel_page._film_info(site, "ar", "x")
    assert "ملخص عربي" in html_ar
    # round3-gaps: the reasons are the hero's «ليش يستاهل؟» (film.why) now, never the tab's — and Arabic only there too
    assert "سبب مهم" not in html_ar and "سبب مهم" in intel_page._why(site, "ar", "x")
    assert "سبب مهم" not in intel_page._why(site, "en", "x")


# ================================================================ item 232 (2026-10-17): the Arabic synopsis
FILM_SYN = {**FILM, "synopsis_en": "Interstellar is a 2014 epic science fiction film directed by Christopher Nolan."}
OPEN_SYN = json.dumps({**json.loads(OPEN_GOOD), "synopsis_ar": "رحلة بالفضاء من إخراج Christopher Nolan عن أب يدوّر كوكب ثاني يعيش فيه البشر."})


def test_validate_open_requires_synopsis_ar_when_an_english_synopsis_is_given():
    why = filmintel._validate_open(json.loads(OPEN_GOOD), [], True, True)
    assert why and "synopsis_ar" in why
    assert filmintel._validate_open(json.loads(OPEN_SYN), [], True, True) is None


def test_validate_open_rejects_synopsis_ar_when_none_was_given():
    why = filmintel._validate_open(json.loads(OPEN_SYN), [], True, False)
    assert why and "synopsis_ar" in why


def test_needs_generate_redoes_a_claude_record_only_for_a_missing_synopsis():
    stable = {"by": "claude", "has_plot": True, "reasons": [], "audience": [], "fun_fact": None, "consensus_ar": None}
    assert filmintel.needs_generate(stable, FILM) is False                      # no English synopsis: nothing to add
    assert filmintel.needs_generate(stable, FILM_SYN) is True                   # a synopsis exists, none in the record
    assert filmintel.needs_generate({**stable, "synopsis_ar": None}, FILM_SYN) is False   # asked before, honestly null
    assert filmintel.needs_generate({**stable, "synopsis_ar": "..."}, FILM_SYN) is False


def test_generate_one_redoes_the_open_half_for_the_synopsis_and_keeps_a_finished_spoiler_half():
    existing = {"by": "claude", "reasons": [{"text": "قديم", "pos": True}], "audience": [], "fun_fact": None,
                "consensus_ar": None, "has_plot": True, "ending": "النهاية المحفوظة.", "qa": [{"q": "س", "a": "ج"}] * 4}
    client = FakeClient([OPEN_SYN])
    out = filmintel._generate_one(client, "interstellar", FILM_SYN, None, [], existing=existing)
    assert client.messages.calls == 1                                            # the open call only
    assert out["synopsis_ar"].startswith("رحلة بالفضاء")
    assert out["ending"] == "النهاية المحفوظة." and len(out["qa"]) == 4 and out["has_plot"] is True
    assert "next_check" not in out


def test_generate_one_prompt_carries_the_english_synopsis_and_the_record_the_arabic_one():
    client = FakeClient([OPEN_SYN])
    out = filmintel._generate_one(client, "interstellar", FILM_SYN, None, [])
    assert out["synopsis_ar"] and out["by"] == "claude"
    prompt = filmintel._open_prompt(FILM_SYN, [])
    assert "synopsis_ar" in prompt and "Christopher Nolan" in prompt
    assert "synopsis_ar" not in filmintel._open_prompt(FILM, []) or '"synopsis_ar": "..." أو null' in filmintel._open_prompt(FILM, [])


def test_write_missing_skips_the_plot_fetch_when_the_spoiler_half_is_done(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])

    def boom(qid):
        raise AssertionError("wikipedia_plot must not be fetched for a finished spoiler half")
    monkeypatch.setattr(filmintel, "wikipedia_plot", boom)
    (tmp_path / "interstellar.json").write_text(json.dumps({"fid": "interstellar", "by": "claude", "reasons": [], "audience": [],
                                                            "fun_fact": None, "consensus_ar": None, "has_plot": True,
                                                            "ending": "x", "qa": [{"q": "a", "b": "c"}] * 4}), encoding="utf-8")
    fake = FakeClient([OPEN_SYN])
    monkeypatch.setattr("verdicts._client", lambda: fake)
    out = filmintel.write_missing({"films": {"interstellar": FILM_SYN}})
    assert out["interstellar"]["synopsis_ar"] and out["interstellar"]["ending"] == "x"


def test_attach_synopses_puts_the_intel_synopsis_on_the_film(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    (tmp_path / "a.json").write_text(json.dumps({"fid": "a", "by": "claude", "synopsis_ar": " قصة أ. "}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"fid": "b", "by": "skip"}), encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps({"fid": "c", "by": "claude", "synopsis_ar": None}), encoding="utf-8")
    films = {"a": {}, "b": {}, "c": {}, "d": {"synopsis_ar": "عندي"}}
    assert intel_page.attach_synopses(films) == 1
    assert films["a"]["synopsis_ar"] == "قصة أ." and "synopsis_ar" not in films["b"] and "synopsis_ar" not in films["c"]
    assert films["d"]["synopsis_ar"] == "عندي"


def test_validate_open_drops_tanwin_from_a_written_synopsis_instead_of_rejecting_it():
    parsed = {**json.loads(OPEN_SYN), "synopsis_ar": "قصة عن أب يسافر بعيداً جداً عن بيته."}
    assert filmintel._validate_open(parsed, [], True, True) is None
    assert parsed["synopsis_ar"] == "قصة عن أب يسافر بعيدا جدا عن بيته."


def test_write_missing_keeps_a_finished_record_when_the_synopsis_call_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(filmintel, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(filmintel, "reddit_snippets", lambda title, year, cap=6: [])
    monkeypatch.setattr(filmintel, "wikipedia_plot", lambda qid: None)
    rec = {"fid": "interstellar", "by": "claude", "reasons": [{"text": "قديم", "pos": True}], "audience": [],
           "fun_fact": None, "consensus_ar": "النقاد حبّوه.", "has_plot": True, "ending": "x", "qa": [{"q": "a", "a": "b"}] * 4}
    (tmp_path / "interstellar.json").write_text(json.dumps(rec), encoding="utf-8")
    fake = FakeClient([OPEN_BAD_DIALECT])    # every attempt rejected
    monkeypatch.setattr("verdicts._client", lambda: fake)
    filmintel.write_missing({"films": {"interstellar": FILM_SYN}})
    after = json.loads((tmp_path / "interstellar.json").read_text(encoding="utf-8"))
    assert after["by"] == "claude" and after["reasons"] == rec["reasons"] and after["ending"] == "x"
    assert "synopsis_ar" not in after and after["next_check"] > date.today().isoformat() and after["retry_reason"]
    assert filmintel.needs_generate(after, FILM_SYN) is False      # backed off now …
    after["next_check"] = (date.today() - timedelta(days=1)).isoformat()
    assert filmintel.needs_generate(after, FILM_SYN) is True       # … retried once the window passes
