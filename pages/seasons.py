"""Phase 2, task 6 (docs/superpowers/specs/2026-09-27-phase2-design.md, section E — Seasons):
Ramadan/Eid mode and kids/summer presets. Owns /eid/, /kids/, /summer/ and the Ramadan iftar
line slotted into home + city pages (Kit.SLOTS "home.after_tonight" / "city.after_tonight").

Hijri dates (per docs/PLUGINS.md, page modules never call the network or invent numbers):
research the same as saas/tools/src/tools/holidays/tool.js's UAE-holidays table (copied below
with attribution, not re-derived) for the two years the site's data window realistically spans.
Ramadan's own start isn't in that source (it lists Eid only) so it is derived as 29 days before
Eid al-Fitr's first day -- a Hijri month is 29 or 30 days, and 29 is the inclusive choice: a
visitor sees Ramadan mode start at most a day late, never a day early. Every date here is an
estimate the way the rest of the site already labels estimates -- "تقريباً".

Iftar/Taraweeh: Maghrib and Isha computed server-side (baked into static HTML, so a visitor
with JS off still sees the iftar line) with the same method and per-minute adjustment measured
and applied in src/js/prayer.js for the client-side «راعِ أوقات الصلاة» switch -- the Dubai/IACAD
method (18.2° twilight angle), maghrib/isha +1 minute. City coordinates copied from that file's
PRAY_AT table, same attribution. The solar-position formulas below are the standard low-precision
NOAA equations (declination + equation of time from the sun's mean anomaly and ecliptic
longitude) that adhan.js itself implements in JS; this is their Python twin, accurate to within
a minute or two -- fine for a line already labelled «تقريباً».
"""
from __future__ import annotations

import math
import os
from datetime import date, timedelta

from site_kit import CITIES, NOINDEX, L, NavItem, P, Page, Plugin, esc, film_flags, num

ASSET_DIR = None
CSS = ("seasons",)
LAZY_JS = ()
DIRS = ("eid", "kids", "summer")

TITLES = {"eid": ("إصدارات العيد", "Eid releases"), "kids": ("صباح العيال", "Kids"),
          "summer": ("سينما الصيف", "Summer")}

# ---------------------------------------------------------------------------------- Hijri dates
# Copied with attribution from saas/tools/src/tools/holidays/tool.js's `H` table (UAE public
# holidays; Cabinet Resolution 27/2024 announcements, 2027 dates are the Astronomy Centre's
# expectations, business/elyoxe-tools/research/data-2026-09-25.md). Only the two Eids -- this
# site has no reason to carry the whole holidays table.
_EID_FITR = {2026: ("2026-03-19", "2026-03-22"), 2027: ("2027-03-09", "2027-03-12")}
_EID_ADHA = {2026: ("2026-05-26", "2026-05-29"), 2027: ("2027-05-15", "2027-05-18")}


def _d(s: str) -> date:
    return date.fromisoformat(s)


EID_FITR = {y: (_d(a), _d(b)) for y, (a, b) in _EID_FITR.items()}
EID_ADHA = {y: (_d(a), _d(b)) for y, (a, b) in _EID_ADHA.items()}
# derived, not sourced -- see module docstring
RAMADAN = {y: (start - timedelta(days=29), start - timedelta(days=1)) for y, (start, _) in EID_FITR.items()}


def is_ramadan(d: date) -> bool:
    return any(start <= d <= end for start, end in RAMADAN.values())


def eid_within(d: date, within_days: int = 10):
    """("fitr"|"adha", first_day) if that Eid's first day is 0..within_days days from `d`
    (today or up to `within_days` days ahead — never a past Eid), else None."""
    for name, table in (("fitr", EID_FITR), ("adha", EID_ADHA)):
        for start, _end in table.values():
            delta = (start - d).days
            if 0 <= delta <= within_days:
                return name, start
    return None


