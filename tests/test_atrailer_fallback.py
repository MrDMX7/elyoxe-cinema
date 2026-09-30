"""steps/atrailer_fallback.py: caching, cap, prune and _search's own filters, subprocess mocked
(the module's `run=` params, or _probe/_search monkeypatched at the step level — never a real
network call, matching tests/test_backdrops.py's approach)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import steps.atrailer_fallback as atf  # noqa: E402


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_ok(*a, **kw):
    return _Result(0, "", "")


def _run_unavailable(*a, **kw):
    return _Result(1, "", "ERROR: [youtube] xxxxxxxxxxx: Video unavailable. This video is no longer available")


def _run_throttled(*a, **kw):
    return _Result(1, "", "ERROR: Sign in to confirm you're not a bot")


# -------- _probe

def test_probe_ok():
    assert atf._probe("dQw4w9WgXcQ", run=_run_ok) == "ok"


def test_probe_dead_on_unavailable_text():
    assert atf._probe("dQw4w9WgXcQ", run=_run_unavailable) == "dead"


def test_probe_unknown_on_throttle_not_dead():
    """A throttle/bot-check is never mistaken for a dead trailer -- it must not trigger a search."""
    assert atf._probe("dQw4w9WgXcQ", run=_run_throttled) == "unknown"


def test_probe_unknown_when_yt_dlp_missing():
    def boom(*a, **kw):
        raise FileNotFoundError("no yt-dlp")
    assert atf._probe("dQw4w9WgXcQ", run=boom) == "unknown"


# -------- _search

def _search_run(lines):
    def run(*a, **kw):
        return _Result(0, "\n".join(lines), "")
    return run


def test_search_picks_first_matching_duration_and_title():
    lines = [
        "aaaaaaaaaaa\t45\tSome Channel\tBehind the scenes",           # too short
        "bbbbbbbbbbb\t130\tStudio Official\tFilm Title Official Trailer",
        "ccccccccccc\t130\tStudio Official\tFilm Title Official Trailer 2",
    ]
    vid, why = atf._search("Film Title", 2026, run=_search_run(lines))
    assert vid == "bbbbbbbbbbb" and why is None


def test_search_rejects_out_of_range_duration():
    lines = ["aaaaaaaaaaa\t900\tStudio\tFilm Title Official Trailer"]
    vid, why = atf._search("Film Title", 2026, run=_search_run(lines))
    assert vid is None and "no candidate" in why


def test_search_rejects_non_trailer_titles():
    lines = ["aaaaaaaaaaa\t120\tRandom Fan\tFull movie reaction"]
    vid, why = atf._search("Film Title", 2026, run=_search_run(lines))
    assert vid is None


# -------- run(): orchestration

def _data(fid="film1", trailer="dQw4w9WgXcQ", status=None):
    f = {"title": "Film Title", "year": 2026, "trailer": trailer}
    if status:
        f["status"] = status
    return {"films": {fid: f}, "coming": {}}


def test_run_replaces_dead_trailer_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(atf, "_probe", lambda *a, **kw: "dead")
    monkeypatch.setattr(atf, "_search", lambda *a, **kw: ("bbbbbbbbbbb", None))
    data = _data()
    out = atf.run(data, {"now": "2026-09-30T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert data["films"]["film1"]["trailer"] == "bbbbbbbbbbb"
    assert data["films"]["film1"]["trailer_fallback"] is True
    assert out["replaced"] == 1
    cache = json.loads((tmp_path / "trailer_fallback.json").read_text())
    assert cache["film1"]["status"] == "dead" and cache["film1"]["replacement"] == "bbbbbbbbbbb"


def test_run_leaves_healthy_trailer_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(atf, "_probe", lambda *a, **kw: "ok")
    monkeypatch.setattr(atf, "_search", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not search")))
    data = _data()
    out = atf.run(data, {"now": "2026-09-30T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert data["films"]["film1"]["trailer"] == "dQw4w9WgXcQ"
    assert "trailer_fallback" not in data["films"]["film1"]
    assert out["replaced"] == 0


def test_run_reapplies_cached_replacement_without_reprobing(tmp_path, monkeypatch):
    """Once a replacement is cached and RECHECK_DAYS_DEAD hasn't elapsed, no yt-dlp call happens at all --
    the film's trailer field (reset to the dead id by enrich.py every run) is simply overwritten again."""
    called = []
    monkeypatch.setattr(atf, "_probe", lambda *a, **kw: called.append("probe") or "dead")
    monkeypatch.setattr(atf, "_search", lambda *a, **kw: called.append("search") or ("bbbbbbbbbbb", None))
    data = _data()
    atf.run(data, {"now": "2026-09-30T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert called == ["probe", "search"]
    called.clear()
    data2 = _data()  # a fresh run's merged data: enrich.py put the ORIGINAL dead id back
    out = atf.run(data2, {"now": "2026-09-30T11:00:00+04:00", "data_dir": str(tmp_path)})
    assert called == []                                    # no network at all
    assert data2["films"]["film1"]["trailer"] == "bbbbbbbbbbb"
    assert out["replaced"] == 1


def test_run_respects_check_cap(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(atf, "CHECK_CAP", 1)
    monkeypatch.setattr(atf, "_probe", lambda tid, **kw: calls.append(tid) or "ok")
    monkeypatch.setattr(atf, "_search", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no budget")))
    data = {"films": {f"f{i}": {"title": "T", "year": 2026, "trailer": "a" * 11} for i in range(5)}, "coming": {}}
    out = atf.run(data, {"now": "2026-09-30T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert len(calls) == 1
    assert out["probed"] == 1


def test_run_offline_never_calls_subprocess_but_applies_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(atf, "_probe", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("offline must not probe")))
    (tmp_path / "trailer_fallback.json").write_text(json.dumps({
        "film1": {"orig": "dQw4w9WgXcQ", "checked_at": "2026-09-01T00:00:00+04:00", "status": "dead",
                  "replacement": "bbbbbbbbbbb", "why": None}
    }))
    data = _data()
    out = atf.run(data, {"now": "2026-09-30T10:00:00+04:00", "data_dir": str(tmp_path), "offline": True})
    assert data["films"]["film1"]["trailer"] == "bbbbbbbbbbb"
    assert out["replaced"] == 1


def test_run_ignores_invalid_and_archived(tmp_path, monkeypatch):
    monkeypatch.setattr(atf, "_probe", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not probe")))
    data = {"films": {
        "bad": {"title": "T", "trailer": "not-11-chars"},
        "gone": {"title": "T", "trailer": "dQw4w9WgXcQ", "status": "archived"},
    }, "coming": {}}
    out = atf.run(data, {"now": "2026-09-30T10:00:00+04:00", "data_dir": str(tmp_path)})
    assert out["checked"] == 0


def test_run_prunes_cache_for_films_no_longer_present(tmp_path):
    (tmp_path / "trailer_fallback.json").write_text(json.dumps({
        "old_film": {"orig": "a" * 11, "checked_at": "2026-09-01T00:00:00+04:00", "status": "dead",
                     "replacement": "b" * 11, "why": None}
    }))
    data = {"films": {}, "coming": {}}
    atf.run(data, {"now": "2026-09-30T10:00:00+04:00", "data_dir": str(tmp_path), "offline": True})
    cache = json.loads((tmp_path / "trailer_fallback.json").read_text())
    assert "old_film" not in cache
