"""Merge the 7 chain readers' output into data/latest.json's shape, and slice it per city.

Shapes: docs/superpowers/plans/2026-09-25-cinema.md ("Task 1 … Interfaces — Produces") for
Cinema/Show, and docs/superpowers/specs/2026-09-25-cinema-design.md ("Shape of the data") for
the merged file. Films are matched across chains by a cleaned-title slug (readers/common.py
slug()) so "Heart of the Beast" and "HEART OF THE BEAST (PG13)" become one film.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from genres import genre_keys, merge_keys
from readers.common import slug, youtube_id

_HERE = os.path.dirname(os.path.abspath(__file__))
ALIASES_PATH = os.path.join(_HERE, "aliases.yaml")
CHAINS_PATH = os.path.join(_HERE, "chains.yaml")
CINEMAS_PATH = os.path.join(_HERE, "cinemas.yaml")
DEFAULT_AD_OFFSET = 15
# carried from the previous latest.json when this run finds nothing better for a film
_PREV_FILM_EXTRAS = ("poster", "poster_2x", "poster_color", "trailer")

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


def merge(results: dict[str, dict | None], previous: dict | None, now: str,
          aliases: dict | None = None) -> dict:
    """Merge each chain's fetch() output (or None/error on failure) into latest.json's shape.

    `results[chain]` is a reader's {"cinemas": [...], "shows": [...]} on success, or None / an
    Exception / an error string on failure. A failed chain keeps its cinemas and shows from
    `previous` (and its previous "at"), marked ok:false with the error. Shows more than 30
    minutes in the past (relative to `now`) are dropped from the output.

    The same film listed under different titles by different chains ("The Vvaan: Force of the
    Forest" / "...Forrest", "Minions & Monsters" / "Minions Monsters") is merged into one fid by
    merge_duplicates() -- `aliases` ({"aliases": {raw fid: canonical}, "titles": {fid: title}},
    default: aliases.yaml) first, then the automatic rules. data["merged"] records
    {merged-away fid: canonical fid} for this run.
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
                "poster_src": [],
                "trailer": None,
                "genres": [],
                "title_ar": None,
                "chains": set(),
            },
        )
        if show.get("film_poster") and show["film_poster"] not in acc["poster_src"]:
            acc["poster_src"].append(show["film_poster"])
        if not acc["trailer"]:
            acc["trailer"] = youtube_id(show.get("film_trailer"))
        if show.get("film_genres"):
            acc["genres"] = merge_keys(acc["genres"], genre_keys(show["film_genres"]))
        if show.get("film_title_ar") and not acc["title_ar"]:
            acc["title_ar"] = show["film_title_ar"]
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
                "poster_src": [],
                "trailer": (pf or {}).get("trailer"),
                "genres": list((pf or {}).get("genres") or []) if isinstance((pf or {}).get("genres"), list) else [],
                "title_ar": (pf or {}).get("title_ar_chain"),
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

    chains_cfg = load_chains()

    for chain, result in results.items():
        prev_chain_info = prev_chains.get(chain, {})
        ok = isinstance(result, dict)

        if ok:
            chains_out[chain] = {"ok": True, "at": now, "error": None}
            for cinema in result.get("cinemas", []):
                cinemas_out[cinema["id"]] = dict(cinema)
            for show in result.get("shows", []):
                fid = add_film(chain, show)
                s = {k: v for k, v in show.items()
                     if not k.startswith("film_") and k not in ("runtime", "poster")}
                if not s.get("lang"):
                    s.pop("lang", None)
                if not s.get("subs"):
                    s.pop("subs", None)
                ends = end_time(show["date"], show["time"], show.get("runtime"), ad_offset(chains_cfg, chain))
                if ends:
                    s["ends"] = ends
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
    films_acc = {fid: acc for fid, acc in films_acc.items() if fid in referenced_fids}
    counts: dict[str, int] = {}
    for s in shows_out:
        counts[s["film"]] = counts.get(s["film"], 0) + 1
    if aliases is None:
        aliases = load_aliases()
    films_acc, mapping = merge_duplicates(films_acc, aliases, counts)
    for s in shows_out:
        s["film"] = mapping.get(s["film"], s["film"])

    films_out = {}
    for fid, acc in films_acc.items():
        f = {
            "title": acc["title"],
            "lang": acc["lang"],
            "rating": acc["rating"],
            "runtime": acc["runtime"],
            "poster": acc["poster"],
            "trailer": acc.get("trailer"),
            "genres": list(acc.get("genres") or []),
            "chains": sorted(acc["chains"]),
        }
        if acc.get("poster_src"):
            f["poster_src"] = list(acc["poster_src"])
        pf = prev_films.get(fid) or {}
        for k in _PREV_FILM_EXTRAS:
            if not f.get(k) and pf.get(k):
                f[k] = pf[k]
        if acc.get("title_ar"):
            f["title_ar_chain"] = acc["title_ar"]
        films_out[fid] = f

    out = {
        "generated": now,
        "chains": chains_out,
        "cinemas": cinemas_out,
        "films": films_out,
        "shows": shows_out,
    }
    if mapping:
        out["merged"] = dict(sorted(mapping.items()))
    return out


