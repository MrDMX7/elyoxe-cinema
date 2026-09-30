"""omdb.py — IMDb rating via OMDb, only when a key is configured (UNIT r3-film). No key anywhere (env
OMDB_KEY, else AWS SSM /elyoxe/omdb/key) => fill_scores() is a no-op, every film's imdb_score stays exactly
what enrich.py already leaves it (None) — insights.py's own comment: "no OMDb key: always empty". Cached in
<data_dir>/omdb_cache.json so a configured key still fetches each film at most once every OMDB_TTL, never
every hourly run.

Two lookups (round3-gaps, 2026-09-30: only 18 of 82 films had a score, because Wikidata gives an IMDb id to
about a third of what the chains show):
  1. by IMDb id, when enrich.py found one (Wikidata) — cached under the id itself, as before;
  2. by title + year, when there is no id or the id lookup came back without a score:
     ?t=<English title>&y=<year>&type=movie. OMDb's answer is accepted ONLY when its release year is within
     ±1 of ours AND its title matches ours once case, diacritics and punctuation are folded away
     (title_key()) — a near-miss is a miss, never a guess. Our year is the film's own (Wikidata), else the
     year a chain first listed it (released / first_seen: a film in cinemas now came out this year or last);
     a re-release with no year of its own is never looked up by title (its first-seen year says nothing about
     when it was made). Every answer — hit OR miss — is cached per film id ("t:<fid>") so a miss is not asked
     again for TITLE_MISS_TTL, and at most TITLE_CAP title requests go out in one run.
Budget: OMDb's free tier is 1000 requests a day. A cold cache costs at most 2 requests per film (y and y-1
when the year is only inferred); after that a film costs one request per OMDB_TTL (hit) or TITLE_MISS_TTL
(miss) — a few dozen a day at most."""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path

import requests

OMDB_TTL = 3 * 24 * 3600   # 3 days (round 3 QA: OMDb free tier is 1000 req/day, so caching still matters,
                           # but 30 days let a fresh rating go stale for too long)
TITLE_MISS_TTL = 7 * 24 * 3600   # a title that OMDb does not know (or knows under another year) is asked again weekly
TITLE_CAP = 200                  # title requests per run, whatever the cache says (well inside 1000/day)
YEAR_SLACK = 1                   # OMDb's year may differ from ours by one (festival vs release year)
RUNTIME_SLACK = 20               # minutes: the chains' own runtimes differ by up to ~15 (ads, cuts)
MIN_VOTES = 100                  # a title-matched rating from fewer IMDb votes is not a rating (5 votes gave "9.4")
ENTRY_V = 2                      # the title entry's shape; an older cached entry is asked again
UA = {"User-Agent": "elyoxe-cinema/1.0 (+https://cinema.elyoxe.com)"}


def _key() -> str | None:
    k = os.environ.get("OMDB_KEY")
    if k:
        return k
    try:
        import boto3

        ssm = boto3.client("ssm", region_name="ap-south-1")
        return ssm.get_parameter(Name="/elyoxe/omdb/key", WithDecryption=True)["Parameter"]["Value"]
    except Exception:
        return None


