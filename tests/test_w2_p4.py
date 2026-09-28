"""W2-P4 · home rows, grid and filters (MASTER-PLAN §2.0, §2.1 below the board, §3.1/§3.3 the one «مع منو» store,
§4.2 #7 #8 #12 #13 #15 #16 #20–#23 #26 #42, §5.3 W2-P4).

Here: the rows' de-duplication (Python and its script twin), «أرخص عرض الليلة» as show cards, no «آخر فرصة», the tile's
verdict word and fixed lines, «بالأرقام», the stale line and a failed city slice never turning a tile «ما يعرض», the
filter sheet's one question («مع منو» / «متى» / «وين», each stored once), «العيال» after 20:00, the disabled «ولا فيلم»,
what W2-P4 deleted (the near row, «بروحي», «ربعي», the preset, ui-near.css) and the real data's rows. What needs a
browser (the chunked render's frames, the page height while scrolling, the sheet at 360 and 390) is
tools/check_w2_p4.cjs. Node tests skip without node, as tests/test_js.py does (the Fold may not have it)."""
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
from pages._core.home import FIRST, NUMS, dedupe  # noqa: E402
from kit.filters import who_fits  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")
JS = Path(ROOT, "src", "js")
CSS = Path(ROOT, "src", "css")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
REAL = os.path.join(ROOT, "data", "latest.json")


def read(out, *parts):
    return open(os.path.join(out, *parts, "index.html"), encoding="utf-8").read()


def main_of(h):
    return h[h.index("<main"):h.index("</main>")]


def rows_of(h):
    """{row key: [the film ids its tiles and show cards link to, in order]} for the rows <main> draws."""
    m = main_of(h)
    out = {}
    for key, body in re.findall(r'<section class="rail" aria-labelledby="r-([a-z]+)"[^>]*>(.*?)</section>', m, re.S):
        out[key] = re.findall(r'<a class="tile[^"]*" href="/(?:en/)?film/([^/]+)/', body)
    return out


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("w2p4") / "out")
    build.build(DATA, DISC, o, noindex=False)
    return o


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    if not os.path.exists(REAL): pytest.skip("no data/latest.json")
    o = str(tmp_path_factory.mktemp("w2p4real") / "out")
    build.build(REAL, os.path.join(ROOT, "discounts.yaml"), o, noindex=False)
    return o


def check_rows(rows):
    """The acceptance: no film in the first 3 slots of two rows, and no row under 4 films."""
    firsts = {}
    for key, fids in rows.items():
        if key in ("coming",): continue                       # announced films, never in another row
        assert len(fids) >= 4, (key, fids)
        for f in fids[:FIRST]:
            assert f not in firsts, (f, key, firsts.get(f))
            firsts[f] = key


# ---------------------------------------------------------------- the rows: de-duplication (§2.1, §4.2 #8)
def test_dedupe_opens_each_row_with_new_films():
    rows = [list("abcdefg"), list("abxy"), list("abcxyzw"), list("pqr"), list("axbyczq")]
    got = dedupe(rows)
    assert got[0] == list("abcdefg")
    assert got[1] is None                                          # 4 films but only 2 new ones: steps aside
    assert got[2] == list("xyzabcw")                               # its new films first, the rest in their order
    assert got[3] is None                                          # under 4
    assert got[4] is None                                          # one new film (q) after a, b, c and x, y, z
    # the invariant, whatever the rows: no film in the first 3 slots of two drawn rows, every drawn row a reordering
    rnd = random.Random(7)
    for _ in range(300):
        pool = [f"f{i}" for i in range(rnd.randint(4, 14))]
        rows = [rnd.sample(pool, rnd.randint(1, len(pool))) for _ in range(rnd.randint(1, 6))]
        seen = set()
        for r, o in zip(rows, dedupe(rows)):
            if o is None:
                assert len(r) < 4 or len([f for f in r if f not in seen]) < FIRST
                continue
            assert sorted(o) == sorted(r) and not set(o[:FIRST]) & seen
            seen |= set(o[:FIRST])


