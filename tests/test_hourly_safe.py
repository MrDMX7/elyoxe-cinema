"""Final fix wave (phase 1): the four findings that blocked the hourly schedule.

C1  a raw fetch is reused only to resume an unfinished run -- never across completed runs -- and a
    reused raw never counts as a fresh healthy fetch (archive clock, alerts).
I1  film history follows a canonical-fid change (merged["merged"] + the members it remembers):
    first_seen kept, no "new film" alert, no archive page for the old fid, a redirect page instead.
I2  archive only after >= 5 days of confirmed absence (time-based, not run counts); the
    chain-failure guard stays.
I3  alerts fire on a change of state (start, and once on clear), persisted in data/alert_state.json.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import alerts  # noqa: E402
import build  # noqa: E402
import refresh  # noqa: E402

FIX = ROOT / "fixtures"
NOW = "2026-09-27T12:10:00+04:00"


def _iso(days=0, hours=0, base=NOW):
    return (datetime.fromisoformat(base) + timedelta(days=days, hours=hours)).isoformat()


# ================================================================ C1 raw reuse = resume only

@pytest.fixture
def sandbox(tmp_path, monkeypatch, offline_steps):
    d = tmp_path / "data"
    for name, rel in [("DATA_DIR", ""), ("RAW_DIR", "raw"), ("LATEST_PATH", "latest.json"),
                      ("HEALTH_PATH", "health.json"), ("FILMS_CACHE_PATH", "films_cache.json"),
                      ("FILM_HISTORY_PATH", "film_history.json"), ("FILM_HISTORY_BACKUP_PATH", "film_history.prev.json"),
                      ("PRICE_CACHE_PATH", "price_cache.json"), ("PRICE_CACHE_BACKUP_PATH", "price_cache.prev.json"),
                      ("NEW_FILMS_PATH", "new_films.json")]:
        monkeypatch.setattr(refresh, name, d / rel if rel else d)
    monkeypatch.setattr(refresh, "FIXTURES_DIR", FIX)
    monkeypatch.setattr(refresh.enrich_mod, "enrich", lambda data, cache_path=None, offline=False: data)
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T12:00:00+04:00")
    return d


def _readers(monkeypatch, calls):
    def make(chain):
        def fn(days=2, **kw):
            calls[chain] = calls.get(chain, 0) + 1
            return json.loads((FIX / f"{chain}.json").read_text(encoding="utf-8"))
        return fn
    monkeypatch.setattr(refresh, "CHAIN_READERS", {c: make(c) for c in refresh.ALL_CHAINS})


def test_an_hourly_second_run_calls_the_reader_again(sandbox, monkeypatch):
    """The review's C1 test: a completed run's raw file is never reused by the next run, however
    young it is -- otherwise an hourly schedule refreshes showtimes every ~4 hours."""
    calls = {}
    _readers(monkeypatch, calls)
    assert refresh.refresh(chains=["vox"], no_verdicts=True) == 0
    monkeypatch.setattr(refresh, "now_iso", lambda: "2026-09-25T13:00:00+04:00")
    assert refresh.refresh(chains=["vox"], no_verdicts=True) == 0
    assert calls["vox"] == 2
    assert not refresh._run_marker_path().exists()  # a completed run leaves no marker behind


def _killed_run(data_dir, run_id="run-a", started="2026-09-25T11:50:00+04:00", raw_run_id=None):
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / ".run.json").write_text(json.dumps({"id": run_id, "started": started}), encoding="utf-8")
    fixture = json.loads((FIX / "vox.json").read_text(encoding="utf-8"))
    fixture["_run_id"] = raw_run_id or run_id
    (raw / "vox.json").write_text(json.dumps(fixture), encoding="utf-8")


def test_a_killed_run_is_resumed_from_its_own_raw_files(sandbox, monkeypatch):
    calls = {}
    _readers(monkeypatch, calls)
    _killed_run(sandbox)
    assert refresh.refresh(chains=["vox", "star"], no_verdicts=True) == 0
    assert calls.get("vox", 0) == 0 and calls["star"] == 1
    health = json.loads((sandbox / "health.json").read_text(encoding="utf-8"))
    assert health["vox"]["ok"] is True and health["vox"]["reused"] is True
    assert not health["star"].get("reused")
    latest = json.loads((sandbox / "latest.json").read_text(encoding="utf-8"))
    assert "_run_id" not in json.dumps(latest)  # the tag never leaks into the published data
    assert not refresh._run_marker_path().exists()


def test_a_raw_file_from_another_run_is_never_reused(sandbox, monkeypatch):
    calls = {}
    _readers(monkeypatch, calls)
    _killed_run(sandbox, run_id="run-b", raw_run_id="run-a")  # vox.json belongs to a finished run
    refresh.refresh(chains=["vox"], no_verdicts=True)
    assert calls["vox"] == 1


def test_a_stale_unfinished_run_is_not_resumed(sandbox, monkeypatch):
    calls = {}
    _readers(monkeypatch, calls)
    _killed_run(sandbox, started="2026-09-25T06:00:00+04:00")  # six hours old: start over
    refresh.refresh(chains=["vox"], no_verdicts=True)
    assert calls["vox"] == 1


def test_force_starts_a_new_run_even_mid_resume(sandbox, monkeypatch):
    calls = {}
    _readers(monkeypatch, calls)
    _killed_run(sandbox)
    refresh.refresh(chains=["vox"], no_verdicts=True, force=True)
    assert calls["vox"] == 1


def test_the_marker_names_the_run_while_it_is_going(sandbox, monkeypatch):
    seen = {}

    def spy(days=2, **kw):
        seen["marker"] = json.loads(refresh._run_marker_path().read_text(encoding="utf-8"))
        return json.loads((FIX / "vox.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(refresh, "CHAIN_READERS", {**{c: spy for c in refresh.ALL_CHAINS}})
    refresh.refresh(chains=["vox"], no_verdicts=True)
    assert seen["marker"]["id"] and seen["marker"]["started"] == "2026-09-25T12:00:00+04:00"
    raw = json.loads((sandbox / "raw" / "vox.json").read_text(encoding="utf-8"))
    assert raw["_run_id"] == seen["marker"]["id"]


# ================================================================ I2 time-based archive (+ C1: reused != fresh)

def _film(title="Gone Film", chains=("vox",)):
    return {"title": title, "title_ar": None, "genres": [], "chains": list(chains)}


def _merged(films, chains_ok, merged_map=None):
    shows = [{"film": f, "cinema": "vox-x", "date": NOW[:10], "time": "19:00"} for f in films]
    m = {"films": films, "shows": shows,
         "chains": {c: {"ok": ok} for c, ok in chains_ok.items()}}
    if merged_map:
        m["merged"] = merged_map
    return m


def _hist(absent_since=None, chains=("vox",), **extra):
    return {"gone-film": {"first_seen": "2026-09-01", "last_seen": "2026-09-20",
                          "last_seen_at": "2026-09-20T23:10:00+04:00", "absent_since": absent_since,
                          "chains": list(chains), "snapshot": _film(chains=chains), **extra}}


def test_first_confirmed_absence_starts_the_clock_and_does_not_archive():
    m = _merged({}, {"vox": True})
    h, _ = refresh.update_film_history(m, _hist(), NOW)
    assert h["gone-film"]["absent_since"] == NOW
    assert "gone-film" not in m["films"]


def test_hourly_absences_do_not_archive_within_five_days():
    h = _hist()
    for hour in range(0, 24 * 4 + 23):  # four days and 23 hours of hourly confirmed absences
        m = _merged({}, {"vox": True})
        h, _ = refresh.update_film_history(m, h, _iso(hours=hour))
        assert "gone-film" not in m["films"], hour


def test_five_days_of_confirmed_absence_archives():
    m = _merged({}, {"vox": True})
    h, _ = refresh.update_film_history(m, _hist(absent_since=_iso(days=-5)), NOW)
    f = m["films"]["gone-film"]
    assert f["status"] == "archived" and f["last_seen"] == "2026-09-20" and f["first_seen"] == "2026-09-01"
    assert h["gone-film"]["archived"] is True


def test_a_chain_outage_neither_starts_nor_completes_the_clock():
    m = _merged({}, {"vox": False})
    h, _ = refresh.update_film_history(m, _hist(), NOW)
    assert h["gone-film"]["absent_since"] is None
    m = _merged({}, {"vox": False})
    h, _ = refresh.update_film_history(m, _hist(absent_since=_iso(days=-6)), NOW)
    assert "gone-film" not in m["films"]  # unproven this run: not archived now


def test_a_reused_raw_is_not_a_confirmed_absence():
    """C1 knock-on: a chain served from a resumed raw is ok, but not a fresh fetch."""
    m = _merged({}, {"vox": True})
    h, _ = refresh.update_film_history(m, _hist(), NOW, fresh_chains=set())
    assert h["gone-film"]["absent_since"] is None
    m = _merged({}, {"vox": True})
    refresh.update_film_history(m, _hist(absent_since=_iso(days=-6)), NOW, fresh_chains=set())
    assert "gone-film" not in m["films"]


def test_an_archived_film_keeps_its_page_through_a_chain_outage():
    m = _merged({}, {"vox": False})
    refresh.update_film_history(m, _hist(absent_since=_iso(days=-9), archived=True), NOW)
    assert m["films"]["gone-film"]["status"] == "archived"


def test_reappearing_resets_the_clock():
    m = _merged({"gone-film": _film()}, {"vox": True})
    h, new = refresh.update_film_history(m, _hist(absent_since=_iso(days=-3)), NOW)
    assert h["gone-film"]["absent_since"] is None and new == []
    assert h["gone-film"]["last_seen_at"] == NOW


def test_an_entry_with_no_chains_needs_every_chain_fresh():
    m = _merged({}, {"vox": True, "star": False})
    h, _ = refresh.update_film_history(m, _hist(absent_since=_iso(days=-6), chains=()), NOW)
    assert "gone-film" not in m["films"]  # star is down -- nothing proves the absence
    m = _merged({}, {"vox": True, "star": True})
    refresh.update_film_history(m, _hist(absent_since=_iso(days=-6), chains=()), NOW)
    assert m["films"]["gone-film"]["status"] == "archived"


def test_a_legacy_record_with_absent_runs_migrates():
    """History written by the run-count rule: an already-archived film stays archived when its
    last showing is 5+ days back; a record mid-streak just starts the clock."""
    legacy = {"gone-film": {"first_seen": "2026-09-01", "last_seen": "2026-09-20", "absent_runs": 3,
                            "chains": ["vox"], "snapshot": _film()}}
    m = _merged({}, {"vox": True})
    refresh.update_film_history(m, legacy, NOW)
    assert m["films"]["gone-film"]["status"] == "archived"
    legacy["gone-film"]["absent_runs"] = 1
    m = _merged({}, {"vox": True})
    h, _ = refresh.update_film_history(m, legacy, NOW)
    assert "gone-film" not in m["films"] and h["gone-film"]["absent_since"] == NOW


# ================================================================ I1 canonical-fid changes

def _mirzapur_history(fid="mirzapur", members=("mirzapur-the-movie",)):
    return {fid: {"first_seen": "2026-09-10", "last_seen": "2026-09-26",
                  "last_seen_at": "2026-09-26T23:10:00+04:00", "absent_since": None,
                  "chains": ["vox", "star"], "members": list(members), "snapshot": _film("Mirzapur")}}


def test_canon_flip_keeps_first_seen_and_never_alerts():
    m = _merged({"mirzapur-the-movie": _film("Mirzapur: The Movie", ("vox", "star"))},
                {"vox": True, "star": True}, merged_map={"mirzapur": "mirzapur-the-movie"})
    h, new = refresh.update_film_history(m, _mirzapur_history(), NOW)
    assert new == []
    assert "mirzapur" not in h
    assert h["mirzapur-the-movie"]["first_seen"] == "2026-09-10"
    assert "mirzapur" in h["mirzapur-the-movie"]["redirect_from"]
    assert m["redirects"] == {"mirzapur": "mirzapur-the-movie"}
    assert "mirzapur" not in m["films"]


def test_canon_flip_found_through_remembered_members_when_the_old_fid_is_gone():
    """The old canonical title vanished from every chain, so this run's merged map doesn't name it;
    the history remembers mirzapur-the-movie was one of mirzapur's members."""
    m = _merged({"mirzapur-the-movie": _film("Mirzapur: The Movie")}, {"vox": True, "star": True})
    h, new = refresh.update_film_history(m, _mirzapur_history(), NOW)
    assert new == [] and "mirzapur" not in h
    assert h["mirzapur-the-movie"]["first_seen"] == "2026-09-10"
    assert m["redirects"] == {"mirzapur": "mirzapur-the-movie"}


