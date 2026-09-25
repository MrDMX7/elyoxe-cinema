"""Merge the 7 chain readers' output into data/latest.json's shape, and slice it per city.

Shapes: docs/superpowers/plans/2026-09-25-cinema.md ("Task 1 … Interfaces — Produces") for
Cinema/Show, and docs/superpowers/specs/2026-09-25-cinema-design.md ("Shape of the data") for
the merged file. Films are matched across chains by a cleaned-title slug (readers/common.py
slug()) so "Heart of the Beast" and "HEART OF THE BEAST (PG13)" become one film.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from readers.common import slug

# All reader-supplied show date/time strings are Asia/Dubai local time (no reader emits an
# offset), and Dubai has stayed at a fixed UTC+4 with no DST, so a fixed-offset tzinfo is exact.
_DUBAI_TZ = timezone(timedelta(hours=4))

# Bracketed/parenthesised suffixes and trailing release-format tags to drop when matching a
# film across chains — but never "Encore": that is a different release of the same title, not
# a tag on it, so it must keep its own fid.
_TRAILING_PARENS = re.compile(r"\s*\([^)]*\)\s*$")
_TRAILING_BRACKETS = re.compile(r"\s*\[[^\]]*\]\s*$")
_TRAILING_IMAX = re.compile(r"\s*-?\s*IMAX\s*$", re.IGNORECASE)
_TRAILING_3D2D = re.compile(r"\s*-?\s*[23]D\s*$", re.IGNORECASE)
_TRAILING_DUBBED = re.compile(r"\s*-\s*Dubbed\s*$", re.IGNORECASE)


def clean_title(title: str) -> str:
    """Strip chain-specific decoration from a film title, keeping "Encore" intact."""
    t = title.strip()
    prev = None
    while prev != t:
        prev = t
        t = _TRAILING_PARENS.sub("", t)
        t = _TRAILING_BRACKETS.sub("", t)
        t = _TRAILING_IMAX.sub("", t)
        t = _TRAILING_3D2D.sub("", t)
        t = _TRAILING_DUBBED.sub("", t)
        t = t.strip()
    return t.replace("&", "and")


def film_fid(title: str) -> str:
    return slug(clean_title(title))


def _better_title(candidate: str, current: str) -> bool:
    """Prefer a normally-cased title ("Heart of the Beast") over an ALL-CAPS one."""
    return current.isupper() and not candidate.isupper()


def _show_dt(show: dict) -> datetime:
    """A show's date+time as Asia/Dubai local time (naive — readers never emit an offset)."""
    return datetime.fromisoformat(f"{show['date']}T{show['time']}")


def _local_now(now: str) -> datetime:
    """Parse `now` (naive or tz-aware ISO) into a naive Asia/Dubai local datetime.

    A naive string is already assumed to be Dubai local time (same convention as show
    date/time). A tz-aware string is converted to Dubai local time first, so a UTC or other
    offset `now` compares correctly against the naive show times.
    """
    dt = datetime.fromisoformat(now)
    if dt.tzinfo is not None:
        dt = dt.astimezone(_DUBAI_TZ).replace(tzinfo=None)
    return dt


