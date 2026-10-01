"""refresh.py — orchestrate the 7 chain readers into data/latest.json + per-city slices.

CLI: python refresh.py [--chains vox,star,...] [--offline] [--no-verdicts] [--days 2] [--force]

Per chain, in its own daemon thread with a wall-clock timeout (a hung fetch becomes a
failure, never blocks the others or the process exit): fetch() -> raw {"cinemas","shows"} ->
written to data/raw/<chain>.json as soon as it finishes, so a killed run resumes (only a raw file
tagged with the id of the unfinished run in data/raw/.run.json is reused, and only within
RESUME_WINDOW; a completed run removes the marker, so every run after it fetches afresh; --force
never resumes) -> price_table
fills any still-null prices from prices.yaml. The per-chain results are then merge()d against
the previous data/latest.json (a chain that failed or wasn't run this time keeps its previous
cinemas/shows, marked stale — see normalize.merge), enrich()ed (hits the network unless
--offline), and — unless --offline or --no-verdicts — verdicts.write_missing() fills in any
new film's verdict. Every film that has a verdicts/<fid>.json (written just now or long ago)
gets it attached as data["films"][fid]["verdict"], exactly what build.py reads.

Neither enrich nor verdicts can abort the publish: both are wrapped, their failures printed
to stderr and recorded into data/health.json (keys "enrich"/"verdicts": {ok, error, ...}) —
latest.json is still written with whatever enrichment/verdicts already succeeded. verdicts is
additionally isolated per film (write_missing() is called once per film, not once for the
whole batch) so one film hitting a rate limit or exhausting its dialect-compliance retries
doesn't stop every other film's verdict from being generated.

data/latest.json and data/<city>.json (normalize.city_slices) are written atomically
(tmp + os.replace). data/health.json is {chain: {ok, at, error, shows}, "enrich": {...},
"verdicts": {...}} for the notifier. Exit code: 0 if at least one requested *chain* is ok
(enrich/verdicts failures alone never flip this to 1 — they degrade, not abort), 1 if every
chain failed.

--offline: no reader is ever called — fixtures/<chain>.json stand in for the raw fetch (used
by the tests, and for a local build with no network).
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import enrich as enrich_mod
import normalize
import price_table
import verdicts as verdicts_mod
from statefile import load_state_json, write_json_atomic, write_state_json
from readers import cinemacity, cineroyal, novo, reel, roxy, star, vox

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
FIXTURES_DIR = ROOT / "fixtures"
LATEST_PATH = DATA_DIR / "latest.json"
HEALTH_PATH = DATA_DIR / "health.json"
FILMS_CACHE_PATH = DATA_DIR / "films_cache.json"
FILM_HISTORY_PATH = DATA_DIR / "film_history.json"
FILM_HISTORY_BACKUP_PATH = DATA_DIR / "film_history.prev.json"
PRICE_CACHE_PATH = DATA_DIR / "price_cache.json"
PRICE_CACHE_BACKUP_PATH = DATA_DIR / "price_cache.prev.json"
NEW_FILMS_PATH = DATA_DIR / "new_films.json"

CHAIN_READERS = {
    "vox": vox.fetch,
    "star": star.fetch,
    "cineroyal": cineroyal.fetch,
    "novo": novo.fetch,
    "reel": reel.fetch,
    "roxy": roxy.fetch,
    "cinemacity": cinemacity.fetch,
}
ALL_CHAINS = list(CHAIN_READERS)
# chains whose reader accepts a `cache=` kwarg (readers/common.py cache_get/cache_set) to reuse a
# same-day seat-map/price sample across runs instead of re-requesting it every hour.
PRICE_CACHE_CHAINS = {"vox", "star", "cineroyal", "novo", "cinemacity", "reel", "roxy"}
# owner's ruling (final review, 2026-09-27): archive only after the film has been confirmed absent from
# every chain that listed it for >= 5 days of successful runs -- time, not run counts (hourly runs).
ARCHIVE_AFTER_ABSENT = timedelta(days=5)
LEGACY_ARCHIVED_RUNS = 2  # a history record from the run-count rule with absent_runs >= this was archived

DEFAULT_TIMEOUT = 8 * 60.0
# Prices are sampled once per cinema x hall x show DATE (weekday/weekend prices differ), so the
# chains that sample doubled their request count on 2026-09-26. Measured on the Fold before that:
# VOX ~490 s (one showtimes page per cinema per day + ~80 seat-map samples, now ~160), Star ~185 s.
# cineroyal already sampled per day. Roxy started sampling (seat-selection page, no login needed)
# on 2026-09-27 -- one extra request per cinema x hall x date on top of its existing ajax calls.
CHAIN_TIMEOUTS = {"vox": 30 * 60.0, "star": 15 * 60.0, "reel": 15 * 60.0, "novo": 12 * 60.0, "cinemacity": 12 * 60.0}
# a killed run is resumed from its own raw files only if it started this recently (else start over)
RESUME_WINDOW = timedelta(hours=2)
DUBAI_TZ = ZoneInfo("Asia/Dubai")
PRICES_DEGRADED_THRESHOLD = 0.5  # priced/attempted below this -> health[chain]["prices_degraded"]


def now_iso() -> str:
    """Current time in Asia/Dubai, ISO 8601 with offset."""
    import datetime as _dt

    return _dt.datetime.now(DUBAI_TZ).isoformat()


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# corruption-safe state files (film_history.json, price_cache.json): see statefile.py
_write_json_atomic = write_json_atomic
_load_state_json = load_state_json
_write_state_json = write_state_json


def _raw_path(chain: str) -> Path:
    return RAW_DIR / f"{chain}.json"


# ---------------------------------------------------------------- resume, never reuse across runs
# data/raw/.run.json = {"id", "started"} is written when a run starts and removed when it finishes.
# Each raw file a run writes carries that run's id ("_run_id"). A raw file is reused only when the
# marker is still there (the previous run was killed before finishing), it started less than
# RESUME_WINDOW ago, and the raw carries *its* id -- i.e. only to resume that unfinished run. A
# completed run leaves no marker, so the next hourly run always fetches every chain afresh.

def _run_marker_path() -> Path:
    return RAW_DIR / ".run.json"


def _start_run(now: str, force: bool) -> tuple[str, bool]:
    """(run id, resuming?) -- resumes an unfinished run's id when its marker is recent, else starts one."""
    marker = None if force else _load_json(_run_marker_path())
    if isinstance(marker, dict) and marker.get("id") and marker.get("started"):
        try:
            age = datetime.fromisoformat(now) - datetime.fromisoformat(marker["started"])
        except (TypeError, ValueError):
            age = None
        if age is not None and timedelta(0) <= age <= RESUME_WINDOW:
            return marker["id"], True
    run_id = uuid.uuid4().hex[:12]
    _write_json_atomic(_run_marker_path(), {"id": run_id, "started": now})
    return run_id, False


