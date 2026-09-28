"""W2-P1 · «الشاشة»: the billboard and the film hero's picture (MASTER-PLAN §1.6, §2.1, §2.2, §5.3).

What is held here, without a browser (the browser half is tools/check_w2_p1.cjs: the first screen's geometry at 360×740
and 390×844, the 320 pass, the Al Ain first visit, the image bytes before a swipe, the strip's indicators in RTL and
LTR, the LCP's opacity, the idle phone, the desktop's pause off screen, reduced motion and the house lights):
  - the frame's newer keys are checked before they reach markup (the portrait crop, its window, its spill);
  - «الشاشة» has three kinds: a graded frame (its portrait crop on a phone, `100vw`), the lit poster case, and the
    title tile; only the page's LCP picture loads with the page, preloaded with the same srcset, sizes and media;
  - the slides: slide 1 is the UAE's most-shown film tonight whatever its verdict (honest, and no price when it is
    «تجنّبه»); slides 2–5 are framed films of the top 10, never «تجنّبه»; the calendar's new release on slide 2 from
    Wednesday 18:00 to Saturday; one billboard for every city (no per-city island);
  - the markup: the title by its length, the verdict word, the velvet CTA with its price, the 48×48 trailer icon, the
    card door, the indicators; no facts line on a phone; the blurred fog gone from home and the film hero;
  - the stylesheet's numbers (the screen's clamp, the case, the hero, the grain, the recede, the lights) and the
    motion law (no phone turn, the desktop's clock only, nothing starting at opacity 0);
  - bill.js and trailer.js in node: the clock only where a turn may happen, billInsert desktop only, the door from the
    card's rules, the house lights.
Node parts skip without node (the Fold may not have it), as tests/test_js.py does."""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
from kit import media  # noqa: E402
from site_kit import Kit  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
SRC = os.path.join(ROOT, "src")
SPILL = ["#1E302C", "#151F20", "#4A5139", "#A38D53"]


def read(out, *parts):
    return open(os.path.join(out, *parts, "index.html"), encoding="utf-8").read()


def css(name):
    return open(os.path.join(SRC, "css", name + ".css"), encoding="utf-8").read()


def js(name):
    return open(os.path.join(SRC, "js", name + ".js"), encoding="utf-8").read()


def frame(fid, **k):
    return dict({"w1280": f"/posters/bd-{fid}-0a1b2c3d4e-1280.webp", "w640": f"/posters/bd-{fid}-0a1b2c3d4e-640.webp", "w": 1280, "h": 536}, **k)


def framed(d):
    """The fixture with W1-D1's frames on some films. Tonight's order (shows today): coyote-vs-acme 47 (يستاهل),
    resident-evil 37 (بين بين), crawlers 35 (تجنّبه), heart-of-the-beast 34 (يستاهل), the-paradise 34, spider-man 28,
    sacrifice 23 (تجنّبه), shish-dou 22 (no verdict)."""
    f = d["films"]
    f["coyote-vs-acme"]["backdrop"] = frame("coyote-vs-acme", p="/posters/bd-coyote-vs-acme-9f8e7d6c5b-p.webp", pw=536, ph=804, x=0.25, spill=SPILL)
    for fid in ("resident-evil", "crawlers", "heart-of-the-beast", "sacrifice", "shish-dou"):
        f[fid]["backdrop"] = frame(fid)
    return d


def built(tmp, mutate=None, only_core=True):
    d = json.load(open(DATA, encoding="utf-8"))
    if mutate: mutate(d)
    p = tmp / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp / "o")
    build.build(str(p), DISC, o, noindex=False, **({"modules": build.discover(only=("core",))} if only_core else {}))
    return o


def bill_of(h):
    i = h.index('<section class="bill"')
    return h[i:h.index("</section>", i) + len("</section>")]


def slides_of(bill):
    return re.findall(r'<div class="slide ([a-z]+)( on)?" role="group"[^>]*>(.*?)(?=<div class="slide |</div><div class="bill-foot">)', bill, re.S)


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return built(tmp_path_factory.mktemp("w2p1"), framed)


# ---------------------------------------------------------------- the frame's keys, checked
class _Media(media.MediaKit):
    def __init__(self, films):
        self.films, self._preload = films, ""

    def ftitle(self, fid, lang):
        f = self.films[fid]
        return (f.get("title_ar") if lang == "ar" else None) or f.get("title") or fid

    def title_attr(self, fid, lang):
        return ' lang="en" dir="ltr"' if lang == "ar" and not self.films[fid].get("title_ar") else ""


