"""W2-P6 (legend MASTER-PLAN §2.4, §2.5, §5.3): the city and cinema pages. The cinema head (Arabic address, three
ways there, «المول يسكّر»), «الليلة هنا» sorted by the next start with the five rows of controls gone and one door to
the filter sheet, one halls table in words, the questions as text (no FAQPage), the city hero (clock, pulse, the
hour's light), «السينمات» and «كل الأوقات», and the early-morning fix: a cinema page keeps tomorrow up to ~140 KB.
The words have twins in src/js/places-live.js, run here in node."""
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

import build  # noqa: E402
from pages._core import places  # noqa: E402
from site_kit import parse_iso  # noqa: E402

FIX = ROOT / "fixtures"
DATA, DISC = FIX / "sample_latest.json", str(FIX / "sample_discounts.yaml")
ACR = {"IMAX", "MAX", "4DX", "MX4D", "VIP", "XXL", "PLF", "2D", "3D", "4K"}
NODE = shutil.which("node")


def read(out, *parts):
    return Path(out, *parts).read_text(encoding="utf-8")


def main_of(h):
    return h[h.index("<main"):h.index("</main>")]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    o = tmp_path_factory.mktemp("w2p6")
    build.build(str(DATA), DISC, str(o), noindex=False)
    return o


def lds(h):
    return [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)


# ---------------------------------------------------------------- the cinema page
def test_the_cinema_head_names_the_address_in_arabic_the_three_ways_and_the_mall(site):
    h = main_of(read(site, "dubai", "reel-dubai-mall", "index.html"))
    head = h[:h.index("</section>")]
    assert "دبي مول، وسط مدينة دبي، دبي" in head                       # cinemas.yaml address_ar
    assert "Downtown Dubai" not in head
    for name, host in (("Google Maps", "google.com/maps/dir"), ("Waze", "waze.com/ul"), ("Uber", "m.uber.com/ul/?action=setPickup")):
        assert re.search(r'<a class="go-b" href="[^"]*' + re.escape(host) + r'[^"]*"[^>]*>' + name + "</a>", head), name
    assert re.search(r'dropoff\[latitude\]=2\d\.\d+&amp;dropoff\[longitude\]=5\d\.\d+&amp;dropoff\[nickname\]=Reel%20at%20', head)
    assert "المول يسكّر 00:00" in head or "المول يسكّر 23:00" in head   # malls.yaml, the build's weekday
    # «سينمتي» is W3-P1's: held, never a control that does nothing
    assert re.search(r'<button type="button" class="fav" data-fav="reel-dubai-mall" aria-pressed="false" hidden>', head)
    en = main_of(read(site, "en", "dubai", "reel-dubai-mall", "index.html"))
    assert "<p class=\"ch-a\">Downtown Dubai</p>" in en[:en.index("</section>")]   # the reader's own, in English


def test_every_cinema_in_the_yaml_has_an_arabic_address():
    y = yaml.safe_load((ROOT / "cinemas.yaml").read_text(encoding="utf-8"))["cinemas"]
    missing = [cid for cid, c in y.items() if not c.get("address_ar")]
    assert not missing, missing
    assert all(re.search(r"[\u0600-\u06FF]", c["address_ar"]) and not re.search(r"[٠-٩]", c["address_ar"]) for c in y.values())
    assert "FLAGGED FOR THE OWNER'S REVIEW" in (ROOT / "cinemas.yaml").read_text(encoding="utf-8")


def test_the_five_control_rows_are_gone_and_one_door_opens_the_filter_sheet(site):
    page = read(site, "dubai", "reel-dubai-mall", "index.html")
    h = main_of(page)
    for gone in ('class="ctl', "data-ends-before", 'data-who="solo"', 'class="chips filters', "بروحي"):
        assert gone not in h, gone
    assert h.count('data-sheet-open="sheet-filter"') == 1
    assert 'id="sheet-filter"' in page and "data-fcount" in h


def test_tonight_here_is_sorted_by_the_next_start_and_tomorrow_folds(site):
    h = main_of(read(site, "dubai", "reel-dubai-mall", "index.html"))
    assert "الليلة هنا" in h
    today = re.search(r'<section class="day" data-d="([\d-]+)"><div class="cfilms">(.*?)</div></section>', h, re.S)
    assert today and today.group(1) == "2026-09-25"
    firsts = []
    for blk in re.findall(r'<div class="cf" .*?(?=<div class="cf" |$)', today.group(2), re.S):
        ts = [t for t in re.findall(r'data-start="(\d\d:\d\d)"', blk) if t >= "18:00"]
        firsts.append(min(ts) if ts else "99:99")
    assert firsts and firsts == sorted(firsts)
    assert re.search(r'<details class="day later" data-d="2026-09-26"><summary><h2>بكرة <small>', h)


