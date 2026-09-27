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
    On every show it fills, sets `price_source: "table"` and `price_checked`: the TABLE
    entry's own `checked` date (when that price was actually seen), never today — the site
    shows it as «السعر بتاريخ <date>» and never under a live «updated X min ago». `today`
    (ISO date, Asia/Dubai) is only the fallback for an entry that carries no date.
    Returns how many shows were filled.
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
        show["price_checked"] = str(entry.get("checked") or today)
        filled += 1

    return filled


# Chains whose later-day shows borrow today's live price for the same cinema x hall (legend §4.1 #34).
# VOX samples one seat-map legend per cinema x hall x date and gives up after a failure or a block, so
# on 2026-09-28 a third of its next-day shows had no price at all («السعر في الشباك») while the same
# hall had a price read that same day. Other chains read (nearly) every date they list.
CARRY_TODAY_CHAINS = ("vox",)


def _is_3d(title) -> bool:
    from readers.common import fmt3d
    return bool(fmt3d(title))


def carry_today(reader_output: dict, today: str, chains=CARRY_TODAY_CHAINS) -> int:
    """Give a later-day show with no price the price read TODAY for the same cinema x hall (x 3D),
    dated: it is marked like a fallback-table price (`price_source: "table"`, `price_checked`: today),
    so every page prints its date («السعر بتاريخ …») instead of passing it off as that day's live
    price, and price_history never records it as that day's reading. `price_basis: "today"` names
    where it came from. Only live prices are carried (a show already priced, or today's own
    table-filled price, is never a source). Returns how many shows were given one."""
    cinema_chain = _cinema_chain_map(reader_output)
    shows = reader_output.get("shows", [])

    def key(s):
        return (s.get("cinema"), s.get("hall_label") or s.get("hall"), _is_3d(s.get("film_title")))

    todays: dict = {}
    for s in shows:
        if s.get("date") != today or not s.get("prices") or s.get("price_source"):
            continue
        if cinema_chain.get(s.get("cinema")) not in chains:
            continue
        best = todays.setdefault(key(s), {})
        for p in s["prices"]:
            if p.get("seat") and p.get("aed") and p["aed"] > 0:
                cur = best.get(p["seat"])
                best[p["seat"]] = p["aed"] if cur is None else min(cur, p["aed"])

    carried = 0
    for s in shows:
        if s.get("prices") is not None or not s.get("date") or s["date"] <= today:
            continue
        if cinema_chain.get(s.get("cinema")) not in chains:
            continue
        seats = todays.get(key(s))
        if not seats:
            continue
        s["prices"] = [{"seat": k, "aed": v} for k, v in seats.items()]
        s["price_source"] = "table"
        s["price_checked"] = today
        s["price_basis"] = "today"
        carried += 1
    return carried
