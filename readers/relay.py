"""readers/relay.py — a chain read on the laptop, handed to the GitHub run (2026-10-24).

The refresh moved to GitHub Actions, but three chains do not read whole from a datacenter address (the cinema-probe of
2026-10-24: Cine Royal's load balancer 403s, Novo's API sits behind a Cloudflare challenge, and Roxy's Akamai let a
real run through with two of its six cinemas missing). Their readers keep running
on the laptop's residential line (tools/relay.py fetch roxy,cineroyal,novo, Task Scheduler «Elyoxe Cinema Relay», the same 7 times), which
writes each raw read to s3://<RELAY_BUCKET>/<RELAY_PREFIX><chain>.json:

    {"cinemas": [...], "shows": [...], "price_health": {...}, "_read_at": <ISO>}      a read
    {"_read_at": <ISO>, "_error": "<why>"}                                              a failed read

The GitHub run's refresh.py lists these chains in CINEMA_RELAY_CHAINS (and last in --chains, so the laptop has had the
first minutes of the run to finish): for them fetch() below stands in for the reader. It waits up to RELAY_WAIT_S for a
read made within RELAY_FRESH_MIN minutes, then returns it with its own read time (refresh.py publishes that, not the
run's). Anything else is a failure, never an empty success: a stale or missing read, or the laptop's own failed read,
raises, so normalize.merge keeps the chain's previous cinemas and shows (marked stale) — one source can never wipe the
other's chains, and only the GitHub run ever merges and deploys.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

RELAY_BUCKET = os.environ.get("CINEMA_RELAY_BUCKET", "elyoxe-media-574771023173")
RELAY_PREFIX = os.environ.get("CINEMA_RELAY_PREFIX", "cinema-ci/relay/")
REGION = "ap-south-1"


def relay_chains() -> list[str]:
    return [c for c in (os.environ.get("CINEMA_RELAY_CHAINS") or "").replace(" ", "").split(",") if c]


def wait_s() -> float:
    try:
        return float(os.environ.get("CINEMA_RELAY_WAIT_S", "900"))
    except ValueError:
        return 900.0


def fresh_min() -> float:
    try:
        return float(os.environ.get("CINEMA_RELAY_FRESH_MIN", "75"))
    except ValueError:
        return 75.0


def _get(chain: str, client=None):
    if client is None:
        import boto3
        client = boto3.client("s3", region_name=REGION)
    try:
        body = client.get_object(Bucket=RELAY_BUCKET, Key=f"{RELAY_PREFIX}{chain}.json")["Body"].read()
    except Exception as e:  # noqa: BLE001 - missing or unreadable is "no read yet"
        if "NoSuchKey" in repr(e) or "404" in repr(e):
            return None
        raise
    return json.loads(body)


def _age(raw: dict, now: datetime) -> timedelta | None:
    try:
        at = datetime.fromisoformat(raw.get("_read_at"))
    except (TypeError, ValueError):
        return None
    return now - (at if at.tzinfo else at.replace(tzinfo=timezone.utc))


def fetch_relayed(chain: str, client=None, sleep=time.sleep, clock=None) -> dict:
    """The laptop's fresh read of `chain` (a dict with "_relay_read_at"), or RuntimeError."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    deadline = time.monotonic() + wait_s()
    fresh = timedelta(minutes=fresh_min())
    last = None
    while True:
        raw = _get(chain, client)
        age = _age(raw, clock()) if isinstance(raw, dict) else None
        if age is not None and age <= fresh:
            if raw.get("_error"):
                raise RuntimeError(f"{chain} (laptop relay): {raw['_error']}")
            if not raw.get("shows"):
                raise RuntimeError(f"{chain} (laptop relay): a read with zero shows")
            raw = {k: v for k, v in raw.items() if k not in ("_error",)}
            raw["_relay_read_at"] = raw.pop("_read_at")
            return raw
        last = raw
        if time.monotonic() >= deadline:
            break
        sleep(30)
    when = (last or {}).get("_read_at") if isinstance(last, dict) else None
    raise RuntimeError(f"{chain} (laptop relay): no read within {fresh_min():.0f} min "
                       f"(last {when or 'never'}) — previous shows kept")


def reader(chain: str):
    """A fetch(days=..., cache=...) stand-in for refresh.CHAIN_READERS."""
    def fetch(days: int = 2, cache: dict | None = None, **_ignored) -> dict:
        return fetch_relayed(chain)
    fetch.__name__ = f"relay_{chain}"
    return fetch