def test_hall_and_seat_labels_are_words_never_capitals(site):
    for parts in (("dubai", "reel-dubai-mall"), ("abu-dhabi", "vox-yas-mall"), ("al-ain", "star-bawadi-mall"), ("dubai",)):
        h = main_of(read(site, *parts, "index.html"))
        labels = re.findall(r'<span class="hn">(.*?)</span>', h) + re.findall(r'<small class="hn">(.*?)</small>', h)
        labels += re.findall(r'<tr class="hh"><th[^>]*>(.*?)</th>', h) + re.findall(r'<th scope="row">(.*?)</th>', h)
        text = [re.sub(r"<[^>]+>", "", x) for x in labels]
        caps = [t for t in text for w in re.findall(r"[A-Za-z0-9]+", t) if re.search(r"[A-Z]{2}", w) and w == w.upper() and w not in ACR]
        assert not caps, (parts, caps[:5])


def test_the_halls_are_one_table_with_gold_on_the_one_cheapest(site):
    h = main_of(read(site, "dubai", "reel-dubai-mall", "index.html"))
    assert h.count('<table class="prices hp">') == 1
    sec = h[h.index('<section class="halls-s">'):]
    sec = sec[:sec.index("</section>")]
    assert sec.count("<tbody>") >= 2 and sec.count("<table") == 1
    assert "p lo" not in sec   # the build writes no gold there: prices.js lows() lights the one cheapest per table


def test_questions_are_plain_text_and_no_page_has_faqpage(site):
    for parts in (("dubai", "reel-dubai-mall"), ("dubai",), ("en", "dubai"), ("en", "dubai", "reel-dubai-mall")):
        page = read(site, *parts, "index.html")
        assert "FAQPage" not in page
        assert 'class="faq"' in page
    h = read(site, "dubai", "reel-dubai-mall", "index.html")
    assert "شو الأفلام اليوم في ريل دبي مول؟" in h and "كم سعر التذكرة في ريل دبي مول؟" in h
    assert "هذي الأسعار قبل خصم البطاقة." in h
    assert "وش" not in main_of(h)


def test_screening_events_carry_the_list_price_and_validate(site):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    by = {}
    for s in data["shows"]:
        ps = [p["aed"] for p in s.get("prices") or [] if p.get("aed")]
        if ps: by.setdefault((s["cinema"], s["date"], s["time"]), set()).add(min(ps))
    n = 0
    for city in ("dubai", "abu-dhabi", "al-ain"):
        for d in Path(site, city).iterdir():
            if not (d / "index.html").exists(): continue
            for g in lds((d / "index.html").read_text(encoding="utf-8")):
                assert g["@context"] == "https://schema.org"
                for node in walk(g):
                    assert node.get("@type") != "FAQPage"
                    if node.get("@type") != "ScreeningEvent": continue
                    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:00\+04:00", node["startDate"])
                    assert node["location"]["@type"] == "MovieTheater" and node["location"]["name"] and node["location"]["url"].startswith("https://")
                    assert node["workPresented"]["@type"] == "Movie" and node["name"]
                    if "offers" in node:
                        o = node["offers"]
                        assert o["@type"] == "Offer" and o["priceCurrency"] == "AED" and o["availability"].startswith("https://schema.org/")
                        cid = d.name
                        key = (cid, node["startDate"][:10], node["startDate"][11:16])
                        assert float(o["price"]) in {float(x) for x in by[key]}, (key, o["price"])   # the list price, never after a card
                        n += 1
    assert n > 20


def test_film_double_is_not_registered_and_the_film_page_has_no_double_feature(site):
    from pages import venue
    p = venue.register(None)
    assert "film.double" not in p.slots
    film = next(Path(site, "film").iterdir())
    assert "فيلمين ورا بعض" not in read(film, "index.html")


def test_the_mall_line_moved_to_the_head_and_is_never_gold():
    css = (ROOT / "src" / "css" / "venue.css").read_text(encoding="utf-8")
    assert not re.search(r"\.mall-late\{[^}]*--gold", css)


