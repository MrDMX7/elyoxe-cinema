"""Reader for 369 Cinemas (369cinemas.ae, managed by Truth Cinemas) — one site, Al Mariah Mall, Abu Dhabi, 9 screens
(owner 2026-11-19). Chain id «cinemas369»: a CSS class (.ch-<chain>) cannot start with a digit.

Server-rendered PHP, no login (a PHP session cookie, a fresh one works):
  GET /                       redirects to /indexdesk; every film as https://369cinemas.ae/movie/<slug>, its language and
                              certificate in the hero's movie-info-list
  GET /movie/<slug>           the title (h1), genre and «02h 00m»; one tab per day (#nav-YYYY-MM-DD-N), each time a button
                              handleRedirection('https://369cinemas.ae/desktop-seat/<hash>%26shid%3D…%26timstr%3D2026-11-19+11%3A00%3A00
                              %26dimen%3D…') — that URL is the booking link, timstr the show's own date and time
  GET <a desktop-seat URL>    every time of that film that day with its screen: data-id (shid) data-scid data-scname
                              «Cinema-2» data-exp «2K 7.1»
Prices, read-only (the call the seat page makes on opening): POST /ajax/dynamic-ajax.php action=loadSeats&scid&shid ->
{"class": {"4": {"name": "STANDARD", "rate": 36.75, "tdamt": 0, "resamt": 0}, …}}; price = rate + tdamt + resamt.
Never call book-ajax.php (seat hold/release) or customer-ajax.php (login). One sample per screen x date x 2D/3D.
"""
from __future__ import annotations

import html as htmllib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from readers.common import CACHE_MISS, Polite, cache_get, cache_set, lang_key, slug, fmt3d as _fmt3d

CHAIN = "cinemas369"
BASE = "https://369cinemas.ae"
DUBAI_TZ = timezone(timedelta(hours=4))
CINEMA = {"id": "cinemas369-al-mariah-mall", "chain": CHAIN, "name": "369 Cinemas Al Mariah Mall", "name_ar": None,
          "city": "abu-dhabi", "mall": "Al Mariah Mall", "address": "Al Mariah Mall, 1st floor, Al Danah, Abu Dhabi, United Arab Emirates",
          "maps": None, "lat": None, "lng": None}
_FILM = re.compile(r'href="(https://369cinemas\.ae/movie/[^"#?]+)"')
_SEAT = re.compile(r"handleRedirection\('(https://369cinemas\.ae/desktop-seat/[^']+)'\)")
_BTN = re.compile(r"<button[^>]*handleRedirection\('(https://369cinemas\.ae/desktop-seat/[^']+)'\)[^>]*>", re.S)
_ATTR = re.compile(r'data-(id|scid|scname|exp)="([^"]*)"')


def _text(s) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def films_from_home(page: str) -> dict[str, dict]:
    """url -> {lang, rating} from the home page's hero items (each item's info list sits just before its link)."""
    out: dict[str, dict] = {}
    for m in _FILM.finditer(page):
        url = m.group(1)
        if url in out:
            continue
        before = page[max(0, m.start() - 4000):m.start()]
        # the item's own <ul class="movie-info-list …"> (its <li>s carry «movie-info-list--item», so split on the <ul>)
        items = re.findall(r'<li class="movie-info-list--item">(.*?)</li>', before.rsplit('<ul class="movie-info-list', 1)[-1] if '<ul class="movie-info-list' in before else "", re.S)
        vals = [_text(x) for x in items if _text(x)]
        lang = next((v for v in vals if lang_key(v)), None)
        rating = next((v.replace(" ", "") for v in vals if re.match(r"^(G|PG|PG\s?1[358]|1[358]\+|18TC|TBC|\d{2}\+)$", v.replace(" ", ""), re.I)), None)
        out[url] = {"lang": lang, "rating": rating}
    return out


def seat_link(url: str) -> dict:
    """A desktop-seat URL's own fields: shid, date, time, dim (its query is URL-encoded inside the path)."""
    q = unquote(url.replace("+", " "))
    get = lambda k: (re.search(rf"[&?]{k}=([^&]*)", q) or [None, ""])[1]
    ts = get("timstr")
    m = re.match(r"(\d{4}-\d\d-\d\d) (\d\d):(\d\d)", ts)
    return {"shid": get("shid"), "date": m.group(1) if m else None, "time": f"{m.group(2)}:{m.group(3)}" if m else None,
            "dim": (get("dimen") or "").upper() or None}


def film_page(page: str) -> dict:
    title = re.search(r'<h1 class="banner-title[^"]*"[^>]*>(.*?)</h1>', page, re.S)
    rt = re.search(r"(\d{1,2})h\s*(\d{1,2})m", page)
    subs = re.search(r"<b>\s*Subtitles\s*:\s*</b>([^<]*)", page)
    poster = re.search(r'<img[^>]+src="(https://369cinemas\.ae/uploads/[^"]+)"', page)
    return {"title": _text(title.group(1)) if title else None,
            "runtime": int(rt.group(1)) * 60 + int(rt.group(2)) if rt else None,
            "subs": subs.group(1).strip() if subs else None,
            "poster": poster.group(1) if poster else None,
            "links": list(dict.fromkeys(_SEAT.findall(page)))}


