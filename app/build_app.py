"""«سينما» as an app (owner 2026-10-18): «إعادة تصميم… نفس الميلس كتطبيق: سهولة الاستخدام والـsmoothness والبساطة».

Two lists at the top, swipe between them like the Meylis tabs:
  الأفلام    genre chips (الكل، أكشن، كوميديا، رعب…) over a poster grid — the poster, the name, the runtime and the IMDb
             score (else the critics' score); a tap opens the film.
  السينمات   the city (or «الأقرب» from the phone's location, nearest first), the cinemas as cards; a tap opens the
             cinema: its films with their posters and showtimes, today or tomorrow.
The film page carries everything: the screen (trailer still), the facts, our verdict, the story, «اسأل الفيلم», and
where it shows — by city, cinema by cinema, every time a button that raises the ticket from the bottom.

Static pages (every film and every cinema is a real page for Google and for the back button), moved between with
the Meylis numbers: a page slides in from the side in 300 ms, back reverses it, a sheet rises from the bottom; the
next page is prerendered, so a tap is instant. One small script for what needs the phone: the swipe between the two
lists, the genre chips, location, the day switch, past times, the ticket and «اسأل الفيلم».

    python app/build_app.py --data data/latest.json --out out_app [--base /next/]
`--base` prefixes every link and asset (a preview at /next/ beside the live site); posters and data stay at the
site's root.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from site_kit import Kit, Halls, load_discounts  # noqa: E402

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731
SITE = "https://cinema.elyoxe.com"
ASK_API = "https://fndms9v719.execute-api.ap-south-1.amazonaws.com/"

CITIES = [("dubai", "دبي"), ("abu-dhabi", "أبوظبي"), ("sharjah", "الشارقة"), ("al-ain", "العين"), ("ajman", "عجمان"),
          ("ras-al-khaimah", "رأس الخيمة"), ("fujairah", "الفجيرة"), ("umm-al-quwain", "أم القيوين")]
CITY = dict(CITIES)
INDIAN = {"Hindi", "Tamil", "Malayalam", "Telugu", "Kannada", "Punjabi", "Marathi", "Bengali"}
# the chips, in the order a person scans them; each matches a film by its genres (or its language)
CHIPS = [("all", "الكل"), ("action", "أكشن"), ("comedy", "كوميديا"), ("horror", "رعب"), ("thriller", "إثارة"),
         ("drama", "دراما"), ("adventure", "مغامرة"), ("family", "عائلي"), ("scifi", "خيال"), ("romance", "رومانسي"),
         ("arabic", "عربي"), ("indian", "هندي")]
GENRE_AR = {"action": "أكشن", "comedy": "كوميديا", "horror": "رعب", "thriller": "إثارة", "drama": "دراما",
            "adventure": "مغامرة", "family": "عائلي", "animation": "أنيميشن", "scifi": "خيال علمي", "fantasy": "فانتازيا",
            "romance": "رومانسي", "crime": "جريمة", "music": "موسيقى", "mystery": "غموض", "war": "حرب",
            "history": "تاريخي", "documentary": "وثائقي", "biography": "سيرة"}
LANG_AR = {"English": "إنجليزي", "Arabic": "عربي", "Hindi": "هندي", "Tamil": "تاميل", "Malayalam": "مالايالام",
           "Telugu": "تيلوغو", "Kannada": "كانادا", "Tagalog": "فلبيني", "Nepali": "نيبالي", "Punjabi": "بنجابي",
           "French": "فرنسي", "Korean": "كوري", "Japanese": "ياباني", "Urdu": "أوردو"}
VERDICT = {"yes": ("يستاهل", "y"), "mixed": ("بين بين", "m"), "skip": ("تجنّبه", "s")}
_PAREN = re.compile(r"\s*\((?:فلم|فيلم)[^)]*\)\s*$")


# ------------------------------------------------------------------ helpers
def title(k, fid):
    """The Arabic title without Wikipedia's «(فلم 2026)» disambiguation."""
    return _PAREN.sub("", k.ftitle(fid, "ar")).strip()


def num(v):
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").rstrip(".")


def score(f):
    """(label, kind): IMDb first (the owner's ask), else the critics' Rotten Tomatoes score, else nothing."""
    if f.get("imdb_score"):
        return f"{float(f['imdb_score']):.1f}", "imdb"
    rt = (f.get("rt") or {}).get("critics")
    if rt is not None:
        return f"{int(rt)}%", "rt"
    return "", ""


def tags(f):
    g = set(f.get("genres") or [])
    out = set(g)
    if g & {"family", "animation"}:
        out.add("family")
    if g & {"scifi", "fantasy"}:
        out.add("scifi")
    if f.get("lang") == "Arabic":
        out.add("arabic")
    if f.get("lang") in INDIAN:
        out.add("indian")
    return out


