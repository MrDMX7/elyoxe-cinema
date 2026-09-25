"""Cine Royal Cinemas (UAE) reader — https://cineroyal.ae

Site is a server-rendered AngularJS app (Angular 1.x, "cinemaApp" module, inline
<script> in every /home/* page) talking to same-origin JSON endpoints under
/home/*. No public REST/OData docs; endpoints were found by reading the inline
controller in the page HTML (readers don't need a JS-executing browser — the
JSON endpoints are plain POST with a JSON body and work fine from `requests`
once a same-origin GET has set the session cookie). Details, sample payloads
and the pricing-safety reasoning are in docs/probe/cineroyal.md.

Chain has five cinemas, all in the Abu Dhabi emirate: Khalidiyah Mall (head
office), Dalma Mall, Al Dhannah Mall (Ruwais/Gharbia), Deerfields Mall
(Al Bahia) and WTC Mall Abu Dhabi. No Sharjah/Al Qana/Dubai locations under
this brand (that is a different chain, CinemaCity, previously "Grand
Cinemas"/Vox-adjacent — out of scope here).
"""
from __future__ import annotations

import datetime
import json
import re
from zoneinfo import ZoneInfo

from readers.common import CITIES, HALLS, Polite, city_of, slug

BASE = "https://cineroyal.ae"
CHAIN = "cineroyal"
DUBAI = ZoneInfo("Asia/Dubai")


def _today_dubai() -> datetime.date:
    return datetime.datetime.now(DUBAI).date()

# (display name, cinemaRefId, extra text so city_of() can place it — all are
# Abu Dhabi emirate malls, some (Deerfields, WTC) don't say "abu dhabi" in
# their own name so we hand city_of() a hint string built from the site's own
# "Cinemas" page copy, not invented).
CINEMAS_META = [
    ("Khalidiyah Mall", 2, "Al Khalidiyah, Abu Dhabi, UAE"),
    ("Dalma Mall", 101, "Musaffah, Abu Dhabi, UAE"),
    ("Al Dhannah Mall", 200, "Ruwais, Al Dhannah, Abu Dhabi, UAE"),
    ("Deerfields Mall", 300, "Al Bahia, Abu Dhabi, UAE"),
    ("WTC Mall Abu Dhabi", 10000001, "World Trade Center, Khalifa Bin Zayed St, Abu Dhabi, UAE"),
]

# The brand's own four screenType labels (from /home/cinemas nav + API) mapped
# onto the shared HALLS enum. Cine Royal runs no IMAX/4DX/MAX/SCREENX screens.
# GOLD and MAX are VOX's own brand names and are never used for another chain — Royal Plus
# (a Dolby Atmos premium screen, not a recliner/luxury seat tier) is "other chain's premium
# format" -> OTHER with the raw label kept in hall_label, matched by halls.yaml separately.
SCREEN_TYPE_TO_HALL = {
    "STANDARD": "Standard",
    "ROYAL PLUS": "OTHER",    # Dolby Atmos premium screen, brand's mid-tier — not GOLD (VOX-only)
    "ROYAL CLASS": "VIP",     # VVIP private viewing / recliners, brand's top tier
    "ROYAL KIDS": "KIDS",
    "KIDS": "KIDS",
}

_LANG_WORDS = [
    ("telugu", "Telugu"), ("malayalam", "Malayalam"), ("tamil", "Tamil"),
    ("hindi", "Hindi"), ("arabic", "Arabic"), ("punjabi", "Punjabi"),
    ("nepali", "Nepali"), ("english", "English"), ("kannada", "Kannada"),
]

_MOVIE_BLOCK_RE = re.compile(
    r'chooseScreen\?prettyUrl=([a-z0-9-]+)"\s+class="movie__title">([^<]+)<',
)


def _cinema_id(name: str) -> str:
    return f"{CHAIN}-{slug(name)}"


def _build_cinemas() -> tuple[list[dict], dict[int, str]]:
    cinemas = []
    ref_to_id = {}
    for name, cinema_ref, hint in CINEMAS_META:
        cid = _cinema_id(name)
        ref_to_id[cinema_ref] = cid
        city = city_of(name, hint) or "abu-dhabi"
        if city not in CITIES:
            raise ValueError(f"cineroyal: unknown city {city!r} for cinema {name!r}")
        cinemas.append({
            "id": cid,
            "chain": CHAIN,
            "name": f"Cine Royal Cinemas {name}",
            "name_ar": None,
            "city": city,
            "mall": name,
            "address": hint,
            "maps": "https://www.google.com/maps/search/?api=1&query=" + hint.replace(" ", "+"),
            "lat": None,
            "lng": None,
        })
    return cinemas, ref_to_id


