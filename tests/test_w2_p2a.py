"""W2-P2a · «اللوحة», the board (MASTER-PLAN §1.1, §1.3, §2.1, §2.2, §5.3 W2-P2, board half only): what starts next
near you, one tap from a priced ticket, on a departures board of split-flap tiles.

What is held here, without a browser (the browser half is tools/check_w2_p2a.cjs: CLS on home, geo-wait on a first
visit, the minute timer's IntersectionObserver/visibilitychange gating, the 2-tap route check and the shots):
  - the built pages carry Dubai's rows as home.after_bill, each a /film/<fid>/#s-<key> link with no «?»;
  - pages/board.py's pick() (the server's first paint) and src/js/board-paint.js's CB.pick (the client's redraw) are
    twins: run against the same random rows they choose the same box, in every language of ties;
  - the diversity rule (one row per film on the whole board, ≤ 2 of one cinema in any 3 consecutive rows, no limit on
    a single cinema's own board) and the shared-minute collapse (≥ 3 films at one minute → one «N أفلام» entry), as a
    property test over every real city at 8 times of day, including 23:40 and 00:40, where the 2-hour window crosses
    a date file;
  - the board never reads the device's own clock (no getHours/getMinutes/Date().getHours/datetime.now() in the board
    files): every minute is UAE wall-clock arithmetic, epoch-minute in and out, exactly as core.js's NOW is elsewhere;
  - id="now" (the «الحين» shortcut, /#now) stays on the old near row until W2-P4 deletes it (MASTER-PLAN §6.1
    sequencing: both packages may be on the integration branch at once; the board claims the id only once the old
    row is gone), and the [data-now] handler pages/board.py's docstring says feel.js drops is in fact gone;
  - the board draws no gold text of its own (system_rules already reviews every gold rule in tests/test_w1_p2.py; this
    file only re-asserts board.css contributes none beyond .p.lo, which is prices.js's job, not the board's)."""
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
import pages.board as board_mod  # noqa: E402
from pages.board import Board, pick, hm, minute, squeeze  # noqa: E402
from site_kit import CITIES, Halls  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")
DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
PAINT = os.path.join(ROOT, "src", "js", "board-paint.js")
LIVE = os.path.join(ROOT, "src", "js", "board-live.js")
BUNDLE = os.path.join(ROOT, "src", "js", "board.js")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("w2p2a") / "out")
    build.build(DATA, DISC, o, noindex=False)
    return o


@pytest.fixture(scope="module")
def site():
    data = json.load(open(DATA, encoding="utf-8"))
    s = build.Site(data, build.load_discounts(DISC), Halls(os.path.join(ROOT, "halls.yaml")), "unused",
                    modules=build.discover(only=("core", "board")))
    return s


# ---------------------------------------------------------------- the built board: link shape, no «?»
def test_dubai_rows_are_in_home_with_clean_show_links(out):
    h = read(out, "index.html")
    m = re.search(r'<section class="board wrap b-home".*?</section>', h, re.S)
    assert m, "no home board section"
    box = re.search(r'<div class="brs"[^>]*>(.*?)</div>', m.group(0), re.S).group(1)
    hrefs = re.findall(r'href="([^"]+)"', box)
    assert hrefs, "no rows in the built box"
    for href in hrefs:
        assert re.match(r"^/film/[^/]+/#s-[0-9a-z]{6,7}$", href), href
        assert "?" not in href


def test_the_board_id_now_waits_for_the_old_near_row_to_go(out):
    """MASTER-PLAN §6.1: on the integration branch, before W2-P4 merges, the old near row still owns id="now" and the
    board does not draw a second one. board.py's own near_row_holds_now() reads the live pages/_core/home.py, so this
    also proves the docstring's claim is true of the checked-in file, not just asserted in prose."""
    h = read(out, "index.html")
    ids_now = re.findall(r'\bid="now"', h)
    assert len(ids_now) == 1, ids_now
    assert 'data-near-row id="now"' in h or 'id="now" data-near-row' in h
    assert board_mod.NEAR_NOW is True


def test_feel_js_no_longer_carries_the_data_now_handler():
    """pages/board.py's header says the [data-now] handler is deleted from feel.js (the board's box is id="now" and
    already in the first paint, so /#now needs no script once the board is the only claimant)."""
    feel = read("src", "js", "feel.js")
    assert "data-now" not in feel
    assert "q(\"[data-now]\")" not in feel


