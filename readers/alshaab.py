"""Reader for Al Shaab Cinema (alshaabcinema.com) — one site, Al Shaab Village, Sharjah (owner 2026-11-19).

The site is ASP.NET MVC, server-rendered, no login, no bot check (read from the laptop 2026-11-19):
  GET /                                      every film (Now Showing + Coming Soon) as `.single-movie` blocks:
                                             /movies/<slug>/<id>, title, genre, language, certificate, thumbnail
  GET /movies/<slug>/<id>                    the film page: one date tab per showing day (#YYYY-MM-DD), 2D/3D,
                                             the trailer (YouTube), the running time
  GET /Movie/ShowsByMalls?date=&movieId=     a JSON string of HTML: per theatre (<p>Al Shaab Village - Sharjah</p>)
                                             and screen (<i>CINEMA 4</i>) its times, each one a booking link
                                             /Booking/SetSession?mallId&showDate&timeId&movieId&screenId
A time after midnight (12:15AM after a 10:00PM in the same list, timeIds rising) belongs to the day's late
programme: 00:00–02:59 is the next calendar day. Not later: a big Indian release opens with a 06:00AM fan show on
its first day (OM, 2026-11-20).

Prices (live, nothing held): the SetSession link sets the session and lands on /booking/seats, whose inline script
names the show (currdate «20 Nov 2026», currtime = timeId, screen_id); GET /Seat/Seats?date&time&movie&screen
&reservation=0 returns every seat with seat_name and seat_price + extra_price (AED, VAT incl. — the page adds the
two). No seat is selected or held. One sample per cinema x hall x date x 2D/3D per run.
Screens on 2026-11-19: CINEMA 1, 4 and 5 (NORMAL 36.75, VIP seats 52.50) and PEARL SUITE (105).
"""
from __future__ import annotations

import html as htmllib
import json
import re
from datetime import date as Date, datetime, timedelta, timezone

from readers.common import (CACHE_MISS, CITIES, Polite, cache_get, cache_set, city_of, lang_key, slug,
                            youtube_id, fmt3d as _fmt3d)

CHAIN = "alshaab"
BASE = "https://www.alshaabcinema.com"
DUBAI_TZ = timezone(timedelta(hours=4))
# the one site's address (Google Maps, 2026-11-19); a theatre the schedule names that is not here gets a cinema of
# its own from its name, so a reopened branch shows up by itself (steps/cinema_coords.py places it on the map)
KNOWN = {
    "al shaab village - sharjah": ("Al Shaab Village", "Al Shaab Village, Al Riqa Suburb, Sharjah, United Arab Emirates"),
}
SEATS = {"NORMAL": "Standard", "VIP": "VIP", "PEARL SUIT": "Pearl Suite", "PEARL SUITE": "Pearl Suite"}
# the site this module reads; readers/cinemax.py hands in its own (the same MITE Solutions platform, rakcinemax.com)
SITE = {"chain": CHAIN, "base": BASE, "brand": "Al Shaab Cinema", "known": KNOWN}

_BLOCK = re.compile(r'<div class="col-md-3 col-sm-4 single-movie">(.*?)(?=<div class="col-md-3 col-sm-4 single-movie">|</div>\s*</div>\s*</div>\s*</div>\s*</div>|$)', re.S)
_HREF = re.compile(r'href="(/movies/[^"/#]+/(\d+))')
_TABS = re.compile(r'href="#(\d{4}-\d\d-\d\d)"')
_LI = re.compile(r"<li>(.*?)</li>", re.S)
_THEATRE = re.compile(r"<p>(.*?)</p>(.*?)(?=<p>|$)", re.S)
_TIME = re.compile(r"href\s*=\s*'(/Booking/SetSession\?[^']+)'[^>]*>\s*(\d{1,2}):(\d\d)\s*([AP]M)\s*<", re.I)
_VARS = re.compile(r"\b(screen_id|movieId|currdate|currtime|reservation)\s*=\s*'([^']*)'")
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _text(s) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def nice_title(t: str) -> str:
    """The site's ALL-CAPS title in title case («BACHELOR PARTY D’EUX» -> «Bachelor Party D’Eux»)."""
    t = _text(t)
    return _WORD.sub(lambda m: m.group(0).capitalize(), t) if t.isupper() else t


