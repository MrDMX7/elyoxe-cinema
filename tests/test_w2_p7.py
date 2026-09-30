"""pages/coming.py's Thursday issue (W2-P7, MASTER-PLAN §2.6): the masthead marquee, the home band (only in
the two live phases), and /cal/thursday.ics. Built with only core + coming, like test_pages_coming_hubs.py."""
import json
import os
import re

import pytest

import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")
DATA = os.path.join(ROOT, "tests", "fixtures", "coming_sample.json")
MODULES = build.discover(only=("core", "coming"))


def read(out, *parts):
    return open(os.path.join(out, *parts), encoding="utf-8").read()


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("w2_p7"))
    build.build(DATA, DISC, o, modules=MODULES)
    return o


def test_masthead_shows_the_word_the_date_count_and_a_templated_intro(out):
    h = read(out, "coming", "index.html")
    m = re.search(r'<div class="cs-mast paper lit">(.*?)</div>', h, re.S)
    assert m, "no masthead on /coming/"
    mast = m.group(1)
    assert "الخميس" in mast
    assert "1 أكتوبر 2026" in mast and "فيلم واحد" in mast   # the fixture's one dated opener (Verity)
    assert "Verity" in mast and "سلسلة وحدة" in mast          # one chain (vox) announcing it -- a real number
    assert "الأحكام تنزل من الخميس للسبت" in mast
    # never a fabricated per-cinema screen count
    assert "سينما" not in mast.replace("سينمات الإمارات", "")


def test_masthead_absent_when_nothing_dated_is_known(tmp_path):
    d = json.load(open(DATA, encoding="utf-8"))
    d["coming"] = {"gatto": d["coming"]["gatto"]}   # undated only
    p = tmp_path / "data.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(p), DISC, o, modules=MODULES)
    h = open(os.path.join(o, "coming", "index.html"), encoding="utf-8").read()
    assert "cs-mast" not in h


def test_countdown_prints_once_in_the_heading_never_gold_on_a_card(out):
    h = read(out, "coming", "index.html")
    assert re.search(r'<h2>1 أكتوبر 2026</h2><p class="cs-cd">بعد \d+ (يوم|أيام)</p>', h)
    assert "cs-cd" not in re.sub(r'<p class="cs-cd">.*?</p>', "", h)   # only the heading's own


def test_home_band_only_in_the_two_live_phases(out, monkeypatch):
    from site_kit import Kit

    import pages.coming as cm

    class Fake:
        def __init__(self, now):
            self.now = now
            self.d = json.load(open(DATA, encoding="utf-8"))
            self.today = "2026-09-25"

        def week_phase(self, now):
            return Kit.week_phase(now)

    import datetime as dt

    wed_eve = dt.datetime(2026, 9, 30, 18, 30)   # Wednesday 18:30
    rest = dt.datetime(2026, 9, 28, 10, 0)       # Monday

    assert cm.ComingPages(Fake(wed_eve))._band("ar") != ""
    assert cm.ComingPages(Fake(rest))._band("ar") == ""


def test_thursday_ics_is_iphone_only_channel_and_never_immutable():
    src = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
    assert '--include "*.ics"' in src
    assert '--content-type "text/calendar; charset=utf-8"' in src
    assert '--cache-control "public, max-age=300"' in src
    assert '--exclude "*.ics"' in src   # kept out of the immutable pass


def test_cal_ics_validates_and_holds_one_vevent_per_dated_thursday(out):
    # read raw (newline="") -- open()'s own universal-newline translation would hide a wrong line ending
    raw = open(os.path.join(out, "cal", "thursday.ics"), encoding="utf-8", newline="").read()
    assert raw.startswith("BEGIN:VCALENDAR\r\n")
    assert "VERSION:2.0" in raw and raw.rstrip().endswith("END:VCALENDAR")
    assert "TZID:Asia/Dubai" in raw
    assert raw.count("BEGIN:VEVENT") == 1 and raw.count("END:VEVENT") == 1   # only Verity is dated
    assert "DTSTART;TZID=Asia/Dubai:20261001T100000" in raw
    assert "SUMMARY:" in raw and "Verity" in raw
    for line in raw.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75 or line.startswith(" ")


def test_cal_ics_never_invents_a_dated_thursday_when_none_is_known(tmp_path):
    d = json.load(open(DATA, encoding="utf-8"))
    d["coming"] = {"gatto": d["coming"]["gatto"]}
    p = tmp_path / "data.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    o = str(tmp_path / "out")
    build.build(str(p), DISC, o, modules=MODULES)
    ics = open(os.path.join(o, "cal", "thursday.ics"), encoding="utf-8").read()
    assert "BEGIN:VEVENT" not in ics
    assert ics.startswith("BEGIN:VCALENDAR") and "END:VCALENDAR" in ics
