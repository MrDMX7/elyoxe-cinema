"""Feel (roadmap 203, 204, 138): the speculation rules and their exclusions on every page, the view transitions
(off under reduced motion, only in the full build), the manifest shortcuts and their icons, and — in node —
that a prerendered page's features wait for activation and that data saver drops the rules."""
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

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
NODE = shutil.which("node")
PRERENDER = ["/film/*", "/en/film/*"]


def read(out, *p):
    return open(os.path.join(out, *p), encoding="utf-8").read()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """core + this module only: the other feature modules are not this test's business."""
    out = str(tmp_path_factory.mktemp("feel"))
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=("core", "feel")))
    return out


@pytest.fixture(scope="module")
def core_only(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("feelcore"))
    build.build(DATA, DISC, out, noindex=False, modules=build.discover(only=("core",)))
    return out


def rules(html):
    m = re.search(r'<script type="speculationrules" id="spec">(.*?)</script>', html, re.S)
    assert m, "no speculation rules"
    return json.loads(m.group(1))


def pages(out):
    for dp, _, fs in os.walk(out):
        for f in fs:
            if f.endswith(".html"): yield os.path.join(dp, f)


def test_every_page_carries_the_rules_in_its_head(site):
    n = 0
    for p in pages(site):
        h = open(p, encoding="utf-8").read()
        if 'rel="canonical"' not in h: continue          # offline.html is standalone, not from the template
        head = h[:h.index("</head>")]
        assert head.count('type="speculationrules"') == 1, p
        rules(head); n += 1
    assert n > 20


def test_prerender_only_film_pages_on_moderate_prefetch_the_rest(site):
    r = rules(read(site, "index.html"))
    (pre,), (pf,) = r["prerender"], r["prefetch"]
    assert pre["eagerness"] == pf["eagerness"] == "moderate"          # hover (200 ms) or pointerdown, never on load
    assert pre["where"]["and"][0] == {"href_matches": PRERENDER}
    # a link carrying state (?city=, ?card=, ?now=) never prerenders: city/card params write the visitor's choice
    no = pre["where"]["and"][1]["not"]["selector_matches"]
    assert "[href*='?']" in no and "[target]" in no and "[download]" in no and "[data-nospec]" in no
    assert pf["where"]["and"][0] == {"href_matches": "/*"}
    skip = pf["where"]["and"][1]["not"]["href_matches"]
    # city and cinema pages are prefetched only: their script saves the page's city on load (core.js), so a
    # prerender on hover would change the visitor's city without a tap; files and data are never fetched ahead
    for p in PRERENDER + ["/data/*", "/assets/*", "/posters/*", "/*.*"]:
        assert p in skip, p


def test_data_saver_and_back_type_script_follows_the_rules(site):
    h = read(site, "en", "index.html")
    i = h.index('id="spec"')
    guard = h[i:h.index("</script>", h.index("</script>", i) + 1)]
    assert "saveData" in guard and "prefers-reduced-data: reduce" in guard and 'getElementById("spec")' in guard
    assert "pagereveal" in guard and '"traverse"' in guard and 'types.add("back")' in guard


def test_view_transitions_only_without_reduced_motion_and_only_in_the_full_build(site, core_only):
    css = read(site, "assets", "cinema.css")
    m = re.search(r"@media \(prefers-reduced-motion:no-preference\)\{(.*)", css, re.S)
    assert m and "@view-transition{navigation:auto}" in m.group(1)
    assert css.count("@view-transition") == 1                          # never outside that media query
    assert "body[data-page=film] .fposter .pst.hero{view-transition-name:poster}" in m.group(1)
    assert ":root[dir=rtl]{--vt-x:14px}" in css and ":root{--vt-x:-14px}" in css   # RTL slides the other way
    assert "view-transition" not in read(core_only, "assets", "cinema.css")


def test_manifest_shortcuts_and_their_icons(site):
    m = json.loads(read(site, "manifest.webmanifest"))
    sc = m["shortcuts"]
    assert [(s["name"], s["url"]) for s in sc] == [("الحين", "/#now"), ("نازل الخميس", "/coming/"), ("قائمتي", "/#mine")]
    for s in sc:
        assert s["short_name"] and s["description"] and len(s["short_name"]) <= 12
        (ic,) = s["icons"]
        f = os.path.join(site, *ic["src"].strip("/").split("/"))
        with Image.open(f) as im:
            assert im.format == "PNG" and f"{im.width}x{im.height}" == ic["sizes"] == "192x192"


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_features_wait_for_a_prerendered_page_to_be_shown(tmp_path):
    feel = open(os.path.join(ROOT, "src", "js", "feel.js"), encoding="utf-8").read()
    harness = """
var L = {}, FEAT = [], ran = [];
var document = { prerendering: true, addEventListener: function (t, f) { (L[t] = L[t] || []).push(f); } };
var window = {}, RM = false, page = "home", body = null, q = function () { return null; };
function feature(fn) { FEAT.push(fn); }
""" + feel + """
feature(function () { ran.push("geo"); });
FEAT.forEach(function (f) { f(); });
var before = ran.slice();
document.prerendering = false; (L.prerenderingchange || []).forEach(function (f) { f(); });
var after = ran.slice();
document.prerendering = false; ran = []; feature(function () { ran.push("now"); }); FEAT[FEAT.length - 1]();
process.stdout.write(JSON.stringify([before, after, ran]));
"""
    (tmp_path / "t.js").write_text(harness, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [[], ["geo"], ["now"]]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_data_saver_removes_the_rules(tmp_path, site):
    h = read(site, "index.html")
    i = h.index('id="spec"')
    j = h.index("<script>", i)
    guard = h[j + len("<script>"):h.index("</script>", j)]
    out = []
    for save, reduced in ((False, False), (True, False), (False, True)):
        harness = (f"var removed = false, spec = {{ remove: function () {{ removed = true; }} }};"
                   f"var navigator = {{ connection: {{ saveData: {str(save).lower()} }} }};"
                   f"var window = {{ matchMedia: function (q) {{ return {{ matches: {str(reduced).lower()} && q.indexOf('reduced-data') >= 0 }}; }} }};"
                   "var document = { getElementById: function () { return spec; } }; function addEventListener() {}\n"
                   + guard + "\nprocess.stdout.write(String(removed));")
        (tmp_path / "g.js").write_text(harness, encoding="utf-8")
        r = subprocess.run([NODE, str(tmp_path / "g.js")], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        out.append(r.stdout)
    assert out == ["false", "true", "true"]


def test_bundle_has_the_feel_module_and_parses(tmp_path, site):
    js = next(f for f in os.listdir(os.path.join(site, "assets")) if re.match(r"cinema\.[0-9a-f]{10}\.js$", f))
    src = read(site, "assets", js)
    assert "function whenActive" in src and "pageswap" in src and "prerenderingchange" in src
    if NODE:
        r = subprocess.run([NODE, "--check", os.path.join(site, "assets", js)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
