"""The chrome every page shares (UI redesign Task 2; W2-P5): one header with the city and card pills, the phone's tab
bar of four, the footer's links, and the sheets the pills and the «قائمتي» tab open — on every page, in both languages,
with no duplicate ids. With no script the pills are plain links and the sheets stay hidden. W2-P5's own contract is in
tests/test_w2_p5.py."""
import collections
import os
import re
import sys
from html.parser import HTMLParser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
from site_kit import CITIES  # noqa: E402
from kit.chrome import ME_TAB  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("chrome") / "out")
    build.build(DATA, DISC, o, noindex=False)
    return o


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def pages(out):
    for dp, _, fs in os.walk(out):
        for f in fs:
            if f.endswith(".html"):
                yield os.path.relpath(os.path.join(dp, f), out).replace(os.sep, "/")


class Ids(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids = collections.Counter()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id": self.ids[v] += 1


def between(h, start, end):
    i = h.index(start)
    return h[i:h.index(end, i) + len(end)]


def test_every_page_has_one_header_one_tab_bar_of_four_the_pills_and_no_duplicate_ids(out):
    seen = 0
    for rel in pages(out):
        h = read(out, rel)
        # offline.html is the service worker's self-contained fallback (inline style, no assets): no site chrome by
        # design; a bare redirect stub has none either
        if rel == "offline.html" or ('http-equiv="refresh"' in h and "<header" not in h): continue
        seen += 1
        assert h.count('<header class="top">') == 1, rel
        assert h.count('<nav class="tabs"') == 1, rel
        tabs = between(h, '<nav class="tabs"', "</nav>")
        assert tabs.count("<a ") == 4, rel
        assert h.count('<footer class="foot">') == 1, rel
        p = Ids(); p.feed(h)
        for i in ("pill-city", "pill-card", "sheet-city", "sheet-card", "main") + (("sheet-me",) if ME_TAB else ()):
            assert p.ids[i] == 1, (rel, i)
        assert "{{" not in h, rel                                        # no template placeholder left
        dup = [k for k, n in p.ids.items() if n > 1]
        assert not dup, (rel, dup)
    assert seen > 100


def test_pills_are_links_with_no_script_and_open_the_sheets_with_it(out):
    for lang, pre in (("ar", ""), ("en", "/en")):
        h = read(out, *(["en"] if lang == "en" else []), "halls", "index.html")
        city = re.search(r'<a class="pill" id="pill-city" href="([^"]+)" data-sheet-open="sheet-city">', h)
        card = re.search(r'<a class="pill" id="pill-card" href="([^"]+)" data-sheet-open="sheet-card">', h)
        assert city and city.group(1) == pre + "/cinemas/"
        assert card and card.group(1) == pre + "/cards/"
        for sid in ("sheet-city", "sheet-card"):
            tag = re.search(r'<div class="sheet" id="' + sid + r'"[^>]*>', h).group(0)
            assert 'role="dialog"' in tag and 'aria-modal="true"' in tag and tag.endswith(" hidden>")
            lab = re.search(r'aria-labelledby="([^"]+)"', tag).group(1)
            assert f'id="{lab}"' in h
    # the pill says the page's city on a city page, Dubai (the script's default) elsewhere
    assert '<span data-city-name>العين</span>' in read(out, "al-ain", "index.html")
    assert '<span data-city-name>Dubai</span>' in read(out, "en", "index.html")
    assert '<span data-card-name>بطاقتي</span>' in read(out, "index.html")


def test_city_sheet_lists_every_city_and_near_me(out):
    h = read(out, "index.html")
    sheet = between(h, '<div class="sheet" id="sheet-city"', '</p></div></div>')
    for c, ar, _ in CITIES:
        assert f'href="/{c}/" data-city="{c}"' in sheet and ar in sheet
    assert "data-citypick" in sheet and 'data-near>' in sheet and "قريب مني" in sheet and "data-near-msg" in sheet
    assert '<a class="opt" href="/dubai/" data-city="dubai" aria-current="true">' in sheet
    assert sheet.index("data-near>") < sheet.index("data-citypick")                 # «قريب مني» first (W2-P5, §2.0)


def test_card_sheet_replaces_the_bank_select(out):
    h = read(out, "index.html")
    assert "<select data-card" not in h and "chips cards" not in h
    sheet = between(h, '<div class="sheet" id="sheet-card"', "</p></div></div>")
    assert '<button type="button" class="opt wide" data-card="" aria-pressed="true">بدون بطاقة</button>' in sheet   # first, full width (W2-P5)
    assert "حكومية" in sheet and 'data-card="fazaa"' in sheet
    assert sheet.index("حكومية") < sheet.index('data-card="fazaa"')
    # one choice per confirmed card, none twice anywhere on the page
    cards = re.findall(r'data-card="([^"]*)"', h)
    assert len(cards) == len(set(cards))


def test_tab_bar_marks_where_you_are_and_search_opens_the_overlay(out):
    home = between(read(out, "index.html"), '<nav class="tabs"', "</nav>")
    assert re.search(r'<a href="/" aria-current="page">', home)
    # D2 (owner, yes): the fourth tab is «قائمتي»; search is the header's icon on every page (W2-P5). The flag off puts
    # «بحث» back: tests/test_w2_p5.py builds both
    fourth = ("قائمتي", "My list") if ME_TAB else ("بحث", "Search")
    assert fourth[0] in home and ('data-search aria-haspopup="dialog"' in home) is not ME_TAB
    city = between(read(out, "dubai", "index.html"), '<nav class="tabs"', "</nav>")
    assert re.search(r'<a href="/cinemas/" aria-current="page">', city)
    en = between(read(out, "en", "index.html"), '<nav class="tabs"', "</nav>")
    assert all(w in en for w in ("Home", "Cinemas", "Coming soon", fourth[1]))
    head = between(read(out, "index.html"), '<header class="top">', "</header>")
    assert 'class="icon srch-b" data-search aria-haspopup="dialog"' in head


def test_header_links_and_footer_links(out):
    h = read(out, "index.html")
    nav = between(h, '<nav class="nav"', "</nav>")
    assert nav.count("<a ") == 4 and "الرئيسية" in nav and "الأسعار والبطاقات" in nav and 'href="/coming/"' in nav
    foot = between(h, '<nav class="foot-l"', "</nav>")
    for href, word in (("/cinemas/", "السينمات"), ("/cards/", "البطاقات والخصومات"), ("/sources/", "من وين الأسعار"),
                       ("/q/", "أسئلة"), ("/halls/", "القاعات"), ("/en/", "English")):
        assert f'href="{href}"' in foot and word in foot, href
    assert foot.index("/sources/") < foot.index("/q/") < foot.index("/arabic/")   # the spec's order, then the features'
    # a film page is not «الرئيسية»
    assert 'aria-current' not in between(read(out, "film", "heart-of-the-beast", "index.html"), '<nav class="nav"', "</nav>")


def test_hero_pages_are_marked_for_the_transparent_header(out):
    assert re.search(r'<body data-page="home"[^>]* data-hero>', read(out, "index.html"))
    assert re.search(r'<body data-page="film"[^>]* data-hero>', read(out, "film", "heart-of-the-beast", "index.html"))
    assert "data-hero" not in re.search(r"<body[^>]*>", read(out, "cards", "index.html")).group(0)


def test_sources_and_cinemas_pages(out):
    src = read(out, "sources", "index.html")
    assert '<ul class="chains">' in src and 'data-at="' in src and '<h1 class="pt">من وين الأسعار</h1>' in src
    assert '<section class="wrap srcs">' not in read(out, "index.html")          # moved off the home page
    cin = read(out, "en", "cinemas", "index.html")
    for c, _, en in CITIES:
        assert f'href="/en/{c}/">{en}</a>' in cin
    assert "/sitemap" not in cin and "https://cinema.elyoxe.com/cinemas/" in read(out, "sitemap.xml")


def test_the_control_sentence_is_gone_from_the_bodies(out):
    for parts in (("index.html",), ("dubai", "index.html"), ("film", "heart-of-the-beast", "index.html")):
        h = read(out, *parts)
        assert "data-citypick" in between(h, '<div class="sheet" id="sheet-city"', "</p></div></div>")
        assert h.count("data-citypick") == 1 and 'class="me-q"' not in h and 'class="citypick"' not in h


def test_sheet_js_is_in_the_main_bundle(out):
    # the bundle as the boot loader names it (W0-P1 dropped its preload: a repeat visit fetched it twice; merged at R0)
    js = re.search(r'"/assets/(cinema\.[0-9a-f]{10}\.js)"', read(out, "index.html")).group(1)
    b = read(out, "assets", js)
    assert "function sheetOpen(" in b and "function bindSheets(" in b and "function chAway(" in b
    assert "function bindTop(" not in b and "top-sent" not in b     # the header's sentinel: a scroll timeline now (W2-P5)
    assert b.index("function sheetOpen(") < b.index("(function init()")


def test_header_cinemas_link_is_current_on_cinema_pages(out):
    for parts in (("cinemas", "index.html"), ("dubai", "index.html"), ("en", "cinemas", "index.html")):
        nav = between(read(out, *parts), '<nav class="nav"', "</nav>")
        assert re.search(r'<a href="(/en)?/cinemas/" aria-current="page">', nav), parts
    assert "aria-current" not in between(read(out, "cards", "index.html"), '<nav class="nav"', "</nav>").split("/cards/")[0]


def test_pill_chevron_points_down_in_both_directions(out):
    css = read(out, "assets", "cinema.css")
    rule = re.search(r"\.pill::after\{[^}]*\}", css).group(0)
    # a ▾ is not direction-dependent: physical borders (logical inline-end would point it sideways in RTL)
    assert "border-right:" in rule and "border-bottom:" in rule and "inline-end" not in rule and "rotate(45deg)" in rule


def test_card_sheet_asks_in_emirati():
    import site_kit
    assert site_kit.CHROME_T["pick_card"][0] == "شو عندك من بطاقة؟"


def test_sheet_js_contract(out):
    js = open(os.path.join(ROOT, "src", "js", "sheet.js"), encoding="utf-8").read()
    # the focus trap covers form controls (a filter sheet has them)
    for sel in ("input:not([disabled])", "select:not([disabled])", "textarea:not([disabled])", '[tabindex]:not([tabindex="-1"])'):
        assert sel in js
    # leaving from inside a sheet replaces its history entry; city/cinema picks and «قريب مني» go through it
    assert "location.replace(u)" in js
    assert "shGo(a.href)" in open(os.path.join(ROOT, "src", "js", "main.js"), encoding="utf-8").read()
    assert "shGo(C.base" in open(os.path.join(ROOT, "src", "js", "near.js"), encoding="utf-8").read()
    # a search tap before the lazy chunk arrived is kept and replayed by the chunk
    assert "CINEMA_SEARCH_WANT" in js and "CINEMA_SEARCH_WANT" in open(os.path.join(ROOT, "src", "js", "search.js"), encoding="utf-8").read()