@needs_node
def test_the_scripts_lead_is_the_twin_of_dedupe(tmp_path):
    """home.js lead() re-opens the rows after the visitor's city re-sorts them: the same rule as the build's dedupe()."""
    src = (JS / "home.js").read_text(encoding="utf-8")
    lead = re.search(r"^function lead\(.*?^\}$", src, re.S | re.M).group(0)
    rnd = random.Random(11)
    cases = []
    for _ in range(200):
        pool = [f"f{i}" for i in range(rnd.randint(4, 12))]
        cases.append([rnd.sample(pool, rnd.randint(1, len(pool))) for _ in range(rnd.randint(1, 6))])
    js = lead + """
    var cases = %s;
    process.stdout.write(JSON.stringify(cases.map(function (rows) {
      var seen = {};
      return rows.map(function (r) { var o = lead(seen, r); if (o) o.slice(0, 3).forEach(function (f) { seen[f] = 1; }); return o; });
    })));""" % json.dumps(cases)
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [dedupe(c) for c in cases]


def test_the_fixtures_rows_hold_the_rule(out):
    for parts in ((), ("en",)):
        check_rows(rows_of(read(out, *parts)))


def test_the_real_rows_hold_the_rule_and_tell_different_stories(real):
    """Over the real-data build: no film in the first 3 slots of two rows, no row under 4 films (the audit found the same
    three posters opening the rows 4 times on the first 4 screens, §4.2 #8)."""
    for parts in ((), ("en",)):
        rows = rows_of(read(real, *parts))
        assert {"top", "cheap"} <= set(rows), rows.keys()
        check_rows(rows)


# ---------------------------------------------------------------- «أرخص عرض الليلة» (§2.1, §4.2 #22)
def test_cheapest_show_tonight_is_show_cards(real):
    h = read(real)
    row = re.search(r'<section class="rail" aria-labelledby="r-cheap" data-rail-cheap>.*?</section>', main_of(h), re.S).group(0)
    assert "أرخص عرض الليلة" in row and "أرخص لك الليلة" not in h
    cards = re.findall(r'<a class="tile shc" href="/film/([^/]+)/#s-([0-9a-z]+)" data-film="\1">.*?<b class="num">(\d\d:\d\d)</b> <bdi>([^<]+)</bdi>'
                       r'.*?<span class="pv"><span class="num">([\d.]+)</span></span>', row, re.S)
    assert len(cards) >= 4 and len({c[0] for c in cards}) == len(cards)          # one show per film
    prices = [float(c[4]) for c in cards]
    # opened with films no earlier row opens with; after those, the cheapest first
    assert prices[3:] == sorted(prices[3:])
    # each card is a real show of that film at that time, its link that show's key (the show link, §2.2: the film page
    # opens its ticket), and its price that show's cheapest
    data = json.load(open(REAL, encoding="utf-8"))
    for fid, key, t, cin, aed in cards:
        shows = [s for s in data["shows"] if s["film"] == fid and s["time"] == t]
        assert shows, (fid, t)
        lows = {min(p["aed"] for p in s.get("prices") or [] if p.get("aed")) for s in shows if any(p.get("aed") for p in s.get("prices") or [])}
        assert float(aed) in lows, (fid, t, aed, lows)
    # the row's card door (one per screen, §1.2 #10): the card sheet, its no-card words kept for when the card goes
    assert 'data-sheet-open="sheet-card" data-door="عندك بطاقة؟ شوف سعرك">عندك بطاقة؟ شوف سعرك' in row


