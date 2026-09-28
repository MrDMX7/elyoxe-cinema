"""The home page (UI redesign Task 3): the billboard and its per-city island, «يبدأ قريب منك», the rows in the spec's
order (each from the site's own data, none under 4 films, «الكل» to a page or to «كل الأفلام» with a preset), the
tile, «كل الأفلام» with the filter and sort sheets holding every control the list used to have above it, what left
the home page (cities grid, cards list, chains' freshness), and the 150 KB budget in both languages."""
import json
import os
import re
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
from site_kit import CITIES  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
BUDGET = 150_000


def read(out, *parts):
    return open(os.path.join(out, *parts, "index.html"), encoding="utf-8").read()


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("home") / "out")
    build.build(DATA, DISC, o, noindex=False)
    return o


def full_data():
    """The fixture with enough of everything for every row: 5 announced films (2 on the coming Thursday), 4 films
    in their last days, 4 Arabic films."""
    d = json.load(open(DATA, encoding="utf-8"))
    fids = list(d["films"])
    for f in fids[:4]: d["films"][f]["lang"] = "Arabic"
    d["films"]["resident-evil"]["verdict"]["verdict"] = "yes"      # 4 «يستاهل» and 4 family films showing
    d["films"]["heart-of-the-beast"]["family"] = True
    for x in d["shows"]:                                            # one film with no price anywhere: «السعر في الشباك»
        if x["film"] == "crawlers": x["prices"] = []
    d["last_chance"] = {"dubai": fids[2:6]}
    d["coming"] = {f"soon-{i}": {"title": f"Soon {i}", "title_ar": None, "release_date": day, "poster": None, "trailer": None,
                                 "genres": ["Drama"], "chains": ["vox"]}
                   for i, day in enumerate(["2026-10-01", "2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22"])}
    return d


def build_full(tmp):
    p = tmp / "d.json"; p.write_text(json.dumps(full_data(), ensure_ascii=False), encoding="utf-8")
    o = str(tmp / "out")
    build.build(str(p), DISC, o, noindex=False)
    return o


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    return build_full(tmp_path_factory.mktemp("homefull"))


def main_of(h):
    return h[h.index("<main"):h.index("</main>")]


def scaled(tmp_path, n=100):
    """The fixture grown to about `n` showing films (each film copied under new ids with its shows), with every row
    full: the page's size as a busy week would make it, measured wherever the suite runs."""
    d = json.load(open(DATA, encoding="utf-8"))
    base = [f for f, v in d["films"].items() if v.get("status") != "archived"]
    shows = list(d["shows"])
    k = 0
    while len([f for f, v in d["films"].items() if v.get("status") != "archived"]) < n:
        k += 1
        for f in base:
            nf = f"{f}-{k}"
            d["films"][nf] = dict(d["films"][f], title=d["films"][f]["title"] + f" {k}")
            if d["films"][nf].get("title_ar"): d["films"][nf]["title_ar"] += f" {k}"
            d["shows"] += [dict(x, film=nf) for x in shows if x["film"] == f and x["date"] == "2026-09-25"]
    fids = [f for f, v in d["films"].items() if v.get("status") != "archived"]
    for f in fids[:12]: d["films"][f]["lang"] = "Arabic"
    d["last_chance"] = {"dubai": fids[:12]}
    d["coming"] = {f"soon-{i}": {"title": f"Soon {i}", "title_ar": None, "release_date": "2026-10-01", "poster": None,
                                 "trailer": None, "genres": ["Drama"], "chains": ["vox"]} for i in range(12)}
    p = tmp_path / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp_path / "o")
    build.build(str(p), DISC, o, noindex=False, modules=build.discover(only=("core", "coming", "hubs")))
    return o, len(fids)


