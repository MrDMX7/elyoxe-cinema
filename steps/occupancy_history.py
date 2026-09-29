"""steps/occupancy_history.py — «أفضل وقت تروح»: the time of day a cinema is usually least full.

Runs after steps/occupancy.py (name sorts after it), over the shows that step just attached
`seats` to this run (occupancy.py's own KEEP_OCC_H=24h freshness — this step only ever sees a
sample once, right after it was taken, never re-reads occupancy.json).

Each fresh sample (free/total seats, this run) is folded into data/occupancy_history.json:

    {"cinema": {"parts": {"morning"|"afternoon"|"evening"|"night": {"n": samples, "sum": Σ occupancy%}},
                "days": [date, …]}}   # distinct dates a sample landed on, kept HIST_DAYS

occupancy% = 1 - free/total (price_history.part_of_day buckets the show's own start time — the
same morning/afternoon/evening/night the price index already uses, so the two never disagree).
Per cinema (not per hall: most cinemas' halls run the same house average, and splitting by hall
too keeps every cell under the 2-sample floor for months). Kept HIST_DAYS days, decayed by simply
dropping samples whose date ages out — no invented smoothing.

`data["cinemas"][cid]["best_time"] = {"part": "morning", "occ": 0.34}` is attached only once the
cinema has samples on at least MIN_DAYS distinct dates and MIN_SAMPLES samples total, and the best
part's own bucket has at least MIN_PART_SAMPLES of them — otherwise the key is simply absent
(pages/venue.py hides the line, never guesses). The lowest average occupancy wins; a tie keeps the
earlier part (PARTS order) so the line doesn't flip on noise alone.

Never raises into the publish; a malformed history file is treated as empty (the next run rebuilds
it), matching statefile.py's corruption-safe contract."""
from __future__ import annotations

from pathlib import Path

import price_history as ph

HIST_DAYS = 60          # distinct dates kept per cinema before the oldest are dropped
MIN_DAYS = 7            # distinct dates required before a cinema's best_time is published
MIN_SAMPLES = 12        # total samples required across all parts
MIN_PART_SAMPLES = 3    # the winning part's own bucket needs at least this many samples


def _fold(entry: dict, part: str, occ: float, date: str) -> None:
    parts = entry.setdefault("parts", {})
    p = parts.setdefault(part, {"n": 0, "sum": 0.0})
    p["n"] += 1
    p["sum"] += occ
    days = entry.setdefault("days", [])
    if date not in days:
        days.append(date)


def _trim(entry: dict, keep_from: str) -> None:
    days = [d for d in entry.get("days") or [] if isinstance(d, str) and d >= keep_from]
    entry["days"] = sorted(set(days))


def best_time(entry: dict) -> dict | None:
    """{"part", "occ"} for `entry` (one cinema's history), or None if it hasn't seen enough yet."""
    days = entry.get("days") or []
    parts = entry.get("parts") or {}
    total_n = sum(int(p.get("n") or 0) for p in parts.values())
    if len(days) < MIN_DAYS or total_n < MIN_SAMPLES:
        return None
    candidates = [(p, v["sum"] / v["n"]) for p, v in parts.items()
                  if v.get("n", 0) >= MIN_PART_SAMPLES and p in ph.PARTS]
    if not candidates:
        return None
    candidates.sort(key=lambda pv: (round(pv[1], 4), ph.PARTS.index(pv[0])))
    part, avg = candidates[0]
    return {"part": part, "occ": round(avg, 4)}


def run(data, ctx):
    import statefile

    ddir = Path(ctx.get("data_dir") or Path(__file__).resolve().parent.parent / "data")
    path = ddir / "occupancy_history.json"
    hist, _status = statefile.load_state_json(path, path.with_name(path.name + ".bak"))
    hist = {k: v for k, v in hist.items() if isinstance(v, dict)} if isinstance(hist, dict) else {}

    today = str(ctx.get("now") or "")[:10]
    folded = 0
    for s in data.get("shows") or []:
        e = s.get("seats")
        if not isinstance(e, dict):
            continue
        total, free = e.get("total"), e.get("free")
        if not isinstance(total, (int, float)) or total <= 0 or not isinstance(free, (int, float)):
            continue
        cid, hhmm, date = s.get("cinema"), s.get("time"), s.get("date")
        if not cid or not hhmm or not date:
            continue
        occ = max(0.0, min(1.0, 1 - free / total))
        part = ph.part_of_day(hhmm)
        entry = hist.setdefault(cid, {})
        _fold(entry, part, occ, date)
        folded += 1

    keep_from = today
    if today:
        try:
            import datetime as _dt
            keep_from = (_dt.date.fromisoformat(today) - _dt.timedelta(days=HIST_DAYS - 1)).isoformat()
        except ValueError:
            pass
    for cid in list(hist):
        _trim(hist[cid], keep_from)
        if not hist[cid].get("days"):
            del hist[cid]

    statefile.write_state_json(path, path.with_name(path.name + ".bak"), hist)

    attached = 0
    for cid, c in (data.get("cinemas") or {}).items():
        c.pop("best_time", None)
        bt = best_time(hist.get(cid) or {})
        if bt:
            c["best_time"] = bt
            attached += 1

    return {"cinemas_with_history": len(hist), "folded": folded, "attached": attached}
