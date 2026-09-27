"""Reel Cinemas (Emaar) reader.

Reel's UAE web app (reelcinemas.com) sits behind Cloudflare bot management and blocks plain
`requests` traffic. But its own frontend loads cinema/film/session/experience data straight
from a public, unauthenticated Vista Cinema data feed hosted on Google Cloud Storage — no
Cloudflare, no login, no API key. See docs/probe/reel.md for how that endpoint was found.

Listings (all GET, no auth, no rate limit observed — politeness gap still applied):
    https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Cinemas.json
    https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Films.json
    https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json/Sessions.json

Prices (live, no seat hold): the booking backend at apiuae.reelcinemas.com returns the session's
ticket list (area + AED price) from `seats/getSeatLayout` *before* any seat is chosen — the call the
seat-selection page makes on load. It needs a guest session, which the site itself opens
anonymously (`auth/loginAsGuest`, no personal data), plus the `CreateMovieCookie` call that tells
the backend which session is being viewed. No seat is ever set (`seats/setSeat` is never
called); the seat-less order times out on its own (`BookingTimer: 300` s in the response — the
site's `order/cancelOrder` is still called after every sample, in a `finally` — it answers 500 for an
order with no seats, which is ignored). One sample per cinema x experience per run; any
failure leaves that hall's `prices` None and never fails the chain. The two header/body encodings
(RSA "source-name", 3DES cookie value) are the site's own, lifted from its public bundle
(assets/index-*.js); see docs/probe/reel.md.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Price-path libraries are imported at module load on purpose: a missing library must fail
# loudly here, not be swallowed into "prices: null" by the sampler.
from Crypto.Cipher import DES3
from Crypto.Util.Padding import pad
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from curl_cffi import requests as cr

from readers.common import (CACHE_MISS, CITIES, HALLS, Polite, arabic_title, cache_get, cache_set,
                            city_of, lang_key, slug, subs_keys, youtube_id, fmt3d as _fmt3d)

BASE = "https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/json"
# the site's own poster path (bundle: e4(id) = `${$3}/vista/movie_images/${id}.jpg`, 300x450)
POSTER = "https://storage.googleapis.com/eeg-prod-reelcinema-sb/web/vista/movie_images/{}.jpg"
API = "https://apiuae.reelcinemas.com/webapi/api"
SITE = "https://www.reelcinemas.com"
CHAIN = "reel"
DUBAI = ZoneInfo("Asia/Dubai")

# Address per Reel UAE cinema id. Cinemas.json carries no address at all, so a UAE cinema with
# live sessions but no entry here is an error (a new/reopened site) — fetch() raises rather than
# dropping it or inventing an address.
_CINEMA_ADDR_HINTS = {
    "0001": "The Dubai Mall, Downtown Dubai, Dubai, UAE",
    "0002": "Dubai Marina Mall, Dubai Marina, Dubai, UAE",
    "0003": "Jebel Ali Recreation Club, Jebel Ali, Dubai, UAE",
    "0004": "The Pointe, Palm Jumeirah, Dubai, UAE",
    "0005": "Rove Downtown, Downtown Dubai, Dubai, UAE",
    "0006": "The Springs Souk, Dubai, UAE",
    "0007": "Al Ghurair Centre, Deira, Dubai, UAE",
}

# Reel "Experience" codes (SessionAttributesNames, upper-cased) -> our hall enum. Ruling 2026-09-26:
# MAX/GOLD are VOX brand names, so another chain's format screens (Dolby Cinema, Infinity Vision)
# are OTHER with the raw screen name kept; a recliner comfort tier (Reel Premium) is VIP.
_EXPERIENCE_HALL = {
    "STANDARD": "Standard",
    "PLATINUM": "SUITES",      # Reel Platinum Suites
    "PREMIUM": "VIP",           # Reel Premium (recliner tier)
    "DOLBY": "OTHER",           # Dolby Cinema — a format, not a service tier
    "SCREENX": "SCREENX",
    "IMAX": "IMAX",
    "REELJUNIOR": "KIDS",
    "INFINITY V": "OTHER",      # Infinity Vision large format (also tagged on Dolby screens)
}
_NAME_FALLBACK = (("IMAX", "IMAX", "IMAX"), ("SCREENX", "SCREENX", "SCREENX"),
                  ("PLATINUM", "SUITES", "PLATINUM"), ("DOLBY", "OTHER", "DOLBY"),
                  ("PREMIUM", "VIP", "PREMIUM"), ("JUNIOR", "KIDS", "REELJUNIOR"),
                  ("4DX", "4DX", "4DX"), ("MX4D", "4DX", "4DX"))

# --- the site's own request encodings (public bundle constants) ---------------------------
_RSA_PUB = (
    "MIIBCgKCAQEAzQaysjNdk7PI3WMNgVgAH6CDtMdrE+aNi9ULVIYWOm6gFSD6Jjiws5wuWTpMq6QPlQRQvj9cAG/DnUkf7o+t2y09"
    "PjK9NYyHGuRP2jX7ojoXKfdiraEeljgT137JpShcJlkp+k00PnQdEOsUKNLSvPO+guhcjw6Ugu/FJmxWmw6APtrf8FKKe7pFzmQS"
    "HTKScgGJanVWbr85J5HL1n+KTQUVmb9xLHvTEYCXdG+5h4xS/OvkURdjCzBeYRJFWn40YjjHKeo2KD3Zz9bXmbv5ZwvJ+LIok8PG"
    "EyE5SVkoYlIS19ssN8a/Fem86H00YxswU4r1qHCZHsxbnj9SeXm9OwIDAQAB"
)
_COOKIE_KEY_SEED = b"ReelCinemasWeb"


def _source_name() -> str:
    """`source-name` header: base64(RSA-PKCS1v1.5("web")) with the bundle's public key."""
    body = "\n".join(_RSA_PUB[i:i + 64] for i in range(0, len(_RSA_PUB), 64))
    pem = f"-----BEGIN RSA PUBLIC KEY-----\n{body}\n-----END RSA PUBLIC KEY-----\n".encode()
    key = serialization.load_pem_public_key(pem)
    return base64.b64encode(key.encrypt(b"web", padding.PKCS1v15())).decode()