# ---------------------------------------------------------------- the city page
def test_the_city_hero_clock_pulse_light_and_the_held_pick(site):
    page = read(site, "dubai", "index.html")
    h = main_of(page)
    hero = h[:h.index("</section>")]
    assert "<h1 class=\"pt\">دبي الليلة</h1>" in hero                          # the fixture is built at 18:00
    assert re.search(r'<p class="cclock" data-cclock dir="ltr"><span class="vh">18:00</span>', hero)
    assert hero.count('class="d"') == 4 and hero.count('class="c"') == 1
    assert re.search(r'<p class="pulse" data-pulse aria-live="polite">\d+ (عرض باقي|عروض باقية) الليلة', hero)
    assert re.search(r'<button type="button" class="btn ghost pl-pick" data-pick="dubai" data-hold hidden>اختار لي في دبي</button>', hero)
    assert re.search(r'<body[^>]* style="--lit:1"', page)


def test_the_lit_follows_the_hour():
    assert [places.lit(h) for h in (6, 12, 20, 21, 22, 23, 0, 1, 5)] == [1, 1, 1, .8, .7, .6, .45, .45, .45]


def test_the_city_cinemas_say_next_and_left_and_cap_at_eight(site):
    h = main_of(read(site, "dubai", "index.html"))
    sec = h[h.index('<section class="wrap cins"'):]
    sec = sec[:sec.index("</section>")]
    rows = re.findall(r'<div class="row cin" data-cin="([^"]+)"', sec)
    assert rows
    assert re.search(r'<span data-cnext>(التالي \d\d:\d\d، .+?|ما في عروض باقية اليوم)</span>', sec)
    assert 'data-cap="8"' in sec and 'data-lo' in sec
    assert ('data-cap-open' in sec) == (len(rows) > 8)


def test_every_time_is_a_film_line_in_the_timetable_and_past_times_hidden(site):
    h = main_of(read(site, "dubai", "index.html"))
    assert "كل الأوقات" in h
    lines = re.findall(r'<details class="srow" data-fid="([^"]+)"><summary class="sf"><bdi class="t"[^>]*>[^<]+</bdi><span class="nx num" data-nx>(\d\d:\d\d)?</span>', h)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    cids = {c for c, x in data["cinemas"].items() if x.get("city") == "dubai"}
    fids = {s["film"] for s in data["shows"] if s["cinema"] in cids and s["date"] == "2026-09-25"}
    assert {f for f, _ in lines} == fids
    # SEO: every show still to come today is a link in the markup (the richest mode on the sample), past ones never
    up = [s for s in data["shows"] if s["cinema"] in cids and s["date"] == "2026-09-25" and s["time"] >= "18:00"]
    assert h.count("data-show=") >= len(up)
    css = (ROOT / "src" / "css" / "places-page.css").read_text(encoding="utf-8")
    assert ".js .srow .tm.past:not(.on){display:none}" in css and ".js .cf:not(.all-t) .tm.past:not(.on){display:none}" in css


def test_the_grid_shows_three_rows_first(site):
    h = main_of(read(site, "dubai", "index.html"))
    assert '<div class="pl-cap" data-cap="9">' in h
    css = (ROOT / "src" / "css" / "places-page.css").read_text(encoding="utf-8")
    assert "nth-child(n+10 of .film:not(.x))" in css and "nth-child(n+9 of .row:not(.x))" in css
    assert places.GRID_CAP == 9 and places.CIN_CAP == 8


def test_the_places_assets_are_page_scoped(site):
    city, cin, home = read(site, "dubai", "index.html"), read(site, "dubai", "reel-dubai-mall", "index.html"), read(site, "index.html")
    assert re.search(r'href="/assets/page-city\.[0-9a-f]{10}\.css"', city) and re.search(r'href="/assets/page-cinema\.[0-9a-f]{10}\.css"', cin)
    assert "page-city" not in home and "places-live" not in home
    assert re.search(r'"places-live": "/assets/places-live\.[0-9a-f]{10}\.js"', city) and '"places-live"' in cin
    shared = (Path(site) / "assets" / "cinema.css").read_text(encoding="utf-8")
    assert ".cclock" not in shared and ".go-b" not in shared


# ---------------------------------------------------------------- the early-morning golden (r0-main-logic §3.3)
def _busy(data, cid, n):
    """`data` with `n` more priced shows at `cid` tomorrow, each with its own booking URL."""
    d = copy.deepcopy(data)
    base = next(s for s in d["shows"] if s["cinema"] == cid and s.get("prices"))
    tmr = (parse_iso(d["generated"]).date().toordinal() + 1)
    import datetime as dt
    day = dt.date.fromordinal(tmr).isoformat()
    for i in range(n):
        s = dict(base, date=day, time=f"{10 + i // 12:02d}:{(i % 12) * 5:02d}", book=f"https://example.com/book/{cid}/{i:05d}?session={i:08d}")
        d["shows"].append(s)
    return d, day


