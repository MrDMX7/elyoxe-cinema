"""Reader for Cinema City UAE (cinemacity.ae) — six sites across Abu Dhabi, Dubai and Sharjah.

Site is a Gatsby front-end backed by a JSON API at
  https://www.cinemacity.ae/api/gatsby-source-boxofficeapi/...
(the "boxofficeapi" name is a Gatsby data-source label, not a third-party service —
 it is Cinema City's own public API and needs no auth, cookies or referrer).

Prices (live, no seat hold): the booking widget at booking.cinemacity.ae (Webedia/Boxoffice
"ticketing" app) exposes the same two calls its seat-preview screen makes before any seat is touched:
  POST /api/launch/seatpreview/<boxofficeSessionId>  -> areas + a dataToken (no seat selected)
  POST /api/Tickets/GetTickets {"dataToken": ...}    -> ticket types with price (fils, VAT incl.)
One sample per cinema x hall_label per run; any failure there leaves `prices` None for that hall.

See docs/probe/cinemacity.md for the full probe notes (endpoints, headers, how the
theater code list and hall/tag vocabulary were discovered, and the price calls).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from readers.common import CITIES, HALLS, Polite, city_of, lang_key, slug, youtube_id, fmt3d as _fmt3d

CHAIN = "cinemacity"
BASE = "https://www.cinemacity.ae/api/gatsby-source-boxofficeapi"
BOOKING = "https://booking.cinemacity.ae"
DUBAI_TZ = timezone(timedelta(hours=4))  # Asia/Dubai, UTC+4 year-round, no DST
_LAUNCH_RE = re.compile(r"/launch/ticketing/([0-9a-f-]{36})")

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
    # MAX/GOLD are VOX brand names (review ruling 2026-09-26): another chain's large-format
    # screen is OTHER with its own label, and a recliner/luxury-seat tier is VIP.
    (lambda tags: "Auditorium.Experience.PLF" in tags, "OTHER", "PLF"),
    (lambda tags: "Auditorium.Experience.InfinityVision" in tags, "OTHER", "InfinityVision"),
    (lambda tags: "Auditorium.Comfort.LuxurySeats" in tags, "VIP", "Luxury Seats"),
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


_SUBS_RE = re.compile(r"^Localization\.Subtitles?\.(\w+)$")


def movie_extras(meta: dict) -> dict:
    """Poster and genres from a `movies` record. Its trailers are boxoffice.media MP4s, not
    YouTube — a YouTube link is taken only if one ever appears."""
    out: dict = {}
    poster = meta.get("poster") or (((meta.get("locale") or {}).get("poster")) or {}).get("url")
    if (poster or "").startswith("http"):
        out["film_poster"] = poster
    loc = meta.get("locale") or {}
    for v in (loc.get("hdTrailers") or []) + (loc.get("sdTrailers") or []):
        yt = youtube_id((v or {}).get("url"))
        if yt:
            out["film_trailer"] = yt
            break
    genres = [g.strip() for g in (meta.get("genres") or "").split(",") if g.strip()]
    if genres:
        out["film_genres"] = genres
    return out


def show_lang(tags: set[str]) -> dict:
    """{"lang", "subs"} from a showtime's Localization.* tags, only when present."""
    out: dict = {}
    lang = lang_key(_film_lang(tags))
    if lang:
        out["lang"] = lang
    matches = [_SUBS_RE.match(t) for t in tags]
    subs = sorted({k for k in (lang_key(m.group(1)) for m in matches if m) if k})
    if subs:
        out["subs"] = subs
    return out


def _book_url(show: dict) -> str | None:
    ticketing = ((show.get("data") or {}).get("ticketing")) or []
    for tk in ticketing:
        if tk.get("provider") == "default" and tk.get("urls"):
            return tk["urls"][0]
    for tk in ticketing:
        if tk.get("urls"):
            return tk["urls"][0]
    return None


def _session_uuid(book: str | None) -> str | None:
    m = _LAUNCH_RE.search(book or "")
    return m.group(1) if m else None