def _cookie_value(obj: dict) -> str:
    """CreateMovieCookie body: 3DES-ECB(md5 key) of the JSON, url-safe base64 — as the bundle's X1()."""
    h = hashlib.md5(_COOKIE_KEY_SEED).hexdigest()
    key = bytes.fromhex(h + h[:16])
    ct = DES3.new(key, DES3.MODE_ECB).encrypt(pad(json.dumps(obj, separators=(",", ":")).encode(), 8))
    return base64.b64encode(ct).decode().replace("/", "_").replace("+", "-")


class _SampleError(Exception):
    pass


class _PriceClient:
    """Guest session against apiuae.reelcinemas.com (curl_cffi: the API is behind Cloudflare)."""

    def __init__(self):
        self._time = time
        self.s = cr.Session(impersonate="chrome")
        self.h = {"Origin": SITE, "Referer": SITE + "/", "Accept": "application/json, text/plain, */*"}
        self._last = 0.0
        self.ok = False

    def _call(self, method: str, path: str, **kw):
        wait = 1.1 - (self._time.monotonic() - self._last)
        if wait > 0:
            self._time.sleep(wait)
        self._last = self._time.monotonic()
        headers = {**self.h, "source-name": _source_name()}
        return self.s.request(method, f"{API}/{path}", headers=headers, timeout=30, **kw)

    def login(self) -> str | None:
        """Open the anonymous guest session. Returns None on success, else an error string."""
        r = self._call("POST", "auth/loginAsGuest", json={})
        try:
            body = r.json() if r.status_code == 200 else {}
        except ValueError:
            body = {}
        token = (((body or {}).get("tokens") or {}).get("access") or {}).get("token")
        self.ok = bool(token) and body.get("statusCode") == 1
        if self.ok:  # the site's axios interceptor sends the guest access token as a Bearer
            self.h["Authorization"] = f"Bearer {token}"
            return None
        return f"loginAsGuest failed: status={r.status_code} statusCode={(body or {}).get('statusCode')}"

    def sample(self, cinema_id: str, session_id: str, experience: str, screen: str) -> list[dict] | None:
        """Read one session's ticket list. Raises _SampleError with the step that failed."""
        info = {"CinemaId": cinema_id, "SessionId": session_id, "Experience": experience, "ScreenName": screen}
        user_session = ""
        try:
            r = self._call("POST", "booking/CreateMovieCookie", json={"value": _cookie_value(info)})
            if r.status_code != 200:
                raise _SampleError(f"CreateMovieCookie status={r.status_code} (cookie key rotated?)")
            r = self._call("POST", "seats/getSeatLayout?IsCancel=false&sessionId=", json={})
            if r.status_code != 200:
                raise _SampleError(f"getSeatLayout status={r.status_code}")
            body = r.json() or {}
            src = body.get("Sourcedata") or {}
            if body.get("statusCode") != 1 or not isinstance(src, dict):
                raise _SampleError(f"getSeatLayout statusCode={body.get('statusCode')} "
                                   f"{str(body.get('statusMessage'))[:80]!r}")
            try:
                user_session = json.loads(src.get("BInfo") or "{}").get("UserSessionId") or ""
            except (TypeError, ValueError):
                user_session = ""
            return self._parse(src)
        finally:
            # abandon the guest order through the site's own cancel call, every time (ruling
            # 2026-09-26). It answers 500 for an order with no seats; that is expected and ignored.
            try:
                self._call("POST", "order/cancelOrder",
                           json={"OptionalClientId": "211.111.111.200", "CinemaId": cinema_id,
                                 "UserSessionId": user_session})
            except Exception as e:  # network error on the courtesy cancel: note it, carry on
                print(f"[readers.reel] cancelOrder failed: {e!r}", file=sys.stderr)

    @staticmethod
    def _parse(src: dict) -> list[dict] | None:
        areas = {a.get("AreaCode"): (a.get("AreaDescription") or "").strip()
                 for a in src.get("AreaEntityList") or []}
        out: dict[str, float] = {}
        for t in src.get("TicketList") or []:
            aed = t.get("PriceInAed")
            if t.get("IsFreeTicket") or not aed or aed <= 0:
                continue
            seat = areas.get(t.get("AreaCode")) or (t.get("TicketDescription") or "").strip()
            if seat and seat not in out:  # first listed ticket per area = the headline fare
                out[seat] = float(aed)
        return [{"seat": k, "aed": v} for k, v in out.items()] or None


