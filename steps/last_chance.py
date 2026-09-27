"""steps/last_chance.py — «آخر فرصة»: a film whose run in a city has shrunk to its last day or two.

run(data, ctx) -> {"cities": {city: n}}

Design spec (docs/superpowers/specs/2026-09-27-phase2-design.md, A): a film qualifies in a city
when shows exist there today and/or tomorrow, none beyond, and it has been seen (film_history's
first_seen) for >= 14 days. `data["shows"]` only ever covers the refresh window (--days, normally
2: today + tomorrow), so "none beyond tomorrow" is simply "no show dated after tomorrow" in what
we have -- a film with a show 3 days out is filtered by refresh() never fetching that far, not by
this step, so a chain that publishes further ahead never gets miscounted as "last chance" here.

data["last_chance"][city] = [fid, ...] sorted, city keys only for cities with at least one film.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

MIN_DAYS_SEEN = 14


def _load_history(data_dir) -> dict:
    p = Path(data_dir or "data") / "film_history.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _today_tomorrow(now_iso) -> tuple[str, str]:
    try:
        d = datetime.fromisoformat(now_iso).date() if now_iso else date.today()
    except ValueError:
        d = date.today()
    return d.isoformat(), (d + timedelta(days=1)).isoformat()


def run(data: dict, ctx: dict) -> dict | None:
    history = _load_history(ctx.get("data_dir"))
    today, tomorrow = _today_tomorrow(ctx.get("now"))
    city_of_cinema = {cid: c.get("city") for cid, c in (data.get("cinemas") or {}).items()}

    by_film_city: dict[tuple, set] = {}
    for s in data.get("shows") or []:
        fid, cid, d = s.get("film"), s.get("cinema"), s.get("date")
        city = city_of_cinema.get(cid)
        if fid and city and d:
            by_film_city.setdefault((fid, city), set()).add(d)

    out: dict[str, list] = {}
    for (fid, city), dates in by_film_city.items():
        if dates - {today, tomorrow}:
            continue  # a show beyond tomorrow -- this run is not (yet) down to its last days
        if today not in dates and tomorrow not in dates:
            continue  # already gone (only past dates on record, e.g. a stale/offline slice)
        first_seen = (history.get(fid) or {}).get("first_seen")
        if not first_seen:
            continue
        try:
            seen_days = (date.fromisoformat(today) - date.fromisoformat(first_seen)).days
        except ValueError:
            continue
        if seen_days >= MIN_DAYS_SEEN:
            out.setdefault(city, set()).add(fid)

    data["last_chance"] = {city: sorted(fids) for city, fids in out.items()}
    return {"cities": {city: len(fids) for city, fids in data["last_chance"].items()}}
