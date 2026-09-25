"""Tests for refresh.py — the orchestrator. Run with `python -m pytest` from the repo root
(saas/cinema) so refresh.py is importable without a conftest.py.

Network is never touched here: --offline runs use fixtures/<chain>.json (real, on disk); the
mixed-mode tests (a chain that raises, a chain that hangs, all chains failing, raw-file reuse)
monkeypatch refresh.CHAIN_READERS with fixture-backed fakes instead. enrich and verdicts are
always stubbed out too (enrich hits Wikidata/RT/Wikipedia, verdicts hits the Anthropic API).
"""
import json
import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import refresh  # noqa: E402
import verdicts as verdicts_mod  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_FIXTURES_DIR = REPO_ROOT / "fixtures"
REAL_VERDICTS_DIR = REPO_ROOT / "verdicts"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Points every path refresh.py writes to at a tmp dir, and stubs enrich (no network)."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(refresh, "DATA_DIR", data_dir)
    monkeypatch.setattr(refresh, "RAW_DIR", data_dir / "raw")
    monkeypatch.setattr(refresh, "LATEST_PATH", data_dir / "latest.json")
    monkeypatch.setattr(refresh, "HEALTH_PATH", data_dir / "health.json")
    monkeypatch.setattr(refresh, "FILMS_CACHE_PATH", data_dir / "films_cache.json")
    monkeypatch.setattr(refresh, "FIXTURES_DIR", REAL_FIXTURES_DIR)

    verdicts_dir = tmp_path / "verdicts"
    verdicts_dir.mkdir()
    monkeypatch.setattr(verdicts_mod, "VERDICTS_DIR", verdicts_dir)

    monkeypatch.setattr(refresh.enrich_mod, "enrich", lambda data, cache_path=None, offline=False: data)
    return data_dir, verdicts_dir


def _copy_verdicts(verdicts_dir, fids):
    for fid in fids:
        shutil.copy(REAL_VERDICTS_DIR / f"{fid}.json", verdicts_dir / f"{fid}.json")


def test_offline_all_chains_ok_with_verdicts(sandbox, monkeypatch):
    data_dir, verdicts_dir = sandbox
    # fixtures are dated 2026-09-25; freeze "now" inside that window so merge()'s 30-min-old
    # cutoff doesn't drop every show before the verdict-attachment can be checked.
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _copy_verdicts(verdicts_dir, ["bloody-tennis", "coyote-vs-acme"])

    code = refresh.refresh(offline=True, no_verdicts=True)

    assert code == 0
    latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    assert set(latest["chains"]) == set(refresh.ALL_CHAINS)
    for chain, info in latest["chains"].items():
        assert info["ok"] is True, chain
    assert latest["shows"], "expected shows to survive the merge"

    films = latest["films"]
    assert "bloody-tennis" in films
    assert films["bloody-tennis"]["verdict"]["verdict"] == "unknown"
    assert films["coyote-vs-acme"]["verdict"]["fid"] == "coyote-vs-acme"
    # a film with no verdicts/<fid>.json on disk gets no "verdict" key invented
    other = next(f for fid, f in films.items() if fid not in ("bloody-tennis", "coyote-vs-acme"))
    assert "verdict" not in other

    # per-city slices and health were also written
    assert (data_dir / "health.json").exists()
    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert all(h["ok"] for h in health.values())
    city_files = {p.stem for p in data_dir.glob("*.json")} - {"latest", "health", "films_cache"}
    assert city_files, "expected at least one data/<city>.json slice"


