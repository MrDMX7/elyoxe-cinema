"""pages/questions.py: /q/<slug>/ answers generated only when the data answers them — the number, its date,
FAQPage JSON-LD and links to the pages that show the evidence; Arabic and English; indexable."""
import json, os, re, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
MINE = ("core", "insights", "questions")   # the other phase-2 modules are other tasks' (the full suite builds them all)


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def ld(html):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))["@graph"]


def faq(html):
    return next(g for g in ld(html) if g.get("@type") == "FAQPage")["mainEntity"][0]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("q"))
    old = os.environ.get("CINEMA_PRICE_HISTORY")
    os.environ["CINEMA_PRICE_HISTORY"] = os.path.join(o + "-none.jsonl")
    try:
        build.build(DATA, DISC, o, noindex=False, modules=build.discover(only=MINE))
    finally:
        if old is None: os.environ.pop("CINEMA_PRICE_HISTORY", None)
        else: os.environ["CINEMA_PRICE_HISTORY"] = old
    return o


def slugs(out):
    return sorted(os.listdir(os.path.join(out, "q")))


def expected_min(city, key):
    """(date, cheapest live seat) in `city` for hall key `key`, on the date with the most priced shows (the
    earliest on a tie) — fixture data, computed independently."""
    d = json.load(open(DATA, encoding="utf-8"))
    h = build.Halls(os.path.join(ROOT, "halls.yaml"))
    by = {}
    for s in d["shows"]:
        c = d["cinemas"][s["cinema"]]
        if c["city"] != city or d["films"][s["film"]].get("status") == "archived": continue
        if h.key(c["chain"], s.get("hall") or "OTHER", s.get("hall_label") or "") != key: continue
        ps = [p["aed"] for p in s.get("prices") or [] if p.get("aed")]
        if ps: by.setdefault(s["date"], []).append(min(ps))
    if not by: return None
    day = max(sorted(by), key=lambda x: len(by[x]))
    return day, min(by[day])


def test_every_question_page_is_whole(out):
    ss = [s for s in slugs(out) if s != "index.html"]
    assert len(ss) >= 15
    for s in ss:
        for lang_parts in ((), ("en",)):
            h = read(out, *lang_parts, "q", s, "index.html")
            assert 'data-page="q"' in h and "noindex" not in h and '<link rel="canonical"' in h
            q = faq(h)
            assert q["name"].endswith("؟" if not lang_parts else "?") and q["acceptedAnswer"]["text"]
            assert re.search(r"\d", q["acceptedAnswer"]["text"])                 # every answer carries a number or a date
            assert re.search(r'<h1 class="pt">[^<]+[؟?]</h1>', h)
            assert len(h.encode()) <= 150_000
    sm = read(out, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/q/</loc>" in sm and "<loc>https://cinema.elyoxe.com/q/fazaa-at-star/</loc>" in sm
    hub = read(out, "q", "index.html")
    assert all(f'href="/q/{s}/"' in hub for s in ss)


def test_imax_price_in_dubai(out):
    got = expected_min("dubai", "IMAX")
    assert got is not None
    day, want = got
    h = read(out, "q", "imax-ticket-price-dubai", "index.html")
    assert "كم سعر تذكرة IMAX في دبي؟" in h
    a = faq(h)["acceptedAnswer"]["text"]
    assert f"{want:.2f}" in a and build.human_date(day, "ar") in a
    assert 'href="/prices/"' in h and 'href="/halls/"' in h and re.search(r'href="/dubai/[a-z0-9-]+/"', h)
    assert 'data-aed="' in h                                                 # repriced after the visitor's card
    en = read(out, "en", "q", "imax-ticket-price-dubai", "index.html")
    assert "How much is an IMAX ticket in Dubai?" in en and build.human_date(day, "en") in faq(en)["acceptedAnswer"]["text"]


def test_no_question_the_data_cannot_answer(out):
    ss = slugs(out)
    assert "screenx-ticket-price-dubai" not in ss and "where-screenx" not in ss     # no ScreenX in the fixture
    assert "esaad-at-star" not in ss                                               # third-party rule: never published
    assert "imax-ticket-price-fujairah" not in ss


def test_card_questions(out):
    yes = read(out, "q", "fazaa-at-star", "index.html")
    assert "هل فزعة تشتغل في ستار؟" in yes
    a = faq(yes)["acceptedAnswer"]["text"]
    assert a.startswith("إيه") and "20%" in a and "25 سبتمبر 2026" in a
    assert 'href="/cards/fazaa/"' in yes and 'href="https://www.starcinemas.ae/offers"' in yes
    no = faq(read(out, "q", "fazaa-at-vox", "index.html"))["acceptedAnswer"]["text"]
    assert "ما لقينا" in no and "25 سبتمبر 2026" in no
    gone = faq(read(out, "q", "fazaa-at-cinemacity", "index.html"))["acceptedAnswer"]["text"]
    assert "انتهى" in gone and "1 سبتمبر 2026" in gone
    assert faq(read(out, "en", "q", "fazaa-at-star", "index.html"))["acceptedAnswer"]["text"].startswith("Yes")


def test_cheapest_tonight_and_where(out):
    h = read(out, "q", "cheapest-cinema-al-ain-tonight", "index.html")
    assert "أرخص سينما في العين الليلة؟" in h
    a = faq(h)["acceptedAnswer"]["text"]
    assert "25 سبتمبر 2026" in a and re.search(r"\d+\.\d\d", a)
    w = read(out, "q", "where-4dx", "index.html")
    assert "وين أقرب سينما فيها 4DX؟" in w
    rows = re.findall(r'<div class="row cin" data-cin="([^"]+)"', w)
    assert rows and all(r.startswith("vox-") for r in rows)
    assert "data-near" in w and 'data-lat="' in w
