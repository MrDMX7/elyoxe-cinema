"""W1-P2 · the system (MASTER-PLAN §1.3–1.5, §5.2): tokens, gold = yours, type, paper.

What is held here, without a browser (the browser half is tools/check_w1_p2.cjs: the gold count on today's home and on
the fixture of the FINAL first screen, tests/fixtures/first_screen.html, the network log of the fonts, the 320 clip,
the press):
  - one price format, «42» for whole dirhams, the same in Python (site_kit.money) and in the page (pure.js fmt);
  - the struck price never glued to the paid one («33.6042.00»), in the server's markup and in the script's;
  - the type scale: the system's sheets (src/cinema.css, src/css/ui-*.css) declare only the 7 steps, the listed object
    sizes and 11 px; its spacing sits on a 4-pt grid; no backdrop-filter;
  - gold only where it is yours (a reviewed list of rules), never on paper, never a colon; velvet never as text on night;
  - every token pair the sheets draw text in is ≥ 4.5:1 (sRGB and the P3 variants);
  - the fonts: no Markazi Latin face, a ≤ 3 KB digits face, the wordmark's own face on /en/;
  - the paper primitives, the velvet jobs, the press states, the motion tokens;
  - Kit.tsize's length steps; one lit cheapest per row.
Node parts skip without node (the Fold may not have it), as tests/test_js.py does."""
import colorsys
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import site_kit  # noqa: E402
from site_kit import Kit, money  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
SYSTEM = [os.path.join(ROOT, "src", "cinema.css")] + sorted(glob.glob(os.path.join(ROOT, "src", "css", "ui-*.css")))


def read(p):
    return open(p, encoding="utf-8").read()


def rules(path):
    """[(selector, body, at-media or "")] of a stylesheet, comments out (one level of @media)."""
    css = re.sub(r"/\*.*?\*/", "", read(path), flags=re.S)
    out, i = [], 0
    for m in re.finditer(r"@media([^{]*)\{((?:[^{}]*\{[^{}]*\})*)\s*\}|([^{}@]+)\{([^{}]*)\}", css):
        if m.group(1) is not None:
            for r in re.finditer(r"([^{}]+)\{([^{}]*)\}", m.group(2)):
                out.append((r.group(1).strip(), r.group(2), m.group(1).strip()))
        else:
            out.append((m.group(3).strip(), m.group(4), ""))
    return out


def system_rules():
    return [(os.path.basename(p), s, b, at) for p in SYSTEM for s, b, at in rules(p)]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("w1p2")
    build.build(DATA, DISC, str(out))
    return out


# ---------------------------------------------------------------- one price format («42», «33.60»)
MONEY_CASES = [42, 42.0, "42", 33.6, 33.599999, 33.6000001, 52.5, 1.005, 10.125, 0.05, 0.005, 195, 19.99, 41.999, 0, 46.2, 57.75,
               37.6, 21, 26.25, 0.1 + 0.2, 99.995, 12.345, 1e-9]


def test_money_prints_whole_dirhams_without_fils():
    assert money(42) == "42" and money(42.0) == "42" and money("195") == "195"
    assert money(33.6) == "33.60" and money(52.5) == "52.50" and money(19.99) == "19.99" and money(0.05) == "0.05"
    assert money(41.999) == "42" and money(33.599999) == "33.60"
    # half up at the fils, as Math.round: 10.125 is exactly representable, so it rounds up (Python's round() would not)
    assert money(10.125) == "10.13" and money(26.25) == "26.25"


