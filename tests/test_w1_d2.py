"""W1-D2 (MASTER-PLAN §5.2): Arabic titles and the Arabic search index.

- enrich.py resolves every film's Arabic title from sourced names only (Wikidata's label and aliases, the chain's
  own Arabic, a titles_ar.yaml entry the owner reviewed); an unreviewed transliteration is never published
  (owner default D12), except for an Arabic-language film, which is always shown in Arabic.
- a film page on `/` keeps its Latin title in <title> and the meta description.
- /data/search.json learns Arabic: the cinemas' Arabic names, cities, formats, chains, every sourced Arabic name of
  a film, and a consonant skeleton of each Latin name so an Arabic spelling finds it; the client (src/js/search.js)
  is run for real in node over an index built from real data (tests/fixtures/w1_d2_latest.json: the Fold's
  data of 2026-09-28 after this package's enrich, every film and cinema, a few shows).

Network is never reached (conftest); the owner-editable titles_ar.yaml decides only the tests that are about it."""
import gzip
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import enrich as enrich_mod  # noqa: E402
import pages.search as search  # noqa: E402

REAL = os.path.join(ROOT, "tests", "fixtures", "w1_d2_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
TITLES = os.path.join(ROOT, "titles_ar.yaml")
SEARCH_JS = os.path.join(ROOT, "src", "js", "search.js")
NODE = shutil.which("node")
ARABIC = re.compile(r"[؀-ۿ]")


@pytest.fixture(autouse=True)
def _no_live_lookups(monkeypatch):
    monkeypatch.setattr(enrich_mod, "_wikidata_trailer", lambda qid: None)


def _titles_file(tmp_path, entries):
    p = tmp_path / "titles_ar.yaml"
    p.write_text(yaml.safe_dump({"titles": entries}, allow_unicode=True), encoding="utf-8")
    return str(p)


# ------------------------------------------------------------------ titles_ar.yaml, as the owner edits it
def test_titles_ar_yaml_is_well_formed():
    raw = yaml.safe_load(open(TITLES, encoding="utf-8"))
    assert isinstance(raw, dict) and isinstance(raw.get("titles"), dict) and raw["titles"]
    for fid, e in raw["titles"].items():
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fid), fid
        assert isinstance(e, dict), fid
        ar = e.get("ar")
        assert isinstance(ar, str) and ARABIC.search(ar), fid
        assert not re.search(r"[٠-٩۰-۹·]", ar) and ar == " ".join(ar.split()), fid   # Western digits, no middle dots
        assert enrich_mod.clean_ar(ar) == ar, fid
        assert isinstance(e.get("review", False), bool) and isinstance(e.get("pin", False), bool), fid


def test_every_film_of_the_real_day_has_a_title_or_an_entry():
    """The review list covered the day: enrich's own report on the real data of 2026-09-28 (65 films, the fixture's
    `titles_ar`, a snapshot, so the owner's later edits of titles_ar.yaml never decide this test) has no film
    without a sourced title or an entry, and sourced + awaiting review reaches the plan's 60."""
    d = json.load(open(REAL, encoding="utf-8"))
    films, rep = d["films"], d["titles_ar"]
    assert len(films) == 65 and rep["missing"] == []
    sourced = sum(1 for f in films.values() if f.get("title_ar"))
    assert sourced == 30                                  # 28 before this package, +«شيش دو» +«إكسهوما»
    assert sourced + sum(1 for r in rep["review"] if not r["pin"]) >= 60


# ------------------------------------------------------------------ the resolution order
def test_resolution_order_and_what_is_never_published():
    r = enrich_mod.resolve_title_ar
    film = {"title": "Toy Story 5", "title_ar_chain": "توي ستوري 5", "lang": "English"}
    assert r(film, "حكاية لعبة 5", ["توي ستوري ٥"]) == ("حكاية لعبة 5", "wikidata", ["توي ستوري 5"])
    assert r(film, None, ["حكاية لعبة 5"])[:2] == ("حكاية لعبة 5", "wikidata-alias")
    assert r(film, None, ())[:2] == ("توي ستوري 5", "chain")
    assert r(film, "Toy Story 5", ())[:2] == ("توي ستوري 5", "chain")        # an English label is never Arabic
    pin = {"ar": "توي ستوري 5", "review": False, "pin": True}
    assert r(film, "حكاية لعبة 5", (), pin) == ("توي ستوري 5", "pin", ["حكاية لعبة 5"])
    assert r(film, "حكاية لعبة 5", (), {**pin, "review": True})[:2] == ("حكاية لعبة 5", "wikidata")   # unreviewed pin: nothing
    bare = {"title": "Aaram", "lang": "Malayalam"}
    assert r(bare, None, (), {"ar": "آرام", "review": True}) == (None, None, [])     # never published, never a key
    assert r(bare, None, (), {"ar": "آرام", "review": False}) == ("آرام", "list", [])
    arabic = {"title": "Shish Dou", "lang": "Arabic"}
    assert r(arabic, None, (), {"ar": "شيش دو", "review": True}) == ("شيش دو", "list-unreviewed", [])
    assert r(arabic, None, (), None) == (None, None, [])


