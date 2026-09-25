"""Build «سينما» — elyoxe.com/cinema — static pages from data/latest.json + discounts.yaml + halls.yaml.

  src/page.html     the page template (head with SEO, header, footer); loads /tools/assets/base.css then cinema.css
  src/cinema.css    the cinema layer over the /tools identity (tokens come from base.css; dark mode here)
  src/cinema.js     client: city + card (localStorage), prices after discount, «on now», cheapest for you

python build.py [--data data/latest.json] [--discounts discounts.yaml] [--halls halls.yaml] [--out out] [--preview]
  -> out/cinema/…  out/en/cinema/…  out/cinema/data/<city>.json  out/cinema/sitemap.xml
  --preview also copies ../tools/src/assets/base.css to out/tools/assets/ for a local server (never deployed from here).

Discount semantics (mirrored in cinema.js): percent -> price×(1-v/100); bogo -> price/2 per person;
excluded_halls / included_halls by hall code; valid_until in the past -> no discount; status none_found ->
«ما لقينا خصم» (we found none), never «they refuse it».
"""
import argparse, datetime as dt, hashlib, html, json, os, re, shutil, sys

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
SITE = "https://elyoxe.com"
sys.path.insert(0, ROOT)
import discounts as _disc  # noqa: E402  (Task 2: load() + apply())

CITIES = [("abu-dhabi", "أبوظبي", "Abu Dhabi"), ("dubai", "دبي", "Dubai"), ("sharjah", "الشارقة", "Sharjah"),
          ("al-ain", "العين", "Al Ain"), ("ajman", "عجمان", "Ajman"), ("ras-al-khaimah", "رأس الخيمة", "Ras Al Khaimah"),
          ("fujairah", "الفجيرة", "Fujairah"), ("umm-al-quwain", "أم القيوين", "Umm Al Quwain")]
CITY = {c[0]: (c[1], c[2]) for c in CITIES}
NEAR = {"umm-al-quwain": "ajman", "fujairah": "sharjah", "ajman": "sharjah", "ras-al-khaimah": "ajman"}
VERDICT = {"yes": ("يستاهل", "Worth it"), "mixed": ("بين بين", "Mixed"), "skip": ("تجنّبه", "Skip it"),
           "unknown": ("ما في تقييم كافي", "Not enough reviews")}
LANGS = {"English": ("إنجليزي", "English"), "Arabic": ("عربي", "Arabic"), "Hindi": ("هندي", "Hindi"), "Telugu": ("تيلوغو", "Telugu"),
         "Malayalam": ("مالايالام", "Malayalam"), "Tamil": ("تاميل", "Tamil"), "Tagalog": ("فلبيني", "Tagalog")}
GENRES = {"Action": "أكشن", "Adventure": "مغامرة", "Drama": "دراما", "Horror": "رعب", "Comedy": "كوميدي", "Animation": "أنيميشن",
          "Thriller": "إثارة", "Superhero": "أبطال خارقين", "Family": "عائلي", "Romance": "رومانسي", "Sci-Fi": "خيال علمي"}
CONF_WEAK = ("غير مؤكد — تأكد من الشباك", "Unconfirmed — check at the box office")
UI = {
    "s_cinema": ("سينما", "Cinema"), "s_home": ("السينما", "Cinema"), "s_cities": ("المدن", "Cities"), "s_cards": ("البطاقات", "Cards"),
    "s_tools": ("الأدوات", "Tools"), "s_halls": ("القاعات", "Halls"), "s_alt": ("English", "العربية"),
    "s_footer": ("سينما من Elyoxe — الأسعار من السينمات نفسها، والخصومات متحقَّق منها بتاريخها", "Cinema by Elyoxe — prices from the cinemas themselves, discounts checked and dated"),
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
}
CITY_T = {k: v for k, v in CITY.items()}


def esc(s):
    return html.escape("" if s is None else str(s))


def L(pair, lang):
    return pair[0] if lang == "ar" else pair[1]


def P(lang, *parts):
    p = "/".join(x for x in parts if x)
    return ("/en" if lang == "en" else "") + "/cinema/" + (p + "/" if p else "")


DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


SCHED_BUDGET = 110_000   # bytes of schedule markup per page; with the chrome a page stays under ~150 KB
BCP47 = {"English": "en", "Arabic": "ar", "Hindi": "hi", "Telugu": "te", "Malayalam": "ml", "Tamil": "ta", "Tagalog": "tl",
         "Urdu": "ur", "Bengali": "bn", "Kannada": "kn", "French": "fr", "Spanish": "es", "Japanese": "ja", "Korean": "ko",
         "Chinese": "zh", "Russian": "ru", "Turkish": "tr", "Persian": "fa", "Filipino": "tl", "Punjabi": "pa", "Marathi": "mr"}
PCT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?\s?%)")


def dates(h):
    """escaped text -> the same with every ISO date and every percentage isolated. Inside an Arabic run a
    number turns Arabic (UBA W2), so «خصم 20%» would print «خصم %20» and 2027-08-05 as 05-08-2027."""
    # dir="ltr": span.num is unicode-bidi:plaintext in base.css, which falls back to the page's RTL for a
    # run with no strong letter — «88%» alone would still print «%88»; base.css isolates span.num[dir=ltr]
    return PCT.sub(r'<span class="num" dir="ltr">\1</span>', DATE.sub(r'<bdi class="num">\1</bdi>', h))


def money(x):
    return f"{float(x):.2f}"


def num(x, cls="num"):
    d = ' dir="ltr"' if "%" in str(x) else ""
    return f'<span class="{cls}"{d}>{esc(x)}</span>'


ARABIC = re.compile(r"[؀-ۿ]")
RERELEASE = ("إعادة عرض", "Re-release")


def clean_reader_name(name):
    """A raw reader cinema name made presentable when cinemas.yaml has no entry: «Al Foah -Al Ain» -> «Al Foah - Al Ain»."""
    n = re.sub(r"\s*-\s*", " - ", (name or "").strip())
    return re.sub(r"\s+", " ", n).strip()


def load_cinema_names(path):
    if not path or not os.path.exists(path): return {}
    return (yaml.safe_load(open(path, encoding="utf-8")) or {}).get("cinemas") or {}


def genre_words(genres, lang):
    """Enriched genres are {"ar": [...], "en": [...]}; older data has a plain English list."""
    if isinstance(genres, dict):
        words = genres.get(lang) or ([] if lang == "en" else [GENRES.get(g, g) for g in genres.get("en") or []])
    else:
        words = [GENRES.get(g, g) if lang == "ar" else g for g in genres or []]
    return [w for w in words if w]


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


