"""Tests for normalize.merge() and normalize.city_slices() — run with `python -m pytest` from
the repo root (saas/cinema) so normalize.py is importable without a conftest.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import normalize  # noqa: E402

NOW = "2026-09-25T20:00:00"

VOX_CINEMA = {
    "id": "vox-al-jimi-mall",
    "chain": "vox",
    "name": "VOX Cinemas Al Jimi Mall",
    "name_ar": None,
    "city": "al-ain",
    "mall": "Al Jimi Mall",
    "address": "Al Jimi Mall, Al Ain",
    "maps": None,
    "lat": None,
    "lng": None,
}

STAR_CINEMA = {
    "id": "star-bawadi-mall",
    "chain": "star",
    "name": "Star Cinemas Bawadi Mall",
    "name_ar": None,
    "city": "al-ain",
    "mall": "Bawadi Mall",
    "address": "Bawadi Mall, Al Ain",
    "maps": None,
    "lat": None,
    "lng": None,
}


def show(**kw):
    base = {
        "cinema": "vox-al-jimi-mall",
        "film_title": "Heart of the Beast",
        "film_lang": "English",
        "film_rating": "PG13",
        "runtime": 105,
        "date": "2026-09-25",
        "time": "19:30",
        "hall": "Standard",
        "hall_label": "CINEMA 3",
        "prices": [{"seat": "Regular", "aed": 46.0}],
        "book": "https://uae.voxcinemas.com/book/1",
    }
    base.update(kw)
    return base


def test_two_chains_merge_to_one_film():
    results = {
        "vox": {
            "cinemas": [VOX_CINEMA],
            "shows": [show(film_title="Heart of the Beast")],
        },
        "star": {
            "cinemas": [STAR_CINEMA],
            "shows": [
                show(
                    cinema="star-bawadi-mall",
                    film_title="HEART OF THE BEAST (PG13)",
                    hall="Standard",
                    hall_label="STAR SELECT",
                    time="20:15",
                    prices=[{"seat": "STAR SELECT", "aed": 42.0}],
                    book="https://starcinemas.ae/book/2",
                )
            ],
        },
    }

    data = normalize.merge(results, previous=None, now=NOW)

    assert list(data["films"].keys()) == ["heart-of-the-beast"]
    film = data["films"]["heart-of-the-beast"]
    assert film["title"] == "Heart of the Beast"
    assert set(film["chains"]) == {"vox", "star"}
    assert len(data["shows"]) == 2
    for s in data["shows"]:
        assert s["film"] == "heart-of-the-beast"
        for dropped in ("film_title", "film_lang", "film_rating", "runtime", "poster"):
            assert dropped not in s
    assert data["chains"]["vox"] == {"ok": True, "at": NOW, "error": None}
    assert data["chains"]["star"] == {"ok": True, "at": NOW, "error": None}


def test_failed_chain_keeps_previous_shows_and_marks_not_ok():
    previous = {
        "generated": "2026-09-25T14:00:00",
        "chains": {"vox": {"ok": True, "at": "2026-09-25T14:00:00", "error": None}},
        "cinemas": {"vox-al-jimi-mall": VOX_CINEMA},
        "films": {
            "heart-of-the-beast": {
                "title": "Heart of the Beast",
                "lang": "English",
                "rating": "PG13",
                "runtime": 105,
                "genres": None,
                "poster": None,
                "chains": ["vox"],
            }
        },
        "shows": [
            {
                "cinema": "vox-al-jimi-mall",
                "film": "heart-of-the-beast",
                "date": "2026-09-25",
                "time": "22:00",
                "hall": "Standard",
                "hall_label": "CINEMA 3",
                "prices": [{"seat": "Regular", "aed": 46.0}],
                "book": "https://uae.voxcinemas.com/book/1",
            }
        ],
    }

    results = {"vox": None}
    data = normalize.merge(results, previous=previous, now=NOW)

    assert data["chains"]["vox"]["ok"] is False
    assert data["chains"]["vox"]["at"] == "2026-09-25T14:00:00"
    assert data["chains"]["vox"]["error"]
    assert data["cinemas"]["vox-al-jimi-mall"] == VOX_CINEMA
    assert len(data["shows"]) == 1
    assert data["shows"][0]["film"] == "heart-of-the-beast"


def test_past_shows_are_dropped():
    results = {
        "vox": {
            "cinemas": [VOX_CINEMA],
            "shows": [
                show(time="19:30"),  # 30 min before NOW: kept (at the -30min boundary)
                show(time="10:00"),  # long past: dropped
            ],
        }
    }
    data = normalize.merge(results, previous=None, now=NOW)
    assert len(data["shows"]) == 1
    assert data["shows"][0]["time"] == "19:30"


def test_tz_aware_now_is_treated_as_dubai_local():
    # 2026-09-26T01:00:00+04:00 == 2026-09-25T21:00:00+00:00 (same instant, Dubai is UTC+4).
    # Cutoff (30 min before) is Dubai-local 2026-09-26 00:30. A show at 00:45 is kept, one at
    # 23:00 the previous evening is dropped. This must not raise even though `now` is aware
    # while show date/time strings are naive (normalize.py:146 TypeError, now fixed).
    results = {
        "vox": {
            "cinemas": [VOX_CINEMA],
            "shows": [
                show(date="2026-09-26", time="00:45"),
                show(date="2026-09-25", time="23:00"),
            ],
        }
    }
    for now in ("2026-09-26T01:00:00+04:00", "2026-09-25T21:00:00+00:00"):
        data = normalize.merge(results, previous=None, now=now)
        assert len(data["shows"]) == 1, now
        assert data["shows"][0]["time"] == "00:45", now


def test_trailing_3d_dash_is_fully_stripped():
    assert normalize.clean_title("Heart of the Beast - 3D") == "Heart of the Beast"
    assert normalize.clean_title("Heart of the Beast 3D") == "Heart of the Beast"
    # "Encore" is a different release, never stripped.
    assert normalize.clean_title("Avengers Endgame: Encore") == "Avengers Endgame: Encore"


def test_chain_absent_from_results_is_marked_stale_not_dropped():
    previous = {
        "generated": "2026-09-25T14:00:00",
        "chains": {
            "vox": {"ok": True, "at": "2026-09-25T14:00:00", "error": None},
            "star": {"ok": True, "at": "2026-09-25T14:00:00", "error": None},
        },
        "cinemas": {"vox-al-jimi-mall": VOX_CINEMA, "star-bawadi-mall": STAR_CINEMA},
        "films": {
            "heart-of-the-beast": {
                "title": "Heart of the Beast",
                "lang": "English",
                "rating": "PG13",
                "runtime": 105,
                "genres": None,
                "poster": None,
                "chains": ["star"],
            }
        },
        "shows": [
            {
                "cinema": "star-bawadi-mall",
                "film": "heart-of-the-beast",
                "date": "2026-09-25",
                "time": "22:00",
                "hall": "Standard",
                "hall_label": "STAR SELECT",
                "prices": [{"seat": "STAR SELECT", "aed": 42.0}],
                "book": "https://starcinemas.ae/book/2",
            }
        ],
    }

    # "star" is not run this cycle at all — not even a None entry.
    results = {"vox": {"cinemas": [VOX_CINEMA], "shows": []}}
    data = normalize.merge(results, previous=previous, now=NOW)

    assert data["chains"]["star"] == {"ok": False, "at": "2026-09-25T14:00:00", "error": "not run"}
    assert data["cinemas"]["star-bawadi-mall"] == STAR_CINEMA
    assert len(data["shows"]) == 1
    assert data["shows"][0]["cinema"] == "star-bawadi-mall"


def test_city_slices_only_contains_its_city():
    dubai_cinema = {**VOX_CINEMA, "id": "vox-mall-of-the-emirates", "city": "dubai"}
    results = {
        "vox": {
            "cinemas": [VOX_CINEMA, dubai_cinema],
            "shows": [
                show(cinema="vox-al-jimi-mall"),
                show(cinema="vox-mall-of-the-emirates"),
            ],
        }
    }
    data = normalize.merge(results, previous=None, now=NOW)
    slices = normalize.city_slices(data)

    assert set(slices.keys()) == {"al-ain", "dubai"}
    al_ain = slices["al-ain"]
    assert list(al_ain["cinemas"].keys()) == ["vox-al-jimi-mall"]
    assert all(s["cinema"] == "vox-al-jimi-mall" for s in al_ain["shows"])
    dubai = slices["dubai"]
    assert list(dubai["cinemas"].keys()) == ["vox-mall-of-the-emirates"]
    assert all(s["cinema"] == "vox-mall-of-the-emirates" for s in dubai["shows"])


# ---------------------------------------------------------------- cross-chain duplicates (fix wave A)

def _acc(title, runtime=None, lang=None):
    return {"title": title, "runtime": runtime, "lang": lang, "rating": None, "poster": None,
            "title_ar": None, "chains": {"x"}}


def _merge(*accs, aliases=None):
    films = {normalize.film_fid(a["title"]): a for a in accs}
    return normalize.merge_duplicates(films, aliases or {}, {})


import pytest  # noqa: E402


@pytest.mark.parametrize("a, b, canon", [
    (_acc("The Vvaan: Force of the Forest", 130, "Hindi"), _acc("The Vvaan: Force of the Forrest", 165, "Hindi"), None),
    (_acc("The Vvaan", 130, "Hindi"), _acc("The Vvaan: Force of the Forest", 130, "Hindi"), "the-vvaan-force-of-the-forest"),
    (_acc("The Smurfs Timeless Adventure Volume 2", 85, "English"), _acc("The Smurf Timeless Adventure Volume 2", 80, "English"),
     "the-smurfs-timeless-adventure-volume-2"),
    (_acc("Butterfly Effect Azzam", 90, "Arabic"), _acc("The Butterfly Effect: Azzam", 90, "Arabic"), "the-butterfly-effect-azzam"),
    (_acc("Buttery Effect Azzam", 90, "Arabic"), _acc("Butterfly Effect Azzam", 90, "Arabic"), None),
    (_acc("Fall 2", 100, "English"), _acc("Fall 2: Deadpoint", 100, "English"), "fall-2-deadpoint"),
    (_acc("Insidious", 105, "English"), _acc("Insidious: Out Of The Further", 105, "English"), "insidious-out-of-the-further"),
    (_acc("Minions Monsters", 120, "English"), _acc("Minions & Monsters", 120, "English"), "minions-and-monsters"),
    (_acc("Mirzapur", 210, "Hindi"), _acc("Mirzapur: The Movie", 210, "Hindi"), "mirzapur-the-movie"),
    (_acc("Dhoomakethu", 130, "Malayalam"), _acc("Dhoomaketu", 125, "Malayalam"), "dhoomakethu"),
    (_acc("Bethlahem Kudumba Unit", 155, "Malayalam"), _acc("Bethlehem Kudumba Unit", 165, "Malayalam"), None),
])
def test_listed_duplicates_merge_automatically(a, b, canon):
    out, mapping = _merge(a, b)
    assert len(out) == 1, (a["title"], b["title"])
    if canon:
        assert list(out) == [canon]


def test_moana_live_action_merges_by_alias():
    aliases = normalize.load_aliases()
    out, mapping = _merge(_acc("Moana", 120, "English"), _acc("Moana Live Action", 120, "English"), aliases=aliases)
    assert list(out) == ["moana"] and mapping == {"moana-live-action": "moana"}


def test_aliases_yaml_picks_the_correct_spelling_and_title():
    aliases = normalize.load_aliases()
    out, mapping = _merge(_acc("The Vvaan: Force of the Forrest", 165, "Hindi"), _acc("The Vvaan: Force of the Forest", 130, "Hindi"),
                          aliases=aliases)
    assert list(out) == ["the-vvaan-force-of-the-forest"]
    assert out["the-vvaan-force-of-the-forest"]["title"] == "The Vvaan: Force of the Forest"
    # an alias applies even when only the misspelt listing is on today
    out, mapping = _merge(_acc("Buttery Effect Azzam", 90, "Arabic"), aliases=aliases)
    assert list(out) == ["the-butterfly-effect-azzam"] and mapping == {"buttery-effect-azzam": "the-butterfly-effect-azzam"}
    out, _ = _merge(_acc("Bethlahem Kudumba Unit", 155, "Malayalam"), _acc("Bethlehem Kudumba Unit", 165, "Malayalam"), aliases=aliases)
    assert list(out) == ["bethlehem-kudumba-unit"]


@pytest.mark.parametrize("a, b", [
    (_acc("Fall", 107, "English"), _acc("Fall 2", 100, "English")),
    (_acc("Fall", 100, "English"), _acc("Fall 2: Deadpoint", 100, "English")),
    (_acc("Moana 2", 100, "English"), _acc("Moana", 100, "English")),
    (_acc("Toy Story 4", 100, "English"), _acc("Toy Story 5", 100, "English")),
    (_acc("The Smurfs Timeless Adventure Volume 2", 85, "English"), _acc("The Smurfs Timeless Adventure Volume 3", 85, "English")),
    (_acc("Cats in the Museum: Treasures of Egypt", 90, "English"), _acc("Cats in The Museum 2:Treasures of Egypt", 90, "English")),
    (_acc("Avengers Endgame", 181, "English"), _acc("Avengers Endgame: Encore", 181, "English")),
    (_acc("Mirzapur", 150, "Hindi"), _acc("Mirzapur: The Movie", 210, "Hindi")),   # subtitle, but runtimes an hour apart
    (_acc("Revolver", 120, "Korean"), _acc("Revolvers", 95, "English")),          # near spelling, nothing else agrees
])
def test_sequels_and_different_films_stay_apart(a, b):
    out, mapping = _merge(a, b)
    assert len(out) == 2 and mapping == {}, (a["title"], b["title"])


def test_merge_rewrites_shows_and_records_the_mapping():
    results = {
        "vox": {"cinemas": [VOX_CINEMA], "shows": [show(film_title="The Vvaan: Force of the Forrest", runtime=165, film_lang="Hindi")]},
        "star": {"cinemas": [STAR_CINEMA], "shows": [show(cinema="star-bawadi-mall", film_title="THE VVAAN: FORCE OF THE FOREST",
                                                          runtime=130, film_lang="Hindi", film_title_ar="ذا فان")]},
    }
    data = normalize.merge(results, previous=None, now=NOW)
    assert list(data["films"]) == ["the-vvaan-force-of-the-forest"]
    assert {s["film"] for s in data["shows"]} == {"the-vvaan-force-of-the-forest"}
    assert data["merged"] == {"the-vvaan-force-of-the-forrest": "the-vvaan-force-of-the-forest"}
    f = data["films"]["the-vvaan-force-of-the-forest"]
    assert set(f["chains"]) == {"vox", "star"} and f["title"] == "The Vvaan: Force of the Forest"
    assert f["title_ar_chain"] == "ذا فان"
    assert all("film_title_ar" not in s for s in data["shows"])


def test_chain_arabic_titles_are_cleaned_and_english_copies_dropped():
    from readers.common import arabic_title
    assert arabic_title("انترستيلر (إعادة اصدار)") == "انترستيلر"
    assert arabic_title("بريشـر") == "بريشر"
    assert arabic_title("Sacrifice") is None and arabic_title("") is None and arabic_title(None) is None
