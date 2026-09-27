"""pages/insights.py: /prices/ (index, history chart ≥ 30 days, cheapest time ≥ 14 days), /boxoffice/, the
compare data + chunk, and «شي يشبه» on film pages. Built from the fixtures with a synthetic price history."""
import datetime as dt, json, os, re, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import pages  # noqa: E402
import price_history as ph  # noqa: E402
import similar as sim  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
MINE = ("core", "insights", "questions")   # the other phase-2 modules are other tasks' (the full suite builds them all)
TODAY = "2026-09-25"


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def ct(html):
    return json.loads(re.search(r"<script>window\.CT = (.*?);</script>", html).group(1))


def ld(html):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))["@graph"]


def history(path, n_days, end="2026-09-24"):
    """n_days of synthetic lines ending `end`: vox Standard climbs 30 -> 30+n/10 (today reads 40); Tuesday mornings are cheap."""
    lines = {}
    e = dt.date.fromisoformat(end)
    for i in range(n_days):
        d = e - dt.timedelta(days=n_days - 1 - i)
        v = round(30 + i / 10, 2)
        cheap = 25.0 if d.weekday() == 1 else 45.0
        lines[d.isoformat()] = {
            "date": d.isoformat(), "at": d.isoformat() + "T09:00:00+04:00", "n": 100, "priced": 90,
            "prices": [["vox", "Standard", "", v, v - 5, v + 5, 60], ["vox", "Standard", "dubai", v, v - 5, v + 5, 30],
                       ["novo", "Standard", "", 45.0, 45.0, 45.0, 30]],
            "parts": [["vox", "Standard", "morning", cheap, 10], ["vox", "Standard", "night", 55.0, 10]],
            "films": {"crawlers": [200, 12], "sacrifice": [5, 1], "gone-film": [999, 30]}}
    ph.dump(lines, path)
    return lines


def build_with(tmp_path_factory, name, n_days):
    out = str(tmp_path_factory.mktemp(name))
    hp = os.path.join(out + "-h.jsonl")
    if n_days: history(hp, n_days)
    old = os.environ.get("CINEMA_PRICE_HISTORY")
    os.environ["CINEMA_PRICE_HISTORY"] = hp
    try:
        build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=MINE))
    finally:
        if old is None: os.environ.pop("CINEMA_PRICE_HISTORY", None)
        else: os.environ["CINEMA_PRICE_HISTORY"] = old
    return out


@pytest.fixture(scope="module")
def none(tmp_path_factory):
    return build_with(tmp_path_factory, "ins0", 0)


@pytest.fixture(scope="module")
def short(tmp_path_factory):
    return build_with(tmp_path_factory, "ins20", 20)


@pytest.fixture(scope="module")
def long(tmp_path_factory):
    return build_with(tmp_path_factory, "ins40", 40)


# ---------------------------------------------------------------- /prices/
def test_prices_index_today_both_languages(none):
    ar, en = read(none, "prices", "index.html"), read(none, "en", "prices", "index.html")
    for h in (ar, en):
        assert 'data-page="prices"' in h and '<h1 class="pt">' in h and '<link rel="canonical"' in h
        assert "noindex" not in h
    idx = re.search(r'<table class="matrix pidx".*?</table>', ar, re.S).group(0)
    # vox Standard today (fixture): median 40.00 of the cheapest seat, 38.00 to 52.00, 69 shows
    row = re.search(r'<tr data-k="vox\|Standard">(.*?)</tr>', idx, re.S).group(1)
    assert all(x in row for x in (">40.00<", ">38.00<", ">52.00<", ">69<"))
    assert "25 سبتمبر 2026" in ar and "25 September 2026" in en
    assert "قبل أي خصم" in ar
    # no history: neither the chart nor the cheapest time; the page says how many days it has
    for h in (ar, en):
        assert "<svg" not in h and 'id="cheapest-time"' not in h


