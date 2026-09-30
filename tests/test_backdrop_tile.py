"""kit/media.py MediaKit.poster's `backdrop_fallback` (296, r4-home, owner idea 2026-09-30): a poster-less
tile with a trailer backdrop (steps/backdrops.py) draws a 2:3 crop of that frame, darkened, with the title kept
over it -- instead of the flat colour tile. The flat tile stays the fallback when there is neither, and every
OTHER caller of poster() (the film hero card, insights, places -- none of which pass the flag) is untouched:
this is opt-in per call site, not a change to poster()'s default behaviour."""
import site_kit


class TinySite(site_kit.Kit):
    pass


def _site(films):
    site = TinySite.__new__(TinySite)
    site.films = films
    site._first_poster = None
    return site


POSTER_FILM = {"title": "Poster Film", "title_ar": "فيلم بوستر", "poster": "/posters/p1-342.webp", "poster_2x": "/posters/p1-684.webp"}
BD_FILM = {"title": "Backdrop Film", "title_ar": "فيلم خلفية",
           "backdrop": {"w1280": "/posters/bd-x-1280.webp", "w640": "/posters/bd-x-640.webp", "w": 1280, "h": 720, "x": 0.25}}
BD_PORTRAIT_FILM = {"title": "Portrait Film", "title_ar": "فيلم عمودي",
                     "backdrop": {"w1280": "/posters/bd-y-1280.webp", "w640": "/posters/bd-y-640.webp", "w": 1280, "h": 720,
                                  "p": "/posters/bd-y-hash-p.webp", "pw": 720, "ph": 1080}}
BARE_FILM = {"title": "Bare Film", "title_ar": "فيلم عادي"}


def test_a_real_poster_still_wins_even_with_backdrop_fallback_on():
    site = _site({"x": dict(POSTER_FILM, backdrop=BD_FILM["backdrop"])})
    html = site.poster("x", "ar", backdrop_fallback=True)
    assert 'class="pst img"' in html and "bd-x" not in html and "p1-342.webp" in html


def test_no_poster_no_backdrop_flag_falls_back_to_the_flat_tile():
    """The default (backdrop_fallback=False, every existing caller): a backdrop is never drawn -- the flat
    colour tile stays exactly as it was, so the film hero card, insights and places are unaffected."""
    site = _site({"x": BD_FILM})
    html = site.poster("x", "ar")
    assert 'class="pst"' in html and "bd-x" not in html and "فيلم خلفية" in html


def test_no_poster_with_backdrop_flag_on_draws_the_landscape_frame_cropped():
    site = _site({"x": BD_FILM})
    html = site.poster("x", "ar", backdrop_fallback=True)
    assert 'class="pst bd img"' in html
    assert "bd-x-640.webp" in html and "bd-x-1280.webp" in html   # srcset carries both widths
    assert "--x:25%" in html                                       # the frame's own window
    assert "فيلم خلفية" in html and 'aria-hidden="true"' not in html.split("pst-t")[1][:40]   # the title stays visible


def test_the_ready_made_portrait_crop_is_preferred_when_w1_d1_wrote_one():
    site = _site({"x": BD_PORTRAIT_FILM})
    html = site.poster("x", "ar", backdrop_fallback=True)
    assert 'class="pst bd img"' in html
    assert "bd-y-hash-p.webp" in html and 'width="720" height="1080"' in html
    assert "bd-y-1280.webp" not in html   # the portrait file alone -- no landscape srcset alongside it


def test_neither_poster_nor_backdrop_is_still_the_flat_tile():
    site = _site({"x": BARE_FILM})
    html = site.poster("x", "ar", backdrop_fallback=True)
    assert 'class="pst"' in html and "bd" not in html.split("style=")[0]
    assert "فيلم عادي" in html


def test_film_tile_passes_the_flag_through():
    """kit/tile.py's film_tile (home rows, the grid) opts in; the film hero card (pages/_core/film.py) does
    not, so a backdrop-only film's poster CARD there is still the flat tile -- what its own picture layer
    (Kit.backdrop, drawn separately) already shows full-bleed behind it."""
    films = {"x": dict(BD_FILM, status="showing", runtime=100)}
    site = TinySite.__new__(TinySite)   # site_kit.Kit already mixes in TileKit (site_kit.py's own class line)
    site.films = films
    site._first_poster = None
    site.now = None
    site.today = "2026-09-30"
    site._by_film = {}
    site.d = {"people": {}}
    site.disc = {}
    site.cards = {}
    site._grid = False
    site._sheets = []

    html = site.film_tile("x", "ar", [], live=False)
    assert 'class="pst bd img"' in html


def test_show_card_also_opts_in():
    """The source call, not a full render (show_card needs a whole cinemas/site fixture beyond this file's
    scope) -- catches the flag being dropped in a future edit."""
    import inspect

    import kit.tile as tile_mod

    src = inspect.getsource(tile_mod.TileKit.show_card)
    assert "backdrop_fallback=True" in src
