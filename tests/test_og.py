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
    assert r1["rendered"] == 2 and r1["skipped"] == 0        # ar + en
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
    assert name2 != name1 and r2["rendered"] == 2
    assert r2["cities"]["test-film"] == "dubai"                # 2 of 3 shows are in Dubai
    assert not (cache / "og" / name1).exists()                 # the stale render is pruned


def test_archived_film_gets_the_no_price_variant(cache):
    data = _data(archived=True)
    r = og_step.run(data, {"data_dir": str(cache), "now": data["generated"]})
    assert r["rendered"] == 2
    assert data["films"]["test-film"]["og"]
    assert "test-film" not in r["cities"]         # an archived film never gets a price/city line


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
    assert '<p class="pshare">' in html and 'data-share-url="' in html


def _node(tmp_path, search, script):
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
    src = stub + share + "\n" + script
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
