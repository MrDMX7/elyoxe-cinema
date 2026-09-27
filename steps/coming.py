"""steps/coming.py — merges coming.fetch_all() into data["coming"] by film fid.

run(data, ctx) -> {"chains": {chain: {"ok","items","error"}}, "films": int}

Same fid as the shows we already publish (normalize.film_fid — imported, never re-implemented)
so a coming-soon film that opens next week folds into the same page once a chain's showtimes
feed picks it up, instead of getting a second, orphaned entry.

data["coming"][fid] = {"title", "title_ar", "release_date" (earliest one seen, or None),
                        "poster", "trailer", "genres": [...], "chains": [chain, ...]}

Two chains naming the same film slightly differently (a stray subtitle, punctuation) end up as
two fids here -- that's the same limitation normalize.merge_duplicates solves for showtimes, and
out of scope for this step; each is still a real, correctly-sourced coming-soon entry either way.

A fid already showing (in data["films"] and not archived, or with a show dated today/tomorrow)
is never listed here -- see _already_showing_fids(). roxy and cineroyal are scraped from a
homepage tab/div rather than a dedicated coming-soon endpoint and can go a day stale.

Offline (ctx["offline"] or COMING_OFFLINE fixtures unavailable): network calls are skipped
entirely and data["coming"] is left untouched (never wiped) -- a step that can't refresh its
data must not blank what a previous successful run wrote.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import coming
import normalize


def _today_tomorrow(now_iso) -> tuple[str, str]:
    try:
        d = datetime.fromisoformat(now_iso).date() if now_iso else date.today()
    except ValueError:
        d = date.today()
    return d.isoformat(), (d + timedelta(days=1)).isoformat()


def _already_showing_fids(data: dict, today: str, tomorrow: str) -> set[str]:
    """fix round 1 (review, Important): a fid must never appear in data["coming"] once it is
    actually showing -- roxy and cineroyal are scraped from a homepage tab/div rather than a
    dedicated coming-soon endpoint, and can go a day stale if a chain forgets to move a film out
    of it. Two independent signals, either is enough: the fid is in data["films"] and not
    archived (site_kit.py's own site.showing rule), or it has a show dated today/tomorrow at all
    (belt-and-suspenders against a film not yet folded into data["films"] this run)."""
    out = {fid for fid, f in (data.get("films") or {}).items() if f.get("status") != "archived"}
    for s in data.get("shows") or []:
        if s.get("date") in (today, tomorrow) and s.get("film"):
            out.add(s["film"])
    return out


def _merge(data: dict, results: dict, today: str, tomorrow: str) -> int:
    out = dict(data.get("coming") or {})
    for chain, r in results.items():
        for item in r.get("items") or []:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            fid = normalize.film_fid(title)
            cur = out.get(fid) or {"title": title, "title_ar": None, "release_date": None,
                                    "poster": None, "trailer": None, "genres": [], "chains": []}
            cur["title_ar"] = cur["title_ar"] or item.get("title_ar")
            rd = item.get("release_date")
            if rd and (not cur["release_date"] or rd < cur["release_date"]):
                cur["release_date"] = rd
            cur["poster"] = cur["poster"] or item.get("poster")
            cur["trailer"] = cur["trailer"] or item.get("trailer")
            for g in item.get("genres") or []:
                if g not in cur["genres"]:
                    cur["genres"].append(g)
            if chain not in cur["chains"]:
                cur["chains"].append(chain)
            out[fid] = cur
    showing = _already_showing_fids(data, today, tomorrow)
    out = {fid: f for fid, f in out.items() if fid not in showing}
    data["coming"] = out
    return len(out)


def run(data: dict, ctx: dict) -> dict | None:
    if ctx.get("offline"):
        return {"chains": {}, "films": len(data.get("coming") or {}), "note": "offline: left as-is"}

    today, tomorrow = _today_tomorrow(ctx.get("now"))
    results = coming.fetch_all()
    n = _merge(data, results, today, tomorrow)

    # best-effort poster mirror, reusing posters.py's own mirror() against a {"films": ...}-shaped
    # view of data["coming"] (same cache/bucket/prefix as the main film posters -- a coming-soon
    # film keeps the same fid and poster once it opens and merges into data["films"]).
    try:
        import posters as posters_mod  # lazy: a missing Pillow costs the posters, not this step

        view = {"films": {fid: dict(f, poster_src=[f["poster"]] if f.get("poster") else [])
                           for fid, f in data["coming"].items()}}
        stats = posters_mod.mirror(view)
        for fid, f in view["films"].items():
            for k in ("poster", "poster_2x", "poster_color"):
                if f.get(k):
                    data["coming"][fid][k] = f[k]
    except Exception as e:  # noqa: BLE001 - posters are a nice-to-have here, never load-bearing
        stats = {"error": str(e)}

    return {"chains": {c: {"ok": r["ok"], "error": r["error"], "n": len(r["items"])}
                       for c, r in results.items()},
            "films": n, "posters": stats}
