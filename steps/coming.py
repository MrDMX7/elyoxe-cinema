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

Offline (ctx["offline"] or COMING_OFFLINE fixtures unavailable): network calls are skipped
entirely and data["coming"] is left untouched (never wiped) -- a step that can't refresh its
data must not blank what a previous successful run wrote.
"""
from __future__ import annotations

import coming
import normalize


def _merge(data: dict, results: dict) -> int:
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
    data["coming"] = out
    return len(out)


def run(data: dict, ctx: dict) -> dict | None:
    if ctx.get("offline"):
        return {"chains": {}, "films": len(data.get("coming") or {}), "note": "offline: left as-is"}

    results = coming.fetch_all()
    n = _merge(data, results)

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
