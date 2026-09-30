"""Task A1 (ops): degraded state + a freeze alert at once, then a reminder every 6h while it lasts.

Ruling parked in docs/CUTOVER.md §6: an already-alerted ongoing failure used to exit 0, so
run-job.sh's state/<job>.state read "ok" for a job that was, in truth, still broken. Fixed by:
run.sh's fail() now exits $DEGRADED_RC (78, "DEGRADED") instead of 0 for a condition that is
already alerted and still bad -- logging the condition + its since-time. A fresh alert (the first
time a condition turns bad) still exits its real code (6 tests, 7 pull, 3 deploy, refresh.py's own
rc) and stamps nothing -- it is only a possible blip. Item 291 (2026-09-30): the very next run, if
still broken, is the SECOND run in a row -- a confirmed freeze -- so remind_once() (data/.reminded-
<key> now holds epoch seconds, not a date) fires AT ONCE on its first call for that key, then
throttles to at most one reminder per 6 hours while the freeze persists (raised from once per
Asia/Dubai calendar day, which could leave up to ~24h of silence between reminders -- a real
20-hour freeze went unnoticed that way). ok_now() gives one "recovered" note and drops the marker,
so a future recurrence of the same key starts a fresh cycle. run-job.sh's finish() treats rc==78 as
a third state (degraded): it records status=degraded in state/<job>.state and does NOT notify (the
job already handled its own alert), so an hourly cinema tick never repeats the same failure
notification every run.

This suite runs run.sh for real (bash subprocess) against a throwaway sandbox: a self-contained git
repo (a local "origin" so `git pull --ff-only` is a trivial no-op success), stub deploy.sh/refresh.py/
posters.py (always succeed -- these tests are about the tests-gate/pull/mem conditions, not about
refresh or deploy themselves), a toggleable failing pytest file for the "tests" gate, and a fake
`flock` on PATH (the dev boxes this suite runs on may not ship one; run.sh only needs "one instance at
a time", never exercised across parallel processes here).
"""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Windows also has a WSL `bash.exe` and a WindowsApps store-install stub earlier or later on PATH
# depending on how the shell that started this test resolved it; run.sh needs an actual POSIX
# shell with a Windows-path view (Git's), so pin it explicitly rather than trust bare "bash"/"git".
BASH = shutil.which("bash.exe", path="C:/Program Files/Git/bin") or shutil.which("bash") or "bash"
GIT = shutil.which("git.exe", path="C:/Program Files/Git/cmd") or shutil.which("git") or "git"


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def sandbox(tmp_path):
    """A throwaway saas/cinema-shaped checkout that bash run.sh can actually execute."""
    for name in ("run.sh", "alerts.py", "statefile.py"):
        shutil.copy(ROOT / name, tmp_path / name)
    _make_executable(tmp_path / "run.sh")

    # stub the other pipeline stages: this suite is about the tests/pull/mem conditions, not
    # about refresh.py or deploy.sh themselves
    (tmp_path / "refresh.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    (tmp_path / "posters.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8"
    )
    deploy = tmp_path / "deploy.sh"
    deploy.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    _make_executable(deploy)

    # verdicts/ must exist and be trackable (empty) so run.sh's commit_verdicts() finds nothing new
    # instead of a real error (a "git" secondary alert unrelated to what these tests check)
    (tmp_path / "verdicts").mkdir()
    (tmp_path / "verdicts" / ".gitkeep").write_text("", encoding="utf-8")

    # a fake `flock` on PATH: the dev machine running this suite may not ship one, and run.sh's
    # single-instance lock is not what these tests are about
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_flock = bin_dir / ("flock.exe" if os.name == "nt" and False else "flock")
    fake_flock.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    _make_executable(fake_flock)

    # C2 (final review): never the production log nor the real notify mechanism, on any machine --
    # run.sh refuses to start under pytest without both (test_run_sh_refuses_under_pytest_without_the_overrides)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
           "CINEMA_LOG_DIR": (tmp_path / "data").as_posix(),
           "CINEMA_ENV_SH": (tmp_path / "no-such-termux-env.sh").as_posix()}
    env.pop("CINEMA_PIP_INSTALL", None)
    env.pop("ELYOXE_JOB", None)   # the Fold's own run sets it; the sandbox behaves the same everywhere
    run = lambda *a: subprocess.run(
        [GIT, *a], cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8",
    )
    run("init", "-q")
    run("config", "user.email", "t@t.example")
    run("config", "user.name", "t")
    run("config", "pull.rebase", "false")  # a global pull.rebase=true on this machine must not apply here
    # test_gate.py is tracked and committed ONCE, never edited again: toggling pass/fail through an
    # untracked marker file (below) keeps the working tree clean, so it never fights `git pull`
    # for reasons unrelated to what these tests check.
    (tmp_path / "test_gate.py").write_text(
        "import os\ndef test_gate():\n    assert not os.path.exists('FAIL_TESTS')\n", encoding="utf-8"
    )
    r = run("add", "-A")
    assert r.returncode == 0, r.stderr
    r = run("commit", "-q", "-m", "init")
    assert r.returncode == 0, r.stderr
    r = run("remote", "add", "origin", str(tmp_path))  # a local "origin": pull is a trivial no-op
    assert r.returncode == 0, r.stderr
    r = run("branch", "--show-current")
    branch = r.stdout.strip() or "master"
    run("fetch", "-q", "origin")
    r = run("branch", f"--set-upstream-to=origin/{branch}", branch)
    assert r.returncode == 0, r.stderr

    return tmp_path, env


