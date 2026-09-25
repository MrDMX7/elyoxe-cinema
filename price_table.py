"""Fallback ticket prices for chains whose readers can't get a price without a seat hold.

Shape of prices.yaml (hand-maintained; every entry carries its own source):

    {chain: {cinema_id_or_"*": {hall: {seats: [{seat, aed}, ...],
                                        source, checked, method, confidence}}}}

`"*"` is only used for a chain whose source says one price list covers every one of its
sites (see docs/probe/prices.md for what "official_page"/"app_api"/"third_party"/
"seat_sample" and "official"/"third-party" mean, and why most cinema x hall combinations
in this table are simply absent rather than guessed).

fill() only ever touches a show whose `prices` is already `None` — a chain reader that
returns real, live prices (cineroyal, star) is never second-guessed by this table.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "prices.yaml"


def load(path: str | Path = "prices.yaml") -> dict:
    """Parse prices.yaml (or `path`) and return its {chain: {cinema_or_*: {hall: entry}}} dict."""
    p = Path(path)
    if str(path) == "prices.yaml" and not p.exists():
        p = _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _cinema_chain_map(data: dict) -> dict:
    """{cinema_id: chain} from either a merged data dict ({id: cinema}) or a raw reader
    output / a list of cinemas ([cinema, ...])."""
    cinemas = data.get("cinemas") or {}
    if isinstance(cinemas, dict):
        return {cid: c.get("chain") for cid, c in cinemas.items()}
    return {c["id"]: c.get("chain") for c in cinemas}


def fill(data_or_reader_output: dict, table: dict, today: str | None = None) -> int:
    """Fill `prices` on every show whose `prices` is `None`, from `table`.

    Looks up `table[chain][cinema_id][hall]` first, then falls back to
    `table[chain]["*"][hall]`. A show already carrying live prices (not None) is left
    untouched. A hall/cinema/chain missing from `table` is left `None` — no invention.
    On every show it fills, sets `price_source: "table"` and `price_checked: today`
    (ISO date, defaults to today in Asia/Dubai). Returns how many shows were filled.
    """
    today = today or datetime.now(ZoneInfo("Asia/Dubai")).date().isoformat()
    cinema_chain = _cinema_chain_map(data_or_reader_output)
    filled = 0

    for show in data_or_reader_output.get("shows", []):
        if show.get("prices") is not None:
            continue

        cid = show.get("cinema")
        chain = cinema_chain.get(cid)
        if not chain:
            continue

        chain_table = table.get(chain)
        if not chain_table:
            continue

        hall = show.get("hall")
        entry = (chain_table.get(cid) or {}).get(hall) or (chain_table.get("*") or {}).get(hall)
        if not entry or not entry.get("seats"):
            continue

        show["prices"] = [dict(s) for s in entry["seats"]]
        show["price_source"] = "table"
        show["price_checked"] = today
        filled += 1

    return filled
