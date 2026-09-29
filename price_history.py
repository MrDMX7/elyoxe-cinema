"""Price history for «سينما» (phase 2, D): one JSON line per show date in data/price_history.jsonl.

A line is what the chains' schedules said about that date, at the run that saw the most shows for it:

  {"date": "2026-09-27", "at": "<generated>", "n": 3279, "priced": 2900,
   "prices": [[chain, hall, city, median, min, max, n], ...],   # city "" = the whole UAE
   "parts":  [[chain, hall, part, median, n], ...],             # part: morning | afternoon | evening | night
   "films":  {fid: [shows, cinemas]}}

A show's price is its cheapest seat, read live from the chain (a fallback-table price, prices.yaml, is not an
observation and never enters the history). `hall` is the halls.yaml key the site shows (site_kit.Halls).

Idempotent per date: a date is replaced only by a better read of it — more live prices, then more shows (the
first full read of a day is kept against the thinner hourly runs that follow once its early shows are gone), so the same data
twice changes nothing. The file lives on the runner and in the private media bucket (cinema-state/price_history.jsonl), never in git.
Read by pages/insights.py and pages/questions.py; written by steps/history.py."""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "price_history.jsonl")
# Private: no CloudFront distribution has the media bucket as an origin. The site's own bucket is served whole
# (OAC), so the history must never live there — the old copy (LEGACY_*) is moved out by steps/history.py.
BUCKET = "elyoxe-media-574771023173"
KEY = "cinema-state/price_history.jsonl"
LEGACY_BUCKET = "elyoxe-cinema-574771023173"
LEGACY_KEY = "state/price_history.jsonl"
PARTS = ("morning", "afternoon", "evening", "night")


def history_path() -> str:
    """Where the pages read the history: CINEMA_PRICE_HISTORY (tests, previews) else data/price_history.jsonl."""
    return os.environ.get("CINEMA_PRICE_HISTORY") or PATH


def part_of_day(hhmm: str) -> str:
    """morning < 12:00 ≤ afternoon < 17:00 ≤ evening < 21:00 ≤ night; after midnight (before 05:00) is night."""
    h = int(str(hhmm)[:2])
    if h < 5: return "night"
    if h < 12: return "morning"
    if h < 17: return "afternoon"
    if h < 21: return "evening"
    return "night"


def show_price(s: dict) -> float | None:
    """The show's cheapest seat, live prices only (never the prices.yaml fallback)."""
    if s.get("price_source") == "table": return None
    ps = [float(p["aed"]) for p in s.get("prices") or [] if isinstance(p, dict) and (p.get("aed") or 0) > 0]
    return min(ps) if ps else None


def _med(xs):
    return round(float(statistics.median(xs)), 2)


def snapshot(data: dict, halls=None) -> dict:
    """{date: line} for every show date in `data` (latest.json's shape). `halls`: a site_kit.Halls, for the
    hall key the site uses; without it the reader's hall code is the key."""
    cinemas = data.get("cinemas") or {}
    films = data.get("films") or {}
    by_date: dict = {}
    for s in data.get("shows") or []:
        c = cinemas.get(s.get("cinema"))
        if not c or not s.get("date") or not s.get("time") or s.get("film") not in films: continue
        if (films[s["film"]] or {}).get("status") == "archived": continue
        by_date.setdefault(str(s["date"]), []).append((s, c))
    out = {}
    for d, rows in sorted(by_date.items()):
        groups, parts, fshows, fcins = {}, {}, {}, {}
        priced = 0
        for s, c in rows:
            chain, city = c.get("chain") or "", c.get("city") or ""
            code, label = s.get("hall") or "OTHER", s.get("hall_label") or ""
            hall = halls.key(chain, code, label) if halls is not None else code
            fshows[s["film"]] = fshows.get(s["film"], 0) + 1
            fcins.setdefault(s["film"], set()).add(s["cinema"])
            p = show_price(s)
            if p is None: continue
            priced += 1
            for k in ((chain, hall, city), (chain, hall, "")):
                groups.setdefault(k, []).append(p)
            parts.setdefault((chain, hall, part_of_day(s["time"])), []).append(p)
        out[d] = {
            "date": d, "at": data.get("generated"), "n": len(rows), "priced": priced,
            "prices": [[ch, h, ci, _med(v), round(min(v), 2), round(max(v), 2), len(v)] for (ch, h, ci), v in sorted(groups.items())],
            "parts": [[ch, h, pt, _med(v), len(v)] for (ch, h, pt), v in sorted(parts.items())],
            "films": {f: [fshows[f], len(fcins[f])] for f in sorted(fshows)},
        }
    return out


