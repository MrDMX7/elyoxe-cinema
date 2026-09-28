"""R0 (MASTER-PLAN §0.3 H4): main's Wave 0 merged into legend. Where both sides built the same page, the merge had to
make main's logic work on the redesign's markup; these are the joins it made, each small enough to test on its own.
The page-level behaviour (a show link landing in a folded city or past the three cinemas laid out, the dock, the
late line through the dock) is driven in Chrome by the R0 smoke (the report in .superpowers/sdd/2026-09-28-legend/).

- #30 against Task 4 I2: the visitor's chosen time (.on) counts as one to come, so a chosen show that starts keeps
  its cinema on screen (hidePassed would have hidden it and film.js would have dropped the dock).
- #27: film.js owns the film page's desktop column (Task 4 I5); ticket.js's rollTicket serves the other pages.
- #23: the film page finds a show link's key in the markup film.js has not laid out yet (keyShow), opens it
  (fsReveal) and then picks the new button.
- #5: home's «الحين» target is the «يبدأ قريب منك» row (id="now"), clear of the sticky header."""
import os
import re
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_w0_p3 import FAKE_DOM, needs_node, node  # noqa: E402
import build  # noqa: E402  (test_w0_p3 put the repo on sys.path)

JS = Path(ROOT, "src", "js")


@needs_node
def test_a_chosen_time_counts_as_one_to_come(tmp_path):
    got = node(tmp_path, ["pure.js", "filters.js"], pre=FAKE_DOM, expr="""(function () {
      ALL.length = 0; body = El("", {});
      var main = El("cgs", {}, body), city = El("fcity", {}, main);
      var a = El("cg", {"data-cin": "a"}, city), ta = El("times", {"data-d": "2026-09-27"}, a);
      El("tm past on", {"data-start": "22:00"}, ta); El("tm past", {"data-start": "21:00"}, ta);
      var b = El("cg", {"data-cin": "b"}, city), tb = El("times", {"data-d": "2026-09-27"}, b);
      El("tm past", {"data-start": "22:00"}, tb);
      var c = El("cg", {"data-cin": "c"}, city), tc = El("times", {"data-d": "2026-09-27"}, c);
      El("tm past", {"data-start": "22:00"}, tc); El("tm", {"data-start": "23:00"}, tc);
      hidePassed();
      return [a.classList.contains("x"), b.classList.contains("x"), c.classList.contains("x"), city.classList.contains("x")]; })()""")
    # a: its only live time is the chosen, started one: kept. b: all passed, none chosen: gone. c: one to come: kept
    assert got == [False, True, False, False]


def test_the_film_pages_desktop_column_is_film_js_s():
    tk = (JS / "ticket.js").read_text(encoding="utf-8")
    roll = tk[tk.index("function rollTicket()"):]
    assert re.match(r'function rollTicket\(\) \{\s*if \(!tk \|\| page === "film" \|\|', roll)
    frm = tk[tk.index("function showFromHash()"):tk.index("function tkScope()")]
    assert "rollTicket()" not in frm and "fsCheck()" in frm


def test_a_show_link_is_found_before_the_layout_and_revealed():
    tk = (JS / "ticket.js").read_text(encoding="utf-8")
    ks = tk[tk.index("function keyShow("):tk.index("function showFromHash()")]
    assert '".tl"' in ks and "showKey(cin, d, x[0], x[1])" in ks        # compact text times count, each with its hall key
    frm = tk[tk.index("function showFromHash()"):tk.index("function tkScope()")]
    assert frm.index("fsReveal(cg)") < frm.index("schedTimes(cg)")       # laid out first, then the new button is found
    assert "tkOpen(hit)" in frm                                           # a phone lands on the ticket, over the dock
    film = (JS / "film.js").read_text(encoding="utf-8")
    rv = film[film.index("function fsReveal("):film.index("function fsSoon(")]
    assert "sec.open = true" in rv and 'classList.remove("more-h")' in rv and "fsHydrate(sec)" in rv


def test_the_now_target_clears_the_sticky_header():
    css = build.css_source()
    assert "#now{scroll-margin-block-start:calc(var(--head) + 8px)}" in css
