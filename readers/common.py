"""Shared pieces for the chain readers: the city and hall vocabularies, slugs, and a polite HTTP session.

Every reader returns {"cinemas": [Cinema], "shows": [Show]} — shapes in docs/superpowers/plans/2026-09-25-cinema.md.
"""
import re, time, unicodedata
import requests

CITIES = ["abu-dhabi", "dubai", "sharjah", "al-ain", "ajman", "ras-al-khaimah", "fujairah", "umm-al-quwain"]
HALLS = ["Standard", "MAX", "IMAX", "4DX", "GOLD", "THEATRE", "SUITES", "KIDS", "VIP", "SCREENX", "OTHER"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")

# words that name a city inside an address or cinema name -> city slug (Al Ain first: its malls sit in Abu Dhabi emirate)
_CITY_WORDS = [
    ("al-ain", ["al ain", "alain", "al-ain", "bawadi", "al jimi", "al foah", "barari", "makani zakher", "zakher"]),
    ("abu-dhabi", ["abu dhabi", "abudhabi", "yas", "reem", "maryah", "dalma", "khalidiyah", "ruwais", "dhannah", "al qana", "khalifa city", "deerfields", "wahda", "raha"]),
    ("dubai", ["dubai", "deira", "jumeirah", "mirdif", "barsha", "marina", "burjuman", "festival city", "karama", "silicon oasis"]),
    ("sharjah", ["sharjah", "zahia", "sahara centre", "mega mall"]),
    ("ajman", ["ajman"]),
    ("ras-al-khaimah", ["ras al khaimah", "rak", "manar", "al hamra"]),
    ("fujairah", ["fujairah"]),
    ("umm-al-quwain", ["umm al quwain", "uaq"]),
]


_ARABIC_LETTER = re.compile(r"[\u0621-\u064a]")


def arabic_title(s):
    """A chain's own Arabic film title, cleaned for display, or None when it isn't Arabic at all
    (Novo fills movie_title_ar with the English title for most films). Drops a trailing
    parenthesis («انترستيلر (إعادة اصدار)»), tatweel («بريشـر») and doubled spaces."""
    if not s or not _ARABIC_LETTER.search(s):
        return None
    t = s.replace("\u0640", "")
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def city_of(*texts: str) -> str | None:
    t = " ".join(x for x in texts if x).lower()
    for city, words in _CITY_WORDS:
        if any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words):
            return city
    return None


class Polite:
    """requests.Session that waits `gap` seconds between calls and retries twice on 429/5xx/timeouts."""

    def __init__(self, gap: float = 1.0, headers: dict | None = None):
        self.s, self.gap, self._last = requests.Session(), gap, 0.0
        self.s.headers.update({"User-Agent": UA, "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                               "Accept-Language": "en-US,en;q=0.9,ar;q=0.8", **(headers or {})})

    def get(self, url, **kw):
        kw.setdefault("timeout", 30)
        for attempt in range(3):
            wait = self.gap - (time.monotonic() - self._last)
            if wait > 0: time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(url, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(3 * (attempt + 1)); continue
                return r
            except requests.RequestException:
                if attempt == 2: raise
                time.sleep(3 * (attempt + 1))

    def post(self, url, **kw):
        kw.setdefault("timeout", 30)
        wait = self.gap - (time.monotonic() - self._last)
        if wait > 0: time.sleep(wait)
        self._last = time.monotonic()
        return self.s.post(url, **kw)
