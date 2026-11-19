"""Reader for Galaxy Cinemas (galaxycinemas.ae) — one site, Fujairah Mall (owner 2026-11-19; found on cinemauae.com as
«Fujairah Mall Cinema»).

ASP.NET WebForms, no login, no bot check:
  GET /                         films as Movie_details.aspx?pid=<base64>-<signature>&mode=NowShowing (ComingSoon skipped)
  GET Movie_details.aspx?…      <h1>TITLE</h1>, Genre, Run time (minutes), Rating «PG-13», Language, the trailer (a YouTube
                                embed in TrailerLink(…)), the poster, and per day its times, each a link
                                SeatLayout.aspx?cid=…&scheid=…&pid=…&date=<ms>&time=<ms>&levelid=1 — `time` is the Dubai wall
                                clock written as India time (1795079400000 at +05:30 = 2026-11-19 14:40, the button's «02:40:PM»),
                                so read at +05:30 it gives the exact calendar date of an after-midnight show
Prices, nothing held: the SeatLayout link (also the booking link) lists its classes as <p id='ticdescN'>VIP</p> and
<p id='pTicAmtN'>AED 42</p>. One sample per date x 2D/3D (the film page names no screen).
"""
from __future__ import annotations

import html as htmllib
import json
import re
from datetime import datetime, timedelta, timezone

from readers.common import CACHE_MISS, Polite, cache_get, cache_set, lang_key, youtube_id, fmt3d as _fmt3d

CHAIN = "galaxy"
BASE = "https://www.galaxycinemas.ae"
DUBAI_TZ = timezone(timedelta(hours=4))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
CINEMA = {"id": "galaxy-fujairah-mall", "chain": CHAIN, "name": "Galaxy Cinemas Fujairah Mall", "name_ar": None,
          "city": "fujairah", "mall": "Fujairah Mall", "address": "Fujairah Mall, Hamad Bin Abdullah Rd, Fujairah, United Arab Emirates",
          "maps": None, "lat": None, "lng": None}
_FILM = re.compile(r"(Movie_details\.aspx\?pid=[^'\" >&]+)&(?:amp;)?mode=NowShowing")
_SEAT = re.compile(r"<a href='(SeatLayout\.aspx\?[^']+)'>\s*(\d{1,2}):(\d\d):?\s*([AP]M)\s*</a>", re.I)


def _text(s) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def nice_title(t: str) -> str:
    core = re.sub(r"\([^)]*\)", "", t)
    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", lambda m: m.group(0).capitalize(), t) if core.isupper() else t


def film_page(page: str) -> dict:
    get = lambda label: _text((re.search(rf"<span>\s*{label}:\s*</span>(.*?)</p>", page, re.S) or [None, ""])[1])
    h1 = re.search(r"<h1>(.*?)</h1>", page, re.S)
    rt = re.search(r"\d+", get("Run time"))
    trailer = re.search(r"TrailerLink\(\"([^\"]+)\"\)", page)
    poster = re.search(r"<div class='movieimage'><img src='([^']+)'", page)
    shows = []
    for link, h, m, ap in _SEAT.findall(page):
        link = htmllib.unescape(link)
        t = re.search(r"[&?]time=(\d{12,14})", link)
        if not t:
            continue
        # the site writes the Dubai wall clock as if it were India time: «02:40:PM» carries 1795079400000 = 09:10Z,
        # which is 14:40 at +05:30 (13:10 read at Dubai's +04:00). The button's own label is the check.
        when = datetime.fromtimestamp(int(t.group(1)) / 1000, IST_TZ)
        label = f"{int(h) % 12 + (12 if ap.upper() == 'PM' else 0):02d}:{m}"
        if when.strftime("%H:%M") != label:
            continue
        shows.append({"date": when.date().isoformat(), "time": label, "book": f"{BASE}/{link}"})
    return {"title": nice_title(_text(h1.group(1))) if h1 else None, "genres": [g.strip() for g in get("Genre").split(",") if g.strip()],
            "runtime": int(rt.group(0)) if rt else None,
            "rating": (lambda v: None if v.upper() in ("", "TBA", "TBC", "NA") else v)(get("Rating").replace("-", "").replace(" ", "")),
            "lang": get("Language") or None, "trailer": youtube_id(trailer.group(1)) if trailer else None,
            "poster": poster.group(1) if poster and poster.group(1).startswith("http") else None, "shows": shows}


