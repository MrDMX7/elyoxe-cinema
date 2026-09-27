"""Inside the hall (phase 2, B): the ticket's hall drawing, «باقي N مقعد» on the times, the best seat.

No page of its own. Two data files for the lazy chunk src/js/seatmap.js (loaded on every page with a ticket):
- /data/occupancy.json {"o": {"cin|fid|date|time": [[hall key, free, total, sampled at (epoch s)]]}} — only
  shows whose own sample is under 90 minutes old when the data was built; the client drops what turns 90 minutes old.
- /data/seats/<cinema>.json {"m": {map key: shape}, "s": {"fid|date|time": [[hall key, map key, best row,
  best x, free, total, at, [status rows]]]}} — the show's own fresh sample (its map, its seats' status, its best
  free seat), else its screen's shape only when steps/occupancy.py could tell it for certain (`seatmap`), with the
  best place in it; a show with neither is left out (no drawing, no seat total).
Shapes and status strings are seats.compact()'s."""
from site_kit import Plugin
import seats as seatsmod

CSS = ("seatmap",)
LAZY_JS = ("seatmap",)
KINDS = ("home", "city", "cinema", "film")


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
    occ, per, best_of = {}, {}, {}
    for s in site.shows:
        cid, hk = s["cinema"], site.hkey(s)
        key = f"{s['film']}|{s['date']}|{s['time']}"
        o = s.get("seats") if isinstance(s.get("seats"), dict) else None
        if o and not (seatsmod.fresh(o, site.now) and o.get("m") in maps):
            o = None
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
    data = {"data/occupancy.json": occ}
    for cid, f in sorted(per.items()):
        data[f"data/seats/{cid}.json"] = f
    return Plugin(data=data, page_js={k: ("seatmap",) for k in KINDS})
