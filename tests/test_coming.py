"""coming.py: each chain's own parser, and fetch_all()'s per-chain isolation (Task 2)."""
import coming


def test_iso_date_formats():
    assert coming._iso_date("2026-10-08T12:00:00Z") == "2026-10-08"
    assert coming._iso_date("01 October 2026") == "2026-10-01"
    assert coming._iso_date("8  October,  2026") == "2026-10-08"
    assert coming._iso_date(None) is None
    assert coming._iso_date("not a date") is None


def test_parse_novo_filters_the_real_coming_soon_signal():
    # movie_is_coming_soon is true even for now-showing films (docs/probe/novo.md) -- only
    # coming_soon_order (non-null) means "not yet playing".
    payload = {"data": {"movies": [
        {"movie_title": "Sacrifice", "movie_is_coming_soon": True, "coming_soon_order": None,
         "now_showing_order": 1, "movie_release_date": "2026-09-24T00:00:00"},
        {"movie_title": "Heart Of The Beast", "movie_title_ar": "قلب الوحش",
         "movie_is_coming_soon": True, "coming_soon_order": 3, "now_showing_order": 5,
         "movie_release_date": "2026-09-25T00:00:00", "movie_image_url": "https://x/img.jpg",
         "movie_trailer_link": "https://www.youtube.com/watch?v=bdPnr4mJoIU",
         "movie_genre": [{"genre_name": "Action"}]},
    ]}}
    out = coming._parse_novo(payload)
    assert len(out) == 1
    item = out[0]
    assert item["title"] == "Heart Of The Beast" and item["title_ar"] == "قلب الوحش"
    assert item["release_date"] == "2026-09-25" and item["trailer"] == "bdPnr4mJoIU"
    assert item["genres"] == ["Action"] and item["chain"] == "novo"


def test_parse_star():
    payload = {"Records": {"data": [
        {"movie_title": "Gatto", "mrrdr_release_date": "2027-03-25",
         "md_thumbnail_url": "https://x/gatto.jpg", "genre_name": "Adventure,Comedy"},
    ]}}
    out = coming._parse_star(payload)
    assert out == [{"title": "Gatto", "title_ar": None, "release_date": "2027-03-25",
                     "poster": "https://x/gatto.jpg", "trailer": None,
                     "genres": ["Adventure", "Comedy"], "chain": "star"}]


VOX_HTML = """
<article  class="movie-summary hero" data-slug="verity"data-title="Verity">
  <div class="trailer"><div class="player"><iframe src="https://www.youtube.com/embed/abc?rel=0"></iframe></div></div>
</article>
<article  class="movie-summary" data-slug="digger"data-title="Digger">
  <a href="/movies/digger"><img class="poster" src="https://assets.example/digger.png"  alt="Digger" /></a>
  <div><h3><a href="/movies/digger">Digger</a></h3>
  <p><strong>Release Date:</strong> 01 October 2026<br /><strong>Starring:</strong> Someone<br /></p></div>
</article>
"""


def test_parse_vox():
    out = coming._parse_vox(VOX_HTML)
    assert [i["title"] for i in out] == ["Verity", "Digger"]
    verity, digger = out
    assert verity["poster"] is None  # the hero article has no img.poster -- handled, not guessed
    assert digger["poster"] == "https://assets.example/digger.png"
    assert digger["release_date"] == "2026-10-01"


def test_parse_reel_excludes_now_showing_rereleases():
    payload = {"value": [
        {"ID": "HO1", "Title": "Interstellar (2014)", "IsComingSoon": True, "IsScheduledAtCinema": True,
         "OpeningDate": "2026-09-14T00:00:00"},  # a re-release, already playing -- not coming-soon
        {"ID": "HO2", "Title": "The Cat In The Hat", "IsComingSoon": True, "IsScheduledAtCinema": False,
         "OpeningDate": "2026-11-05T00:00:00", "TrailerUrl": "https://youtu.be/xyz1234567z"},
    ]}
    out = coming._parse_reel(payload, "https://posters.example/{}.jpg")
    assert len(out) == 1
    assert out[0]["title"] == "The Cat In The Hat"
    assert out[0]["poster"] == "https://posters.example/HO2.jpg"
    assert out[0]["release_date"] == "2026-11-05"
    assert out[0]["trailer"] == "xyz1234567z"


ROXY_HTML = """
<div class="coh-accordion-tabs-content advance-booking-tab">should never be scanned</div>
<div class="coh-accordion-tabs-content coming-soon-tab">
<article data-history-node-id="177711">
<h2 class="coh-heading movie-title"> Reckless </h2>
<p class="coh-paragraph movie-genre">Action, Thriller</p>
<img src="/sites/default/files/reckless.jpg">
<p class="coh-paragraph"><span>Release Date:</span> <time datetime="2026-10-08T12:00:00Z">8 October, 2026</time></p>
</article>
</div>
"""


def test_parse_roxy_only_reads_the_coming_soon_tab():
    out = coming._parse_roxy(ROXY_HTML, "https://www.theroxycinemas.com")
    assert len(out) == 1
    item = out[0]
    assert item["title"] == "Reckless" and item["genres"] == ["Action", "Thriller"]
    assert item["poster"] == "https://www.theroxycinemas.com/sites/default/files/reckless.jpg"
    assert item["release_date"] == "2026-10-08"


CINEROYAL_HTML = """
<h2 id='target_comingSoon'>Coming Soon</h2>
<div class="col-sm-12 col-md-12 pull-left" id="comingSoon" style="display: none">
  <div class="movie movie--test movie--test--dark movie--test--left">
    <div class="movie__images">
      <a href="/home/chooseScreen/digger" class="movie-beta__link">
        <img alt='' src="https://s3.amazonaws.com/x/digger.jpg">
      </a>
      <div class="movie__info">
        <a href="/home/chooseScreen/digger" class="movie__title">DIGGER</a>
        <p class="movie__option"><a href="/home/chooseScreen/digger"></a><a href="/home/chooseScreen/digger">Comedy,Drama</a></p>
      </div>
    </div>
  </div>
</div>
"""


def test_parse_cineroyal():
    out = coming._parse_cineroyal(CINEROYAL_HTML)
    assert out == [{"title": "DIGGER", "title_ar": None, "release_date": None,
                     "poster": "https://s3.amazonaws.com/x/digger.jpg", "trailer": None,
                     "genres": ["Comedy", "Drama"], "chain": "cineroyal"}]


def test_fetch_cinemacity_always_raises_isolated():
    import pytest

    with pytest.raises(RuntimeError):
        coming.fetch_cinemacity()


def test_fetch_all_isolates_one_chains_failure(monkeypatch):
    monkeypatch.setattr(coming, "GAP", 0)

    def boom():
        raise RuntimeError("boom")

    out = coming.fetch_all(chains=["novo", "star"],
                            fetchers={"novo": boom, "star": lambda: [{"title": "X"}]})
    assert out["novo"]["ok"] is False and "boom" in out["novo"]["error"] and out["novo"]["items"] == []
    assert out["star"]["ok"] is True and out["star"]["items"] == [{"title": "X"}]
