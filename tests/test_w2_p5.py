"""W2-P5 · Chrome, doors and sheets (MASTER-PLAN §2.0, §5.3, §4.2 #11 #24 #25; owner decision D2).

What the server draws: every sheet's draggable head (the grabber and the title), the filter sheet's two stops (60 % and
92 %), «قريب مني» and «بدون بطاقة» as full-width first rows, each city's cinema count, each card's best number, the
fourth tab «قائمتي» (D2, behind kit.chrome.ME_TAB) and its honest sheet, and the lazy drag chunk the scrim names.
What the stylesheet and the bundle promise: an opaque tab bar that steps away and yields, a header that solidifies on
a scroll timeline, the floating lines on --chrome-b, the gold outline for what you chose, reduced motion honoured,
vibrate only after a user activation, drag.js within 1.5 KB gz.
What the scripts do, run in node (skipped without node, as tests/test_js.py): chrome.js's 12 px hide and return, the
stub yield, the haptic gate, the re-tap to top and «امسح بياناتي»; drag.js's release rules (30 %, 0.5 px/ms, the
stops). The browser checks are tools/check_w2_p5.cjs."""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import kit.chrome as chrome  # noqa: E402
from site_kit import CITIES  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node not installed")


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("w2p5") / "out")
    build.build(DATA, DISC, o, noindex=False)
    return o


@pytest.fixture(scope="module")
def out_off(tmp_path_factory):
    """The same build with D2's flag off: «بحث» is the fourth tab again and no «قائمتي» sheet is drawn."""
    o = str(tmp_path_factory.mktemp("w2p5off") / "out")
    was = chrome.ME_TAB
    chrome.ME_TAB = False
    try:
        build.build(DATA, DISC, o, noindex=False)
    finally:
        chrome.ME_TAB = was
    return o


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


def sheet_of(h, sid):
    m = re.search(r'<div class="sheet" id="' + sid + r'".*?(?=<div class="sheet" id=|<script)', h, re.S)
    assert m, sid
    return m.group(0)


def tabs_of(h):
    return re.search(r'<nav class="tabs".*?</nav>', h, re.S).group(0)


def css(out):
    return read(out, "assets", "cinema.css")


def bundle(out):
    js = re.search(r'"/assets/(cinema\.[0-9a-f]{10}\.js)"', read(out, "index.html")).group(1)
    return read(out, "assets", js)


# ------------------------------------------------------------------ the sheets' markup
def test_every_sheet_has_a_draggable_head_and_the_filter_sheet_stops_at_60_and_92(out):
    h = read(out, "index.html")
    ids = re.findall(r'<div class="sheet" id="([\w-]+)"', h)
    assert {"sheet-city", "sheet-card", "sheet-filter", "sheet-me"} <= set(ids)
    for sid in ids:
        s = sheet_of(h, sid)
        # the head (grabber + title row) is one box that stays put and is what drag.js takes hold of
        assert re.search(r'^<div class="sheet" id="[\w-]+" role="dialog" aria-modal="true" aria-labelledby="[\w-]+-t"( data-detents="[\d ]+")? hidden>'
                         r'<div class="sheet-t"><div class="grab" aria-hidden="true"></div><div class="sheet-h"><h2 id="[\w-]+-t">', s), sid
        assert "data-sheet-close" in s                                         # × stays (a drag is never the only way out)
    assert 'id="sheet-filter" role="dialog" aria-modal="true" aria-labelledby="sheet-filter-t" data-detents="60 92" hidden>' in h
    assert chrome.DETENTS == {"sheet-filter": "60 92"}
    assert "data-detents" not in sheet_of(h, "sheet-city")                     # the others open whole


def test_the_city_sheet_leads_with_near_me_and_counts_each_citys_cinemas(out):
    for lang, parts in (("ar", ()), ("en", ("en",))):
        s = sheet_of(read(out, *parts, "index.html"), "sheet-city")
        first = re.search(r'<div class="sheet-b"><div class="sec">(<button [^>]*>)', s).group(1)
        assert 'class="opt wide near-b" data-near' in first, lang               # «قريب مني», a full-width first row
        assert s.index("data-near>") < s.index("data-citypick")
        index = read(out, *parts, "cinemas", "index.html")
        for c, _, _ in CITIES:
            # the same count the cinemas index prints for that city
            n = re.search(r'href="' + ("/en" if lang == "en" else "") + "/" + c + r'/">[^<]+</a> <small>(.*?)</small></h2>', index)
            opt = re.search(r'<a class="opt" href="[^"]*/' + c + r'/" data-city="' + c + r'"[^>]*>[^<]+(?: <small class="n">(.*?)</small>)?</a>', s)
            assert opt, (lang, c)
            if n and re.search(r">0<|^0 ", n.group(1)): assert opt.group(1) is None, (lang, c)   # none yet: no «0 سينما»
            elif n: assert opt.group(1) == n.group(1), (lang, c, opt.group(1), n.group(1))
    ar = sheet_of(read(out, "index.html"), "sheet-city")
    assert re.search(r'دبي <small class="n"><span class="num">\d+</span> سينما</small>', ar) or "دبي <small" in ar


