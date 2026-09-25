"""Tests for price_table.load()/fill() — run with `python -m pytest` from the repo root
(saas/cinema) so price_table.py is importable without a conftest.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import price_table  # noqa: E402


def _cinema(cid, chain):
    return {"id": cid, "chain": chain, "name": cid, "name_ar": None, "city": "al-ain",
            "mall": None, "address": None, "maps": None, "lat": None, "lng": None}


def _show(cinema, hall, prices=None):
    return {"film_title": "Test Film", "date": "2026-09-26", "time": "20:00", "hall": hall,
            "hall_label": hall, "prices": prices, "book": "https://example.test/book",
            "cinema": cinema}


TABLE = {
    "vox": {
        "vox-al-jimi-mall": {
            "Standard": {
                "seats": [{"seat": "Regular", "aed": 46}],
                "source": "test", "checked": "2026-09-25", "method": "seat_sample", "confidence": "official",
            }
        },
        "*": {
            "Standard": {
                "seats": [{"seat": "Regular", "aed": 99}],
                "source": "test", "checked": "2026-09-25", "method": "seat_sample", "confidence": "official",
            }
        },
    }
}


def test_cinema_specific_entry_wins_over_star_entry():
    data = {
        "cinemas": {"vox-al-jimi-mall": _cinema("vox-al-jimi-mall", "vox")},
        "shows": [_show("vox-al-jimi-mall", "Standard")],
    }
    filled = price_table.fill(data, TABLE)
    assert filled == 1
    show = data["shows"][0]
    assert show["prices"] == [{"seat": "Regular", "aed": 46}]
    assert show["price_source"] == "table"
    assert show["price_checked"]


def test_star_entry_used_when_no_cinema_specific_entry():
    data = {
        "cinemas": {"vox-some-other-mall": _cinema("vox-some-other-mall", "vox")},
        "shows": [_show("vox-some-other-mall", "Standard")],
    }
    filled = price_table.fill(data, TABLE)
    assert filled == 1
    assert data["shows"][0]["prices"] == [{"seat": "Regular", "aed": 99}]


def test_live_prices_are_never_overwritten():
    live = [{"seat": "VIP", "aed": 52.5}]
    data = {
        "cinemas": {"vox-al-jimi-mall": _cinema("vox-al-jimi-mall", "vox")},
        "shows": [_show("vox-al-jimi-mall", "Standard", prices=live)],
    }
    filled = price_table.fill(data, TABLE)
    assert filled == 0
    show = data["shows"][0]
    assert show["prices"] == live
    assert "price_source" not in show


def test_hall_missing_from_table_stays_null():
    data = {
        "cinemas": {"vox-al-jimi-mall": _cinema("vox-al-jimi-mall", "vox")},
        "shows": [_show("vox-al-jimi-mall", "IMAX")],
    }
    filled = price_table.fill(data, TABLE)
    assert filled == 0
    show = data["shows"][0]
    assert show["prices"] is None
    assert "price_source" not in show


def test_chain_missing_from_table_stays_null():
    data = {
        "cinemas": {"roxy-city-walk": _cinema("roxy-city-walk", "roxy")},
        "shows": [_show("roxy-city-walk", "Standard")],
    }
    filled = price_table.fill(data, TABLE)
    assert filled == 0
    assert data["shows"][0]["prices"] is None


def test_fill_accepts_a_list_of_cinemas_like_a_raw_reader_output():
    data = {
        "cinemas": [_cinema("vox-al-jimi-mall", "vox")],
        "shows": [_show("vox-al-jimi-mall", "Standard")],
    }
    filled = price_table.fill(data, TABLE)
    assert filled == 1


def test_real_prices_yaml_loads_and_every_entry_is_fully_sourced():
    table = price_table.load()
    assert table, "prices.yaml should not be empty"
    required = {"seats", "source", "checked", "method", "confidence"}
    for chain, cinemas in table.items():
        for cinema_id, halls in cinemas.items():
            for hall, entry in halls.items():
                missing = required - entry.keys()
                assert not missing, f"{chain}/{cinema_id}/{hall} missing {missing}"
                assert entry["method"] in ("official_page", "app_api", "third_party", "seat_sample")
                assert entry["confidence"] in ("official", "third-party")
                assert entry["seats"], f"{chain}/{cinema_id}/{hall} has no seats"
                for seat in entry["seats"]:
                    assert isinstance(seat["aed"], (int, float)) and seat["aed"] > 0
