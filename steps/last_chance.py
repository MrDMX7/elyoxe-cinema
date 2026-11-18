"""steps/last_chance.py — «آخر فرصة»: a film on its way out of the cinemas, by the collapse of its shows.

The first rule («no show after tomorrow») was switched off on 2026-09-28 (W0-P2, MASTER-PLAN §4.1 #13): with the
readers' two-day window it is true of every film, so every film older than 14 days would have been flagged. The
spec allowed it back only on a real signal; this is the third one it names, a collapse in a film's show count
(owner's pick, 2026-11-18). The signal is the price history's per-day film counts (data/price_history.jsonl,
"films": {fid: [shows, cinemas]} for every show date, written by steps/history.py, which runs before this step).

A film qualifies when it
  - was first seen MIN_DAYS_SEEN (14) days ago or more (data/film_history.json),
  - had a PEAK of at least MIN_PEAK (20) shows on one day in the last PEAK_WINDOW_DAYS (28) days, and
  - has COLLAPSE (a quarter) of that peak or fewer today and tomorrow (the larger of the two counts).
A weekday dip is far above a quarter of the weekend's count, and a film that never had 20 shows a day is not
leaving: it never arrived big. The page says the numbers («من X عرض باليوم إلى Y»), not a guess.

data["last_chance"] = {city: [fid, ...]} for every city the film plays today or tomorrow (as before), and
data["last_chance_info"] = {fid: {"peak": int, "peak_date": str, "now": int}}. run() -> {"films": n, "cities": {...}}.
Nothing here can stop the run; without history it flags nothing."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

MIN_DAYS_SEEN = 14
MIN_PEAK = 20
PEAK_WINDOW_DAYS = 28
COLLAPSE = 0.25


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) or default
    except (OSError, ValueError):
        return default


def _counts(data_dir) -> dict:
    """{date: {fid: shows}} from the price history (one JSON line per show date)."""
    out = {}
    try:
        lines = (Path(data_dir or "data") / "price_history.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("date") and isinstance(rec.get("films"), dict):
            out[rec["date"]] = {fid: (v[0] if isinstance(v, list) and v else 0) for fid, v in rec["films"].items()}
    return out


def _today_tomorrow(now_iso) -> tuple[str, str]:
    try:
        d = datetime.fromisoformat(now_iso).date() if now_iso else date.today()
    except ValueError:
        d = date.today()
    return d.isoformat(), (d + timedelta(days=1)).isoformat()


def collapse(data: dict, ctx: dict) -> tuple[dict, dict]:
    """({city: [fid]}, {fid: {peak, peak_date, now}}) by the rule above."""
    data_dir = ctx.get("data_dir")
    history = _json(Path(data_dir or "data") / "film_history.json", {})
    counts = _counts(data_dir)
    today, tomorrow = _today_tomorrow(ctx.get("now"))
    t = date.fromisoformat(today)
    window = {(t - timedelta(days=i)).isoformat() for i in range(1, PEAK_WINDOW_DAYS + 1)}
    city_of = {cid: c.get("city") for cid, c in (data.get("cinemas") or {}).items()}

    live: dict[str, dict] = {}          # fid -> {date: shows} from this run's own data, today and tomorrow
    cities: dict[str, set] = {}
    for s in data.get("shows") or []:
        fid, d, city = s.get("film"), s.get("date"), city_of.get(s.get("cinema"))
        if fid and d in (today, tomorrow):
            live.setdefault(fid, {}).setdefault(d, 0)
            live[fid][d] += 1
            if city:
                cities.setdefault(fid, set()).add(city)

    out, info = {}, {}
    for fid, days in live.items():
        first = (history.get(fid) or {}).get("first_seen")
        try:
            if not first or (t - date.fromisoformat(first)).days < MIN_DAYS_SEEN:
                continue
        except ValueError:
            continue
        past = [(counts[d].get(fid, 0), d) for d in window if d in counts]
        if not past:
            continue
        peak, peak_date = max(past)
        # today's full count is the history's own line for today when it has one (the run that saw the most shows)
        now_n = max(max((counts.get(d) or {}).get(fid, 0), days.get(d, 0)) for d in (today, tomorrow))
        if peak >= MIN_PEAK and now_n <= peak * COLLAPSE:
            info[fid] = {"peak": peak, "peak_date": peak_date, "now": now_n}
            for city in cities.get(fid, ()):
                out.setdefault(city, set()).add(fid)
    return {c: sorted(f) for c, f in out.items()}, info


def run(data: dict, ctx: dict) -> dict | None:
    data["last_chance"], data["last_chance_info"] = collapse(data, ctx)
    return {"films": len(data["last_chance_info"]), "cities": {c: len(f) for c, f in data["last_chance"].items()}}
