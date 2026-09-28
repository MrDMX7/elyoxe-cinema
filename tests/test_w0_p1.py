"""W0-P1, the trust sweep on live main: chrome, copy and cards (MASTER-PLAN §4.1 #1-#10 and the build-time half
of #30). One test per acceptance line; tools/check_w0_p1.cjs checks the same things in a real Chrome.

The build is the sample fixture with three changes that make each bug reachable: the Fujairah cinema moves to
Umm Al Quwain (a city with one cinema), VOX Al Jimi gets a GOLD show of «قلب الوحش» that started before the
data was built (a hall with nothing left to show) and a GOLD pair for «The Paradise» (one past, one to come), and
the VOX Fazaa rule carries the live file's raw note («… رجع Page Not Found»). Two pages are left with nothing to
show: «Last Night», a film on its last night after its last start (one GOLD show at 11:00, none tomorrow), and VOX
City Centre Sharjah, which keeps only today's shows before 18:00 (tomorrow's aren't listed yet)."""
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402
import site_kit  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
NODE = shutil.which("node")
RAW_NOTE = "ما لقينا عرض فزعة قائم الآن — الرابط الرسمي رجع Page Not Found"
JIMI = "vox-al-jimi-mall"
SHJ = "vox-city-centre-sharjah"
SHELL = '<aside class="ticket" id="ticket" data-ticket hidden></aside>'


def read(out, *p):
    return open(os.path.join(out, *p), encoding="utf-8").read()


def pages(out):
    for dp, _, fs in os.walk(out):
        for f in fs:
            if f.endswith(".html"): yield os.path.join(dp, f)