def test_cheap_show_cards_are_that_films_cheapest_show(tmp_path):
    """On the fixture (a Friday, 18:00): each card is its film's cheapest show still to start tonight in Dubai, with the
    show's own key; the script redraws the row for the visitor's city and card."""
    o = str(tmp_path / "o")
    build.build(DATA, DISC, o, noindex=False)
    row = re.search(r'<section class="rail" aria-labelledby="r-cheap".*?</section>', read(o), re.S)
    assert row
    data = json.load(open(DATA, encoding="utf-8"))
    dubai = {c for c, v in data["cinemas"].items() if v.get("city") == "dubai"}
    for fid, key, aed in re.findall(r'href="/film/([^/]+)/#s-([0-9a-z]+)".*?<span class="num">([\d.]+)</span></span></span></a>', row.group(0) if row else "", re.S):
        tonight = [s for s in data["shows"] if s["film"] == fid and s["cinema"] in dubai and (s["date"], s["time"]) >= ("2026-09-25", "18:00")
                   and (s["date"] == "2026-09-25" or s["time"] < "03:00")]
        low = min(p["aed"] for s in tonight for p in s.get("prices") or [] if p.get("aed"))
        assert float(aed) == low, (fid, aed, low)


# ---------------------------------------------------------------- the tile (§2.1 #4, §4.2 #21)
def test_grid_tiles_open_with_the_verdict_word(out):
    m = main_of(read(out))
    grid = m[m.index('<section class="all wrap"'):]
    words = re.findall(r'<a class="film tile v-(\w+)"[^>]*>.*?<span class="vw">([^<]+)</span><span class="m" data-cheap>', grid, re.S)
    want = {"yes": "يستاهل", "mixed": "بين بين", "skip": "تجنّبه", "unknown": "الحكم بعده"}
    assert words and all(want[v] == w for v, w in words), words
    # a row's tile has no verdict word: its row already says why it is there
    rows = m[:m.index('<section class="all wrap"')]
    assert '<span class="vw">' not in rows
    css = (CSS / "ui-tile.css").read_text(encoding="utf-8")
    # every line has a fixed height (the grid's placeholders know a tile's height before it is drawn); two title lines
    assert re.search(r"\.tile \.t\{[^}]*block-size:2\.7em[^}]*-webkit-line-clamp:2", css)
    assert re.search(r"\.tile \.vw\{[^}]*block-size:1\.5em", css) and re.search(r"\.tile \.m\{[^}]*block-size:1\.5em[^}]*text-overflow:ellipsis", css)


def test_the_grids_placeholders_hold_the_real_pitch():
    """§4.2 #13: a tile not yet drawn holds a column-wide 2:3 poster plus its fixed lines (8 + 43.2 + 19.5 + 19.5 px),
    worked out from the grid's own width (a size container), not a guess."""
    css = (CSS / "ui-grid.css").read_text(encoding="utf-8")
    assert "[data-films]{container-type:inline-size}" in css
    assert "[data-films] > .film{contain-intrinsic-block-size:auto calc((100cqi - 24px) / 3 * 1.5 + 90.2px)}" in css
    assert "(100cqi - 96px) / 7 * 1.5 + 90.2px" in css
    assert round(8 + 2 * 16 * 1.35 + 13 * 1.5 + 13 * 1.5, 1) == 90.2
    assert "auto 240px" not in css