# ------------------------------------------------------------------------------ iftar / taraweeh
# Copied with attribution from src/js/prayer.js's PRAY_AT (itself researched against the
# published UAE prayer timetable, 2026-09-24).
CITY_COORDS = {"abu-dhabi": (24.4539, 54.3773), "dubai": (25.2048, 55.2708), "sharjah": (25.3463, 55.4209),
               "al-ain": (24.2075, 55.7447), "ajman": (25.4052, 55.5136), "umm-al-quwain": (25.5647, 55.5552),
               "ras-al-khaimah": (25.8007, 55.9762), "fujairah": (25.1288, 56.3265)}
UAE_UTC_OFFSET_H = 4  # no DST
TARAWEEH_AFTER_ISHA_MIN = 60


def _julian_day(y: int, m: int, day: int) -> float:
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5


def _sun_position(jd: float) -> tuple[float, float]:
    """(declination degrees, equation of time hours) — low-precision NOAA/adhan formulas."""
    dd = jd - 2451545.0
    g = math.radians((357.529 + 0.98560028 * dd) % 360)
    q = (280.459 + 0.98564736 * dd) % 360
    lon = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    e = math.radians(23.439 - 0.00000036 * dd)
    dec = math.degrees(math.asin(math.sin(e) * math.sin(lon)))
    ra = math.degrees(math.atan2(math.cos(e) * math.sin(lon), math.cos(lon))) / 15.0 % 24
    eqt = q / 15.0 - ra
    if eqt > 12:
        eqt -= 24
    elif eqt < -12:
        eqt += 24
    return dec, eqt


def _hour_angle(lat: float, dec_deg: float, angle_deg: float) -> float:
    lat_r, dec_r = math.radians(lat), math.radians(dec_deg)
    val = (-math.sin(math.radians(angle_deg)) - math.sin(lat_r) * math.sin(dec_r)) / (math.cos(lat_r) * math.cos(dec_r))
    val = max(-1.0, min(1.0, val))
    return math.degrees(math.acos(val)) / 15.0


def prayer_minutes(lat: float, lng: float, d: date) -> dict:
    """{"maghrib", "isha"}: minutes after local (UAE, UTC+4) midnight."""
    dec, eqt = _sun_position(_julian_day(d.year, d.month, d.day))
    noon_utc = 12 - lng / 15.0 - eqt

    def local_minutes(angle_deg, adjust_min):
        utc_h = noon_utc + _hour_angle(lat, dec, angle_deg)  # after solar noon
        return (round((utc_h + UAE_UTC_OFFSET_H) * 60) + adjust_min) % (24 * 60)

    return {"maghrib": local_minutes(0.833, 1), "isha": local_minutes(18.2, 1)}


def taraweeh_minutes(lat: float, lng: float, d: date) -> int:
    return (prayer_minutes(lat, lng, d)["isha"] + TARAWEEH_AFTER_ISHA_MIN) % (24 * 60)


def fmt_hm(minutes: int, lang: str) -> str:
    h, m = divmod(minutes, 60)
    ap = ("ص" if h < 12 else "م") if lang == "ar" else ("AM" if h < 12 else "PM")
    return f"{h % 12 or 12}:{m:02d} {ap}"


def iftar_line(city: str, d: date, lang: str) -> str | None:
    c = CITY_COORDS.get(city)
    if not c:
        return None
    t = fmt_hm(prayer_minutes(*c, d)["maghrib"], lang)
    return (f"الإفطار (المغرب) في {t}" if lang == "ar" else f"Iftar (Maghrib) at {t}")


def taraweeh_note(city: str, d: date, lang: str) -> str | None:
    c = CITY_COORDS.get(city)
    if not c:
        return None
    t = fmt_hm(taraweeh_minutes(*c, d), lang)
    return (f"بعد التراويح تقريباً ({t})" if lang == "ar" else f"after Taraweeh, approx. ({t})")