def _hall_of(session: dict) -> tuple[str, str, str]:
    """Return (hall, hall_label, experience_code) for a Vista session record."""
    attrs = [a.upper() for a in (session.get("SessionAttributesNames") or [])]
    screen_name = (session.get("ScreenName") or "").strip()
    for attr in _EXPERIENCE_HALL:  # dict order = priority (Dolby beats Infinity Vision)
        if attr in attrs:
            return _EXPERIENCE_HALL[attr], screen_name or attr.title(), attr
    up = screen_name.upper()
    for needle, hall, code in _NAME_FALLBACK:
        if needle in up:
            return hall, screen_name or needle.title(), code
    # unrecognised screen: its own price key, never shared with real Standard screens
    return "OTHER", screen_name or "Standard", f"OTHER:{screen_name}"


def _slugify(title: str) -> str:
    """Mirror Reel's own frontend slug function (i3 in the bundle)."""
    s = title.lower().replace("&", "-and-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def film_extras(film: dict, genre_names: dict) -> dict:
    """Poster, trailer, genres, language and subtitles one Films.json record states."""
    out: dict = {"film_poster": POSTER.format(film["ID"])} if film.get("ID") else {}
    yt = youtube_id(film.get("TrailerUrl"))
    if yt:
        out["film_trailer"] = yt
    genres = [genre_names[g] for g in (film.get("GenreId"), film.get("GenreId2"), film.get("GenreId3"))
              if g and genre_names.get(g)]
    if genres:
        out["film_genres"] = genres
    lang = lang_key(_clean(film.get("Language")))
    if lang:
        out["lang"] = lang
    subs = subs_keys(_clean(film.get("SubTitle")))
    if subs:
        out["subs"] = subs
    return out


def fetch(days: int = 2, prices: bool = True, cache: dict | None = None) -> dict:
    http = Polite(gap=1.0)

    cinemas_raw = http.get(f"{BASE}/Cinemas.json").json()["value"]
    films_raw = http.get(f"{BASE}/Films.json").json()["value"]
    sessions_raw = http.get(f"{BASE}/Sessions.json").json()["value"]

    films_by_id = {f["ID"]: f for f in films_raw}
    try:  # genre names: a failure only costs the genres
        genre_names = {g["ID"]: (g.get("Name") or "").strip()
                       for g in http.get(f"{BASE}/FilmGenres.json").json()["value"]}
    except Exception:
        genre_names = {}

    now = datetime.now(DUBAI)
    today = now.date()
    target_dates = {(today + timedelta(days=d)).isoformat() for d in range(max(days, 1))}

    uae = {c["ID"]: c for c in cinemas_raw if c.get("CinemaNationalId") == "UAE"}
    in_window = [s for s in sessions_raw
                 if s.get("CinemaId") in uae and (s.get("Showtime") or "")[:10] in target_dates]
    live_ids = sorted({s["CinemaId"] for s in in_window})
    missing = [cid for cid in live_ids if cid not in _CINEMA_ADDR_HINTS]
    if missing:
        raise ValueError(f"reel: UAE cinema(s) with live sessions but no address hint: "
                         f"{[(m, uae[m].get('Name')) for m in missing]}")

    cinemas, cinema_id_of = [], {}
    for cid in live_ids:
        c = uae[cid]
        addr = _CINEMA_ADDR_HINTS[cid]
        name = c["Name"]
        city = city_of(name, addr) or "dubai"
        if city not in CITIES:
            raise ValueError(f"reel: no city for {name!r}")
        cinema_id_of[cid] = f"{CHAIN}-{slug(name)}"
        cinemas.append({
            "id": cinema_id_of[cid],
            "chain": CHAIN,
            "name": f"Reel Cinemas {name}",
            "name_ar": _clean(c.get("NameAlt")),
            "city": city,
            "mall": name,
            "address": addr,
            "maps": None,
            "lat": _num(c.get("Latitude")),
            "lng": _num(c.get("Longitude")),
        })

    shows, sample_for = [], {}
    for s in in_window:
        showtime = s.get("Showtime") or ""
        if "T" not in showtime:
            continue
        date_part, time_part = showtime.split("T", 1)
        film = films_by_id.get(s.get("ScheduledFilmId"))
        if not film:
            continue
        hall, hall_label, code = _hall_of(s)
        if hall not in HALLS:
            hall = "OTHER"
        # resolved hall in the key (no OTHER<->Standard sharing), and the show date: weekday/weekend
        # prices differ, so each cinema x hall is sampled once per day; a 3D title is its own key
        key = (s["CinemaId"], hall, code, date_part, _fmt3d(film.get("Title")))
        # sample a session that hasn't started (an hour's margin) and still sells seats
        start = datetime.fromisoformat(showtime).replace(tzinfo=DUBAI)
        if (key not in sample_for and start > now + timedelta(hours=1)
                and (s.get("SeatsAvailable") or 0) > 0 and s.get("AllowTicketSales", True)):
            cookie_exp = "STANDARD" if code.startswith("OTHER:") else code
            sample_for[key] = (s["CinemaId"], s["SessionId"], cookie_exp, (s.get("ScreenName") or "").strip())
        film_id = film["ID"]
        shows.append({
            "cinema": cinema_id_of[s["CinemaId"]],
            "film_title": _clean(film.get("Title")) or "",
            "film_title_ar": arabic_title(film.get("TitleAlt")),
            "film_lang": _clean(film.get("Language")),
            "film_rating": _clean(film.get("Rating")),
            "runtime": film.get("RunTime"),
            "date": date_part,
            "time": time_part[:5],
            "hall": hall,
            "hall_label": hall_label,
            "prices": key,  # resolved below
            "book": f"{SITE}/en-ae/movie-details/{film_id}/{_slugify(film['Title'])}",
            **film_extras(film, genre_names),
        })

    if not shows:
        raise RuntimeError("reel: zero shows in the window — Sessions.json stale or feed moved")

    price_of: dict = {}
    health = {"attempted": 0, "priced": 0, "error": None}
    if prices and sample_for:
        fresh_sample_for = {}
        for key, v in sample_for.items():
            hit = cache_get(cache, key)
            if hit is not CACHE_MISS:  # already sampled today -- reuse instead of another call
                price_of[key] = hit
                health["cached"] = health.get("cached", 0) + 1
            else:
                fresh_sample_for[key] = v
        sample_for = fresh_sample_for
    if prices and sample_for:
        try:  # constructing the curl_cffi session is part of the price path: it must not fail the chain
            pc = _PriceClient()
            err = pc.login()
        except Exception as e:  # session construction, network, Cloudflare or crypto failure
            err = f"price client/guest login raised {e!r}"
        if err:
            health["error"] = err
            print(f"[readers.reel] price sampling skipped: {err}", file=sys.stderr)
        else:
            errors = []
            for key, (cid, sid, code, screen) in sample_for.items():
                health["attempted"] += 1
                try:
                    price_of[key] = pc.sample(cid, sid, code, screen)
                except _SampleError as e:
                    price_of[key] = None
                    errors.append(f"{cid}/{sid}: {e}")
                except Exception as e:  # network error on one sample: that hall stays None
                    price_of[key] = None
                    errors.append(f"{cid}/{sid}: {e!r}")
                if price_of.get(key):
                    health["priced"] += 1
                cache_set(cache, key, price_of.get(key))
            for e in errors:
                print(f"[readers.reel] price sample failed: {e}", file=sys.stderr)
            if health["attempted"] and not health["priced"]:
                health["error"] = f"0/{health['attempted']} samples priced; first: {errors[0] if errors else 'empty ticket lists'}"
    for sh in shows:
        sh["prices"] = price_of.get(sh["prices"])

    return {"cinemas": cinemas, "shows": shows, "price_health": health}


if __name__ == "__main__":
    import sys

    data = fetch()
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