@needs_node
def test_the_tiles_line_by_card_and_clock(tmp_path):
    """With a card: yours and the list price struck; with no card after 17:00: «التالي 21:30 …»; by day «من 42»."""
    src = (JS / "home.js").read_text(encoding="utf-8")
    fn = re.search(r"^var FX = .*?^\}$", src, re.S | re.M).group(0)
    js = """
var AR = true, TX = { from: "من" }, C = { box: "السعر في الشباك", not_in_city: "ما يعرض في {city}", cinemas: {} }, S = { cinemas: { r: { ar: "ريل دبي مول" } } };
var TODAY = "2026-09-27", card = "", MIN = 0;
function nowMin() { return MIN; }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
function sub(s, o) { return String(s).replace(/\\{(\\w+)\\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); }
function nm(o) { return o ? o.ar : ""; }
function fmt(n) { return String(n); }
function payCell(b) { return "<b>" + b.pay + "</b>" + (b.off ? ' <s class="num">' + b.aed + "</s>" : ""); }
function asofNote() { return ""; }
var BOX = { innerHTML: "" }, EL = {};
function q(sel, r) { return sel === "[data-cheap]" ? BOX : null; }   /* box starts empty: no ".p" to find yet */
""" + fn + """
var sh = [{ d: TODAY, t: "21:30", c: "r" }], b = { pay: 42, aed: 42, off: false, s: sh[0] };
var out = [];
MIN = 18 * 60; tileLine(EL, true, sh, b, false, "دبي"); out.push(BOX.innerHTML);
MIN = 11 * 60; tileLine(EL, true, sh, b, false, "دبي"); out.push(BOX.innerHTML);
card = "fazaa"; MIN = 18 * 60; tileLine(EL, true, sh, { pay: 33.6, aed: 42, off: true, s: sh[0] }, false, "دبي"); out.push(BOX.innerHTML);
card = ""; tileLine(EL, false, [], null, false, "دبي"); out.push(BOX.innerHTML);
process.stdout.write(JSON.stringify(out));
"""
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got[0] == '<span class="nx">التالي 21:30 <bdi>ريل دبي مول</bdi></span>'
    assert got[1] == 'من <span class="p" data-shown="42"><b>42</b></span>'
    assert got[2] == 'من <span class="p" data-shown="33.6"><b>33.6</b> <s class="num">42</s></span>'
    assert got[3] == '<span class="fw">ما يعرض في دبي</span>'


# ---------------------------------------------------------------- «بالأرقام» (§2.1, §4.2 #42)
def test_the_numbers_row_is_three_44px_links_not_a_paragraph(out):
    h = read(out)
    row = re.search(r'<section class="rail nums" aria-labelledby="r-nums">.*?</section>', h, re.S).group(0)
    assert "بالأرقام" in row
    links = re.findall(r'<li><a href="([^"]+)">([^<]+)</a></li>', row)
    assert [x[0] for x in links] == ["/prices/", "/boxoffice/", "/q/"]
    assert 'class="wrap insx"' not in main_of(h) and '<p class="links more"><a href="/prices/">' not in h
    css = (CSS / "ui-rows.css").read_text(encoding="utf-8")
    assert re.search(r"\.nums-l a\{[^}]*min-block-size:44px", css)
    assert "/en/prices/" in read(out, "en")


def test_the_numbers_row_reads_insights_own_markup():
    """insights.py is W2-P9's and stays as it is: the row is made from its home_links output, so a change there shows here."""
    from pages.insights import Insights
    html = Insights.home_links(None, None, "ar")
    assert NUMS.search(html) and len(re.findall(r'<a href="', html)) == 3


# ---------------------------------------------------------------- a failed city slice (§1.7, §4.2 #7)
def test_the_stale_line_is_in_the_page_hidden(out):
    h = read(out)
    m = re.search(r'<p class="stale-l wrap" data-stale hidden>([^<]+)</p>', h)
    assert m and m.group(1) == "ما قدرنا نحدّث الأوقات، هذي آخر نسخة من 18:00"
    assert "Couldn’t refresh the times. This is the 18:00 copy." in read(out, "en")
    assert main_of(h).index("data-stale") < main_of(h).index('aria-labelledby="r-top"')


