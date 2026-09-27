"""W0-P3, the trust sweep's client half (plan §4.1 #23–#30): the show link #s-<key>, «الحين» preferring a film
worth it, «الأحسن تقييم» by critics + audience, the late leave-by line and its VALARM, the box-office-only
button, the seats index. The page-level behaviour (a tap landing on the ticket, the desktop column, a hall
hiding as its last time passes) is driven in Chrome by tools/check_w0_p3.cjs; here are the pure parts in node
and the build's data. Node tests skip without node, as tests/test_js.py does (the Fold may not have it)."""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import seats  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")
JS = Path(ROOT, "src", "js")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")

# what the bundle's other files give these modules, reduced to what the functions under test touch
STUB = """
var document = { getElementById: function () { return null; }, querySelector: function () { return null; },
  querySelectorAll: function () { return []; }, body: { getAttribute: function () { return null; } } };
var body = document.body, page = null, AR = true, lang = "ar", C = {}, D = null, G = null, S = null, card = "", city = "dubai";
var TX = { sep: "، " };
function q(s, r) { return (r || document).querySelector(s); }
function qa() { return []; }
function esc(s) { return String(s == null ? "" : s); }
function sub(s, o) { return String(s).replace(/\\{(\\w+)\\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); }
function hhmm(ms) { return new Date(ms + 4 * 3600e3).toISOString().slice(11, 16); }
function uae(s) { return new Date(s.length <= 16 ? s + ":00+04:00" : s); }
var FEAT = []; function feature(fn) { FEAT.push(fn); }
var NOW = new Date(), TODAY = "2026-09-27";
"""