# ---------------------------------------------------------------- cross-chain duplicates

def load_aliases(path: str = ALIASES_PATH) -> dict:
    """aliases.yaml -> {"aliases": {raw fid: canonical fid}, "titles": {canonical fid: display title}}."""
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
    except (OSError, ImportError):
        return {"aliases": {}, "titles": {}}
    return {"aliases": dict(y.get("aliases") or {}), "titles": dict(y.get("titles") or {})}


_NUMBER = re.compile(r"^(?:\d+|ii|iii|iv|vi|vii|viii|ix)$")
# a subtitle that names a different release of the same film -- never merged into the plain title
_RELEASE_WORDS = {"encore", "anniversary", "rerelease", "re", "remastered", "extended", "cut"}
_SUBTITLE_SEP = re.compile(r"\s*(?::|\s[-\u2013\u2014]\s|\s-|-\s)\s*")
RUNTIME_TOLERANCE = 6  # minutes


def _tokens(title: str) -> list[str]:
    """Cleaned title -> comparison tokens: lowercase words, "and"/"&" dropped, a leading "the" dropped."""
    toks = [t for t in slug(clean_title(title)).split("-") if t and t != "and"]
    if toks and toks[0] == "the":
        toks = toks[1:]
    return toks


def _numbers(toks: list[str]) -> list[str]:
    return [t for t in toks if _NUMBER.match(t)]


