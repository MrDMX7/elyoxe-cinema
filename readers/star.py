"""Star Cinemas UAE reader.

Public API of https://www.starcinemas.ae (backed by web-api.starcinemas.ae). No login, no seat
hold: showtimes come from `movie-shows` (a plain schedule listing), and — where affordable —
one seat-map read (`seat-layout/<ss_id>`) per cinema x hall is used to sample real seat-class
prices. See docs/probe/star.md for the full endpoint map, the token, and the rate-limit story.
"""
from __future__ import annotations

import datetime
import json

from readers.common import CITIES, HALLS, Polite, city_of, slug

BASE = "https://web-api.starcinemas.ae/api/v3/external"
SITE = "https://www.starcinemas.ae"
CHAIN = "star"

# Public, read-only bearer token shipped inside Star's own web bundle
# (https://www.starcinemas.ae/assets/index-*.js, `const TOKEN=...`). It is not a login
# credential — every anonymous visitor's browser sends this same static token on every
# API call the site itself makes; we are replicating that, not authenticating as a user.
TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJ0b2tlbiI6Ijc1ZDAzZDQwLTJiYTQtNDk5ZC04ZGU0LTY4NTQ4ODIzZDUxNSIsImlhdCI6MTY4MjU0MTUyOX0."
    "kutbXGZb1pQsxymG2dKqopjNcthIuYoexIVfL9RYpNY"
)

HEADERS = {"Accept": "application/json", "Authorization": TOKEN}

# cinema_latitude/longitude the API returns for cinemas it hasn't surveyed yet are a
# placeholder ("21.12345"/"31.123456" and close variants) repeated verbatim across several
# cinemas — not real coordinates. Anything matching this pattern is dropped to None rather
# than published as a location.
_DUMMY_LAT = {"21.12345", "12.12345"}
_DUMMY_LNG = {"31.12345", "31.123456"}

# screen_type_name (Star's own screen-class label) -> our hall enum. Star's screen classes are
# audio/format/seat-comfort labels (NORMAL, SUITES, KIDS, DOLBY, ATMOS, PREMIUM...) not the
# IMAX/4DX/MAX big-format screens the shared enum otherwise covers — Star simply doesn't run
# those. Only the labels that map cleanly are translated; everything else is OTHER with the
# original Star label kept verbatim in hall_label. Seat *classes* (Star Select, Star Plus, Star
# VIP, Premium, Premium Plus, Star Platinum Suites...) are never hall names — they go in
# prices[].seat.
HALL_MAP = {
    "NORMAL": "Standard",
    "SUITES": "SUITES",
    "KIDS": "KIDS",
    "IMAX": "IMAX",
    "4DX": "4DX",
}


def _dummy_latlng(lat: str | None, lng: str | None) -> bool:
    return (lat or "").strip() in _DUMMY_LAT and (lng or "").strip() in _DUMMY_LNG


