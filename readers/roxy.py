"""Roxy Cinemas UAE reader.

Roxy runs on a custom Drupal 9/10 site (theroxycinemas.com). There is no
documented JSON API — showtimes are fetched by the page's own jQuery via a
Drupal AJAX endpoint that returns a JSON envelope wrapping a server-rendered
HTML fragment:

    GET /en/movie-schedule/ajax?nid=<movie-node-id>&promotion=
    -> {"status": "success", "html": "<div id=\"movie-schedule-block\">...</div>"}

The HTML fragment embeds one <input type="radio"> per session with all the
fields we need as plain attributes: cinema-name, cinema-id, screen, nid,
date, time, session. A single call returns *all* upcoming dates (today
through +5 days) for that movie across *all* six cinemas, so fetch() makes
one polite request per now-showing movie, not one per cinema x day.

See docs/probe/roxy.md for the full probe notes, including why prices are
always None here (booking needs login -> seat hold) and the Akamai block
seen when calling these endpoints from this dev network.
"""
from __future__ import annotations

import re
from typing import Any

from .common import CITIES, HALLS, Polite, city_of, slug

BASE = "https://www.theroxycinemas.com"

# url-slug, site cinema-id, display name, google maps url (None if not found in probe)
CINEMAS = [
    ("dubai-hills", "0000000007", "Dubai Hills Mall", None),
    ("al-khawaneej", "0000000006", "Al Khawaneej",
     "https://www.google.com/maps/place/Roxy+Cinemas+-+Al+Khawaneej/data=!4m2!3m1!1s0x0:0x8dcac873f1ed19b4"),
    ("the-beach", "0000000002", "The Beach, JBR",
     "https://www.google.com/maps/place/Roxy+Cinemas+The+Beach+JBR/data=!4m2!3m1!1s0x0:0xb417c5d8985a6ba0"),
    ("citywalk", "0000000001", "City Walk",
     "https://www.google.com/maps/place/Roxy+Cinemas+City+Walk/data=!4m2!3m1!1s0x0:0xb896252cb929a92"),
    ("boxpark", "0000000003", "Boxpark",
     "https://www.google.com/maps/place/Roxy+Cinemas+-+Boxpark/data=!4m2!3m1!1s0x0:0x43e1b42f4ce3ea05"),
    ("circle-mall", "0000000009", "Circle Mall", None),
]

# ROXY's own tier names -> the shared hall enum. Xtreme is Roxy's giant laser-screen
# format (-> MAX); Platinum is the ultra-premium recliner tier (-> VIP per the brief's
# rule); Gold/GOLD is a literal enum value; Silver is the base standard tier
# (-> Standard); Bronze is a discount tier and 2L (couple/love-seat format) and
# "Private Screen" (a whole room hired privately) don't match a named bucket -> OTHER,
# except Private Screen which is closest to SUITES.
HALL_MAP = {
    "xtreme": "MAX",
    "platinum": "VIP",
    "gold": "GOLD",
    "silver": "Standard",
    "bronze": "OTHER",
    "2l": "OTHER",
    "private screen": "SUITES",
}

MOVIE_LINK_RE = re.compile(r"/en/movie/([a-z0-9-]+)")
NID_RE = re.compile(r'data-history-node-id="(\d+)"')
SESSION_RE = re.compile(
    r'cinema-name="([^"]+)" cinema-id="([^"]+)" screen="([^"]+)" nid="(\d+)" '
    r'date="([^"]+)" time="([^"]+)" session="(\d+)"'
)
TITLE_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")
DURATION_RE = re.compile(r"(\d+)\s*Hour[s]?\s*(\d+)?\s*Minute[s]?")
LANG_RE = re.compile(r"Language:\s*([A-Za-z]+)")
RATING_RE = re.compile(r'id="movie-rating">([^<]+)<')

WEEKDAY_DATE_RE = re.compile(r"^([A-Za-z]{3}) (\d{1,2}) [A-Za-z]{3}$")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


def _hall(label: str) -> str:
    return HALL_MAP.get(label.strip().lower(), "OTHER")


def _map_date(raw: str, year: int) -> str | None:
    """'Sep 25 Fri' -> '2026-09-25'. Returns None if unparsable."""
    m = WEEKDAY_DATE_RE.match(raw)
    if not m:
        return None
    mon, day = m.group(1), int(m.group(2))
    mnum = MONTHS.get(mon)
    if not mnum:
        return None
    return f"{year:04d}-{mnum:02d}-{day:02d}"


