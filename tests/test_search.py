"""Search (phase 3, batch A, task A5): pages/search.py's normalize() and index builder, and src/js/search.js's
mirrored normalize/score run for real in Node (skipped where Node is missing, matching tests/test_plugins.py's
own NODE guard) — including the brief's own worked example, «سبايدرمان»/«سبايدر مان»/spiderman/spider man."""
import gzip, json, os, re, shutil, subprocess, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import pages.search as search  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
NODE = shutil.which("node")


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def ct(html):
    return json.loads(re.search(r"<script>window\.CT = (.*?);</script>", html).group(1))


# ------------------------------------------------------------------ normalize(): the rule, not a hand list
def test_normalize_folds_spelling_variants_by_rule():
    """The brief's own example: three spellings collapse to one key without anyone listing them."""
    forms = ("Spider-Man", "Spider Man", "spiderman", "SPIDER MAN", "spider-man")
    keys = {search.normalize(s) for s in forms}
    assert keys == {"spiderman"}


def test_normalize_folds_arabic_letter_variants():
    assert search.normalize("أحمد") == search.normalize("إحمد") == search.normalize("آحمد") == search.normalize("احمد")
    assert search.normalize("مكتبة") == search.normalize("مكتبه")
    assert search.normalize("مصطفى") == search.normalize("مصطفي")
    assert search.normalize("رؤيا") == search.normalize("رويا") and search.normalize("بيئة") == search.normalize("بيئه")
    assert search.normalize("سؤال") != search.normalize("سءال")  # drops ء itself, never invents a letter


def test_normalize_drops_diacritics_and_punctuation_and_spaces():
    assert search.normalize("قِصَّةُ الحُبّ") == search.normalize("قصة الحب")
    assert search.normalize("Spider-Man: Brand New Day") == search.normalize("Spider Man Brand New Day")
    assert search.normalize("") == "" and search.normalize(None) == ""


# ------------------------------------------------------------------ the index builder
@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("search") / "o")
    build.build(DATA, DISC, o, modules=build.discover(only=("core", "people", "people_index", "search")))
    return o


@pytest.fixture(scope="module")
def index(out):
    return json.loads(read(out, "data", "search.json"))


def test_films_and_cinemas_indexed_with_rule_generated_keys(index):
    films = {e["p"]: e for e in index if e["t"] == "f"}
    assert "film/spider-man-brand-new-day" in films
    e = films["film/spider-man-brand-new-day"]
    assert e["a"] and e["e"] and set(e["k"]) == {search.normalize(e["a"]), search.normalize(e["e"])}
    assert "spidermanbrandnewday" in e["k"]
    cinemas = {e["p"] for e in index if e["t"] == "c"}
    assert "dubai/reel-dubai-mall" in cinemas


def test_malls_link_to_one_of_their_own_cinemas(index):
    data = json.load(open(DATA, encoding="utf-8"))
    cinemas = data["cinemas"]
    for e in index:
        if e["t"] != "m":
            continue
        city, cid = e["p"].split("/", 1)
        assert cid in cinemas and cinemas[cid]["city"] == city   # never a guessed path


def test_no_people_data_means_no_person_entries(index):
    assert not any(e["t"] == "p" for e in index)   # fixtures/sample_latest.json has no data["people"]


def test_archived_films_are_indexed_and_marked(index):
    """Ruling round 2 (task-A5-review.md): search is a lookup surface, not a listing -- an archived film
    keeps a real, useful page (linked from a person's "shown before" list), so it stays findable, marked
    `x` so the client can both rank it after every showing match and label it. "weapons" is archived in
    fixtures/sample_latest.json (tests/test_build.py::test_archived_film_keeps_its_page asserts its page
    exists and that it is absent from every OTHER data/*.json file -- search.json is its one exception,
    checked there too)."""
    data = json.load(open(DATA, encoding="utf-8"))
    archived_fids = {fid for fid, f in data["films"].items() if f.get("status") == "archived"}
    assert archived_fids
    films = {e["p"]: e for e in index if e["t"] == "f"}
    assert "film/weapons" in films and films["film/weapons"].get("x") == 1
    for fid in archived_fids:
        e = films.get(f"film/{fid}")
        assert e is not None and e.get("x") == 1
    showing_fids = {fid for fid, f in data["films"].items() if f.get("status") != "archived"}
    for fid in showing_fids:
        e = films.get(f"film/{fid}")
        if e:
            assert "x" not in e