def test_prices_title_says_the_index_day_and_the_chains_it_has(none):
    ar, en = read(none, "prices", "index.html"), read(none, "en", "prices", "index.html")
    t = re.search(r"<title>(.*?)</title>", ar).group(1)
    assert "25 سبتمبر 2026" in t and "25 September 2026" in re.search(r"<title>(.*?)</title>", en).group(1)
    desc = re.search(r'<meta name="description" content="([^"]*)"', ar).group(1)
    assert "فوكس" in desc and "سينما سيتي" in desc


def test_day_counts_read_as_arabic(tmp_path_factory):
    out = build_with(tmp_path_factory, "ins2", 1)                # one recorded day + the index day = two
    say = re.search(r'<p class="hint hist-n">(.*?)</p>', read(out, "prices", "index.html"), re.S).group(1)
    assert "يومين" in say and "2 أيام" not in say and "كل يوم" not in say
    assert "2 أيام" not in read(out, "boxoffice", "index.html")


def test_prices_short_history_shows_cheapest_time_not_chart(short):
    ar = read(short, "prices", "index.html")
    assert 'id="cheapest-time"' in ar and "<svg" not in ar
    sec = re.search(r'<section[^>]*id="cheapest-time".*?</section>', ar, re.S).group(0)
    assert "الثلاثاء" in sec and "25.00" in sec
    assert "30" in re.search(r'<p class="hint hist-n">(.*?)</p>', ar, re.S).group(1)


def test_prices_long_history_chart_with_table_and_change(long):
    ar, en = read(long, "prices", "index.html"), read(long, "en", "prices", "index.html")
    fig = re.search(r'<figure class="chart".*?</figure>', ar, re.S).group(0)
    assert '<svg' in fig and 'role="img"' in fig and "<title" in fig
    tbl = re.search(r'<details class="chart-t">.*?</details>', ar, re.S).group(0)
    assert "<table" in tbl and "2026-09-24" in tbl and "33.90" in tbl          # the last recorded day
    assert "زاد" in ar and "rose" in en                                         # 40 days of a climbing price
    assert 'id="cheapest-time"' in ar


# ---------------------------------------------------------------- /boxoffice/
def test_boxoffice_ranks_by_shows_and_says_not_tickets(none, long):
    ar, en = read(none, "boxoffice", "index.html"), read(none, "en", "boxoffice", "index.html")
    ol = re.search(r'<ol class="bo">(.*?)</ol>', ar, re.S).group(1)
    ids = re.findall(r'<li data-fid="([^"]+)"', ol)
    # the fixture's two days: coyote 47+41 shows, resident-evil 37+37, crawlers 35+35
    assert ids[:3] == ["coyote-vs-acme", "resident-evil", "crawlers"]
    assert re.search(r'data-fid="coyote-vs-acme".*?<span class="num">88</span>', ol, re.S)
    assert "تذاكر" in ar and "tickets" in en
    assert any(g.get("@type") == "ItemList" for g in ld(ar))
    # with history: the week adds it up (crawlers 200/day for the 6 days before), a film with no page is left out
    ids2 = re.findall(r'<li data-fid="([^"]+)"', read(long, "boxoffice", "index.html"))
    assert ids2[0] == "crawlers" and "gone-film" not in ids2


# ---------------------------------------------------------------- compare + similar
def test_compare_data_and_chunk(none):
    j = json.loads(read(none, "data", "compare.json"))
    d = json.load(open(DATA, encoding="utf-8"))
    showing = {f for f, v in d["films"].items() if v.get("status") != "archived"}
    assert set(j["f"]) == showing and j["t"] == TODAY
    assert j["f"]["crawlers"][2] == "skip"
    # the cheapest ticket per city, before and after each card: star fazaa is 20 % off
    base, cards = j["p"]["resident-evil"]["al-ain"]
    assert base > 0 and all(v < base for v in cards.values())
    assert all(len(x) == 3 for x in j["n"]["crawlers"]["dubai"]) and len(j["n"]["crawlers"]["dubai"]) <= 6
    film = read(none, "film", "crawlers", "index.html")
    # the chunk is fetched only where a compare box is: the box names it, a few bytes of the main bundle load it
    url = re.search(r'<section class="wrap cmp" data-cmp="crawlers" data-cmp-src="(/assets/compare\.[0-9a-f]{10}\.js)" hidden>', film).group(1)
    assert read(none, *url.strip("/").split("/")).startswith("(function (K) {")
    assert f'data-cmp-src="{url}"' in read(none, "boxoffice", "index.html")
    archived = read(none, "film", "weapons", "index.html")
    assert "data-cmp" not in archived and "compare" not in json.dumps(ct(archived).get("chunks") or {})
    assert "data-cmp-src" in read(none, "assets", re.search(r'\("/assets/(cinema\.[0-9a-f]{10}\.js)",document\)', film).group(1))


