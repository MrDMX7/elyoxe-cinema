"""omdb.py — IMDb rating via OMDb, only when a key is configured (UNIT r3-film). No key anywhere (env
OMDB_KEY, else AWS SSM /elyoxe/omdb/key) => fill_scores() is a no-op, every film's imdb_score stays exactly
what enrich.py already leaves it (None) — insights.py's own comment: "no OMDb key: always empty". Cached in
<data_dir>/omdb_cache.json per IMDb id so a configured key still fetches each film at most once every
OMDB_TTL, never every hourly run."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

OMDB_TTL = 30 * 24 * 3600   # 30 days: a public rating barely moves once a film has settled
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


def _fetch(imdb_id: str, key: str) -> float | None:
    try:
        r = requests.get("https://www.omdbapi.com/", params={"i": imdb_id, "apikey": key}, headers=UA, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    if data.get("Response") != "True":
        return None
    rating = data.get("imdbRating")
    try:
        return float(rating) if rating and rating != "N/A" else None
    except (TypeError, ValueError):
        return None


def fill_scores(data: dict, data_dir=None) -> dict:
    """Fills film["imdb_score"] for every film with an imdb id, only when a key is configured. Never raises;
    a per-film fetch failure just leaves that film's score as it was. Returns a small report for health.json."""
    key = _key()
    if not key:
        return {"ok": True, "skipped": "no OMDB_KEY configured"}
    cache = _load_cache(data_dir)
    now = time.time()
    fetched = 0
    for fid, film in (data.get("films") or {}).items():
        imdb_id = (film.get("imdb") or {}).get("id") if isinstance(film.get("imdb"), dict) else None
        if not imdb_id:
            continue
        entry = cache.get(imdb_id)
        if entry and (now - entry.get("at", 0)) < OMDB_TTL:
            film["imdb_score"] = entry.get("score")
            continue
        score = _fetch(imdb_id, key)
        cache[imdb_id] = {"score": score, "at": now}
        film["imdb_score"] = score
        fetched += 1
    _write_cache(data_dir, cache)
    return {"ok": True, "fetched": fetched}