def test_canon_flips_back_and_forth_without_losing_anything():
    m = _merged({"mirzapur-the-movie": _film()}, {"vox": True, "star": True},
                merged_map={"mirzapur": "mirzapur-the-movie"})
    h, _ = refresh.update_film_history(m, _mirzapur_history(), NOW)
    m = _merged({"mirzapur": _film()}, {"vox": True, "star": True},
                merged_map={"mirzapur-the-movie": "mirzapur"})
    h, new = refresh.update_film_history(m, h, _iso(hours=1))
    assert new == [] and set(h) == {"mirzapur"}
    assert h["mirzapur"]["first_seen"] == "2026-09-10"
    assert m["redirects"] == {"mirzapur-the-movie": "mirzapur"}


def test_the_old_fid_is_never_archived_after_a_flip():
    h = _mirzapur_history()
    for day in range(8):
        m = _merged({"mirzapur-the-movie": _film()}, {"vox": True, "star": True},
                    merged_map={"mirzapur": "mirzapur-the-movie"})
        h, new = refresh.update_film_history(m, h, _iso(days=day))
        assert new == [] and "mirzapur" not in m["films"]


def test_both_fids_in_history_merge_to_the_earliest_first_seen():
    h = {**_mirzapur_history(), **_mirzapur_history("mirzapur-the-movie", members=())}
    h["mirzapur-the-movie"]["first_seen"] = "2026-09-20"
    m = _merged({"mirzapur-the-movie": _film()}, {"vox": True}, merged_map={"mirzapur": "mirzapur-the-movie"})
    h2, _ = refresh.update_film_history(m, h, NOW)
    assert h2["mirzapur-the-movie"]["first_seen"] == "2026-09-10" and "mirzapur" not in h2


