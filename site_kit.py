"""The kit every page module shares — pages/core.py and each phase-2 feature (pages/<feature>.py) import it.

  constants     CITIES, CITY, T, UI, VERDICT, LANGS, budgets (PAGE_TARGET, CHROME, SCHED_BUDGET), regexes
  helpers       esc, L, P, dates (ISO dates and percentages isolated for RTL), money, num, human_date, span_dates,
                genre_*, film_flags, hue, ago, parse_iso, discounts (after, rule_*), Halls, clean_label, minify_*
  Kit           the site's state (films, cinemas, shows, cards, rules) and its markup: names, price cells, fit() to
                a byte budget, crumbs, JSON-LD, the slots, page() and write(); since W1-P1 its helper families are
                mixins in kit/ (media: posters and frames; tile: tiles, rows, the grid; sched: time buttons;
                ticket: the ticket; chrome: header, tab bar, footer, sheets; filters: the filter sheet's content),
                one Wave 2 owner each (MASTER-PLAN §6.2)
  plug-in types Page, Emit, NavItem, Plugin — what a module's register(site) returns (docs/PLUGINS.md)

build.py (the loader) is `class Site(Kit)`; page modules never import build."""
import colorsys, datetime as dt, hashlib, html, json, os, re, shutil, sys
from dataclasses import dataclass, field
from typing import Callable
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


def ar_count_num(n, forms):
    """ar_count as markup: the digits in a .num span, the words escaped. 1 and 2 are words alone
    («سينما وحدة», «سينمتين»), so a count never reads «1 سينما»."""
    return esc(forms[0] if n == 1 else forms[1]) if n in (1, 2) else f"{num(n)} {esc(forms[2] if 3 <= n <= 10 else forms[3])}"


CINEMAS_AR = ("سينما وحدة", "سينمتين", "سينمات", "سينما")
FILMS_AR = ("فيلم واحد", "فيلمين", "أفلام", "فيلم")


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
# a source check's raw words (an English error page) are never printed: the card pages say what it means
SOURCE_GONE = re.compile(r"not found|\b404\b", re.I)
SOURCE_GONE_AR = "صفحة العرض الرسمية انحذفت، فما نعرض الخصم"
UI = {
    "s_mark": ("سينما", "Cinema"), "s_films": ("الرئيسية", "Home"), "s_cinemas": ("السينمات", "Cinemas"),
    "s_thursday": ("نازل قريب", "Coming soon"), "s_cards": ("البطاقات", "Cards"), "s_halls": ("القاعات", "Halls"),
    "s_alt": ("English", "العربية"), "s_nav": ("الأقسام", "Sections"), "s_skip": ("تخطَّ إلى المحتوى", "Skip to content"),
    "s_footer": ("سينما من Elyoxe. الأسعار من السينمات نفسها، والخصومات متحقَّق منها بتاريخها.",
                 "Cinema by Elyoxe. Prices from the cinemas themselves; discounts checked and dated."),
    "s_studio": ("استوديو Elyoxe", "Elyoxe studio"),
    # the chrome (UI redesign Task 2): header tools, the phone tab bar, the footer's links
    "s_search": ("بحث", "Search"), "s_tabs": ("التنقل", "Navigation"), "s_more": ("روابط الموقع", "Site links"),
    "s_cards_h": ("الأسعار والبطاقات", "Prices and cards"),   # the header's label for the cards link (crumbs keep s_cards)
    "s_cards_f": ("البطاقات والخصومات", "Cards and discounts"), "s_sources": ("من وين الأسعار", "Where prices come from"),
}
# the chrome's own words (not in the template's {{…}} table)
CHROME_T = {"city": ("المدينة", "City"), "card": ("البطاقة", "Card"), "mycard": ("بطاقتي", "My card"),
            "close": ("سكّر", "Close"), "near": ("قريب مني", "Near me"), "gov": ("حكومية", "Government"),
            "bank": ("بنوك", "Banks"), "pick_city": ("وين أنت؟", "Where are you?"), "pick_card": ("شو عندك من بطاقة؟", "Which card do you have?"),
            "all_cards": ("خصم كل بطاقة في كل سينما", "Every card’s discount at every cinema"),
            "all_cities": ("كل السينمات حسب المدينة", "Every cinema by city")}