def test_the_frames_newer_keys_are_checked_before_markup():
    good = frame("a", p="/posters/bd-a-1-p.webp", pw=536, ph=804, x=0.25, spill=SPILL)
    k = _Media({"a": {"backdrop": good}})
    assert k.frame("a") == {"w1280": "/posters/bd-a-0a1b2c3d4e-1280.webp", "w640": "/posters/bd-a-0a1b2c3d4e-640.webp", "w": 1280, "h": 536,
                            "p": "/posters/bd-a-1-p.webp", "pw": 536, "ph": 804, "x": 0.25, "spill": SPILL}
    for bad in ({"p": "https://evil.example/bd-a-p.webp"}, {"p": "/posters/bd-a-1-p.webp\" onerror=\"x"}, {"pw": 0}, {"ph": "tall"},
                {"x": 1.5}, {"x": -0.1}, {"x": True}, {"x": "0.5"}, {"spill": ["red", "#000000", "#000000", "#000000"]},
                {"spill": SPILL[:3]}, {"spill": "#000000"}):
        got = _Media({"a": {"backdrop": dict(good, **bad)}}).frame("a")
        key = next(iter(bad))
        assert (key if key not in ("pw", "ph") else "p") not in got, bad
        assert got["w1280"] and got["w640"]
    # never an f-string of a raw number: a zero or a word falls back to the frame's usual size
    got = _Media({"a": {"backdrop": frame("a", w=0, h="x")}}).frame("a")
    assert (got["w"], got["h"]) == (1280, 720)
    assert _Media({"a": {"backdrop": None}}).frame("a") is None and _Media({"a": {}}).frame("a") is None


def test_the_screen_has_three_kinds_and_only_the_first_loads():
    films = {"fr": {"backdrop": frame("fr", p="/posters/bd-fr-1-p.webp", pw=536, ph=804, x=0.125, spill=SPILL), "poster_color": "#112233"},
             "lit": {"poster": "/posters/lit-1-342.webp", "poster_2x": "/posters/lit-1-684.webp", "poster_color": "#445566"},
             "none": {"title": "The Paradise", "year": 2026}}
    k = _Media(films)
    s = k.screen("fr", "ar", first=True)
    assert s["kind"] == "fr" and s["case"] == "" and s["spill"] == SPILL
    assert '<div class="bd fr" style="--pc:#112233;--x:12.5%" aria-hidden="true"><picture>' in s["layer"]
    assert '<source media="(max-width:767px)" srcset="/posters/bd-fr-1-p.webp" width="536" height="804">' in s["layer"]
    assert re.search(r'<img src="[^"]+-1280\.webp" srcset="[^"]+-640\.webp 640w, [^"]+-1280\.webp 1280w" sizes="100vw" width="1280" height="536" alt=""'
                     r' fetchpriority="high"', s["layer"])
    # the preload follows the picture: the portrait on a phone, the landscape (same srcset and sizes) wider
    assert s["preload"] == ('<link rel="preload" as="image" href="/posters/bd-fr-1-p.webp" media="(max-width:767px)" fetchpriority="high">'
                            '<link rel="preload" as="image" href="/posters/bd-fr-0a1b2c3d4e-1280.webp" imagesrcset="/posters/bd-fr-0a1b2c3d4e-640.webp 640w, '
                            '/posters/bd-fr-0a1b2c3d4e-1280.webp 1280w" imagesizes="100vw" media="(min-width:768px)" fetchpriority="high">')
    # a later slide: written unloaded (bill.js loads it), never a fetch with the page
    s2 = k.screen("fr", "ar", first=False)
    assert s2["preload"] == "" and not re.search(r'\s(src|srcset)="', s2["layer"]) and 'data-srcset="/posters/bd-fr-1-p.webp"' in s2["layer"]
    assert 'fetchpriority' not in s2["layer"] and 'decoding="async"' in s2["layer"]
    # the lit case: the poster's own light behind, the sharp poster in the case, preloaded as drawn
    s = k.screen("lit", "ar")
    assert s["kind"] == "lit" and s["layer"] == '<div class="bd lit" style="--pc:#445566" aria-hidden="true"></div>'
    assert s["case"].startswith('<span class="case" style="--pc:#445566"><img src="/posters/lit-1-342.webp" srcset="/posters/lit-1-342.webp 342w, '
                                '/posters/lit-1-684.webp 684w" sizes="(min-width:1024px) 240px, 160px" width="342" height="513" alt="" fetchpriority="high"')
    assert s["preload"] == ('<link rel="preload" as="image" href="/posters/lit-1-342.webp" imagesrcset="/posters/lit-1-342.webp 342w, '
                            '/posters/lit-1-684.webp 684w" imagesizes="(min-width:1024px) 240px, 160px" fetchpriority="high">')
    assert k.screen("lit", "ar", first=False)["case"].count('data-src="') == 1 and k.screen("lit", "ar", case=False)["case"] == ""
    # no poster either: the title in Markazi and the year, over velvet to night; never a flat block
    s = k.screen("none", "ar")
    assert s["kind"] == "noimg" and s["preload"] == "" and '<div class="bd noimg"' in s["layer"]
    assert s["case"] == ('<span class="case pst" style="--pc:' + re.search(r"--pc:(#[0-9A-Fa-f]{6})", s["case"]).group(1) +
                         '" aria-hidden="true"><span class="pst-t" lang="en" dir="ltr">The Paradise</span><span class="num">2026</span></span>')