def test_home_of_about_100_films_within_150kb(tmp_path):
    """Always runs (fix round 1, I3): the fixture scaled to ~100 films with every row drawn stays inside 150 KB in
    both languages (the live page held 66 films at 138 KB before the hover panels left the markup)."""
    o, n = scaled(tmp_path)
    assert n >= 100
    for parts in ((), ("en",)):
        h = read(o, *parts)
        assert h.count('class="film tile') == n
        # near + every row but «آخر فرصة», which is off with steps/last_chance.py (W0-P2, plan §4.1 #13, merged at R0)
        assert len(re.findall(r'<section class="rail"', h)) == 7
        size = os.path.getsize(os.path.join(o, *parts, "index.html"))
        assert size <= BUDGET, (parts, size)


def test_home_within_150kb_both_languages(out):
    for parts in ((), ("en",)):
        assert os.path.getsize(os.path.join(out, *parts, "index.html")) <= BUDGET, parts


def test_real_home_within_150kb_both_languages(tmp_path):
    """The live data (skipped where there is none): 66 films in the grid plus every row stays inside 150 KB."""
    src = os.path.join(ROOT, "data", "latest.json")
    if not os.path.exists(src): pytest.skip("no data/latest.json")
    o = str(tmp_path / "o")
    build.build(src, os.path.join(ROOT, "discounts.yaml"), o, noindex=False)
    for parts in ((), ("en",)):
        n = os.path.getsize(os.path.join(o, *parts, "index.html"))
        assert n <= BUDGET, (parts, n)


def test_billboard_slides_first_the_real_top_then_frames(tmp_path):
    """Fix round 1, I1: slide 1 is the city's real most-shown film (the eyebrow says so), frame or not; slides 2-5
    prefer the films of its top 10 that have a trailer frame, then the rest in order."""
    from pages.core import CorePages
    site = types.SimpleNamespace(films={f"f{i}": {} for i in range(12)})
    for i in (1, 7, 9, 11): site.films[f"f{i}"]["backdrop"] = {"w640": "a", "w1280": "b"}
    pick = CorePages(site).bill_pick
    ranked = [f"f{i}" for i in range(12)]
    assert pick(ranked) == ["f0", "f1", "f7", "f9", "f2"]           # f11 is outside the top 10
    assert pick(["f7", "f0", "f1"]) == ["f7", "f1", "f0"]
    assert pick([]) == []


def test_billboard_pause_button_and_phone_sizes(out):
    h = read(out)
    bill = re.search(r'<section class="bill".*?</section>', h, re.S).group(0)
    assert re.search(r'<button type="button" class="bill-pp" data-bill-pp aria-pressed="false"><span class="vh">أوقف التقليب</span></button>', bill)
    js = open(os.path.join(ROOT, "src", "js", "bill.js"), encoding="utf-8").read()
    assert "billHold.user" in js and "requestIdleCallback" in js and '"(min-width:1024px) 100vw, 320px"' in js
    # the live flag is set before the slide's words change: a turn is never announced
    show = js[js.index("function billShow("):js.index("function billDots(")]
    assert show.index('slide.setAttribute("aria-live"') < show.index("slide.innerHTML")
    # the slide's box keeps one height (a turn is never a layout shift) and the near row's place is held
    assert re.search(r"\.bill-in\{[^}]*min-block-size:430px", css_all()) and ".js .rail[data-near-row][hidden]{display:block;visibility:hidden}" in css_all()
    # stale layers go: every child but the newest
    assert "c !== nu" in show
    css = build.css_source()
    assert "rgba(0,0,0,.5)" not in css[css.index("/* ------------------------------------------------ home (UI redesign Task 3)"):]
    assert ".btn.ghost{backdrop-filter" not in css and ".bill .btn.ghost{" in css
    assert css.count(".cta{display:flex") == 1


def css_all():
    return build.css_source()


