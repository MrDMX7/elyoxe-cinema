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

Cache (data/films_cache.json, gitignored): per-fid {"ids": {...}, "ids_status":
"found"|"not_found"|"error", "ids_checked_at": ISO, "ratings": {...}, "ratings_at": ISO}.
"found" is permanent (never re-queried). "not_found" (a genuine, successfully-queried empty
result) is retried after NOT_FOUND_TTL — a title with no Wikidata item today may get one once
the film is a few days old. "error" (a network/HTTP/parse failure — we couldn't tell either
way) is retried much sooner, after ERROR_TTL, specifically so a transient outage during a
film's first-ever lookup doesn't get treated as "confirmed absent" and left that way forever
(round-3 controller review, 2026-09-26). Ratings (the RT numbers) expire after RATINGS_TTL
regardless of ids status. offline=True never touches the network — whatever is in the cache
(or nothing) is used.

Wikidata matching only ever accepts a film-shaped hit whose own publication year is in
`accepted_years` — the current/previous calendar year by default, or a single explicit
`{film["year_hint"]}` when a reader/caller supplies one. There is no fallback to "the best
non-matching-year hit anyway": a title collision with an older or unrelated work (e.g. "The
Odyssey" 2016 vs the 2026 Nolan film, "Insidious" the franchise vs one specific 2026 entry)
must return no match rather than silently attach the wrong film's data — a wrong match is
worse than none (round-3 controller review; the per-title `search_title` override in
seed_verdicts.py is still how a title that doesn't surface its correct match in the top
search hits at all gets there, orthogonal to this year filter). The Rotten Tomatoes fetch has
the same guard: a page's own `releaseYear` (read out of its `where-to-watch-json` block) must
match the Wikidata-recorded year for that same qid, or the rating is dropped rather than
attached to the wrong film.

Re-releases (fix wave, 2026-09-26): a classic back in cinemas (The Dark Knight, Interstellar)
has no current-year Wikidata film, so the year filter above finds nothing. Only then, and only
under three guards, an older film is accepted: its English label equals the cleaned title
exactly (case/punctuation-insensitive), it has >= 20 sitelinks (a well-known film, not a
same-named obscurity), and its runtime, when both are known, is within 5 minutes of the
listing's (plus: its original language, when Wikidata and the listing both give one, agrees).
Such a film carries film["rerelease"] = True, and its RT page is checked against its own year.

Synopsis: only for a film whose Wikidata match was accepted, and only from that item's own
English Wikipedia sitelink — never a title search (that is how "Dhoomakethu" 2026 got the
plot of a 1968 Kannada film). title_ar: the item's real Arabic label (never its English label
as a fallback), else the Arabic title a chain publishes (Reel's TitleAlt, Novo's
movie_title_ar), else none. Never machine-translated.
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
NOT_FOUND_TTL = timedelta(days=3)
ERROR_TTL = timedelta(hours=6)
FILM_QIDS = {"Q11424", "Q24862", "Q24869"}  # film, short film, television film
LOOKUP_VERSION = 2          # 2: re-release fallback — a "not_found" from an older version is retried once
RERELEASE_MIN_SITELINKS = 20
RERELEASE_RUNTIME_TOLERANCE = 5
# listing language -> Wikidata QID of that language (P364, original language of the film)
LANG_QIDS = {"English": "Q1860", "Arabic": "Q13955", "Hindi": "Q1568", "Malayalam": "Q36236",
             "Tamil": "Q5885", "Telugu": "Q8097", "Korean": "Q9176", "Japanese": "Q5287",
             "French": "Q150", "Tagalog": "Q34057", "Punjabi": "Q58635"}
_ARABIC = re.compile(r"[\u0600-\u06ff]")

_last_call = [0.0]


class LookupFailed(Exception):
    """A Wikidata call failed at the network/HTTP/JSON-parse level — distinct from a
    legitimate empty result (HTTP 200, zero hits), so the caller can avoid caching a
    transient failure as a permanent "not found" for this film."""


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


def _fresh(iso_ts, ttl):
    if not iso_ts:
        return False
    try:
        t = datetime.fromisoformat(iso_ts)
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - t < ttl


