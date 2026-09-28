"""W0-P2 · Trust sweep: pages (MASTER-PLAN §4.1 #11–#22, #37). The page-level checks live beside each page's own
tests (test_pages_coming_hubs, test_steps_last_chance, test_venue, test_insights, test_questions, test_seasons);
this file holds what crosses them: the two lazy chunks the package changes or adds, run in node the way
tests/test_js.py runs pure.js, and one real build that walks every acceptance line at once. The node tests skip
without node (the Fold may not have it)."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

NODE = shutil.which("node")
node = pytest.mark.skipif(not NODE, reason="node not installed")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")

# a minimal window.CINEMA for a chunk: the clock (UAE time, as core.js's uae()), a fake DOM, getJSON
K_STUB = r"""
function uae(s) { return new Date(s.length <= 16 ? s + ":00+04:00" : s); }
function El(attrs, kids) { this.a = attrs || {}; this.kids = kids || []; this.hidden = !!this.a.hidden; this.parent = null;
  var me = this; this.kids.forEach(function (k) { k.parent = me; }); }
El.prototype.getAttribute = function (k) { return k in this.a ? this.a[k] : null; };
El.prototype.all = function () { var out = []; this.kids.forEach(function (k) { out.push(k); out = out.concat(k.all()); }); return out; };
El.prototype.closest = function (sel) { var k = sel.slice(1, -1), n = this; while (n) { if (n.getAttribute(k) !== null) return n; n = n.parent; } return null; };
function matches(el, sel) { return sel.split(",").some(function (s) { return el.getAttribute(s.trim().slice(1, -1)) !== null; }); }
var ROOT_EL = new El({}, []);
var NOW = "2026-09-25T12:00";
var SLICES = {};
var K = { AR: true, lang: "ar", C: { days: ["2026-09-25", "2026-09-26"], cities: {} }, now: function () { return uae(NOW); }, uae: uae,
  qa: function (sel, r) { return (r || ROOT_EL).all().filter(function (e) { return matches(e, sel); }); },
  q: function () { return null; }, esc: function (s) { return String(s); }, city: function () { return "dubai"; }, card: function () { return ""; },
  getJSON: function (u) { return Promise.resolve(u in SLICES ? SLICES[u] : null); }, sub: function (s) { return s; }, fmt: String };
global.setInterval = function () {};
"""


def run_node(tmp_path, pre, chunk, post):
    src = open(os.path.join(ROOT, "src", "js", chunk), encoding="utf-8").read()
    (tmp_path / "t.js").write_text(K_STUB + pre + "\n" + src + "\n" + post, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@node
def test_when_hides_what_the_clock_has_passed_and_empty_groups(tmp_path):
    """A pair leaves at its first start (a bare HH:MM takes its day from data-d); /kids/ swaps mornings at 14:00."""
    pre = r"""
var p1 = new El({"data-until": "12:30"}), p2 = new El({"data-until": "21:00"}), p3 = new El({"data-until": "11:00"});
var li1 = new El({"data-when-group": ""}, [p1, p2]), li2 = new El({"data-when-group": ""}, [p3]);
var det = new El({"data-d": "2026-09-25", "data-when-group": ""}, [li1, li2]);
var today = new El({"data-until": "2026-09-25T14:00"}), tomorrow = new El({"data-from": "2026-09-25T14:00", hidden: ""});
ROOT_EL = new El({}, [det, today, tomorrow]);
function snap() { return [p1.hidden, p2.hidden, p3.hidden, li1.hidden, li2.hidden, det.hidden, today.hidden, tomorrow.hidden]; }
var out = [];
"""
    post = r"""
out.push(snap());
NOW = "2026-09-25T16:00"; when(); out.push(snap());
NOW = "2026-09-25T21:00"; when(); out.push(snap());
process.stdout.write(JSON.stringify(out));
"""
    noon, four, nine = run_node(tmp_path, pre, "when.js", post)
    #            p1     p2     p3    li1    li2    det   today  tomorrow
    assert noon == [False, False, True, False, True, False, False, True]
    assert four == [True, False, True, False, True, False, True, False]
    assert nine == [True, True, True, True, True, True, True, False]


@node
def test_compare_next_times_come_from_the_day_slices_on_the_visitors_clock(tmp_path):
    """After 21:30 compare said «ما في عروض باقية» for every film (compare.json kept six times from the build):
    the times now come from the city's slices, filtered by the visitor's clock, one entry per start time; a
    slice that could not be read leaves the cell empty rather than claiming nothing is left."""
    pre = r"""