def test_the_backdrop_is_full_bleed_whatever_a_caller_asks():
    k = _Media({"fr": {"backdrop": frame("fr")}, "lit": {"poster": "/posters/lit-342.webp"}})
    layer = k.backdrop("fr", hero=True, sizes="(min-width:1024px) 100vw, 320px")
    assert 'sizes="100vw"' in layer and "320px" not in layer and 'imagesizes="100vw"' in k._preload
    k._preload = ""
    assert k.backdrop("lit", hero=True) == '<div class="bd lit" style="--pc:' + re.search(r"--pc:(#[0-9A-Fa-f]{6})", k.backdrop("lit")).group(1) + '" aria-hidden="true"></div>'
    assert k._preload == ""      # the film hero's card is the case there: it preloads itself as the page's first poster


# ---------------------------------------------------------------- which films
def _pages(films, now="2026-09-25T18:00:00+04:00", shows=None):
    from pages.core import CorePages
    now = dt.datetime.fromisoformat(now)
    shows = shows or []
    by = {}
    for s in shows: by.setdefault(s["film"], []).append(s)
    site = types.SimpleNamespace(films=films, now=now, showing=list(films), d={}, _by_film=by,
                                 today_count={f: sum(1 for s in ss if s["date"] == now.date().isoformat()) for f, ss in by.items()},
                                 week_phase=Kit.week_phase, frame=lambda f: films[f].get("backdrop"))
    return CorePages(site)


def test_slide_one_is_the_top_whatever_it_is_and_the_rest_are_framed_and_never_skip():
    films = {f"f{i}": {"verdict": {"verdict": "yes"}} for i in range(12)}
    for i in (1, 2, 3, 7, 9, 11): films[f"f{i}"]["backdrop"] = frame(f"f{i}")
    films["f2"]["verdict"]["verdict"] = "skip"                 # framed but «تجنّبه»: never promoted
    films["f0"]["verdict"]["verdict"] = "skip"                 # slide 1 stays, honest
    pick = _pages(films).bill_pick
    ranked = [f"f{i}" for i in range(12)]
    assert pick(ranked) == ["f0", "f1", "f3", "f7", "f9"]      # f11 is outside the top 10; f2 is «تجنّبه»
    assert pick(["f5", "f1"]) == ["f5", "f1"] and pick([]) == []
    films["f3"]["verdict"] = None                              # no verdict yet: may be promoted
    assert "f3" in pick(ranked)


@pytest.mark.parametrize("now,released,eye", [
    ("2026-09-23T19:00:00+04:00", "2026-09-24", "eve"),       # Wednesday evening: opens tomorrow
    ("2026-09-23T17:59:00+04:00", "2026-09-24", None),        # Wednesday before 18:00: not yet
    ("2026-09-24T10:00:00+04:00", "2026-09-24", "new"),       # Thursday
    ("2026-09-26T22:00:00+04:00", "2026-09-24", "new"),       # Saturday
    ("2026-09-27T10:00:00+04:00", "2026-09-24", None),        # Sunday: the week has moved on
])
def test_the_calendars_new_release_takes_slide_two(now, released, eye):
    day = now[:10]
    films = {"top": {"verdict": {"verdict": "yes"}}, "a": {"verdict": {"verdict": "yes"}, "backdrop": frame("a")},
             "new": {"verdict": {"verdict": "mixed"}, "released": released}}
    shows = [{"film": f, "date": day if f != "new" or eye != "eve" else released} for f in ("top", "top", "a", "new")]
    p = _pages(films, now, shows)
    slides = p.bill_slides(["top", "a", "new"])
    assert slides[0] == ("top", "top")
    assert slides[1] == (("new", eye) if eye else ("a", "on"))
    films["new"]["verdict"]["verdict"] = "skip"                # never «تجنّبه», even new
    assert ("new", eye) not in p.bill_slides(["top", "a", "new"])


