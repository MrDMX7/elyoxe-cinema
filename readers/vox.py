"""VOX Cinemas UAE reader.

fetch(days=2) -> {"cinemas": [Cinema], "shows": [Show]}  (shapes: readers/common.py docstring)

Endpoints (see docs/probe/vox.md for the full probe):
  - GET https://uae.voxcinemas.com/cinemas                    -> list of cinemas (slug, name, address)
  - GET https://uae.voxcinemas.com/showtimes/<slug>?d=YYYYMMDD -> that cinema's showtimes for one day,
    server-rendered HTML (no separate JSON XHR to call instead).

Akamai Bot Manager blocks plain `requests`/`curl` from this machine at the TLS-fingerprint level
(connection just hangs until timeout, no HTTP response at all). `curl_cffi` with
`impersonate="chrome"` matches Chrome's TLS fingerprint and gets a normal 200, so this reader uses
that instead of readers.common.Polite (which wraps plain `requests` and would hang here). CITIES,
HALLS, slug() and city_of() are still reused from readers.common.

Prices (live, no seat hold): the seat-map page the guest flow opens *before* any seat is clicked
already carries every seat class with its price in the legend markup:
  <li class="seat standard ..." data-area="0000000002" data-label="Regular" data-price="50.00 AED per ticket">
The reader walks the site's own guest path once per cinema x hall per run --
  GET /booking/<session>  (opens an anonymous guest order, as "Continue as Guest" does)
  GET /booking/<order>/seats/fetch -> GET /booking/<order>/seats   (read the legend)
  GET /booking/<order>/abandon?success_url=/showtimes               (the page's own "back" link)
-- and never POSTs the page's `/allocate` form, so no seat is ever selected or held. Any failure
leaves that hall's prices None; a 403/429 there stops price sampling for the rest of the run.
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from curl_cffi import requests as cr

from readers.common import CITIES, HALLS, city_of, lang_key, slug as _slug, subs_keys, youtube_id, fmt3d as _fmt3d

BASE = "https://uae.voxcinemas.com"
UA_IMPERSONATE = "chrome"
GAP = 1.1  # seconds between requests, stays under ~1 req/s
DUBAI = ZoneInfo("Asia/Dubai")
_PRICE_RE = re.compile(r"([\d.]+)\s*AED")

# Cinemas whose name/address don't carry a recognisable city word for common.city_of()
# (truncated addresses on VOX's own site, or malls named without their city).
MANUAL_CITY = {
    "burjuman": "dubai",
    "city-centre-meaisem": "dubai",
    "city-centre-shindagha": "dubai",
    "kempinski-mall-of-emirates": "dubai",
    "megaplex-cineplex-grand-hyatt": "dubai",
    "mall-of-the-emirates": "dubai",
}

# VOX "experience" labels seen in showtime pages -> our HALLS enum (exact match, case-insensitive).
# Anything not listed here (e.g. "THEATRE PODS in IMAX", "Couch - 2 Seater") -> OTHER, raw text kept
# in hall_label.
HALL_MAP = {
    "standard": "Standard",
    "max": "MAX",
    "imax": "IMAX",
    "4dx": "4DX",
    "gold": "GOLD",
    "theatre": "THEATRE",
    "kids": "KIDS",
    "screenx": "SCREENX",
    "vip": "VIP",
    "suites": "SUITES",
}

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap]m)", re.I)


class _Client:
    """Minimal polite wrapper around curl_cffi (Polite in common.py uses plain requests, which
    Akamai blocks here — see module docstring)."""

    def __init__(self, gap: float = GAP):
        self.s = cr.Session()
        self.gap = gap
        self._last = 0.0

    def get(self, url: str, **kw):
        wait = self.gap - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self._last = time.monotonic()
            try:
                r = self.s.get(url, impersonate=UA_IMPERSONATE, timeout=30, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                return r
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))


def _hall_of(raw: str) -> tuple[str, str]:
    key = raw.strip().lower()
    return HALL_MAP.get(key, "OTHER"), raw.strip()


def _to_24h(raw: str) -> str | None:
    m = _TIME_RE.search(raw)
    if not m:
        return None
    h, mnt, ap = int(m.group(1)), m.group(2), m.group(3).lower()
    if ap == "am":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return f"{h:02d}:{mnt}"


def _fetch_cinema_list(client: _Client) -> list[dict]:
    r = client.get(f"{BASE}/cinemas")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    for art in soup.select("article.cinema-summary"):
        cslug = art.get("data-slug") or ""
        h3 = art.select_one("h3 a")
        name = h3.get_text(strip=True) if h3 else cslug
        addr_p = art.select_one("p")
        address = ""
        if addr_p:
            address = addr_p.get_text(" ", strip=True).replace("Address:", "").strip()
        has_showtimes = art.select_one('a[href^="/showtimes/"]') is not None
        if not cslug or not has_showtimes:
            continue  # e.g. galleria-mall-dubai-moonlight, sharjah-safari: no bookable schedule
        out.append({"slug": cslug, "name": name, "address": address})
    return out


def _parse_showtimes(html: str, cinema_name: str, date_str: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    shows = []
    for art in soup.select("article.movie-compare"):
        movie_slug = art.get("data-slug") or ""
        h2 = art.select_one("aside.movie-hero h2")
        film_title = h2.get_text(strip=True) if h2 else None
        if not film_title:
            continue
        cls = art.select_one("aside.movie-hero span.classification")
        film_rating = cls.get_text(strip=True) if cls else None
        tags = art.select("aside.movie-hero span.tag")
        film_lang, runtime = None, None
        for tag in tags:
            t = tag.get_text(strip=True)
            m = re.match(r"(\d+)\s*min", t, re.I)
            if m:
                runtime = int(m.group(1))
            elif t:
                film_lang = film_lang or t
        for dates_div in art.select("div.dates"):
            for hall_li in dates_div.select("ol.showtimes > li"):
                strong = hall_li.select_one("strong")
                # only the strong's own text: its info-icon <a> / tooltip <div> children are UI copy
                raw_hall = ""
                if strong:
                    raw_hall = " ".join(t.strip() for t in strong.find_all(string=True, recursive=False)
                                        if t.strip())
                raw_hall = raw_hall or "Standard"
                hall, hall_label = _hall_of(raw_hall)
                for a in hall_li.select("ol > li > a.showtime"):
                    time_24 = _to_24h(a.get_text())
                    href = a.get("href") or ""
                    if not time_24 or not href:
                        continue
                    if href.startswith("/"):
                        href = BASE + href
                    shows.append({
                        "film_title": film_title,
                        "film_lang": film_lang,
                        "film_rating": film_rating,
                        "runtime": runtime,
                        "date": date_str,
                        "time": time_24,
                        "hall": hall,
                        "hall_label": hall_label,
                        "prices": None,
                        "book": href,
                        "_movie": movie_slug,
                    })
    return shows


def movie_extras(html: str) -> dict:
    """What a VOX film page (/movies/<slug>) states about the film: the portrait poster
    (img.poster, 480x686 — the showtimes page only has a 940x328 hero), the YouTube trailer it
    embeds, and its aside facts: Genre, Language, Subtitle(s). Only what is there."""
    soup = BeautifulSoup(html, "lxml")
    out: dict = {}
    img = soup.select_one("img.poster")
    if img and (img.get("src") or "").startswith("http"):
        out["film_poster"] = img["src"]
    for iframe in soup.select("div.trailer iframe, iframe"):
        yt = youtube_id(iframe.get("src") or "")
        if yt:
            out["film_trailer"] = yt
            break
    facts = {}
    for p in soup.select("aside p"):
        strong = p.select_one("strong")
        if not strong:
            continue
        label = strong.get_text(strip=True).rstrip(":").strip().lower()
        facts[label] = p.get_text(" ", strip=True)[len(strong.get_text(strip=True)):].strip()
    genres = [g.strip() for g in (facts.get("genre") or "").split(",") if g.strip()]
    if genres:
        out["film_genres"] = genres
    lang = lang_key(facts.get("language"))
    if lang:
        out["lang"] = lang
    subs = subs_keys(facts.get("subtitle(s)") or facts.get("subtitles"))
    if subs:
        out["subs"] = subs
    return out


def _legend_prices(html: str) -> list[dict] | None:
    """Seat classes + prices from the seat-map legend (the li elements that carry data-price)."""
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, float] = {}
    for li in soup.select("li.seat[data-price]"):
        label = (li.get("data-label") or "").strip()
        m = _PRICE_RE.search(li.get("data-price") or "")
        if label and m and float(m.group(1)) > 0 and label not in out:
            out[label] = float(m.group(1))
    return [{"seat": k, "aed": v} for k, v in out.items()] or None


class _Blocked(Exception):
    pass


def _sample_prices(client: _Client, book_url: str) -> list[dict] | None:
    """One read of the pre-selection seat map for this session, then abandon the empty order."""
    r = client.get(book_url)
    if r is None or r.status_code in (403, 429):
        raise _Blocked(f"{book_url}: {getattr(r, 'status_code', None)}")
    m = re.search(r"/booking/([^/?#]+_[^/?#]+)/", str(r.url))
    if r.status_code != 200 or not m:
        return None
    order = m.group(1)
    try:
        prices = None
        f = client.get(f"{BASE}/booking/{order}/seats/fetch")
        if f is not None and f.status_code in (403, 429):
            raise _Blocked(f"seats/fetch: {f.status_code}")
        for attempt in range(3):
            p = client.get(f"{BASE}/booking/{order}/seats")
            if p is None:
                break
            if p.status_code in (403, 429):
                raise _Blocked(f"seats: {p.status_code}")
            if p.status_code == 200 and str(p.url).rstrip("/").endswith("/seats"):
                prices = _legend_prices(p.text)
                break
            time.sleep(2 * (attempt + 1))  # still on /seats/processing
        return prices
    finally:
        try:  # the seat page's own "back to showtimes" link -- releases the empty guest order
            client.get(f"{BASE}/booking/{order}/abandon?success_url=%2Fshowtimes", allow_redirects=False)
        except Exception:
            pass


def fetch(days: int = 2, prices: bool = True) -> dict:
    client = _Client()
    cinemas_raw = _fetch_cinema_list(client)

    cinemas, shows = [], []
    now = datetime.now(DUBAI)
    today = now.date()
    calls = failed = 0

    for c in cinemas_raw:
        cslug = c["slug"]
        cid = f"vox-{cslug}"
        name = c["name"]
        address = c["address"]
        city = MANUAL_CITY.get(cslug) or city_of(name, address)
        if city not in CITIES:
            # Should not happen for a real UAE VOX cinema; fail loudly rather than ship a bad row.
            raise ValueError(f"vox: could not determine city for cinema '{name}' ({cslug!r}, addr={address!r})")

        cinemas.append({
            "id": cid,
            "chain": "vox",
            "name": f"VOX Cinemas {name}",
            "name_ar": None,
            "city": city,
            "mall": name,
            "address": address,
            "maps": None,
            "lat": None,
            "lng": None,
        })

        for offset in range(days):
            d = today + timedelta(days=offset)
            d_str = d.strftime("%Y%m%d")
            date_str = d.strftime("%Y-%m-%d")
            calls += 1
            r = client.get(f"{BASE}/showtimes/{cslug}?d={d_str}")
            if r is None or r.status_code != 200:
                failed += 1
                continue
            for show in _parse_showtimes(r.text, name, date_str):
                show["cinema"] = cid
                shows.append(show)

    if calls and failed * 2 > calls:
        raise RuntimeError(f"vox: {failed}/{calls} showtime pages failed -- Akamai block or site change")

    # one film page per film: poster, trailer, genres, language + subtitles (never fails the chain)
    extras: dict[str, dict] = {}
    for movie_slug in sorted({sh.get("_movie") for sh in shows if sh.get("_movie")}):
        try:
            r = client.get(f"{BASE}/movies/{movie_slug}")
            extras[movie_slug] = movie_extras(r.text) if r is not None and r.status_code == 200 else {}
        except Exception:
            extras[movie_slug] = {}
    for sh in shows:
        sh.update(extras.get(sh.pop("_movie", None) or "", {}))
    if not shows:
        raise RuntimeError("vox: zero shows parsed -- showtime markup changed")

    # prices: one legend read per cinema x hall_label x show date (weekday/weekend prices differ; a
    # 3D title is its own key), on a session at least an hour away
    def pkey(sh):
        return (sh["cinema"], sh["hall_label"], sh["date"], _fmt3d(sh.get("film_title")))
    price_of: dict[tuple, list[dict] | None] = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    if prices:
        tries: dict[tuple, int] = {}
        for sh in sorted(shows, key=lambda x: (x["date"], x["time"])):
            key = pkey(sh)
            if price_of.get(key) or tries.get(key, 0) >= 2:
                continue
            start = datetime.strptime(f"{sh['date']} {sh['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=DUBAI)
            if start < now + timedelta(hours=1):
                continue
            tries[key] = tries.get(key, 0) + 1
            health["attempted"] += 1
            try:
                price_of[key] = _sample_prices(client, sh["book"])
            except _Blocked as e:
                health["error"] = f"price sampling stopped on a block: {e}"
                print(f"[readers.vox] {health['error']}", file=sys.stderr)
                break
            except Exception:
                price_of[key] = None
    for sh in shows:
        sh["prices"] = price_of.get(pkey(sh))
    health["priced"] = sum(1 for v in price_of.values() if v)
    if health["attempted"] and not health["priced"] and not health["error"]:
        health["error"] = f"0/{health['attempted']} seat-map legend samples priced"
    return {"cinemas": cinemas, "shows": shows, "price_health": health}


if __name__ == "__main__":
    import json
    import sys

    result = fetch(days=int(sys.argv[1]) if len(sys.argv) > 1 else 2)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
