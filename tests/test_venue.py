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


# ---------------------------------------------------------------- a real build: the slots actually fill
@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("venue"))
    build.build(DATA, DISC, o, noindex=False)
    return o


def read(out_dir, *parts):
    return open(os.path.join(out_dir, *parts), encoding="utf-8").read()


def test_mall_note_on_a_cinema_we_have_hours_for(out):
    # reel-dubai-mall is in the sample fixture and in malls.yaml (dubai-mall)
    html = read(out, "dubai", "reel-dubai-mall", "index.html")
    assert 'class="mall-note"' in html and "المول يسكّر" in html


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
