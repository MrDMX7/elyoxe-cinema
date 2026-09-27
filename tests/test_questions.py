"""pages/questions.py: /q/<slug>/ — the question set comes from a stable basis (cities × hall classes that exist,
cards with an announced official offer × their chains, cities, formats), so no URL vanishes between runs. A
question the day's data answers (with a floor: ≥ 3 cinemas or ≥ 10 shows behind a number) is an indexable page
with the number, its date, FAQPage JSON-LD and evidence links; one it does not answer is a noindex page saying
«ما عندنا رقم موثوق اليوم», kept out of the sitemap and the hub. Arabic and English."""
import json, os, re, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
MINE = ("core", "insights", "questions")   # the other phase-2 modules are other tasks' (the full suite builds them all)
NONE = "ما عندنا رقم موثوق اليوم"


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def ld(html):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))["@graph"]


def faq(html):
    return next(g for g in ld(html) if g.get("@type") == "FAQPage")["mainEntity"][0]


def build_from(tmp_path_factory, name, data=None):
    o = str(tmp_path_factory.mktemp(name))
    path = DATA
    if data is not None:
        path = o + "-data.json"
        json.dump(data, open(path, "w", encoding="utf-8"))
    build.build(path, DISC, o, noindex=False, modules=build.discover(only=MINE))
    return o


def fixture():
    return json.load(open(DATA, encoding="utf-8"))


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return build_from(tmp_path_factory, "q")


@pytest.fixture(scope="module")
def unpriced(tmp_path_factory):
    """The same schedules with every live price gone (all chains on the fallback table for a run)."""
    d = fixture()
    for s in d["shows"]: s["prices"] = None
    return build_from(tmp_path_factory, "q0", d)


def slugs(out):
    return sorted(x for x in os.listdir(os.path.join(out, "q")) if x != "index.html")


def answered(out, s, *lang):
    return "noindex" not in read(out, *lang, "q", s, "index.html")


def expected_min(city, key):
    """(date, cheapest live seat, shows) in `city` for hall key `key`, on the date with the most priced shows."""
    d = fixture()
    h = build.Halls(os.path.join(ROOT, "halls.yaml"))
    by = {}
    for s in d["shows"]:
        c = d["cinemas"][s["cinema"]]
        if c["city"] != city or d["films"][s["film"]].get("status") == "archived": continue
        if h.key(c["chain"], s.get("hall") or "OTHER", s.get("hall_label") or "") != key: continue
        ps = [p["aed"] for p in s.get("prices") or [] if p.get("aed")]
        if ps: by.setdefault(s["date"], []).append(min(ps))
    day = max(sorted(by), key=lambda x: len(by[x]))
    return day, min(by[day]), len(by[day])


def test_answered_pages_are_whole_and_indexed(out):
    ss = [s for s in slugs(out) if answered(out, s)]
    assert len(ss) >= 12
    sm, hub = read(out, "sitemap.xml"), read(out, "q", "index.html")
    for s in ss:
        for lang in ((), ("en",)):
            h = read(out, *lang, "q", s, "index.html")
            assert 'data-page="q"' in h and '<link rel="canonical"' in h and NONE not in h
            q = faq(h)
            assert q["name"].endswith("?" if lang else "؟") and re.search(r"\d", q["acceptedAnswer"]["text"])
            assert re.search(r'<h1 class="pt">[^<]+[؟?]</h1>', h) and len(h.encode()) <= 150_000
        assert f"<loc>https://cinema.elyoxe.com/q/{s}/</loc>" in sm and f'href="/q/{s}/"' in hub
    assert "<loc>https://cinema.elyoxe.com/q/</loc>" in sm


def test_unanswered_pages_stay_noindex_out_of_sitemap_and_hub(out):
    thin = [s for s in slugs(out) if not answered(out, s)]
    assert "imax-ticket-price-dubai" in thin               # 1 cinema, 8 shows: under the floor
    sm, hub = read(out, "sitemap.xml"), read(out, "q", "index.html")
    for s in thin:
        for lang in ((), ("en",)):
            h = read(out, *lang, "q", s, "index.html")
            assert '<meta name="robots" content="noindex' in h and "FAQPage" not in h
            assert (NONE if not lang else "no reliable number today") in h
            assert re.search(r'<a href="/(en/)?(prices|halls|cards|dubai|[a-z-]+)/', h)      # where to look instead
        assert f"/q/{s}/</loc>" not in sm and f'href="/q/{s}/"' not in hub