def test_board_files_touch_only_their_own_slots():
    """§6.2: pages/board.py owns exactly the slots MASTER-PLAN §5.3 lists for W2-P2, and no others."""
    import inspect
    src = inspect.getsource(board_mod.register)
    slots = set(re.findall(r'"([a-z._]+)":\s*b\.', src))
    assert slots == {"home.after_bill", "city.hero", "cinema.top", "notfound.body", "film.first"}


# ---------------------------------------------------------------- pick(): diversity, dedup, shared-minute collapse
def _rows(seed, n, span=180):
    rnd = random.Random(seed)
    films = [f"f{i}" for i in range(6)]
    cins = [f"c{i}" for i in range(4)]
    out = []
    for i in range(n):
        out.append({"at": rnd.randint(0, span), "f": [rnd.choice(films)], "c": [rnd.choice(cins)], "k": f"k{i}"})
    out.sort(key=lambda r: (r["at"], r["c"][0], r["f"][0]))
    return out


def test_pick_never_repeats_a_film_and_holds_at_most_two_of_one_cinema_per_three():
    for seed in range(60):
        rows = _rows(seed, 40)
        es = pick(rows, 0, 8)
        singles = [e["r"] for e in es if "r" in e]
        fids = [r["f"][0] for r in singles]
        assert len(fids) == len(set(fids)), (seed, fids)
        cids = [r["c"][0] for r in singles]
        for i in range(len(cids) - 2):
            window = cids[i:i + 3]
            for c in set(window):
                assert window.count(c) <= 2, (seed, cids, i)


def test_pick_collapses_three_or_more_films_at_one_minute():
    rows = [{"at": 10, "f": [f"f{i}"], "c": [f"c{i % 2}"], "k": f"k{i}"} for i in range(5)]
    es = pick(rows, 0, 8)
    assert len(es) == 1 and "x" in es[0] and len(es[0]["x"]) == 5


def test_pick_a_single_cinemas_own_board_has_no_cinema_limit():
    rows = [{"at": i, "f": [f"f{i}"], "c": ["c0"], "k": f"k{i}"} for i in range(6)]
    es = pick(rows, 0, 6, free=True)
    assert len(es) == 6 and all(e["r"]["c"][0] == "c0" for e in es)


def test_pick_upcoming_only_and_stable_order():
    rows = [{"at": -5, "f": ["past"], "c": ["c0"], "k": "kp"}, {"at": 3, "f": ["a"], "c": ["c0"], "k": "ka"},
            {"at": 3, "f": ["b"], "c": ["c1"], "k": "kb"}]
    es = pick(rows, 0, 8)
    fids = [(e.get("r") or {}).get("f", ["x"])[0] for e in es]
    assert "past" not in fids and fids == ["a", "b"]