SLICES["/data/dubai-2026-09-25.json"] = { F: [["hob", "قلب الوحش", "Heart"], ["re", "ريزدنت", "RE"]],
  S: [[0, 0, "19:00"], [1, 0, "22:25"], [2, 0, "22:25"], [0, 0, "22:40"], [0, 1, "20:00"]] };
SLICES["/data/dubai-2026-09-26.json"] = { F: [["hob", "قلب الوحش", "Heart"]], S: [[0, 0, "10:30"]] };
NOW = "2026-09-25T21:45";
"""
    post = r"""
var first = soon({}, "hob");
setTimeout(function () {
  var hob = soon({}, "hob"), re = soon({}, "re"), none = soon({}, "nothing");
  NEXT = {}; SLICES = {}; nextTimes("dubai");
  setTimeout(function () {
    process.stdout.write(JSON.stringify([first, hob, re, none, soon({}, "hob")]));
  }, 20);
}, 20);
"""
    first, hob, re_, none, offline = run_node(tmp_path, pre, "compare.js", post)
    assert first == ""                                   # still loading: nothing drawn yet
    assert re.findall(r"\d\d:\d\d", hob) == ["22:25", "22:40", "10:30"] and "باكر" in hob and "19:00" not in hob
    assert re_ == "ما في عروض باقية" and none == "ما في عروض باقية"
    assert offline == ""                                 # no slice read: never «ما في عروض باقية»


@node
def test_both_chunks_parse_as_built(tmp_path):
    for name in ("when", "compare"):
        p = tmp_path / f"{name}.js"
        p.write_text(build.chunk_js(os.path.join(ROOT, "src", "js", name + ".js")), encoding="utf-8")
        r = subprocess.run([NODE, "--check", str(p)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    """Every module, from the fixture at a daytime clock, with a Friday release and a stale last-chance list."""
    d = json.load(open(DATA, encoding="utf-8"))
    d["generated"] = "2026-09-25T13:00:00+04:00"
    d["last_chance"] = {"dubai": ["heart-of-the-beast"]}
    d["coming"] = {"anbil-avan": {"title": "Anbil Avan", "title_ar": None, "release_date": "2026-10-02", "poster": None,
                                  "trailer": None, "genres": [], "chains": ["vox"]}}
    o = str(tmp_path_factory.mktemp("w0p2"))
    path = o + "-data.json"
    json.dump(d, open(path, "w", encoding="utf-8"))
    build.build(path, DISC, o, noindex=False)
    return o


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def test_every_acceptance_line_on_one_build(out):
    coming = read(out, "coming", "index.html")
    assert "disabled" not in coming and "cs-notify" not in coming and re.search(r"<h2>1 أكتوبر 2026</h2><ul class=\"cs-grid\">.*?Anbil Avan", coming, re.S)
    for parts in (("index.html",), ("dubai", "index.html")):
        assert "آخر فرصة" not in read(out, *parts)
    for fid in ("heart-of-the-beast", "resident-evil"):
        assert "dfeat" not in read(out, "film", fid, "index.html")
    j = json.loads(read(out, "data", "compare.json"))
    assert set(j) == {"t", "f", "p"}
    assert not os.path.exists(os.path.join(out, "summer"))
    kids = read(out, "kids", "index.html")
    assert 'data-until="2026-09-25T14:00"' in kids and 'data-from="2026-09-25T14:00" hidden' in kids
    ct = json.loads(re.search(r"<script>window\.CT = (.*?);</script>", read(out, "dubai", "reel-dubai-mall", "index.html")).group(1))
    assert "when" in ct.get("chunks", {})                 # the cinema page asks for the clock chunk
    assert "مؤشر الأسعار، 25 سبتمبر 2026" in read(out, "prices", "index.html")
