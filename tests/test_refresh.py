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


def test_price_health_passthrough_and_degraded_flag(sandbox, monkeypatch):
    """A reader's top-level "price_health" (new field, some readers don't have it yet) drives
    health.json's priced accounting and prices_degraded flag, and never leaks into latest.json."""
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")

    def vox_with_price_health(days=2):
        data = json.loads((REAL_FIXTURES_DIR / "vox.json").read_text(encoding="utf-8"))
        data["price_health"] = {"attempted": 10, "priced": 3, "error": None}  # < 50% -> degraded
        return data

    _fake_readers(monkeypatch)
    monkeypatch.setattr(refresh, "CHAIN_READERS", {**refresh.CHAIN_READERS, "vox": vox_with_price_health})

    code = refresh.refresh(chains=["vox"], offline=False, no_verdicts=True)

    assert code == 0
    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["vox"]["price_health"] == {"attempted": 10, "priced": 3, "error": None}
    assert health["vox"]["prices_degraded"] is True

    latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    assert "price_health" not in latest
    assert all("price_health" not in s for s in latest["shows"])


def test_price_health_absent_falls_back_to_show_counts(sandbox, monkeypatch):
    """A chain whose reader doesn't emit price_health yet (all current fixtures) still gets a
    sane priced accounting and prices_degraded computed off shows[].prices."""
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _fake_readers(monkeypatch)

    code = refresh.refresh(chains=["vox"], offline=False, no_verdicts=True)

    assert code == 0
    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert "price_health" not in health["vox"]  # nothing to pass through
    assert "prices_degraded" in health["vox"]  # still computed, off shows[].prices


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


def _verdict_json(fid, verdict="yes"):
    return {"fid": fid, "verdict": verdict, "ar": "زين", "en": "Good.", "basis": "test",
            "written": "2026-09-25", "by": "claude"}


def test_verdicts_success_path_is_attached(sandbox, monkeypatch):
    """verdicts_mod.write_missing is actually called (not just skipped, as every other test
    runs with no_verdicts=True) on the success path, and its output ends up attached."""
    data_dir, verdicts_dir = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _fake_readers(monkeypatch)
    calls = []

    def fake_write_missing(data, force=False, notes=None):
        for fid in data.get("films", {}):
            calls.append(fid)
            path = verdicts_dir / f"{fid}.json"
            if not path.exists():
                path.write_text(json.dumps(_verdict_json(fid)), encoding="utf-8")
        return {}

    monkeypatch.setattr(verdicts_mod, "write_missing", fake_write_missing)

    code = refresh.refresh(chains=["vox"], offline=False, no_verdicts=False)

    assert code == 0
    assert calls, "write_missing was never invoked"
    latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    assert latest["films"], "expected films from the vox fixture"
    for film in latest["films"].values():
        assert film["verdict"]["verdict"] == "yes"

    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["verdicts"]["ok"] is True
    assert health["verdicts"]["failed"] == []
    assert health["verdicts"]["succeeded"] == health["verdicts"]["attempted"]


def test_verdicts_failure_degrades_but_still_writes_latest(sandbox, monkeypatch):
    """The critical fix: write_missing raising (Anthropic API error, or dialect-retry
    exhaustion — verdicts.py's own RuntimeError) must not abort refresh() — latest.json is
    still written, and the failure is recorded in health.json instead."""
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _fake_readers(monkeypatch)

    def raising_write_missing(data, force=False, notes=None):
        raise RuntimeError("anthropic api boom")

    monkeypatch.setattr(verdicts_mod, "write_missing", raising_write_missing)

    code = refresh.refresh(chains=["vox"], offline=False, no_verdicts=False)

    assert code == 0  # the vox chain fetch itself still succeeded — only verdicts degraded
    latest_path = data_dir / "latest.json"
    assert latest_path.exists(), "latest.json must still be written despite verdicts failing"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["shows"], "the chain's freshly-fetched shows must not be discarded"

    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["verdicts"]["ok"] is False
    assert "boom" in health["verdicts"]["error"]
    assert health["verdicts"]["failed"]  # every attempted film recorded as failed
    assert health["verdicts"]["succeeded"] == 0


