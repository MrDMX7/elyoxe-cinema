"""pages/board.py's home head (297, r4-home, owner idea 2026-09-30): the chosen city sits in the board's own
heading now («يبدأ قريب منك في دبي»/«Starting near you in Dubai»), not a separate line under it — and the same
`data-board-city` element board-paint.js's CB.draw already updates live still carries that job, just moved."""
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys  # noqa: E402

sys.path.insert(0, ROOT)
import build  # noqa: E402

DATA = os.path.join(ROOT, "fixtures", "sample_latest.json")
DISC = os.path.join(ROOT, "fixtures", "sample_discounts.yaml")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = str(tmp_path_factory.mktemp("r4home_city") / "out")
    build.build(DATA, DISC, o, noindex=False)
    return o


def test_home_board_heading_carries_the_city_in_both_languages(out):
    ar = read(out, "index.html")
    m = re.search(r'<h2 id="bh-t">(.*?)</h2>', ar, re.S)
    assert m, "no board heading on home"
    assert m.group(0) == '<h2 id="bh-t">يبدأ قريب منك<span class="bh-city" data-board-city-wrap> في <span data-board-city>دبي</span></span></h2>'
    en = read(out, "en", "index.html")
    m2 = re.search(r'<h2 id="bh-t">(.*?)</h2>', en, re.S)
    assert m2.group(0) == '<h2 id="bh-t">Starting near you<span class="bh-city" data-board-city-wrap> in <span data-board-city>Dubai</span></span></h2>'


def test_the_city_is_no_longer_repeated_on_its_own_line(out):
    """The old subline («دبي، الحين») is gone: only «الحين» + the clock is left under the heading -- the city
    is said once, in the heading."""
    h = read(out, "index.html")
    m = re.search(r'<p class="bh-s">.*?</p>', h, re.S)
    assert m and "data-board-city" not in m.group(0)
    assert "الحين" in m.group(0)


def test_geo_wait_still_hides_the_citys_first_guess(out):
    """A first visit with no saved city hides «في <city>» along with the rest of .bh-c (board.css .geo-wait)
    until /geo answers -- honesty §1.2: never claim a city before the visitor's own is known."""
    css = read("src", "css", "board.css")
    assert re.search(r"\.geo-wait\s+\.bh-c\s*,\s*\.geo-wait\s+\.bh-city\s*,", css), \
        ".geo-wait must hide .bh-city alongside .bh-c"


def test_board_paints_own_city_binding_is_unchanged(out):
    """board-paint.js still looks up the element by `[data-board-city]` alone, so moving it inside the h2 in
    Python needed no client change (CB.draw's `cn = q("[data-board-city]")`)."""
    js = read("src", "js", "board-paint.js")
    assert 'q("[data-board-city]")' in js