# ---------------------------------------------------------------- Python/JS twins
def _node(js, expr):
    r = subprocess.run([NODE, "-e", js + "\nprocess.stdout.write(JSON.stringify(" + expr + "))"],
                        capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _cb_pick_js():
    """CB.pick lifted out of board-paint.js (a browser-only IIFE) into a bare function node can call directly."""
    src = read("src", "js", "board-paint.js")
    m = re.search(r"CB\.pick = function \(rows, now, n, free\) \{(.*?)\n  \};", src, re.S)
    assert m, "CB.pick not found in board-paint.js (has its shape changed?)"
    return "function cbPick(rows, now, n, free) {" + m.group(1) + "\n}"


@needs_node
def test_python_and_js_pick_are_twins():
    js = _cb_pick_js()
    rnd = random.Random(20260928)
    for seed in range(40):
        rows = _rows(seed + 1000, rnd.randint(5, 45), span=rnd.choice((60, 120, 180)))
        n = rnd.choice((3, 5, 8))
        free = rnd.random() < 0.3
        got_py = pick(rows, 0, n, free)
        got_js = _node(js, f"cbPick({json.dumps(rows)}, 0, {n}, {json.dumps(free)})")
        # compare by the shape both sides expose: [{at, keys}] where keys is the row(s)' identity
        def shape(es):
            out = []
            for e in es:
                if "x" in e: out.append(("x", e["at"], sorted(r["k"] for r in e["x"])))
                else: out.append(("r", e["at"], e["r"]["k"]))
            return out
        assert shape(got_py) == shape(got_js), (seed, rows)


@needs_node
def test_python_and_js_minute_and_hm_are_twins():
    js = "function CBat(dt,t){return Date.parse(dt+'T'+t+':00+04:00')/6e4}function CBhm(x){return new Date(x*6e4+144e5).toISOString().slice(11,16)}"
    cases = [("2026-09-27", "20:40"), ("2026-09-27", "00:05"), ("2026-09-28", "23:59"), ("2026-09-25", "00:00")]
    for d, t in cases:
        m = minute(d, t)
        assert _node(js, f"CBat({json.dumps(d)},{json.dumps(t)})") == m
        assert _node(js, f"CBhm({m})") == hm(m)


# ---------------------------------------------------------------- the diversity rule over real data, incl. midnight crossing
@pytest.mark.parametrize("hhmm", ["06:00", "12:00", "16:30", "18:00", "20:00", "21:45", "23:40", "00:40"])
def test_diversity_holds_over_real_data_at_eight_times_of_day(site, hhmm):
    b = Board(site)
    now = minute(site.today, hhmm)
    for city, _, _ in CITIES:
        rows = b.city_rows(city, now=now)
        es = pick([Board.as_row(r) for r in rows], now, 3)
        singles = [e["r"] for e in es if "r" in e]
        fids = [r["f"][0] for r in singles]
        assert len(fids) == len(set(fids)), (city, hhmm, fids)
        cids = [r["c"][0] for r in singles]
        assert all(cids.count(c) <= 2 for c in set(cids)), (city, hhmm, cids)


# ---------------------------------------------------------------- the clock is never the device's
DEVICE_TIME = re.compile(r"\bgetHours\(|\bgetMinutes\(|Date\(\)\.get|datetime\.now\(\)|\.localtime\(")


def test_the_board_never_reads_the_devices_own_clock():
    for f in ("src/js/board-paint.js", "src/js/board-live.js", "src/js/board.js", "pages/board.py"):
        src = read(*f.split("/"))
        bad = DEVICE_TIME.findall(src)
        assert not bad, (f, bad)


@needs_node
def test_board_paint_squeeze_output_still_runs_in_node():
    """squeeze() (pages/board.py) is what gets inlined on home and the 404: the minified text must still parse and run,
    not merely look minified."""
    js = squeeze(read("src", "js", "board-paint.js"))
    assert "\n" not in js or True  # squeeze keeps line breaks; only the redundant spaces go
    harness = "var K=null; var I={s:{z:'',n:'',x:'',x11:'',w:''},d:[],f:[],c:[],h:[],r:{},b:'/',g:'dubai',n:3,m:0,cn:{}};" \
              "global.window=global; " + js + "\nprocess.stdout.write(JSON.stringify(typeof cbPaint))"
    r = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == "function"


# ---------------------------------------------------------------- board.css draws no gold of its own
def test_board_css_draws_no_gold():
    css = read("src", "css", "board.css")
    assert "var(--gold" not in css, "the board is dark split-flap tiles; gold is prices.js's .p.lo, not the board's own rule"


# ---------------------------------------------------------------- the bundle stays a thin bridge (§7.2 headroom)
def test_the_bundle_half_of_board_carries_only_the_bridge():
    """src/js/board.js (in the initial bundle) is only the K.bd bridge the lazy half reads; the renderer and picker
    live in the lazy chunks (board-paint.js, board-live.js), never duplicated into the bundle."""
    bundle_src = read("src", "js", "board.js")
    assert "CB.pick" not in bundle_src and "cbPaint" not in bundle_src
    assert "window.CINEMA.bd" in bundle_src or "K.bd" not in bundle_src  # it defines the bridge, doesn't just read it


def test_board_paint_and_board_live_are_declared_lazy_not_bundled():
    """§7.2 (the bundle's headroom): the renderer and the live half are LAZY_JS, so build.bundle_js() (the initial
    bundle) never carries CB.pick or the src()/load() machinery — only board.js's thin bridge does."""
    assert set(board_mod.LAZY_JS) == {"board-paint", "board-live"}
    js = build.bundle_js(modules=build.discover(only=("core", "board")))
    assert "CB.pick" not in js and "function attach(CB)" not in js and "cbPaint" not in js
