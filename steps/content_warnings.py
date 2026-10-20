"""steps/content_warnings.py — what a family should know before going, and whether to stay for the end credits
(owner 2026-10-20: «محتوى الفيلم للعائلة» + «مشاهد ما بعد النهاية»).

Source: Does the Dog Die? (doesthedogdie.com) — community yes/no ratings per topic, through its official API (free tier,
key in SSM /elyoxe/dtdd/key, account hello@elyoxe.com; its terms: attribution on the page, cache refreshed within 30
days, no bulk harvesting — we ask only about the films showing). A film is found by its IMDb id (the search returns
each item's imdbId), else by its exact title and a release year within one of ours.

Only the topics in TOPICS are kept — what matters to a family in the UAE and to anyone deciding whether to stay after the
credits. A topic counts as "yes" with at least 3 votes and twice as many yes as no, "no" the same the other way round;
anything closer is left out. The ratings describe the ORIGINAL cut: UAE cinemas show edited versions, which the page says.

film["content"] = {"flags": [topic keys rated yes], "credits": True|False|None, "votes": the film's total ratings,
"url": its page on doesthedogdie.com}. Cached in data/dtdd.json: a found film 7 days, a miss 3 days; at most FETCH_CAP
API calls a run. A failure never stops the run."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

API = "https://www.doesthedogdie.com"
FETCH_CAP = 20
FOUND_DAYS, MISS_DAYS = 7, 3
CREDITS = 346   # «there's end credits scenes?»
# topic id -> our key (pages/ask.py and app/build_app.py give each key its words)
TOPICS = {197: "sex", 279: "nudity", 182: "sexual_assault", 188: "blood", 296: "body_horror", 203: "torture",
          232: "guns", 161: "jump_scares", 207: "ghosts", 224: "possession", 369: "demons", 193: "drugs",
          225: "alcohol", 464: "smoking", 158: "child_dies", 189: "animal_dies"}


def _key():
    k = os.environ.get("DTDD_KEY")
    if k:
        return k
    try:
        import boto3
        return boto3.client("ssm", region_name="ap-south-1").get_parameter(
            Name="/elyoxe/dtdd/key", WithDecryption=True)["Parameter"]["Value"]
    except Exception:  # noqa: BLE001
        return None


def _get(path, key, params=None):
    import requests
    r = requests.get(API + path, params=params, timeout=20,
                     headers={"Accept": "application/json", "X-API-KEY": key,
                              "User-Agent": "elyoxe-cinema/1.0 (+https://cinema.elyoxe.com)"})
    r.raise_for_status()
    return r.json()


def _norm(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def _match(items, film):
    imdb = (film.get("imdb") or {}).get("id")
    if imdb:
        for it in items:
            if it.get("imdbId") == imdb:
                return it
    want, year = _norm(film.get("title")), film.get("year")
    for it in items:
        if _norm(it.get("name")) == want and year and str(it.get("releaseYear") or "")[:4].isdigit() \
                and abs(int(str(it["releaseYear"])[:4]) - int(year)) <= 1:
            return it
    return None


def verdict(stat):
    y, n = int(stat.get("yesSum") or 0), int(stat.get("noSum") or 0)
    if y >= 3 and y >= 2 * n:
        return True
    if n >= 3 and n >= 2 * y:
        return False
    return None


def summarize(media):
    stats = {s.get("TopicId"): s for s in media.get("topicItemStats") or []}
    flags = [k for tid, k in TOPICS.items() if tid in stats and verdict(stats[tid]) is True]
    credits = verdict(stats[CREDITS]) if CREDITS in stats else None
    item = media.get("item") or {}
    return {"flags": flags, "credits": credits, "votes": int(item.get("numRatings") or 0),
            "url": f"{API}/media/{item.get('id')}" if item.get("id") else None}


def run(data: dict, ctx: dict) -> dict | None:
    if ctx.get("offline"):
        return {"skipped": "offline"}
    data_dir = Path(ctx.get("data_dir") or Path(__file__).resolve().parent.parent / "data")
    cpath = data_dir / "dtdd.json"
    try:
        cache = json.loads(cpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    showing = {s.get("film") for s in data.get("shows") or []}
    films = {fid: f for fid, f in (data.get("films") or {}).items() if fid in showing and f.get("status") != "archived"}
    today = dt.date.today()
    key, calls, found, fetched = None, 0, 0, 0
    for fid, f in films.items():
        hit = cache.get(fid) or {}
        fresh_days = FOUND_DAYS if hit.get("content") else MISS_DAYS
        if hit.get("at", "") < (today - dt.timedelta(days=fresh_days)).isoformat() and calls + 2 <= FETCH_CAP:
            key = key or _key()
            if not key:
                break
            try:
                calls += 1
                item = _match((_get("/dddsearch", key, {"q": f.get("title") or ""}) or {}).get("items") or [], f)
                content = None
                if item:
                    calls += 1
                    content = summarize(_get(f"/media/{item['id']}", key))
                hit = {"at": today.isoformat(), "content": content}
                cache[fid] = hit
                fetched += 1
            except Exception as e:  # noqa: BLE001 - one film's failure never stops the others
                print(f"content_warnings: {fid}: {e}")
                continue
        if hit.get("content"):
            f["content"] = hit["content"]
            found += 1
    try:
        cpath.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return {"films": len(films), "with_content": found, "fetched": fetched, "api_calls": calls}