def test_members_are_remembered_for_the_next_flip():
    m = _merged({"mirzapur": _film()}, {"vox": True}, merged_map={"mirzapur-the-movie": "mirzapur"})
    h, _ = refresh.update_film_history(m, {}, NOW)
    assert h["mirzapur"]["members"] == ["mirzapur-the-movie"]


# ---------------------------------------------------------------- the build side of I1

DATA = ROOT / "fixtures" / "sample_latest.json"
DISC = ROOT / "fixtures" / "sample_discounts.yaml"


def _build(tmp_path, mutate=lambda d: None):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    mutate(data)
    p = tmp_path / "d.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "o"
    build.build(str(p), str(DISC), str(out), noindex=False)
    return out, data


def test_an_old_fid_gets_a_redirect_page_not_a_film_page(tmp_path):
    def mutate(d):
        d["redirects"] = {"mirzapur": "crawlers", "gone-nowhere": "no-such-film"}
    out, _ = _build(tmp_path, mutate)
    for lang, pre in (("ar", ""), ("en", "/en")):
        page = (out / pre.strip("/") / "film" / "mirzapur" / "index.html").read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex">' in page
        assert f'<link rel="canonical" href="https://cinema.elyoxe.com{pre}/film/crawlers/">' in page
        assert f'<meta http-equiv="refresh" content="0; url={pre}/film/crawlers/">' in page
        assert f'href="{pre}/film/crawlers/"' in page
    assert not (out / "film" / "gone-nowhere").exists()  # a target with no page gets no redirect
    sm = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "/film/mirzapur/" not in sm and "/film/crawlers/" in sm