def test_clean_ar_prints_the_site_way():
    assert enrich_mod.clean_ar("سقوط ٢:  ديدبوينت (فيلم)") == "سقوط 2: ديدبوينت"
    assert enrich_mod.clean_ar("نهوض فارس الظلام (فيلم)") == "نهوض فارس الظلام"
    assert enrich_mod.clean_ar("Crawlers") is None and enrich_mod.clean_ar(None) is None


def test_enrich_publishes_reviewed_holds_unreviewed_and_reports_both(tmp_path):
    path = _titles_file(tmp_path, {
        "aaram": {"ar": "آرام", "source": "proposed", "review": True},
        "vibe": {"ar": "فايب", "source": "proposed"},
        "shish-dou": {"ar": "شيش دو", "source": "proposed", "review": True},
    })
    data = {"films": {"aaram": {"title": "Aaram", "lang": "Malayalam"}, "vibe": {"title": "Vibe", "lang": "Hindi"},
                      "shish-dou": {"title": "Shish Dou", "lang": "Arabic"}, "runner": {"title": "Runner", "lang": "English"},
                      "mutiny": {"title": "Mutiny", "title_ar_chain": "ميوتني"}},
            "shows": [{"film": "aaram"}, {"film": "aaram"}, {"film": "runner"}]}
    films = enrich_mod.enrich(data, cache_path=str(tmp_path / "c.json"), offline=True, titles_path=path)["films"]
    assert films["aaram"]["title_ar"] is None and films["aaram"]["aka_ar"] == []
    assert (films["vibe"]["title_ar"], films["vibe"]["title_ar_src"]) == ("فايب", "list")
    assert (films["shish-dou"]["title_ar"], films["shish-dou"]["title_ar_src"]) == ("شيش دو", "list-unreviewed")
    assert (films["mutiny"]["title_ar"], films["mutiny"]["title_ar_src"]) == ("ميوتني", "chain")
    rep = data["titles_ar"]
    assert [r["fid"] for r in rep["review"]] == ["aaram", "shish-dou"]        # busiest first
    assert rep["review"][0]["shows"] == 2 and rep["review"][1]["now"] == "شيش دو"
    assert [r["fid"] for r in rep["missing"]] == ["runner"]
    assert rep["sources"] == {"latin": 2, "list": 1, "list-unreviewed": 1, "chain": 1}


def test_shish_dou_renders_in_arabic_from_the_real_list(tmp_path):
    data = {"films": {"shish-dou": {"title": "Shish Dou", "lang": "Arabic"}}}
    film = enrich_mod.enrich(data, cache_path=str(tmp_path / "c.json"), offline=True)["films"]["shish-dou"]
    assert film["title_ar"] == "شيش دو" and film["title_ar_src"] == "list"


# ------------------------------------------------------------------ Wikidata's Arabic, re-read in one call
def _found(qid, **extra):
    fresh = datetime.now(timezone.utc).isoformat()
    return {"ids": {"qid": qid, **extra}, "ids_status": "found", "ids_checked_at": fresh, "lookup_v": 2}


def test_arabic_labels_and_aliases_are_read_in_one_batch_and_kept_for_ar_ttl(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"crawlers": _found("Q1"), "moana": _found("Q2", title_ar="موانا")}), encoding="utf-8")
    calls = []

    def fake_entities(ids, props="labels|claims"):
        calls.append((list(ids), props))
        return {"Q1": {"labels": {"ar": {"value": "كرولرز"}},
                       "aliases": {"ar": [{"value": "الزواحف"}, {"value": "Crawlers"}, {"value": "كرولرز"}]}}}
    monkeypatch.setattr(enrich_mod, "_wikidata_entities", fake_entities)
    titles = _titles_file(tmp_path, {})
    data = {"films": {"crawlers": {"title": "Crawlers"}, "moana": {"title": "Moana"}}}
    films = enrich_mod.enrich(data, cache_path=str(cache), titles_path=titles)["films"]
    assert calls == [(["Q1", "Q2"], "labels|aliases")]                      # one call for every due item
    assert films["crawlers"]["title_ar"] == "كرولرز" and films["crawlers"]["aka_ar"] == ["الزواحف"]
    assert films["moana"]["title_ar"] == "موانا"                            # missing from the answer: kept
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["crawlers"]["ar"]["label"] == "كرولرز" and "ar" not in saved["moana"]
    enrich_mod.enrich({"films": {"crawlers": {"title": "Crawlers"}}}, cache_path=str(cache), titles_path=titles)
    assert len(calls) == 1                                                    # Q1 is fresh: never asked again
    saved["crawlers"]["ar"]["at"] = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    cache.write_text(json.dumps(saved), encoding="utf-8")
    calls.clear()
    enrich_mod.enrich({"films": {"crawlers": {"title": "Crawlers"}}}, cache_path=str(cache), titles_path=titles)
    assert calls == [(["Q1"], "labels|aliases")]                             # re-read after AR_TTL