def test_verdicts_one_bad_film_does_not_stop_the_others(sandbox, monkeypatch):
    """Per-film isolation: write_missing() is called once per film from refresh.py (not once
    for the whole batch), so one film raising doesn't stop the rest from getting a verdict."""
    data_dir, verdicts_dir = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _fake_readers(monkeypatch)

    bad_fid = "resident-evil"  # present in fixtures/vox.json

    def flaky_write_missing(data, force=False, notes=None):
        (fid, _film), = data["films"].items()  # refresh.py calls this once per film
        if fid == bad_fid:
            raise RuntimeError("dialect retries exhausted")
        path = verdicts_dir / f"{fid}.json"
        if not path.exists():
            path.write_text(json.dumps(_verdict_json(fid)), encoding="utf-8")
        return {}

    monkeypatch.setattr(verdicts_mod, "write_missing", flaky_write_missing)

    code = refresh.refresh(chains=["vox"], offline=False, no_verdicts=False)

    assert code == 0
    latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    assert bad_fid in latest["films"]
    assert "verdict" not in latest["films"][bad_fid]  # no verdict invented for the bad film
    others = [f for fid, f in latest["films"].items() if fid != bad_fid]
    assert others and all(f.get("verdict", {}).get("verdict") == "yes" for f in others)

    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["verdicts"]["ok"] is False
    assert health["verdicts"]["failed"] == [bad_fid]
    assert health["verdicts"]["succeeded"] == health["verdicts"]["attempted"] - 1


def test_hung_chain_exit_code_ignores_enrich_verdicts_health(sandbox, monkeypatch):
    """The exit code must key off the requested chains only — an "enrich"/"verdicts" pseudo
    entry with ok:True in health.json must never mask every real chain having failed."""
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    _fake_readers(monkeypatch, hang=["novo"])

    code = refresh.refresh(chains=["novo"], offline=False, no_verdicts=True, timeout=0.3)

    assert code == 1
    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["novo"]["ok"] is False
    assert health["enrich"]["ok"] is True  # the stub never raises


# ---------------------------------------------------------------- fix wave D

def test_zero_attempted_price_health_is_never_degraded(sandbox, monkeypatch):
    """Roxy reports price_health {attempted: 0} by design (prices come from prices.yaml)."""
    data_dir, _ = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")

    def roxy_like(days=2):
        data = json.loads((REAL_FIXTURES_DIR / "roxy.json").read_text(encoding="utf-8"))
        for s in data["shows"]:
            s["prices"] = None
        data["price_health"] = {"attempted": 0, "priced": 0, "error": None}
        return data

    _fake_readers(monkeypatch)
    monkeypatch.setattr(refresh, "CHAIN_READERS", {**refresh.CHAIN_READERS, "roxy": roxy_like})
    assert refresh.refresh(chains=["roxy"], offline=False, no_verdicts=True) == 0
    health = json.loads((data_dir / "health.json").read_text(encoding="utf-8"))
    assert health["roxy"]["prices_degraded"] is False


def test_vox_gets_a_longer_timeout_than_the_others():
    assert refresh.chain_timeout("vox") == 900
    assert all(refresh.chain_timeout(c) == 480 for c in refresh.ALL_CHAINS if c != "vox")


def test_merged_away_verdict_files_are_folded(sandbox, monkeypatch):
    data_dir, verdicts_dir = sandbox
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    (verdicts_dir / "fall-2.json").write_text(json.dumps(_verdict_json("fall-2", "mixed")), encoding="utf-8")
    (verdicts_dir / "buttery-effect-azzam.json").write_text(json.dumps(_verdict_json("buttery-effect-azzam", "unknown")),
                                                           encoding="utf-8")
    _fake_readers(monkeypatch)
    assert refresh.refresh(chains=["vox"], offline=False, no_verdicts=True) == 0
    assert not (verdicts_dir / "fall-2.json").exists()
    assert (verdicts_dir / "fall-2-deadpoint.json").exists()           # moved: nothing better was there
    assert json.loads((verdicts_dir / "fall-2-deadpoint.json").read_text(encoding="utf-8"))["fid"] == "fall-2-deadpoint"
    assert not (verdicts_dir / "buttery-effect-azzam.json").exists()
