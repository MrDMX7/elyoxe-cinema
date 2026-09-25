"""Novo Cinemas UAE reader.

Site: https://uae.novocinemas.com (Next.js app; data comes from a JSON API at
https://uae-api.novocinemas.com, discovered by patching window.fetch/XMLHttpRequest
in the built-in browser pane while clicking a date tab on a movie page — see
docs/probe/novo.md for the full trace).

fetch(days=2) returns {"cinemas": [Cinema], "shows": [Show]} for today + the next
(days - 1) days, across all six live Novo Cinemas UAE sites.
"""
import re
from datetime import date, datetime, timedelta

from readers.common import CITIES, HALLS, Polite, city_of, slug

API = "https://uae-api.novocinemas.com/api/home"
SITE = "https://uae.novocinemas.com"

# The API returns cinema.address == "" for every site (verified live 2026-09-25) and
# city_of() can't place two of them from the mall name alone, so we pin those two.
_CITY_OVERRIDE = {
    "Sahara Centre": "sharjah",
    "Mega Mall": "sharjah",
    "Manar Mall": "ras-al-khaimah",
    "BAS Mall - Baniyas": "abu-dhabi",
    "Buhairah Centre": "sharjah",
    "Dragon Mart": "dubai",
}

_HALL_WORDS = [
    ("IMAX", ["imax"]),
    ("4DX", ["4dx"]),
    ("SCREENX", ["screenx", "screen x"]),
    ("GOLD", ["gold"]),
    ("VIP", ["vip", "platinum", "lux", "sky", "7 star", "7star"]),
    ("SUITES", ["suite"]),
    ("KIDS", ["kid"]),
    ("THEATRE", ["theatre", "theater", "private"]),
    ("MAX", ["max"]),
]


def _hall_for(experience_name: str) -> str:
    e = (experience_name or "").lower()
    for hall, words in _HALL_WORDS:
        if any(w in e for w in words):
            assert hall in HALLS
            return hall
    return "Standard"


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
    return m.group(1) if m else None


def fetch(days: int = 2) -> dict:
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
        assert city in CITIES, f"novo cinema {name!r} has no known city"
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

    dates = [(date.today() + timedelta(days=i)).isoformat() for i in range(max(days, 1))]

    shows = []
    for movie in movies:
        mid = movie["movie_id"]
        title = movie["movie_title"]
        film_lang = _film_lang(movie)
        rating = movie.get("movie_rating") or None
        runtime = movie.get("movie_duration") or None
        book = _book_url(mid, title)

        for d in dates:
            r = s.get(f"{API}/sessions/{mid}/date/{d}", params={
                "cinemaId": "null", "languageId": "", "timing": "", "formatId": "",
                "country_id": 2, "channel": "web", "v": 2,
            })
            if r.status_code != 200:
                continue
            body = r.json()
            if not body.get("success"):
                continue  # e.g. {"message": "No sessions found"} for a movie not on that day
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
                    shows.append({
                        "cinema": cinema_id,
                        "film_title": title,
                        "film_lang": film_lang,
                        "film_rating": rating,
                        "runtime": runtime,
                        "date": d,
                        "time": t,
                        "hall": _hall_for(hall_label),
                        "hall_label": hall_label,
                        # Ticket prices are only exposed once a seat is held in the
                        # booking flow (Vista-style session lock) — never fetched.
                        # See docs/probe/novo.md.
                        "prices": None,
                        "book": book,
                    })

    return {"cinemas": cinemas, "shows": shows}


if __name__ == "__main__":
    import json
    import sys

    out = fetch(days=2)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
