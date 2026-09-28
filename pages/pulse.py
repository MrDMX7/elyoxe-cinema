"""Signals (legend W1-D3): what changed, how old a chain's prices are, and what a hall is called. No page of its
own, no script, no stylesheet: two data files, one line under a cinema's prices, and the helpers the redesigned
pages read (W2-P3 time buttons and the stub, W2-P6 tables, W3-P1 «من آخر زيارة», W3-P8 rank arrows).

/data/pulse.json  {"_": [generated, seed date],
                   fid: [verdict, first_seen, coming, [[similar fid, reason], … up to 4]]}
  verdict   "y" يستاهل · "m" بين بين · "s" تجنّبه · "" no verdict yet (the same four as site_kit.VERDICT)
  first_seen film_history.json's own date (refresh.attach_first_seen), "" for a film not shown yet. Every film
            present at the seeding run carries the seed date (all 66 read 2026-09-27), so that date says nothing
            about newness: «جديد» leans on `coming` for those, and on first_seen only when it is after the seed
  coming    the release date a chain's coming-soon list gives: for a coming film its date, for a showing film
            the date it had before it opened (refresh.carry_released), else ""
  reason    why the pair is alike, the strongest first (similar.py, as the «شي يشبه» tab ranks them):
            "d:<person id>" same director, "c:<person id>" shared cast, "g:<genre key>", "l:<language>"
  Every showing film and every coming film; ≤ 8 KB gzipped on real data (tests/test_w1_d3.py).

/data/rank.json   {"d": today, "y": yesterday, "at": generated,
                   "uae": {"d": [[fid, shows, cinemas], …], "y": […]},
                   "c": {city: {"d": […], "y": […]}}}
  Each list is that day's whole schedule in rank order (most shows, then most cinemas, then fid), so rank = index
  + 1 and an arrow is yesterday's rank minus today's. UAE: price_history.jsonl's day lines (the /boxoffice/
  source; today's line from this build when the history lacks it). Cities: refresh.py's per-city day reads
  (data["rank_days"]: the fullest read of each day, which price_history does not keep per city); with none, today
  is counted from this build and yesterday is empty.

cinema.after_halls  «أسعار ريل من 18:05» under a cinema's prices when its chain was last read more than 2 h before
                    this build (each chain's own read time, refresh.apply_read_times). The voice table's line.

Helpers for other packages: read_label(site, chain, lang), hall_label(site, chain, code, raw label, lang)."""
from __future__ import annotations

import datetime as dt
import os
import re

import yaml

import price_history as ph
import similar as simmod
from site_kit import MONTHS, MONTHS_EN, Plugin, esc, parse_iso

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HALLS_PATH = os.path.join(ROOT, "halls.yaml")
OLD_AFTER = dt.timedelta(hours=2)          # a chain read longer ago than this labels its prices with the time
VERDICT_CODE = {"yes": "y", "mixed": "m", "skip": "s"}
DUBAI = dt.timezone(dt.timedelta(hours=4))


def register(site):
    p = Pulse(site)
    return Plugin(data={"data/pulse.json": p.pulse, "data/rank.json": p.rank},
                  slots={"cinema.after_halls": lambda s, lang, cid: p.cinema_note(lang, cid)})


# ---------------------------------------------------------------- each chain's own read time
def chain_short(site, chain, lang):
    """«ريل» / "Reel": the chain's short name (halls.yaml `name_ar`, `short`)."""
    c = (site.h.y.get(chain) or {}) if getattr(site, "h", None) is not None else {}
    return (c.get("name_ar") if lang == "ar" else c.get("short") or c.get("name")) or chain.title()


def read_label(site, chain, lang, now=None):
    """«أسعار ريل من 18:05» when `chain` was last read more than 2 h before `now` (the build's clock), else "".
    Yesterday: «أسعار ريل من أمس 18:05»; earlier: «أسعار ريل من 21 سبتمبر». The time is the chain's own read
    (data["chains"][chain]["at"]), in UAE time."""
    info = (site.d.get("chains") or {}).get(chain) or {}
    try:
        at = parse_iso(info["at"]).astimezone(DUBAI)
    except (KeyError, TypeError, ValueError):
        return ""
    now = (now or site.now).astimezone(DUBAI)
    if now - at <= OLD_AFTER:
        return ""
    name, hm = chain_short(site, chain, lang), at.strftime("%H:%M")
    days = (now.date() - at.date()).days
    if lang == "ar":
        when = hm if days == 0 else f"أمس {hm}" if days == 1 else f"{at.day} {MONTHS[at.month - 1]}"
        return f"أسعار {name} من {when}"
    when = hm if days == 0 else f"yesterday {hm}" if days == 1 else f"{at.day} {MONTHS_EN[at.month - 1]}"
    return f"{name} prices from {when}"


# ---------------------------------------------------------------- hall labels (halls.yaml `labels`)
_LABELS: dict = {}


def labels(path=HALLS_PATH):
    """halls.yaml's `labels` block, read once per path."""
    if path not in _LABELS:
        try:
            y = yaml.safe_load(open(path, encoding="utf-8")) or {}
        except OSError:
            y = {}
        _LABELS[path] = y.get("labels") or {}
    return _LABELS[path]


