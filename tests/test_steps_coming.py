"""steps/coming.py: merges coming.fetch_all() by film fid (Task 2)."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("steps.coming", ROOT / "steps" / "coming.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_offline_leaves_existing_coming_data_untouched(monkeypatch):
    mod = _load()
    called = []
    monkeypatch.setattr(mod.coming, "fetch_all", lambda: called.append(1) or {})
    data = {"coming": {"digger": {"title": "Digger"}}}
    out = mod.run(data, {"offline": True})
    assert not called   # network never touched offline
    assert data["coming"] == {"digger": {"title": "Digger"}}
    assert out["films"] == 1


def test_merges_two_chains_by_fid_and_unions_fields(monkeypatch):
    mod = _load()
    results = {
        "vox": {"ok": True, "error": None, "items": [
            {"title": "Digger", "title_ar": None, "release_date": "2026-10-01",
             "poster": "https://vox/digger.jpg", "trailer": None, "genres": ["Action"], "chain": "vox"},
        ]},
        "star": {"ok": True, "error": None, "items": [
            {"title": "Digger", "title_ar": "دِغر", "release_date": "2026-09-28",
             "poster": None, "trailer": "abcdefghijk", "genres": ["Thriller"], "chain": "star"},
        ]},
    }
    monkeypatch.setattr(mod.coming, "fetch_all", lambda: results)
    # posters.mirror is best-effort and imported lazily inside run(); make it a no-op here so this
    # test exercises the merge logic only (posters.py's own behaviour has its own tests).
    fake_posters = type(sys)("posters")
    fake_posters.mirror = lambda view: {"films": 0, "with_poster": 0, "downloaded": 0, "failed": 0}
    monkeypatch.setitem(sys.modules, "posters", fake_posters)

    data = {}
    out = mod.run(data, {"offline": False})

    assert list(data["coming"].keys()) == ["digger"]
    f = data["coming"]["digger"]
    assert f["title"] == "Digger" and f["title_ar"] == "دِغر"
    assert f["release_date"] == "2026-09-28"   # the earliest of the two chains' dates
    assert f["poster"] == "https://vox/digger.jpg"   # vox had one, star's None never overwrites it
    assert f["trailer"] == "abcdefghijk"
    assert sorted(f["genres"]) == ["Action", "Thriller"]
    assert sorted(f["chains"]) == ["star", "vox"]
    assert out["films"] == 1
    assert out["chains"]["vox"]["ok"] is True and out["chains"]["star"]["ok"] is True


def test_a_broken_chain_never_drops_the_others(monkeypatch):
    mod = _load()
    results = {
        "roxy": {"ok": False, "error": "RuntimeError: boom", "items": []},
        "novo": {"ok": True, "error": None, "items": [
            {"title": "Sacrifice", "title_ar": None, "release_date": None, "poster": None,
             "trailer": None, "genres": [], "chain": "novo"},
        ]},
    }
    monkeypatch.setattr(mod.coming, "fetch_all", lambda: results)
    fake_posters = type(sys)("posters")
    fake_posters.mirror = lambda view: {}
    monkeypatch.setitem(sys.modules, "posters", fake_posters)

    data = {}
    out = mod.run(data, {"offline": False})
    assert "sacrifice" in data["coming"]
    assert out["chains"]["roxy"]["ok"] is False
    assert out["chains"]["novo"]["ok"] is True
