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
CITIES = ["abu-dhabi", "dubai", "sharjah", "ajman", "umm-al-quwain", "ras-al-khaimah", "fujairah", "al-ain"]
PRERENDER = ["/film/*", "/en/film/*"] + [f"/{c}/*" for c in CITIES] + [f"/en/{c}/*" for c in CITIES]


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


def test_prerender_film_city_and_cinema_pages_on_moderate_prefetch_the_rest(site):
    r = rules(read(site, "index.html"))
    (pre,), (pf,) = r["prerender"], r["prefetch"]
    assert pre["eagerness"] == pf["eagerness"] == "moderate"          # hover (200 ms) or pointerdown, never on load
    assert pre["where"]["and"][0] == {"href_matches": PRERENDER}
    # a link carrying state (?city=, ?card=, ?now=) never prerenders: city/card params write the visitor's choice
    no = pre["where"]["and"][1]["not"]["selector_matches"]
    assert "[href*='?']" in no and "[target]" in no and "[download]" in no and "[data-nospec]" in no
    assert pf["where"]["and"][0] == {"href_matches": "/*"}
    skip = pf["where"]["and"][1]["not"]["href_matches"]
    # film, city and cinema pages prerender (no script runs until they are shown: the «boot» loader); the rest
    # is prefetched; files and data are never fetched ahead
    for p in PRERENDER + ["/data/*", "/assets/*", "/posters/*", "/*.*"]:
        assert p in skip, p


def test_data_saver_and_back_type_script_follows_the_rules(site):
    h = read(site, "en", "index.html")
    i = h.index('id="spec"')
    guard = h[i:h.index("</script>", h.index("</script>", i) + 1)]
    assert "saveData" in guard and "prefers-reduced-data: reduce" in guard and 'getElementById("spec")' in guard
    assert "pagereveal" in guard and '"traverse"' in guard and 'types.add("back")' in guard


def test_every_page_loads_the_bundle_through_the_boot_loader(site):
    n = 0
    for p in pages(site):
        h = open(p, encoding="utf-8").read()
        if 'rel="canonical"' not in h: continue
        js = re.search(r'<link rel="preload" href="(/assets/cinema\.[0-9a-f]{10}\.js)" as="script">', h).group(1)
        assert f'<script src="{js}"' not in h and "defer></script>" not in h       # never a plain script tag
        boot = re.search(r'<script id="boot">(.*?)</script>', h).group(1)
        assert boot.endswith(f'("{js}",document)') and "d.prerendering" in boot and '"prerenderingchange"' in boot
        assert h.index('<script id="boot">') > h.index("<script>window.CT =")  # the strings are there first
        n += 1
    assert n > 20


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_boot_inserts_nothing_while_prerendering(tmp_path, site):
    boot = re.search(r'<script id="boot">(.*?)</script>', read(site, "film", next(iter(os.listdir(os.path.join(site, "film")))), "index.html")).group(1)
    harness = """
var L = {}, added = [], registered = 0;
var navigator = { serviceWorker: { register: function () { registered++; return { catch: function () {} }; } } };
function mk(prerendering, ready) {
  L = {}; added = [];
  return { prerendering: prerendering, readyState: ready,
    addEventListener: function (t, f, o) { (L[t] = L[t] || []).push(f); },
    createElement: function (tag) { return { tag: tag }; },
    body: { appendChild: function (el) { added.push(el); } } };
}
var out = {};
var document = mk(true, "complete");
(function (document) { BOOT })(document);
out.during = added.length; out.listeners = Object.keys(L);
document.prerendering = false; (L.prerenderingchange || []).forEach(function (f) { f(); });
out.after = added.map(function (e) { return e.tag + " " + e.src; });
added[0].onload && added[0].onload(); out.sw = registered;
document = mk(false, "loading");
(function (document) { BOOT })(document);
out.normal = added.length; out.normalOnload = !!added[0].onload;
process.stdout.write(JSON.stringify(out));
""".replace("BOOT", boot)
    (tmp_path / "b.js").write_text(harness, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "b.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    js = re.search(r'\("([^"]+)",document\)$', boot).group(1)
    assert got["during"] == 0 and got["listeners"] == ["prerenderingchange"]    # nothing runs, nothing is fetched to run
    assert got["after"] == ["script " + js]
    assert got["sw"] == 1              # shown after its load event: the worker registration pwa.js waits on is done here
    assert got["normal"] == 1 and got["normalOnload"] is False                  # an ordinary visit: straight in, as before


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
feature(function () { ran.push("search"); throw new Error("a feature that throws"); });
feature(function () { ran.push("share"); });
console.error = function () {};
FEAT.forEach(function (f) { f(); });
var before = ran.slice();
document.prerendering = false; (L.prerenderingchange || []).forEach(function (f) { f(); });
var sync = ran.slice(), steps = [];
/* each feature in its own task: after each zero-timeout at most one more has run */
function step() { steps.push(ran.length); if (ran.length < 3) setTimeout(step, 0); else done(); }
setTimeout(step, 0);
function done() {
  ran = []; feature(function () { ran.push("late"); }); FEAT[FEAT.length - 1]();
  setTimeout(function () { process.stdout.write(JSON.stringify([before, sync, steps, ran])); }, 5);
}
"""
    (tmp_path / "t.js").write_text(harness, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    before, sync, steps, late = json.loads(r.stdout)
    assert before == [] and sync == []          # nothing while prerendering, nothing in the activation task itself
    # then one feature per task, in order (feel.js's own two features queue first); a throwing one stops no other
    assert steps[-1] == 3 and len(steps) >= 3 and all(0 <= b - a <= 1 for a, b in zip(steps, steps[1:]))
    assert late == ["late"]


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


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_day_labels_format_each_date_once_and_read_the_same(tmp_path):
    """156 day labels over 2 dates (a film page) build at most 2 formatters, and say exactly what the
    uncached humanDay said (src/js/main.js)."""
    main = open(os.path.join(ROOT, "src", "js", "main.js"), encoding="utf-8").read()
    i = main.index("var HUMAN_DAY = {};")
    j = main.index("function dayName", i)
    cached = main[i:j]
    old = ('function oldDay(d) {\n  try { return new Date(d + "T12:00:00Z").toLocaleDateString(AR ? "ar-AE-u-nu-latn" : "en-GB", '
           '{ timeZone: "UTC", day: "numeric", month: "long" }); }\n  catch (e) { return d; }\n}\n')
    out = {}
    for lang in ("ar", "en"):
        harness = (f"var AR = {str(lang == 'ar').lower()};\n" + old + cached + """
var labels = []; for (var k = 0; k < 156; k++) labels.push(k % 3 ? "2026-09-27" : "2026-09-28");
var want = labels.map(oldDay);
var calls = 0, orig = Date.prototype.toLocaleDateString;
Date.prototype.toLocaleDateString = function () { calls++; return orig.apply(this, arguments); };
var got = labels.map(humanDay);
process.stdout.write(JSON.stringify({ calls: calls, same: JSON.stringify(got) === JSON.stringify(want), sample: got.slice(0, 2), bad: humanDay("x") }));
""")
        (tmp_path / "d.js").write_text(harness, encoding="utf-8")
        r = subprocess.run([NODE, str(tmp_path / "d.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        out[lang] = json.loads(r.stdout)
    for lang, o in out.items():
        assert o["calls"] <= 2 and o["same"], (lang, o)          # 156 labels, 2 dates: at most 2 formatters, same text
    assert out["en"]["sample"] == ["28 September", "27 September"] and out["en"]["bad"] in ("x", "Invalid Date")