def _finish_run() -> None:
    try:
        _run_marker_path().unlink()
    except FileNotFoundError:
        pass


def _resumable_raw(chain: str, run_id: str):
    """The chain's raw fetch from the unfinished run `run_id`, or None (the tag is stripped; `_read_at`, the
    time that fetch finished, stays for the caller to take off)."""
    raw = _load_json(_raw_path(chain))
    if not isinstance(raw, dict) or raw.pop("_run_id", None) != run_id:
        return None
    return raw


# ---------------------------------------------------------------- each chain's own read time (W1-D3)
# data["chains"][chain]["at"] is the time that chain's own read finished, not the run's start: the chains are
# read one after another (a day's first run takes ~30 min), and a chain resumed from a killed run's raw file was
# read up to RESUME_WINDOW earlier. A chain that failed keeps its previous "at" (normalize.merge), so the site can
# say «أسعار ريل من 18:05» on prices older than 2 h (pages/pulse.py) and /sources/ lists seven real times.

def _raw_read_at(raw: dict, run_started: str | None, fallback: str) -> str:
    """When a resumed raw file was read: its own `_read_at` tag (taken off `raw`), else the unfinished run's start
    (a raw written before the tag existed was read after that, so the time is never later than the truth)."""
    at = raw.pop("_read_at", None)
    try:
        return datetime.fromisoformat(at).isoformat() if at else (run_started or fallback)
    except (TypeError, ValueError):
        return run_started or fallback


def apply_read_times(merged: dict, read_at: dict) -> None:
    """Each chain read this run carries its own read time in data["chains"] (and so in every city slice)."""
    for chain, at in read_at.items():
        info = (merged.get("chains") or {}).get(chain)
        if isinstance(info, dict) and info.get("ok"):
            info["at"] = at


# ---------------------------------------------------------------- published signals (W1-D3)

def attach_first_seen(merged: dict, history: dict) -> None:
    """film["first_seen"] = film_history.json's own date for every film (read, never recomputed): the site
    publishes it in /data/pulse.json. Films present at the seeding run all carry the seed date."""
    for fid, film in (merged.get("films") or {}).items():
        first = (history.get(fid) or {}).get("first_seen")
        if first:
            film["first_seen"] = first


def carry_released(merged: dict, previous: dict | None) -> None:
    """film["released"]: the release date a chain's coming-soon list gave the film before it opened, kept while it
    shows (the coming step drops a film once it is showing, and normalize.merge rebuilds films each run)."""
    previous = previous or {}
    prev_films, prev_coming = previous.get("films") or {}, previous.get("coming") or {}
    for fid, film in (merged.get("films") or {}).items():
        if film.get("status") == "archived":
            continue
        rel = (prev_films.get(fid) or {}).get("released") or (prev_coming.get(fid) or {}).get("release_date")
        if isinstance(rel, str) and len(rel) == 10:
            film["released"] = rel


RANK_KEEP_DAYS = 2   # the rank's per-city day reads keep yesterday and later (pages/pulse.py: rank.json)


def day_counts(data: dict) -> dict:
    """{date: {city: {fid: [shows, cinemas]}}} of this read's shows (films only, archived films have none)."""
    cinemas, films = data.get("cinemas") or {}, data.get("films") or {}
    acc: dict = {}
    for s in data.get("shows") or []:
        c, fid, d = cinemas.get(s.get("cinema")), s.get("film"), s.get("date")
        if not c or not c.get("city") or fid not in films or not d:
            continue
        per = acc.setdefault(str(d), {}).setdefault(c["city"], {}).setdefault(fid, [0, set()])
        per[0] += 1
        per[1].add(s["cinema"])
    return {d: {city: {fid: [n, len(cs)] for fid, (n, cs) in sorted(fs.items())} for city, fs in sorted(cities.items())}
            for d, cities in sorted(acc.items())}