def set_tests(sandbox_dir: Path, passing: bool) -> None:
    """Toggle the "tests" gate without touching a tracked file (git-dirtiness would fail `git pull`
    for reasons unrelated to what these tests check)."""
    marker = sandbox_dir / "FAIL_TESTS"
    if passing:
        marker.unlink(missing_ok=True)
    else:
        marker.write_text("", encoding="utf-8")


def run_cinema(sandbox, force_python=None):
    tmp_path, env = sandbox
    run_env = dict(env)
    if force_python:
        run_env["PY"] = force_python
    r = subprocess.run([BASH, "run.sh"], cwd=tmp_path, env=run_env,
                        capture_output=True, text=True, encoding="utf-8")
    log = (tmp_path / "data" / "cinema.log")
    return r.returncode, (r.stdout + r.stderr), (log.read_text(encoding="utf-8") if log.exists() else "")


def alert_state(sandbox):
    tmp_path, _ = sandbox
    p = tmp_path / "data" / "alert_state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def reminded_marker(sandbox, key):
    tmp_path, _ = sandbox
    p = tmp_path / "data" / f".reminded-{key}"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


# ================================================================ fresh failure

def test_a_fresh_test_failure_exits_6_and_alerts_once(sandbox):
    set_tests(sandbox[0], passing=False)
    rc, out, log = run_cinema(sandbox)
    assert rc == 6, out
    assert "FAILED: الاختبارات فشلت" in log
    assert alert_state(sandbox)["tests"]["sig"] == "bad"
    # item 291: a single fresh failure is only a possible blip, not a confirmed freeze -- no
    # reminder marker is stamped yet (that belongs solely to remind_once, so a still-broken run
    # right after this one alerts AT ONCE instead of the marker already looking "covered")
    assert reminded_marker(sandbox, "tests") is None


# ================================================================ degraded, not ok

def test_an_ongoing_failure_is_degraded_not_ok_or_a_repeat_failure(sandbox):
    """The exact bug the ruling closes: a second run of the same still-broken condition used to
    exit 0 (read as "ok" by run-job.sh). It must now exit 78 (DEGRADED) -- neither 0 nor the
    original 6 -- and log the condition with its since-time."""
    set_tests(sandbox[0], passing=False)
    run_cinema(sandbox)                       # run 1: fresh alert
    since_after_first = alert_state(sandbox)["tests"]["since"]

    rc, out, log = run_cinema(sandbox)        # run 2: still broken, already alerted
    assert rc == 78, out
    assert "DEGRADED: tests" in log
    assert since_after_first in log           # the since-time is recorded, not just "still broken"
    # the condition is unchanged (same sig/since) -- alerts.py's own state never repeats itself
    assert alert_state(sandbox)["tests"] == {"sig": "bad", "since": since_after_first}


# ================================================================ item 291: freeze alert at once, then every 6h

