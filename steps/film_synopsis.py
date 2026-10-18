"""steps/film_synopsis.py — a synopsis for every showing film (owner 2026-10-18: «النبذة ضرورية»).

Wikipedia's lead (enrich.py → film["synopsis_en"]) covers about half the films; Arabic, Gulf and smaller Indian films
mostly have none. Before the intel step writes the Arabic synopsis (steps/intel.py, filmintel: Claude from
synopsis_en), this fills the gap from two more sources, in order, never overwriting an existing synopsis:
  1. Reel Cinemas' own film feed (Films.json on their public storage — the one readers/reel.py already reads):
     its `Synopsis` for the films Reel shows, matched by title.
  2. OMDb (the key steps/intel.py already uses for IMDb scores): the film's IMDb plot, by its IMDb id, else by title
     and year (the year must match when we know it), cached a month per film in data/omdb_plots.json.
film["synopsis_src"] says which one ("reel" | "omdb"). A source that fails is skipped; the step never raises.
Runs in name order before steps/intel.py ("film_…" < "intel")."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

REEL_FILMS = "https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Films.json"
_TAG = re.compile(r"\s*\((?:hindi|tamil|telugu|malayalam|kannada|arabic|english|3d|imax|2d|atmos|dubbed[^)]*)\)\s*", re.I)


def _key(title: str) -> str:
    t = _TAG.sub(" ", (title or "").lower())
    return re.sub(r"[^a-z0-9]+", "", t)


def _clean(text: str) -> str:
    t = re.sub(r"^\s*synopsis\s*:\s*", "", (text or "").strip(), flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _reel(data_dir: Path) -> dict:
    """{title key: synopsis} from Reel's feed (curl_cffi: it sits behind Cloudflare like their API)."""
    try:
        from curl_cffi import requests as cr
        films = cr.get(REEL_FILMS, impersonate="chrome120", timeout=30).json().get("value") or []
    except Exception as e:  # noqa: BLE001
        print(f"film_synopsis: reel feed unavailable: {e}")
        return {}
    out = {}
    for f in films:
        syn = _clean(f.get("Synopsis") or f.get("ShortSynopsis") or "")
        if len(syn) >= 40:
            out.setdefault(_key(f.get("Title") or ""), syn)
    return out


def _omdb_plot(film: dict, key: str, cache: dict, fid: str) -> str | None:
    hit = cache.get(fid)
    today = dt.date.today()
    if hit and hit.get("at", "") >= (today - dt.timedelta(days=30)).isoformat():
        return hit.get("plot") or None
    import omdb
    imdb = (film.get("imdb") or {}).get("id")
    params = {"i": imdb, "plot": "full"} if imdb else {"t": film.get("title") or "", "plot": "full", "type": "movie"}
    if not imdb and film.get("year"):
        params["y"] = str(film["year"])
    j = omdb._get(params, key) or {}
    plot = j.get("Plot") if j.get("Response") == "True" else None
    if plot and plot != "N/A" and not imdb and film.get("year") and str(j.get("Year", ""))[:4] not in (str(film["year"]), str(film["year"] - 1)):
        plot = None   # a title match from another year is another film
    plot = plot if plot and plot != "N/A" and len(plot) >= 40 else None
    cache[fid] = {"plot": plot, "at": today.isoformat()}
    return plot


def run(data: dict, ctx: dict) -> dict | None:
    if ctx.get("offline"):
        return {"skipped": "offline"}
    data_dir = Path(ctx.get("data_dir") or Path(__file__).resolve().parent.parent / "data")
    showing = {s.get("film") for s in data.get("shows") or []}
    need = {fid: f for fid, f in (data.get("films") or {}).items()
            if fid in showing and f.get("status") != "archived" and not f.get("synopsis_en")}
    if not need:
        return {"filled": 0}
    filled = {"reel": 0, "omdb": 0}
    reel = _reel(data_dir)
    for fid, f in need.items():
        for t in [f.get("title")] + list(f.get("aka") or []):
            syn = reel.get(_key(t or ""))
            if syn:
                f["synopsis_en"], f["synopsis_src"] = syn, "reel"
                filled["reel"] += 1
                break
    try:
        import omdb
        key = omdb._key()
    except Exception:   # noqa: BLE001
        key = None
    if key:
        cpath = data_dir / "omdb_plots.json"
        try:
            cache = json.loads(cpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        for fid, f in need.items():
            if f.get("synopsis_en"):
                continue
            try:
                plot = _omdb_plot(f, key, cache, fid)
            except Exception as e:  # noqa: BLE001
                print(f"film_synopsis: omdb {fid}: {e}")
                continue
            if plot:
                f["synopsis_en"], f["synopsis_src"] = plot, "omdb"
                filled["omdb"] += 1
        try:
            cpath.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return {"needed": len(need), "filled": filled, "still_none": sum(1 for f in need.values() if not f.get("synopsis_en"))}