# the home page's words (UI redesign Task 3)
HOME_T = {"top": ("الأكثر عرضاً الليلة", "Most shown tonight"), "top_in": ("الأكثر عرضاً في {city} الليلة", "Most shown in {city} tonight"),
          "yes": ("يستاهل", "Worth it"), "yes_sub": ("حكمنا من تقييمات النقاد والجمهور", "Our call, from critics and audiences"),
          "cheap": ("أرخص لك الليلة", "Cheapest for you tonight"), "family": ("للعائلة", "For the family"),
          "coming": ("نازل الخميس", "Out Thursday"), "last": ("آخر فرصة", "Last chance"), "arabic": ("عربي", "Arabic"),
          "near": ("يبدأ قريب منك", "Starting near you"), "all": ("الكل", "See all"), "all_films": ("كل الأفلام", "All films"),
          "filter": ("تصفية", "Filter"), "sort": ("الترتيب", "Sort"), "sort_default": ("الأكثر عرضاً", "Most shown"),
          "genre": ("النوع", "Genre"), "who": ("مع منو رايح؟", "Who’s coming?"), "before": ("لازم يخلص قبل", "Has to end by"),
          "lang": ("اللغة", "Language"), "prayer": ("الصلاة", "Prayer"), "clear": ("مسح", "Clear"),
          "times": ("الأوقات والأسعار", "Times and prices"), "trailer": ("الإعلان", "Trailer"), "from": ("من", "from"),
          "tag_thu": ("الخميس", "Thursday"), "tag_last": ("آخر أسبوع", "Last week"),
          "prev": ("السابق", "Previous"), "next": ("التالي", "Next"), "slides": ("الأفلام الأبرز", "Featured films"),
          "min": ("دقيقة", "min"), "pause": ("أوقف التقليب", "Pause the slides")}
# the film page's words (UI redesign Task 4)
FILM_T = {"about": ("عن الفيلم", "About"), "cast": ("الطاقم", "Cast"), "similar": ("شي يشبه", "More like it"),
          "double": ("فيلمين ورا بعض", "Double feature"), "compare": ("قارن", "Compare"), "tabs": ("عن الفيلم وأكثر", "About the film and more"),
          "more": ("المزيد", "More"), "less": ("أقل", "Less"), "share": ("شارك", "Share"), "trailer": ("الإعلان", "Trailer"),
          "opts": ("خيارات العرض", "Showtime options"), "days": ("الأيام", "Days"),
          "times": ("المواعيد والأسعار", "Showtimes and prices"),
          "pick": ("اختر وقت", "Pick a time"),
          "pick_s": ("اختر وقت من المواعيد، وتطلع لك تذكرته هني: سعر كل مقعد بعد خصم بطاقتك، والحجز والاتجاهات.",
                     "Pick a showtime and its ticket shows here: every seat’s price after your card, booking and directions."),
          "details": ("التفاصيل والحجز", "Details and booking"), "chosen": ("الوقت المختار", "Chosen time"),
          "n_cin": (("سينما وحدة", "سينمتين", "سينمات", "سينما"), ("cinema", "cinemas")),
          "none": ("ما لقينا عروض لهذا الفيلم في اليومين الجايين.", "No shows for this film in the next two days.")}
WEEKDAYS = (("الاثنين", "Mon"), ("الثلاثاء", "Tue"), ("الأربعاء", "Wed"), ("الخميس", "Thu"), ("الجمعة", "Fri"), ("السبت", "Sat"), ("الأحد", "Sun"))
# inline icons (24 px grid, stroked in currentColor): the phone tab bar and the header's search button
ICONS = {"home": '<path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z"/>',
         "pin": '<path d="M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/>',
         "cal": '<rect x="4" y="5" width="16" height="15"/><path d="M4 10h16M9 3v4M15 3v4"/>',
         "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
         # the home page (UI redesign Task 3): the «تصفية» chip, a row's arrows (drawn pointing to the inline end:
         # CSS turns them in RTL), the trailer's play mark
         "filter": '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
         "next": '<path d="m9 5 7 7-7 7"/>', "prev": '<path d="m15 5-7 7 7 7"/>',
         # the film page (Task 4): «شارك», the day bar's «⋯»
         "share": '<path d="M12 3v12M7 8l5-5 5 5M5 14v6h14v-6"/>',
         "dots": '<circle cx="5" cy="12" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="19" cy="12" r="1.3" fill="currentColor"/>'}


