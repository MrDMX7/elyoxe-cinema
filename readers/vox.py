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

Prices: VOX never shows a per-seat-class price until a seat is clicked in the seat map, and clicking
a seat holds it. The task's binding rule forbids reading a price that way, so this reader always sets
"prices": None for VOX and records the finding in docs/probe/vox.md instead of guessing.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup
from curl_cffi import requests as cr

from readers.common import CITIES, HALLS, city_of, slug as _slug

BASE = "https://uae.voxcinemas.com"
UA_IMPERSONATE = "chrome"
GAP = 1.1  # seconds between requests, stays under ~1 req/s

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

    def get(self, url: str):
        wait = self.gap - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self._last = time.monotonic()
            try:
                r = self.s.get(url, impersonate=UA_IMPERSONATE, timeout=30)
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
                raw_hall = strong.get_text(strip=True) if strong else "Standard"
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
                    })
    return shows


def fetch(days: int = 2) -> dict:
    client = _Client()
    cinemas_raw = _fetch_cinema_list(client)

    cinemas, shows = [], []
    today = date.today()

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
            r = client.get(f"{BASE}/showtimes/{cslug}?d={d_str}")
            if r.status_code != 200:
                continue
            for show in _parse_showtimes(r.text, name, date_str):
                show["cinema"] = cid
                shows.append(show)

    return {"cinemas": cinemas, "shows": shows}


if __name__ == "__main__":
    import json
    import sys

    result = fetch(days=int(sys.argv[1]) if len(sys.argv) > 1 else 2)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
