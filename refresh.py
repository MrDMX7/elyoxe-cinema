"""refresh.py — orchestrate the 7 chain readers into data/latest.json + per-city slices.

CLI: python refresh.py [--chains vox,star,...] [--offline] [--no-verdicts] [--days 2] [--force]

Per chain, in its own daemon thread with a wall-clock timeout (a hung fetch becomes a
failure, never blocks the others or the process exit): fetch() -> raw {"cinemas","shows"} ->
written to data/raw/<chain>.json as soon as it finishes, so a killed run resumes (a raw file
younger than RAW_REUSE_WINDOW is reused instead of refetching, unless --force) -> price_table
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
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import enrich as enrich_mod
import normalize
import price_table
import verdicts as verdicts_mod
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
# same-day seat-map/price sample across runs instead of re-requesting it every hour. Roxy never
# samples (login-gated: see readers/roxy.py) so it's not in this set.
PRICE_CACHE_CHAINS = {"vox", "star", "cineroyal", "novo", "cinemacity", "reel"}
ARCHIVE_AFTER_ABSENT_RUNS = 2  # owner's rule: archive only after 2 consecutive *confirmed* absences

DEFAULT_TIMEOUT = 8 * 60.0
# Prices are sampled once per cinema x hall x show DATE (weekday/weekend prices differ), so the
# chains that sample doubled their request count on 2026-09-26. Measured on the Fold before that:
# VOX ~490 s (one showtimes page per cinema per day + ~80 seat-map samples, now ~160), Star ~185 s.
# cineroyal already sampled per day; roxy samples nothing (login-gated).
CHAIN_TIMEOUTS = {"vox": 30 * 60.0, "star": 15 * 60.0, "reel": 15 * 60.0, "novo": 12 * 60.0, "cinemacity": 12 * 60.0}
RAW_REUSE_WINDOW = timedelta(hours=3)
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


def _write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- corruption-safe state files
# film_history.json and price_cache.json are the two files this run's own past depends on --
# losing price_cache.json only costs a re-sample, but losing film_history.json unnoticed causes
# an alert storm (every current film looks "new" against an empty history) and silently drops
# every archived film's permanent page. Both get the same policy: never trust a file that fails
# to parse, keep it around for forensics instead of overwriting it, fall back to the last known
# good copy, and if there isn't one, say so explicitly rather than merely returning `{}`.

def _load_state_json(path: Path, backup_path: Path) -> tuple[dict | None, str]:
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
        print(f"refresh: {path.name} was corrupt ({e}) -- kept at {corrupt_path.name}", file=sys.stderr)
        if backup_path.exists():
            try:
                return json.loads(backup_path.read_text(encoding="utf-8")), "restored"
            except (OSError, json.JSONDecodeError):
                pass
        return None, "no_backup"


def _write_state_json(path: Path, backup_path: Path, data) -> None:
    """Atomic write of `data` to `path`, first rotating `path`'s *current* content into
    `backup_path` -- but only when that current content is itself valid JSON, so a corrupt file
    is never promoted into "the backup" a future corruption would restore from. One generation
    back is all this keeps; that's enough to survive a single bad write/read, which is the
    failure mode this guards against (not a general history of every past run)."""
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            json.loads(text)  # only rotate a file that's actually good
        except (OSError, json.JSONDecodeError):
            pass
        else:
            try:
                _write_json_atomic(backup_path, json.loads(text))
            except OSError:
                pass
    _write_json_atomic(path, data)


def _raw_path(chain: str) -> Path:
    return RAW_DIR / f"{chain}.json"


def _fresh_raw(chain: str, force: bool):
    """The chain's raw fetch already on disk, if younger than RAW_REUSE_WINDOW and not --force."""
    if force:
        return None
    p = _raw_path(chain)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > RAW_REUSE_WINDOW.total_seconds():
        return None
    return _load_json(p)


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


