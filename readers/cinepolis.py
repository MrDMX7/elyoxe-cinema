"""Reader for Cinépolis UAE (uae.cinepolisgulf.com) — one site, Oasis Mall, Sharjah (owner 2026-11-19).

Its Circle Mall (JVC) site closed on 2025-11-12 and is Roxy now. The site's own public API, no token for these calls
(Cloudflare sets a __cf_bm cookie and asks nothing), base https://api.cinepolisgulf.com/api, country_id=2 = UAE:
  GET cinemas/cinemas/?event_country_id=&country_id=2          the UAE cinemas (cinema_id, cinema_name; lat/lng 0)
  GET v2/home/nowshowing-v2/?country_id=2, advancebooking-v2    the films: ID, Title «X (Lang)», Rating, RunTime,
                                                                movie_lang, movie_trailer, movie_image_url_1
  GET movies/show-dates-v2?movie_id=&country_id=2               the film's days
  GET movies/show-times-v2/{id}/?show_date=&movie_id=&country_id=2
      per cinema (id, name, name_ar, address) and screen type (Standard, Junior) its sessions: sessionId «1252-144918»,
      showtime «2026-11-19T14:30:00.000Z» — the Z is false, it is Dubai local time (14:30–22:10 only makes sense so),
      sessionDimension «3D» or null
Prices, nothing held: GET booking/ticket-price/{session}/{cinema}/?country_id=2 (without all=Y, which adds ~30 promo
types) -> Tickets[{Description STANDARD / DELUXE / RECLINER, PriceInCents (VAT incl.)}]; test, voucher and promo
types are dropped. 2026-11-19: Standard 40, Deluxe 50, Recliner 70 (2D); 48, 58, 78 (3D).
Booking: the film's page (the per-show routes only work inside the app).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from readers.common import (CACHE_MISS, CITIES, Polite, cache_get, cache_set, city_of, lang_key, slug,
                            youtube_id, fmt3d as _fmt3d)

CHAIN = "cinepolis"
API = "https://api.cinepolisgulf.com/api"
SITE = "https://uae.cinepolisgulf.com"
DUBAI_TZ = timezone(timedelta(hours=4))
_SKIP = re.compile(r"VOUCHER|PROMO|TEST|COMP|BOGO|STAFF|INVITE", re.I)


def _data(r):
    r.raise_for_status()
    body = r.json()
    return body.get("data") if isinstance(body, dict) else body


def hall_of(screen_type: str) -> tuple[str, str]:
    t = (screen_type or "").strip()
    if re.search(r"junior|kids", t, re.I):
        return "KIDS", "Junior"
    return "Standard", "Standard"


def prices_from_tickets(data) -> list[dict] | None:
    """ticket-price -> [{"seat", "aed"}], one per seat class, cheapest first; None when nothing is on sale."""
    out: dict[str, float] = {}
    for t in ((data or {}).get("Tickets") or []):
        name = (t.get("Description") or "").strip()
        cents = t.get("PriceInCents") or 0
        if not name or _SKIP.search(name) or cents <= 0 or t.get("IsRedemptionTicket") or t.get("IsComplimentaryTicket"):
            continue
        if t.get("IsThirdPartyMemberTicket") or t.get("IsAvailableForLoyaltyMembersOnly"):
            continue
        seat = re.sub(r"\s+[23]D$", "", name, flags=re.I).upper()
        seat = re.sub(r"\bDBB\b", "DOUBLE BEAN BAG", re.sub(r"^JR\s+", "JUNIOR ", seat)).title()
        out[seat] = min(round(cents / 100, 2), out.get(seat, 1e9))
    return [{"seat": k, "aed": v} for k, v in sorted(out.items(), key=lambda kv: kv[1])] or None


def sessions(data) -> list[dict]:
    """show-times-v2 -> [{cinema, name, name_ar, address, screen, session, date, time, dim}]"""
    out = []
    for c in data or []:
        for st in c.get("screenTypes") or []:
            for s in st.get("showTimes") or []:
                when = s.get("showtime") or ""
                m = re.match(r"(\d{4}-\d\d-\d\d)T(\d\d:\d\d)", when)
                sid = str(s.get("sessionId") or "")
                if not m or "-" not in sid:
                    continue
                out.append({"cinema": str(c.get("id")), "name": c.get("name") or "", "name_ar": (c.get("name_ar") or "").strip() or None,
                            "address": c.get("address") or "", "screen": st.get("name") or "",
                            "session": sid.split("-", 1)[1], "date": m.group(1), "time": m.group(2),
                            "dim": (s.get("sessionDimension") or "").upper() or None})
    return out


def _cinema(s: dict) -> dict:
    name = s["name"]                                     # «Oasis Mall - Sharjah»
    mall = re.sub(r"\s*-\s*[^-]+$", "", name) or name
    address = ", ".join(x for x in (s["address"], name.split(" - ")[-1], "United Arab Emirates") if x)
    # the name's own emirate first: «Al Wahda street» in Oasis Mall's address reads as Abu Dhabi's Al Wahda Mall
    city = city_of(name.split(" - ")[-1]) or city_of(name, address)
    if city not in CITIES:
        raise ValueError(f"cinepolis: no city for {name!r}")
    return {"id": f"{CHAIN}-{slug(name)}", "chain": CHAIN, "name": f"Cinepolis {name}", "name_ar": s["name_ar"],
            "city": city, "mall": mall, "address": address, "maps": None, "lat": None, "lng": None}


def fetch(days: int = 2, cache: dict | None = None) -> dict:
    sess = Polite(gap=0.6, headers={"Origin": SITE, "Referer": SITE + "/"})
    today = datetime.now(DUBAI_TZ).date()
    window = [(today + timedelta(days=i)).isoformat() for i in range(days)]
    films: dict[str, dict] = {}
    for feed in ("v2/home/nowshowing-v2/", "v2/home/advancebooking-v2/"):
        for f in _data(sess.get(f"{API}/{feed}", params={"country_id": 2})) or []:
            films.setdefault(f["ID"], f)
    if not films:
        raise RuntimeError("cinepolis: no films in now-showing or advance booking")

    cinemas: dict[str, dict] = {}
    shows: list[dict] = []
    price: dict[tuple, list | None] = {}
    tries: dict[tuple, int] = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    for fid, f in films.items():
        dates = set(_data(sess.get(f"{API}/movies/show-dates-v2", params={"movie_id": fid, "country_id": 2})) or [])
        title = (f.get("Title") or "").strip()
        lang = f.get("movie_lang") or None
        rating = re.sub(r"\s+", "", f.get("Rating") or "") or None
        poster = f.get("movie_image_url_1") if str(f.get("movie_image_url_1") or "").startswith("http") and not str(f.get("movie_image_url_1")).endswith("/null") else None
        trailer = youtube_id(f.get("movie_trailer"))
        for day in (d for d in window if d in dates):
            r = sess.get(f"{API}/movies/show-times-v2/{fid}/", params={"show_date": day, "movie_id": fid, "country_id": 2})
            if r.status_code != 200:
                continue
            for s in sessions(_data(r)):
                if s["date"] not in window:
                    continue
                cin = cinemas.get(s["cinema"]) or cinemas.setdefault(s["cinema"], _cinema(s))
                hall, label = hall_of(s["screen"])
                t = f"{title} (3D)" if s["dim"] == "3D" and "3d" not in title.lower() else title
                key = (cin["id"], label, s["date"], _fmt3d(t))
                if key not in price:
                    hit = cache_get(cache, key)
                    if hit is not CACHE_MISS:
                        price[key], tries[key] = hit, 2
                        health["cached"] = health.get("cached", 0) + 1
                if price.get(key) is None and tries.get(key, 0) < 2:
                    tries[key] = tries.get(key, 0) + 1
                    try:
                        pr = sess.get(f"{API}/booking/ticket-price/{s['session']}/{s['cinema']}/", params={"country_id": 2})
                        price[key] = prices_from_tickets(_data(pr)) if pr.status_code == 200 else None
                    except Exception:  # noqa: BLE001 - an unpriced hall, never a failed chain
                        price[key] = None
                    health["attempted"] += 1
                    cache_set(cache, key, price[key])
                show = {"cinema": cin["id"], "film_title": t, "film_lang": lang, "film_rating": rating,
                        "runtime": f.get("RunTime") or None, "date": s["date"], "time": s["time"], "hall": hall,
                        "hall_label": label, "prices": key, "book": f"{SITE}/movies/{fid}"}
                if poster:
                    show["film_poster"] = poster
                if trailer:
                    show["film_trailer"] = trailer
                if lang_key(lang):
                    show["lang"] = lang_key(lang)
                shows.append(show)
    for sh in shows:
        sh["prices"] = price.get(sh["prices"])
    if not shows:
        raise RuntimeError("cinepolis: zero shows in the window — the show-times API changed or is blocked")
    health["priced"] = sum(1 for v in price.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} ticket-price samples priced"
    return {"cinemas": list(cinemas.values()), "shows": shows, "price_health": health}


if __name__ == "__main__":
    import sys

    json.dump(fetch(days=2), sys.stdout, ensure_ascii=False, indent=2)
