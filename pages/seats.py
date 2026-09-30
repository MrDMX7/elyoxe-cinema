"""Inside the hall (phase 2, B): the ticket's hall drawing, «باقي N مقعد» on the times, the best seat.

No page of its own. Two data files for the lazy chunk src/js/seatmap.js (loaded on every page with a ticket):
- /data/occupancy.json {"o": {"cin|fid|date|time": [[hall key, free, total, sampled at (epoch s)]]}} — only
  shows whose own sample is under 90 minutes old when the data was built; the client drops what turns 90 minutes old.
- /data/seats/<cinema>.json {"m": {map key: shape}, "s": {"fid|date|time": [[hall key, map key, best row,
  best x, free, total, at, [status rows]]]}} — the show's own fresh sample (its map, its seats' status, its best
  free seat), else its screen's shape only when steps/occupancy.py could tell it for certain (`seatmap`), with the
  best place in it; a show with neither is left out (no drawing, no seat total).
- /data/seats/index.json ["cinema", …] — the cinemas that have a seats file, always written (an empty list when
  none has one), so the chunk asks only for files that exist instead of a 404 on every ticket tap.
Shapes and status strings are seats.compact()'s."""
from site_kit import Plugin
import seats as seatsmod

CSS = ("seatmap",)
LAZY_JS = ("seatmap",)
KINDS = ("home", "city", "cinema", "film")
# «باقي N مقعد» is a scarcity flag, not a seat counter: > 15 free is not shown anywhere (R4 §300). The no-script
# page can only ever be as fresh as the build that wrote it (seatsmod.fresh() below judges that at build time,
# the same tolerance every other live figure on this site already carries); a script-enabled visitor gets the
# live, timestamped version instead (seatmap.js re-checks freshness against the visitor's own clock).
SEATS_LEFT_MAX = 15


def private_off(shows):
    """Readers' `_` handles never reach the site, even if the refresh step that removes them failed."""
    for s in shows:
        for k in [k for k in s if k.startswith("_")]:
            del s[k]


def _epoch(at):
    t = seatsmod._parse_at(at)
    return int(t.timestamp()) if t else None


def build_data(site):
    """(occupancy.json, {cinema: seats/<cinema>.json}) from the site's shows and data["seatmaps"]."""
    maps = (site.d.get("seatmaps") or {}).get("maps") or {}
    # the occupancy step's own clock: it runs after the chains, ~30 min past data["generated"] on a first run
    ref = max(site.now, seatsmod._parse_at(site.d.get("seats_now")) or site.now)
    occ, per, best_of = {}, {}, {}
    for s in site.shows:
        cid, hk = s["cinema"], site.hkey(s)
        key = f"{s['film']}|{s['date']}|{s['time']}"
        raw = s.get("seats") if isinstance(s.get("seats"), dict) else None
        fresh = bool(raw) and seatsmod.fresh(raw, ref)
        # s["seats_left"] (R4 §300): kit/sched.py's data-left on the time button and kit/ticket.py's own badge
        # both already read this — it was declared and never set. A fresh, scarce sample only: never a healthy
        # hall (noise, not help) and never a stale one (the freshness gate this file already had for the seat map).
        if fresh and isinstance(raw.get("free"), int) and 0 < raw["free"] <= SEATS_LEFT_MAX:
            s["seats_left"] = raw["free"]
        o = raw if fresh and raw.get("m") in maps else None
        mkey = o["m"] if o else (s.get("seatmap") if s.get("seatmap") in maps else None)
        if not mkey:
            continue
        row = [hk, mkey, None, None]
        if o:
            b = o.get("best") or {}
            row[2:4] = [b.get("row"), b.get("x")]
            row += [o["free"], o["total"], _epoch(o["at"]), o.get("st") or []]
            occ.setdefault(f"{cid}|{key}", []).append([hk, o["free"], o["total"], _epoch(o["at"])])
        else:
            if mkey not in best_of:
                best_of[mkey] = seatsmod.best_seat(seatsmod.expand(maps[mkey]), statuses=False) or {}
            row[2:4] = [best_of[mkey].get("row"), best_of[mkey].get("x")]
        f = per.setdefault(cid, {"m": {}, "s": {}})
        f["m"][mkey] = maps[mkey]
        f["s"].setdefault(key, []).append(row)
    return {"o": occ}, per


def register(site):
    private_off(site.d.get("shows") or [])
    private_off(site.shows)
    occ, per = build_data(site)
    data = {"data/occupancy.json": occ, "data/seats/index.json": sorted(per)}
    for cid, f in sorted(per.items()):
        data[f"data/seats/{cid}.json"] = f
    return Plugin(data=data, page_js={k: ("seatmap",) for k in KINDS})
