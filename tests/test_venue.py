"""pages/venue.py — Phase 2 Task 4 (docs/superpowers/specs/2026-09-27-phase2-design.md, C «Planning» +
B.46 «Snacks»): mall-closing time math (including past-midnight shows), double-feature pairing, and the
rendered sections on a real build. src/js/plan.js's own pure functions (ics text, the Google Calendar
link, leave-by) run in node, the same way tests/test_js.py runs pure.js."""
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
from pages import venue  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
NODE = shutil.which("node")


def show(cin="c1", film="f1", date="2026-09-25", time="20:00", ends=None):
    s = {"cinema": cin, "film": film, "date": date, "time": time}
    if ends:
        s["ends"] = ends
    return s


# ---------------------------------------------------------------- mall hours / closing
def test_close_minutes_midnight_is_the_end_of_that_date():
    mall = {"hours": {"thu": "00:00", "fri": "23:00"}}
    assert venue.close_minutes(mall, "2026-10-01") == 1440   # 2026-10-01 is a Thursday
    assert venue.close_minutes(mall, "2026-10-02") == 1380   # Friday


def test_close_minutes_absent_day_is_none_not_guessed():
    mall = {"hours": {"thu": "22:00"}}
    assert venue.close_minutes(mall, "2026-10-02") is None    # Friday not in hours: absent


def test_show_end_minutes_crosses_midnight():
    assert venue.show_end_minutes(show(time="23:30", ends="01:15")) == 1515   # +24h
    assert venue.show_end_minutes(show(time="14:00", ends="16:20")) == 980
    assert venue.show_end_minutes(show(time="14:00")) is None   # no estimate: never guessed


def test_shows_past_closing():
    mall = {"hours": {"thu": "22:00"}}
    ss = [show(time="19:00", ends="21:45"), show(time="20:30", ends="22:30", film="f2")]
    late = venue.shows_past_closing(ss, mall, "2026-10-01")   # Thursday
    assert [s["film"] for s in late] == ["f2"]


def test_mall_for_cinema_only_matches_a_listed_cinema():
    malls = {"m1": {"cinemas": ["a", "b"]}}
    assert venue.mall_for_cinema(malls, "a")[0] == "m1"
    assert venue.mall_for_cinema(malls, "z") == (None, None)


def test_indirectly_sourced_malls_are_flagged_in_the_data_itself():
    """The three City Centre entries could not be fetched directly this pass (review minor #3): they
    must carry `source_note` so a future maintainer knows to re-verify them, without having to diff
    against the task report to find out which ones."""
    malls = venue.load_malls()
    indirect = ("city-centre-deira", "city-centre-mirdif", "city-centre-sharjah")
    for mid in indirect:
        assert malls[mid].get("source_note"), mid
    # every directly-fetched entry stays unflagged (source_note is not padding on everything)
    assert "source_note" not in malls["dubai-mall"]
    assert "source_note" not in malls["abu-dhabi-mall"]


# ---------------------------------------------------------------- snacks (B.46)
class _SiteStub:
    """Just enough of Kit for snacks_section: .rules (already official-only, as site_kit filters it), .disc's
    cards (their names), .today and .h.chain_name — never the full build, so this stays a unit test of
    venue.py's own logic."""
    def __init__(self, rules=None, cards=None):
        self.rules = rules or {}
        self.disc = {"cards": cards or []}
        self.today = "2026-09-25"
        self.h = types.SimpleNamespace(chain_name=lambda chain, lang: chain)


def test_snacks_price_is_wrapped_in_num_like_every_other_price(monkeypatch):
    monkeypatch.setattr(venue, "load_snacks", lambda: {
        "vox": {"combos": [{"ar": "بوشار", "en": "Popcorn", "aed": 26.0, "source": "https://x", "checked": "2026-09-27"}]}})
    html = venue.snacks_section(_SiteStub(), "ar", "vox")
    assert 'class="num"' in html and money_str(26.0) in html


def money_str(x):
    from site_kit import money
    return money(x)


def test_snacks_note_ar_is_rendered_not_dropped(monkeypatch):
    monkeypatch.setattr(venue, "load_snacks", lambda: {
        "vox": {"combos": [{"ar": "ناتشوز", "en": "Nachos", "aed": 53.0, "note_ar": "مع جبنة وصوص",
                             "source": "https://x", "checked": "2026-09-27"}]}})
    html = venue.snacks_section(_SiteStub(), "ar", "vox")
    assert "مع جبنة وصوص" in html and 'class="ndesc"' in html


