"""coming.py — each chain's own "coming soon" feed, one function per chain, isolated.

Task 2 (docs/superpowers/specs/2026-09-27-phase2-design.md, A: «نازل الخميس»). Each
`fetch_<chain>()` hits that chain's own site/API (same hosts/tokens the readers already use —
imported read-only from readers/<chain>.py, never duplicated) and returns a list of dicts:

    {"title": str, "title_ar": str|None, "release_date": "YYYY-MM-DD"|None,
     "poster": url|None, "trailer": youtube-id|None, "genres": [str], "chain": <chain>}

`fetch_all()` calls every chain, catching each one's own exception so a single chain's page
format changing never loses the other six (steps/coming.py records the per-chain health).
Politeness matches the readers: at most one request every ~1s per chain, and this module makes
one to a handful of requests per chain per run (a single listing page/endpoint each) — nowhere
near the readers' per-showtime fan-out.

Chain notes (docs/probe/*.md has the readers' own probe notes; these hosts were confirmed live
2026-09-27, see .superpowers/sdd/2026-09-27-phase2/task-2-report.md):
  - novo: GET {API}/movies (readers/novo.py's own `API`) already returns every film, coming or
    not; `movie_is_coming_soon` is true even for now-showing films (the reader's own docstring
    warns about this) so the real signal is `coming_soon_order is not None`.
  - star: GET {BASE}/coming-soon-movies (readers/star.py's own `BASE` + public `TOKEN`) — a
    dedicated endpoint, no filtering needed.
  - vox: GET {BASE}/movies/comingsoon (readers/vox.py's own `BASE`) — a server-rendered listing
    page (Akamai blocks plain requests here exactly as the reader's docstring describes, so this
    uses the same curl_cffi impersonation).
  - reel: GET {API}/Films.json (readers/reel.py's own googleapis `BASE`) carries `IsComingSoon`
    and `IsScheduledAtCinema` on every film; a true "not yet playing" film has the first true and
    the second false (a re-release can have both true — that's "now showing", excluded).
  - roxy: GET /en (readers/roxy.py's own `BASE`) is server-rendered and includes a hidden
    "Coming Soon" accordion tab with the same info a movie page would have — one request instead
    of the reader's per-movie schedule calls.
  - cineroyal: GET {BASE}/home (readers/cineroyal.py's own `BASE`) — same story, a hidden
    `#comingSoon` div server-rendered into the homepage.
  - cinemacity: no coming-soon feed was found (2026-09-27 probe) — the Gatsby movies API needs
    known film ids to return anything, and the client-rendered listing page's own data call
    wasn't found without executing its JS. `fetch_cinemacity()` always raises; isolated like any
    other chain failure, and called out in the task report rather than guessed at.
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime

from readers.common import Polite, arabic_title, youtube_id

CHAINS = ("vox", "star", "novo", "reel", "roxy", "cineroyal", "cinemacity")
GAP = 1.0  # seconds between requests, shared by every chain fetcher below


def _iso_date(s) -> str | None:
    """A date string in one of the formats these feeds use -> "YYYY-MM-DD", else None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    s = re.sub(r"\s+", " ", s.replace(",", " ")).strip()
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _item(title, chain, title_ar=None, release_date=None, poster=None, trailer=None, genres=None):
    return {"title": title, "title_ar": title_ar or None, "release_date": _iso_date(release_date),
            "poster": poster or None, "trailer": youtube_id(trailer) if trailer else None,
            "genres": [g for g in (genres or []) if g], "chain": chain}


# ---------------------------------------------------------------- novo
def _parse_novo(payload: dict) -> list[dict]:
    movies = (payload.get("data") or {}).get("movies") or []
    out = []
    for m in movies:
        if m.get("coming_soon_order") is None:
            continue  # movie_is_coming_soon is true for now-showing films too -- not the real signal
        genres = [g.get("genre_name") for g in (m.get("movie_genre") or []) if g.get("genre_name")]
        out.append(_item(m.get("movie_title"), "novo", title_ar=arabic_title(m.get("movie_title_ar")),
                          release_date=m.get("movie_release_date"),
                          poster=m.get("movie_image_url") or m.get("movie_banner_url"),
                          trailer=m.get("movie_trailer_link"), genres=genres))
    return out


