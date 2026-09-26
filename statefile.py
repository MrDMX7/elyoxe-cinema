"""statefile.py — corruption-safe JSON state files (stdlib only, so the chroot's system python3 can
import it from run-job.sh as well as the venv).

film_history.json, price_cache.json and alert_state.json are the files a run's own past depends on.
Policy for all of them: never trust a file that fails to parse, keep it around for forensics instead
of overwriting it, fall back to the last known good copy, and if there isn't one, say so explicitly
rather than merely returning `{}`.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_state_json(path: Path, backup_path: Path) -> tuple[dict | None, str]:
    """Load a state JSON file, tolerating corruption. Returns (data, status):
      "missing"   -- `path` doesn't exist (data is None) -- a genuinely first run.
      "ok"        -- `path` parsed fine (data is its content).
      "restored"  -- `path` was corrupt (renamed to "<name>.corrupt-<timestamp>", kept on disk)
                     and `backup_path` parsed fine (data is the backup's content).
      "no_backup" -- `path` was corrupt and `backup_path` is missing or also corrupt (data is
                     None) -- callers must treat this the same as "missing" for any purpose that
                     depends on the file's *history*, since none of it can be trusted.
    Never raises: a corrupt file is renamed, not deleted, and any OSError renaming it is itself
    swallowed (the corrupt bytes just stay at their original path instead) so a full disk or a
    permissions quirk can't turn a bad-JSON problem into a crashed run.
    """
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "ok"
    except (OSError, json.JSONDecodeError) as e:
        corrupt_path = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%dT%H%M%S')}")
        try:
            path.rename(corrupt_path)
        except OSError:
            corrupt_path = path
        print(f"{path.name} was corrupt ({e}) -- kept at {corrupt_path.name}", file=sys.stderr)
        if backup_path.exists():
            try:
                return json.loads(backup_path.read_text(encoding="utf-8")), "restored"
            except (OSError, json.JSONDecodeError):
                pass
        return None, "no_backup"


def write_state_json(path: Path, backup_path: Path, data) -> None:
    """Atomic write of `data` to `path`, first rotating `path`'s *current* content into
    `backup_path` -- but only when that current content is itself valid JSON, so a corrupt file
    is never promoted into "the backup" a future corruption would restore from. One generation
    back is all this keeps: enough to survive a single bad write/read."""
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            json.loads(text)  # only rotate a file that's actually good
        except (OSError, json.JSONDecodeError):
            pass
        else:
            try:
                write_json_atomic(backup_path, json.loads(text))
            except OSError:
                pass
    write_json_atomic(path, data)
