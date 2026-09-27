"""Phase-2 step: hall maps and «باقي N مقعد» (spec B; the logic is in seats.py).

1. Every show's `_sid` (a reader's session handle) is used here and then removed — never published.
2. The hall shapes the readers kept while sampling prices this run (seats.KEPT) are merged into
   data/seatmaps.json {"halls": {"cinema|hall_label": {"m": shape key, "at"}}, "maps": {key: shape}}.
3. Shows starting within the next 3 hours are sampled (seats.sample: ≤ 60 requests per chain, ≥ 1 s apart,
   no seat selected, no login) into data/occupancy.json {"shows": {show key: {free, total, at, m, st, best}},
   "maps": {key: shape}}. Both files are atomic, corruption-safe state files (statefile.py).
4. A show gets `seats` = {free, total, at, m, st, best} only when its sample is under 90 minutes old; the data
   gets `seatmaps` = {"halls": {"cinema|hall_label": key}, "maps": {key: shape}} for the halls it shows.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import seats
import statefile

KEEP_DAYS = 45          # a hall shape not seen again for this long is dropped
KEEP_OCC_H = 24         # occupancy entries are kept a day (for the resample check), shown for 90 minutes


def _load(path: Path) -> dict:
    data, _status = statefile.load_state_json(path, path.with_name(path.name + ".bak"))
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict) -> None:
    statefile.write_state_json(path, path.with_name(path.name + ".bak"), data)


_parse = seats._parse_at


def run(data, ctx):
    shows = data.get("shows") or []
    cinemas = data.get("cinemas") or {}
    sids = {}
    for i, s in enumerate(shows):           # take the session handles off every show first, whatever happens next
        sid = s.pop("_sid", None)
        if sid not in (None, ""):
            sids[i] = str(sid)

    now = _parse(ctx.get("now")) or datetime.now(seats.DUBAI)
    ddir = Path(ctx.get("data_dir") or Path(__file__).resolve().parent.parent / "data")
    maps_path, occ_path = ddir / "seatmaps.json", ddir / "occupancy.json"

    # hall shapes from this run's price samples
    sm = _load(maps_path)
    halls, maps = dict(sm.get("halls") or {}), dict(sm.get("maps") or {})
    with seats._LOCK:
        kept = dict(seats.KEPT)
        seats.KEPT.clear()
    for hk, v in kept.items():
        key = seats.shape_key(v["shape"])
        maps[key] = v["shape"]
        halls[hk] = {"m": key, "at": v["at"]}
    cutoff = now - timedelta(days=KEEP_DAYS)
    halls = {k: v for k, v in halls.items() if (_parse(v.get("at")) or now) >= cutoff}
    maps = {k: v for k, v in maps.items() if k in {h["m"] for h in halls.values()}}
    if kept or sm:
        _save(maps_path, {"halls": halls, "maps": maps})

    # occupancy for the shows about to start
    occ = _load(occ_path)
    occ_shows, occ_maps = dict(occ.get("shows") or {}), dict(occ.get("maps") or {})
    report = {}
    if not ctx.get("offline"):
        todo = []
        for i, s in enumerate(shows):
            chain = (cinemas.get(s.get("cinema")) or {}).get("chain")
            if chain in seats.SUPPORTED:
                todo.append({**s, "_chain": chain, "_sid": sids.get(i)})
        got, report = seats.sample(todo, now, recent=occ_shows)
        for k, v in got.items():
            key = seats.shape_key(v["shape"])
            occ_maps[key] = v["shape"]
            occ_shows[k] = {"free": v["free"], "total": v["total"], "at": v["at"], "m": key, "st": v["st"], "best": v["best"]}
    old = now - timedelta(hours=KEEP_OCC_H)
    occ_shows = {k: v for k, v in occ_shows.items() if (_parse(v.get("at")) or old) > old}
    occ_maps = {k: v for k, v in occ_maps.items() if k in {e.get("m") for e in occ_shows.values()}}
    if occ_shows or occ:
        _save(occ_path, {"shows": occ_shows, "maps": occ_maps})

    # attach: fresh occupancy on its show; the hall shapes the data's shows use
    attached, used = 0, {}
    for s in shows:
        s.pop("seats", None)
        e = occ_shows.get(seats.show_key(s))
        if e and seats.fresh(e, now) and e.get("m") in occ_maps:
            s["seats"] = {k: e[k] for k in ("free", "total", "at", "m", "st", "best")}
            used[e["m"]] = occ_maps[e["m"]]
            attached += 1
    hall_ix = {}
    for s in shows:
        hk = f"{s.get('cinema')}|{s.get('hall_label') or ''}"
        h = halls.get(hk)
        if h and h.get("m") in maps:
            hall_ix[hk] = h["m"]
            used[h["m"]] = maps[h["m"]]
    if hall_ix or used:
        data["seatmaps"] = {"halls": hall_ix, "maps": used}
    else:
        data.pop("seatmaps", None)

    return {"maps_kept": len(kept), "halls": len(hall_ix), "attached": attached,
            "chains": {c: r for c, r in sorted(report.items())}}