def films_from_home(page: str, base: str = BASE) -> list[dict]:
    """Every `.single-movie` block on the home page -> {id, path, title, genres, lang, rating, poster}, once per id."""
    out, seen = [], set()
    for blk in _BLOCK.findall(page):
        m = _HREF.search(blk)
        if not m or m.group(2) in seen:
            continue
        seen.add(m.group(2))
        # the poster's alt carries the whole title; the <h3> is cut («OM -CHAPTER 1: UDH...») on the Now Showing tab
        alt = re.search(r'<img[^>]*alt="([^"]+)"', blk)
        title = alt or re.search(r"<h3[^>]*>(.*?)</h3>", blk, re.S)
        genre = re.search(r'<span class="title">(.*?)</span>', blk, re.S)
        lang = re.search(r"<h5[^>]*>(.*?)</h5>", blk, re.S)
        cert = re.search(r'<span class="certificate">(.*?)</span>', blk, re.S)
        img = re.search(r'<img src="([^"]+)"', blk)
        out.append({
            "id": m.group(2), "path": m.group(1),
            "title": _text(title.group(1)) if title else None,
            "genres": [g.strip() for g in _text(genre.group(1)).split("|") if g.strip()] if genre else [],
            "lang": _text(lang.group(1)) if lang else None,
            "rating": re.sub(r"\s+", "", _text(cert.group(1))) if cert else None,
            "poster": (base + img.group(1)) if img and img.group(1).startswith("/") else (img.group(1) if img else None),
        })
    return out


def film_page(page: str) -> dict:
    """The film page's showing days, 2D/3D, trailer id and running time (minutes)."""
    hero = page.split('id="content_hero"', 1)[-1].split("Synopsis", 1)[0]
    fmt = re.search(r'<span class="certificate">\s*([23]D)\s*</span>', hero)
    trailer = None
    for href in re.findall(r'href="([^"]*youtube[^"]*)"', hero):
        trailer = youtube_id(href.replace("//http", "http"))
        if trailer:
            break
    rt = re.search(r"Running time</i>\s*(?:(\d+)\s*Hrs?)?\s*(?:(\d+)\s*Mins?)?", page)
    runtime = (int(rt.group(1) or 0) * 60 + int(rt.group(2) or 0)) if rt and (rt.group(1) or rt.group(2)) else None
    return {"dates": sorted(set(_TABS.findall(page))), "fmt": fmt.group(1) if fmt else None,
            "trailer": trailer, "runtime": runtime or None}


def _hhmm(h: str, m: str, ap: str) -> int:
    h24 = int(h) % 12 + (12 if ap.upper() == "PM" else 0)
    return h24 * 60 + int(m)


def shows_from_day(body: str, day: str, base: str = BASE) -> list[dict]:
    """A ShowsByMalls answer (its JSON string already decoded) -> [{theatre, screen, date, time, book}]."""
    out = []
    for theatre, rest in _THEATRE.findall(body or ""):
        for li in _LI.findall(rest):
            sc = re.search(r"<i>(.*?)</i>", li, re.S)
            screen = _text(sc.group(1)) if sc else ""
            for link, h, m, ap in _TIME.findall(li):
                mins = _hhmm(h, m, ap)
                d = Date.fromisoformat(day) + timedelta(days=1 if mins < 3 * 60 else 0)
                out.append({"theatre": _text(theatre), "screen": screen, "date": d.isoformat(),
                            "time": f"{mins // 60:02d}:{mins % 60:02d}", "book": base + htmllib.unescape(link)})
    return out


def hall_of(screen: str) -> tuple[str, str]:
    return ("SUITES", "Pearl Suite") if "PEARL" in screen.upper() else ("Standard", "Standard")


def prices_from_seats(payload: dict) -> list[dict] | None:
    """/Seat/Seats -> [{"seat", "aed"}] per seat category, cheapest first; None when there is no seat list.

    Keyed on seat_category_id, not seat_name: Cinemax's screen P1 sells two «NORMAL» categories at 36.75 and 42.00
    (2026-11-19). A name two categories share keeps its plain label on the cheaper one; the dearer one is named by its
    rows («Standard (A–B)»)."""
    if not isinstance(payload, dict) or payload.get("isAvail") != 1:
        return None
    cats: dict[str, dict] = {}
    for s in payload.get("result") or []:
        if s.get("isBlank") or not s.get("seat_name"):
            continue
        aed = round(float(s.get("seat_price") or 0) + float(s.get("extra_price") or 0), 2)
        if aed <= 0:
            continue
        name = str(s["seat_name"]).strip().upper()
        c = cats.setdefault(str(s.get("seat_category_id") or s.get("seat_category") or name),
                            {"label": SEATS.get(name, name.title()), "aed": aed, "rows": set()})
        c["aed"] = min(c["aed"], aed)
        if s.get("seat_row"):
            c["rows"].add(str(s["seat_row"]))
    out, seen = [], set()
    for c in sorted(cats.values(), key=lambda c: c["aed"]):
        label = c["label"]
        if label in seen:
            rows = sorted(c["rows"])
            label = f"{label} ({rows[0]}–{rows[-1]})" if len(rows) > 1 else f"{label} ({rows[0]})" if rows else f"{label} {c['aed']:g}"
        seen.add(c["label"])
        out.append({"seat": label, "aed": c["aed"]})
    return out or None


def _decode(r) -> str:
    try:
        v = r.json()
    except ValueError:
        return r.text or ""
    return v if isinstance(v, str) else ""


