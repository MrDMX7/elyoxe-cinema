"""Build «سينما» — https://cinema.elyoxe.com — static pages from data/latest.json + discounts.yaml + halls.yaml.

  src/page.html     the page template (head with SEO, header with the wordmark and nav, footer)
  src/cinema.css    the «هـ» design system (night, velvet, marquee gold; Markazi Text + Readex Pro)
  src/cinema.js     client: city + card (localStorage), prices after discount, «الحين», the ticket
  src/fonts/        self-hosted woff2 subsets (OFL, licences beside them)

python build.py [--data data/latest.json] [--discounts discounts.yaml] [--halls halls.yaml] [--out out]
  -> out/index.html  out/en/…  out/<city>/  out/<city>/<cinema>/  out/film/<fid>/  out/cards/…  out/halls/
     out/data/<city>-<date>.json  out/data/discounts.json  out/sitemap.xml  out/robots.txt  out/404.html
     out/assets/{cinema.css,cinema.js,icon.svg,fonts/}

Discount semantics (mirrored in cinema.js): percent -> price×(1-v/100); bogo -> price/2 per person;
excluded_halls / included_halls by hall code; valid_until in the past -> no discount; status none_found ->
«ما لقينا خصم» (we found none), never «they refuse it». Only official rules are published, and only cards
with at least one current official discount appear anywhere (the spec: third-party/unconfirmed stay hidden).
"""
import argparse, colorsys, datetime as dt, hashlib, html, json, os, re, shutil, sys
from urllib.parse import quote

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
SITE = "https://cinema.elyoxe.com"
sys.path.insert(0, ROOT)
import discounts as _disc  # noqa: E402  (load() + compute(); confirmed_cards() when Task 2 lands)
try:  # Task 2: genre keys -> labels
    import genres as _genres  # noqa: E402
except Exception:  # pragma: no cover - the module is optional
    _genres = None

CITIES = [("abu-dhabi", "أبوظبي", "Abu Dhabi"), ("dubai", "دبي", "Dubai"), ("sharjah", "الشارقة", "Sharjah"),
          ("al-ain", "العين", "Al Ain"), ("ajman", "عجمان", "Ajman"), ("ras-al-khaimah", "رأس الخيمة", "Ras Al Khaimah"),
          ("fujairah", "الفجيرة", "Fujairah"), ("umm-al-quwain", "أم القيوين", "Umm Al Quwain")]
CITY = {c[0]: (c[1], c[2]) for c in CITIES}
NEAR = {"umm-al-quwain": "ajman", "fujairah": "sharjah", "ajman": "sharjah", "ras-al-khaimah": "ajman"}
VERDICT = {"yes": ("يستاهل", "Worth it"), "mixed": ("بين بين", "Mixed"), "skip": ("تجنّبه", "Skip it"),
           "unknown": ("ما في تقييم كافي", "Not enough reviews")}
LANGS = {"English": ("إنجليزي", "English"), "Arabic": ("عربي", "Arabic"), "Hindi": ("هندي", "Hindi"), "Telugu": ("تيلوغو", "Telugu"),
         "Malayalam": ("مالايالام", "Malayalam"), "Tamil": ("تاميل", "Tamil"), "Tagalog": ("فلبيني", "Tagalog"),
         "Urdu": ("أوردو", "Urdu"), "French": ("فرنسي", "French"), "Korean": ("كوري", "Korean"), "Japanese": ("ياباني", "Japanese"),
         "Nepali": ("نيبالي", "Nepali"), "Punjabi": ("بنجابي", "Punjabi")}
# live data (Task 2) carries ISO 639-1 keys per show: en, ar, hi, ml …
LANGS.update({"en": LANGS["English"], "ar": LANGS["Arabic"], "hi": LANGS["Hindi"], "te": LANGS["Telugu"], "ml": LANGS["Malayalam"],
              "ta": LANGS["Tamil"], "tl": LANGS["Tagalog"], "ur": LANGS["Urdu"], "fr": LANGS["French"], "ko": LANGS["Korean"],
              "ja": LANGS["Japanese"], "ne": LANGS["Nepali"], "pa": LANGS["Punjabi"]})


def ar_count(n, forms):
    """Arabic counted nouns, as cinema.js's arCount: 1 · 2 · 3–10 (plural) · 11+ (singular again)."""
    return forms[0] if n == 1 else forms[1] if n == 2 else f"{n} {forms[2]}" if 3 <= n <= 10 else f"{n} {forms[3]}"


def seats_left(n, lang):
    if lang == "en": return f"{n} seat left" if n == 1 else f"{n} seats left"
    return "باقي " + ar_count(n, ("مقعد واحد", "مقعدين", "مقاعد", "مقعد"))


def lang_words(v, lang):
    """A language key, or subtitle keys joined by '+' ("ar+en"), as words in the page language."""
    sep = "، " if lang == "ar" else ", "
    return sep.join(L(LANGS.get(k, (k, k)), lang) for k in str(v).split("+") if k)
# older data: genres as a plain English list; Task 2 adds lowercase keys with labels in genres.py
GENRES = {"Action": "أكشن", "Adventure": "مغامرة", "Drama": "دراما", "Horror": "رعب", "Comedy": "كوميدي", "Animation": "أنيميشن",
          "Thriller": "إثارة", "Superhero": "أبطال خارقين", "Family": "عائلي", "Romance": "رومانسي", "Sci-Fi": "خيال علمي"}
GENRE_FALLBACK = {"action": ("أكشن", "Action"), "adventure": ("مغامرة", "Adventure"), "drama": ("دراما", "Drama"),
                  "horror": ("رعب", "Horror"), "comedy": ("كوميدي", "Comedy"), "animation": ("أنيميشن", "Animation"),
                  "thriller": ("إثارة", "Thriller"), "superhero": ("أبطال خارقين", "Superhero"), "family": ("عائلي", "Family"),
                  "romance": ("رومانسي", "Romance"), "sci-fi": ("خيال علمي", "Sci-fi"), "science-fiction": ("خيال علمي", "Sci-fi"),
                  "fantasy": ("فانتازيا", "Fantasy"), "crime": ("جريمة", "Crime"), "mystery": ("غموض", "Mystery"),
                  "musical": ("موسيقي", "Musical"), "music": ("موسيقي", "Music"), "documentary": ("وثائقي", "Documentary"),
                  "war": ("حرب", "War"), "history": ("تاريخي", "History"), "sport": ("رياضة", "Sport"), "biography": ("سيرة", "Biography")}
FAMILY_RATINGS = {"G", "PG", "PG13", "PG-13", "PG 13"}
KIDS_RATINGS = {"G", "PG"}
CONF_WEAK = ("غير مؤكد — تأكد من الشباك", "Unconfirmed — check at the box office")
UI = {
    "s_mark": ("سينما", "Cinema"), "s_films": ("الأفلام", "Films"), "s_cinemas": ("السينمات", "Cinemas"),
    "s_thursday": ("نازل الخميس", "Out Thursday"), "s_cards": ("البطاقات", "Cards"), "s_halls": ("القاعات", "Halls"),
    "s_alt": ("English", "العربية"), "s_nav": ("الأقسام", "Sections"), "s_skip": ("تخطَّ إلى المحتوى", "Skip to content"),
    "s_footer": ("سينما من Elyoxe. الأسعار من السينمات نفسها، والخصومات متحقَّق منها بتاريخها.",
                 "Cinema by Elyoxe. Prices from the cinemas themselves; discounts checked and dated."),
    "s_studio": ("استوديو Elyoxe", "Elyoxe studio"),
}
T = {  # strings shared with cinema.js (window.CT)
    "aed": ("درهم", "AED"), "box": ("السعر في الشباك", "Price at the box office"), "nocard": ("بدون بطاقة", "No card"),
    "none_found": ("ما لقينا خصم", "No discount found"), "unchecked": ("ما تحققنا بعد", "Not checked yet"),
    "expired": ("العرض انتهى", "Offer ended"), "excluded": ("القاعة مب داخلة في الخصم", "This hall is excluded"),
    "cheap_tonight": ("أرخص تذكرة لك الليلة", "Cheapest for you tonight"), "cheap_tomorrow": ("أرخص تذكرة لك بكرة", "Cheapest for you tomorrow"),
    "not_in_city": ("ما يعرض في {city}", "Not showing in {city}"), "now_empty": ("ما في عرض يبدأ خلال ساعتين في {city}. أقرب عرض: {next}.", "Nothing starts in the next 2 hours in {city}. Next: {next}."),
    "now_none": ("ما في عروض باقية اليوم في {city}.", "No shows left today in {city}."),
    "updated": ("آخر تحديث", "Last updated"), "weak": CONF_WEAK, "per_person": ("للشخص — بشرط تذكرتين", "per person, with 2 tickets"),
    "asof": ("السعر بتاريخ {date}", "Price as of {date}"),
    "with": ("مع {card}", "with {card}"), "ago_m": ("قبل {n} دقيقة", "{n} min ago"), "ago_h": ("قبل {n}", "{n} ago"),
    "now_label": ("أقرب عرض يبدأ الحين", "Next show starting now"),
    "now_quiet": ("ما في عرض يبدأ خلال 45 دقيقة", "Nothing starts within 45 minutes"),   # one line: the slot keeps its height "in_min": ("بعد {n} دقيقة", "in {n} min"),
    "ends": ("يخلص تقريباً {t}", "Ends around {t}"), "today": ("اليوم", "Today"), "tomorrow": ("بكرة", "Tomorrow"),
    "book_at": ("احجز من موقع {chain}", "Book on the {chain} site"), "share": ("أرسلها للقروب", "Send to the group"),
    "after_card": ("بعد خصم {card}", "after {card}"), "in_cinema": ("{film} في {cinema}", "{film} at {cinema}"),
}
RERELEASE = ("إعادة عرض", "Re-release")
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
HHMM = re.compile(r"^\d{2}:\d{2}$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
YT = re.compile(r"^[A-Za-z0-9_-]{11}$")
SAFE_URL = re.compile(r"^https?://", re.I)
OUR_POSTER = re.compile(r"^/posters/[A-Za-z0-9._-]+\.webp$")   # posters.py mirrors to /posters/<fid>-<hash>-342.webp
SCHED_BUDGET = 100_000   # bytes of schedule markup per page; with the chrome a page stays under 150 KB
# every page is rendered as richly as fits PAGE_TARGET (the spec's budget is 150 KB; the target leaves
# headroom for busier days): each schedule tries its modes in order and the last, «compact», is bounded —
# times as plain text that cinema.js turns into buttons and prices from the city's /data slice
PAGE_TARGET = 125_000
CHROME = 7_000           # the template, window.CT and the page's price lists' wrapper, measured ~6 KB
BCP47 = {"English": "en", "Arabic": "ar", "Hindi": "hi", "Telugu": "te", "Malayalam": "ml", "Tamil": "ta", "Tagalog": "tl",
         "Urdu": "ur", "Bengali": "bn", "Kannada": "kn", "French": "fr", "Spanish": "es", "Japanese": "ja", "Korean": "ko",
         "Chinese": "zh", "Russian": "ru", "Turkish": "tr", "Persian": "fa", "Filipino": "tl", "Punjabi": "pa", "Marathi": "mr"}
PCT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?\s?%)")
ARABIC = re.compile(r"[؀-ۿ]")
MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
# the CSS width each poster class is drawn at (cinema.css): row tile, the big first tile, the film hero, list thumb
POSTER_SIZES = {"pst": "(min-width:1024px) 15vw, 150px", "pst big": "(min-width:1024px) 15vw, 220px",
                "pst hero": "(min-width:1280px) 300px, (min-width:1024px) 220px, min(62vw, 260px)", "pst sm": "(min-width:1024px) 96px, 72px"}
# preloaded fonts: the faces whose late swap would move the layout — the Arabic display face (headings are
# large: a swap from the fallback reflows everything under them) and the body face of the page's script.
# The digits' latin subset is small in the layout and comes through the stylesheet; every preload shares a
# slow phone link with the LCP poster.
FONTS = {"ar": ("markazi-700-arabic.woff2", "readex-arabic.woff2"), "en": ("readex-latin.woff2",)}
# a show with no booking URL still books somewhere: the chain's own site
CHAIN_SITE = {"vox": "https://uae.voxcinemas.com/", "star": "https://www.starcinemas.ae/", "novo": "https://uae.novocinemas.com/",
              "reel": "https://www.reelcinemas.ae/", "roxy": "https://www.theroxycinemas.com/", "cineroyal": "https://cineroyal.ae/",
              "cinemacity": "https://www.cinemacity.ae/"}


def rel(u):
    """Our own URL as a root-relative path (shorter markup); anything else unchanged."""
    return u[len(SITE):] if isinstance(u, str) and u.startswith(SITE + "/") else u


def esc(s):
    return html.escape("" if s is None else str(s))


def L(pair, lang):
    return pair[0] if lang == "ar" else pair[1]


def P(lang, *parts):
    """Site path: Arabic at the root, English under /en/."""
    p = "/".join(quote(str(x), safe="-._~") for x in parts if x)
    return ("/en/" if lang == "en" else "/") + (p + "/" if p else "")


def dates(h):
    """escaped text -> the same with every ISO date and every percentage isolated. Inside an Arabic run a
    number turns Arabic (UBA W2), so «خصم 20%» would print «خصم %20» and 2027-08-05 as 05-08-2027."""
    # dir="ltr": span.num alone falls back to the page's RTL for a run with no strong letter
    return PCT.sub(r'<span class="num" dir="ltr">\1</span>', DATE.sub(r'<bdi class="num">\1</bdi>', h))


def money(x):
    return f"{float(x):.2f}"


def num(x, cls="num"):
    d = ' dir="ltr"' if "%" in str(x) else ""
    return f'<span class="{cls}"{d}>{esc(x)}</span>'


def span_dates(a, b, lang):
    """«25 سبتمبر إلى 16 أكتوبر 2026» / "25 September to 16 October 2026" (the year once when both share it)."""
    try:
        da, db = dt.date.fromisoformat(str(a)), dt.date.fromisoformat(str(b))
    except ValueError:
        return None
    m = MONTHS if lang == "ar" else MONTHS_EN
    fa = f"{da.day} {m[da.month - 1]}" + ("" if da.year == db.year else f" {da.year}")
    return f"{fa} {'إلى' if lang == 'ar' else 'to'} {db.day} {m[db.month - 1]} {db.year}"


def human_date(d, lang):
    """«25 سبتمبر 2026» / "25 September 2026" — never a bare ISO date an RTL run would reverse."""
    try:
        x = dt.date.fromisoformat(str(d))
    except ValueError:
        return str(d or "")
    return f"{x.day} {(MONTHS if lang == 'ar' else MONTHS_EN)[x.month - 1]} {x.year}"


def clean_reader_name(name):
    """A raw reader cinema name made presentable when cinemas.yaml has no entry: «Al Foah -Al Ain» -> «Al Foah - Al Ain»."""
    n = re.sub(r"\s*-\s*", " - ", (name or "").strip())
    return re.sub(r"\s+", " ", n).strip()


def load_cinema_names(path):
    if not path or not os.path.exists(path): return {}
    return (yaml.safe_load(open(path, encoding="utf-8")) or {}).get("cinemas") or {}


# ---------------------------------------------------------------- genres
def gslug(g):
    s = re.sub(r"[^a-z0-9]+", "-", str(g or "").lower()).strip("-")
    return re.sub(r"-film$", "", s)


def genre_label(key, lang):
    """genres.py (Task 2) when it has the key, else the local table, else the key itself."""
    if _genres is not None:
        fn = getattr(_genres, "label", None)
        if callable(fn):
            try:
                v = fn(key, lang)
                if v: return v
            except Exception:
                pass
        for name in ("LABELS", "GENRES", "labels"):
            m = getattr(_genres, name, None)
            if isinstance(m, dict) and key in m:
                v = m[key]
                if isinstance(v, dict): v = v.get(lang)
                elif isinstance(v, (list, tuple)): v = v[0 if lang == "ar" else 1] if len(v) > 1 else v[0]
                if v: return str(v)
    p = GENRE_FALLBACK.get(key)
    return L(p, lang) if p else key.replace("-", " ").capitalize()