@needs_node
def test_a_failed_slice_keeps_the_servers_prices_and_says_so(tmp_path):
    """loadCity: a network failure or a 5xx on today's slice leaves S empty (renderHome draws nothing, so no tile turns
    «ما يعرض») and shows the stale line; a 404 is a day with no shows, not a failure; the minute asks again."""
    src = (JS / "home.js").read_text(encoding="utf-8")
    body = src[src.index("/* a day's slice:"):src.index("/* a city page on a busy day")]
    js = """
var C = { days: ["2026-09-27", "2026-09-28"] }, AR = true, JC = {}, city = "dubai", TODAY = "2026-09-27", TOMORROW = "2026-09-28", LOC = null, S = null;
var STALE = [{ hidden: true }], DREW = 0, ANSWER = {};
function qa() { return STALE; }
function uae(s) { return new Date(s.length <= 16 ? s + ":00+04:00" : s); }
function renderSched() {} function renderHome() { DREW++; } function applyNear() {}
function fetch(u) {
  var a = ANSWER[u.slice(-15, -5)];
  if (a === "net") return Promise.reject(new Error("offline"));
  return Promise.resolve({ ok: a === 200, status: a, json: function () { return Promise.resolve({ C: [["c1", "vox", "ف", "V"]], F: [["f1", "ف", "F"]], H: [["S", "vox|Standard", "ع", "S"]], P: [], B: [], S: [[0, 0, "21:00", 0, -1, -1, ""]] }); } });
}
""" + body + """
function run(a, b) {
  ANSWER = { "2026-09-27": a, "2026-09-28": b }; JC = {}; PS = {}; S = null; DREW = 0; STALE[0].hidden = true;
  return loadCity().then(function () { return [a, b, SLICE_BAD, !STALE[0].hidden, S ? S.shows.length : null, DREW]; });
}
Promise.resolve().then(function () { return run("net", 200); }).then(function (x) { R.push(x); return run(503, 200); })
  .then(function (x) { R.push(x); return run(200, "net"); }).then(function (x) { R.push(x); return run(404, 404); })
  .then(function (x) { R.push(x); return run(404, "net"); }).then(function (x) { R.push(x); return run(200, 200); })
  .then(function (x) { R.push(x); process.stdout.write(JSON.stringify(R)); });
var R = [];
"""
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got[0] == ["net", 200, True, True, None, 0]                 # offline: the server's prices, the stale line
    assert got[1] == [503, 200, True, True, None, 0]                   # a 5xx: the same
    assert got[2] == [200, "net", False, False, 1, 1]                  # tomorrow's missing: today still draws
    assert got[3] == [404, 404, False, False, 0, 1]                    # no shows in the city: said as such, not stale
    assert got[4] == [404, "net", True, True, None, 0]                 # none today and tomorrow's failed: stale
    assert got[5] == [200, 200, False, False, 2, 1]
    # the minute asks again, and a failed fetch is never kept in the cache
    assert "if (SLICE_BAD) citySlice();" in src and "delete JC[u]" in src


def test_no_tile_is_turned_off_by_a_failed_fetch():
    src = (JS / "home.js").read_text(encoding="utf-8")
    # renderHome only runs over an arrived slice (S), and «off» is only ever set from it
    rh = src[src.index("function renderHome("):]
    assert rh.index("if (!S) return;") < rh.index('classList.toggle("off"')
    assert src.count('"off"') == 1 + src.count('classList.contains("off")')


# ---------------------------------------------------------------- the chunked render (§2.1 «Speed», §4.2 #12)
def test_render_home_yields_rail_by_rail_visible_first():
    src = (JS / "home.js").read_text(encoding="utf-8")
    rh = src[src.index("function renderHome("):src.index("function homeMinute(")]
    assert "scheduler.yield" in src and "setTimeout(r, 0)" in src
    assert "batches.sort(function (a, b) { return b.on - a.on; })" in rh and "i += 24" in rh
    assert "p = p.then(later)" in rh and "gen === HGEN" in rh
    # each show's start is worked out once per slice (one Date per day), never by parsing a string per comparison
    assert "at: d0 + " in src and "function start(s) { return s.at != null ? s.at :" in src