def test_no_duplicate_ids_on_any_page_even_with_summer_open(tmp_path):
    """Fix round 1, I2: /summer/ draws one «كل الأفلام» grid per city; the sheets and the section's ids come once per
    page. Built in July (summer open) so the loop really runs; every page is checked."""
    d = json.load(open(DATA, encoding="utf-8"))
    d["generated"] = "2026-07-15T10:00:00+04:00"
    for x in d["shows"]: x["date"] = {"2026-09-25": "2026-07-15", "2026-09-26": "2026-07-16"}.get(x["date"], x["date"])
    for f in d["films"].values(): f["family"] = True
    p = tmp_path / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp_path / "o")
    build.build(str(p), DISC, o, noindex=False)
    summer = read(o, "summer")
    assert summer.count('<div class="grid" data-films>') >= 2
    assert summer.count('id="sheet-filter"') == 1 and summer.count('id="all"') == 1
    assert "data-prayer" not in summer                                 # /summer/ never had the prayer switch
    bad = []
    for dp, _, fs in os.walk(o):
        for f in fs:
            if f.endswith(".html"):
                ids = re.findall(r'\sid="([^"]+)"', open(os.path.join(dp, f), encoding="utf-8").read())
                if len(ids) != len(set(ids)): bad.append(os.path.relpath(os.path.join(dp, f), o))
    assert not bad, bad[:10]


def test_billboard_and_its_island(out):
    for lang, parts in (("ar", ()), ("en", ("en",))):
        h = read(out, *parts)
        bill = re.search(r'<section class="bill" data-bill[^>]*aria-label="[^"]+">.*?</section>', h, re.S).group(0)
        # Dubai's most shown tonight, server-drawn, the eyebrow naming the city
        assert ("الأكثر عرضاً في دبي الليلة" if lang == "ar" else "Most shown in Dubai tonight") in bill
        assert re.search(r'<h2 class="bill-t"><a href="/(en/)?film/[^"]+/" data-bill-a', bill)
        assert 'data-from="' in bill and 'class="btn main"' in bill and "data-bill-tr" in bill
        island = json.loads(re.search(r'<script type="application/json" id="bill-data">(.*?)</script>', bill, re.S).group(1))
        assert "*" in island["c"] and set(island["c"]) <= {c for c, _, _ in CITIES} | {"*"}   # a city with nothing tonight: none
        for c, rows in island["c"].items():
            assert 1 <= len(rows) <= 5
            for fid, price in rows:
                assert fid in island["f"]
                assert price is None or len(price) == 6
        for o in island["f"].values():
            assert o["t"] and o["h"] and o["v"] and o["w"] and isinstance(o["x"], list)
            assert "·" not in "".join(o["x"])                               # facts are spans, never a dotted string
        dots = re.findall(r'<button type="button" aria-label="([^"]+)" aria-pressed="(true|false)"><i></i></button>', bill)
        assert len(dots) == len(island["c"]["dubai"]) and dots[0][1] == "true" and all(d[0] for d in dots)
        assert re.search(r'<body data-page="home"[^>]* data-hero>', h)


def test_near_row_is_drawn_by_the_script_and_hidden_until_then(out):
    h = read(out)
    # id="now": the manifest's «الحين» shortcut lands here (W0-P1, plan §4.1 #5, merged at R0)
    row = re.search(r'<section class="rail" aria-labelledby="r-near" id="now" data-near-row hidden>.*?</section>', h, re.S).group(0)
    assert "يبدأ قريب منك" in row and "data-near-sub" in row and "data-near" in row and '<div class="strip" data-strip></div>' in row
    js = open(os.path.join(ROOT, "src", "js", "home.js"), encoding="utf-8").read()
    near = js[js.index("function renderNear("):js.index("function renderFrom(")]
    assert "3 * 3600e3" in near and "row.hidden = !list.length" in near and "inMinutes(" in near and "kmTo(" in near


