"""Reader for Safeer Cinemas (safeercinemas.com) — one site, Dibba, Fujairah (owner 2026-11-19). The Grand Safeer Mall
cinema in Musaffah is Star's, already read by readers/star.py.

ASP.NET WebForms on IIS, no login, no bot check, but slow (the seat page takes ~8 s): every request gets 90 s.
  GET /                                  films as MovieDetails.aspx?movieid=<n>&schedulestatus=1 (0 = coming soon)
  GET MovieDetails.aspx?…                <h3>Title (PG15)</h3>, the language, 2D/3D, «Running Time : 130 min», the trailer,
                                         and the signed link MovieShowTime.aspx?movieid=<base64>-<signature>
  GET MovieShowTime.aspx?…               per day (tab_N) and venue (<h4>Safeer Cinemas - Dibba</h4>) the times, each
                                         <a href=SelectSeats.aspx?EventID=…&ReqDate=…>11:45 PM <div class='cinema-screen'>Screen-5</div>
Every parameter is base64 plus a signature (ReqDate «MjAyNi0xMS0xOQ==» = 2026-11-19): readable, not buildable, so the
links are taken from the page as they are. The SelectSeats link is the booking link and, opened, the price list,
nothing held: <div class='section-title …'>STANDARD</div><div class='price-info'>STANDARD - …36.75</div>; a section
with no name (rows A–B, 42.00 on 2026-11-19) is named by its rows. One sample per screen x date x 2D/3D.
"""
from __future__ import annotations

import base64
import html as htmllib
import json
import re
from datetime import date as Date, datetime, timedelta, timezone
from urllib.parse import unquote

from readers.common import CACHE_MISS, CITIES, Polite, cache_get, cache_set, lang_key, slug, subs_keys, youtube_id, fmt3d as _fmt3d

CHAIN = "safeer"
BASE = "https://www.safeercinemas.com"
DUBAI_TZ = timezone(timedelta(hours=4))
TIMEOUT = 90
KNOWN = {"safeer cinemas - dibba": ("safeer-dibba", "Safeer Market", "Safeer Market, 1st floor, Dibba, Fujairah, United Arab Emirates", "fujairah")}
_FILM = re.compile(r"href=['\"]?MovieDetails\.aspx\?movieid=(\d+)&(?:amp;)?schedulestatus=1")
_TAB = re.compile(r"<div id='tab_\d+' class='tab-pane[^']*'>(.*?)(?=<div id='tab_\d+' class='tab-pane|$)", re.S)
_VENUE = re.compile(r"<h4[^>]*>(.*?)</h4>(.*?)(?=<h4|$)", re.S)
_TIME = re.compile(r"<a href=['\"]?(SelectSeats\.aspx\?[^'\" >]+)['\"]?[^>]*>\s*(\d{1,2}):(\d\d)\s*([AP]M)\s*(?:<div class='cinema-screen'>(.*?)</div>)?", re.I | re.S)
_SECTION = re.compile(r"section-title[^'\"]*['\"]>([^<]*)</div>\s*<div class=['\"]price-info['\"]>.*?([\d]+(?:\.\d+)?)\s*</div>(.*?)(?=<div class=['\"]section['\"]>|$)", re.S)