def update_rank_days(merged: dict, previous: dict | None, now: str) -> dict:
    """merged["rank_days"] = {date: {city: {fid: [shows, cinemas]}}}: per date and city, the fullest read seen so
    far (the most shows; the first read of a day holds all of it, the hourly runs after it lose the shows already
    played). Carried run to run in latest.json, dates before yesterday dropped. The per-city counts
    price_history.jsonl does not keep (its films are UAE-wide), for rank.json's arrows."""
    keep_from = (_as_time(now).date() - timedelta(days=RANK_KEEP_DAYS - 1)).isoformat()
    prev = (previous or {}).get("rank_days") or {}
    out: dict = {}
    for d, cities in prev.items():
        if isinstance(d, str) and d >= keep_from and isinstance(cities, dict):
            out[d] = {c: dict(v) for c, v in cities.items() if isinstance(v, dict)}
    size = lambda fs: sum(int(v[0]) for v in fs.values())
    for d, cities in day_counts(merged).items():
        if d < keep_from:
            continue
        slot = out.setdefault(d, {})
        for city, fs in cities.items():
            if size(fs) >= size(slot.get(city) or {}):
                slot[city] = fs
    merged["rank_days"] = {d: dict(sorted(v.items())) for d, v in sorted(out.items())}
    return merged["rank_days"]


def _fetch_chain(chain: str, days: int, offline: bool, price_cache: dict | None = None):
    """The raw fetch for one chain: a reader call, or (--offline) its fixture.

    `price_cache`, when given and `chain` is one of PRICE_CACHE_CHAINS, is today's slice of
    data/price_cache.json for this chain -- passed as the reader's own `cache=` kwarg so it can
    reuse an already-sampled cinema x hall x date price instead of requesting it again (mutated
    in place by the reader; refresh() persists it back to disk after the run).
    """
    if offline:
        data = _load_json(FIXTURES_DIR / f"{chain}.json")
        if data is None:
            raise FileNotFoundError(f"no fixture at fixtures/{chain}.json")
        return data
    kwargs = {}
    if price_cache is not None and chain in PRICE_CACHE_CHAINS:
        kwargs["cache"] = price_cache
    return CHAIN_READERS[chain](days=days, **kwargs)


def _run_chain(chain: str, days: int, offline: bool, timeout: float, price_cache: dict | None = None) -> dict:
    """Runs `_fetch_chain` in a daemon thread with a wall-clock timeout.

    A daemon thread (not a ThreadPoolExecutor, whose worker threads are joined at interpreter
    exit) so a genuinely hung reader never blocks this process from finishing or exiting —
    it's simply abandoned once `timeout` elapses, and its result (if it ever arrives) is
    discarded via the queue.
    """
    start = time.monotonic()
    q: queue.Queue = queue.Queue(maxsize=1)

    def worker():
        try:
            q.put(("ok", _fetch_chain(chain, days, offline, price_cache)))
        except Exception as e:  # noqa: BLE001 - a reader failure is data, not a crash
            q.put(("err", e))

    threading.Thread(target=worker, daemon=True).start()
    try:
        status, payload = q.get(timeout=timeout)
    except queue.Empty:
        return {"ok": False, "result": None, "error": f"timed out after {timeout:.0f}s",
                "seconds": time.monotonic() - start}

    seconds = time.monotonic() - start
    if status == "err":
        return {"ok": False, "result": None, "error": str(payload), "seconds": seconds}
    return {"ok": True, "result": payload, "error": None, "seconds": seconds}


