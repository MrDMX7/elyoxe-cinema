"""cinema.js in node: the pure functions (src/js/pure.js — Arabic counted minutes, haversine, the time
filters, the prayer overlap, the film filters, the companion presets, the «الحين» window) run as they are,
and the built bundle parses (a syntax error there would silently disable every client feature)."""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")


def run(tmp_path, expr_js):
    src = open(os.path.join(ROOT, "src", "js", "pure.js"), encoding="utf-8").read()
    (tmp_path / "t.js").write_text(src + "\nprocess.stdout.write(JSON.stringify(" + expr_js + "));\n", encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_arabic_minutes_and_seats(tmp_path):
    got = run(tmp_path, "[0,1,2,3,9,10,11,45].map(function(n){return inMinutes(n,'ar')}).concat([inMinutes(9,'en'), seatsLeft(1,'ar'), seatsLeft(2,'ar'), seatsLeft(7,'ar'), seatsLeft(23,'ar'), seatsLeft(1,'en')])")
    assert got == ["يبدأ الحين", "بعد دقيقة", "بعد دقيقتين", "بعد 3 دقايق", "بعد 9 دقايق", "بعد 10 دقايق", "بعد 11 دقيقة", "بعد 45 دقيقة",
                   "in 9 min", "باقي مقعد واحد", "باقي مقعدين", "باقي 7 مقاعد", "باقي 23 مقعد", "1 seat left"]


def test_haversine_and_km_text(tmp_path):
    # Dubai Mall to Mall of the Emirates ≈ 11.9 km in a straight line; Abu Dhabi to Dubai ≈ 123 km
    got = run(tmp_path, "[haversine(25.1972,55.2796,25.1181,55.2006), haversine(24.4539,54.3773,25.2048,55.2708), haversine(1,1,1,1), kmText(4.24,'ar'), kmText(16.4,'en')]")
    assert 11.6 < got[0] < 12.1 and 120 < got[1] < 126 and got[2] == 0
    assert got[3] == "4.2 كم" and got[4] == "16 km"


def test_show_span_and_time_filters(tmp_path):
    got = run(tmp_path, """[showSpan('21:00','23:15'), showSpan('23:30','01:40'), showSpan('00:30','02:30'), showSpan('19:00',null,120), showSpan('19:00',null,null),
      endsOk(showSpan('21:00','23:15'),'23:00'), endsOk(showSpan('21:00','22:50'),'23:00'), endsOk(showSpan('23:30','01:40'),'24:00'), endsOk(showSpan('21:00','22:50'),''),
      endsOk(showSpan('22:00','23:59'),'24:00'), lateOk(showSpan('20:59','23:00'),true), lateOk(showSpan('21:00','23:00'),true), lateOk(showSpan('00:30','02:00'),true), lateOk(showSpan('14:00','16:00'),false)]""")
    assert got[:5] == [[1260, 1395], [1410, 1540], [30, 150], [1140, 1275], [1140, 1290]]   # calendar dates: 00:30 is early that day
    assert got[5:] == [False, True, False, True, True, False, True, True, True]


def test_prayer_overlap(tmp_path):
    # Maghrib at 18:10 (1090), a 20-minute congregation window
    got = run(tmp_path, """[overlaps(showSpan('17:00','19:00'),1090,20), overlaps(showSpan('18:20','20:30'),1090,20), overlaps(showSpan('18:31','20:30'),1090,20),
      overlaps(showSpan('16:00','18:09'),1090,20), overlaps(showSpan('16:00','18:11'),1090,20), overlaps(null,1090,20), overlaps(showSpan('17:00','19:00'),null,20)]""")
    assert got == [True, True, False, False, True, False, False]


def test_a_remembered_filter_falls_back_to_all_where_the_page_has_no_chip(tmp_path):
    got = run(tmp_path, """[effectiveFilter('genre:thriller', ['all','family','kids','genre:action']), effectiveFilter('genre:action', ['all','genre:action']),
      effectiveFilter('family', ['all','family','kids']), effectiveFilter('', ['all']), effectiveFilter('kids', [])]""")
    assert got == ["all", "genre:action", "family", "all", "all"]


def test_film_filters_and_companions(tmp_path):
    got = run(tmp_path, """[filmOk({genres:['action'],family:false,kids:false},'all'), filmOk({genres:['action']},'genre:action'), filmOk({genres:['drama']},'genre:action'),
      filmOk({family:true},'family'), filmOk({family:true,kids:false},'kids'), filmOk({kids:true},'kids'),
      whoPreset('family'), whoPreset('kids'), whoPreset('friends'), whoPreset('solo'), whoPreset(''), verdictRank('yes'), verdictRank('skip'), verdictRank('odd')]""")
    assert got[:6] == [True, True, False, True, False, True]
    assert got[6] == {"filt": "family", "before": "", "late": False, "sort": "time"}
    assert got[7] == {"filt": "kids", "before": "21:00", "late": False, "sort": "time"}
    assert got[8]["late"] is True and got[8]["sort"] == "time"
    assert got[9] == got[10] == {"filt": "all", "before": "", "late": False, "sort": ""}
    assert got[11:] == [0, 3, 2]


def test_now_window_prefers_the_nearest_cinema(tmp_path):
    got = run(tmp_path, """(function(){ var n = 1e12, m = 60e3;
      var shows = [{at:n-5*m,km:1,id:'started'},{at:n+10*m,km:8,id:'far-soon'},{at:n+30*m,km:2,id:'near-later'},{at:n+50*m,km:0.5,id:'too-late'}];
      var noloc = shows.map(function(s){return {at:s.at,km:null,id:s.id}});
      return [pickNow(shows,n,45).id, pickNow(noloc,n,45).id, pickNow([{at:n+46*m,km:1}],n,45)]; })()""")
    assert got == ["near-later", "far-soon", None]


def test_bundle_parses_and_has_every_module(tmp_path):
    js = build.bundle_js()
    p = tmp_path / "b.js"
    p.write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, "--check", str(p)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    for fn in ("function discAfter", "function renderPrices", "function openTicket", "function applyPrayer", "function applyFilters",
               "function askNear", "function openTrailer", "function bindPWA", "function inMinutes"):
        assert fn in js, fn
    # the same bundle evaluates without a page: it must not throw at load before touching the DOM
    assert js.startswith("(function () {") and js.rstrip().endswith("})();")


def test_service_worker_and_manifest(tmp_path):
    sw = open(os.path.join(ROOT, "src", "sw.js"), encoding="utf-8").read()
    r = subprocess.run([NODE, "--check", os.path.join(ROOT, "src", "sw.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "/offline.html" in sw and "10 * 60e3" in sw and '"/assets/"' in sw and '"/posters/"' in sw and '"/data/"' in sw
    m = json.load(open(os.path.join(ROOT, "src", "manifest.webmanifest"), encoding="utf-8"))
    assert m["name"] == "سينما" and m["dir"] == "rtl" and m["lang"] == "ar" and m["start_url"] == "/" and m["display"] == "standalone"
    assert m["theme_color"] == m["background_color"] == "#0F0B0C"
    assert {i["sizes"] for i in m["icons"]} == {"192x192", "512x512"} and any(i["purpose"] == "maskable" for i in m["icons"])
    for i in m["icons"]:
        assert os.path.exists(os.path.join(ROOT, "src", "icons", os.path.basename(i["src"])))


def test_language_filter_and_film_count(tmp_path):
    """Home's filter sheet (UI redesign Task 3): the language chip, and «اعرض N فيلم» counted as site_kit.films_n."""
    assert run(tmp_path, '[langOk("English", ""), langOk("English", "English"), langOk("Hindi", "English"), langOk("", "Arabic")]') == [True, True, False, False]
    got = run(tmp_path, '[1, 2, 5, 23].map(function (n) { return filmsN(n, "ar"); }).concat([filmsN(1, "en"), filmsN(23, "en")])')
    assert got == [build.Site.films_n(1, "ar"), build.Site.films_n(2, "ar"), build.Site.films_n(5, "ar"), build.Site.films_n(23, "ar"), "1 film", "23 films"]
    assert got[:4] == ["فيلم واحد", "فيلمين", "5 أفلام", "23 فيلم"]


def test_verdict_filter(tmp_path):
    """«يستاهل» in home's filter sheet (fix round 1, M4): only films whose verdict is yes."""
    assert run(tmp_path, '[filmOk({v: "yes"}, "yes"), filmOk({v: "mixed"}, "yes"), filmOk({v: "mixed"}, "all")]') == [True, False, True]


# ---------------------------------------------------------------- W1-P1: core.js in node (the clock, the hook bus)
# what core.js reads at load, and nothing more: a page with no saved state, no ?now= unless given
CORE_STUB = """
var window = { CT: {}, console: console, matchMedia: function () { return { matches: false }; },
  localStorage: { getItem: function () { return null; }, setItem: function () {}, removeItem: function () {} } };
var document = { documentElement: { lang: "ar" }, body: { getAttribute: function () { return null; } } };
var location = { search: %s };
function shareParams() {}
var __now = %d; Date.now = function () { return __now; };
"""


def core(tmp_path, expr, now_ms, search="", tz=None):
    """src/js/core.js run in node with Date.now() pinned to `now_ms` (and TZ set, if given), then `expr` printed as JSON."""
    src = CORE_STUB % (json.dumps(search), now_ms) + open(os.path.join(ROOT, "src", "js", "core.js"), encoding="utf-8").read()
    (tmp_path / "c.js").write_text(src + "\nprocess.stdout.write(JSON.stringify(" + expr + "));\n", encoding="utf-8")
    env = dict(os.environ, TZ=tz) if tz else None
    r = subprocess.run([NODE, str(tmp_path / "c.js")], capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_clock_is_dubais_whatever_the_devices_zone(tmp_path):
    """MASTER-PLAN §1.3: every timer reads UAE time from core.js (NOW, nowMin, TODAY), never the device's own hours. Run
    under TZ=America/New_York, where the device's clock says 13:30 on the 27th while Dubai is at 21:30, and at 00:30 on
    the 28th in Dubai while New York is still on the 27th."""
    import datetime as dt
    at = lambda s: int(dt.datetime.fromisoformat(s).timestamp() * 1000)
    expr = "[TODAY, TOMORROW, nowMin(), hhmm(NOW.getTime()), new Date(Date.now()).getHours()]"
    got = core(tmp_path, expr, at("2026-09-27T21:30:00+04:00"), tz="America/New_York")
    assert got[:4] == ["2026-09-27", "2026-09-28", 21 * 60 + 30, "21:30"]
    assert got[4] == 13                                               # the device's own hour: what a naive timer would read
    got = core(tmp_path, expr, at("2026-09-28T00:30:00+04:00"), tz="America/New_York")
    assert got[:4] == ["2026-09-28", "2026-09-29", 30, "00:30"] and got[4] == 16   # New York: 16:30 on the 27th
    # ?now= pretends it is that UAE time, and the device's zone still does not enter
    got = core(tmp_path, expr, at("2026-09-27T21:30:00+04:00"), search="?now=2026-09-27T23:50", tz="America/New_York")
    assert got[:4] == ["2026-09-27", "2026-09-28", 23 * 60 + 50, "23:50"]
    # and the same instant read in Dubai itself agrees
    assert core(tmp_path, expr, at("2026-09-27T21:30:00+04:00"), tz="Asia/Dubai")[:4] == ["2026-09-27", "2026-09-28", 1290, "21:30"]


def test_the_hook_bus_runs_every_handler_in_order_and_survives_one_that_throws(tmp_path):
    expr = """(function () {
      var seen = [];
      var err = console.error; console.error = function () { seen.push("logged"); };
      on("card", function (x) { seen.push("a:" + x); });
      on("card", function () { throw new Error("boom"); });
      on("card", function (x) { seen.push("c:" + x); });
      on("minute", function (x) { seen.push("m:" + (x === NOW)); });
      emit("card", "fazaa"); emit("minute", NOW); emit("nobody-listens", 1);
      console.error = err;
      return seen; })()"""
    assert core(tmp_path, expr, 1790000000000) == ["a:fazaa", "logged", "c:fazaa", "m:true"]


def test_main_emits_the_six_events_and_the_minute_is_aligned():
    """The events main.js promises (docs/PLUGINS.md): ready at the end of start-up, slice when the city's shows are in,
    card and city when the visitor picks one, day on a day button, minute at each UAE :00 from one aligned timeout."""
    main = open(os.path.join(ROOT, "src", "js", "main.js"), encoding="utf-8").read()
    for ev in ("ready", "slice", "card", "city", "day", "minute"):
        assert f'emit("{ev}"' in main, ev
    assert "setInterval(" not in main                                 # never a free interval (MASTER-PLAN §1.3)
    assert "60e3 - (Date.now() + FAKE) % 60e3" in main                # the next :00 of the page's own UAE clock
    assert main.rstrip().endswith('emit("ready");\n})();')            # the last thing start-up does
    assert "citySlice()" in main and 'if (S && S.city === city) emit("slice", S)' in main