# ================================================================ cards: an old card link stays useful

def test_a_card_with_no_confirmed_discount_gets_a_noindex_stub(tmp_path):
    out, _ = _build(tmp_path)
    ar = (out / "cards" / "homat" / "index.html").read_text(encoding="utf-8")
    en = (out / "en" / "cards" / "homat" / "index.html").read_text(encoding="utf-8")
    assert "ما لقينا خصم مؤكد لهالبطاقة حالياً" in ar and 'href="/cards/"' in ar
    assert 'href="/en/cards/"' in en
    for page in (ar, en):
        assert '<meta name="robots" content="noindex">' in page
    sm = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "/cards/homat/" not in sm
    home = (out / "index.html").read_text(encoding="utf-8")
    assert 'data-card="homat"' not in home and "/cards/homat/" not in home


# ================================================================ I3 alerts on change of state

def test_a_condition_alerts_once_when_it_starts_and_once_when_it_clears():
    s = {}
    s, m = alerts.step(s, "mem", bad=True, start="الذاكرة ما فضت", clear="الذاكرة رجعت", now=NOW)
    assert m == "الذاكرة ما فضت"
    for _ in range(5):
        s, m = alerts.step(s, "mem", bad=True, start="الذاكرة ما فضت", clear="الذاكرة رجعت", now=NOW)
        assert m is None
    s, m = alerts.step(s, "mem", bad=False, start="x", clear="الذاكرة رجعت", now=NOW)
    assert m == "الذاكرة رجعت"
    s, m = alerts.step(s, "mem", bad=False, start="x", clear="الذاكرة رجعت", now=NOW)
    assert m is None