def node(tmp_path, files, expr):
    src = STUB + "\n".join((JS / f).read_text(encoding="utf-8") for f in files)
    (tmp_path / "t.js").write_text(src + "\nprocess.stdout.write(JSON.stringify(" + expr + "));\n", encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def py_show_key(cin, d, t, hk):
    """The Python twin W1-P1 will add as Kit.show_key: FNV-1a 32-bit over the UTF-8 of «cinema|date|time|hall
    key», base36, left-padded to 6 characters."""
    h = 0x811C9DC5
    for b in "|".join([cin, d, t, hk or "Standard"]).encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    digits, k = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while True:
        h, r = divmod(h, 36)
        k = digits[r] + k
        if not h:
            break
    return k.rjust(6, "0")


# ---------------------------------------------------------------- the fixture site, with seats for two cinemas
@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = json.load(open(DATA, encoding="utf-8"))
    gen = seats._parse_at(d["generated"])
    s0 = next(s for s in d["shows"] if (s["date"], s["time"]) > (gen.date().isoformat(), gen.strftime("%H:%M")))
    s1 = next(s for s in d["shows"] if s is not s0 and s["cinema"] != s0["cinema"])
    shape, st = seats.compact(seats.normalise("reel", json.loads((Path(ROOT) / "tests" / "fixtures" / "seats" / "reel.json").read_text(encoding="utf-8"))))
    key = seats.shape_key(shape)
    s0["seats"] = {"free": 36, "total": 39, "at": (gen - timedelta(minutes=20)).isoformat(), "m": key, "st": st, "best": {"row": "C", "x": 4}}
    s1["seatmap"] = key
    d["seatmaps"] = {"maps": {key: shape}}
    p = tmp_path_factory.mktemp("w0p3data") / "latest.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    out = str(tmp_path_factory.mktemp("w0p3site"))
    build.build(str(p), DISC, out, noindex=False)
    return out, d, {s0["cinema"], s1["cinema"]}


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


# ---------------------------------------------------------------- #23 the show link
@needs_node
def test_show_key_matches_its_python_twin_on_every_show(tmp_path, site):
    out = site[0]
    rows = []
    for f in sorted(Path(out, "data").glob("*-20*.json")):
        j = json.loads(f.read_text(encoding="utf-8"))
        d = re.search(r"(\d{4}-\d\d-\d\d)\.json$", f.name).group(1)
        rows += [[j["C"][a[0]][0], d, a[2], j["H"][a[3]][1].split("|", 1)[1]] for a in j["S"]]
    assert len(rows) > 100
    got = node(tmp_path, ["ticket.js"], "[" + ",".join("showKey(%s)" % json.dumps(r)[1:-1] for r in rows) + "]")
    assert got == [py_show_key(*r) for r in rows]
    assert all(re.fullmatch(r"[0-9a-z]{6,7}", k) for k in got)
    assert len(set(got)) == len({tuple(r) for r in rows})          # one key per show, no collision in the fixture
    # a non-ASCII hall key hashes its UTF-8 bytes, as the Python twin does
    assert node(tmp_path, ["ticket.js"], 'showKey("c","2026-09-27","22:10","قاعة")') == py_show_key("c", "2026-09-27", "22:10", "قاعة")


def test_now_links_to_the_show_never_a_query():
    home = (JS / "home.js").read_text(encoding="utf-8")
    assert 'box.href = C.base + "film/" + s.f + "/#s-" + showKey(s.c, s.d, s.t, s.k);' in home
    for f in ("home.js", "ticket.js", "main.js"):     # no string that builds a ?s= link (comments may name it)
        assert not re.search(r"""["'][^"'\n]*\?s=""", (JS / f).read_text(encoding="utf-8")), f
    t = (JS / "ticket.js").read_text(encoding="utf-8")
    assert "هالعرض بدأ، هذي الأوقات الجاية" in t and 'window.addEventListener("hashchange", showFromHash)' in t
    assert "if (!showFromHash()) rollTicket();" in (JS / "main.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- #24 «الحين»
@needs_node
def test_now_prefers_a_film_worth_it_inside_the_window(tmp_path):
    got = node(tmp_path, ["pure.js", "home.js"], """(function () { var n = 1e12, m = 60e3;
      var sh = [{at: n + 2 * m, km: null, v: "unknown", id: "runner"}, {at: n + 7 * m, km: null, v: "yes", id: "beast"},
                {at: n + 12 * m, km: null, v: "mixed", id: "paradise"}, {at: n + 50 * m, km: null, v: "yes", id: "too-late"}];
      var near = [{at: n + 2 * m, km: 9, v: "yes", id: "far-good"}, {at: n + 20 * m, km: 1, v: "mixed", id: "near-good"},
                  {at: n + 1 * m, km: 0.5, v: "unknown", id: "nearest-unknown"}];
      var none = [{at: n + 2 * m, km: null, v: "skip", id: "skip"}, {at: n + 9 * m, km: null, v: "unknown", id: "unknown"}];
      return [nowPick(sh, n, 45).id, nowPick(near, n, 45).id, nowPick(none, n, 45).id,
              nowPick([{at: n + 50 * m, km: null, v: "yes"}], n, 45), nowPick([{at: n - m, km: null, v: "yes"}], n, 45)]; })()""")
    # a «يستاهل»/«بين بين» film inside the window wins over a sooner unknown one (Runner at 22:03, audit §3);
    # among the good ones the nearest cinema, then the soonest; with none good, the soonest of any
    assert got == ["beast", "near-good", "skip", None, None]


# ---------------------------------------------------------------- #25 «الأحسن تقييم»
@needs_node
def test_best_reviewed_puts_scored_films_first_by_critics_plus_audience(tmp_path):
    films = [["resident-evil", None, "yes"], ["avengers-encore", None, "yes"], ["pradhama", None, "yes"],
             ["the-paradise", [None, 78], "mixed"], ["heart", [88, 96], "yes"], ["coyote", [96, 94], "yes"],
             ["sacrifice", [31, 42], "skip"], ["tie-mixed", [91, 94], "mixed"], ["tie-yes", [91, 94], "yes"],
             ["runner", None, "unknown"], ["hanuman", [None, 97], "mixed"]]
    got = node(tmp_path, ["pure.js", "filters.js"],
               "(function(){var f=" + json.dumps(films) + ";return f.map(function(x,i){return [scoreRank(x[1],x[2])*1e3+i,x[0]];})"
               ".sort(function(a,b){return a[0]-b[0];}).map(function(x){return x[1];});})()")
    assert got == ["coyote", "tie-yes", "tie-mixed", "heart", "sacrifice",      # both scores, by the sum; the verdict breaks the tie
                   "hanuman", "the-paradise",                                    # one score
                   "resident-evil", "avengers-encore", "pradhama", "runner"]     # none: last, by verdict, then the page's order
    js = (JS / "filters.js").read_text(encoding="utf-8")
    assert 'if (ST.sort === "verdict")' in js and "scoreRank(scoresOf(fid)" in js
    # a re-sorted sideways row starts at its first film (it used to stay where the old first tile went)
    assert "if (box.scrollWidth > box.clientWidth) box.scrollLeft = 0;" in js


def test_scores_island_on_the_pages_with_the_sort(site):
    out, d = site[0], site[1]
    pat = re.compile(r'<script type="application/json" id="cinema-sc">(.*?)</script>')
    for parts in (("index.html",), ("en", "index.html"), ("dubai", "index.html")):
        m = pat.search(read(out, *parts))
        assert m, parts
        sc = json.loads(m.group(1))
        for fid, v in sc.items():
            rt = d["films"][fid].get("rt") or {}
            assert v == [rt.get("critics"), rt.get("audience")] and v != [None, None]
        assert "shish-dou" not in sc and sc["the-paradise"] == [None, 78]
    cin = next(s["cinema"] for s in d["shows"] if d["films"][s["film"]].get("rt"))
    city = d["cinemas"][cin]["city"]
    m = pat.search(read(out, city, cin, "index.html"))
    assert m and set(json.loads(m.group(1))) <= {s["film"] for s in d["shows"] if s["cinema"] == cin}
    assert 'id="cinema-sc"' not in read(out, "film", "heart-of-the-beast", "index.html")   # no sort there


# ---------------------------------------------------------------- #26 the late leave-by line, the VALARM
@needs_node
def test_leave_by_already_past_says_when_you_would_arrive(tmp_path):
    got = node(tmp_path, ["pure.js", "plan.js"], """(function () {
      var st = uae("2026-09-27T22:17").getTime(), m = 60e3, tr = {mins: 18, start: st, leave: st - 18 * m};   // leave-by 21:59
      var at = function (hm) { return uae("2026-09-27T" + hm).getTime(); };
      return [planLeaveLine(tr, at("21:50"), true), planLeaveLine(tr, at("21:59"), true), planLeaveLine(tr, at("22:10"), true),
              planLeaveLine(tr, at("22:00"), true), planLeaveLine(tr, at("22:01"), true), planLeaveLine(tr, at("22:04"), true),
              planLeaveLine(tr, at("22:10"), false), planLeaveLine(tr, at("22:00"), false)]; })()""")
    assert got[0] == "اطلع من البيت الساعة 21:59 تقريباً" and got[1] == got[0]
    assert got[2] == "لو طلعت الحين توصل 22:28، بعد ما يبدأ بـ11 دقيقة"      # 21:59 at 22:10 (audit §4)
    assert got[3] == "لو طلعت الحين توصل 22:18، بعد ما يبدأ بدقيقة"
    assert got[4] == "لو طلعت الحين توصل 22:19، بعد ما يبدأ بدقيقتين"
    assert got[5] == "لو طلعت الحين توصل 22:22، بعد ما يبدأ بـ5 دقايق"
    assert got[6] == "Leave now and you’ll arrive 22:28, 11 minutes after it starts."
    assert got[7] == "Leave now and you’ll arrive 22:18, 1 minute after it starts."
    for s in got[:6]:
        assert "·" not in s and not re.search("[٠-٩]", s)


@needs_node
def test_valarm_rings_at_the_leave_by(tmp_path):
    got = node(tmp_path, ["pure.js", "plan.js"], """(function () {
      var x = {film: "a", cin: "b", date: "2026-09-27", time: "22:17", endHm: "00:10", lat: 25.2, lng: 55.3};
      var tr = planTrip(x, {lat: 25.25, lng: 55.3});
      var withLoc = planIcs(Object.assign({}, x, {alarm: tr.mins})), noLoc = planIcs(Object.assign({}, x, {alarm: 0}));
      return [tr.mins, planLeaveBy(x, {lat: 25.25, lng: 55.3}), hhmm(tr.leave), /TRIGGER:(\\S+)/.exec(withLoc)[1], /TRIGGER:(\\S+)/.exec(noLoc)[1]]; })()""")
    mins, leave, leave2, trig, trig0 = got
    assert leave == leave2 and trig == f"-PT{mins}M"          # the alarm is the leave-by, not a fixed hour
    assert trig0 == "-PT60M"                                  # no place known: an hour before, as before
    js = (JS / "plan.js").read_text(encoding="utf-8")
    assert "x.alarm = trip ? trip.mins : 0;" in js and "planLeaveLine(trip, NOW.getTime(), AR)" in js


# ---------------------------------------------------------------- #28 box office only
def test_box_office_only_card_leads_with_the_box_office():
    t = (JS / "ticket.js").read_text(encoding="utf-8")
    assert 'box: "الخصم من الشباك بس"' in t and 'box: "Discount at the box office only."' in t
    assert "r.box_office_only && after(100, chain" in t and "a.href = mapsTo(cin)" in t
    assert "renderBook(chain);" in t and "renderBook(x.chain);" in t


@needs_node
def test_box_office_button_in_node(tmp_path):
    # a ticket and its button as plain objects: Star + Fazaa (box office only) swaps the button, no card restores it
    harness = """
    function el(attrs) { var a = Object.assign({}, attrs), cls = {};
      return { getAttribute: function (k) { return k in a ? a[k] : null; }, setAttribute: function (k, v) { a[k] = String(v); },
        hasAttribute: function (k) { return k in a; }, removeAttribute: function (k) { delete a[k]; },
        toggleAttribute: function (k, on) { if (on) a[k] = ""; else delete a[k]; },
        classList: { contains: function (c) { return !!cls[c]; } }, textContent: "", set href(v) { a.href = v; }, get href() { return a.href; } }; }
    var btn = el({ href: "https://www.starcinemas.ae/now-showing-booking/2557/1/" });
    tk = el({ "data-cin": "star-al-ghurair-centre-dubai", "data-hc": "Standard", "data-hkey": "Standard" });
    tk.querySelector = function (s) { return s === "[data-tk-book]" ? btn : null; };
    G = { "star-al-ghurair-centre-dubai": ["dubai", "star", 25.2678, 55.31749] };
    D = { rules: { star: { fazaa: { type: "percent", value: 20, box_office_only: true } } } };
    C.book_at = "احجز من موقع {chain}";
    card = "fazaa"; renderBook("star"); var on = [btn.textContent, btn.href];
    card = ""; renderBook("star"); var off = [btn.textContent, btn.href];
    """
    src = STUB + "".join((JS / f).read_text(encoding="utf-8") for f in ("disc.js", "near.js", "prices.js", "ticket.js"))
    (tmp_path / "t.js").write_text(src + harness + "\nprocess.stdout.write(JSON.stringify([on, off]));\n", encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    on, off = json.loads(r.stdout)
    assert on == ["الخصم من الشباك بس", "https://www.google.com/maps/dir/?api=1&destination=25.2678,55.31749"]
    assert off == ["احجز من موقع star", "https://www.starcinemas.ae/now-showing-booking/2557/1/"]


# ---------------------------------------------------------------- #29 the seats index
def test_seats_index_lists_exactly_the_files_that_exist(site):
    out, _, with_seats = site
    sdir = Path(out, "data", "seats")
    ix = json.loads((sdir / "index.json").read_text(encoding="utf-8"))
    files = sorted(p.stem for p in sdir.glob("*.json") if p.name != "index.json")
    assert ix == files == sorted(with_seats)


def test_seats_index_is_written_when_no_cinema_has_seats(tmp_path):
    out = str(tmp_path / "o")
    build.build(DATA, DISC, out, noindex=False)
    assert json.loads(Path(out, "data", "seats", "index.json").read_text(encoding="utf-8")) == []


@needs_node
def test_seat_chunk_asks_only_for_listed_cinemas(tmp_path):
    src = (JS / "seatmap.js").read_text(encoding="utf-8")
    harness = """
    var asked = [], document = { body: {} };
    var K = {AR: true, lang: "ar", esc: String, q: function () { return null; }, qa: function () { return []; },
      getJSON: function (u) { asked.push(u); return Promise.resolve(u.indexOf("index.json") >= 0 ? ["listed"] : null); } };
    function btn(cin) { return { closest: function (s) {
        if (s === "[data-cin]") return { getAttribute: function () { return cin; } };
        if (s === "[data-d]") return { getAttribute: function () { return "2026-09-27"; } };
        if (s === ".cf, .srow") return { getAttribute: function () { return "f"; } };
        return null; }, getAttribute: function () { return "22:10"; } }; }
    var tk = { hidden: false, getAttribute: function () { return null; } };
    """ + src + """
    forTime(tk, btn("missing"), false); forTime(tk, btn("listed"), false);
    setTimeout(function () { process.stdout.write(JSON.stringify(asked)); }, 50);
    """
    (tmp_path / "t.js").write_text(harness.replace("if (typeof document !== \"undefined\" && K.q) start();", ""), encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    asked = json.loads(r.stdout)
    assert "/data/seats/listed.json" in asked and "/data/seats/missing.json" not in asked
    assert set(asked) == {"/data/seats/index.json", "/data/seats/listed.json"}


# ---------------------------------------------------------------- #27 #30 and the bundle
def test_bundle_carries_the_new_client_and_parses(tmp_path):
    js = build.bundle_js()
    for fn in ("function showKey", "function showFromHash", "function rollTicket", "function pickState", "function renderBook",
               "function nowPick", "function scoreRank", "function hidePassed", "function planLeaveLine", "function planTrip"):
        assert fn in js, fn
    assert "اختار وقت" in js
    if NODE:
        p = tmp_path / "b.js"
        p.write_text(js, encoding="utf-8")
        r = subprocess.run([NODE, "--check", str(p)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


def test_the_minute_moves_the_ticket_and_hides_passed_halls():
    main = (JS / "main.js").read_text(encoding="utf-8")
    assert "marks(); hidePassed(); ages(); renderNow(); rollTicket();" in main
    f = (JS / "filters.js").read_text(encoding="utf-8")
    assert 'var GONE = ".hl, .tl, .scin, .cg, .cf, .srow, .fcity, .day[data-d]";' in f
    # «ما في شي يطابق» is never blamed on the clock: the empty list is judged without the blocks whose times ran out
    assert ".filter(function (el) { return gone.get(el) !== 1; })" in f and "var gone = hidePassed();" in f