def _film_lang(film_name: str, api_language) -> str | None:
    if isinstance(api_language, str) and api_language.strip():
        return api_language.strip().title()
    low = film_name.lower()
    for word, label in _LANG_WORDS:
        if re.search(r"\b" + word + r"\b", low):
            return label
    return None


def _runtime_minutes(length) -> int | None:
    if not isinstance(length, str):
        return None
    m = re.search(r"(\d+)", length)
    return int(m.group(1)) if m else None


def _list_now_showing(s: Polite) -> list[tuple[str, str]]:
    r = s.get(BASE + "/home/nowShowing")
    if r is None or r.status_code != 200:
        raise RuntimeError(
            f"cineroyal: /home/nowShowing failed (status={getattr(r, 'status_code', None)})"
        )
    seen, out = set(), []
    for m in _MOVIE_BLOCK_RE.finditer(r.text):
        pretty_url, title = m.group(1), m.group(2).strip()
        if pretty_url in seen:
            continue
        seen.add(pretty_url)
        out.append((pretty_url, title))
    if not out:
        raise RuntimeError("cineroyal: /home/nowShowing returned zero films (markup may have changed)")
    return out


def _get_showtimes(s: Polite, pretty_url: str, film_name: str, showdate: str) -> dict | None:
    headers = {"Content-Type": "application/json;charset=UTF-8", "Origin": BASE,
               "Referer": f"{BASE}/home/chooseScreen?prettyUrl={pretty_url}"}
    params = {"prettyUrl": pretty_url, "showdate": showdate, "cinemaRefId": 0,
              "filmName": film_name, "screenType": None}
    r = s.post(BASE + "/home/getShowTimesByFilmAndShowDate", data=json.dumps(params), headers=headers)
    if r is None or r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, dict) or "shows" not in data:
        return None
    return data


def _get_seat_prices(s: Polite, screen_ref, cinema_ref, show_date: str, show_time: str,
                      pretty_url: str) -> list[dict] | None:
    """One read-only call to the seat-map endpoint for a given hall/day. It
    returns the full seat grid with a per-seat `unitPrice`/`tierName` BEFORE
    any seat is picked (every seat comes back `"selected": false`) — no seat
    is reserved by this call, so it is the "ticket-types/price list" source
    the pricing rule allows. See docs/probe/cineroyal.md for the evidence.
    """
    # server 405s this endpoint without a Referer that looks like a chooseScreen
    # page (a plain hotlink/CSRF guard, not a session-hold check — see probe doc)
    headers = {"Content-Type": "application/json;charset=UTF-8", "Origin": BASE,
               "Referer": f"{BASE}/home/chooseScreen?prettyUrl={pretty_url}"}
    params = {"screenRefId": screen_ref, "cinemaRefId": cinema_ref,
              "showDate": show_date, "showTime": show_time}
    r = s.post(BASE + "/home/getSeatsByScreenRef", data=json.dumps(params), headers=headers)
    if r is None or r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    row_seats = data.get("rowSeats") if isinstance(data, dict) else None
    if not row_seats:
        return None
    tiers: dict[str, float] = {}
    for row in row_seats.values():
        for seat in row.get("seats", []):
            tier, price = seat.get("tierName"), seat.get("unitPrice")
            if tier and isinstance(price, (int, float)) and price > 0:
                tiers.setdefault(tier, float(price))
    if not tiers:
        return None
    return [{"seat": tier, "aed": aed} for tier, aed in sorted(tiers.items())]