def test_a_freeze_confirmed_twice_in_a_row_alerts_at_once(sandbox):
    """The behaviour change: the SECOND consecutive bad run (the one that first proves this is a
    real freeze, not a one-off blip) must notify immediately -- not wait for a marker that the old
    calendar-day scheme had already (wrongly) pre-stamped on the very first, fresh failure."""
    set_tests(sandbox[0], passing=False)
    run_cinema(sandbox)                                    # run 1: fresh alert, no marker yet

    rc, out, log = run_cinema(sandbox)                     # run 2: still broken -- twice in a row
    assert rc == 78, out
    assert "notify (unavailable): سينما ⚠ — سينما: بعده" in log
    assert "من " in log                                    # "<condition> من <since>" -- the template shape
    assert reminded_marker(sandbox, "tests") is not None    # the freeze reminder cycle started now


def test_a_reminder_does_not_repeat_within_6_hours(sandbox):
    set_tests(sandbox[0], passing=False)
    run_cinema(sandbox)                                    # run 1: fresh
    _, _, log_after_second = run_cinema(sandbox)            # run 2: freeze confirmed, alerts at once
    stamped_after_second = reminded_marker(sandbox, "tests")

    rc, out, log = run_cinema(sandbox)                      # run 3, minutes later: still < 6h
    assert rc == 78, out
    new_lines = log[len(log_after_second):] if log.startswith(log_after_second) else log
    assert "بعده" not in new_lines
    assert reminded_marker(sandbox, "tests") == stamped_after_second


def test_a_reminder_fires_again_once_6_hours_have_passed(sandbox):
    tmp_path, _ = sandbox
    set_tests(tmp_path, passing=False)
    run_cinema(sandbox)                                    # run 1: fresh
    run_cinema(sandbox)                                    # run 2: freeze confirmed, alerts at once
    old_marker = int(reminded_marker(sandbox, "tests"))
    # simulate 6h + 1s having passed since the last reminder
    (tmp_path / "data" / ".reminded-tests").write_text(str(old_marker - 21601), encoding="utf-8")

    rc, out, log = run_cinema(sandbox)
    assert rc == 78, out
    assert "notify (unavailable): سينما ⚠ — سينما: بعده" in log
    new_marker = int(reminded_marker(sandbox, "tests"))
    assert new_marker > old_marker - 21601                 # the marker actually advanced

    # and it stays quiet again right after (< 6h since this new reminder)
    log_before = log
    rc2, out2, log2 = run_cinema(sandbox)
    assert rc2 == 78
    new_lines = log2[len(log_before):] if log2.startswith(log_before) else log2
    assert "بعده" not in new_lines
    assert int(reminded_marker(sandbox, "tests")) == new_marker


# ================================================================ recovery

def test_recovery_notifies_once_and_clears_the_marker(sandbox):
    set_tests(sandbox[0], passing=False)
    run_cinema(sandbox)                                    # fresh failure
    run_cinema(sandbox)                                    # degraded
    assert reminded_marker(sandbox, "tests") is not None

    set_tests(sandbox[0], passing=True)
    rc, out, log = run_cinema(sandbox)
    assert rc == 0, out
    assert "رجعت خضراء" in log or "الاختبارات رجعت خضراء" in log
    assert "tests" not in alert_state(sandbox)
    assert reminded_marker(sandbox, "tests") is None       # a future recurrence starts a fresh cycle

    # and a further green run stays quiet (ok_now only speaks on the clear itself)
    rc2, out2, log2 = run_cinema(sandbox)
    assert rc2 == 0, out2
    assert "الاختبارات رجعت خضراء" not in log2[len(log):] if log2.startswith(log) else True


# ================================================================ the same mechanism covers pull

def test_a_second_failed_pull_is_also_degraded_not_a_repeat_alert(sandbox):
    """git pull fails every time here (no ref to pull, once the local commit has moved past what
    origin has) -- proving fail()'s degraded path is the SAME code for every key run.sh uses it
    for (pull/tests/refresh/deploy), not a one-off special case for "tests"."""
    tmp_path, env = sandbox
    # make origin unreachable as a ref: point it at a nonexistent remote path
    subprocess.run([GIT, "remote", "set-url", "origin", str(tmp_path / "does-not-exist")],
                    cwd=tmp_path, env=env, capture_output=True, text=True)

    rc, out, log = run_cinema(sandbox)
    assert rc == 7, out
    assert "FAILED: git pull" in log

    rc2, out2, log2 = run_cinema(sandbox)
    assert rc2 == 78, out2
    assert "DEGRADED: pull" in log2