def _js_fmt(tmp_path, values):
    src = read(os.path.join(ROOT, "src", "js", "pure.js"))
    (tmp_path / "f.js").write_text(src + "\nprocess.stdout.write(JSON.stringify(" + json.dumps(values) + ".map(function (v) { return fmt(+v); })));\n",
                                   encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "f.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_money_and_fmt_are_twins(tmp_path):
    """The build writes a price with site_kit.money, the page rewrites it with pure.js fmt after a card: the two must read
    the same for every price, or a tile's digits would flip with no card change."""
    rnd = random.Random(20260928)
    vals = [float(v) for v in MONEY_CASES]
    vals += [round(rnd.uniform(0, 400), rnd.choice((0, 1, 2, 3, 6))) for _ in range(3000)]
    vals += [a * (1 - p / 100) for a in (33, 35, 42, 45, 46, 52.5, 57.75, 65, 75, 95, 150, 195) for p in (5, 10, 12.5, 15, 20, 25, 30, 33, 40, 50)]
    vals += [a / 2 for a in range(0, 500)]
    assert _js_fmt(tmp_path, vals) == [money(v) for v in vals]


def test_the_page_formats_money_once():
    """fmt lives in pure.js (node-testable, beside the other pure helpers), not twice in the bundle."""
    js = build.bundle_js()
    assert len(re.findall(r"\bfunction fmt\(", js)) == 1
    assert "function fmt(" in read(os.path.join(ROOT, "src", "js", "pure.js"))
    assert "function fmt(" not in read(os.path.join(ROOT, "src", "js", "core.js"))
    assert ".toFixed(2)" not in re.sub(r"function fmt\([^\n]*", "", js), "a second price formatter crept into the bundle"


# ---------------------------------------------------------------- «33.6042.00»: the struck price after a gap
GLUED = (re.compile(r"\d\.\d\d\d"), re.compile(r"\d\d\.\d\d\d\d"))


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


def test_no_tile_text_reads_glued_in_the_built_pages(site):
    bad = []
    for p in glob.glob(os.path.join(str(site), "**", "index.html"), recursive=True):
        h = read(p)
        for m in re.finditer(r'<a class="(?:film )?tile[^"]*"[^>]*>(.*?)</a>', h, re.S):
            t = _text(m.group(1))
            if any(g.search(t) for g in GLUED): bad.append((os.path.relpath(p, str(site)), t[:80]))
    assert not bad, bad[:5]


@needs_node
def test_the_scripts_price_cells_put_a_gap_before_the_struck_price(tmp_path):
    """prices.js priceHTML (a cell after a card) and payCell (home's tiles and the billboard's «من X»): what you pay first,
    a space, then the list price struck; never «33.6042» for a reader or a screen reader."""
    js = "\n".join(read(os.path.join(ROOT, "src", "js", f)) for f in ("pure.js", "disc.js", "flip.js", "prices.js"))
    harness = r"""
var RM = false, C = { per_person: "للشخص", asof: "السعر بتاريخ {date}" }, card = "fazaa", TODAY = "2026-09-27";
var D = { rules: { vox: { fazaa: { type: "percent", value: 20 } } } };
function esc(s) { return String(s == null ? "" : s); }
function sub(s, o) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return o[k] != null ? o[k] : m; }); }
var attrs = { "data-aed": "42", "data-chain": "vox", "data-hall": "Standard", "data-hk": "Standard", "data-cin": "c" };
var el = { getAttribute: function (k) { return attrs[k] == null ? null : attrs[k]; }, setAttribute: function (k, v) { attrs[k] = v; },
  hasAttribute: function (k) { return attrs[k] != null; } };
var out = [priceHTML(el, false), payCell({ pay: 33.6, aed: 42, off: true, r: null }, false, null), payCell({ pay: 42, aed: 42, off: false, r: null }, false, null)];
process.stdout.write(JSON.stringify(out));
"""
    (tmp_path / "p.js").write_text(js + harness, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "p.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    cell, pay, plain = json.loads(r.stdout)
    assert _text(cell) == "33.60 42" and cell.index("<b>") < cell.index("<s")
    assert _text(pay) == "33.60 42" and pay == '<b>33.60</b> <s class="num">42</s>'
    assert plain == "<b>42</b>"
    for h in (cell, pay):
        assert not any(g.search(_text(h)) for g in GLUED)
    # home.js builds its tile cells and the billboard's «من X» with payCell: no hand-glued copy left
    home = read(os.path.join(ROOT, "src", "js", "home.js"))
    assert "payCell(b, go, was)" in home and '"</b>" + (b.off' not in home


# ---------------------------------------------------------------- gold = yours: the rows' single cheapest
def test_each_home_row_lights_its_single_cheapest(site):
    h = read(os.path.join(str(site), "index.html"))
    strips = re.findall(r'<div class="strip" data-strip data-lo>(.*?)</div></section>', h, re.S)
    assert strips, "no home row carries data-lo"
    for s in strips:
        cells = re.findall(r'<span class="p( lo)?" data-aed="([0-9.]+)"', s)
        if not cells: continue
        lit = [float(v) for lo, v in cells if lo]
        assert len(lit) == 1 and lit[0] == min(float(v) for _, v in cells)
        first = next(i for i, (lo, v) in enumerate(cells) if float(v) == lit[0])
        assert cells[first][0], "a tie lights the first cheapest, as prices.js lows() does"
    assert Kit.lo('<span class="p" data-aed="42"></span><span class="p" data-aed="33.6"></span><span class="p" data-aed="33.6"></span>') == \
        '<span class="p" data-aed="42"></span><span class="p lo" data-aed="33.6"></span><span class="p" data-aed="33.6"></span>'
    assert Kit.lo("<b>nothing priced</b>") == "<b>nothing priced</b>"


@needs_node
def test_lows_lights_one_per_row_with_no_card_and_none_with_one(tmp_path):
    js = read(os.path.join(ROOT, "src", "js", "prices.js"))
    harness = r"""
function cell(v, off) { var c = {}, a = { "data-shown": v };
  return { classList: { add: function (k) { c[k] = 1; }, remove: function (k) { delete c[k]; }, has: function (k) { return !!c[k]; } },
    getAttribute: function (k) { return a[k] == null ? null : a[k]; }, closest: function () { return off ? {} : null; } }; }
var row = [cell("52.50"), cell("42", true), cell("46.20"), cell("46.20")], table = [cell("35"), cell("35")];
var groups = [{ cells: row }, { cells: table }];
function qa(sel, root) { return root ? root.cells : groups; }
var card = "", out = [];
lows(); out.push(row.map(function (c) { return c.classList.has("lo"); }), table.map(function (c) { return c.classList.has("lo"); }));
card = "fazaa"; lows(); out.push(row.concat(table).some(function (c) { return c.classList.has("lo"); }));
process.stdout.write(JSON.stringify(out));
"""
    (tmp_path / "l.js").write_text(js + harness, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "l.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    # the cheapest showing tile (46.20; the 42 is «off», not showing in the city) lit once, the first on a tie; a card: none
    assert json.loads(r.stdout) == [[False, False, True, False], [True, False], False]


GOLD_RULES = {
    # the wordmark
    ".mark",
    # your number: the price after your card (a cell with a struck list price); with no card the row's cheapest
    ".p:has(s) b,.p.lo .num,.p.lo b",
    # «يستاهل»
    ".bill-v b.v-yes", ".fv.v-yes .word", ".v-yes .vw,.vw.v-yes", ".tile.v-yes .hv .vw",
    # what you chose: inside a sheet, and the day you picked
    ".opt[aria-pressed=true],.opt[aria-current],.sheet .chip[aria-pressed=true]", ".dy[aria-pressed=true] b",
    # a card's offer and the price after it, on the card pages
    ".crd .off", ".ex b", ".matrix td b",
    # the card sheet: each card's best number («فزعة 20%», MASTER-PLAN §2.0; W2-P5): what that card gives you
    ".opt .best",
}


def test_gold_is_only_yours():
    """Every rule of the system that draws TEXT in gold is on this reviewed list (§1.5): a new gold rule fails here until
    someone argues it is the visitor's own number, the verdict word, a choice, or the wordmark. Never a colon, a pill,
    a list price, a countdown or anything on paper."""
    got = {s for f, s, b, at in system_rules() if re.search(r"(?<![-\w])color:\s*var\(--gold(-hi)?\)", b)}
    assert got == GOLD_RULES, sorted(got ^ GOLD_RULES)
    for f, s, b, at in system_rules():
        if re.search(r"(?<![-\w])color:\s*var\(--gold", b):
            assert not re.search(r"\.(c|flip|pill|tk-|dk-|dock|ticket|paper|stub)\b", s), s
    # the colon of every flip time and clock is the dull part
    assert any(s == ".flip .c" and "color:var(--seat)" in b for f, s, b, at in system_rules())


def test_velvet_is_never_text_on_night():
    """Velvet text is 1.84:1 on night: it may colour words only on paper or the screen-light buttons."""
    for f, s, b, at in system_rules():
        if re.search(r"(?<![-\w])color:\s*var\(--velvet\)", b):
            assert re.search(r"\.(btn\.main|paper|tk-|dk-|ticket)", s), s


def test_the_velvet_jobs():
    r = {s: b for f, s, b, at in system_rules() if not at}
    assert "border-block-start-color:var(--velvet)" in r[".tabs a[aria-current]"]          # the tab bar's 2 px bar
    assert "border-block-start:2px solid transparent" in r[".tabs a"].replace(" ", " ")
    on = r[".tm.on,.tm[aria-current],.tm:active"]
    assert "background:var(--velvet)" in on and "color:var(--screen)" in on                 # a pressed time fills velvet
    assert "background:var(--velvet)" in r[".tx .tm.on,.tx .tm[aria-current]"]
    tag = r[".tile .tag"]
    assert "background:var(--velvet)" in tag and "font-size:12px" in tag                   # tags 12 px
    assert "background:var(--velvet)" in r[".tk-act .book"] and "background:var(--velvet)" in r[".btn.velvet"]


# ---------------------------------------------------------------- contrast
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum_hex(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _lum_p3(r, g, b):
    return 0.2289746 * _lin(r) + 0.6917385 * _lin(g) + 0.0792869 * _lin(b)


def tokens():
    root = re.search(r":root\{(.*?)\}", re.sub(r"/\*.*?\*/", "", read(SYSTEM[0]), flags=re.S), re.S).group(1)
    t = {k: v.strip() for k, v in re.findall(r"--([\w-]+):([^;]+)", root)}
    p3 = re.search(r"@media \(color-gamut:p3\)\{:root\{(.*?)\}\}", read(SYSTEM[0]), re.S).group(1)
    return t, {k: tuple(float(x) for x in v.split()) for k, v in re.findall(r"--([\w-]+):color\(display-p3 ([^)]+)\)", p3)}


def ratio(a, b):
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# every pair the system draws text in (text on ground), from the rules below plus the §1.5 table
TEXT_PAIRS = [("screen", "night"), ("dim", "night"), ("seat", "night"), ("gold", "night"), ("live", "night"),
              ("screen", "velvet"), ("gold", "velvet"), ("dim", "velvet"), ("screen", "ink"), ("gold", "ink"),
              ("ink", "screen"), ("ink-2", "screen"), ("velvet", "screen"), ("night", "screen"),
              ("ink", "paper-2"), ("ink-2", "paper-2"), ("ink", "paper-hi"), ("ink", "paper-lo"), ("ink-2", "paper-lo"), ("velvet", "paper-lo"),
              ("screen", "tile"), ("seat", "tile"), ("ink", "gold")]


def test_every_token_pair_drawn_as_text_is_at_least_4_5_to_1():
    t, p3 = tokens()
    lum = {k: _lum_hex(v) for k, v in t.items() if re.fullmatch(r"#[0-9A-Fa-f]{6}", v)}
    low = [(a, b, round(ratio(lum[a], lum[b]), 2)) for a, b in TEXT_PAIRS if ratio(lum[a], lum[b]) < 4.5]
    assert not low, low
    # a screen that shows P3 gets a richer gold and velvet: the same pairs hold there
    lum3 = dict(lum, **{k: _lum_p3(*v) for k, v in p3.items()})
    low3 = [(a, b, round(ratio(lum3[a], lum3[b]), 2)) for a, b in TEXT_PAIRS if ratio(lum3[a], lum3[b]) < 4.5]
    assert set(p3) == {"gold", "velvet"} and not low3, low3
    assert ratio(lum3["gold"], lum["night"]) >= 9.5          # «gold on night stays» about 10:1 (§1.5)
    # and every rule that sets both a text token and a ground token in one place
    for f, s, b, at in system_rules():
        c = re.search(r"(?<![-\w])color:\s*var\(--([\w-]+)\)", b)
        g = re.search(r"(?<![-\w])background(?:-color)?:\s*var\(--([\w-]+)\)", b)
        if c and g and c.group(1) in lum and g.group(1) in lum:
            assert ratio(lum[c.group(1)], lum[g.group(1)]) >= 4.5, (f, s, c.group(1), g.group(1))


def test_gold_and_green_never_go_on_paper():
    for f, s, b, at in system_rules():
        if re.search(r"\.(paper|stub|ticket|tk-\w+|dock|dk-\w+)\b", s):
            assert not re.search(r"(?<![-\w])color:\s*var\(--(gold|live)", b), s


# ---------------------------------------------------------------- type: seven steps
SCALE = {"var(--fs-hero)", "var(--fs-h1)", "var(--fs-h2)", "var(--fs-title)", "var(--fs-body)", "var(--fs-meta)", "var(--fs-time)", "inherit"}
# the listed object sizes (§1.4) and the few named exceptions, each with its job
OBJECT_PX = {"11px": "licence credits", "12px": "velvet tags (§1.5)", "20px": "board row time on flip tiles", "22px": "the verdict word on the billboard",
             "32px": "the wordmark (the h1 step's floor)"}


def test_the_type_scale_tokens():
    t, _ = tokens()
    assert t["fs-hero"] == "clamp(38px,12vw,64px)" and t["fs-h1"] == "clamp(32px,8vw,48px)" and t["fs-h2"] == "28px"
    assert t["fs-title"] == t["fs-body"] == "16px" and t["fs-meta"] == "13px" and t["fs-time"] == "17px"
    assert t["lh-body"] == "1.75" and "--lh-body:1.55" in read(SYSTEM[0])     # Arabic 1.75, English 1.55
    body = next(b for f, s, b, at in system_rules() if s == "body" and not at)
    assert "font-variant-numeric:tabular-nums lining-nums" in body and "font-size:var(--fs-body)" in body


def test_the_system_declares_only_the_scale():
    """Every font-size (and font shorthand size) in the system's sheets is a scale token, a title set by length, or a
    listed object size: 29 sizes and two clamps are gone (MASTER-PLAN §5.2 W1-P2)."""
    bad = []
    for f, s, b, at in system_rules():
        for v in re.findall(r"(?<![-\w])font-size:\s*([^;]+)", b):
            v = v.strip()
            if v in SCALE or v in OBJECT_PX: continue
            if v in ("min(var(--tsize,var(--fs-hero)),16vw)", "min(calc(var(--tsize,64px) * 1.5),96px)"): continue
            bad.append((f, s, v))
        for v in re.findall(r"(?<![-\w])font:\s*([^;]+)", b):
            size = re.search(r"(var\(--fs-[\w]+\)|\d+px)(?=/|\s)", v)
            if size and size.group(1) not in SCALE and size.group(1) not in OBJECT_PX: bad.append((f, s, v))
    assert not bad, bad
    sizes = {v.strip() for f, s, b, at in system_rules() for v in re.findall(r"(?<![-\w])font-size:\s*([^;]+)", b)}
    assert not {v for v in sizes if re.fullmatch(r"[\d.]+(px|em|rem)", v)} - set(OBJECT_PX)


def test_titles_are_sized_by_length_never_clamped():
    assert [Kit.tsize(t) for t in ("قلب الوحش", "ريزدنت ايفل", "x" * 12, "x" * 13, "x" * 20, "x" * 21, "x" * 30, "x" * 31, "")] == \
        [64, 64, 64, 48, 48, 38, 38, 32, 64]
    # marks and joiners add nothing a reader counts
    assert Kit.tsize("مُحَمَّد‌ علي") == Kit.tsize("محمد علي") == 64
    r = {s: b for f, s, b, at in system_rules() if not at}
    assert "min(var(--tsize,var(--fs-hero)),16vw)" in r[".bill-t"] and "min(var(--tsize,var(--fs-hero)),16vw)" in r[".ft"]
    assert "text-wrap:balance" in r["h1,h2,h3"]
    assert "line-clamp" not in r[".ft"]


def test_paragraphs_are_paragraph_light_with_arabic_leading():
    r = {s: b for f, s, b, at in system_rules() if not at}
    for s in (".fv", ".bill-v", ".syn", ".lead", ".hall p", ".faq details p"):
        assert "color:var(--dim)" in r[s] and "line-height:var(--lh-body)" in r[s], s
    for s in (".fv .word", ".bill-v b"):
        assert "var(--display)" in r[s], s


# ---------------------------------------------------------------- space: a 4-pt grid, a 16 px gutter
def test_spacing_sits_on_a_4pt_grid():
    bad = []
    for f, s, b, at in system_rules():
        for prop, v in re.findall(r"(?<![-\w])((?:margin|padding|gap|row-gap|column-gap)(?:-(?:inline|block)(?:-(?:start|end))?)?)\s*:\s*([^;]+)", b):
            for n in re.findall(r"(-?\d*\.?\d+)px", v):
                if abs(float(n)) > 2 and float(n) % 4: bad.append((f, s, prop, v))
    assert not bad, bad
    t, _ = tokens()
    assert t["gut"] == "16px" and [t[f"s{i}"] for i in range(1, 9)] == ["4px", "8px", "12px", "16px", "24px", "32px", "48px", "64px"]


def test_no_backdrop_filter():
    assert not [s for f, s, b, at in system_rules() if "backdrop-filter" in b]


# ---------------------------------------------------------------- motion and press
def test_motion_tokens_and_press():
    t, _ = tokens()
    assert t["ease-out"] == "cubic-bezier(.19,1,.22,1)" and t["ease-sheet"] == "cubic-bezier(.32,.72,0,1)" and t["ease-house"] == "cubic-bezier(.65,0,.35,1)"
    src = read(SYSTEM[0])
    assert "-webkit-tap-highlight-color:transparent" in src
    press = re.search(r"@media \(prefers-reduced-motion:no-preference\)\{(:is\(\.btn,\.chip,\.opt,\.tm,\.tabs a,\.dk-b\):active[^{]*)\{([^}]*)\}\}", src)
    assert press and "transform:scale(.97)" in press.group(2) and "transition-duration:0s" in press.group(2)
    assert re.search(r"\.btn,\.chip,\.opt,\.tm,\.tp,\.film \.pst,\.dk-b\{transition:transform \.14s var\(--ease-out\)\}", src)
    assert "@media (hover:none){.tile:active .tp,.film:active .pst{opacity:.85}}" in src
    tabs = read(os.path.join(ROOT, "src", "css", "ui-tabs.css"))
    assert "transition:color .18s" in tabs          # a tab changes colour in 180 ms and never slides
    every = "".join(read(p) for p in SYSTEM)
    assert "var(--ease)" not in re.sub(r"--ease:var\(--ease-out\)", "", every), "every curve is one of the three"


# ---------------------------------------------------------------- fonts
def test_no_markazi_latin_face_and_a_tiny_digits_face():
    css = build.css_source()
    assert "markazi-700-latin" not in css                       # never on a page (§7.1): Latin in a Markazi run falls to Readex
    faces = re.findall(r"@font-face\{([^}]*)\}", css)
    digits = [f for f in faces if "markazi-700-digits" in f]
    assert len(digits) == 1 and "unicode-range:U+0030-003A" in digits[0] and '"Markazi Text"' in digits[0]
    mark = [f for f in faces if "markazi-700-mark" in f]
    assert len(mark) == 1 and '"Markazi Mark"' in mark[0]
    assert re.search(r'\[lang=en\] \.mark\{font-family:"Markazi Mark",serif\}', read(os.path.join(ROOT, "src", "css", "ui-chrome.css")))
    for n, cap in (("markazi-700-digits.woff2", 3000), ("markazi-700-mark.woff2", 3000)):
        assert os.path.getsize(os.path.join(ROOT, "src", "fonts", n)) <= cap, n
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "subset_digits.py"), "--check"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    from fontTools.ttLib import TTFont
    assert sorted(TTFont(os.path.join(ROOT, "src", "fonts", "markazi-700-digits.woff2")).getBestCmap()) == list(range(0x30, 0x3B))
    assert sorted(TTFont(os.path.join(ROOT, "src", "fonts", "markazi-700-mark.woff2")).getBestCmap()) == sorted(ord(c) for c in "سينما")


def test_the_wordmark_is_arabic_on_en_too(site):
    en, ar = read(os.path.join(str(site), "en", "index.html")), read(os.path.join(str(site), "index.html"))
    assert en.count('<a class="mark" href="/en/" lang="ar" aria-label="Cinema">سينما</a>') == 2
    assert ar.count('<a class="mark" href="/">سينما</a>') == 2
    assert '<meta property="og:site_name" content="Cinema">' in en      # the language's own name stays in the metadata


# ---------------------------------------------------------------- paper
def test_the_paper_primitives():
    paper = {s: b for s, b, at in rules(os.path.join(ROOT, "src", "css", "ui-paper.css"))}
    assert paper[".paper"] == "background:var(--screen);color:var(--ink)"
    assert "grid-template-columns:minmax(0,1fr) 1px 104px" in paper[".stub"]
    perf = paper[".perf"]
    assert "var(--rule)" in perf and "repeating-linear-gradient" in perf
    notch = paper[".perf::before,.perf::after"]
    assert "inline-size:12px" in notch and "block-size:12px" in notch and "var(--notch,var(--night))" in notch
    assert "color:var(--velvet)" in paper[".paper .p:has(s) b"] and "color:var(--ink-2)" in paper[".paper .p s.num"]
    body = read(os.path.join(ROOT, "src", "css", "ui-paper.css"))
    assert "radius" not in re.sub(r"/\*.*?\*/", "", body, flags=re.S) and "box-shadow" not in body
    t, _ = tokens()
    assert (t["rule"], t["ink-2"], t["paper-hi"], t["paper-lo"], t["vnight"]) == ("#B9A987", "#5A4A33", "#FFF9EF", "#E7DCCB", "#140B0D")
    assert "--paper-hi" in paper[".paper.lit"] and "--paper-lo" in paper[".paper.lit"]


def test_the_struck_price_is_always_the_dull_part():
    """s.num outranks .p .num wherever a price sits (the old «.p s» lost to it: a struck price read gold or velvet)."""
    r = {s: b for f, s, b, at in system_rules() if not at}
    assert "color:var(--seat)" in r[".p s.num"] and "order:2" in r[".p s.num"]
    assert "color:var(--ink-2)" in r[".btn.main .p s.num"] and "color:var(--dim)" in r[".btn.velvet .p s.num"]
    assert "color:var(--ink-2)" in r[".tk-seats .p s.num"]
    assert "color:var(--screen)" in r[".p .num,.p b,.pv .num"] and "font-weight:600" in r[".p .num,.p b,.pv .num"]