# ---------------------------------------------------------------- the billboard's markup
def test_one_billboard_for_every_city_slide_one_the_uaes_top(out):
    for lang, parts, eye in (("ar", (), "الأكثر عرضاً الليلة"), ("en", ("en",), "Most shown tonight")):
        h = read(out, *parts)
        bill = bill_of(h)
        sl = slides_of(bill)
        assert [x[0] for x in sl] == ["fr", "fr", "fr", "fr"] and [bool(x[1]) for x in sl] == [True, False, False, False]
        fids = [re.search(r'href="/(?:en/)?film/([^/]+)/"', x[2]).group(1) for x in sl]
        assert fids == ["coyote-vs-acme", "resident-evil", "heart-of-the-beast", "shish-dou"]   # never crawlers or sacrifice («تجنّبه»)
        assert f'<p class="eyebrow">{eye}</p>' in sl[0][2]
        # no city in it: no per-city island, no «في دبي», nothing a first visitor's city could swap after paint
        assert 'id="bill-data"' not in h and "data-bill-a" not in bill and "دبي" not in bill and "Dubai" not in bill
        assert re.search(r'<body data-page="home"[^>]* data-hero>', h)


def test_only_slide_ones_picture_loads_with_the_page_and_it_is_preloaded(out):
    h = read(out)
    bill = bill_of(h)
    sl = slides_of(bill)
    assert re.search(r'<source media="\(max-width:767px\)" srcset="/posters/bd-coyote-vs-acme-9f8e7d6c5b-p\.webp"', sl[0][2])
    for x in sl[1:]:
        assert not re.search(r'\s(src|srcset)="', x[2]) and "data-src=" in x[2]
    assert h.count('fetchpriority="high"') == 3          # the phone's and the wider screen's preloads, and slide 1's picture
    head = h[:h.index("</head>")]
    assert '<link rel="preload" as="image" href="/posters/bd-coyote-vs-acme-9f8e7d6c5b-p.webp" media="(max-width:767px)" fetchpriority="high">' in head
    assert re.search(r'<link rel="preload" as="image" href="/posters/bd-coyote-vs-acme-0a1b2c3d4e-1280\.webp" imagesrcset="[^"]+" imagesizes="100vw" '
                     r'media="\(min-width:768px\)" fetchpriority="high">', head)


def test_each_slide_says_its_film_in_the_approved_order(out):
    bill = bill_of(read(out))
    one = slides_of(bill)[0][2]
    t = re.search(r'<h2 class="bill-t" style="--tsize:(\d+)px"><a href="/film/coyote-vs-acme/">([^<]+)</a></h2>', one)
    assert t and int(t.group(1)) == Kit.tsize(t.group(2))
    assert re.search(r'<p class="bill-v"><b class="v-yes">يستاهل\.</b> ', one)
    assert re.search(r'<p class="cta"><a class="btn velvet bill-go" href="/film/coyote-vs-acme/">الأوقات والأسعار <span class="from">من '
                     r'<span class="p" data-aed="\d+(\.\d\d)?" data-chain="[a-z]+"', one)
    # the order of the words: eyebrow, title, verdict, (the desktop's facts), the CTA
    assert one.index("eyebrow") < one.index("bill-t") < one.index("bill-v") < one.index("bill-f") < one.index("cta")
    # no verdict yet: the short line alone, no sentence (§1.7)
    last = slides_of(bill)[3][2]
    assert '<p class="bill-v"><b class="v-unknown">الحكم بعده</b></p>' in last
    # the trailer: an icon-only 48×48 button that says its one word to a screen reader
    tr = re.findall(r'<a class="btn ghost bill-tr" href="https://www\.youtube-nocookie\.com/embed/([^"]+)" data-trailer="\1"[^>]*aria-label="([^"]+)">', bill)
    assert tr and all(w == "الإعلان" for _, w in tr) and "العرض الترويجي" not in bill and ">Trailer<" not in bill
    # the card door: the screen's one door, the card sheet's; the indicators at its inline end
    foot = bill[bill.index('<div class="bill-foot">'):]
    assert re.search(r'<a class="door js-only" href="/cards/" data-sheet-open="sheet-card" data-bill-door[^>]*><span data-door-t>عندك بطاقة؟ شوف سعرك</span> ▾</a>', foot)
    dots = re.findall(r'<button type="button" aria-label="([^"]+)" aria-pressed="(true|false)"><i></i></button>', foot)
    assert len(dots) == 4 and [d[1] for d in dots] == ["true", "false", "false", "false"]
    assert foot.index("door") < foot.index("bill-nav")
    # the spill of slide 1's frame, on the first paint
    assert re.search(r'<section class="bill" data-bill [^>]*data-spill style="--sp1:#1E302C;--sp2:#151F20;--sp3:#4A5139;--sp4:#A38D53;">', bill)


