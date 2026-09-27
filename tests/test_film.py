"""The film page (UI redesign Task 4): the hero (frame or poster fallback, title, English title and year, verdict,
facts, الإعلان/شارك/قارن), the sticky day bar with its «⋯» sheet (prayer, «مع منو رايح؟», «لازم يخلص قبل»), the
schedule by city (the visitor's open, the rest folded) with the ticket beside it («اختر وقت» when nothing is chosen)
and the phone's dock, the tabs (each feature's section in its own, anchor links with no script), the archived
page, what left the page («أنا في … وعندي»), the client's contract, and the 150 KB budget for a film with many shows."""
import gzip
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
BUDGET = 150_000
FID = "heart-of-the-beast"


def read(out, *parts):
    return open(os.path.join(out, *parts, "index.html"), encoding="utf-8").read()


def main_of(h):
    return h[h.index("<main"):h.index("</main>")]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("film") / "out")
    build.build(DATA, DISC, o, noindex=False)
    return o


def test_hero_title_verdict_facts_and_actions(out):
    h = read(out, "film", FID)
    hero = h[h.index('<section class="fhero'):h.index('<section class="fsched"')]
    assert '<h1 class="ft">قلب الوحش</h1>' in hero
    assert '<p class="fte"><bdi lang="en" dir="ltr">Heart of the Beast</bdi></p>' in hero       # the fixture has no year
    assert re.search(r'<p class="fv verdict v-yes" id="fv" data-fv><b class="word">يستاهل\.</b> <span class="say">', hero)
    assert 'data-fv-more aria-controls="fv" aria-expanded="false" hidden>المزيد</button>' in hero
    ff = re.search(r'<p class="ff">(.*?)</p>', hero).group(1)
    assert '<span class="basis rates">' in ff and '<span class="num">118</span> دقيقة' in ff and "PG15" in ff and "·" not in ff
    cta = re.search(r'<p class="cta">(.*?)</p>', hero).group(1)
    labels = re.findall(r'</svg>([^<]+)</a>|js-only" href="#compare"[^>]*>([^<]+)</a>', cta)
    assert [a or b for a, b in labels] == ["الإعلان", "شارك", "قارن"]
    assert 'data-trailer="k8Qm3LzT0aE"' in cta and "data-share-url=" in cta and 'data-tab-go="compare"' in cta
    # the poster card (desktop) with the velvet glow, the view transition's «poster»
    assert '<div class="fposter"><span class="pst hero img"' in hero
    en = read(out, "en", "film", FID)
    assert '<h1 class="ft">Heart of the Beast</h1>' in en and '<p class="fte">' not in en        # no English title twice
    assert re.search(r'</svg>Trailer</a>.*</svg>Share</a>.*>Compare</a>', en)


def test_hero_frame_is_the_lcp_and_poster_fallback_is_one_download(tmp_path):
    d = json.load(open(DATA, encoding="utf-8"))
    d["films"][FID]["backdrop"] = {"w1280": "/posters/bd-heart-0123456789-1280.webp", "w640": "/posters/bd-heart-0123456789-640.webp", "w": 1280, "h": 720}
    p = tmp_path / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp_path / "o")
    build.build(str(p), DISC, o, noindex=False, modules=build.discover(only=("core",)))
    h = read(o, "film", FID)
    assert '<section class="fhero fr">' in h
    assert re.search(r'<link rel="preload" as="image" href="/posters/bd-heart-0123456789-1280\.webp" imagesrcset="[^"]*640w[^"]*1280w" '
                     r'imagesizes="\(min-width:1024px\) 100vw, 320px" fetchpriority="high">', h)
    assert 'class="fr"' in h and h.count('fetchpriority="high"') == 2        # the preload and the frame
    assert re.search(r'<span class="pst hero img"[^>]*>.*?loading="lazy"', h)   # the card: desktop only, never fetched on a phone
    # no frame: the poster blurred (the preloaded 342w file), and the card's `sizes` resolves to that same file on a phone
    h2 = read(o, "film", "sacrifice")
    assert '<div class="bd pf"' in h2 and 'class="pb"' in h2
    pb = re.search(r'<img src="([^"]+)" class="pb"', h2).group(1)
    card = re.search(r'<span class="pst hero img"[^>]*>.*?<img src="([^"]+)"([^>]*)>', h2).group(0)
    assert f'src="{pb}"' in card and 'srcset=' not in card or 'sizes="(min-width:1024px) 240px, 1px"' in card


