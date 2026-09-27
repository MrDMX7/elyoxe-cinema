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


_3D = re.compile(r"(?<![A-Za-z0-9])3D(?![A-Za-z0-9])", re.I)


def fmt3d(title) -> str:
    """"3D" when a film title carries the 3D format (several chains mark it only there), else "".
    Part of every reader's price-sample key, so a 2D sample never prices a 3D show."""
    return "3D" if title and _3D.search(title) else ""


# ---------------------------------------------------------------- per-film / per-show extras
# Film-level extras a reader may add to each show (normalize.merge folds them onto the film and
# never copies a film_* key onto the show):
#   film_poster:  the chain's own poster URL (absolute) — posters.py mirrors the largest portrait one
#   film_trailer: a YouTube URL or 11-char id the chain publishes
#   film_genres:  the chain's raw genre labels (list of str) — genres.genre_keys() maps them
# Show-level extras, only when the chain's payload states them (never guessed):
#   lang: ISO-ish language key (LANG_CODES values), subs: list of such keys

LANG_CODES = {
    "english": "en", "arabic": "ar", "hindi": "hi", "malayalam": "ml", "tamil": "ta", "telugu": "te",
    "tagalog": "tl", "filipino": "tl", "punjabi": "pa", "nepali": "ne", "korean": "ko", "japanese": "ja",
    "french": "fr", "kannada": "kn", "urdu": "ur", "bengali": "bn", "bangla": "bn", "marathi": "mr",
    "gujarati": "gu", "spanish": "es", "chinese": "zh", "mandarin": "zh", "cantonese": "zh",
    "turkish": "tr", "russian": "ru", "persian": "fa", "farsi": "fa", "german": "de", "italian": "it",
    "sinhala": "si", "thai": "th", "indonesian": "id", "portuguese": "pt",
}
_ISO2 = set(LANG_CODES.values())


def lang_key(name) -> str | None:
    """"English" / "ENGLISH" / "EN" / "Localization.Language.English" -> "en"; None when unknown."""
    if not name or not isinstance(name, str):
        return None
    t = name.strip().rsplit(".", 1)[-1].strip().lower()
    t = re.sub(r"\s*\((?:dubbed|dub)\)\s*$", "", t)
    if t in LANG_CODES:
        return LANG_CODES[t]
    if t in _ISO2:
        return t
    if t in ("eng",):
        return "en"
    if t in ("ara",):
        return "ar"
    return None


def subs_keys(text) -> list[str]:
    """"Arabic | English", "Arabic & English", ["AR", "EN"] -> ["ar", "en"]; [] when none/unknown."""
    if not text:
        return []
    parts = text if isinstance(text, (list, tuple)) else re.split(r"\s*(?:\||,|&|/|\band\b)\s*", str(text), flags=re.I)
    out: list[str] = []
    for p in parts:
        k = lang_key(p)
        if k and k not in out:
            out.append(k)
    return out


_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_URL = re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/|v/|live/)|youtu\.be/)"
                     r"([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")


def youtube_id(v) -> str | None:
    """A YouTube URL (watch / youtu.be / embed / shorts) or a bare 11-char id -> the id, else None."""
    if not v or not isinstance(v, str):
        return None
    v = v.strip().replace("&amp;", "&").replace("&#x3D;", "=")
    if _YT_ID.match(v):
        return v
    m = _YT_URL.search(v)
    return m.group(1) if m else None


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def city_of(*texts: str) -> str | None:
    t = " ".join(x for x in texts if x).lower()
    for city, words in _CITY_WORDS:
        if any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words):
            return city
    return None


# ---------------------------------------------------------------- cross-run price cache
# A chain's slice of data/price_cache.json (refresh.py: {chain: {date: {key: value}}}, only
# today's date ever handed down) — a plain {str: [{"seat","aed"}]|None} mapping, or None when the
# caller has no persistence to offer (tests, --offline). Every reader that samples prices builds
# its own per-run dedup key as a tuple (cinema, hall[, ...], date[, ...] — order is the reader's
# own, cache_get/cache_set just need it stable); joined here into one string so it survives JSON.
_CACHE_MISS = object()
CACHE_MISS = _CACHE_MISS


def _join_key(key) -> str:
    return "|".join(str(part) for part in key)


def cache_get(cache: dict | None, key):
    """`cache[key joined]` if `cache` is not None and already has it, else CACHE_MISS (a sentinel
    distinct from a legitimately-cached `None`, which means "sampled, no price found")."""
    if cache is None:
        return _CACHE_MISS
    return cache.get(_join_key(key), _CACHE_MISS)


def cache_set(cache: dict | None, key, value) -> None:
    if cache is not None:
        cache[_join_key(key)] = value


def keep_layout(chain: str, cinema: str, hall_label: str, date: str, raw) -> None:
    """Phase-2 hook (seats.py): the seat-layout response a reader just fetched for a price, kept as that
    hall's map for the ticket's drawing. Never raises, never makes a request."""
    try:
        import seats
        seats.keep(chain, cinema, hall_label, date, raw)
    except Exception:  # noqa: BLE001 - the map is a bonus; the price sample must never suffer for it
        pass


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