def test_snacks_note_ar_absent_on_english_page(monkeypatch):
    monkeypatch.setattr(venue, "load_snacks", lambda: {
        "vox": {"combos": [{"ar": "ناتشوز", "en": "Nachos", "aed": 53.0, "note_ar": "مع جبنة وصوص",
                             "source": "https://x", "checked": "2026-09-27"}]}})
    html = venue.snacks_section(_SiteStub(), "en", "vox")
    assert "مع جبنة وصوص" not in html


def test_snacks_no_chain_entry_renders_nothing(monkeypatch):
    monkeypatch.setattr(venue, "load_snacks", lambda: {})
    assert venue.snacks_section(_SiteStub(), "ar", "novo") == ""


# ---------------------------------------------------------------- FOOD_WORDS heuristic
def test_food_words_surfaces_an_official_note_that_mentions_food(monkeypatch):
    monkeypatch.setattr(venue, "load_snacks", lambda: {})   # no combos: isolate the food-discount branch
    rules = {"cineroyal": {"fab": {"type": "fixed", "note_ar": "التذكرة بـ20 درهم وخصم 20% على الأكل", "source": "https://cineroyal.ae/x"}}}
    html = venue.snacks_section(_SiteStub(rules), "ar", "cineroyal")
    assert 'class="food-disc"' in html and "الأكل" in html


def test_food_line_names_its_card(monkeypatch):
    """«خصم البطاقات على الأكل» listed HSBC's rule with no card name (W0-P2, MASTER-PLAN §4.1 #16)."""
    monkeypatch.setattr(venue, "load_snacks", lambda: {})
    rules = {"vox": {"hsbc": {"type": "bogo", "note_ar": "اشترِ تذكرة وخذ الثانية مجاناً + خصم 25% على المأكولات", "source": "https://x"}}}
    cards = [{"id": "hsbc", "name_ar": "إتش إس بي سي", "name_en": "HSBC"}]
    ar = venue.snacks_section(_SiteStub(rules, cards), "ar", "vox")
    assert re.search(r'<ul class="food-disc"><li><b><bdi>إتش إس بي سي</bdi></b>: اشترِ تذكرة', ar)
    en = venue.snacks_section(_SiteStub(rules, cards), "en", "vox")
    assert '<b><bdi>HSBC</bdi></b>: <span lang="ar" dir="rtl">' in en


def test_food_line_skips_an_expired_offer(monkeypatch):
    monkeypatch.setattr(venue, "load_snacks", lambda: {})
    rules = {"vox": {"hsbc": {"type": "bogo", "valid_until": "2026-09-01", "note_ar": "خصم 25% على المأكولات", "source": "https://x"}}}
    assert venue.snacks_section(_SiteStub(rules), "ar", "vox") == ""


def test_food_words_skips_a_note_that_never_mentions_food():
    rules = {"star": {"fazaa": {"note_ar": "من الشباك فقط، 4 تذاكر باليوم", "source": "https://x"}}}
    assert venue.snacks_section(_SiteStub(rules), "ar", "star") == ""   # no combos, no food word: nothing


def test_food_words_matches_every_listed_word():
    for w in venue.FOOD_WORDS:
        rules = {"c": {"card": {"type": "percent", "note_ar": f"خصم على {w}", "source": "https://x"}}}
        assert venue.snacks_section(_SiteStub(rules), "ar", "c") != "", w


# ---------------------------------------------------------------- double feature (design C.43)
def test_double_feature_pairs_within_15_to_45_minutes():
    ss = [show(cin="c1", film="a", time="18:00", ends="20:00"),
          show(cin="c1", film="b", time="20:14", ends="22:00"),    # gap 14: too soon
          show(cin="c1", film="c", time="20:15", ends="22:20"),    # gap 15: in
          show(cin="c1", film="d", time="20:45", ends="23:00"),    # gap 45: in
          show(cin="c1", film="e", time="20:46", ends="23:05")]    # gap 46: too far
    pairs = venue.double_features(ss)
    got = sorted((b["film"], gap) for a, b, gap in pairs if a["film"] == "a")
    assert got == [("c", 15), ("d", 45)]