# --------------------------------------------------------------------------------- kids/summer
def kids_shows(site, before_hour: int | None = 14, flag_index: int = 1):
    """{city: [(fid, [shows today, optionally before `before_hour`])]} for films matching
    `film_flags(f)[flag_index]` (0 = family, 1 = kids — G/PG + animation/family), today only,
    non-empty groups only.

    `before_hour=None` drops the time cutoff entirely — the design brief (section E) states the
    "before 14:00" rule for the *kids* preset only ("a kids preset (G/PG + animation/family,
    starting before 14:00) and a summer page in July–August"), not for /summer/, so build_summer
    calls this with `before_hour=None, flag_index=0` rather than duplicating this loop."""
    out: dict = {}
    for s in site.shows:
        if s["date"] != site.today:
            continue
        if before_hour is not None and s["time"] >= f"{before_hour:02d}:00":
            continue
        f = site.films.get(s["film"])
        if not f or not film_flags(f)[flag_index]:
            continue
        city = (site.cinemas.get(s["cinema"]) or {}).get("city")
        if not city:
            continue
        out.setdefault(city, {}).setdefault(s["film"], []).append(s)
    return {city: sorted(fids.items(), key=lambda kv: -len(kv[1])) for city, fids in out.items()}


def summer_active(today: date) -> bool:
    return today.month in (7, 8)


# ------------------------------------------------------------------------------------- register
def register(site):
    p = SeasonsPages(site)
    today_d = date.fromisoformat(site.today)
    eid = eid_within(today_d)
    ramadan = is_ramadan(today_d)
    in_summer = summer_active(today_d)

    pages = []
    for lang in ("ar", "en"):
        pages.append(Page(("kids",), lang, (lambda lang=lang: p.build_kids(lang))))
        pages.append(Page(("summer",), lang, (lambda lang=lang: p.build_summer(lang, in_summer))))
        if eid:
            pages.append(Page(("eid",), lang, (lambda lang=lang, eid=eid: p.build_eid(lang, eid))))

    nav = [NavItem("kids", href=lambda lang: P(lang, "kids"), label=TITLES["kids"])]
    if in_summer:
        nav.append(NavItem("summer", href=lambda lang: P(lang, "summer"), label=TITLES["summer"]))
    if eid:
        nav.append(NavItem("eid", href=lambda lang: P(lang, "eid"), label=TITLES["eid"]))

    slots = {}
    if ramadan:
        slots["home.after_tonight"] = lambda site, lang: p.ramadan_banner(lang, "dubai")
        slots["city.after_tonight"] = lambda site, lang, city=None: p.ramadan_banner(lang, city) if city else ""

    return Plugin(pages=pages, nav=nav, slots=slots,
                  data={"data/seasons.json": {"ramadan": ramadan, "eid": (eid[0] if eid else None)}})


