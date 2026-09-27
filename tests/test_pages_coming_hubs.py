"""pages/coming.py + pages/hubs.py (Task 2): /coming/, /arabic/, /events/, the last-chance strip,
and the «نازل الخميس» nav re-point -- built with only core + these two modules so this test
never depends on other in-flight phase-2 page modules landing in pages/ at the same time."""
import json
import os
import re

import pytest

import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
DATA = os.path.join(ROOT, "tests", "fixtures", "coming_sample.json")
MODULES = build.discover(only=("core", "coming", "hubs"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("coming_hubs"))
    build.build(DATA, DISC, o, modules=MODULES)
    return o


def test_coming_page_groups_by_release_thursday_and_dated_countdown(out):
    h = read(out, "coming", "index.html")
    assert "نازل الخميس" in h
    assert "1 أكتوبر 2026" in h        # Verity's release_date (2026-10-01) is itself a Thursday
    assert "التاريخ لاحقاً" in h        # Gatto has no release_date
    assert "cs-card" in h and h.count("cs-card") == 2
    assert "cs-notify" not in h and "disabled" not in h and "نبّهني" not in h   # the dead «نبّهني» is gone (W0-P2)


def test_coming_page_english_variant(out):
    h = read(out, "en", "coming", "index.html")
    assert "Out Thursday" in h and "Date to be announced" in h


def test_thursday_nav_link_repoints_to_coming(out):
    home = read(out, "index.html")
    nav = re.search(r'<nav class="nav".*?</nav>', home, re.S).group(0)
    assert '<a href="/coming/">نازل الخميس</a>' in nav


def test_coming_data_slice_written(out):
    d = json.loads(read(out, "data", "coming.json"))
    assert set(d) == {"verity", "gatto"}
    assert d["verity"]["release_date"] == "2026-10-01"


def test_arabic_hub_lists_only_arabic_language_films(out):
    ar = read(out, "arabic", "index.html")
    assert 'data-fid="shish-dou"' in ar
    for other in ("heart-of-the-beast", "resident-evil", "the-paradise"):
        assert f'data-fid="{other}"' not in ar   # English/Telugu films never show up here


def test_arabic_hub_english_variant(out):
    en = read(out, "en", "arabic", "index.html")
    assert "Arabic & Gulf" in en


def test_events_hub_lists_recognised_events_from_data(out):
    h = read(out, "events", "index.html")
    assert "K-Fest" in h or "مهرجان كي-فست" in h
    assert '<a class="nm" href="/film/heart-of-the-beast/">' in h
    assert "noindex" not in h   # real event data exists -- indexed normally
    sm = read(out, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/events/</loc>" in sm


def test_events_hub_empty_state_is_noindex_and_out_of_sitemap(tmp_path):
    # Fix round 2 (re-review, Critical persisted): a genuinely empty /events/ must be noindex and
    # excluded from the sitemap -- tests/test_preview.py carries a matching exemption for this
    # exact honest-empty text so that pre-existing, project-wide contract still holds.
    data = json.loads(open(DATA, encoding="utf-8").read())
    data["events"] = []
    empty_data = tmp_path / "no_events.json"
    empty_data.write_text(json.dumps(data), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(empty_data), DISC, o, modules=MODULES)

    h = open(os.path.join(o, "events", "index.html"), encoding="utf-8").read()
    assert "ما عندنا فعاليات مؤكدة" in h
    assert '<meta name="robots" content="noindex,nofollow">' in h
    en = open(os.path.join(o, "en", "events", "index.html"), encoding="utf-8").read()
    assert "No chain-confirmed events yet" in en
    assert '<meta name="robots" content="noindex,nofollow">' in en

    sm = open(os.path.join(o, "sitemap.xml"), encoding="utf-8").read()
    assert "/events/" not in sm   # excluded entirely, ar and en both


def test_events_hub_with_real_events_is_indexed_and_in_sitemap(out):
    # `out` is the module fixture built from tests/fixtures/coming_sample.json, which carries a
    # real (K-Fest) event -- the opposite case from the empty-state test above.
    h = read(out, "events", "index.html")
    assert "noindex" not in h
    sm = read(out, "sitemap.xml")
    assert "<loc>https://cinema.elyoxe.com/events/</loc>" in sm
    assert "<loc>https://cinema.elyoxe.com/en/events/</loc>" in sm


def test_no_last_chance_strip_even_with_a_list_in_the_data(out):
    """The fixture still carries data["last_chance"] (al-ain: heart-of-the-beast); the strip is deleted and the
    step switched off (W0-P2, MASTER-PLAN §4.1 #13), so no page prints «آخر فرصة» whatever the data says."""
    assert json.load(open(DATA, encoding="utf-8")).get("last_chance")
    for parts in (("index.html",), ("al-ain", "index.html"), ("dubai", "index.html"), ("en", "index.html"), ("en", "al-ain", "index.html")):
        h = read(out, *parts)
        assert "آخر فرصة" not in h and "Last chance" not in h and "last-chance" not in h, parts


def test_phone_bottom_bar_stays_one_row_with_the_feature_links(out):
    """Seven links in a four-column grid wrapped to a second 58 px row on phones (seen at 375 px, 2026-09-27)."""
    nav = re.search(r'<nav class="nav".*?</nav>', read(out, "index.html"), re.S).group(0)
    assert nav.count("<a ") > 4
    css = read(out, "assets", "cinema.css")
    assert re.search(r"@media \(max-width:\s*1023px\)\s*\{\s*\.nav\{grid-auto-flow:\s*column", css)


@pytest.mark.parametrize("day,thursday", [
    ("2026-09-28", "2026-10-01"),   # Monday -> the coming Thursday
    ("2026-09-29", "2026-10-01"),   # Tuesday
    ("2026-09-30", "2026-10-01"),   # Wednesday
    ("2026-10-01", "2026-10-01"),   # Thursday -> itself
    ("2026-10-02", "2026-10-01"),   # Friday -> the Thursday before («Anbil Avan» sat under 8 October)
    ("2026-10-03", "2026-10-01"),   # Saturday
    ("2026-10-04", "2026-10-01"),   # Sunday
])
def test_release_week_is_the_thursday_that_opens_it(day, thursday):
    from pages import coming as cm
    assert cm._thursday_of(day) == thursday


def test_friday_release_groups_under_the_thursday_before(tmp_path):
    d = json.load(open(DATA, encoding="utf-8"))
    d["coming"]["anbil-avan"] = {"title": "Anbil Avan", "title_ar": None, "release_date": "2026-10-02", "poster": None,
                                 "trailer": None, "genres": [], "chains": ["vox"]}
    path = tmp_path / "data.json"
    path.write_text(json.dumps(d), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(path), DISC, o, modules=MODULES)
    h = open(os.path.join(o, "coming", "index.html"), encoding="utf-8").read()
    week = re.search(r'<section class="wrap cs-week"><h2>1 أكتوبر 2026</h2>(.*?)</section>', h, re.S).group(1)
    assert "Anbil Avan" in week and "8 أكتوبر" not in h


def test_countdown_counts_days_in_arabic_grammar():
    import types
    from pages import coming as cm
    now = types.SimpleNamespace(date=lambda: __import__("datetime").date(2026, 9, 27))
    cd = lambda d, lang="ar": cm.ComingPages._countdown(types.SimpleNamespace(now=now), d, lang)
    assert cd("2026-09-28") == "بكرة" and cd("2026-09-29") == "بعد يومين"
    assert cd("2026-10-01") == "بعد 4 أيام" and cd("2026-10-09") == "بعد 12 يوم"
    assert cd("2026-10-01", "en") == "In 4 days" and cd("2026-09-28", "en") == "Tomorrow"


# ------------------------------------------------------------------ final review M1: /coming/ polish
def _coming_build(tmp_path, coming):
    data = json.loads(open(DATA, encoding="utf-8").read())
    data["coming"] = coming
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "data.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(p), DISC, o, modules=MODULES)
    return o


def _c(title, date="2026-10-01", chains=("vox",), genres=()):
    return {"title": title, "title_ar": None, "release_date": date, "poster": None, "trailer": None,
            "genres": list(genres), "chains": list(chains)}


def test_coming_names_chains_not_keys_and_uses_the_arabic_comma(tmp_path):
    o = _coming_build(tmp_path, {"verity": _c("Verity", chains=("vox", "star", "cineroyal"))})
    ar, en = read(o, "coming", "index.html"), read(o, "en", "coming", "index.html")
    chains_ar = re.search(r'<span class="cs-chains">(.*?)</span>', ar).group(1)
    assert "vox" not in chains_ar and "cineroyal" not in chains_ar
    assert "فوكس" in chains_ar and "ستار" in chains_ar and "، " in chains_ar and ", " not in chains_ar
    chains_en = re.search(r'<span class="cs-chains">(.*?)</span>', en).group(1)
    assert "VOX" in chains_en.upper() and ", " in chains_en and "cineroyal" not in chains_en


def test_coming_translates_genres_and_omits_unknown_labels(tmp_path):
    o = _coming_build(tmp_path, {"x-film": _c("X Film", genres=("Psychological", "Creature", "Sci Fi"))})
    ar = read(o, "coming", "index.html")
    meta = re.search(r'<span class="cs-meta">(.*?)</span>', ar).group(1)
    assert "Psychological" not in meta and "Creature" not in meta and "Sci Fi" not in meta
    assert "إثارة" in meta and "خيال علمي" in meta and "، " in meta
    o2 = _coming_build(tmp_path / "b", {"y-film": _c("Y Film", genres=("Creature",))})
    assert 'class="cs-meta"' not in read(o2, "coming", "index.html")   # nothing known -> no genre line


def test_coming_folds_near_identical_titles_into_one_card(tmp_path):
    o = _coming_build(tmp_path, {
        "the-legendaires": _c("The Legendaires", chains=("reel",)),
        "the-legendaries": _c("The Legendaries", chains=("star", "cineroyal")),
        "donand-39-t-trouble-the-trouble": _c("Don&#39;t Trouble The Trouble", "2026-10-02", ("vox",)),
        "don-t-trouble-the-trouble": _c("Don't Trouble The Trouble", "2026-10-02", ("star",)),
        "dont-trouble-the-trouble": _c("Dont Trouble The Trouble (Telugu)", "2026-10-02", ("reel",)),
        "the-shawshank-redemption": _c("The Shawshank Redemption (Re Release)", "2026-10-15", ("reel",)),
        "the-shawshank-redemption-re-release": _c("The Shawshank Redemption - Re release", "2026-10-15", ("star",)),
        # guards: a different date, or a different number, never folds
        "the-mongoose": _c("The Mongoose", "2026-10-25"), "the-mangoose": _c("The Mangoose", "2026-10-29"),
        "golmaal-4": _c("Golmaal 4", "2026-11-01"), "golmaal-5": _c("Golmaal 5", "2026-11-01"),
    })
    ar = read(o, "coming", "index.html")
    assert ar.count("cs-card") == 7
    assert "The Legendaries" in ar and "The Legendaires" not in ar     # the spelling more chains use wins
    names = re.findall(r'<span class="cs-n">(.*?)</span>', ar)
    assert sum("Trouble The Trouble" in n for n in names) == 1 and "&amp;#39;" not in ar   # an HTML entity in a feed title is decoded once
    card = re.search(r'<li class="cs-card">(?:(?!</li>).)*Legendaries.*?</li>', ar, re.S).group(0)
    assert all(n in card for n in ("ريل", "ستار", "سيني رويال"))           # the chains of both spellings
    assert sum("Shawshank" in n for n in names) == 1
    assert "The Mongoose" in ar and "The Mangoose" in ar and "Golmaal 4" in ar and "Golmaal 5" in ar


def test_near_duplicate_guard_unit():
    import pages.coming as pc
    assert pc._same_title("The Legendaires", "The Legendaries")
    assert pc._same_title("Don&#39;t Trouble The Trouble", "Dont Trouble The Trouble (Telugu)")
    assert not pc._same_title("Golmaal 4", "Golmaal 5")
    assert not pc._same_title("Wake", "Make")           # short titles need an exact match
    assert not pc._same_title("Ramayana", "Ramayana: Part One (Hindi)")