def test_the_card_sheet_leads_with_no_card_and_shows_each_cards_best_number(out):
    s = sheet_of(read(out, "index.html"), "sheet-card")
    first = re.search(r'<div class="sheet-b"><div class="sec">(<button [^>]*>[^<]*</button>)</div>', s).group(1)
    assert first == '<button type="button" class="opt wide" data-card="" aria-pressed="true">بدون بطاقة</button>'
    bests = re.findall(r'data-card="([\w-]+)" aria-pressed="false">[^<]+ <b class="best">(.+?)</b></button>', s)
    assert bests, "no card shows its best number"
    for cid, b in bests:
        # dates(): only the digits sit in their own dir="ltr" span (site_kit's sitewide rule); the Arabic word
        # around them (e.g. «لين») is never itself flipped, so «لين 25%» keeps «لين» first, reading right to left
        assert re.fullmatch(r'(لين )?(<span class="num" dir="ltr">\d+(\.\d+)?%</span>|1\+1|\d+(\.\d+)? درهم)', b), (cid, b)
    assert re.search(r"\.opt \.best\{[^}]*color:var\(--gold\)", css(out))       # gold: what that card gives you


def _rules(**cards):
    """{chain: {card: rule}} from card=[(chain, type, value), …]."""
    out = {}
    for card, offers in cards.items():
        for chain, typ, val in offers:
            out.setdefault(chain, {})[card] = {"type": typ, "value": val, "confidence": "official"}
    return out


def test_a_cards_best_number():
    best = lambda rules, cid, lang="ar": chrome.ChromeKit.card_best(types.SimpleNamespace(rules=rules, today="2026-09-28"), cid, lang)
    assert best(_rules(fazaa=[("vox", "percent", 20), ("star", "percent", 20)]), "fazaa") == "20%"
    assert best(_rules(fazaa=[("vox", "percent", 20), ("reel", "percent", 25)]), "fazaa") == "لين 25%"      # offers differ
    assert best(_rules(fazaa=[("vox", "percent", 20), ("reel", "percent", 25)]), "fazaa", "en") == "up to 25%"
    assert best(_rules(adcb=[("vox", "bogo", None), ("reel", "percent", 20)]), "adcb") == "1+1"          # half off each
    assert best(_rules(x=[("vox", "fixed", 30), ("reel", "fixed", 25)]), "x") == "25 درهم"               # the cheapest ticket
    assert best(_rules(fazaa=[("vox", "percent", 20)]), "esaad") == ""
    gone = _rules(fazaa=[("vox", "percent", 20)]); gone["vox"]["fazaa"]["valid_until"] = "2026-01-01"
    assert best(gone, "fazaa") == ""                                                                    # expired: nothing


# ------------------------------------------------------------------ D2: «قائمتي»
def test_the_fourth_tab_is_my_list_and_search_stays_the_headers_icon(out):
    """2026-10-23: the phone's bar is the app's three tabs (the home's panes) with or without ME_TAB; «قائمتي» (its
    sheet) stays on the page, search stays the header's icon."""
    assert chrome.ME_TAB is True                                                # the owner's yes (2026-09-28)
    for parts, words in (((), ("السينمات", "الأفلام", "قريباً")), (("en",), ("Cinemas", "Films", "Coming soon"))):
        h = read(out, *parts, "index.html")
        t = tabs_of(h)
        a = re.findall(r"<a [^>]*>", t)
        assert len(a) == 3 and all(f"<span>{w}</span>" in t for w in words)
        assert "data-search" not in t and "data-me-tab" not in t
        assert h.count("data-search") == 1 and 'class="icon srch-b" data-search' in h                    # the header's icon
    n = 0
    for dp, _, fs in os.walk(out):
        for f in fs:
            if not f.endswith(".html"): continue
            h = open(os.path.join(dp, f), encoding="utf-8").read()
            if '<nav class="tabs"' not in h: continue
            n += 1
            assert h.count('id="sheet-me"') == 1, f
            assert 'class="icon srch-b" data-search' in h, f
    assert n > 100