def test_day_bar_and_its_options_sheet(out):
    h = read(out, "film", FID)
    bar = re.search(r'<div class="dbar js-only">(.*?)</div></div>', h).group(1)
    days = re.findall(r'<button type="button" class="dy" data-day="([\d-]+)" data-wd="[^"]+" aria-pressed="(true|false)"><b>([^<]+)</b><span class="num">([^<]+)</span>', bar)
    assert [(x[0], x[1], x[2]) for x in days] == [("2026-09-25", "true", "اليوم"), ("2026-09-26", "false", "بكرة")]
    assert days[0][3] == "الجمعة 25"
    assert 'data-sheet-open="sheet-fopts"' in bar and 'data-fcount hidden' in bar
    sheet = h[h.index('id="sheet-fopts"'):]
    sheet = sheet[:sheet.index('</div></div></div>') + 1]
    assert 'role="dialog" aria-modal="true"' in h[h.index('id="sheet-fopts"') - 40:h.index('id="sheet-fopts"') + 80]
    assert len(re.findall(r'data-who="', sheet)) == 4 and len(re.findall(r'data-before="', sheet)) == 5
    assert "data-prayer" in sheet and "data-hide-clash" in sheet and "data-reset" in sheet
    # the old control rows are gone from the page body; the sentence «أنا في … وعندي» too
    m = main_of(h)
    assert "data-me" not in m and 'class="ctl' not in m and "<select" not in m and "أنا في" not in h
    assert h.count('id="sheet-fopts"') == 1


def test_schedule_by_city_ticket_column_and_dock(out):
    h = read(out, "film", FID)
    m = main_of(h)
    sec = m[m.index('<section class="fsched"'):]
    assert '<h2 class="vh" id="times-h">المواعيد والأسعار</h2>' in sec
    cities = re.findall(r'<details class="fcity" data-city="([a-z-]+)"( open)?><summary><h2>[^<]+</h2><span class="fc-n">([^<]+)</span></summary>', sec)
    assert cities and [c for c, o, _ in cities if o] == ["dubai"]          # no script: Dubai open (the default city)
    assert re.match(r"^(سينما وحدة|سينمتين|\d+ سينمات|\d+ سينما)$", dict((c, n) for c, _, n in cities)["dubai"])
    # every time a booking link with its show id; the halls and their «من» prices for a visitor with no script
    assert re.search(r'<div class="hl" data-hall="[^"]+" data-hk="[^"]+"><p class="hl-n"><span class="hn">', sec)
    assert 'class="tm' in sec and "data-show=" in sec
    # the ticket's column: «اختر وقت» (hidden until the script says) and the server's ticket
    col = sec[sec.index('<div class="tkcol">'):]
    assert col.startswith('<div class="tkcol"><div class="tk-empty" data-tk-empty hidden><p class="k">اختر وقت</p>')
    assert '<aside class="ticket" id="ticket" data-ticket' in col
    # the dock: hidden, filled by film.js
    assert re.search(r'<div class="dock" data-dock role="region" aria-label="الوقت المختار" hidden>.*data-dk-p.*data-dk-s.*'
                     r'<button type="button" class="btn dk-b" data-dk-open aria-haspopup="dialog">التفاصيل والحجز</button>', m)
    assert '<p class="nc" data-nc hidden></p>' in m and "data-empty hidden" in m


def test_tabs_are_links_to_sections_in_order(out):
    h = read(out, "film", FID)
    m = main_of(h)
    tabs = re.search(r'<div class="wrap tabsx" data-tabs aria-label="عن الفيلم وأكثر">(.*?)</div>', m).group(1)
    got = re.findall(r'<a href="#(\w+)" data-tab="\1"( class="js-only")?>([^<]+)</a>', tabs)
    order = ["about", "cast", "similar", "double", "compare"]
    keys = [k for k, _, _ in got]
    assert keys == [k for k in order if k in keys] and keys[0] == "about" and "compare" in keys
    assert dict((k, j) for k, j, _ in got)["compare"] == ' class="js-only"'    # script-drawn: so is its tab
    assert [t for _, _, t in got][:2] == ["عن الفيلم", "شي يشبه"] or "الطاقم" in [t for _, _, t in got]
    secs = re.findall(r'<section class="tpn" id="(\w+)">', m)
    assert secs == keys                                                        # no script: the sections, in the tabs' order
    about = m[m.index('<section class="tpn" id="about">'):]
    about = about[:about.index("</section>")]
    assert '<h2 class="tp-h">عن الفيلم</h2>' in about and '<p class="syn"' in about and '<dl class="facts">' in about
    assert "<dt>في الإمارات</dt>" in about and '<nav class="crumbs"' in about
    # each feature's section went to its own tab (the film.* slots)
    assert '<section class="sim">' in m[m.index('id="similar"'):] and 'data-cmp="heart-of-the-beast"' in m[m.index('id="compare"'):]
    if "double" in keys: assert '<details class="dfeat" open>' in m[m.index('id="double"'):]


def test_the_hash_names_a_real_section_and_no_ids_repeat(out):
    for parts in (("film", FID), ("en", "film", FID), ("film", "weapons"), ("film", "crawlers")):
        h = read(out, *parts)
        ids = re.findall(r'\sid="([^"]+)"', h)
        assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
        for k in re.findall(r'data-tab="(\w+)"', h):
            assert f'id="{k}"' in h


