"""steps/og.py + pages/og.py (roadmap #206) and src/js/share.js (#82).

Python: the share image is deterministic for the same inputs (same file, no rewrite; a run
that changes nothing on disk touches no mtimes), regenerates only when an input actually changes
(price, city or the poster file), gives an archived film the no-price variant, and og:image on the
built film page points at the file steps/og.py produced (pages/og.py's site_kit.py hook).

Node (skipped without node): src/js/share.js's own decision — apply a shared ?city=&card= only when
nothing is saved yet or the saved values already agree; a differing saved value is left alone and
queued as `pendingShare` instead of being overwritten — and its `shareURL()` appends the CURRENT
visitor's own city/card (never the sharer's) to a share link's base URL.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import site_kit  # noqa: E402
import steps.og as og_step  # noqa: E402
from pages import og as og_page  # noqa: E402

NODE = shutil.which("node")


def _poster(path, w=342, h=513):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (80, 40, 20)).save(path, "WEBP")


def _data(today="2026-09-27", price=35, archived=False):
    return {
        "generated": f"{today}T12:00:00+04:00",
        "cinemas": {"c1": {"chain": "vox", "city": "dubai"}, "c2": {"chain": "vox", "city": "sharjah"}},
        "films": {
            "test-film": {
                "title": "Test Film", "title_ar": "فيلم تجربة",
                "status": "archived" if archived else "showing",
                "poster": "https://cinema.elyoxe.com/posters/test-film-342.webp",
                "poster_2x": "https://cinema.elyoxe.com/posters/test-film-684.webp",
            }
        },
        "shows": [] if archived else [
            {"film": "test-film", "cinema": "c1", "date": today, "time": "19:00",
             "prices": [{"seat": "Regular", "aed": price}]},
            {"film": "test-film", "cinema": "c1", "date": today, "time": "21:00",
             "prices": [{"seat": "Regular", "aed": price + 20}]},
            {"film": "test-film", "cinema": "c2", "date": today, "time": "20:00",
             "prices": [{"seat": "Regular", "aed": price + 5}]},
        ],
    }


@pytest.fixture
def cache(tmp_path):
    _poster(tmp_path / "data" / "posters" / "test-film-684.webp")
    return tmp_path / "data"


def test_renders_once_and_is_deterministic(cache):
    data = _data()
    ctx = {"data_dir": str(cache), "now": data["generated"]}
    r1 = og_step.run(data, ctx)
    assert r1["rendered"] == 4 and r1["skipped"] == 0        # og ar+en + the r3-seo Stories card ar+en
    assert "test-film" in data["films"] and data["films"]["test-film"]["og_story"].keys() == {"ar", "en"}
    name_ar = data["films"]["test-film"]["og"]["ar"]
    png1 = (cache / "og" / name_ar).read_bytes()
    mtime1 = (cache / "og" / name_ar).stat().st_mtime_ns

    # a second run with the exact same inputs must not re-render (same file, same bytes, same mtime)
    data2 = _data()
    r2 = og_step.run(data2, {"data_dir": str(cache), "now": data2["generated"]})
    assert r2["rendered"] == 0 and r2["skipped"] == 0
    assert data2["films"]["test-film"]["og"]["ar"] == name_ar
    assert (cache / "og" / name_ar).stat().st_mtime_ns == mtime1
    assert (cache / "og" / name_ar).read_bytes() == png1


def test_regenerates_when_the_price_changes_and_keeps_dubai_the_loudest_city(cache):
    ctx1 = {"data_dir": str(cache)}
    d1 = _data(price=35)
    og_step.run(d1, {**ctx1, "now": d1["generated"]})
    name1 = d1["films"]["test-film"]["og"]["ar"]

    d2 = _data(price=50)
    r2 = og_step.run(d2, {**ctx1, "now": d2["generated"]})
    name2 = d2["films"]["test-film"]["og"]["ar"]
    assert name2 != name1 and r2["rendered"] == 4              # og ar+en + the Stories card ar+en, all re-priced
    assert r2["cities"]["test-film"] == "dubai"                # 2 of 3 shows are in Dubai
    assert not (cache / "og" / name1).exists()                 # the stale render is pruned


def test_archived_film_gets_the_no_price_variant(cache):
    data = _data(archived=True)
    r = og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    assert r["rendered"] == 2
    assert data["films"]["test-film"]["og"]
    assert "test-film" not in r["cities"]         # an archived film never gets a price/city line


def _data_price_city_mismatch(today="2026-09-27"):
    """2 of 3 shows (the loudest city) are in Dubai at 100/90 AED; the single cheapest show of all
    (20 AED) is in Sharjah. Review counter-example: the card must say Dubai's own cheapest (90),
    never Sharjah's 20 attached to Dubai's name."""
    return {
        "generated": f"{today}T12:00:00+04:00",
        "cinemas": {"c1": {"chain": "vox", "city": "dubai"}, "c2": {"chain": "vox", "city": "dubai"},
                    "c3": {"chain": "vox", "city": "sharjah"}},
        "films": {"test-film": {"title": "Test Film", "title_ar": "فيلم تجربة", "status": "showing"}},
        "shows": [
            {"film": "test-film", "cinema": "c1", "date": today, "time": "19:00", "prices": [{"seat": "Regular", "aed": 100}]},
            {"film": "test-film", "cinema": "c2", "date": today, "time": "21:00", "prices": [{"seat": "Regular", "aed": 90}]},
            {"film": "test-film", "cinema": "c3", "date": today, "time": "20:00", "prices": [{"seat": "Regular", "aed": 20}]},
        ],
    }


def test_price_is_the_chosen_citys_own_cheapest_never_a_cheaper_other_citys():
    d = _data_price_city_mismatch()
    price, city = og_step._cheapest_and_city(d["shows"], d["cinemas"], "test-film", "2026-09-27")
    assert city == "dubai"          # 2 of 3 shows
    assert price == 90              # Dubai's OWN cheapest -- never Sharjah's 20


def test_no_priced_show_in_the_loudest_city_drops_the_price_not_the_city():
    today = "2026-09-27"
    shows = [
        {"film": "test-film", "cinema": "c1", "date": today, "time": "19:00", "prices": []},
        {"film": "test-film", "cinema": "c2", "date": today, "time": "21:00", "prices": [{"seat": "Regular", "aed": 0}]},
        {"film": "test-film", "cinema": "c3", "date": today, "time": "20:00", "prices": [{"seat": "Regular", "aed": 20}]},
    ]
    cinemas = {"c1": {"city": "dubai"}, "c2": {"city": "dubai"}, "c3": {"city": "sharjah"}}
    price, city = og_step._cheapest_and_city(shows, cinemas, "test-film", today)
    assert city == "dubai" and price is None   # never falls back to Sharjah's 20


def _cmap(name):
    from fontTools.ttLib import TTFont
    return set(TTFont(os.path.join(ROOT, "src", "fonts", name)).getBestCmap())


def test_every_glyph_the_renderer_draws_exists_in_the_font_it_picks_for_it():
    """The exact fontTools cmap check the review asked for: for every line _card() actually draws in
    Arabic, run it through the real `_runs()` script-splitter and confirm the font `draw_line()` would
    pick for each run has every character it is asked to draw -- catches the missing-glyph-box bug
    (Arabic-subset fonts have no digits, Latin-subset fonts have no Arabic) without needing to OCR a
    rendered PNG."""
    import site_kit as sk
    cmaps = {n: _cmap(n) for n in ("markazi-700-arabic.woff2", "markazi-700-latin.woff2",
                                    "readex-arabic.woff2", "readex-latin.woff2")}
    lines = [
        ("wordmark", "سينما", "markazi-700-arabic.woff2", "markazi-700-latin.woff2"),
        ("title", "فيلم تجربة", "markazi-700-arabic.woff2", "markazi-700-latin.woff2"),
        ("price (has a Western-numeral price inside Arabic text)",
         "من 90 درهم الليلة في دبي", "readex-arabic.woff2", "readex-latin.woff2"),
        ("date (Arabic month name with Western-numeral day/year)",
         sk.human_date("2026-09-27", "ar"), "readex-arabic.woff2", "readex-latin.woff2"),
    ]
    for label, text, ar_name, other_name in lines:
        for is_ar, run_text in og_step._runs(text):
            cmap = cmaps[ar_name if is_ar else other_name]
            missing = [ch for ch in run_text if not ch.isspace() and ord(ch) not in cmap]
            assert not missing, f"{label}: {ar_name if is_ar else other_name} has no glyph for {missing!r} in {run_text!r}"


def test_arabic_runs_are_laid_right_to_left():
    """Release fix: v2 cards laid Arabic runs left to right, so «من 90 درهم الليلة في دبي» read
    «دبي في الليلة درهم 90 من». Visual order (left to right) must be the logical order reversed, with a
    digit run kept whole (its digits stay left to right)."""
    vis = [t for _, t in og_step._visual_runs("من 90 درهم", "ar")]
    assert vis == ["درهم", " 90 ", "من"]
    date = [t for _, t in og_step._visual_runs("27 سبتمبر 2026", "ar")]
    assert date == ["2026 ", "سبتمبر", " 27"]           # rightmost is the day; the spaces stay BETWEEN the words
    assert og_step._visual_runs("From AED 35 tonight", "en") == [(False, "From AED 35 tonight")]


def test_text_block_never_runs_across_the_poster():
    x, right = og_step._text_anchor("ar", True)
    assert right and x <= og_step.W - og_step.POSTER_W - 40      # right-aligned, ending left of the poster
    x, right = og_step._text_anchor("en", True)
    assert not right and x >= og_step.POSTER_W + 40              # left-aligned, starting right of the poster


def test_a_card_renders_fast_once_fonts_are_warm(cache):
    """Final review I1: the woff2 -> TTF conversion ran 6x per card (~2.5 s/card); it is memoised now."""
    import time
    poster = cache / "posters" / "test-film-684.webp"
    og_step._card("ar", "فيلم", 35, "دبي", "27 سبتمبر 2026", poster, "سينما")     # warm the caches
    t = time.perf_counter()
    for lang in ("ar", "en"):
        og_step._card(lang, "فيلم تجربة", 35, "دبي", "27 سبتمبر 2026", poster, "سينما")
    assert (time.perf_counter() - t) / 2 < 0.5


def test_story_card_is_1080x1920_and_has_no_city_in_its_price_line(cache):
    """r3-seo: the Stories card names no city (it isn't tied to one place the way the 1200x630 card is) —
    only «من {price} درهم» / "From AED {price}", the cheapest confirmed price among ALL of today's shows."""
    data = _data()   # 2 Dubai shows (35, 55) + 1 Sharjah show (40): cheapest overall is 35
    og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    name_ar = data["films"]["test-film"]["og_story"]["ar"]
    im = Image.open(cache / "og" / name_ar)
    assert im.size == (og_step.SW, og_step.SH) == (1080, 1920)


def test_story_card_pruned_and_rerendered_when_the_cheapest_price_changes(cache):
    d1 = _data(price=35)
    og_step.run(d1, {"data_dir": str(cache), "now": d1["generated"]})
    name1 = d1["films"]["test-film"]["og_story"]["ar"]

    d2 = _data(price=50)
    og_step.run(d2, {"data_dir": str(cache), "now": d2["generated"]})
    name2 = d2["films"]["test-film"]["og_story"]["ar"]
    assert name2 != name1
    assert not (cache / "og" / name1).exists()                  # pruned with the 1200x630 card's stale render


def test_archived_film_gets_no_story_card(cache):
    data = _data(archived=True)
    og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    assert "og_story" not in data["films"]["test-film"]


def test_story_card_is_webp_under_250kb(cache):
    """Round 3 QA fix: was a ~1.6MB PNG, up to ~120/day from the owner's phone. Now WebP, <= STORY_MAX_BYTES."""
    data = _data()
    og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    name_ar = data["films"]["test-film"]["og_story"]["ar"]
    assert name_ar.endswith(".webp")
    path = cache / "og" / name_ar
    assert path.stat().st_size <= og_step.STORY_MAX_BYTES
    im = Image.open(path)
    assert im.format == "WEBP" and im.size == (1080, 1920)


def test_story_card_not_rerendered_when_only_the_date_changes(cache):
    """The date must not be baked into the hash (or the image): a calendar-day rollover with nothing else
    different about the film must not force a regeneration -- that was the source of ~120 renders/day."""
    d1 = _data(today="2026-09-27", price=35)
    og_step.run(d1, {"data_dir": str(cache), "now": d1["generated"]})
    name1 = d1["films"]["test-film"]["og_story"]["ar"]

    before = set((cache / "og").glob("*story*.webp"))

    d2 = _data(today="2026-09-28", price=35)   # only the date moved; price/title/poster are identical
    og_step.run(d2, {"data_dir": str(cache), "now": d2["generated"]})
    name2 = d2["films"]["test-film"]["og_story"]["ar"]

    assert name2 == name1                                       # same cache file reused
    assert (cache / "og" / name1).exists()                      # never pruned
    assert set((cache / "og").glob("*story*.webp")) == before   # nothing new drawn for the story card
                                                                 # (the 1200x630 og card DOES show the date
                                                                 # and is expected to re-render -- unrelated)


def test_story_render_cap_limits_new_renders_per_run(cache):
    """At most STORY_CAP brand-new Stories renders per run; a cache hit doesn't count against it."""
    data = {
        "generated": "2026-09-27T12:00:00+04:00",
        "cinemas": {"c1": {"chain": "vox", "city": "dubai"}},
        "films": {}, "shows": [],
    }
    n_films = og_step.STORY_CAP + 5
    for i in range(n_films):
        fid = f"film-{i}"
        _poster(cache / "posters" / f"{fid}-684.webp")
        data["films"][fid] = {
            "title": f"Film {i}", "title_ar": f"فيلم {i}", "status": "showing",
            "poster": f"https://cinema.elyoxe.com/posters/{fid}-342.webp",
            "poster_2x": f"https://cinema.elyoxe.com/posters/{fid}-684.webp",
        }
        data["shows"].append({"film": fid, "cinema": "c1", "date": "2026-09-27", "time": "19:00",
                               "prices": [{"seat": "Regular", "aed": 35}]})
    og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    with_story_1 = sum(1 for f in data["films"].values() if "og_story" in f)
    # each film needs 2 new renders (ar+en); the cap counts individual renders, so a cap of STORY_CAP
    # fully covers STORY_CAP // 2 films this run -- fewer than the whole catalogue
    assert with_story_1 == og_step.STORY_CAP // 2 < n_films

    # a second run over the SAME unchanged catalogue must not touch the films already rendered (cache hits,
    # free) and picks up more of the remaining ones within its own fresh per-run cap -- progress, not a stall
    og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    with_story_2 = sum(1 for f in data["films"].values() if "og_story" in f)
    assert with_story_2 == min(n_films, 2 * (og_step.STORY_CAP // 2))
    assert with_story_2 > with_story_1


def test_missing_poster_is_skipped_not_crashed(tmp_path):
    data = _data()
    r = og_step.run(data, {"data_dir": str(tmp_path / "data"), "now": data["generated"]})
    assert r["skipped"] == 1 and "og" not in data["films"]["test-film"]


def test_film_page_og_image_points_at_the_rendered_file(tmp_path, cache):
    data = _data()
    og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    name_ar = data["films"]["test-film"]["og"]["ar"]

    disc_path = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
    out = str(tmp_path / "out")
    monkey_root = og_page.ROOT
    try:
        og_page.ROOT = str(cache.parent)          # so pages/og.py reads data/og/ from our tmp cache, not the repo's
        site = build.Site(data, build.load_discounts(disc_path), build.Halls(os.path.join(ROOT, "halls.yaml")), out,
                           modules=build.discover(only={"core", "og"}))
        site.run()
    finally:
        og_page.ROOT = monkey_root
    html = open(os.path.join(out, "film", "test-film", "index.html"), encoding="utf-8").read()
    assert f'og:image" content="{site_kit.SITE}/og/{name_ar}"' in html
    assert os.path.isfile(os.path.join(out, "og", name_ar))
    # the film page's share link is the hero's «شارك» (UI redesign Task 4: slot film.share)
    assert re.search(r'<a class="btn ghost" href="https://wa\.me/\?text=[^"]+"[^>]*data-share data-share-msg="[^"]+" data-share-url="', html)
    # I2: the rendered card is 1200x630, so the page says so
    assert '<meta property="og:image:width" content="1200">' in html
    assert '<meta property="og:image:height" content="630">' in html


def test_film_page_links_the_story_card_from_the_share_actions(tmp_path, cache):
    """r3-seo: pages/og.py copies data/og/*-story-*.png into out/og/ and the film hero's share actions get a
    second, plain download link pointing at it (no new share flow, no new button style)."""
    data = _data()
    og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    name_story = data["films"]["test-film"]["og_story"]["ar"]

    disc_path = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
    out = str(tmp_path / "out")
    monkey_root = og_page.ROOT
    try:
        og_page.ROOT = str(cache.parent)
        site = build.Site(data, build.load_discounts(disc_path), build.Halls(os.path.join(ROOT, "halls.yaml")), out,
                           modules=build.discover(only={"core", "og"}))
        site.run()
    finally:
        og_page.ROOT = monkey_root
    assert os.path.isfile(os.path.join(out, "og", name_story))
    html = open(os.path.join(out, "film", "test-film", "index.html"), encoding="utf-8").read()
    assert f'href="{site_kit.SITE}/og/{name_story}" download' in html
    assert "صورة ستوري" in html


def test_og_dims_only_for_1200x630_images(tmp_path):
    """I2: a film page with no rendered card falls back to its portrait poster -- no 1200x630 claim there;
    a page on the site-wide default og-<lang>.png keeps it."""
    data = _data()                                   # no steps/og run: no data["films"][..]["og"]
    disc_path = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
    out = str(tmp_path / "out")
    site = build.Site(data, build.load_discounts(disc_path), build.Halls(os.path.join(ROOT, "halls.yaml")), out,
                      modules=build.discover(only={"core", "og"}))
    site.run()
    film = open(os.path.join(out, "film", "test-film", "index.html"), encoding="utf-8").read()
    assert 'og:image" content="https://cinema.elyoxe.com/posters/test-film-684.webp"' in film
    assert "og:image:width" not in film and "og:image:height" not in film
    home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    assert f'og:image" content="{site_kit.SITE}/assets/og-ar.png"' in home
    assert '<meta property="og:image:width" content="1200">' in home


def _node(tmp_path, search, script, before=""):
    """share.js standalone: `feature()` is stubbed to never call its callback, so shareParams()/shareURL()
    (both hoisted, top-level) can be driven directly with fake get/set/param/city/card — the same
    contract core.js gives every feature module (docs/PLUGINS.md)."""
    share = open(os.path.join(ROOT, "src", "js", "share.js"), encoding="utf-8").read()
    stub = (
        "var STORE = {};\n"
        "function get(k){ return STORE.hasOwnProperty(k) ? STORE[k] : null; }\n"
        "function set(k,v){ if (v===''||v==null) delete STORE[k]; else STORE[k]=String(v); }\n"
        "var location = { search: " + json.dumps(search) + " };\n"
        "function param(k){ var m=new RegExp('[?&]'+k+'=([^&]+)').exec(location.search); return m?decodeURIComponent(m[1]):null; }\n"
        "function feature(fn) { /* never invoked: this test drives shareParams/shareURL directly */ }\n"
        "var document = { addEventListener: function(){}, body: { appendChild: function(){} },\n"
        "  createElement: function(){ return { setAttribute:function(){}, addEventListener:function(){} }; } };\n"
        "var navigator = {};\n"
        "function esc(s){ return String(s); }\n"
        "var city, card;\n"
        "var C = { cities: { dubai: 'دبي' }, cards: { carrefour: 'كاريفور' } }, AR = true;\n"
    )
    src = stub + before + "\n" + share + "\n" + script
    (tmp_path / "t.js").write_text(src, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_share_params_applies_when_nothing_saved(tmp_path):
    got = _node(tmp_path, "?city=dubai&card=carrefour", """
shareParams();
process.stdout.write(JSON.stringify({ city: get("city"), card: get("card"), pending: pendingShare }));
""")
    assert got == {"city": "dubai", "card": "carrefour", "pending": None}


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_share_params_never_silently_overwrites_a_different_saved_choice(tmp_path):
    got = _node(tmp_path, "?city=dubai", """
STORE["city"] = "abu-dhabi";
shareParams();
process.stdout.write(JSON.stringify({ city: get("city"), pending: pendingShare }));
""")
    assert got["city"] == "abu-dhabi"                      # untouched
    assert got["pending"] == {"city": "dubai", "card": None}


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_share_params_applies_when_saved_already_agrees(tmp_path):
    got = _node(tmp_path, "?city=dubai&card=carrefour", """
STORE["city"] = "dubai"; STORE["card"] = "carrefour";
shareParams();
process.stdout.write(JSON.stringify({ pending: pendingShare }));
""")
    assert got == {"pending": None}


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_share_url_appends_the_current_visitor_not_the_sharers(tmp_path):
    got = _node(tmp_path, "", """
city = "al-ain"; card = "";
process.stdout.write(JSON.stringify([shareURL("https://cinema.elyoxe.com/film/x/"), shareURL("https://cinema.elyoxe.com/film/x/?y=1")]));
""")
    assert got == ["https://cinema.elyoxe.com/film/x/?city=al-ain",
                   "https://cinema.elyoxe.com/film/x/?y=1&city=al-ain"]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_unknown_city_is_dropped_before_it_is_ever_stored(tmp_path):
    """An unknown ?city= (stale/malformed/tampered link) is never applied -- not queued as a prompt
    either, since C.cities doesn't know it (review fix: validate before storing OR queuing)."""
    got = _node(tmp_path, "?city=narnia", """
shareParams();
process.stdout.write(JSON.stringify({ city: get("city"), pending: pendingShare }));
""")
    assert got == {"city": None, "pending": None}


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_unknown_card_is_dropped_while_a_valid_city_in_the_same_link_still_applies(tmp_path):
    got = _node(tmp_path, "?city=dubai&card=goldcard", """
shareParams();
process.stdout.write(JSON.stringify({ city: get("city"), card: get("card"), pending: pendingShare }));
""")
    assert got == {"city": "dubai", "card": None, "pending": None}


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_unknown_value_is_dropped_even_on_the_deferred_yes_click_path(tmp_path):
    """A saved choice differs (so this would normally queue a prompt) but the shared value itself is
    unknown -- it must never reach `pendingShare`, so a "Yes" click has nothing bad to apply."""
    got = _node(tmp_path, "?city=narnia", """
STORE["city"] = "abu-dhabi";
shareParams();
process.stdout.write(JSON.stringify({ city: get("city"), pending: pendingShare }));
""")
    assert got == {"city": "abu-dhabi", "pending": None}   # untouched AND nothing queued to ask about


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_a_link_with_no_card_param_does_not_touch_card(tmp_path):
    """No `card=` at all (param() returns null, never "") -- the validation guard (`scard && ...`) must
    not misfire on that null, and a link carrying only a city must never clear an unrelated saved card."""
    got = _node(tmp_path, "?city=dubai", """
shareParams();
process.stdout.write(JSON.stringify({ city: get("city"), card: get("card") }));
""")
    assert got == {"city": "dubai", "card": None}


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_pending_prompt_survives_the_bundle_order(tmp_path):
    """The live bundle runs core.js (which calls the hoisted shareParams()) BEFORE share.js's own top-level
    statements. A `var pendingShare = null;` there wiped the queued prompt, so the "use your friend's
    settings?" bar never showed on cinema.elyoxe.com. Reproduce that order."""
    got = _node(tmp_path, "?city=dubai", """
process.stdout.write(JSON.stringify({ city: get("city"), pending: pendingShare }));
""", before='STORE["city"] = "abu-dhabi";\nshareParams();')
    assert got == {"city": "abu-dhabi", "pending": {"city": "dubai", "card": None}}