def test_double_feature_ignores_other_cinemas_other_dates_and_same_film():
    ss = [show(cin="c1", film="a", time="18:00", ends="20:00"),
          show(cin="c2", film="b", time="20:20", ends="22:00"),                     # different cinema
          show(cin="c1", film="a", time="20:20", ends="22:00"),                     # same film as a
          show(cin="c1", film="b", date="2026-09-26", time="20:20", ends="22:00")]  # different date
    assert venue.double_features(ss) == []


def test_double_feature_across_midnight():
    # a is dated today and ends after midnight; b is dated TOMORROW (as the data itself would date a
    # 02:00 show) — they must still pair, on the real calendar rather than each show's own date alone.
    ss = [show(cin="c1", film="a", date="2026-09-25", time="23:30", ends="01:45"),
          show(cin="c1", film="b", date="2026-09-26", time="02:00", ends="04:00")]
    pairs = venue.double_features(ss)
    assert len(pairs) == 1
    a, b, gap = pairs[0]
    assert a["film"] == "a" and b["film"] == "b" and gap == 15


class _PairSite:
    """ftitle / cname / cinemas for double_feature_html — the slot's rendering alone, at real volume."""
    def __init__(self, n_cin):
        cities = ["dubai", "abu-dhabi", "sharjah", "al-ain"]
        self.cinemas = {f"c{i}": {"city": cities[i % len(cities)], "chain": "vox"} for i in range(n_cin)}

    def ftitle(self, fid, lang): return f"Film {fid}"
    def cname(self, cid, lang): return f"Cinema {cid}"


def _busy_day(n_cin=60, films="abcdefgh"):
    """Every cinema shows every film every 20 minutes from 12:00: thousands of 15-45 minute pairs."""
    ss = []
    for i in range(n_cin):
        for j, f in enumerate(films):
            for k in range(12):
                m = 12 * 60 + j * 7 + k * 50
                e = m + 120
                ss.append(show(cin=f"c{i}", film=f, time=f"{m // 60 % 24:02d}:{m % 60:02d}", ends=f"{e // 60 % 24:02d}:{e % 60:02d}"))
    return ss


def test_group_pairs_folds_times_of_the_same_films_at_the_same_cinema():
    ss = [show(cin="c1", film="a", time="18:00", ends="20:00"), show(cin="c1", film="b", time="20:20", ends="22:00"),
          show(cin="c1", film="a", time="21:00", ends="23:00"), show(cin="c1", film="b", time="23:30", ends="01:00")]
    groups = venue.group_pairs(venue.double_features(ss))
    assert groups == [("c1", "a", "b", [("18:00", "20:20"), ("21:00", "23:30")])]


def test_venue_no_longer_fills_the_film_page():
    """The film page's all-cities double feature is deleted (W0-P2, MASTER-PLAN §4.1 #14)."""
    assert not hasattr(venue, "film_double_feature_html")
    plugin = venue.register(types.SimpleNamespace())
    # W2-P6 (MASTER-PLAN §2.4, §2.5): the redesigned cinema and city pages load the lazy places-live chunk too
    assert set(plugin.slots) == {"cinema.after_halls"} and plugin.page_js == {
        "cinema": ["when", "places-live"], "city": ["places-live"]}


def test_cinema_page_double_features_are_grouped_bounded_and_written_with_then():
    site = _PairSite(1)
    pairs = venue.double_features(_busy_day(1))
    html = venue.double_feature_html(site, "ar", pairs, "2026-09-25")
    assert html.startswith('<details class="dfeat" data-d="2026-09-25" data-when-group><summary>فيلمين ورا بعض</summary>')
    # no heavier than the arrow version (< 6 KB): the block counts against the page budget, and the schedule's
    # per-show booking links must never be what gives way for it
    assert html.count("<li data-when-group>") == min(len(venue.group_pairs(pairs)), venue.MAX_LINES) and len(html.encode()) < 6_000
    # two start times in reading order, «ثم» between them, and no arrow left to flip in an RTL line
    assert '<span data-until="12:00">12:00 ثم 14:37</span>' in html
    assert "→" not in html and "←" not in html and "</details>" in html
    assert re.search(r'<b><bdi>Film a</bdi></b> ثم <b><bdi>Film [b-h]</bdi></b>', html)
    en = venue.double_feature_html(site, "en", pairs, "2026-09-25")
    assert " then " in en and "→" not in en


class _Kit:
    """The Kit surface future_pairs reads: today's shows by cinema and the build's clock."""
    def __init__(self, shows, now="21:30", today="2026-09-25"):
        self._by_cin, self.today, self._now = {}, today, now
        for s in shows: self._by_cin.setdefault(s["cinema"], []).append(s)

    def is_past(self, s):
        return (s["date"], s["time"]) < (self.today, self._now)