def hm(t):
    return t[:5]


DIRHAM = '<svg class="aed" viewBox="0 0 24 24" aria-label="درهم" role="img"><path d="M7.5 4v16h4.2c4.6 0 7.8-3.3 7.8-8s-3.2-8-7.8-8z" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/><path d="M3 10h18M3 14h18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>'


def t12(t):
    """«16:25» → («4:25», «مساء»); the small hours are «بالليل» (owner 2026-10-18: «بدال 16 نقول 4 مساء»)."""
    h, m = int(t[:2]), t[3:5]
    word = "بالليل" if h < 4 else "الصبح" if h < 12 else "الظهر" if h == 12 else "مساء"
    return f"{h % 12 or 12}:{m}", word


def ap(t):
    """The one-letter period for a small button: ص before noon, م after."""
    return "ص" if 4 <= int(t[:2]) < 12 else "م"


def runtime(f):
    r = f.get("runtime")
    if not r:
        return ""
    r = int(r)
    return f'<bdi dir="ltr" class="n">{r // 60}:{r % 60:02d}</bdi>' if r >= 60 else f'<bdi class="n">{r}</bdi> د'


def svg(name):
    p = {"back": '<path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
         "pin": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="9.5" r="2.5" fill="currentColor"/>',
         "star": '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.8z" fill="currentColor"/>',
         "play": '<path d="M8 5v14l11-7z" fill="currentColor"/>',
         "clock": '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
         "chat": '<path d="M5 5h14v10H9l-4 4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
         "map": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="2"/>',
         "film": '<rect x="4" y="5" width="16" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 9h16M4 15h16M9 5v14M15 5v14" stroke="currentColor" stroke-width="1.6"/>',
         "seat": '<path d="M6 11V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v4M4 11h16v5H4zM6 16v3M18 16v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>'}
    return f'<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">{p[name]}</svg>'


