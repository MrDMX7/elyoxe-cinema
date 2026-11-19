"""«عروض مجانية» page (owner 2026-11-19): /free/ and /en/free/ in the app's design, from data["free"]; a row at the top of
the home's «قريباً» and a footer link lead to it, and the sitemap lists it while it has something to show."""
import datetime as dt
import json
import os
import re
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

import build_app  # noqa: E402
from site_kit import Halls, load_discounts  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


def _items(today):
    d = dt.date.fromisoformat(today)
    at = lambda n: (d + dt.timedelta(days=n)).isoformat()  # noqa: E731
    return [
        {"id": "jlt-1", "title": "Inside Out 2", "venue": "JLT Park, Cluster Q", "venue_ar": "حديقة JLT", "city": "dubai",
         "date": at(1), "time": "19:30", "price": 0, "price_note_ar": "ببلاش على العشب", "rsvp": False, "url": "https://jlt.ae/x",
         "source": "jlt", "series": "Cinema Under the Stars", "series_ar": "سينما تحت النجوم"},
        {"id": "louvre-1", "title": "Family Film Screenings", "title_ar": "أفلام العائلة", "venue": "Louvre Abu Dhabi",
         "venue_ar": "اللوفر أبوظبي", "city": "abu-dhabi", "date": at(3), "time": "14:00", "price": 0, "rsvp": True,
         "url": "https://louvre.example/x", "source": "hand", "note_ar": "أفلام قصيرة ثم فيلم طويل"},
        {"id": "als-1", "title": "Hijra", "venue": "The Yard, Alserkal Avenue", "venue_ar": "السركال أفنيو، The Yard",
         "city": "dubai", "date": at(3), "time": "", "price": None, "rsvp": True, "url": "https://alserkal.online/event/hijra",
         "source": "alserkal"},
        {"id": "cf-1", "title": "Emirati Film Month", "title_ar": "شهر الفيلم الإماراتي", "venue": "Cultural Foundation",
         "venue_ar": "المجمّع الثقافي", "city": "abu-dhabi", "date": at(5), "end_date": at(40), "time": "", "price": 0,
         "rsvp": False, "url": "https://culturalfoundation.ae/x", "source": "hand"},
        {"id": "old-1", "title": "Gone", "venue": "x", "city": "dubai", "date": at(-2), "time": "19:00", "price": 0,
         "url": "https://x.example", "source": "hand"},
    ]


def _build(tmp_path, lang):
    out = str(tmp_path / lang)
    os.makedirs(out)
    data = json.load(open(DATA, encoding="utf-8"))
    build_app.LANG = lang
    try:
        app = build_app.App(data, load_discounts(DISC), Halls(os.path.join(ROOT, "halls.yaml")), out,
                            "/en/" if lang == "en" else "/", live=True)
        data["free"] = _items(app.k.today)
        app.run()
    finally:
        build_app.LANG = "ar"
    return out, app


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def test_the_free_page_lists_what_is_to_come_by_day(tmp_path):
    out, app = _build(tmp_path, "ar")
    h = read(out, "free", "index.html")
    assert h.count('class="fcard"') == 4                                   # the past one is gone
    assert 'data-kind="free"' in h and "عروض مجانية" in h
    assert h.index("برامج على كم يوم") < h.index('class="cday"')            # a run of days comes first
    assert "شهر الفيلم الإماراتي" in h and ">لين<" in h
    assert h.count('class="ftag free"') == 3 and "الدخول في الرابط" in h and "الوقت في الرابط" in h
    assert 'data-c="dubai"' in h and 'data-c="abu-dhabi"' in h               # one chip per emirate that has something
    assert "حديقة JLT" in h and "سينما تحت النجوم" in h and "أفلام قصيرة ثم فيلم طويل" in h
    ld = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]
    events = [e for g in ld for e in (g.get("@graph") if isinstance(g, dict) and "@graph" in g else [g]) if isinstance(e, dict) and e.get("@type") == "Event"]
    assert len(events) == 4 and sum(1 for e in events if e.get("isAccessibleForFree")) == 3
    assert any(e["startDate"].endswith("T19:30:00+04:00") for e in events)


def test_the_home_and_every_page_lead_to_it(tmp_path):
    out, app = _build(tmp_path, "ar")
    home = read(out, "index.html")
    row = re.search(r'<a class="crow freerow" href="/free/">(.*?)</a>', home, re.S)
    assert row and "4 " in row.group(1)
    assert home.index("freerow") > home.index('data-key="coming"')         # inside «قريباً», at its top
    assert '<a href="/free/">عروض مجانية</a>' in read(out, "film", app.films[0], "index.html")


def test_the_english_free_page(tmp_path):
    out, app = _build(tmp_path, "en")
    h = read(out, "free", "index.html")
    assert '<html lang="en" dir="ltr"' in h and "Free screenings" in h and "Inside Out 2" in h and "Emirati Film Month" in h
    body = re.sub(r"<script.*?</script>", "", h, flags=re.S)
    left = {x.strip() for x in re.findall(r"[؀-ۿ][^<>\"]*", body)} - {"العربية"}
    assert not left, left
    assert '<a href="/en/free/">Free screenings</a>' in h


def test_the_sitemap_lists_it_only_with_something_on_it():
    sys.path.insert(0, os.path.join(ROOT, "pages"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("free_page", os.path.join(ROOT, "pages", "free.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    on = SimpleNamespace(d={"free": [{"date": "2026-12-01"}]}, today="2026-11-20")
    off = SimpleNamespace(d={"free": [{"date": "2026-11-01"}]}, today="2026-11-20")
    assert mod.register(on).sitemap == [("free",)] and mod.register(off).sitemap == []


def test_the_free_page_script_parses_and_filters():
    js = read(ROOT, "app", "app.js")
    assert "[data-free-city]" in js and "data-free-none" in js