def _load_cache(data_dir) -> dict:
    p = Path(data_dir or "data") / "omdb_cache.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _write_cache(data_dir, cache: dict) -> None:
    p = Path(data_dir or "data") / "omdb_cache.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def _get(params: dict, key: str) -> dict | None:
    """One OMDb request; the JSON body, or None on any network/HTTP/JSON failure (never raises)."""
    try:
        r = requests.get("https://www.omdbapi.com/", params=dict(params, apikey=key), headers=UA, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _score(data: dict | None) -> float | None:
    if not data or data.get("Response") != "True":
        return None
    rating = data.get("imdbRating")
    try:
        return float(rating) if rating and rating != "N/A" else None
    except (TypeError, ValueError):
        return None


def _fetch(imdb_id: str, key: str) -> float | None:
    return _score(_get({"i": imdb_id}, key))


def _fetch_title(title: str, year: int, key: str) -> dict | None:
    """?t=&y=&type=movie. The raw answer reduced to {"title", "year", "imdb_id", "score"}, or None when OMDb has
    nothing (or the request failed). Matching is the caller's job (accept())."""
    data = _get({"t": title, "y": str(year), "type": "movie"}, key)
    if not data or data.get("Response") != "True":
        return None
    m = re.match(r"\d{4}", str(data.get("Year") or ""))
    rt = re.match(r"(\d+)\s*min", str(data.get("Runtime") or ""))
    try:
        votes = int(str(data.get("imdbVotes") or "").replace(",", ""))
    except ValueError:
        votes = 0
    return {"title": data.get("Title") or "", "year": int(m.group(0)) if m else None,
            "imdb_id": data.get("imdbID") or None, "score": _score(data), "votes": votes,
            "runtime": int(rt.group(1)) if rt else None,
            "langs": [x.strip() for x in str(data.get("Language") or "").split(",") if x.strip() and x.strip() != "N/A"]}


# ----------------------------------------------------------------------------------------- title matching
_AMP = re.compile(r"\s*&\s*")
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def title_key(s) -> str:
    """A title folded for comparison: NFKD with the combining marks dropped («Amélie» = «Amelie»), casefolded,
    «&» read as «and», every space and punctuation mark removed («Coyote VS Acme» = «Coyote vs. Acme»,
    «Spider-Man» = «Spider Man»)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    s = s.replace("’", "'")
    s = _AMP.sub(" and ", s)
    return _NON_ALNUM.sub("", s)


def accept(film_title: str, film_year: int, found: dict | None, lang: str | None = None, runtime=None) -> bool:
    """OMDb's answer is this film only when the folded titles are equal and the years are within YEAR_SLACK — and,
    where both sides know them, the film's language is among OMDb's and the runtimes are within RUNTIME_SLACK
    (a generic title — «Wake», «Life After You» — otherwise lands on another country's film of the same name)."""
    if not found or not found.get("year") or not film_year:
        return False
    if not (title_key(found.get("title")) == title_key(film_title) != "" and abs(int(found["year"]) - int(film_year)) <= YEAR_SLACK):
        return False
    langs = [str(x).casefold() for x in found.get("langs") or []]
    if lang and langs and str(lang).casefold() not in langs:
        return False
    try:
        if runtime and found.get("runtime") and abs(int(runtime) - int(found["runtime"])) > RUNTIME_SLACK:
            return False
    except (TypeError, ValueError):
        pass
    return True


def ref_year(film: dict) -> tuple[int | None, bool]:
    """(the year to ask OMDb for, whether it is the film's own). Its own year (Wikidata) first; else — only for a
    film that is not a re-release — the year a chain first dated it (released, then first_seen)."""
    y = film.get("year")
    try:
        if y:
            return int(y), True
    except (TypeError, ValueError):
        pass
    if film.get("rerelease"):
        return None, False
    for k in ("released", "first_seen"):
        m = re.match(r"(\d{4})-\d\d-\d\d", str(film.get(k) or ""))
        if m:
            return int(m.group(1)), False
    return None, False


def _title_lookup(film: dict, key: str) -> tuple[dict, int]:
    """(cache entry, requests spent). y = our year, and with only an inferred year also y-1 (OMDb's y is exact:
    a film released last December and still showing this autumn is filed under last year)."""
    title = str(film.get("title") or "").strip()
    year, own = ref_year(film)
    entry = {"q": [title, year], "hit": False, "score": None, "imdb_id": None, "v": ENTRY_V}
    spent = 0
    for y in ([year] if own else [year, year - 1]):
        found = _fetch_title(title, y, key)
        spent += 1
        if accept(title, year, found, film.get("lang"), film.get("runtime")):
            # a match with too few votes is still this film (its id is kept) but its number is not shown
            score = found.get("score") if (found.get("votes") or 0) >= MIN_VOTES else None
            entry.update(hit=True, score=score, imdb_id=found.get("imdb_id"), year=found.get("year"),
                         title=found.get("title"), votes=found.get("votes"))
            break
    return entry, spent


def fill_scores(data: dict, data_dir=None) -> dict:
    """Fills film["imdb_score"] for every film OMDb can vouch for, only when a key is configured. Never raises;
    a per-film fetch failure just leaves that film's score as it was. Returns a small report for health.json."""
    key = _key()
    if not key:
        return {"ok": True, "skipped": "no OMDB_KEY configured"}
    cache = _load_cache(data_dir)
    now = time.time()
    fetched = by_title = title_requests = 0
    for fid, film in (data.get("films") or {}).items():
        imdb_id = (film.get("imdb") or {}).get("id") if isinstance(film.get("imdb"), dict) else None
        if imdb_id:
            entry = cache.get(imdb_id)
            if entry and (now - entry.get("at", 0)) < OMDB_TTL:
                film["imdb_score"] = entry.get("score")
            else:
                score = _fetch(imdb_id, key)
                cache[imdb_id] = {"score": score, "at": now}
                film["imdb_score"] = score
                fetched += 1
            if film.get("imdb_score") is not None:
                continue
        # the title lookup: no id, or the id gave no score
        title = str(film.get("title") or "").strip()
        year, _own = ref_year(film)
        if not title or not year:
            continue
        ck = "t:" + fid
        entry = cache.get(ck)
        fresh = (entry and entry.get("q") == [title, year] and entry.get("v") == ENTRY_V
                 and (now - entry.get("at", 0)) < (OMDB_TTL if entry.get("hit") else TITLE_MISS_TTL))
        if not fresh:
            if title_requests >= TITLE_CAP:
                continue
            entry, spent = _title_lookup(film, key)
            entry["at"] = now
            cache[ck] = entry
            title_requests += spent
        if entry.get("hit") and entry.get("score") is not None:
            film["imdb_score"] = entry["score"]
            if not imdb_id and entry.get("imdb_id"):
                film["imdb"] = {"id": entry["imdb_id"], "src": "omdb-title"}
            by_title += 1
    _write_cache(data_dir, cache)
    return {"ok": True, "fetched": fetched, "by_title": by_title, "title_requests": title_requests}