# ---------------------------------------------------------------- the one question (§2.0, §3.1, §3.3, §4.2 #26)
def test_the_filter_sheet_opens_with_the_one_question(out):
    for lang, parts in (("ar", ()), ("en", ("en",))):
        h = read(out, *parts)
        fs = re.search(r'<div class="sheet" id="sheet-filter".*?data-fn-live aria-live="polite"></p></div></div>', h, re.S).group(0)
        heads = re.findall(r'<div class="sec ask"><h3 class="l" id="sf-(\w+)">([^<]+)</h3>', fs)
        assert heads == ([("who", "مع منو"), ("when", "متى"), ("where", "وين")] if lang == "ar"
                         else [("who", "Who’s coming"), ("when", "When"), ("where", "Where")])
        assert fs.index('class="sec ask"') < fs.index('id="sf-genre"')
        who = re.findall(r'<button type="button" class="opt" data-who="(\w*)" aria-pressed="(true|false)">([^<]+)<small>([^<]+)</small></button>', fs)
        if lang == "ar":
            # three answers, each saying what it sets; «كبار» (no limit) is the default
            assert who == [("", "true", "كبار", "كل الأفلام"), ("family", "false", "العايلة", "لين PG13، بدون رعب ولا حرب"),
                           ("kids", "false", "العيال", "للأطفال، ويخلص قبل 9 بالليل")]
            when = re.findall(r'data-when="(\w+)" aria-pressed="false">([^<]+)</button>', fs)
            assert when == [("now", "الحين"), ("tonight", "الليلة"), ("late", "بعد العشا"), ("tomorrow", "بكرة")]
            where = re.findall(r'data-where="(\w*)" aria-pressed="(true|false)"( hidden)?>([^<]+)</button>', fs)
            assert where == [("near", "false", "", "قريب مني"), ("mine", "false", " hidden", "سينمتي"), ("", "true", "", "أي مكان")]
            assert "العيال؟ الليلة ما في شي يناسب، شوف بكرة الصبح" in fs and ">بكرة الصبح</button>" in fs
            # the disabled «ولا فيلم، خفّف التصفية» is in the button, its words shown by ui-grid.css once it is disabled
            assert '<span data-fnone>ولا فيلم، خفّف التصفية</span>' in fs
        assert len(who) == 3
        for gone in ('data-who="solo"', 'data-who="friends"', "بروحي", "ربعي", "مع منو رايح؟", 'data-filter="family"', 'data-filter="kids"'):
            assert gone not in fs, gone


def test_who_fits_is_the_one_rule():
    """«العايلة»: nothing above PG13, no horror or war; «العيال»: children's films (the grid and the pick read data-fits)."""
    f = lambda **k: dict({"genres": []}, **k)
    assert who_fits(f(rating="PG13", genres=["Action"])) == "family"
    assert who_fits(f(rating="PG13", genres=["Horror"])) == ""
    assert who_fits(f(rating="PG", genres=["War", "Drama"])) == ""
    assert who_fits(f(rating="PG15", genres=["Comedy"])) == "" and who_fits(f(rating="18+", genres=[])) == ""
    assert who_fits(f(rating="G", genres=["Animation", "Family"])) == "family kids"
    assert who_fits(f(rating=None, genres=["Drama"], family=True)) == "family"      # unrated: the data's own flag
    assert who_fits(f(rating=None, genres=["Drama"])) == ""


def test_the_family_row_is_the_family_answer_best_suited_first(tmp_path):
    d = json.load(open(DATA, encoding="utf-8"))
    for fid, r in (("heart-of-the-beast", "PG"), ("shish-dou", "PG13"), ("the-paradise", "PG13")): d["films"][fid]["rating"] = r
    p = tmp_path / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    o = str(tmp_path / "o")
    build.build(str(p), DISC, o, noindex=False)
    fam = rows_of(read(o)).get("family")
    if fam is None: pytest.skip("the fixture's family row stepped aside (dedupe)")
    assert set(fam) <= {"coyote-vs-acme", "heart-of-the-beast", "shish-dou", "the-paradise", "spider-man-brand-new-day"}
    assert "resident-evil" not in fam and "crawlers" not in fam


