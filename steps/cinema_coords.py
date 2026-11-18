"""steps/cinema_coords.py — coordinates for a cinema a chain opened after cinemas.yaml was last written (owner 2026-11-18).

normalize.finalize() gives every cinema cinemas.yaml's lat/lng, else the reader's own when inside the UAE. A cinema with
neither is one nobody has written a yaml line for yet: VOX Moonlight (2026-11-12) froze the site for a week, because the
gate's test wanted its coordinates in the yaml. This step looks such a cinema up the way coords.py does by hand (the
chain's own page or map link, then OpenStreetMap Nominatim) and writes the answer on latest.json only, coord_source
"auto: <source>". The yaml line stays a person's job: refresh.yaml_health() raises one «cinemas.yaml» alert until it exists.
A cinema nobody could place is published without coordinates (no «أقرب سينما», «الوصول» searches Maps by name).

data/auto_coords.json: {cid: {lat, lng, coord_source, at}} for a hit, kept until the yaml has the cinema;
{cid: {miss: true, at}} for a miss, retried after MISS_DAYS. At most CAP lookups a run; offline makes none. A failing
lookup counts as a miss. Nothing here can stop the run (refresh.run_steps isolates it anyway)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAP = 5
MISS_DAYS = 2


def _default_locate(data_dir: Path):
    """coords.locate with one shared Geo (curl_cffi session, Nominatim pacing). Its page cache is this step's own
    data/auto_geocode.json, never coords.py's geocode_cache.json: a test reads that one whenever it exists, and the
    runner has none — a first lookup writing it would stop the gate this step is here to keep open."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import coords

    geo = coords.Geo(cache_path=data_dir / "auto_geocode.json")

    def locate(cid, c):
        try:
            return coords.locate(cid, c, geo)
        finally:
            geo.save()
    return locate


def _ok(city, lat, lng) -> bool:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import coords

    try:
        return coords.in_box(city, float(lat), float(lng))
    except (TypeError, ValueError):
        return False


def _apply(c: dict, lat, lng, src: str) -> None:
    c["lat"], c["lng"] = float(lat), float(lng)
    c["coord_source"] = src if src.startswith("auto: ") else f"auto: {src}"
    c["maps"] = f"https://www.google.com/maps/search/?api=1&query={c['lat']},{c['lng']}"


def run(data: dict, ctx: dict) -> dict:
    cinemas = data.get("cinemas") or {}
    todo = sorted(cid for cid, c in cinemas.items() if c.get("lat") is None or c.get("lng") is None)
    if not todo:
        return {"auto": [], "missing": []}
    path = Path(ctx.get("data_dir") or ROOT / "data") / "auto_coords.json"
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    now_s = ctx.get("now") or datetime.now().astimezone().isoformat()
    now = datetime.fromisoformat(now_s)
    locate = ctx.get("locate")
    auto, missing, looked = [], [], 0
    for cid in todo:
        c = cinemas[cid]
        e = cache.get(cid) or {}
        if e.get("lat") is not None and _ok(c.get("city"), e["lat"], e.get("lng")):
            _apply(c, e["lat"], e["lng"], e.get("coord_source") or "cached")
            auto.append(cid)
            continue
        fresh_miss = e.get("miss") and now - datetime.fromisoformat(e["at"]) < timedelta(days=MISS_DAYS)
        if fresh_miss or ctx.get("offline") or looked >= CAP:
            missing.append(cid)
            continue
        if locate is None:
            locate = _default_locate(path.parent)
        looked += 1
        try:
            r = locate(cid, c)
        except Exception as ex:  # noqa: BLE001 - a lookup that fails is a miss, never a failed run
            print(f"cinema_coords: {cid}: {type(ex).__name__}: {ex}", file=sys.stderr)
            r = None
        if r and _ok(c.get("city"), r[0], r[1]):
            cache[cid] = {"lat": float(r[0]), "lng": float(r[1]), "coord_source": r[2], "at": now_s}
            _apply(c, r[0], r[1], r[2])
            auto.append(cid)
        else:
            cache[cid] = {"miss": True, "at": now_s}
            missing.append(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return {"auto": auto, "missing": missing, "looked_up": looked}
