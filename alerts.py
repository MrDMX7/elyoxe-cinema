"""alerts.py — notify on a change of state, not on every run (stdlib only).

An hourly job turns a standing condition (a chain's prices degraded all day, the phone busy with
Chromium) into 24 identical notifications. Every alert of the cinema job goes through here instead:
a condition notifies when it starts, once more when it clears, and never in between. State lives in
data/alert_state.json (atomic, corruption-safe like film_history.json: a corrupt file is kept for
forensics and the last good copy is used).

State: {key: {"sig": str, "since": iso}} for every condition that is currently bad; a key is removed
when it clears. "sig" is the kind of trouble ("failed", "degraded", "bad"), never the error text --
a timeout that becomes an HTTP 503 is the same standing failure, not news.

CLI (prints the notification body to send, or nothing; exit 0 always unless misused):
  python alerts.py health [data/health.json]           per-chain + secondary conditions of this run
  python alerts.py cond KEY --bad MSG [--clear MSG]    a named condition is present
  python alerts.py cond KEY --ok [--clear MSG]         a named condition is absent
CINEMA_ALERT_DIR overrides the directory holding alert_state.json (tests).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from statefile import load_state_json, write_state_json

ROOT = Path(__file__).resolve().parent
CHAINS = ("vox", "star", "cineroyal", "novo", "reel", "roxy", "cinemacity")


def _dir() -> Path:
    return Path(os.environ.get("CINEMA_ALERT_DIR") or ROOT / "data")


def _now() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=4))).isoformat(timespec="seconds")


def step(state: dict, key: str, bad: bool, start: str, clear: str | None, now: str, sig: str = "bad"):
    """One condition's transition. Returns (new_state, message or None).
    Starts (absent -> bad) and changes of kind (degraded -> failed) return `start`; clearing
    (bad -> absent) returns `clear` (None: clear silently); anything else returns None."""
    state = dict(state)
    prev = state.get(key)
    if bad:
        if prev and prev.get("sig") == sig:
            return state, None
        state[key] = {"sig": sig, "since": now}
        return state, start
    if prev is None:
        return state, None
    del state[key]
    return state, clear


def health_line(state: dict, health: dict, now: str):
    """This run's health.json against the alert state -> (new_state, notification line or "").
    A chain served from a resumed raw file (health[c]["reused"]) says nothing new about the chain:
    its condition is left exactly as it was, neither raised nor cleared."""
    main, low = [], []
    for c in CHAINS:
        v = health.get(c)
        if not isinstance(v, dict) or v.get("reused"):
            continue
        if not v.get("ok"):
            state, m = step(state, f"chain:{c}", True, f"{c}: فشل ({(v.get('error') or 'ما انقرأ')[:60]})", None, now, "failed")
        elif v.get("prices_degraded"):
            state, m = step(state, f"chain:{c}", True, f"{c}: الأسعار ناقصة", None, now, "degraded")
        else:
            state, m = step(state, f"chain:{c}", False, "", f"{c}: رجع طبيعي", now)
        if m:
            main.append(m)
    for k, v in sorted(health.items()):   # enrich / verdicts / posters: lower priority (the site still deployed)
        if k in CHAINS or not isinstance(v, dict):
            continue
        state, m = step(state, f"aux:{k}", v.get("ok") is False, f"{k}: {(v.get('error') or 'فشل')[:60]}",
                        f"{k}: رجع طبيعي", now, "failed")
        if m:
            low.append(m)
    return state, " · ".join(main + ([f"(ثانوي) {' · '.join(low)}"] if low else []))


def _load() -> dict:
    d = _dir()
    data, _ = load_state_json(d / "alert_state.json", d / "alert_state.prev.json")
    return data if isinstance(data, dict) else {}


def _save(state: dict) -> None:
    d = _dir()
    write_state_json(d / "alert_state.json", d / "alert_state.prev.json", state)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("health")
    h.add_argument("path", nargs="?", default=str(ROOT / "data" / "health.json"))
    c = sub.add_parser("cond")
    c.add_argument("key")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--bad", metavar="MSG")
    g.add_argument("--ok", action="store_true")
    c.add_argument("--clear", metavar="MSG")
    a = ap.parse_args(argv)

    state, now = _load(), _now()
    if a.cmd == "health":
        try:
            health = json.loads(Path(a.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"alerts: health.json unreadable: {e}", file=sys.stderr)
            return 0
        state, out = health_line(state, health, now)
    else:
        state, out = step(state, a.key, a.bad is not None, a.bad or "", a.clear, now)
    _save(state)
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