def _text(s) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def b64(part: str) -> str | None:
    """«MjAyNi0xMS0xOQ%3d%3d-ldlXf%2fyJhvU%3d» -> «2026-11-19» (the value before the signature)."""
    v = unquote(part or "").split("-", 1)[0]
    try:
        return base64.b64decode(v + "=" * (-len(v) % 4)).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def details(page: str) -> dict:
    h3 = re.search(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>\s*<h4>(.*?)</h4>\s*<h5><span>(.*?)</span>", page, re.S)
    raw = _text(h3.group(1)) if h3 else ""
    get = lambda label: (re.search(rf"<b>\s*{label}\s*:\s*</b>\s*([^<]*)", page) or [None, ""])[1].strip()
    rt = re.search(r"(\d+)\s*min", get("Running Time"))
    link = re.search(r"(MovieShowTime\.aspx\?movieid=[^'\" >]+)", page)
    return {"title": re.sub(r"\s*\((?:G|PG\d*|\d{2}\+|18TC|TBC)\)\s*$", "", raw, flags=re.I).strip(),
            "lang": get("Language") or (_text(h3.group(2)) if h3 else None) or None,
            "genres": [g.strip() for g in (_text(h3.group(3)) if h3 else get("Genre")).split(",") if g.strip()],
            "fmt": (_text(h3.group(4)) if h3 else "").upper() or None,
            "rating": get("Rating").replace(" ", "") or None, "runtime": int(rt.group(1)) if rt else None,
            "subs": get(r"Subtitle\(s\)") or None,
            "trailer": youtube_id((re.search(r"href=(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]{11})", page) or [None, None])[1]),
            "showtimes": htmllib.unescape(link.group(1)) if link else None}


def _hhmm(h, m, ap) -> int:
    return (int(h) % 12 + (12 if ap.upper() == "PM" else 0)) * 60 + int(m)


def shows_from_page(page: str) -> list[dict]:
    """MovieShowTime.aspx -> [{venue, screen, date, time, book}]; ReqDate is the business day, 00:00–02:59 the next one."""
    out = []
    for tab in _TAB.findall(page) or [page]:
        for venue, rest in _VENUE.findall(tab):
            for link, h, m, ap, screen in _TIME.findall(rest):
                link = htmllib.unescape(link)
                day = b64((re.search(r"ReqDate=([^&]+)", link) or [None, ""])[1])
                if not day or not re.match(r"^\d{4}-\d\d-\d\d$", day):
                    continue
                mins = _hhmm(h, m, ap)
                d = Date.fromisoformat(day) + timedelta(days=1 if mins < 3 * 60 else 0)
                out.append({"venue": _text(venue), "screen": _text(screen), "date": d.isoformat(),
                            "time": f"{mins // 60:02d}:{mins % 60:02d}", "book": f"{BASE}/{link}"})
    return out


def hall_of(screen: str) -> tuple[str, str]:
    """«Safeer Elite» (90.00, 2026-11-19) and «Safeer Prime» (52.50) are its premium halls; «Screen-N» the regular ones."""
    s = (screen or "").strip()
    if re.search(r"elite", s, re.I):
        return "VIP", "Safeer Elite"
    if re.search(r"prime", s, re.I):
        return "OTHER", "Safeer Prime"
    return "Standard", "Standard"


def prices_from_seats(page: str, hall: str | None = None) -> list[dict] | None:
    """The seat page's sections -> [{"seat", "aed"}]. A section with no name is the hall itself when it is the only
    one (a premium hall sells one class), else it is named by its rows."""
    sections = _SECTION.findall(page or "")
    out = []
    for name, aed, grid in sections:
        aed = float(aed)
        if aed <= 0:
            continue
        name = _text(name).title()
        if not name and len(sections) == 1 and hall and hall != "Standard":
            name = hall
        if not name:
            rows = sorted(set(re.findall(r"<div class=['\"]row-label['\"]>([A-Z]{1,2})</div>", grid)))
            name = f"Rows {rows[0]}–{rows[-1]}" if len(rows) > 1 else f"Row {rows[0]}" if rows else "Seats"
        out.append({"seat": name, "aed": round(aed, 2)})
    return sorted(out, key=lambda p: p["aed"]) or None


def cinema_of(venue: str) -> dict:
    cid, mall, address, city = KNOWN.get(venue.lower(), (f"{CHAIN}-{slug(re.sub(r'(?i)^safeer cinemas?\s*-\s*', '', venue))}",
                                                         re.sub(r"(?i)^safeer cinemas?\s*-\s*", "", venue), venue, None))
    if city not in CITIES:
        from readers.common import city_of
        city = city_of(address, venue)
    if city not in CITIES:
        raise ValueError(f"safeer: no city for {venue!r}")
    return {"id": cid, "chain": CHAIN, "name": f"Safeer Cinemas {mall}", "name_ar": None, "city": city, "mall": mall,
            "address": address, "maps": None, "lat": None, "lng": None}


def fetch(days: int = 2, cache: dict | None = None) -> dict:
    sess = Polite(gap=0.8)
    today = datetime.now(DUBAI_TZ).date()
    window = {(today + timedelta(days=i)).isoformat() for i in range(days)}
    r = sess.get(BASE + "/", timeout=TIMEOUT)
    r.raise_for_status()
    ids = list(dict.fromkeys(_FILM.findall(r.text)))
    if not ids:
        raise RuntimeError("safeer: the home page lists no showing films (markup changed?)")
    cinemas, shows, price, tries = {}, [], {}, {}
    health = {"attempted": 0, "priced": 0, "error": None}
    for mid in ids:
        dr = sess.get(f"{BASE}/MovieDetails.aspx", params={"movieid": mid, "schedulestatus": 1}, timeout=TIMEOUT)
        if dr.status_code != 200:
            continue
        d = details(dr.text)
        if not d["title"] or not d["showtimes"]:
            continue
        sr = sess.get(f"{BASE}/{d['showtimes']}", timeout=TIMEOUT)
        if sr.status_code != 200:
            continue
        title = f"{d['title']} (3D)" if d["fmt"] == "3D" and "3d" not in d["title"].lower() else d["title"]
        for s in shows_from_page(sr.text):
            if s["date"] not in window:
                continue
            cin = cinemas.get(s["venue"]) or cinemas.setdefault(s["venue"], cinema_of(s["venue"]))
            hall, label = hall_of(s["screen"])
            key = (cin["id"], s["screen"] or label, s["date"], _fmt3d(title))
            if key not in price:
                hit = cache_get(cache, key)
                if hit is not CACHE_MISS:
                    price[key], tries[key] = hit, 2
                    health["cached"] = health.get("cached", 0) + 1
            if price.get(key) is None and tries.get(key, 0) < 2:
                tries[key] = tries.get(key, 0) + 1
                try:
                    pr = sess.get(s["book"], timeout=TIMEOUT)
                    price[key] = prices_from_seats(pr.text, label) if pr.status_code == 200 else None
                except Exception:  # noqa: BLE001 - an unpriced screen, never a failed chain
                    price[key] = None
                health["attempted"] += 1
                cache_set(cache, key, price[key])
            show = {"cinema": cin["id"], "film_title": title, "film_lang": d["lang"], "film_rating": d["rating"],
                    "runtime": d["runtime"], "date": s["date"], "time": s["time"], "hall": hall, "hall_label": label,
                    "prices": key, "book": s["book"], "_screen": s["screen"] or None,
                    "film_poster": f"{BASE}/admin/MovieImages/Mobile/{mid}.jpg"}
            if d["trailer"]:
                show["film_trailer"] = d["trailer"]
            if d["genres"]:
                show["film_genres"] = d["genres"]
            if lang_key(d["lang"]):
                show["lang"] = lang_key(d["lang"])
            if subs_keys(d["subs"]):
                show["subs"] = subs_keys(d["subs"])
            shows.append(show)
    for sh in shows:
        sh["prices"] = price.get(sh["prices"])
    if not shows:
        raise RuntimeError("safeer: zero shows in the window — the show-time pages changed or are blocked")
    health["priced"] = sum(1 for v in price.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} seat-page samples priced"
    return {"cinemas": list(cinemas.values()), "shows": shows, "price_health": health}


if __name__ == "__main__":
    import sys

    json.dump(fetch(days=2), sys.stdout, ensure_ascii=False, indent=2)