def test_a_cinema_page_keeps_tomorrow_up_to_140_kb(tmp_path):
    """The Fold's 04:50 run: a whole day ahead made three cinema pages drop tomorrow at 94 KB of 150. A page whose full
    schedule fits under ~140 KB keeps it (Task 4's ruling, carried to places); the hard 150 KB stays."""
    data, day = _busy(json.loads(DATA.read_text(encoding="utf-8")), "reel-dubai-mall", 150)
    p = tmp_path / "d.json"; p.write_text(json.dumps(data), encoding="utf-8")
    build.build(str(p), DISC, str(tmp_path / "o"), noindex=False)
    page = read(tmp_path / "o", "dubai", "reel-dubai-mall", "index.html")
    n = len(page.encode())
    assert f'<details class="day later" data-d="{day}">' in page, n            # tomorrow kept
    assert n <= 150_000
    assert places.PLACE_TARGET == 140_000


# ---------------------------------------------------------------- the words, and their twins in node
@pytest.mark.parametrize("n,ar,en", [(1, "عرض واحد باقي", "1 left"), (2, "عرضين باقيين", "2 left"), (5, "5 عروض باقية", "5 left"),
                                     (18, "18 عرض باقي", "18 left")])
def test_left_words(n, ar, en):
    assert places.left_words(n, "ar") == ar and places.left_words(n, "en") == en


def test_pulse_and_past_words():
    assert places.pulse_words(214, 38, "الليلة", "ar") == "214 عرض باقي الليلة، 38 تبدأ خلال ساعة"
    assert places.pulse_words(7, 1, "اليوم", "ar") == "7 عروض باقية اليوم، واحد منها يبدأ خلال ساعة"
    assert places.pulse_words(2, 0, "tonight", "en") == "2 shows left tonight"
    assert [places.past_words(n, "ar") for n in (1, 2, 3, 12)] == ["عرض واحد فات", "عرضين فاتوا", "+3 عروض فاتت", "+12 عرض فات"]
    assert places.say_name("ريل — دبي مول", "ar") == "ريل دبي مول" and places.say_name("Reel — The Dubai Mall", "en") == "Reel at The Dubai Mall"


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_the_js_twins_say_what_the_python_says(tmp_path):
    src = (ROOT / "src" / "js" / "places-live.js").read_text(encoding="utf-8")
    js = ("var PL = (function (K) {\n" + src + "\nreturn {plLeft: plLeft, plPast: plPast, plPulse: plPulse, plNext: plNext, plLit: plLit, plWhen: plWhen, plHM: plHM};\n})(null);\n"
          "var out = [];\n"
          "[1,2,3,5,10,11,18,214].forEach(function (n) { out.push(PL.plLeft(n, true), PL.plLeft(n, false), PL.plPast(n, true), PL.plPast(n, false)); });\n"
          "out.push(PL.plPulse(214, 38, 'الليلة', true), PL.plPulse(7, 1, 'اليوم', true), PL.plPulse(3, 0, 'الليلة', true), PL.plPulse(2, 0, 'tonight', false), PL.plPulse(1, 1, 'today', false));\n"
          "out.push(PL.plNext('21:30', 18, true), PL.plNext('', 0, true), PL.plNext('21:30', 2, false));\n"
          "[0,1,5,6,12,20,21,22,23].forEach(function (h) { out.push(PL.plLit(h)); });\n"
          "out.push(PL.plWhen(16, true), PL.plWhen(17, true), PL.plHM(Date.UTC(2026, 8, 26, 17, 5)));\n"
          "process.stdout.write(JSON.stringify(out));\n")
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    want = []
    for n in (1, 2, 3, 5, 10, 11, 18, 214):
        want += [places.left_words(n, "ar"), places.left_words(n, "en"), places.past_words(n, "ar"), places.past_words(n, "en")]
    want += [places.pulse_words(214, 38, "الليلة", "ar"), places.pulse_words(7, 1, "اليوم", "ar"), places.pulse_words(3, 0, "الليلة", "ar"),
             places.pulse_words(2, 0, "tonight", "en"), places.pulse_words(1, 1, "today", "en")]
    want += ["التالي 21:30، 18 عرض باقي", "ما في عروض باقية اليوم", "next 21:30, 2 left"]
    want += [places.lit(h) for h in (0, 1, 5, 6, 12, 20, 21, 22, 23)]
    want += ["اليوم", "الليلة", "21:05"]
    assert got == want