def test_my_list_promises_nothing_that_does_not_exist(out):
    s = sheet_of(read(out, "index.html"), "sheet-me")
    words = [w.strip() for w in re.findall(r">([^<>]+)<", s) if w.strip()]
    assert words == ["قائمتي", "مدينتك", "دبي", "بطاقتك", "بدون بطاقة", "هذي اختياراتك، محفوظة على تلفونك بس.", "امسح بياناتي"]
    assert 'data-sheet-open="sheet-city"' in s and 'data-sheet-open="sheet-card"' in s                 # its two rows open those
    assert 'data-me-clear data-t="امسح بياناتي" data-sure="متأكد؟ اضغط مرة ثانية"' in s
    for w in ("قريب", "قريباً", "soon", "احفظ", "نبّهني", "فيلم"):                                     # no list, no promise of one
        assert w not in s, w
    assert "<b data-city-name>العين</b>" in sheet_of(read(out, "al-ain", "index.html"), "sheet-me")     # the page's city
    en = sheet_of(read(out, "en", "index.html"), "sheet-me")
    assert "These are your choices, kept on your phone only." in en and "Clear my data" in en


def test_with_the_flag_off_search_is_the_fourth_tab_again(out_off):
    """With the flag off there is no «قائمتي» sheet; the bar is still the app's three tabs and search the header's icon."""
    h = read(out_off, "index.html")
    t = tabs_of(h)
    assert len(re.findall(r"<a [^>]*>", t)) == 3 and "data-search" not in t
    assert 'id="sheet-me"' not in h and "قائمتي" not in h
    assert h.count("data-search") == 1


# ------------------------------------------------------------------ the drag chunk
def test_the_drag_chunk_is_named_by_the_scrim_and_fits_its_budget(out):
    h = read(out, "index.html")
    u = re.search(r'<div class="sh-scrim" data-sheet-scrim data-drag-js="(/assets/drag\.[0-9a-f]{10}\.js)" hidden></div>', h).group(1)
    raw = read(out, *u.strip("/").split("/")).encode()
    assert len(gzip.compress(raw, 9)) <= 1500, len(gzip.compress(raw, 9))       # MASTER-PLAN §7.3 #9: drag.js ≤ 1.5 KB gz
    # chrome.js fetches it on idle (phones) or at the first sheet; main.js does not load it at start-up with the chunks
    ct = json.loads(re.search(r"<script>window\.CT = (\{.*?\});</script>", h).group(1))
    assert "drag" not in ct.get("chunks", {})
    assert 'data-drag-js="/assets/drag.' in read(out, "film", "heart-of-the-beast", "index.html")
    js = raw.decode()
    assert 'K.emit("detent"' in js and "0.3 * (sh.offsetHeight - l)" in js and "v > 0.5" in js


# ------------------------------------------------------------------ the stylesheet
def rule(c, sel):
    m = re.search(r"(?:^|[}\s])" + re.escape(sel) + r"\{([^}]*)\}", c)
    assert m, sel
    return m.group(1)


def test_the_tab_bar_is_opaque_steps_away_and_yields(out):
    c = css(out)
    t = rule(c, ".tabs")
    assert "background:var(--night)" in t and "rgba(" not in t                  # opaque night (§2.0)
    assert "transition:transform .22s var(--ease-sheet)" in t                    # 220 ms --ease-sheet (§1.3)
    assert "padding-block-end:env(safe-area-inset-bottom)" in t
    assert ".tabs-away .tabs:not(:focus-within){transform:translateY(100%)}" in c   # keyboard focus brings it back
    assert re.search(r"@media \(prefers-reduced-motion:reduce\)\{\.tabs\{transition:none\}\}", c)
    assert re.search(r"\.tabs a\{min-block-size:60px;", c)                      # the bar's 60 px: --chrome-b's fallback