def title_case(text, acronyms):
    """Every all-capitals word that is not an acronym becomes Title Case («PREMIER» -> «Premier», «SAMSUNG ONYX» ->
    «Samsung Onyx»); acronyms, mixed-case brands (ScreenX) and Arabic stay as they are."""
    keep = {a.upper() for a in acronyms}
    return re.sub(r"[A-Za-z0-9]+", lambda m: m.group(0) if m.group(0).upper() in keep or not re.search(r"[A-Z]{2}", m.group(0))
                  or m.group(0) != m.group(0).upper() else m.group(0).capitalize(), text or "")


def hall_label(site, chain, code, raw_label, lang, table=None):
    """What a hall is called on a time button, the stub and in tables: halls.yaml labels[chain][key], then
    labels.any[key], then the entry's (name_ar, name), then the raw name in Title Case (acronyms kept). Never an
    all-capitals word except the acronyms."""
    t = table if table is not None else labels()
    key, name, entry, _clean = site.h.resolve(chain, code, raw_label)
    pair = (t.get(chain) or {}).get(key) or (t.get("any") or {}).get(key)
    if pair:
        return pair[0] if lang == "ar" else pair[1]
    acr = t.get("acronyms") or ()
    if entry:
        return (entry.get("name_ar") if lang == "ar" else None) or title_case(entry.get("name") or key, acr)
    return title_case(name, acr)


# ---------------------------------------------------------------- the plug-in
class Pulse:
    def __init__(self, site):
        self.s = site

    # -------- «أسعار ريل من 18:05» under a cinema's prices
    def cinema_note(self, lang, cid):
        chain = (self.s.cinemas.get(cid) or {}).get("chain")
        text = read_label(self.s, chain, lang) if chain else ""
        return f'<p class="hint" data-read-old="{esc(chain)}">{esc(text)}</p>' if text else ""

    # -------- /data/pulse.json
    def pulse(self):
        s = self.s
        films, today = s.films, s.today
        showing = [f for f in s.showing if f in films]
        counts = {}
        for x in s.shows:
            if x.get("date") == today:
                counts[x["film"]] = counts.get(x["film"], 0) + 1
        with_shows = {x["film"] for x in s.shows}
        pool = [f for f in showing if f in with_shows]
        pp = simmod.people_of(films)
        directors = lambda x: set(simmod._ids(films[x].get("directors")) + simmod._ids(films[x].get("director")))
        seed = min((str(f.get("first_seen")) for f in films.values() if f.get("first_seen")), default="")
        out = {"_": [s.d.get("generated") or "", seed]}
        for fid in showing:
            f = films[fid]
            v = (f.get("verdict") or {}).get("verdict") if isinstance(f.get("verdict"), dict) else None
            sims = []
            if fid in with_shows:
                for other, _score, reasons in simmod.similar(films, fid, pool, n=4, weight=lambda y: counts.get(y, 0), _pp=pp):
                    kind, val = reasons[0]
                    if kind == "person":
                        code = f"{'d' if val in directors(fid) and val in directors(other) else 'c'}:{val}"
                    else:
                        code = f"{kind[0]}:{val}"
                    sims.append([other, code])
            out[fid] = [VERDICT_CODE.get(v, ""), str(f.get("first_seen") or ""), str(f.get("released") or ""), sims]
        for fid, c in (s.d.get("coming") or {}).items():
            if fid not in out and isinstance(c, dict):
                out[fid] = ["", "", str(c.get("release_date") or ""), []]
        return out

    # -------- /data/rank.json
    @staticmethod
    def ordered(fs):
        """[[fid, shows, cinemas], …] in rank order."""
        return [[f, int(v[0]), int(v[1])] for f, v in sorted(fs.items(), key=lambda kv: (-int(kv[1][0]), -int(kv[1][1]), kv[0]))]

    def rank(self):
        s = self.s
        today = s.today
        yday = (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat()
        # UAE: the history's day lines (the /boxoffice/ source), this build's read of today when it has none
        snap = ph.snapshot({"generated": s.d.get("generated"), "shows": s.shows, "cinemas": s.cinemas, "films": s.films}, s.h)
        hist = {d: v for d, v in ph.load(ph.history_path()).items() if d <= today}
        full, _ = ph.merge(hist, {d: v for d, v in snap.items() if d == today})
        uae = {k: self.ordered((full.get(d) or {}).get("films") or {}) for k, d in (("d", today), ("y", yday))}
        # cities: refresh's fullest per-city read of each day
        days = s.d.get("rank_days") or {}
        cities = sorted({c.get("city") for c in s.cinemas.values() if c.get("city")})
        now_counts = {}
        for x in s.shows:
            c = s.cinemas.get(x["cinema"]) or {}
            if x.get("date") == today and c.get("city"):
                per = now_counts.setdefault(c["city"], {}).setdefault(x["film"], [0, set()])
                per[0] += 1
                per[1].add(x["cinema"])
        now_counts = {c: {f: [n, len(cs)] for f, (n, cs) in fs.items()} for c, fs in now_counts.items()}
        by_city = {}
        for city in cities:
            t = (days.get(today) or {}).get(city) or now_counts.get(city) or {}
            y = (days.get(yday) or {}).get(city) or {}
            if t or y:
                by_city[city] = {"d": self.ordered(t), "y": self.ordered(y)}
        return {"d": today, "y": yday, "at": s.d.get("generated") or "", "uae": uae, "c": by_city}