def test_cinema_page_keeps_only_pairs_whose_first_film_has_not_started():
    ss = [show(film="a", time="19:00", ends="21:00"), show(film="b", time="21:20", ends="23:00"),   # a started: gone
          show(film="c", time="21:40", ends="23:30"), show(film="d", time="23:50", ends="01:30")]   # c ahead: kept
    pairs = venue.future_pairs(_Kit(ss), "c1")
    assert [(a["film"], b["film"]) for a, b, _ in pairs] == [("c", "d")]
    assert venue.double_feature_html(_PairSite(2), "ar", venue.future_pairs(_Kit(ss, now="23:59"), "c1"), "2026-09-25") == ""


# ---------------------------------------------------------------- a real build: the slots actually fill
@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("venue"))
    build.build(DATA, DISC, o, noindex=False)
    return o


def read(out_dir, *parts):
    return open(os.path.join(out_dir, *parts), encoding="utf-8").read()


def test_mall_note_on_a_cinema_we_have_hours_for(out):
    # reel-dubai-mall is in the sample fixture and in malls.yaml (dubai-mall). W2-P6 (MASTER-PLAN §2.4) moved
    # «المول يسكّر HH:MM» out of venue.py's own .mall-note block and into the cinema page's own head .meta
    # (pages/_core/places.py); mall_section()/mall_note() stay for any other page that still wants the block.
    html = read(out, "dubai", "reel-dubai-mall", "index.html")
    assert 'class="closes"' in html and "المول يسكّر" in html


def test_no_mall_note_for_a_cinema_we_never_confirmed():
    malls = venue.load_malls()
    # every fixture cinema not in malls.yaml renders nothing rather than a guess
    assert venue.mall_for_cinema(malls, "novo-manar-mall") == (None, None)


def test_snacks_render_only_for_a_chain_in_snacks_yaml(out):
    html = read(out, "abu-dhabi", "vox-yas-mall", "index.html")   # vox is in snacks.yaml
    assert 'class="snacks"' in html and "الأكل" in html