def screens_from_seat_page(page: str) -> dict[str, dict]:
    """shid -> {scid, scname, exp} for every time listed on a desktop-seat page."""
    out = {}
    for btn in _BTN.finditer(page):
        a = dict(_ATTR.findall(btn.group(0)))
        if a.get("id"):
            out[a["id"]] = {"scid": a.get("scid"), "scname": a.get("scname") or "", "exp": a.get("exp") or ""}
    return out


def prices_from_classes(payload: dict) -> list[dict] | None:
    cls = (payload or {}).get("class") or {}
    out: dict[str, float] = {}
    for c in cls.values():
        name = (c.get("name") or "").strip()
        name = name.upper() if len(name) <= 3 else name.title()      # «VIP» stays VIP, «PRIME VIEW» -> «Prime View»
        aed = round(float(c.get("rate") or 0) + float(c.get("tdamt") or 0) + float(c.get("resamt") or 0), 2)
        if name and aed > 0:
            out[name] = min(aed, out.get(name, aed))
    return [{"seat": k, "aed": v} for k, v in sorted(out.items(), key=lambda kv: kv[1])] or None


def hall_of(scname: str, exp: str, title: str) -> tuple[str, str]:
    if re.search(r"infinity", f"{scname} {exp} {title}", re.I):
        return "OTHER", "Infinity Vision"
    return "Standard", "Standard"


def clean_title(t: str) -> str:
    """«AVENGERS DOOMSDAY - INFINITY VISION» -> «Avengers Doomsday»; the site's capitals in title case."""
    t = re.sub(r"\s*-+\s*infinity\s+vision\s*$", "", _text(t), flags=re.I)
    core = re.sub(r"\([^)]*\)", "", t)          # «RAMAYANA: RISE OF A LEGEND (Malayalam)»: capitals outside the brackets
    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", lambda m: m.group(0).capitalize(), t) if core.isupper() else t


def fetch(days: int = 2, cache: dict | None = None) -> dict:
    sess = Polite(gap=0.8)
    today = datetime.now(DUBAI_TZ).date()
    window = {(today + timedelta(days=i)).isoformat() for i in range(days)}
    r = sess.get(BASE + "/")
    r.raise_for_status()
    films = films_from_home(r.text)
    if not films:
        raise RuntimeError("cinemas369: the home page lists no films (markup changed?)")
    shows, price, tries = [], {}, {}
    health = {"attempted": 0, "priced": 0, "error": None}
    for url, meta in films.items():
        fp_r = sess.get(url)
        if fp_r.status_code != 200:
            continue
        fp = film_page(fp_r.text)
        raw_title = fp["title"] or ""
        title = clean_title(raw_title)
        if not title:
            continue
        if not meta.get("lang"):   # not in the home page's hero: the title's own «(Malayalam)», when it has one
            p = re.search(r"\(([^)]+)\)\s*$", raw_title)
            meta = dict(meta, lang=p.group(1).strip().title() if p and lang_key(p.group(1)) else None)
        links = [(u, seat_link(u)) for u in fp["links"]]
        links = [(u, s) for u, s in links if s["date"] in window and s["shid"]]
        screens: dict[str, dict] = {}
        for day in sorted({s["date"] for _, s in links}):
            first = next(u for u, s in links if s["date"] == day)
            sp = sess.get(first)
            if sp.status_code == 200:
                screens.update(screens_from_seat_page(sp.text))
        for u, s in links:
            sc = screens.get(s["shid"], {})
            hall, label = hall_of(sc.get("scname", ""), sc.get("exp", ""), raw_title)
            t = f"{title} (3D)" if s["dim"] == "3D" and "3d" not in title.lower() else title
            key = (CINEMA["id"], sc.get("scname") or label, s["date"], _fmt3d(t))
            if key not in price:
                hit = cache_get(cache, key)
                if hit is not CACHE_MISS:
                    price[key], tries[key] = hit, 2
                    health["cached"] = health.get("cached", 0) + 1
            if price.get(key) is None and tries.get(key, 0) < 2 and sc.get("scid"):
                tries[key] = tries.get(key, 0) + 1
                try:
                    pr = sess.post(f"{BASE}/ajax/dynamic-ajax.php", data={"action": "loadSeats", "scid": sc["scid"], "shid": s["shid"]},
                                   headers={"X-Requested-With": "XMLHttpRequest", "Referer": u})
                    price[key] = prices_from_classes(pr.json()) if pr.status_code == 200 else None
                except Exception:  # noqa: BLE001 - an unpriced screen, never a failed chain
                    price[key] = None
                health["attempted"] += 1
                cache_set(cache, key, price[key])
            show = {"cinema": CINEMA["id"], "film_title": t, "film_lang": meta.get("lang"), "film_rating": meta.get("rating"),
                    "runtime": fp["runtime"], "date": s["date"], "time": s["time"], "hall": hall, "hall_label": label,
                    "prices": key, "book": u, "_screen": sc.get("scname") or None}
            if fp["poster"]:
                show["film_poster"] = fp["poster"]
            if lang_key(meta.get("lang")):
                show["lang"] = lang_key(meta.get("lang"))
            shows.append(show)
    for sh in shows:
        sh["prices"] = price.get(sh["prices"])
    if not shows:
        raise RuntimeError("cinemas369: zero shows in the window — the film pages changed or are blocked")
    health["priced"] = sum(1 for v in price.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} loadSeats samples priced"
    return {"cinemas": [dict(CINEMA)], "shows": shows, "price_health": health}


if __name__ == "__main__":
    import sys

    json.dump(fetch(days=2), sys.stdout, ensure_ascii=False, indent=2)