def load(path: str = PATH) -> dict:
    """{date: line}; a torn or foreign line is skipped, never fatal."""
    out = {}
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return out
    with fh:
        for raw in fh:
            try:
                line = json.loads(raw)
                dt.date.fromisoformat(line["date"])
            except (ValueError, KeyError, TypeError):
                continue
            if isinstance(line, dict) and isinstance(line.get("prices"), list):
                out[line["date"]] = line
    return out


def merge(old: dict, new: dict) -> tuple[dict, list]:
    """(merged, dates changed): a date is added, or replaced only by a better read of it — more live prices
    first, then more shows (a run whose chain fell back to the price table sees shows but no prices)."""
    merged, changed = dict(old), []
    q = lambda x: (int(x.get("priced") or 0), int(x.get("n") or 0))
    for d, line in sorted(new.items()):
        cur = merged.get(d)
        if cur is None or q(line) > q(cur):
            merged[d] = line
            changed.append(d)
    return merged, changed


def dump(lines: dict, path: str = PATH) -> None:
    """One line per date, in date order, written atomically."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for d in sorted(lines):
            fh.write(json.dumps(lines[d], ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- readings (pages)
def days(lines: dict, upto: str | None = None) -> list:
    """The dates with priced shows, oldest first, up to `upto` (inclusive)."""
    return [d for d in sorted(lines) if (upto is None or d <= upto) and lines[d].get("priced")]


def series(lines: dict, chain: str, hall: str = "Standard", city: str = "", upto: str | None = None) -> list:
    """[(date, median, n)] for one chain × hall × city ("" = UAE) over the dates that have it."""
    out = []
    for d in days(lines, upto):
        for ch, h, ci, med, _lo, _hi, n in lines[d]["prices"]:
            if ch == chain and h == hall and ci == city:
                out.append((d, med, n)); break
    return out


def cheapest_time(lines: dict, chain: str, hall: str = "Standard", upto: str | None = None) -> list:
    """[(weekday 0=Mon, part, mean of the daily medians weighted by shows, shows, days seen)], cheapest first.
    Only (weekday, part) cells seen on at least two dates count: one Tuesday is an anecdote."""
    acc = {}
    for d in days(lines, upto):
        wd = dt.date.fromisoformat(d).weekday()
        for ch, h, pt, med, n in lines[d].get("parts") or []:
            if ch == chain and h == hall:
                a = acc.setdefault((wd, pt), [0.0, 0, 0])
                a[0] += med * n; a[1] += n; a[2] += 1
    rows = [(wd, pt, round(s / n, 2), n, k) for (wd, pt), (s, n, k) in acc.items() if n and k >= 2]
    return sorted(rows, key=lambda r: (r[2], r[0], PARTS.index(r[1])))


def week_films(lines: dict, end: str, span: int = 7) -> tuple[dict, list]:
    """({fid: [shows summed, most cinemas on one day]}, dates used) over the `span` dates ending at `end`."""
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=span - 1)).isoformat()
    used = [d for d in sorted(lines) if start <= d <= end]
    tot = {}
    for d in used:
        for fid, (n, c) in (lines[d].get("films") or {}).items():
            t = tot.setdefault(fid, [0, 0])
            t[0] += int(n); t[1] = max(t[1], int(c))
    return tot, used


def week_over_week(lines: dict, end: str, span: int = 7) -> tuple[dict, list, dict, list]:
    """(this week's totals, its dates, last week's totals, its dates) — the same `span`-day window ending
    at `end`, and the `span` days immediately before it. Used for /boxoffice/'s week-over-week arrows: a
    film's last-week rank comes from ranking `prev_tot` the same way the caller ranks `tot`."""
    tot, used = week_films(lines, end, span)
    prev_end = (dt.date.fromisoformat(end) - dt.timedelta(days=span)).isoformat()
    prev_tot, prev_used = week_films(lines, prev_end, span)
    return tot, used, prev_tot, prev_used


def ranked_fids(tot: dict) -> list:
    """fids ordered the way /boxoffice/ ranks them: most shows, then most cinemas, then fid — the same key
    pages/insights.py's Insights.week() sorts `tot` with, so a rank computed here and one computed there
    agree without either importing the other."""
    return [f for f, _ in sorted(tot.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))]