def fetch_novo() -> list[dict]:
    from readers.novo import API

    http = Polite(gap=GAP, headers={"Accept": "application/json"})
    r = http.get(f"{API}/movies", params={"country_id": 2, "channel": "web"})
    if r is None or r.status_code != 200:
        raise RuntimeError(f"novo: /movies failed (status={getattr(r, 'status_code', None)})")
    return _parse_novo(r.json())


# ---------------------------------------------------------------- star
def _parse_star(payload: dict) -> list[dict]:
    movies = (payload.get("Records") or {}).get("data") or []
    out = []
    for m in movies:
        genres = [g for g in str(m.get("genre_name") or "").split(",") if g]
        out.append(_item(m.get("movie_title"), "star",
                          release_date=m.get("mrrdr_release_date") or m.get("original_release_date"),
                          poster=m.get("md_thumbnail_url"), genres=genres))
    return out


def fetch_star() -> list[dict]:
    from readers.star import BASE, TOKEN

    http = Polite(gap=GAP, headers={"Accept": "application/json", "Authorization": TOKEN})
    r = http.get(f"{BASE}/coming-soon-movies")
    if r is None or r.status_code != 200:
        raise RuntimeError(f"star: /coming-soon-movies failed (status={getattr(r, 'status_code', None)})")
    return _parse_star(r.json())


# ---------------------------------------------------------------- vox
_VOX_ARTICLE = re.compile(r"<article\s+class=\"movie-summary[^\"]*\"\s*data-slug=\"([^\"]*)\"\s*"
                          r"data-title=\"([^\"]*)\".*?</article>", re.S)
_VOX_POSTER = re.compile(r'<img class="poster" src="([^"]+)"')
_VOX_RELEASE = re.compile(r"Release Date:</strong>\s*([^<]+?)\s*<br")


def _parse_vox(html_text: str) -> list[dict]:
    out = []
    for m in _VOX_ARTICLE.finditer(html_text):
        block, title = m.group(0), m.group(2)
        if not title:
            continue
        poster_m = _VOX_POSTER.search(block)
        rel_m = _VOX_RELEASE.search(block)
        out.append(_item(title, "vox", release_date=rel_m.group(1) if rel_m else None,
                          poster=poster_m.group(1) if poster_m else None))
    return out


def fetch_vox() -> list[dict]:
    from curl_cffi import requests as cr

    from readers.vox import BASE

    s = cr.Session()
    r = s.get(f"{BASE}/movies/comingsoon", impersonate="chrome", timeout=30)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"vox: /movies/comingsoon failed (status={getattr(r, 'status_code', None)})")
    return _parse_vox(r.text)


# ---------------------------------------------------------------- reel
def _parse_reel(payload: dict, poster_tpl: str) -> list[dict]:
    films = (payload or {}).get("value") or []
    out = []
    for f in films:
        if not (f.get("IsComingSoon") and not f.get("IsScheduledAtCinema")):
            continue
        fid = f.get("ID")
        out.append(_item(f.get("Title"), "reel", release_date=f.get("OpeningDate"),
                          poster=poster_tpl.format(fid) if fid else None, trailer=f.get("TrailerUrl")))
    return out


def fetch_reel() -> list[dict]:
    from readers.reel import BASE, POSTER

    http = Polite(gap=GAP)
    r = http.get(f"{BASE}/Films.json")
    if r is None or r.status_code != 200:
        raise RuntimeError(f"reel: /Films.json failed (status={getattr(r, 'status_code', None)})")
    return _parse_reel(r.json(), POSTER)


# ---------------------------------------------------------------- roxy
_ROXY_TAB = re.compile(r'class="coh-accordion-tabs-content coming-soon-tab"[^>]*>(.*)', re.S)
_ROXY_ARTICLE = re.compile(r'<article\b[^>]*data-history-node-id="(\d+)"[^>]*>(.*?)</article>', re.S)
_ROXY_TITLE = re.compile(r'movie-title["\'][^>]*>\s*([^<]+?)\s*<')
_ROXY_POSTER = re.compile(r'<img[^>]+src="([^"]+)"')
_ROXY_GENRE = re.compile(r'movie-genre["\'][^>]*>([^<]*)<')
_ROXY_RELEASE = re.compile(r'Release Date:.*?<time datetime="([^"T]+)')


