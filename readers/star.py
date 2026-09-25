"""Star Cinemas UAE reader.

Public API of https://www.starcinemas.ae (backed by web-api.starcinemas.ae). No login, no seat
hold: showtimes come from `movie-shows` (a plain schedule listing), and — where affordable —
one seat-map read (`seat-layout/<ss_id>`) per cinema x hall is used to sample real seat-class
prices. See docs/probe/star.md for the full endpoint map, the token, and the rate-limit story.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
import time
from zoneinfo import ZoneInfo

from readers.common import CITIES, HALLS, Polite, city_of, slug

BASE = "https://web-api.starcinemas.ae/api/v3/external"
SITE = "https://www.starcinemas.ae"
CHAIN = "star"
DUBAI = ZoneInfo("Asia/Dubai")

# Public, read-only bearer token shipped inside Star's own web bundle
# (https://www.starcinemas.ae/assets/index-*.js, `STARCINEMAS_TOKEN="..."`). It is not a login
# credential — every anonymous visitor's browser sends this same static token on every
# API call the site itself makes; we are replicating that, not authenticating as a user.
# Tried first, as-is. If it has rotated (a 401/403 from any `/external/*` call), `fetch()`
# re-extracts a fresh one from the live bundle once — see `_refresh_token()`.
TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJ0b2tlbiI6Ijc1ZDAzZDQwLTJiYTQtNDk5ZC04ZGU0LTY4NTQ4ODIzZDUxNSIsImlhdCI6MTY4MjU0MTUyOX0."
    "kutbXGZb1pQsxymG2dKqopjNcthIuYoexIVfL9RYpNY"
)

# Regexes used to re-extract the token from a fresh copy of Star's bundle. The site is a Vite
# build: the entry HTML links one or more `/assets/index-*.js` (and sometimes other chunk
# names); the token is assigned to `STARCINEMAS_TOKEN` (then aliased to a local `TOKEN`) as a
# plain string literal. Tested against a saved snippet in tests/fixtures/star_bundle_snippet.js.
_BUNDLE_SRC_RE = re.compile(r'<script[^>]+src="(/assets/[^"]+\.js)"')
_TOKEN_RE = re.compile(r'STARCINEMAS_TOKEN\s*=\s*"([^"]+)"')
_TOKEN_FALLBACK_RE = re.compile(r'\bTOKEN\s*=\s*"(eyJ[A-Za-z0-9_=.\-]+)"')

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
# prices[].seat. GOLD and MAX are VOX's own brand names and are never used for another chain.
HALL_MAP = {
    "NORMAL": "Standard",
    "SUITES": "SUITES",
    "KIDS": "KIDS",
    "IMAX": "IMAX",
    "4DX": "4DX",
}

# Fallback city map for the 17 known Star sites, keyed by the cinema's own slug(name). This is
# a safety net only: every current site's name already carries a recognizable city word (e.g.
# "National Cinema - Abu Dhabi"), so city_of() resolves all 17 without it in practice. Kept so a
# rename that drops the trailing "- <City>" suffix degrades to this table instead of a null
# city, and fetch() still raises rather than publish a cinema with no city if both miss.
_CITY_OVERRIDE: dict[str, str] = {
    "al-ghurair-centre-dubai": "dubai",
    "national-cinema-abu-dhabi": "abu-dhabi",
    "central-mall-kc-abu-dhabi": "abu-dhabi",
    "grand-safeer-abu-dhabi": "abu-dhabi",
    "mall-of-al-ain-al-ain": "al-ain",
    "bawadi-mall-al-ain": "al-ain",
    "grand-mall-ajman": "ajman",
    "century-mall-fujairah": "fujairah",
    "dana-plaza-fujairah": "fujairah",
    "star-cinemas-ras-al-khaimah": "ras-al-khaimah",
    "mall-of-uaq-umm-al-quwain": "umm-al-quwain",
    "al-wahda-mall-abu-dhabi": "abu-dhabi",
    "al-foah-al-ain": "al-ain",
    "barari-outlet-mall-al-ain": "al-ain",
    "al-raha-abu-dhabi": "abu-dhabi",
    "junction-mall-dip-dubai": "dubai",
    "makani-zakher-mall-al-ain": "al-ain",
}


def _today_dubai() -> datetime.date:
    return datetime.datetime.now(DUBAI).date()


def extract_token(bundle_text: str) -> str | None:
    """Pull the bearer token out of a Star JS bundle's source text.

    Tried in the order the real bundle was found to use: the named
    `STARCINEMAS_TOKEN="..."` assignment first, then a bare `TOKEN="eyJ..."` (a JWT-shaped
    string) as a fallback in case the variable gets renamed in a future build.
    """
    m = _TOKEN_RE.search(bundle_text)
    if m:
        return m.group(1)
    m = _TOKEN_FALLBACK_RE.search(bundle_text)
    return m.group(1) if m else None


def _refresh_token(http: Polite) -> str | None:
    """Fetch the live site, find its current JS bundle(s), and re-extract the token."""
    r = http.get(SITE)
    if r is None or r.status_code != 200:
        return None
    bundle_paths = _BUNDLE_SRC_RE.findall(r.text)
    for path in bundle_paths:
        url = path if path.startswith("http") else f"{SITE}{path}"
        br = http.get(url)
        if br is None or br.status_code != 200:
            continue
        token = extract_token(br.text)
        if token:
            return token
    return None


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
    city = city_of(name, address, location) or _CITY_OVERRIDE.get(slug(name))
    if city not in CITIES:
        raise RuntimeError(
            f"star: could not determine a city for cinema {name!r} (id {rec.get('cinema_id')!r}); "
            "add it to readers/star.py::_CITY_OVERRIDE"
        )
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


def _actual_start_dubai(rec: dict) -> datetime.datetime | None:
    """The real start instant, converted to Asia/Dubai. Star buckets shows on
    `ss_start_date`/`ss_start_show_time` by *business day* (a show at "00:25" on business day
    2026-09-25 actually plays on the calendar date 2026-09-26): `ss_actual_start_date_time`
    (falling back to `ss_start_date_time`) is a real epoch-ms UTC timestamp that doesn't have
    that problem, so date/time are always derived from it rather than from the string fields.
    """
    ms = rec.get("ss_actual_start_date_time") or rec.get("ss_start_date_time")
    if not isinstance(ms, (int, float)):
        return None
    try:
        return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).astimezone(DUBAI)
    except (OverflowError, OSError, ValueError):
        return None


# A single 401/403 is first treated as a transient rate-limit: back off and retry once before
# blaming the token (the probe saw Star 403 bursts under load, not only token rot).
BACKOFF_S = 30


def _get_with_refresh(http: Polite, url: str, state: dict) -> "requests.Response | None":  # noqa: F821
    r = http.get(url)
    if r is not None and r.status_code in (401, 403):
        print(f"[readers.star] {url}: {r.status_code}, backing off {BACKOFF_S}s and retrying once",
              file=sys.stderr)
        time.sleep(BACKOFF_S)
        r = http.get(url)
    if r is not None and r.status_code in (401, 403) and not state["refreshed"]:
        state["refreshed"] = True
        new_token = _refresh_token(Polite(gap=2.0))
        if new_token and new_token != state["token"]:
            state["token"] = new_token
            http.s.headers["Authorization"] = new_token
            r = http.get(url)
    if r is not None and r.status_code in (401, 403):
        raise RuntimeError(
            f"star: {url} returned {r.status_code} — bearer token (readers/star.py TOKEN) appears "
            "rotated/invalid, and re-extracting a fresh one from the live bundle also failed"
        )
    return r


def fetch(days: int = 2) -> dict:
    state = {"token": TOKEN, "refreshed": False}
    http = Polite(gap=2.0, headers={"Accept": "application/json", "Authorization": TOKEN})

    today = _today_dubai()
    wanted_dates = {(today + datetime.timedelta(days=i)).isoformat() for i in range(max(days, 1))}

    cinemas: list[dict] = []
    cinema_by_id: dict[int, dict] = {}
    r = _get_with_refresh(http, f"{BASE}/cinemas", state)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"star: /cinemas failed (status={getattr(r, 'status_code', None)})")
    for rec in r.json().get("Records", []):
        c = _cinema_from_record(rec)
        cinema_by_id[rec["cinema_id"]] = c
        cinemas.append({k: v for k, v in c.items() if k != "_cinema_id"})
    if not cinemas:
        raise RuntimeError("star: /cinemas returned zero cinemas")

    r = _get_with_refresh(http, f"{BASE}/now-showing-movies", state)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"star: /now-showing-movies failed (status={getattr(r, 'status_code', None)})")
    movies = r.json().get("Records", {}).get("data", []) or []
    movie_ids = sorted({m["movie_id"] for m in movies if m.get("movie_id")})
    rating_by_movie = {m["movie_id"]: (m.get("rating") or None) for m in movies if m.get("movie_id")}

    # price cache: (cinema_id, hall_label) -> [{"seat": ..., "aed": ...}, ...] | None
    # At most one seat-layout read per cinema x hall for the whole run (well inside the
    # brief's "at most one price call per cinema x hall per day" ceiling, since days<=2 share
    # one cached sample rather than re-sampling per day).
    price_cache: dict[tuple[int, str], object] = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    notes: list[str] = []

    shows: list[dict] = []
    listing_calls = 0
    listing_failed = 0
    for movie_id in movie_ids:
        listing_calls += 1
        r = _get_with_refresh(http, f"{BASE}/movie-shows/{movie_id}", state)
        if r is None or r.status_code != 200:
            listing_failed += 1
            notes.append(f"movie-shows/{movie_id}: status={getattr(r, 'status_code', None)}, skipped")
            continue
        try:
            recs = r.json().get("Records", {}).get("data", []) or []
        except json.JSONDecodeError:
            listing_failed += 1
            notes.append(f"movie-shows/{movie_id}: unparseable JSON, skipped")
            continue
        for rec in recs:
            cid_num = rec.get("cinema_id")
            cinema = cinema_by_id.get(cid_num)
            if cinema is None:
                continue
            start = _actual_start_dubai(rec)
            if start is None:
                continue
            date = start.date().isoformat()
            if date not in wanted_dates:
                continue
            time_str = start.strftime("%H:%M")
            hall, hall_label = _hall_from_show(rec)

            cache_key = (cid_num, hall_label)
            if cache_key not in price_cache:
                ss_id = rec.get("ss_id")
                if ss_id:
                    health["attempted"] += 1
                    pr = http.get(f"{BASE}/seat-layout/{ss_id}")
                    # Price-call failures never raise — they only ever leave prices null,
                    # per the binding rule (a 401/403 here is not the token-rot path; only
                    # the listing/showtime calls above trigger a token refresh + raise).
                    if pr is not None and pr.status_code == 200:
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
                        notes.append(
                            f"seat-layout/{ss_id} (cinema {cid_num}, hall {hall_label}): "
                            f"status={getattr(pr, 'status_code', None)}, prices left null"
                        )
                else:
                    price_cache[cache_key] = None

            prices = price_cache[cache_key]

            shows.append(
                {
                    "cinema": cinema["id"],
                    "film_title": rec.get("movie_title") or rec.get("alternate_movie_name_language"),
                    "film_lang": rec.get("lang_name"),
                    "film_rating": rec.get("rating") or rating_by_movie.get(movie_id) or None,
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
        print(f"[readers.star] {len(notes)} note(s):", file=sys.stderr)
        for n in notes:
            print(f"  - {n}", file=sys.stderr)

    if listing_calls and listing_failed / listing_calls > 0.5:
        raise RuntimeError(
            f"star: {listing_failed}/{listing_calls} movie-shows requests failed "
            "(non-200 or unparseable) — treating the run as broken rather than publishing a "
            "partial/empty result"
        )
    if not shows:
        raise RuntimeError("star: fetch produced zero shows")

    health["priced"] = sum(1 for v in price_cache.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} seat-layout samples priced"
    return {"cinemas": cinemas, "shows": shows, "price_health": health}