# ---------- Wikidata ----------
#
# _wikidata_search/_wikidata_entities raise LookupFailed on a network/HTTP/parse failure —
# they do NOT swallow it into an empty list/dict the way they used to, because an empty dict
# from "the request failed" and an empty dict from "Wikidata legitimately has zero hits" used
# to be indistinguishable to the caller, and the caller (enrich()) cached both as the same
# permanent "not found". A real empty *result* (HTTP 200, `{"search": []}`) still returns []
# normally — that's not a failure, it's an answer.

def _wikidata_search(title):
    r = _polite_get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbsearchentities", "search": title, "language": "en",
                "format": "json", "type": "item", "limit": 6},
    )
    if r is None:
        raise LookupFailed("network error calling wbsearchentities")
    if r.status_code != 200:
        raise LookupFailed(f"wbsearchentities HTTP {r.status_code}")
    try:
        return r.json().get("search", [])
    except ValueError as e:
        raise LookupFailed(f"bad JSON from wbsearchentities: {e}") from e


def _wikidata_entities(ids, props="labels|claims"):
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    r = _polite_get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbgetentities", "ids": "|".join(ids), "format": "json",
                "languages": "en|ar", "props": props},
    )
    if r is None:
        raise LookupFailed("network error calling wbgetentities")
    if r.status_code != 200:
        raise LookupFailed(f"wbgetentities HTTP {r.status_code}")
    try:
        return r.json().get("entities", {})
    except ValueError as e:
        raise LookupFailed(f"bad JSON from wbgetentities: {e}") from e


def _label(entities, qid, lang):
    labels = entities.get(qid, {}).get("labels", {})
    if lang in labels:
        return labels[lang]["value"]
    if "en" in labels:
        return labels["en"]["value"]
    return None


def _arabic_label(entities, qid):
    """The item's own Arabic label, or None — never the English label standing in for it."""
    v = (entities.get(qid, {}).get("labels", {}).get("ar") or {}).get("value")
    return v if v and _ARABIC.search(v) else None


def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


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


def _best_film_in_hits(hits, accepted_years):
    """Given wbsearchentities hits, returns the qid of the first film-shaped hit whose own
    publication year is in `accepted_years`, or None.

    No "best guess" fallback: a film-shaped hit whose year is wrong (or unknown) is not
    returned even if it's the only film-shaped hit. Round-3 controller review — the previous
    version returned the best film-shaped hit regardless of year when nothing recent was
    found, which is how "The Odyssey" silently resolved to a 2016 film. Wrong match is worse
    than no match: the caller treats None as "not found" and moves on, rather than attaching
    another film's title_ar/genres/cast/runtime/ids to this listing.
    """
    if not hits:
        return None
    entities = _wikidata_entities([h["id"] for h in hits])
    for h in hits:
        qid = h["id"]
        ent = entities.get(qid)
        if not ent or not _looks_like_a_film(h, ent):
            continue
        if _claim_year(ent) in accepted_years:
            return qid
    return None


def _find_film_qid(title, accepted_years):
    """Wikidata match: instance-of film, publication year in `accepted_years`, or None.

    A plain title search often loses to a franchise/game entity of the same name (e.g.
    "Resident Evil" the video-game franchise outranks the 2026 film), or surfaces an older
    film with the same title (e.g. "The Odyssey" 2016) ahead of or instead of the current
    one. So: try the plain title first; if it doesn't land on a hit whose year is in
    `accepted_years`, retry with a "(2026 film)"/"(2025 film)" disambiguator, which is how
    Wikidata titles most just-released films. If neither lands on an accepted year, return
    None — never the best non-matching hit (see _best_film_in_hits).
    """
    hits = _wikidata_search(title)
    qid = _best_film_in_hits(hits, accepted_years)
    if qid:
        return qid
    for suffix in (" (2026 film)", " (2025 film)"):
        more_hits = _wikidata_search(title + suffix)
        more_qid = _best_film_in_hits(more_hits, accepted_years)
        if more_qid:
            return more_qid
    return None