def _lev(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein distance, stopping early once every path exceeds `cap`."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _runtime_close(a, b):
    """True/False when both runtimes are known, None when either is missing."""
    if not a or not b:
        return None
    return abs(a - b) <= RUNTIME_TOLERANCE


def same_film(a: dict, b: dict) -> bool:
    """The automatic duplicate rule for two films' accumulators ({title, runtime, lang}).

    1. identical comparison tokens (leading "the" and "and"/"&" ignored) -> same film;
    2. one title is the other plus a ":"/" - " subtitle (the head before the separator has the
       other's exact tokens), the subtitle carries no number and no release word (Encore,
       Anniversary...), and runtimes, when both are known, are within 6 minutes;
    3. near-identical spelling: edit distance <= 2 on titles of 8+ characters, and runtimes
       within 6 minutes or the same language.
    Never across a differing number token: Fall / Fall 2, Toy Story 4 / 5, Volume 2 / 3 stay apart.
    """
    ta, tb = _tokens(a["title"]), _tokens(b["title"])
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    rt = _runtime_close(a.get("runtime"), b.get("runtime"))
    for y, tx in ((b, ta), (a, tb)):
        parts = _SUBTITLE_SEP.split(clean_title(y["title"]), maxsplit=1)
        if len(parts) == 2:
            head, sub = _tokens(parts[0]), _tokens(parts[1])
            if (head == tx and sub and not _numbers(sub) and not (set(sub) & _RELEASE_WORDS)
                    and rt is not False):
                return True
    if _numbers(ta) != _numbers(tb):
        return False
    sa, sb = " ".join(ta), " ".join(tb)
    if min(len(sa), len(sb)) < 8 or _lev(sa, sb, 2) > 2:
        return False
    same_lang = bool(a.get("lang")) and a.get("lang") == b.get("lang")
    return rt is True or same_lang


def merge_duplicates(films: dict, aliases: dict | None = None, counts: dict | None = None):
    """{fid: acc} -> ({canonical fid: merged acc}, {merged-away fid: canonical fid}).

    aliases.yaml wins first (raw fid -> canonical, applied even when only one spelling is on
    today); the automatic rule (same_film) then clusters what's left. A cluster's canonical fid
    is an aliases.yaml target when one is in it, else the longest cleaned title (ties: more
    shows, then alphabetical). The merged film keeps the canonical's fields and fills gaps from
    the others; its title is aliases.yaml's `titles` entry when there is one.
    """
    aliases = aliases or {}
    amap: dict = aliases.get("aliases") or {}
    titles: dict = aliases.get("titles") or {}
    counts = counts or {}

    def target(fid: str) -> str:
        seen = set()
        while fid in amap and fid not in seen:
            seen.add(fid)
            fid = amap[fid]
        return fid

    fids = sorted(films)
    parent = {f: f for f in fids}

    def find(f):
        while parent[f] != f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_target: dict = {}
    for f in fids:
        by_target.setdefault(target(f), []).append(f)
    for group in by_target.values():
        for f in group[1:]:
            union(group[0], f)
    for i, a in enumerate(fids):
        for b in fids[i + 1:]:
            if find(a) != find(b) and same_film(films[a], films[b]):
                union(a, b)

    clusters: dict = {}
    for f in fids:
        clusters.setdefault(find(f), []).append(f)

    alias_targets = set(amap.values())
    out: dict = {}
    mapping: dict = {}
    for members in clusters.values():
        targets = sorted({target(m) for m in members if target(m) != m or m in alias_targets})
        if targets:
            canon = targets[0]
        else:
            canon = sorted(members, key=lambda m: (-len(clean_title(films[m]["title"])),
                                                   -counts.get(m, 0), m))[0]
        order = sorted(members, key=lambda m: (m != canon, -counts.get(m, 0), m))
        acc = dict(films.get(canon) or films[order[0]])
        acc["chains"] = set()
        for m in order:
            fm = films[m]
            acc["chains"] |= set(fm.get("chains") or ())
            for k in ("lang", "rating", "runtime", "poster", "title_ar", "trailer"):
                if not acc.get(k) and fm.get(k):
                    acc[k] = fm[k]
            acc["genres"] = merge_keys(acc.get("genres"), fm.get("genres"))
            acc["poster_src"] = list(dict.fromkeys((acc.get("poster_src") or []) + (fm.get("poster_src") or [])))
            if _better_title(fm["title"], acc["title"]):
                acc["title"] = fm["title"]
        if titles.get(canon):
            acc["title"] = titles[canon]
        out[canon] = acc
        for m in members:
            if m != canon:
                mapping[m] = canon
    return out, mapping


# ---------------------------------------------------------------- phase 1 derived fields

_RATINGS = ("G", "PG", "PG13", "PG15", "15+", "18+")


def uae_rating(raw) -> str | None:
    """A chain's certificate -> one of G, PG, PG13, PG15, 15+, 18+ (UAE classes); None if unknown.
    "PG-13"/"PG 13" -> PG13, "15" -> 15+, "18TC" -> 18+, Reel's "TBA-PG15" -> PG15, "TBA" -> None."""
    if not raw or not isinstance(raw, str):
        return None
    t = re.sub(r"[\s\-_]", "", raw.upper())
    if t.startswith("TBA"):
        t = t[3:]
    if t in _RATINGS:
        return t
    if re.match(r"^15(\+|PLUS)?$", t):
        return "15+"
    if re.match(r"^(18|21)(\+|PLUS)?(TC)?$", t):
        return "18+"
    return None


def derive_flags(rating, genres) -> dict:
    """family: G/PG/PG13. kids: G/PG and the film is animation or family."""
    g = set(genres or [])
    return {"family": rating in ("G", "PG", "PG13"),
            "kids": rating in ("G", "PG") and bool(g & {"animation", "family"})}


def end_time(date: str, time: str, runtime, offset) -> str | None:
    """HH:MM the film lets out: start + ad offset + runtime (wraps past midnight). None without runtime."""
    try:
        runtime = int(runtime or 0)
    except (TypeError, ValueError):
        return None
    if runtime <= 0:
        return None
    try:
        start = datetime.fromisoformat(f"{date}T{time}")
    except (TypeError, ValueError):
        return None
    return (start + timedelta(minutes=runtime + int(offset or 0))).strftime("%H:%M")


def _load_yaml(path):
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, ImportError):
        return {}