def test_the_fog_is_gone_from_home_and_the_film_hero(out):
    for page in (read(out), read(out, "film", "sacrifice"), read(out, "film", "crawlers"), read(out, "film", "heart-of-the-beast")):
        assert 'class="bd pf"' not in page and 'class="pb"' not in page and 'class="ps"' not in page
    sheet = css("ui-bill") + css("ui-fhero")
    assert "blur(" not in sheet and "backdrop-filter" not in sheet and ".pf" not in sheet and "img.pb" not in sheet


def test_slide_one_that_is_skip_is_honest_and_has_no_price(tmp_path):
    def m(d):
        framed(d)
        for s in list(d["shows"]):
            if s["film"] == "crawlers": d["shows"].append(dict(s, time="23:59"))   # crawlers («تجنّبه») becomes tonight's top
    bill = bill_of(read(built(tmp_path, m)))
    one = slides_of(bill)[0][2]
    assert "/film/crawlers/" in one and '<b class="v-skip">تجنّبه.</b>' in one
    assert '<a class="btn velvet bill-go" href="/film/crawlers/">الأوقات</a>' in one and 'class="from"' not in one
    assert all("v-skip" not in x[2] for x in slides_of(bill)[1:])


def test_a_new_release_takes_slide_two_on_thursday_to_saturday(tmp_path):
    def m(d):
        framed(d)
        d["films"]["the-paradise"]["released"] = "2026-09-24"       # the fixture is built Friday 2026-09-25 18:00
    sl = slides_of(bill_of(read(built(tmp_path, m))))
    assert "/film/the-paradise/" in sl[1][2] and '<p class="eyebrow">جديد هالخميس</p>' in sl[1][2]
    assert sl[1][0] == "noimg" and "/film/the-paradise/" not in "".join(x[2] for x in sl[2:])


def test_the_film_hero_picture(tmp_path, plain):
    def m(d):
        framed(d)
        d["films"]["heart-of-the-beast"]["backdrop"] = frame("heart-of-the-beast", p="/posters/bd-heart-of-the-beast-1-p.webp", pw=536, ph=804)
    h = read(built(tmp_path, m), "film", "heart-of-the-beast")
    hero = h[h.index('<section class="fhero'):h.index('<section class="fsched"')]
    assert hero.startswith('<section class="fhero fr"><div class="fh-bd"><div class="bd fr"')
    assert '<source media="(max-width:767px)" srcset="/posters/bd-heart-of-the-beast-1-p.webp" width="536" height="804">' in hero
    assert 'sizes="100vw"' in hero and h.count('fetchpriority="high"') == 3      # two preloads (phone, wider) and the frame
    assert re.search(r'<div class="fposter"><span class="pst hero img"[^>]*>.*?loading="lazy"', hero)   # the card: not drawn on a phone
    # no frame, a poster: the lit field, and the card is the case (eager, the page's first poster, preloaded as drawn)
    h = read(plain, "film", "sacrifice")
    hero = h[h.index('<section class="fhero'):h.index('<section class="fsched"')]
    assert hero.startswith('<section class="fhero"><div class="fh-bd"><div class="bd lit" style="--pc:#')
    img = re.search(r'<div class="fposter"><span class="pst hero img"[^>]*>.*?(<img [^>]*>)', hero).group(1)
    assert 'fetchpriority="high"' in img and "loading=" not in img
    assert re.search(r'<link rel="preload" as="image" href="' + re.escape(re.search(r'src="([^"]+)"', img).group(1)) + r'"', h[:h.index("</head>")])
    # no frame and no poster: velvet light, and the title tile is the case
    h = read(plain, "film", "spider-man-brand-new-day")
    hero = h[h.index('<section class="fhero'):h.index('<section class="fsched"')]
    assert hero.startswith('<section class="fhero np"><div class="fh-bd"><div class="bd noimg"') and '<div class="fposter"><span class="pst hero"' in hero