def test_malls_pick_the_first_cinema_that_has_a_city_not_just_the_first_listed():
    """Fix round 1 (task-A5-review.md): a mall's `cinemas:` list can name a cinema id first that turns out
    to have no `city` recorded -- the mall must still resolve to a LATER one that does, not be dropped."""
    cinemas = {"no-city-cinema": {}, "has-city-cinema": {"city": "dubai"}}
    malls_yaml = search.MALLS_PATH
    import yaml
    raw = {"malls": {"test-mall": {"ar": "تست", "en": "Test", "cinemas": ["no-city-cinema", "has-city-cinema"]}}}
    import tempfile, os as _os
    fd, path = tempfile.mkstemp(suffix=".yaml")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(raw, fh)
        search.MALLS_PATH = path
        out = search._malls(cinemas)
    finally:
        search.MALLS_PATH = malls_yaml
    assert out["test-mall"]["path"] == "dubai/has-city-cinema"


def test_closed_panel_css_guards_the_hidden_attribute(out):
    """Critical bug (A4 review): `.srch{display:flex}` alone beats the UA stylesheet's bare `[hidden]`
    rule on specificity-tie-by-source-order (this partial is appended after src/cinema.css), so a CLOSED
    search panel rendered as a full-screen layer over every page and swallowed clicks -- a tap on the
    home page's first poster never navigated. Every other `hidden`-toggled element in this codebase
    (src/cinema.css: `.now[hidden]`, `.film[hidden]`, `.ticket[hidden]`, `.empty[hidden]`, …) carries its
    own explicit `[hidden]{display:none}` override for exactly this reason; `.srch` must too."""
    css = read(out, "assets", "cinema.css")
    assert ".srch[hidden]{display:none}" in css
    # the guard must win: same class, plus the attribute, out-specifies the bare .srch{display:flex} rule
    assert css.index(".srch[hidden]") > css.index(".srch{")


def test_every_entry_has_a_name_a_path_and_at_least_one_key(index):
    for e in index:
        assert e["t"] in ("f", "c", "m", "p")
        assert e["a"] or e["e"]
        assert e["p"] and "//" not in e["p"] and not e["p"].startswith("/") and not e["p"].endswith("/")
        assert e["k"]


def test_index_is_small_and_gz_friendly(index):
    raw = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(raw) < 50_000                       # this fixture's whole catalogue
    assert len(gzip.compress(raw)) < len(raw) * 0.6  # repetitive keys/paths compress well


def test_search_chunk_loads_on_every_kind(out):
    for parts in (("index.html",), ("film", "heart-of-the-beast", "index.html"), ("cards", "index.html"),
                  ("en", "cards", "adcb", "index.html"), ("halls", "index.html")):
        chunks = ct(read(out, *parts)).get("chunks", {})
        assert "search" in chunks and re.fullmatch(r"/assets/search\.[0-9a-f]{10}\.js", chunks["search"])


def test_header_button_hook_is_missing_and_flagged(out):
    """docs/PLUGINS.md's NavItem only ever renders an <a> link (site_kit.py's nav_links) -- there is no hook
    for a header BUTTON that opens a panel, so the page HTML itself must not contain one; src/js/search.js
    injects it at runtime instead (task-A5-report.md records the gap)."""
    home = read(out, "index.html")
    assert "srch-btn" not in home
    chunk_url = ct(home)["chunks"]["search"]
    chunk = read(out, *chunk_url.strip("/").split("/"))
    assert "srch-btn" in chunk and ".top-in" in chunk