def _runtime_of(ent):
    for v in _claim_values(ent, "P2047"):
        try:
            return round(float(str(v["amount"]).lstrip("+")))
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _find_rerelease_qid(title, runtime=None, lang=None):
    """An older film for a title with no current-year match — see the module docstring's
    "Re-releases": exact English label, >= RERELEASE_MIN_SITELINKS sitelinks, runtime within
    RERELEASE_RUNTIME_TOLERANCE when both are known, original language agreeing when both are
    known. Returns the qid or None. May raise LookupFailed."""
    want = _norm_title(title)
    if not want:
        return None
    hits = _wikidata_search(title)
    if not hits:
        return None
    entities = _wikidata_entities([h["id"] for h in hits], props="labels|claims|sitelinks")
    for h in hits:
        qid = h["id"]
        ent = entities.get(qid)
        if not ent or not _looks_like_a_film(h, ent):
            continue
        label = ((ent.get("labels") or {}).get("en") or {}).get("value")
        if _norm_title(label) != want:
            continue
        if len(ent.get("sitelinks") or {}) < RERELEASE_MIN_SITELINKS:
            continue
        rt = _runtime_of(ent)
        if runtime and rt and abs(int(runtime) - rt) > RERELEASE_RUNTIME_TOLERANCE:
            continue
        lang_qid = LANG_QIDS.get(lang or "")
        langs = {v.get("id") for v in _claim_values(ent, "P364")}
        if lang_qid and langs and lang_qid not in langs:
            continue
        return qid
    return None


def _rerelease_ids(title, runtime=None, lang=None):
    """_wikidata_ids() for the re-release fallback: {} or the same dict with rerelease=True."""
    qid = _find_rerelease_qid(title, runtime, lang)
    if not qid:
        return {}
    out = _ids_for_qid(qid)
    if out:
        out["rerelease"] = True
    return out


def _wikidata_ids(title, accepted_years):
    """Returns a permanent-cacheable dict of ids/labels for a title, or {} if unmatched.

    May raise LookupFailed if a Wikidata call fails at the network/HTTP/parse level — the
    caller (enrich()) must not treat that the same as a confirmed empty match.
    """
    qid = _find_film_qid(title, accepted_years)
    if not qid:
        return {}
    return _ids_for_qid(qid)