def test_rows_in_order_from_the_data(full):
    h = read(full)
    m = main_of(h)
    keys = re.findall(r'<section class="rail" aria-labelledby="r-([a-z]+)"', m)
    # no «آخر فرصة» row and no «آخر أسبوع» tag while steps/last_chance.py is off (W0-P2, plan §4.1 #13, merged at R0),
    # whatever data["last_chance"] holds; test_last_chance_row_only_with_the_step_on draws it with the switch on
    assert keys == ["near", "top", "yes", "cheap", "family", "coming", "arabic"], keys
    assert "آخر أسبوع" not in m
    rows = {k: re.search(r'<section class="rail" aria-labelledby="r-' + k + r'".*?</section>', m, re.S).group(0) for k in keys}
    for k in keys[1:]:
        assert rows[k].count('class="tile') >= 4, k
    # «الكل»: a page, or «كل الأفلام» with its sort or filter chosen
    href = lambda k: re.search(r'<a class="all-l" href="([^"]+)"', rows[k]).group(1)
    assert href("top") == "/#all" and href("yes") == "/?f=yes#all" and href("cheap") == "/?sort=price#all"
    assert href("family") == "/?f=family#all" and href("coming") == "/coming/" and href("arabic") == "/arabic/"
    # tags: «الخميس» on this Thursday's releases only
    assert rows["coming"].count('<span class="tag">الخميس</span>') == 2
    # rows re-sort for the visitor: «الأكثر عرضاً» by their city, «أرخص لك» after their card
    assert 'data-rail-sort="count"' in rows["top"] and 'data-rail-sort="pay"' in rows["cheap"]
    # the verdict row holds only «يستاهل» films
    assert set(re.findall(r'class="tile v-(\w+)"', rows["yes"])) == {"yes"}
    # a row's tile: the id and runtime the prices read, not the filter attributes (the sheet filters the grid)
    assert "data-genres" not in rows["top"] and 'data-fid="' in rows["top"]
    assert 'data-rail="1"' in rows["top"] and 'aria-label="التالي"' in rows["top"]


def test_last_chance_row_only_with_the_step_on(tmp_path, monkeypatch):
    """The row and the tags the redesign draws from data["last_chance"] come back only when the step is switched on
    again on a real signal (W2-P4 deletes this code or rebuilds it on that signal)."""
    from steps import last_chance
    monkeypatch.setattr(last_chance, "ENABLED", True)
    m = main_of(read(build_full(tmp_path)))
    keys = re.findall(r'<section class="rail" aria-labelledby="r-([a-z]+)"', m)
    assert keys == ["near", "top", "yes", "cheap", "family", "coming", "last", "arabic"], keys
    row = re.search(r'<section class="rail" aria-labelledby="r-last".*?</section>', m, re.S).group(0)
    assert 'class="all-l"' not in row and row.count('<span class="tag">آخر أسبوع</span>') == 4


def test_rows_under_four_are_skipped(out):
    m = main_of(read(out))
    assert 'aria-labelledby="r-arabic"' not in m          # one Arabic film in the fixture
    assert 'aria-labelledby="r-coming"' not in m and 'aria-labelledby="r-last"' not in m


def test_tile_markup(out):
    m = main_of(read(out))
    tile = re.search(r'<a class="film tile v-yes" href="/film/coyote-vs-acme/"[^>]*>.*?</a>', m, re.S).group(0)
    for attr in ('data-fid="coyote-vs-acme"', "data-genres=", "data-family=", "data-kids=", 'data-v="yes"', "data-runtime=", 'data-lang="English"'):
        assert attr in tile, attr
    # the desktop hover panel is drawn by home.js (hoverPanel), not shipped per tile (fix round 1, I3)
    assert re.search(r'<span class="tp"><span class="pst img"[^>]*><img [^>]+></span></span><span class="t">كايوتي ضد أكمي</span>'
                     r'<span class="m" data-cheap>من <span class="pv"><span class="num">[\d.]+</span></span> درهم</span></a>$', tile)
    assert 'class="hv"' not in m
    js = open(os.path.join(ROOT, "src", "js", "home.js"), encoding="utf-8").read()
    assert "function hoverPanel(" in js and "(hover: hover) and (min-width: 1024px)" in js