class SeasonsPages:
    def __init__(self, site):
        self.site = site

    def __getattr__(self, k):
        return getattr(self.site, k)

    # ---- Ramadan slot -------------------------------------------------------------------
    def ramadan_banner(self, lang, city):
        today_d = date.fromisoformat(self.today)
        iftar = iftar_line(city, today_d, lang)
        tara = taraweeh_note(city, today_d, lang)
        if not iftar:
            return ""
        bits = esc(iftar) + (f" · {esc(tara)}" if tara else "")
        return f'<p class="wrap iftar">{bits}</p>'

    # ---- /eid/ ---------------------------------------------------------------------------
    def build_eid(self, lang, eid):
        which, start = eid
        name = {"fitr": ("عيد الفطر", "Eid al-Fitr"), "adha": ("عيد الأضحى", "Eid al-Adha")}[which]
        # Task A's «نازل الخميس» feed, when it exists: a dict keyed by fid (steps/coming.py
        # `data["coming"][fid] = {...}`; pages/coming.py reads it the same way), never a list.
        coming = self.d.get("coming")
        if coming:
            fids = [fid for fid, c in coming.items()
                    if c.get("release_date") and start <= date.fromisoformat(c["release_date"]) <= start + timedelta(days=10)
                    and fid in self.films]
        else:
            fids = list(self.showing)
        title = L(TITLES["eid"], lang)
        body = f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>'
        body += (f'<p class="lead">{L(name, lang)} {esc(("يوم " if lang == "ar" else "on ") + start.isoformat())}'
                 f' — {("تقريباً" if lang == "ar" else "approx.")}</p></section>')
        if fids:
            body += self.posters_row(lang, fids, [s for s in self.shows if s["film"] in fids], L(TITLES["eid"], lang))
        else:
            body += (f'<p class="wrap empty">{"ما عندنا أفلام مؤكدة لهالعيد للحين" if lang == "ar" else "No confirmed releases for this Eid yet"}</p>')
        return {"title": title, "desc": title, "body": body, "kind": "eid", "nav": "eid",
                "graph": [self.breadcrumb_ld(lang, (title, P(lang, "eid")))]}

    # ---- /kids/ ----------------------------------------------------------------------------
    def build_kids(self, lang):
        groups = kids_shows(self.site)
        title = L(TITLES["kids"], lang)
        body = f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>'
        body += (f'<p class="lead">{"أفلام مناسبة للعيال، قبل الساعة 2 الظهر، حسب المدينة." if lang == "ar" else "Films suited for kids, before 2pm, by city."}</p></section>')
        if not groups:
            body += f'<p class="wrap empty">{"ما فيه عروض عيال قبل الظهر اليوم" if lang == "ar" else "No kids-hours shows today"}</p>'
        else:
            for city, ar, en in CITIES:
                if city not in groups:
                    continue
                body += f'<section class="wrap"><h2>{esc(L((ar, en), lang))}</h2><div class="rows">'
                for fid, shows in groups[city]:
                    times = " ".join(sorted({s["time"] for s in shows}))
                    body += (f'<div class="row"><a href="{P(lang, "film", fid)}">{esc(self.ftitle(fid, lang))}</a>'
                             f'<span class="sub">{num(times)}</span></div>')
                body += '</div></section>'
        return {"title": title, "desc": title, "body": body, "kind": "kids", "nav": "kids",
                "graph": [self.breadcrumb_ld(lang, (title, P(lang, "kids")))]}

    # ---- /summer/ ----------------------------------------------------------------------------
    def build_summer(self, lang, in_summer):
        title = L(TITLES["summer"], lang)
        body = f'<section class="head wrap">{self.crumbs(lang, (title, None))}<h1 class="pt">{esc(title)}</h1>'
        if not in_summer:
            body += (f'<p class="lead">{"صفحة الصيف تفتح يوليو وأغسطس. رجعوا وقتها." if lang == "ar" else "The summer page opens in July and August. Come back then."}</p></section>')
            # path=: written at its normal place but kept out of the sitemap while noindex (final review I2)
            return {"title": title, "desc": title, "body": body, "kind": "summer", "robots": NOINDEX,
                    "path": os.path.join(self.out, *(["en"] if lang == "en" else []), "summer", "index.html")}
        # family films (film_flags index 0), any time of day -- no "before 14:00" cutoff: the
        # brief states that restriction for the kids preset only, not for /summer/ (kids_shows()
        # docstring). Reuses kids_shows() rather than repeating its filter/group loop here.
        groups = kids_shows(self.site, before_hour=None, flag_index=0)
        body += (f'<p class="lead">{"أفلام عائلية، فترة الصيف." if lang == "ar" else "Family films, summer break."}</p></section>')
        if not groups:
            body += f'<p class="wrap empty">{"ما فيه عروض عائلية اليوم" if lang == "ar" else "No family-hours shows today"}</p>'
        else:
            for city, ar, en in CITIES:
                if city not in groups:
                    continue
                fids = [fid for fid, _shows in groups[city]]
                body += f'<section class="wrap"><h2>{esc(L((ar, en), lang))}</h2>'
                body += self.posters_row(lang, fids, self.shows, "")
                body += '</section>'
        return {"title": title, "desc": title, "body": body, "kind": "summer", "nav": "summer",
                "graph": [self.breadcrumb_ld(lang, (title, P(lang, "summer")))]}
