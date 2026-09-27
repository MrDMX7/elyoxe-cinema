"""Novo Cinemas UAE reader.

Site: https://uae.novocinemas.com (Next.js app; data comes from a JSON API at
https://uae-api.novocinemas.com, discovered by patching window.fetch/XMLHttpRequest
in the built-in browser pane while clicking a date tab on a movie page — see
docs/probe/novo.md for the full trace).

fetch(days=2) returns {"cinemas": [Cinema], "shows": [Show]} for today + the next
(days - 1) days (Asia/Dubai), across all six live Novo Cinemas UAE sites.

Prices (live, no seat hold): GET /api/booking/seat-layout/cinemas/{cinemaId}/sessions/{sessionId}
is the call the seat-selection page makes on load, before any seat is touched. Each seat area carries
its name and `priceInCents` — the exact figure the page prints in the area header ("COOL (AED 36.75)").
No login, no guest form, no seat selection. One sample per cinema x hall per run; a failure there
leaves that hall's `prices` None and never fails the chain.
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from readers.common import (CACHE_MISS, CITIES, HALLS, Polite, arabic_title, cache_get, cache_set,
                             city_of, keep_layout, lang_key, slug, subs_keys, youtube_id)

API = "https://uae-api.novocinemas.com/api/home"
BOOKING_API = "https://uae-api.novocinemas.com/api/booking"
SITE = "https://uae.novocinemas.com"
DUBAI = ZoneInfo("Asia/Dubai")

# The API returns cinema.address == "" for every site (verified live 2026-09-25) and
# city_of() can't place most of them from the mall name alone, so we pin them.
_CITY_OVERRIDE = {
    "Sahara Centre": "sharjah",
    "Mega Mall": "sharjah",
    "Manar Mall": "ras-al-khaimah",
    "BAS Mall - Baniyas": "abu-dhabi",
    "Buhairah Centre": "sharjah",
    "Dragon Mart": "dubai",
}

# Novo's session `experience` is mostly the projection format ("2D"/"3D"), which says nothing
# about the hall, so plain formats map to Standard. Named hall products map by keyword; GOLD and
# MAX are VOX brands and are never assigned here (ruling 2026-09-26). Anything unrecognised is
# OTHER with the raw label kept — never silently Standard.
_FORMATS = {"2d", "3d", "2d atmos", "3d atmos", "4k", "atmos", "dolby atmos", "hfr"}
_HALL_WORDS = [
    ("IMAX", ["imax"]),
    ("4DX", ["4dx"]),
    ("SCREENX", ["screenx", "screen x"]),
    ("VIP", ["vip", "platinum", "lux", "sky", "7 star", "7star", "recliner"]),
    ("SUITES", ["suite"]),
    ("KIDS", ["kid"]),
    ("THEATRE", ["theatre", "theater", "private"]),
]
_LANGS = {"english", "arabic", "hindi", "malayalam", "tamil", "telugu", "kannada", "urdu", "bengali",
          "punjabi", "marathi", "french", "spanish", "korean", "japanese", "chinese", "mandarin",
          "turkish", "tagalog", "filipino", "russian", "persian", "farsi", "german", "italian"}


def _hall_for(experience_name: str) -> str:
    e = (experience_name or "").strip().lower()
    if not e or e in _FORMATS:
        return "Standard"
    for hall, words in _HALL_WORDS:
        if any(w in e for w in words):
            if hall not in HALLS:
                raise ValueError(f"novo: hall {hall!r} not in HALLS")
            return hall
    return "OTHER"


def _time_24h(show_time: str) -> str | None:
    try:
        return datetime.strptime(show_time.strip(), "%I:%M %p").strftime("%H:%M")
    except (ValueError, AttributeError):
        return None


def _book_url(movie_id, title: str) -> str:
    part = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").upper() or "MOVIE"
    return f"{SITE}/movies/{movie_id}/{part}"


def _film_lang(movie: dict) -> str | None:
    lang = movie.get("language")
    if isinstance(lang, dict) and lang.get("lang_name"):
        return lang["lang_name"]
    m = re.search(r"\(([^)]+)\)\s*$", movie.get("movie_title") or "")
    # only a real language name counts: "(Live-Action)" is not a language
    return m.group(1) if m and m.group(1).strip().lower() in _LANGS else None


def movie_extras(movie: dict) -> dict:
    """Poster (movie_image_url, portrait — movie_banner_url is the landscape banner), trailer,
    genres, and the language/subtitles the movie record (or its title's "(Tamil)") states."""
    out: dict = {}
    if (movie.get("movie_image_url") or "").startswith("http"):
        out["film_poster"] = movie["movie_image_url"]
    yt = youtube_id(movie.get("movie_trailer_link"))
    if yt:
        out["film_trailer"] = yt
    genres = [g.get("genre_name") for g in movie.get("movie_genre") or [] if g.get("genre_name")]
    if genres:
        out["film_genres"] = genres
    lang = lang_key(_film_lang(movie))
    if lang:
        out["lang"] = lang
    sub = movie.get("subtitle_language")
    subs = subs_keys(sub.get("lang_name") if isinstance(sub, dict) else sub)
    if subs:
        out["subs"] = subs
    return out


def _sample_prices(s: Polite, cinema_num, session_id, on_layout=None) -> list[dict] | None:
    """Seat-area prices for one session, from the seat-selection page's load call. None on failure."""
    try:
        r = s.get(f"{BOOKING_API}/seat-layout/cinemas/{cinema_num}/sessions/{session_id}",
                  params={"country_id": 2, "channel": "web"})
        if r.status_code != 200:
            return None
        body = r.json()
        if not body.get("success"):
            return None
        if on_layout:
            on_layout(body)
        out: dict[str, float] = {}
        for a in (body.get("data") or {}).get("areas") or []:
            name, cents = (a.get("name") or "").strip(), a.get("priceInCents") or 0
            if name and cents > 0 and name not in out:
                out[name] = round(cents / 100, 2)
        return [{"seat": k, "aed": v} for k, v in out.items()] or None
    except Exception:
        return None


def fetch(days: int = 2, prices: bool = True, cache: dict | None = None) -> dict:
    s = Polite(gap=1.0)

    r = s.get(f"{API}/cinemas", params={"country_id": 2, "channel": "web"})
    r.raise_for_status()
    cinemas_raw = r.json()["data"]

    cinemas = []
    cinema_id_by_name = {}
    for c in cinemas_raw:
        name = c["name"]
        cid = f"novo-{slug(name)}"
        cinema_id_by_name[name] = cid
        city = _CITY_OVERRIDE.get(name) or city_of(name, c.get("address") or "")
        if city not in CITIES:
            raise ValueError(f"novo cinema {name!r} has no known city")
        lat = float(c["lat"]) if c.get("lat") not in (None, "") else None
        lng = float(c["long"]) if c.get("long") not in (None, "") else None
        cinemas.append({
            "id": cid,
            "chain": "novo",
            "name": f"Novo Cinemas {name}",
            "name_ar": (f"نوفو سينما {c['name_ar']}" if c.get("name_ar") else None),
            "city": city,
            "mall": name,
            "address": c.get("address") or f"{name}, UAE",
            "maps": (f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
                     if lat is not None and lng is not None else None),
            "lat": lat,
            "lng": lng,
        })

    r = s.get(f"{API}/movies", params={"country_id": 2, "channel": "web"})
    r.raise_for_status()
    movies = r.json()["data"]["movies"]

    now = datetime.now(DUBAI)
    dates = [(now.date() + timedelta(days=i)).isoformat() for i in range(max(days, 1))]
    window = set(dates)
    # Novo files after-midnight shows under the previous business day, so today's 00:xx shows
    # live in yesterday's list: query it too and keep only what lands inside the window.
    query_dates = [(now.date() - timedelta(days=1)).isoformat()] + dates

    shows = []
    calls = failed = 0
    price_cache: dict[tuple[str, str, str], list[dict] | None] = {}
    price_tries: dict[tuple[str, str], int] = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    for movie in movies:
        mid = movie["movie_id"]
        title = movie["movie_title"]
        film_lang = _film_lang(movie)
        rating = movie.get("movie_rating") or None
        runtime = movie.get("movie_duration") or None
        book = _book_url(mid, title)
        extras = movie_extras(movie)

        for d in query_dates:
            r = s.get(f"{API}/sessions/{mid}/date/{d}", params={
                "cinemaId": "null", "languageId": "", "timing": "", "formatId": "",
                "country_id": 2, "channel": "web", "v": 2,
            })
            calls += 1
            try:
                body = r.json()
            except ValueError:
                body = {}
            if r.status_code == 400 and "no sessions" in str(body.get("message", "")).lower():
                continue  # {"success": false, "message": "No sessions found"}: not playing that day
            if r.status_code != 200 or not body.get("success"):
                failed += 1
                continue
            day_sessions = (body.get("data") or {}).get("sessions", {}).get(d, {})
            for cinema_key, sessions in day_sessions.items():
                cinema_name = cinema_key.split("~")[0]
                cinema_id = cinema_id_by_name.get(cinema_name)
                if cinema_id is None:
                    continue  # unknown cinema key, skip rather than fabricate a Cinema
                for sess in sessions:
                    if sess.get("sessionDisabled"):
                        continue
                    t = _time_24h(sess.get("show_time", ""))
                    if t is None:
                        continue
                    hall_label = sess.get("experience") or "2D"
                    start = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=DUBAI)
                    # Novo lists after-midnight shows under the previous business day
                    # (isMidnightShow); the Show carries the calendar date of the real start.
                    if sess.get("isMidnightShow") and t < "06:00":
                        start += timedelta(days=1)
                    cal_date = start.date().isoformat()
                    if cal_date not in window:
                        continue
                    # one sample per cinema x hall x show date: weekday and weekend prices differ
                    key = (cinema_id, hall_label, cal_date)
                    if key not in price_cache:
                        hit = cache_get(cache, key)
                        if hit is not CACHE_MISS:  # already sampled today -- reuse, don't retry it
                            price_cache[key] = hit
                            price_tries[key] = 2
                            health["cached"] = health.get("cached", 0) + 1
                    if (prices and price_cache.get(key) is None and price_tries.get(key, 0) < 2
                            and start > now + timedelta(hours=1) and sess.get("session_id")):
                        price_tries[key] = price_tries.get(key, 0) + 1
                        price_cache[key] = _sample_prices(
                            s, sess.get("cinemaId"), sess["session_id"],
                            on_layout=lambda raw, c=cinema_id, h=hall_label, d=cal_date: keep_layout("novo", c, h, d, raw))
                        health["attempted"] += 1
                        cache_set(cache, key, price_cache[key])
                    shows.append({
                        "cinema": cinema_id,
                        "film_title": title,
                        "film_title_ar": arabic_title(movie.get("movie_title_ar")),
                        "film_lang": film_lang,
                        "film_rating": rating,
                        "runtime": runtime,
                        "date": cal_date,
                        "time": t,
                        "hall": _hall_for(hall_label),
                        "hall_label": hall_label,
                        "prices": key,  # resolved after the loop, once each hall is sampled
                        "book": book,
                        # the session, for seats.py's occupancy sample (stripped before publishing)
                        "_sid": f"{sess.get('cinemaId')}|{sess.get('session_id')}" if sess.get("session_id") else None,
                        **extras,
                    })

    if calls and failed * 2 > calls:
        raise RuntimeError(f"novo: {failed}/{calls} session calls failed — API blocked or changed")
    if not shows:
        raise RuntimeError("novo: zero shows in the window — sessions API returned nothing usable")
    for sh in shows:
        sh["prices"] = price_cache.get(sh["prices"])
    health["priced"] = sum(1 for v in price_cache.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} seat-layout samples priced"
    return {"cinemas": cinemas, "shows": shows, "price_health": health}


if __name__ == "__main__":
    import json
    import sys

    out = fetch(days=2)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
