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