def test_tile_without_a_price_says_box_office(full):
    tile = re.search(r'<a class="film tile[^"]*" href="/film/crawlers/"[^>]*>.*?</a>', main_of(read(full)), re.S).group(0)
    assert tile.endswith('<span class="m" data-cheap><span class="na">السعر في الشباك</span></span></a>')


def test_all_films_grid_and_its_sheets(full):
    for lang, parts in (("ar", ()), ("en", ("en",))):
        h = read(full, *parts)
        m = main_of(h)
        grid = re.search(r'<section class="all wrap" id="all" aria-labelledby="all-h">.*?</section>', m, re.S).group(0)
        assert grid.count('class="film tile') == len(re.findall(r'"@type": "ListItem", "position": \d+, "url": "[^"]+/film/', h))
        assert 'data-sheet-open="sheet-filter"' in grid and 'data-sheet-open="sheet-sort"' in grid and "data-fcount hidden" in grid
        assert '<div class="grid" data-films>' in grid and "data-empty" in grid
        after = h[h.index("</main>"):]
        fs = re.search(r'<div class="sheet" id="sheet-filter" role="dialog" aria-modal="true" aria-labelledby="sheet-filter-t" hidden>.*?data-fn-live aria-live="polite"></p></div></div>', after, re.S).group(0)
        # every control the list had above it, in the sheet: genre (all, family, kids, genres), who, ends-before,
        # sort, the prayer switch — plus the language when the films have more than one — «مسح» and «اعرض N»
        for need in ('data-filter="all"', 'data-filter="family"', 'data-filter="kids"', 'data-filter="yes"', 'data-filter="genre:',
                     'data-who="solo"', 'data-who="friends"', 'data-who="family"', 'data-who="kids"',
                     'data-before=""', 'data-before="21:00"', 'data-before="24:00"',
                     'data-sort="price"', 'data-sort="time"', 'data-sort="verdict"',
                     'role="switch"', "data-prayer", "data-hide-clash", "data-prayer-times",
                     'data-flang=""', 'data-flang="Arabic"', "data-reset", "data-show-all", "data-fn"):
            assert need in fs, (lang, need)
        assert fs.count('data-filter="genre:family"') == 0   # «عائلي» is its own chip, never twice
        ss = re.search(r'<div class="sheet" id="sheet-sort".*?</div></div></div>', after, re.S).group(0)
        assert "data-sort-pick" in ss and ss.count("data-sort=") == 3
        assert len(re.findall(r'\sid="([^"]+)"', h)) == len(set(re.findall(r'\sid="([^"]+)"', h)))


def test_home_no_longer_carries_the_cities_cards_or_freshness(out):
    for parts in ((), ("en",)):
        m = main_of(read(out, *parts))
        assert 'id="cities"' not in m and 'class="clist"' not in m
        assert "cardsx" not in m and 'href="/cards/fazaa/"' not in m and 'href="/en/cards/fazaa/"' not in m
        assert 'class="chains"' not in m and "data-at=" not in m
        assert "data-me" not in m and 'class="ctl' not in m and "<select" not in m


def test_search_tab_falls_back_to_all_films(out):
    tabs = re.search(r'<nav class="tabs".*?</nav>', read(out), re.S).group(0)
    assert re.search(r'<a href="/#all" data-search', tabs)


def test_filters_js_reads_the_sheet(out):
    js = open(os.path.join(ROOT, "src", "js", "filters.js"), encoding="utf-8").read()
    for need in ("[data-before]", "[data-flang]", "data-sort-pick", "[data-fcount]", "[data-fn-live]", 'param("sort")', 'param("f")', 'param("fl")'):
        assert need in js, need
    bill = open(os.path.join(ROOT, "src", "js", "bill.js"), encoding="utf-8").read()
    assert "6000" in bill and "if (!RM)" in bill and "visibilitychange" in bill and "mouseenter" in bill and "focusin" in bill