# ------------------------------------------------------------------ the app
class App:
    def __init__(self, data, disc, halls, out, base, live=False):
        # live: the main site — the old URLs (/film/<fid>/, /<city>/<cinema>/), open to search engines, written over the
        # old build's own pages in out/ (deploy.sh runs build.py first; its other pages stay: cards, prices, English…)
        self.live = live
        # the Arabic synopsis lives in intel/<fid>.json (filmintel, item 232); the old site attaches it at build time
        try:
            import filmintel
            for fid, f in (data.get("films") or {}).items():
                rec = filmintel.read(fid) or {}
                if not f.get("synopsis_ar") and rec.get("by") in ("claude", "hand") and isinstance(rec.get("synopsis_ar"), str):
                    f["synopsis_ar"] = rec["synopsis_ar"].strip()
        except Exception as e:  # noqa: BLE001 - no synopsis is a page without one, never a failed build
            print("app: synopses not attached:", e)
        self.k = Kit(data, disc, halls, out)
        self.d, self.out, self.base = data, out, base.rstrip("/") + "/"
        k = self.k
        self.shows = [s for s in k.shows if s["date"] in (k.today, k.tomorrow)]
        self.count = {}
        for s in self.shows:
            self.count[s["film"]] = self.count.get(s["film"], 0) + 1
        self.films = sorted((fid for fid in k.showing if self.count.get(fid)), key=lambda f: (-self.count[f], title(k, f)))
        self.cins = sorted({s["cinema"] for s in self.shows})
        self.people = data.get("people") or {}
        self.css_name = self.js_name = None
        self._ld, self._og = [], None
        self.fresh()

    def u(self, *parts):
        if self.live and parts and parts[0] == "f":
            return f"/film/{parts[1]}/"
        if self.live and parts and parts[0] == "c":
            return f"/{self.k.cinemas[parts[1]].get('city')}/{parts[1]}/"
        return self.base + "/".join(parts) + ("/" if parts else "")

    def chain(self, cid):
        return self.k.h.chain_name(self.k.cinemas[cid]["chain"], "ar")

    def mark(self, cid, cls=""):
        """The chain's own app icon (app/logos/<chain>.webp, owner 2026-10-19) in its square; the coloured name
        tile when a chain has none."""
        ch, name = self.k.cinemas[cid]["chain"], self.chain(cid)
        src = self.logos.get(ch)
        inner = f'<img src="{E(src)}" alt="{E(name)}" width="64" height="64" decoding="async">' if src else E(name)
        return f'<span class="cc-logo{" " + cls if cls else ""}{" img" if src else ""} ch-{E(ch)}">{inner}</span>'

    def cname(self, cid):
        """«فوكس — الجيمي مول» → the mall alone on a card under its chain («الجيمي مول»)."""
        n = self.k.cname(cid, "ar")
        return n.split(" — ", 1)[1] if " — " in n else n

    def poster(self, fid, w=342, cls="pst", eager=False):
        f = self.k.films[fid]
        pc = E(f.get("poster_color") or "#3a302a")
        if not f.get("poster"):
            return f'<span class="{cls} np" style="--pc:{pc}"><b>{E(title(self.k, fid))}</b></span>'
        src = f["poster"] if w <= 342 or not f.get("poster_2x") else f["poster_2x"]
        ss = f' srcset="{E(f["poster"])} 342w, {E(f["poster_2x"])} 684w" sizes="(min-width:900px) 200px, 46vw"' if f.get("poster_2x") and cls == "pst" else ""
        lazy = "" if eager else ' loading="lazy"'
        return f'<span class="{cls}" style="--pc:{pc}"><img src="{E(src)}"{ss} width="342" height="513" alt="" decoding="async"{lazy}></span>'

    def fresh(self):
        self._rows, self._seats, self._seat_i, self._cins = [], [], {}, set()

    def table(self):
        if not self._rows:
            return ""
        cins = {c: [self.cname(c), self.k.cinemas[c].get("city") or "", self.k.cinemas[c]["chain"], self.chain(c)] for c in sorted(self._cins)}
        j = json.dumps({"r": self._rows, "s": self._seats, "c": cins}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return f'<script type="application/json" id="shows">{j}</script>'

    # -------- what search engines and shares read (live)
    def alt(self, path):
        if not self.live:
            return ""
        en = SITE + "/en" + path
        return (f'<link rel="alternate" hreflang="ar" href="{E(SITE + path)}"><link rel="alternate" hreflang="en" href="{E(en)}">'
                f'<link rel="alternate" hreflang="x-default" href="{E(SITE + path)}">')

    def ld(self):
        if not self._ld:
            return ""
        g = json.dumps({"@context": "https://schema.org", "@graph": self._ld}, ensure_ascii=False).replace("</", "<\\/")
        return f'<script type="application/ld+json">{g}</script>'

    def spec(self):
        if self.live:
            pats = ["/film/*", "/"] + [f"/{c}/*" for c, _ in CITIES]
        else:
            pats = [f"{self.base}f/*", f"{self.base}c/*", self.base]
        return json.dumps({"prerender": [{"where": {"href_matches": pats}, "eagerness": "moderate"}]})

    def footer(self):
        """The rest of the site, one quiet line at the end: nothing lost, nothing in the way."""
        links = [("/cards/", "البطاقات والخصومات"), ("/prices/", "أسعار التذاكر"), ("/coming/", "قريباً"), ("/q/", "أسئلة"), ("/en/", "English")]
        return '<footer class="foot">' + "".join(f'<a href="{h}">{t}</a>' for h, t in links) + '<small>سينما من Elyoxe</small></footer>'

    # -------- page frame
    def page(self, path, ttl, desc, body, kind, head_extra="", canon=None):
        canon = SITE + path if self.live else (canon or (SITE + path))
        body = body + (self.footer() if self.live else "")
        doc = f"""<!doctype html>
<html lang="ar" dir="rtl" data-kind="{kind}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(ttl)}</title><meta name="description" content="{E(desc)}">
{"" if self.live else '<meta name="robots" content="noindex">'}<link rel="canonical" href="{E(canon)}">{self.alt(path)}
<meta property="og:title" content="{E(ttl)}"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website">
<meta property="og:url" content="{E(canon)}"><meta property="og:image" content="{E(self._og or SITE + '/assets/og-ar.png')}"><meta name="twitter:card" content="summary_large_image">
<link rel="manifest" href="/manifest.webmanifest">{self.ld()}
<meta name="theme-color" content="#F3EEE6"><meta name="color-scheme" content="light">
<link rel="icon" href="/assets/icon.svg" type="image/svg+xml">
<link rel="preload" href="{self.base}assets/fonts/plex-ar-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{self.base}assets/fonts/plex-ar-700.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{self.base}assets/{self.css_name}">{head_extra}
<script type="speculationrules">{self.spec()}</script>
<script>(function(){{addEventListener("pagereveal",function(e){{var t=e.viewTransition,a=window.navigation&&navigation.activation;if(t&&a&&a.from&&a.entry&&a.navigationType==="traverse"&&a.entry.index<a.from.index)document.documentElement.dataset.nav="pop";else if(t)document.documentElement.dataset.nav="push";if(t)t.finished.finally(function(){{delete document.documentElement.dataset.nav}})}});addEventListener("pageswap",function(e){{var t=e.viewTransition,a=e.activation;if(t&&a&&a.navigationType==="traverse"&&a.entry&&a.from&&a.entry.index<a.from.index)document.documentElement.dataset.nav="pop";else if(t)document.documentElement.dataset.nav="push"}})}})()</script>
</head><body>{body}{self.table()}
<div class="scrim" data-scrim hidden></div>
<script>window.APP={{base:"{self.base}",ask:"{ASK_API}",today:"{self.k.today}",tomorrow:"{self.k.tomorrow}",logos:{json.dumps(self.logos)}}}</script>
<script src="{self.base}assets/{self.js_name}" defer></script>
</body></html>"""
        p = os.path.join(self.out, *[x for x in path.replace(self.base, "", 1).split("/") if x], "index.html")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(doc)

    def bar(self, ttl, back=True):
        b = (f'<a class="pg-back" href="{self.base}" data-back aria-label="رجوع">{svg("back")}</a>' if back else "<span></span>")
        return f'<header class="pgbar">{b}<h1>{E(ttl)}</h1><span></span></header>'

    # -------- home
    def tile(self, fid):
        k, f = self.k, self.k.films[fid]
        sc, kind = score(f)
        meta = []
        if f.get("runtime"):
            meta.append(f'<span class="m-rt">{svg("clock")}{runtime(f)}</span>')
        if sc:
            meta.append(f'<span class="m-sc {kind}">{svg("star") if kind == "imdb" else ""}<b>{E(sc)}</b>{"<small>IMDb</small>" if kind == "imdb" else "<small>النقاد</small>"}</span>')
        age = f'<i class="age">{E(f["rating"])}</i>' if f.get("rating") else ""
        return (f'<a class="tile" href="{self.u("f", fid)}" data-g="{E(" ".join(sorted(tags(f))))}">'
                f'<span class="tp">{self.poster(fid)}{age}</span>'
                f'<span class="tt">{E(title(k, fid))}</span><span class="tm">{"".join(meta)}</span></a>')

    def ccard(self, cid):
        c = self.k.cinemas[cid]
        n = len({s["film"] for s in self.shows if s["cinema"] == cid and s["date"] == self.k.today})
        lat, lng = c.get("lat"), c.get("lng")
        geo = f' data-lat="{lat:.5f}" data-lng="{lng:.5f}"' if lat is not None and lng is not None else ""
        return (f'<a class="ccard" href="{self.u("c", cid)}" data-city="{E(c.get("city") or "")}"{geo}>'
                + self.mark(cid) +
                f'<span class="cc-b"><b>{E(self.cname(cid))}</b><small>{E(CITY.get(c.get("city"), ""))}'
                f'<span class="cc-km" data-km></span></small></span>'
                f'<span class="cc-n"><b>{n}</b><small>فيلم اليوم</small></span></a>')

    def billboard(self):
        """«الشاشة» from the live site, smaller: tonight's five most-shown films that have a trailer still, a card each,
        swiped sideways; the name, two facts and one button."""
        k = self.k
        top = [f for f in self.films if (k.films[f].get("backdrop") or {}).get("w640")][:5]
        if not top:
            return ""
        slides = []
        for i, fid in enumerate(top):
            f = k.films[fid]; bd = f["backdrop"]
            sc, kind = score(f)
            facts = " · ".join(x for x in [runtime(f), E(f.get("rating") or ""), (f"★ {sc}" if kind == "imdb" else "")] if x)
            lazy = "" if i == 0 else ' loading="lazy"'
            pri = ' fetchpriority="high"' if i == 0 else ""
            slides.append(f'<a class="bb" href="{self.u("f", fid)}" style="--pc:{E(f.get("poster_color") or "#3a302a")}">'
                          f'<img src="{E(bd["w640"])}" srcset="{E(bd["w640"])} 640w, {E(bd.get("w1280") or bd["w640"])} 1280w" sizes="(min-width:900px) 860px, 92vw" alt=""{lazy}{pri}>'
                          f'<span class="bb-t"><small>الأكثر عرضاً الليلة</small><b>{E(title(k, fid))}</b><i>{facts}</i></span></a>')
        dots = "".join(f'<i{" class=\"on\"" if i == 0 else ""}></i>' for i in range(len(top)))
        return f'<section class="bill"><div class="bb-row" data-bill>{"".join(slides)}</div><div class="bb-dots" data-dots>{dots}</div></section>'

    def soon_board(self):
        """«يبدأ قريب منك» from the live site: three rows, the flip clock, the visitor's city. The page carries today's
        times compactly (#soon) and the script picks the next three in the city."""
        k = self.k
        cins = sorted({s["cinema"] for s in self.shows if s["date"] == k.today})
        ci = {c: i for i, c in enumerate(cins)}
        fi = {f: i for i, f in enumerate(self.films)}
        rows = []
        for s in self.shows:
            if s["date"] != k.today or s["film"] not in fi:
                continue
            pr = [p["aed"] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
            rows.append([ci[s["cinema"]], fi[s["film"]], hm(s["time"]), float(num(min(pr))) if pr else 0])
        data = {"c": [[c, self.cname(c), k.cinemas[c].get("city") or "", k.cinemas[c]["chain"], self.chain(c)] for c in cins],
                "f": [[f, title(k, f), k.films[f].get("poster") or ""] for f in self.films], "r": rows, "d": k.today}
        j = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return (f'<section class="soon" data-soon><h2>يبدأ قريب منك <span data-soon-city></span></h2><div class="sb" data-soon-rows></div><template id="aed">{DIRHAM}</template>'
                f'<p class="empty sm" data-soon-none hidden>ما في عروض قريبة الحين.</p></section>'
                f'<script type="application/json" id="soon">{j}</script>')

    def home(self, path=None, merged=True):
        k = self.k
        chips = []
        for key, label in CHIPS:
            if key == "all" or any(key in tags(k.films[f]) for f in self.films):
                chips.append(f'<button type="button" class="chip{" on" if key == "all" else ""}" data-chip="{key}">{label}</button>')
        grid = "".join(self.tile(f) for f in self.films)
        cities = [c for c, _ in CITIES if any(k.cinemas[x].get("city") == c for x in self.cins)]
        cchips = (f'<button type="button" class="chip near" data-near>{svg("pin")}الأقرب</button>'
                  + "".join(f'<button type="button" class="chip" data-city="{c}">{CITY[c]}</button>' for c in cities))
        cards = "".join(self.ccard(c) for c in sorted(self.cins, key=lambda c: (k.cinemas[c].get("city") or "", self.cname(c))))
        body = f"""<div class="app">
<header class="tophead"><a class="brand" href="{self.base}">سينما</a>
<nav class="toptabs" role="tablist"><button type="button" role="tab" class="on" data-pane="0" aria-selected="true">الأفلام</button><button type="button" role="tab" data-pane="1" aria-selected="false">السينمات</button></nav><span></span></header>
<main class="pager" data-pager>
<section class="pane" aria-label="الأفلام">{(self.billboard() + self.soon_board()) if merged else ""}<div class="chips" data-chips>{"".join(chips)}</div>
<div class="grid" data-grid>{grid}</div><p class="empty" data-none hidden>ما في أفلام بهالتصنيف اليوم.</p></section>
<section class="pane" aria-label="السينمات"><div class="chips" data-cchips>{cchips}</div>
<p class="geo-msg" data-geo-msg hidden></p><div class="clist" data-clist>{cards}</div></section>
</main></div>"""
        self.page(path or self.base, "سينما الإمارات — الأفلام والمواعيد والأسعار", "كل أفلام سينمات الإمارات اليوم، مصنّفة، وكل سينما بمواعيدها.", body, "home")

    # -------- shows → time buttons
    def times(self, shows):
        out = []
        for s in sorted(shows, key=lambda s: (s["date"], s["time"] < "04:00", s["time"])):   # 00:45 is that night's last show
            pr = [p["aed"] for p in s.get("prices") or [] if (p.get("aed") or 0) > 0]
            hk = self.k.hkey(s)
            hall = self.k.hname(s, "ar") if hk != "Standard" else ""
            # the ticket's details live once per page in #shows (a table, not 600 bytes of attributes per button):
            # [day, time, ends, hall, booking url, language, seat-list index]; seat lists are shared in #seats
            seats = [[p["seat"], p["aed"]] for p in sorted(s.get("prices") or [], key=lambda p: p.get("aed") or 0) if (p.get("aed") or 0) > 0]
            sk = json.dumps(seats, ensure_ascii=False)
            if sk not in self._seat_i:
                self._seat_i[sk] = len(self._seats); self._seats.append(seats)
            self._rows.append([s["date"], hm(s["time"]), s.get("ends") or "", hall, self.k.book_url(s), s.get("lang") or "", self._seat_i[sk], s["cinema"]])
            self._cins.add(s["cinema"])
            out.append(f'<button type="button" class="tbtn" data-d="{s["date"]}" data-t="{hm(s["time"])}" data-i="{len(self._rows) - 1}">'
                       f'<b>{t12(hm(s["time"]))[0]}<sup>{ap(s["time"])}</sup></b>{f"<small>{E(hall)}</small>" if hall else ""}{f"<i>{num(min(pr))}{DIRHAM}</i>" if pr else ""}</button>')
        return "".join(out)

    def dayswitch(self):
        k = self.k
        has = {s["date"] for s in self.shows}
        btn = lambda d, lab, on: f'<button type="button" class="seg{" on" if on else ""}" data-day="{d}">{lab}</button>' if d in has else ""
        return f'<div class="segs" data-days>{btn(k.today, "اليوم", True)}{btn(k.tomorrow, "بكرة", k.today not in has)}</div>'

    # -------- film page
    def film(self, fid):
        self.fresh()
        k, f = self.k, self.k.films[fid]
        t = title(k, fid)
        sc, kind = score(f)
        bd = (f.get("backdrop") or {})
        still = bd.get("w1280") if bd.get("w1280") else None
        hero_bg = f'<img class="fh-still" src="{E(bd.get("w640") or still)}" srcset="{E(bd.get("w640"))} 640w, {E(still)} 1280w" sizes="100vw" alt="" fetchpriority="high">' if still else ""
        chips = []
        if f.get("runtime"):
            chips.append(f'<span>{svg("clock")}{runtime(f)}</span>')
        if f.get("rating"):
            chips.append(f'<span class="age2">{E(f["rating"])}</span>')
        if sc:
            chips.append(f'<span class="sc {kind}">{svg("star") if kind == "imdb" else ""}<b>{E(sc)}</b>{"IMDb" if kind == "imdb" else "النقاد"}</span>')
        if f.get("lang"):
            chips.append(f'<span>{E(LANG_AR.get(f["lang"], f["lang"]))}</span>')
        genres = "، ".join(GENRE_AR[g] for g in (f.get("genres") or []) if g in GENRE_AR)
        vd = f.get("verdict") or {}
        vw = VERDICT.get(vd.get("verdict"))
        vtext = re.sub(r"\s*\((?:فلم|فيلم)\s*\d{4}\)", "", vd.get("ar") or "")
        verdict = (f'<div class="verdict v-{vw[1]}"><b>{vw[0]}</b><p>{E(vtext)}</p></div>' if vw and vtext else "")
        syn = f.get("synopsis_ar") or ""
        syn_en = "" if syn else (f.get("synopsis_en") or "")
        about = (f'<section class="about" data-about><p class="syn clamp" data-clamp>{E(syn)}</p><button type="button" class="more" data-more hidden>المزيد</button></section>' if syn else
                 f'<section class="about" data-about><p class="syn clamp" lang="en" dir="ltr" data-clamp>{E(syn_en)}</p><button type="button" class="more" data-more hidden>المزيد</button></section>' if syn_en else "")
        cast = []
        for q in (f.get("cast") or [])[:8]:
            p = self.people.get(q) if isinstance(q, str) else None
            if p and (p.get("name_en") or p.get("name_ar")):
                cast.append(E(p.get("name_en") or p.get("name_ar")))
        crew = (f'<section class="sec"><h2>الطاقم</h2><p class="crew">{"" if not f.get("director") else "إخراج <b lang=en>" + E(f["director"]) + "</b><br>"}'
                f'{"<span lang=en>" + "، ".join(cast) + "</span>" if cast else ""}</p></section>' if cast or f.get("director") else "")
        trailer = (f'<button type="button" class="btn ghost" data-trailer="{E(f["trailer"])}">{svg("play")}الإعلان</button>' if f.get("trailer") else "")
        ask = (f'<button type="button" class="btn ghost" data-ask-open>{svg("chat")}اسأل الفيلم</button>')
        # where it shows: city tabs (the visitor's own first, script), each city its cinemas and their times
        shows = [s for s in self.shows if s["film"] == fid]
        cities = [c for c, _ in CITIES if any(k.cinemas[s["cinema"]].get("city") == c for s in shows)]
        sched = ""
        for c in cities:
            blocks = ""
            for cid in sorted({s["cinema"] for s in shows if k.cinemas[s["cinema"]].get("city") == c}, key=self.cname):
                cs = [s for s in shows if s["cinema"] == cid]
                cc = k.cinemas[cid]
                geo = f' data-lat="{cc["lat"]:.5f}" data-lng="{cc["lng"]:.5f}"' if cc.get("lat") is not None and cc.get("lng") is not None else ""
                blocks += (f'<div class="cblock" data-cin="{E(cid)}"{geo}><a class="cb-h" href="{self.u("c", cid)}">{self.mark(cid, "sm")}'
                           f'<b>{E(self.cname(cid))}</b><span class="cc-km" data-km></span></a><div class="times">{self.times(cs)}</div></div>')
            sched += f'<div class="city" data-city="{c}" hidden>{blocks}</div>'
        ctabs = "".join(f'<button type="button" class="chip" data-ctab="{c}">{CITY[c]}</button>' for c in cities)
        where = (f'<section class="sec where"><h2>وين يعرض</h2>{self.dayswitch()}<div class="chips" data-ctabs>{ctabs}</div>{sched}'
                 f'<p class="empty" data-past hidden>خلصت عروض اليوم هني، شوف بكرة.</p></section>') if shows else ""
        body = f"""<div class="pg film">{self.bar(t)}
<section class="fhero" style="--pc:{E(f.get('poster_color') or '#3a302a')}">{hero_bg}<div class="fh-in">{self.poster(fid, cls="pst big", eager=True)}
<div class="fh-t"><h2 class="ft">{E(t)}</h2>{f'<p class="fte" lang="en" dir="ltr">{E(f["title"])}{" · " + str(f["year"]) if f.get("year") else ""}</p>' if f.get("title") and f.get("title") != t else ""}
<div class="fchips">{"".join(chips)}</div>{f'<p class="fg">{genres}</p>' if genres else ""}</div></div></section>
<div class="acts">{trailer}{ask}</div>
{about}<section class="nearest" data-nearest hidden><h2>أقرب عرض لك</h2><div data-nearest-row></div></section>
{verdict}{where}{crew}
<section class="sec ask" data-ask data-fid="{E(fid)}"><h2>اسأل الفيلم</h2><p class="lead">اسأل أي شي عن الفيلم، ونجاوبك من قصته ومعلوماته بس. اللي يحرق نخفيه لين تضغط.</p>
<form class="ask-f" data-ask-form><input name="q" maxlength="240" autocomplete="off" enterkeyhint="send" placeholder="مثلاً: يناسب العيال؟" aria-label="سؤالك"><button class="btn velvet" type="submit">اسأل</button></form>
<div class="chips wrap">{"".join(f'<button type="button" class="chip" data-ask-q="{q}">{q}</button>' for q in ["شو نوع الفيلم؟", "يناسب العيال؟", "عن شو القصة؟", "شو يصير في النهاية؟"])}</div><div class="ask-out" data-ask-out></div></section>
</div>{self.sheet()}"""
        mv = {"@type": "Movie", "name": t, "url": SITE + self.u("f", fid), "inLanguage": "ar"}
        if f.get("title") and f["title"] != t: mv["alternateName"] = f["title"]
        if f.get("poster_2x") or f.get("poster"): mv["image"] = SITE + (f.get("poster_2x") or f.get("poster"))
        if f.get("runtime"): mv["duration"] = f"PT{int(f['runtime'])}M"
        if f.get("rating"): mv["contentRating"] = f["rating"]
        if f.get("genres"): mv["genre"] = [GENRE_AR[g] for g in f["genres"] if g in GENRE_AR]
        if f.get("director"): mv["director"] = {"@type": "Person", "name": f["director"]}
        if f.get("synopsis_ar") or f.get("synopsis_en"): mv["description"] = (f.get("synopsis_ar") or f.get("synopsis_en"))[:300]
        self._ld = [mv, {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "سينما", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": t, "item": SITE + self.u("f", fid)}]}]
        self._og = SITE + (f.get("poster_2x") or f.get("poster")) if (f.get("poster_2x") or f.get("poster")) else None
        self.page(self.u("f", fid), f"{t} — المواعيد والأسعار في سينمات الإمارات", (f.get("synopsis_ar") or t)[:150], body, "film",
                  canon=f"{SITE}/film/{fid}/")
        self._ld, self._og = [], None

    # -------- cinema page
    def cinema(self, cid):
        self.fresh()
        k, c = self.k, self.k.cinemas[cid]
        shows = [s for s in self.shows if s["cinema"] == cid]
        films = sorted({s["film"] for s in shows}, key=lambda f: (-self.count.get(f, 0), title(k, f)))
        rows = ""
        for fid in films:
            f = k.films[fid]
            sc, kind = score(f)
            meta = " · ".join(x for x in [runtime(f), E(f.get("rating") or ""), (("★ " + sc + " IMDb") if kind == "imdb" else ("النقاد " + sc)) if sc else ""] if x)
            rows += (f'<div class="frow" data-fid="{E(fid)}"><a class="fr-p" href="{self.u("f", fid)}">{self.poster(fid, cls="pst sm")}</a>'
                     f'<div class="fr-b"><a class="fr-t" href="{self.u("f", fid)}">{E(title(k, fid))}</a><p class="fr-m">{meta}</p>'
                     f'<div class="times">{self.times([s for s in shows if s["film"] == fid])}</div></div></div>')
        ll = f'{c["lat"]},{c["lng"]}' if c.get("lat") is not None else ""
        maps = f"https://www.google.com/maps/dir/?api=1&destination={ll}" if ll else (c.get("maps") or "")
        waze = f"https://waze.com/ul?ll={ll}&navigate=yes" if ll else ""
        name = f"{self.chain(cid)} — {self.cname(cid)}"
        body = f"""<div class="pg cinema">{self.bar(name)}
<section class="chead">{self.mark(cid, "lg")}<div><h2>{E(self.cname(cid))}</h2>
<p>{E(CITY.get(c.get("city"), ""))}{" · " + E(c.get("address")) if c.get("address") else ""}</p></div></section>
<div class="acts">{f'<a class="btn ghost" href="{E(maps)}" target="_blank" rel="noopener">{svg("map")}Google Maps</a>' if maps else ""}{f'<a class="btn ghost" href="{E(waze)}" target="_blank" rel="noopener">{svg("map")}Waze</a>' if waze else ""}</div>
<section class="sec">{self.dayswitch()}<div class="films">{rows}</div><p class="empty" data-past hidden>خلصت عروض اليوم هني، شوف بكرة.</p></section>
</div>{self.sheet()}"""
        th = {"@type": "MovieTheater", "name": name, "url": SITE + self.u("c", cid)}
        if c.get("address"): th["address"] = c["address"]
        if c.get("lat") is not None: th["geo"] = {"@type": "GeoCoordinates", "latitude": c["lat"], "longitude": c["lng"]}
        self._ld = [th]
        self.page(self.u("c", cid), f"{name} — الأفلام والمواعيد اليوم", f"أفلام {name} اليوم وبكرة بمواعيدها وأسعارها.", body, "cinema",
                  canon=f"{SITE}/{c.get('city')}/{cid}/")
        self._ld = []

    # -------- the ticket sheet (one per page, filled by the script)
    def sheet(self):
        return f"""<template id="aed">{DIRHAM}</template><section class="sheet" data-sheet role="dialog" aria-modal="true" aria-labelledby="tk-film" hidden>
<div class="grab" data-grab></div><div class="tk"><div class="tk-top"><div><p class="tk-cin" data-tk-cin></p><h3 id="tk-film" data-tk-film></h3><p class="tk-when" data-tk-when></p></div>
<div class="tk-time"><small data-tk-day></small><b data-tk-time></b></div></div>
<table class="tk-seats"><tbody data-tk-seats></tbody></table>
<a class="btn velvet wide" data-tk-book target="_blank" rel="noopener nofollow">احجز</a>
<button type="button" class="btn ghost wide" data-tk-close>سكّر</button></div></section>"""

    # -------- assets
    def assets(self):
        a = os.path.join(self.out, "assets")
        os.makedirs(os.path.join(a, "fonts"), exist_ok=True)
        for fn in os.listdir(os.path.join(HERE, "fonts")):
            if fn.endswith(".woff2"):
                shutil.copy(os.path.join(HERE, "fonts", fn), os.path.join(a, "fonts", fn))
        css = open(os.path.join(HERE, "app.css"), encoding="utf-8").read().replace("__BASE__", self.base)
        js = open(os.path.join(HERE, "app.js"), encoding="utf-8").read()
        self.css_name = f"app.{hashlib.sha1(css.encode()).hexdigest()[:10]}.css"
        self.js_name = f"app.{hashlib.sha1(js.encode()).hexdigest()[:10]}.js"
        open(os.path.join(a, self.css_name), "w", encoding="utf-8").write(css)
        self.logos = {}                          # chain -> its icon, content-hashed like the rest of assets/
        os.makedirs(os.path.join(a, "logos"), exist_ok=True)
        for fn in sorted(os.listdir(os.path.join(HERE, "logos"))):
            if fn.endswith(".webp"):
                raw = open(os.path.join(HERE, "logos", fn), "rb").read()
                name = f"{fn[:-5]}.{hashlib.sha1(raw).hexdigest()[:10]}.webp"
                open(os.path.join(a, "logos", name), "wb").write(raw)
                self.logos[fn[:-5]] = f"{self.base}assets/logos/{name}"
        open(os.path.join(a, self.js_name), "w", encoding="utf-8").write(js)

    def run(self):
        if not self.live:                       # the preview owns its folder; live writes over the old build's pages only
            shutil.rmtree(self.out, ignore_errors=True)
        os.makedirs(self.out, exist_ok=True)
        self.assets()
        self.home()
        if os.environ.get("APP_SAMPLE") and not self.live:
            self.home(self.base + "sample/", merged=True)
        for fid in self.films:
            self.film(fid)
        for cid in self.cins:
            self.cinema(cid)
        return 1 + len(self.films) + len(self.cins)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "latest.json"))
    ap.add_argument("--discounts", default=os.path.join(ROOT, "discounts.yaml"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out_app"))
    ap.add_argument("--base", default="/")
    ap.add_argument("--live", action="store_true", help="the main site: old URLs, indexable, over out/'s old pages")
    a = ap.parse_args()
    data = json.load(open(a.data, encoding="utf-8"))
    app = App(data, load_discounts(a.discounts), Halls(os.path.join(ROOT, "halls.yaml")), a.out, "/" if a.live else a.base, live=a.live)
    n = app.run()
    print(f"app: {n} pages -> {a.out} (base {app.base})")


if __name__ == "__main__":
    main()