def _cinemas() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Build the Cinema list and a site-cinema-id -> our-id lookup."""
    cinemas = []
    id_by_site_id = {}
    for _url_slug, site_id, name, maps in CINEMAS:
        address = f"{name}, Dubai, UAE"
        cid = f"roxy-{slug(name)}"
        id_by_site_id[site_id] = cid
        cinemas.append({
            "id": cid,
            "chain": "roxy",
            "name": f"ROXY Cinemas {name}",
            "name_ar": None,
            "city": city_of(address) or "dubai",
            "mall": name,
            "address": address,
            "maps": maps,
            "lat": None,
            "lng": None,
        })
    return cinemas, id_by_site_id


def _now_showing_slugs(session: Polite) -> list[str]:
    r = session.get(f"{BASE}/en")
    r.raise_for_status()
    return sorted(set(MOVIE_LINK_RE.findall(r.text)))


def _movie_meta(session: Polite, movie_slug: str) -> tuple[str | None, dict[str, Any]]:
    """Return (nid, {title, runtime, lang, rating}) for one movie page."""
    r = session.get(f"{BASE}/en/movie/{movie_slug}")
    r.raise_for_status()
    html = r.text
    nid_m = NID_RE.search(html)
    nid = nid_m.group(1) if nid_m else None

    cut = html.split("other-movies-sec")[0]
    title_m = TITLE_RE.search(cut)
    dur_m = DURATION_RE.search(cut)
    lang_m = LANG_RE.search(cut)
    rating_m = RATING_RE.search(cut)

    runtime = None
    if dur_m:
        hours = int(dur_m.group(1) or 0)
        minutes = int(dur_m.group(2) or 0)
        runtime = hours * 60 + minutes

    meta = {
        "title": title_m.group(1).strip() if title_m else movie_slug,
        "runtime": runtime,
        "lang": lang_m.group(1) if lang_m else None,
        "rating": (rating_m.group(1).strip().replace(" ", "") if rating_m else None) or None,
    }
    return nid, meta


def fetch(days: int = 2) -> dict[str, list[dict[str, Any]]]:
    """Fetch Roxy Cinemas UAE cinemas + showtimes for today + (days - 1) more days.

    Prices are always None: seeing a session's seat map/price requires logging in
    (booking.theroxycinemas.com redirects to /en/login first), which is a seat-hold
    flow we're not allowed to trigger. See docs/probe/roxy.md.
    """
    import datetime

    session = Polite(gap=1.0)
    cinemas, id_by_site_id = _cinemas()

    today = datetime.date.today()
    want_dates = {(today + datetime.timedelta(days=i)).isoformat() for i in range(max(days, 1))}
    year = today.year

    shows: list[dict[str, Any]] = []
    seen_slots: set[tuple[str, str, str, str]] = set()

    for movie_slug in _now_showing_slugs(session):
        nid, meta = _movie_meta(session, movie_slug)
        if not nid:
            continue

        r = session.get(f"{BASE}/en/movie-schedule/ajax", params={"nid": nid, "promotion": ""})
        if r.status_code != 200:
            continue
        try:
            payload = r.json()
        except ValueError:
            continue
        html = payload.get("html", "")

        for m in SESSION_RE.finditer(html):
            _cinema_name, site_cinema_id, screen, _nid, raw_date, time_, session_id = m.groups()
            cid = id_by_site_id.get(site_cinema_id)
            if not cid:
                continue
            date = _map_date(raw_date, year)
            if date is None or date not in want_dates:
                continue

            key = (cid, screen, date, session_id)
            if key in seen_slots:
                continue
            seen_slots.add(key)

            shows.append({
                "cinema": cid,
                "film_title": meta["title"],
                "film_lang": meta["lang"],
                "film_rating": meta["rating"],
                "runtime": meta["runtime"],
                "date": date,
                "time": time_,
                "hall": _hall(screen),
                "hall_label": screen,
                "prices": None,
                "book": f"{BASE}/en/movie/{movie_slug}#movie-schedule-block",
            })

    return {"cinemas": cinemas, "shows": shows}


if __name__ == "__main__":
    import json
    print(json.dumps(fetch(), ensure_ascii=False, indent=2))