def test_search_css_partial_bundled(out):
    assert ".srch-btn" in read(out, "assets", "cinema.css")


# ------------------------------------------------------------------ the client fold/score, run for real
RAW = os.path.join(ROOT, "src", "js", "search.js")


def run_node(js_tail):
    stub = (
        "var K={AR:false,esc:function(s){return String(s);},q:function(){return null;},qa:function(){return [];},"
        "getJSON:function(){return Promise.resolve([]);},C:{base:'/'},now:function(){return new Date();},"
        "get:function(){return null;},set:function(){}};\n"
        "global.document={documentElement:{classList:{add:function(){},remove:function(){}}},"
        "addEventListener:function(){},body:{appendChild:function(){}}};\n")
    src = open(RAW, encoding="utf-8").read()
    script = stub + src + "\n" + js_tail
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_normalize_matches_python_rule_on_spiderman():
    out_txt = run_node(
        'console.log(JSON.stringify([norm("Spider-Man"), norm("Spider Man"), norm("spiderman"), '
        'norm("سبايدر مان"), norm("سبايدرمان")]));')
    forms = json.loads(out_txt)
    assert forms[0] == forms[1] == forms[2] == "spiderman"
    assert forms[3] == forms[4] == search.normalize("سبايدرمان")


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_score_prefers_exact_then_prefix_then_substring_then_typo():
    out_txt = run_node(
        'console.log(JSON.stringify(['
        'score("spiderman", ["spiderman"]), '
        'score("spider", ["spidermanbrandnewday"]), '
        'score("manbrand", ["spidermanbrandnewday"]), '
        'score("spidernan", ["spiderman"]), '  # one substitution: a real typo
        'score("zzz", ["spiderman"])]));')
    exact, prefix, substr, typo, none_ = json.loads(out_txt)
    assert exact > prefix > substr > typo > 0 and none_ == -1


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_score_tolerates_one_or_two_typos_by_word_length():
    # short words (<=3 folded chars) get no typo tolerance at all -- a 1-letter slip is a different word
    assert json.loads(run_node('console.log(score("kat", ["dog"]));')) == -1
    # a longer word tolerates a single substitution
    assert json.loads(run_node('console.log(score("spidermam", ["spiderman"]));')) >= 0
    # a long word tolerates two
    assert json.loads(run_node('console.log(score("dhabx", ["abudhabi"]));')) == -1  # too different, not just 2 edits
    assert json.loads(run_node('console.log(score("abudabi", ["abudhabi"]));')) >= 0