def _to_float(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _cinema_from_record(rec: dict) -> dict:
    cid = f"star-{slug(rec['cinema_name'])}"
    name = rec["cinema_name"]
    address = rec.get("cinema_address") or ""
    location = rec.get("cinema_location") or ""
    city = city_of(name, address, location) or _CITY_OVERRIDE.get(rec["cinema_id"])
    # "Al Ghurair Centre - Dubai" -> mall "Al Ghurair Centre"; standalone sites like
    # "National Cinema - Abu Dhabi" have no real mall, so mall is left as the same first
    # segment (best-effort) rather than invented.
    mall = name.split(" - ")[0].split(",")[0].strip() or None
    lat = _to_float(rec.get("cinema_latitude"))
    lng = _to_float(rec.get("cinema_longitude"))
    if _dummy_latlng(rec.get("cinema_latitude"), rec.get("cinema_longitude")):
        lat = lng = None
    return {
        "id": cid,
        "chain": CHAIN,
        "name": name,
        "name_ar": None,  # the public API never returns an Arabic cinema_name
        "city": city,
        "mall": mall,
        "address": address,
        "maps": rec.get("map_view_url") or None,
        "lat": lat,
        "lng": lng,
        "_cinema_id": rec["cinema_id"],  # internal only, stripped before writing the fixture
    }


# A handful of cinema_ids whose name/address alone don't carry a recognizable city word.
_CITY_OVERRIDE: dict[int, str] = {}


def _hall_from_show(rec: dict) -> tuple[str, str]:
    raw = (rec.get("screen_type_name") or "").strip() or (rec.get("mf_name") or "Standard").strip()
    hall = HALL_MAP.get(raw.upper(), "OTHER")
    label = raw if raw else (rec.get("mf_name") or "Standard")
    return hall, label


def _book_url(movie_id: int) -> str:
    # The site keeps the selected cinema in browser state (header dropdown / localStorage),
    # not in the URL — /now-showing-booking/<movie_id>/1/ is the real link the site's own
    # movie cards point at (the trailing "1" is a fixed language id, not a cinema id). We
    # were not able to confirm a per-cinema deep link, so every show for a given film links
    # to this one page; see docs/probe/star.md.
    return f"{SITE}/now-showing-booking/{movie_id}/1/"


def fetch(days: int = 2) -> dict:
    http = Polite(gap=2.0, headers=HEADERS)

    today = datetime.date.today()
    wanted_dates = {(today + datetime.timedelta(days=i)).isoformat() for i in range(max(days, 1))}

    cinemas: list[dict] = []
    cinema_by_id: dict[int, dict] = {}
    r = http.get(f"{BASE}/cinemas")
    for rec in r.json().get("Records", []):
        c = _cinema_from_record(rec)
        cinema_by_id[rec["cinema_id"]] = c
        cinemas.append({k: v for k, v in c.items() if k != "_cinema_id"})

    r = http.get(f"{BASE}/now-showing-movies")
    movies = r.json().get("Records", {}).get("data", []) or []
    movie_ids = sorted({m["movie_id"] for m in movies if m.get("movie_id")})

    # price cache: (cinema_id, hall) -> [{"seat": ..., "aed": ...}, ...] | "blocked"
    # At most one seat-layout read per cinema x hall for the whole run (well inside the
    # brief's "at most one price call per cinema x hall per day" ceiling, since days<=2 share
    # one cached sample rather than re-sampling per day).
    price_cache: dict[tuple[int, str], object] = {}
    notes: list[str] = []

    shows: list[dict] = []
    for movie_id in movie_ids:
        r = http.get(f"{BASE}/movie-shows/{movie_id}")
        if r.status_code == 403:
            notes.append(f"movie-shows/{movie_id}: 403 rate-limited, skipped")
            continue
        recs = r.json().get("Records", {}).get("data", []) or []
        for rec in recs:
            cid_num = rec.get("cinema_id")
            cinema = cinema_by_id.get(cid_num)
            if cinema is None:
                continue
            date = rec.get("ss_start_date")
            if date not in wanted_dates:
                continue
            time_str = (rec.get("ss_start_show_time") or "")[:5]
            if not time_str:
                continue
            hall, hall_label = _hall_from_show(rec)

            cache_key = (cid_num, hall_label)
            if cache_key not in price_cache:
                ss_id = rec.get("ss_id")
                prices = None
                if ss_id:
                    pr = http.get(f"{BASE}/seat-layout/{ss_id}")
                    if pr.status_code == 403:
                        price_cache[cache_key] = None
                        notes.append(
                            f"seat-layout/{ss_id} (cinema {cid_num}, hall {hall_label}): "
                            "403 rate-limited, prices left null"
                        )
                    elif pr.status_code == 200:
                        try:
                            seat_recs = pr.json().get("Records") or []
                        except json.JSONDecodeError:
                            seat_recs = []
                        by_type: dict[str, float] = {}
                        for s in seat_recs:
                            seat_type = s.get("sst_seat_type")
                            price = _to_float(s.get("seat_price"))
                            if seat_type and price and price > 0:
                                by_type[seat_type] = price
                        price_cache[cache_key] = (
                            [{"seat": k, "aed": v} for k, v in sorted(by_type.items())]
                            if by_type
                            else None
                        )
                    else:
                        price_cache[cache_key] = None
                else:
                    price_cache[cache_key] = None

            prices = price_cache[cache_key]

            shows.append(
                {
                    "cinema": cinema["id"],
                    "film_title": rec.get("movie_title") or rec.get("alternate_movie_name_language"),
                    "film_lang": rec.get("lang_name"),
                    "film_rating": rec.get("rating") or None,
                    "runtime": rec.get("mrrdr_runtime"),
                    "date": date,
                    "time": time_str,
                    "hall": hall,
                    "hall_label": hall_label,
                    "prices": prices,
                    "book": _book_url(movie_id),
                }
            )

    if notes:
        print(f"[readers.star] {len(notes)} rate-limit note(s):")
        for n in notes:
            print(f"  - {n}")

    return {"cinemas": cinemas, "shows": shows}
