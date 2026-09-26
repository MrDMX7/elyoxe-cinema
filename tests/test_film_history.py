"""Tests for Task 6: data/film_history.json (permanent archive + first_seen/last_seen), the
new-film alert list, and the price cache's per-date reset as seen through refresh().

update_film_history() is pure (no I/O) and tested directly with hand-built `merged` dicts --
same style as normalize.py's own unit tests. The price-cache-resets-per-date behaviour needs the
real refresh() pipeline (it lives in refresh.refresh(), not in update_film_history), so those two
tests reuse test_refresh.py's `sandbox`/`_fake_readers` pattern.
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import refresh  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_FIXTURES_DIR = REPO_ROOT / "fixtures"


def _film(title="A Film", chains=("vox",), **extra):
    return {"title": title, "title_ar": None, "poster": None, "genres": [], "rating": None,
            "runtime": None, "chains": list(chains), **extra}


def _merged(films, shows, chains_ok):
    return {
        "films": films,
        "shows": shows,
        "chains": {c: {"ok": ok, "at": "2026-09-27T10:00:00+04:00", "error": None}
                   for c, ok in chains_ok.items()},
    }


def _show(fid, cinema="vox-x"):
    return {"film": fid, "cinema": cinema, "date": "2026-09-27", "time": "19:00"}


# ---------------------------------------------------------------- new-film detection

def test_brand_new_fid_is_reported():
    merged = _merged({"new-film": _film()}, [_show("new-film")], {"vox": True})
    new_history, new_films = refresh.update_film_history(merged, {}, "2026-09-27")
    assert [f["fid"] for f in new_films] == ["new-film"]
    assert new_films[0]["cinemas"] == 1
    assert new_history["new-film"]["first_seen"] == "2026-09-27"
    assert new_history["new-film"]["last_seen"] == "2026-09-27"
    assert new_history["new-film"]["absent_runs"] == 0


def test_fid_already_in_history_is_not_reported_again():
    history = {"old-film": {"first_seen": "2026-09-01", "last_seen": "2026-09-26",
                             "absent_runs": 0, "chains": ["vox"], "snapshot": _film()}}
    merged = _merged({"old-film": _film()}, [_show("old-film")], {"vox": True})
    _, new_films = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_films == []


def test_first_seen_is_never_overwritten_once_set():
    history = {"old-film": {"first_seen": "2026-08-01", "last_seen": "2026-09-26",
                             "absent_runs": 0, "chains": ["vox"], "snapshot": _film()}}
    merged = _merged({"old-film": _film()}, [_show("old-film")], {"vox": True})
    new_history, _ = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_history["old-film"]["first_seen"] == "2026-08-01"
    assert new_history["old-film"]["last_seen"] == "2026-09-27"


# ---------------------------------------------------------------- archival + the absence guard

def _absent_history(chains=("vox",), absent_runs=0, last_seen="2026-09-20"):
    return {"gone-film": {"first_seen": "2026-09-01", "last_seen": last_seen,
                           "absent_runs": absent_runs, "chains": list(chains),
                           "snapshot": _film(chains=chains, title="Gone Film")}}


def test_absent_film_is_not_archived_after_one_confirmed_absent_run():
    history = _absent_history(absent_runs=0)
    merged = _merged({}, [], {"vox": True})
    new_history, _ = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_history["gone-film"]["absent_runs"] == 1
    assert "gone-film" not in merged["films"]  # not archived yet -- just gone from the listing


def test_absent_film_is_archived_after_two_confirmed_absent_runs():
    history = _absent_history(absent_runs=1)
    merged = _merged({}, [], {"vox": True})
    new_history, _ = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_history["gone-film"]["absent_runs"] == 2
    film = merged["films"]["gone-film"]
    assert film["status"] == "archived"
    assert film["first_seen"] == "2026-09-01"
    assert film["last_seen"] == "2026-09-20"  # frozen at the last real showing, not today
    assert film["title"] == "Gone Film"


def test_archived_film_stays_archived_on_every_later_run():
    """Once past the threshold, absent_runs only grows -- the film is re-added every run."""
    history = _absent_history(absent_runs=5)
    merged = _merged({}, [], {"vox": True})
    new_history, _ = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_history["gone-film"]["absent_runs"] == 6
    assert merged["films"]["gone-film"]["status"] == "archived"


def test_a_chain_outage_blocks_archival_and_does_not_advance_the_counter():
    """The owner's binding guard: a chain that ever listed the film must be healthy AND absent
    this run before its absence counts -- a failed/not-run chain must never let it be archived,
    and must not even advance the streak (so a real 2nd confirmed absence starts fresh later)."""
    history = _absent_history(chains=("vox", "star"), absent_runs=1)
    merged = _merged({}, [], {"vox": True, "star": False})  # star down this run
    new_history, _ = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_history["gone-film"]["absent_runs"] == 1  # untouched, not advanced to 2
    assert "gone-film" not in merged["films"]  # never archived while unproven


def test_a_chain_not_run_at_all_also_blocks_archival():
    """merged["chains"] simply missing a chain (never run this call) must be treated as not ok,
    same as an explicit failure -- normalize.merge()'s own "not run" chains are ok:false, but a
    caller that omits the key entirely must not accidentally read that as healthy."""
    history = _absent_history(chains=("reel",), absent_runs=1)
    merged = _merged({}, [], {"vox": True})  # "reel" isn't even a key here
    new_history, _ = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_history["gone-film"]["absent_runs"] == 1
    assert "gone-film" not in merged["films"]


def test_film_reappearing_before_archival_resets_absent_runs():
    history = _absent_history(absent_runs=1)
    merged = _merged({"gone-film": _film(title="Gone Film")}, [_show("gone-film")], {"vox": True})
    new_history, new_films = refresh.update_film_history(merged, history, "2026-09-27")
    assert new_history["gone-film"]["absent_runs"] == 0
    assert new_films == []  # it was already in history -- not a "new" film
    assert merged["films"]["gone-film"].get("status") != "archived"


# ---------------------------------------------------------------- the seeding-run rule (in refresh())

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(refresh, "DATA_DIR", data_dir)
    monkeypatch.setattr(refresh, "RAW_DIR", data_dir / "raw")
    monkeypatch.setattr(refresh, "LATEST_PATH", data_dir / "latest.json")
    monkeypatch.setattr(refresh, "HEALTH_PATH", data_dir / "health.json")
    monkeypatch.setattr(refresh, "FILMS_CACHE_PATH", data_dir / "films_cache.json")
    monkeypatch.setattr(refresh, "FILM_HISTORY_PATH", data_dir / "film_history.json")
    monkeypatch.setattr(refresh, "PRICE_CACHE_PATH", data_dir / "price_cache.json")
    monkeypatch.setattr(refresh, "NEW_FILMS_PATH", data_dir / "new_films.json")
    monkeypatch.setattr(refresh, "FIXTURES_DIR", REAL_FIXTURES_DIR)
    monkeypatch.setattr(refresh.enrich_mod, "enrich", lambda data, cache_path=None, offline=False: data)
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    return data_dir


def test_the_run_that_creates_film_history_seeds_silently(sandbox):
    data_dir = sandbox
    assert not (data_dir / "film_history.json").exists()

    code = refresh.refresh(offline=True, no_verdicts=True)

    assert code == 0
    assert (data_dir / "film_history.json").exists()
    new_films = json.loads((data_dir / "new_films.json").read_text(encoding="utf-8"))
    assert new_films == []  # every film is technically "new" to an empty history -- seeded, not alerted


def test_a_real_new_film_on_a_later_run_is_reported(sandbox):
    data_dir = sandbox
    refresh.refresh(offline=True, no_verdicts=True)  # seeding run

    history_path = data_dir / "film_history.json"
    history = json.loads(history_path.read_text(encoding="utf-8"))
    # drop one film from history so this run sees it as "new" again, as if it just appeared
    dropped_fid, dropped = next(iter(history.items()))
    del history[dropped_fid]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    code = refresh.refresh(offline=True, no_verdicts=True)

    assert code == 0
    new_films = json.loads((data_dir / "new_films.json").read_text(encoding="utf-8"))
    assert [f["fid"] for f in new_films] == [dropped_fid]
    assert new_films[0]["title"]


# ---------------------------------------------------------------- price cache resets per date

def _fake_readers_with_price_cache_spy(monkeypatch, seen_caches):
    def make(chain):
        def fn(days=2, **kw):
            if "cache" in kw:
                seen_caches[chain] = kw["cache"]
            return json.loads((REAL_FIXTURES_DIR / f"{chain}.json").read_text(encoding="utf-8"))
        return fn
    fakes = {chain: make(chain) for chain in refresh.ALL_CHAINS}
    monkeypatch.setattr(refresh, "CHAIN_READERS", fakes)


def test_price_cache_persisted_and_reused_next_run(sandbox, monkeypatch):
    data_dir = sandbox
    seen: dict = {}
    _fake_readers_with_price_cache_spy(monkeypatch, seen)

    refresh.refresh(chains=["vox"], offline=False, no_verdicts=True)
    seen["vox"]["vox-fake|Standard|2026-09-25"] = [{"seat": "Standard", "aed": 40.0}]  # simulate a sample

    on_disk = json.loads((data_dir / "price_cache.json").read_text(encoding="utf-8"))
    # refresh() writes back whatever it handed the reader, mutated in place
    assert "vox" not in on_disk or on_disk.get("vox", {}).get("2026-09-25") is not None

    refresh.refresh(chains=["vox"], offline=False, no_verdicts=True)
    assert seen["vox"].get("vox-fake|Standard|2026-09-25") == [{"seat": "Standard", "aed": 40.0}]


def test_price_cache_resets_on_a_new_date(sandbox, monkeypatch):
    data_dir = sandbox
    data_dir.mkdir(parents=True)
    (data_dir / "price_cache.json").write_text(json.dumps({
        "vox": {"2026-09-24": {"stale|Standard|2026-09-24": [{"seat": "Standard", "aed": 99.0}]}}
    }), encoding="utf-8")

    seen: dict = {}
    _fake_readers_with_price_cache_spy(monkeypatch, seen)
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")  # a new date

    refresh.refresh(chains=["vox"], offline=False, no_verdicts=True)

    assert seen["vox"] == {}  # yesterday's entries were never handed down