SAFE_URL = re.compile(r"^https?://", re.I)


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
    def __init__(self, data, disc, halls, out):
        self.d, self.disc, self.h, self.out = data, disc, halls, out
        self.rules, self.cards = disc["rules"], disc["cards"]
        self.now = parse_iso(data.get("generated") or dt.datetime.now().isoformat())
        self.today = self.now.date().isoformat()
        self.tomorrow = (self.now.date() + dt.timedelta(days=1)).isoformat()
        self.films, self.cinemas = data.get("films", {}), data.get("cinemas", {})
        self.shows = [s for s in data.get("shows", []) if s.get("cinema") in self.cinemas and s.get("film") in self.films]
        for s in self.shows:  # a chain's booking URL is a link on our page: http(s) only, never javascript:
            if s.get("book") and not SAFE_URL.match(str(s["book"])): s["book"] = None
        for f in self.films.values():  # v lands in class="v-…": a hand-edited verdict file must not inject
            vd = f.get("verdict")
            if isinstance(vd, dict) and vd.get("verdict") not in VERDICT: f["verdict"] = dict(vd, verdict="unknown")
        self.tpl = open(os.path.join(SRC, "page.html"), encoding="utf-8").read()
        self.urls, self.hashes, self.lastmod_path = [], {}, None
        self.names = load_cinema_names(os.path.join(ROOT, "cinemas.yaml"))
        self.v = hashlib.sha1(b"".join(open(os.path.join(SRC, f), "rb").read() for f in sorted(os.listdir(SRC)))).hexdigest()[:10]

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

    def title_html(self, fid, lang, tag="b", cls="t"):
        t = self.ftitle(fid, lang)
        attr = ' lang="en" dir="ltr"' if lang == "ar" and not self.films[fid].get("title_ar") else ""
        return f'<{tag} class="{cls}"{attr}>{esc(t)}</{tag}>'

    def hall_code_label(self, s):
        return s.get("hall") or "OTHER", s.get("hall_label") or ""

    def hkey(self, s):
        c = self.cinemas[s["cinema"]]["chain"]; code, label = self.hall_code_label(s)
        return self.h.key(c, code, label)

    def hname(self, s, lang):
        c = self.cinemas[s["cinema"]]["chain"]; code, label = self.hall_code_label(s)
        return self.h.name(c, code, label, lang)

    def chain_ok(self, chain):
        return (self.d.get("chains", {}).get(chain) or {}).get("ok", True)

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
        """hall key -> {code, label, seats{seat: aed}, asof} from today's shows first, then any day.
        Live prices win over the fallback table; a hall priced only from the table carries `asof`
        (the table entry's date) so its cells say «السعر بتاريخ …» instead of borrowing the live freshness."""
        out = {}
        shows = [s for s in self.shows if s["cinema"] == cid]
        for s in sorted(shows, key=lambda s: s["date"] != self.today):
            k = self.hkey(s); code, label = self.hall_code_label(s)
            h = out.setdefault(k, {"code": code, "label": label, "seats": {}, "sample": s, "asof": None, "_table": {}})
            asof = self.table_date(s)
            seats = h["_table"] if asof else h["seats"]
            for p in s.get("prices") or []:
                if p.get("aed") and p["aed"] > 0:
                    cur = seats.get(p["seat"])
                    seats[p["seat"]] = p["aed"] if cur is None else min(cur, p["aed"])
            if asof and (h["asof"] is None or asof < h["asof"]): h["asof"] = asof
        for h in out.values():
            tbl = h.pop("_table")
            if h["seats"]: h["asof"] = None
            elif tbl: h["seats"] = tbl
            else: h["asof"] = None
        for code in self.cinemas[cid].get("halls") or []:
            if isinstance(code, str) and not any(v["code"] == code for v in out.values()) and code not in ("OTHER",):
                out.setdefault(self.h.key(self.cinemas[cid]["chain"], code, ""), {"code": code, "label": "", "seats": {}, "sample": None, "asof": None})
        order = lambda kv: (kv[1]["code"] != "Standard", min(kv[1]["seats"].values()) if kv[1]["seats"] else 9999)
        return dict(sorted(out.items(), key=order))

    def min_price(self, shows):
        best = None
        for s in shows:
            for p in s.get("prices") or []:
                if p.get("aed") and (best is None or p["aed"] < best[0]): best = (p["aed"], s)
        return best

    # -------- page plumbing
    def picker(self, lang, city=None, show_city=True):
        cities = "".join(f'<option value="{c}"{" selected" if c == city else ""}>{esc(L((a, e), lang))}</option>' for c, a, e in CITIES)
        gov = [c for c in self.cards if c.get("kind") == "gov"]; bank = [c for c in self.cards if c.get("kind") != "gov"]
        opt = lambda cs: "".join(f'<option value="{esc(c["id"])}">{esc(c["name_ar"] if lang == "ar" else c["name_en"])}</option>' for c in cs)
        cards = (f'<option value="">{esc(L(T["nocard"], lang))}</option>'
                 f'<optgroup label="{"بطاقات حكومية" if lang == "ar" else "Government cards"}">{opt(gov)}</optgroup>'
                 + (f'<optgroup label="{"بطاقات البنوك" if lang == "ar" else "Bank cards"}">{opt(bank)}</optgroup>' if bank else ""))
        c_sel = (f'<span>{"أنا في" if lang == "ar" else "I’m in"}</span> <label class="sel"><span class="vh">{"المدينة" if lang == "ar" else "City"}</span>'
                 f'<select data-city>{cities}</select></label> ') if show_city else ""
        k_sel = (f'<span>{("ومعي" if show_city else "بطاقتك") if lang == "ar" else ("with" if show_city else "Your card")}</span> '
                 f'<label class="sel"><span class="vh">{"البطاقة" if lang == "ar" else "Card"}</span><select data-card>{cards}</select></label>')
        return (f'<form class="pick{" big" if show_city else ""}" data-pick onsubmit="return false">{c_sel}{k_sel}</form>'
                f'<div class="cardnote" data-cardnote hidden></div>')

    def crumbs(self, lang, *items):
        parts = [f'<a href="{P(lang)}">{esc(L(UI["s_cinema"], lang))}</a>']
        for name, href in items:
            parts.append(f'<a href="{href}">{esc(name)}</a>' if href else esc(name))
        return f'<p class="crumbs">{" / ".join(parts)}</p>'

    def breadcrumb_ld(self, lang, *items):
        chain = [(L(UI["s_cinema"], lang), SITE + P(lang))] + [(n, SITE + h) for n, h in items]
        return {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(chain)]}

    def page(self, lang, parts, title, desc, body, graph, pagekind, attrs=""):
        other = "en" if lang == "ar" else "ar"
        vals = {k: esc(L(v, lang)) for k, v in UI.items()}
        strings = {k: L(v, lang) for k, v in T.items()}
        strings["cities"] = {c: L((a, e), lang) for c, a, e in CITIES}
        strings["v"] = {k: L(v, lang) for k, v in VERDICT.items()}
        strings["cards"] = {c["id"]: (c["name_ar"] if lang == "ar" else c["name_en"]) for c in self.cards}
        strings["base"] = P(lang)
        vals.update({
            "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "locale": "ar_AE" if lang == "ar" else "en_US",
            "title": esc(title), "description": esc(desc),
            "url": SITE + P(lang, *parts), "url_ar": SITE + P("ar", *parts), "url_en": SITE + P("en", *parts),
            "alt": P(other, *parts), "alt_lang": other, "hub": P(lang), "cities_href": P(lang) + "#cities",
            "cards_href": P(lang, "cards"), "tools_href": "/tools/" if lang == "ar" else "/en/tools/",
            "home": "/" if lang == "ar" else "/en/", "v": self.v, "page": pagekind, "attrs": attrs,
            "og": "og-ar.png" if lang == "ar" else "og-en.png",
            "jsonld": json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/"),
            "strings": json.dumps(strings, ensure_ascii=False).replace("</", "<\\/"),
            "body": body,
        })
        self.hashes[P(lang, *parts)] = hashlib.sha1((title + desc + body).encode()).hexdigest()[:12]
        out = re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals.get(m.group(1), m.group(0))), self.tpl)
        self.write(os.path.join(self.out, *(["en"] if lang == "en" else []), "cinema", *parts, "index.html"), out)
        if lang == "ar": self.urls.append(parts)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # the site's digits are Western, always — a hand-typed ٣ in a yaml note is corrected here
        text = text.translate({0x0660 + i: 0x30 + i for i in range(10)} | {0x06F0 + i: 0x30 + i for i in range(10)})
        open(path, "w", encoding="utf-8", newline="\n").write(text)

    # -------- film tile (home, city)
    def film_tile(self, fid, lang, shows):
        f = self.films[fid]; v = (f.get("verdict") or {}).get("verdict") or "unknown"
        rt = f.get("rt") or {}
        poster = (f'<img class="poster" src="{esc(f["poster"])}" alt="" loading="lazy" width="120" height="180" onerror="this.remove()">'
                  if f.get("poster") else "")
        other_title = f.get("title") if lang == "ar" and f.get("title_ar") else None
        rts = []
        if rt.get("critics") is not None: rts.append(f'{"النقاد" if lang == "ar" else "Critics"} {num(str(rt["critics"]) + "%")}')
        if rt.get("audience") is not None: rts.append(f'{"الجمهور" if lang == "ar" else "Audience"} {num(str(rt["audience"]) + "%")}')
        best = self.min_price([s for s in shows if s["film"] == fid and s["date"] == self.today])
        cheap = (f'<span class="lbl">{"أرخص تذكرة اليوم" if lang == "ar" else "Cheapest today"}</span>'
                 f'<span class="amt"><span class="num">{money(best[0])}</span> <small>{esc(L(T["aed"], lang))}</small></span>'
                 f'<span class="where">{esc(self.cname(best[1]["cinema"], lang))}</span>' + self.asof_html(self.table_date(best[1]), lang)) if best else \
                f'<span class="lbl">{esc(L(T["box"], lang))}</span>'
        meta = " ".join(x for x in [f'<span class="rr">{esc(L(RERELEASE, lang))}</span>' if f.get("rerelease") else "",
                                    num(f["rating"]) if f.get("rating") else "",
                                    num(f"{f['runtime']}") + (" د" if lang == "ar" else " min") if f.get("runtime") else ""] if x)
        return (f'<a class="film v-{v}" href="{P(lang, "film", fid)}" data-fid="{esc(fid)}">{poster}<span class="fbody">'
                f'<span class="top"><span class="v">{esc(L(VERDICT.get(v, VERDICT["unknown"]), lang))}</span><span class="meta">{meta}</span></span>'
                f'{self.title_html(fid, lang)}'
                + (f'<span class="te" lang="en" dir="ltr">{esc(other_title)}</span>' if other_title else "")
                + (f'<span class="rt">{" ".join(rts)}</span>' if rts else "")
                + f'<span class="cheap" data-cheap>{cheap}</span></span></a>')

    # ================================================================ pages
    def home(self):
        films = sorted(self.films, key=lambda fid: (-len([s for s in self.shows if s["film"] == fid and s["date"] == self.today]), fid))
        for lang in ("ar", "en"):
            by_city = {c: len([x for x in self.cinemas.values() if x.get("city") == c]) for c, _, _ in CITIES}
            body = (f'<p class="crumbs">Elyoxe / {esc(L(UI["s_cinema"], lang))}</p>'
                    + f'<h1>{"كل سينما في الإمارات، والسعر بعد خصم بطاقتك" if lang == "ar" else "Every cinema in the UAE, priced after your card discount"}</h1>'
                    + f'<p class="lead">{"مواعيد اليوم وسعر كل قاعة وكل فئة كرسي، من السينمات نفسها. اختر مدينتك وبطاقتك، والأسعار تنحسب لك." if lang == "ar" else "Today’s showtimes and the price of every hall and seat class, straight from the cinemas. Pick your city and card; prices are worked out for you."}</p>'
                    + self.picker(lang, "dubai")
                    + f'<section class="now" data-now><h2><i class="live" aria-hidden="true"></i>{"يبدأ خلال ساعتين" if lang == "ar" else "Starting in the next 2 hours"} <span data-now-city></span></h2>'
                      f'<ul class="strip" data-now-list></ul><p class="hint" data-now-empty>{"فعّل الجافاسكربت عشان تشوف العروض الجاية في مدينتك." if lang == "ar" else "Turn on JavaScript to see what starts soon in your city."}</p></section>'
                    + f'<section class="films"><h2>{"الأفلام المعروضة" if lang == "ar" else "Now showing"} <small class="num">{len(films)}</small></h2>'
                      f'<div class="fgrid">{"".join(self.film_tile(fid, lang, self.shows) for fid in films)}</div></section>'
                    + f'<section class="cities" id="cities"><h2>{"المدن" if lang == "ar" else "Cities"}</h2><ul class="clist">'
                    + "".join(f'<li><a href="{P(lang, c)}">{esc(L((a, e), lang))}</a> <span class="n">{num(by_city[c])} {"سينما" if lang == "ar" else ("cinema" if by_city[c] == 1 else "cinemas")}</span></li>' for c, a, e in CITIES)
                    + '</ul></section>'
                    + self.cards_strip(lang)
                    + self.sources(lang))
            title = ("سينما الإمارات اليوم — الأفلام والأسعار وخصم فزعة وإسعاد | Elyoxe" if lang == "ar"
                     else "UAE cinemas today — films, ticket prices and card discounts | Elyoxe")
            desc = ("مواعيد أفلام اليوم في كل سينمات الإمارات، سعر التذكرة لكل قاعة وفئة، والسعر بعد خصم فزعة وإسعاد وحماة الوطن وعروض البنوك، وهل الفيلم يستاهل."
                    if lang == "ar" else "Today’s showtimes at every UAE cinema, the ticket price per hall and seat class, the price after Fazaa, Esaad, Homat Al Watan and bank offers, and whether the film is worth it.")
            graph = [{"@type": "WebSite", "name": L(UI["s_cinema"], lang) + " — Elyoxe", "url": SITE + P(lang), "inLanguage": lang},
                     {"@type": "ItemList", "name": "Films", "itemListElement": [
                         {"@type": "ListItem", "position": i + 1, "url": SITE + P(lang, "film", fid), "name": self.ftitle(fid, lang)} for i, fid in enumerate(films)]},
                     self.breadcrumb_ld(lang)]
            self.page(lang, (), title, desc, body, graph, "home")

    def cards_strip(self, lang):
        gov = [c for c in self.cards if c.get("kind") == "gov"]
        bank = [c for c in self.cards if c.get("kind") != "gov"]
        a = lambda c: f'<a href="{P(lang, "cards", c["id"])}">{esc(c["name_ar"] if lang == "ar" else c["name_en"])}</a>'
        return (f'<section class="cardsx"><h2>{"خصم بطاقتك في السينما" if lang == "ar" else "Your card at the cinema"}</h2>'
                f'<p class="lead">{"وين تنفع كل بطاقة، كم تخصم، وشروطها — ومتى تحققنا منها." if lang == "ar" else "Where each card works, how much it takes off, the conditions — and when we checked."}</p>'
                f'<p class="links"><span>{"حكومية" if lang == "ar" else "Government"}</span> {" ".join(a(c) for c in gov)}</p>'
                + (f'<p class="links"><span>{"بنوك" if lang == "ar" else "Banks"}</span> {" ".join(a(c) for c in bank)}</p>' if bank else "")
                + f'<p class="links"><a href="{P(lang, "cards")}">{"كل البطاقات في جدول واحد" if lang == "ar" else "All cards in one table"}</a> <a href="{P(lang, "halls")}">{"القاعات المميزة، شو فيها؟" if lang == "ar" else "Premium halls, explained"}</a></p></section>')

    def sources(self, lang):
        rows = []
        for chain, ch in sorted(self.d.get("chains", {}).items()):
            at = parse_iso(ch["at"]) if ch.get("at") else None
            state = ("" if ch.get("ok", True) else f' <span class="stale">{"ما قدرنا نحدّث آخر مرة" if lang == "ar" else "last refresh failed"}</span>')
            rows.append(f'<li><b>{esc(self.h.chain_name(chain, lang))}</b> '
                        + (f'<span class="age" data-at="{esc(ch["at"])}">{esc(L(T["updated"], lang))} {esc(ago(at, self.now, lang))}</span>' if at else "")
                        + state + '</li>')
        return (f'<section class="srcs"><h2>{"من وين الأسعار" if lang == "ar" else "Where the prices come from"}</h2>'
                f'<p class="hint">{"من نظام الحجز عند كل سينما، ثلاث مرات باليوم. إذا ما حصلنا السعر نكتب «السعر في الشباك»، وما نخمّن." if lang == "ar" else "From each chain’s booking system, three times a day. When we can’t read a price we say «price at the box office» — we never guess."}</p>'
                f'<ul class="chains">{"".join(rows)}</ul></section>')

    # -------------------------------------------------- city
    def city_pages(self):
        for city, ar, en in CITIES:
            cids = [cid for cid, c in self.cinemas.items() if c.get("city") == city]
            shows = [s for s in self.shows if s["cinema"] in cids]
            today = [s for s in shows if s["date"] == self.today]
            fids = sorted({s["film"] for s in today}, key=lambda f: self.ftitle(f, "en"))
            for lang in ("ar", "en"):
                cn = L((ar, en), lang)
                body = self.crumbs(lang, (cn, None))
                body += f'<h1>{"سينما " + cn + " اليوم" if lang == "ar" else "Cinemas in " + cn + " today"}</h1>'
                if not cids:
                    near = NEAR.get(city, "dubai"); nn = L(CITY[near], lang)
                    body += (f'<p class="lead">{f"ما عندنا بيانات سينما في {cn} لين الحين. أقرب مدينة عندنا: " if lang == "ar" else f"We have no cinema data for {cn} yet. Nearest city: "}'
                             f'<a href="{P(lang, near)}">{esc(nn)}</a>.</p>')
                else:
                    body += (f'<p class="lead">{f"{len(cids)} سينما و{len(fids)} فيلم اليوم. السعر لكل قاعة من السينما نفسها، وينحسب بعد خصم بطاقتك." if lang == "ar" else f"{len(cids)} cinemas and {len(fids)} films today. Every hall’s price comes from the cinema itself and is worked out after your card."}</p>')
                    body += self.picker(lang, city)
                    body += f'<section><h2>{"السينمات" if lang == "ar" else "Cinemas"}</h2><div class="rows">'
                    for cid in cids:
                        c = self.cinemas[cid]; pr = self.cinema_prices(cid)
                        # the lowest known price in any hall (an unpriced Standard hall must not hide a priced one)
                        low = min(((a, h["code"], k, h["asof"]) for k, h in pr.items() for a in h["seats"].values()), default=None)
                        halls = [k for k in pr if k != "Standard"]
                        hn = ("، " if lang == "ar" else ", ").join(self.h.name(c["chain"], pr[k]["code"], pr[k]["label"], lang) for k in halls)
                        body += (f'<div class="row cin"><a class="nm" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a>'
                                 f'<span class="sub">{("<bdi>" + esc(hn) + "</bdi>") if hn else ""} {self.fresh(c["chain"], lang)}</span>'
                                 f'<span class="from">{("من " if lang == "ar" else "from ") + self.pcell(low[0], c["chain"], low[1], low[2], cid, low[3], lang) if low else self.box(lang)}</span></div>')
                    body += '</div></section>'
                    for mode in ("links", "plain"):
                        sched = f'<section><h2>{"اليوم في " + cn if lang == "ar" else "Today in " + cn}</h2><div class="sched">'
                        for fid in fids:
                            fs = [s for s in today if s["film"] == fid]
                            v = ((self.films[fid].get("verdict") or {}).get("verdict")) or "unknown"
                            sched += (f'<div class="srow"><div class="sf"><a href="{P(lang, "film", fid)}">{self.title_html(fid, lang, "b", "t")}</a>'
                                      f'<span class="v v-{v}">{esc(L(VERDICT.get(v, VERDICT["unknown"]), lang))}</span></div><div class="sc">')
                            for cid in cids:
                                cs = [s for s in fs if s["cinema"] == cid]
                                if not cs: continue
                                sched += f'<p><a class="cn" href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a> {self.times(cs, lang, tag_halls=True, links=mode == "links")}</p>'
                            sched += '</div></div>'
                        sched += '</div></section>'
                        if len(sched.encode()) <= SCHED_BUDGET: break
                    body += sched
                title = (f"سينما {cn} اليوم — الأفلام والأسعار وخصم فزعة" if lang == "ar" else f"{cn} cinemas today — films, prices and card discounts")
                names = ("، " if lang == "ar" else ", ").join(self.cname(c, lang) for c in cids[:6])
                desc = (f"أفلام سينمات {cn} اليوم ومواعيدها، سعر التذكرة لكل قاعة، والسعر بعد خصم فزعة وإسعاد وحماة الوطن والبنوك. {names}" if lang == "ar"
                        else f"Films and showtimes at {cn} cinemas today, ticket prices per hall, and the price after Fazaa, Esaad, Homat Al Watan and bank cards. {names}")
                graph = [{"@type": "ItemList", "name": title, "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "item": self.theater_ld(cid, lang)} for i, cid in enumerate(cids)]},
                    self.breadcrumb_ld(lang, (cn, P(lang, city)))]
                self.page(lang, (city,), title, desc, body, graph, "city", f' data-city="{city}" data-chains="{" ".join(sorted({self.cinemas[c]["chain"] for c in cids}))}"')

    def times(self, shows, lang, tag_halls=False, links=True):
        """Showtimes as one lean list per day: <span class="times" data-d="…"><a href=booking>19:30</a>…</span>.
        cinema.js reads the day from data-d and the time from each item's first 5 characters."""
        out = []
        for d in sorted({s["date"] for s in shows}):
            items = []
            for s in sorted((s for s in shows if s["date"] == d), key=lambda s: s["time"]):
                tag = f'<small>{self.hall_html(s, lang)}</small>' if tag_halls and self.hkey(s) != "Standard" else ""
                items.append(f'<a href="{esc(s["book"])}">{esc(s["time"])}{tag}</a>' if links and s.get("book") else f'<span>{esc(s["time"])}{tag}</span>')
            out.append(f'<span class="times" data-d="{d}">{"".join(items)}</span>')
        return "".join(out)

    def cname_html(self, cid, lang):
        """The cinema's name, marked English when an Arabic page has only the English name."""
        n = esc(self.cname(cid, lang))
        return f'<bdi lang="en">{n}</bdi>' if self.cname_is_en(cid, lang) else n

    def hall_html(self, s, lang):
        n = self.hname(s, lang)
        return f'<bdi lang="en">{esc(n)}</bdi>' if lang == "ar" and re.search(r"[A-Za-z]", n) else esc(n)

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
        if BCP47.get(self.films[s["film"]].get("lang")): e["inLanguage"] = BCP47[self.films[s["film"]]["lang"]]
        ps = [p["aed"] for p in s.get("prices") or [] if p.get("aed")]
        if ps: e["offers"] = {"@type": "Offer", "price": money(min(ps)), "priceCurrency": "AED", "url": s.get("book") or SITE, "availability": "https://schema.org/InStock"}
        return e

    # -------------------------------------------------- cinema
    def cinema_pages(self):
        for cid, c in self.cinemas.items():
            city, chain = c.get("city"), c["chain"]
            pr = self.cinema_prices(cid)
            shows = [s for s in self.shows if s["cinema"] == cid]
            for lang in ("ar", "en"):
                cn, name = L(CITY.get(city, (city, city)), lang), self.cname(cid, lang)
                body = self.crumbs(lang, (cn, P(lang, city)), (name, None))
                body += f'<h1{" lang=\"en\"" if self.cname_is_en(cid, lang) else ""}>{esc(name)}</h1>'
                # the name already says the mall; the reader's address is English, isolated
                addr = esc(c.get("address") or ("" if cid in self.names else c.get("mall")) or "")
                addr = f'<bdi lang="en">{addr}</bdi>' if addr else ""
                maps = c.get("maps") or ("https://www.google.com/maps/search/?api=1&query=" + re.sub(r"\s+", "+", c.get("name") or cid))
                body += (f'<p class="lead">{addr}{" — " if addr else ""}<a href="{esc(maps)}" rel="noopener" target="_blank">{"افتح في الخريطة" if lang == "ar" else "Open in Maps"}</a></p>'
                         f'<p class="freshline">{self.fresh(chain, lang, always=True)}</p>')
                body += self.picker(lang, city, show_city=False)
                # halls: explained + prices
                body += f'<section><h2>{"القاعات والأسعار" if lang == "ar" else "Halls and prices"}</h2><div class="halls">'
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
                    body += (f'<div class="hall"><h3{" lang=\"en\"" if lang == "ar" and re.search("[A-Za-z]", hn) else ""}>{esc(hn)}</h3>' + (f'<p>{dates(esc(what))}{note}{src}</p>' if what else "") +
                             f'<table class="prices"><thead><tr><th scope="col">{"الفئة" if lang == "ar" else "Seat"}</th><th scope="col">{"السعر" if lang == "ar" else "Price"} <small>{esc(L(T["aed"], lang))}</small></th></tr></thead><tbody>{seats}</tbody></table></div>')
                body += f'</div><p class="hint"><a href="{P(lang, "halls")}">{"كل القاعات المميزة في الإمارات، مقارنة" if lang == "ar" else "Every premium hall in the UAE, compared"}</a></p></section>'
                # cards
                body += f'<section><h2>{"البطاقات في " + self.h.chain_name(chain, lang) if lang == "ar" else "Cards at " + self.h.chain_name(chain, lang)}</h2><div class="rows">'
                for card in self.cards:
                    r = rule_for(self.rules, chain, card["id"]); st = rule_state(r, self.today)
                    if st == "unchecked": continue
                    body += self.card_row(card, chain, r, st, lang, P(lang, "cards", card["id"]))
                body += '</div></section>'
                # schedule
                for day, lab in ((self.today, ("اليوم", "Today")), (self.tomorrow, ("بكرة", "Tomorrow"))):
                    ds = [s for s in shows if s["date"] == day]
                    if not ds: continue
                    body += f'<section><h2>{esc(L(lab, lang))} <small class="num">{day}</small></h2><div class="sched">'
                    for fid in sorted({s["film"] for s in ds}, key=lambda f: self.ftitle(f, "en")):
                        fs = [s for s in ds if s["film"] == fid]
                        body += f'<div class="srow"><div class="sf"><a href="{P(lang, "film", fid)}">{self.title_html(fid, lang)}</a></div><div class="sc">'
                        for k in dict.fromkeys(self.hkey(s) for s in fs):
                            hs = [s for s in fs if self.hkey(s) == k]
                            body += f'<p><span class="hn">{self.hall_html(hs[0], lang)}</span> {self.times(hs, lang)}</p>'
                        body += '</div></div>'
                    body += '</div></section>'
                title = (f"{name} — أسعار التذاكر ومواعيد اليوم وخصم البطاقات" if lang == "ar" else f"{name} — ticket prices, today’s showtimes and card discounts")
                desc = (f"مواعيد أفلام {name} اليوم، سعر التذكرة لكل قاعة وفئة، شو الفرق بين القاعات، والسعر بعد خصم فزعة وإسعاد والبنوك." if lang == "ar"
                        else f"Today’s showtimes at {name}, ticket prices per hall and seat class, what each hall offers, and the price after Fazaa, Esaad and bank cards.")
                th = self.theater_ld(cid, lang)
                th["event"] = [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:40]
                graph = [th, self.breadcrumb_ld(lang, (cn, P(lang, city)), (name, P(lang, city, cid)))]
                self.page(lang, (city, cid), title, desc, body, graph, "cinema", f' data-city="{city}" data-chains="{chain}"')

    def card_row(self, card, chain, r, st, lang, card_href=None, label=None):
        cname = label or (card["name_ar"] if lang == "ar" else card["name_en"])
        head = f'<a class="nm" href="{card_href}">{esc(cname)}</a>' if card_href else f'<span class="nm">{esc(cname)}</span>'
        if st == "ok":
            val = f'<b class="off{" txt" if r.get("type") in ("bogo", "fixed") else ""}">{dates(esc(rule_offer(r, lang)))}</b>'
            terms = rule_terms(r, lang)
        elif st == "expired":
            val = f'<span class="nil">{esc(L(T["expired"], lang))}</span>'; terms = [f'{"كان" if lang == "ar" else "Was"} {rule_offer(r, lang)}, {"لين" if lang == "ar" else "until"} {r.get("valid_until")}']
        elif st == "none_found":
            val = f'<span class="nil">{esc(L(T["none_found"], lang))}</span>'
            terms = [r["note_ar"]] if lang == "ar" and r.get("note_ar") and r["note_ar"] != T["none_found"][0] else []
        else:
            val = f'<span class="nil">{esc(L(T["unchecked"], lang))}</span>'; terms = []
        w = f' <small class="weak">{esc(L(CONF_WEAK, lang))}</small>' if weak(r) and st == "ok" else ""
        chk = (f' <a class="src" href="{esc(r["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>'
               f' <small class="chkd">{"تحققنا" if lang == "ar" else "checked"} {num(r.get("checked"))}</small>') if r and r.get("source") else ""
        return (f'<div class="row crd">{head}<span class="val">{val}{w}</span>'
                f'<span class="sub">{dates(esc(" · ".join(str(t) for t in terms)))}{chk}</span></div>')

    # -------------------------------------------------- film
    def film_pages(self):
        for fid, f in self.films.items():
            shows = [s for s in self.shows if s["film"] == fid]
            vd = f.get("verdict") or {}; v = vd.get("verdict") or "unknown"
            for lang in ("ar", "en"):
                t = self.ftitle(fid, lang)
                body = self.crumbs(lang, (t, None))
                attr = ' lang="en" dir="ltr"' if lang == "ar" and not f.get("title_ar") else ""
                body += f'<h1{attr}>{esc(t)}</h1>'
                if lang == "ar" and f.get("title_ar") and f.get("title"): body += f'<p class="te" lang="en" dir="ltr">{esc(f["title"])}</p>'
                if f.get("rerelease"):
                    yr = f' <span class="num">{esc(f["year"])}</span>' if f.get("year") else ""
                    body += f'<p class="rr">{esc(L(RERELEASE, lang))}{" — من سنة" if lang == "ar" and yr else (" — first released" if yr else "")}{yr}</p>'
                facts = []
                if f.get("rating"): facts.append(("التصنيف", "Rating", num(f["rating"])))
                if f.get("runtime"): facts.append(("المدة", "Runtime", num(f["runtime"]) + (" دقيقة" if lang == "ar" else " min")))
                if f.get("lang"): facts.append(("اللغة", "Language", esc(L(LANGS.get(f["lang"], (f["lang"], f["lang"])), lang))))
                gw = genre_words(f.get("genres"), lang)
                if gw: facts.append(("النوع", "Genre", esc(("، " if lang == "ar" else ", ").join(gw))))
                rt = f.get("rt") or {}
                if rt.get("critics") is not None: facts.append(("نقاد Rotten Tomatoes", "Rotten Tomatoes critics", num(f'{rt["critics"]}%')))
                if rt.get("audience") is not None: facts.append(("جمهور Rotten Tomatoes", "Rotten Tomatoes audience", num(f'{rt["audience"]}%')))
                body += (f'<section class="verdict v-{v}"><p class="word">{esc(L(VERDICT.get(v, VERDICT["unknown"]), lang))}</p>'
                         + (f'<p class="say">{dates(esc(vd.get("ar") if lang == "ar" else vd.get("en")))}</p>' if (vd.get("ar") if lang == "ar" else vd.get("en")) else "")
                         + (f'<p class="basis"><bdi dir="ltr">{dates(esc(vd["basis"]))}</bdi></p>' if vd.get("basis") else "")
                         + '</section>')
                body += '<dl class="facts">' + "".join(f'<div><dt>{esc(a if lang == "ar" else e)}</dt><dd>{val}</dd></div>' for a, e, val in facts) + '</dl>'
                syn = f.get("synopsis_ar") if lang == "ar" else None
                syn = syn or f.get("synopsis") or f.get("overview")
                if syn: body += f'<p class="syn"{" lang=\"en\" dir=\"ltr\"" if lang == "ar" and not f.get("synopsis_ar") else ""}>{esc(syn)}</p>'
                body += self.picker(lang, "dubai")
                cities = [c for c, _, _ in CITIES if any(self.cinemas[s["cinema"]].get("city") == c for s in shows)]
                if not cities:
                    body += f'<p class="lead">{"ما لقينا عروض لهذا الفيلم في اليومين الجايين." if lang == "ar" else "No shows for this film in the next two days."}</p>'
                # the schedule is most of the page's weight: render it as richly as the budget allows
                for mode in ("full", "today", "plain"):
                    sched = self.film_schedule(shows, cities, lang, mode)
                    if len(sched.encode()) <= SCHED_BUDGET: break
                body += sched
                vword = L(VERDICT.get(v, VERDICT["unknown"]), lang)
                title = (f"فيلم {t} في سينما الإمارات — المواعيد والأسعار، ويستاهل؟" if lang == "ar" else f"{t} in UAE cinemas — showtimes, prices and is it worth it?")
                desc = (f"{t}: {vword}. مواعيد العرض في سينمات الإمارات اليوم وبكرة، سعر التذكرة لكل قاعة، والسعر بعد خصم بطاقتك." if lang == "ar"
                        else f"{t}: {vword}. Showtimes in UAE cinemas today and tomorrow, ticket prices per hall, and the price after your card discount.")
                movie = {"@type": "Movie", "name": f.get("title") or t, "url": SITE + P(lang, "film", fid)}
                if BCP47.get(f.get("lang")): movie["inLanguage"] = BCP47[f["lang"]]
                if f.get("title_ar"): movie["alternateName"] = f["title_ar"]
                if f.get("runtime"): movie["duration"] = f"PT{int(f['runtime'])}M"
                if genre_words(f.get("genres"), "en"): movie["genre"] = genre_words(f.get("genres"), "en")
                if f.get("poster"): movie["image"] = f["poster"]
                if f.get("rating"): movie["contentRating"] = f["rating"]
                if f.get("year"): movie["dateCreated"] = str(f["year"])
                imdb = f["imdb"].get("id") if isinstance(f.get("imdb"), dict) else f.get("imdb")
                if imdb: movie["sameAs"] = f"https://www.imdb.com/title/{imdb}/"
                graph = [movie] + [self.screening_ld(s, lang) for s in shows if s["date"] == self.today][:30] + [self.breadcrumb_ld(lang, (t, P(lang, "film", fid)))]
                self.page(lang, ("film", fid), title, desc, body, graph, "film", f' data-chains="{" ".join(sorted({self.cinemas[s["cinema"]]["chain"] for s in shows}))}"')

    def film_schedule(self, shows, cities, lang, mode):
        """city → cinema → hall: prices once per hall, then today's (and tomorrow's) times as one compact list.
        mode full = today + tomorrow, times linked to booking; today = today only; plain = today, unlinked."""
        days = [(self.today, ("اليوم", "Today"))] + ([(self.tomorrow, ("بكرة", "Tomorrow"))] if mode == "full" else [])
        out = []
        for city in cities:
            cs = [s for s in shows if self.cinemas[s["cinema"]].get("city") == city and s["date"] in (d for d, _ in days)]
            if not cs: continue
            out.append(f'<section class="fcity" data-city="{city}"><h2><a href="{P(lang, city)}">{esc(L(CITY[city], lang))}</a></h2>')
            for cid in dict.fromkeys(s["cinema"] for s in cs):
                chain = self.cinemas[cid]["chain"]
                ss = [s for s in cs if s["cinema"] == cid]
                out.append(f'<div class="fcin"><h3><a href="{P(lang, city, cid)}">{self.cname_html(cid, lang)}</a> {self.fresh(chain, lang)}</h3>')
                for k in dict.fromkeys(self.hkey(s) for s in ss):
                    hs = [s for s in ss if self.hkey(s) == k]
                    withp = [s for s in hs if any((p.get("aed") or 0) > 0 for p in s.get("prices") or [])]
                    priced = next((s for s in withp if not self.table_date(s)), None) or next(iter(withp), None)  # live first
                    pc = ("".join(f'<span class="seat"><small>{esc(p["seat"])}</small> {self.pcell(p["aed"], chain, priced.get("hall") or "OTHER", k, cid, self.table_date(priced), lang)}</span>'
                                  for p in sorted((p for p in priced["prices"] if (p.get("aed") or 0) > 0), key=lambda p: p["aed"])) if priced else self.box(lang))
                    tl = "".join(f'<span class="dd"><i>{esc(L(lab, lang))}</i>{self.times([s for s in hs if s["date"] == d], lang, links=mode != "plain")}</span>'
                                 for d, lab in days if any(s["date"] == d for s in hs))
                    out.append(f'<div class="line"><span class="hn">{self.hall_html(hs[0], lang)}</span><span class="pr">{pc}</span>{tl}</div>')
                out.append('</div>')
            out.append('</section>')
        if mode != "full" and len(days) == 1:
            out.append(f'<p class="hint">{"مواعيد بكرة في صفحة كل سينما." if lang == "ar" else "Tomorrow’s times are on each cinema’s page."}</p>')
        return "".join(out)

    # -------------------------------------------------- cards
    def example(self, chain, card, lang):
        """«تذكرة ستار العادية 42.00 ← 33.60» from the cheapest priced seat this chain sells in a hall the card covers."""
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
        arrow = "←" if lang == "ar" else "→"
        pp = f' <small class="per">{esc(L(T["per_person"], lang))}</small>' if (rule_for(self.rules, chain, card) or {}).get("type") == "bogo" else ""
        return f'<p class="ex">{esc(what)} <s class="num">{money(aed)}</s> {arrow} <b class="num">{money(a)}</b> <small>{esc(L(T["aed"], lang))}</small>{pp}</p>'

    def card_pages(self):
        chains = sorted({c["chain"] for c in self.cinemas.values()} | set(self.rules))
        for card in self.cards:
            cid = card["id"]
            for lang in ("ar", "en"):
                cn = card["name_ar"] if lang == "ar" else card["name_en"]
                body = self.crumbs(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, None))
                body += f'<h1>{"خصم " + cn + " على السينما" if lang == "ar" else cn + " discounts at UAE cinemas"}</h1>'
                ok = [ch for ch in chains if rule_state(rule_for(self.rules, ch, cid), self.today) == "ok"]
                okn = ("، " if lang == "ar" else ", ").join(self.h.chain_name(ch, lang) for ch in ok)
                body += (f'<p class="lead">{(f"تنفع اليوم في: {okn}." if ok else f"ما لقينا خصم قائم لبطاقة {cn} في السينمات اليوم.") if lang == "ar" else (f"Works today at: {okn}." if ok else f"We found no current {cn} discount at UAE cinemas.")}'
                         f' {"كل سطر تحت فيه مصدره وتاريخ آخر فحص." if lang == "ar" else "Every line below carries its source and the date we checked it."}</p>')
                body += '<section><div class="rows cardrows">'
                faq = []
                for ch in chains:
                    r = rule_for(self.rules, ch, cid); st = rule_state(r, self.today)
                    body += self.card_row(card, ch, r, st, lang, label=self.h.chain_name(ch, lang))
                    if st == "ok": body += self.example(ch, cid, lang)
                    chn = self.h.chain_name(ch, lang)
                    q = f"هل خصم {cn} يشتغل في {chn}؟" if lang == "ar" else f"Does {cn} work at {chn}?"
                    if st == "ok":
                        a = (f"إيه، {rule_offer(r, lang)}" + (f" ({'، '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". تحققنا {r.get('checked')}." if lang == "ar"
                             else f"Yes, {rule_offer(r, lang)}" + (f" ({', '.join(rule_terms(r, lang))})" if rule_terms(r, lang) else "") + f". Checked {r.get('checked')}.")
                        if weak(r): a += " " + L(CONF_WEAK, lang) + "."
                    elif st == "none_found":
                        a = (f"ما لقينا خصم {cn} في {chn} وقت آخر فحص ({r.get('checked')})." if lang == "ar" else f"We found no {cn} discount at {chn} when we last checked ({r.get('checked')}).")
                    elif st == "expired":
                        a = (f"كان في {rule_offer(r, lang)} لين {r.get('valid_until')}، والعرض انتهى." if lang == "ar" else f"There was {rule_offer(r, lang)} until {r.get('valid_until')}; it has ended.")
                    else: continue
                    faq.append((q, a))
                body += '</div></section>'
                if faq:
                    body += (f'<section class="faq"><h2>{"أسئلة" if lang == "ar" else "Questions"}</h2>'
                             + "".join(f"<details><summary>{esc(q)}</summary><p>{dates(esc(a))}</p></details>" for q, a in faq) + '</section>')
                body += self.cards_strip(lang)
                title = (f"خصم {cn} على السينما — {okn or 'السينمات'}، كم توفّر؟" if lang == "ar" else f"{cn} cinema discount in the UAE — where it works and how much you save")
                desc = (f"وين ينفع خصم {cn} في سينمات الإمارات، كم يخصم، شروطه، وأمثلة على السعر قبل وبعد الخصم — من المصدر الرسمي وبتاريخ الفحص." if lang == "ar"
                        else f"Where the {cn} discount works at UAE cinemas, how much it takes off, its conditions and before/after prices — from the official source, dated.")
                graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
                         self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")), (cn, P(lang, "cards", cid)))]
                self.page(lang, ("cards", cid), title, desc, body, graph, "card")
        # index: every card × every chain
        for lang in ("ar", "en"):
            body = self.crumbs(lang, (L(UI["s_cards"], lang), None))
            body += f'<h1>{"خصومات السينما بالبطاقات" if lang == "ar" else "Cinema discounts by card"}</h1>'
            body += f'<p class="lead">{"كل بطاقة مقابل كل سلسلة. الفراغ يعني ما تحققنا بعد، مب إن السينما ترفض." if lang == "ar" else "Every card against every chain. A blank means not checked yet — not that the cinema refuses it."}</p>'
            head = "".join(f'<th scope="col">{esc(self.h.chain_name(ch, lang))}</th>' for ch in chains)
            rows = ""
            for card in self.cards:
                cells = ""
                for ch in chains:
                    r = rule_for(self.rules, ch, card["id"]); st = rule_state(r, self.today)
                    txt = (f'<b class="num" dir="ltr">{"1+1" if r.get("type") == "bogo" else (f'{float(r.get("value") or 0):g} AED' if r.get("type") == "fixed" else f'{r.get("value", 0):g}%')}</b>' + ("<sup>*</sup>" if weak(r) else "")) if st == "ok" else \
                          (f'<span class="nil">{esc(L(T["none_found"], lang))}</span>' if st == "none_found" else f'<span class="nil">{esc(L(T["expired"], lang))}</span>' if st == "expired" else "")
                    cells += f"<td>{txt}</td>"
                rows += f'<tr><th scope="row"><a href="{P(lang, "cards", card["id"])}">{esc(card["name_ar"] if lang == "ar" else card["name_en"])}</a></th>{cells}</tr>'
            body += (f'<div class="xwrap"><table class="matrix"><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
                     f'<p class="hint"><sup>*</sup> {esc(L(CONF_WEAK, lang))}. {"1+1 = تذكرتين بسعر وحدة." if lang == "ar" else "1+1 = buy one, get one."}</p>')
            title = ("خصومات السينما في الإمارات — فزعة وإسعاد وحماة الوطن وعروض البنوك" if lang == "ar" else "UAE cinema discounts — Fazaa, Esaad, Homat Al Watan and bank cards")
            desc = ("جدول واحد لكل خصومات السينما في الإمارات: فزعة وإسعاد وحماة الوطن والبنوك، في فوكس وستار ونوفو وريل وروكسي وسيني رويال وسينما سيتي." if lang == "ar"
                    else "One table of every UAE cinema discount: Fazaa, Esaad, Homat Al Watan and banks, at VOX, Star, Novo, Reel, Roxy, Cine Royal and Cinemacity.")
            self.page(lang, ("cards",), title, desc, body, [self.breadcrumb_ld(lang, (L(UI["s_cards"], lang), P(lang, "cards")))], "cards")

    # -------------------------------------------------- halls
    def halls_page(self):
        for lang in ("ar", "en"):
            body = self.crumbs(lang, (L(UI["s_halls"], lang), None))
            body += f'<h1>{"القاعات المميزة في سينمات الإمارات" if lang == "ar" else "Premium cinema halls in the UAE"}</h1>'
            body += f'<p class="lead">{"كل سلسلة تسمّي قاعتها الغالية باسم. هني شو فيها فعلاً، وكم سعرها اليوم، ووين تلقاها." if lang == "ar" else "Every chain names its premium hall differently. Here is what is actually inside, what it costs today and where to find it."}</p>'
            faq = []
            for chain, c in self.h.y.items():
                body += f'<section class="hchain"><h2>{esc(self.h.chain_name(chain, lang))}</h2><div class="halls">'
                for e in c.get("halls", []):
                    ss = [s for s in self.shows if self.cinemas[s["cinema"]]["chain"] == chain and self.hkey(s) == e["key"]]
                    ps = [p["aed"] for s in ss for p in s.get("prices") or [] if p.get("aed")]
                    where = sorted({s["cinema"] for s in ss})
                    rng = (f'{num(money(min(ps)))}' + (f' – {num(money(max(ps)))}' if max(ps) != min(ps) else "") + f' <small>{esc(L(T["aed"], lang))}</small>') if ps else ""
                    what = e.get("what_ar") if lang == "ar" else e.get("what_en")
                    conf = {"high": "", "medium": ("من مصدر غير رسمي" if lang == "ar" else "from a non-official source"),
                            "low": ("ما تأكدنا من التفاصيل" if lang == "ar" else "details not confirmed")}.get(e.get("confidence"), "")
                    body += (f'<div class="hall"><h3>{esc(e.get("name") or e["key"])}</h3><p>{dates(esc(what))}'
                             + (f' <small class="weak">{esc(conf)}</small>' if conf else "")
                             + (f' <a class="src" href="{esc(e["source"])}" rel="noopener" target="_blank">{"المصدر" if lang == "ar" else "Source"}</a>' if e.get("source") else "") + '</p>'
                             + (f'<p class="rng">{"اليوم" if lang == "ar" else "Today"} {rng}</p>' if rng else "")
                             + (f'<p class="where">{" ".join(f"<a href=\"{P(lang, self.cinemas[w]["city"], w)}\">{esc(self.cname(w, lang))}</a>" for w in where)}</p>' if where else "")
                             + '</div>')
                    faq.append(((f"شو فيها قاعة {e.get('name') or e['key']} في {self.h.chain_name(chain, lang)}؟" if lang == "ar" else f"What is {e.get('name') or e['key']} at {self.h.chain_name(chain, lang)}?"), what))
                body += '</div></section>'
            title = ("قاعات السينما في الإمارات — GOLD وTHEATRE وIMAX وSUITES، شو الفرق وكم السعر؟" if lang == "ar" else "UAE premium cinema halls — GOLD, THEATRE, IMAX, SUITES: what’s the difference?")
            desc = ("شو الفرق بين قاعات فوكس جولد وثياتر وماكس، وستار سويتس، ونوفو سفن ستار، وروكسي بلاتينيوم، وريل دولبي، وكم سعرها اليوم." if lang == "ar"
                    else "The difference between VOX GOLD, THEATRE and MAX, Star Suites, Novo 7 Star, Roxy Platinum, Reel Dolby and more — and what they cost today.")
            graph = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq if a]},
                     self.breadcrumb_ld(lang, (L(UI["s_halls"], lang), P(lang, "halls")))]
            self.page(lang, ("halls",), title, desc, body, graph, "halls")

    # -------------------------------------------------- data for cinema.js, sitemap, assets
    def slices(self):
        """/cinema/data/<city>-<date>.json per city and day, holding only what cinema.js reads, as indexed arrays:
        C[[cid, chain, ar, en]] F[[fid, ar, en]] H[[hall code, key, ar, en]] P[[[seat, aed]…]] B[booking URL prefixes]
        S[[cinema i, film i, "HH:MM", hall i, price i|-1, prefix i|-1, url tail(, table date)]] — the 8th
        element is present only when the price came from prices.yaml, and is that entry's date."""
        ddir = os.path.join(self.out, "cinema", "data")
        for city, _, _ in CITIES:
            cids = {cid for cid, c in self.cinemas.items() if c.get("city") == city}
            for day in sorted({s["date"] for s in self.shows if s["cinema"] in cids}):
                ss = sorted((s for s in self.shows if s["cinema"] in cids and s["date"] == day), key=lambda s: s["time"])
                lists = {"C": [], "F": [], "H": [], "P": [], "B": []}
                idx = {k: {} for k in lists}

                def at(kind, key, row):
                    if key not in idx[kind]: idx[kind][key] = len(lists[kind]); lists[kind].append(row)
                    return idx[kind][key]
                S = []
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
                    S.append(row)
                j = {"g": self.d.get("generated"), **lists, "S": S}
                self.write(os.path.join(ddir, f"{city}-{day}.json"), json.dumps(j, ensure_ascii=False, separators=(",", ":")))
        rules = {ch: {card: {k: v for k, v in r.items() if k in ("status", "type", "value", "excluded_halls", "halls_excluded", "included_halls", "included_cinemas", "valid_until", "confidence", "box_office_only", "max_tickets")}
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
                known[u] = [h, day]
                sm.append(f"<url><loc>{SITE + u}</loc><lastmod>{day}</lastmod>"
                          f'<xhtml:link rel="alternate" hreflang="ar" href="{SITE + P("ar", *parts)}"/>'
                          f'<xhtml:link rel="alternate" hreflang="en" href="{SITE + P("en", *parts)}"/>'
                          f'<xhtml:link rel="alternate" hreflang="x-default" href="{SITE + P("ar", *parts)}"/></url>')
        sm.append("</urlset>")
        self.write(os.path.join(self.out, "cinema", "sitemap.xml"), "\n".join(sm))
        if self.lastmod_path:
            os.makedirs(os.path.dirname(self.lastmod_path), exist_ok=True)
            json.dump(known, open(self.lastmod_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)

    def assets(self):
        adir = os.path.join(self.out, "cinema", "assets")
        os.makedirs(adir, exist_ok=True)
        for f in ("cinema.css", "cinema.js"):
            self.write(os.path.join(adir, f), open(os.path.join(SRC, f), encoding="utf-8").read())

    def run(self):
        self.home(); self.city_pages(); self.cinema_pages(); self.film_pages(); self.card_pages(); self.halls_page()
        self.slices(); self.sitemap(); self.assets()
        return len(self.urls)


def build(data_path, discounts_path, out, halls_path=None, preview=False, lastmod_path=None):
    data = json.load(open(data_path, encoding="utf-8"))
    disc = load_discounts(discounts_path)
    halls = Halls(halls_path or os.path.join(ROOT, "halls.yaml"))
    for sub in ("cinema", os.path.join("en", "cinema")):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    site = Site(data, disc, halls, out); site.lastmod_path = lastmod_path
    n = site.run()
    if preview:   # local server only: the live site gets base.css from saas/tools
        base = os.path.join(ROOT, "..", "tools", "src", "assets", "base.css")
        os.makedirs(os.path.join(out, "tools", "assets"), exist_ok=True)
        shutil.copy(base, os.path.join(out, "tools", "assets", "base.css"))
    return n


def main():
    first = lambda *ps: next((p for p in ps if os.path.exists(p)), ps[-1])
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=first(os.path.join(ROOT, "data", "latest.json"), os.path.join(ROOT, "fixtures", "sample_latest.json")))
    ap.add_argument("--discounts", default=first(os.path.join(ROOT, "discounts.yaml"), os.path.join(ROOT, "fixtures", "sample_discounts.yaml")))
    ap.add_argument("--halls", default=os.path.join(ROOT, "halls.yaml"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--preview", action="store_true", help="copy ../tools base.css into out/ for a local server")
    a = ap.parse_args()
    n = build(a.data, a.discounts, a.out, a.halls, a.preview, os.path.join(ROOT, "data", "lastmod.json"))
    print(f"built {n} pages ×2 languages from {os.path.relpath(a.data, ROOT)} + {os.path.relpath(a.discounts, ROOT)} -> {a.out}")


if __name__ == "__main__":
    main()
