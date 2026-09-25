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

data/latest.json and data/<city>.json (normalize.city_slices) are written atomically
(tmp + os.replace). data/health.json is {chain: {ok, at, error, shows}} for the notifier.
Exit code: 0 if at least one chain in this run is ok, 1 if every one of them failed.

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

DEFAULT_TIMEOUT = 8 * 60.0
RAW_REUSE_WINDOW = timedelta(hours=3)
DUBAI_TZ = ZoneInfo("Asia/Dubai")


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


def _fetch_chain(chain: str, days: int, offline: bool):
    """The raw fetch for one chain: a reader call, or (--offline) its fixture."""
    if offline:
        data = _load_json(FIXTURES_DIR / f"{chain}.json")
        if data is None:
            raise FileNotFoundError(f"no fixture at fixtures/{chain}.json")
        return data
    return CHAIN_READERS[chain](days=days)


def _run_chain(chain: str, days: int, offline: bool, timeout: float) -> dict:
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
            q.put(("ok", _fetch_chain(chain, days, offline)))
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


def refresh(chains=None, offline: bool = False, no_verdicts: bool = False, days: int = 2,
            force: bool = False, timeout: float = DEFAULT_TIMEOUT) -> int:
    """Runs the full pipeline once. Returns the process exit code (0 ok, 1 all chains failed)."""
    chains = list(chains) if chains else list(ALL_CHAINS)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    table = price_table.load()
    previous = _load_json(LATEST_PATH)
    now = now_iso()

    results: dict = {}
    health: dict = {}
    summaries: list[str] = []

    for chain in chains:
        cached = _fresh_raw(chain, force)
        if cached is not None:
            raw, ok, error, seconds = cached, True, None, 0.0
        else:
            outcome = _run_chain(chain, days, offline, timeout)
            ok, error, seconds, raw = outcome["ok"], outcome["error"], outcome["seconds"], outcome["result"]
            if ok:
                _write_json_atomic(_raw_path(chain), raw)

        if ok:
            price_table.fill(raw, table, today=now[:10])
            total = len(raw.get("shows", []))

            # A reader may report its own price accounting via a top-level "price_health"
            # {"attempted","priced","error"} — preferred when present since it can count seat
            # samples the reader tried and failed on, not just shows[].prices. Tolerated as
            # absent (older readers/fixtures): falls back to counting shows[].prices directly.
            # Never copied into `raw` itself past this point, so it can't leak into latest.json
            # (normalize.merge only ever reads raw["cinemas"]/raw["shows"]).
            reader_price_health = raw.get("price_health") or {}
            if reader_price_health.get("attempted"):
                attempted = reader_price_health["attempted"]
                priced = reader_price_health.get("priced") or 0
            else:
                attempted = total
                priced = sum(1 for s in raw.get("shows", []) if s.get("prices") is not None)
            pct = (priced / attempted * 100) if attempted else 0.0
            degraded = bool(attempted and (priced / attempted) < 0.5)

            results[chain] = raw
            health[chain] = {"ok": True, "at": now, "error": None, "shows": total,
                              "prices_degraded": degraded}
            if reader_price_health:
                health[chain]["price_health"] = {
                    "attempted": attempted, "priced": priced,
                    "error": reader_price_health.get("error"),
                }
            summaries.append(
                f"{chain}: ok  cinemas={len(raw.get('cinemas', []))}  shows={total}  "
                f"priced={pct:.0f}%{'  DEGRADED' if degraded else ''}  {seconds:.1f}s"
            )
        else:
            results[chain] = error
            health[chain] = {"ok": False, "at": now, "error": error, "shows": 0}
            summaries.append(f"{chain}: FAILED  {error}  {seconds:.1f}s")

    merged = normalize.merge(results, previous, now)
    enrich_mod.enrich(merged, cache_path=str(FILMS_CACHE_PATH), offline=offline)

    if not offline and not no_verdicts:
        verdicts_mod.write_missing(merged)
    _attach_verdicts(merged)

    _write_json_atomic(LATEST_PATH, merged)
    for city, city_data in normalize.city_slices(merged).items():
        _write_json_atomic(DATA_DIR / f"{city}.json", city_data)
    _write_json_atomic(HEALTH_PATH, health)

    for line in summaries:
        print(line)

    return 0 if any(h["ok"] for h in health.values()) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--chains", help=f"comma-separated subset of {','.join(ALL_CHAINS)} (default: all)")
    ap.add_argument("--offline", action="store_true", help="use fixtures/<chain>.json instead of calling readers")
    ap.add_argument("--no-verdicts", action="store_true", help="skip verdicts.write_missing()")
    ap.add_argument("--days", type=int, default=2)
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