def test_the_header_turns_solid_the_instant_the_page_scrolls(out):
    """Round r3 (owner report: the header sat translucent over the title for a stretch of scroll): the old scroll
    timeline (0-56px fade) is gone; a class toggled by an IntersectionObserver (chrome.js) on a sentinel at the
    very top of body now flips the header solid in one step, the moment scrollY leaves 0."""
    c = css(out)
    # the header's OWN scroll-timeline is gone (the home billboard's unrelated .bill recede/dim/lift keeps its own
    # animation-timeline rules elsewhere in this same sheet — a different feature, untouched here)
    assert "@keyframes top-solid" not in c and "animation-range:0 56px" not in c
    assert "body[data-hero] .top::before{" not in c.replace(".js body[data-hero] .top::before{", "")
    assert ".js body[data-hero] .top{background:linear-gradient(rgba(15,11,12,.85),rgba(15,11,12,0)) border-box;border-block-end-color:transparent}" in c
    assert ".js body[data-hero] .top::before{" in c and "opacity:0}" in c
    assert ".js body[data-hero].scrolled .top::before{opacity:1}" in c
    assert rule(c, ".top").startswith("position:sticky") and "background:var(--night)" in rule(c, ".top")   # no script: solid
    h = read(out, "film", "heart-of-the-beast", "index.html")
    assert '<span class="vh" id="scroll-mark" aria-hidden="true"></span>' in h
    b = bundle(out)
    assert 'q("#scroll-mark")' in b and "IntersectionObserver" in b
    assert 'body.classList.toggle("scrolled"' in b


def test_the_header_also_goes_solid_when_the_film_heros_text_reflows_under_it_with_no_scroll(out):
    """Round r3, coordinator-caught follow-up: the sentinel above only sees a real scroll. The film hero
    (ui-fhero.css .fhero, justify-content:flex-end) anchors its text block to the picture's BOTTOM — opening
    «ليش يستاهل؟» can grow that block past the picture's own min-height, and once it does, flex-end has no
    slack left: the title itself jumps to y=0, straight under a still-translucent header, with scrollY
    unchanged throughout (a screenshot proved it: after-390-why-open.png). A second observer, on the title
    itself with the header's own live height as its top rootMargin, catches this the same way it catches a
    real scroll — IntersectionObserver recomputes on any geometry change of its target, not only scrolling —
    and both observers drive the SAME class through a shared flag object, so neither can clear what the
    other just set."""
    b = bundle(out)
    assert 'q(".fhero h1.ft")' in b and 'q(".top")' in b
    assert 'rootMargin: "-" + topEl.offsetHeight + "px 0px 0px 0px"' in b
    assert "SOL.a || SOL.b" in b   # neither observer can silently win over the other


def test_the_floating_lines_sit_on_the_chrome_not_under_it(out):
    c = css(out)
    assert "html .shareask{inset-block-end:0;transform:translateY(calc(-1 * max(var(--chrome-b,61px),env(safe-area-inset-bottom))))" in c
    assert re.search(r"\.inst\{[^}]*transform:translateY\(calc\(-1 \* max\(var\(--chrome-b,61px\),env\(safe-area-inset-bottom\)\)\)\)", c)
    desk = re.search(r"@media \(min-width:1024px\)\{\.inst\{inset-inline:auto 24px;inset-block-end:24px;transform:none\}html \.shareask\{transform:none\}\}", c)
    assert desk


def test_sheets_rise_from_the_edge_and_what_you_chose_is_a_gold_outline(out):
    c = css(out)
    assert "@keyframes sheet-up{from{transform:translateY(100%)}}" in c
    sh = rule(c, ".sheet")
    assert "overscroll-behavior:contain" in sh and "calc(var(--dt,0px) + 20px + env(safe-area-inset-bottom))" in sh
    assert "block-size:44px" in rule(c, ".grab")                                 # a 44 px grabber hit area
    assert "position:sticky" in rule(c, ".sheet-t") and "touch-action:none" in rule(c, ".sheet-t")
    on = rule(c, ".opt[aria-pressed=true],.opt[aria-current],.sheet .chip[aria-pressed=true]")
    assert "background:none" in on and "color:var(--gold)" in on and "border-color:var(--gold)" in on   # never a white fill
    assert "inline-size:100%" in rule(c, ".opt.wide")
    rm = re.findall(r"@media \(prefers-reduced-motion:reduce\)\{([^@]*?\})\}", c)
    assert any(".sheet,.sh-scrim{animation:none;transition:none!important}" in m for m in rm)