def _sample_prices(sess: Polite, session_uuid: str) -> list[dict] | None:
    """Seat-class prices for one showtime, from the widget's own pre-seat calls. None on any failure."""
    hdr = {"Accept": "application/json", "Content-Type": "application/json"}
    try:
        r = sess.post(f"{BOOKING}/api/launch/seatpreview/{session_uuid}",
                      json={"requestData": None, "circuitId": 0, "selectedLanguageCulture": "en-US"},
                      headers=hdr)
        if r.status_code != 200:
            return None
        pv = r.json()
        token = pv.get("dataToken")
        layout = ((pv.get("selectSeatsModel") or {}).get("seatsLayoutModel")) or {}
        area_name = {str(a.get("areaNumber")): (a.get("name") or "").strip() for a in layout.get("areas") or []}
        cat_name: dict[str, str] = {}
        for row in layout.get("rows") or []:
            for seat in row.get("seats") or []:
                code, aid = seat.get("areaCategoryCode"), str(seat.get("areaId"))
                if code and area_name.get(aid):
                    cat_name.setdefault(code, area_name[aid])
        if not token:
            return None
        r = sess.post(f"{BOOKING}/api/Tickets/GetTickets", json={"dataToken": token}, headers=hdr)
        if r.status_code != 200:
            return None
        groups = ((r.json().get("selectTicketsModel") or {}).get("groupedTicketTypes")) or []
        out: dict[str, float] = {}
        for g in groups:
            for t in g.get("ticketTypeModels") or []:
                if (t.get("isMemberTicket") or t.get("isRedemptionTicket") or t.get("isThirdPartyMemberTicket")
                        or t.get("isCardPaymentPromotionTicket") or t.get("isLoyaltyCreditTicket")):
                    continue
                price = float(t.get("price") or 0)
                if price <= 0:
                    continue
                seat = cat_name.get(t.get("areaCategoryCode")) or (t.get("displayName") or "").strip()
                if seat and seat not in out:  # first listed ticket per seat class = the headline fare
                    out[seat] = round(price / 100, 2)
        return [{"seat": k, "aed": v} for k, v in out.items()] or None
    except Exception:  # any HTTP/JSON/shape surprise leaves this hall unpriced, never fails the chain
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
    frm = f"{today.isoformat()}T00:00:00"  # calendar day start: keeps today's 00:00-03:00 shows
    to = f"{(today + timedelta(days=days)).isoformat()}T03:00:00"

    cinemas = []
    per_cinema_schedule: dict[str, dict] = {}
    movie_ids: set[str] = set()

    for code, name, mall, address in CINEMAS_RAW:
        cid = _cinema_id(name)
        city = city_of(address, name, mall)
        if city not in CITIES:
            raise ValueError(f"cinemacity: no city for {name!r} ({address!r})")
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

    price_cache: dict[tuple, list[dict] | None] = {}
    price_tries: dict[tuple[str, str], int] = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    today_s, last_s = today.isoformat(), (today + timedelta(days=days - 1)).isoformat()
    shows = []
    for cid, sched in per_cinema_schedule.items():
        for movie_id, by_date in sched.items():
            meta = movies_meta.get(movie_id, {})
            title = meta.get("title") or movie_id
            certificate = meta.get("certificate")
            rating = certificate.replace("-", "").replace(" ", "") if certificate else None
            runtime_s = meta.get("runtime")
            runtime = round(runtime_s / 60) if runtime_s else None
            extras = movie_extras(meta)

            for _business_day, showlist in by_date.items():
                for s in showlist:
                    if s.get("isExpired"):
                        continue
                    tags = set(s.get("tags", []))
                    hall, hall_label = _hall(tags)
                    # calendar date of the real start (the API buckets by a 03:00 business day)
                    date, time_ = s["startsAt"][:10], s["startsAt"].split("T")[1][:5]
                    if not (today_s <= date <= last_s):
                        continue
                    book = _book_url(s) or "https://www.cinemacity.ae/our-locations/"
                    key = (cid, hall_label, date, _fmt3d(title))
                    # one successful sample per cinema x hall x show date (weekday/weekend prices
                    # differ; a 3D title is its own key); a failed sample is retried on
                    # the next show of that hall, at most twice, then the hall stays unpriced
                    if price_cache.get(key) is None and price_tries.get(key, 0) < 2:
                        price_tries[key] = price_tries.get(key, 0) + 1
                        uuid = _session_uuid(book)
                        price_cache[key] = _sample_prices(sess, uuid) if uuid else None
                        health["attempted"] += 1
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
                        "prices": key,  # resolved after the loop, once every hall is sampled
                        "book": book,
                        **extras,
                        **show_lang(tags),
                    })

    for sh in shows:
        sh["prices"] = price_cache.get(sh["prices"])
    if not shows:
        raise RuntimeError("cinemacity: zero shows in the window — schedule API changed or blocked")
    health["priced"] = sum(1 for v in price_cache.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} seatpreview/GetTickets samples priced"
    return {"cinemas": cinemas, "shows": shows, "price_health": health}


if __name__ == "__main__":
    import json
    import sys

    result = fetch(days=2)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