def _ids_for_qid(qid):
    entities = _wikidata_entities([qid], props="labels|claims|sitelinks")
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

    enwiki = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")
    return {
        "qid": qid,
        "enwiki": enwiki,
        "title_ar": _arabic_label(entities, qid),
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

def _rt_release_year(html):
    """Pulls the release year RT itself prints for this page, from the `where-to-watch-json`
    block's `"releaseYear":"2026"` field. Not present under every id, so a miss returns None
    (treated as "can't verify" by the caller, not as a mismatch)."""
    m = re.search(r'"releaseYear"\s*:\s*"(\d{4})"', html)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _rt_ratings(rt_id, expected_year=None):
    """Scrape the RT page for tomatometer/popcornmeter numbers and the consensus line.

    If `expected_year` is given and the page's own release year is readable and differs,
    the whole result is dropped (None) rather than attached to the wrong film — this is the
    Wikidata-recorded rt_id turning out to point at the wrong RT entry (rare, but the exact
    shape of bug that put a 2016 "The Odyssey" number on the 2026 Nolan film before the
    Wikidata-side year guard existed). A page where the year can't be read at all is
    accepted leniently — we already trust the qid it came from.
    """
    r = _polite_get(f"https://www.rottentomatoes.com/m/{rt_id}")
    if r is None or r.status_code != 200:
        return None
    html = r.text
    if expected_year is not None:
        page_year = _rt_release_year(html)
        if page_year is not None and page_year != expected_year:
            return None
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
    """The REST summary of one exact English Wikipedia page (the matched item's sitelink)."""
    r = _polite_get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title.replace(' ', '_'), safe='')}"
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
    current_year = datetime.now(timezone.utc).year

    for fid, film in films.items():
        _blank_film_fields(film)
        # search_title is an optional override for the Wikidata/Wikipedia query only — the
        # displayed film["title"] never changes. Useful when the UAE listing's title is
        # ambiguous (e.g. "Insidious" for a franchise with six films, "The Odyssey" which
        # collides with several older works of the same name).
        title = film.get("search_title") or film.get("title") or fid
        # A reader/caller can pin the exact expected year (e.g. from its own listing data);
        # otherwise accept the current or previous calendar year, which covers both a film
        # that opened late last year and is still in UAE cinemas, and one opening this year.
        year_hint = film.get("year_hint")
        accepted_years = {year_hint} if year_hint else {current_year, current_year - 1}

        entry = cache.get(fid, {})
        ids = entry.get("ids")
        # Backward-compatible status inference for a cache written before ids_status existed:
        # a truthy "ids" is treated as a confirmed "found" (unchanged behavior); a falsy one
        # with no status is unknown-provenance (could be an old permanent "not found" or a
        # pre-upgrade write) and is simply re-attempted once, which is always safe.
        ids_status = entry.get("ids_status") or ("found" if ids else None)
        ids_checked_at = entry.get("ids_checked_at")

        if ids_status == "found":
            should_attempt = False  # a confirmed match is permanent, never re-queried
        elif ids_status == "not_found":
            # a "not found" from before the re-release fallback existed is retried once now
            should_attempt = (entry.get("lookup_v", 1) < LOOKUP_VERSION
                              or not _fresh(ids_checked_at, NOT_FOUND_TTL))
        elif ids_status == "error":
            should_attempt = not _fresh(ids_checked_at, ERROR_TTL)
        else:  # never attempted
            should_attempt = True

        if should_attempt and not offline:
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                found = _wikidata_ids(title, accepted_years)
                if not found and not year_hint:
                    found = _rerelease_ids(title, film.get("runtime"), film.get("lang"))
            except LookupFailed:
                # Transient failure — do NOT overwrite a previously-found `ids` (there isn't
                # one, by construction of should_attempt, except in the "not_found"-retry
                # case where ids is already {} anyway) and do NOT mark this "not_found" — a
                # network blip must not permanently poison a film that was never actually
                # confirmed absent from Wikidata. Retried again after ERROR_TTL.
                entry["ids_status"] = "error"
                entry["ids_checked_at"] = now_iso
                dirty = True
                found = ids or {}
            except Exception:
                # An unexpected bug in our own parsing is not proof the film has no Wikidata
                # entry either — same conservative "error" treatment, not "not_found".
                entry["ids_status"] = "error"
                entry["ids_checked_at"] = now_iso
                dirty = True
                found = ids or {}
            else:
                entry["ids"] = found
                entry["ids_status"] = "found" if found else "not_found"
                entry["ids_checked_at"] = now_iso
                entry["lookup_v"] = LOOKUP_VERSION
                dirty = True
            ids = found

            # the plot only of the page Wikidata itself links to this film — never a title search
            if found and found.get("enwiki"):
                try:
                    syn = _wikipedia_summary(found["enwiki"])
                except Exception:
                    syn = None
                if syn:
                    entry["synopsis_en"] = syn
                    dirty = True

        ids = ids or {}
        if not ids.get("qid") and entry.pop("synopsis_en", None) is not None:
            dirty = True  # a synopsis without an accepted match is someone else's plot

        title_ar = ids.get("title_ar")
        if title_ar and not _ARABIC.search(title_ar):
            title_ar = None  # an older cache entry holding the English label as "title_ar"
        title_ar = title_ar or film.get("title_ar_chain")
        if title_ar:
            film["title_ar"] = title_ar
        film["rerelease"] = bool(ids.get("rerelease"))
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
        if entry.get("synopsis_en") and ids.get("qid"):
            film["synopsis_en"] = entry["synopsis_en"]

        rt_id = ids.get("rt_id")
        ratings = entry.get("ratings")
        ratings_at = entry.get("ratings_at")
        need_ratings = rt_id and not offline and (ratings is None or not _fresh(ratings_at, RATINGS_TTL))
        if need_ratings:
            # Guard against a stale/wrong Wikidata rt_id: the RT page's own release year must
            # match the year Wikidata recorded for this same qid, or the rating is dropped.
            try:
                fresh_ratings = _rt_ratings(rt_id, expected_year=ids.get("year"))
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