@needs_node
def test_the_questions_pure_parts(tmp_path):
    src = (JS / "filters.js").read_text(encoding="utf-8")
    pure = src[src.index("/* pure (tests/test_w2_p4.py"):src.index("/* the page ----")]
    js = pure + """
function uaeMs(s) { return new Date(s + ":00+04:00").getTime(); }
function win(w, s) { var r = whenWin(w, uaeMs(s)); return r && [new Date(r[0] + 4 * 3600e3).toISOString().slice(0, 16), new Date(r[1] + 4 * 3600e3).toISOString().slice(0, 16)]; }
process.stdout.write(JSON.stringify([
  whoOk("family kids", "kids"), whoOk("family", "kids"), whoOk("", ""), whoOk(null, "family"), whoOk("family", ""),
  kidsOk([600, 720]), kidsOk([1140, 1260]), kidsOk([1140, 1261]), kidsOk([30, 150]), kidsOk(null),
  win("now", "2026-09-27T20:40"), win("tonight", "2026-09-27T14:00"), win("tonight", "2026-09-27T20:40"), win("late", "2026-09-27T14:00"),
  win("tomorrow", "2026-09-27T20:40"), win("tonight", "2026-09-28T00:40"), win("tomorrow", "2026-09-28T00:40"), win("", "2026-09-27T20:40"),
  Object.keys(nearSet({ a: 1.2, b: 30, c: 9.9, d: 12, e: 40 })).sort(), Object.keys(nearSet({ a: 50, b: 30, c: 45, d: 60 })).sort()
]));"""
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got[:5] == [True, False, True, False, True]
    assert got[5:10] == [True, True, False, False, True]              # «العيال»: from 06:00, over by 21:00
    assert got[10] == ["2026-09-27T20:40", "2026-09-27T23:10"]         # «الحين»: the next 2 h 30
    assert got[11] == ["2026-09-27T18:00", "2026-09-28T03:00"]         # «الليلة»: 18:00 to 03:00
    assert got[12] == ["2026-09-27T20:40", "2026-09-28T03:00"]
    assert got[13] == ["2026-09-27T21:30", "2026-09-28T03:00"]         # «بعد العشا»
    assert got[14] == ["2026-09-28T06:00", "2026-09-29T03:00"]         # «بكرة»
    assert got[15] == ["2026-09-28T00:40", "2026-09-28T03:00"]         # 00:40: the night still running is «الليلة»
    assert got[16] == ["2026-09-28T06:00", "2026-09-29T03:00"]         # … and «بكرة» is the day that starts
    assert got[17] is None
    assert got[18] == ["a", "c", "d"] and got[19] == ["a", "b", "c"]   # within 10 km, never fewer than the 3 nearest


def test_each_answer_is_stored_once_and_nothing_else_is_set():
    """One localStorage value each (cinema.who, cinema.when, cinema.where, core.js set() prefixes «cinema.»), written only
    by the sheet's click and the reset; the old preset that also set the genre, the end time and the sort is gone."""
    src = (JS / "filters.js").read_text(encoding="utf-8")
    for k in ("who", "when", "where"):
        assert len(re.findall(r'save\("' + k + '"', src)) + len(re.findall(r"save\(k, ", src)) >= 1
    bind = src[src.index("function bindFilters("):]
    branch = bind[bind.index('if ((b = t.closest("[data-who],[data-when],[data-where]")))'):bind.index("refilter(); emit(\"ask\", ask());")]
    assert 'save("filt"' not in branch and 'save("before"' not in branch and 'save("sort"' not in branch
    assert "whoPreset" not in src and "whoPreset" not in (JS / "pure.js").read_text(encoding="utf-8")
    # a stored «بروحي»/«ربعي» from before reads as «كبار» and is forgotten
    assert 'if (ST.who !== "family" && ST.who !== "kids" && ST.who) save("who", "");' in src
    # the pick (W2-P2b) reads the answers and opens this sheet at its top; every change is said on the hook bus
    assert "window.CINEMA.ask = ask" in src and "window.CINEMA.askOpen = askOpen" in src and 'emit("ask", ask())' in src
    # the grid tile's answers live in data-fits: a tile tap is never read as an answer
    assert 'getAttribute("data-fits")' in src