def test_a_label_wikidata_removed_is_followed_and_a_failed_read_keeps_the_title(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    titles = _titles_file(tmp_path, {})
    cache.write_text(json.dumps({"x": _found("Q1", title_ar="قديم")}), encoding="utf-8")

    def fails(ids, props="labels|claims"):
        raise enrich_mod.LookupFailed("HTTP 503")
    monkeypatch.setattr(enrich_mod, "_wikidata_entities", fails)
    film = enrich_mod.enrich({"films": {"x": {"title": "X"}}}, cache_path=str(cache), titles_path=titles)["films"]["x"]
    assert film["title_ar"] == "قديم"
    monkeypatch.setattr(enrich_mod, "_wikidata_entities", lambda ids, props="labels|claims": {"Q1": {"labels": {}, "aliases": {}}})
    film = enrich_mod.enrich({"films": {"x": {"title": "X", "title_ar_chain": "إكس"}}}, cache_path=str(cache), titles_path=titles)["films"]["x"]
    assert (film["title_ar"], film["title_ar_src"]) == ("إكس", "chain")


def test_offline_never_asks_for_arabic_labels(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("network")
    monkeypatch.setattr(enrich_mod, "_wikidata_entities", boom)
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"x": _found("Q1", title_ar="عنوان")}), encoding="utf-8")
    film = enrich_mod.enrich({"films": {"x": {"title": "X"}}}, cache_path=str(cache), offline=True,
                             titles_path=_titles_file(tmp_path, {}))["films"]["x"]
    assert film["title_ar"] == "عنوان"


