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


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_parses_as_valid_javascript_when_wrapped_as_a_chunk(tmp_path):
    chunk = build.chunk_js(RAW)
    p = tmp_path / "search.chunk.js"
    p.write_text(chunk, encoding="utf-8")
    r = subprocess.run([NODE, "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