def _parse_roxy(html_text: str, base: str) -> list[dict]:
    tab_m = _ROXY_TAB.search(html_text)
    tab = tab_m.group(1) if tab_m else ""
    out = []
    for m in _ROXY_ARTICLE.finditer(tab):
        block = m.group(2)
        title_m = _ROXY_TITLE.search(block)
        if not title_m:
            continue
        poster_m = _ROXY_POSTER.search(block)
        genre_m = _ROXY_GENRE.search(block)
        rel_m = _ROXY_RELEASE.search(block)
        genres = [g.strip() for g in (genre_m.group(1) if genre_m else "").split(",") if g.strip()]
        poster = poster_m.group(1) if poster_m else None
        if poster and poster.startswith("/"):
            poster = base + poster
        out.append(_item(title_m.group(1), "roxy", release_date=rel_m.group(1) if rel_m else None,
                          poster=poster, genres=genres))
    return out


def fetch_roxy() -> list[dict]:
    from curl_cffi import requests as cr

    from readers.roxy import BASE

    s = cr.Session()
    r = s.get(f"{BASE}/en", impersonate="chrome", timeout=30)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"roxy: /en failed (status={getattr(r, 'status_code', None)})")
    return _parse_roxy(r.text, BASE)


# ---------------------------------------------------------------- cineroyal
# The #comingSoon div is plain server-rendered HTML (not a separate endpoint) -- one movie block
# is <img src=...> ... movie__title ... movie__option (two <a>: an empty one, then the genre text)
# in that fixed order, so a single sequential regex (finditer never re-scans consumed text) pairs
# each poster with its own title without needing to balance the surrounding <div>s.
_CR_TAB = re.compile(r'id="comingSoon"[^>]*>(.*)', re.S)
_CR_ITEM = re.compile(
    r'<img alt=\'\' src="([^"]+)">.*?class="movie__title"[^>]*>\s*([^<]+?)\s*<'
    r'.*?class="movie__option">\s*<a[^>]*>\s*</a>\s*<a[^>]*>([^<]*)</a>', re.S)


def _parse_cineroyal(html_text: str) -> list[dict]:
    tab_m = _CR_TAB.search(html_text)
    tab = tab_m.group(1) if tab_m else ""
    out = []
    for poster, title, genre in _CR_ITEM.findall(tab):
        genres = [g.strip() for g in genre.split(",") if g.strip()]
        out.append(_item(title, "cineroyal", poster=poster or None,
                          genres=genres))  # Cine Royal's coming-soon dates are almost always "TBA"
    return out


def fetch_cineroyal() -> list[dict]:
    from readers.cineroyal import BASE

    http = Polite(gap=GAP)
    r = http.get(f"{BASE}/home")
    if r is None or r.status_code != 200:
        raise RuntimeError(f"cineroyal: /home failed (status={getattr(r, 'status_code', None)})")
    return _parse_cineroyal(r.text)


# ---------------------------------------------------------------- cinemacity
def fetch_cinemacity() -> list[dict]:
    # 2026-09-27 probe (task-2-report.md): the Gatsby movies API (readers/cinemacity.py's own
    # BASE) only returns data for known film ids, and the client-rendered /movies/ "Coming Soon"
    # tab makes its own fetch that wasn't found without executing the page's JS. No safe guess is
    # made here -- this chain's coming-soon feed is simply missing until a real endpoint is found.
    raise RuntimeError("cinemacity: no coming-soon endpoint found (see docs/probe/cinemacity.md notes "
                        "and task-2-report.md) -- add one here once found, don't guess a URL")


FETCHERS = {
    "novo": fetch_novo, "star": fetch_star, "vox": fetch_vox, "reel": fetch_reel,
    "roxy": fetch_roxy, "cineroyal": fetch_cineroyal, "cinemacity": fetch_cinemacity,
}


def fetch_all(chains=None, fetchers: dict | None = None) -> dict:
    """Calls every chain's fetcher, isolated. Returns {chain: {"ok", "items", "error"}}."""
    fetchers = fetchers or FETCHERS
    out = {}
    for chain in (chains or CHAINS):
        fn = fetchers.get(chain)
        if fn is None:
            continue
        try:
            out[chain] = {"ok": True, "items": fn(), "error": None}
        except Exception as e:  # noqa: BLE001 - one chain's feed breaking must never lose the others
            out[chain] = {"ok": False, "items": [], "error": f"{type(e).__name__}: {e}"}
            print(f"[coming] {chain}: {e}", file=sys.stderr)
        time.sleep(GAP)
    return out


if __name__ == "__main__":
    import json

    result = fetch_all()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
