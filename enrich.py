"""Film enrichment: Wikidata + Rotten Tomatoes public page + Wikipedia summary.

No TMDB/OMDb keys exist for this project and none are created (controller ruling,
2026-09-25). Instead:
  - Wikidata (wbsearchentities + wbgetentities, no key) for title_ar, year, genres,
    director, cast, runtime, the IMDb id (P345) and the Rotten Tomatoes id (P1258).
  - The Rotten Tomatoes page itself (https://www.rottentomatoes.com/m/<id>) for the
    Tomatometer/Popcornmeter percentages, review counts and critics consensus —
    parsed out of the page's embedded `media-scorecard-json` block and the
    `#critics-consensus` div, not an API.
  - Wikipedia's REST summary endpoint for an English synopsis. No invention.
  - imdb_score is always written as null: there is no OMDb key, so it waits for one.

enrich(data, cache_path="data/films_cache.json", offline=False) -> dict mutates
data["films"][fid] in place, adding: title_ar, year, genres{ar,en}, director, cast,
runtime (only if missing), synopsis_en, wikidata{qid}, imdb{id}, imdb_score(None),
rt{critics, critics_count, audience, consensus, url}. `poster` is left untouched.

Cache (data/films_cache.json, gitignored): per-fid {"ids": {...permanent...},
"ratings": {...}, "ratings_at": ISO}. ids are cached forever once found; ratings
(the RT numbers) expire after 3 days and are refetched. offline=True never touches
the network — whatever is in the cache (or nothing) is used.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

UA = "elyoxe-cinema/1.0 (+https://elyoxe.com/cinema; contact hello@elyoxe.com)"
GAP_SECONDS = 2.0
RATINGS_TTL = timedelta(days=3)
FILM_QIDS = {"Q11424", "Q24862", "Q24869"}  # film, short film, television film

_last_call = [0.0]


def _polite_get(url, **kw):
    """A GET with a floor on time-between-requests, tolerant of network failure."""
    wait = GAP_SECONDS - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()
    kw.setdefault("timeout", 20)
    headers = kw.pop("headers", {})
    headers.setdefault("User-Agent", UA)
    try:
        return requests.get(url, headers=headers, **kw)
    except requests.RequestException:
        return None


def _load_cache(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_cache(path, cache):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _fresh(iso_ts):
    if not iso_ts:
        return False
    try:
        t = datetime.fromisoformat(iso_ts)
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - t < RATINGS_TTL


# ---------- Wikidata ----------

def _wikidata_search(title):
    r = _polite_get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbsearchentities", "search": title, "language": "en",
                "format": "json", "type": "item", "limit": 6},
    )
    if r is None or r.status_code != 200:
        return []
    try:
        return r.json().get("search", [])
    except ValueError:
        return []


def _wikidata_entities(ids):
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    r = _polite_get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbgetentities", "ids": "|".join(ids), "format": "json",
                "languages": "en|ar", "props": "labels|claims"},
    )
    if r is None or r.status_code != 200:
        return {}
    try:
        return r.json().get("entities", {})
    except ValueError:
        return {}


def _label(entities, qid, lang):
    labels = entities.get(qid, {}).get("labels", {})
    if lang in labels:
        return labels[lang]["value"]
    if "en" in labels:
        return labels["en"]["value"]
    return None


def _claim_values(entity, prop):
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        try:
            out.append(c["mainsnak"]["datavalue"]["value"])
        except (KeyError, TypeError):
            continue
    return out


def _claim_year(entity, prop="P577"):
    for v in _claim_values(entity, prop):
        try:
            return int(v["time"][1:5])
        except (KeyError, TypeError, ValueError):
            continue
    return None


_DESC_FILM = re.compile(r"\bfilm\b", re.IGNORECASE)
_DESC_NOT_FILM = re.compile(r"video game|soundtrack|\bscore\b|franchise|universe|book|novel", re.IGNORECASE)


def _looks_like_a_film(hit, ent):
    """P31 in FILM_QIDS covers plain "film"; Wikidata also has many film subtypes (animated
    film, documentary film, ...) not worth enumerating one by one, so fall back to the search
    hit's own description ("2026 animated film directed by ...") when P31 doesn't match.
    """
    instances = {v.get("id") for v in _claim_values(ent, "P31")}
    if instances & FILM_QIDS:
        return True
    desc = hit.get("description") or ""
    return bool(_DESC_FILM.search(desc)) and not _DESC_NOT_FILM.search(desc)


def _best_film_in_hits(hits):
    """Given wbsearchentities hits, returns (qid, is_recent) for the best film match, or (None, False)."""
    if not hits:
        return None, False
    entities = _wikidata_entities([h["id"] for h in hits])
    best, best_recent = None, False
    for h in hits:
        qid = h["id"]
        ent = entities.get(qid)
        if not ent or not _looks_like_a_film(h, ent):
            continue
        recent = _claim_year(ent) in (2025, 2026)
        if best is None:
            best, best_recent = qid, recent
        if recent and not best_recent:
            best, best_recent = qid, recent
        if recent:
            break
    return best, best_recent


def _find_film_qid(title):
    """Best-effort Wikidata match: instance-of film, 2025/2026 publication preferred.

    A plain title search often loses to a franchise/game entity of the same name (e.g.
    "Resident Evil" the video-game franchise outranks the 2026 film), or finds an older
    film with the same title (e.g. an "The Odyssey" from 2016). So: try the plain title
    first; if it doesn't land on a 2025/2026 film, retry with a "(2026 film)"/"(2025 film)"
    disambiguator, which is how Wikidata titles most just-released films. Fall back to
    whatever the plain search found (even if not recent) rather than nothing.
    """
    hits = _wikidata_search(title)
    qid, recent = _best_film_in_hits(hits)
    if recent:
        return qid
    for suffix in (" (2026 film)", " (2025 film)"):
        more_hits = _wikidata_search(title + suffix)
        more_qid, more_recent = _best_film_in_hits(more_hits)
        if more_recent:
            return more_qid
    return qid


def _wikidata_ids(title):
    """Returns a permanent-cacheable dict of ids/labels for a title, or {} if unmatched."""
    qid = _find_film_qid(title)
    if not qid:
        return {}
    entities = _wikidata_entities([qid])
    ent = entities.get(qid)
    if not ent:
        return {}

    genre_ids = [v.get("id") for v in _claim_values(ent, "P136")]
    director_ids = [v.get("id") for v in _claim_values(ent, "P57")]
    cast_ids = [v.get("id") for v in _claim_values(ent, "P161")][:3]
    side_entities = _wikidata_entities(genre_ids + director_ids + cast_ids)

    runtimes = _claim_values(ent, "P2047")
    runtime = None
    if runtimes:
        try:
            runtime = round(float(str(runtimes[0]["amount"]).lstrip("+")))
        except (KeyError, TypeError, ValueError):
            runtime = None

    imdb_ids = _claim_values(ent, "P345")
    rt_ids = _claim_values(ent, "P1258")

    return {
        "qid": qid,
        "title_ar": _label(entities, qid, "ar"),
        "year": _claim_year(ent),
        "runtime": runtime,
        "genres": {
            "en": [_label(side_entities, g, "en") for g in genre_ids if _label(side_entities, g, "en")],
            "ar": [_label(side_entities, g, "ar") for g in genre_ids if _label(side_entities, g, "ar")],
        },
        "director": next((_label(side_entities, d, "en") for d in director_ids
                           if _label(side_entities, d, "en")), None),
        "cast": [_label(side_entities, c, "en") for c in cast_ids if _label(side_entities, c, "en")],
        "imdb_id": imdb_ids[0] if imdb_ids else None,
        # Wikidata's P1258 value is sometimes bare ("heart_of_the_beast") and sometimes
        # already prefixed with the RT URL segment ("m/heart_of_the_beast") — normalise to bare.
        "rt_id": re.sub(r"^m/", "", rt_ids[0]) if rt_ids else None,
    }


# ---------- Rotten Tomatoes ----------

def _rt_ratings(rt_id):
    """Scrape the RT page for tomatometer/popcornmeter numbers and the consensus line."""
    r = _polite_get(f"https://www.rottentomatoes.com/m/{rt_id}")
    if r is None or r.status_code != 200:
        return None
    html = r.text
    m = re.search(r'id="media-scorecard-json"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        card = json.loads(m.group(1))
    except (ValueError, TypeError):
        return None

    critics = card.get("criticsScore", {})
    audience = card.get("audienceScore", {})

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    consensus = None
    cm = re.search(r'id="critics-consensus"[^>]*>.*?<p>(.*?)</p>', html, re.S)
    if cm:
        consensus = re.sub(r"<[^>]+>", "", cm.group(1)).strip()

    return {
        "critics": _int(critics.get("score")),
        "critics_count": _int(critics.get("reviewCount")),
        "audience": _int(audience.get("score")),
        "consensus": consensus,
        "url": f"https://www.rottentomatoes.com/m/{rt_id}",
    }


# ---------- Wikipedia synopsis ----------

def _wikipedia_summary(title):
    r = _polite_get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
    )
    if r is None or r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    extract = data.get("extract")
    return extract.strip() if extract else None


# ---------- main entry ----------

def _blank_film_fields(film):
    film.setdefault("title_ar", None)
    film.setdefault("year", None)
    film.setdefault("genres", {"ar": [], "en": []})
    film.setdefault("director", None)
    film.setdefault("cast", [])
    film.setdefault("synopsis_en", None)
    film.setdefault("wikidata", {"qid": None})
    film.setdefault("imdb", {"id": None})
    film.setdefault("imdb_score", None)
    film.setdefault("rt", None)
    film.setdefault("poster", film.get("poster"))


def enrich(data: dict, cache_path: str = "data/films_cache.json", offline: bool = False) -> dict:
    films = data.get("films", {})
    cache = _load_cache(cache_path)
    dirty = False

    for fid, film in films.items():
        _blank_film_fields(film)
        # search_title is an optional override for the Wikidata/Wikipedia query only — the
        # displayed film["title"] never changes. Useful when the UAE listing's title is
        # ambiguous (e.g. "Insidious" for a franchise with six films, "The Odyssey" which
        # collides with several older works of the same name).
        title = film.get("search_title") or film.get("title") or fid
        entry = cache.get(fid, {})
        ids = entry.get("ids")

        if ids is None and not offline:
            try:
                found = _wikidata_ids(title)
            except Exception:
                found = {}
            ids = found or {}
            entry["ids"] = ids
            dirty = True

            if not offline:
                try:
                    syn = _wikipedia_summary(title)
                except Exception:
                    syn = None
                if syn:
                    entry["synopsis_en"] = syn
                    dirty = True

        ids = ids or {}

        if ids.get("title_ar"):
            film["title_ar"] = ids["title_ar"]
        if ids.get("year"):
            film["year"] = ids["year"]
        if ids.get("runtime") and not film.get("runtime"):
            film["runtime"] = ids["runtime"]
        if ids.get("genres"):
            film["genres"] = ids["genres"]
        if ids.get("director"):
            film["director"] = ids["director"]
        if ids.get("cast"):
            film["cast"] = ids["cast"]
        film["wikidata"] = {"qid": ids.get("qid")}
        film["imdb"] = {"id": ids.get("imdb_id")}
        film["imdb_score"] = None  # no OMDb key — filled later by hand
        if entry.get("synopsis_en"):
            film["synopsis_en"] = entry["synopsis_en"]

        rt_id = ids.get("rt_id")
        ratings = entry.get("ratings")
        ratings_at = entry.get("ratings_at")
        need_ratings = rt_id and not offline and (ratings is None or not _fresh(ratings_at))
        if need_ratings:
            try:
                fresh_ratings = _rt_ratings(rt_id)
            except Exception:
                fresh_ratings = None
            if fresh_ratings:
                ratings = fresh_ratings
                ratings_at = datetime.now(timezone.utc).isoformat()
                entry["ratings"] = ratings
                entry["ratings_at"] = ratings_at
                dirty = True

        film["rt"] = ratings

        cache[fid] = entry

    if dirty and not offline:
        _save_cache(cache_path, cache)

    return data
