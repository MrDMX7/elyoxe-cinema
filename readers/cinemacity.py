"""Reader for Cinema City UAE (cinemacity.ae) — six sites across Abu Dhabi, Dubai and Sharjah.

Site is a Gatsby front-end backed by a JSON API at
  https://www.cinemacity.ae/api/gatsby-source-boxofficeapi/...
(the "boxofficeapi" name is a Gatsby data-source label, not a third-party service —
 it is Cinema City's own public API and needs no auth, cookies or referrer).

See docs/probe/cinemacity.md for the full probe notes (endpoints, headers, how the
theater code list and hall/tag vocabulary were discovered, and why prices are None).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .common import HALLS, Polite, city_of, slug

CHAIN = "cinemacity"
BASE = "https://www.cinemacity.ae/api/gatsby-source-boxofficeapi"
DUBAI_TZ = timezone(timedelta(hours=4))  # Asia/Dubai, UTC+4 year-round, no DST

# (Vista theater code, display name, mall, address) — from https://www.cinemacity.ae/our-locations/
# and each location's own page (2026-09-25). Addresses are stable venue data (not showtime data),
# so they are hardcoded here rather than re-scraped from HTML on every run.
CINEMAS_RAW = [
    ("G01IH", "Cinemacity AlQana", "AlQana",
     "14 Al Migharah St - Rabdan, Al Rabdan, Abu Dhabi, United Arab Emirates"),
    ("G0FO1", "Cinemacity Starlight", "Marina Mall",
     "Marina Mall, Abu Dhabi, Abu Dhabi, United Arab Emirates"),
    ("G00YW", "Cinemacity Fountain Views", "The Dubai Mall",
     "Boulevard Mohamad Bin Rached, Downtown Dubai, Dubai, United Arab Emirates"),
    ("X0FR7", "Cinemacity Arabian Centre", "Arabian Centre Mall",
     "Arabian Centre Mall, Al Khawaneej, Dubai, United Arab Emirates"),
    ("G01PB", "Cinemacity Rahmania", "Rahmania Mall",
     "Rahmania Mall, Rahmania, Sharjah, United Arab Emirates"),
    ("X110K", "Cinemacity Zero 6 Mall", "Zero 6 Mall",
     "University City Road - Zero 6 Mall, Al Juraina, Sharjah, United Arab Emirates"),
]

_LANG_RE = re.compile(r"^Localization\.Language\.(\w+)$")

# tag -> (hall enum, human label), checked in priority order; first match wins.
_HALL_RULES = [
    (lambda tags: any("Imax" in t for t in tags), "IMAX", "IMAX"),
    (lambda tags: any("4DX" in t for t in tags), "4DX", "4DX"),
    (lambda tags: any("ScreenX" in t for t in tags), "SCREENX", "ScreenX"),
    (lambda tags: any("Kids" in t for t in tags), "KIDS", "Kids"),
    (lambda tags: any("Suite" in t for t in tags), "SUITES", "Suites"),
    (lambda tags: "Showtime.Service.VIP" in tags, "VIP", "VIP"),
    (lambda tags: "Auditorium.Experience.PLF" in tags, "MAX", "PLF"),
    (lambda tags: "Auditorium.Experience.InfinityVision" in tags, "MAX", "InfinityVision"),
    (lambda tags: "Auditorium.Comfort.LuxurySeats" in tags, "GOLD", "Luxury Seats"),
    (lambda tags: "Showtime.Experience.CinemaCityArthouse" in tags, "OTHER", "Arthouse"),
]


def _hall(tags: set[str]) -> tuple[str, str]:
    for match, hall, label in _HALL_RULES:
        if match(tags):
            return hall, label
    return "Standard", "Standard"


def _film_lang(tags: set[str]) -> str | None:
    for t in tags:
        m = _LANG_RE.match(t)
        if m:
            return m.group(1)
    return None


def _book_url(show: dict) -> str | None:
    ticketing = ((show.get("data") or {}).get("ticketing")) or []
    for tk in ticketing:
        if tk.get("provider") == "default" and tk.get("urls"):
            return tk["urls"][0]
    for tk in ticketing:
        if tk.get("urls"):
            return tk["urls"][0]
    return None


def _cinema_id(name: str) -> str:
    short = re.sub(r"^cinemacity\s+", "", name, flags=re.IGNORECASE)
    return f"{CHAIN}-{slug(short)}"


def fetch(days: int = 2) -> dict:
    """Fetch Cinema City UAE cinemas + shows for today + `days`-1 more days.

    One `schedule` request per cinema covers the whole window (the API takes a
    from/to range), and movie metadata (title, certificate, runtime) is fetched
    in a couple of batched `movies?ids=...` calls — well under "1 req/s" and far
    fewer than one call per cinema x hall x day.
    """
    sess = Polite(gap=1.0)

    today = datetime.now(DUBAI_TZ).date()
    frm = f"{today.isoformat()}T03:00:00"
    to = f"{(today + timedelta(days=days)).isoformat()}T03:00:00"

    cinemas = []
    per_cinema_schedule: dict[str, dict] = {}
    movie_ids: set[str] = set()

    for code, name, mall, address in CINEMAS_RAW:
        cid = _cinema_id(name)
        city = city_of(address, name, mall)
        cinemas.append({
            "id": cid,
            "chain": CHAIN,
            "name": name,
            "name_ar": None,
            "city": city,
            "mall": mall,
            "address": address,
            "maps": None,
            "lat": None,
            "lng": None,
        })

        r = sess.get(f"{BASE}/schedule", params={
            "from": frm,
            "to": to,
            "includeAllMovies": "true",
            "theaters": f'{{"id":"{code}","timeZone":"Asia/Dubai"}}',
        })
        r.raise_for_status()
        payload = r.json().get(code, {})
        sched = payload.get("schedule", {})
        per_cinema_schedule[cid] = sched
        movie_ids.update(sched.keys())

    movies_meta: dict[str, dict] = {}
    ids_list = sorted(movie_ids)
    for i in range(0, len(ids_list), 25):
        chunk = ids_list[i:i + 25]
        r = sess.get(f"{BASE}/movies", params=[
            ("basic", "false"), ("castingLimit", "3"), *[("ids", mid) for mid in chunk]
        ])
        r.raise_for_status()
        for m in r.json():
            movies_meta[m["id"]] = m

    shows = []
    for cid, sched in per_cinema_schedule.items():
        for movie_id, by_date in sched.items():
            meta = movies_meta.get(movie_id, {})
            title = meta.get("title") or movie_id
            certificate = meta.get("certificate")
            rating = certificate.replace("-", "").replace(" ", "") if certificate else None
            runtime_s = meta.get("runtime")
            runtime = round(runtime_s / 60) if runtime_s else None

            for date, showlist in by_date.items():
                for s in showlist:
                    if s.get("isExpired"):
                        continue
                    tags = set(s.get("tags", []))
                    hall, hall_label = _hall(tags)
                    time_ = s["startsAt"].split("T")[1][:5]
                    shows.append({
                        "cinema": cid,
                        "film_title": title,
                        "film_lang": _film_lang(tags),
                        "film_rating": rating,
                        "runtime": runtime,
                        "date": date,
                        "time": time_,
                        "hall": hall,
                        "hall_label": hall_label,
                        "prices": None,  # see docs/probe/cinemacity.md — needs a seat hold
                        "book": _book_url(s),
                    })

    return {"cinemas": cinemas, "shows": shows}


if __name__ == "__main__":
    import json
    import sys

    result = fetch(days=2)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
