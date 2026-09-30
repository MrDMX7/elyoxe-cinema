"""kit/tile.py TileKit.week_tag (round 3 QA fix, owner idea #284): the poster-TILE-only «جديد»/«الأسبوع N»
micro-label. The film page itself already shows the full release date (pages/_core/film.py film_about) --
this is a separate, tile-only helper, never a replacement for it. No «آخر عرض» countdown is ever built here:
no chain data field marks a last-showing date, so nothing is inferred (deliberately not implemented)."""
import datetime as dt

from kit.tile import TileKit


class FakeSite(TileKit):
    """Only what week_tag (and its own _tile_release_seed helper) touch: self.films, self.now."""

    def __init__(self, films, now):
        self.films = films
        self.now = now


NOW = dt.datetime.fromisoformat("2026-09-30T12:00:00+04:00")


def _site(rel=None, first_seen=None, archived=False, seed=None):
    f = {"status": "archived" if archived else "showing"}
    if rel is not None:
        f["released"] = rel
    if first_seen is not None:
        f["first_seen"] = first_seen
    films = {"x": f}
    if seed is not None:
        films["seed-film"] = {"first_seen": seed}
    return FakeSite(films, NOW)


def test_first_week_is_new():
    site = _site(rel="2026-09-30")   # released today: day 0
    assert site.week_tag("x", "ar") == "جديد"
    assert site.week_tag("x", "en") == "New"


def test_day_six_is_still_first_week():
    site = _site(rel="2026-09-24")   # 6 days old: still week 1
    assert site.week_tag("x", "ar") == "جديد"


def test_day_seven_rolls_into_week_two():
    site = _site(rel="2026-09-23")   # 7 days old: week 2 starts
    assert site.week_tag("x", "ar") == "الأسبوع 2"
    assert site.week_tag("x", "en") == "Week 2"


def test_day_fourteen_is_week_three():
    site = _site(rel="2026-09-16")   # 14 days old
    assert site.week_tag("x", "ar") == "الأسبوع 3"


def test_prefers_released_over_first_seen():
    site = _site(rel="2026-09-23", first_seen="2026-09-01")
    assert site.week_tag("x", "ar") == "الأسبوع 2"


def test_falls_back_to_first_seen_when_no_released():
    # an earlier-first_seen sibling film so "2026-09-23" isn't itself the catalogue-wide seed date
    site = _site(first_seen="2026-09-23", seed="2026-01-01")
    assert site.week_tag("x", "ar") == "الأسبوع 2"


def test_archived_film_gets_no_label():
    site = _site(rel="2026-09-30", archived=True)
    assert site.week_tag("x", "ar") is None


def test_no_date_at_all_gets_no_label():
    site = _site()
    assert site.week_tag("x", "ar") is None


def test_bare_first_seen_equal_to_the_tracking_seed_is_not_a_release_date():
    """A film whose only date is the earliest first_seen across the whole catalogue did not necessarily open
    that day -- it may be much older, tracking just started then (same honesty rule as the film page's own
    week line, pages/_core/film.py's _release_seed)."""
    site = _site(first_seen="2026-09-01", seed="2026-09-01")
    assert site.week_tag("x", "ar") is None


def test_future_release_date_gets_no_label():
    site = _site(rel="2026-10-05")   # not open yet
    assert site.week_tag("x", "ar") is None


def test_film_tile_shows_the_week_label_when_no_other_tag(monkeypatch):
    """film_tile's own precedence: an explicit tag wins, then «إعادة عرض», then week_tag -- never stacked."""
    import site_kit

    class TinySite(site_kit.Kit):
        pass

    films = {"x": {"status": "showing", "title": "Film X", "title_ar": "فيلم اكس", "released": "2026-09-23",
                   "runtime": 100}}
    site = TinySite.__new__(TinySite)
    site.films = films
    site.now = NOW
    site.today = "2026-09-30"
    site._by_film = {}
    site.d = {"people": {}}
    site.disc = {}
    site.cards = {}

    html = site.film_tile("x", "ar", [], live=False)
    assert '<span class="tag wk">الأسبوع 2</span>' in html
    assert "الأسبوع 2" not in site.film_tile("x", "ar", [], live=False, row=True)   # curated home row: no tag

    films["x"]["rerelease"] = True
    html_rerelease = site.film_tile("x", "ar", [], live=False)
    assert "إعادة عرض" in html_rerelease and "الأسبوع 2" not in html_rerelease
