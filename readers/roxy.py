"""Roxy Cinemas UAE reader.

Roxy runs on a custom Drupal 9/10 site (theroxycinemas.com). There is no
documented JSON API — showtimes are fetched by the page's own jQuery via a
Drupal AJAX endpoint that returns a JSON envelope wrapping a server-rendered
HTML fragment:

    GET /en/movie-schedule/ajax?nid=<movie-node-id>&promotion=
    -> {"status": "success", "html": "<div id=\"movie-schedule-block\">...</div>"}

The HTML fragment embeds one <input type="radio"> per session with all the
fields we need as plain attributes: cinema-name, cinema-id, screen, nid,
date, time, session. A single call returns *all* upcoming dates (today
through +5 days) for that movie across *all* six cinemas, so fetch() makes
one polite request per now-showing movie, not one per cinema x day.

Akamai blocks plain `requests`/stdlib TLS from this machine (same as VOX —
see readers/vox.py): a direct `requests.get()` against theroxycinemas.com
returns HTTP 403 "Access Denied" even for the plain homepage, regardless of
headers. `curl_cffi` with `impersonate="chrome"` matches Chrome's TLS
fingerprint and gets a normal 200, so this reader uses that instead of
readers.common.Polite (which wraps plain `requests` and would 403 here).
CITIES, HALLS, slug() and city_of() are still reused from readers.common.

See docs/probe/roxy.md for the full probe notes, including why prices are
always None here (booking needs login -> seat hold).
"""
from __future__ import annotations

import datetime
import json
import re
import time
from typing import Any
from zoneinfo import ZoneInfo

from curl_cffi import requests as cr

from readers.common import CITIES, HALLS, city_of, lang_key, slug, subs_keys, youtube_id

BASE = "https://www.theroxycinemas.com"
UA_IMPERSONATE = "chrome"
GAP = 1.0  # seconds between requests, stays at ~1 req/s
DUBAI = ZoneInfo("Asia/Dubai")


def _today_dubai() -> datetime.date:
    return datetime.datetime.now(DUBAI).date()

# url-slug, site cinema-id, display name, google maps url (None if not found in probe)
CINEMAS = [
    ("dubai-hills", "0000000007", "Dubai Hills Mall", None),
    ("al-khawaneej", "0000000006", "Al Khawaneej",
     "https://www.google.com/maps/place/Roxy+Cinemas+-+Al+Khawaneej/data=!4m2!3m1!1s0x0:0x8dcac873f1ed19b4"),
    ("the-beach", "0000000002", "The Beach, JBR",
     "https://www.google.com/maps/place/Roxy+Cinemas+The+Beach+JBR/data=!4m2!3m1!1s0x0:0xb417c5d8985a6ba0"),
    ("citywalk", "0000000001", "City Walk",
     "https://www.google.com/maps/place/Roxy+Cinemas+City+Walk/data=!4m2!3m1!1s0x0:0xb896252cb929a92"),
    ("boxpark", "0000000003", "Boxpark",
     "https://www.google.com/maps/place/Roxy+Cinemas+-+Boxpark/data=!4m2!3m1!1s0x0:0x43e1b42f4ce3ea05"),
    ("circle-mall", "0000000009", "Circle Mall", None),
]

# Cinemas whose name/address don't carry a recognisable city word for common.city_of()
# (e.g. "Al Khawaneej" is a Dubai neighborhood but isn't in common.py's _CITY_WORDS list).
# Hand fallback here rather than editing common.py, which is shared across all chains.
MANUAL_CITY = {
    "al-khawaneej": "dubai",
}

# ROXY's own tier names -> the shared hall enum. MAX and GOLD are VOX's own brand names and
# are never used for another chain, even when that chain's format is similar: Xtreme (Roxy's
# giant laser-screen format) and Gold (Roxy's own premium tier) are "other chain's premium
# format" -> OTHER, with the raw Roxy label kept verbatim in hall_label (halls.yaml matches
# them by label, not by this enum code). Platinum is the ultra-premium recliner tier -> VIP
# per the brief's recliner/luxury-seat-tier rule. Silver is the base standard tier ->
# Standard. Bronze is a discount tier and 2L (couple/love-seat format) don't match a named
# bucket -> OTHER. "Private Screen" (a whole room hired privately) is closest to SUITES.
HALL_MAP = {
    "xtreme": "OTHER",
    "platinum": "VIP",
    "gold": "OTHER",
    "silver": "Standard",
    "bronze": "OTHER",
    "2l": "OTHER",
    "private screen": "SUITES",
}