@pytest.fixture(scope="module")
def plain(tmp_path_factory):
    return built(tmp_path_factory.mktemp("w2p1plain"))


def test_an_archived_film_has_a_hero_with_no_price_and_no_time(plain):
    for parts in (("film", "weapons"), ("en", "film", "weapons")):
        h = read(plain, *parts)
        i = h.index('<section class="fhero')
        hero = h[i:h.index("</section>", i)]
        assert 'class="bd ' in hero and 'class="p"' not in hero and "data-show" not in hero and "bill-go" not in hero and "data-aed" not in hero
        assert "fetchpriority" not in hero or 'class="pst hero' in hero


# ---------------------------------------------------------------- the stylesheet's numbers
def test_the_screens_sizes():
    b, f = css("ui-bill"), css("ui-fhero")
    assert ".bill{position:relative;block-size:clamp(440px,72svh,640px);margin-block-start:calc(-1 * (var(--head) + 1px))}" in b
    assert re.search(r"\.slide\{[^}]*display:grid;grid-template-rows:minmax\(0,1fr\) auto", b)
    case = re.search(r"\n\.case\{([^}]*)\}", b).group(1)
    for need in ("block-size:min(100%,clamp(180px,27svh,240px))", "aspect-ratio:2/3", "outline:1px solid var(--rule)", "outline-offset:8px",
                 "box-shadow:0 30px 120px -20px color-mix(in srgb,var(--pc) 60%,transparent)"):
        assert need in case, need
    assert ".bd.lit{background:radial-gradient(60% 45% at var(--cx,50%) 32%,color-mix(in srgb,var(--pc) 55%,var(--night)),var(--night) 72%)}" in b
    assert ".fhero.fr{min-block-size:clamp(360px,50svh,440px)}" in f and ".pst.hero{block-size:clamp(120px,20svh,180px)" in f
    assert ".fhero.fr .fposter{display:none}" in f
    # the CTA row: velvet, 48 px; the trailer a 48×48 icon on a phone (its word shows on a desktop)
    assert ".bill-go{flex:1 1 auto;min-inline-size:0;min-block-size:48px" in b and ".bill-tr{flex:0 0 48px;inline-size:48px;min-block-size:48px" in b
    assert ".bill-tr .tr-w{display:none}" in b
    # 44 px targets: the door, each indicator; the pause is the desktop's only
    assert re.search(r"\.door\{[^}]*min-block-size:44px", b) and re.search(r"\.dots button\{[^}]*block-size:44px", b)
    assert re.search(r"\.bill-pp\{display:none;inline-size:44px;block-size:44px", b)
    # no facts line on a phone
    phone = b[:b.index("@media (min-width:1024px)")]
    assert re.search(r"\.bill-f\{display:none", phone) and ".bill-f{display:flex}" in b[b.index("@media (min-width:1024px)"):]


def test_grain_frames_only_and_the_recede_only_with_motion():
    b = css("ui-bill")
    assert re.sub(r"/\*.*?\*/", "", b, flags=re.S).count("feTurbulence") == 1 and "baseFrequency='.9' numOctaves='2'" in b
    grain = re.search(r"\.bd\.fr::before\{([^}]*)\}", b).group(1)
    assert "opacity:.07" in grain and "feTurbulence" in grain and "animation" not in grain
    rec = b[b.index("@supports (animation-timeline:scroll())"):b.index("@keyframes bill-rec")]
    assert "@media (prefers-reduced-motion:no-preference)" in rec and "animation-timeline:scroll(root)" in rec and "animation-range:0 60vh" in rec
    assert "@keyframes bill-rec{to{transform:scale(.88)}}" in b and "@keyframes bill-lift{to{transform:translateY(-48px);opacity:0}}" in b
    assert "@keyframes bill-dim{from{opacity:0}to{opacity:.38}}" in b


