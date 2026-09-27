"""The home page (UI redesign Task 3): the billboard and its per-city island, «يبدأ قريب منك», the rows in the spec's
order (each from the site's own data, none under 4 films, «الكل» to a page or to «كل الأفلام» with a preset), the
tile, «كل الأفلام» with the filter and sort sheets holding every control the list used to have above it, what left
the home page (cities grid, cards list, chains' freshness), and the 150 KB budget in both languages."""
import json
import os
import re
import sys

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


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    """The fixture with enough of everything for every row: 5 announced films (2 on the coming Thursday), 4 films
    in their last days, 4 Arabic films."""
    d = json.load(open(DATA, encoding="utf-8"))
    fids = list(d["films"])
    for f in fids[:4]: d["films"][f]["lang"] = "Arabic"
    d["films"]["resident-evil"]["verdict"]["verdict"] = "yes"      # 4 «يستاهل» and 4 family films showing
    d["films"]["heart-of-the-beast"]["family"] = True
    d["last_chance"] = {"dubai": fids[2:6]}
    d["coming"] = {f"soon-{i}": {"title": f"Soon {i}", "title_ar": None, "release_date": day, "poster": None, "trailer": None,
                                 "genres": ["Drama"], "chains": ["vox"]}
                   for i, day in enumerate(["2026-10-01", "2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22"])}
    tmp = tmp_path_factory.mktemp("homefull")
    p = tmp / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp / "out")
    build.build(str(p), DISC, o, noindex=False)
    return o


def main_of(h):
    return h[h.index("<main"):h.index("</main>")]


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
    row = re.search(r'<section class="rail" aria-labelledby="r-near" data-near-row hidden>.*?</section>', h, re.S).group(0)
    assert "يبدأ قريب منك" in row and "data-near-sub" in row and "data-near" in row and '<div class="strip" data-strip></div>' in row
    js = open(os.path.join(ROOT, "src", "js", "home.js"), encoding="utf-8").read()
    near = js[js.index("function renderNear("):js.index("function renderFrom(")]
    assert "3 * 3600e3" in near and "row.hidden = !list.length" in near and "inMinutes(" in near and "kmTo(" in near


def test_rows_in_order_from_the_data(full):
    h = read(full)
    m = main_of(h)
    keys = re.findall(r'<section class="rail" aria-labelledby="r-([a-z]+)"', m)
    assert keys == ["near", "top", "yes", "cheap", "family", "coming", "last", "arabic"], keys
    rows = {k: re.search(r'<section class="rail" aria-labelledby="r-' + k + r'".*?</section>', m, re.S).group(0) for k in keys}
    for k in keys[1:]:
        assert rows[k].count('class="tile') >= 4, k
    # «الكل»: a page, or «كل الأفلام» with its sort or filter chosen
    href = lambda k: re.search(r'<a class="all-l" href="([^"]+)"', rows[k]).group(1)
    assert href("top") == "/#all" and href("yes") == "/?sort=verdict#all" and href("cheap") == "/?sort=price#all"
    assert href("family") == "/?f=family#all" and href("coming") == "/coming/" and href("arabic") == "/arabic/"
    assert 'class="all-l"' not in rows["last"]
    # tags: «الخميس» on this Thursday's releases only, «آخر أسبوع» on every last-chance tile
    assert rows["coming"].count('<span class="tag">الخميس</span>') == 2
    assert rows["last"].count('<span class="tag">آخر أسبوع</span>') == 4
    # rows re-sort for the visitor: «الأكثر عرضاً» by their city, «أرخص لك» after their card
    assert 'data-rail-sort="count"' in rows["top"] and 'data-rail-sort="pay"' in rows["cheap"]
    # the verdict row holds only «يستاهل» films
    assert set(re.findall(r'class="tile v-(\w+)"', rows["yes"])) == {"yes"}
    # a row's tile: the id and runtime the prices read, not the filter attributes (the sheet filters the grid)
    assert "data-genres" not in rows["top"] and 'data-fid="' in rows["top"]
    assert 'data-rail="1"' in rows["top"] and 'aria-label="التالي"' in rows["top"]


def test_rows_under_four_are_skipped(out):
    m = main_of(read(out))
    assert 'aria-labelledby="r-arabic"' not in m          # one Arabic film in the fixture
    assert 'aria-labelledby="r-coming"' not in m and 'aria-labelledby="r-last"' not in m


def test_tile_markup(out):
    m = main_of(read(out))
    tile = re.search(r'<a class="film tile v-yes" href="/film/coyote-vs-acme/"[^>]*>.*?</a>', m, re.S).group(0)
    for attr in ('data-fid="coyote-vs-acme"', "data-genres=", "data-family=", "data-kids=", 'data-v="yes"', "data-runtime=", 'data-lang="English"'):
        assert attr in tile, attr
    assert re.search(r'<span class="tp"><span class="pst img"[^>]*><img [^>]+></span><span class="hv" aria-hidden="true"><span class="vw">يستاهل</span>'
                     r'<span class="nx" data-next></span></span></span><span class="t">كايوتي ضد أكمي</span>'
                     r'<span class="m" data-cheap>من <span class="pv"><span class="num">[\d.]+</span></span> درهم</span></a>$', tile)
    # no price known: «السعر في الشباك»
    assert re.search(r'<span class="m" data-cheap><span class="na">السعر في الشباك</span></span>', m) or "السعر في الشباك" not in m


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
        for need in ('data-filter="all"', 'data-filter="family"', 'data-filter="kids"', 'data-filter="genre:',
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