DOM_STUB = r"""
var FOCUSED = null, DOC_LISTENERS = {}, PANEL_REFS = {};
function makeEl(tag) {
  return {
    tagName: String(tag || "div").toUpperCase(), attrs: {}, listeners: {}, hidden: false, className: "", value: "",
    setAttribute: function (k, v) { this.attrs[k] = String(v); },
    getAttribute: function (k) { return this.attrs.hasOwnProperty(k) ? this.attrs[k] : null; },
    removeAttribute: function (k) { delete this.attrs[k]; },
    addEventListener: function (t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    fire: function (t, ev) { (this.listeners[t] || []).forEach(function (fn) { fn(ev || {}); }); },
    appendChild: function (c) { return c; },
    insertBefore: function (c) { return c; },
    focus: function () { FOCUSED = this; },
    scrollIntoView: function () {},
    classList: { add: function () {}, remove: function () {}, contains: function () { return false; } }
  };
}
var HOST = makeEl("div"), ALT = makeEl("a");
PANEL_REFS.input = makeEl("input"); PANEL_REFS.list = makeEl("ul");
PANEL_REFS.empty = makeEl("p"); PANEL_REFS.close = makeEl("button");
function fakeQ(sel) {
  if (sel === ".top-in") return HOST;
  if (sel === ".alt") return ALT;
  if (sel === "#srch-input") return PANEL_REFS.input;
  if (sel === "#srch-list") return PANEL_REFS.list;
  if (sel === "#srch-empty") return PANEL_REFS.empty;
  if (sel === "#srch-close") return PANEL_REFS.close;
  return null;
}
global.document = {
  documentElement: { classList: { add: function () {}, remove: function () {} } },
  body: { appendChild: function () {} },
  createElement: function (tag) { return makeEl(tag); },
  addEventListener: function (t, fn) { (DOC_LISTENERS[t] = DOC_LISTENERS[t] || []).push(fn); }
};
var K = {
  AR: false, esc: function (s) { return String(s); }, q: fakeQ, qa: function () { return []; },
  getJSON: function () { return Promise.resolve([]); }, C: { base: "/" },
  now: function () { return new Date(); }, get: function () { return null; }, set: function () {}
};
"""


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_open_close_aria_expanded_and_focus_return(tmp_path):
    """open()/close() through the real button+input+panel wiring build() sets up, over a tiny hand-rolled
    DOM stub (no jsdom in this repo's toolchain -- toolcheck's own "ask the device" rule: it is genuinely
    not installed, not merely unconfigured)."""
    src = open(RAW, encoding="utf-8").read()
    tail = r"""
var results = {};
results.initiallyHidden = panel.hidden;
btn.fire("click");                                    // open()
results.afterOpenHidden = panel.hidden;
results.afterOpenAriaExpanded = input.getAttribute("aria-expanded");
DATA = [{t: "f", a: "فيلم", e: "Film", p: "film/x", k: ["film"]}];
input.value = "film";
input.fire("input");                                  // search("film") -> one exact match
results.afterSearchAriaExpanded = input.getAttribute("aria-expanded");
input.fire("keydown", { key: "Escape", preventDefault: function () {} });   // close()
results.afterEscapeHidden = panel.hidden;
results.focusReturnedToButton = FOCUSED === btn;
console.log(JSON.stringify(results));
"""
    script = DOM_STUB + src + "\n" + tail
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip())
    assert out["initiallyHidden"] is True
    assert out["afterOpenHidden"] is False and out["afterOpenAriaExpanded"] == "false"
    assert out["afterSearchAriaExpanded"] == "true"
    assert out["afterEscapeHidden"] is True
    assert out["focusReturnedToButton"] is True


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_archived_films_ranked_after_showing_and_labelled():
    """Ruling round 2 (task-A5-review.md): an archived film (`x: 1` in the index, pages/search.py) is still
    a real result -- but on an equal score it must render after a showing match, labelled, never mixed in
    indistinguishably. Two entries tie on an exact-match score (100) here on purpose, so the only thing that
    can separate them in `list.innerHTML`'s order is the archived flag, not the score."""
    src = open(RAW, encoding="utf-8").read()
    tail = r"""
DATA = [
  { t: "f", a: null, e: "Old Film", p: "film/old", k: ["tie"], x: 1 },
  { t: "f", a: null, e: "New Film", p: "film/new", k: ["tie"] }
];
input.value = "tie";
input.fire("input");
var html = list.innerHTML;
console.log(JSON.stringify({
  order: html.indexOf("film/new") < html.indexOf("film/old") ? "new-first" : "old-first",
  labelled: html.indexOf("No longer showing") !== -1,
  newUnlabelled: html.slice(0, html.indexOf("film/old")).indexOf("No longer showing") === -1
}));
"""
    script = DOM_STUB + src + "\n" + tail
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip())
    assert out["order"] == "new-first" and out["labelled"] is True and out["newUnlabelled"] is True


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_parses_as_valid_javascript_when_wrapped_as_a_chunk(tmp_path):
    chunk = build.chunk_js(RAW)
    p = tmp_path / "search.chunk.js"
    p.write_text(chunk, encoding="utf-8")
    r = subprocess.run([NODE, "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
