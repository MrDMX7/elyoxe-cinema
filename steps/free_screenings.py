"""steps/free_screenings.py — «عروض مجانية» (owner 2026-11-19: «حلو نشتغل عليه»): free and community film screenings
across the UAE that are not on any chain's booking site — park and beach cinemas, museums, universities, festivals.

Two kinds of source, both into one list:
  - read on every run (a plain request each, no browser; samples in tests/fixtures/free/):
      jlt       Cinema Under the Stars, JLT Park — the season's whole Saturday line-up is in the page's HTML
      nyuad     NYU Abu Dhabi Arts Center — its own events JSON; event_type «Screening»
      akil      Cinema Akil — its films API; only a session every seat of which is priced 0 (an outdoor night, a matinee)
      alserkal  Alserkal Avenue — its events page; a card labelled «Film Screening»
  - free_screenings.yaml (the repo root): the rest, entered by hand from the source's own page, because the page
    blocks scripts (Louvre Abu Dhabi, Dubai Holding communities), is a once-a-year festival, or lives on Instagram.
    An entry past its last day simply stops showing.

A source that fails keeps its last good items from the previous run (data/latest.json) while they are still to come,
so one site's bad night does not empty the page. Research behind the choice of sources: the 2026-11-19 survey
(docs/superpowers/specs/2026-11-19-free-screenings-design.md).

data["free"] = [{"id", "title", "venue", "city", "date", "time", "end_date", "price", "price_note_ar",
                 "rsvp", "url", "source", "kind", "note_ar", "lang"}], sorted by (date, time), only what is still
to come within HORIZON_DAYS (a range runs until its end_date). price: 0 = free, a number = AED, None = not stated.
run() -> {"items": n, "sources": {name: count | "error: …" | "kept N"}}.
"""
from __future__ import annotations

import html as _html
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
HAND = ROOT / "free_screenings.yaml"
HORIZON_DAYS = 75
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

JLT_URL = "https://jlt.ae/calendar/cinema-under-the-stars"
NYUAD_URL = "https://publicprograms.nyuad.nyu.edu/en/events.ppeventslist.en.upcoming.json"
NYUAD_SITE = "https://publicprograms.nyuad.nyu.edu"
AKIL_SITE = "https://www.cinemaakil.com"
ALSERKAL_URL = "https://alserkal.online/events"


def _today(now_iso) -> date:
    try:
        return datetime.fromisoformat(now_iso).date() if now_iso else date.today()
    except ValueError:
        return date.today()


def _hhmm(text: str) -> str:
    """«7:30 PM», «7:30pm», «19:30» -> «19:30»; anything else -> ""."""
    m = re.search(r"(\d{1,2})(?::(\d\d))?\s*([ap])\.?m\.?", text or "", re.I)
    if m:
        h, mi = int(m.group(1)) % 12, int(m.group(2) or 0)
        return f"{h + (12 if m.group(3).lower() == 'p' else 0):02d}:{mi:02d}"
    m = re.search(r"\b(\d{1,2}):(\d\d)\b", text or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60]


# ---------------------------------------------------------------- the readers (pure: text in, items out)
def parse_jlt(page: str) -> list[dict]:
    """One `cinema-listing-item` per Saturday: data-month «Nov 2026», a «Nov 21» label, «Saturday, 7:30 PM», the title."""
    out = []
    for m in re.finditer(r'<div class="cinema-listing-item" data-month="([A-Za-z]{3}) (\d{4})">(.*?)(?=<div class="cinema-listing-item"|\Z)',
                         page, re.S):
        mon, year, body = MONTHS.get(m.group(1).lower()), int(m.group(2)), m.group(3)
        day = re.search(r"<span>\s*[A-Za-z]{3}\s+(\d{1,2})\s*</span>", body)
        title = re.search(r'alt="([^"]+?) poster"', body)
        if not (mon and day and title):
            continue
        rest = _text(body)
        d = date(year, mon, int(day.group(1)))
        name = _html.unescape(title.group(1)).strip()
        out.append({"id": f"jlt-{d.isoformat()}", "title": name, "venue": "JLT Park, Cluster Q", "venue_ar": "حديقة أبراج بحيرات جميرا (JLT)، كلستر Q", "city": "dubai",
                     "date": d.isoformat(), "time": _hhmm(rest) or "19:30", "price": 0,
                     "price_note_ar": "الدخول ببلاش على العشب، وبين باق وفشار بـ30 درهم", "rsvp": False,
                     "url": JLT_URL, "source": "jlt", "kind": "outdoor", "series": "Cinema Under the Stars", "series_ar": "سينما تحت النجوم"})
    return out