def _health(**chains):
    h = {c: {"ok": True, "prices_degraded": False} for c in alerts.CHAINS}
    h.update(chains)
    return h


def test_health_alerts_only_on_change():
    s = {}
    s, line = alerts.health_line(s, _health(cinemacity={"ok": True, "prices_degraded": True}), NOW)
    assert "cinemacity: الأسعار ناقصة" in line
    s, line = alerts.health_line(s, _health(cinemacity={"ok": True, "prices_degraded": True}), NOW)
    assert line == ""
    # a different state for the same chain is news; a new error text for the same state is not
    s, line = alerts.health_line(s, _health(cinemacity={"ok": False, "error": "timed out after 720s"}), NOW)
    assert "cinemacity: فشل" in line
    s, line = alerts.health_line(s, _health(cinemacity={"ok": False, "error": "HTTP 503"}), NOW)
    assert line == ""
    s, line = alerts.health_line(s, _health(), NOW)
    assert "cinemacity" in line and "رجع" in line
    s, line = alerts.health_line(s, _health(), NOW)
    assert line == ""


def test_a_reused_chain_neither_raises_nor_clears_its_alert():
    s = {}
    s, _ = alerts.health_line(s, _health(vox={"ok": True, "prices_degraded": True}), NOW)
    s, line = alerts.health_line(s, _health(vox={"ok": True, "prices_degraded": False, "reused": True}), NOW)
    assert line == "" and s["chain:vox"]["sig"] == "degraded"
    s2, line = alerts.health_line({}, _health(star={"ok": True, "prices_degraded": True, "reused": True}), NOW)
    assert line == "" and "chain:star" not in s2


