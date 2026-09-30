"""pick.js, «اختار لي»'s scorer (legend W2-P2b, MASTER-PLAN §3.1). Golden-style tests over small frozen contexts,
following tests/test_w0_p3.py's node harness: pick.js is a lazy chunk (K = window.CINEMA), so it is run here after a
minimal stub of what src/js/board.js and src/js/filters.js hand it (K.bd, window.CINEMA.ask), with K.q standing in
for the grid tile a real page would carry the film's verdict/«مع منو» fit/rating on (kit/tile.py film_attrs).
Node tests skip without node, as tests/test_js.py does (the Fold may not have it)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")
JS = Path(ROOT, "src", "js", "pick.js")

# a minimal city slice (S), UAE minutes; `now` is 2026-10-01 20:00 Dubai time. Two cinemas (c1 3 km away, c2 20 km),
# three films: f1 «يستاهل» family-fit (G), f2 «تجنّبه», f3 unknown verdict, kids-fit
NOW_MS = 1000000000000  # an arbitrary fixed instant; only relative offsets below matter to the scorer
STUB = r"""
var K = (function () {
  var meta = %(meta)s, cins = { c1: {chain:"reel",ar:"سي وان",en:"C1"}, c2: {chain:"vox",ar:"سي تو",en:"C2"} };
  var km = { c1: 3, c2: 20 };
  function makeEl(attrs) { return { getAttribute: function (k) { return attrs.hasOwnProperty(k) ? attrs[k] : null; } }; }
  return {
    AR: true, lang: "ar", C: { aed: "درهم", base: "/", cards: { fazaa: "فزعة" }, after_card: "بعد خصم {card}" },
    q: function (sel) { var m = /data-fid="([^"]+)"/.exec(sel); var f = m && meta[m[1]]; return f ? makeEl(f) : null; },
    qa: function () { return []; },
    esc: function (s) { return String(s == null ? "" : s); },
    sub: function (s, o) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); },
    now: function () { return { getTime: function () { return %(now)s; } }; },
    city: function () { return "dubai"; },
    card: function () { return %(card)s; },
    showKey: function () { return "abcdef"; },
    fmt: function (n) { return String(n); },
    bd: {
      S: function () { return null; }, loc: function () { return null; }, G: function () { return null; },
      km: function (c) { return km[c]; }, kmt: function (k) { return k + " كم"; },
      nm: function (o) { return o ? o.ar : ""; }, days: function () { return ["2026-10-01", "2026-10-02"]; },
      day: function () { return Promise.resolve({ cinemas: {}, films: {}, shows: [] }); },
      /* mirrors src/js/prices.js priceHTML closely enough for the tests: with card "fazaa" every price is
         halved and struck (BOGO-shaped, just to exercise the discounted branch), and data-asof is dropped when
         RENDER_ASOF is false (unconfirmed dates never show as if they were live) */
      price: function (el) {
        var aed = +el.getAttribute("data-aed");
        if (%(card)s === "fazaa") {
          var pay = Math.round(aed / 2 * 100) / 100;
          el.setAttribute("data-shown", pay);
          return "<b>" + pay + '</b> <s class="num">' + aed + "</s>";
        }
        el.setAttribute("data-shown", aed);
        return '<span class="num">' + aed + "</span>";
      }
    }
  };
})();
function fakeEl() {
  var a = {};
  return { attrs: a, setAttribute: function (k, v) { a[k] = String(v); }, getAttribute: function (k) { return a.hasOwnProperty(k) ? a[k] : null; },
    hasAttribute: function (k) { return a.hasOwnProperty(k); }, insertAdjacentElement: function () {}, focus: function () {} };
}
var document = { addEventListener: function () {}, getElementById: function () { return null; }, createElement: function () { return fakeEl(); }, body: { appendChild: function () {} } };
var window = { CINEMA: { ask: function () { return %(ask)s; } } };
"""

META = {
    "f1": {"data-v": "yes", "data-fits": "family", "data-rating": "G"},
    "f2": {"data-v": "skip", "data-fits": "", "data-rating": ""},
    "f3": {"data-v": "unknown", "data-fits": "kids", "data-rating": ""},
}


def shows(now):
    """c1 f1 in 40 min (reachable, in the «الحين» plateau), c1 f2 «تجنّبه» in 40 min, c2 f3 in 45 min, at the same
    cinema c1 a second f1-like film f4 (also «يستاهل», so the diversity rule is exercised) 50 min out."""
    return [
        {"c": "c1", "f": "f1", "d": "2026-10-01", "t": "20:40", "h": "Standard", "k": "Standard", "p": [["a", 42]], "b": "https://reel.example/1", "at": now + 40 * 6e4},
        {"c": "c1", "f": "f2", "d": "2026-10-01", "t": "20:40", "h": "Standard", "k": "Standard", "p": [["a", 42]], "b": None, "at": now + 40 * 6e4},
        {"c": "c2", "f": "f3", "d": "2026-10-01", "t": "21:00", "h": "Standard", "k": "Standard", "p": [["a", 30]], "b": None, "at": now + 60 * 6e4},
        {"c": "c1", "f": "f4", "d": "2026-10-01", "t": "20:50", "h": "Standard", "k": "Standard", "p": [["a", 50]], "b": None, "at": now + 50 * 6e4},
        # unreachable: 5 min out, less than the 35-min no-location floor
        {"c": "c1", "f": "f5", "d": "2026-10-01", "t": "20:05", "h": "Standard", "k": "Standard", "p": [["a", 20]], "b": None, "at": now + 5 * 6e4},
    ]


META2 = dict(META, f4={"data-v": "yes", "data-fits": "family", "data-rating": "PG"}, f5={"data-v": "yes", "data-fits": "", "data-rating": ""})


def run(tmp_path, ask, meta=META2, now=NOW_MS, expr="null", pre="", card='""'):
    stub = STUB % {"meta": json.dumps(meta), "now": now, "ask": json.dumps(ask), "card": card}
    src = stub + "\n" + JS.read_text(encoding="utf-8") + "\n" + pre + "\nprocess.stdout.write(JSON.stringify(" + expr + "));\n"
    (tmp_path / "t.js").write_text(src, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_hard_filters_drop_started_unreachable_skip_and_who_mismatch(tmp_path):
    """f2 «تجنّبه» and f5 (5 min out, under the 35-min no-location floor) never reach the candidate list; with
    «العايلة», f3 (kids-only, no family fit) is excluded too."""
    fids = run(tmp_path, {"who": "", "when": "", "where": ""},
               pre="var c = pkCandidates(" + json.dumps({"cinemas": {}, "films": {}, "shows": shows(NOW_MS)}) + ", " + str(NOW_MS) + ", {who:'',when:''}, '2026-10-02');",
               expr="c.map(function(x){return x.s.f})")
    assert "f2" not in fids and "f5" not in fids and "f1" in fids and "f3" in fids and "f4" in fids


def test_candidate_pay_is_the_cheapest_positive_price(tmp_path):
    """Fix round, Critical #1: `Math.min` over positives concat([0]) always gave 0. A show with a real, positive
    price (f1: 42) must candidate at that price, never 0 — and a show with no priced seat at all (none in this
    fixture) still falls back to 0, not a crash."""
    pays = run(tmp_path, {},
               pre="var c = pkCandidates(" + json.dumps({"cinemas": {}, "films": {}, "shows": shows(NOW_MS)}) + ", " + str(NOW_MS) + ", {who:'',when:''}, '2026-10-02');",
               expr="c.reduce(function(o,x){o[x.s.f]=x.pay;return o;},{})")
    assert pays["f1"] == 42 and pays["f4"] == 50 and pays["f3"] == 30   # never 0 while a positive price exists

    fam = run(tmp_path, {}, meta=META2,
              pre="var c = pkCandidates(" + json.dumps({"cinemas": {}, "films": {}, "shows": shows(NOW_MS)}) + ", " + str(NOW_MS) + ", {who:'family',when:''}, '2026-10-02');",
              expr="c.map(function(x){return x.s.f})")
    assert "f3" not in fam and "f1" in fam and "f4" in fam   # f3 is kids-only, never assumed family-safe


def test_rank_is_deterministic_and_respects_the_diversity_rule(tmp_path):
    Y = {"cinemas": {"c1": {"chain": "reel", "ar": "سي وان", "en": "C1"}, "c2": {"chain": "vox", "ar": "سي تو", "en": "C2"}}, "films": {}, "shows": shows(NOW_MS)}
    pre = ("var cand = pkCandidates(" + json.dumps(Y) + ", " + str(NOW_MS) + ", {who:'',when:''}, '2026-10-02');"
           "var r1 = pkRank(cand, " + str(NOW_MS) + ", {who:'',when:''});"
           "var r2 = pkRank(cand, " + str(NOW_MS) + ", {who:'',when:''});")
    out = run(tmp_path, {}, pre=pre, expr="[r1.map(function(x){return x.c.s.f}), r2.map(function(x){return x.c.s.f}), r1.map(function(x){return x.c.s.c})]")
    assert out[0] == out[1]                       # the same inputs give the same pick, every time
    fids = out[0]
    assert len(fids) == len(set(fids))             # one card per film
    cins = out[2]
    counts = {}
    for c in cins: counts[c] = counts.get(c, 0) + 1
    assert all(n <= 2 for n in counts.values())     # ≤ 2 of one cinema among the kept cards


def test_why_always_names_something_and_carries_the_price(tmp_path):
    Y = {"cinemas": {"c1": {"chain": "reel", "ar": "سي وان", "en": "C1"}, "c2": {"chain": "vox", "ar": "سي تو", "en": "C2"}}, "films": {}, "shows": shows(NOW_MS)}
    pre = ("PK.Y = " + json.dumps(Y) + ";"
           "var cand = pkCandidates(PK.Y, " + str(NOW_MS) + ", {who:'',when:''}, '2026-10-02');"
           "var r = pkRank(cand, " + str(NOW_MS) + ", {who:'',when:''});"
           "var pr = pkPrice(r[0].c);"
           "var why = pkWhy(r[0], pkWhyPrice(pr), '2026-10-02');")
    why = run(tmp_path, {}, pre=pre, expr="why")
    assert why and why != ""                        # «ليش؟» is mandatory: it never renders empty
    assert "42" in why and "درهم" in why            # fix round Critical #1/Important #6: the real price, with its unit


def test_why_price_shows_after_card_only_when_the_card_actually_paid_less(tmp_path):
    """Fix round, Important #6: no card → plain «42 درهم»; card «fazaa» (which our price stub halves) →
    the shown (after-card) figure plus «بعد خصم فزعة», never the struck list price or the asof note run in beside
    it with no unit (the old bug: "29 42" glued together)."""
    Y = {"cinemas": {"c1": {"chain": "reel", "ar": "سي وان", "en": "C1"}}, "films": {}, "shows": shows(NOW_MS)}
    pre = ("var cand = pkCandidates(" + json.dumps(Y) + ", " + str(NOW_MS) + ", {who:'',when:''}, '2026-10-02');"
           "var f1 = cand.filter(function(c){return c.s.f==='f1';})[0];"
           "var pr = pkPrice(f1);")
    no_card = run(tmp_path, {}, pre=pre + "var out = pkWhyPrice(pr);", expr="out", card='""')
    assert no_card == '<span class="num">42</span> درهم'
    with_card = run(tmp_path, {}, pre=pre + "var out = pkWhyPrice(pr);", expr="out", card='"fazaa"')
    assert with_card == '<span class="num">21</span> درهم بعد خصم فزعة'


def test_why_start_reason_never_says_tonight_for_tomorrow_or_a_far_show(tmp_path):
    """Fix round, Important #5: a tomorrow show, or a same-day show hours out, must not be captioned «الليلة»."""
    Y = {"cinemas": {"c1": {"chain": "reel", "ar": "سي وان", "en": "C1"}}, "films": {}, "shows": [
        {"c": "c1", "f": "f1", "d": "2026-10-02", "t": "20:40", "h": "Standard", "k": "Standard", "p": [["a", 42]], "b": None, "at": NOW_MS + 24 * 3600e3},
        {"c": "c1", "f": "f4", "d": "2026-10-01", "t": "23:00", "h": "Standard", "k": "Standard", "p": [["a", 50]], "b": None, "at": NOW_MS + 2 * 3600e3},
    ]}
    pre = ("var cand = pkCandidates(" + json.dumps(Y) + ", " + str(NOW_MS) + ", {who:'',when:''}, '2026-10-02');"
           "var r = pkRank(cand, " + str(NOW_MS) + ", {who:'',when:''});"
           "var out = {};"
           "r.forEach(function(x){ out[x.c.s.f] = pkWhy(x, '', '2026-10-02'); });")
    out = run(tmp_path, {}, meta=META2, pre=pre, expr="out")
    assert "الليلة" not in out["f1"] and "بكرة" in out["f1"]      # tomorrow's show
    assert "الليلة" not in out["f4"]                              # 2 h out, past the 90-min "starts in N" window


def test_pk_pure_terms(tmp_path):
    got = run(tmp_path, {}, pre="", expr="""[pkVerdict('yes'), pkVerdict('mixed'), pkVerdict('unknown'),
      pkDist(2), pkDist(15), pkDist(40), pkDist(null),
      pkWhoFit({fits:'family',rating:'G'},'family'), pkWhoFit({fits:'family',rating:'PG13'},'family'),
      pkWhoFit({fits:'kids',rating:''},'kids'), pkWhoFit({fits:'',rating:''},'kids'), pkWhoFit({fits:'',rating:''},'')]""")
    assert got[:3] == [1, .55, .3]
    assert got[3] == 1 and got[5] == 0 and got[6] == .5 and got[4] == pytest.approx(1 - 12 / 27)
    assert got[7:] == [1, .5, 1, 0, .5]