def merge(results: dict[str, dict | None], previous: dict | None, now: str) -> dict:
    """Merge each chain's fetch() output (or None/error on failure) into latest.json's shape.

    `results[chain]` is a reader's {"cinemas": [...], "shows": [...]} on success, or None / an
    Exception / an error string on failure. A failed chain keeps its cinemas and shows from
    `previous` (and its previous "at"), marked ok:false with the error. Shows more than 30
    minutes in the past (relative to `now`) are dropped from the output.
    """
    previous = previous or {}
    prev_cinemas: dict = previous.get("cinemas", {})
    prev_shows: list = previous.get("shows", [])
    prev_chains: dict = previous.get("chains", {})
    prev_films: dict = previous.get("films", {})

    chains_out: dict = {}
    cinemas_out: dict = {}
    shows_out: list = []
    films_acc: dict = {}

    def add_film(chain: str, show: dict) -> str:
        cleaned = clean_title(show["film_title"])
        fid = film_fid(show["film_title"])
        acc = films_acc.setdefault(
            fid,
            {
                "title": cleaned,
                "lang": None,
                "rating": None,
                "runtime": None,
                "poster": None,
                "chains": set(),
            },
        )
        if _better_title(cleaned, acc["title"]):
            acc["title"] = cleaned
        if show.get("film_lang") and not acc["lang"]:
            acc["lang"] = show["film_lang"]
        if show.get("film_rating") and not acc["rating"]:
            acc["rating"] = show["film_rating"]
        runtime = show.get("runtime")
        if runtime is not None:
            acc["runtime"] = max(acc["runtime"] or 0, runtime)
        if show.get("poster") and not acc["poster"]:
            acc["poster"] = show["poster"]
        acc["chains"].add(chain)
        return fid

    def add_prev_film(chain: str, fid: str) -> None:
        pf = prev_films.get(fid)
        acc = films_acc.setdefault(
            fid,
            {
                "title": (pf or {}).get("title", fid),
                "lang": (pf or {}).get("lang"),
                "rating": (pf or {}).get("rating"),
                "runtime": (pf or {}).get("runtime"),
                "poster": (pf or {}).get("poster"),
                "chains": set(),
            },
        )
        acc["chains"].add(chain)

    def carry_over_chain(chain: str) -> None:
        """Restore a chain's cinemas + shows from `previous` verbatim (failed or not run)."""
        prev_chain_cinema_ids = {cid for cid, c in prev_cinemas.items() if c.get("chain") == chain}
        for cid in prev_chain_cinema_ids:
            cinemas_out[cid] = prev_cinemas[cid]
        for show in prev_shows:
            if show.get("cinema") in prev_chain_cinema_ids:
                shows_out.append(dict(show))
                if show.get("film"):
                    add_prev_film(chain, show["film"])

    for chain, result in results.items():
        prev_chain_info = prev_chains.get(chain, {})
        ok = isinstance(result, dict)

        if ok:
            chains_out[chain] = {"ok": True, "at": now, "error": None}
            for cinema in result.get("cinemas", []):
                cinemas_out[cinema["id"]] = dict(cinema)
            for show in result.get("shows", []):
                fid = add_film(chain, show)
                s = {k: v for k, v in show.items() if k not in ("film_title", "film_lang", "film_rating", "runtime", "poster")}
                s["film"] = fid
                shows_out.append(s)
        else:
            error = None if result is None else str(result)
            chains_out[chain] = {
                "ok": False,
                "at": prev_chain_info.get("at", now),
                "error": error or "no data",
            }
            carry_over_chain(chain)

    # A chain that was refreshed before but isn't in `results` at all this run (e.g. its reader
    # crashed before returning, or was skipped) is stale, not silently dropped.
    for chain, prev_chain_info in prev_chains.items():
        if chain in results:
            continue
        chains_out[chain] = {
            "ok": False,
            "at": prev_chain_info.get("at", now),
            "error": "not run",
        }
        carry_over_chain(chain)

    cutoff = _local_now(now) - timedelta(minutes=30)
    shows_out = [s for s in shows_out if _show_dt(s) >= cutoff]
    shows_out.sort(key=lambda s: (s["date"], s["time"]))

    referenced_fids = {s["film"] for s in shows_out}
    films_out = {
        fid: {
            "title": acc["title"],
            "lang": acc["lang"],
            "rating": acc["rating"],
            "runtime": acc["runtime"],
            "poster": acc["poster"],
            "chains": sorted(acc["chains"]),
        }
        for fid, acc in films_acc.items()
        if fid in referenced_fids
    }

    return {
        "generated": now,
        "chains": chains_out,
        "cinemas": cinemas_out,
        "films": films_out,
        "shows": shows_out,
    }


def city_slices(data: dict) -> dict:
    """Per-city subsets of a merged latest.json: {city: {generated, chains, cinemas, films, shows}}."""
    cinemas = data.get("cinemas", {})
    shows = data.get("shows", [])
    films = data.get("films", {})
    chains = data.get("chains", {})

    by_city: dict[str, dict] = {}
    for cid, cinema in cinemas.items():
        city = cinema.get("city")
        if city is None:
            continue
        by_city.setdefault(city, {})[cid] = cinema

    slices: dict[str, dict] = {}
    for city, city_cinemas in by_city.items():
        city_cids = set(city_cinemas)
        city_shows = [s for s in shows if s.get("cinema") in city_cids]
        fids = {s["film"] for s in city_shows if s.get("film")}
        city_films = {fid: films[fid] for fid in fids if fid in films}
        used_chains = {c.get("chain") for c in city_cinemas.values()}
        city_chains = {ch: v for ch, v in chains.items() if ch in used_chains}
        slices[city] = {
            "generated": data.get("generated"),
            "chains": city_chains,
            "cinemas": city_cinemas,
            "films": city_films,
            "shows": city_shows,
        }
    return slices
