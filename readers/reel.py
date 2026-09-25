"""Reel Cinemas (Emaar) reader.

Reel's UAE web app (reelcinemas.com) sits behind Cloudflare bot management and blocks plain
`requests` traffic. But its own frontend loads cinema/film/session/experience data straight
from a public, unauthenticated Vista Cinema data feed hosted on Google Cloud Storage — no
Cloudflare, no login, no API key. See docs/probe/reel.md for how that endpoint was found.

Endpoints (all GET, no auth, no rate limit observed — politeness gap still applied):
    https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Cinemas.json
    https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Films.json
    https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Sessions.json
    https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Experience.json

Prices: Vista's public feed never carries a real price (`MinimumTicketPriceInCents` is always
null on this feed). The only place Reel exposes AED prices is the seat-selection/GetSeatLayout
API, which requires an active booking session (a seat hold) to call. Per the binding pricing
rule, that endpoint is never called — every show's `prices` is `None`.
"""
import re
from datetime import datetime, timedelta

from readers.common import CITIES, HALLS, Polite, city_of, slug

BASE = "https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json"
CHAIN = "reel"

# Reel's Cinemas.json lists every cinema the group has ever operated across the region
# (including Bahrain/KSA and UAE locations that were probed live on 2026-09-25 and came back
# with zero sessions in the feed — Jebel Ali Recreation Club, The Pointe, Rove Downtown,
# Al Ghurair Centre, the Drive-In). Only UAE cinemas that actually have sessions right now are
# published as Cinema records; a mall with no live sessions is not a working cinema today, and
# inventing an address/city for a closed screen would violate the "no invented data" rule.
# The three that are live: Dubai Mall (0001), Dubai Marina Mall (0002), The Springs Souk (0006).
_CINEMA_ADDR_HINTS = {
    "0001": "The Dubai Mall, Downtown Dubai, Dubai, UAE",
    "0002": "Dubai Marina Mall, Dubai Marina, Dubai, UAE",
    "0006": "The Springs Souk, Dubai, UAE",
}

# Reel "Experience" codes (from Experience.json) -> our hall enum. A session's
# SessionAttributesNames carries the upper-cased code (e.g. "PLATINUM", "SCREENX", "DOLBY").
_EXPERIENCE_HALL = {
    "STANDARD": "Standard",
    "PLATINUM": "SUITES",      # Reel Platinum Suites
    "PREMIUM": "GOLD",          # Reel Premium (recliner comfort tier)
    "DOLBY": "VIP",              # Dolby Cinema (premium immersive screen)
    "SCREENX": "SCREENX",
    "IMAX": "IMAX",
    "REELJUNIOR": "KIDS",
}


def _hall_of(session: dict) -> tuple[str, str]:
    """Return (hall, hall_label) for a Vista session record."""
    attrs = [a.upper() for a in (session.get("SessionAttributesNames") or [])]
    screen_name = (session.get("ScreenName") or "").strip()
    for attr in attrs:
        if attr in _EXPERIENCE_HALL:
            return _EXPERIENCE_HALL[attr], screen_name or attr.title()
    # fall back to guessing from the screen name itself
    up = screen_name.upper()
    for needle, hall in (("IMAX", "IMAX"), ("SCREENX", "SCREENX"), ("PLATINUM", "SUITES"),
                          ("DOLBY", "VIP"), ("PREMIUM", "GOLD"), ("JUNIOR", "KIDS"),
                          ("4DX", "4DX"), ("MX4D", "4DX")):
        if needle in up:
            return hall, screen_name or needle.title()
    return "OTHER", screen_name or "Standard"


def _slugify(title: str) -> str:
    """Mirror Reel's own frontend slug function (i3 in the bundle)."""
    s = title.lower().replace("&", "-and-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


def fetch(days: int = 2) -> dict:
    http = Polite(gap=1.0)

    cinemas_raw = http.get(f"{BASE}/Cinemas.json").json()["value"]
    films_raw = http.get(f"{BASE}/Films.json").json()["value"]
    sessions_raw = http.get(f"{BASE}/Sessions.json").json()["value"]

    films_by_id = {f["ID"]: f for f in films_raw}

    today = datetime.now().date()
    target_dates = {(today + timedelta(days=d)).isoformat() for d in range(days)}

    live_cinema_ids = {c["ID"] for c in cinemas_raw
                        if c.get("CinemaNationalId") == "UAE" and c["ID"] in _CINEMA_ADDR_HINTS}

    cinemas = []
    for c in cinemas_raw:
        cid = c["ID"]
        if cid not in live_cinema_ids:
            continue
        addr = _CINEMA_ADDR_HINTS[cid]
        name = c["Name"]
        cinemas.append({
            "id": f"{CHAIN}-{slug(name)}",
            "chain": CHAIN,
            "name": f"Reel Cinemas {name}",
            "name_ar": _clean(c.get("NameAlt")),
            "city": city_of(name, addr) or "dubai",
            "mall": name,
            "address": addr,
            "maps": None,
            "lat": c.get("Latitude"),
            "lng": c.get("Longitude"),
        })

    cinema_id_of = {c["ID"]: f"{CHAIN}-{slug(c['Name'])}" for c in cinemas_raw if c["ID"] in live_cinema_ids}

    shows = []
    for s in sessions_raw:
        cid = s.get("CinemaId")
        if cid not in cinema_id_of:
            continue
        showtime = s.get("Showtime") or ""
        if "T" not in showtime:
            continue
        date_part, time_part = showtime.split("T", 1)
        if date_part not in target_dates:
            continue
        film = films_by_id.get(s.get("ScheduledFilmId"))
        if not film:
            continue
        hall, hall_label = _hall_of(s)
        if hall not in HALLS:
            hall = "OTHER"
        film_id = film["ID"]
        book = f"https://www.reelcinemas.com/en-ae/movie-details/{film_id}/{_slugify(film['Title'])}"
        shows.append({
            "cinema": cinema_id_of[cid],
            "film_title": _clean(film.get("Title")) or "",
            "film_lang": _clean(film.get("Language")),
            "film_rating": _clean(film.get("Rating")),
            "runtime": film.get("RunTime"),
            "date": date_part,
            "time": time_part[:5],
            "hall": hall,
            "hall_label": hall_label,
            "prices": None,
            "book": book,
        })

    return {"cinemas": cinemas, "shows": shows}


if __name__ == "__main__":
    import json
    import sys

    data = fetch()
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