def test_kids_after_eight_offers_tomorrow_morning():
    src = (JS / "filters.js").read_text(encoding="utf-8")
    assert 'function kidsLate() { return ST.who === "kids" && ST.when !== "tomorrow" && nowMin() >= 1200; }' in src
    assert 'save("when", "tomorrow")' in src


def test_a_row_heading_is_its_44px_link(out):
    m = main_of(read(out))
    heads = re.findall(r'<div class="rail-h wrap">(.*?)</div>', m, re.S)
    assert heads and all(h.startswith('<a class="rail-a" href="') or "r-nums" in h for h in heads)
    css = (CSS / "ui-rows.css").read_text(encoding="utf-8")
    assert re.search(r"\.rail-a\{[^}]*min-block-size:44px", css) and re.search(r"\.rail-h \.door\{min-block-size:44px", css)
    assert '<a class="all-l"' not in m


# ---------------------------------------------------------------- what W2-P4 deleted, and what it kept for others
def test_what_w2_p4_deleted():
    home, filters_js, pure = ((JS / f).read_text(encoding="utf-8") for f in ("home.js", "filters.js", "pure.js"))
    for gone in ("function renderNow(", "function renderNear(", "function nowPick(", "function verdictOf("):
        assert gone not in home, gone
    for gone in ("function whoPreset(", "function lateOk(", "function pickNow("):
        assert gone not in pure, gone
    assert "function active(" not in filters_js
    main, near = (JS / "main.js").read_text(encoding="utf-8"), (JS / "near.js").read_text(encoding="utf-8")
    assert "renderNow" not in main + near and "renderNear" not in main + near
    core = (JS / "core.js").read_text(encoding="utf-8")
    for key in ("near_sub:", "ends_b:", "no_clash:", "active:", "away:"):
        assert key not in core, key
    assert not (CSS / "ui-near.css").exists()
    from pages import core as pc
    assert "ui-near" not in pc.CSS
    # kept for the others: the near line (Kit.me) and the flip tiles the board draws on (W2-P2)
    rows = (CSS / "ui-rows.css").read_text(encoding="utf-8")
    assert ".flip .d{" in rows and ".me{" in rows and ".near-m:empty{display:none}" in rows
    assert "function flipTime(" in (JS / "flip.js").read_text(encoding="utf-8")


def test_voice_strings():
    """The copy follows the voice table (§1.7): the empty filter, the disabled button, «العيال» after 20:00, the stale line."""
    core = (JS / "core.js").read_text(encoding="utf-8")
    assert 'empty: "ما في شي يطابق. خفّف التصفية شوي"' in core and 'empty: "Nothing matches. Loosen the filters a little."' in core
    from kit import filters as kf
    assert kf.EMPTY[0] == "ما في شي يطابق. خفّف التصفية شوي" and kf.NONE_BTN[0] == "ولا فيلم، خفّف التصفية"
    assert kf.KIDS_LATE[0] == "العيال؟ الليلة ما في شي يناسب، شوف بكرة الصبح"
    from pages._core.home import ROW_T
    assert ROW_T["stale"][0] == "ما قدرنا نحدّث الأوقات، هذي آخر نسخة من {t}"
    def flat(v):
        if isinstance(v, str): yield v
        elif isinstance(v, dict):
            for x in v.values(): yield from flat(x)
        else:
            for x in v: yield from flat(x)
    words = " ".join(flat((ROW_T, kf.ASK_T, kf.WHO, kf.WHEN, kf.WHERE, kf.KIDS_LATE, kf.KIDS_AM)))
    assert "·" not in words and "وش" not in words.split() and "معي" not in words
    assert not re.search(r"[٠-٩]", words)                              # Western digits