def prices_from_seat_page(page: str) -> list[dict] | None:
    out: dict[str, float] = {}
    for n, name in re.findall(r"<p id='ticdesc(\d+)'>(.*?)</p>", page or "", re.S):
        amt = re.search(rf"<p id='pTicAmt{n}'>\s*AED\s*([\d.]+)\s*</p>", page)
        name = _text(name)
        name = name.upper() if len(name) <= 3 else name.title()
        if amt and name and float(amt.group(1)) > 0:
            out[name] = min(float(amt.group(1)), out.get(name, 1e9))
    return [{"seat": k, "aed": round(v, 2)} for k, v in sorted(out.items(), key=lambda kv: kv[1])] or None


def fetch(days: int = 2, cache: dict | None = None) -> dict:
    sess = Polite(gap=0.8)
    today = datetime.now(DUBAI_TZ).date()
    window = {(today + timedelta(days=i)).isoformat() for i in range(days)}
    r = sess.get(BASE + "/", timeout=60)
    r.raise_for_status()
    links = list(dict.fromkeys(htmllib.unescape(x) for x in _FILM.findall(r.text)))
    if not links:
        raise RuntimeError("galaxy: the home page lists no showing films (markup changed?)")
    shows, price, tries = [], {}, {}
    health = {"attempted": 0, "priced": 0, "error": None}
    for link in links:
        fr = sess.get(f"{BASE}/{link}&mode=NowShowing", timeout=60)
        if fr.status_code != 200:
            continue
        fp = film_page(fr.text)
        if not fp["title"]:
            continue
        title = fp["title"]
        for s in fp["shows"]:
            if s["date"] not in window:
                continue
            key = (CINEMA["id"], "Standard", s["date"], _fmt3d(title))
            if key not in price:
                hit = cache_get(cache, key)
                if hit is not CACHE_MISS:
                    price[key], tries[key] = hit, 2
                    health["cached"] = health.get("cached", 0) + 1
            if price.get(key) is None and tries.get(key, 0) < 2:
                tries[key] = tries.get(key, 0) + 1
                try:
                    pr = sess.get(s["book"], timeout=60)
                    price[key] = prices_from_seat_page(pr.text) if pr.status_code == 200 else None
                except Exception:  # noqa: BLE001 - an unpriced day, never a failed chain
                    price[key] = None
                health["attempted"] += 1
                cache_set(cache, key, price[key])
            show = {"cinema": CINEMA["id"], "film_title": title, "film_lang": fp["lang"], "film_rating": fp["rating"],
                    "runtime": fp["runtime"], "date": s["date"], "time": s["time"], "hall": "Standard", "hall_label": "Standard",
                    "prices": key, "book": s["book"]}
            if fp["poster"]:
                show["film_poster"] = fp["poster"]
            if fp["trailer"]:
                show["film_trailer"] = fp["trailer"]
            if fp["genres"]:
                show["film_genres"] = fp["genres"]
            if lang_key(fp["lang"]):
                show["lang"] = lang_key(fp["lang"])
            shows.append(show)
    for sh in shows:
        sh["prices"] = price.get(sh["prices"])
    if not shows:
        raise RuntimeError("galaxy: zero shows in the window — the film pages changed or are blocked")
    health["priced"] = sum(1 for v in price.values() if v)
    if health["attempted"] and not health["priced"]:
        health["error"] = f"0/{health['attempted']} seat-page samples priced"
    return {"cinemas": [dict(CINEMA)], "shows": shows, "price_health": health}


if __name__ == "__main__":
    import sys

    json.dump(fetch(days=2), sys.stdout, ensure_ascii=False, indent=2)