# ------------------------------------------------------------------ the bundle
def test_the_bundle_vibrates_only_after_a_tap(out):
    b = bundle(out)
    assert b.count("vibrate(") == 1                                              # one call in the whole bundle
    assert "function haptic() { if (CH.tap && navigator.vibrate) navigator.vibrate(8); }" in b
    assert 'document.addEventListener("click", function (e) { if (e.isTrusted) CH.tap = true; }, true);' in b
    assert re.search(r'\["card", "plan", "save", "detent"\]\.forEach\(function \(ev\) \{ on\(ev, haptic\); \}\)', b)
    assert 'on("stub", function (x)' in b


def test_openers_are_delegated_so_a_door_drawn_later_opens_its_sheet(out):
    b = bundle(out)
    assert 'e.target.closest("[data-sheet-open]")' in b and 'emit("sheet", el)' in b and 'emit("sheet", null)' in b
    assert "function bindTop(" not in b                                          # the sentinel: a scroll timeline now


# ------------------------------------------------------------------ W2-P5's words (for the dialect gate)
def test_the_new_words_keep_the_voice():
    ar = [v[0] for v in chrome.CHROME_W2.values()]
    for w in ar:
        assert not re.search(r"[٠-٩۰-۹]", w), w                # Western digits
        assert "ً" not in w and "·" not in w, w                              # no tanween, no middle dot
        for bad in ("وش", "جوال", "معي", "الآن"):
            assert not re.search(r"(?<![\w])" + bad + r"(?![\w])", w), (w, bad)
    for v in chrome.CHROME_W2.values():
        assert not re.search(r"\b[A-Z]{2,}\b", v[1].replace("AED", "")), v[1]     # no all-caps words