def icon(name):
    return (f'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8"'
            f' aria-hidden="true" focusable="false">{ICONS[name]}</svg>')
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
FID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,120}$")   # a slug: safe as a path segment and in an attribute
SAFE_URL = re.compile(r"^https?://", re.I)
OUR_POSTER = re.compile(r"^/posters/[A-Za-z0-9._-]+\.webp$")   # posters.py mirrors to /posters/<fid>-<hash>-342.webp
OUR_BACKDROP = re.compile(r"^/posters/bd-[A-Za-z0-9._-]+\.webp$")   # steps/backdrops.py: /posters/bd-<fid>-<hash>-1280.webp
SCHED_BUDGET = 100_000   # bytes of schedule markup per page; with the chrome a page stays under 150 KB
# every page is rendered as richly as fits PAGE_TARGET (the spec's budget is 150 KB; the target leaves
# headroom for busier days): each schedule tries its modes in order and the last, «compact», is bounded —
# times as plain text that cinema.js turns into buttons and prices from the city's /data slice
PAGE_TARGET = 125_000
# the template, window.CT and the page's price lists' wrapper: ~6 KB measured in phase 1, plus ~3.3 KB of the
# redesign's chrome (UI redesign Task 2: the header's tools, the tab bar's icons, the footer's links, the two
# sheets — measured 4.5 KB on a film page against 1.2 KB before)
CHROME = 10_000
BCP47 = {"English": "en", "Arabic": "ar", "Hindi": "hi", "Telugu": "te", "Malayalam": "ml", "Tamil": "ta", "Tagalog": "tl",
         "Urdu": "ur", "Bengali": "bn", "Kannada": "kn", "French": "fr", "Spanish": "es", "Japanese": "ja", "Korean": "ko",
         "Chinese": "zh", "Russian": "ru", "Turkish": "tr", "Persian": "fa", "Filipino": "tl", "Punjabi": "pa", "Marathi": "mr"}
PCT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?\s?%)")
ARABIC = re.compile(r"[؀-ۿ]")
MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
# the CSS width each poster class is drawn at (cinema.css): row tile, the big first tile, the film hero, list thumb
POSTER_SIZES = {"pst": "(min-width:1024px) 15vw, 150px", "pst big": "(min-width:1024px) 15vw, 220px",
                "pst hero": "(min-width:1280px) 300px, (min-width:1024px) 220px, min(62vw, 260px)", "pst sm": "(min-width:1024px) 96px, 72px",
                # the home grid: 3 columns on a phone, 7 on a desktop (UI redesign Task 3); a row's tile is 128/188 px
                "tile": "(min-width:1024px) 13vw, 32vw", "tile row": "(min-width:1024px) 188px, 128px"}
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


def note_ar(r, ok=False):
    """A rule's Arabic note as the site prints it: a note carrying the source check's raw English error
    («الرابط الرسمي رجع Page Not Found») becomes one Arabic sentence (SOURCE_GONE_AR). Beside a discount the
    site does show (`ok`, the terms of a live rule) that sentence would be false, so there the error is dropped."""
    n = (r or {}).get("note_ar") or ""
    return ("" if ok else SOURCE_GONE_AR) if SOURCE_GONE.search(n) else n