def test_nothing_on_the_screen_starts_at_opacity_zero():
    """The LCP picture and title never start at opacity 0 (§1.3): on a phone no rule sets it on the screen's parts; on a
    desktop only the slides that are not showing are faded out, never slide 1 (the server marks it «on»)."""
    b = css("ui-bill")
    phone = re.sub(r"/\*.*?\*/", "", b[:b.index("@media (min-width:1024px)")], flags=re.S)
    phone = re.sub(r"@keyframes [a-z-]+\{[^{}]*(\{[^}]*\}[^{}]*)*\}", "", phone)   # the recede's keyframes run on the scroll, from 1
    zero = [r for r in re.findall(r"([^{}]+)\{[^}]*opacity:0[;}]", phone)]
    assert [z.strip() for z in zero] == [".bill-spill"], zero        # the spill (no content), lit only with a frame
    desk = b[b.index("@media (min-width:1024px)"):]
    assert ".slide{grid-area:1/1" in desk and ".slide.on{opacity:1;visibility:visible" in desk
    for f in ("ui-bill", "ui-fhero", "ui-lights"):
        assert not re.search(r"\.(bd|case|bill-t|ft|fhero|fposter)[^{]*\{[^}]*animation:[^}]*\bin\b", css(f))


def test_the_house_lights():
    li = css("ui-lights")
    assert ".lights{position:fixed;inset:0;z-index:90;background:var(--night);opacity:0;pointer-events:none;transition:opacity .45s var(--ease-house)}" in li
    assert ".lights.down{opacity:.92;transition-duration:.7s}" in li and ".trl-d::backdrop{background:transparent}" in li
    assert ".trl-d[open]{animation:trl-up .24s var(--ease-house) .1s both}" in li
    rm = li[li.index("@media (prefers-reduced-motion:reduce)"):]
    assert ".lights,.lights.down{transition:none}" in rm and ".trl-d[open]{animation:none}" in rm
    t = js("trailer")
    assert "houseLights(true)" in t and "houseLights(false)" in t and "TX.bill_tr" in t


def test_a_phone_keeps_the_poster_morph():
    # both names live in transitions.css, the one file @view-transition is allowed in (test_feel.py asserts a
    # core-only build carries none of it): ui-fhero.css only draws .fhero.fr .fposter{display:none} so the case
    # never competes with the frame for the name
    f = re.sub(r"/\*.*?\*/", "", css("ui-fhero"), flags=re.S)
    assert ".fhero.fr .fposter{display:none}" in f and "view-transition" not in f
    t = open(os.path.join(SRC, "css", "transitions.css"), encoding="utf-8").read()
    assert "@media (max-width:1023px) and (prefers-reduced-motion:no-preference){\n  body[data-page=film] .fhero.fr .fh-bd{view-transition-name:poster}\n}" in t
    assert "body[data-page=film] .fposter .pst.hero{view-transition-name:poster}" in t


# ---------------------------------------------------------------- the scripts
def test_bill_js_reads_no_scroll_maths_and_has_no_phone_clock():
    b = re.sub(r"/\*.*?\*/", "", js("bill"), flags=re.S)
    assert "scrollLeft" not in b and "scrollX" not in b and "IntersectionObserver" in b
    assert "BILL_PHONE_ROTATE = false" in b and "saveData" in b and "requestIdleCallback" in b
    assert "innerHTML" in b and b.count("innerHTML") == 2        # billInsert's parse and a new indicator only; no slide is ever rewritten
    assert "#bill-data" not in b and "billShow" not in b and "billFrame" not in b     # the per-city island and the swap are gone