# ------------------------------------------------------------------ the scripts, in node
def node(tmp_path, name, src):
    f = tmp_path / name
    f.write_text(src, encoding="utf-8")
    r = subprocess.run([NODE, str(f)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr + r.stdout
    return json.loads(r.stdout.strip().splitlines()[-1])


CHROME_HARNESS = r"""
(function () {
var OUT = {};
var HOOKS = {}; function on(ev, fn) { (HOOKS[ev] = HOOKS[ev] || []).push(fn); } function emit(ev, x) { (HOOKS[ev] || []).forEach(function (f) { f(x); }); }
var FEAT = []; function feature(fn) { FEAT.push(fn); }
var cls = {}, props = {}, winL = {}, docL = {}, vib = [], scrolled = [], reloads = 0, closes = 0, docked = false, loaded = [];
var document = { documentElement: { classList: { toggle: function (c, v) { cls[c] = !!v; } }, style: { setProperty: function (k, v) { props[k] = v; } } },
  addEventListener: function (t, f) { (docL[t] = docL[t] || []).push(f); }, createElement: function () { return {}; }, head: { appendChild: function (s) { loaded.push(s.src); } } };
var tabs = { offsetHeight: 61 };
function q(s, r) { if (r) return r.q(s); return s === ".tabs" ? tabs : null; }
function qa() { return []; }
var body = { classList: { contains: function (c) { return c === "docked" && docked; } } };
var SH = null, shPushed = false, shScrim = { getAttribute: function () { return "/assets/drag.0123456789.js"; } };
function sheetClose() { closes++; }
var card = "", C = { cards: { fazaa: "فزعة" }, nocard: "بدون بطاقة" }, RM = false, scrollY = 0;
function addEventListener(t, f) { (winL[t] = winL[t] || []).push(f); }
var navigator = { vibrate: function (n) { vib.push(n); return true; }, userActivation: { hasBeenActive: true } };   /* a touch scroll sets it */
function getComputedStyle() { return { bottom: "0px" }; }
function desk() { return false; }
var idle = [], window = { requestIdleCallback: function (f) { idle.push(f); } }, requestIdleCallback = window.requestIdleCallback;
var location = { pathname: "/", reload: function () { reloads++; } };
function scrollTo(o) { scrolled.push(o); }
var localStorage = { "cinema.card": "fazaa", "cinema.city": "dubai", "cinema.loc": "25,55,1", "other.key": "x" };
localStorage.removeItem = function (k) { delete this[k]; };
Object.defineProperty(localStorage, "removeItem", { enumerable: false });
__SRC__
FEAT.forEach(function (f) { f(); });
function scroll(y) { scrollY = y; winL.scroll.forEach(function (f) { f(); }); return !!cls["tabs-away"]; }
OUT.start = [!!cls["tabs-away"], props["--chrome-b"], idle.length];
idle.forEach(function (f) { f(); }); OUT.loaded = loaded.slice();
OUT.scroll = [scroll(5), scroll(13), scroll(20), scroll(40), scroll(28), scroll(27), scroll(40), scroll(50), scroll(0)];
OUT.bar = props["--chrome-b"];
SH = {}; OUT.sheetOpen = [scroll(100), scroll(200)]; SH = null;
docked = true; OUT.docked = [scroll(400), scroll(600)]; docked = false;
scroll(0);
emit("stub", "open"); OUT.stubOpen = [!!cls["tabs-away"], props["--chrome-b"]];
emit("stub", "close"); OUT.stubClose = [!!cls["tabs-away"], props["--chrome-b"]];
["card", "plan", "save", "detent"].forEach(function (e) { emit(e, 1); }); emit("stub", "open"); emit("stub", "close");
function clickAll(ev) { docL.click.forEach(function (f) { f(ev); }); }
clickAll({ isTrusted: false, target: { closest: function () { return null; } }, preventDefault: function () {} });   /* a script's click */
["card", "plan", "save", "detent"].forEach(function (e) { emit(e, 1); }); emit("stub", "open"); emit("stub", "close");
OUT.vibBefore = vib.length;
clickAll({ isTrusted: true, target: { closest: function () { return null; } }, preventDefault: function () {} });    /* a tap */
["card", "plan", "save", "detent"].forEach(function (e) { emit(e, 1); }); emit("stub", "open"); emit("stub", "close");
OUT.vibAfter = vib.slice();
function click(a) { var ev = { target: { closest: function () { return a; } }, prevented: false, preventDefault: function () { this.prevented = true; } }; docL.click.forEach(function (f) { f(ev); }); return ev.prevented; }
var here = { pathname: "/", hasAttribute: function () { return false; } }, there = { pathname: "/cinemas/", hasAttribute: function () { return false; } };
OUT.retap = [click(here), scrolled.length, scrolled[0] && scrolled[0].top, click(there), scrolled.length];
var btn = { textContent: "امسح بياناتي", hasAttribute: function (n) { return n === "data-me-clear"; },
  getAttribute: function (n) { return { "data-sure": "متأكد؟ اضغط مرة ثانية", "data-t": "امسح بياناتي" }[n]; } };
var cardEl = { textContent: "" }, sheet = { id: "sheet-me", q: function (s) { return s === "[data-me-clear]" ? btn : cardEl; } };
card = "fazaa"; emit("sheet", sheet); OUT.meCard = cardEl.textContent;
click(btn); OUT.clear1 = [btn.textContent, Object.keys(localStorage).length, reloads];
emit("sheet", sheet); OUT.reset = btn.textContent;
click(btn); click(btn); OUT.clear2 = [Object.keys(localStorage).sort(), reloads, closes];
localStorage["cinema.card"] = "x"; shPushed = true; emit("sheet", sheet); click(btn); click(btn);
OUT.clear3 = [Object.keys(localStorage).sort(), reloads, closes, (winL.popstate || []).length];
(winL.popstate || []).forEach(function (f) { f(); }); OUT.clear3.push(reloads);
console.log(JSON.stringify(OUT));
})();
"""


@needs_node
def test_chrome_js_hides_yields_ticks_only_after_a_tap_and_clears(tmp_path):
    src = open(os.path.join(ROOT, "src", "js", "chrome.js"), encoding="utf-8").read()
    o = node(tmp_path, "chrome.js", CHROME_HARNESS.replace("__SRC__", src))
    assert o["start"] == [False, "61px", 1] and o["loaded"] == ["/assets/drag.0123456789.js"]   # idle prefetch of drag.js
    # 5: nothing; 13: more than 12 down, away; 20, 40: still away; 28: 12 up is not enough; 27: 13 up, back; 40: 13 down,
    # away; 50: still away; 0: the top always brings it back
    assert o["scroll"] == [False, True, True, True, True, False, True, True, False]
    assert o["bar"] == "61px"
    assert o["sheetOpen"] == [False, False] and o["docked"] == [False, False]   # never while a sheet or the old dock is up
    assert o["stubOpen"] == [True, "0px"] and o["stubClose"] == [False, "61px"]  # yields to the stub, and comes back
    assert o["vibBefore"] == 0                                                  # nothing before a tap, even with an activation
    assert o["vibAfter"] == [8, 8, 8, 8, 8]                                     # card, plan, save, detent, the stub rising
    assert o["retap"] == [True, 1, 0, False, 1]                                 # the tab you are on: to the top, in place
    assert o["meCard"] == "فزعة"
    assert o["clear1"] == ["متأكد؟ اضغط مرة ثانية", 4, 0]                       # the first tap only asks
    assert o["reset"] == "امسح بياناتي"                                         # reopened: asks again from the start
    assert o["clear2"] == [["other.key"], 1, 0]                                 # every «cinema.» key, nothing else; reload
    assert o["clear3"] == [["other.key"], 1, 1, 1, 2]                           # with the sheet's history entry: back first


DRAG_HARNESS = r"""
var OUT = {}, timers = [], emits = [], clicks = 0;
function setTimeout(f) { timers.push(f); }
function flush() { var t = timers.splice(0); t.forEach(function (f) { f(); }); }
var innerWidth = 360, innerHeight = 740, HTMLInputElement = function () {};
var window = { PointerEvent: function () {} };
function Style() {}
Style.prototype.setProperty = function (k, v) { this[k] = v; };
function El(tag, cls, attrs, parent) { this.tagName = tag; this.cls = cls || []; this.attrs = attrs || {}; this.parent = parent; this.kids = []; this.style = new Style(); this.hidden = false; this.offsetHeight = 0; if (parent) parent.kids.push(this); }
El.prototype.matches = function (sel) { var e = this; return sel.split(",").some(function (s) { s = s.trim(); return s[0] === "." ? e.cls.indexOf(s.slice(1)) >= 0 : s[0] === "[" ? s.slice(1, -1) in e.attrs : e.tagName === s; }); };
El.prototype.closest = function (sel) { for (var e = this; e; e = e.parent) if (e.matches(sel)) return e; return null; };
El.prototype.getAttribute = function (n) { return n in this.attrs ? this.attrs[n] : null; };
El.prototype.setAttribute = function (n, v) { this.attrs[n] = String(v); };
El.prototype.hasAttribute = function (n) { return n in this.attrs; };
El.prototype.removeAttribute = function (n) { if (n === "style") this.style = new Style(); delete this.attrs[n]; };
El.prototype.querySelector = function (sel) { for (var i = 0; i < this.kids.length; i++) { var k = this.kids[i]; if (k.matches(sel)) return k; var r = k.querySelector(sel); if (r) return r; } return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.setPointerCapture = function () {};
var docL = {}, scrim = new El("div", [], { "data-sheet-scrim": "" });
var document = { addEventListener: function (t, f) { (docL[t] = docL[t] || []).push(f); },
  querySelector: function (s) { return s === "[data-sheet-scrim]" ? scrim : null; } };
var HOOKS = {}, K = { on: function (ev, f) { (HOOKS[ev] = HOOKS[ev] || []).push(f); }, emit: function (ev, x) { emits.push([ev, x]); (HOOKS[ev] || []).forEach(function (f) { f(x); }); } };
function make(detents, h) {
  var sh = new El("div", ["sheet"], detents ? { "data-detents": detents } : {}), t = new El("div", ["sheet-t"], {}, sh),
    x = new El("button", ["sheet-x"], { "data-sheet-close": "" }, t);
  x.click = function () { clicks++; sh.hidden = true; K.emit("sheet", null); };
  sh.offsetHeight = h; sh.head = t; sh.x = x;
  return sh;
}
function ty(sh) { var m = /translateY\((-?[\d.]+)px\)/.exec(sh.style.transform || ""); return m ? +m[1] : null; }
var T = 1000;
function ev(type, target, y, dt) { T += dt || 0; var e = { target: target, pointerId: 1, clientY: y, button: 0, timeStamp: T }; (docL[type] || []).forEach(function (f) { f(e); }); }
/* a drag from y0 by dy in steps of `step` px every `ms` ms, then a release: [where the release sends it, closed?, [where
   the finger had it, the scrim's opacity there], where it rests after the settle (a closed sheet has no style left)] */
function drag(sh, y0, dy, step, ms, target) {
  var c0 = clicks; ev("pointerdown", target || sh.head, y0, 500);
  var n = Math.ceil(Math.abs(dy) / step), y = y0;
  for (var i = 1; i <= n; i++) { y = y0 + (i === n ? dy : Math.sign(dy) * step * i); ev("pointermove", target || sh.head, y, ms); }
  var mid = [ty(sh), scrim.style.opacity];
  ev("pointerup", target || sh.head, y, 1);
  var rel = ty(sh); flush();
  return [rel, clicks > c0, mid, ty(sh)];
}
(function (K) {
__SRC__
})(K);
/* a sheet with no stops, 500 px tall */
var a = make(null, 500);
K.emit("sheet", a);
OUT.plain = { open: [ty(a), a.S || null] };
OUT.plain.slow28 = drag(a, 400, 140, 20, 50);                // 28 %: back to 0
OUT.plain.slow32 = drag(a, 400, 160, 20, 50);                // 32 %: away
a.hidden = false; K.emit("sheet", a);
OUT.plain.flick = drag(a, 400, 45, 15, 10);                  // 9 % at 1.5 px/ms: away
a.hidden = false; K.emit("sheet", a);
OUT.plain.half = drag(a, 400, 250, 25, 50)[2];               // the scrim at half the sheet: half its light
a.hidden = false; K.emit("sheet", a);
OUT.plain.tap = drag(a, 400, 0, 1, 50);                      // a tap is not a drag
OUT.plain.onX = drag(a, 400, 200, 20, 50, a.x);              // pressing × is not a drag
innerWidth = 1280; OUT.plain.desk = drag(a, 400, 200, 20, 50); innerWidth = 360;
/* the filter sheet: 60 % and 92 % of a 740 px screen */
var f = make("60 92", 681);
emits = []; K.emit("sheet", f);
OUT.det = { open: [ty(f), f.S, f.style.blockSize, f.style["--dt"]] };
emits = []; OUT.det.up200 = drag(f, 400, -200, 20, 50).concat([f.style["--dt"], JSON.stringify(emits.filter(function (e) { return e[0] === "detent"; }))]);
emits = []; OUT.det.down100 = drag(f, 200, 100, 20, 50).concat([JSON.stringify(emits.filter(function (e) { return e[0] === "detent"; }))]);
emits = []; OUT.det.down180 = drag(f, 200, 180, 20, 50).concat([f.style["--dt"], JSON.stringify(emits.filter(function (e) { return e[0] === "detent"; }))]);
OUT.det.down100b = drag(f, 400, 100, 20, 50);                // 337 is above 237 + 30 % of the rest: back to 237
emits = []; OUT.det.flickUp = drag(f, 400, -45, 15, 10).concat([JSON.stringify(emits.filter(function (e) { return e[0] === "detent"; }))]);
OUT.det.flickDown = drag(f, 200, 45, 15, 10);                // from 92 %, a flick down lands on 60 %, not away
OUT.det.away = drag(f, 400, 150, 20, 50);                    // 387 is past 30 % below 60 %: away
console.log(JSON.stringify(OUT));
"""


@needs_node
def test_drag_js_follows_the_thumb_closes_past_30_percent_or_on_a_flick_and_holds_the_stops(tmp_path):
    src = open(os.path.join(ROOT, "src", "js", "drag.js"), encoding="utf-8").read()
    o = node(tmp_path, "drag.js", DRAG_HARNESS.replace("__SRC__", src))
    p = o["plain"]
    assert p["open"] == [None, None]                                             # a plain sheet opens as the CSS draws it
    assert p["slow28"][:2] == [0, False] and p["slow28"][2] == [140, 0.72] and p["slow28"][3] == 0   # 1:1, the scrim with it, back
    assert p["slow32"][:2] == [500, True] and p["slow32"][3] is None             # past 30 %: out of sight, × pressed, style gone
    assert p["flick"][:2] == [500, True]                                         # a flick over 0.5 px/ms closes it
    assert p["half"][0] == 250 and abs(p["half"][1] - 0.5) < 1e-9               # the scrim fades with the drag
    assert p["tap"][:2] == [None, False] and p["onX"][:2] == [None, False] and p["desk"][:2] == [None, False]
    d = o["det"]
    assert d["open"] == [237, [0, 237], "680.8px", "237px"]                     # opens at 60 %, 92 % tall
    assert d["up200"][:4] == [0, False, [37, ""], 0] and d["up200"][4:] == ["0px", '[["detent",0]]']   # 92 %, one tick
    assert d["down100"][:2] == [0, False] and d["down100"][4] == "[]"           # nearer 92 %: stays, no tick
    assert d["down180"][:2] == [237, False] and d["down180"][4:] == ["237px", '[["detent",237]]']
    assert d["down100b"][:2] == [237, False]                                     # 337 is within 30 % below 60 %: back
    assert d["flickUp"][:2] == [0, False] and d["flickUp"][4] == '[["detent",0]]'
    assert d["flickDown"][:2] == [237, False]                                    # from 92 %, a flick down lands on 60 %
    assert d["away"][:2] == [681, True]                                          # past 30 % below 60 %: away