def rule_terms(r, lang):
    t = []
    note = note_ar(r, ok=True) if lang == "ar" else ""
    if r.get("box_office_only") and "الشباك" not in note: t.append("من الشباك فقط" if lang == "ar" else "Box office only")
    if r.get("max_tickets") and not re.search("تذاكر|تذكرة", note): t.append(f'{r["max_tickets"]} تذاكر بالحد' if lang == "ar" else f'Up to {r["max_tickets"]} tickets')
    inc, exc = r.get("included_halls"), r.get("excluded_halls") or r.get("halls_excluded")
    hn = lambda hs: [("القاعة العادية" if h == "Standard" else h) if lang == "ar" else h for h in hs]
    if inc: t.append("يشمل " + "، ".join(hn(inc)) + " فقط" if lang == "ar" else "Only " + ", ".join(inc))
    if exc: t.append(("ما يشمل " + "، ".join(hn(exc))) if lang == "ar" else "Excludes " + ", ".join(exc))
    if r.get("included_cinemas") is not None: t.append("في فروع محددة بس" if lang == "ar" else "Selected branches only")
    if r.get("valid_until"): t.append((f'لين {r["valid_until"]}') if lang == "ar" else f'Until {r["valid_until"]}')
    if lang == "ar" and note and r.get("type"): t.append(note)
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


# pages whose first section is a full-bleed backdrop: the header starts transparent over it (data-hero)
HERO_KINDS = ("home", "film")
NOINDEX = '<meta name="robots" content="noindex,nofollow">'
OG_DIMS = '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'


# ---------------------------------------------------------------- plug-in types (docs/PLUGINS.md)
@dataclass
class Page:
    """One page in one language. `build()` returns site.page()'s keywords: title, desc, body, kind, and
    optionally graph (JSON-LD nodes), attrs, nav, og_image, robots, path, js (lazy chunks for this page)."""
    parts: tuple
    lang: str
    build: Callable[[], dict]


@dataclass
class Emit:
    """A writer that renders several pages itself through site.page() (the core page types: one loop over
    cities, cinemas, films… sharing its work across both languages)."""
    run: Callable[[], None]


@dataclass
class NavItem:
    """A header link. `key` films / cinemas / thursday / cards re-points that built-in link (href, and label
    when given); any other key adds a link to the footer's row (Kit.chrome; the header and the phone's tab bar
    keep their four places: a fifth sat off-screen). aria-current when a page passes nav=key."""
    key: str
    href: object = None          # a path, or fn(lang) -> path
    label: tuple = None          # (ar, en)


@dataclass
class Plugin:
    """What register(site) returns (a bare list is read as `pages`). Written in module order, core first:
    every page, then every data file, then the sitemap (pages by site.page() are in it on their own)."""
    pages: list = field(default_factory=list)      # Page | Emit, in order
    data: dict = field(default_factory=dict)       # "data/<name>.json" (under out/) -> JSON-able, or fn() -> JSON-able
    sitemap: list = field(default_factory=list)    # extra path-part tuples (pages written with path=)
    nav: list = field(default_factory=list)        # NavItem
    slots: dict = field(default_factory=dict)      # slot name -> fn(site, lang, **ctx) -> html (Kit.SLOTS)
    page_js: dict = field(default_factory=dict)    # page kind ("home", "film"…, "*" = every page) -> lazy chunk names to load there


class Pages:
    """A page module's renderer: self.<name> reads through to the site, so a method written for the site
    (self.poster, self.page, self.shows …) works unchanged here."""

    def __init__(self, site):
        self.site = site

    def __getattr__(self, k):
        return getattr(self.site, k)


# the Kit's helper families (W1-P1): mixins in kit/, imported here once every helper above exists
from kit.chrome import ChromeKit  # noqa: E402
from kit.filters import FiltersKit  # noqa: E402
from kit.media import MediaKit  # noqa: E402
from kit.sched import SchedKit  # noqa: E402
from kit.ticket import TicketKit  # noqa: E402
from kit.tile import TileKit  # noqa: E402