def _fake_readers(monkeypatch, fail=(), hang=(), calls=None):
    """Monkeypatches refresh.CHAIN_READERS with fixture-backed fakes: `fail` chains raise,
    `hang` chains sleep past any reasonable timeout, everything else returns its fixture."""
    calls = calls if calls is not None else {}

    def make(chain):
        def fn(days=2):
            calls[chain] = calls.get(chain, 0) + 1
            if chain in fail:
                raise RuntimeError(f"{chain} boom")
            if chain in hang:
                time.sleep(5)
            return json.loads((REAL_FIXTURES_DIR / f"{chain}.json").read_text(encoding="utf-8"))
        return fn

    fakes = {chain: make(chain) for chain in refresh.ALL_CHAINS}
    monkeypatch.setattr(refresh, "CHAIN_READERS", fakes)
    return calls


def test_chain_raises_keeps_previous_shows(sandbox, monkeypatch):
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")

    previous = {
        "generated": "2026-09-24T12:00:00+04:00",
        "chains": {"vox": {"ok": True, "at": "2026-09-24T12:00:00+04:00", "error": None}},
        "cinemas": {"vox-test": {"id": "vox-test", "chain": "vox", "name": "VOX Test",
                                  "name_ar": None, "city": "dubai", "mall": None, "address": None,
                                  "maps": None, "lat": None, "lng": None}},
        "films": {"stale-film": {"title": "Stale Film", "lang": None, "rating": None,
                                  "runtime": None, "poster": None, "chains": ["vox"]}},
        "shows": [{"cinema": "vox-test", "film": "stale-film", "date": "2099-01-01", "time": "20:00",
                   "hall": "Standard", "hall_label": "Standard", "prices": None,
                   "book": "https://example.test", "price_source": None}],
    }
    data_dir.mkdir(parents=True)
    (data_dir / "latest.json").write_text(json.dumps(previous), encoding="utf-8")

    _fake_readers(monkeypatch, fail=["vox"])

    code = refresh.refresh(offline=False, no_verdicts=True)

    assert code == 0  # six of seven chains still ok
    latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    assert latest["chains"]["vox"]["ok"] is False
    assert "boom" in latest["chains"]["vox"]["error"]
    vox_shows = [s for s in latest["shows"] if s["cinema"] == "vox-test"]
    assert len(vox_shows) == 1
    assert vox_shows[0]["film"] == "stale-film"

    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["vox"]["ok"] is False


def test_hung_chain_is_timed_out(sandbox, monkeypatch):
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _fake_readers(monkeypatch, hang=["novo"])

    start = time.monotonic()
    code = refresh.refresh(chains=["novo"], offline=False, no_verdicts=True, timeout=0.3)
    elapsed = time.monotonic() - start

    assert code == 1  # the only chain run, and it failed
    assert elapsed < 4  # never waits for the hung reader, only for the timeout
    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["novo"]["ok"] is False
    assert "timed out" in health["novo"]["error"]


def test_all_chains_failed_exits_1(sandbox, monkeypatch):
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _fake_readers(monkeypatch, fail=refresh.ALL_CHAINS)

    code = refresh.refresh(offline=False, no_verdicts=True)

    assert code == 1


def test_fresh_raw_file_is_reused_without_refetching(sandbox, monkeypatch):
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    calls = _fake_readers(monkeypatch)

    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True)
    fixture = json.loads((REAL_FIXTURES_DIR / "vox.json").read_text(encoding="utf-8"))
    (raw_dir / "vox.json").write_text(json.dumps(fixture), encoding="utf-8")

    code = refresh.refresh(chains=["vox"], offline=False, no_verdicts=True)

    assert code == 0
    assert calls.get("vox", 0) == 0  # never called — the fresh raw file was reused
    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["vox"]["ok"] is True


def test_force_ignores_fresh_raw_file(sandbox, monkeypatch):
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    calls = _fake_readers(monkeypatch)

    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True)
    fixture = json.loads((REAL_FIXTURES_DIR / "vox.json").read_text(encoding="utf-8"))
    (raw_dir / "vox.json").write_text(json.dumps(fixture), encoding="utf-8")

    code = refresh.refresh(chains=["vox"], offline=False, no_verdicts=True, force=True)

    assert code == 0
    assert calls.get("vox", 0) == 1  # refetched despite the fresh file on disk