def _sample(sess: Polite, book: str, base: str = BASE) -> list[dict] | None:
    try:
        page = sess.get(book).text
        v = dict(_VARS.findall(page))
        if not v.get("currtime") or not v.get("screen_id"):
            return None
        r = sess.get(f"{base}/Seat/Seats", params={"date": v.get("currdate"), "time": v["currtime"], "movie": v.get("movieId"),
                                                   "screen": v["screen_id"], "reservation": v.get("reservation") or "0"})
        return prices_from_seats(r.json()) if r.status_code == 200 else None
    except Exception:  # noqa: BLE001 - an unpriced hall, never a failed chain
        return None


def _cinema(theatre: str, site: dict = SITE) -> dict:
    chain = site["chain"]
    mall, address = site["known"].get(theatre.lower(), (re.sub(r"\s*-\s*[^-]+$", "", theatre) or theatre, theatre))
    city = city_of(theatre.split(" - ")[-1]) or city_of(address, theatre)
    if city not in CITIES:
        raise ValueError(f"{chain}: no city for theatre {theatre!r}")
    return {"id": f"{chain}-{slug(theatre)}", "chain": chain, "name": f"{site['brand']} {mall}", "name_ar": None,
            "city": city, "mall": mall, "address": address, "maps": None, "lat": None, "lng": None}


def fetch(days: int = 2, cache: dict | None = None, site: dict = SITE) -> dict:
    chain, base = site["chain"], site["base"]
    sess = Polite(gap=0.7, headers={"X-Requested-With": "XMLHttpRequest"})
    today = datetime.now(DUBAI_TZ).date()
    window = {(today + timedelta(days=i)).isoformat() for i in range(days)}
    r = sess.get(base + "/")
    r.raise_for_status()
    films = films_from_home(r.text, base)
    if not films:
        raise RuntimeError(f"{chain}: the home page lists no films (markup changed?)")

    cinemas: dict[str, dict] = {}
    shows: list[dict] = []
    price: dict[tuple, list | None] = {}
    tries: dict[tuple, int] = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    # the business day before today still owns the after-midnight shows of today (00:00–02:59)
    ask_days = sorted(window | {(today - timedelta(days=1)).isoformat()})
    for f in films:
        fr = sess.get(base + f["path"])
        if fr.status_code != 200:
            continue
        fp = film_page(fr.text)
        title = nice_title(f["title"] or "")
        if not title:
            continue
        if fp["fmt"] == "3D" and "3d" not in title.lower():
            title = f"{title} (3D)"
        lang = lang_key(f["lang"]) if f["lang"] else None
        for day in (d for d in ask_days if d in fp["dates"]):
            sr = sess.get(f"{base}/Movie/ShowsByMalls", params={"date": day, "movieId": f["id"]})
            if sr.status_code != 200:
                continue
            for s in shows_from_day(_decode(sr), day, base):
                if s["date"] not in window:
                    continue
                cin = cinemas.get(s["theatre"]) or cinemas.setdefault(s["theatre"], _cinema(s["theatre"], site))
                hall, label = hall_of(s["screen"])
                # one sample per physical screen, not per hall label: Cinemax's «SCREEN P1»…«P4» and its plain screens are
                # all «Standard» halls, and P1 sells a 42.00 «NORMAL» row the plain screens may not (2026-11-19)
                key = (cin["id"], s["screen"] or label, s["date"], _fmt3d(title))
                if key not in price:
                    hit = cache_get(cache, key)
                    if hit is not CACHE_MISS:
                        price[key], tries[key] = hit, 2
                        health["cached"] = health.get("cached", 0) + 1
                if price.get(key) is None and tries.get(key, 0) < 2:
                    tries[key] = tries.get(key, 0) + 1
                    price[key] = _sample(sess, s["book"], base)
                    health["attempted"] += 1
                    cache_set(cache, key, price[key])
                show = {"cinema": cin["id"], "film_title": title, "film_lang": f["lang"], "film_rating": f["rating"],
                        "runtime": fp["runtime"], "date": s["date"], "time": s["time"], "hall": hall, "hall_label": label,
                        "prices": key, "book": s["book"], "_screen": s["screen"]}
                if f["poster"]:
                    show["film_poster"] = f["poster"]
                if fp["trailer"]:
                    show["film_trailer"] = fp["trailer"]
                if f["genres"]:
                    show["film_genres"] = f["genres"]
                if lang:
                    show["lang"] = lang
                shows.append(show)
    for sh in shows:
        sh["prices"] = price.get(sh["prices"])
    if not shows:
        raise RuntimeError(f"{chain}: zero shows in the window — the schedule endpoint changed or is blocked")
    health["priced"] = sum(1 for v in price.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} seat-map samples priced"
    return {"cinemas": list(cinemas.values()), "shows": shows, "price_health": health}


if __name__ == "__main__":
    import sys

    json.dump(fetch(days=2), sys.stdout, ensure_ascii=False, indent=2)