BILL_HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function run(desk, flag, rm) {
  let intervals = 0;
  const ctx = { RM: rm, card: "", C: {}, D: null, qa: () => [], q: () => null, sub: (s) => s,
    setInterval: () => { intervals++; return 1; }, clearInterval: () => {}, navigator: {}, document: {}, window: {} };
  vm.createContext(ctx);
  vm.runInContext(src + "\nBILL_PHONE_ROTATE = " + flag + ";", ctx);
  const slides = [{}, {}, {}];
  ctx.qa = (s) => (s === ".slide" ? slides : []);
  ctx.BILL = { box: {}, strip: {}, i: 0, t: null, desk, touched: false, hold: { user: false, hover: false, focus: false, hidden: false, off: false } };
  vm.runInContext("billClock()", ctx);
  const paused = vm.runInContext("billPaused()", ctx);
  ctx.BILL.hold.off = true;
  const pausedOff = vm.runInContext("billPaused()", ctx);
  ctx.BILL.hold.off = false; ctx.BILL.touched = true;
  const pausedTouched = vm.runInContext("billPaused()", ctx);
  const ins = vm.runInContext("billInsert('<div class=\"slide\"></div>')", Object.assign(ctx, { document: { createElement: () => ({ set innerHTML(v) {}, firstElementChild: null }) } }));
  return { intervals, paused, pausedOff, pausedTouched, ins };
}
console.log(JSON.stringify({ phone: run(false, false, false), desk: run(true, false, false), deskRM: run(true, false, true), flag: run(false, true, false) }));
"""


@needs_node
def test_the_turn_is_the_desktops_only(tmp_path):
    h = tmp_path / "h.cjs"; h.write_text(BILL_HARNESS, encoding="utf-8")
    r = subprocess.run([NODE, str(h), os.path.join(SRC, "js", "bill.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["phone"]["intervals"] == 0 and o["phone"]["paused"] is True           # D3: a phone never turns by itself
    assert o["desk"]["intervals"] == 1 and o["desk"]["paused"] is False and o["desk"]["pausedOff"] is True   # paused off screen
    assert o["deskRM"]["intervals"] == 0 and o["deskRM"]["paused"] is True          # never under reduced motion
    assert o["flag"]["intervals"] == 1 and o["flag"]["pausedTouched"] is True       # the flag: the approved turn until a touch
    assert o["phone"]["ins"] is False                                               # billInsert: a desktop's only


DOOR_HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const read = (f) => fs.readFileSync(f, "utf8");
const [bill, disc, prices] = process.argv.slice(2).map(read);
const attrs = { "data-no": "عندك بطاقة؟ شوف سعرك", "data-yes": "السعر بعد خصم {card}", "data-not": "ما في خصم {card} في {chain}" };
const t = { textContent: "عندك بطاقة؟ شوف سعرك" };
const door = { getAttribute: (k) => attrs[k] };
const cell = { getAttribute: (k) => ({ "data-aed": "42", "data-chain": "vox", "data-hall": "Standard", "data-hk": "Standard", "data-cin": "vox-moe" })[k] };
function run(cardId, D) {
  const ctx = { RM: false, card: cardId, C: { cards: { fazaa: "فزعة" } }, D, TODAY: "2026-09-25", TX: {}, esc: (s) => s,
    sub: (s, o) => s.replace(/\{(\w+)\}/g, (m, k) => o[k]), chainName: (c) => ({ vox: "فوكس" })[c] || c,
    q: (s) => (s === "[data-bill-door]" ? door : s === "[data-door-t]" ? t : s === ".bill-go .p[data-aed]" ? cell : null),
    qa: (s) => (s === ".slide" ? [{}] : []) };
  vm.createContext(ctx);
  vm.runInContext(disc + "\n" + prices + "\n" + bill, ctx);
  ctx.BILL = { box: {}, strip: {}, i: 0 };
  t.textContent = "عندك بطاقة؟ شوف سعرك";
  vm.runInContext("billDoor()", ctx);
  return t.textContent;
}
const ok = { rules: { vox: { fazaa: { type: "percent", value: 20, status: "ok" } } } };
const none = { rules: { vox: { fazaa: { status: "none_found" } } } };
console.log(JSON.stringify({ nocard: run("", null), before: run("fazaa", null), yes: run("fazaa", ok), not: run("fazaa", none) }));
"""


@needs_node
def test_the_card_door_says_what_the_card_does_at_that_price(tmp_path):
    h = tmp_path / "d.cjs"; h.write_text(DOOR_HARNESS, encoding="utf-8")
    r = subprocess.run([NODE, str(h)] + [os.path.join(SRC, "js", n + ".js") for n in ("bill", "disc", "prices")],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o == {"nocard": "عندك بطاقة؟ شوف سعرك", "before": "عندك بطاقة؟ شوف سعرك",   # the card's rules not in yet: unchanged
                 "yes": "السعر بعد خصم فزعة", "not": "ما في خصم فزعة في فوكس"}


def test_the_billboard_costs_less_html_than_before(out):
    assert len(read(out).encode()) < 150_000 and len(read(out, "en").encode()) < 150_000
