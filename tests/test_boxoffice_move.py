"""pages/insights.py's Insights.rank_move (the week-over-week word on /boxoffice/): a pure function of
(rank_now, prev_rank, lang), tested without building a page."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pages.insights import Insights  # noqa: E402


def test_new_entry_has_no_previous_rank():
    kind, text = Insights.rank_move(3, None, "ar")
    assert kind == "new" and text == "جديد"


def test_same_rank_is_no_change():
    kind, text = Insights.rank_move(2, 2, "ar")
    assert kind == "same"


def test_moved_up_says_talaa_with_the_count():
    kind, text = Insights.rank_move(2, 5, "ar")   # was #5, now #2: up 3
    assert kind == "up" and "طلع" in text and "3" in text


def test_moved_down_says_nazal():
    kind, text = Insights.rank_move(5, 2, "ar")   # was #2, now #5: down 3
    assert kind == "down" and "نزل" in text


def test_singular_and_dual_forms():
    assert "مرتبة" == Insights.rank_move(2, 3, "ar")[1].split()[-1]     # up 1
    assert Insights.rank_move(3, 5, "ar")[1].endswith("مرتبتين")        # up 2


def test_english_side():
    kind, text = Insights.rank_move(2, 5, "en")
    assert kind == "up" and text == "Up 3 spots"
    kind, text = Insights.rank_move(3, None, "en")
    assert kind == "new" and text == "New"