MOVIE_LINK_RE = re.compile(r"/en/movie/([a-z0-9-]+)")
NID_RE = re.compile(r'data-history-node-id="(\d+)"')
SESSION_RE = re.compile(
    r'cinema-name="([^"]+)" cinema-id="([^"]+)" screen="([^"]+)" nid="(\d+)" '
    r'date="([^"]+)" time="([^"]+)" session="(\d+)"'
)
TITLE_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")
DURATION_RE = re.compile(r"(\d+)\s*Hour[s]?\s*(\d+)?\s*Minute[s]?")
LANG_RE = re.compile(r"Language:\s*([A-Za-z]+)")
RATING_RE = re.compile(r'id="movie-rating">([^<]+)<')

WEEKDAY_DATE_RE = re.compile(r"^([A-Za-z]{3}) (\d{1,2}) [A-Za-z]{3}$")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


class _Client:
    """Minimal polite wrapper around curl_cffi (Polite in common.py uses plain requests,
    which Akamai 403s here — see module docstring)."""

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


def _hall(label: str) -> str:
    return HALL_MAP.get(label.strip().lower(), "OTHER")


def _map_date(raw: str, today: datetime.date, time_hint: str | None = None) -> str | None:
    """'Sep 25 Fri' -> '2026-09-25'. Returns None if unparsable.

    Two corrections beyond a plain year-stamp:
    - Year is picked as whichever of `today.year`/`today.year + 1` lands the date closest to
      `today` (not blindly `today.year`), so a Dec 31 run asking about "Jan 01" doesn't map it
      to the year that just ended and filter it out as if it were a year-old show.
    - Roxy buckets a show under the *business day* it started on, not its calendar date: a
      session listed as "Sep 25 Fri" at "00:10" actually plays on the 26th. When `time_hint`
      (the raw "HH:MM" session time) has an hour before 04:00, one day is added.
    """
    m = WEEKDAY_DATE_RE.match(raw)
    if not m:
        return None
    mon, day = m.group(1), int(m.group(2))
    mnum = MONTHS.get(mon)
    if not mnum:
        return None

    best = None
    for candidate_year in (today.year - 1, today.year, today.year + 1):
        try:
            d = datetime.date(candidate_year, mnum, day)
        except ValueError:
            continue
        delta = abs((d - today).days)
        if best is None or delta < best[0]:
            best = (delta, d)
    if best is None:
        return None
    result = best[1]

    if time_hint:
        try:
            hour = int(time_hint.split(":", 1)[0])
        except (ValueError, IndexError):
            hour = None
        if hour is not None and hour < 4:
            result = result + datetime.timedelta(days=1)

    return result.isoformat()


def _cinemas() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Build the Cinema list and a site-cinema-id -> our-id lookup."""
    cinemas = []
    id_by_site_id = {}
    for url_slug, site_id, name, maps in CINEMAS:
        address = f"{name}, Dubai, UAE"
        cid = f"roxy-{slug(name)}"
        id_by_site_id[site_id] = cid
        city = MANUAL_CITY.get(url_slug) or city_of(address)
        if city not in CITIES:
            raise ValueError(f"roxy: could not determine city for cinema '{name}' ({url_slug!r})")
        cinemas.append({
            "id": cid,
            "chain": "roxy",
            "name": f"ROXY Cinemas {name}",
            "name_ar": None,
            "city": city,
            "mall": name,
            "address": address,
            "maps": maps,
            "lat": None,
            "lng": None,
        })
    return cinemas, id_by_site_id


def _now_showing_slugs(client: _Client) -> list[str]:
    r = client.get(f"{BASE}/en")
    r.raise_for_status()
    slugs = sorted(set(MOVIE_LINK_RE.findall(r.text)))
    if not slugs:
        raise RuntimeError("roxy: /en returned zero now-showing movie links (markup may have changed)")
    return slugs


_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_SUBS_RE = re.compile(r"Subtitles?:\s*([^<]+)<")
_TRAILER_RE = re.compile(r'trailer-btn[^>]*data-link="([^"]+)"|data-link="([^"]*youtu[^"]+)"')


def movie_extras(html: str) -> dict:
    """What a Roxy film page states: its schema.org Movie block (image = the portrait
    thumbnail, genre), the trailer button's YouTube link, Language and Subtitles."""
    cut = html.split("other-movies-sec")[0]
    out: dict = {}
    for m in _LD_RE.finditer(cut):
        try:
            ld = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(ld, dict) and ld.get("@type") == "Movie":
            if (ld.get("image") or "").startswith("http"):
                out["film_poster"] = ld["image"]
            genres = [g.strip() for g in str(ld.get("genre") or "").split(",") if g.strip()]
            if genres:
                out["film_genres"] = genres
            break
    t = _TRAILER_RE.search(cut)
    yt = youtube_id((t.group(1) or t.group(2)) if t else None)
    if yt:
        out["film_trailer"] = yt
    lm = LANG_RE.search(cut)
    lang = lang_key(lm.group(1)) if lm else None
    if lang:
        out["lang"] = lang
    sm = _SUBS_RE.search(cut)
    subs = subs_keys(sm.group(1).strip()) if sm else []
    if subs:
        out["subs"] = subs
    return out