def test_similar_on_showing_film_pages_only(none):
    h = read(none, "film", "crawlers", "index.html")
    sec = re.search(r'<section class="sim">.*?</section>', h, re.S).group(0)
    links = re.findall(r'href="/film/([^/"]+)/"', sec)
    assert 1 <= len(links) <= 4 and "crawlers" not in links and "resident-evil" in links   # both horror
    assert "رعب" in sec
    assert '<section class="sim">' not in read(none, "film", "weapons", "index.html")        # archived: core has its own


def test_similar_scoring():
    films = {"a": {"genres": ["horror"], "lang": "English", "directors": ["Q9"], "cast": ["Q1"]},
             "b": {"genres": ["horror"], "lang": "Hindi"},
             "c": {"genres": ["comedy"], "lang": "English", "directors": ["Q9"]},
             "d": {"genres": ["comedy"], "lang": "English", "cast": ["Q1"]},
             "e": {"genres": ["horror", "comedy"], "lang": "English"},
             "f": {"genres": ["drama"], "lang": "English"}}
    got = sim.similar(films, "a", list(films))
    assert [g[0] for g in got] == ["c", "d", "e", "b"]     # person 4+1 (twice), genre 3+1, genre 3; lang alone never counts
    assert ("person", "Q9") in got[0][2] and ("lang", "English") in got[0][2]
    assert "f" not in [g[0] for g in sim.similar(films, "a", list(films), n=9)]


@pytest.fixture(scope="module")
def people_build(tmp_path_factory):
    """cast/directors are person ids (Task 1): Q2 has names and a page, Q1 has no entry at all."""
    d = json.load(open(DATA, encoding="utf-8"))
    d["films"]["crawlers"]["cast"] = ["Q1", "Q2"]
    d["films"]["resident-evil"]["cast"] = ["Q1", "Q2"]
    d["films"]["crawlers"]["directors"] = ["Q3", "Q4"]
    d["films"]["resident-evil"]["directors"] = ["Q3", "Q4"]
    d["people"] = {"Q2": {"qid": "Q2", "slug": "milla-j", "name_en": "Milla J", "name_ar": "ميلا ج", "photo": None,
                          "bio": {}, "notable": []},
                   "Q3": {"qid": "Q3", "slug": "q3", "name_en": "Q3", "name_ar": None},        # a label that is only an id
                   "Q4": {"qid": "Q4", "name_en": "No Slug", "name_ar": "بلا رابط"}}            # no slug: a name, never a link
    out = str(tmp_path_factory.mktemp("insp"))
    path = out + "-data.json"
    json.dump(d, open(path, "w", encoding="utf-8"))
    mods = [m for m in MINE + ("people",) if m in pages.names()]
    build.build(path, DISC, out, noindex=False, modules=build.discover(only=mods))
    return out, "people" in mods


def test_similar_names_people_never_ids(people_build):
    out, has_people = people_build
    for parts, name in ((("film", "crawlers"), "ميلا ج"), (("en", "film", "crawlers"), "Milla J")):
        sec = re.search(r'<section class="sim">.*?</section>', read(out, *parts, "index.html"), re.S).group(0)
        assert name in sec and not re.search(r"(?<![A-Za-z0-9])Q[0-9]+(?![0-9])", sec)
        if has_people:
            assert f'href="{"/en" if parts[0] == "en" else ""}/people/milla-j/"' in sec


def test_pages_within_budget(long):
    for parts in (("prices",), ("en", "prices"), ("boxoffice",), ("en", "boxoffice"), ("film", "crawlers")):
        assert len(read(long, *parts, "index.html").encode()) <= 150_000