def update_film_history(merged: dict, history: dict, today: str) -> tuple[dict, list[dict]]:
    """Advances film_history.json state for this run and returns (new_history, new_films).

    Owner's rules (Task 6):
      - a film absent from `merged["films"]` this run is archived (status "archived" +
        first_seen/last_seen, re-added into merged["films"] in place) only once it has been
        *confirmed* absent for ARCHIVE_AFTER_ABSENT_RUNS consecutive runs -- "confirmed" meaning
        every chain that ever listed it (history[fid]["chains"]) reported ok=True this run and
        none of them lists it any more. A chain outage never counts toward, or resets, that
        streak: the film's entry is carried over untouched until every one of its chains is
        healthy again.
      - new_films: fids seen for the first time ever (not in `history` at all before this call).
        Callers must NOT alert on these when `history` itself didn't exist before this run (the
        seeding run) -- that's the caller's job (refresh() below), not this function's, since
        "did the file exist" isn't something `history` (already loaded into a dict) can answer.
    """
    current_films = merged.get("films", {})
    chains_ok = {c: bool(info.get("ok")) for c, info in (merged.get("chains") or {}).items()}
    counts = _cinema_counts(merged)

    new_history = dict(history)
    new_films: list[dict] = []

    for fid, f in current_films.items():
        prev = history.get(fid)
        if prev is None:
            new_films.append({
                "fid": fid,
                "title": f.get("title") or fid,
                "title_ar": f.get("title_ar") or f.get("title_ar_chain"),
                "cinemas": counts.get(fid, 0),
            })
        new_history[fid] = {
            "first_seen": (prev or {}).get("first_seen") or today,
            "last_seen": today,
            "absent_runs": 0,
            "chains": sorted(set(f.get("chains") or [])) or (prev or {}).get("chains") or [],
            "snapshot": {k: v for k, v in f.items() if k != "chains"},
        }

    for fid, rec in history.items():
        if fid in current_films:
            continue  # handled above -- still showing (or just started showing again)
        listed_by = rec.get("chains") or []
        confirmed_absent = all(chains_ok.get(c, False) for c in listed_by)
        if not confirmed_absent:
            new_history[fid] = rec  # a listing chain is down/not-run -- absence unproven, don't touch
            continue
        absent_runs = int(rec.get("absent_runs") or 0) + 1
        new_history[fid] = {**rec, "absent_runs": absent_runs}
        if absent_runs >= ARCHIVE_AFTER_ABSENT_RUNS:
            snap = dict(rec.get("snapshot") or {})
            snap["status"] = "archived"
            snap["first_seen"] = rec.get("first_seen")
            snap["last_seen"] = rec.get("last_seen")
            snap.setdefault("chains", listed_by)
            current_films[fid] = snap

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

    for chain in chains:
        cached = _fresh_raw(chain, force)
        if cached is not None:
            raw, ok, error, seconds = cached, True, None, 0.0
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
                _write_json_atomic(_raw_path(chain), raw)
                if private_cache is not None:
                    # only a chain that actually finished within its timeout gets to update the
                    # persisted cache -- an abandoned/timed-out attempt's copy is simply dropped
                    chain_price_caches[chain] = private_cache

        if ok:
            price_table.fill(raw, table, today=now[:10])
            total = len(raw.get("shows", []))

            # A reader may report its own price accounting via a top-level "price_health"
            # {"attempted","priced","error"} — preferred when present since it can count seat
            # samples the reader tried and failed on, not just shows[].prices. Tolerated as
            # absent (older readers/fixtures): falls back to counting shows[].prices directly.
            # Never copied into `raw` itself past this point, so it can't leak into latest.json
            # (normalize.merge only ever reads raw["cinemas"]/raw["shows"]).
            # A reader that reports price_health with attempted == 0 (Roxy: its prices come from
            # prices.yaml by design, it never samples) is not degraded — nothing was tried.
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
            health[chain] = {"ok": True, "at": now, "error": None, "shows": total,
                              "prices_degraded": degraded}
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
                f"{'  DEGRADED' if degraded else ''}  {seconds:.1f}s"
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

    if not offline and not no_verdicts:
        verdict_health = _write_verdicts_isolated(merged)
        health["verdicts"] = verdict_health
        if not verdict_health["ok"]:
            summaries.append(
                f"verdicts: {verdict_health['succeeded']}/{verdict_health['attempted']} ok, "
                f"failed: {', '.join(verdict_health['failed'])}"
            )
    _attach_verdicts(merged)

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

    new_history, new_films = update_film_history(merged, history, today)
    _write_state_json(FILM_HISTORY_PATH, FILM_HISTORY_BACKUP_PATH, new_history)
    _write_json_atomic(NEW_FILMS_PATH, new_films if history_existed else [])
    if new_films:
        summaries.append(
            ("new films (seeded, no alert): " if not history_existed else "new films: ")
            + ", ".join(f"{f['title']} ({f['cinemas']} سينما)" for f in new_films)
        )

    _write_json_atomic(LATEST_PATH, merged)
    for city, city_data in normalize.city_slices(merged).items():
        _write_json_atomic(DATA_DIR / f"{city}.json", city_data)
    _write_json_atomic(HEALTH_PATH, health)

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
    ap.add_argument("--force", action="store_true", help="ignore any reusable data/raw/<chain>.json")
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
