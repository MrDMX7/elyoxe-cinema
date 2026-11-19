"""Reader for Cinema Akil (cinemaakil.com) — Dubai's independent arthouse cinema: Alserkal Avenue (one 133-seat screen,
unassigned seating) and its screen at the 25hours Hotel, One Central (owner 2026-11-19).

One public call carries everything (Cloudflare in front, no challenge):
  GET https://www.cinemaakil.com/api/films?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
    newFilms[]          id, title, image_url, languageandsubtitles, buy_tickets_link («/now-showing-booking/<id>/<slug>»)
    films.Records[]     movie_id, original_movie_title, rating «PG-15», runtime, trailers[].trailer_link, and
                        screens[].shows[{date, shows[]}] — each show: ss_start_show_time (local «18:00»), cinema_name,
                        cinema_address, screen_name, mf_name «2D», movie_lang, sub_lang_1_name, and its prices in
                        schedulePricing[{sst_seat_type, rc_total_amount}] (Standard 52.50; «Chairs» at the hotel)
Booking is per film (you pick the show on that page). Its talks and film-club nights are listed as their own titles
(«Spirited Away with The Reel Deal Film Club», «Fjord - TALK TO STRANGERS Moderated by: …»): the film is the title,
so the night joins the film's page, at its own price.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from readers.common import CITIES, Polite, city_of, lang_key, slug, subs_keys, youtube_id

CHAIN = "akil"
SITE = "https://www.cinemaakil.com"
DUBAI_TZ = timezone(timedelta(hours=4))
# cinema_name (lower) -> (id, mall, address); Google Maps, 2026-11-19. Another name gets a cinema of its own.
KNOWN = {
    "cinema akil in alserkal avenue": ("akil-alserkal-avenue", "Alserkal Avenue",
                                       "Warehouse 68, Alserkal Avenue, Al Quoz Industrial Area 1, Dubai, United Arab Emirates"),
    "cinema akil in 25hours hotel": ("akil-25hours-hotel", "25hours Hotel One Central",
                                     "25hours Hotel, One Central, Trade Centre St, Dubai, United Arab Emirates"),
}
_EVENT = re.compile(r"\s+(?:with\s+the\s+reel\s+deal\s+film\s+club|-\s*talk\s+to\s+strangers\b.*)$", re.I)


def film_of(title: str) -> str:
    """The film a night is built on: «Spirited Away with The Reel Deal Film Club» -> «Spirited Away»."""
    t = re.sub(r"\s+", " ", (title or "").strip())
    return _EVENT.sub("", t).strip() or t


def cinema_of(name: str, address: str = "") -> dict:
    key = re.sub(r"\s+", " ", (name or "").strip()).lower()
    cid, mall, addr = KNOWN.get(key, (f"{CHAIN}-{slug(re.sub(r'(?i)^cinema akil( in)?', '', name))}",
                                      re.sub(r"(?i)^cinema akil( in)?\s*", "", name).strip() or name, address or name))
    city = city_of(addr, name) or "dubai"
    if city not in CITIES:
        raise ValueError(f"akil: no city for {name!r}")
    return {"id": cid, "chain": CHAIN, "name": f"Cinema Akil {mall}", "name_ar": None, "city": city, "mall": mall,
            "address": addr, "maps": None, "lat": None, "lng": None}


def shows_from(payload: dict, window: set[str]) -> tuple[list[dict], list[dict]]:
    """The films API answer -> (cinemas, shows) for the days in `window`."""
    meta = {str(f.get("id")): f for f in payload.get("newFilms") or []}
    cinemas: dict[str, dict] = {}
    shows: list[dict] = []
    for r in ((payload.get("films") or {}).get("Records") or []):
        mid = str(r.get("movie_id"))
        nf = meta.get(mid, {})
        title = film_of(r.get("original_movie_title") or nf.get("title") or "")
        if not title:
            continue
        book = SITE + nf["buy_tickets_link"] if str(nf.get("buy_tickets_link") or "").startswith("/") else f"{SITE}/now-showing-booking/{mid}/{slug(title)}"
        trailer = next((y for y in (youtube_id(t.get("trailer_link")) for t in r.get("trailers") or []) if y), None)
        rating = (r.get("rating") or "").replace("-", "").replace(" ", "") or None
        for sc in r.get("screens") or []:
            for day in sc.get("shows") or []:
                if day.get("date") not in window:
                    continue
                for s in day.get("shows") or []:
                    tm = s.get("ss_start_show_time") or ""
                    if not re.match(r"^\d\d:\d\d$", tm) or s.get("ss_is_active", "Y") != "Y":
                        continue
                    cin = cinema_of(s.get("cinema_name") or "", (s.get("cinema_address") or "").title())
                    cinemas.setdefault(cin["id"], cin)
                    prices = {}
                    for p in s.get("schedulePricing") or []:
                        aed = float(p.get("rc_total_amount") or 0)
                        seat = (p.get("sst_seat_type") or "").strip() or "Standard"
                        if aed > 0:
                            prices[seat] = min(aed, prices.get(seat, aed))
                    lang_name = (s.get("movie_lang") or "").split(",")[0].strip() or None
                    show = {"cinema": cin["id"], "film_title": title if (s.get("mf_name") or "").upper() != "3D" else f"{title} (3D)",
                            "film_lang": lang_name, "film_rating": rating, "runtime": r.get("runtime") or None,
                            "date": day["date"], "time": tm, "hall": "Standard", "hall_label": "Standard",
                            "prices": [{"seat": k, "aed": round(v, 2)} for k, v in sorted(prices.items(), key=lambda kv: kv[1])] or None,
                            "book": book}
                    if str(nf.get("image_url") or "").startswith("http"):
                        show["film_poster"] = nf["image_url"]
                    if trailer:
                        show["film_trailer"] = trailer
                    if lang_key(lang_name):
                        show["lang"] = lang_key(lang_name)
                    subs = subs_keys(s.get("sub_lang_1_name") or "")
                    if subs:
                        show["subs"] = subs
                    shows.append(show)
    return list(cinemas.values()), shows


def fetch(days: int = 2, cache: dict | None = None) -> dict:
    sess = Polite(gap=1.0)
    today = datetime.now(DUBAI_TZ).date()
    window = {(today + timedelta(days=i)).isoformat() for i in range(days)}
    r = sess.get(f"{SITE}/api/films", params={"startDate": min(window), "endDate": max(window)})
    r.raise_for_status()
    cinemas, shows = shows_from(r.json(), window)
    if not shows:
        raise RuntimeError("akil: zero shows in the window — the films API changed or is blocked")
    priced = sum(1 for s in shows if s["prices"])
    return {"cinemas": cinemas, "shows": shows,
            "price_health": {"attempted": 0, "priced": priced, "error": None if priced else "no schedulePricing on any show"}}


if __name__ == "__main__":
    import sys

    json.dump(fetch(days=2), sys.stdout, ensure_ascii=False, indent=2)