def fetch(days: int = 2) -> dict:
    s = Polite(gap=1.0, headers={"Accept": "application/json, text/html;q=0.9, */*;q=0.8"})
    # one same-origin GET establishes the session cookie every POST below needs
    s.get(BASE + "/home/nowShowing")

    cinemas, ref_to_id = _build_cinemas()
    films = _list_now_showing(s)  # raises if the request failed or no films were found

    today = _today_dubai()
    dates = [today + datetime.timedelta(days=i) for i in range(max(days, 1))]
    want_dates = {d.strftime("%Y-%m-%d") for d in dates}
    price_cache: dict[tuple, list[dict] | None] = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    shows: list[dict] = []
    seen_shows: set[tuple] = set()

    showtime_calls = 0
    showtime_failed = 0

    for pretty_url, film_name in films:
        for d in dates:
            showdate_param = d.strftime("%d-%b-%Y")  # e.g. "25-Sep-2026" — what the site's own JS sends
            date_iso = d.strftime("%Y-%m-%d")
            showtime_calls += 1
            data = _get_showtimes(s, pretty_url, film_name, showdate_param)
            if not data:
                showtime_failed += 1
                continue
            film_meta = data.get("film") or {}
            film_rating = film_meta.get("rating") or None
            runtime = _runtime_minutes(film_meta.get("length"))
            film_lang = _film_lang(film_name, film_meta.get("language"))

            for cinema_block in data.get("shows", []):
                cinema_ref = cinema_block.get("cinemaRefId")
                cinema_id = ref_to_id.get(cinema_ref)
                if not cinema_id:
                    continue
                for st in cinema_block.get("filmShowTimeList", []):
                    hall = SCREEN_TYPE_TO_HALL.get(
                        (cinema_block.get("screenType") or "").upper(), "OTHER"
                    )
                    hall_label = cinema_block.get("screenType") or st.get("screen") or "OTHER"
                    formatted_time = st.get("formattedShowTime", "")
                    time_24 = _to_24h(formatted_time)
                    show_date_iso = st.get("showDate") or date_iso
                    if not time_24:
                        continue
                    # The API's own `showDate` is already the real calendar date (verified live:
                    # a "12:15AM" show carries showDate one day ahead of the query's showdate
                    # param, matching its UTC `showTime` converted to Asia/Dubai) — no business-
                    # day correction needed here, unlike Star/Roxy. Still, only keep shows that
                    # land inside the requested window: a `showdate=25-Sep` query can return a
                    # showDate of 26-Sep (the post-midnight show) which a `showdate=26-Sep` query
                    # also returns independently — filtering + dedup below collapses that.
                    if show_date_iso not in want_dates:
                        continue

                    screen_ref = st.get("screenRefId")
                    # Cache key is (cinema, hall, date) — one price sample per cinema x hall
                    # class x day, not per physical screen (several STANDARD screens at one
                    # cinema must not each cost their own call).
                    price_key = (cinema_ref, hall, show_date_iso)
                    if price_key not in price_cache:
                        health["attempted"] += 1
                        price_cache[price_key] = _get_seat_prices(
                            s, screen_ref, cinema_ref, show_date_iso, formatted_time, pretty_url
                        )
                    prices = price_cache[price_key]

                    film_title = film_name.title() if film_name.isupper() else film_name
                    dedup_key = (cinema_id, film_title, show_date_iso, time_24, hall)
                    if dedup_key in seen_shows:
                        continue
                    seen_shows.add(dedup_key)

                    shows.append({
                        "cinema": cinema_id,
                        "film_title": film_title,
                        "film_lang": film_lang,
                        "film_rating": film_rating,
                        "runtime": runtime,
                        "date": show_date_iso,
                        "time": time_24,
                        "hall": hall,
                        "hall_label": hall_label,
                        "prices": prices,
                        "book": f"{BASE}/home/chooseScreen?prettyUrl={pretty_url}",
                    })

    if not all(sh["hall"] in HALLS for sh in shows):
        raise ValueError("cineroyal: a show landed with a hall outside the shared HALLS enum")

    if showtime_calls and showtime_failed / showtime_calls > 0.5:
        raise RuntimeError(
            f"cineroyal: {showtime_failed}/{showtime_calls} getShowTimesByFilmAndShowDate "
            "requests failed (non-200 or unparseable) — treating the run as broken rather than "
            "publishing a partial/empty result"
        )
    if not shows:
        raise RuntimeError("cineroyal: fetch produced zero shows")

    health["priced"] = sum(1 for v in price_cache.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} getSeatsByScreenRef samples priced"
    return {"cinemas": cinemas, "shows": shows, "price_health": health}


def _to_24h(formatted: str) -> str | None:
    """"11:40PM" -> "23:40". Returns None if the string can't be parsed."""
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([AP]M)$", (formatted or "").strip(), re.I)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if ampm == "AM":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12
    return f"{hour:02d}:{minute:02d}"


if __name__ == "__main__":
    out = fetch()
    print(f"cinemas={len(out['cinemas'])} shows={len(out['shows'])}")