def test_titles_cli_lists_what_waits_busiest_first(tmp_path, capsys):
    data = {"films": {"a": {"title": "A", "lang": "Hindi"}, "b": {"title": "B"}, "c": {"title": "C", "title_ar": "سي"}},
            "titles_ar": {"review": [{"fid": "a", "title": "A", "lang": "Hindi", "shows": 9, "ar": "إيه", "pin": False, "now": None}],
                          "missing": [{"fid": "b", "title": "B", "lang": None, "shows": 1}], "sources": {}}}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert enrich_mod.main(["titles", str(p)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("# awaiting review (1)") and out[1].startswith('  a: {ar: "إيه", en: "A", review: true}')
    assert "9 shows, Hindi" in out[1] and out[2].startswith("# no Arabic title and no entry (1)")
    assert out[3].startswith('  b: {ar: "", en: "B", review: true}')
    assert enrich_mod.main([]) == 2


# ------------------------------------------------------------------ the build on real data
@pytest.fixture(scope="module")
def site(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("w1d2") / "o")
    build.build(REAL, DISC, o, modules=build.discover(only=("core", "people", "people_index", "questions", "search")))
    return o


@pytest.fixture(scope="module")
def index(site):
    return json.load(open(os.path.join(site, "data", "search.json"), encoding="utf-8"))


def _head(site, *parts):
    h = open(os.path.join(site, *parts, "index.html"), encoding="utf-8").read()
    title = html.unescape(re.search(r"<title>(.*?)</title>", h, re.S).group(1))
    desc = html.unescape(re.search(r'<meta name="description" content="(.*?)">', h, re.S).group(1))
    return h, title, desc


def test_every_film_page_on_root_keeps_its_latin_title(site):
    films = json.load(open(REAL, encoding="utf-8"))["films"]
    arabic = 0
    for fid, f in films.items():
        h, title, desc = _head(site, "film", fid)
        assert f["title"] in title and f["title"] in desc, fid
        assert len(h.encode("utf-8")) <= 150_000
        _, t_en, _ = _head(site, "en", "film", fid)
        assert t_en.startswith(f["title"]) and not ARABIC.search(t_en), fid
        if f.get("title_ar"):
            arabic += 1
            assert f["title_ar"] in title and title.index(f["title_ar"]) < title.index(f["title"]), fid
            fte = re.search(r'<p class="fte"><bdi lang="en" dir="ltr">(.*?)</bdi>', h)       # the hero's secondary line
            assert fte and html.unescape(fte.group(1)) == f["title"], fid
    assert arabic >= 30


def test_shish_dou_page_is_arabic(site):
    h, title, _ = _head(site, "film", "shish-dou")
    assert "شيش دو" in title and re.search(r"<h1[^>]*>[^<]*شيش دو", h)


def test_index_names_all_66_cinemas_in_arabic_and_learns_cities_formats_chains(index):
    data = json.load(open(REAL, encoding="utf-8"))
    cin = {e["p"].split("/")[-1]: e for e in index if e["t"] == "c"}
    assert len(cin) == len(data["cinemas"]) == 66 and all(ARABIC.search(e["a"]) for e in cin.values())
    assert cin["reel-dubai-mall"]["a"] == "ريل — دبي مول"
    cities = {e["p"]: e for e in index if e["t"] == "y"}
    assert cities["dubai"]["a"] == "دبي" and "rak" in cities["ras-al-khaimah"]["k"]
    fmts = {e["e"]: e for e in index if e["t"] == "h"}
    assert fmts["IMAX"]["p"] == "q/where-imax" and search.normalize("آيماكس") in fmts["IMAX"]["k"]
    assert fmts["Halls"]["p"] == "halls"
    assert all(e["p"] == "halls" or e["p"].startswith("q/") for e in fmts.values())
    chains = {e["a"] for e in index if e["t"] == "n"}
    assert chains == {"فوكس", "ريل", "نوفو", "روكسي", "ستار", "سينما سيتي", "سيني رويال"}


def test_film_entries_carry_every_sourced_name_and_the_skeleton(index):
    films = {e["p"]: e for e in index if e["t"] == "f"}
    sp = films["film/spider-man-brand-new-day"]
    assert search.normalize("سبايدر-مان: يوم جديد") in sp["k"] and search.normalize("سبايدرمان 4") in sp["k"]
    assert sp["s"] == "sbdr mn brnd n d"
    assert films["film/the-odyssey"]["s"] == "t ads"
    assert films["film/avengers-endgame-encore"]["a"] is None      # unreviewed: its Arabic is nowhere in the index
    assert "افنجرز" not in json.dumps(films["film/avengers-endgame-encore"], ensure_ascii=False)


def test_search_json_grows_by_at_most_6_kb_gz(index):
    """What W1-D2 adds (cities, formats, chains, the skeletons, the extra keys) costs <= 6 KB gz."""
    def gz(x):
        return len(gzip.compress(json.dumps(x, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9))
    before = [{**{k: v for k, v in e.items() if k != "s"}, "k": sorted({search.normalize(e["a"]), search.normalize(e["e"])} - {""})}
              for e in index if e["t"] in ("f", "c", "m", "p")]
    assert gz(index) - gz(before) <= 6 * 1024


@pytest.mark.parametrize("name, query, hit", [
    ("Avengers Endgame: Encore", "أفنجرز", 50), ("Spider-Man: Brand New Day", "سبايدر", 50),
    ("Spider-Man: Brand New Day", "سبايدر مان", 50), ("The Odyssey", "اوديسا", 45), ("Resident Evil", "ريزدنت ايفل", 50),
    ("Crawlers", "كراولرز", 50), ("I’M Game", "آيم قيم", 50), ("Avengers Endgame: Encore", "اند قيم", 45),
    ("Toy Story 5", "توي ستوري ٥", 50), ("Brad Pitt", "براد بيت", 50),
    ("The Odyssey", "اود", -1), ("Moana", "موانا", -1), ("Heart of the Beast", "سبايدر", -1)])
def test_skeleton_matches(name, query, hit):
    assert search.skeleton_match(search.skeleton_ar(query), search.skeleton(name)) == hit


# ------------------------------------------------------------------ the client, run for real in node
STUB = r"""
function el() { return { attrs: {}, listeners: {}, hidden: false, value: "", innerHTML: "", textContent: "",
  setAttribute: function (k, v) { this.attrs[k] = String(v); }, getAttribute: function (k) { return this.attrs[k] || null; },
  removeAttribute: function (k) { delete this.attrs[k]; }, addEventListener: function (t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
  fire: function (t, e) { (this.listeners[t] || []).forEach(function (f) { f(e || {}); }); }, appendChild: function (c) { return c; },
  insertBefore: function (c) { return c; }, focus: function () {}, scrollIntoView: function () {}, classList: { add: function () {}, remove: function () {} } }; }
var R = { ".top-in": el(), "#srch-input": el(), "#srch-list": el(), "#srch-empty": el(), "#srch-close": el() };
global.document = { documentElement: { classList: { add: function () {}, remove: function () {} } }, body: { appendChild: function () {} },
  createElement: function () { return el(); }, addEventListener: function () {} };
var K = { AR: true, esc: function (s) { return String(s); }, q: function (s) { return R[s] || null; }, qa: function () { return []; },
  getJSON: function () { return Promise.resolve([]); }, C: { base: "/" }, now: function () { return new Date(); }, get: function () { return null; }, set: function () {} };
"""


def _node(tmp_path, tail):
    src = open(SEARCH_JS, encoding="utf-8").read()
    p = tmp_path / "search_run.js"          # a file, not `node -e`: the real index is longer than a Windows command line
    p.write_text(STUB + src + "\n" + tail, encoding="utf-8")
    r = subprocess.run([NODE, str(p)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_skeleton_is_python_skeleton(tmp_path):
    qs = ["أفنجرز", "سبايدر مان", "اوديسا", "ريزدنت ايفل", "آيم قيم", "توي ستوري ٥", "تشارلي", "ڤوكس", "إكسهوما",
          "هارت اوف ذا بيست", "بِيْسْت", "ـسبايدر", "عزام", "ظبي", "", "imax"]
    got = _node(tmp_path, "console.log(JSON.stringify(" + json.dumps(qs, ensure_ascii=False) + ".map(skel)));")
    assert got == [search.skeleton_ar(q) for q in qs]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_fold_is_python_fold_with_the_persian_letters(tmp_path):
    qs = ["ڤوكس", "پاو باترول", "گولد", "چارلي", "فوكس مول الإمارات", "سبايدر-مان: يوم جديد", "IMAX", "آيماكس"]
    got = _node(tmp_path, "console.log(JSON.stringify(" + json.dumps(qs, ensure_ascii=False) + ".map(norm)));")
    assert got == [search.normalize(q) for q in qs]
    assert search.normalize("ڤوكس") == search.normalize("فوكس")


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_finds_the_right_target_over_the_real_index(index, tmp_path):
    """The package's acceptance: «أفنجرز», «سبايدر», «اوديسا», «فوكس», «imax», «فوكس مول الامارات» and «دبي مول»
    (both cinemas), typed into the real client over the index built from the day's real data."""
    queries = ["أفنجرز", "سبايدر", "اوديسا", "فوكس", "imax", "فوكس مول الامارات", "دبي مول", "ايماكس", "vox", "العين",
               "ڤوكس", "توي ستوري", "شيش دو"]
    tail = ("DATA = " + json.dumps(index, ensure_ascii=False) + ";\nvar out = {};\n"
            + json.dumps(queries, ensure_ascii=False) + ".forEach(function (qq) { R['#srch-input'].value = qq; "
            "R['#srch-input'].fire('input'); var ps = []; R['#srch-list'].innerHTML.replace(/data-p=\"([^\"]+)\"/g, "
            "function (m, p) { ps.push(p); }); out[qq] = ps; });\nconsole.log(JSON.stringify(out));")
    got = _node(tmp_path, tail)
    films = lambda q: [p for p in got[q] if p.startswith("film/")]
    places = lambda q: [p for p in got[q] if not p.startswith(("film/", "people/"))]
    assert films("أفنجرز")[0] == "film/avengers-endgame-encore"
    assert films("سبايدر")[0] == "film/spider-man-brand-new-day" and "film/spider-island" in films("سبايدر")
    assert films("اوديسا")[0] == "film/the-odyssey"
    assert len(places("فوكس")) == 8 and all(p.split("/")[-1].startswith("vox-") for p in places("فوكس"))
    assert places("imax")[0] == "q/where-imax" and places("ايماكس")[0] == "q/where-imax"
    assert places("فوكس مول الامارات")[0] == "dubai/vox-mall-of-the-emirates"
    assert {"dubai/reel-dubai-mall", "dubai/cinemacity-fountain-views"} <= set(places("دبي مول"))
    assert all(p.split("/")[-1].startswith("vox-") for p in places("vox"))
    assert places("العين")[0] == "al-ain"
    assert places("ڤوكس") == places("فوكس")
    assert films("توي ستوري") == ["film/toy-story-5"] and films("شيش دو") == ["film/shish-dou"]