def test_plan_js_is_in_the_bundle_and_bundle_still_parses(tmp_path):
    js = build.bundle_js()
    assert "function planIcs" in js and "function planLeaveBy" in js
    if NODE:
        p = tmp_path / "b.js"
        p.write_text(js, encoding="utf-8")
        r = subprocess.run([NODE, "--check", str(p)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- plan.js pure functions, in node
PLAN = os.path.join(ROOT, "src", "js", "plan.js")
pytestmark_node = pytest.mark.skipif(not NODE, reason="node not installed")


def run(tmp_path, expr_js):
    src = open(PLAN, encoding="utf-8").read()
    # minimal stand-ins for the bundle-scope helpers plan.js relies on (core.js/pure.js — this file is
    # not those files' to edit, so the same tiny pure definitions are restated here for the node run only)
    stub = ("var FEAT=[];function feature(fn){FEAT.push(fn);}var AR=true;"
            "function esc(s){return String(s);}"
            "function sub(s,o){return s.replace(/\\{(\\w+)\\}/g,function(m,k){return o[k];});}"
            "function haversine(lat1,lng1,lat2,lng2){var r=Math.PI/180,a=Math.sin((lat2-lat1)*r/2),b=Math.sin((lng2-lng1)*r/2);"
            "var h=a*a+Math.cos(lat1*r)*Math.cos(lat2*r)*b*b;return 12742*Math.asin(Math.min(1,Math.sqrt(h)));}"
            "function hhmm(ms){return new Date(ms+4*3600e3).toISOString().slice(11,16);}\n")
    (tmp_path / "t.js").write_text(stub + src + "\nprocess.stdout.write(JSON.stringify(" + expr_js + "));\n", encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_ics_has_the_required_fields_and_asia_dubai_tz(tmp_path):
    ics = run(tmp_path, 'planIcs({film:"فيلم",cin:"سينما",date:"2026-09-27",time:"20:00",endHm:"22:15",lat:25.1,lng:55.2})')
    for needle in ("BEGIN:VCALENDAR", "BEGIN:VEVENT", "BEGIN:VALARM", "TRIGGER:-PT60M", "TZID:Asia/Dubai",
                   "DTSTART;TZID=Asia/Dubai:20260927T200000", "DTEND;TZID=Asia/Dubai:20260927T221500"):
        assert needle in ics, ics


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_ics_end_after_midnight_rolls_the_date(tmp_path):
    ics = run(tmp_path, 'planIcs({film:"a",cin:"b",date:"2026-09-27",time:"23:30",endHm:"01:15",lat:null,lng:null})')
    assert "DTEND;TZID=Asia/Dubai:20260928T011500" in ics


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_ics_escapes_commas_and_newlines(tmp_path):
    ics = run(tmp_path, 'planIcs({film:"a, b\\nc",cin:"x",date:"2026-09-27",time:"20:00",endHm:null,lat:null,lng:null})')
    assert "SUMMARY:a\\, b\\nc — x" in ics


def _ics_esc(s):
    """Python mirror of plan.js's planIcsEsc, for building the expected value in the folding test."""
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _unfold_ics(text):
    """RFC 5545 §3.1 unfolding: a CRLF immediately followed by exactly one space or tab continues the
    previous logical line. This is the small unfold/parse helper the fold fix is checked against."""
    return re.sub(r"\r\n[ \t]", "", text)


def _ics_props(text):
    """{property name: value} from the UNFOLDED text (this file's properties never repeat a name)."""
    out = {}
    for ln in _unfold_ics(text).split("\r\n"):
        if ln and ":" in ln:
            k, _, v = ln.partition(":")
            out[k.split(";")[0]] = v
    return out


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_ics_long_arabic_lines_are_folded_at_75_octets_and_unfold_correctly(tmp_path):
    film = "فيلم طويل جداً, بعنوان يحكي قصة قديمة عن رحلة بعيدة جداً في الصحراء الكبرى وسط الليل"
    cin = "سينما فوكس — مول الإمارات الكبير في الطابق الثاني قرب المدخل الرئيسي جداً وبعيد شوي"
    x = {"film": film, "cin": cin, "date": "2026-09-27", "time": "20:00", "endHm": "22:15", "lat": 25.1, "lng": 55.2}
    ics = run(tmp_path, "planIcs(" + json.dumps(x, ensure_ascii=False) + ")")
    physical = ics.split("\r\n")
    if physical and physical[-1] == "":
        physical = physical[:-1]
    # it actually folded (more physical lines than the fixed 16-line template) and every one is legal
    assert len(physical) > 16
    for ln in physical:
        n = len(ln.encode("utf-8"))
        assert n <= 75, (n, ln)
    assert any(ln.startswith(" ") for ln in physical)          # continuation lines exist
    assert not any(ln.startswith("  ") for ln in physical)     # exactly one leading space, never more
    # never split a multi-byte Arabic character: every physical line must itself decode as valid UTF-8
    for ln in physical:
        ln.encode("utf-8").decode("utf-8")   # raises UnicodeDecodeError on a broken split
    # unfolding restores exactly the original, unfolded property values
    props = _ics_props(ics)
    assert props["SUMMARY"] == _ics_esc(film + " — " + cin)
    assert props["LOCATION"] == _ics_esc(cin)
    assert props["TRIGGER"] == "-PT60M"


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_ics_short_ascii_lines_stay_unfolded(tmp_path):
    ics = run(tmp_path, 'planIcs({film:"a",cin:"b",date:"2026-09-27",time:"20:00",endHm:null,lat:null,lng:null})')
    assert "\r\n " not in ics   # nothing here is anywhere near 75 octets


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_gcal_url_uses_utc_and_is_four_hours_behind_local(tmp_path):
    url = run(tmp_path, 'planGCalUrl({film:"a",cin:"b",date:"2026-09-27",time:"20:00",endHm:"22:00",lat:null,lng:null})')
    assert "dates=20260927T160000Z%2F20260927T180000Z" in url


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_leave_by_returns_null_with_no_location(tmp_path):
    got = run(tmp_path, 'planLeaveBy({date:"2026-09-27",time:"20:00",lat:25.1,lng:55.2}, null)')
    assert got is None


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_leave_by_is_before_showtime_and_labelled_approximate(tmp_path):
    got = run(tmp_path, 'planLeaveBy({date:"2026-09-27",time:"20:00",lat:25.2048,lng:55.2708}, {lat:24.4539,lng:54.3773})')
    assert re.match(r"^\d\d:\d\d$", got)
    assert got < "20:00"   # Abu Dhabi to Dubai is a real drive: leaves well before 8pm