def load_chains(path: str = CHAINS_PATH) -> dict:
    """chains.yaml -> {"default_ad_offset_min": int, "chains": {chain: {"ad_offset_min": int}}}."""
    y = _load_yaml(path)
    return {"default_ad_offset_min": y.get("default_ad_offset_min", DEFAULT_AD_OFFSET),
            "chains": dict(y.get("chains") or {})}


def ad_offset(cfg: dict | None, chain: str | None) -> int:
    cfg = cfg or {}
    default = cfg.get("default_ad_offset_min", DEFAULT_AD_OFFSET)
    return int(((cfg.get("chains") or {}).get(chain) or {}).get("ad_offset_min", default))


def load_cinema_meta(path: str = CINEMAS_PATH) -> dict:
    """cinemas.yaml `cinemas:` -> {cid: {ar, en, lat, lng, coord_source}}."""
    return dict(_load_yaml(path).get("cinemas") or {})


def maps_url(lat, lng) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def finalize(data: dict, chains_cfg: dict | None = None, cinema_meta: dict | None = None) -> dict:
    """The fields derived after merge + enrich (so Wikidata's runtime/genres count):
    chains[*].ad_offset_min · films: rating normalised, genres as GENRES keys, family/kids ·
    shows: ends where still missing (film runtime) · cinemas: lat/lng/coord_source from
    cinemas.yaml (else the reader's own), maps = a Google Maps link to those coordinates."""
    chains_cfg = chains_cfg if chains_cfg is not None else load_chains()
    meta = cinema_meta if cinema_meta is not None else load_cinema_meta()

    for chain, info in (data.get("chains") or {}).items():
        info["ad_offset_min"] = ad_offset(chains_cfg, chain)

    films = data.get("films") or {}
    for f in films.values():
        f["rating"] = uae_rating(f.get("rating"))
        g = f.get("genres")
        if isinstance(g, dict):  # an older enrich shape {"ar": [...], "en": [...]}
            g = g.get("en")
        f["genres"] = merge_keys(genre_keys(g) if g else [])
        f.update(derive_flags(f["rating"], f["genres"]))

    cinemas = data.get("cinemas") or {}
    for s in data.get("shows") or []:
        if s.get("ends"):
            continue
        film = films.get(s.get("film")) or {}
        chain = (cinemas.get(s.get("cinema")) or {}).get("chain")
        ends = end_time(s["date"], s["time"], film.get("runtime"), ad_offset(chains_cfg, chain))
        if ends:
            s["ends"] = ends

    for cid, c in cinemas.items():
        m = meta.get(cid) or {}
        if m.get("lat") is not None and m.get("lng") is not None:
            c["lat"], c["lng"] = float(m["lat"]), float(m["lng"])
            c["coord_source"] = m.get("coord_source")
        if c.get("lat") is not None and c.get("lng") is not None:
            c["maps"] = maps_url(c["lat"], c["lng"])
    return data


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