def test_secondary_failures_are_state_change_too():
    s = {}
    s, line = alerts.health_line(s, _health(verdicts={"ok": False, "error": "rate limit"}), NOW)
    assert "(ثانوي)" in line and "verdicts" in line
    s, line = alerts.health_line(s, _health(verdicts={"ok": False, "error": "other"}), NOW)
    assert line == ""


def test_the_cli_persists_state_and_survives_corruption(tmp_path):
    env = {**os.environ, "CINEMA_ALERT_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "alerts.py"), *a], env=env,
                                    capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    assert run("cond", "mem", "--bad", "ما فضت", "--clear", "رجعت") == "ما فضت"
    assert run("cond", "mem", "--bad", "ما فضت", "--clear", "رجعت") == ""
    assert json.loads((tmp_path / "alert_state.json").read_text(encoding="utf-8"))["mem"]["sig"] == "bad"
    (tmp_path / "alert_state.json").write_text("{broken", encoding="utf-8")
    # corrupt state falls back to the last good copy: still "already alerted", no repeat
    run("cond", "tests", "--ok", "--clear", "رجعت")  # a write that rotates the backup first
    (tmp_path / "alert_state.json").write_text("{broken", encoding="utf-8")
    assert run("cond", "mem", "--bad", "ما فضت", "--clear", "رجعت") == ""
    assert list(tmp_path.glob("alert_state.json.corrupt-*"))
    assert run("cond", "mem", "--ok", "--clear", "رجعت") == "رجعت"
    (tmp_path / "health.json").write_text(json.dumps(_health(roxy={"ok": False, "error": "x"})), encoding="utf-8")
    assert "roxy" in run("health", str(tmp_path / "health.json"))
    assert run("health", str(tmp_path / "health.json")) == ""


# ================================================================ the scripts wire it in

def test_run_sh_routes_every_notification_through_alert_state():
    sh = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert "alerts.py" in sh and "alert health data/health.json" in sh
    assert re.search(r"^ok_now mem ", sh, re.M) and "ok_now() { local m; m=$(alert cond \"$1\" --ok" in sh
    assert "3-hour" not in sh


def test_a_failed_pull_stops_the_run_and_alerts():
    """final review M3: `git pull --ff-only` failing (EOL-dirty files, a diverged checkout) used to log a
    WARN and deploy the old code as if it were the release. It must go through fail() -- one alert via
    alerts.py, a non-zero exit -- before the test gate, refresh or deploy can run.
    Manual check (docs/CUTOVER-PHASE2.md §2): in a clone with no upstream, `bash run.sh` prints
    "FAILED: git pull ..." and exits 7."""
    sh = (ROOT / "run.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in sh.splitlines() if not l.strip().startswith("#"))
    m = re.search(r"if ! git pull --ff-only --autostash -q; then\n(.*?)\nfi", code, re.S)
    assert m, "the pull must be checked"
    assert re.match(r"\s*fail \".*\" 7 pull$", m.group(1)), m.group(1)
    assert "WARN: git pull" not in code
    assert code.index("git pull --ff-only") < code.index("-m pytest") < code.index("refresh.py") < code.index("./deploy.sh")
    assert "ok_now pull " in code


def test_wire_cloudfront_is_gone():
    assert not (ROOT / "wire_cloudfront.py").exists()
    live = [*ROOT.glob("*.py"), *ROOT.glob("*.sh"), *ROOT.glob("infra/*"), *ROOT.glob(".github/**/*.yml"),
            ROOT / "docs" / "CUTOVER.md"]   # historical plans/ledgers keep their record
    for p in live:
        if p.is_file():
            assert "wire_cloudfront" not in p.read_text(encoding="utf-8", errors="ignore"), p