def _movie_meta(client: _Client, movie_slug: str) -> tuple[str | None, dict[str, Any]]:
    """Return (nid, {title, runtime, lang, rating}) for one movie page."""
    r = client.get(f"{BASE}/en/movie/{movie_slug}")
    r.raise_for_status()
    html = r.text
    nid_m = NID_RE.search(html)
    nid = nid_m.group(1) if nid_m else None

    cut = html.split("other-movies-sec")[0]
    title_m = TITLE_RE.search(cut)
    dur_m = DURATION_RE.search(cut)
    lang_m = LANG_RE.search(cut)
    rating_m = RATING_RE.search(cut)

    runtime = None
    if dur_m:
        hours = int(dur_m.group(1) or 0)
        minutes = int(dur_m.group(2) or 0)
        runtime = hours * 60 + minutes

    meta = {
        "title": title_m.group(1).strip() if title_m else movie_slug,
        "runtime": runtime,
        "lang": lang_m.group(1) if lang_m else None,
        "rating": (rating_m.group(1).strip().replace(" ", "") if rating_m else None) or None,
        "extras": movie_extras(html),
    }
    return nid, meta


def _label_twin_sessions(shows: list[dict[str, Any]]) -> None:
    """Two screens can run the same film at the same time in the same hall class. Roxy's
    markup carries no screen name (only the class, e.g. "Silver", and a session id), so both
    rows are kept and their hall_label gets the session id to tell them apart. Pops `_session`."""
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for sh in shows:
        groups.setdefault((sh["cinema"], sh["film_title"], sh["date"], sh["time"], sh["hall_label"]), []).append(sh)
    for twins in groups.values():
        if len(twins) > 1:
            for sh in twins:
                sh["hall_label"] = f"{sh['hall_label']} (session {sh['_session']})"
    for sh in shows:
        sh.pop("_session", None)


def fetch(days: int = 2) -> dict[str, list[dict[str, Any]]]:
    """Fetch Roxy Cinemas UAE cinemas + showtimes for today + (days - 1) more days.

    Prices are always None: seeing a session's seat map/price requires logging in
    (the site shows "Please log in to continue" before any seat map or price), which
    is a seat-hold flow we're not allowed to trigger. See docs/probe/roxy.md.
    """
    client = _Client()
    cinemas, id_by_site_id = _cinemas()

    today = _today_dubai()
    want_dates = {(today + datetime.timedelta(days=i)).isoformat() for i in range(max(days, 1))}

    shows: list[dict[str, Any]] = []
    seen_slots: set[tuple[str, str, str, str]] = set()

    ajax_calls = 0
    ajax_failed = 0

    for movie_slug in _now_showing_slugs(client):
        nid, meta = _movie_meta(client, movie_slug)
        if not nid:
            continue

        ajax_calls += 1
        r = client.get(f"{BASE}/en/movie-schedule/ajax", params={"nid": nid, "promotion": ""})
        if r.status_code != 200:
            ajax_failed += 1
            continue
        try:
            payload = r.json()
        except ValueError:
            ajax_failed += 1
            continue
        html = payload.get("html", "")

        for m in SESSION_RE.finditer(html):
            _cinema_name, site_cinema_id, screen, _nid, raw_date, time_, session_id = m.groups()
            cid = id_by_site_id.get(site_cinema_id)
            if not cid:
                continue
            date = _map_date(raw_date, today, time_hint=time_)
            if date is None or date not in want_dates:
                continue

            key = (cid, screen, date, session_id)
            if key in seen_slots:
                continue
            seen_slots.add(key)

            shows.append({
                "_session": session_id,
                "cinema": cid,
                "film_title": meta["title"],
                "film_lang": meta["lang"],
                "film_rating": meta["rating"],
                "runtime": meta["runtime"],
                "date": date,
                "time": time_,
                "hall": _hall(screen),
                "hall_label": screen,
                "prices": None,
                "book": f"{BASE}/en/movie/{movie_slug}#movie-schedule-block",
                **meta.get("extras", {}),
            })

    if ajax_calls and ajax_failed / ajax_calls > 0.5:
        raise RuntimeError(
            f"roxy: {ajax_failed}/{ajax_calls} movie-schedule/ajax requests failed "
            "(non-200 or unparseable) — treating the run as broken rather than publishing a "
            "partial/empty result"
        )
    if not shows:
        raise RuntimeError("roxy: fetch produced zero shows")

    _label_twin_sessions(shows)
    # Roxy has no hold-free price source (seat map is login-gated): nothing attempted, no error.
    return {"cinemas": cinemas, "shows": shows,
            "price_health": {"attempted": 0, "priced": 0, "error": None}}


if __name__ == "__main__":
    import json
    import sys

    result = fetch(days=int(sys.argv[1]) if len(sys.argv) > 1 else 2)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