def parse_nyuad(payload: dict) -> list[dict]:
    """The Arts Center's upcoming-events JSON: event_type «Screening»; one item per performance (date_time)."""
    out = []
    for e in (payload or {}).get("result") or []:
        if (e.get("event_type") or "").lower() != "screening":
            continue
        url = NYUAD_SITE + e["url"] if str(e.get("url") or "").startswith("/") else (e.get("url") or NYUAD_SITE)
        runs = [p for p in e.get("performances") or [] if p.get("date")] or [{"date": e.get("start_date"), "date_time": ""}]
        for p in runs:
            if not p.get("date"):
                continue
            tm = (p.get("date_time") or "")[11:16] or _hhmm(e.get("display_date") or "")
            out.append({"id": f"nyuad-{_slug(e.get('event_title'))}-{p['date']}", "title": (e.get("event_title") or "").strip(),
                        "venue": "NYU Abu Dhabi Arts Center, Saadiyat", "venue_ar": "مركز الفنون في جامعة نيويورك أبوظبي، السعديات", "city": "abu-dhabi", "date": p["date"], "time": tm,
                        "price": None, "rsvp": True, "url": url, "source": "nyuad", "kind": "university",
                        "series": (e.get("prefix") or "").strip() or None})
    return out


def parse_akil(payload: dict) -> list[dict]:
    """Cinema Akil's films API: a session is listed only when it has prices and every one of them is 0."""
    out = []
    for r in ((payload or {}).get("films") or {}).get("Records") or []:
        title = (r.get("original_movie_title") or "").strip()
        if not title:
            continue
        for sc in r.get("screens") or []:
            for day in sc.get("shows") or []:
                for s in day.get("shows") or []:
                    prices = [float(p.get("rc_total_amount") or 0) for p in s.get("schedulePricing") or []]
                    tm = s.get("ss_start_show_time") or ""
                    if not prices or max(prices) > 0 or not re.match(r"^\d\d:\d\d$", tm) or s.get("ss_is_active", "Y") != "Y":
                        continue
                    where = (s.get("cinema_name") or "").strip()
                    venue = "Cinema Akil, " + ("25hours Hotel One Central" if "25hours" in where.lower()
                                               else "the Yard, Alserkal Avenue" if "outdoor" in where.lower()
                                               else "Alserkal Avenue")
                    venue_ar = ("سينما عقيل، فندق 25hours ون سنترال" if "25hours" in where.lower()
                                else "سينما عقيل، ساحة السركال أفنيو" if "outdoor" in where.lower() else "سينما عقيل، السركال أفنيو")
                    out.append({"id": f"akil-{r.get('movie_id')}-{day.get('date')}-{tm.replace(':', '')}", "title": title,
                                "venue": venue, "venue_ar": venue_ar, "city": "dubai", "date": day.get("date"), "time": tm, "price": 0,
                                "price_note_ar": "السعر صفر في موقع سينما عقيل", "rsvp": True,
                                "url": f"{AKIL_SITE}/now-showing-booking/{r.get('movie_id')}/{_slug(title)}",
                                "source": "akil", "kind": "cinema", "lang": (s.get("movie_lang") or "").split(",")[0].strip() or None})
    return out


def parse_alserkal(page: str) -> list[dict]:
    """Alserkal's events page (Webflow): an event card whose label says «Film Screening», with its venue and start date."""
    out = []
    for m in re.finditer(r'<a href="(/event/[^"]+)" class="event-card[^"]*">(.*?)</a>', page, re.S):
        body = m.group(2)
        label = _text((re.search(r'class="event-card-label">(.*?)</div>', body, re.S) or [None, ""])[1])
        if "film screening" not in label.lower():
            continue
        title = _text((re.search(r'class="event-card-title">(.*?)</h3>', body, re.S) or [None, ""])[1])
        venue = _text((re.search(r'class="event-card-organizer">(.*?)</div>', body, re.S) or [None, ""])[1])
        start = re.search(r'event-starts="([A-Za-z]+ \d{1,2}, \d{4})"', body)
        if not (title and start):
            continue
        d = datetime.strptime(start.group(1), "%B %d, %Y").date()
        out.append({"id": f"alserkal-{_slug(title)}-{d.isoformat()}", "title": title,
                    "venue": f"{venue}, Alserkal Avenue" if venue else "Alserkal Avenue",
                    "venue_ar": f"السركال أفنيو، {venue}" if venue else "السركال أفنيو", "city": "dubai",   # Arabic first: bidi
                    "date": d.isoformat(), "time": "", "price": None, "rsvp": True,
                    "url": "https://alserkal.online" + m.group(1), "source": "alserkal", "kind": "arts"})
    return out