def genre_keys(f):
    """A film's genres as lowercase keys, whatever shape the data has."""
    g = f.get("genre_keys") or f.get("genres")
    if isinstance(g, dict):
        g = g.get("keys") or g.get("en") or []
    fold = getattr(_genres, "genre_keys", None) if _genres is not None else None
    if callable(fold):   # genres.py folds raw labels («horror film», «Survival Thriller») onto its keys
        try:
            return [k for k in fold(list(g or [])) if k != "other"]
        except Exception:
            pass
    return [k for k in dict.fromkeys(gslug(x) for x in g or []) if k]


def genre_words(genres, lang):
    """Enriched genres are {"ar": [...], "en": [...]}; older data has a plain English list; Task 2 keys."""
    if isinstance(genres, dict):
        words = genres.get(lang) or ([] if lang == "en" else [GENRES.get(g, g) for g in genres.get("en") or []])
    else:
        words = [GENRES[g] if lang == "ar" and g in GENRES else (g if lang == "en" and g in GENRES else genre_label(gslug(g), lang))
                 for g in genres or []]
    return [w for w in words if w]


def film_flags(f):
    """(family, kids): the data's own flags when present (Task 2), else from the UAE rating + genre."""
    r = str(f.get("rating") or "").upper().replace(" ", "")
    keys = set(genre_keys(f))
    fam = f.get("family") if f.get("family") is not None else r in {x.replace(" ", "") for x in FAMILY_RATINGS}
    kids = f.get("kids") if f.get("kids") is not None else (r in KIDS_RATINGS and bool(keys & {"animation", "family"}))
    return bool(fam), bool(kids)


def hue(fid):
    """A stable dark tile colour from the film id (for a film with no poster colour)."""
    h = int(hashlib.sha1(fid.encode()).hexdigest()[:4], 16) / 0xFFFF
    r, g, b = colorsys.hls_to_rgb(h, 0.2, 0.35)
    return "#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))