class Kit(MediaKit, TileKit, SchedKit, TicketKit, ChromeKit, FiltersKit):
    noindex = False   # set by build(): PREVIEW=1
    # filled by the loader (build.Site) from the page modules; empty, the pages are phase 1's to the byte
    nav_items, slots, kind_js, chunk_urls = (), {}, {}, {}
    # page kind -> /assets/page-<kind>.<hash>.css: a module's PAGE_CSS, a second small stylesheet on that kind only (W1-P1)
    page_css = {}
    # the places core pages leave for a feature, each fn(site, lang, **ctx) -> html
    SLOTS = {"home.after_tonight": "home, after its rows, before «كل الأفلام»",
             "city.after_tonight": "city page, under its «الليلة» (ctx: city)",
             "cinema.after_halls": "cinema page, after «القاعات والأسعار» (ctx: cid)",
             "film.info": "film page, «عن الفيلم» tab, after the synopsis and facts (ctx: fid)",
             # the film page's other places (UI redesign Task 4): each fills its own tab, or the hero's actions
             "film.share": "film page, the hero's actions: a share link (ctx: fid)",
             "film.cast": "film page, «الطاقم» tab (ctx: fid)",
             "film.similar": "film page, «شي يشبه» tab (ctx: fid)",
             "film.double": "film page, «فيلمين ورا بعض» tab (ctx: fid); unfilled since W0-P2 (plan §4.1 #14), W2-P6 retires it",
             "film.compare": "film page, «قارن» tab (ctx: fid); the hero's «قارن» links to it",
             # Wave 2's places (W1-P1, MASTER-PLAN §5.2): declared before anyone fills them, so no Wave 2 package edits
             # pages/core.py, pages/_core/* or build.py to get one. A Wave 3–4 slot is declared by the package that fills it
             "head.inline": "every page's <head>, right after the «js» class script: a small inline script that must run before first paint (ctx: kind)",
             "home.after_bill": "home, right under the billboard (and its visually hidden h1): the board, W2-P2",
             "home.after_board": "home, under the board, above the rows: the Thursday band, W2-P7",
             "film.first": "film page (showing), between the hero and the day bar: «أقرب عرض لك», W2-P2 (ctx: fid)",
             "cinema.top": "cinema page, under its head (name, address, directions): the board's rows, W2-P2 (ctx: cid, city)",
             "city.hero": "city page with cinemas, under its head: the board's rows, W2-P2 (ctx: city)",
             "notfound.body": "the 404, under its head: the leader's rows, W2-P2/W2-P10",
             "offline.body": "the offline page, before its English line; self-contained markup (no site stylesheet there), W2-P2/W2-P10",
             "ticket.actions": "the ticket's actions row, after «أرسلها للقروب» (ctx: show, the show's dict), W2-P3",
             "sources.body": "/sources/, after the chains' list: «كيف نختار لك», W2-P2"}

    def slot(self, name, lang, **ctx):
        return "".join(fn(self, lang, **ctx) or "" for fn in self.slots.get(name, ()))

    @staticmethod
    def show_key(cinema, date, time, hall=None):
        """The show link's key (MASTER-PLAN §2.2, W1-P1): /film/<fid>/#s-<key>. FNV-1a 32-bit over the UTF-8 of
        «cinema|date|time|hall key» (the hall key Kit.hkey gives: «Standard» when there is none), in base36, left-
        padded to 6 characters (6–7 in all). Stable across the hourly builds, because every input is. The script's
        twin is showKey() in src/js/core.js; tests/test_showkey.py holds them equal over every show."""
        h = 0x811C9DC5
        for b in "|".join((str(cinema), str(date), str(time), str(hall or "Standard"))).encode("utf-8"):
            h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
        k = ""
        while True:
            h, r = divmod(h, 36)
            k = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + k
            if not h: break
        return k.rjust(6, "0")

    def show_key_of(self, s):
        """Kit.show_key for a show as the data has it (its hall key from Kit.hkey)."""
        return self.show_key(s["cinema"], s["date"], s["time"], self.hkey(s))

    @staticmethod
    def week_phase(now):
        """Where the cinema week stands in UAE time (MASTER-PLAN §1.1, the Thursday band and the rows' eyebrows):
        «wed-eve» from Wednesday 18:00, «thu-sat» Thursday 00:00 to Saturday 23:59, «rest» otherwise. `now` is an
        aware datetime (read in UAE time) or a naive one already in UAE time; the build passes site.now."""
        if now.tzinfo is not None: now = now.astimezone(dt.timezone(dt.timedelta(hours=4)))
        wd = now.weekday()   # Mon 0 … Sun 6
        if wd == 2 and now.hour >= 18: return "wed-eve"
        if wd in (3, 4, 5): return "thu-sat"
        return "rest"

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
            bd = f.get("backdrop")
            if isinstance(bd, dict):
                if not (OUR_BACKDROP.match(str(bd.get("w1280"))) and OUR_BACKDROP.match(str(bd.get("w640")))):
                    f["backdrop"] = None   # steps/backdrops.py's own paths only -- never a hotlinked/tampered value
            elif bd is not None:
                f["backdrop"] = None
        self.tpl = open(os.path.join(SRC, "page.html"), encoding="utf-8").read()
        self.og_override = {}   # (lang, parts) -> full URL; a feature (pages/og.py) fills this before pages render
        self.urls, self.hashes, self.lastmod_path = [], {}, None
        self.names = load_cinema_names(os.path.join(ROOT, "cinemas.yaml"))
        h = hashlib.sha1()
        for dp, _, fs in sorted(os.walk(SRC)):
            for f in sorted(fs): h.update(open(os.path.join(dp, f), "rb").read())
        self.v = h.hexdigest()[:10]
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
        self._sheets, self._preload, self._grid = [], "", False   # a page's own sheets (after the header's), its hero image preload
        # {old fid: canonical fid} (refresh.update_film_history): a film whose canonical fid changed keeps
        # its old URL as a noindex redirect page. Only to a film that has a page, never over a real film.
        self.redirects = {o: n for o, n in (data.get("redirects") or {}).items()
                          if isinstance(o, str) and FID.match(o) and n in self.films and o not in self.films}

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

    def score(self, f, lang):
        rt = f.get("rt") or {}
        if rt.get("critics") is not None: return f'{"النقاد" if lang == "ar" else "Critics"} {num(str(rt["critics"]) + "%")}'
        if rt.get("audience") is not None: return f'{"الجمهور" if lang == "ar" else "Audience"} {num(str(rt["audience"]) + "%")}'
        return f'<bdi class="num" dir="ltr">{esc(f["rating"])}</bdi>' if f.get("rating") else ""

    def vword(self, fid, lang):
        v = (self.films[fid].get("verdict") or {}).get("verdict") or "unknown"
        return v, L(VERDICT.get(v, VERDICT["unknown"]), lang)

    def crumbs(self, lang, *items):
        parts = [f'<a href="{P(lang)}">{esc(L(UI["s_mark"], lang))}</a>']
        for name, href in items:
            parts.append(f'<a href="{href}">{esc(name)}</a>' if href else f'<span>{esc(name)}</span>')
        return f'<nav class="crumbs" aria-label="{"المسار" if lang == "ar" else "Breadcrumb"}">{" / ".join(parts)}</nav>'

    def breadcrumb_ld(self, lang, *items):
        chain = [(L(UI["s_mark"], lang), SITE + P(lang))] + [(n, SITE + h) for n, h in items]
        return {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(chain)]}

    def page(self, lang, parts, title, desc, body, graph, pagekind, attrs="", nav="films", og_image=None, path=None, robots="", js=()):
        """Write one page from src/page.html. `js`: lazy chunks (a module's LAZY_JS) this page loads, on top
        of those a module asked for on every page of this kind (Plugin.page_js)."""
        other = "en" if lang == "ar" else "ar"
        vals = {k: esc(L(v, lang)) for k, v in UI.items()}
        strings = {k: L(v, lang) for k, v in T.items()}
        strings["cities"] = {c: L((a, e), lang) for c, a, e in CITIES}
        strings["v"] = {k: L(v, lang) for k, v in VERDICT.items()}
        strings["cards"] = {c["id"]: (c["name_ar"] if lang == "ar" else c["name_en"]) for c in self.cards}
        strings["base"] = P(lang)
        strings["mycard"] = L(CHROME_T["mycard"], lang)   # the card pill with no card chosen
        strings["langs"] = {k: L(v, lang) for k, v in LANGS.items()}
        strings["ad"] = {ch: int((c or {}).get("ad_offset_min") or 15) for ch, c in (self.d.get("chains") or {}).items() if isinstance(c, dict)}
        strings["adhan"] = "/assets/" + self.adhan_name
        strings["days"] = sorted({s["date"] for s in self.shows})
        strings["sites"] = CHAIN_SITE   # a time with no booking URL of its own books on its chain's site   # the slice dates that exist (no 404 for a day not built)
        chunks = {n: self.chunk_urls[n] for n in dict.fromkeys((*js, *self.kind_js.get(pagekind, ()), *self.kind_js.get("*", ()))) if n in self.chunk_urls}
        if chunks: strings["chunks"] = chunks   # main.js loads each after start-up
        pre = [f'<link rel="preload" href="/assets/fonts/{f}" as="font" type="font/woff2" crossorigin>' for f in FONTS[lang]]
        fp = self._first_poster
        if self._preload: pre.insert(0, self._preload)   # the page's hero image (the home billboard's frame)
        elif fp and fp.get("poster"):
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
            "cinemas_href": P(lang, "cinemas"), "thursday_href": P(lang),
            "cards_href": P(lang, "cards"), "halls_href": P(lang, "halls"),
            # «الرئيسية» is the home page only
            "c_films": ' aria-current="page"' if nav == "films" and pagekind == "home" else "",
            "c_cinemas": ' aria-current="page"' if nav == "cinemas" else "",
            "c_cards": ' aria-current="page"' if nav == "cards" else "",
            "v": self.v, "js": "/assets/" + self.js_name, "page": pagekind, "attrs": attrs, "preload": "\n".join(pre), "robots": robots,
            "og_image": esc(self.og_override.get((lang, tuple(parts))) or og_image or f"{SITE}/assets/og-{lang}.png"),
            # 1200x630 is declared only for images known to be that size (final review I2): a rendered card
            # (og_override) or the site-wide default -- never a page's own og_image (a portrait poster, a photo)
            "og_dims": (OG_DIMS if (lang, tuple(parts)) in self.og_override or not og_image else ""),
            "jsonld": json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/"),
            "strings": json.dumps(strings, ensure_ascii=False).replace("</", "<\\/"),
            "body": body + pdata, "c_thursday": "",
            # W1-P1: the page kind's own stylesheet (PAGE_CSS), and the head.inline slot (a pre-paint script); both empty
            # leave the page byte for byte as it was
            "page_css": f'<link rel="stylesheet" href="{self.page_css[pagekind]}">' if pagekind in self.page_css else "",
            "head_inline": self.slot("head.inline", lang, kind=pagekind),
        })
        vals["s_cards"] = esc(L(UI["s_cards_h"], lang))   # the header says «الأسعار والبطاقات»; crumbs keep «البطاقات»
        if pagekind in HERO_KINDS: vals["attrs"] += " data-hero"
        extra = self.nav_links(vals, lang, nav)
        self.chrome(vals, lang, nav, pagekind, city[0] if city else None, extra)
        vals["sheets"] += "".join(self._sheets)
        self.hashes[P(lang, *parts)] = hashlib.sha1((title + desc + body).encode()).hexdigest()[:12]
        out = re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals.get(m.group(1), m.group(0))), self.tpl)
        dest = path or os.path.join(self.out, *(["en"] if lang == "en" else []), *parts, "index.html")
        self.write(dest, out)
        if lang == "ar" and path is None: self.urls.append(parts)
        self._P, self._Pi, self._first_poster = [], {}, None
        self._sheets, self._preload, self._grid = [], "", False

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # the site's digits are Western, always — a hand-typed ٣ in a yaml note is corrected here
        text = text.translate({0x0660 + i: 0x30 + i for i in range(10)} | {0x06F0 + i: 0x30 + i for i in range(10)})
        open(path, "w", encoding="utf-8", newline="\n").write(text)

    def geo_attrs(self, c):
        return f' data-lat="{float(c["lat"])}" data-lng="{float(c["lng"])}"' if c.get("lat") is not None and c.get("lng") is not None else ""

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
            note = note_ar(r)
            terms = [note] if lang == "ar" and note and note != T["none_found"][0] else []
        else:
            val = f'<span class="nil">{esc(L(T["unchecked"], lang))}</span>'; terms = []
        chk = (f' <a class="src" href="{esc(r["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>'
               f' <small class="chkd">{"تحققنا" if lang == "ar" else "checked"} {esc(human_date(r.get("checked"), lang))}</small>') if r and r.get("source") else ""
        return (f'<div class="row crd">{head}<span class="val">{val}</span>'
                f'<span class="sub">{dates(esc(("، " if lang == "ar" else ", ").join(str(t) for t in terms)))}{chk}</span></div>')

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