def run_steps(data: dict, ctx: dict, steps_dir: Path | None = None) -> dict:
    """Run every steps/<name>.py that defines run(data, ctx), sorted by name, each isolated.
    Returns {name: {"ok", "error", **whatever run returned}} for health.json."""
    import importlib.util
    out = {}
    d = steps_dir or (ROOT / "steps")
    for path in sorted(d.glob("[a-z]*.py")) if d.is_dir() else []:
        name = path.stem
        t0 = time.monotonic()
        try:
            spec = importlib.util.spec_from_file_location(f"steps.{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            extra = mod.run(data, ctx) or {}
            out[name] = {"ok": True, "error": None, **extra}
        except Exception as e:  # noqa: BLE001 - a feature step must degrade, never abort the publish
            out[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            print(f"refresh: step {name} failed: {e}", file=sys.stderr)
        out[name]["sec"] = round(time.monotonic() - t0, 2)
    return out


def _attach_verdicts(data: dict) -> None:
    for fid, film in data.get("films", {}).items():
        verdict = _load_json(verdicts_mod.VERDICTS_DIR / f"{fid}.json")
        if verdict is not None:
            film["verdict"] = verdict


def _write_verdicts_isolated(data: dict) -> dict:
    """Calls verdicts.write_missing() once per film instead of once for the whole batch, so a
    single film's Anthropic API error or exhausted dialect-compliance retries
    (verdicts.py's own RuntimeError after MAX_ATTEMPTS) can't stop every other film's verdict
    from being generated. verdicts.py itself is out of scope for refresh.py's task and is not
    touched — this is the per-film isolation done from the caller's side instead.

    Returns {"ok", "attempted", "succeeded", "failed": [fid, ...], "error": last error str|None}
    — never raises.
    """
    attempted = 0
    succeeded = 0
    failed: list[str] = []
    last_error = None

    for fid, film in list(data.get("films", {}).items()):
        attempted += 1
        try:
            verdicts_mod.write_missing({"films": {fid: film}})
            succeeded += 1
        except Exception as e:  # noqa: BLE001 - one bad film must not stop the others
            failed.append(fid)
            last_error = f"{fid}: {e}"
            print(f"refresh: verdicts for {fid!r} failed: {e}", file=sys.stderr)

    return {"ok": not failed, "attempted": attempted, "succeeded": succeeded,
            "failed": failed, "error": last_error}


def _fix_verdict_text(data: dict) -> dict:
    """W0-P4 (legend §4.1 #36): rewrite only the verdicts whose text spells the film differently from
    the site's title or states another runtime (verdicts.text_mismatches), at most
    verdicts.TEXT_FIX_CAP a run and once per fid per title-and-runtime basis; a fid that still fails
    waits in health["verdict_text"]["unfixed"] instead of looping. Never raises."""
    # the check's memory, data/verdict_fixes.json: {fid: {basis, at, ok}} (resolved at call time, so a
    # test's sandboxed DATA_DIR is honoured)
    path = DATA_DIR / "verdict_fixes.json"
    try:
        state = _load_json(path)
        new_state, report = verdicts_mod.fix_text_mismatches(data, state if isinstance(state, dict) else {},
                                                             today=now_iso()[:10])
        _write_json_atomic(path, new_state)
        return report
    except Exception as e:  # noqa: BLE001 - the check must never abort the publish
        print(f"refresh: verdict text check failed: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


def chain_timeout(chain: str) -> float:
    return CHAIN_TIMEOUTS.get(chain, DEFAULT_TIMEOUT)


# ---------------------------------------------------------------- film history / archive / new-film alert

def _cinema_counts(merged: dict) -> dict[str, int]:
    """{fid: distinct cinema count} from this run's shows -- for the new-film alert line."""
    out: dict[str, set] = {}
    for s in merged.get("shows", []):
        fid = s.get("film")
        if fid:
            out.setdefault(fid, set()).add(s.get("cinema"))
    return {fid: len(cids) for fid, cids in out.items()}


def _as_time(now: str) -> datetime:
    """An ISO timestamp, or a bare date (tests, legacy records) read as that date's noon in Dubai."""
    if len(now) == 10:
        now = f"{now}T12:00:00+04:00"
    t = datetime.fromisoformat(now)
    return t if t.tzinfo else t.replace(tzinfo=DUBAI_TZ)


def _fold_target(old: str, rec: dict, current: dict, alias: dict, members_of: dict) -> str | None:
    """The current canonical fid that film-history record `old` now lives under, if any: through this
    run's merge map / aliases.yaml (followed to its end), else through the members the record
    remembers (the old canonical title may have left every chain, so this run's map can't name it)."""
    t, seen = alias.get(old), set()
    while t and t not in current and t not in seen:
        seen.add(t)
        t = alias.get(t)
    if t in current:
        return t
    known = {old, *(rec.get("members") or [])}
    for c in sorted(current):
        if c in known or members_of.get(c, set()) & known:
            return c
    return None


def update_film_history(merged: dict, history: dict, now: str, fresh_chains=None,
                        aliases: dict | None = None, event_labels: dict | None = None) -> tuple[dict, list[dict]]:
    """Advances film_history.json state for this run and returns (new_history, new_films).
    Mutates `merged`: archived films are added to merged["films"], and merged["redirects"] is set
    to {old fid: canonical fid} for every fid that was folded into another one (build.py writes a
    noindex redirect page for each).

    Record: {first_seen, last_seen (dates), last_seen_at, absent_since (ISO|None), archived (bool),
    chains, members (raw fids merged into it), redirect_from (former canonical fids), snapshot}.

    Rules:
      - Canonical-fid changes (final review I1): normalize.merge_duplicates may pick a different
        canonical fid for the same film from one run to the next. Before anything else, a history
        fid that is not current but maps to a current canonical fid (merged["merged"], `aliases`,
        or the members its record remembers) is folded into it: earliest first_seen, members and
        redirect_from merged, the old record removed -- so the film keeps its first_seen, never
        alerts as new, and the old fid never gets an archive page.
      - Archive (owner's ruling, final review I2): a film absent from `merged["films"]` is archived
        only once it has been *confirmed* absent for ARCHIVE_AFTER_ABSENT (5 days) -- the clock
        (absent_since) starts at the first confirmed absence and must still be confirmed this run.
        "Confirmed" = every chain that ever listed it (all chains of this run when none is recorded)
        is in `fresh_chains`: ok this run *and* freshly fetched -- a chain served from a resumed raw
        file (final review C1) or down/not run proves nothing, so the clock neither starts nor
        completes then. Once archived, a film stays archived (its page kept) until it shows again.
      - new_films: canonical fids not in history (after folding). The caller suppresses the alert
        on the seeding run.
    """
    t_now = _as_time(now)
    now_iso = t_now.isoformat()
    today = now_iso[:10]
    current_films = merged.get("films", {})
    chains_info = merged.get("chains") or {}
    if fresh_chains is None:
        fresh_chains = {c for c, info in chains_info.items() if info.get("ok")}
    fresh_chains = set(fresh_chains)
    counts = _cinema_counts(merged)
    run_map = dict(merged.get("merged") or {})
    alias = {**(aliases or {}), **run_map}
    members_of: dict[str, set] = {}
    for m, c in run_map.items():
        members_of.setdefault(c, set()).add(m)

    hist = {k: dict(v) for k, v in history.items() if isinstance(v, dict)}
    # a not-a-film event (normalize.NOT_A_FILM_KINDS) recorded as a film by an earlier run is dropped:
    # never archived into a film page, never counted as absent (W0-P4, legend §4.1 #32)
    labels = normalize.load_event_labels() if event_labels is None else event_labels
    hist = {k: v for k, v in hist.items()
            if k in current_films or not normalize.event_label(((v.get("snapshot") or {}).get("title")) or "", labels)}

    # 1. fold records whose film now lives under another canonical fid
    for old in sorted(hist):
        if old in current_films or old not in hist:
            continue
        target = _fold_target(old, hist[old], current_films, alias, members_of)
        if not target or target == old:
            continue
        rec = hist.pop(old)
        into = hist.get(target)
        redirect_from = set(rec.get("redirect_from") or []) | {old}
        members = set(rec.get("members") or [])
        if into:
            firsts = [x for x in (into.get("first_seen"), rec.get("first_seen")) if x]
            into["first_seen"] = min(firsts) if firsts else None
            redirect_from |= set(into.get("redirect_from") or [])
            members |= set(into.get("members") or [])
        else:
            into = dict(rec)
        into["redirect_from"] = sorted(redirect_from - {target})
        into["members"] = sorted(members - {target})
        hist[target] = into

    new_history: dict = {}
    new_films: list[dict] = []

    # 2. current films
    for fid, f in current_films.items():
        prev = hist.get(fid)
        if prev is None:
            new_films.append({
                "fid": fid,
                "title": f.get("title") or fid,
                "title_ar": f.get("title_ar") or f.get("title_ar_chain"),
                "cinemas": counts.get(fid, 0),
            })
        prev = prev or {}
        new_history[fid] = {
            "first_seen": prev.get("first_seen") or today,
            "last_seen": today,
            "last_seen_at": now_iso,
            "absent_since": None,
            "archived": False,
            "chains": sorted(set(f.get("chains") or [])) or prev.get("chains") or [],
            "members": sorted((set(prev.get("members") or []) | members_of.get(fid, set())) - {fid}),
            "redirect_from": sorted(set(prev.get("redirect_from") or []) - {fid}),
            "snapshot": {k: v for k, v in f.items() if k != "chains"},
        }

    # 3. absent films: the 5-day clock
    for fid, rec in hist.items():
        if fid in current_films:
            continue
        original = history.get(fid) or {}
        rec = {k: v for k, v in rec.items() if k != "absent_runs"}
        archived = bool(rec.get("archived"))
        absent_since = rec.get("absent_since")
        if "absent_runs" in original and "absent_since" not in original:
            # a record from the run-count rule: an archived one runs its clock from its last showing
            if int(original.get("absent_runs") or 0) >= LEGACY_ARCHIVED_RUNS and rec.get("last_seen"):
                absent_since = _as_time(rec["last_seen"]).replace(hour=0, minute=0, second=0).isoformat()
        listed_by = rec.get("chains") or sorted(chains_info)
        confirmed = bool(listed_by) and all(c in fresh_chains for c in listed_by)
        if confirmed:
            absent_since = absent_since or now_iso
            if t_now - _as_time(absent_since) >= ARCHIVE_AFTER_ABSENT:
                archived = True
        rec.update(absent_since=absent_since, archived=archived)
        new_history[fid] = rec
        if archived:
            snap = dict(rec.get("snapshot") or {})
            snap["status"] = "archived"
            snap["first_seen"] = rec.get("first_seen")
            snap["last_seen"] = rec.get("last_seen")
            snap.setdefault("chains", rec.get("chains") or [])
            current_films[fid] = snap

    redirects = {old: canon for canon, rec in new_history.items() if canon in current_films
                 for old in rec.get("redirect_from") or [] if old != canon and old not in current_films}
    if redirects:
        merged["redirects"] = dict(sorted(redirects.items()))
    else:
        merged.pop("redirects", None)
    return new_history, new_films


def refresh(chains=None, offline: bool = False, no_verdicts: bool = False, days: int = 2,
            force: bool = False, timeout: float | None = None) -> int:
    """Runs the full pipeline once. Returns the process exit code (0 ok, 1 all chains failed).

    `timeout` (seconds) overrides every chain's own wall-clock limit (chain_timeout: CHAIN_TIMEOUTS,
    else 480 s) — the tests use it."""
    chains = list(chains) if chains else list(ALL_CHAINS)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    table = price_table.load()
    previous = _load_json(LATEST_PATH)
    now = now_iso()
    today = now[:10]

    results: dict = {}
    health: dict = {}
    summaries: list[str] = []

    # Price cache (data/price_cache.json): {chain: {date: {key: [{"seat","aed"}]|None}}}. Only
    # today's slice is ever handed to a reader, and only today's slice is ever written back --
    # this *is* the "resets per date" rule: a run on a new calendar date simply starts every
    # chain's cache empty again, ignoring (and dropping) whatever an earlier date left behind.
    # Corruption-safe (fix round 1): losing this file only costs a re-sample, never a crash.
    price_cache_on_disk, price_cache_status = _load_state_json(PRICE_CACHE_PATH, PRICE_CACHE_BACKUP_PATH)
    if price_cache_status == "restored":
        summaries.append("price_cache.json restored from backup after corruption")
    elif price_cache_status == "no_backup":
        summaries.append("price_cache.json corrupt, no backup -- starting empty (re-sampling today)")
    price_cache_on_disk = price_cache_on_disk or {}
    chain_price_caches = {
        c: dict((price_cache_on_disk.get(c) or {}).get(today) or {}) for c in PRICE_CACHE_CHAINS
    }

    # C1 (final review): resume an unfinished run from its own raw files, never reuse across runs
    run_id, resuming = _start_run(now, force)
    run_started = None
    if resuming:
        summaries.append(f"resuming unfinished run {run_id}")
        run_started = (_load_json(_run_marker_path()) or {}).get("started")
    reused: set[str] = set()
    read_at: dict[str, str] = {}   # chain -> when its own read finished (W1-D3)

    for chain in chains:
        cached = _resumable_raw(chain, run_id) if resuming else None
        if cached is not None:
            raw, ok, error, seconds = cached, True, None, 0.0
            reused.add(chain)
            read_at[chain] = _raw_read_at(raw, run_started, now)
        else:
            # fix round 1 (concurrency): hand the reader its OWN copy, never the dict this
            # function later serializes -- an abandoned timeout thread can keep mutating this
            # private copy in the background forever; nothing else ever looks at it again once
            # this call returns not-ok, so it can't race with json.dumps below.
            private_cache = dict(chain_price_caches[chain]) if chain in PRICE_CACHE_CHAINS else None
            outcome = _run_chain(chain, days, offline, timeout if timeout is not None else chain_timeout(chain),
                                  price_cache=private_cache)
            ok, error, seconds, raw = outcome["ok"], outcome["error"], outcome["seconds"], outcome["result"]
            if ok:
                read_at[chain] = now_iso()
                _write_json_atomic(_raw_path(chain), {**raw, "_run_id": run_id, "_read_at": read_at[chain]})
                if private_cache is not None:
                    # only a chain that actually finished within its timeout gets to update the
                    # persisted cache -- an abandoned/timed-out attempt's copy is simply dropped
                    chain_price_caches[chain] = private_cache

        if ok:
            carried = price_table.carry_today(raw, now[:10])
            price_table.fill(raw, table, today=now[:10])
            total = len(raw.get("shows", []))

            # A reader may report its own price accounting via a top-level "price_health"
            # {"attempted","priced","error"} — preferred when present since it can count seat
            # samples the reader tried and failed on, not just shows[].prices. Tolerated as
            # absent (older readers/fixtures): falls back to counting shows[].prices directly.
            # Never copied into `raw` itself past this point, so it can't leak into latest.json
            # (normalize.merge only ever reads raw["cinemas"]/raw["shows"]).
            # A reader that reports price_health with attempted == 0 (e.g. called with
            # prices=False, or every key already cache-hit) is not degraded — nothing was tried.
            reader_price_health = raw.get("price_health") or {}
            if "attempted" in reader_price_health:
                attempted = reader_price_health.get("attempted") or 0
                priced = reader_price_health.get("priced") or 0
            else:
                attempted = total
                priced = sum(1 for s in raw.get("shows", []) if s.get("prices") is not None)
            cached_reused = reader_price_health.get("cached") or 0
            pct = (priced / attempted * 100) if attempted else 0.0
            degraded = bool(attempted > 0 and (priced / attempted) < PRICES_DEGRADED_THRESHOLD)

            results[chain] = raw
            health[chain] = {"ok": True, "at": read_at.get(chain, now), "error": None, "shows": total,
                              "prices_degraded": degraded}
            if carried:
                health[chain]["carried_today"] = carried
            if chain in reused:
                # a resumed raw is this unfinished run's own earlier fetch, not a fresh one: it never
                # counts as a confirmed absence (film history) nor raises/clears an alert (alerts.py)
                health[chain]["reused"] = True
            if reader_price_health:
                # "attempted"/"priced" count network calls this run only -- honest about what
                # actually hit the chain's site; "cached" is same-day samples reused instead
                # (data/price_cache.json), never counted as an "attempt".
                health[chain]["price_health"] = {
                    "attempted": attempted, "priced": priced, "cached": cached_reused,
                    "error": reader_price_health.get("error"),
                }
            summaries.append(
                f"{chain}: ok  cinemas={len(raw.get('cinemas', []))}  shows={total}  "
                f"priced={pct:.0f}%{f'  cached={cached_reused}' if cached_reused else ''}"
                f"{f'  carried_today={carried}' if carried else ''}"
                f"{'  DEGRADED' if degraded else ''}{'  (resumed)' if chain in reused else ''}  {seconds:.1f}s"
            )
        else:
            results[chain] = error
            health[chain] = {"ok": False, "at": now, "error": error, "shows": 0}
            summaries.append(f"{chain}: FAILED  {error}  {seconds:.1f}s")

    # persist today's price samples -- any other date already on disk is dropped here, which is
    # the cache's "resets per date" rule in practice. A dict(v) snapshot per chain: only a
    # finished chain's cache is ever assigned back into chain_price_caches[chain] above, but this
    # copy is cheap insurance against json.dumps iterating a dict some other code still holds a
    # reference to (fix round 1 -- the review's concurrency finding).
    _write_state_json(PRICE_CACHE_PATH, PRICE_CACHE_BACKUP_PATH,
                       {c: {today: dict(v)} for c, v in chain_price_caches.items() if v})

    merged = normalize.merge(results, previous, now)
    apply_read_times(merged, read_at)       # W1-D3: each chain's own read time, not the run's start
    carry_released(merged, previous)

    # W0-P4 (legend §4.1 #31): films whose chains disagree on the runtime by more than
    # normalize.RUNTIME_GAP_MIN minutes -- the film uses the chains' median; the gap is only reported
    gaps = merged.pop("runtime_gaps", [])
    health["runtime"] = {"ok": True, "error": None, "gaps": gaps}
    if gaps:
        summaries.append("runtime: chains disagree by > %d min on %d film(s): " % (normalize.RUNTIME_GAP_MIN, len(gaps))
                         + ", ".join(f"{g['fid']} {g['runtime']} ({' '.join(f'{c}={v}' for c, v in g['chains'].items())})"
                                     for g in gaps))
    if merged.get("event_shows"):
        summaries.append(f"events: {len(merged['event_shows'])} not-a-film session(s) kept out of films (data event_shows)")

    # a film merged into another (normalize.merge_duplicates, aliases.yaml) takes its verdict file
    # with it: moved to the canonical fid when that one has nothing better, else deleted
    try:
        folded = verdicts_mod.fold_merged({**normalize.load_aliases().get("aliases", {}),
                                           **merged.get("merged", {})})
        if folded:
            summaries.append("verdicts folded: " + ", ".join(f"{k} {v}" for k, v in folded.items()))
    except Exception as e:  # noqa: BLE001 - housekeeping must never abort the publish
        print(f"refresh: fold_merged failed: {e}", file=sys.stderr)

    # enrich() is already exception-safe per film internally, but is wrapped here too
    # (defensively — e.g. a cache-file I/O error) so nothing it does can abort the publish;
    # merged.films still get written with whatever enrichment happened before any failure.
    try:
        enrich_mod.enrich(merged, cache_path=str(FILMS_CACHE_PATH), offline=offline)
        health["enrich"] = {"ok": True, "error": None}
    except Exception as e:  # noqa: BLE001 - enrichment failing must degrade, not abort
        health["enrich"] = {"ok": False, "error": str(e)}
        print(f"refresh: enrich failed: {e}", file=sys.stderr)
        summaries.append(f"enrich: FAILED  {e}")

    # phase 1 derived fields (ends, genres keys, family/kids, coordinates, ad offsets), then the
    # poster mirror into data/posters/ (uploaded separately: `python posters.py --upload`).
    # Neither may abort the publish.
    try:
        normalize.finalize(merged)
    except Exception as e:  # noqa: BLE001
        print(f"refresh: finalize failed: {e}", file=sys.stderr)
        summaries.append(f"finalize: FAILED  {e}")
    if offline:
        for film in merged.get("films", {}).values():
            film.pop("poster_src", None)
    else:
        try:
            import posters as posters_mod  # lazy: a missing Pillow costs the posters, not the run

            ph = posters_mod.mirror(merged)
            health["posters"] = {"ok": True, "error": None, **ph}
            summaries.append(f"posters: {ph['with_poster']}/{len(merged.get('films', {}))} films  "
                             f"downloaded={ph['downloaded']} failed={ph['failed']}")
        except Exception as e:  # noqa: BLE001
            for film in merged.get("films", {}).values():
                film.pop("poster_src", None)
            health["posters"] = {"ok": False, "error": str(e)}
            print(f"refresh: posters failed: {e}", file=sys.stderr)

    if verdicts_mod.claude_off():
        summaries.append("verdicts: Claude switched off (~/.elyoxe/claude-off) — existing verdicts kept, none written")
    if not offline and not no_verdicts and not verdicts_mod.claude_off():
        verdict_health = _write_verdicts_isolated(merged)
        health["verdicts"] = verdict_health
        if not verdict_health["ok"]:
            summaries.append(
                f"verdicts: {verdict_health['succeeded']}/{verdict_health['attempted']} ok, "
                f"failed: {', '.join(verdict_health['failed'])}"
            )
        text_health = _fix_verdict_text(merged)
        health["verdict_text"] = text_health
        if text_health.get("rewritten") or text_health.get("unfixed") or text_health.get("error"):
            summaries.append(f"verdict text: {text_health.get('mismatches', '?')} mismatch(es), rewritten: "
                             f"{', '.join(text_health.get('rewritten') or []) or '-'}, unfixed: "
                             f"{', '.join(text_health.get('unfixed') or []) or '-'}")
    _attach_verdicts(merged)

    # phase-2 data steps: every steps/<name>.py with run(data, ctx) -> dict|None, in name order.
    # Each is isolated like enrich: a failure is recorded in health["steps"][name] and never aborts.
    step_results = run_steps(merged, {"offline": offline, "now": now, "data_dir": str(DATA_DIR)})
    health["steps"] = {"ok": all(r["ok"] for r in step_results.values()),
                       "error": None if all(r["ok"] for r in step_results.values())
                       else ", ".join(n for n, r in step_results.items() if not r["ok"]),
                       "items": step_results}

    # film history: archive a film that's confirmed gone (permanent page, see update_film_history),
    # and collect fids appearing for the first time ever -- for run.sh's one new-film notification.
    # The very first run (no film_history.json on disk yet) seeds it silently: every current film
    # is "new" only in the trivial sense of not being in an empty history, not worth alerting on.
    #
    # Corruption-safe (fix round 1): `history_existed` must mean "a *parsed* history existed",
    # never merely "a file was present" -- a corrupt-but-present file used to slip through this
    # check as True while `history` itself silently degraded to {}, producing an alert for every
    # currently-showing film (a real run hit 60) and quietly losing every archived film's record
    # (absent from both the empty `history` and `merged["films"]`, so update_film_history's
    # absence loop never saw them again). Now: "ok"/"restored" both count as real prior state
    # ("restored" recovers it from the one-generation-back backup and behaves normally); only
    # "missing" (first run ever) and "no_backup" (corrupt with nothing to recover) suppress the
    # alert -- and both leave `history` empty, so update_film_history's absence loop has nothing
    # to archive against this run either, i.e. "no_backup" is a silent re-seed exactly as ruled.
    history, history_status = _load_state_json(FILM_HISTORY_PATH, FILM_HISTORY_BACKUP_PATH)
    if history_status == "restored":
        summaries.append("film_history.json restored from backup after corruption")
    elif history_status == "no_backup":
        summaries.append("film_history.json corrupt, no backup -- re-seeded silently (no alert, nothing archived)")
    history = history or {}
    history_existed = history_status in ("ok", "restored")

    fresh = {c for c in chains if health.get(c, {}).get("ok") and c not in reused}
    try:
        static_aliases = normalize.load_aliases().get("aliases", {})
    except Exception:  # noqa: BLE001 - aliases.yaml unreadable: this run's merge map still folds
        static_aliases = {}
    new_history, new_films = update_film_history(merged, history, now, fresh_chains=fresh,
                                                 aliases=static_aliases)
    _write_state_json(FILM_HISTORY_PATH, FILM_HISTORY_BACKUP_PATH, new_history)
    attach_first_seen(merged, new_history)   # W1-D3: published in /data/pulse.json, never recomputed
    _write_json_atomic(NEW_FILMS_PATH, new_films if history_existed else [])
    if new_films:
        summaries.append(
            ("new films (seeded, no alert): " if not history_existed else "new films: ")
            + ", ".join(f"{f['title']} ({f['cinemas']} سينما)" for f in new_films)
        )

    try:
        update_rank_days(merged, previous, now)   # W1-D3: per-city day reads for /data/rank.json
    except Exception as e:  # noqa: BLE001 - the rank is a bonus; it must never abort the publish
        print(f"refresh: rank days failed: {e}", file=sys.stderr)
    _write_json_atomic(LATEST_PATH, merged)
    for city, city_data in normalize.city_slices(merged).items():
        _write_json_atomic(DATA_DIR / f"{city}.json", city_data)
    _write_json_atomic(HEALTH_PATH, health)
    _finish_run()   # completed: the next run fetches every chain afresh

    for line in summaries:
        print(line)

    # Only the requested chains decide the exit code: an enrich/verdicts degrade never flips
    # a run with at least one healthy chain to a failure exit.
    return 0 if any(health[chain]["ok"] for chain in chains) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--chains", help=f"comma-separated subset of {','.join(ALL_CHAINS)} (default: all)")
    ap.add_argument("--offline", action="store_true", help="use fixtures/<chain>.json instead of calling readers")
    ap.add_argument("--no-verdicts", action="store_true", help="skip verdicts.write_missing()")
    ap.add_argument("--days", type=int, default=2, help="days ahead each reader fetches showtimes for")
    ap.add_argument("--force", action="store_true", help="never resume an unfinished run's data/raw/<chain>.json")
    args = ap.parse_args(argv)

    chains = args.chains.split(",") if args.chains else None
    if chains:
        bad = [c for c in chains if c not in CHAIN_READERS]
        if bad:
            ap.error(f"unknown chain(s): {', '.join(bad)} (known: {', '.join(ALL_CHAINS)})")

    return refresh(chains=chains, offline=args.offline, no_verdicts=args.no_verdicts,
                    days=args.days, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