def gold(film, time, today):
    return {"cinema": JIMI, "film": film, "date": today, "time": time, "hall": "GOLD", "hall_label": "GOLD",
            "prices": [{"seat": "Gold", "aed": 150}], "book": f"https://uae.voxcinemas.com/booking/{film}-{time}"}


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w0p1")
    d = json.load(open(DATA, encoding="utf-8"))
    today = d["generated"][:10]
    fuj = next(cid for cid, c in d["cinemas"].items() if c["city"] == "fujairah")
    d["cinemas"][fuj]["city"] = "umm-al-quwain"
    d["shows"] += [gold("heart-of-the-beast", "11:00", today), gold("the-paradise", "11:00", today), gold("the-paradise", "21:00", today)]
    d["films"]["last-night"] = dict({k: v for k, v in d["films"]["sacrifice"].items() if k != "title_ar"}, title="Last Night")
    d["shows"] = [s for s in d["shows"] if not (s["cinema"] == SHJ and (s["date"] != today or s["time"] >= "18:00"))] + [gold("last-night", "11:00", today)]
    (tmp / "data.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    disc = yaml.safe_load(open(DISC, encoding="utf-8"))
    disc["rules"]["vox"]["fazaa"]["note_ar"] = RAW_NOTE
    (tmp / "disc.yaml").write_text(yaml.safe_dump(disc, allow_unicode=True), encoding="utf-8")
    o = str(tmp / "out")
    build.build(str(tmp / "data.json"), str(tmp / "disc.yaml"), o, noindex=False)
    return o


# ------------------------------------------------------------------ #1 the tab bar: four tabs, never under the page
def test_the_tab_bar_holds_the_four_builtin_links_on_every_page(out):
    n = 0
    for p in pages(out):
        h = open(p, encoding="utf-8").read()
        m = re.search(r'<nav class="nav".*?</nav>', h, re.S)
        if not m: continue
        assert m.group(0).count("<a ") == 4, p
        n += 1
    assert n > 50


# (legend, R0: the redesign's chrome since UI redesign Task 2: the phone's bar is nav.tabs, outside the header;
#  the footer's row is nav.foot-l, «من وين الأسعار» then the features, then «القاعات»; the studio link sits under it)
def test_the_feature_links_moved_to_the_footer(out):
    for lang, parts, want in (("ar", (), ("عربي وخليجي", "فعاليات", "صباح العيال")), ("en", ("en",), ("Arabic &amp; Gulf", "Events", "Kids"))):
        h = read(out, *parts, "index.html")
        nav = re.search(r'<nav class="nav".*?</nav>', h, re.S).group(0)
        tabs = re.search(r'<nav class="tabs".*?</nav>', h, re.S).group(0)
        foot = re.search(r'<nav class="foot-l".*?</nav>', h, re.S).group(0)
        for w in want:
            assert w in foot and w not in nav and w not in tabs, (lang, w)
        assert foot.index("/sources/") < foot.index("/arabic/") < foot.index("/halls/")   # after the sources, before the halls
    kids = re.search(r'<nav class="foot-l".*?</nav>', read(out, "kids", "index.html"), re.S).group(0)
    assert '<a href="/kids/" aria-current="page">صباح العيال</a>' in kids                          # the page you are on
    css = read(out, "assets", "cinema.css")
    assert ".foot-l a{min-block-size:44px;display:inline-flex;align-items:center}" in css          # a real tap target
    assert "grid-auto-flow:column" not in css and "grid-auto-columns:minmax(84px" not in css        # no sideways bar


def test_the_header_is_raised_while_it_carries_the_view_transition_name(out):
    """view-transition-name makes .top a stacking context at z 0, so the fixed tab bar inside it was painted under
    every positioned thing in <main> (posters are z 1). z 30 puts it back: above the page, under the ticket."""
    css = read(out, "assets", "cinema.css")
    motion = re.search(r"@media \(prefers-reduced-motion:no-preference\)\{(.*)", css, re.S).group(1)
    assert ".top{view-transition-name:top;z-index:30}" in motion
    assert "view-transition-name:top}" not in css                   # never the name without the z-index
    # legend: the bar is nav.tabs, fixed at z 30 outside the header (no stacking context can hold it under the page)
    assert re.search(r"\.tabs\{position:fixed;[^}]*z-index:30", css)
    home = read(out, "index.html")
    assert home.index("</header>") < home.index('<nav class="tabs"')
    assert re.search(r"\.js \.ticket\{position:fixed;[^}]*z-index:40", css)   # the open ticket still covers the bar


# ------------------------------------------------------------------ #2 the ticket's plan links on paper
def _vars():
    root = re.search(r":root\{(.*?)\}", open(os.path.join(ROOT, "src", "cinema.css"), encoding="utf-8").read(), re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", root))


def _contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    x, y = lum(a), lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def test_the_plan_links_and_the_leave_by_line_are_ink_on_the_ticket_paper(out):
    v = _vars()
    css = read(out, "assets", "cinema.css")
    assert re.search(r"\.ticket\{background:var\(--screen\)", css)                 # the paper
    # legend: the redesign's own rules, the same fix: the plan row's links in ink, the leave-by line in ink-2
    assert ".ticket .plan-add .lnk{color:var(--ink);" in css and ".ticket .plan-leave{color:var(--ink-2)}" in css
    assert _contrast(v["screen"], v["screen"]) == 1                                 # what it was
    assert _contrast(v["ink"], v["screen"]) >= 4.5 and _contrast(v["ink-2"], v["screen"]) >= 4.5
    assert _contrast(v["seat"], v["screen"]) < 4.5                                  # why .plan-leave moved off seat grey
    assert ".ticket .plan-add{padding:8px 16px 0;" in css                           # the row keeps the ticket's margins


# ------------------------------------------------------------------ #3 the shared-link bar above the tab bar
def test_the_shared_link_bar_sits_above_the_tab_bar(out):
    css = read(out, "assets", "cinema.css")
    # legend: the bar (nav.tabs) is 60 px of links under a 1 px rule, plus the safe area: the prompt sits on top of it
    assert re.search(r"\.tabs a\{min-block-size:60px;", css) and re.search(r"\.tabs\{[^}]*border-block-start:1px solid", css)
    assert ".shareask{position:fixed;inset-inline:0;inset-block-end:calc(61px + env(safe-area-inset-bottom));z-index:20;" in css
    assert "@media (min-width:1024px){.shareask{inset-block-end:0}}" in css      # desktop has no tab bar
    assert ".shareask{position:fixed;inset-inline:0;inset-block-end:0;" not in css


# ------------------------------------------------------------------ #4 #5 the manifest's shortcuts
def test_the_manifest_has_no_mine_shortcut_and_now_has_a_target(out):
    m = json.loads(read(out, "manifest.webmanifest"))
    urls = [s["url"] for s in m["shortcuts"]]
    assert "/#mine" not in urls and urls == ["/#now", "/coming/"]
    assert not os.path.exists(os.path.join(out, "assets", "icons", "sc-mine.png"))
    assert not os.path.exists(os.path.join(ROOT, "src", "icons", "sc-mine.png"))
    for parts in ((), ("en",)):
        h = read(out, *parts, "index.html")
        # legend: home's «الحين» is the row «يبدأ قريب منك» (UI redesign Task 3; the board takes the id in W2-P2)
        assert h.count('id="now"') == 1 and '<section class="rail" aria-labelledby="r-near" id="now" data-near-row data-hold hidden>' in h
    assert 'id="now"' not in read(out, "dubai", "index.html")                     # home only: one target
    # hidden until the city's slice is in, the row still holds its place, so /#now scrolls to it at once
    assert ".js .rail[data-near-row][hidden]{display:block;visibility:hidden}" in read(out, "assets", "cinema.css")


# ------------------------------------------------------------------ #6 the bundle is fetched once
def test_no_page_preloads_the_bundle(out):
    n = 0
    for p in pages(out):
        h = open(p, encoding="utf-8").read()
        if 'rel="canonical"' not in h: continue
        assert 'as="script"' not in h, p
        assert re.search(r'<script id="boot">.*\("/assets/cinema\.[0-9a-f]{10}\.js",document\)</script>', h), p
        n += 1
    assert n > 50


# ------------------------------------------------------------------ #7 «كل ساعة»
def test_where_the_prices_come_from_says_every_hour(out):
    # legend: «من وين الأسعار» is its own page, /sources/ (UI redesign Task 3), no longer a section of home
    assert "من نظام الحجز عند كل سينما: المواعيد كل ساعة، والسعر مرة باليوم لكل قاعة." in read(out, "sources", "index.html")
    assert "From each chain’s booking system: showtimes every hour, prices once a day per hall." in read(out, "en", "sources", "index.html")
    for p in pages(out):
        h = open(p, encoding="utf-8").read()
        assert "ثلاث مرات باليوم" not in h and "three times a day" not in h, p


# ------------------------------------------------------------------ #8 no raw «Page Not Found»
def test_a_source_error_is_said_in_arabic():
    assert site_kit.note_ar({"note_ar": RAW_NOTE}) == "صفحة العرض الرسمية انحذفت، فما نعرض الخصم"
    assert site_kit.note_ar({"note_ar": "404 من الموقع"}) == site_kit.SOURCE_GONE_AR
    assert site_kit.note_ar({"note_ar": "من الشباك فقط، 4 تذاكر باليوم"}) == "من الشباك فقط، 4 تذاكر باليوم"
    assert site_kit.note_ar({}) == "" and site_kit.note_ar(None) == ""
    # beside a discount the site shows, «فما نعرض الخصم» would be false: a live rule's terms drop the error instead
    assert site_kit.note_ar({"note_ar": RAW_NOTE}, ok=True) == ""
    assert site_kit.note_ar({"note_ar": "من الشباك فقط، 4 تذاكر باليوم"}, ok=True) == "من الشباك فقط، 4 تذاكر باليوم"
    live = {"type": "percent", "value": 20, "box_office_only": True, "note_ar": RAW_NOTE}
    assert site_kit.rule_terms(live, "ar") == ["من الشباك فقط"]


def test_the_fazaa_page_and_the_vox_pages_print_no_raw_source_error(out):
    fz = read(out, "cards", "fazaa", "index.html")
    row = re.search(r'<div class="row crd"><span class="nm">فوكس</span>.*?</div>', fz, re.S).group(0)
    assert "صفحة العرض الرسمية انحذفت، فما نعرض الخصم" in row
    for p in pages(out):
        h = open(p, encoding="utf-8").read()
        body = h[h.index("<body"):] if "<body" in h else h
        assert not re.search(r"not found", body, re.I) or p.endswith("404.html"), p


# ------------------------------------------------------------------ #9 counts in Arabic grammar
def test_counts_read_in_arabic_grammar(out):
    f = lambda n: site_kit.ar_count_num(n, site_kit.CINEMAS_AR)
    assert [f(1), f(2)] == ["سينما وحدة", "سينمتين"]
    assert f(3) == '<span class="num">3</span> سينمات' and f(10).endswith(" سينمات") and f(22) == '<span class="num">22</span> سينما'
    # legend: the cities and their counts are on /cinemas/ (UI redesign Task 2), no longer a list on home
    home = read(out, "cinemas", "index.html")
    li = lambda city: re.search(rf'<section class="wrap cities" id="{city}"><h2><a href="/{city}/">[^<]+</a> <small>(.*?)</small></h2>', home).group(1)
    assert li("umm-al-quwain") == "سينما وحدة" and li("dubai") == '<span class="num">3</span> سينمات'
    assert "1 سينما" not in home and '<span class="num">1</span> سينما' not in home
    lead = re.search(r'<p class="lead">(.*?)</p>', read(out, "umm-al-quwain", "index.html")).group(1)
    assert lead.startswith("سينما وحدة و") and " اليوم." in lead
    assert re.search(r'<p class="lead">1 cinema and \d+ films? today\.', read(out, "en", "umm-al-quwain", "index.html"))


# ------------------------------------------------------------------ #10 the ticket's terms, each once
def _terms(tmp_path, rules, ar):
    src = open(os.path.join(ROOT, "src", "js", "prices.js"), encoding="utf-8").read()
    sep = "، " if ar else ", "
    harness = (f"var AR = {str(ar).lower()}, TX = {{ sep: '{sep}' }}, C = {{ weak: 'غير مؤكد' }};\n"
               "function esc(s) { return String(s); }\n" + src +
               f"\nprocess.stdout.write(JSON.stringify({json.dumps(rules, ensure_ascii=False)}.map(terms)));\n")
    (tmp_path / "terms.js").write_text(harness, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "terms.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_the_ticket_names_each_condition_once(tmp_path):
    star = yaml.safe_load(open(DISC, encoding="utf-8"))["rules"]["star"]["fazaa"]
    (ar,) = _terms(tmp_path, [star], True)
    assert ar == "، من الشباك فقط، 4 تذاكر باليوم"          # was «من الشباك فقط، لين 4 تذاكر، من الشباك فقط، 4 تذاكر باليوم»
    (en,) = _terms(tmp_path, [star], False)
    assert en == ", box office only, up to 4 tickets"          # English prints no Arabic note: the flags stay
    (raw,) = _terms(tmp_path, [dict(star, note_ar=RAW_NOTE)], True)
    assert raw == "، من الشباك فقط، لين 4 تذاكر"               # a raw source error is dropped, as note_ar(r, ok=True)
    real = yaml.safe_load(open(os.path.join(ROOT, "discounts.yaml"), encoding="utf-8"))["rules"]
    rules = [r for cs in real.values() for r in (cs or {}).values() if isinstance(r, dict) and r.get("type")]
    for lang in (True, False):
        for r, t in zip(rules, _terms(tmp_path, rules, lang)):
            parts = [p.strip() for p in t.split("،" if lang else ",") if p.strip()]
            assert len(parts) == len(set(parts)), (r, t)
            if lang and "الشباك" in (r.get("note_ar") or ""): assert t.count("الشباك") == r["note_ar"].count("الشباك"), t


# ------------------------------------------------------------------ #30 (build half) no hall heading over nothing
class Halls(HTMLParser):
    """Each <div class="hl"> block: its label and the times under it (to come, and passed)."""

    def __init__(self):
        super().__init__()
        self.stack, self.halls, self.cur = [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs); cls = (a.get("class") or "").split()
        if tag == "div" and "hl" in cls and self.cur is None:
            self.cur = {"hall": a.get("data-hall"), "live": 0, "past": 0, "tl": "", "depth": 0, "text": ""}
        if self.cur is not None:
            if tag == "div": self.cur["depth"] += 1
            if "tm" in cls: self.cur["past" if "past" in cls else "live"] += 1
            self.stack.append("tl" if "tl" in cls else tag)

    def handle_endtag(self, tag):
        if self.cur is None: return
        if self.stack: self.stack.pop()
        if tag == "div":
            self.cur["depth"] -= 1
            if self.cur["depth"] == 0: self.halls.append(self.cur); self.cur = None

    def handle_data(self, data):
        if self.cur is not None:
            self.cur["text"] += data
            if "tl" in self.stack: self.cur["tl"] += data


def halls_of(html):
    p = Halls(); p.feed(html); return p.halls


def test_a_hall_whose_times_have_all_passed_is_not_drawn(out):
    cin = halls_of(read(out, "al-ain", JIMI, "index.html"))
    film = read(out, "film", "heart-of-the-beast", "index.html")
    jimi = film[film.index(f'<div class="cg" data-cin="{JIMI}"'):]
    jimi = jimi[:jimi.index('<div class="cg" ', 10)] if '<div class="cg" ' in jimi[10:] else jimi
    assert not any(h["hall"] == "GOLD" for h in halls_of(jimi))                 # «قلب الوحش» GOLD: 11:00 only, built at 18:00
    assert sum(h["hall"] == "GOLD" for h in cin) == 1                            # The Paradise's GOLD pair stays on the cinema page
    (pair,) = [h for h in cin if h["hall"] == "GOLD"]
    assert pair["live"] == 1 and pair["past"] == 1                               # 21:00 to come, 11:00 faded
    paradise = halls_of(read(out, "film", "the-paradise", "index.html"))
    assert any(h["hall"] == "GOLD" for h in paradise)


def test_every_hall_heading_has_a_time_to_come(out):
    n = 0
    for p in pages(out):
        rel = os.path.relpath(p, out).replace(os.sep, "/")
        if not (rel.startswith(("film/", "en/film/")) or re.match(r"^(en/)?[a-z-]+/[a-z0-9-]+/index\.html$", rel)): continue
        h = open(p, encoding="utf-8").read()
        for hl in halls_of(h):
            assert hl["live"] or re.search(r"\d\d:\d\d", hl["tl"]), (rel, hl["hall"], hl["text"][:80])
            n += 1
        assert '<span class="tl"></span>' not in h, rel                            # no day row with nothing left
    assert n > 50


def test_live_halls_keeps_a_hall_with_any_time_to_come():
    site = build.Site.__new__(build.Site)
    site.today, site.now = "2026-09-25", site_kit.parse_iso("2026-09-25T18:00:00+04:00")
    from pages.core import CorePages
    cp = CorePages(site)
    shows = [{"cinema": "a", "date": "2026-09-25", "time": t, "k": k} for t, k in (("10:00", "gold"), ("12:00", "max"), ("19:00", "max"))]
    shows.append({"cinema": "a", "date": "2026-09-26", "time": "09:00", "k": "gold2"})
    kept = cp.live_halls(shows, lambda s: s["k"])
    assert [s["time"] for s in kept] == ["12:00", "19:00", "09:00"]              # gold (past only) goes; max keeps its 12:00


def test_a_film_with_every_show_started_says_it_has_none_to_come(out):
    """Review I1: a film's last night after its last start (no tomorrow listed) printed an empty schedule under the
    day controls. It now reads as a film with no shows: the lead, no day tab, and no ticket for a started show."""
    for parts, say in (((), "ما لقينا عروض لهذا الفيلم في اليومين الجايين."), (("en",), "No shows for this film in the next two days.")):
        h = read(out, *parts, "film", "last-night", "index.html")
        # legend: the redesign's schedule column (UI redesign Task 4) around the same lead, and no day bar
        assert f'<div class="cgs"><p class="nc" data-nc hidden></p><p class="lead">{say}</p><p class="empty" data-empty hidden></p></div>' in h, parts
        assert '<div class="hl"' not in h and 'data-day=' not in h and SHELL in h, parts
    busy = read(out, "film", "heart-of-the-beast", "index.html")
    assert '<details class="fcity' in busy and 'data-day=' in busy and SHELL not in busy


def test_a_cinema_with_every_time_today_started_says_when_tomorrows_come(out):
    for parts, say in (((), "مواعيد بكرة تنزل هني الصبح."), (("en",), "Tomorrow’s times appear here in the morning.")):
        h = read(out, *parts, "sharjah", SHJ, "index.html")
        assert f'<p class="hint">{say}</p>' in h and '<section class="day"' not in h and SHELL in h, parts
    busy = read(out, "al-ain", JIMI, "index.html")
    assert '<section class="day"' in busy and "مواعيد بكرة تنزل هني الصبح." not in busy and SHELL not in busy
