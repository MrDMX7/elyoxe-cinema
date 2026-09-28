"""Phase-2 step: hall maps and «باقي N مقعد» (spec B; the logic is in seats.py).

1. Every show's `_`-prefixed reader handles (`_sid` the session, `_screen` the physical screen) are taken off
   first — before anything is imported — so none is ever published, even if the rest of this step fails.
2. The hall shapes the readers kept while sampling prices this run (seats.KEPT) are merged into
   data/seatmaps.json {"v": 2, "halls": {"cinema|hall_label|screen": {"m": shape key, "at"}}, "maps": {key: shape}}
   (screen "#<shape key>" when the chain names none, so each distinct shape of a label is its own entry).
3. Shows starting within the next 3 hours are sampled (seats.sample: ≤ 60 requests per chain, redirects
   included, ≥ 1 s apart, no seat selected, no login) into data/occupancy.json {"shows": {show key: {free,
   total, at, m, st, best}}, "maps": {key: shape}}. Both files are atomic, corruption-safe state files.
   Which shows (legend W1-D3, `aim`): each chain gets exactly the shows its request cap can read, reachable
   ones first (30 to 180 minutes out) at the busiest cinemas, one per cinema before a second anywhere. Before
   it, seats.pick walked the cinemas in id order, so VOX's six samples a run (9 requests each under the 60 cap)
   went every hour to the same six alphabetically first cinemas, a median 10 minutes before the show.
4. A show gets `seats` = {free, total, at, m, st, best} only when its own sample is under 90 minutes old, and
   `seatmap` = a shape key only when that shape is certainly its screen's: its screen's own shape, or — when the
   chain names no screen — the one shape ever seen for its hall label (two or more: nothing). The data gets
   `seatmaps` = {"maps": {key: shape}} for the keys its shows use.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

KEEP_DAYS = 45          # a hall shape not seen again for this long is dropped
KEEP_OCC_H = 24         # occupancy entries are kept a day (for the resample check), shown for 90 minutes

# ---- the sampler's aim (W1-D3). What one seat-map sample costs in requests as seats._sampler meters it (every
# redirect counted; VOX measured live on 2026-09-28: booking 4 hops, seats/fetch 3, seats 1, abandon 1), the extra
# requests a chain's first sample makes (Reel's guest login, Cine Royal's warm-up page) and the requests kept back
# for releasing an order. capacity() is then how many shows a chain's cap (seats.MAX_REQ) can read in one run.
COST = {"vox": 9, "reel": 3}
FIRST = {"reel": 1, "cineroyal": 1}
RESERVE = {"vox": 1, "reel": 1}
REACH_MIN = 30          # a show starting sooner than this is sampled only after every reachable one
BEST_LEAD_MIN = 120     # a sample is shown for 90 min (seats.FRESH_MIN) and a show is chosen up to ~30 min before
                        # it starts, so one read 2 h ahead stays useful for its whole life


def capacity(chain, cap=None):
    """How many shows `chain` can have sampled in one run within its request cap (default seats.MAX_REQ)."""
    import seats
    cap = seats.MAX_REQ if cap is None else cap
    return max(0, (cap - RESERVE.get(chain, 0) - FIRST.get(chain, 0)) // COST.get(chain, 1))


def aim(todo, now, recent=None, day_shows=None, cap=None):
    """The shows to hand seats.sample this run: per chain at most capacity(chain), each one seats.pick would
    accept (starting within the next seats.WINDOW_H hours, readable, not sampled in the last RESAMPLE_MIN).
    Order, tier by tier: 1) 30–180 min out with no sample still shown (< seats.FRESH_MIN), 2) 30–180 min out with
    an older one, 3) under 30 min out. Inside a tier: one show per cinema, the busiest cinema first (most shows on
    now's date in `day_shows`), before a second show anywhere; inside a cinema the show nearest 2 h out first
    (BEST_LEAD_MIN), then the sooner. Handing each chain no more than it can read keeps seats.pick's own
    id-order walk from choosing among them."""
    import seats
    recent = recent or {}
    end = now + timedelta(hours=seats.WINDOW_H)
    today = now.date().isoformat()
    busy = {}
    for s in day_shows or todo:
        if s.get("date") == today:
            busy[s.get("cinema")] = busy.get(s.get("cinema"), 0) + 1
    tiers, seen = {}, set()
    for s in todo:
        chain = s.get("_chain")
        if chain not in seats.SUPPORTED or (chain in seats.NEEDS_SID and not s.get("_sid")):
            continue
        if chain in ("vox", "cinemacity") and not s.get("book"):
            continue
        try:
            st = seats._start(s)
        except (KeyError, ValueError, TypeError):
            continue
        k = seats.show_key(s)
        if not (now < st <= end) or k in seen or seats.fresh(recent.get(k), now, seats.RESAMPLE_MIN):
            continue
        seen.add(k)
        lead = (st - now).total_seconds() / 60
        tier = 2 if lead < REACH_MIN else 1 if seats.fresh(recent.get(k), now) else 0
        tiers.setdefault(chain, {}).setdefault(tier, {}).setdefault(s.get("cinema"), []).append(((abs(lead - BEST_LEAD_MIN), st), s))
    out = []
    for chain, by_tier in sorted(tiers.items()):
        n, picked = capacity(chain, cap), []
        for tier in sorted(by_tier):
            cins = sorted(by_tier[tier].items(), key=lambda kv: (-busy.get(kv[0], 0), str(kv[0])))
            queues = [sorted(v, key=lambda t: t[0]) for _, v in cins]
            while any(queues) and len(picked) < n:
                for q in queues:
                    if q and len(picked) < n:
                        picked.append(q.pop(0)[1])
        out.extend(picked)
    return out


def run(data, ctx):
    shows = data.get("shows") or []
    handles = []
    for s in shows:                          # first, whatever happens next: nothing private is published
        handles.append({k: s.pop(k) for k in [k for k in s if k.startswith("_")]})

    import seats
    import statefile

    def load(path):
        got, _status = statefile.load_state_json(path, path.with_name(path.name + ".bak"))
        return got if isinstance(got, dict) else {}

    def save(path, obj):
        statefile.write_state_json(path, path.with_name(path.name + ".bak"), obj)

    parse = seats._parse_at
    cinemas = data.get("cinemas") or {}
    now = parse(ctx.get("now")) or datetime.now(seats.DUBAI)
    ddir = Path(ctx.get("data_dir") or Path(__file__).resolve().parent.parent / "data")
    maps_path, occ_path = ddir / "seatmaps.json", ddir / "occupancy.json"

    # hall shapes from this run's price samples
    sm = load(maps_path)
    if sm.get("v") != 2:                     # the first format keyed by label only: start again
        sm = {}
    halls, maps = dict(sm.get("halls") or {}), dict(sm.get("maps") or {})
    with seats._LOCK:
        kept = dict(seats.KEPT)
        seats.KEPT.clear()
    for hk, v in kept.items():
        key = seats.shape_key(v["shape"])
        maps[key] = v["shape"]
        halls[hk] = {"m": key, "at": v["at"]}
    cutoff = now - timedelta(days=KEEP_DAYS)
    halls = {k: v for k, v in halls.items() if (parse(v.get("at")) or now) >= cutoff and k.count("|") >= 2}
    maps = {k: v for k, v in maps.items() if k in {h["m"] for h in halls.values()}}
    if kept or sm:
        save(maps_path, {"v": 2, "halls": halls, "maps": maps})

    # occupancy for the shows about to start
    occ = load(occ_path)
    occ_shows, occ_maps = dict(occ.get("shows") or {}), dict(occ.get("maps") or {})
    report = {}
    if not ctx.get("offline"):
        # ctx["now"] is the refresh's start, and the chains run first (~30 min on a day's first run): a live
        # step picks, stamps and judges freshness on its own clock, or every sample looks "from the future"
        now = max(now, datetime.now(seats.DUBAI))
        todo = []
        for s, h in zip(shows, handles):
            chain = (cinemas.get(s.get("cinema")) or {}).get("chain")
            if chain in seats.SUPPORTED:
                todo.append({**s, "_chain": chain, "_sid": h.get("_sid")})
        aimed = aim(todo, now, recent=occ_shows, day_shows=shows)
        got, report = seats.sample(aimed, now, recent=occ_shows)
        for s in aimed:
            r = report.setdefault(s["_chain"], {})
            r["aimed"] = r.get("aimed", 0) + 1
        now = max(now, datetime.now(seats.DUBAI))       # the sampler ran up to ~4 minutes
        for k, v in got.items():
            key = seats.shape_key(v["shape"])
            occ_maps[key] = v["shape"]
            occ_shows[k] = {"free": v["free"], "total": v["total"], "at": v["at"], "m": key, "st": v["st"], "best": v["best"]}
    old = now - timedelta(hours=KEEP_OCC_H)
    occ_shows = {k: v for k, v in occ_shows.items() if (parse(v.get("at")) or old) > old}
    occ_maps = {k: v for k, v in occ_maps.items() if k in {e.get("m") for e in occ_shows.values()}}
    if occ_shows or occ:
        save(occ_path, {"shows": occ_shows, "maps": occ_maps})

    # which shape belongs to which label: {"cinema|label": {screen: shape key}}
    by_label = {}
    for hk, v in halls.items():
        base, _, screen = hk.rpartition("|")
        by_label.setdefault(base, {})[screen] = v["m"]

    attached, drawn, used = 0, 0, {}
    for s, h in zip(shows, handles):
        s.pop("seats", None); s.pop("seatmap", None)
        e = occ_shows.get(seats.show_key(s))
        if e and seats.fresh(e, now) and e.get("m") in occ_maps:
            s["seats"] = {k: e[k] for k in ("free", "total", "at", "m", "st", "best")}
            used[e["m"]] = occ_maps[e["m"]]
            attached += 1
        seen = by_label.get(f"{s.get('cinema')}|{s.get('hall_label') or ''}") or {}
        screen = h.get("_screen")
        if screen:
            m = seen.get(str(screen))
        else:           # every shape seen for the label (named screens included): exactly one, or nothing
            distinct = set(seen.values())
            m = distinct.pop() if len(distinct) == 1 else None
        if m and m in maps:
            s["seatmap"] = m
            used[m] = maps[m]
            drawn += 1
    data["seats_now"] = now.isoformat()   # the build judges each sample's freshness by this clock (pages/seats.py)
    if used:
        data["seatmaps"] = {"maps": used}
    else:
        data.pop("seatmaps", None)

    return {"maps_kept": len(kept), "shapes": len(maps), "drawn": drawn, "attached": attached,
            "chains": {c: r for c, r in sorted(report.items())}}