def nyuad_detail(page: str) -> dict:
    """An NYUAD event page: the venue is the schema.org place name after the date (a screening can be off campus —
    Hekayah 2026 was at Souq Al Mina), and «This event is not ticketed» means free, first come first served."""
    out = {}
    v = re.search(r'class="t3 date-time.*?<meta itemprop="name" content="([^"]+)"', page, re.S)
    if v:
        out["venue"] = _html.unescape(v.group(1)).strip()
    tickets = _text((re.search(r"<h2>Ticket Information</h2>(.*?)</article>", page, re.S) or [None, ""])[1])
    if re.search(r"not ticketed|free (?:admission|entry|of charge)|admission is free", tickets, re.I):
        out.update(price=0, rsvp=not re.search(r"first come", tickets, re.I),
                   price_note_ar="ببلاش، اللي يوصل أول يدخل" if re.search(r"first come", tickets, re.I) else "ببلاش")
    else:
        aed = re.search(r"AED\s*(\d+(?:\.\d+)?)", tickets)
        if aed:
            out["price"] = float(aed.group(1))
    return out


def alserkal_detail(page: str) -> dict:
    """An Alserkal event page: «Open Hours» → the start time, «Venue» → the place."""
    out = {}
    hrs = re.search(r"Open Hours</strong></div></div><div[^>]*><div class=\"event-detail-value\">([^<]+)<", page)
    if hrs and _hhmm(hrs.group(1)):
        out["time"] = _hhmm(hrs.group(1))
    return out


def hand_items(path: Path = HAND) -> list[dict]:
    """free_screenings.yaml's items, as they are (the file's header says what each field means)."""
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    out = []
    for it in doc.get("items") or []:
        if not (it.get("id") and it.get("title") and it.get("date") and it.get("city")):
            continue
        it = {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in it.items()}   # YAML reads 2026-11-19 as a date
        out.append({**it, "end_date": it.get("end_date") or None, "time": str(it.get("time") or ""),
                    "source": it.get("source") or "hand"})
    return out


# ---------------------------------------------------------------- fetching
def _fetch_all() -> dict:
    """{source: [items] | Exception} — each source on its own, so one site's failure is only its own."""
    from readers.common import Polite
    sess = Polite(gap=1.0)
    today = date.today()
    jobs = {
        "jlt": lambda: parse_jlt(sess.get(JLT_URL).text),
        "nyuad": lambda: parse_nyuad(sess.get(NYUAD_URL).json()),
        "akil": lambda: parse_akil(sess.get(f"{AKIL_SITE}/api/films", params={
            "startDate": today.isoformat(), "endDate": (today + timedelta(days=45)).isoformat()}).json()),
        "alserkal": lambda: parse_alserkal(sess.get(ALSERKAL_URL).text),
    }
    details = {"nyuad": nyuad_detail, "alserkal": alserkal_detail}
    out = {}
    for name, job in jobs.items():
        try:
            out[name] = job()
        except Exception as e:  # noqa: BLE001 - one source's failure must not cost the others
            out[name] = e
            continue
        if name in details:                       # each event's own page: the venue, time and entry the list leaves out
            pages = {}
            for it in out[name]:
                try:
                    if it["url"] not in pages:
                        pages[it["url"]] = details[name](sess.get(it["url"]).text)
                    got = pages[it["url"]]
                    if got.get("venue") and "arts center" not in got["venue"].lower():
                        it.pop("venue_ar", None)          # the Arabic name was the Arts Center's; this one is elsewhere
                    it.update(got)
                except Exception:  # noqa: BLE001 - the list's own item stands without its details
                    pass
    return out


def _previous(data_dir) -> list[dict]:
    try:
        return json.loads((Path(data_dir or ROOT / "data") / "latest.json").read_text(encoding="utf-8")).get("free") or []
    except (OSError, ValueError):
        return []


def collect(fetched: dict, hand: list[dict], previous: list[dict], today: date) -> tuple[list[dict], dict]:
    """Merge the readers' items, the hand list and (for a failed source) its previous items; keep what is to come."""
    report, items = {}, list(hand)
    for name, got in fetched.items():
        if isinstance(got, Exception):
            kept = [p for p in previous if p.get("source") == name]
            items += kept
            report[name] = f"error: {type(got).__name__}: {str(got)[:120]}" + (f" (kept {len(kept)})" if kept else "")
        else:
            items += got
            report[name] = len(got)
    report["hand"] = len(hand)
    last = (today + timedelta(days=HORIZON_DAYS)).isoformat()
    seen, out = set(), []
    for it in sorted(items, key=lambda i: (i.get("date") or "", i.get("time") or "", i.get("id") or "")):
        until = it.get("end_date") or it.get("date") or ""
        if not until or until < today.isoformat() or (it.get("date") or "") > last or it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
    return out, report


def run(data: dict, ctx: dict) -> dict | None:
    today = _today(ctx.get("now"))
    fetched = {} if ctx.get("offline") else _fetch_all()
    items, report = collect(fetched, hand_items(), _previous(ctx.get("data_dir")), today)
    data["free"] = items
    return {"items": len(items), "sources": report}