# ================================================================ C2: never the real log / notify

def test_run_sh_refuses_under_pytest_without_the_overrides(sandbox):
    """The guard: a test that runs run.sh without CINEMA_LOG_DIR/CINEMA_ENV_SH (so it would append to the
    Fold's production cinema.log and source the real notify) is stopped at the door, before any log line."""
    tmp_path, env = sandbox
    for missing in ("CINEMA_LOG_DIR", "CINEMA_ENV_SH"):
        bare = {k: v for k, v in env.items() if k != missing}
        bare["PYTEST_CURRENT_TEST"] = os.environ.get("PYTEST_CURRENT_TEST", "guard")
        r = subprocess.run([BASH, "run.sh"], cwd=tmp_path, env=bare, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 64, r.stdout + r.stderr
        assert "refusing" in r.stderr
        assert not (tmp_path / "data" / "cinema.log").exists()


def test_the_sandbox_log_is_the_temp_one_and_notify_is_unavailable(sandbox):
    set_tests(sandbox[0], passing=False)
    rc, out, log = run_cinema(sandbox)
    assert rc == 6
    assert "FAILED: الاختبارات فشلت" in log                 # written to <tmp>/data/cinema.log, nowhere else
    assert "notify (unavailable): سينما ✗" in log           # CINEMA_ENV_SH points nowhere: no real notify


# ================================================================ C1: requirements self-heal

def _fake_pip(tmp_path, fail=False):
    calls = tmp_path / "pip-calls"
    script = tmp_path / "fakepip.sh"
    script.write_text(f'#!/usr/bin/env bash\necho call >> "{calls.as_posix()}"\nexit {1 if fail else 0}\n',
                      encoding="utf-8")
    return f"bash {script.as_posix()}", calls


def _pip_calls(calls):
    return len(calls.read_text(encoding="utf-8").splitlines()) if calls.exists() else 0


def test_requirements_install_runs_once_per_change_and_records_the_hash(sandbox):
    tmp_path, env = sandbox
    set_tests(tmp_path, passing=True)
    cmd, calls = _fake_pip(tmp_path)
    env["CINEMA_PIP_INSTALL"] = cmd
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")

    rc, out, log = run_cinema(sandbox)                       # no data/.req-hash yet: install
    assert rc == 0, out
    assert _pip_calls(calls) == 1
    h1 = (tmp_path / "data" / ".req-hash").read_text(encoding="utf-8").strip()
    assert len(h1) == 64

    rc, out, _ = run_cinema(sandbox)                         # unchanged: no install
    assert rc == 0, out
    assert _pip_calls(calls) == 1

    (tmp_path / "requirements.txt").write_text("requests\nfonttools\nbrotli\n", encoding="utf-8")
    rc, out, _ = run_cinema(sandbox)                         # changed: install again, new hash
    assert rc == 0, out
    assert _pip_calls(calls) == 2
    assert (tmp_path / "data" / ".req-hash").read_text(encoding="utf-8").strip() != h1


def test_a_failed_install_stops_before_tests_and_keeps_the_old_hash(sandbox):
    tmp_path, env = sandbox
    set_tests(tmp_path, passing=True)
    cmd, calls = _fake_pip(tmp_path, fail=True)
    env["CINEMA_PIP_INSTALL"] = cmd
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")

    rc, out, log = run_cinema(sandbox)
    assert rc == 5, out
    assert "FAILED: pip install" in log
    assert not (tmp_path / "data" / ".req-hash").exists()    # never recorded as installed
    assert "== cinema run done" not in log

    rc2, out2, log2 = run_cinema(sandbox)                    # still failing: degraded, retried every run
    assert rc2 == 78, out2
    assert _pip_calls(calls) == 2
    assert "DEGRADED: deps" in log2

    cmd_ok, _ = _fake_pip(tmp_path)                          # fixed: installs, records, recovers
    env["CINEMA_PIP_INSTALL"] = cmd_ok
    rc3, out3, _ = run_cinema(sandbox)
    assert rc3 == 0, out3
    assert (tmp_path / "data" / ".req-hash").exists()
    assert "deps" not in alert_state(sandbox)