def test_archived_film_in_the_new_hero(out):
    h = read(out, "film", "weapons")
    hero = h[h.index('<section class="fhero'):]
    hero = hero[:hero.index('<div class="ftabs">')]
    assert '<div class="archived"><p class="arch-s">عُرض في سينمات الإمارات من 7 أغسطس إلى 17 سبتمبر 2026</p>' in hero
    assert 'class="btn light" href="/"' in hero and "المعروض الحين" in hero
    assert '<section class="fsched"' not in h and 'class="dbar' not in h and "data-dock" not in h
    tabs = re.findall(r'data-tab="(\w+)"', h)
    assert tabs[0] == "about" and "similar" in tabs and "compare" not in tabs and "double" not in tabs
    assert 'class="tonight wrap similar"' in h[h.index('id="similar"'):]


def test_the_client_has_the_film_modules_and_one_sheet_opener():
    """tabs.js and film.js are in the bundle; ticket.js opens its sheet with tkOpen — a second `function sheetOpen`
    in the one-scope bundle (sheet.js's comes later) silently replaced it, and the phone's ticket never opened."""
    src = lambda n: open(os.path.join(ROOT, "src", "js", n + ".js"), encoding="utf-8").read()
    js = build.bundle_js()
    assert js.count("function sheetOpen(") == 1 and "function tkOpen(" in js
    for fn in ("bindTabs", "fsFlat", "fsPicked", "fsClear", "fsCities", "fsMore", "fsSoon", "bindVerdict"):
        assert f"function {fn}(" in js, fn
    assert "fsPicked(btn, x)" in src("ticket") and "tkOpen(b)" in src("film")
    assert 'setAttribute("role", "tablist")' in src("tabs") and "aria-selected" in src("tabs") and "ArrowLeft" in src("tabs")
    assert len(gzip.compress(js.encode())) < 45 * 1024


def scaled_film(tmp_path, cinemas=60, per=10):
    """The fixture's film at `cinemas` cinemas (the fixture's twelve copied, across every city), `per` shows a day
    each over two days: a busier film than the busiest live one (555 shows at 53 cinemas)."""
    d = json.load(open(DATA, encoding="utf-8"))
    base = [s for s in d["shows"] if s["film"] == FID]
    by_cin = {}
    for s in base: by_cin.setdefault(s["cinema"], []).append(s)
    src = list(by_cin)
    times = ["10:15", "11:30", "12:45", "14:00", "15:15", "16:30", "17:45", "19:00", "20:15", "21:30", "22:45", "23:59"]
    k = 0
    while len({s["cinema"] for s in d["shows"] if s["film"] == FID}) < cinemas:
        k += 1
        for c in src:
            nc = f"{c}-{k}"
            d["cinemas"][nc] = dict(d["cinemas"][c], name=d["cinemas"][c].get("name", c) + f" {k}")
            proto = by_cin[c][0]
            for day in ("2026-09-25", "2026-09-26"):
                d["shows"] += [dict(proto, cinema=nc, date=day, time=t, book=(proto.get("book") or "https://example.com/b") + f"?s={nc}{day}{t}")
                               for t in times[:per]]
    p = tmp_path / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp_path / "o")
    build.build(str(p), DISC, o, noindex=False)
    n = len([s for s in d["shows"] if s["film"] == FID])
    return o, n


def test_a_film_with_many_shows_stays_within_150kb(tmp_path):
    """Always runs: the film at ~60 cinemas, ~1200 shows, every tab drawn, stays inside 150 KB in both languages (the
    schedule gives way — compact times — before the page does)."""
    o, n = scaled_film(tmp_path)
    assert n > 1000
    for parts in (("film", FID), ("en", "film", FID)):
        h = read(o, *parts)
        assert 'class="tl"' in h or "data-show=" in h                          # a schedule, whichever form fitted
        assert h.count('<details class="fcity"') >= 6
        size = os.path.getsize(os.path.join(o, *parts, "index.html"))
        assert size <= BUDGET, (parts, size)


def test_real_film_pages_within_150kb(tmp_path):
    """The live data (skipped where there is none): every film page, both languages."""
    src = os.path.join(ROOT, "data", "latest.json")
    if not os.path.exists(src): pytest.skip("no data/latest.json")
    o = str(tmp_path / "o")
    build.build(src, os.path.join(ROOT, "discounts.yaml"), o, noindex=False)
    for base in (os.path.join(o, "film"), os.path.join(o, "en", "film")):
        for fid in os.listdir(base):
            f = os.path.join(base, fid, "index.html")
            if os.path.exists(f): assert os.path.getsize(f) <= BUDGET, (f, os.path.getsize(f))