def test_url_set_does_not_depend_on_the_days_prices(out, unpriced):
    assert slugs(out) == slugs(unpriced)
    assert not any(answered(unpriced, s) for s in slugs(unpriced) if "price" in s or "tonight" in s)


def test_price_answer_above_the_floor(out):
    day, want, n = expected_min("dubai", "Standard")
    assert n >= 10
    h = read(out, "q", "cinema-ticket-price-dubai", "index.html")
    assert "كم سعر تذكرة السينما العادية في دبي؟" in h
    a = faq(h)["acceptedAnswer"]["text"]
    assert f"{want:.2f}" in a and build.human_date(day, "ar") in a
    assert 'href="/prices/"' in h and re.search(r'href="/dubai/[a-z0-9-]+/"', h) and 'data-aed="' in h
    en = read(out, "en", "q", "cinema-ticket-price-dubai", "index.html")
    assert "How much is a cinema ticket in Dubai?" in en and build.human_date(day, "en") in faq(en)["acceptedAnswer"]["text"]


def test_the_basis_is_what_exists(out):
    ss = slugs(out)
    assert "imax-ticket-price-fujairah" not in ss            # no chain in Fujairah has an IMAX hall
    assert "esaad-at-star" not in ss                         # third-party rule: never published
    assert "homat-at-star" not in ss                         # a card with no announced offer anywhere
    assert "where-screenx" in ss and not answered(out, "where-screenx")   # Reel has ScreenX; none showing today


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


def test_where_lists_todays_cinemas(out):
    w = read(out, "q", "where-4dx", "index.html")
    assert "وين أقرب سينما فيها 4DX؟" in w
    rows = re.findall(r'<div class="row cin" data-cin="([^"]+)"', w)
    assert rows and all(r.startswith("vox-") for r in rows)
    assert "data-near" in w and 'data-lat="' in w and "25 سبتمبر 2026" in faq(w)["acceptedAnswer"]["text"]


def test_format_names_read_whole_in_the_answer(out):
    """«4DX» in an Arabic answer read «DX4»: the number isolate took the 4 alone (MASTER-PLAN §4.1 #19)."""
    ans = re.search(r'<p class="ans">(.*?)</p>', read(out, "q", "where-4dx", "index.html"), re.S).group(1)
    assert '<bdi dir="ltr">4DX</bdi>' in ans and ">4</span>DX" not in ans
    from pages.questions import Questions
    assert Questions.digits("MX4D بـ55.00 و2D و20%") == ('<bdi dir="ltr">MX4D</bdi> بـ<span class="num" dir="ltr">55.00</span> '
                                                        'و<bdi dir="ltr">2D</bdi> و<span class="num" dir="ltr">20%</span>')


def test_tonight_counts_only_shows_still_ahead_and_after_midnight(tmp_path_factory):
    d = fixture()
    d["generated"] = "2026-09-25T22:10:00+04:00"
    cid = next(c for c, v in d["cinemas"].items() if v["city"] == "al-ain")
    film = next(f for f, v in d["films"].items() if v.get("status") != "archived")
    mk = lambda date, t, aed: {"cinema": cid, "film": film, "date": date, "time": t, "hall": "Standard", "hall_label": "",
                               "prices": [{"seat": "A", "aed": aed}]}
    d["shows"] = [s for s in d["shows"] if d["cinemas"][s["cinema"]]["city"] != "al-ain"]
    d["shows"] += [mk("2026-09-25", "20:00", 5.0)]                              # already started: not tonight
    d["shows"] += [mk("2026-09-25", f"23:{m:02d}", 60.0) for m in range(0, 50, 5)]
    d["shows"] += [mk("2026-09-26", "00:30", 9.99), mk("2026-09-26", "04:00", 1.0)]   # after midnight; next morning
    o = build_from(tmp_path_factory, "qt", d)
    a = faq(read(o, "q", "cheapest-cinema-al-ain-tonight", "index.html"))["acceptedAnswer"]["text"]
    assert "9.99" in a and "00:30" in a and "5.00" not in a and "1.00" not in a