# ---------------------------------------------------------------- relative time (same wording as cinema.js)
def ago(at, now, lang):
    mins = max(0, int((now - at).total_seconds() // 60))
    if lang == "en":
        if mins < 60: return f"{max(mins, 1)} min ago"
        h = mins // 60
        if h < 24: return f"{h} hour{'s' if h != 1 else ''} ago"
        d = h // 24; return f"{d} day{'s' if d != 1 else ''} ago"
    if mins < 60:
        n = max(mins, 1)
        return "قبل دقيقة" if n == 1 else "قبل دقيقتين" if n == 2 else f"قبل {n} دقايق" if n <= 10 else f"قبل {n} دقيقة"
    h = mins // 60
    if h < 24:
        return "قبل ساعة" if h == 1 else "قبل ساعتين" if h == 2 else f"قبل {h} ساعات" if h <= 10 else f"قبل {h} ساعة"
    d = h // 24
    return "قبل يوم" if d == 1 else "قبل يومين" if d == 2 else f"قبل {d} أيام" if d <= 10 else f"قبل {d} يوم"


def parse_iso(s):
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone(dt.timedelta(hours=4)))


# ---------------------------------------------------------------- discounts
def load_discounts(path):
    d = _disc.load(path) or {}
    d.setdefault("cards", []); d.setdefault("rules", {})
    return d


def official_rules(rules):
    """Only rules the chain or the card issuer states themselves (confidence official)."""
    return {ch: {c: r for c, r in (cs or {}).items() if isinstance(r, dict) and r.get("confidence") == "official"}
            for ch, cs in (rules or {}).items()}


def confirmed_cards(disc, today):
    """Cards with at least one current official discount — discounts.confirmed_cards() when it exists."""
    fn = getattr(_disc, "confirmed_cards", None)
    if callable(fn):   # discounts.confirmed_cards(rules, today) -> card ids
        ids = set(fn(disc["rules"], today) or [])
        return [c for c in disc["cards"] if c["id"] in ids]
    ok = {card for ch, cs in official_rules(disc["rules"]).items() for card, r in cs.items() if _disc.state(r, today) == "ok"}
    return [c for c in disc["cards"] if c["id"] in ok]


def rule_for(rules, chain, card):
    return _disc.rule(rules, chain, card)


def rule_state(r, today):
    return _disc.state(r, today)


def weak(r):
    return bool(r) and r.get("confidence") in ("third-party", "unconfirmed")


def after(price, chain, hall, card, rules, today, hall_key=None, cinema=None):
    """(price after `card` at `chain` in `hall` (a hall code; `hall_key` its halls.yaml key) at `cinema`
    on `today`, state) — discounts.compute(), the one semantics cinema.js mirrors."""
    a, st, _ = _disc.compute(price, chain, hall, card, rules, hall_key=hall_key, cinema=cinema, today=today)
    return a, st


def rule_offer(r, lang):
    if r.get("type") == "bogo": return "تذكرتين بسعر وحدة" if lang == "ar" else "Buy one, get one"
    v = f'{float(r.get("value") or 0):g}'
    if r.get("type") == "fixed": return f"التذكرة بـ{v} درهم" if lang == "ar" else f"Tickets at AED {v}"
    return f"خصم {v}%" if lang == "ar" else f"{v}% off"


def rule_terms(r, lang):
    t = []
    note = (r.get("note_ar") or "") if lang == "ar" else ""
    if r.get("box_office_only") and "الشباك" not in note: t.append("من الشباك فقط" if lang == "ar" else "Box office only")
    if r.get("max_tickets") and not re.search("تذاكر|تذكرة", note): t.append(f'{r["max_tickets"]} تذاكر بالحد' if lang == "ar" else f'Up to {r["max_tickets"]} tickets')
    inc, exc = r.get("included_halls"), r.get("excluded_halls") or r.get("halls_excluded")
    hn = lambda hs: [("القاعة العادية" if h == "Standard" else h) if lang == "ar" else h for h in hs]
    if inc: t.append("يشمل " + "، ".join(hn(inc)) + " فقط" if lang == "ar" else "Only " + ", ".join(inc))
    if exc: t.append(("ما يشمل " + "، ".join(hn(exc))) if lang == "ar" else "Excludes " + ", ".join(exc))
    if r.get("included_cinemas") is not None: t.append("في فروع محددة بس" if lang == "ar" else "Selected branches only")
    if r.get("valid_until"): t.append((f'لين {r["valid_until"]}') if lang == "ar" else f'Until {r["valid_until"]}')
    if lang == "ar" and r.get("note_ar") and r.get("type"): t.append(r["note_ar"])
    return t


# ---------------------------------------------------------------- halls
class Halls:
    def __init__(self, path):
        self.y = (yaml.safe_load(open(path, encoding="utf-8")) or {}).get("chains", {}) if path and os.path.exists(path) else {}
        self._cache = {}

    def chain_name(self, chain, lang):
        c = self.y.get(chain) or {}
        return (c.get("name_ar") if lang == "ar" else c.get("name")) or chain.title()

    def match(self, chain, code, label):
        entries = (self.y.get(chain) or {}).get("halls", [])
        for e in entries:
            if e.get("match") and label and re.search(e["match"], label, re.I): return e
        for e in entries:
            if code in (e.get("codes") or []): return e
        return None

    def resolve(self, chain, code, label):
        """(key, display name, halls.yaml entry|None, clean) for a reader's hall code + raw label.

        Order: a halls.yaml entry for this chain (by label regex, then code) → Standard for format-only
        labels («2D», «NORMAL», «Screen 4») → the reader's hall code → the cleaned label. `clean` is
        False when the name came from a raw label (kept out of JSON-LD)."""
        ck = (chain, code, label)
        if ck in self._cache: return self._cache[ck]
        lab = clean_label(label)
        e = self.match(chain, code, lab)
        if e: r = (e["key"], e.get("name") or e["key"], e, True)
        elif code == "Standard" or (code in ("OTHER", "", None) and FORMAT_ONLY.match(lab or "2D")): r = ("Standard", "Standard", None, True)
        elif code and code != "OTHER": r = (code, code, None, True)
        else: r = (lab.upper(), lab, None, False)
        self._cache[ck] = r
        return r

    def key(self, chain, code, label):
        return self.resolve(chain, code, label)[0]

    def name(self, chain, code, label, lang):
        k, n, _, _ = self.resolve(chain, code, label)
        return ("عادية" if lang == "ar" else "Standard") if k == "Standard" else n


# a label that only names a projection format or a screen number is the regular hall
FORMAT_ONLY = re.compile(r"^(?:[234]D|[234]L|2D/3D|NORMAL|STANDARD|REGULAR|SILVER|DIGITAL|(?:SCREEN|HALL|CINEMA)\s*\d*|\d+)?$", re.I)


def clean_label(label):
    """Raw reader label -> a short display label: drops tooltip text glued on («Private CinemaiThis session
    can be…» -> «Private Cinema»), trailing screen numbers, and anything past 24 characters."""
    s = (label or "").strip()
    m = re.search(r"[a-z](i?)[A-Z]", s)      # a lower→upper run-on is where a tooltip was glued on (the «i» is its info icon)
    if m: s = s[:m.start(1)]
    s = re.split(r"\s*[(\[|:;.]\s*|\s+[-–—]\s+", s)[0]
    s = re.sub(r"\s+\d+$", "", re.sub(r"\s+", " ", s)).strip()
    if len(s) > 24: s = s[:24].rsplit(" ", 1)[0]
    return s


# ---------------------------------------------------------------- the site
class Site:
    noindex = False   # set by build(): PREVIEW=1

    def __init__(self, data, disc, halls, out):
        self.d, self.disc, self.h, self.out = data, disc, halls, out
        self.now = parse_iso(data.get("generated") or dt.datetime.now().isoformat())
        self.today = self.now.date().isoformat()
        self.tomorrow = (self.now.date() + dt.timedelta(days=1)).isoformat()
        self.rules = official_rules(disc["rules"])            # third-party/unconfirmed never published
        self.cards = confirmed_cards(disc, self.today)        # only cards with a current official discount
        self.films, self.cinemas = data.get("films", {}), data.get("cinemas", {})
        self.shows = [s for s in data.get("shows", []) if s.get("cinema") in self.cinemas and s.get("film") in self.films]
        for s in self.shows:  # a chain's booking URL is a link on our page: http(s) only, never javascript:
            if s.get("book") and not SAFE_URL.match(str(s["book"])): s["book"] = None
            if s.get("ends") and not HHMM.match(str(s["ends"])): s["ends"] = None
            if isinstance(s.get("subs"), (list, tuple)): s["subs"] = "+".join(str(x) for x in s["subs"] if x) or None
        for f in self.films.values():  # values that land in attributes or styles must not inject
            vd = f.get("verdict")
            if isinstance(vd, dict) and vd.get("verdict") not in VERDICT: f["verdict"] = dict(vd, verdict="unknown")
            for k in ("poster", "poster_2x"):
                # our mirror is a site-root path: made absolute here (og:image and JSON-LD need a full URL)
                if f.get(k) and OUR_POSTER.match(str(f[k])): f[k] = SITE + f[k]
                if f.get(k) and not SAFE_URL.match(str(f[k])): f[k] = None
            if f.get("poster_color") and not HEX.match(str(f["poster_color"])): f["poster_color"] = None
            if f.get("trailer") and not YT.match(str(f["trailer"])): f["trailer"] = None
        self.tpl = open(os.path.join(SRC, "page.html"), encoding="utf-8").read()
        self.urls, self.hashes, self.lastmod_path = [], {}, None
        self.names = load_cinema_names(os.path.join(ROOT, "cinemas.yaml"))
        h = hashlib.sha1()
        for dp, _, fs in sorted(os.walk(SRC)):
            for f in sorted(fs): h.update(open(os.path.join(dp, f), "rb").read())
        self.v = h.hexdigest()[:10]
        self.js = bundle_js()
        self.js_name = f"cinema.{hashlib.sha1(self.js.encode()).hexdigest()[:10]}.js"
        self.adhan = open(os.path.join(SRC, "js", "vendor", "adhan.umd.min.js"), encoding="utf-8").read()
        self.adhan_name = f"adhan.{hashlib.sha1(self.adhan.encode()).hexdigest()[:10]}.js"
        # an archived film (no longer showing) keeps its page as an archive, and appears nowhere else
        self.showing = [fid for fid, f in self.films.items() if f.get("status") != "archived"]
        self.shows = [s for s in self.shows if self.films[s["film"]].get("status") != "archived"]
        self._by_film, self._by_cin = {}, {}
        for s in self.shows:
            self._by_film.setdefault(s["film"], []).append(s); self._by_cin.setdefault(s["cinema"], []).append(s)
        self.today_count = {fid: sum(1 for s in ss if s["date"] == self.today) for fid, ss in self._by_film.items()}
        self._P, self._Pi, self._first_poster = [], {}, None

    # -------- names
    def cname(self, cid, lang):
        """cinemas.yaml «chain — mall» first; else the reader's Arabic name (ar); else its cleaned name."""
        n = self.names.get(cid) or {}
        c = self.cinemas[cid]
        return n.get(lang) or (c.get("name_ar") if lang == "ar" else None) or clean_reader_name(c.get("name")) or cid

    def cname_is_en(self, cid, lang):
        return lang == "ar" and not ARABIC.search(self.cname(cid, lang))

    def ftitle(self, fid, lang):
        f = self.films[fid]
        return (f.get("title_ar") if lang == "ar" else None) or f.get("title") or fid

    def title_attr(self, fid, lang):
        return ' lang="en" dir="ltr"' if lang == "ar" and not self.films[fid].get("title_ar") else ""

    def title_html(self, fid, lang, tag="b", cls="t"):
        return f'<{tag} class="{cls}"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</{tag}>'

    def hall_code_label(self, s):
        return s.get("hall") or "OTHER", s.get("hall_label") or ""

    def hkey(self, s):
        c = self.cinemas[s["cinema"]]["chain"]; code, label = self.hall_code_label(s)
        return self.h.key(c, code, label)

    def hname(self, s, lang):
        c = self.cinemas[s["cinema"]]["chain"]; code, label = self.hall_code_label(s)
        return self.h.name(c, code, label, lang)

    def fresh(self, chain, lang, always=False):
        ch = self.d.get("chains", {}).get(chain) or {}
        if not ch.get("at") or (ch.get("ok", True) and not always): return ""
        at = parse_iso(ch["at"])
        cls = "age stale" if not ch.get("ok", True) else "age"
        why = "" if ch.get("ok", True) else f' <span class="stale">{"— ما قدرنا نحدّث، هذي آخر أسعار قريناها" if lang == "ar" else "— the last refresh failed; these are the last prices we read"}</span>'
        return f'<span class="{cls}" data-at="{esc(ch["at"])}">{esc(L(T["updated"], lang))} {esc(ago(at, self.now, lang))}</span>{why}'

    # -------- price cells
    def pcell(self, aed, chain, code, hkey, cid, asof=None, lang="ar"):
        """A price cell cinema.js rewrites after the visitor's card. `asof` marks a price from the fallback
        table (prices.yaml): it carries its own date («السعر بتاريخ …») instead of the live freshness."""
        a = f' data-asof="{esc(asof)}"' if asof else ""
        return (f'<span class="p" data-aed="{money(aed)}" data-chain="{esc(chain)}" data-hall="{esc(code)}" data-hk="{esc(hkey)}" data-cin="{esc(cid)}"{a}>'
                f'<span class="num">{money(aed)}</span>{self.asof_html(asof, lang)}</span>')

    def asof_html(self, asof, lang):
        return f'<small class="asof">{dates(esc(L(T["asof"], lang).format(date=asof)))}</small>' if asof else ""

    @staticmethod
    def table_date(s):
        """The table entry's date for a show priced from prices.yaml, else None (a live price)."""
        return s.get("price_checked") if s.get("price_source") == "table" else None

    def box(self, lang):
        return f'<span class="na">{esc(L(T["box"], lang))}</span>'

    def cinema_prices(self, cid):
        """hall key -> {code, label, seats{seat: aed}, asof}: ONE day's prices per hall — today's when they are
        live, else the next day with live prices, else the fallback table (whose `asof`, the table entry's
        date, makes its cells say «السعر بتاريخ …» instead of borrowing the live freshness). Prices are
        sampled per show date, so days are never mixed (a Friday sample is not a Saturday price)."""
        out, buckets = {}, {}
        for s in self._by_cin.get(cid, []):
            k = self.hkey(s); code, label = self.hall_code_label(s)
            out.setdefault(k, {"code": code, "label": label, "seats": {}, "sample": s, "asof": None})
            asof = self.table_date(s)
            b = buckets.setdefault(k, {}).setdefault((asof is not None, s["date"] != self.today, s["date"]), {"seats": {}, "asof": asof})
            for p in s.get("prices") or []:
                if p.get("aed") and p["aed"] > 0:
                    cur = b["seats"].get(p["seat"])
                    b["seats"][p["seat"]] = p["aed"] if cur is None else min(cur, p["aed"])
        for k, bs in buckets.items():
            best = min((key for key, b in bs.items() if b["seats"]), default=None)   # live first, then today first
            if best is not None: out[k]["seats"], out[k]["asof"] = bs[best]["seats"], bs[best]["asof"]
        for code in self.cinemas[cid].get("halls") or []:
            if isinstance(code, str) and not any(v["code"] == code for v in out.values()) and code not in ("OTHER",):
                out.setdefault(self.h.key(self.cinemas[cid]["chain"], code, ""), {"code": code, "label": "", "seats": {}, "sample": None, "asof": None})
        order = lambda kv: (kv[1]["code"] != "Standard", min(kv[1]["seats"].values()) if kv[1]["seats"] else 9999)
        return dict(sorted(out.items(), key=order))

    def min_price(self, shows):
        best = None
        for s in shows:
            for p in s.get("prices") or []:
                if p.get("aed") and p["aed"] > 0 and (best is None or p["aed"] < best[0]): best = (p["aed"], s)
        return best

    def min_cell(self, shows, lang):
        """The cheapest known ticket among `shows` as a live price cell, or None."""
        b = self.min_price(shows)
        if not b: return None
        aed, s = b; code, _ = self.hall_code_label(s)
        return self.pcell(aed, self.cinemas[s["cinema"]]["chain"], code, self.hkey(s), s["cinema"], self.table_date(s), lang), s

    @staticmethod
    def end_offset(s):
        """Minutes from a show's start to its approximate end (0 when the data has no end)."""
        if not s.get("ends"): return 0
        h, m = map(int, s["time"].split(":")); eh, em = map(int, s["ends"].split(":"))
        return (eh * 60 + em - h * 60 - m) % 1440

    # -------- show ids, time buttons and the page's price lists (for the ticket)
    @staticmethod
    def sid(s):
        k = "|".join(str(s.get(x) or "") for x in ("cinema", "film", "date", "time", "hall", "hall_label", "book"))
        return hashlib.sha1(k.encode()).hexdigest()[:10]

    def pidx(self, s):
        pr = [[p["seat"], p["aed"]] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
        if not pr: return None
        k = json.dumps(pr)
        if k not in self._Pi: self._Pi[k] = len(self._P); self._P.append(pr)
        return self._Pi[k]

    def book_url(self, s):
        """The show's booking URL, else the chain's own site (a time always leads somewhere with no script)."""
        return s.get("book") or CHAIN_SITE.get(self.cinemas[s["cinema"]]["chain"]) or (SITE + P("ar", self.cinemas[s["cinema"]].get("city"), s["cinema"]))

    def is_past(self, s):
        return (s["date"], s["time"]) < (self.today, self.now.strftime("%H:%M"))

    def tbtn(self, s, lang, links=True, tag=True, on=False):
        """A showtime is a link to its booking page (works with no script); cinema.js prevents the navigation
        and opens the ticket instead. data-show is the show's stable id; data-p indexes the page's price lists
        (#cinema-p), data-book is the booking URL. A show already started when the data was built is plain text."""
        t = f'<small>{self.hall_html(s, lang)}</small>' if tag and self.hkey(s) != "Standard" else ""
        if self.is_past(s):
            return f'<span class="tm past" data-start="{esc(s["time"])}">{esc(s["time"])}{t}</span>'
        a = [f'data-show="{self.sid(s)}"', f'data-start="{esc(s["time"])}"']
        if s.get("ends"): a.append(f'data-ends="{esc(s["ends"])}"')
        if s.get("lang"): a.append(f'data-lang="{esc(s["lang"])}"')
        if s.get("subs"): a.append(f'data-subs="{esc(s["subs"])}"')
        if isinstance(s.get("seats_left"), int) and s["seats_left"] > 0: a.append(f'data-left="{s["seats_left"]}"')
        pi = self.pidx(s)
        if pi is not None: a.append(f'data-p="{pi}"')
        if self.table_date(s) and pi is not None: a.append(f'data-asof="{esc(self.table_date(s))}"')
        # plain (over budget): the chain's site instead of the long per-show URL
        href = self.book_url(s) if links else (CHAIN_SITE.get(self.cinemas[s["cinema"]]["chain"]) or self.book_url(s))
        if links and s.get("book"): a.append(f'data-book="{esc(s["book"])}"')
        return (f'<a class="tm{" on" if on else ""}" href="{esc(href)}" rel="noopener nofollow" target="_blank" {" ".join(a)}'
                f'{" aria-current=\"true\"" if on else ""}>{esc(s["time"])}{t}</a>')

    def times(self, shows, lang, tag_halls=False, links=True, day_label=True, on=None):
        """Showtimes, one row per day: <div class="times" data-d="…"><span class="dl">اليوم</span><button…>…"""
        out = []
        for d in sorted({s["date"] for s in shows}):
            lab = f'<span class="dl">{esc(L(T["today"] if d == self.today else T["tomorrow"] if d == self.tomorrow else (d, d), lang))}</span>' if day_label else ""
            items = "".join(self.tbtn(s, lang, links, tag_halls, on is not None and self.sid(s) == on)
                            for s in sorted((s for s in shows if s["date"] == d), key=lambda s: s["time"]))
            out.append(f'<div class="times" data-d="{d}">{lab}{items}</div>')
        return "".join(out)

    def times_compact(self, shows, lang, tag=False, day_label=True):
        """The bounded form: per day, the times still to come as text, one run per hall
        (<span class="tl" data-hk="IMAX"><small>IMAX</small> 13:00 15:30</span>). No script: the cinema's name
        links to its page, where every time books. cinema.js makes each time a button whose ticket it fills
        from the city's slice."""
        out = []
        for d in sorted({s["date"] for s in shows}):
            ds = [s for s in shows if s["date"] == d and not self.is_past(s)]
            if not ds: continue
            lab = f'<span class="dl">{esc(L(T["today"] if d == self.today else T["tomorrow"] if d == self.tomorrow else (d, d), lang))}</span>' if day_label else ""
            keys = sorted(dict.fromkeys(self.hkey(s) for s in ds), key=lambda k: k != "Standard")
            runs = []
            for k in keys:
                hs = [s for s in ds if self.hkey(s) == k]
                ts = " ".join(sorted({s["time"] for s in hs}))
                if tag and k != "Standard":
                    runs.append(f'<span class="tl" data-hk="{esc(k)}"><small>{self.hall_html(hs[0], lang)}</small> {ts}</span>')
                else:
                    runs.append(f'<span class="tl">{ts}</span>')
            out.append(f'<div class="times" data-d="{d}">{lab}{"".join(runs)}</div>')
        return "".join(out)

    def fit(self, render, modes, budget):
        """The first mode whose markup (with the page's price lists) fits `budget` bytes; else the last."""
        for mode in modes:
            self._P, self._Pi = [], {}
            html_ = render(mode)
            n = len(html_.encode()) + len(json.dumps(self._P, ensure_ascii=False, separators=(",", ":")).encode())
            if n <= budget: break
        return html_, mode

    @staticmethod
    def ld_size(graph):
        return len(json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).encode())

    def cname_html(self, cid, lang):
        """The cinema's name, marked English when an Arabic page has only the English name."""
        n = esc(self.cname(cid, lang))
        return f'<bdi lang="en">{n}</bdi>' if self.cname_is_en(cid, lang) else n

    def hall_html(self, s, lang):
        n = self.hname(s, lang)
        return f'<bdi lang="en">{esc(n)}</bdi>' if lang == "ar" and re.search(r"[A-Za-z]", n) else esc(n)

    # -------- posters
    def poster(self, fid, lang, cls="pst", eager=False, size=(342, 513), lazy=True, sizes=None):
        """The poster, or — when there is none (or it fails to load) — a typographic tile in the film's colour."""
        f = self.films[fid]
        pc = f.get("poster_color") or hue(fid)
        img = ""
        if f.get("poster"):
            first = self._first_poster is None and eager
            if first: self._first_poster, self._first_sizes = f, sizes or POSTER_SIZES.get(cls, POSTER_SIZES["pst"])
            # width descriptors + the size the tile is drawn at, so a desktop grid tile or a 72 px list poster
            # does not fetch the 684 px file on a 1x screen
            ss = (f' srcset="{esc(rel(f["poster"]))} 342w, {esc(rel(f["poster_2x"]))} 684w" sizes="{sizes or POSTER_SIZES.get(cls, POSTER_SIZES["pst"])}"'
                  if f.get("poster_2x") else "")
            # a real poster carries its own title: the tile's title stays underneath, hidden, and comes back
            # (the class drops) only if the image fails to load
            img = (f'<img src="{esc(rel(f["poster"]))}"{ss} width="{size[0]}" height="{size[1]}" alt="" decoding="async"'
                   + (' fetchpriority="high"' if first else ' loading="lazy"' if lazy else "") + ">")
            return (f'<span class="{cls} img" style="--pc:{pc}"><span class="pst-t" aria-hidden="true"{self.title_attr(fid, lang)}>'
                    f'{esc(self.ftitle(fid, lang))}</span>{img}</span>')
        return (f'<span class="{cls}" style="--pc:{pc}"><span class="pst-t"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span></span>')

    def backdrop(self, fid, hero=False):
        """The film's poster enlarged and blurred over its colour: there is no backdrop image in the data.
        Blurred 40 px, its resolution does not show: on a film page it asks for exactly what the hero poster
        resolves to (same srcset and sizes, so one download serves both — and not lazy: it is the page's largest
        paint); on the home hero (desktop only, hidden on a phone, so lazy) the 342 px file."""
        f = self.films[fid]
        pc = f.get("poster_color") or hue(fid)
        if f.get("poster"):
            ss = (f' srcset="{esc(rel(f["poster"]))} 342w, {esc(rel(f["poster_2x"]))} 684w" sizes="{POSTER_SIZES["pst hero"]}"'
                  if hero and f.get("poster_2x") else "")
            lz = "" if hero else ' loading="lazy"'
            img = f'<img src="{esc(rel(f["poster"]))}"{ss} alt="" width="342" height="513" decoding="async"{lz} onerror="this.remove()">'
            return f'<div class="bd" style="--pc:{pc}" aria-hidden="true">{img}</div>'
        # no poster: never a flat colour field — night, the velvet glow, and the film's typographic tile
        return (f'<div class="bd noimg" style="--pc:{pc}" aria-hidden="true"><span class="pst bd-t">'
                f'<span class="pst-t">{esc(self.ftitle(fid, "ar"))}</span></span></div>')

    def score(self, f, lang):
        rt = f.get("rt") or {}
        if rt.get("critics") is not None: return f'{"النقاد" if lang == "ar" else "Critics"} {num(str(rt["critics"]) + "%")}'
        if rt.get("audience") is not None: return f'{"الجمهور" if lang == "ar" else "Audience"} {num(str(rt["audience"]) + "%")}'
        return f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>' if f.get("rating") else ""

    def vword(self, fid, lang):
        v = (self.films[fid].get("verdict") or {}).get("verdict") or "unknown"
        return v, L(VERDICT.get(v, VERDICT["unknown"]), lang)

    # -------- page plumbing
    def card_chips(self, lang):
        gov = [c for c in self.cards if c.get("kind") == "gov"]; bank = [c for c in self.cards if c.get("kind") != "gov"]
        nm = lambda c: c["name_ar"] if lang == "ar" else c["name_en"]
        chips = [f'<button type="button" class="chip" data-card="" aria-pressed="true">{esc(L(T["nocard"], lang))}</button>']
        chips += [f'<button type="button" class="chip" data-card="{esc(c["id"])}" aria-pressed="false">{esc(nm(c))}</button>' for c in gov]
        if bank:
            opts = "".join(f'<option value="{esc(c["id"])}">{esc(nm(c))}</option>' for c in bank)
            chips.append(f'<label class="chip sel"><span class="vh">{"بطاقة بنك" if lang == "ar" else "Bank card"}</span>'
                         f'<select data-card><option value="">{"بطاقة بنك" if lang == "ar" else "Bank card"}</option>{opts}</select></label>')
        return (f'<div class="chips cards js-only" role="group" aria-label="{"البطاقة" if lang == "ar" else "Card"}">{"".join(chips)}</div>'
                f'<noscript><p class="nojs"><a href="{P(lang, "cards")}">{"خصم كل بطاقة في كل سينما" if lang == "ar" else "Every card’s discount at every cinema"}</a></p></noscript>')

    def me(self, lang, city=None, mode="home"):
        """The control sentence «أنا في [المدينة] وعندي [البطاقة]». The city is a disclosure of links to the
        city pages (works with no script); the cards are buttons cinema.js drives."""
        city = city or "dubai"
        links = "".join(f'<li><a href="{P(lang, c)}" data-city="{c}"{" aria-current=\"true\"" if c == city else ""}>{esc(L((a, e), lang))}</a></li>' for c, a, e in CITIES)
        pick = (f'<details class="citypick" data-citypick><summary><span data-city-name>{esc(L(CITY[city], lang))}</span></summary>'
                f'<ul class="pop">{links}</ul></details>')
        if mode == "cinema":
            q = f'<p class="me-q">{"وعندي" if lang == "ar" else "I have"}</p>'
        else:
            q = f'<div class="me-q">{"أنا في" if lang == "ar" else "I’m in"} {pick} {"وعندي" if lang == "ar" else "with"}</div>'
        now = ""
        if mode in ("home", "city"):
            now = (f'<a class="now" href="#tonight" data-now hidden><span class="now-tx"><span class="now-l">{esc(L(T["now_label"], lang))}</span>'
                   f'<span class="now-f" data-now-film></span><span class="now-w" data-now-where></span></span>'
                   f'<span class="flip" dir="ltr" data-now-time></span></a>')
        near = (f'<p class="near js-only"><button type="button" class="lnk" data-near>{"أقرب سينما لي" if lang == "ar" else "Nearest cinema to me"}</button>'
                f'<span class="near-m" data-near-msg aria-live="polite"></span></p>')
        return f'<div class="me me-{mode}" data-me>{q}{self.card_chips(lang)}{near}{now}</div>'

    def filters(self, lang, fids):
        """Genre chips (cinema.js): all, family, kids, and the four genres most films here share."""
        counts = {}
        for fid in fids:
            for k in genre_keys(self.films[fid]): counts[k] = counts.get(k, 0) + 1
        top = [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]]
        b = lambda attrs, label, on=False: f'<button type="button" class="chip" {attrs} aria-pressed="{"true" if on else "false"}">{esc(label)}</button>'
        chips = [b('data-filter="all"', "الكل" if lang == "ar" else "All", True),
                 b('data-filter="family"', "عائلي" if lang == "ar" else "Family"),
                 b('data-filter="kids"', "للأطفال" if lang == "ar" else "Kids")]
        chips += [b(f'data-filter="genre:{esc(k)}"', genre_label(k, lang)) for k in top]
        return f'<div class="chips filters js-only" role="group" aria-label="{"النوع" if lang == "ar" else "Genre"}">{"".join(chips)}</div>'

    def controls(self, lang, sort=True, prayer=False, who=True):
        """The second row cinema.js drives: «مع منو رايح؟» presets, «يخلص قبل», the sort, the prayer switch."""
        ar = lang == "ar"
        b = lambda attrs, label: f'<button type="button" class="chip" {attrs} aria-pressed="false">{esc(label)}</button>'
        out = []
        if who:
            ws = [("solo", "بروحي", "Just me"), ("friends", "ربعي", "Friends"), ("family", "العائلة", "Family"), ("kids", "العيال", "The kids")]
            out.append(f'<div class="ctl-g"><span class="ctl-l" id="who-{lang}">{"مع منو رايح؟" if ar else "Going with"}</span>'
                       f'<div class="chips who" role="group" aria-labelledby="who-{lang}">{"".join(b(f"data-who={chr(34)}{k}{chr(34)}", a if ar else e) for k, a, e in ws)}</div></div>')
        opts = [("", "أي وقت", "Any time"), ("21:00", "9 بالليل", "9 pm"), ("22:00", "10 بالليل", "10 pm"), ("23:00", "11 بالليل", "11 pm"), ("24:00", "12 بالليل", "Midnight")]
        out.append(f'<label class="ctl-g ends"><span class="ctl-l">{"يخلص قبل" if ar else "Ends before"}</span>'
                   f'<select data-ends-before="">{"".join(f"<option value={chr(34)}{v}{chr(34)}>{esc(a if ar else e)}</option>" for v, a, e in opts)}</select></label>')
        if sort:
            ss = [("price", "الأرخص لك", "Cheapest for you"), ("time", "الأقرب وقت", "Soonest"), ("verdict", "الأحسن تقييم", "Best reviewed")]
            out.append(f'<div class="ctl-g"><span class="ctl-l" id="sort-{lang}">{"رتّب" if ar else "Sort"}</span>'
                       f'<div class="chips sorts" role="group" aria-labelledby="sort-{lang}">{"".join(b(f"data-sort={chr(34)}{k}{chr(34)}", a if ar else e) for k, a, e in ss)}</div></div>')
        if prayer: out.append(self.prayer_switch(lang))
        return f'<div class="ctl js-only">{"".join(out)}</div>'

    def prayer_switch(self, lang):
        """«راعِ أوقات الصلاة» (off by default): cinema.js marks shows overlapping Maghrib / Isha, and can hide them."""
        ar = lang == "ar"
        lab = "راعِ أوقات الصلاة" if ar else "Mind prayer times"
        return (f'<div class="ctl-g prayer"><span id="pr-{lang}">{lab}</span>'
                f'<button type="button" class="switch" role="switch" aria-checked="false" data-prayer aria-labelledby="pr-{lang}"><i></i></button>'
                f'<button type="button" class="chip hide-clash" data-hide-clash aria-pressed="false" hidden>{"أخفِ العروض المتقاطعة" if ar else "Hide clashing shows"}</button>'
                f'<span class="pr-t" data-prayer-times aria-live="polite"></span></div>')

    def film_tile(self, fid, lang, shows, big=False, i=99, live=False):
        f = self.films[fid]; v, vw = self.vword(fid, lang)
        today = [s for s in shows if s["film"] == fid and s["date"] == self.today] or [s for s in shows if s["film"] == fid]
        mc = self.min_price(today) if live else self.min_cell(today, lang)
        cell = (f'<span class="pv"><span class="num">{money(mc[0])}</span></span>' if live else mc[0]) if mc else ""   # .pv: cinema.js reprices it
        price = (f'<span class="fp">{cell}</span><span class="fw">{self.cname_html(mc[1]["cinema"], lang)}</span>' if mc
                 else f'<span class="fp">{self.box(lang)}</span>')
        rr = f'<span class="rr">{esc(L(RERELEASE, lang))}</span>' if f.get("rerelease") else ""
        attrs = self.film_attrs(fid) + f' data-v="{v}"'
        attrs += f' data-runtime="{int(f["runtime"])}"' if f.get("runtime") else ""
        return (f'<a class="film v-{v}{" big" if big else ""}" href="{P(lang, "film", fid)}"{attrs}>'
                + self.poster(fid, lang, eager=True, lazy=i >= 1, sizes=POSTER_SIZES["pst big" if big else "pst"])
                + (f'<span class="fn"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</span>' if f.get("poster") else "")
                + f'<span class="fm"><span class="vw">{esc(vw)}</span><span class="sc">{self.score(f, lang)}</span></span>{rr}'
                + f'<span class="cheap" data-cheap>{price}</span></a>')

    def film_attrs(self, fid):
        """What cinema.js filters a film by: its id, genre keys and the family/kids flags."""
        f = self.films[fid]; fam, kids = film_flags(f)
        return f' data-fid="{esc(fid)}" data-genres="{esc(" ".join(genre_keys(f)))}" data-family="{int(fam)}" data-kids="{int(kids)}"'

    def crumbs(self, lang, *items):
        parts = [f'<a href="{P(lang)}">{esc(L(UI["s_mark"], lang))}</a>']
        for name, href in items:
            parts.append(f'<a href="{href}">{esc(name)}</a>' if href else f'<span>{esc(name)}</span>')
        return f'<nav class="crumbs" aria-label="{"المسار" if lang == "ar" else "Breadcrumb"}">{" / ".join(parts)}</nav>'

    def breadcrumb_ld(self, lang, *items):
        chain = [(L(UI["s_mark"], lang), SITE + P(lang))] + [(n, SITE + h) for n, h in items]
        return {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(chain)]}

    def ticket_shell(self):
        return '<aside class="ticket" id="ticket" data-ticket hidden></aside>'

    def ticket(self, s, lang, hidden=False):
        """The ticket for one show, server-rendered (no-script visitors see the prices); cinema.js refills it
        for whichever time is tapped: phone = bottom sheet, desktop = side panel."""
        cid, chain = s["cinema"], self.cinemas[s["cinema"]]["chain"]
        code, _ = self.hall_code_label(s); hk = self.hkey(s); asof = self.table_date(s)
        hidden = " hidden" if hidden else ""
        day = L(T["today"] if s["date"] == self.today else T["tomorrow"] if s["date"] == self.tomorrow else (s["date"], s["date"]), lang)
        lines = []
        if hk != "Standard": lines.append(f'<span class="tk-h">{self.hall_html(s, lang)}</span>')
        if s.get("ends"): lines.append(f'<span>{esc(L(T["ends"], lang).format(t=s["ends"]))}</span>')
        lg = s.get("lang") or self.films[s["film"]].get("lang")
        if lg:
            ln = lang_words(lg, lang)
            sb = lang_words(s["subs"], lang) if s.get("subs") else ""
            lines.append(f'<span>{esc(ln)}{("، ترجمة " + esc(sb) if lang == "ar" else ", " + esc(sb) + " subtitles") if sb else ""}</span>')
        seats = "".join(f'<tr><th scope="row"{" lang=\"en\"" if lang == "ar" and not ARABIC.search(p["seat"]) else ""}><bdi>{esc(p["seat"])}</bdi></th>'
                        f'<td>{self.pcell(p["aed"], chain, code, hk, cid, asof, lang)}</td></tr>'
                        for p in sorted((p for p in s.get("prices") or [] if (p.get("aed") or 0) > 0), key=lambda p: p["aed"]))
        seats = seats or f'<tr><td colspan="2">{self.box(lang)}</td></tr>'
        ftitle, cn = self.ftitle(s["film"], lang), self.cname(cid, lang)
        msg = f'{L(T["in_cinema"], lang).format(film=ftitle, cinema=cn)}، {day} {s["time"]}' if lang == "ar" else f'{L(T["in_cinema"], lang).format(film=ftitle, cinema=cn)}, {day} {s["time"]}'
        share = "https://wa.me/?text=" + quote(msg + "\n" + SITE + P(lang, "film", s["film"]), safe="")
        # the show's own booking page, else the chain's site (never the previous show's link)
        book = (f'<a class="book" href="{esc(self.book_url(s))}" rel="noopener nofollow" target="_blank" data-tk-book data-book="{esc(s.get("book") or "")}">'
                f'{esc(L(T["book_at"], lang).format(chain=self.h.chain_name(chain, lang)))}</a>')
        left = s.get("seats_left")
        left = f'<p class="tk-left" data-tk-seats>{esc(seats_left(int(left), lang))}</p>' if isinstance(left, int) and left > 0 else '<p class="tk-left" data-tk-seats hidden></p>'
        return (f'<aside class="ticket" id="ticket" data-ticket data-show="{self.sid(s)}" data-cin="{esc(cid)}" data-chain="{esc(chain)}"'
                f' role="dialog" aria-labelledby="tk-cin"{hidden}>'
                f'<div class="tk-top"><div class="tk-main"><p class="tk-cin" id="tk-cin" data-tk-cin>{self.cname_html(cid, lang)}</p>'
                f'<p class="tk-film" data-tk-film{self.title_attr(s["film"], lang)}>{esc(ftitle)}</p>'
                f'<p class="tk-when" data-tk-when>{"".join(lines)}</p>{left}</div>'
                f'<div class="tk-stub"><span data-tk-day>{esc(day)}</span><b dir="ltr" data-tk-time>{esc(s["time"])}</b></div></div>'
                f'<table class="tk-seats"><tbody data-tk-rows>{seats}</tbody></table>'
                f'<p class="tk-terms" data-tk-terms hidden></p><p class="tk-go" data-tk-go>{self.directions(self.cinemas[cid], lang)}</p>'
                f'<p class="vh" data-tk-live aria-live="polite"></p>'
                f'<div class="tk-act">{book}<a class="share" href="{esc(share)}" rel="noopener" target="_blank" data-tk-share data-share="{esc(msg)}">{esc(L(T["share"], lang))}</a></div>'
                f'<button type="button" class="tk-x js-only" data-tk-close aria-label="{"سكّر" if lang == "ar" else "Close"}"></button></aside>')

    def first_city_show(self, shows, cities):
        """The next show in the city the page shows first (Dubai, the script's default, when it is there)."""
        order = (["dubai"] if "dubai" in cities else []) + [c for c in cities if c != "dubai"]
        for c in order:
            n = self.next_show([s for s in shows if self.cinemas[s["cinema"]].get("city") == c])
            if n: return n
        return self.next_show(shows)

    def next_show(self, shows):
        """The first show still to come when the data was built (priced first), else the first at all."""
        hhmm = self.now.strftime("%H:%M")
        key = lambda s: (s["date"], s["time"])
        up = sorted((s for s in shows if (s["date"], s["time"]) >= (self.today, hhmm)), key=key)
        pool = up or sorted(shows, key=key)
        return next((s for s in pool if s.get("prices")), pool[0] if pool else None)

    def page(self, lang, parts, title, desc, body, graph, pagekind, attrs="", nav="films", og_image=None, path=None, robots=""):
        other = "en" if lang == "ar" else "ar"
        vals = {k: esc(L(v, lang)) for k, v in UI.items()}
        strings = {k: L(v, lang) for k, v in T.items()}
        strings["cities"] = {c: L((a, e), lang) for c, a, e in CITIES}
        strings["v"] = {k: L(v, lang) for k, v in VERDICT.items()}
        strings["cards"] = {c["id"]: (c["name_ar"] if lang == "ar" else c["name_en"]) for c in self.cards}
        strings["base"] = P(lang)
        strings["langs"] = {k: L(v, lang) for k, v in LANGS.items()}
        strings["ad"] = {ch: int((c or {}).get("ad_offset_min") or 15) for ch, c in (self.d.get("chains") or {}).items() if isinstance(c, dict)}
        strings["adhan"] = "/assets/" + self.adhan_name
        strings["days"] = sorted({s["date"] for s in self.shows})
        strings["sites"] = CHAIN_SITE   # a time with no booking URL of its own books on its chain's site   # the slice dates that exist (no 404 for a day not built)
        pre = [f'<link rel="preload" href="/assets/fonts/{f}" as="font" type="font/woff2" crossorigin>' for f in FONTS[lang]]
        fp = self._first_poster
        if fp and fp.get("poster"):
            ss = (f' imagesrcset="{esc(rel(fp["poster"]))} 342w, {esc(rel(fp["poster_2x"]))} 684w" imagesizes="{esc(self._first_sizes)}"'
                  if fp.get("poster_2x") else "")
            pre.insert(0, f'<link rel="preload" as="image" href="{esc(rel(fp["poster"]))}"{ss} fetchpriority="high">')
        pdata = (f'<script type="application/json" id="cinema-p">{json.dumps(self._P, ensure_ascii=False, separators=(",", ":"))}</script>'
                 if self._P else "")
        city = next((c for c in CITIES if c[0] in parts[:1]), None)
        if self.noindex: robots = NOINDEX      # a preview host is never indexed, whatever the page asked for
        vals.update({
            "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "locale": "ar_AE" if lang == "ar" else "en_US",
            "title": esc(title), "description": esc(desc),
            "url": SITE + P(lang, *parts), "url_ar": SITE + P("ar", *parts), "url_en": SITE + P("en", *parts),
            "alt": P(other, *parts), "alt_lang": other, "hub": P(lang),
            "cinemas_href": P(lang, city[0]) if city else P(lang) + "#cities", "thursday_href": P(lang),
            "cards_href": P(lang, "cards"), "halls_href": P(lang, "halls"),
            "c_films": ' aria-current="page"' if nav == "films" else "", "c_cinemas": ' aria-current="page"' if nav == "cinemas" else "",
            "c_cards": ' aria-current="page"' if nav == "cards" else "",
            "v": self.v, "js": "/assets/" + self.js_name, "page": pagekind, "attrs": attrs, "preload": "\n".join(pre), "robots": robots,
            "og_image": esc(og_image or f"{SITE}/assets/og-{lang}.png"),
            "jsonld": json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/"),
            "strings": json.dumps(strings, ensure_ascii=False).replace("</", "<\\/"),
            "body": body + pdata,
        })
        self.hashes[P(lang, *parts)] = hashlib.sha1((title + desc + body).encode()).hexdigest()[:12]
        out = re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals.get(m.group(1), m.group(0))), self.tpl)
        dest = path or os.path.join(self.out, *(["en"] if lang == "en" else []), *parts, "index.html")
        self.write(dest, out)
        if lang == "ar" and path is None: self.urls.append(parts)
        self._P, self._Pi, self._first_poster = [], {}, None

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # the site's digits are Western, always — a hand-typed ٣ in a yaml note is corrected here
        text = text.translate({0x0660 + i: 0x30 + i for i in range(10)} | {0x06F0 + i: 0x30 + i for i in range(10)})
        open(path, "w", encoding="utf-8", newline="\n").write(text)

    def posters_row(self, lang, fids, shows, heading, city_label="", prayer=False):
        tiles = "".join(self.film_tile(fid, lang, shows, big=i == 0, i=i, live=True) for i, fid in enumerate(fids))
        return (f'<section class="tonight wrap" id="tonight"><div class="sec-h"><h2>{esc(heading)}<span class="h-city" data-city-label>{esc(city_label)}</span></h2>'
                f'{self.filters(lang, fids)}</div>{self.controls(lang, prayer=prayer)}<div class="posters" data-films>{tiles}</div>'
                f'<p class="empty" data-empty hidden></p></section>')

    # ================================================================ pages
    def home(self):
        films = sorted(self.showing, key=lambda fid: (-self.today_count.get(fid, 0), fid))
        for lang in ("ar", "en"):
            by_city = {c: len([x for x in self.cinemas.values() if x.get("city") == c]) for c, _, _ in CITIES}
            body = ""
            if films:
                fid = films[0]; f = self.films[fid]; v, vw = self.vword(fid, lang)
                vd = f.get("verdict") or {}
                say = vd.get("ar") if lang == "ar" else vd.get("en")
                facts = [x for x in [self.score(f, lang),
                                     (f'{"الجمهور" if lang == "ar" else "Audience"} {num(str((f.get("rt") or {})["audience"]) + "%")}'
                                      if (f.get("rt") or {}).get("audience") is not None and (f.get("rt") or {}).get("critics") is not None else ""),
                                     (num(f["runtime"]) + (" دقيقة" if lang == "ar" else " min")) if f.get("runtime") else ""] if x]
                mc = self.min_cell(self._by_film.get(fid, []), lang)
                trailer = (f'<a class="btn ghost" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                           f'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>{"العرض الترويجي" if lang == "ar" else "Trailer"}</a>') if f.get("trailer") else ""
                feat = (f'<div class="feat"><p class="eyebrow">{"الأكثر عرضاً الليلة" if lang == "ar" else "Most shown tonight"}</p>'
                        f'<p class="feat-t"{self.title_attr(fid, lang)}><a href="{P(lang, "film", fid)}">{esc(self.ftitle(fid, lang))}</a></p>'
                        f'<p class="feat-m"><span class="vw v-{v}">{esc(vw)}</span>{"".join(f"<span>{x}</span>" for x in facts)}</p>'
                        + (f'<p class="feat-s">{dates(esc(say))}</p>' if say else "")
                        + f'<p class="feat-a"><a class="btn light" href="{P(lang, "film", fid)}">{"الأوقات والأسعار" if lang == "ar" else "Times and prices"}'
                        + (f'<span class="from" data-from="{esc(fid)}">{"من" if lang == "ar" else "from"} {mc[0]} {esc(L(T["aed"], lang))}</span>' if mc else "")
                        + f'</a>{trailer}</p></div>')
                body += f'<section class="hero">{self.backdrop(fid)}<div class="wrap hero-in">{feat}{self.me(lang, "dubai", "home")}</div></section>'
            else:
                body += f'<section class="hero"><div class="wrap hero-in">{self.me(lang, "dubai", "home")}</div></section>'
            body += (f'<h1 class="vh">{"كل سينما في الإمارات، والسعر بعد خصم بطاقتك" if lang == "ar" else "Every cinema in the UAE, priced after your card discount"}</h1>')
            body += self.posters_row(lang, films, self.shows, "الليلة" if lang == "ar" else "Tonight")
            body += (f'<section class="wrap cities" id="cities"><h2>{"السينمات حسب المدينة" if lang == "ar" else "Cinemas by city"}</h2><ul class="clist">'
                     + "".join(f'<li><a href="{P(lang, c)}">{esc(L((a, e), lang))}</a> <span class="n">{num(by_city[c])} {"سينما" if lang == "ar" else ("cinema" if by_city[c] == 1 else "cinemas")}</span></li>' for c, a, e in CITIES)
                     + '</ul></section>')
            hn = self.first_city_show(self.shows, ["dubai"])
            body += self.cards_strip(lang) + self.sources(lang) + (self.ticket(hn, lang, hidden=True) if hn else self.ticket_shell())
            title = ("سينما الإمارات اليوم — الأفلام والأسعار وخصم فزعة وإسعاد" if lang == "ar"
                     else "UAE cinemas today — films, ticket prices and card discounts")
            desc = ("مواعيد أفلام اليوم في كل سينمات الإمارات، سعر التذكرة لكل قاعة وفئة، والسعر بعد خصم فزعة وإسعاد وعروض البنوك، وهل الفيلم يستاهل."
                    if lang == "ar" else "Today’s showtimes at every UAE cinema, the ticket price per hall and seat class, the price after Fazaa, Esaad and bank offers, and whether the film is worth it.")
            graph = [{"@type": "WebSite", "name": L(UI["s_mark"], lang), "url": SITE + P(lang), "inLanguage": lang},
                     {"@type": "ItemList", "name": "Films", "itemListElement": [
                         {"@type": "ListItem", "position": i + 1, "url": SITE + P(lang, "film", fid), "name": self.ftitle(fid, lang)} for i, fid in enumerate(films)]},
                     self.breadcrumb_ld(lang)]
            self.page(lang, (), title, desc, body, graph, "home")

    def cards_strip(self, lang):
        gov = [c for c in self.cards if c.get("kind") == "gov"]
        bank = [c for c in self.cards if c.get("kind") != "gov"]
        a = lambda c: f'<a href="{P(lang, "cards", c["id"])}">{esc(c["name_ar"] if lang == "ar" else c["name_en"])}</a>'
        return (f'<section class="wrap cardsx"><h2>{"خصم بطاقتك في السينما" if lang == "ar" else "Your card at the cinema"}</h2>'
                f'<p class="lead">{"وين تنفع كل بطاقة، كم تخصم، وشروطها، ومتى تحققنا منها. نعرض بس الخصومات اللي أعلنتها السينما أو البطاقة نفسها." if lang == "ar" else "Where each card works, how much it takes off, the conditions and when we checked. Only discounts the cinema or the card issuer states themselves."}</p>'
                + (f'<p class="links"><span>{"حكومية" if lang == "ar" else "Government"}</span> {" ".join(a(c) for c in gov)}</p>' if gov else "")
                + (f'<p class="links"><span>{"بنوك" if lang == "ar" else "Banks"}</span> {" ".join(a(c) for c in bank)}</p>' if bank else "")
                + f'<p class="links more"><a href="{P(lang, "cards")}">{"كل البطاقات في جدول واحد" if lang == "ar" else "All cards in one table"}</a> <a href="{P(lang, "halls")}">{"القاعات المميزة، شو فيها؟" if lang == "ar" else "Premium halls, explained"}</a></p></section>')

    def sources(self, lang):
        rows = []
        for chain, ch in sorted(self.d.get("chains", {}).items()):
            at = parse_iso(ch["at"]) if ch.get("at") else None
            state = ("" if ch.get("ok", True) else f' <span class="stale">{"ما قدرنا نحدّث آخر مرة" if lang == "ar" else "last refresh failed"}</span>')
            rows.append(f'<li><b>{esc(self.h.chain_name(chain, lang))}</b> '
                        + (f'<span class="age" data-at="{esc(ch["at"])}">{esc(L(T["updated"], lang))} {esc(ago(at, self.now, lang))}</span>' if at else "")
                        + state + '</li>')
        return (f'<section class="wrap srcs"><h2>{"من وين الأسعار" if lang == "ar" else "Where the prices come from"}</h2>'
                f'<p class="hint">{"من نظام الحجز عند كل سينما، ثلاث مرات باليوم. إذا ما حصلنا السعر نكتب «السعر في الشباك»، وما نخمّن." if lang == "ar" else "From each chain’s booking system, three times a day. When we can’t read a price we say «price at the box office» — we never guess."}</p>'
                f'<ul class="chains">{"".join(rows)}</ul></section>')

    # -------------------------------------------------- city
    def city_pages(self):
        for city, ar, en in CITIES:
            cids = [cid for cid, c in self.cinemas.items() if c.get("city") == city]
            shows = [s for cid in cids for s in self._by_cin.get(cid, [])]
            today = [s for s in shows if s["date"] == self.today]
            fids = sorted({s["film"] for s in today}, key=lambda f: (-sum(1 for s in today if s["film"] == f), self.ftitle(f, "en")))
            for lang in ("ar", "en"):
                cn = L((ar, en), lang)
                body = f'<section class="head wrap">{self.crumbs(lang, (cn, None))}'
                body += f'<h1 class="pt">{"سينما " + cn + " اليوم" if lang == "ar" else "Cinemas in " + cn + " today"}</h1>'
                if not cids:
                    near = NEAR.get(city, "dubai"); nn = L(CITY[near], lang)
                    body += (f'<p class="lead">{f"ما عندنا بيانات سينما في {cn} لين الحين. أقرب مدينة عندنا: " if lang == "ar" else f"We have no cinema data for {cn} yet. Nearest city: "}'
                             f'<a href="{P(lang, near)}">{esc(nn)}</a>.</p></section>')
                    body += self.ticket_shell()
                else:
                    body += (f'<p class="lead">{f"{len(cids)} سينما و{len(fids)} فيلم اليوم. السعر لكل قاعة من السينما نفسها، وينحسب بعد خصم بطاقتك." if lang == "ar" else f"{len(cids)} cinemas and {len(fids)} films today. Every hall’s price comes from the cinema itself and is worked out after your card."}</p></section>')
                    body += f'<div class="wrap">{self.me(lang, city, "city")}</div>'
                    if fids: body += self.posters_row(lang, fids, today, "الليلة في " + cn if lang == "ar" else "Tonight in " + cn, prayer=True)
                    body += f'<section class="wrap"><h2>{"السينمات" if lang == "ar" else "Cinemas"}</h2><div class="rows">'
                    for cid in cids:
                        c = self.cinemas[cid]; pr = self.cinema_prices(cid)
                        # the lowest known price in any hall (an unpriced Standard hall must not hide a priced one)
                        low = min(((a, h["code"], k, h["asof"]) for k, h in pr.items() for a in h["seats"].values()), default=None)
                        halls = [k for k in pr if k != "Standard"]
                        hn = ("، " if lang == "ar" else ", ").join(self.h.name(c["chain"], pr[k]["code"], pr[k]["label"], lang) for k in halls)
                        body += (f'<div class="row cin" data-cin="{esc(cid)}"{self.geo_attrs(c)}><a class="nm" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a>'
                                 f'<span class="sub"><span data-dist></span>{("<bdi>" + esc(hn) + "</bdi>") if hn else ""} {self.fresh(c["chain"], lang)}</span>'
                                 f'<span class="from">{("من " if lang == "ar" else "from ") + self.pcell(low[0], c["chain"], low[1], low[2], cid, low[3], lang) if low else self.box(lang)}</span></div>')
                    body += '</div></section>'
                    cnx = self.next_show(today)
                    tk = self.ticket(cnx, lang) if cnx else self.ticket_shell()

                    def city_sched(mode, fids=fids, today=today, cids=cids, cn=cn, lang=lang, city=city, cnx=cnx):
                        """links / plain: every time a link; compact: times as text; digestN (a busy day): the first
                        N cinemas per film and a link to the film's page — cinema.js redraws the whole list from
                        the city's slice, so only a visitor with no script sees the digest."""
                        small = mode == "compact" or mode.startswith("digest")
                        sched = (f'<section><h2>{"اليوم في " + cn if lang == "ar" else "Today in " + cn}</h2>'
                                 f'<div class="sched"{f" data-sched={chr(34)}{mode.rstrip(chr(49) + chr(50) + chr(51))}{chr(34)}" if small else ""}>')
                        for fid in fids:
                            fs = [s for s in today if s["film"] == fid]
                            v, vw = self.vword(fid, lang)
                            # only the id: cinema.js reads the genres and flags from the film's tile above
                            sched += (f'<div class="srow" data-fid="{esc(fid)}"><div class="sf"><a href="{P(lang, "film", fid)}">{self.title_html(fid, lang, "b", "t")}</a>'
                                      f'<span class="vw v-{v}">{esc(vw)}</span></div><div class="sc">')
                            mine = [cid for cid in cids if any(s["cinema"] == cid and not (small and self.is_past(s)) for s in fs)]
                            shown = mine[:int(mode[-1])] if mode.startswith("digest") else mine
                            for cid in shown:
                                cs = [s for s in fs if s["cinema"] == cid]
                                if small:   # a relative link (the city page is the cinema's parent) and no chain: the slice has it
                                    sched += (f'<div class="scin" data-cin="{esc(cid)}"><a class="cn" href="{esc(cid)}/">{self.cname_html(cid, lang)}</a>'
                                              f'{self.times_compact(cs, lang, tag=True, day_label=False)}</div>')
                                else:
                                    tm = self.times(cs, lang, tag_halls=True, links=mode == "links", day_label=False, on=self.sid(cnx) if cnx else None)
                                    sched += f'<div class="scin" data-cin="{esc(cid)}" data-chain="{esc(self.cinemas[cid]["chain"])}"><a class="cn" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a>{tm}</div>'
                            if len(mine) > len(shown):
                                n = len(mine) - len(shown)
                                sched += (f'<a class="more" href="{P(lang, "film", fid)}">{f"و{n} سينما ثانية" if lang == "ar" else f"and {n} more cinemas"}</a>')
                            sched += '</div></div>'
                        return sched + '</div></section>'
                    graph0 = [{"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": self.theater_ld(c, lang)} for i, c in enumerate(cids)]}]
                    left = PAGE_TARGET - CHROME - len(body.encode()) - len(tk.encode()) - self.ld_size(graph0) - 600
                    sched, _ = self.fit(city_sched, ("links", "plain", "compact", "digest3", "digest2", "digest1"), left)
                    body += f'<div class="wrap split"><div class="main">{sched}</div>{tk}</div>'
                title = (f"سينما {cn} اليوم — الأفلام والأسعار وخصم فزعة" if lang == "ar" else f"{cn} cinemas today — films, prices and card discounts")
                names = ("، " if lang == "ar" else ", ").join(self.cname(c, lang) for c in cids[:6])
                desc = (f"أفلام سينمات {cn} اليوم ومواعيدها، سعر التذكرة لكل قاعة، والسعر بعد خصم فزعة وإسعاد والبنوك. {names}" if lang == "ar"
                        else f"Films and showtimes at {cn} cinemas today, ticket prices per hall, and the price after Fazaa, Esaad and bank cards. {names}")
                graph = [{"@type": "ItemList", "name": title, "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "item": self.theater_ld(cid, lang)} for i, cid in enumerate(cids)]},
                    self.breadcrumb_ld(lang, (cn, P(lang, city)))]
                self.page(lang, (city,), title, desc, body, graph, "city", f' data-city="{city}" data-chains="{" ".join(sorted({self.cinemas[c]["chain"] for c in cids}))}"', nav="cinemas")

    def geo_attrs(self, c):
        return f' data-lat="{float(c["lat"])}" data-lng="{float(c["lng"])}"' if c.get("lat") is not None and c.get("lng") is not None else ""

    def directions(self, c, lang):
        """«الوصول»: Google Maps and Waze to the cinema's coordinates (or its maps link)."""
        if c.get("lat") is not None and c.get("lng") is not None:
            ll = f'{float(c["lat"])},{float(c["lng"])}'
            g, w = f"https://www.google.com/maps/dir/?api=1&destination={ll}", f"https://waze.com/ul?ll={ll}&navigate=yes"
        else:
            m = c.get("maps") if SAFE_URL.match(str(c.get("maps") or "")) else None
            g, w = m or ("https://www.google.com/maps/search/?api=1&query=" + quote(c.get("name") or "")), None
        out = f'<a href="{esc(g)}" rel="noopener" target="_blank" lang="en">Google Maps</a>'
        if w: out += f'{"، " if lang == "ar" else ", "}<a href="{esc(w)}" rel="noopener" target="_blank" lang="en">Waze</a>'
        return f'<span class="go" data-go>{"الاتجاهات:" if lang == "ar" else "Directions:"} {out}</span>'

    def theater_ld(self, cid, lang):
        c = self.cinemas[cid]
        t = {"@type": "MovieTheater", "name": self.cname(cid, lang), "url": SITE + P(lang, c["city"], cid),
             "address": {"@type": "PostalAddress", "streetAddress": c.get("address") or "", "addressLocality": L(CITY.get(c["city"], (c["city"], c["city"])), lang), "addressCountry": "AE"}}
        if c.get("lat") and c.get("lng"): t["geo"] = {"@type": "GeoCoordinates", "latitude": c["lat"], "longitude": c["lng"]}
        return t

    def screening_ld(self, s, lang):
        e = {"@type": "ScreeningEvent", "name": self.ftitle(s["film"], lang), "startDate": f'{s["date"]}T{s["time"]}:00+04:00',
             "location": {k: v for k, v in self.theater_ld(s["cinema"], lang).items() if k in ("@type", "name", "url", "address")},
             "workPresented": {"@type": "Movie", "name": self.films[s["film"]].get("title") or s["film"]},
             "eventStatus": "https://schema.org/EventScheduled"}
        chain = self.cinemas[s["cinema"]]["chain"]; code, label = self.hall_code_label(s)
        key, name, _, clean = self.h.resolve(chain, code, label)
        if clean: e["videoFormat"] = name       # never a raw reader label
        lg = s.get("lang") or self.films[s["film"]].get("lang")
        if BCP47.get(lg): e["inLanguage"] = BCP47[lg]
        ps = [p["aed"] for p in s.get("prices") or [] if p.get("aed")]
        if ps: e["offers"] = {"@type": "Offer", "price": money(min(ps)), "priceCurrency": "AED", "url": s.get("book") or SITE, "availability": "https://schema.org/InStock"}
        return e

    # -------------------------------------------------- cinema (the second flow: cinema → films → times → ticket)
    def cinema_pages(self):
        for cid, c in self.cinemas.items():
            city, chain = c.get("city"), c["chain"]
            pr = self.cinema_prices(cid)
            shows = self._by_cin.get(cid, [])
            nxt = self.next_show(shows)
            for lang in ("ar", "en"):
                cn, name = L(CITY.get(city, (city, city)), lang), self.cname(cid, lang)
                body = f'<section class="head wrap">{self.crumbs(lang, (cn, P(lang, city)), (name, None))}'
                body += f'<h1 class="pt"{" lang=\"en\"" if self.cname_is_en(cid, lang) else ""}>{esc(name)}</h1>'
                # the name already says the mall; the reader's address is English, isolated
                addr = esc(c.get("address") or ("" if cid in self.names else c.get("mall")) or "")
                body += (f'<p class="lead">{f"<bdi lang=\"en\">{addr}</bdi>" if addr else ""}</p>'
                         f'<p class="meta">{self.directions(c, lang)} {self.fresh(chain, lang, always=True)}</p></section>')
                body += f'<div class="wrap">{self.me(lang, city, "cinema")}</div>'
                body += '<div class="wrap split"><div class="main">'
                cfids = sorted({s["film"] for s in shows})
                body += f'<div class="sec-h cin-h">{self.filters(lang, cfids)}</div>{self.controls(lang, prayer=True)}<p class="empty" data-empty hidden></p>'
                # halls: explained + prices
                rest = ''
                rest += f'<section><h2>{"القاعات والأسعار" if lang == "ar" else "Halls and prices"}</h2><div class="halls">'
                for k, h in pr.items():
                    e = self.h.match(chain, h["code"], h["label"])
                    hn = self.h.name(chain, h["code"], h["label"], lang)
                    what = (e.get("what_ar") if lang == "ar" else e.get("what_en")) if e else ""
                    note = ""
                    if e and e.get("confidence") == "low":
                        note = f' <small class="weak">{"ما تأكدنا من التفاصيل" if lang == "ar" else "details not confirmed"}</small>'
                    src = f' <a class="src" href="{esc(e["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>' if e and e.get("source") else ""
                    seats = "".join(f'<tr><th scope="row">{esc(seat)}</th><td>{self.pcell(aed, chain, h["code"], k, cid, h["asof"], lang)}</td></tr>'
                                    for seat, aed in sorted(h["seats"].items(), key=lambda x: x[1])) or f'<tr><td colspan="2">{self.box(lang)}</td></tr>'
                    rest += (f'<div class="hall"><h3{" lang=\"en\"" if lang == "ar" and re.search("[A-Za-z]", hn) else ""}>{esc(hn)}</h3>' + (f'<p>{dates(esc(what))}{note}{src}</p>' if what else "") +
                             f'<table class="prices"><thead><tr><th scope="col">{"الفئة" if lang == "ar" else "Seat"}</th><th scope="col">{"السعر" if lang == "ar" else "Price"} <small>{esc(L(T["aed"], lang))}</small></th></tr></thead><tbody>{seats}</tbody></table></div>')
                rest += f'</div><p class="hint"><a href="{P(lang, "halls")}">{"كل القاعات المميزة في الإمارات، مقارنة" if lang == "ar" else "Every premium hall in the UAE, compared"}</a></p></section>'
                # cards (confirmed only)
                rows = ""
                for card in self.cards:
                    r = rule_for(self.rules, chain, card["id"]); st = rule_state(r, self.today)
                    if st == "unchecked": continue
                    rows += self.card_row(card, chain, r, st, lang, P(lang, "cards", card["id"]))
                if rows:
                    rest += f'<section><h2>{"البطاقات في " + self.h.chain_name(chain, lang) if lang == "ar" else "Cards at " + self.h.chain_name(chain, lang)}</h2><div class="rows">{rows}</div></section>'
                rest += '</div>' + (self.ticket(nxt, lang) if nxt else self.ticket_shell()) + '</div>'
                # films with their times, today then tomorrow — as richly as fits what the rest of the page leaves
                th0 = self.theater_ld(cid, lang)
                th0["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                left = PAGE_TARGET - CHROME - len(body.encode()) - len(rest.encode()) - self.ld_size([th0]) - 600
                sched, _ = self.fit(lambda m: self.cinema_schedule(shows, lang, m, self.sid(nxt) if nxt else None), ("full", "today", "plain", "compact"), left)
                body += sched + rest
                title = (f"{name} — أسعار التذاكر ومواعيد اليوم وخصم البطاقات" if lang == "ar" else f"{name} — ticket prices, today’s showtimes and card discounts")
                desc = (f"مواعيد أفلام {name} اليوم، سعر التذكرة لكل قاعة وفئة، شو الفرق بين القاعات، والسعر بعد خصم فزعة وإسعاد والبنوك." if lang == "ar"
                        else f"Today’s showtimes at {name}, ticket prices per hall and seat class, what each hall offers, and the price after Fazaa, Esaad and bank cards.")
                th = self.theater_ld(cid, lang)
                th["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                graph = [th, self.breadcrumb_ld(lang, (cn, P(lang, city)), (name, P(lang, city, cid)))]
                self.page(lang, (city, cid), title, desc, body, graph, "cinema",
                          f' data-city="{city}" data-chains="{chain}" data-cin="{esc(cid)}"', nav="cinemas")

    def cinema_schedule(self, shows, lang, mode, on=None):
        """The films at one cinema: poster, title, verdict, then each hall's time buttons. mode full = today +
        tomorrow with booking URLs; today = today only; plain = today, no booking URLs on the buttons."""
        out = []
        days = ((self.today, ("اليوم", "Today")), (self.tomorrow, ("بكرة", "Tomorrow")))
        for day, lab in days[:2 if mode in ("full", "compact") else 1]:
            ds = [s for s in shows if s["date"] == day]
            if not ds: continue
            out.append(f'<section class="day" data-d="{day}"><h2>{esc(L(lab, lang))} <small>{esc(human_date(day, lang))}</small></h2><div class="cfilms">')
            fids = sorted({s["film"] for s in ds}, key=lambda f: (-sum(1 for s in ds if s["film"] == f), self.ftitle(f, "en")))
            for fid in fids:
                fs = [s for s in ds if s["film"] == fid]
                v, vw = self.vword(fid, lang)
                out.append(f'<div class="cf"{self.film_attrs(fid)} data-v="{v}"><a class="cf-p" href="{P(lang, "film", fid)}" tabindex="-1" aria-hidden="true">{self.poster(fid, lang, "pst sm")}</a>'
                           f'<div class="cf-b"><h3><a href="{P(lang, "film", fid)}"{self.title_attr(fid, lang)}>{esc(self.ftitle(fid, lang))}</a></h3>'
                           f'<p class="cf-m"><span class="vw v-{v}">{esc(vw)}</span>{self.score(self.films[fid], lang)}</p>')
                for k in dict.fromkeys(self.hkey(s) for s in fs):
                    hs = [s for s in fs if self.hkey(s) == k]
                    out.append(f'<div class="hl" data-hall="{esc(hs[0].get("hall") or "OTHER")}" data-hk="{esc(k)}"><span class="hn">{self.hall_html(hs[0], lang)}</span>'
                               + (self.times_compact(hs, lang, day_label=False) if mode == "compact" else
                                  self.times(hs, lang, links=mode != "plain", day_label=False, on=on)) + '</div>')
                out.append('</div></div>')
            out.append('</div></section>')
        if mode not in ("full", "compact"):
            out.append(f'<p class="hint">{"مواعيد بكرة تنزل هني الصبح." if lang == "ar" else "Tomorrow’s times appear here in the morning."}</p>')
        return "".join(out)

    def card_row(self, card, chain, r, st, lang, card_href=None, label=None):
        cname = label or (card["name_ar"] if lang == "ar" else card["name_en"])
        head = f'<a class="nm" href="{card_href}">{esc(cname)}</a>' if card_href else f'<span class="nm">{esc(cname)}</span>'
        if st == "ok":
            val = f'<b class="off{" txt" if r.get("type") in ("bogo", "fixed") else ""}">{dates(esc(rule_offer(r, lang)))}</b>'
            terms = rule_terms(r, lang)
        elif st == "expired":
            val = f'<span class="nil">{esc(L(T["expired"], lang))}</span>'; terms = [f'{"كان" if lang == "ar" else "Was"} {rule_offer(r, lang)}، {"لين" if lang == "ar" else "until"} {r.get("valid_until")}']
        elif st == "none_found":
            val = f'<span class="nil">{esc(L(T["none_found"], lang))}</span>'
            terms = [r["note_ar"]] if lang == "ar" and r.get("note_ar") and r["note_ar"] != T["none_found"][0] else []
        else:
            val = f'<span class="nil">{esc(L(T["unchecked"], lang))}</span>'; terms = []
        chk = (f' <a class="src" href="{esc(r["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>'
               f' <small class="chkd">{"تحققنا" if lang == "ar" else "checked"} {esc(human_date(r.get("checked"), lang))}</small>') if r and r.get("source") else ""
        return (f'<div class="row crd">{head}<span class="val">{val}</span>'
                f'<span class="sub">{dates(esc(("، " if lang == "ar" else ", ").join(str(t) for t in terms)))}{chk}</span></div>')

    # -------------------------------------------------- film (film → cinemas → times → ticket)
    def film_pages(self):
        for fid, f in self.films.items():
            shows = self._by_film.get(fid, [])
            vd = f.get("verdict") or {}; v = vd.get("verdict") or "unknown"
            cities = [c for c, _, _ in CITIES if any(self.cinemas[s["cinema"]].get("city") == c for s in shows)]
            for lang in ("ar", "en"):
                t = self.ftitle(fid, lang)
                attr = self.title_attr(fid, lang)
                head = self.crumbs(lang, (t, None)) + f'<h1 class="ft"{attr}>{esc(t)}</h1>'
                if lang == "ar" and f.get("title_ar") and f.get("title"): head += f'<p class="fte" lang="en" dir="ltr">{esc(f["title"])}</p>'
                if f.get("rerelease"):
                    yr = f' <span class="num">{esc(f["year"])}</span>' if f.get("year") else ""
                    head += f'<p class="rr">{esc(L(RERELEASE, lang))}{" — من سنة" if lang == "ar" and yr else (" — first released" if yr else "")}{yr}</p>'
                facts = []
                rt = f.get("rt") or {}
                # the ratings sit under the verdict as two plain items, in reading order (not a mixed-language «basis»)
                rates = [f'<span>{esc(a if lang == "ar" else e)} {num(str(rt[k]) + "%")}</span>'
                         for k, a, e in (("critics", "النقاد", "Critics"), ("audience", "الجمهور", "Audience")) if rt.get(k) is not None]
                if not rates and vd.get("basis"):   # no rt block: the verdict's basis carries them («RT 96% (249 ناقد)، الجمهور 91%»)
                    b = str(vd["basis"])
                    for rx, a, e in ((r"\bRT (\d{1,3})%", "النقاد", "Critics"), (r"(?:الجمهور|[Aa]udience) (\d{1,3})%", "الجمهور", "Audience")):
                        m = re.search(rx, b)
                        if m: rates.append(f'<span>{esc(a if lang == "ar" else e)} {num(m.group(1) + "%")}</span>')
                if f.get("runtime"): facts.append(("المدة", "Runtime", num(f["runtime"]) + (" د" if lang == "ar" else " min")))
                if f.get("rating"): facts.append(("التصنيف", "Rating", f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>'))
                if f.get("lang"): facts.append(("اللغة", "Language", esc(lang_words(f["lang"], lang))))
                subs = [s["subs"] for s in shows if s.get("subs")]
                if subs:
                    top = max(set(subs), key=subs.count)
                    facts.append(("الترجمة", "Subtitles", esc(lang_words(top, lang))))
                gw = genre_words(f.get("genres"), lang)
                if gw: facts.append(("النوع", "Genre", esc(("، " if lang == "ar" else ", ").join(gw))))
                say = vd.get("ar") if lang == "ar" else vd.get("en")
                info = (f'<div class="verdict v-{v}"><p class="word">{esc(L(VERDICT.get(v, VERDICT["unknown"]), lang))}</p>'
                        + (f'<p class="say">{dates(esc(say))}</p>' if say else "") + '</div>'
                        + (f'<p class="basis rates">{"".join(rates)}</p>' if rates else
                           f'<p class="basis"><bdi>{dates(esc(str(vd["basis"]).replace(" · ", "، " if lang == "ar" else ", ")))}</bdi></p>'
                           if vd.get("basis") and vd["basis"] not in ("manual", "unknown", "template") else ""))
                syn = (f.get("synopsis_ar") if lang == "ar" else None) or f.get("synopsis") or f.get("overview")
                if syn: info += f'<p class="syn"{" lang=\"en\" dir=\"ltr\"" if lang == "ar" and not f.get("synopsis_ar") else ""}>{esc(syn)}</p>'
                info += '<dl class="facts">' + "".join(f'<div><dt>{esc(a if lang == "ar" else e)}</dt><dd>{val}</dd></div>' for a, e, val in facts) + '</dl>'
                if f.get("trailer"):
                    info += (f'<p class="trl"><a class="btn ghost" href="https://www.youtube-nocookie.com/embed/{esc(f["trailer"])}" data-trailer="{esc(f["trailer"])}" rel="noopener" target="_blank">'
                             f'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>{"العرض الترويجي" if lang == "ar" else "Trailer"}</a></p>')
                if f.get("status") == "archived":
                    body = (f'<section class="fhero">{self.backdrop(fid, hero=True)}<div class="wrap fgrid">'
                            f'<div class="fposter">{self.poster(fid, lang, "pst hero", eager=True, size=(342, 513))}</div>'
                            f'<div class="finfo"><div class="fhead">{head}</div>{info}{self.archive_note(fid, lang)}</div></div></section>'
                            + self.similar(fid, lang))
                    title = (f"فيلم {t} — انتهى عرضه في سينما الإمارات، ويستاهل؟" if lang == "ar" else f"{t} — no longer in UAE cinemas; was it worth it?")
                    desc = (f"{t}: {L(VERDICT.get(v, VERDICT['unknown']), lang)}. التقييمات والمعلومات، ومتى عُرض في سينمات الإمارات، وشو المعروض الحين." if lang == "ar"
                            else f"{t}: {L(VERDICT.get(v, VERDICT['unknown']), lang)}. Ratings, facts, when it showed in UAE cinemas, and what is showing now.")
                    self.page(lang, ("film", fid), title, desc, body, [self.movie_ld(fid, lang), self.breadcrumb_ld(lang, (t, P(lang, "film", fid)))],
                              "film", f' data-fid="{esc(fid)}" data-archived="1"', og_image=f.get("poster_2x") or f.get("poster"))
                    continue
                info += self.me(lang, "dubai", "film")
                days = [d for d in (self.today, self.tomorrow) if any(s["date"] == d for s in shows)]
                tabs = "".join(f'<button type="button" class="chip" data-day="{d}" aria-pressed="{"true" if i == 0 else "false"}">{esc(L(T["today"] if d == self.today else T["tomorrow"], lang))}</button>' for i, d in enumerate(days))
                info += (f'<div class="bar js-only"><div class="chips days" role="group" aria-label="{"اليوم" if lang == "ar" else "Day"}">{tabs}</div></div>'
                         f'{self.controls(lang, sort=False, prayer=True)}<p class="empty" data-empty hidden></p>')
                nxt = self.first_city_show(shows, cities)
                if not cities:
                    sched = f'<p class="lead">{"ما لقينا عروض لهذا الفيلم في اليومين الجايين." if lang == "ar" else "No shows for this film in the next two days."}</p>'
                else:
                    # the schedule is most of the page's weight: render it as richly as fits what the rest leaves
                    graph0 = [self.movie_ld(fid, lang)] + [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:30]
                    fixed = len((head + info + self.backdrop(fid, hero=True) + self.poster(fid, lang, "pst hero", size=(342, 513))).encode())
                    left = PAGE_TARGET - CHROME - fixed - self.ld_size(graph0) - 4500 - 1200   # the ticket, the page's wrappers
                    # full, else compact: both keep today AND tomorrow (a page built late at night still has the next
                    # day's times when the visitor's «اليوم» has moved on)
                    sched, mode = self.fit(lambda m: self.film_schedule(shows, cities, lang, m, self.sid(nxt) if nxt else None), ("full", "compact"), left)
                    if mode not in ("full", "compact") and nxt and nxt["date"] != self.today: nxt = self.first_city_show([s for s in shows if s["date"] == self.today], cities) or nxt
                # a day tab only for a day the schedule actually has
                for d in days:
                    if f'data-d="{d}"' not in sched:
                        info = re.sub(r'<button type="button" class="chip" data-day="' + d + r'"[^>]*>[^<]*</button>', "", info)
                ticket = self.ticket(nxt, lang) if nxt else self.ticket_shell()
                body = (f'<section class="fhero">{self.backdrop(fid, hero=True)}<div class="wrap fgrid">'
                        f'<div class="fposter">{self.poster(fid, lang, "pst hero", eager=True, size=(342, 513))}</div>'
                        f'<div class="finfo"><div class="fhead">{head}</div>{info}<div class="cgs">{sched}</div></div>{ticket}</div></section>')
                vword = L(VERDICT.get(v, VERDICT["unknown"]), lang)
                title = (f"فيلم {t} في سينما الإمارات — المواعيد والأسعار، ويستاهل؟" if lang == "ar" else f"{t} in UAE cinemas — showtimes, prices and is it worth it?")
                desc = (f"{t}: {vword}. مواعيد العرض في سينمات الإمارات اليوم وبكرة، سعر التذكرة لكل قاعة، والسعر بعد خصم بطاقتك." if lang == "ar"
                        else f"{t}: {vword}. Showtimes in UAE cinemas today and tomorrow, ticket prices per hall, and the price after your card discount.")
                graph = [self.movie_ld(fid, lang)] + [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:30] + [self.breadcrumb_ld(lang, (t, P(lang, "film", fid)))]
                self.page(lang, ("film", fid), title, desc, body, graph, "film",
                          f' data-fid="{esc(fid)}" data-chains="{" ".join(sorted({self.cinemas[s["cinema"]]["chain"] for s in shows}))}"'
                          + (f' data-runtime="{int(f["runtime"])}"' if f.get("runtime") else ""),
                          og_image=f.get("poster_2x") or f.get("poster"))

    def movie_ld(self, fid, lang):
        f = self.films[fid]; t = self.ftitle(fid, lang)
        movie = {"@type": "Movie", "name": f.get("title") or t, "url": SITE + P(lang, "film", fid)}
        if BCP47.get(f.get("lang")): movie["inLanguage"] = BCP47[f["lang"]]
        if f.get("title_ar"): movie["alternateName"] = f["title_ar"]
        if f.get("runtime"): movie["duration"] = f"PT{int(f['runtime'])}M"
        if genre_words(f.get("genres"), "en"): movie["genre"] = genre_words(f.get("genres"), "en")
        if f.get("poster"): movie["image"] = f["poster"]
        if f.get("rating"): movie["contentRating"] = f["rating"]
        if f.get("year"): movie["dateCreated"] = str(f["year"])
        if f.get("trailer"): movie["trailer"] = {"@type": "VideoObject", "name": f.get("title") or t, "embedUrl": f"https://www.youtube-nocookie.com/embed/{f['trailer']}"}
        imdb = f["imdb"].get("id") if isinstance(f.get("imdb"), dict) else f.get("imdb")
        if imdb: movie["sameAs"] = f"https://www.imdb.com/title/{imdb}/"
        return movie

    def archive_note(self, fid, lang):
        """An archived film: when it showed (or that it has ended), and the way back to what is showing now."""
        f = self.films[fid]
        span = span_dates(f.get("first_seen"), f.get("last_seen"), lang) if f.get("first_seen") and f.get("last_seen") else None
        say = ((f"عُرض في سينمات الإمارات من {span}" if lang == "ar" else f"Shown in UAE cinemas from {span}") if span
               else ("انتهى عرضه في السينما" if lang == "ar" else "No longer showing in cinemas"))
        return (f'<div class="archived"><p class="arch-s">{esc(say)}</p>'
                f'<p><a class="btn light" href="{P(lang)}">{"المعروض الحين" if lang == "ar" else "Showing now"}</a></p></div>')

    def similar(self, fid, lang, n=6):
        """Up to n films showing now: shared genre keys first, then by verdict, then by how much they show."""
        mine = set(genre_keys(self.films[fid]))
        rank = {"yes": 0, "mixed": 1, "unknown": 2, "skip": 3}
        pool = [x for x in self.showing if x != fid and self._by_film.get(x)]
        pool.sort(key=lambda x: (-len(mine & set(genre_keys(self.films[x]))), rank.get(self.vword(x, lang)[0], 2), -self.today_count.get(x, 0), x))
        if not pool[:n]: return ""
        tiles = "".join(self.film_tile(x, lang, self._by_film.get(x, [])) for x in pool[:n])
        return (f'<section class="tonight wrap similar"><div class="sec-h"><h2>{"أفلام معروضة الحين تشبهه" if lang == "ar" else "Showing now, in the same vein"}</h2></div>'
                f'<div class="posters grid">{tiles}</div></section>')

    def film_schedule(self, shows, cities, lang, mode, on=None):
        """city → cinema group → hall: the hall's price (once, or per day when days differ), then the time
        buttons per day. mode full = today + tomorrow with booking URLs; today = today only; plain = unlinked."""
        days = [(self.today, ("اليوم", "Today"))] + ([(self.tomorrow, ("بكرة", "Tomorrow"))] if mode in ("full", "compact") else [])
        out = []
        for city in cities:
            cs = [s for s in shows if self.cinemas[s["cinema"]].get("city") == city and s["date"] in (d for d, _ in days)]
            if not cs: continue
            out.append(f'<section class="fcity" data-city="{city}"><h2><a href="{P(lang, city)}">{esc(L(CITY[city], lang))}</a></h2>')
            for cid in dict.fromkeys(s["cinema"] for s in cs):
                chain = self.cinemas[cid]["chain"]
                ss = [s for s in cs if s["cinema"] == cid]
                out.append(f'<div class="cg" data-cin="{esc(cid)}" data-chain="{esc(chain)}"{self.geo_attrs(self.cinemas[cid])}>'
                           f'<div class="cg-h"><h3><a href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a></h3>'
                           f'<p class="cg-m"><span data-dist></span>{self.fresh(chain, lang)}</p></div>')
                for k in dict.fromkeys(self.hkey(s) for s in ss):
                    hs = [s for s in ss if self.hkey(s) == k]
                    # prices are sampled per show date (weekday/weekend differ): one price per hall when every
                    # day agrees, else one per day — so a live Friday price never stands for Saturday

                    def price_for(group):
                        withp = [s for s in group if any((p.get("aed") or 0) > 0 for p in s.get("prices") or [])]
                        priced = next((s for s in withp if not self.table_date(s)), None) or next(iter(withp), None)  # live first
                        if not priced: return None
                        low = min((p for p in priced["prices"] if (p.get("aed") or 0) > 0), key=lambda p: p["aed"])
                        return (("من " if lang == "ar" else "from ")
                                + self.pcell(low["aed"], chain, priced.get("hall") or "OTHER", k, cid, self.table_date(priced), lang))
                    hd = [(d, lab) for d, lab in days if any(s["date"] == d for s in hs)]
                    per_day = {d: price_for([s for s in hs if s["date"] == d]) for d, _ in hd}
                    known = {v for v in per_day.values() if v}
                    split = len(known) > 1 or (len(known) == 1 and None in per_day.values())
                    pc = "" if split else (next(iter(known)) if known else self.box(lang))
                    rows = "".join(f'<div class="times" data-d="{d}"><span class="dl">{esc(L(lab, lang))}</span>'
                                   + (f'<span class="pr">{per_day[d] or self.box(lang)}</span>' if split else "")
                                   + (f'<span class="tl">{" ".join(sorted({s["time"] for s in hs if s["date"] == d and not self.is_past(s)}))}</span>' if mode == "compact" else
                                      "".join(self.tbtn(s, lang, mode != "plain", False, on == self.sid(s))
                                              for s in sorted((s for s in hs if s["date"] == d), key=lambda s: s["time"])))
                                   + '</div>' for d, lab in hd)
                    out.append(f'<div class="hl" data-hall="{esc(hs[0].get("hall") or "OTHER")}" data-hk="{esc(k)}">'
                               f'<p class="hl-n"><span class="hn">{self.hall_html(hs[0], lang)}</span>' + (f'<span class="pr">{pc}</span>' if pc else "") + f'</p>{rows}</div>')
                out.append('</div>')
            out.append('</section>')
        if mode not in ("full", "compact") and len(days) == 1:
            out.append(f'<p class="hint">{"مواعيد بكرة في صفحة كل سينما." if lang == "ar" else "Tomorrow’s times are on each cinema’s page."}</p>')
        return "".join(out)

    # -------------------------------------------------- cards
    def example(self, chain, card, lang):
        """«تذكرة ستار العادية 42.00 33.60» (struck, then paid) from the cheapest priced seat this chain sells
        in a hall the card covers."""
        best = None
        for s in self.shows:
            if self.cinemas[s["cinema"]]["chain"] != chain: continue
            for p in s.get("prices") or []:
                a, _ = after(p["aed"], chain, s.get("hall") or "OTHER", card, self.rules, self.today, self.hkey(s), s["cinema"])
                if a is not None and (best is None or (s.get("hall") == "Standard", -p["aed"]) > (best[2].get("hall") == "Standard", -best[0])):
                    best = (p["aed"], a, s, p["seat"])
        if not best: return ""
        aed, a, s, seat = best
        hn = self.hname(s, lang)
        what = (f"تذكرة {self.h.chain_name(chain, lang)} {'العادية' if s.get('hall') == 'Standard' else hn} ({seat})" if lang == "ar"
                else f"A {self.h.chain_name(chain, lang)} {'Standard' if s.get('hall') == 'Standard' else hn} ticket ({seat})")
        pp = f' <small class="per">{esc(L(T["per_person"], lang))}</small>' if (rule_for(self.rules, chain, card) or {}).get("type") == "bogo" else ""
        return f'<p class="ex">{esc(what)} <s class="num">{money(aed)}</s> <b class="num">{money(a)}</b> <small>{esc(L(T["aed"], lang))}</small>{pp}</p>'

    def card_pages(self):
        chains = sorted({c["chain"] for c in self.cinemas.values()} | set(self.rules))
        for card in self.cards:
            cid = card["id"]
            for lang in ("ar", "en"):
                cn = card["name_ar"] if lang == "ar" else card["name_en"]
                body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, None))}'
                body += f'<h1 class="pt">{"خصم " + cn + " على السينما" if lang == "ar" else cn + " discounts at UAE cinemas"}</h1>'
                ok = [ch for ch in chains if rule_state(rule_for(self.rules, ch, cid), self.today) == "ok"]
                okn = ("، " if lang == "ar" else ", ").join(self.h.chain_name(ch, lang) for ch in ok)
                body += (f'<p class="lead">{(f"تنفع اليوم في: {okn}." if ok else f"ما لقينا خصم قائم لبطاقة {cn} في السينمات اليوم.") if lang == "ar" else (f"Works today at: {okn}." if ok else f"We found no current {cn} discount at UAE cinemas.")}'
                         f' {"كل سطر تحت فيه مصدره وتاريخ آخر فحص." if lang == "ar" else "Every line below carries its source and the date we checked it."}</p></section>')
                body += '<section class="wrap"><div class="rows cardrows">'
                faq = []
                for ch in chains:
                    r = rule_for(self.rules, ch, cid); st = rule_state(r, self.today)
                    if st == "unchecked": continue
                    body += self.card_row(card, ch, r, st, lang, label=self.h.chain_name(ch, lang))
                    if st == "ok": body += self.example(ch, cid, lang)
                    chn = self.h.chain_name(ch, lang)
                    q = f"هل خصم {cn} يشتغل في {chn}؟" if lang == "ar" else f"Does {cn} work at {chn}?"
                    if st == "ok":
                        a = (f"إيه، {rule_offer(r, lang)}" + (f" ({'، '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". تحققنا {r.get('checked')}." if lang == "ar"
                             else f"Yes, {rule_offer(r, lang)}" + (f" ({', '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". Checked {r.get('checked')}.")
                    elif st == "none_found":
                        a = (f"ما لقينا خصم {cn} في {chn} وقت آخر فحص ({r.get('checked')})." if lang == "ar" else f"We found no {cn} discount at {chn} when we last checked ({r.get('checked')}).")
                    elif st == "expired":
                        a = (f"كان في {rule_offer(r, lang)} لين {r.get('valid_until')}، والعرض انتهى." if lang == "ar" else f"There was {rule_offer(r, lang)} until {r.get('valid_until')}; it has ended.")
                    else: continue
                    faq.append((q, a))
                body += '</div></section>'
                if faq:
                    body += (f'<section class="wrap faq"><h2>{"أسئلة" if lang == "ar" else "Questions"}</h2>'
                             + "".join(f"<details><summary>{esc(q)}</summary><p>{dates(esc(a))}</p></details>" for q, a in faq) + '</section>')
                body += self.cards_strip(lang)
                title = (f"خصم {cn} على السينما — {okn or 'السينمات'}، كم توفّر؟" if lang == "ar" else f"{cn} cinema discount in the UAE — where it works and how much you save")
                desc = (f"وين ينفع خصم {cn} في سينمات الإمارات، كم يخصم، شروطه، وأمثلة على السعر قبل وبعد الخصم — من المصدر الرسمي وبتاريخ الفحص." if lang == "ar"
                        else f"Where the {cn} discount works at UAE cinemas, how much it takes off, its conditions and before/after prices — from the official source, dated.")
                graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
                         self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, P(lang, "cards", cid)))]
                self.page(lang, ("cards", cid), title, desc, body, graph, "card", nav="cards")
        # index: every confirmed card × every chain
        for lang in ("ar", "en"):
            body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_cards"], lang), None))}'
            body += f'<h1 class="pt">{"خصومات السينما بالبطاقات" if lang == "ar" else "Cinema discounts by card"}</h1>'
            body += f'<p class="lead">{"كل بطاقة مقابل كل سلسلة، من المصدر الرسمي. الفراغ يعني ما لقينا خصم رسمي، مب إن السينما ترفض." if lang == "ar" else "Every card against every chain, from the official source. A blank means no official discount found — not that the cinema refuses it."}</p></section>'
            head = "".join(f'<th scope="col">{esc(self.h.chain_name(ch, lang))}</th>' for ch in chains)
            rows = ""
            for card in self.cards:
                cells = ""
                for ch in chains:
                    r = rule_for(self.rules, ch, card["id"]); st = rule_state(r, self.today)
                    txt = (f'<b class="num" dir="ltr">{"1+1" if r.get("type") == "bogo" else (f"{float(r.get("value") or 0):g} AED" if r.get("type") == "fixed" else f"{r.get("value", 0):g}%")}</b>') if st == "ok" else \
                          (f'<span class="nil">{esc(L(T["none_found"], lang))}</span>' if st == "none_found" else f'<span class="nil">{esc(L(T["expired"], lang))}</span>' if st == "expired" else "")
                    cells += f"<td>{txt}</td>"
                rows += f'<tr><th scope="row"><a href="{P(lang, "cards", card["id"])}">{esc(card["name_ar"] if lang == "ar" else card["name_en"])}</a></th>{cells}</tr>'
            body += (f'<section class="wrap"><div class="xwrap"><table class="matrix"><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
                     f'<p class="hint">{"1+1 = تذكرتين بسعر وحدة." if lang == "ar" else "1+1 = buy one, get one."}</p></section>')
            title = ("خصومات السينما في الإمارات — فزعة وإسعاد وعروض البنوك" if lang == "ar" else "UAE cinema discounts — Fazaa, Esaad and bank cards")
            desc = ("جدول واحد لكل خصومات السينما الرسمية في الإمارات: فزعة وإسعاد والبنوك، في فوكس وستار ونوفو وريل وروكسي وسيني رويال وسينما سيتي." if lang == "ar"
                    else "One table of every official UAE cinema discount: Fazaa, Esaad and banks, at VOX, Star, Novo, Reel, Roxy, Cine Royal and Cinemacity.")
            self.page(lang, ("cards",), title, desc, body, [self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")))], "cards", nav="cards")

    # -------------------------------------------------- halls
    def halls_page(self):
        for lang in ("ar", "en"):
            body = f'<section class="head wrap">{self.crumbs(lang, (L(UI["s_halls"], lang), None))}'
            body += f'<h1 class="pt">{"القاعات المميزة في سينمات الإمارات" if lang == "ar" else "Premium cinema halls in the UAE"}</h1>'
            body += f'<p class="lead">{"كل سلسلة تسمّي قاعتها الغالية باسم. هني شو فيها فعلاً، وكم سعرها اليوم، ووين تلقاها." if lang == "ar" else "Every chain names its premium hall differently. Here is what is actually inside, what it costs today and where to find it."}</p></section>'
            faq = []
            for chain, c in self.h.y.items():
                body += f'<section class="wrap hchain"><h2>{esc(self.h.chain_name(chain, lang))}</h2><div class="halls">'
                for e in c.get("halls", []):
                    ss = [s for s in self.shows if self.cinemas[s["cinema"]]["chain"] == chain and self.hkey(s) == e["key"]]
                    ps = [p["aed"] for s in ss for p in s.get("prices") or [] if p.get("aed")]
                    where = sorted({s["cinema"] for s in ss})
                    rng = (f'{num(money(min(ps)))}' + (f' – {num(money(max(ps)))}' if max(ps) != min(ps) else "") + f' <small>{esc(L(T["aed"], lang))}</small>') if ps else ""
                    what = e.get("what_ar") if lang == "ar" else e.get("what_en")
                    conf = {"high": "", "medium": ("من مصدر غير رسمي" if lang == "ar" else "from a non-official source"),
                            "low": ("ما تأكدنا من التفاصيل" if lang == "ar" else "details not confirmed")}.get(e.get("confidence"), "")
                    hname = e.get("name") or e["key"]
                    latin = lang == "ar" and not ARABIC.search(hname)
                    body += (f'<div class="hall"><h3{" lang=\"en\"" if latin else ""}>{esc(hname)}</h3><p>{dates(esc(what))}'
                             + (f' <small class="weak">{esc(conf)}</small>' if conf else "")
                             + (f' <a class="src" href="{esc(e["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>' if e.get("source") else "") + '</p>'
                             + (f'<p class="rng">{"اليوم" if lang == "ar" else "Today"} {rng}</p>' if rng else "")
                             + (f'<p class="where">{"".join(f"<a href=\"{P(lang, self.cinemas[w]["city"], w)}\">{self.cname_html(w, lang)}</a>" for w in where)}</p>' if where else "")
                             + '</div>')
                    faq.append(((f"شو فيها قاعة {e.get('name') or e['key']} في {self.h.chain_name(chain, lang)}؟" if lang == "ar" else f"What is {e.get('name') or e['key']} at {self.h.chain_name(chain, lang)}?"), what))
                body += '</div></section>'
            title = ("قاعات السينما في الإمارات — GOLD وTHEATRE وIMAX وSUITES، شو الفرق وكم السعر؟" if lang == "ar" else "UAE premium cinema halls — GOLD, THEATRE, IMAX, SUITES: what’s the difference?")
            desc = ("شو الفرق بين قاعات فوكس جولد وثياتر وماكس، وستار سويتس، ونوفو سفن ستار، وروكسي بلاتينيوم، وريل دولبي، وكم سعرها اليوم." if lang == "ar"
                    else "The difference between VOX GOLD, THEATRE and MAX, Star Suites, Novo 7 Star, Roxy Platinum, Reel Dolby and more — and what they cost today.")
            graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq if a]},
                     self.breadcrumb_ld(lang, (L(UI["s_halls"], lang), P(lang, "halls")))]
            self.page(lang, ("halls",), title, desc, body, graph, "halls")

    # -------------------------------------------------- 404
    def not_found(self):
        body = (f'<section class="head wrap nf"><h1 class="pt">ما لقينا هالصفحة</h1>'
                f'<p class="lead">يمكن الفيلم نزل من السينما، أو الرابط تغيّر. <a href="/">الأفلام المعروضة اليوم</a>.</p>'
                f'<p class="lead" lang="en" dir="ltr">We couldn’t find this page. <a href="/en/">Films showing today, in English</a>.</p></section>')
        self.page("ar", (), "ما لقينا هالصفحة — سينما", "الصفحة غير موجودة.", body, [], "404",
                  path=os.path.join(self.out, "404.html"), robots='<meta name="robots" content="noindex">')

    # -------------------------------------------------- data for cinema.js, sitemap, assets
    def slices(self):
        """/data/<city>-<date>.json per city and day, holding only what cinema.js reads, as indexed arrays:
        C[[cid, chain, ar, en]] F[[fid, ar, en]] H[[hall code, key, ar, en]] P[[[seat, aed]…]] B[booking URL prefixes]
        S[[cinema i, film i, "HH:MM", hall i, price i|-1, prefix i|-1, url tail(, table date)]] — the 8th
        element is present only when the price came from prices.yaml, and is that entry's date.
        Aligned with S when any is known: E[minutes from start to the approximate end, 0 = unknown] and
        Li[index into L[[lang, subs]] or -1]."""
        ddir = os.path.join(self.out, "data")
        for city, _, _ in CITIES:
            cids = {cid for cid, c in self.cinemas.items() if c.get("city") == city}
            for day in sorted({s["date"] for s in self.shows if s["cinema"] in cids}):
                ss = sorted((s for s in self.shows if s["cinema"] in cids and s["date"] == day), key=lambda s: s["time"])
                lists = {"C": [], "F": [], "H": [], "P": [], "B": [], "L": []}
                idx = {k: {} for k in lists}

                def at(kind, key, row):
                    if key not in idx[kind]: idx[kind][key] = len(lists[kind]); lists[kind].append(row)
                    return idx[kind][key]
                S, E, Li = [], [], []
                for s in ss:
                    cid, fid, chain = s["cinema"], s["film"], self.cinemas[s["cinema"]]["chain"]
                    code = s.get("hall") or "OTHER"
                    ci = at("C", cid, [cid, chain, self.cname(cid, "ar"), self.cname(cid, "en")])
                    fi = at("F", fid, [fid, self.ftitle(fid, "ar"), self.ftitle(fid, "en")])
                    hk = self.hkey(s)
                    hi = at("H", (chain, hk, code), [code, chain + "|" + hk, self.hname(s, "ar"), self.hname(s, "en")])
                    pr = [[p["seat"], p["aed"]] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
                    pi = at("P", json.dumps(pr), pr) if pr else -1
                    bi, tail = -1, ""
                    if s.get("book"):
                        pre, _, tail = s["book"].rpartition("/")
                        bi = at("B", pre + "/", pre + "/") if pre else -1
                        if not pre: tail = s["book"]
                    row = [ci, fi, s["time"], hi, pi, bi, tail]
                    if pr and self.table_date(s): row.append(self.table_date(s))  # a table price carries its date
                    E.append(self.end_offset(s))
                    Li.append(at("L", (s.get("lang"), s.get("subs")), [s.get("lang"), s.get("subs")]) if s.get("lang") or s.get("subs") else -1)
                    S.append(row)
                j = {"g": self.d.get("generated"), **{k: v for k, v in lists.items() if k != "L"}, "S": S}
                if any(E): j["E"] = E
                if lists["L"]: j["L"], j["Li"] = lists["L"], Li
                self.write(os.path.join(ddir, f"{city}-{day}.json"), json.dumps(j, ensure_ascii=False, separators=(",", ":")))
        # «أقرب سينما لي» and the ticket's directions: every cinema's city and coordinates, {cid: [city, chain, lat, lng, ar, en]}
        geo = {cid: [c.get("city"), c["chain"], round(float(c["lat"]), 5), round(float(c["lng"]), 5), self.cname(cid, "ar"), self.cname(cid, "en")]
               for cid, c in self.cinemas.items() if c.get("lat") is not None and c.get("lng") is not None}
        self.write(os.path.join(ddir, "cinemas.json"), json.dumps(geo, ensure_ascii=False, separators=(",", ":")))
        rules = {ch: {card: {k: v for k, v in r.items() if k in ("status", "type", "value", "excluded_halls", "halls_excluded", "included_halls", "included_cinemas", "valid_until", "confidence", "box_office_only", "max_tickets", "note_ar")}
                      for card, r in (cards or {}).items()} for ch, cards in self.rules.items()}
        chains = {ch: self.h.chain_name(ch, "ar") for ch in set(self.rules) | {c["chain"] for c in self.cinemas.values()}}
        chains_en = {ch: self.h.chain_name(ch, "en") for ch in chains}
        self.write(os.path.join(ddir, "discounts.json"), json.dumps({"cards": self.cards, "rules": rules, "chains": {"ar": chains, "en": chains_en}},
                                                                    ensure_ascii=False, separators=(",", ":"), default=str))

    def sitemap(self):
        """hreflang pairs + x-default; lastmod moves only when the page's content hash changes (lastmod_path keeps them)."""
        known = {}
        if self.lastmod_path and os.path.exists(self.lastmod_path):
            try: known = json.load(open(self.lastmod_path, encoding="utf-8"))
            except ValueError: known = {}
        sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
        for parts in self.urls:
            for lang in ("ar", "en"):
                u = P(lang, *parts); h = self.hashes.get(u, "")
                prev = known.get(u)
                day = prev[1] if prev and prev[0] == h else self.today
                if parts[:1] == ("film",) and (self.films.get(parts[1]) or {}).get("status") == "archived":
                    day = str(self.films[parts[1]].get("last_seen") or day)   # an archive changes when the run ends
                known[u] = [h, day]
                sm.append(f"<url><loc>{SITE + u}</loc><lastmod>{day}</lastmod>"
                          f'<xhtml:link rel="alternate" hreflang="ar" href="{SITE + P("ar", *parts)}"/>'
                          f'<xhtml:link rel="alternate" hreflang="en" href="{SITE + P("en", *parts)}"/>'
                          f'<xhtml:link rel="alternate" hreflang="x-default" href="{SITE + P("ar", *parts)}"/></url>')
        sm.append("</urlset>")
        self.write(os.path.join(self.out, "sitemap.xml"), "\n".join(sm))
        if self.noindex:   # preview: nothing is crawled, and no sitemap is advertised
            self.write(os.path.join(self.out, "robots.txt"), "User-agent: *\nDisallow: /\n")
        else:
            self.write(os.path.join(self.out, "robots.txt"), f"User-agent: *\nAllow: /\nDisallow: /data/\n\nSitemap: {SITE}/sitemap.xml\n")
        if self.lastmod_path:
            os.makedirs(os.path.dirname(self.lastmod_path), exist_ok=True)
            json.dump(known, open(self.lastmod_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)

    def offline(self):
        """The service worker's fallback when a page is not cached and there is no network: one self-contained
        file (its style inline, system fonts), so it looks right on the first offline hit with nothing cached."""
        page = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ما في إنترنت — سينما</title><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#0F0B0C"><meta name="color-scheme" content="dark">
<style>
body{margin:0;min-height:100vh;background:#0F0B0C radial-gradient(280px 220px at 70% 90px,rgba(122,22,38,.6),rgba(15,11,12,0)) no-repeat;color:#F1EAE0;
font:16px/1.7 "Readex Pro","Segoe UI",Tahoma,system-ui,sans-serif}
main{max-width:40rem;margin:0 auto;padding:48px 20px}
.m{font-weight:700;font-size:34px;color:#E2B659;text-decoration:none}
h1{font-size:36px;line-height:1.15;margin:40px 0 12px}
p{margin:0 0 14px;color:#C9BDAE}
a{color:#F1EAE0;text-decoration-color:#A89C8E;text-underline-offset:.2em}
[lang=en]{direction:ltr;text-align:left;font-size:14px;color:#A89C8E}
</style></head><body><main>
<a class="m" href="/">سينما</a>
<h1>ما في إنترنت الحين</h1>
<p>الصفحات اللي فتحتها قبل تشتغل بدون نت. ارجع لها، أو جرّب مرة ثانية لين يرجع الاتصال.</p>
<p><a href="/">الأفلام المعروضة اليوم</a></p>
<p lang="en">You are offline. Pages you opened before still work. <a href="/en/">Films today, in English</a>.</p>
</main></body></html>
"""
        self.write(os.path.join(self.out, "offline.html"), page)

    def assets(self):
        adir = os.path.join(self.out, "assets")
        os.makedirs(os.path.join(adir, "fonts"), exist_ok=True)
        for f in ("cinema.css", "icon.svg"):
            if os.path.exists(os.path.join(SRC, f)):
                t = open(os.path.join(SRC, f), encoding="utf-8").read()
                self.write(os.path.join(adir, f), minify_css(t) if f.endswith(".css") else t)
        self.write(os.path.join(adir, self.js_name), self.js)
        self.write(os.path.join(adir, self.adhan_name), self.adhan)
        # PWA: the worker must sit at the root to control every page; the manifest names the icons
        self.write(os.path.join(self.out, "sw.js"), open(os.path.join(SRC, "sw.js"), encoding="utf-8").read().replace("__V__", self.v))
        self.write(os.path.join(self.out, "manifest.webmanifest"), open(os.path.join(SRC, "manifest.webmanifest"), encoding="utf-8").read())
        idir = os.path.join(SRC, "icons")
        os.makedirs(os.path.join(adir, "icons"), exist_ok=True)
        for f in os.listdir(idir) if os.path.isdir(idir) else []:
            if f.endswith(".png"): shutil.copy(os.path.join(idir, f), os.path.join(adir, "icons", f))
        for f in ("og-ar.png", "og-en.png"):
            if os.path.exists(os.path.join(SRC, f)): shutil.copy(os.path.join(SRC, f), os.path.join(adir, f))
        fdir = os.path.join(SRC, "fonts")
        for f in os.listdir(fdir) if os.path.isdir(fdir) else []:
            shutil.copy(os.path.join(fdir, f), os.path.join(adir, "fonts", f))

    def run(self):
        self.home(); self.city_pages(); self.cinema_pages(); self.film_pages(); self.card_pages(); self.halls_page(); self.not_found(); self.offline()
        self.slices(); self.sitemap(); self.assets()
        return len(self.urls)


# the client: small modules under src/js/, concatenated in this order into ONE function scope (so they share
# helpers without globals), comments and indentation stripped. pure.js and disc.js are plain function
# declarations with no page access: tests/test_js.py and tests/test_parity.py run them in node as they are.
JS_MODULES = ("core", "pure", "disc", "flip", "prices", "near", "prayer", "home", "filters", "ticket", "trailer", "pwa", "main")


def minify_css(css):
    """Comments out, each line trimmed and joined, the space after ; { } and before { dropped. Nothing inside a
    value is touched (content:" " and font names keep their spaces)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = "".join(line.strip() for line in css.splitlines())
    return re.sub(r"\s*([{}])\s*|;\s+", lambda m: m.group(1) or ";", css) + "\n"


def minify_lite(js):
    """Drop /* */ comments, whole-line // comments and indentation. Deliberately naive: the modules never
    put «/*» or a line-leading «//» inside a string or a regex (tests/test_js.py checks the bundle parses)."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    out = []
    for line in js.splitlines():
        t = line.strip()
        if t and not t.startswith("//"): out.append(t)
    return "\n".join(out)


def bundle_js(src=None):
    src = src or os.path.join(SRC, "js")
    parts = [open(os.path.join(src, m + ".js"), encoding="utf-8").read() for m in JS_MODULES]
    return minify_lite('(function () {\n"use strict";\n' + "\n".join(parts) + "\n})();\n") + "\n"


GENERATED = [c for c, _, _ in CITIES] + ["film", "cards", "halls", "data", "assets", "en", "cinema"]


NOINDEX = '<meta name="robots" content="noindex,nofollow">'


def preview_mode(env=None):
    """PREVIEW=1 (or true/yes) in the environment: the build is a preview. Every page is noindex,nofollow
    and robots.txt is `Disallow: /` with no Sitemap line. Unset or 0: the normal, indexable site."""
    return str((env if env is not None else os.environ).get("PREVIEW", "")).strip().lower() in ("1", "true", "yes")


def build(data_path, discounts_path, out, halls_path=None, preview=False, lastmod_path=None, noindex=None):
    data = json.load(open(data_path, encoding="utf-8"))
    disc = load_discounts(discounts_path)
    halls = Halls(halls_path or os.path.join(ROOT, "halls.yaml"))
    for sub in GENERATED:          # only what this build writes; anything else in out/ is left alone
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    for f in ("index.html", "404.html", "offline.html", "sitemap.xml", "robots.txt", "sw.js", "manifest.webmanifest"):
        try: os.remove(os.path.join(out, f))
        except FileNotFoundError: pass
    site = Site(data, disc, halls, out); site.lastmod_path = lastmod_path
    site.noindex = preview_mode() if noindex is None else noindex
    return site.run()


def main():
    first = lambda *ps: next((p for p in ps if os.path.exists(p)), ps[-1])
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=first(os.path.join(ROOT, "data", "latest.json"), os.path.join(ROOT, "fixtures", "sample_latest.json")))
    ap.add_argument("--discounts", default=first(os.path.join(ROOT, "discounts.yaml"), os.path.join(ROOT, "fixtures", "sample_discounts.yaml")))
    ap.add_argument("--halls", default=os.path.join(ROOT, "halls.yaml"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--preview", action="store_true", help="(kept for old callers; the site no longer needs anything from ../tools)")
    a = ap.parse_args()
    n = build(a.data, a.discounts, a.out, a.halls, a.preview, os.path.join(ROOT, "data", "lastmod.json"))
    print(f"built {n} pages ×2 languages from {os.path.relpath(a.data, ROOT)} + {os.path.relpath(a.discounts, ROOT)} -> {a.out}")


if __name__ == "__main__":
    main()
